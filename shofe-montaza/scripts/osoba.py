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
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from common import FONTS_DIR, die, ffmpeg, fmt_time

MODEL = "osoba_modnet.onnx"
MODEL_URL = ("https://github.com/Zeyi-Lin/HivisionIDPhotos/releases/download/pretrained-model/"
             "modnet_photographic_portrait_matting.onnx")
MODEL_SHA = "07c308cf0fc7e6e8b2065a12ed7fc07e1de8febb7dc7839d7b7f15dd66584df9"
MODEL_LIC = "Apache-2.0 (MODNet, ZHKKKe/MODNet; ONNX iz izdanja Zeyi-Lin/HivisionIDPhotos)"
REF = 384                 # px po duljoj strani za model (512 = sporije, malo oštriji rub)
GLADI = 0.25              # razlika maske ispod koje se susjedne sličice miješaju (treperenje)
VERZIJA_KOMADA = 1        # povećaj kad se promijeni izgled → stari komadi u predmemoriji ne vrijede
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


def maske(proj, g, video, W, H, fps, ispis=False):
    """Maske osobe za taj dio gotovog videa (veličina modela) + ključ sadržaja; predmemorija po sličicama."""
    import numpy as np
    mw, mh = velicina_modela(W, H)
    hs = hashlib.sha256()
    male = []
    for fr in _citaj(video, g["s"], g["n"], mw, mh, fps):
        hs.update(fr.tobytes())
        male.append(fr)
    key = hs.hexdigest()[:20] + f"_{REF}"
    d = Path(proj) / "_tmp" / "grafika"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"maske_{key}.npz"
    if f.exists():
        try:
            return np.load(f)["m"].astype(np.float32) / 255.0, key
        except (OSError, ValueError, KeyError):
            pass
    if ispis:
        print(f"  tekst iza osobe {g['id']}: maska osobe za {len(male)} sličica ...")
    mk = Maskirac()
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


def komad(proj, g, video, W, H, fps, ispis=False):
    """Taj dio gotovog videa s tekstom iza osobe → _tmp/grafika/grafika_iza_<ključ>.mp4 (n sličica). (put, nov)"""
    import cv2
    import numpy as np
    from grafika import fps_arg
    p = parametri(g["p"])
    if not p["tekst"]:
        raise Greska(f"{g['id']}: tekst iza osobe nema teksta (--tekst \"…\")")
    ms, key = maske(proj, g, video, W, H, fps, ispis=ispis)
    sloj, x, y = postavi(p["tekst"], W, H, p["boja"], p["polozaj"], ms[len(ms) // 2] if len(ms) else None)
    k2 = hashlib.sha256(json.dumps([key, p, W, H, g["n"], fps_arg(fps), VERZIJA_KOMADA]).encode()).hexdigest()[:24]
    d = Path(proj) / "_tmp" / "grafika"
    out = d / f"grafika_iza_{k2}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out, False
    tmp = d / ("_" + out.name)
    cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", fps_arg(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "10",
           "-pix_fmt", "yuv420p", str(tmp)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for j, fr in enumerate(_citaj(video, g["s"], g["n"], W, H, fps)):
            m = cv2.resize(ms[min(j, len(ms) - 1)], (W, H), interpolation=cv2.INTER_LINEAR)
            a, dy = animacija(j, g["n"], fps)
            enc.stdin.write(np.ascontiguousarray(slozi(fr, m, sloj, x, y, a, dy)).tobytes())
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
        raise Greska(f"tekst iza osobe {g['id']} nije kodiran: {err[-500:]}")
    tmp.replace(out)
    return out, True


def na_sliku(png, g, j, fps):
    """Jedna sličica (--kadar, pokazi): maska iz same slike, tekst iza osobe u trenutku j → isti PNG."""
    import numpy as np
    from PIL import Image
    p = parametri(g["p"])
    if not p["tekst"]:
        return False
    with Image.open(png) as im:
        rgb = np.asarray(im.convert("RGB"))
    H, W = rgb.shape[:2]
    m = Maskirac()(rgb)
    sloj, x, y = postavi(p["tekst"], W, H, p["boja"], p["polozaj"], m)
    a, dy = animacija(j, g["n"], fps)
    Image.fromarray(slozi(rgb, m, sloj, x, y, a, dy)).save(png)
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
