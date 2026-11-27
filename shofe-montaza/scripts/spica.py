"""Uvodna i odjavna špica epizode (M4.4c)

  python spica.py shofe_projekt dodaj [--uvod generirana|intro.mp4|nema] [--odjava generirana|outro.mp4|nema]
                                      [--poslije 0:25] [--naslov "..."] [--ime "Sunčani4M"] [--broj 12]
                                      [--glazba spica.mp3] [--trajanje-uvoda 5] [--trajanje-odjave 15]
  python spica.py shofe_projekt makni                   bez špica
  python spica.py shofe_projekt pokazi                  napravi špice i slike za provjeru (spica_*.png)
  python spica.py postavi --uvod intro.mp4 --odjava outro.mp4 [--glazba x.mp3] [--ime ...]
                                                        zapamti Markove datoteke za sve epizode

Špica ide samo u glavni video (reel_vN), ne u isječke. `--poslije` = vrijeme u videu BEZ špice na kojem
ide uvodna špica (iza najave / „cold opena"); zadano 0 = na samom početku. Sve što je iza nje (titlovi,
poglavlja, MP3, naredbe po vremenu) pomakne se za trajanje špice.

U edit.json:
  "spica": {"uvod": {"datoteka": "C:/…/intro.mp4", "trajanje": 8.0} | {"generirana": true, "trajanje": 5},
            "odjava": … isto …, "poslije": 25.0,
            "naslov": "…", "ime": "Sunčani4M", "broj": 12, "glazba": "C:/…/spica.mp3"}
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from common import FONTS_DIR, data_dir, die, ffmpeg, fmt_time, load_json, run, save_json, video_info

ZADANO_IME = "Sunčani4M"
UVOD_GEN = 5.0               # s, generirana uvodna špica (kartica s imenom i naslovom)
ODJAVA_GEN = 15.0            # s, generirana odjava: YouTube završni zaslon traje zadnjih 5–20 s
ODJAVA_MIN, ODJAVA_MAX = 5.0, 20.0
UVOD_MAX = 60.0
CILJ_LUFS = -14.0            # Markova datoteka: kao glavni video (YouTube −14 LUFS)
GLAZBA_LUFS = -16.0          # glazba ispod generirane kartice: malo ispod govora
SNAP = 1.5                   # s: „poslije" se pomakne na najbliži rez glavnog videa unutar ovoga
NASTAVAK = " (nastavak)"


# ---------------------------------------------------------------- postavke
def zadano():
    p = data_dir() / "spica.json"
    return load_json(p) if p.exists() else {}


def aktivna(edit):
    sp = (edit or {}).get("spica")
    return bool(sp) and bool(sp.get("uvod") or sp.get("odjava"))


def okviri(d, fps):
    return max(1, int(round(float(d) * fps)))


def trajanje_dijela(dio, fps):
    """Trajanje špice u cijelim okvirima (isto u renderu, poglavljima i naredbama)."""
    if not dio:
        return 0.0
    return okviri(dio.get("trajanje") or 0, fps) / fps


def rezovi_glavnog(cuts, speed):
    return [0.0] + [c["o"] / speed for c in cuts[1:]]


def tocka(at, ws, cuts, speed):
    """Gdje točno ide uvodna špica blizu `at` (vrijeme glavnog videa): nikad usred riječi. Prednost ima kraj
    rečenice unutar 3 s, inače najbliža stanka; u stanci, rez glavnog videa ako ga ima (čišći zvuk).
    ws = riječi gotovog videa [{t, s, e}] u vremenu prije brzine."""
    if not ws:
        return at
    ws = sorted(ws, key=lambda w: w["s"])
    rez = [c["o"] for c in cuts[1:]]
    gaps = []
    for w1, w2 in zip(ws, ws[1:]):
        lo, hi = w1["e"] / speed, w2["s"] / speed
        if hi < lo:
            lo = hi = (lo + hi) / 2
        inside = [x / speed for x in rez if lo - 1e-6 <= x / speed <= hi + 1e-6]
        t = min(inside, key=lambda x: abs(x - (lo + hi) / 2)) if inside else (lo + hi) / 2
        gaps.append((t, w1["t"].rstrip()[-1:] in ".!?…"))
    if not gaps:
        return at
    sent = [t for t, end in gaps if end and abs(t - at) <= 3.0]
    pool = sent or [t for t, _ in gaps]
    return min(pool, key=lambda t: abs(t - at))


def raspored(edit, cuts, speed, fps, glavni, ws=None):
    """→ None ili {"at", "uvod", "odjava", "glavni", "ukupno"} (sekunde; at = vrijeme glavnog videa
    gdje ide uvodna špica: u stanci između riječi, po mogućnosti na kraju rečenice, poravnato na okvir).
    ws = riječi gotovog videa (render.out_words); bez njih samo na najbliži rez unutar 1,5 s."""
    if not aktivna(edit):
        return None
    sp = edit["spica"]
    du, do = trajanje_dijela(sp.get("uvod"), fps), trajanje_dijela(sp.get("odjava"), fps)
    at = max(0.0, float(sp.get("poslije") or 0.0))
    if du and at > 0:
        if at >= glavni - 1.0:
            at = 0.0
        elif ws:
            at = tocka(at, ws, cuts, speed)
        else:
            near = min(rezovi_glavnog(cuts, speed), key=lambda x: abs(x - at)) if cuts else at
            if abs(near - at) <= SNAP:
                at = near
    at = round(at * fps) / fps
    return {"at": at, "uvod": du, "odjava": do, "glavni": glavni, "ukupno": glavni + du + do}


def u_konacno(t, r):
    """Vrijeme glavnog videa → vrijeme videa sa špicom."""
    if not r:
        return t
    return t + r["uvod"] if t >= r["at"] - 1e-6 else t


def iz_konacnog(t, r):
    """Vrijeme videa sa špicom → (vrijeme glavnog videa ili None, "uvod"/"odjava"/None)."""
    if not r:
        return t, None
    if t < r["at"]:
        return t, None
    if t < r["at"] + r["uvod"]:
        return None, "uvod"
    m = t - r["uvod"]
    if m <= r["glavni"] + 1e-6:
        return m, None
    return None, "odjava"


def pomakni_cues(cues, r):
    """SRT titlovi glavnog videa → vrijeme videa sa špicom; titl prije špice ne prelazi u nju."""
    if not r:
        return cues
    out = []
    for c in cues:
        c = dict(c)
        if c["od"] < r["at"] - 1e-6:
            c["do"] = round(min(c["do"], r["at"]), 3)
        else:
            c["od"], c["do"] = round(c["od"] + r["uvod"], 3), round(c["do"] + r["uvod"], 3)
        if c["do"] - c["od"] > 0.05:
            out.append(c)
    return out


def poglavlja(ch, r, trajanje_glavnog):
    """Poglavlja u vremenu glavnog videa ([{od, naslov, vrsta}], bez spajanja kratkih) → u vremenu videa sa
    špicom, sa špicama kao vlastitim dijelovima („Uvod", „Odjava"); tema koju špica prekine nastavlja se."""
    if not r:
        return ch
    out = []
    at, du = r["at"], r["uvod"]
    before = [c for c in ch if c["od"] < at - 1e-6]
    after = [dict(c, od=c["od"] + du) for c in ch if c["od"] >= at - 1e-6]
    out += [dict(c) for c in before]
    if du:
        out.append({"od": at, "naslov": "Uvod", "vrsta": "spica"})
        if before and (not after or after[0]["od"] - (at + du) > 1e-3):
            prev = before[-1]
            base = prev["naslov"].replace(NASTAVAK, "")
            out.append({"od": at + du, "naslov": base + NASTAVAK, "vrsta": prev["vrsta"]})
    out += after
    if r["odjava"]:
        out.append({"od": trajanje_glavnog + du, "naslov": "Odjava", "vrsta": "spica"})
    return sorted(out, key=lambda c: c["od"])


# ---------------------------------------------------------------- izrada špica
def _hash(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _ass_esc(t):
    return str(t).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _boja(hexstr, alpha=0):
    h = hexstr.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def kartica_ass(path, vrsta, sp, W, H, d, boja="#FF7A00"):
    """ASS s tekstom generirane kartice. Uvod: ime podcasta (veliko, boja isticanja), naslov epizode, broj.
    Odjava: zahvala i ime u gornjoj trećini, donji dio slobodan za elemente završnog zaslona YouTubea."""
    s = min(W, H) / 1080
    ml = round(W * 0.09)
    acc, white = _boja(boja), _boja("#FFFFFF")
    soft = _boja("#FFFFFF", 0x30)
    ime = _ass_esc(sp.get("ime") or ZADANO_IME).upper()
    styles = [
        f"Style: Ime,Anton,{round(150 * s)},{acc},&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,0,{round(4 * s)},5,{ml},{ml},0,1",
        f"Style: Naslov,Montserrat ExtraBold,{round(66 * s)},{white},&H000000FF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,0,{round(3 * s)},5,{ml},{ml},0,1",
        f"Style: Mali,Montserrat SemiBold,{round(44 * s)},{soft},&H000000FF,&H00000000,&H78000000,0,0,0,0,100,100,1,0,1,0,{round(2 * s)},5,{ml},{ml},0,1",
        f"Style: Zahvala,Montserrat Black,{round(84 * s)},{white},&H000000FF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,0,{round(3 * s)},5,{ml},{ml},0,1",
        f"Style: Traka,Arial,10,{acc},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    end = d
    cx = W // 2

    def ev(style, y, text, t0=0, rise=30):
        y0 = round(y + rise * s)
        tag = f"{{\\an5\\move({cx},{y0},{cx},{round(y)},{t0},{t0 + 450})\\fad({220 if t0 == 0 else 1},0)"
        if t0:
            tag += f"\\alpha&HFF&\\t({t0},{t0 + 300},\\alpha&H00&)"
        return f"Dialogue: 1,{_t(0)},{_t(end)},{style},,0,0,0,,{tag}}}{text}"

    lines = []
    if vrsta == "uvod":
        lines.append(ev("Ime", H * 0.40, ime))
        bw, bh = round(W * 0.12), max(6, round(8 * s))
        y = round(H * 0.40 + 92 * s)
        lines.append(f"Dialogue: 0,{_t(0.15)},{_t(end)},Traka,,0,0,0,,{{\\an7\\pos({cx - bw // 2},{y})\\p1"
                     f"\\clip({cx},{y},{cx},{y + bh})\\t(0,350,\\clip({cx - bw // 2},{y},{cx + bw // 2},{y + bh}))}}"
                     f"m 0 0 l {bw} 0 {bw} {bh} 0 {bh}{{\\p0}}")
        if sp.get("naslov"):
            lines.append(ev("Naslov", H * 0.585, _ass_esc(sp["naslov"]), t0=250))
        if sp.get("broj") not in (None, ""):
            lines.append(ev("Mali", H * 0.70, f"Epizoda {_ass_esc(sp['broj'])}", t0=450))
    else:
        lines.append(ev("Zahvala", H * 0.15, _ass_esc(sp.get("odjava_tekst") or "Hvala što ste gledali!")))
        lines.append(ev("Ime", H * 0.275, ime, t0=200))
        lines.append(ev("Mali", H * 0.37, _ass_esc(sp.get("odjava_poziv") or "Pretplati se za nove epizode"),
                        t0=400))
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            *styles, "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    Path(path).write_text("\n".join(head + lines) + "\n", encoding="utf-8")


def _t(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    cs = min(99, int(round((s - int(s)) * 100)))
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs:02d}"


def _pozadina(proj, sp, W, H, png):
    """Mutna, tamnija slika iz epizode (ili zadana slika) kao pozadina generirane kartice."""
    src = sp.get("pozadina")
    if src and Path(src).exists():
        inp, ss = ["-i", Path(src)], []
    else:
        pj = load_json(proj / "project.json")
        ss = ["-ss", f"{max(0.0, float(pj.get('duration') or 0) * 0.35):.2f}"]
        inp = ["-i", "source.mp4"]
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma={max(12, round(min(W, H) / 40))},"
          "eq=brightness=-0.26:saturation=0.6:contrast=0.9,vignette=angle=PI/4")
    run([ffmpeg(), "-y", "-v", "error", *ss, *inp, "-frames:v", "1", "-vf", vf, png.relative_to(proj).as_posix()],
        cwd=proj)


def _glazba_lanac(d):
    return (f"aresample=48000,aformat=channel_layouts=stereo,atrim=0:{d:.4f},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={GLAZBA_LUFS}:TP=-2,aresample=48000,afade=t=in:d=0.3,"
            f"afade=t=out:st={max(0.0, d - 1.0):.4f}:d=1.0,apad,atrim=0:{d:.4f}")


def napravi_generiranu(proj, vrsta, sp, W, H, fps, d, out, boja="#FF7A00"):
    tmp = proj / "_tmp"
    tmp.mkdir(exist_ok=True)
    fdir = proj / "fonts"
    fdir.mkdir(exist_ok=True)
    import shutil
    for f in FONTS_DIR.glob("*.ttf"):
        if not (fdir / f.name).exists():
            shutil.copy2(f, fdir / f.name)
    bg = tmp / f"spica_{vrsta}_pozadina.png"
    _pozadina(proj, sp, W, H, bg)
    ass = tmp / f"spica_{vrsta}.ass"
    kartica_ass(ass, vrsta, sp, W, H, d, boja)
    n = okviri(d, fps)
    # lagano približavanje pozadine (2 % kroz cijelu karticu), tekst preko, ulaz/izlaz kroz crno
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='1+0.02*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}"
          f":s={W}x{H}:fps={fps},setsar=1,subtitles=filename={ass.relative_to(proj).as_posix()}:fontsdir=fonts,"
          f"fade=t=in:d=0.25,fade=t=out:st={max(0.0, d - 0.3):.4f}:d=0.3,format=yuv420p")
    cmd = [ffmpeg(), "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", bg.relative_to(proj).as_posix()]
    glazba = sp.get("glazba")
    if glazba and Path(glazba).exists():
        cmd += ["-i", Path(glazba)]
        af = _glazba_lanac(d)
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        af = f"atrim=0:{d:.4f}"
    cmd += ["-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]", "-frames:v", str(n),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-t", f"{n / fps:.4f}", out.relative_to(proj).as_posix()]
    run(cmd, cwd=proj)


def napravi_iz_datoteke(proj, src, W, H, fps, d, out):
    """Markova datoteka: prilagođena veličini videa (cijela slika, crni rub ako treba), isti broj okvira,
    zvuk stalnim pojačanjem na −14 LUFS kao glavni video, limiter vrhova."""
    import epizoda
    info = video_info(src)
    n = okviri(d, fps)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
          f"fps={fps},format=yuv420p")
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", Path(src)]
    if info["has_audio"]:
        I, tp = epizoda.izmjeri(src)
        gain = 0.0 if I < -70 else CILJ_LUFS - I
        lim = ",alimiter=limit=0.84:attack=1:release=80:level=0" if tp + gain > -1.5 else ""
        af = (f"[0:a:0]aresample=192000,volume={gain:.2f}dB{lim},aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=out:st={max(0.0, d - 0.04):.4f}:d=0.04,apad,atrim=0:{n / fps:.4f}[a]")
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        af = f"[1:a]atrim=0:{n / fps:.4f}[a]"
    cmd += ["-filter_complex", f"[0:v:0]{vf}[v];{af}", "-map", "[v]", "-map", "[a]", "-frames:v", str(n),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out.relative_to(proj).as_posix()]
    run(cmd, cwd=proj)


def pripremi(proj, edit, W, H, fps, boja="#FF7A00", ispis=True):
    """Napravi (ili uzmi iz _tmp) špice za ovaj edit → {"uvod": Path|None, "odjava": Path|None, "napomene"}."""
    proj = Path(proj)
    sp = edit.get("spica") or {}
    res, notes = {"uvod": None, "odjava": None}, []
    for vrsta in ("uvod", "odjava"):
        dio = sp.get(vrsta)
        if not dio:
            continue
        d = trajanje_dijela(dio, fps)
        key = {"v": 1, "dio": dio, "W": W, "H": H, "fps": fps, "boja": boja}
        if dio.get("datoteka"):
            src = Path(dio["datoteka"])
            if not src.is_absolute():
                src = proj / src
            if not src.exists():
                die(f"špica ne postoji: {src} (spica.py {proj.name} dodaj --{vrsta} …)")
            key["mtime"] = src.stat().st_mtime
            real = video_info(src)["dur"]
            if real + 1.0 / fps < d:
                notes.append(f"{vrsta}: datoteka je kraća ({real:.2f} s) od upisanog trajanja — ponovi `spica.py dodaj`")
        else:
            key.update({k: sp.get(k) for k in ("naslov", "ime", "broj", "glazba", "pozadina", "odjava_tekst",
                                               "odjava_poziv")})
        out = proj / "_tmp" / f"spica_{vrsta}_{_hash(key)}.mkv"
        if not out.exists():
            out.parent.mkdir(exist_ok=True)
            if ispis:
                print(f"Radim {'uvodnu' if vrsta == 'uvod' else 'odjavnu'} špicu ({d:.1f} s) ...")
            if dio.get("datoteka"):
                napravi_iz_datoteke(proj, src, W, H, fps, d, out)
            else:
                napravi_generiranu(proj, vrsta, sp, W, H, fps, d, out, boja)
        res[vrsta] = out
    res["napomene"] = notes
    return res


# ---------------------------------------------------------------- render
def graf(r, files, n_inputs, brzo, W):
    """Filteri koji glavni [vout]/[aout] spoje sa špicama → (filteri, ulazni argumenti, oznake)."""
    g, inputs = [], []
    k = n_inputs
    segs = []
    tail = (f",scale={W // 2}:-2" if brzo else "")
    for vrsta in ("uvod", "odjava"):
        if files.get(vrsta):
            inputs += ["-i", files[vrsta]]
            g.append(f"[{k}:v]setsar=1{tail},format=yuv420p[sp_{vrsta}_v]")
            g.append(f"[{k}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
                     f"[sp_{vrsta}_a]")
            k += 1
    at = r["at"]
    g.append("[vout0]setsar=1[vm]")
    g.append("[aout0]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[am]")
    if files.get("uvod") and at > 0:
        g.append("[vm]split=2[vm1][vm2]")
        g.append("[am]asplit=2[am1][am2]")
        g.append(f"[vm1]trim=end={at:.4f},setpts=PTS-STARTPTS[p1v]")
        g.append(f"[vm2]trim=start={at:.4f},setpts=PTS-STARTPTS[p2v]")
        g.append(f"[am1]atrim=end={at:.4f},asetpts=PTS-STARTPTS[p1a]")
        g.append(f"[am2]atrim=start={at:.4f},asetpts=PTS-STARTPTS[p2a]")
        segs += ["[p1v][p1a]", "[sp_uvod_v][sp_uvod_a]", "[p2v][p2a]"]
    else:
        if files.get("uvod"):
            segs.append("[sp_uvod_v][sp_uvod_a]")
        segs.append("[vm][am]")
    if files.get("odjava"):
        segs.append("[sp_odjava_v][sp_odjava_a]")
    g.append("".join(segs) + f"concat=n={len(segs)}:v=1:a=1[vout][aout]")
    return g, inputs


def opis(r, edit):
    sp = edit.get("spica") or {}
    parts = []
    for vrsta, ime in (("uvod", "uvodna"), ("odjava", "odjavna")):
        dio = sp.get(vrsta)
        if dio:
            src = Path(dio["datoteka"]).name if dio.get("datoteka") else "generirana"
            d = r["uvod"] if vrsta == "uvod" else r["odjava"]
            where = f" na {fmt_time(r['at'])}" if vrsta == "uvod" and r["at"] > 0 else ""
            parts.append(f"{ime} {d:.1f} s ({src}){where}")
    return "Špica: " + ", ".join(parts)


# ---------------------------------------------------------------- CLI
def _vrijeme(s):
    import uredi
    return uredi.parse_time(s)


def _dio(val, trajanje, zad, fps, proj, vrsta):
    """--uvod/--odjava vrijednost → zapis u edit.json (ili None)."""
    if val is None:
        val = zad.get(vrsta) or "generirana"
    v = str(val).strip()
    if v.lower() in ("nema", "bez", "ne", "0", "none"):
        return None
    if v.lower() in ("generirana", "generiraj", "da", "auto"):
        d = float(trajanje if trajanje is not None else (UVOD_GEN if vrsta == "uvod" else ODJAVA_GEN))
        if vrsta == "odjava" and not ODJAVA_MIN <= d <= ODJAVA_MAX:
            die(f"generirana odjava: {ODJAVA_MIN:.0f}–{ODJAVA_MAX:.0f} s (YouTube završni zaslon)")
        if vrsta == "uvod" and not 2.0 <= d <= 15.0:
            die("generirana uvodna špica: 2–15 s")
        return {"generirana": True, "trajanje": round(d, 3)}
    p = Path(v)
    if not p.is_absolute():
        p = (proj / p) if (proj / p).exists() else (Path.cwd() / p)
    if not p.exists():
        die(f"ne postoji: {v}")
    p = p.resolve()
    info = video_info(p)
    d = math.floor(info["dur"] * fps + 1e-6) / fps
    if trajanje is not None:
        d = min(d, float(trajanje))
    if d < 0.5:
        die(f"{p.name} je prekratak za špicu")
    if vrsta == "uvod" and d > UVOD_MAX:
        print(f"  napomena: uvodna špica traje {d:.0f} s — preporuka je do 30 s")
    return {"datoteka": str(p), "trajanje": round(d, 4)}


def cmd_dodaj(proj, a):
    import uredi
    edit = load_json(proj / "edit.json")
    pj = load_json(proj / "project.json")
    fps = pj["fps"]
    zad = zadano()
    ep = load_json(proj / "epizoda.json") if (proj / "epizoda.json").exists() else {}
    old = edit.get("spica") or {}
    sp = {}
    sp["uvod"] = _dio(a.uvod, a.trajanje_uvoda, zad, fps, proj, "uvod")
    sp["odjava"] = _dio(a.odjava, a.trajanje_odjave, zad, fps, proj, "odjava")
    if not sp["uvod"] and not sp["odjava"]:
        die("ni uvodne ni odjavne špice (za micanje: spica.py projekt makni)")
    sp["poslije"] = _vrijeme(a.poslije) if a.poslije else float(old.get("poslije") or 0.0)
    sp["ime"] = a.ime or old.get("ime") or zad.get("ime") or ep.get("autor") or ZADANO_IME
    sp["naslov"] = a.naslov if a.naslov is not None else (old.get("naslov") or ep.get("naslov") or "")
    broj = a.broj if a.broj is not None else (old.get("broj") or ep.get("broj"))
    if broj not in (None, ""):
        sp["broj"] = broj
    glazba = a.glazba or old.get("glazba") or zad.get("glazba")
    if glazba:
        g = Path(glazba)
        if not g.is_absolute():
            g = (proj / g) if (proj / g).exists() else Path.cwd() / g
        if not g.exists():
            die(f"glazba ne postoji: {glazba}")
        sp["glazba"] = str(g.resolve())
    for k in ("odjava_tekst", "odjava_poziv", "pozadina"):
        if getattr(a, k, None):
            sp[k] = getattr(a, k)
        elif old.get(k):
            sp[k] = old[k]
    sp = {k: v for k, v in sp.items() if v is not None}
    uredi.save_history(proj, "spica dodaj")
    edit["spica"] = sp
    save_json(proj / "edit.json", edit)
    print("Špica upisana u edit.json:")
    for vrsta, ime in (("uvod", "Uvodna"), ("odjava", "Odjavna")):
        dio = sp.get(vrsta)
        if dio:
            src = Path(dio["datoteka"]).name if dio.get("datoteka") else "generirana kartica"
            print(f"  {ime}: {src}, {dio['trajanje']:.1f} s")
    if sp.get("uvod"):
        print(f"  Uvodna ide na {fmt_time(sp['poslije'])} gotovog videa (bez špice)"
              + (" — iza najave" if sp["poslije"] > 0 else " — na samom početku"))
    if any((sp.get(v) or {}).get("generirana") for v in ("uvod", "odjava")):
        print(f"  Tekst: {sp['ime']}" + (f" · {sp['naslov']}" if sp.get("naslov") else "")
              + (f" · Epizoda {sp['broj']}" if sp.get("broj") else ""))
    print(f"Pogledaj: python spica.py {proj.name} pokazi   ·   render: python render.py {proj.name}")
    print(f"Poništi: python uredi.py {proj.name} vrati")


def cmd_pokazi(proj):
    edit = load_json(proj / "edit.json")
    if not aktivna(edit):
        die(f"nema špice (python spica.py {proj.name} dodaj)")
    import render
    pj = load_json(proj / "project.json")
    W, H, fps = pj["width"], pj["height"], pj["fps"]
    st = render.resolve_style(edit)
    files = pripremi(proj, edit, W, H, fps, st.get("boja_isticanja", "#FF7A00"))
    for n in files["napomene"]:
        print(f"  ! {n}")
    out = []
    for vrsta in ("uvod", "odjava"):
        f = files.get(vrsta)
        if not f:
            continue
        d = trajanje_dijela(edit["spica"][vrsta], fps)
        t = min(d * 0.6, d - 0.4) if vrsta == "uvod" else min(2.0, d * 0.5)
        png = proj / f"spica_{vrsta}.png"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", f.relative_to(proj).as_posix(),
             "-frames:v", "1", png.name], cwd=proj)
        out.append(png)
        print(f"{'Uvodna' if vrsta == 'uvod' else 'Odjavna'} špica: {png}")
    return out


def cmd_postavi(a):
    cfg = zadano()
    for k in ("uvod", "odjava", "glazba"):
        v = getattr(a, k)
        if v is None:
            continue
        if v.lower() in ("generirana", "nema"):
            cfg[k] = v.lower()
            continue
        p = Path(v).resolve()
        if not p.exists():
            die(f"ne postoji: {v}")
        cfg[k] = str(p)
    if a.ime:
        cfg["ime"] = a.ime
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    save_json(d / "spica.json", cfg)
    print(f"Zapamćeno za sve epizode ({d / 'spica.json'}):")
    for k, v in cfg.items():
        print(f"  {k}: {v}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "postavi":
        ap = argparse.ArgumentParser(prog="spica.py postavi", description="Zapamti Markove špice za sve epizode")
        ap.add_argument("x")
        ap.add_argument("--uvod")
        ap.add_argument("--odjava")
        ap.add_argument("--glazba")
        ap.add_argument("--ime")
        cmd_postavi(ap.parse_args())
        return 0
    ap = argparse.ArgumentParser(description="Uvodna i odjavna špica epizode")
    ap.add_argument("projekt")
    ap.add_argument("naredba", choices=["dodaj", "makni", "pokazi"])
    ap.add_argument("--uvod", help="generirana | putanja do intro videa | nema")
    ap.add_argument("--odjava", help="generirana | putanja do outro videa | nema")
    ap.add_argument("--poslije", help="vrijeme gotovog videa (bez špice) za uvodnu špicu, npr. 0:25 iza najave")
    ap.add_argument("--naslov", help="naslov epizode na generiranoj kartici")
    ap.add_argument("--ime", help=f"ime podcasta (zadano {ZADANO_IME})")
    ap.add_argument("--broj", help="broj epizode")
    ap.add_argument("--glazba", help="glazba ispod generirane špice")
    ap.add_argument("--pozadina", help="slika za pozadinu generirane špice (zadano: mutni kadar epizode)")
    ap.add_argument("--odjava-tekst", dest="odjava_tekst", help="zahvala na odjavi")
    ap.add_argument("--odjava-poziv", dest="odjava_poziv", help="poziv na odjavi (zadano: Pretplati se …)")
    ap.add_argument("--trajanje-uvoda", dest="trajanje_uvoda", type=float, help=f"s (generirana: {UVOD_GEN:g})")
    ap.add_argument("--trajanje-odjave", dest="trajanje_odjave", type=float,
                    help=f"s (generirana: {ODJAVA_GEN:g}, YouTube završni zaslon 5–20 s)")
    a = ap.parse_args()
    proj = Path(a.projekt).resolve()
    for f in ("project.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    if a.naredba == "dodaj":
        cmd_dodaj(proj, a)
    elif a.naredba == "makni":
        import uredi
        edit = load_json(proj / "edit.json")
        if "spica" not in edit:
            print("Nema špice.")
            return 0
        uredi.save_history(proj, "spica makni")
        edit.pop("spica")
        save_json(proj / "edit.json", edit)
        print("Špica maknuta iz edit.json (vrijedi od sljedećeg rendera).")
    else:
        cmd_pokazi(proj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
