"""Izdvajanje osobe (M5.7): maska osobe po sličici + tekst iza osobe.

  python osoba.py provjera              je li model spreman (MODNet, 26 MB, skida se prvi put)
  python osoba.py preuzmi               skini model sada (inače se skine pri prvom efektu)
  python osoba.py pokazi slika.png|video.mp4 [--t 0:03] [--tekst "SUNČANO"] [--polozaj auto]
                                        → *_osoba.png: maska (zeleno = pozadina) i tekst iza osobe

Model: MODNet (ZHKKKe/MODNet, Apache-2.0), službeni ONNX „photographic portrait matting", preuzet s izdanja
HivisionIDPhotos (Apache-2.0) na GitHubu. Radi u OpenCV-u (cv2.dnn) na procesoru, bez novih paketa.
Daje mekanu masku (kosa, prsti), ne samo osoba/pozadina. Sličica se smanji na ~384 px po duljoj strani
(~0,1 s na 2 jezgre), maska se vrati na punu veličinu; susjedne maske se zaglade kad se malo razlikuju
(manje treperenja), a kod pokreta ostaje nova maska (bez „duha").

Efekt u edit.json (efekti.py projekt dodaj iza 0:03-0:06 --tekst "SUNČANO"):
  {"tip": "iza", "od", "do", "parametri": {"tekst": "SUNČANO", "boja": "#FFFFFF", "polozaj": "auto"}}
Tekst je velik (Anton), stoji iza glave: osoba prekriva donji dio slova. Ulazi odozdo (0,35 s), na kraju se
utiša (0,25 s). polozaj auto = iznad glave, glava malo zalazi u slova; gore | sredina | dolje ručno.
Render: isti prolaz kao HTML grafika (grafika.umetni) — komad tog dijela gotovog videa s tekstom iza osobe
zamijeni taj dio videa; maske i komad su u predmemoriji (_tmp/grafika), pa se drugi put ne računaju.

Nova pozadina (M5.7b, efekti.py projekt dodaj pozadina 0:00-0:08 [--zamuti 0.5 | --boja | --slika | --video]):
  {"tip": "pozadina", "parametri": {"vrsta": "zamuti"|"boja"|"slika"|"video", "zamuti": 0–1, "boja", "slika", "video"}}
Osoba ostaje, iza nje: zamućena vlastita pozadina (normalizirano zamućenje bez osobe), boja, slika ili video
(pokriju kadar, video u krug). Rub: maska malo stegnuta, stara pozadina oduzeta iz mekanog ruba, light wrap.
HTML grafika iza osobe (grafika s "iza": true): HyperFrames komad, pa osoba ispred. Kod svih: titlovi, naslov i
natpisi (captions.ass) ostaju ispred efekta. Pozadine se umeću prve (grafika.umetni, dvije faze).
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import FONTS_DIR, die, ffmpeg, fmt_time

MODEL = "osoba_modnet.onnx"
MODEL_URL = ("https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/"
             "modnet_photographic_portrait_matting.onnx")
MODEL_SHA = "07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9"
MODEL_LIC = "Apache-2.0 (MODNet, ZHKKKe/MODNet; ONNX iz izdanja Zeyi-Lin/HivisionIDPhotos)"
REF = 384                 # px po duljoj strani za model (tekst iza osobe: dovoljna je glava)
REF_TIJELO = 512          # nova pozadina, grafika iza osobe: cijelo tijelo (na 384 MODNet gubi donji dio
                          # tijela u širem kadru; 512 = veličina na kojoj je treniran, ~2,5× sporije)
GLADI = 0.25              # razlika maske ispod koje se susjedne sličice miješaju (treperenje)
VERZIJA_KOMADA = 3        # povećaj kad se promijeni izgled → stari komadi u predmemoriji ne vrijede
FONT = "Anton-Regular.ttf"
ULAZ, IZLAZ = 0.35, 0.25  # s: tekst ulazi odozdo / utiša se na kraju
POLOZAJI = ("auto", "gore", "sredina", "dolje")
MAX_TEKST = 40


class Greska(Exception):
    pass


# ---------------------------------------------------------------- model
def models_dir():
    import govornici
    return govornici.models_dir()


def model_path(d=None):
    return Path(d or models_dir()) / MODEL


def stanje():
    p = model_path()
    if p.exists() and p.stat().st_size > 1_000_000:
        return True, f"model osobe: {p}"
    return False, "model osobe nije skinut (skine se pri prvom efektu, ili: python osoba.py preuzmi)"


def ensure_model(d=None, ispis=True):
    """Putanja modela; skine ga (26 MB) ako ga nema. Greska ako ne može."""
    import govornici as G
    d = Path(d or models_dir())
    dest = d / MODEL
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    d.mkdir(parents=True, exist_ok=True)
    if ispis:
        print(f"Prvo pokretanje: skidam model za izdvajanje osobe (26 MB) u {d}")
    raw = d / (MODEL + ".preuzeto")
    try:
        G._download(MODEL_URL, raw)
    except Exception as e:
        raise Greska(f"ne mogu skinuti model osobe ({MODEL_URL}): {e}. Provjeri internet (treba samo prvi put).")
    if G.sha256(raw) != MODEL_SHA:
        print(f"  Upozorenje: {MODEL} ima drugu kontrolnu sumu nego što je Shofe provjerio. Nastavljam.")
    raw.replace(dest)
    (d / "osoba-LICENSE.txt").write_text(f"{MODEL}: MODNet portrait matting, {MODEL_LIC}\nIzvor: {MODEL_URL}\n",
                                         encoding="utf-8")
    return dest


def velicina_modela(W, H, ref=REF):
    """Veličina ulaza modela (višekratnik 32) za video W×H."""
    s = ref / float(max(W, H))
    return max(32, int(round(W * s / 32)) * 32), max(32, int(round(H * s / 32)) * 32)


class Maskirac:
    """MODNet u cv2.dnn: sličica (RGB uint8, bilo koja veličina) → maska float32 0–1 iste veličine."""

    def __init__(self, ref=REF, model=None):
        import cv2
        self.cv2 = cv2
        self.ref = ref
        try:
            self.net = cv2.dnn.readNetFromONNX(str(model or ensure_model()))
        except cv2.error as ex:
            raise Greska(f"model osobe se ne može učitati: {ex}")

    def __call__(self, rgb):
        import numpy as np
        cv2 = self.cv2
        h, w = rgb.shape[:2]
        mw, mh = velicina_modela(w, h, self.ref)
        x = rgb if (w, h) == (mw, mh) else cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA)
        x = (x.astype(np.float32) - 127.5) / 127.5
        self.net.setInput(x.transpose(2, 0, 1)[None])
        m = self.net.forward()[0, 0]
        if (w, h) != (mw, mh):
            m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
        return np.clip(m, 0.0, 1.0).astype(np.float32)


def zagladi(prev, m):
    """Susjedne maske: gdje se malo razlikuju, pola-pola (manje treperenja); gdje se osoba pomaknula, nova."""
    import numpy as np
    if prev is None:
        return m
    w = np.clip(1.0 - np.abs(m - prev) / GLADI, 0.0, 1.0) * 0.5
    return m * (1.0 - w) + prev * w


# ---------------------------------------------------------------- gdje je osoba
def glava(m, prag=0.5):
    """Maska → {vrh, x, sirina} glave (0–1) ili None: najviši red s osobom i sredina osobe u tom pojasu."""
    import numpy as np
    h, w = m.shape
    rows = (m > prag).sum(axis=1)
    min_w = max(2, int(0.02 * w))
    ys = np.nonzero(rows >= min_w)[0]
    if not len(ys) or (m > prag).mean() < 0.01:
        return None
    vrh = int(ys[0])
    pojas = m[vrh:min(h, vrh + max(2, h // 12))] > prag
    xs = np.nonzero(pojas.any(axis=0))[0]
    return {"vrh": vrh / h, "x": float(xs.mean() / w) if len(xs) else 0.5,
            "sirina": float((xs[-1] - xs[0] + 1) / w) if len(xs) else 0.0}


# ---------------------------------------------------------------- tekst
def _boja(b):
    b = str(b or "#FFFFFF").lstrip("#")
    try:
        return tuple(int(b[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def retci(tekst):
    """'SUNČANO|PUT' ili '\\n' → retci; dulji tekst s razmakom → dva retka podjednake duljine."""
    t = str(tekst or "").strip()
    if "|" in t or "\n" in t:
        return [r.strip() for r in t.replace("\n", "|").split("|") if r.strip()]
    w = t.split()
    if len(t) <= 12 or len(w) < 2:
        return [t]
    best = min(range(1, len(w)), key=lambda k: abs(len(" ".join(w[:k])) - len(" ".join(w[k:]))))
    return [" ".join(w[:best]), " ".join(w[best:])]


def sloj_teksta(tekst, W, H, boja="#FFFFFF", sjena=True, mjera=1.0):
    """Tekst (velika slova, Anton) → (RGBA numpy uint8 h×w, visina retka); širina ≤ 92 % kadra (× mjera)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    lines = [r.upper() for r in retci(tekst)] or [" "]
    uspravno = H > W
    max_h = (0.20 if uspravno else 0.34) * H / max(1, len(lines)) * (1.25 if len(lines) > 1 else 1.0)
    f100 = ImageFont.truetype(str(FONTS_DIR / FONT), 100)
    sirina100 = max(f100.getbbox(r)[2] - f100.getbbox(r)[0] for r in lines)
    visina100 = f100.getbbox("ČĆŠŽĐ" + "".join(lines))[3] - f100.getbbox("ČĆŠŽĐ" + "".join(lines))[1]
    vel = int(max(12, mjera * min(0.92 * W / max(1, sirina100) * 100, max_h / max(1, visina100) * 100)))
    font = ImageFont.truetype(str(FONTS_DIR / FONT), vel)
    razmak = int(vel * 0.02)
    bbs = [font.getbbox(r) for r in lines]
    top = min(b[1] for b in bbs)
    lh = max(b[3] for b in bbs) - top
    korak = int(lh * 1.04) + razmak
    tw = max(b[2] - b[0] for b in bbs)
    pad = int(vel * 0.12)
    img_w, img_h = tw + 2 * pad, korak * (len(lines) - 1) + lh + 2 * pad
    col = _boja(boja)
    alfa = Image.new("L", (img_w, img_h), 0)
    d = ImageDraw.Draw(alfa)
    for i, (r, b) in enumerate(zip(lines, bbs)):
        x = pad + (tw - (b[2] - b[0])) // 2 - b[0]
        d.text((x, pad + i * korak - top), r, font=font, fill=255)
    a = np.asarray(alfa, np.float32) / 255.0
    rgb = np.empty((img_h, img_w, 3), np.float32)
    rgb[:] = col
    if sjena:   # mekana sjena: tekst čitljiv i na svijetloj pozadini
        s = np.asarray(alfa.filter(ImageFilter.GaussianBlur(max(2, vel // 22))), np.float32) / 255.0
        s = np.roll(s, (max(1, vel // 40), max(1, vel // 60)), axis=(0, 1)) * 0.45
        out_a = a + s * (1 - a)
        rgb = rgb * (a / np.maximum(out_a, 1e-6))[..., None]
        a = out_a
    out = np.dstack([np.clip(rgb, 0, 255), a * 255.0]).astype(np.uint8)
    return out, lh


def pokrivenost(sloj, x, y, m, W, H):
    """Koliki dio slova (po alfi) prekriva osoba kad sloj stoji na (x, y); m = maska bilo koje veličine."""
    import cv2
    import numpy as np
    sh, sw = sloj.shape[:2]
    mh, mw = m.shape
    sx, sy = mw / float(W), mh / float(H)
    a = cv2.resize(sloj[..., 3], (max(1, int(sw * sx)), max(1, int(sh * sy))), interpolation=cv2.INTER_AREA)
    a = a.astype(np.float32) / 255.0
    x0, y0 = int(x * sx), int(y * sy)
    mm = np.zeros_like(a)
    ys, xs = max(0, y0), max(0, x0)
    ye, xe = min(mh, y0 + a.shape[0]), min(mw, x0 + a.shape[1])
    if ye > ys and xe > xs:
        mm[ys - y0:ye - y0, xs - x0:xe - x0] = m[ys:ye, xs:xe]
    return float((a * mm).sum() / max(1e-6, a.sum()))


MAX_POKRIVENO = 0.45      # auto: najviše toliko slova smije biti iza osobe, inače tekst ide drugdje


def mjesto(sloj, W, H, polozaj="auto", m=None):
    """Gornji lijevi kut sloja (x, y) u kadru. auto: dno slova malo ispod vrha glave (glava zalazi u slova);
    ako bi osoba prekrila više od MAX_POKRIVENO slova (krupni kadar), najbliže mjesto gdje se tekst čita."""
    sh, sw = sloj.shape[:2]
    uspravno = H > W
    gore = int((0.115 if uspravno else 0.06) * H)      # sigurna zona reela (Instagram/TikTok gore)
    dolje = int((0.70 if uspravno else 0.80) * H)      # iznad titlova
    x = (W - sw) // 2
    p = str(polozaj or "auto").lower()
    gl = glava(m) if m is not None else None
    if p == "gore":
        y = gore
    elif p == "sredina":
        y = int(0.42 * H - sh / 2)
    elif p == "dolje":
        y = dolje - sh
    elif gl:
        y = int(gl["vrh"] * H + 0.40 * sh - sh)        # 40 % visine slova iza glave
    else:
        y = int(0.30 * H - sh / 2)
    y = max(gore, min(y, dolje - sh))
    if p == "auto" and m is not None:
        if pokrivenost(sloj, x, y, m, W, H) > MAX_POKRIVENO:
            ys = list(range(gore, max(gore, dolje - sh) + 1, max(4, H // 100)))
            cov = {yy: pokrivenost(sloj, x, yy, m, W, H) for yy in ys}
            dobri = [yy for yy in ys if cov[yy] <= MAX_POKRIVENO]
            y = min(dobri, key=lambda yy: abs(yy - y)) if dobri else min(ys, key=lambda yy: cov[yy])
    return x, y


MJERE = (1.0, 0.8, 0.65, 0.5)    # auto: ako se tekst nigdje ne čita (krupni kadar), manja slova


def postavi(tekst, W, H, boja="#FFFFFF", polozaj="auto", m=None):
    """Sloj teksta i mjesto → (sloj, x, y). auto + maska: najveća slova koja se još čitaju iza osobe."""
    best = None
    for k in (MJERE if (str(polozaj or "auto").lower() == "auto" and m is not None) else MJERE[:1]):
        sloj, _ = sloj_teksta(tekst, W, H, boja, mjera=k)
        x, y = mjesto(sloj, W, H, polozaj, m)
        if m is None:
            return sloj, x, y
        c = pokrivenost(sloj, x, y, m, W, H)
        if c <= MAX_POKRIVENO:
            return sloj, x, y
        if best is None or c < best[0]:
            best = (c, sloj, x, y)
    return best[1], best[2], best[3]


def animacija(j, n, fps):
    """Sličica j od n → (prozirnost 0–1, pomak dolje u udjelu visine sloja)."""
    t, d = j / float(fps), n / float(fps)
    ul = min(ULAZ, d / 3)
    iz = min(IZLAZ, d / 4)
    a, dy = 1.0, 0.0
    if t < ul:
        k = t / ul
        e = 1 - (1 - k) ** 3
        a, dy = min(1.0, k * 1.6), 0.35 * (1 - e)
    if t > d - iz:
        a = min(a, max(0.0, (d - t) / iz))
    return a, dy


def slozi(rgb, m, sloj, x, y, a=1.0, dy=0.0):
    """Sličica RGB uint8 + maska osobe + sloj teksta (RGBA) na (x, y) → nova sličica: tekst iza osobe."""
    import numpy as np
    H, W = rgb.shape[:2]
    sh, sw = sloj.shape[:2]
    y = int(round(y + dy * sh))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + sw), min(H, y + sh)
    if a <= 0.003 or x1 <= x0 or y1 <= y0:
        return rgb
    s = sloj[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    la = s[..., 3:4] / 255.0 * a * (1.0 - m[y0:y1, x0:x1, None])
    out = rgb.copy()
    reg = out[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(reg * (1 - la) + s[..., :3] * la + 0.5, 0, 255).astype(np.uint8)
    return out


# ---------------------------------------------------------------- komad za render
def _citaj(video, s, n, w, h, fps):
    """n sličica gotovog videa od vremena s, veličine w×h, kao RGB (generator)."""
    from grafika import fps_arg
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{max(0.0, s - 0.25 / float(fps)):.4f}", "-i", str(video),
           "-an", "-vf", f"scale={w}:{h}:flags=area,setsar=1", "-frames:v", str(n), "-r", fps_arg(fps),
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    import numpy as np
    k, vel = 0, w * h * 3
    try:
        while k < n:
            b = p.stdout.read(vel)
            if len(b) < vel:
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
            k += 1
    finally:
        p.stdout.close()
        err = p.stderr.read().decode("utf-8", "replace")
        p.wait()
    if k < n:
        raise Greska(f"iz videa sam dobio {k} od {n} sličica za tekst iza osobe ({err[-300:]})")


def parametri(p):
    t = str((p or {}).get("tekst") or "").strip()
    return {"tekst": t, "boja": (p or {}).get("boja") or "#FFFFFF",
            "polozaj": str((p or {}).get("polozaj") or "auto").lower()}


def maske(proj, g, video, W, H, fps, ispis=False, cisto=None, ref=REF):
    """Maske osobe za taj dio gotovog videa (veličina modela) + ključ sadržaja; predmemorija po sličicama.
    cisto = ista slika bez titlova (render.py; vrijeme titlova s0) — maska iz nje, titlovi ne zbune model."""
    mw, mh = velicina_modela(W, H, ref)
    hs = hashlib.sha256()
    male = []
    src, s = (cisto, g.get("s0", g["s"])) if cisto else (video, g["s"])
    for fr in _citaj(src, s, g["n"], mw, mh, fps):
        hs.update(fr.tobytes())
        male.append(fr)
    key = hs.hexdigest()[:20] + f"_{ref}"
    d = Path(proj) / "_tmp" / "grafika"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"maske_{key}.npz"
    if f.exists():
        try:
            return np.load(f)["m"].astype(np.float32) / 255.0, key
        except (OSError, ValueError, KeyError):
            pass
    if ispis:
        print(f"  {g['id']}: maska osobe za {len(male)} sličica ...")
    mk = Maskirac(ref=ref)
    out, prev = [], None
    for fr in male:
        m = zagladi(prev, mk(fr))
        out.append(m)
        prev = m
    arr = np.stack(out)
    np.savez_compressed(f, m=np.round(arr * 255).astype(np.uint8))
    for old in d.glob("maske_*.npz"):       # samo nekoliko zadnjih (svaka promjena videa = nove maske)
        if old != f and len(list(d.glob("maske_*.npz"))) > 12:
            old.unlink(missing_ok=True)
    return arr, key


def komad(proj, g, video, W, H, fps, ispis=False, cisto=None):
    """Taj dio gotovog videa s tekstom iza osobe → _tmp/grafika/grafika_iza_<ključ>.mp4 (n sličica). (put, nov)"""
    import cv2
    from grafika import fps_arg
    p = parametri(g["p"])
    if not p["tekst"]:
        raise Greska(f"{g['id']}: tekst iza osobe nema teksta (--tekst \"…\")")
    ms, key = maske(proj, g, video, W, H, fps, ispis=ispis, cisto=cisto)
    sloj, x, y = postavi(p["tekst"], W, H, p["boja"], p["polozaj"], ms[len(ms) // 2] if len(ms) else None)
    s0 = g.get("s0", g["s"])
    k2 = hashlib.sha256(json.dumps([key, p, W, H, g["n"], fps_arg(fps), _kljuc_titlova(proj, s0, g["n"]),
                                    VERZIJA_KOMADA]).encode()).hexdigest()[:24]
    d = Path(proj) / "_tmp" / "grafika"
    out = d / f"grafika_iza_{k2}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out, False

    def slicice():
        ta = titlovi_alfa(proj, s0, g["n"], W, H, fps)      # titlovi i naslov ostaju ispred teksta
        for j, fr in enumerate(_citaj(video, g["s"], g["n"], W, H, fps)):
            m = cv2.resize(ms[min(j, len(ms) - 1)], (W, H), interpolation=cv2.INTER_LINEAR)
            a, dy = animacija(j, g["n"], fps)
            yield vrati_titlove(slozi(fr, m, sloj, x, y, a, dy), fr, next(ta, None))

    _kodiraj(slicice(), out, W, H, fps, f"tekst iza osobe {g['id']}")
    return out, True


def na_sliku(png, g, j, fps, proj=None, cisto=None):
    """Jedna sličica (--kadar, pokazi): maska iz same slike → isti PNG. Tekst iza osobe (iza) ili nova
    pozadina (pozadina) u trenutku j; titlovi ostaju ispred (proj = mapa projekta s captions.ass)."""
    import numpy as np
    from PIL import Image
    with Image.open(png) as im:
        rgb = np.asarray(im.convert("RGB"))
    H, W = rgb.shape[:2]
    cist = _slika_ili(cisto, rgb)          # bez titlova (render.py --kadar): maska i zamućenje iz nje
    if g.get("tip") == "pozadina":
        p = pozadina_parametri(g["p"], proj)
        m = Maskirac(ref=REF_TIJELO)(cist)
        if bez_osobe(m[None]):
            return False
        out = slozi_pozadinu(rgb, m, Pozadina(p, W, H, fps, j_od=j)(cist, m), prozirnost_pozadine(j, g, fps))
    else:
        p = parametri(g["p"])
        if not p["tekst"]:
            return False
        m = Maskirac()(cist)
        sloj, x, y = postavi(p["tekst"], W, H, p["boja"], p["polozaj"], m)
        a, dy = animacija(j, g["n"], fps)
        out = slozi(rgb, m, sloj, x, y, a, dy)
    if proj is not None:
        ta = next(titlovi_alfa(proj, g.get("s0", g["s"]) + j / float(fps), 1, W, H, fps), None)
        out = vrati_titlove(out, rgb, ta)
    Image.fromarray(out).save(png)
    return True


def _slika_ili(f, rgb):
    """Slika f (iste veličine kao rgb) ili rgb ako je nema."""
    from PIL import Image
    if not f or not Path(f).exists():
        return rgb
    with Image.open(f) as im:
        c = np.asarray(im.convert("RGB"))
    return c if c.shape == rgb.shape else rgb


# ---------------------------------------------------------------- titlovi ostaju ispred
def titlovi_alfa(proj, s, n, W, H, fps):
    """Alfa titlova, naslova i natpisa (captions.ass projekta) za n sličica od vremena s (vrijeme titlova)
    → generator float32 H×W (0–1); bez captions.ass ili ako ffmpeg ne može: ništa (prazan generator)."""
    import numpy as np
    from grafika import fps_arg
    proj = Path(proj)
    if not (proj / "captions.ass").exists():
        return
    fd = "fonts" if (proj / "fonts").is_dir() else None
    sub = "subtitles=filename=captions.ass:alpha=1" + (f":fontsdir={fd}" if fd else "")
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-f", "lavfi", "-i",
           f"color=c=black@0.0:s={W}x{H}:r={fps_arg(fps)},format=rgba",
           "-vf", f"setpts=PTS+{max(0.0, s):.4f}/TB,{sub}", "-frames:v", str(n),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
    p = subprocess.Popen(cmd, cwd=proj, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    vel = W * H * 4
    try:
        for _ in range(n):
            b = p.stdout.read(vel)
            if len(b) < vel:
                break
            yield np.frombuffer(b, np.uint8).reshape(H, W, 4)[..., 3].astype(np.float32) / 255.0
    finally:
        p.stdout.close()
        p.kill()
        p.wait()


def vrati_titlove(out, fr, ta):
    """Gdje su titlovi (alfa ta), vrati piksele gotove sličice fr: titlovi stoje ispred efekta."""
    import numpy as np
    if ta is None or ta.max() <= 0.003:
        return out
    t = ta[..., None]
    return np.clip(out.astype(np.float32) * (1 - t) + fr.astype(np.float32) * t + 0.5, 0, 255).astype(np.uint8)


def _kljuc_titlova(proj, s, n):
    f = Path(proj) / "captions.ass"
    if not f.exists():
        return None
    return [hashlib.sha256(f.read_bytes()).hexdigest()[:16], round(float(s), 4), n]


# ---------------------------------------------------------------- nova pozadina (M5.7b)
POZADINE = ("zamuti", "boja", "slika", "video")
SLIKE = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEI = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
ZAMUTI = 0.5             # zadana jačina zamućenja (0–1) za vrstu zamuti
ZAMUTI_SIGMA = 0.045     # sigma zamućenja pri jačini 1, u udjelu kraće strane kadra
STEGNI = 0.08            # maska osobe se malo stegne (0–1): rub kose ne nosi staru pozadinu
OMOT = 0.35              # svjetlo pozadine preko ruba osobe (light wrap): manje izrezan izgled
POZ_PRIJELAZ = 0.2       # s: nova pozadina se pretopi na početku i kraju (osim na samom početku/kraju videa)


def pozadina_parametri(p, proj=None):
    """Parametri iz edit.json → {vrsta, boja, datoteka (Path ili None), zamuti (0–1)}."""
    p = p or {}
    v = str(p.get("vrsta") or "").lower()
    if v not in POZADINE:
        v = "slika" if p.get("slika") else "video" if p.get("video") else "boja" if p.get("boja") else "zamuti"
    dat = p.get("datoteka") or p.get(v if v in ("slika", "video") else "_")
    f = None
    if dat and v in ("slika", "video"):
        f = Path(str(dat))
        if not f.is_absolute() and proj is not None:
            f = Path(proj) / f
    z = p.get("zamuti")
    try:
        z = float(z) if z is not None and z is not True else (ZAMUTI if v == "zamuti" or z is True else 0.0)
    except (TypeError, ValueError):
        z = ZAMUTI
    return {"vrsta": v, "boja": p.get("boja") or "#1E3A5F", "datoteka": f, "zamuti": max(0.0, min(1.0, z))}


def _pokrij(rgb, W, H):
    """Slika bilo koje veličine → W×H: poveća se da pokrije cijeli kadar i izreže po sredini."""
    import cv2
    h, w = rgb.shape[:2]
    s = max(W / float(w), H / float(h))
    nw, nh = max(W, int(round(w * s))), max(H, int(round(h * s)))
    r = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    x0, y0 = (nw - W) // 2, (nh - H) // 2
    return np.ascontiguousarray(r[y0:y0 + H, x0:x0 + W])


def _sigma(W, H, z):
    return max(0.0, z) * ZAMUTI_SIGMA * min(W, H)


def _gauss(x, sigma):
    import cv2
    return cv2.GaussianBlur(x, (0, 0), sigmaX=max(0.3, sigma), borderType=cv2.BORDER_REFLECT)


def zamuti(rgb, sigma):
    """Obično zamućenje (slika ili video pozadine), računato na smanjenoj slici (brže, isti izgled)."""
    import cv2
    if sigma < 0.5:
        return rgb
    H, W = rgb.shape[:2]
    k = max(1, int(sigma // 3))
    small = cv2.resize(rgb, (max(8, W // k), max(8, H // k)), interpolation=cv2.INTER_AREA).astype(np.float32)
    b = _gauss(small, sigma / k)
    return np.clip(cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR) + 0.5, 0, 255).astype(np.uint8)


def zamuti_bez_osobe(rgb, m, sigma):
    """Zamućena pozadina iz same snimke, bez boja osobe (normalizirano zamućenje s maskom, kao Google Meet):
    piksel pozadine = prosjek okolne pozadine, osoba ne „curi" u zamućenje (nema svijetle aure oko glave).
    Gdje je pozadine premalo (iza osobe), obično zamućenje cijele slike."""
    import cv2
    H, W = rgb.shape[:2]
    k = max(1, int(sigma // 3))
    sw, sh = max(8, W // k), max(8, H // k)
    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
    w = 1.0 - cv2.resize(m, (sw, sh), interpolation=cv2.INTER_AREA)
    w = np.clip((w - 0.15) / 0.85, 0.0, 1.0).astype(np.float32)      # rub osobe ne ulazi u prosjek
    s = sigma / k
    num = _gauss(small * w[..., None], s)
    den = _gauss(w, s)[..., None]
    plain = _gauss(small, s)
    q = np.clip(den / 0.12, 0.0, 1.0)
    b = num / np.maximum(den, 1e-4) * q + plain * (1 - q)
    return np.clip(cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR) + 0.5, 0, 255).astype(np.uint8)


def _boja_slika(boja, W, H):
    """Jednobojna pozadina s blagim prijelazom (gore malo svjetlije, dolje tamnije): ne izgleda kao rupa."""
    c = np.array(_boja(boja), np.float32)
    y = np.linspace(1.10, 0.82, H, dtype=np.float32)[:, None, None]
    return np.clip(np.broadcast_to(c * y, (H, 1, 3)).repeat(W, axis=1) + 0.5, 0, 255).astype(np.uint8)


def _citaj_video_pozadine(f, n, W, H, fps):
    """n sličica videa pozadine (vrti se u krug ako je kraći), pokriva cijeli kadar W×H → generator RGB."""
    from grafika import fps_arg
    cmd = [ffmpeg(), "-v", "error", "-nostdin", "-stream_loop", "-1", "-i", str(f), "-an",
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,crop={W}:{H},setsar=1",
           "-r", fps_arg(fps), "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    vel, k = W * H * 3, 0
    try:
        while k < n:
            b = p.stdout.read(vel)
            if len(b) < vel:
                break
            yield np.frombuffer(b, np.uint8).reshape(H, W, 3)
            k += 1
    finally:
        p.stdout.close()
        err = p.stderr.read().decode("utf-8", "replace")
        p.wait()
    if k < n:
        raise Greska(f"video pozadine {f.name}: dobio sam {k} od {n} sličica ({err[-300:]})")


MIN_OSOBA = 0.02         # pozadina: barem toliki dio kadra mora biti osoba (u prosjeku), inače se ne mijenja


def bez_osobe(ms):
    """Maske (n×h×w, 0–1) → True ako osoba gotovo nije u kadru (MODNet je nije našao)."""
    return len(ms) == 0 or float((np.asarray(ms) > 0.5).mean()) < MIN_OSOBA


def provjeri_datoteku(p):
    """Greska ako slika/video pozadine ne postoji ili se ne može otvoriti."""
    f = p.get("datoteka")
    if p["vrsta"] not in ("slika", "video"):
        return
    if not f or not Path(f).exists():
        raise Greska(f"{p['vrsta']} pozadine ne postoji: {f}")
    ok = SLIKE if p["vrsta"] == "slika" else VIDEI
    if Path(f).suffix.lower() not in ok:
        raise Greska(f"{p['vrsta']} pozadine treba biti {', '.join(ok)} (ne {Path(f).suffix or 'bez nastavka'})")


class Pozadina:
    """Nova pozadina sličicu po sličicu: poz(fr, m) → RGB W×H (zamuti iz same sličice bez osobe; boja/slika
    ista svaki put; video sljedeća sličica, u krug). j_od = preskoči toliko sličica videa (--kadar)."""

    def __init__(self, p, W, H, fps, n=1, j_od=0):
        self.p, self.W, self.H = p, W, H
        self.sig = _sigma(W, H, p["zamuti"])
        self.fiksna, self.vid = None, None
        v = p["vrsta"]
        if v == "boja":
            self.fiksna = _boja_slika(p["boja"], W, H)
        elif v in ("slika", "video"):
            provjeri_datoteku(p)
        if v == "slika":
            from PIL import Image
            with Image.open(p["datoteka"]) as im:
                self.fiksna = zamuti(_pokrij(np.asarray(im.convert("RGB")), W, H), self.sig)
        elif v == "video":
            self.vid = _citaj_video_pozadine(p["datoteka"], j_od + n, W, H, fps)
            for _ in range(j_od):
                next(self.vid)

    def __call__(self, fr, m):
        if self.fiksna is not None:
            return self.fiksna
        if self.vid is not None:
            return zamuti(next(self.vid), self.sig)
        return zamuti_bez_osobe(fr, m, max(self.sig, 2.0))


def slozi_pozadinu(fr, m, bg, a=1.0):
    """Osoba iz sličice fr (maska m, puna veličina) ispred pozadine bg; rub osobe dobije malo svjetla nove pozadine
    (light wrap), pa ne izgleda izrezano. a = koliko je nove pozadine (pretapanje)."""
    import cv2
    if a <= 0.003:
        return fr
    H, W = fr.shape[:2]
    f32, b32 = fr.astype(np.float32), bg.astype(np.float32)
    m = np.clip((m - STEGNI) / (1.0 - STEGNI), 0.0, 1.0)            # rub malo stegnut: manje stare pozadine
    sw, sh = max(8, W // 4), max(8, H // 4)
    ms = cv2.resize(m, (sw, sh), interpolation=cv2.INTER_AREA)
    sg = max(1.0, 0.006 * min(W, H) / 4)
    # čišćenje ruba: u poluprozirnim pikselima (kosa) boja = osoba + stara pozadina; stara pozadina se procijeni
    # iz okolne pozadine i oduzme, pa kosa ne nosi sivi/zeleni rub stare pozadine na novu
    fs = cv2.resize(fr, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
    wo = np.clip(1.0 - ms * 1.6, 0.0, 1.0)
    sgo = sg * 2.5
    staro = _gauss(fs * wo[..., None], sgo) / np.maximum(_gauss(wo, sgo), 1e-3)[..., None]
    staro = cv2.resize(staro, (W, H), interpolation=cv2.INTER_LINEAR)
    mm = m[..., None]
    rubni = (mm > 0.02) & (mm < 0.98)
    cist = np.where(rubni, np.clip((f32 - (1 - mm) * staro) / np.maximum(mm, 0.15), 0, 255), f32)
    out = cist * mm + b32 * (1 - mm)
    # light wrap: na unutarnjem rubu osobe malo zamućene pozadine (računato na četvrtini veličine)
    rub = np.clip(ms - _gauss(ms, sg), 0.0, 1.0) * 2.0
    bs = cv2.resize(bg, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
    bw = _gauss(bs * (1 - ms[..., None]), sg) / np.maximum(_gauss(1 - ms, sg), 1e-3)[..., None]
    rub = cv2.resize(np.clip(rub, 0, 1) * OMOT, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
    bw = cv2.resize(bw, (W, H), interpolation=cv2.INTER_LINEAR)
    out = out * (1 - rub) + bw * rub
    if a < 0.997:
        out = f32 * (1 - a) + out * a
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def prozirnost_pozadine(j, g, fps):
    """Sličica j efekta pozadina → udio nove pozadine: pretapanje 0,2 s na početku/kraju (ne na rubu videa)."""
    n = g["n"]
    d = min(POZ_PRIJELAZ, n / float(fps) / 4)
    if d <= 0:
        return 1.0
    a = 1.0
    if g.get("k0", 1) > 0:
        a = min(a, (j + 1) / (d * fps))
    if not g.get("do_kraja"):
        a = min(a, (n - j) / (d * fps))
    return float(max(0.0, min(1.0, a)))


def _potpis(f):
    try:
        st = Path(f).stat()
        return [Path(f).name, st.st_size, int(st.st_mtime)]
    except OSError:
        return None


def _kodiraj(slicice, out, W, H, fps, sto):
    """Generator RGB sličica → out (libx264, gotovo bez gubitka); Greska ako ffmpeg padne."""
    from grafika import fps_arg
    tmp = out.with_name("_" + out.name)
    cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", fps_arg(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
           "-pix_fmt", "yuv420p", str(tmp)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fr in slicice:
            enc.stdin.write(np.ascontiguousarray(fr).tobytes())
    except Greska:
        enc.kill()
        raise
    finally:
        try:
            enc.stdin.close()
        except OSError:
            pass
    err = enc.stderr.read().decode("utf-8", "replace")
    if enc.wait() != 0 or not tmp.exists():
        raise Greska(f"{sto} nije kodiran: {err[-500:]}")
    tmp.replace(out)


def komad_pozadine(proj, g, video, W, H, fps, ispis=False, cisto=None):
    """Taj dio gotovog videa s novom pozadinom iza osobe → _tmp/grafika/grafika_pozadina_<ključ>.mp4. (put, nov)"""
    import cv2
    from grafika import fps_arg
    p = pozadina_parametri(g["p"], proj)
    provjeri_datoteku(p)
    ms, key = maske(proj, g, video, W, H, fps, ispis=ispis, cisto=cisto, ref=REF_TIJELO)
    if bez_osobe(ms):
        raise Greska("u tom dijelu Shofe ne vidi osobu (maska je gotovo prazna), pa bi nova pozadina prekrila "
                     "cijeli kadar; probaj dio gdje se osoba jasno vidi")
    s0 = g.get("s0", g["s"])
    k2 = hashlib.sha256(json.dumps([key, {**p, "datoteka": _potpis(p["datoteka"]) if p["datoteka"] else None},
                                    W, H, g["n"], fps_arg(fps), g.get("k0", 1) > 0, bool(g.get("do_kraja")),
                                    _kljuc_titlova(proj, s0, g["n"]), VERZIJA_KOMADA]).encode()).hexdigest()[:24]
    d = Path(proj) / "_tmp" / "grafika"
    out = d / f"grafika_pozadina_{k2}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out, False
    if ispis:
        print(f"  pozadina {g['id']} ({p['vrsta']}): {g['n']} sličica ...")

    def slicice():
        poz = Pozadina(p, W, H, fps, n=g["n"])
        ta = titlovi_alfa(proj, s0, g["n"], W, H, fps)
        # zamućenje iz slike bez titlova (inače bi zamućeni titlovi ostali kao mrlja iza pravih)
        cf = _citaj(cisto, s0, g["n"], W, H, fps) if (cisto and p["vrsta"] == "zamuti") else None
        for j, fr in enumerate(_citaj(video, g["s"], g["n"], W, H, fps)):
            m = cv2.resize(ms[min(j, len(ms) - 1)], (W, H), interpolation=cv2.INTER_LINEAR)
            izvor = next(cf, fr) if cf is not None else fr
            o = slozi_pozadinu(fr, m, poz(izvor, m), prozirnost_pozadine(j, g, fps))
            yield vrati_titlove(o, fr, next(ta, None))

    _kodiraj(slicice(), out, W, H, fps, f"pozadina {g['id']}")
    return out, True


# ---------------------------------------------------------------- HTML grafika iza osobe (--iza)
def komad_grafike_iza(proj, g, video, f_graf, W, H, fps, ispis=False, cisto=None):
    """HyperFrames komad grafike (proziran .mov) iza osobe: grafika preko tog dijela videa, pa osoba i titlovi
    natrag ispred → _tmp/grafika/grafika_izah_<ključ>.mp4. (put, nov)"""
    import cv2
    from grafika import fps_arg, _sha_file
    ms, key = maske(proj, g, video, W, H, fps, ispis=ispis, cisto=cisto, ref=REF_TIJELO)
    s0 = g.get("s0", g["s"])
    k2 = hashlib.sha256(json.dumps([key, _sha_file(f_graf), W, H, g["n"], fps_arg(fps),
                                    _kljuc_titlova(proj, s0, g["n"]), VERZIJA_KOMADA]).encode()).hexdigest()[:24]
    d = Path(proj) / "_tmp" / "grafika"
    out = d / f"grafika_izah_{k2}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out, False

    def graf_frames():
        cmd = [ffmpeg(), "-v", "error", "-nostdin", "-i", str(f_graf), "-vf", f"scale={W}:{H},setsar=1",
               "-frames:v", str(g["n"]), "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        vel = W * H * 4
        try:
            while True:
                b = p.stdout.read(vel)
                if len(b) < vel:
                    break
                yield np.frombuffer(b, np.uint8).reshape(H, W, 4)
        finally:
            p.stdout.close()
            p.wait()

    def slicice():
        gf = graf_frames()
        ta = titlovi_alfa(proj, s0, g["n"], W, H, fps)
        zadnja = None
        for j, fr in enumerate(_citaj(video, g["s"], g["n"], W, H, fps)):
            zadnja = next(gf, zadnja)
            m = cv2.resize(ms[min(j, len(ms) - 1)], (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
            f32 = fr.astype(np.float32)
            if zadnja is not None:
                ga = zadnja[..., 3:4].astype(np.float32) / 255.0 * (1 - m)
                f32 = f32 * (1 - ga) + zadnja[..., :3].astype(np.float32) * ga
            o = np.clip(f32 + 0.5, 0, 255).astype(np.uint8)
            yield vrati_titlove(o, fr, next(ta, None))

    _kodiraj(slicice(), out, W, H, fps, f"grafika iza osobe {g['id']}")
    return out, True


def grafika_iza_na_sliku(png, f_graf, j, proj=None, t_titlova=None, fps=30, cisto=None):
    """--kadar: sličica j HTML grafike iza osobe na PNG (maska iz same slike) → isti PNG."""
    from PIL import Image
    with Image.open(png) as im:
        rgb = np.asarray(im.convert("RGB"))
    H, W = rgb.shape[:2]
    r = subprocess.run([ffmpeg(), "-v", "error", "-nostdin", "-i", str(f_graf), "-vf",
                        f"select='eq(n\\,{j})',scale={W}:{H}", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba",
                        "-"], capture_output=True)
    if r.returncode != 0 or len(r.stdout) < W * H * 4:
        return False
    gr = np.frombuffer(r.stdout[:W * H * 4], np.uint8).reshape(H, W, 4)
    m = Maskirac(ref=REF_TIJELO)(_slika_ili(cisto, rgb))[..., None]
    ga = gr[..., 3:4].astype(np.float32) / 255.0 * (1 - m)
    out = np.clip(rgb * (1 - ga) + gr[..., :3] * ga + 0.5, 0, 255).astype(np.uint8)
    if proj is not None and t_titlova is not None:
        out = vrati_titlove(out, rgb, next(titlovi_alfa(proj, t_titlova, 1, W, H, fps), None))
    Image.fromarray(out).save(png)
    return True


# ---------------------------------------------------------------- naredbe
def _slika_iz(ulaz, t):
    import numpy as np
    from PIL import Image
    ulaz = Path(ulaz)
    if ulaz.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        with Image.open(ulaz) as im:
            return np.asarray(im.convert("RGB"))
    r = subprocess.run([ffmpeg(), "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", str(ulaz), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        die(f"ne mogu uzeti sličicu iz {ulaz} u {fmt_time(t)}")
    import io
    with Image.open(io.BytesIO(r.stdout)) as im:
        return np.asarray(im.convert("RGB"))


def cmd_pokazi(ulaz, t, tekst, polozaj, boja):
    """Maska (pozadina zelena) lijevo, tekst iza osobe desno → <ime>_osoba.png."""
    import numpy as np
    from PIL import Image
    rgb = _slika_iz(ulaz, t)
    H, W = rgb.shape[:2]
    try:
        m = Maskirac()(rgb)
    except Greska as ex:
        die(str(ex))
    zel = (rgb * m[..., None] + np.array([30, 200, 60]) * (1 - m[..., None])).astype(np.uint8)
    sloj, x, y = postavi(tekst, W, H, boja, polozaj, m)
    iza = slozi(rgb, m, sloj, x, y)
    out = Path(ulaz).with_name(Path(ulaz).stem + "_osoba.png")
    Image.fromarray(np.hstack([zel, iza])).save(out)
    print(f"{out}  (lijevo: maska osobe, zeleno = pozadina; desno: „{tekst}“ iza osobe)")


def main():
    ap = argparse.ArgumentParser(description="Izdvajanje osobe: maska (MODNet) i tekst iza osobe")
    ap.add_argument("naredba", help="provjera | preuzmi | pokazi")
    ap.add_argument("ulaz", nargs="?", help="pokazi: slika ili video")
    ap.add_argument("--t", default="0", help="pokazi iz videa: vrijeme (0:03)")
    ap.add_argument("--tekst", default="SUNČANO")
    ap.add_argument("--polozaj", default="auto", choices=POLOZAJI)
    ap.add_argument("--boja", default="#FFFFFF")
    a = ap.parse_args()
    n = a.naredba.lower()
    if n == "provjera":
        ok, msg = stanje()
        print(("[ok] " if ok else "[--] ") + msg)
        sys.exit(0 if ok else 1)
    if n == "preuzmi":
        try:
            print(f"Model osobe: {ensure_model()}")
        except Greska as ex:
            die(str(ex))
        return
    if n in ("pokazi", "pokaži"):
        if not a.ulaz:
            die("koja slika ili video? python osoba.py pokazi slika.png")
        import uredi
        try:
            t = uredi.parse_time(a.t)
        except ValueError as ex:
            die(str(ex))
        cmd_pokazi(a.ulaz, t, a.tekst, a.polozaj, a.boja)
        return
    die("naredbe: provjera, preuzmi, pokazi")


if __name__ == "__main__":
    main()
