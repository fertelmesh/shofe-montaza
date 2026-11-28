"""Prijelazi na rezovima (M5.2a): iris, rolete, vrata, brisanje, klizanje, pretapanje, kroz crno/bijelo,
prolaz (zum kroz rez), zamah, pikseli. Upisuju se u edit.json `efekti` kao i ostali efekti (efekti.py dodaj iris 0:12),
render.py ih slaže u istom prolazu kodiranja.

Prijelaz je centriran na rezu i **ne mijenja trajanje videa**: pola prijelaza je kraj kadra prije reza,
pola početak kadra iza reza, a za drugu polovicu svaki kadar uzima „ručke" — sličice snimke odmah iza
kraja kadra A i odmah prije početka kadra B (kao DaVinci/Premiere). Zato titlovi, zvuk, glazba i
poglavlja ostaju na istim mjestima, a zvuk na rezu ostaje čisti rez.

U edit.json: {"tip": "iris", "od": kraj kadra A (s snimke), "do": početak kadra B (s snimke),
"parametri": {"trajanje": 0.6, "smjer": "lijevo", "lice": {...}}}. Rez se nađe po tim vremenima i
nakon drugih izmjena (ako jedno od dva vremena još vrijedi).
"""
from common import ffmpeg

# xfade = ugrađeni prijelaz ffmpega; "maska" = naša maska iz numpyja (iris prema licu, rolete);
# "vrata" = dvije polovice starog kadra odu lijevo i desno (overlay)
TIPOVI = {
    "pretapanje": {"xfade": "fade", "zadano": 0.5, "opis": "meko pretapanje jednog kadra u drugi"},
    "crno": {"xfade": "fadeblack", "zadano": 0.7, "opis": "kroz crno (kraj jedne priče, početak druge)"},
    "bljesak": {"xfade": "fadewhite", "zadano": 0.4, "opis": "kroz bijeli bljesak (energija, nova tema)"},
    "iris": {"xfade": "maska", "zadano": 0.6, "opis": "novi kadar se otvori u krugu oko lica (ili sredine)"},
    "rolete": {"xfade": "maska", "zadano": 0.6, "opis": "novi kadar se spusti kroz vodoravne rolete"},
    "vrata": {"xfade": "vrata", "zadano": 0.6, "opis": "stari kadar se otvori po sredini kao dvoja vrata"},
    "brisanje": {"xfade": "wipe", "zadano": 0.4, "smjer": True, "opis": "oštra crta prebriše kadar (--smjer)"},
    "klizanje": {"xfade": "slide", "zadano": 0.4, "smjer": True, "opis": "novi kadar ugura stari van (--smjer)"},
    "prolaz": {"xfade": "zoomin", "zadano": 0.5, "opis": "zum kroz rez: kamera proleti u novi kadar"},
    "zamah": {"xfade": "slide", "zadano": 0.35, "smjer": True, "trag": True,
              "opis": "brzi zamah kamere: kadar odleti s mutnim tragom (--smjer)"},
    "pikseli": {"xfade": "pixelize", "zadano": 0.6, "opis": "kadar se raspadne u kockice i složi u novi"},
}
ALIASI = {"krug": "iris", "otvaranje": "iris", "zaluzine": "rolete", "žaluzine": "rolete", "roleta": "rolete",
          "blinds": "rolete", "doors": "vrata", "wipe": "brisanje", "slide": "klizanje", "guranje_kadra": "klizanje",
          "fade": "pretapanje", "dissolve": "pretapanje", "kroz_crno": "crno", "zatamnjenje": "crno",
          "kroz_bijelo": "bljesak", "flash": "bljesak", "zum_kroz": "prolaz", "zoom_through": "prolaz", "proletiti": "prolaz", "whip": "zamah", "piksel": "pikseli",
          "pixel": "pikseli", "kockice": "pikseli"}
SMJEROVI = {"lijevo": "left", "desno": "right", "gore": "up", "dolje": "down"}
MIN_T, MAX_T = 0.2, 1.5       # s trajanja prijelaza
ROLETE = 7                    # broj traka (rolete)
TOL = 0.021                   # s: rez je „isti" ako se kraj A ili početak B poklapa unutar toga


def je_prijelaz(tip):
    return tip in TIPOVI


def trajanje(p, tip):
    try:
        d = float(p.get("trajanje") or TIPOVI[tip]["zadano"])
    except (TypeError, ValueError):
        d = TIPOVI[tip]["zadano"]
    return max(MIN_T, min(MAX_T, d))


def granice(cuts):
    """Rezovi gotovog videa: [(k, kraj A u snimci, početak B u snimci, vrijeme reza u gotovom videu)]."""
    return [(k, cuts[k - 1]["b"], cuts[k]["a"], cuts[k]["o"]) for k in range(1, len(cuts))]


def nadji_rez(od, do, cuts):
    """Indeks kadra B (k) za rez s krajem A = od i početkom B = do, ili None. Prvo oba vremena, pa jedno."""
    gr = granice(cuts)
    best = None
    for k, a, b, _ in gr:
        if abs(a - od) <= TOL and abs(b - do) <= TOL:
            return k
    for k, a, b, _ in gr:
        dd = min(abs(a - od), abs(b - do))
        if dd <= TOL and (best is None or dd < best[0]):
            best = (dd, k)
    return best[1] if best else None


def plan_jedan(eid, tip, e, p, cuts, fps):
    """Prijelaz iz edit.json → ({id, tip, s, e, p, rez, t, n, a_src, b_src}, napomena)."""
    try:
        od, do = float(e["od"]), float(e["do"])
    except (KeyError, TypeError, ValueError) as ex:
        return None, f"efekt {eid} preskočen: {ex}"
    k = nadji_rez(od, do, cuts)
    if k is None:
        return None, f"prijelaz {eid} ({tip}) preskočen: tog reza više nema (video je drukčije izrezan)"
    A, B = cuts[k - 1], cuts[k]
    d = trajanje(p, tip)
    # pola prijelaza na svakoj strani, ali najviše 45 % kadra: ne vidi se prethodni rez, a dva prijelaza
    # na rezovima oko kratkog kadra se ne preklapaju
    n1 = int(round(d / 2 * fps))
    room = int(min(A["b"] - A["a"], B["b"] - B["a"]) * fps * 0.45)
    note = None
    if n1 > room:
        n1 = room
        note = f"prijelaz {eid} ({tip}) skraćen na {2 * n1 / fps:.2f} s (kratak kadar)"
    if 2 * n1 / fps < MIN_T - 1e-6 or n1 < 2:
        return None, f"prijelaz {eid} ({tip}) preskočen: kadar uz rez je prekratak"
    t = B["o"]
    x = {"id": eid, "tip": tip, "s": t - n1 / fps, "e": t + n1 / fps, "t": t, "n": 2 * n1, "rez": k,
         "a_src": A["b"] - n1 / fps, "b_src": B["a"] - n1 / fps, "p": dict(p, trajanje=round(2 * n1 / fps, 3))}
    return x, note


# ---------------------------------------------------------------- ffmpeg
def _f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _ease(q):
    return f"(({q})*({q})*(3-2*({q})))"


def xfade_name(x):
    """Ugrađeni prijelaz ffmpega (xfade) ili None za naš prijelaz (maska, vrata)."""
    T = TIPOVI[x["tip"]]
    name = T["xfade"]
    if name in ("maska", "vrata"):
        return None
    if T.get("smjer"):
        name += SMJEROVI.get(str(x["p"].get("smjer") or "lijevo").lower(), "left")
    return name


def maska(x, j, W, H):
    """Maska kadra B za sličicu j prijelaza s maskom (0–255, numpy H×W): 255 = novi kadar.
    Računa se u numpyju (izraz po pikselu u ffmpegu bio bi ~100× sporiji)."""
    import numpy as np
    q = min(1.0, j / max(1, x["n"] - 1))       # prva sličica = kadar A, zadnja = kadar B
    e = q * q * (3 - 2 * q)
    if x["tip"] == "iris":
        lice = x["p"].get("lice")
        cx, cy = (float(lice["x"]) * W, float(lice["y"]) * H) if lice else (W / 2, H * 0.42)
        R = max(((cx - a) ** 2 + (cy - b) ** 2) ** 0.5 for a in (0, W) for b in (0, H)) * 1.02
        f = max(2.0, min(W, H) / 200)              # meki rub (px), bez stepenica
        yy, xx = np.ogrid[:H, :W]
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        m = np.clip((e * (R + f) - d) / f, 0, 1)
    else:  # rolete: u svakoj traci novi kadar se spušta odozgo
        h = H / ROLETE
        f = max(1.5, H / 600)
        y = np.arange(H, dtype=np.float64)
        col = np.clip((e * (h + f) - np.mod(y, h)) / f, 0, 1)
        m = np.repeat(col[:, None], W, axis=1)
    return (m * 255 + 0.5).astype(np.uint8)


def pripremi_maske(px, proj, W, H, frames=None):
    """PNG maske za prijelaze s maskom u _tmp/ (Pillow: radi i s č/ž u putanji na Windowsu)."""
    from pathlib import Path

    from PIL import Image
    d = Path(proj) / "_tmp"
    d.mkdir(exist_ok=True)
    for x in px:
        if TIPOVI[x["tip"]]["xfade"] != "maska":
            continue
        for old in d.glob(f"maska_{x['id']}_*.png"):
            old.unlink()
        for j in (range(x["n"]) if frames is None else frames):
            Image.fromarray(maska(x, j, W, H), "L").save(d / f"maska_{x['id']}_{j:03d}.png", compress_level=1)


def ulazi(px, src, off, fps, start=None):
    """Ulazi za ffmpeg: za svaki prijelaz dva kratka komada snimke (kadar A s ručkom, kadar B s ručkom)
    i, za iris/rolete, niz maski. start = prva maska (za jednu sličicu)."""
    args = []
    for x in px:
        dur = (x["n"] + 2) / fps
        for t0 in (x["a_src"], x["b_src"]):
            args += ["-threads", "1", "-ss", f"{max(0.0, t0 - off - 0.25 / fps):.4f}", "-t", f"{dur:.4f}", "-i", src]
        if TIPOVI[x["tip"]]["xfade"] == "maska":
            args += ["-framerate", str(fps), "-start_number", str(start or 0), "-i", f"_tmp/maska_{x['id']}_%03d.png"]
    return args


def broj_ulaza(x):
    return 3 if TIPOVI[x["tip"]]["xfade"] == "maska" else 2


def _komad(lab, x, grade, zoom, fmt):
    chain = f"{lab}setpts=PTS-STARTPTS,trim=end_frame={x['n']},setpts=PTS-STARTPTS,{grade}"
    if zoom:
        chain += f",{zoom}"
    return chain + f",settb=AVTB,format={fmt}"


def _spoj(x, ia, ib, im, fps, grade, za, zb, i, W):
    """Filteri jednog prijelaza → [pxi] (n sličica, vrijeme od 0)."""
    name = xfade_name(x)
    if name:
        d = x["n"] / fps
        tr = TIPOVI[x["tip"]].get("trag")      # zamah: mutni trag = prosjek susjednih sličica
        trag = ""
        if tr:  # usred zamaha slika se razmaže vodoravno (brzi pomak kamere), na rubovima je oštra
            sm = str(x["p"].get("smjer") or "lijevo").lower()
            sx, sy = (max(4, W // 18), 1) if sm in ("lijevo", "desno") else (1, max(4, W // 18))
            trag = (f",tmix=frames=3,avgblur=sizeX={sx}:sizeY={sy}:"
                    f"enable='between(t,{_f(0.12 * d)},{_f(0.88 * d)})'")
        return [_komad(f"[{ia}:v]", x, grade, za, "yuv444p") + f"[pa{i}]",
                _komad(f"[{ib}:v]", x, grade, zb, "yuv444p") + f"[pb{i}]",
                f"[pa{i}][pb{i}]xfade=transition={name}:duration={_f(d)}:offset=0{trag},format=yuv420p[px{i}]"]
    if TIPOVI[x["tip"]]["xfade"] == "vrata":  # lijeva polovica ode lijevo, desna desno, iza je novi kadar
        D = (x["n"] - 1) / fps
        e = _ease(f"clip(t/{_f(D)},0,1)")
        return [_komad(f"[{ia}:v]", x, grade, za, "yuv420p") + f",split=2[pl{i}][pr{i}]",
                f"[pl{i}]crop=iw/2:ih:0:0[pal{i}]",
                f"[pr{i}]crop=iw-iw/2:ih:iw/2:0[par{i}]",
                _komad(f"[{ib}:v]", x, grade, zb, "yuv420p") + f"[pb{i}]",
                f"[pb{i}][pal{i}]overlay=x='-{_f(W / 2 + 2)}*{e}':y=0:eval=frame[pd{i}]",
                f"[pd{i}][par{i}]overlay=x='{W // 2}+{_f(W / 2 + 2)}*{e}':y=0:eval=frame,format=yuv420p[px{i}]"]
    return [_komad(f"[{ia}:v]", x, grade, za, "yuv420p") + f"[pa{i}]",
            _komad(f"[{ib}:v]", x, grade, zb, "yuv420p") + f"[pb{i}]",
            f"[{im}:v]setpts=PTS-STARTPTS,settb=AVTB,format=gray[pm{i}]",
            f"[pb{i}][pm{i}]alphamerge[pc{i}]",
            f"[pa{i}][pc{i}]overlay=0:0:format=auto:shortest=1,format=yuv420p[px{i}]"]


def graf(px, prvi, vin, vout, W, H, fps, grade, zoom_a, zoom_b):
    """Filteri: prijelazi preko glavne trake `vin` → `vout`. prvi = indeks prvog ulaza prijelaza;
    zoom_a/zoom_b(x) = lanac zuma stila za kadar A/B (ili None)."""
    g = []
    cur = vin
    eps = 0.5 / fps
    k = prvi
    for i, x in enumerate(px):
        g += _spoj(x, k, k + 1, k + 2, fps, grade, zoom_a(x), zoom_b(x), i, W)
        k += broj_ulaza(x)
        g[-1] = g[-1].replace(f"[px{i}]", f",setpts=PTS-STARTPTS+{_f(x['s'])}/TB[px{i}]")
        nxt = vout if i == len(px) - 1 else f"[pv{i}]"
        g.append(f"{cur}[px{i}]overlay=0:0:eof_action=pass:repeatlast=0:"
                 f"enable='between(t,{_f(x['s'] - eps)},{_f(x['e'] - eps)})'{nxt}")
        cur = nxt
    return g


def u_prijelazu(px, pre):
    return next((x for x in px if x["s"] - 1e-6 <= pre < x["e"] - 1e-6), None)


def slika(x, pre, src, off, W, H, fps, grade, zoom_a, zoom_b, rep, png, proj="."):
    """Jedna sličica gotovog videa (vrijeme `pre`, prije brzine) usred prijelaza → ffmpeg naredba.
    rep = filteri iza prijelaza (efekti, titlovi) kao popis."""
    j = max(0, min(x["n"] - 1, int(round((pre - x["s"]) * fps))))
    pripremi_maske([x], proj, W, H)
    fc = _spoj(x, 0, 1, 2, fps, grade, zoom_a, zoom_b, 0, W)
    fc[-1] = fc[-1].replace("[px0]", f",trim=start_frame={j}:end_frame={j + 1},setpts=PTS-STARTPTS+{pre:.4f}/TB"
                            + "".join("," + r for r in rep) + "[out]")
    return [ffmpeg(), "-y", "-v", "error", *ulazi([x], src, off, fps), "-filter_complex", ";".join(fc),
            "-map", "[out]", "-frames:v", "1", png]
