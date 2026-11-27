"""Podcast epizoda: poglavlja za YouTube i MP3 za podcast platforme (M4.4a)

  python epizoda.py shofe_projekt poglavlja [--verzija N]       reel_vN.poglavlja.txt + reel_vN.chapters.json
  python epizoda.py shofe_projekt mp3 [--verzija N] [--kbps 128] [--naslov "..."] [--autor "..."] [--slika x.jpg]
                                                                 reel_vN.mp3 (−16 LUFS, ID3 poglavlja)

Poglavlja su teme iz analiza.json ("teme", Claude ih piše u vremenu izvorne snimke) prevedene u vrijeme
gotovog videa (izrezi, izbačeni odsječci, brzina), plus svaka zadržana pjesma kao svoje poglavlje.
Pravila YouTubea: prvo poglavlje u 00:00, barem 3, svako barem 10 s, uzlazno.
"""
import argparse
import math
import re
import sys
from pathlib import Path

from common import die, ffmpeg, fmt_time, load_json, run, save_json

MIN_POGLAVLJE = 10.0        # s, YouTube minimum
MIN_BROJ = 3                # YouTube prikazuje poglavlja tek od 3
MP3_CILJ = -16.0            # LUFS, Apple Podcasts (±1), AES TD1008 za stereo
MP3_TP = -1.0               # dBTP najviše
MP3_LIMIT_DB = -2.0         # vrh uzorka iza limitera na 192 kHz (true peak ostaje ispod −1 dBTP i nakon MP3)
MP3_KBPS = 128              # stereo, 44,1 kHz: Apple preporučuje 128–256 kbps za stereo MP3
ZADANI_AUTOR = "Sunčani4M"


# ---------------------------------------------------------------- poglavlja
def _cist(naslov):
    t = re.sub(r"[<>]", "", str(naslov or "")).strip()   # YouTube ne dopušta < > u opisu
    return re.sub(r"\s+", " ", t)


def naziv_pjesme(n, k):
    name = _cist(n.get("naziv"))
    return f"Pjesma: {name}" if name else ("Nastup benda" if k == 0 else f"Nastup benda {k + 1}")


def komadi(teme, pjesme):
    """Dijelovi u izvornom vremenu: [(od, do, naslov, vrsta)]. Pjesma je svoje poglavlje; tema koju pjesma
    prekine nastavlja se nakon nje kao „naslov (nastavak)"."""
    song_r = sorted((float(n["od"]), float(n["do"]), naziv_pjesme(n, k)) for k, n in enumerate(pjesme))
    out = [(a, b, t, "pjesma") for a, b, t in song_r]
    for t in sorted(teme, key=lambda x: float(x["od"])):
        a, b = float(t["od"]), float(t["do"])
        title = _cist(t.get("naslov")) or "Tema"
        pieces = [(a, b)]
        for sa, sb, _ in song_r:
            nxt = []
            for pa, pb in pieces:
                if sb <= pa or sa >= pb:
                    nxt.append((pa, pb))
                    continue
                if sa > pa:
                    nxt.append((pa, sa))
                if sb < pb:
                    nxt.append((sb, pb))
            pieces = nxt
        pieces = [(pa, pb) for pa, pb in pieces if pb - pa > 1e-3]
        for i, (pa, pb) in enumerate(pieces):
            out.append((pa, pb, title if i == 0 else f"{title} (nastavak)", "tema"))
    return sorted(out)


def u_gotovom(a, b, cuts):
    """Prvi trenutak dijela [a, b) izvornog videa u gotovom videu i koliko ga je ostalo (prije brzine)."""
    start, kept = None, 0.0
    for c in cuts:
        lo, hi = max(a, c["a"]), min(b, c["b"])
        if hi - lo > 1e-3:
            if start is None:
                start = c["o"] + lo - c["a"]
            kept += hi - lo
    return start, kept


def slozi(teme, pjesme, cuts, trajanje, brzina=1.0, min_len=MIN_POGLAVLJE):
    """Poglavlja u vremenu gotovog videa: [{"od", "naslov", "vrsta"}], prvo u 0, svako ≥ min_len."""
    ch = []
    for a, b, title, kind in komadi(teme, pjesme):
        s, kept = u_gotovom(a, b, cuts)
        if s is None or kept < 0.5:
            continue
        ch.append({"od": s / brzina, "naslov": title, "vrsta": kind, "trajanje": kept / brzina})
    ch.sort(key=lambda c: c["od"])
    # dva dijela iste teme zaredom (između izrezano) = jedno poglavlje
    merged = []
    for c in ch:
        base = c["naslov"].replace(" (nastavak)", "")
        if merged and merged[-1]["naslov"].replace(" (nastavak)", "") == base and c["vrsta"] == merged[-1]["vrsta"]:
            continue
        if merged and c["od"] - merged[-1]["od"] < 1e-3:
            continue
        merged.append(c)
    ch = merged
    if not ch:
        return []
    ch[0]["od"] = 0.0                 # YouTube: prvo poglavlje u 00:00 (početak prije prve teme ide u nju)

    def dur(i):
        return (ch[i + 1]["od"] if i + 1 < len(ch) else trajanje) - ch[i]["od"]

    while len(ch) > 1:
        short = [i for i in range(len(ch)) if dur(i) < min_len]
        if not short:
            break
        i = min(short, key=dur)
        j = i - 1 if i > 0 else 1          # spoji s prethodnim (prvo: sa sljedećim)
        lo, hi = min(i, j), max(i, j)
        p_lo, p_hi = ch[lo]["vrsta"] == "pjesma", ch[hi]["vrsta"] == "pjesma"
        if p_lo != p_hi:                    # pjesma zadrži svoje ime, ostatak teme uz nju nestane
            keep = ch[lo] if p_lo else ch[hi]
        else:                               # inače ime duljeg dijela
            keep = ch[lo] if dur(lo) >= dur(hi) else ch[hi]
        new = dict(keep, od=ch[lo]["od"])
        ch[lo:hi + 1] = [new]
    for c in ch:
        c.pop("trajanje", None)
    return ch


def yt_vrijeme(t, sat):
    t = int(math.floor(t + 1e-6))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if sat else f"{m:02d}:{s:02d}"


def youtube_tekst(ch, trajanje):
    sat = trajanje >= 3600
    return "\n".join(f"{yt_vrijeme(c['od'], sat)} {c['naslov']}" for c in ch) + "\n"


def podcast_vrijeme(t, sat):
    t = int(math.floor(t + 1e-6))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if sat else f"{m:02d}:{s:02d}"


def podcast_tekst(ch, trajanje):
    """Poglavlja u opisu epizode za Spotify for Creators: MM:SS ili HH:MM:SS, prvo 00:00, jedno po retku."""
    sat = trajanje >= 3600
    return "\n".join(f"{podcast_vrijeme(c['od'], sat)} {c['naslov']}" for c in ch) + "\n"


def chapters_json(ch, trajanje):
    """Podcasting 2.0 JSON Chapters (podcastindex.org), za hostove koji ga primaju (<podcast:chapters>)."""
    out = []
    for i, c in enumerate(ch):
        end = ch[i + 1]["od"] if i + 1 < len(ch) else trajanje
        out.append({"startTime": round(c["od"], 2), "endTime": round(end, 2), "title": c["naslov"]})
    return {"version": "1.2.0", "chapters": out}


# ---------------------------------------------------------------- iz projekta
def odaberi(proj, verzija=None):
    """(edit, osnovno ime, opis, video ili None) za verziju koju korisnik gleda (ili zadanu)."""
    import titlovi
    import verzije
    edit, base, what = titlovi.pick(proj, verzija)
    if base == "titlovi_trenutno":
        base = "trenutno"
    video = None
    found = verzije.found_versions(proj)
    if found:
        v = verzija if verzija is not None else verzije.viewed(proj)
        vf = verzije.video_file(proj, v)
        video = (proj / vf) if vf else None
    return edit, base, what, video


def poglavlja_za(proj, edit, min_len=MIN_POGLAVLJE):
    """(poglavlja, trajanje gotovog videa, upozorenja) iz analiza.json teme + pjesme u edit.json."""
    import render
    proj = Path(proj)
    an = load_json(proj / "analiza.json") if (proj / "analiza.json").exists() else {}
    teme = [t for t in an.get("teme") or [] if isinstance(t, dict) and "od" in t and "do" in t]
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    st = render.resolve_style(edit)
    cuts, _, total = render.build_cuts(words, edit, st, pj["fps"], pj["duration"])
    speed = float(edit.get("brzina") or 1.0)
    pjesme = [n for n in sorted(edit.get("nastupi") or [], key=lambda n: float(n["od"]))
              if n.get("zadrzi", True) and float(n["do"]) > float(n["od"])]
    final = total / speed
    warn = []
    if not teme:
        warn.append("u analiza.json nema tema (\"teme\") — poglavlja su samo pjesme; Claude ih treba upisati")
    ch = slozi(teme, pjesme, cuts, final, speed, min_len)
    if len(ch) < MIN_BROJ:
        warn.append(f"samo {len(ch)} poglavlja: YouTube ih prikazuje tek od {MIN_BROJ} (i svako ≥ 10 s)")
    return ch, final, warn


def napisi_poglavlja(proj, edit, base, min_len=MIN_POGLAVLJE):
    ch, final, warn = poglavlja_za(proj, edit, min_len)
    txt = proj / f"{base}.poglavlja.txt"
    if ch:
        txt.write_text(youtube_tekst(ch, final), encoding="utf-8")
        save_json(proj / f"{base}.chapters.json", chapters_json(ch, final))
    return {"poglavlja": ch, "trajanje": final, "upozorenja": warn, "txt": txt if ch else None}


def for_render(proj, edit, out, W, H, trajanje):
    """Poslije rendera vodoravnog videa duljeg od 3 min s temama: poglavlja uz video. Nikad ne ruši render."""
    try:
        proj = Path(proj)
        if W <= H or trajanje < 180 or not (proj / "analiza.json").exists():
            return []
        if not (load_json(proj / "analiza.json").get("teme")):
            return []
        r = napisi_poglavlja(proj, edit, Path(out).stem)
        if not r["txt"]:
            return []
        lines = [f"Poglavlja za YouTube: {r['txt'].name} ({len(r['poglavlja'])}; zalijepi u opis videa)"]
        return lines + [f"  ! {w}" for w in r["upozorenja"]]
    except Exception as e:  # poglavlja su dodatak; render je važniji
        return [f"Poglavlja nisu napravljena: {e}"]


# ---------------------------------------------------------------- MP3
def izmjeri(path, af=None):
    """(integrirana glasnoća LUFS, true peak dBTP) zvuka datoteke (EBU R128)."""
    chain = (af + "," if af else "") + "ebur128=peak=true"
    r = run([ffmpeg(), "-hide_banner", "-nostats", "-nostdin", "-i", path, "-map", "0:a:0",
             "-af", chain, "-f", "null", "-"])
    txt = r.stderr
    summ = txt[txt.rfind("Summary:"):] if "Summary:" in txt else txt
    mi = re.search(r"I:\s*(-?[\d.]+|-inf)\s*LUFS", summ)
    mp = re.search(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS", summ)
    if not mi:
        die(f"ne mogu izmjeriti glasnoću: {path}")
    val = lambda m: -120.0 if (m is None or "inf" in m.group(1)) else float(m.group(1))  # noqa: E731
    return val(mi), val(mp)


def _esc(v):
    return re.sub(r"([=;#\\\n])", r"\\\1", str(v))


def ffmetadata(tags, ch, trajanje):
    L = [";FFMETADATA1"]
    L += [f"{k}={_esc(v)}" for k, v in tags.items() if v]
    for i, c in enumerate(ch):
        end = ch[i + 1]["od"] if i + 1 < len(ch) else trajanje
        L += ["", "[CHAPTER]", "TIMEBASE=1/1000", f"START={int(round(c['od'] * 1000))}",
              f"END={int(round(end * 1000))}", f"title={_esc(c['naslov'])}"]
    return "\n".join(L) + "\n"


def lanac(gain_db, limiter):
    out = f"aresample=192000,volume={gain_db:.2f}dB"
    if limiter:
        out += f",alimiter=limit={10 ** (MP3_LIMIT_DB / 20):.4f}:attack=1:release=80:level=0"
    return out + ",aresample=44100"


def postavke(proj):
    p = Path(proj) / "epizoda.json"
    return load_json(p) if p.exists() else {}


def napravi_mp3(proj, video, base, ch, trajanje, kbps=MP3_KBPS, naslov=None, autor=None, slika=None, ispis=True):
    proj = Path(proj)
    cfg = postavke(proj)
    for k, v in (("naslov", naslov), ("autor", autor)):
        if v:
            cfg[k] = v
    save_json(proj / "epizoda.json", cfg)
    title = cfg.get("naslov") or proj.name
    artist = cfg.get("autor") or ZADANI_AUTOR
    if ispis:
        print(f"Mjerim glasnoću {Path(video).name} ...")
    I, tp = izmjeri(video)
    gain = MP3_CILJ - I
    out = proj / f"{base}.mp3"
    meta = proj / "_tmp" / "mp3_meta.txt"
    meta.parent.mkdir(exist_ok=True)
    tags = {"title": title, "artist": artist, "album_artist": artist, "album": cfg.get("album") or artist,
            "genre": "Podcast", "comment": "Shofe"}
    with open(meta, "w", encoding="utf-8", newline="\n") as f:   # Windows: bez \r u vrijednostima
        f.write(ffmetadata(tags, ch, trajanje))
    img = None
    if slika:
        img = Path(slika)
        if not img.is_absolute():
            img = (proj / img) if (proj / img).exists() else Path.cwd() / img
        if not img.exists():
            die(f"slika ne postoji: {slika}")
    res = None
    for _ in range(3):
        limiter = tp + gain > MP3_LIMIT_DB
        cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-i", video, "-i", meta]
        if img:
            cmd += ["-i", img]
        cmd += ["-map", "0:a:0"] + (["-map", "2:v:0"] if img else []) + [
            "-map_metadata", "1", "-map_chapters", "1", "-af", lanac(gain, limiter),
            "-c:a", "libmp3lame", "-b:a", f"{int(kbps)}k", "-ar", "44100", "-ac", "2"]
        if img:
            cmd += ["-c:v", "mjpeg", "-vf", "scale='min(1400,iw)':-2", "-disposition:v", "attached_pic",
                    "-metadata:s:v", "title=Cover", "-metadata:s:v", "comment=Cover (front)"]
        cmd += ["-id3v2_version", "3", "-write_id3v1", "1", out]
        run(cmd, cwd=proj)
        I2, tp2 = izmjeri(out)
        res = {"mp3": out, "lufs": I2, "tp": tp2, "pojacanje": gain, "limiter": limiter}
        if abs(I2 - MP3_CILJ) <= 0.3 and tp2 <= MP3_TP:
            break
        if tp2 > MP3_TP and abs(I2 - MP3_CILJ) <= 0.3:
            tp = max(tp, MP3_LIMIT_DB + 1 - gain)   # vrh: uključi limiter
            continue
        gain += MP3_CILJ - I2                         # limiter stisnuo glasne dijelove: ispravi
    return res


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Poglavlja za YouTube i MP3 za podcast platforme")
    ap.add_argument("projekt")
    ap.add_argument("naredba", choices=["poglavlja", "mp3"])
    ap.add_argument("--verzija", type=int, default=None, help="broj verzije (reel_vN); zadano: ona koju gledaš")
    ap.add_argument("--min", type=float, default=MIN_POGLAVLJE, help="najkraće poglavlje u s (YouTube: 10)")
    ap.add_argument("--kbps", type=int, default=MP3_KBPS, help="MP3 kbps (stereo; zadano 128)")
    ap.add_argument("--naslov", default=None, help="naslov epizode u MP3 (pamti se)")
    ap.add_argument("--autor", default=None, help=f"autor/podcast u MP3 (pamti se; zadano {ZADANI_AUTOR})")
    ap.add_argument("--slika", default=None, help="naslovna slika u MP3 (kvadratna, npr. 3000×3000)")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    if a.min < MIN_POGLAVLJE:
        die("YouTube ne prihvaća poglavlja kraća od 10 s")
    edit, base, what, video = odaberi(proj, a.verzija)
    r = napisi_poglavlja(proj, edit, base, a.min)
    ch, final = r["poglavlja"], r["trajanje"]
    print(f"Poglavlja ({what}, video {fmt_time(final)}): {len(ch)}")
    if ch:
        print(youtube_tekst(ch, final).rstrip())
        print(f"  → {r['txt'].name} (zalijepi u opis na YouTubeu), {base}.chapters.json (podcast platforme)")
    for w in r["upozorenja"]:
        print(f"  ! {w}")
    if a.naredba == "mp3":
        if video is None:
            die("nema gotovog videa te verzije: prvo render.py (MP3 se radi iz gotovog videa)")
        if not a.kbps or not 64 <= a.kbps <= 320:
            die("--kbps između 64 i 320")
        m = napravi_mp3(proj, video, base, ch, final, a.kbps, a.naslov, a.autor, a.slika)
        size = m["mp3"].stat().st_size / 1e6
        print(f"\nMP3 za podcast platforme: {m['mp3'].name}  ({size:.1f} MB, {a.kbps} kbps stereo, 44,1 kHz, "
              f"{fmt_time(final)})")
        print(f"  Glasnoća {m['lufs']:.1f} LUFS (cilj {MP3_CILJ:.0f}), vrh {m['tp']:.1f} dBTP"
              + (" (limiter vrhova)" if m["limiter"] else "") + f", {len(ch)} poglavlja u ID3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
