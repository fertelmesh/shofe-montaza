"""Titlovi kao datoteka: SRT (YouTube, Facebook, DaVinci, VLC) i VTT (web).

  python titlovi.py shofe_projekt                  SRT za verziju koju gledaš → reel_vN.srt uz video
  python titlovi.py shofe_projekt --format oba     SRT + VTT
  python titlovi.py shofe_projekt --verzija 2      za reel_v2
  python titlovi.py shofe_projekt --trenutno       iz trenutnog edit.json (još nerenderirane izmjene)
  python titlovi.py shofe_projekt --ispis          ispiši titlove u konzolu

render.py sam napravi reel_vN.srt uz svaki video, pa ovo treba samo za VTT, stariju verziju ili ispis.

Za razliku od titlova upisanih u video (karaoke, 2–4 riječi), ovo su klasični titlovi za čitanje:
cijele fraze, najviše 2 retka po 42 znaka, 0,83–7 s na ekranu, rez na kraju rečenice ili stanci,
tekst onakav kakav je ispravljen u edit.json (pravopis, imena), velika/mala slova kao u govoru.
Vremena su vremena gotovog videa (nakon rezova i brzine).
"""
import argparse
import re
import sys
from pathlib import Path

from common import die, fmt_time, load_json

MAX_LINE = 42          # znakova po retku (Netflix/BBC praksa za latinicu)
MAX_LINES = 2
MAX_DUR = 7.0          # s na ekranu najviše
MIN_DUR = 5 / 6        # s na ekranu najmanje (20 sličica pri 24 fps)
CPS = 17               # znakova u sekundi: ugodna brzina čitanja
LINGER = 0.3           # titl ostaje još malo nakon zadnje riječi
PAUSE_BREAK = 0.7      # stanka u govoru koja uvijek počinje novi titl

SENT_END = re.compile(r"[.!?…]+[\"'”»)]*$")
CLAUSE_END = re.compile(r"[,;:–—]+[\"'”»)]*$")
# riječi kojima redak ne bi trebao završiti (prijedlozi, veznici, nenaglašeni oblici)
WEAK_END = {"i", "a", "u", "na", "za", "od", "do", "s", "sa", "k", "ka", "o", "po", "pri", "iz", "uz", "bez",
            "kroz", "prema", "da", "ali", "ili", "te", "pa", "ni", "niti", "nego", "je", "se", "su", "sam", "smo",
            "ste", "si", "će", "ću", "bi", "što", "kad", "kada", "ako", "jer", "kao", "the", "a", "an", "to", "of"}


def _plain(t):
    return re.sub(r"[^\w]", "", t.lower())


def _text(ws):
    return " ".join(w["t"] for w in ws)


# ---------------------------------------------------------------- titlovi iz riječi
def group_words(ws):
    """Riječi gotovog videa [{t, s, e}] → skupine riječi, svaka postaje jedan titl."""
    cap = MAX_LINE * MAX_LINES
    groups, cur = [], []

    def split_overflow(cur, w):
        """cur je pun: prekini na zadnjem zarezu u drugoj polovici ako postoji, inače ispred w."""
        n = len(cur)
        for k in range(n - 2, 0, -1):
            if CLAUSE_END.search(cur[k]["t"]) and len(_text(cur[:k + 1])) >= 0.4 * cap:
                return cur[:k + 1], cur[k + 1:]
        return cur, []

    for w in ws:
        if cur:
            prev = cur[-1]
            txt = _text(cur + [w])
            hard = SENT_END.search(prev["t"]) or w["s"] - prev["e"] > PAUSE_BREAK
            soft = CLAUSE_END.search(prev["t"]) and len(_text(cur)) >= MAX_LINE
            if hard or soft:
                groups.append(cur)
                cur = []
            elif len(txt) > cap or w["e"] - cur[0]["s"] > MAX_DUR:
                done, cur = split_overflow(cur, w)
                groups.append(done)
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def split_lines(ws):
    """Tekst titla u 1–2 retka: što ravnomjerniji, prekid po mogućnosti iza interpunkcije,
    redak ne završava prijedlogom ili veznikom."""
    toks = [w["t"] for w in ws]
    full = " ".join(toks)
    if len(full) <= MAX_LINE or len(toks) < 2:
        return [full]
    best, best_score = None, None
    for i in range(1, len(toks)):
        l1, l2 = " ".join(toks[:i]), " ".join(toks[i:])
        over = max(len(l1) - MAX_LINE, 0) + max(len(l2) - MAX_LINE, 0)
        score = over * 100 + abs(len(l1) - len(l2))
        if CLAUSE_END.search(toks[i - 1]) or SENT_END.search(toks[i - 1]):
            score -= 20
        if _plain(toks[i - 1]) in WEAK_END:
            score += 10
        if best_score is None or score < best_score:
            best, best_score = [l1, l2], score
    return best


def make_cues(ws, total, fps=30):
    """Riječi gotovog videa (s, e u sekundama gotovog videa) → [{od, do, retci}]."""
    ws = [w for w in ws if w["t"].strip()]
    groups = group_words(ws)
    gap = 2.0 / fps
    cues = []
    for n, g in enumerate(groups):
        start = max(g[0]["s"], 0.0)
        nxt = groups[n + 1][0]["s"] if n + 1 < len(groups) else total
        last = g[-1]["e"]
        reading = len(_text(g)) / CPS
        # dovoljno dugo za čitanje, ali ne više od sekunde iza zadnje izgovorene riječi
        want = max(last + LINGER, start + MIN_DUR, min(start + reading, last + 1.0))
        end = min(want, start + MAX_DUR, nxt - gap, total)
        end = max(end, min(last, nxt - gap, total), start + 0.1)  # nikad prije kraja zadnje riječi
        cues.append({"od": round(start, 3), "do": round(end, 3), "retci": split_lines(g)})
    return cues


# ---------------------------------------------------------------- zapis
def _ts(t, sep):
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt_text(cues):
    return "".join(f"{i}\n{_ts(c['od'], ',')} --> {_ts(c['do'], ',')}\n" + "\n".join(c["retci"]) + "\n\n"
                   for i, c in enumerate(cues, 1))


def vtt_text(cues):
    body = "".join(f"{i}\n{_ts(c['od'], '.')} --> {_ts(c['do'], '.')}\n" + "\n".join(c["retci"]) + "\n\n"
                   for i, c in enumerate(cues, 1))
    return "WEBVTT\n\n" + body


def write_srt(path, cues):
    # UTF-8 s BOM-om i CRLF (klasični SubRip) na svakom sustavu: YouTube ga prihvaća, a Windows
    # programi (DaVinci, Premiere, Notepad) tada sigurno čitaju č ć š ž đ
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:  # Path.write_text(newline=) tek od 3.10
        f.write(srt_text(cues))


def write_vtt(path, cues):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(vtt_text(cues))


# ---------------------------------------------------------------- iz projekta
def finished_words(proj, edit, pj, words):
    """Riječi u vremenu gotovog videa, s tekstom kakav je u titlovima (ispravci, izbaci, izrezi, brzina)."""
    import render  # tek ovdje: render.py uvozi ovaj modul

    st = render.resolve_style(edit)
    cuts, kept, total = render.build_cuts(words, edit, st, pj["fps"], pj["duration"])
    if not cuts:
        die("nema ničega za zadržati (svi odsječci su isključeni?)")
    speed = float(edit.get("brzina") or 1.0)
    ws = render.out_words(words, kept, cuts, set())
    return [dict(w, s=w["s"] / speed, e=w["e"] / speed) for w in ws], total / speed


def cues_for(proj, edit):
    proj = Path(proj)
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    ws, total = finished_words(proj, edit, pj, words)
    return make_cues(ws, total, pj["fps"]), total


def main():
    import verzije

    ap = argparse.ArgumentParser(description="Titlovi kao SRT/VTT datoteka")
    ap.add_argument("projekt")
    ap.add_argument("--format", default="srt", choices=["srt", "vtt", "oba"])
    ap.add_argument("--verzija", type=int, default=None, help="broj verzije (reel_vN); zadano: ona koju gledaš")
    ap.add_argument("--trenutno", action="store_true", help="iz trenutnog edit.json")
    ap.add_argument("--izlaz", default=None, help="ime datoteke bez nastavka (zadano reel_vN)")
    ap.add_argument("--ispis", action="store_true", help="ispiši titlove")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    for f in ("project.json", "transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    found = verzije.found_versions(proj)
    if a.trenutno or (not found and a.verzija is None):
        edit, base, what = load_json(proj / "edit.json"), "titlovi_trenutno", "trenutni edit.json"
    else:
        v = a.verzija if a.verzija is not None else verzije.viewed(proj)
        if v not in found:
            die(f"nema verzije {v}. Postoje: {', '.join(map(str, sorted(found))) or 'nijedna'}")
        vf = verzije.video_file(proj, v)
        edit, base, what = load_json(found[v]), (Path(vf).stem if vf else f"reel_v{v}"), f"verzija {v}"
    base = a.izlaz or base

    cues, total = cues_for(proj, edit)
    if not cues:
        die("nema riječi za titlove")
    outs = []
    if a.format in ("srt", "oba"):
        write_srt(proj / f"{base}.srt", cues)
        outs.append(proj / f"{base}.srt")
    if a.format in ("vtt", "oba"):
        write_vtt(proj / f"{base}.vtt", cues)
        outs.append(proj / f"{base}.vtt")
    if a.ispis:
        for i, c in enumerate(cues, 1):
            print(f"{i:3d}  {fmt_time(c['od'])}–{fmt_time(c['do'])}  {' / '.join(c['retci'])}")
        print()
    print(f"Titlovi ({what}): {len(cues)} titlova, video {fmt_time(total)}")
    for o in outs:
        print(f"  {o}")


if __name__ == "__main__":
    sys.exit(main())
