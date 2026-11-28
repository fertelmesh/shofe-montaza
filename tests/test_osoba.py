"""Izdvajanje osobe (M5.7a): maska osobe (MODNet u cv2.dnn) i efekt „tekst iza osobe" (`iza`).

Bez modela: raspored i slaganje teksta uz nacrtanu masku, umetanje komada na točne sličice (lažni maskirač).
S pravim modelom (SHOFE_MODELI/osoba_modnet.onnx; skida se s GitHub izdanja) — u CI-ju SHOFE_OSOBA_TEST=1, tada
se test ne smije preskočiti."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import grafika  # noqa: E402
import osoba  # noqa: E402

FPS = 30


def run(script, *args, ok=True, env=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def maska_osobe(W, H, cx=0.5, vrh=0.35, glava_r=0.11):
    """Nacrtana osoba: glava (krug) od `vrh` nadolje + tijelo (pravokutnik) do dna."""
    import cv2
    m = np.zeros((H, W), np.float32)
    r = int(glava_r * W)
    cy = int(vrh * H) + r
    cv2.circle(m, (int(cx * W), cy), r, 1.0, -1)
    cv2.rectangle(m, (int(cx * W - 1.6 * r), cy + r), (int(cx * W + 1.6 * r), H), 1.0, -1)
    return m


# ---------------------------------------------------------------- bez modela
def test_retci_i_sloj_teksta():
    assert osoba.retci("SUNČANO") == ["SUNČANO"]
    assert osoba.retci("SUNČANI|PUT") == ["SUNČANI", "PUT"]
    assert osoba.retci("ovo je dulja rečenica") == ["ovo je dulja", "rečenica"]
    s, lh = osoba.sloj_teksta("Čćšžđ", 1080, 1920)
    assert s.dtype == np.uint8 and s.shape[2] == 4
    assert s.shape[1] <= 0.92 * 1080 + 2 * 0.12 * 400 and lh > 100
    assert (s[..., 3] > 200).mean() > 0.15                          # slova su puna (font ima č ć š ž đ)
    bijelo = s[s[..., 3] > 250][:, :3]
    assert bijelo.min() > 240                                       # bijela slova, sjena samo oko njih
    s2, _ = osoba.sloj_teksta("Čćšžđ", 1080, 1920, boja="#FF7A00", mjera=0.5)
    assert s2.shape[1] < s.shape[1] * 0.6
    puna = s2[s2[..., 3] > 250][:, :3]
    assert abs(int(puna[:, 0].mean()) - 255) < 3 and abs(int(puna[:, 1].mean()) - 0x7A) < 3


def test_mjesto_iza_glave_i_krupni_kadar():
    W, H = 1080, 1920
    m = maska_osobe(W, H, vrh=0.35)
    gl = osoba.glava(m)
    assert abs(gl["vrh"] - 0.35) < 0.01 and abs(gl["x"] - 0.5) < 0.02
    sloj, x, y = osoba.postavi("SUNČANO", W, H, m=m)
    sh = sloj.shape[0]
    assert y < 0.35 * H < y + sh                                    # glava zalazi u slova
    c = osoba.pokrivenost(sloj, x, y, m, W, H)
    assert 0.02 < c <= osoba.MAX_POKRIVENO
    assert y >= 0.115 * H                                           # sigurna zona reela gore
    # bez osobe: gornja trećina; ručni položaji
    sl, x0, y0 = osoba.postavi("SUNČANO", W, H, m=np.zeros((H // 4, W // 4), np.float32))
    assert abs((y0 + sl.shape[0] / 2) / H - 0.30) < 0.02
    _, _, yg = osoba.postavi("SUNČANO", W, H, polozaj="gore", m=m)
    _, _, yd = osoba.postavi("SUNČANO", W, H, polozaj="dolje", m=m)
    assert yg == int(0.115 * H) and yd > 0.45 * H
    # krupni kadar (osoba od vrha kadra, široka): slova se smanje / pomaknu dok se ne čitaju
    big = maska_osobe(W, H, vrh=0.05, glava_r=0.3)
    sb, xb, yb = osoba.postavi("SUNČANO", W, H, m=big)
    assert osoba.pokrivenost(sb, xb, yb, big, W, H) < osoba.pokrivenost(*osoba.sloj_teksta("SUNČANO", W, H)[:1],
                                                                        xb, yb, big, W, H) + 1e-6


def test_animacija_i_slaganje():
    a0, dy0 = osoba.animacija(0, 90, 30)
    a1, dy1 = osoba.animacija(45, 90, 30)
    a2, _ = osoba.animacija(89, 90, 30)
    assert a0 == 0 and dy0 > 0.3 and a1 == 1 and dy1 == 0 and a2 < 0.2
    W, H = 200, 300
    rgb = np.full((H, W, 3), 50, np.uint8)
    m = np.zeros((H, W), np.float32)
    m[:, 100:] = 1.0                                                # desna polovica = osoba
    sloj = np.zeros((40, 180, 4), np.uint8)
    sloj[..., :3] = 255
    sloj[..., 3] = 255
    out = osoba.slozi(rgb, m, sloj, 10, 100)
    assert (out[110:130, 20:90] == 255).all()                      # tekst na pozadini
    assert (out[110:130, 110:180] == 50).all()                     # osoba ispred teksta
    assert (out[:90] == 50).all() and (out[150:] == 50).all()
    assert (osoba.slozi(rgb, m, sloj, 10, 100, a=0.0) == rgb).all()
    # zaglađivanje: mala razlika se miješa, veliki pomak ostaje nov
    p = np.full((4, 4), 0.5, np.float32)
    assert abs(float(osoba.zagladi(p, np.full((4, 4), 0.6, np.float32))[0, 0]) - 0.55) < 0.03
    assert float(osoba.zagladi(p, np.full((4, 4), 1.0, np.float32))[0, 0]) == 1.0


def test_velicina_modela_i_stanje(tmp_path, monkeypatch):
    assert osoba.velicina_modela(1080, 1920) == (224, 384)
    assert osoba.velicina_modela(1920, 1080) == (384, 224)
    monkeypatch.setenv("SHOFE_MODELI", str(tmp_path))
    ok, msg = osoba.stanje()
    assert not ok and "preuzmi" in msg


# ---------------------------------------------------------------- projekt
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_efekti_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("osoba čž"), SCRIPTS)
    run("render.py", proj, "--izlaz", "ref.mp4")
    return proj


def frames(path, w=135, h=240):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3).astype(np.int16)


def audio_md5(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def test_efekti_dodaj_iza(projekt):
    r = run("efekti.py", projekt, "dodaj", "iza", "1-3", ok=False)
    assert r.returncode != 0 and "--tekst" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "iza", "1-3", "--tekst", "A", "--boja", "crvena", ok=False)
    assert r.returncode != 0 and "#RRGGBB" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "iza", "1-3", "--tekst", "A", "--polozaj", "lijevo", ok=False)
    assert r.returncode != 0 and "auto" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "trzaj", "1-2", "--tekst", "A", ok=False)
    assert r.returncode != 0 and "iza" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "iza", "1-3", "--tekst", "x" * 50, ok=False)
    assert r.returncode != 0 and "znakova" in r.stderr
    out = run("efekti.py", projekt, "dodaj", "tekst_iza", "1-3", "--tekst", "SUNČANO", "--boja", "#ffc21a").stdout
    assert "„SUNČANO“ iza osobe" in out
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    e = [x for x in edit["efekti"] if x["tip"] == "iza"]
    assert len(e) == 1 and e[0]["parametri"] == {"tekst": "SUNČANO", "boja": "#FFC21A"}
    assert "„SUNČANO“ iza osobe" in run("efekti.py", projekt, "popis").stdout
    run("efekti.py", projekt, "makni", e[0]["id"])


class LazniMaskirac:
    """Umjesto MODNeta: osoba = elipsa oko nacrtanog lica i tijela (sredina kadra)."""
    poziva = 0

    def __init__(self, *a, **k):
        pass

    def __call__(self, rgb):
        LazniMaskirac.poziva += 1
        h, w = rgb.shape[:2]
        return maska_osobe(w, h, vrh=0.26, glava_r=0.14)


def test_umetanje_na_tocne_slicice(projekt, monkeypatch, tmp_path):
    import shutil
    vid = tmp_path / "v.mp4"
    shutil.copy2(projekt / "ref.mp4", vid)
    monkeypatch.setattr(osoba, "Maskirac", LazniMaskirac)
    gx = [{"id": "E1", "tip": "iza", "s": 1.0, "k0": 30, "n": 60, "p": {"tekst": "SUNČANO"}, "fps": 30.0}]
    lines = grafika.umetni(tmp_path, gx, vid, 540, 960, FPS, ispis=False)
    assert "Grafika: 1" in lines[0] and "renderirao 1" in lines[0]
    assert LazniMaskirac.poziva == 60
    a, b = frames(projekt / "ref.mp4"), frames(vid)
    assert len(a) == len(b)
    d = np.abs(a - b)
    inside = range(36, 85)                                             # tekst je ušao (0,35 s) i nije se utišao
    gore = (slice(int(240 * 0.115), int(240 * 0.32)), slice(5, 30))   # lijevo od glave, u pojasu teksta
    assert all(d[i][gore].mean() > 40 for i in inside), [round(float(d[i][gore].mean()), 1) for i in inside]
    lice = (slice(int(240 * 0.30), int(240 * 0.40)), slice(57, 78))    # glava je ispred teksta
    assert max(float(d[i][lice].mean()) for i in inside) < 3
    izvan = [i for i in range(len(d)) if not 30 <= i < 90]
    assert max(float(d[i].mean()) for i in izvan) < 1.0
    assert audio_md5(vid) == audio_md5(projekt / "ref.mp4")
    # drugi put: maske i komad iz predmemorije
    shutil.copy2(projekt / "ref.mp4", vid)
    LazniMaskirac.poziva = 0
    lines = grafika.umetni(tmp_path, gx, vid, 540, 960, FPS, ispis=False)
    assert "renderirao 0" in lines[0] and LazniMaskirac.poziva == 0
    # bez teksta: napomena, video ostaje isti
    shutil.copy2(projekt / "ref.mp4", vid)
    lines = grafika.umetni(tmp_path, [dict(gx[0], p={})], vid, 540, 960, FPS, ispis=False)
    assert any("nije u videu" in x for x in lines)


# ---------------------------------------------------------------- pravi model
def model_spreman():
    ok, msg = osoba.stanje()
    if not ok and os.environ.get("SHOFE_OSOBA_TEST"):
        try:
            osoba.ensure_model()
            return
        except osoba.Greska as ex:
            pytest.fail(f"SHOFE_OSOBA_TEST=1, a model osobe nije spreman: {ex}")
    if not ok:
        pytest.skip(msg)


def test_pravi_model_i_render(projekt):
    """MODNet radi u cv2.dnn (izlaz 0–1, ista sličica = ista maska), render s efektom iza i --kadar ne padaju,
    a bez HyperFramesa tekst iza osobe ipak uđe u video."""
    model_spreman()
    mk = osoba.Maskirac()
    rgb = np.asarray(frames(projekt / "ref.mp4", 270, 480)[30], np.uint8)
    m = mk(rgb)
    assert m.shape == (480, 270) and m.dtype == np.float32 and 0.0 <= m.min() and m.max() <= 1.0
    assert np.abs(mk(rgb) - m).max() < 1e-5
    run("efekti.py", projekt, "dodaj", "iza", "1-3", "--tekst", "SUNČANO")
    env = dict(os.environ, SHOFE_HYPERFRAMES=str(projekt / "nema_hf"))
    out = run("render.py", projekt, "--izlaz", "iza.mp4", env=env).stdout
    assert "Grafika: 1" in out and "grafika nije u videu" not in out
    a, b = frames(projekt / "ref.mp4"), frames(projekt / "iza.mp4")
    assert len(a) == len(b)
    d = [float(np.abs(a[i] - b[i]).mean()) for i in range(len(a))]
    assert d[60] > 2 and max(d[:28]) < 1.0 and max(d[95:]) < 1.0
    assert audio_md5(projekt / "iza.mp4") == audio_md5(projekt / "ref.mp4")
    r = run("render.py", projekt, "--kadar", "2", env=env)
    assert r.returncode == 0
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    run("efekti.py", projekt, "makni", next(x["id"] for x in edit["efekti"] if x["tip"] == "iza"))
