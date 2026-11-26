"""Naslovna sličica (M3.4b): najbolji kadar (lice, oštrina, otvorene oči, svjetlo) + kratki tekst.

  python naslovna.py shofe_projekt                 video koji gledaš (reel_vN), inače svi gotovi isječci
  python naslovna.py shofe_projekt K1,K3           ti isječci;  isjecci = svi;  v3 = reel_v3
  python naslovna.py shofe_projekt K1 --tekst "ČISTA KLIMA ZA *5 MIN*"   tekst (*zvjezdice* = boja isticanja)
  python naslovna.py shofe_projekt K1 --kadar 3    uzmi 3. kandidata s <video>.naslovna_kandidati.jpg
  python naslovna.py shofe_projekt K1 --vrijeme 0:12.5   kadar iz te sekunde gotovog videa
  python naslovna.py shofe_projekt K1 --bez-teksta

Za svaki video napravi uz njega:
  <video>.naslovna_9x16.jpg     1080×1920: Instagram/TikTok/YouTube Shorts; lice i tekst stoje u
                                sredini 3:4 (1080×1440) koju Instagram pokazuje na profilu
  <video>.naslovna_16x9.jpg     1280×720: YouTube (iz izvorne vodoravne snimke kad postoji)
  <video>.naslovna_kandidati.jpg   6 najboljih kadrova s ocjenom (za --kadar)
  <video>.naslovna_pregled.jpg  obje sličice + crte Instagramove mreže (za provjeru očima)
Izbor (tekst, kadar) pamti se u naslovna.json, pa nova naredba s drugim tekstom zadrži kadar.
Kadar se uzima iz source.mp4 (bez titlova i hooka), s bojom slike iz stila videa.
"""
import argparse
import re
import subprocess
from pathlib import Path

import numpy as np

from common import FONTS_DIR, GRADES, die, ffmpeg, fmt_time, load_json, run, save_json, video_info

DATOTEKA = "naslovna.json"
VELICINA = {"9x16": (1080, 1920), "16x9": (1280, 720)}
MREZA_34 = 240          # px gore i dolje koje Instagramova mreža (3:4) odreže od 1080×1920
TEKST_9x16 = (270, 1250)  # y-raspon za tekst: ispod gornjih 14 %, iznad donjih 35 % (sučelje mreža)
RUB = 70                # px s lijeva i desna (6 % širine)
FPS_KANDIDATA = 2.0     # kadrova u sekundi za ocjenu
MAX_KANDIDATA = 240
RAZMAK = 1.5            # s između kandidata na popisu
BROJ_KANDIDATA = 6
SIRINA_ANALIZE = 540
DUGI_TEKST = 32         # znakova; dulje je teško čitljivo na malom ekranu

HDR_CHAIN = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
             "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


class Greska(Exception):
    pass


# ---------------------------------------------------------------- vremena: gotovi video ↔ source.mp4
def edit_videa(proj, v):
    """edit (rječnik) iz kojeg je video renderiran: isjecci/K1….edit.json ili verzije/edit_vN.json."""
    import verzije
    proj = Path(proj)
    if v["vrsta"] == "isjecak":
        p = (proj / v["video"]).with_suffix(".edit.json")
    else:
        m = re.search(r"reel_v(\d+)", v["video"])
        p = verzije.vdir(proj) / f"edit_v{m.group(1)}.json" if m else proj / "edit.json"
    if not p.exists():
        p = proj / "edit.json"
    if not p.exists():
        raise Greska(f"ne znam iz kojeg je dijela snimke {v['video']} (nema {p.name})")
    return load_json(p)


def rezovi(proj, edit):
    """Dijelovi source.mp4 koji su u gotovom videu: [{'a','b','o'}] (o = početak u gotovom videu)."""
    import render
    pj = load_json(Path(proj) / "project.json")
    words = load_json(Path(proj) / "transcript.json")["words"]
    st = render.resolve_style(edit)
    cuts, _, total = render.build_cuts(words, edit, st, pj["fps"], pj["duration"])
    speed = float(edit.get("brzina") or 1.0)
    return cuts, total / speed, st, speed


def u_izvor(t_out, cuts, speed=1.0):
    """Sekunda gotovog videa → sekunda source.mp4."""
    t = max(0.0, t_out * speed)
    for c in cuts:
        if c["o"] <= t < c["o"] + (c["b"] - c["a"]):
            return c["a"] + (t - c["o"])
    return cuts[-1]["b"] - 0.05 if cuts else 0.0


def u_video(t_src, cuts, speed=1.0):
    for c in cuts:
        if c["a"] - 1e-6 <= t_src <= c["b"] + 1e-6:
            return (c["o"] + t_src - c["a"]) / speed
    return None


def dijelovi_za_ocjenu(cuts, rub=0.25, spoji=2.0):
    """Dijelovi source.mp4 koje treba pregledati: rezovi bez samog ruba, bliski rezovi spojeni
    (jedan ffmpeg za njih). → [(a, b, [rezovi])]."""
    out = []
    for c in cuts:
        a, b = c["a"] + rub, c["b"] - rub
        if b <= a:
            a = b = (c["a"] + c["b"]) / 2
        if out and a - out[-1][1] < spoji:
            out[-1] = (out[-1][0], b, out[-1][2] + [(a, b)])
        else:
            out.append((a, b, [(a, b)]))
    return out


def ucitaj_kadrove(src, cuts, w, h, maks=MAX_KANDIDATA):
    """BGR sličice (w×h) iz source.mp4 svakih 1/fps unutar rezova → {sekunda source.mp4: sličica}.
    fps = FPS_KANDIDATA, manje za dugi video (najviše `maks` sličica)."""
    total = sum(c["b"] - c["a"] for c in cuts)
    fps = min(FPS_KANDIDATA, maks / max(total, 1e-3))
    n = w * h * 3
    out = {}
    for a, b, unutra in dijelovi_za_ocjenu(cuts):
        dur = b - a + 1.0 / fps
        cmd = [ffmpeg(), "-v", "error", "-ss", f"{a:.3f}", "-i", str(src), "-t", f"{dur:.3f}", "-an",
               "-vf", f"fps={fps:.4f}:round=near,scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        buf = subprocess.run(cmd, capture_output=True).stdout
        for i in range(len(buf) // n):
            t = round(a + i / fps, 3)
            if any(x - 1e-3 <= t <= y + 1e-3 for x, y in unutra):
                out[t] = np.frombuffer(buf[i * n:(i + 1) * n], np.uint8).reshape(h, w, 3)
    return out


def _detektor(w, h):
    import kadar
    return kadar.detector(w, h)


def mjere(img, det):
    """Sirove mjere jednog kadra: lice (najveće), oštrina, oči, svjetlo, položaj."""
    import cv2
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    m = {"svjetlo": float(g.mean()), "ostrina_slike": float(cv2.Laplacian(g, cv2.CV_32F).var()),
         "lice": None, "lica": 0}
    _, res = det.detect(img)
    faces = [] if res is None else sorted(res, key=lambda d: -d[2] * d[3])
    m["lica"] = len(faces)
    if not faces:
        return m
    d = faces[0]
    x, y, fw, fh = map(float, d[:4])
    lm = [float(v) for v in d[4:14]]
    x0, y0, x1, y1 = int(max(x, 0)), int(max(y, 0)), int(min(x + fw, w)), int(min(y + fh, h))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return m
    fb = g[y0:y1, x0:x1]
    fb128 = cv2.resize(fb, (128, int(128 * fb.shape[0] / fb.shape[1]) or 1), interpolation=cv2.INTER_AREA)
    e1, e2, nos = np.array(lm[0:2]), np.array(lm[2:4]), np.array(lm[4:6])
    ed = max(4.0, float(np.linalg.norm(e2 - e1)))
    oci = []
    for e in (e1, e2):
        rx, ry = max(2, int(0.22 * ed)), max(2, int(0.14 * ed))
        p = g[max(0, int(e[1]) - ry):int(e[1]) + ry, max(0, int(e[0]) - rx):int(e[0]) + rx]
        if p.size >= 16:
            oci.append(float(p.std()))
    sredina = (e1 + e2) / 2
    m["lice"] = {
        "x": (x + fw / 2) / w, "y": (y + fh / 2) / h, "w": fw / w, "h": fh / h, "s": float(d[14]),
        "box": [x / w, y / h, (x + fw) / w, (y + fh) / h],
        "ostrina": float(cv2.Laplacian(fb128, cv2.CV_32F).var()),
        "oci": (float(np.mean(oci)) / (float(fb.std()) + 1.0)) if oci else 0.0,
        "svjetlo": float(fb.mean()),
        "frontalno": float(max(0.0, 1.0 - 2.0 * abs(nos[0] - sredina[0]) / ed)),
        "u_kadru": bool(x >= 0 and y >= 0 and x + fw <= w and y + fh <= h),
    }
    return m


def _rel(v, ref):
    return float(min(1.0, v / ref)) if ref > 0 else 0.0


def _svjetlo(b):
    """0–1: dobro osvijetljeno 70–190 (0–255)."""
    if 70 <= b <= 190:
        return 1.0
    return float(max(0.0, 1.0 - (70 - b) / 50)) if b < 70 else float(max(0.0, 1.0 - (b - 190) / 45))


def ocijeni(mj, trenuci=()):
    """Mjere svih kandidata → ocjena 0–10 i razlog. Oštrina i oči se mjere prema najboljima u istom
    videu (ista osoba, ista kamera), pa ne ovise o svjetlu ni kameri."""
    lica = [m["lice"] for m in mj.values() if m["lice"]]
    ref_ostr = np.percentile([l["ostrina"] for l in lica], 90) if lica else 0

    def ref_oci(l):   # oči se uspoređuju s licima slične veličine (malo lice = manje detalja oko očiju)
        sl = [x["oci"] for x in lica if 0.75 <= x["h"] / l["h"] <= 1.33]
        return np.percentile(sl, 90) if sl else 0
    ref_slika = np.percentile([m["ostrina_slike"] for m in mj.values()], 90) if mj else 0
    out = {}
    for t, m in mj.items():
        l = m["lice"]
        razlozi = []
        bonus = 0.0
        for tr in trenuci:
            if tr.get("od", 0) - 0.3 <= t <= tr.get("do", 0) + 0.3:
                bonus = max(bonus, 0.5 * min(5, tr.get("ocjena") or 3) / 5)
        if l:
            vel = float(np.clip((l["h"] - 0.05) / 0.15, 0, 1))
            ostr = _rel(l["ostrina"], ref_ostr)
            oci_rel = _rel(l["oci"], ref_oci(l))
            oci = float(np.clip((oci_rel - 0.6) / 0.25, 0, 1))
            svj = _svjetlo(l["svjetlo"])
            sred = 1.0 if (l["u_kadru"] and abs(l["x"] - 0.5) < 0.3) else 0.0
            s = 2 + 3 * vel + 2 * ostr + 1.5 * oci + 2 * svj + 0.5 * sred + 0.5 * l["frontalno"] + bonus
            s = s / 12.0 * 10 * (0.8 + 0.2 * oci)     # zatvorene oči kvare inače dobar kadar
            if vel < 0.6:
                razlozi.append("lice malo")
            if ostr < 0.6:
                razlozi.append("mutno")
            if oci < 0.5 and ostr >= 0.6:
                razlozi.append("oči zatvorene?")
            if svj < 0.6:
                razlozi.append("tamno" if l["svjetlo"] < 70 else "presvijetlo")
            if not sred:
                razlozi.append("lice uz rub")
            if l["frontalno"] < 0.5:
                razlozi.append("lice iz profila")
            if m["lica"] > 1:
                razlozi.append(f"{m['lica']} lica")
        else:
            s = (3 * _rel(m["ostrina_slike"], ref_slika) + 2 * _svjetlo(m["svjetlo"]) + bonus) / 12.0 * 10
            razlozi.append("nema lica")
        if bonus:
            razlozi.append("jak trenutak")
        out[t] = {"ocjena": round(float(s), 2), "razlog": ", ".join(razlozi) or "lice veliko, oštro, oči otvorene"}
    return out


def najbolji(ocjene, n=BROJ_KANDIDATA, razmak=RAZMAK):
    """Najbolji kadrovi, barem `razmak` s jedan od drugoga."""
    out = []
    for t, o in sorted(ocjene.items(), key=lambda kv: -kv[1]["ocjena"]):
        if all(abs(t - x["izvor"]) >= razmak for x in out):
            out.append({"izvor": t, **o})
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- tekst
def font_datoteka(ime):
    ime = (ime or "Montserrat Black").strip()
    for c in (ime.replace(" ", "-") + ".ttf", ime.replace(" ", "") + "-Regular.ttf", ime + "-Regular.ttf"):
        if (FONTS_DIR / c).exists():
            return FONTS_DIR / c
    return FONTS_DIR / "Montserrat-Black.ttf"


_FONT_BAJTOVI = {}


def ucitaj_font(path, size):
    """Font iz bajtova (FreeType na Windowsu ne voli putanje s kvačicama, npr. C:/Users/Šimun)."""
    import io
    from PIL import ImageFont
    p = str(path)
    if p not in _FONT_BAJTOVI:
        _FONT_BAJTOVI[p] = Path(p).read_bytes()
    return ImageFont.truetype(io.BytesIO(_FONT_BAJTOVI[p]), size)


def tokeni(tekst):
    """'ČISTA KLIMA za *5 MIN*' → [('ČISTA', False), ('KLIMA', False), ('ZA', False), ('5', True), ('MIN', True)]."""
    out, ist = [], False
    for dio in re.split(r"(\*)", tekst or ""):
        if dio == "*":
            ist = not ist
            continue
        for w in dio.split():
            out.append((w.upper(), ist))
    return out


def _particije(n, k):
    """Sve podjele n riječi u najviše k redaka → popisi indeksa početka redaka."""
    if n == 0:
        return
    yield [0]
    if k > 1:
        for i in range(1, n):
            for rest in _particije(n - i, k - 1):
                if len(rest) < k:
                    yield [0] + [i + r for r in rest]


def prelomi(tok, font, max_w, max_redaka=3):
    """Najbolji prijelom u retke koji stanu u max_w, ili None. Redak ne završava jednoslovnom riječi
    („u", „i", „s"…, hrvatski pravopis), riječ od 1–2 znaka ne stoji sama u retku; manje redaka i
    ujednačenije duljine su bolje."""
    n = len(tok)
    best = None
    if n > 12:   # predug tekst: samo pohlepno
        lines, cur = [], []
        for t in tok:
            if cur and font.getlength(" ".join(w for w, _ in cur + [t])) > max_w:
                lines.append(cur)
                cur = []
            cur.append(t)
        lines.append(cur)
        return lines if len(lines) <= max_redaka else None
    for starts in _particije(n, max_redaka):
        lines = [tok[a:b] for a, b in zip(starts, starts[1:] + [n])]
        sir = [font.getlength(" ".join(w for w, _ in ln)) for ln in lines]
        if max(sir) > max_w:
            continue
        kazna = 0.0
        for k, ln in enumerate(lines):
            if k < len(lines) - 1 and len(ln[-1][0]) == 1 and ln[-1][0].isalpha():
                kazna += 3
            if len(ln) == 1 and len(ln[0][0]) <= 2 and n > 1:
                kazna += 3
            if k < len(lines) - 1 and ln[-1][1] and lines[k + 1][0][1]:
                kazna += 1          # istaknuta skupina (*Renault 4*) ostaje u jednom retku
        cijena = kazna + 0.6 * len(lines) + float(np.std(sir)) / max_w
        if best is None or cijena < best[0]:
            best = (cijena, lines)
    return best[1] if best else None


def slozi_tekst(tekst, font_path, box, max_size=200, min_size=40, max_redaka=3):
    """Najveći font s kojim tekst stane u box (x0, y0, x1, y1). → (font, retci, visina retka) ili None."""
    tok = tokeni(tekst)
    if not tok:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    po_broju = {}    # broj redaka → najveći font s dobrim prijelomom
    size = max_size
    while size >= min_size:
        f = ucitaj_font(font_path, size)
        lh = int(size * 1.08)
        lines = prelomi(tok, f, bw, max_redaka=min(max_redaka, max(1, bh // lh)))
        if lines and (_dobar(lines) or size <= min_size + 30):
            po_broju.setdefault(len(lines), (f, lines, lh))
        size -= 6
    if po_broju:
        # najveći font, ali manje redaka ako su slova tek malo manja (lakše se čita u jednom pogledu)
        izbor = max(po_broju.values(), key=lambda r: r[0].size)
        for n in sorted(po_broju):
            if n < len(izbor[1]) and po_broju[n][0].size >= 0.85 * izbor[0].size:
                izbor = po_broju[n]
                break
        return izbor
    f = ucitaj_font(font_path, min_size)
    return f, prelomi(tok, f, bw, 99) or [tok], int(min_size * 1.08)


def _dobar(lines):
    """Prijelom bez pravopisnih kazni (inače probaj manji font)."""
    for k, ln in enumerate(lines):
        if k < len(lines) - 1 and len(ln[-1][0]) == 1 and ln[-1][0].isalpha():
            return False
        if len(ln) == 1 and len(ln[0][0]) <= 2 and len(lines) > 1:
            return False
    return True


def nacrtaj_tekst(img, tekst, font_path, box, boja, ist, obrub_boja="#000000", poravnanje="sredina",
                  okomito="sredina", max_size=200):
    """Nacrta tekst u box; vrati stvarni pravokutnik teksta (x0, y0, x1, y1) ili None."""
    from PIL import ImageDraw
    r = slozi_tekst(tekst, font_path, box, max_size=max_size)
    if not r:
        return None
    f, lines, lh = r
    d = ImageDraw.Draw(img)
    stroke = max(3, int(f.size * 0.09))
    total_h = len(lines) * lh
    if okomito == "gore":
        y = box[1]
    elif okomito == "dolje":
        y = box[3] - total_h
    else:
        y = box[1] + (box[3] - box[1] - total_h) // 2
    asc = f.getmetrics()[0]
    cap = f.getbbox("H")[1]   # razmak od vrha retka do vrha velikog slova
    real = [10 ** 9, 10 ** 9, -1, -1]
    for ln in lines:
        lw = f.getlength(" ".join(w for w, _ in ln))
        if poravnanje == "lijevo":
            x = box[0]
        elif poravnanje == "desno":
            x = box[2] - lw
        else:
            x = box[0] + (box[2] - box[0] - lw) / 2
        yy = y - cap + (lh - (asc - cap)) // 2
        for k, (w, hi) in enumerate(ln):
            word = w + (" " if k < len(ln) - 1 else "")
            d.text((x, yy), w, font=f, fill=ist if hi else boja, stroke_width=stroke, stroke_fill=obrub_boja)
            bb = d.textbbox((x, yy), w, font=f, stroke_width=stroke)
            real = [min(real[0], bb[0]), min(real[1], bb[1]), max(real[2], bb[2]), max(real[3], bb[3])]
            x += f.getlength(word)
        y += lh
    return tuple(int(v) for v in real)


def zatamni(img, y0, y1, gore=True, jacina=0.55):
    """Blagi tamni prijelaz iza teksta (čitljivost na svijetloj pozadini)."""
    from PIL import Image
    w, h = img.size
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if y1 <= y0:
        return img
    a = np.linspace(jacina, 0, y1 - y0) if gore else np.linspace(0, jacina, y1 - y0)
    mask = np.zeros((h, w), np.uint8)
    mask[y0:y1, :] = (a * 255).astype(np.uint8)[:, None]
    crno = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(crno, img, Image.fromarray(mask, "L"))


# ---------------------------------------------------------------- slaganje sličica
def kadar_slika(proj, src, t, grade, vf_pre=None):
    """Jedan kadar (PIL RGB) u punoj rezoluciji, s bojom slike iz stila."""
    from PIL import Image
    tmp = Path(proj) / "_tmp"
    tmp.mkdir(exist_ok=True)
    png = tmp / "naslovna_kadar.png"
    chain = ([vf_pre] if vf_pre else []) + ([grade] if grade else [])
    cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(Path(src).resolve()), "-frames:v", "1"]
    if chain:
        cmd += ["-vf", ",".join(chain)]
    run(cmd + [png.name], cwd=tmp)
    with Image.open(png) as im:
        return im.convert("RGB")


def lice_na(img_pil):
    """Najveće lice na slici → (x0, y0, x1, y1) u pikselima ili None."""
    lica = lica_na(img_pil)
    return lica[0] if lica else None


def lica_na(img_pil):
    """Sva lica na slici, najveće prvo → [(x0, y0, x1, y1)] u pikselima."""
    import cv2
    w, h = img_pil.size
    s = min(1.0, SIRINA_ANALIZE / max(w, h) * 1.6)
    aw, ah = max(32, int(w * s)), max(32, int(h * s))
    arr = cv2.resize(cv2.cvtColor(np.asarray(img_pil), cv2.COLOR_RGB2BGR), (aw, ah), interpolation=cv2.INTER_AREA)
    det = _detektor(aw, ah)
    _, res = det.detect(arr)
    if res is None or not len(res):
        return []
    return [tuple(float(v) / s for v in (d[0], d[1], d[0] + d[2], d[1] + d[3]))
            for d in sorted(res, key=lambda d: -d[2] * d[3])]


def cover(img, W, H, cx=0.5, cy=0.5):
    """Izreži i skaliraj sliku da popuni W×H; (cx, cy) = točka koja treba ostati u kadru (0–1)."""
    from PIL import Image
    w, h = img.size
    s = max(W / w, H / h)
    nw, nh = int(round(w * s)), int(round(h * s))
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int(np.clip(cx * nw - W / 2, 0, nw - W))
    y = int(np.clip(cy * nh - H / 2, 0, nh - H))
    return im.crop((x, y, x + W, y + H))


def napravi_9x16(img, face, tekst, st):
    """→ (slika 1080×1920, raspored {'lice', 'tekst'})."""
    W, H = VELICINA["9x16"]
    w, h = img.size
    if face:
        fcx, fcy = (face[0] + face[2]) / 2 / w, (face[1] + face[3]) / 2 / h
    else:
        fcx, fcy = 0.5, 0.45
    out = cover(img, W, H, fcx, fcy)
    s = max(W / w, H / h)
    ox = int(np.clip(fcx * w * s - W / 2, 0, w * s - W))
    oy = int(np.clip(fcy * h * s - H / 2, 0, h * s - H))
    lice = None
    if face:
        lice = tuple(int(v) for v in (face[0] * s - ox, face[1] * s - oy, face[2] * s - ox, face[3] * s - oy))
    rez = {"lice": lice, "tekst": None, "upozorenja": []}
    if lice and (lice[1] < MREZA_34 or lice[3] > H - MREZA_34):
        rez["upozorenja"].append("lice izlazi iz dijela koji Instagram pokazuje na profilu (3:4)")
    if not tekst:
        return out, rez
    y_lo, y_hi = TEKST_9x16
    if lice:
        gore = (y_lo, lice[1] - 30)
        dolje = (lice[3] + 40, y_hi)
        if dolje[1] - dolje[0] < 260:       # malo mjesta ispod lica: smije do dna 3:4 mreže
            dolje = (lice[3] + 40, H - MREZA_34 - 40)
        mjesto, okom = (gore, "dolje") if gore[1] - gore[0] >= dolje[1] - dolje[0] else (dolje, "gore")
        if mjesto[1] - mjesto[0] < 220:     # lice je preveliko: tekst preko donjeg dijela lica, uz zatamnjenje
            mjesto, okom = (max(y_lo, H - MREZA_34 - 520), H - MREZA_34 - 40), "dolje"
            rez["upozorenja"].append("tekst djelomično preko lica — probaj kraći tekst ili drugi kadar")
    else:
        mjesto, okom = (y_lo, y_lo + 520), "gore"
    box = (RUB, int(mjesto[0]), W - RUB, int(mjesto[1]))
    gore_tekst = box[3] <= H / 2
    out = zatamni(out, 0 if gore_tekst else box[1] - 120, box[3] + 140 if gore_tekst else H, gore=gore_tekst)
    t = nacrtaj_tekst(out, tekst, font_datoteka(st.get("hook_font") or st.get("font")), box,
                      st.get("boja_teksta", "#FFFFFF"), st.get("boja_isticanja", "#FFC21A"),
                      okomito=okom, max_size=190)
    rez["tekst"] = t
    return out, rez


def napravi_16x9(img, face, tekst, st):
    """→ (slika 1280×720, raspored). Uspravni kadar: oštra osoba s jedne strane, mutna ista slika iza."""
    from PIL import Image, ImageEnhance, ImageFilter
    W, H = VELICINA["16x9"]
    w, h = img.size
    rez = {"lice": None, "tekst": None, "upozorenja": []}
    fcx = ((face[0] + face[2]) / 2 / w) if face else 0.5
    fcy = ((face[1] + face[3]) / 2 / h) if face else 0.45
    if w / h >= 1.5:                       # vodoravna snimka: zum na lice, lice na trećinu
        fh = (face[3] - face[1]) / h if face else 0.3
        zum = float(np.clip(0.5 / max(fh, 1e-3), 1.0, 1.8))
        cw, ch = w / zum, h / zum
        strana = "desno" if fcx >= 0.5 else "lijevo"
        tx = fcx * w - (cw * (0.68 if strana == "desno" else 0.32))
        x0 = float(np.clip(tx, 0, w - cw))
        y0 = float(np.clip(fcy * h - ch * 0.42, 0, h - ch))
        out = img.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS)
        if face:
            s = W / cw
            rez["lice"] = tuple(int(v) for v in ((face[0] - x0) * s, (face[1] - y0) * s,
                                                  (face[2] - x0) * s, (face[3] - y0) * s))
        tekst_lijevo = strana == "desno"
    else:                                 # uspravna snimka: osoba desno (3:4 izrez), mutna pozadina
        bg = cover(img, W, H, fcx, fcy).filter(ImageFilter.GaussianBlur(28))
        bg = ImageEnhance.Brightness(bg).enhance(0.55)
        fw = int(H * 0.8)
        fg = cover(img, fw, H, fcx, fcy)
        x = W - fw - 40
        bg.paste(fg, (x, 0))
        out = bg
        if face:
            s = max(fw / w, H / h)
            ox = int(np.clip(fcx * w * s - fw / 2, 0, w * s - fw))
            oy = int(np.clip(fcy * h * s - H / 2, 0, h * s - H))
            rez["lice"] = tuple(int(v) for v in (face[0] * s - ox + x, face[1] * s - oy,
                                                  face[2] * s - ox + x, face[3] * s - oy))
        tekst_lijevo = True
    if not tekst:
        return out, rez
    lice = rez["lice"]
    if tekst_lijevo:
        x1 = (lice[0] - 30) if lice else W // 2
        box = (50, 50, int(max(W * 0.42, min(x1, W * 0.6))), H - 60)
    else:
        x0 = (lice[2] + 30) if lice else W // 2
        box = (int(min(max(W * 0.58, x0), W * 0.4)), 50, W - 50, H - 110)   # dolje desno je trajanje videa
    a = np.zeros((H, W), np.float32)
    span = np.linspace(0.6, 0, W // 2)
    if tekst_lijevo:
        a[:, :W // 2] = span[None, :]
    else:
        a[:, W - W // 2:] = span[::-1][None, :]
    druga = [f for f in lica_na(out) if not lice or abs((f[0] + f[2]) / 2 - (lice[0] + lice[2]) / 2) > 40]
    out = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), out, Image.fromarray((a * 255).astype(np.uint8), "L"))
    t = nacrtaj_tekst(out, tekst, font_datoteka(st.get("hook_font") or st.get("font")), box,
                      st.get("boja_teksta", "#FFFFFF"), st.get("boja_isticanja", "#FFC21A"),
                      poravnanje="lijevo" if tekst_lijevo else "desno", max_size=150)
    rez["tekst"] = t
    if t and any(f[2] > t[0] and f[0] < t[2] and f[3] > t[1] and f[1] < t[3] for f in druga):
        rez["upozorenja"].append("tekst prekriva drugu osobu — ako smeta, probaj drugi kadar")
    return out, rez


def izvorni_klip(proj, t_src):
    """Originalna snimka i sekunda u njoj za sekundu source.mp4 (za 16:9 iz vodoravne snimke)."""
    pj = load_json(Path(proj) / "project.json")
    for c in pj.get("clips") or []:
        if c.get("start", 0) - 1e-6 <= t_src < c.get("start", 0) + c.get("dur", 0) + 1e-6:
            f = Path(c.get("file", ""))
            if f.exists() and c.get("w") and c.get("h"):
                return f, t_src - c["start"], c
    return None, None, None


def sredina_izreza(pj, clip, t_orig):
    """Gdje je (0–1 širine originala) bilo središte uspravnog kadra u toj sekundi: crop_x iz
    prepare.py ili kadar.py (kadar prati govornika) → koju osobu 9:16 pokazuje."""
    cx = clip.get("crop_x", 0.5)
    for k in clip.get("kadrovi") or []:
        if k["od"] - 1e-6 <= t_orig < k["do"] + 1e-6:
            cx = k["crop_x"]
            break
    W, H, w, h = pj["width"], pj["height"], clip["w"], clip["h"]
    sw = w * max(W / w, H / h)
    return float((cx * (sw - W) + W / 2) / sw)


def pregled_slika(n9, n16, path):
    """Obje sličice jedna do druge; na 9:16 crte gdje Instagramova mreža (3:4) reže."""
    from PIL import Image, ImageDraw
    a = n9.resize((405, 720))
    d = ImageDraw.Draw(a)
    y = int(MREZA_34 * 720 / 1920)
    for yy in (y, 720 - y):
        for x in range(0, 405, 14):
            d.line((x, yy, x + 7, yy), fill=(255, 60, 60), width=2)
    out = Image.new("RGB", (405 + 20 + 1280, 720), (24, 24, 24))
    out.paste(a, (0, 0))
    out.paste(n16, (425, 0))
    out.save(path, quality=88)


def kandidati_slika(frames, kand, path):
    from PIL import Image, ImageDraw
    th = 400
    tiles = []
    f = ucitaj_font(FONTS_DIR / "Montserrat-ExtraBold.ttf", 22)
    for n, k in enumerate(kand, 1):
        arr = frames.get(k["izvor"])
        if arr is None:
            continue
        im = Image.fromarray(arr[:, :, ::-1].copy())
        im = im.resize((int(im.width * th / im.height), th))
        d = ImageDraw.Draw(im)
        d.rectangle((0, th - 64, im.width, th), fill=(0, 0, 0))
        d.text((8, th - 60), f"{n}  {k['ocjena']:.1f}  {fmt_time(k['vrijeme'])}", font=f, fill=(255, 220, 60))
        d.text((8, th - 32), k["razlog"][:40], font=ucitaj_font(FONTS_DIR / "Montserrat-SemiBold.ttf", 16),
               fill=(255, 255, 255))
        tiles.append(im)
    if not tiles:
        return None
    out = Image.new("RGB", (sum(t.width for t in tiles) + 8 * (len(tiles) - 1), th), (255, 255, 255))
    x = 0
    for t in tiles:
        out.paste(t, (x, 0))
        x += t.width + 8
    out.save(path, quality=88)
    return path


# ---------------------------------------------------------------- jedan video
def trenuci(proj):
    p = Path(proj) / "analiza.json"
    try:
        return load_json(p).get("trenuci") or [] if p.exists() else []
    except (OSError, ValueError):
        return []


def analiziraj(proj, v, ispis=print):
    """Ocijeni kadrove videa → (kandidati, sličice, cuts, st, speed)."""
    proj = Path(proj)
    edit = edit_videa(proj, v)
    cuts, total, st, speed = rezovi(proj, edit)
    if not cuts:
        raise Greska(f"{v['video']}: nema ničega u montaži")
    pj = load_json(proj / "project.json")
    aw = SIRINA_ANALIZE if pj["width"] <= pj["height"] else 640
    ah = int(round(aw * pj["height"] / pj["width"] / 2)) * 2
    frames = ucitaj_kadrove(proj / "source.mp4", cuts, aw, ah)
    det = _detektor(aw, ah)
    mj = {t: mjere(fr, det) for t, fr in frames.items()}
    oc = ocijeni(mj, trenuci(proj))
    kand = najbolji(oc)
    for k in kand:
        k["vrijeme"] = round(u_video(k["izvor"], cuts, speed) or 0.0, 2)
    return kand, frames, cuts, edit, st, speed, total


def napravi(proj, v, d, tekst=None, kadar=None, vrijeme=None, bez_teksta=False, ispis=print):
    """Naslovne sličice za video v; d = naslovna.json (mijenja se). → rječnik s datotekama i upozorenjima."""
    proj = Path(proj)
    e = d["videi"].setdefault(v["id"], {})
    e["video"] = v["video"]
    kand, frames, cuts, edit, st, speed, total = analiziraj(proj, v, ispis)
    if not kand:
        raise Greska(f"{v['video']}: nijedan kadar za ocjenu")
    stem = (proj / v["video"]).with_suffix("")
    kp = kandidati_slika(frames, kand, Path(f"{stem}.naslovna_kandidati.jpg"))
    e["kandidati"] = [{"n": n, "vrijeme": k["vrijeme"], "izvor": k["izvor"], "ocjena": k["ocjena"],
                       "razlog": k["razlog"]} for n, k in enumerate(kand, 1)]
    # izbor kadra
    if vrijeme is not None:
        if not 0 <= vrijeme <= total + 0.05:
            raise Greska(f"vrijeme {fmt_time(vrijeme)} je izvan videa (traje {fmt_time(total)})")
        e["izbor"] = {"vrijeme": round(vrijeme, 2), "izvor": round(u_izvor(vrijeme, cuts, speed), 3), "rucno": True}
    elif kadar is not None:
        if not 1 <= kadar <= len(kand):
            raise Greska(f"nema kandidata {kadar} (ima ih {len(kand)}, vidi {Path(kp).name if kp else ''})")
        k = kand[kadar - 1]
        e["izbor"] = {"vrijeme": k["vrijeme"], "izvor": k["izvor"], "rucno": True}
    elif not (e.get("izbor") or {}).get("rucno") or u_video((e.get("izbor") or {}).get("izvor", -1), cuts, speed) is None:
        e["izbor"] = {"vrijeme": kand[0]["vrijeme"], "izvor": kand[0]["izvor"], "rucno": False}
    # tekst
    if bez_teksta:
        e["tekst"] = ""
    elif tekst is not None:
        e["tekst"] = tekst.strip()
    elif "tekst" not in e:
        e["tekst"] = v.get("hook") or ""
    upoz = []
    txt = e["tekst"]
    cist = txt.replace("*", "")
    if txt and (len(cist) > DUGI_TEKST or len(cist.split()) > 6):
        upoz.append(f"tekst je dug ({len(cist.split())} riječi, {len(cist)} znakova) — na naslovnoj 2–5 riječi, "
                    f"ne ponavljaj cijeli naslov: --tekst \"…\"")
    if not txt and not bez_teksta:
        upoz.append("nema teksta (ni hooka) — dodaj: --tekst \"2–5 riječi\"")
    grade = GRADES.get(st.get("boja_slike", "neutralno"), GRADES["neutralno"])
    t_src = e["izbor"]["izvor"]
    img = kadar_slika(proj, proj / "source.mp4", t_src, grade)
    face = lice_na(img)
    n9, r9 = napravi_9x16(img, face, txt, st)
    # 16:9: iz originalne vodoravne snimke kad postoji (širi kadar), inače iz source.mp4
    img16, face16 = img, face
    orig, t_orig, clip = izvorni_klip(proj, t_src)
    if orig is not None and clip["w"] / clip["h"] >= 1.5 and img.width / img.height < 1.5:
        try:
            info = video_info(orig)
            img16 = kadar_slika(proj, orig, t_orig, grade, vf_pre=HDR_CHAIN if info["hdr"] else None)
            # osoba koju pokazuje uspravni kadar (govornik), ne nužno najveće lice
            sx = sredina_izreza(load_json(proj / "project.json"), clip, t_orig) * img16.width
            lica = lica_na(img16)
            face16 = min(lica, key=lambda f: abs((f[0] + f[2]) / 2 - sx)) if lica else None
        except SystemExit:
            img16, face16 = img, face
    n16, r16 = napravi_16x9(img16, face16, txt, st)
    out9, out16 = Path(f"{stem}.naslovna_9x16.jpg"), Path(f"{stem}.naslovna_16x9.jpg")
    n9.save(out9, quality=92)
    n16.save(out16, quality=90)
    pr = Path(f"{stem}.naslovna_pregled.jpg")
    pregled_slika(n9, n16, pr)
    upoz += [f"9:16: {u}" for u in r9["upozorenja"]] + [f"16:9: {u}" for u in r16["upozorenja"]]
    izb = next((k for k in kand if abs(k["izvor"] - t_src) < 0.01), None)
    if izb and "oči zatvorene" in izb["razlog"]:
        upoz.append("na izabranom kadru oči su možda zatvorene — pogledaj kandidate")
    if not face:
        upoz.append("na kadru nema lica — naslovne s licem bolje prolaze; pogledaj kandidate")
    e["datoteke"] = {"9x16": out9.relative_to(proj).as_posix(), "16x9": out16.relative_to(proj).as_posix(),
                     "pregled": pr.relative_to(proj).as_posix(),
                     "kandidati": Path(kp).relative_to(proj).as_posix() if kp else None}
    e["raspored"] = {"9x16": r9, "16x9": r16}
    e["upozorenja"] = upoz
    return e


# ---------------------------------------------------------------- naredbeni redak
def ucitaj(proj):
    p = Path(proj) / DATOTEKA
    d = {}
    if p.exists():
        try:
            d = load_json(p)
        except ValueError as ex:
            raise Greska(f"{DATOTEKA} nije ispravan JSON ({ex})")
    d.setdefault("videi", {})
    return d


def parse_vrijeme(s):
    s = s.strip().replace(",", ".")
    if ":" in s:
        m, _, sec = s.rpartition(":")
        return int(m or 0) * 60 + float(sec)
    return float(s)


def main():
    import objava
    ap = argparse.ArgumentParser(description="Naslovna sličica: najbolji kadar + tekst (9:16 i 16:9)")
    ap.add_argument("projekt")
    ap.add_argument("cilj", nargs="?", default="", help="isjecci | K1,K3 | reel | v3 (zadano: video koji gledaš)")
    ap.add_argument("--tekst", help="tekst na sličici, 2–5 riječi; *riječ* = u boji isticanja stila")
    ap.add_argument("--kadar", type=int, help="broj kandidata s <video>.naslovna_kandidati.jpg")
    ap.add_argument("--vrijeme", help="sekunda gotovog videa (npr. 0:12.5) iz koje se uzima kadar")
    ap.add_argument("--bez-teksta", action="store_true")
    a = ap.parse_args()
    proj = Path(a.projekt)
    if not proj.is_dir():
        die(f"nema mape projekta {proj}")
    try:
        import PIL  # noqa: F401
    except ImportError:
        die("nema paketa Pillow. Pokreni: python doctor.py --popravi")
    try:
        videi = objava.odaberi_videe(proj, a.cilj)
        if (a.tekst is not None or a.kadar or a.vrijeme) and len(videi) > 1:
            raise Greska("--tekst/--kadar/--vrijeme vrijede za jedan video — navedi koji (npr. K1 ili v3)")
        d = ucitaj(proj)
        vr = parse_vrijeme(a.vrijeme) if a.vrijeme else None
        for v in videi:
            e = napravi(proj, v, d, tekst=a.tekst, kadar=a.kadar, vrijeme=vr, bez_teksta=a.bez_teksta)
            save_json(proj / DATOTEKA, d)
            izb = e["izbor"]
            k1 = next((k for k in e["kandidati"] if abs(k["izvor"] - izb["izvor"]) < 0.01), None)
            print(f"{v['id']}  {v['video']}")
            print(f"  kadar: {fmt_time(izb['vrijeme'])} u videu" + (" (tvoj izbor)" if izb["rucno"] else "")
                  + (f", ocjena {k1['ocjena']:.1f}/10 — {k1['razlog']}" if k1 else ""))
            print(f"  tekst: {e['tekst'] or '(bez teksta)'}")
            print(f"  9:16  {proj / e['datoteke']['9x16']}")
            print(f"  16:9  {proj / e['datoteke']['16x9']}")
            print(f"  pregled: {proj / e['datoteke']['pregled']}")
            if e["datoteke"].get("kandidati"):
                print(f"  kandidati: {proj / e['datoteke']['kandidati']}  (drugi kadar: --kadar N)")
                for k in e["kandidati"]:
                    print(f"    {k['n']}. {fmt_time(k['vrijeme'])}  {k['ocjena']:.1f}  {k['razlog']}")
            for u in e["upozorenja"]:
                print(f"  Upozorenje: {u}")
            print()
    except (Greska, objava.Greska) as ex:
        die(str(ex))


if __name__ == "__main__":
    main()
