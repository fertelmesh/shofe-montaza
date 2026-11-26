"""M3.2: kadar 9:16 prati govornika (kadar.py) na vodoravnom klipu s dvije osobe.

Probni klip (make_kadar_klip.py): osoba A lijevo, B desno, nacrtana lica, usta se miču po glasu iz
razgovor.m4a; glas C govori izvan kadra. Treba OpenCV (opencv-python-headless) — bez njega se preskače.
"""
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import kadar as K  # noqa: E402

cv2 = pytest.importorskip("cv2")
cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
import make_kadar_klip as MK  # noqa: E402

RAZ = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))
SHIRT = {"A": np.array(MK.SEATS["A"][5]), "B": np.array(MK.SEATS["B"][5])}


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def frame_bgr(path, t, w=270, h=480):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3)


def who_is_shown(img):
    """Čija je majica na dnu sredine kadra (A plava, B zelena) i gdje je lice (x 0–1)."""
    h, w = img.shape[:2]
    px = img[int(h * 0.9), w // 2 - 10:w // 2 + 10].mean(axis=0)
    g = min(SHIRT, key=lambda k: np.abs(px - SHIRT[k]).sum())
    det = cv2.FaceDetectorYN.create(str(K.MODEL), "", (w, h), 0.6, 0.3, 5)
    _, res = det.detect(img)
    fx = float(res[0][0] + res[0][2] / 2) / w if res is not None else None
    return g, fx


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    base = tmp_path_factory.mktemp("kadar čćž")
    snimke = base / "Sunčani4M snimke"
    snimke.mkdir()
    MK.make(snimke / "razgovor u autu.mp4")
    p = base / "projekt"
    run("prepare.py", snimke, "--out", p)
    words = [w for w in RAZ["words"] if w["e"] <= MK.DUR]
    save(p / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    segs = [{"od": a, "do": b, "govornik": "G" + str("ABC".index(g) + 1)} for a, b, g in MK.truth()]
    save(p / "govornici.json", {"govornici": [], "odsjecci": segs})
    r = run("kadar.py", p)
    assert "kadar prati govornika" in r.stdout
    return p


# ---------------------------------------------------------------- bez videa

def test_kadrovi_rupe_i_prekratki():
    f = K.FPS_ANALIZE
    act = [-1] * 5 + [0] * 30 + [1] * 5 + [0] * 20 + [-1] * 30 + [1] * 40
    runs = K.shots(act)
    # rupe na početku i usred govora preuzmu susjeda; 0,5 s osobe 1 ne mijenja kadar
    assert runs == [(0, 90, 0), (90, 130, 1)]
    assert K.shots([0] * 3 * f) == [(0, 3 * f, 0)]
    # između dva različita govornika kratki dio ide duljem susjedu
    assert K.shots([0] * 40 + [1] * 5 + [2] * 20) == [(0, 45, 0), (45, 65, 2)]


def test_crop_iz_polozaja_lica():
    info = {"w": 1920, "h": 1080}
    assert K.crop_for(0.5, info, 1080, 1920) == pytest.approx(0.5)
    assert K.crop_for(0.02, info, 1080, 1920) == 0.0 and K.crop_for(0.98, info, 1080, 1920) == 1.0
    # lice na 0,3 širine: središte kadra točno na licu
    cx = K.crop_for(0.3, info, 1080, 1920)
    sw = 1920 * 1920 / 1080
    assert (sw - 1080) * cx + 540 == pytest.approx(0.3 * sw)
    assert K.crop_for(0.3, {"w": 1080, "h": 1920}, 1080, 1920) == 0.5     # uspravno: ništa za pomicati
    assert K.needs_tracking({"w": 1920, "h": 1080}, 1080, 1920)
    assert not K.needs_tracking({"w": 1080, "h": 1920}, 1080, 1920)


def test_naredbe_za_ffmpeg_rez_bez_svenka(tmp_path):
    f = K.FPS_ANALIZE
    put = [0.2] * (2 * f) + [0.8] * (2 * f)
    res = {"put": put, "fps_analize": f, "dur": 4.0,
           "kadrovi": [{"od": 0.0, "do": 2.0, "crop_x": 0.2}, {"od": 2.0, "do": 4.0, "crop_x": 0.8}]}
    dst = tmp_path / "k.txt"
    K.cmd_file(res, {"w": 1920, "h": 1080}, 1080, 1920, 30, dst, t0=0.1)
    lines = dst.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "0.1000 crop@kadar x (iw-1080)*0.2000;"
    assert lines[1] == "2.1000 crop@kadar x (iw-1080)*0.8000;"   # jedan skok točno na rezu
    assert len(lines) == 2


def test_govornik_prema_usnama():
    n = 100
    t = np.arange(n) / 10
    quiet, loud = np.full(n, 0.1), np.full(n, 0.1)
    p0 = {"x": np.full(n, 0.3), "akt": np.where(t < 5, 0.8, 0.1)}
    p1 = {"x": np.full(n, 0.7), "akt": np.where(t >= 5, 0.8, 0.1)}
    segs = [(0.0, 5.0, "G2"), (5.0, 10.0, "G1"), (6.0, 7.0, "G3")]
    mapping, _ = K.match_speakers([p0, p1], segs, t)
    assert mapping == {"G2": 0, "G1": 1}
    assert quiet.sum() == loud.sum()


# ---------------------------------------------------------------- pravi klip

def test_kadar_prati_onoga_tko_govori(proj):
    kj = load(proj / "kadar.json")
    (c,) = kj["klipovi"]
    assert c["nacin"] == "govornici" and len(c["osobe"]) == 2
    assert [o["govornik"] for o in c["osobe"]] == ["G1", "G2"]      # A lijevo = G1, B desno = G2
    for a, b, g in MK.truth():
        mid = (a + b) / 2
        k = next(k for k in c["kadrovi"] if k["od"] <= mid < k["do"])
        if g == "C":                                                  # izvan kadra: kadar ostaje
            assert k["govornik"] == "G2"
            continue
        assert k["govornik"] == {"A": "G1", "B": "G2"}[g]
        assert abs(k["od"] - a) < 0.5 or k["od"] < a                   # rez najkasnije na početku rečenice
        shown, fx = who_is_shown(frame_bgr(proj / "source.mp4", mid))
        assert shown == g, (mid, shown, g)
        assert fx is not None and abs(fx - 0.5) < 0.08, (mid, fx)     # lice na sredini kadra 9:16
    # rezovi između govornika, bez međupoložaja (švenka preko praznog prostora)
    assert len(c["kadrovi"]) == 5 and all(k["nacin"] == "miruje" for k in c["kadrovi"])
    pj = load(proj / "project.json")
    assert pj["clips"][0]["kadar"] == "prati" and len(pj["clips"][0]["kadrovi"]) == 5
    assert abs(pj["duration"] - MK.DUR) < 0.15


def test_bez_govornika_samo_usne(proj, tmp_path):
    p = tmp_path / "usne"
    p.mkdir()
    for f in ("project.json", "transcript.json", "source.mp4"):
        shutil.copy(proj / f, p / f)
    r = run("kadar.py", p, "--analiza")
    assert "govornici.py" in r.stdout                                  # savjet da pokrene govornike
    (c,) = load(p / "kadar.json")["klipovi"]
    assert c["nacin"] == "usne"
    for a, b, g in MK.truth():
        if g == "C":
            continue
        mid = (a + b) / 2
        k = next(k for k in c["kadrovi"] if k["od"] <= mid < k["do"])
        assert k["osoba"] == {"A": "O1", "B": "O2"}[g], (a, b, k)


def test_davinci_rez_na_promjeni_govornika(proj):
    run("plan.py", proj)
    run("davinci.py", proj, "--trenutno")
    root = ET.parse(proj / "titlovi_trenutno.fcpxml").getroot()
    spine = root.find("library/event/project/sequence/spine")
    pos = [float(c.find("adjust-transform").get("position").split()[0]) for c in spine
           if c.find("adjust-transform") is not None]
    assert any(x > 5 for x in pos) and any(x < -5 for x in pos)       # lijevo (A) i desno (B)
    # slika iz originala po FCPXML-u = Shofeov source.mp4 (isti izrez za svaki dio)
    pj = load(proj / "project.json")
    W, H = pj["width"], pj["height"]
    cl = pj["clips"][0]
    s = max(W / cl["w"], H / cl["h"])
    sw, sh = round(cl["w"] * s / 2) * 2, round(cl["h"] * s / 2) * 2
    T = __import__("davinci").parse_time
    asset = next(a for a in root.iter("asset") if a.get("hasVideo") == "1")
    for c in spine:
        if c.find("adjust-transform") is None:
            continue
        px = float(c.find("adjust-transform").get("position").split()[0])
        local = float(T(c.get("start")) - T(asset.get("start"))) + float(T(c.get("duration"))) / 2
        x0 = (sw - W) / 2 - px / 100 * H
        vf = f"scale={sw}:{sh},crop={W}:{H}:{x0:.1f}:0,scale=108:192"
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{local:.3f}", "-i", cl["file"], "-frames:v", "1",
                            "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
        got = np.frombuffer(r.stdout, np.uint8).astype(float)
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{cl['start'] + local:.3f}", "-i",
                            str(proj / "source.mp4"), "-frames:v", "1", "-vf", "scale=108:192", "-f", "rawvideo",
                            "-pix_fmt", "gray", "-"], capture_output=True)
        want = np.frombuffer(r.stdout, np.uint8).astype(float)
        assert np.mean(np.abs(got - want)) < 10, (local, px, np.mean(np.abs(got - want)))


def test_vrati_i_uspravni_klip(proj, tmp_path):
    p = tmp_path / "vrati"
    p.mkdir()
    for f in ("project.json", "transcript.json", "source.mp4"):
        shutil.copy(proj / f, p / f)
    run("kadar.py", p, "--vrati")
    pj = load(p / "project.json")
    assert "kadrovi" not in pj["clips"][0]
    shown_before = who_is_shown(frame_bgr(proj / "source.mp4", 3.0))[1]
    img = frame_bgr(p / "source.mp4", 3.0)
    # nepomični kadar na sredini: lice A (x 0,27 snimke) je izvan ili na rubu kadra
    assert shown_before is not None and (who_is_shown(img)[1] is None or abs(who_is_shown(img)[1] - 0.5) > 0.2)
    # uspravni klip: ništa za pratiti
    u = tmp_path / "uspravni"
    run("prepare.py", FIX / "klip2.mp4", "--out", u)
    r = run("kadar.py", u)
    assert "preskačem" in r.stdout and not (u / "kadar.json").exists()
    # vodoravni klip bez lica: kadar ostaje gdje ga je stavio prepare.py
    v = tmp_path / "bez lica"
    run("prepare.py", FIX / "klip1.mp4", "--out", v, "--crop-x", "0.3")
    r = run("kadar.py", v, "--analiza")
    (c,) = load(v / "kadar.json")["klipovi"]
    assert c["nacin"] == "nema lica" and [k["crop_x"] for k in c["kadrovi"]] == [0.3]


def test_kamera_miruje_ili_ide_za_licem():
    n = 100
    info = {"w": 1920, "h": 1080}
    still = {"x": 0.3 + 0.01 * np.sin(np.arange(n) / 3), "w": np.full(n, 0.1)}       # njiše se: kamera miruje
    walk = {"x": np.linspace(0.2, 0.7, n), "w": np.full(n, 0.1)}                      # hoda: kamera ide za licem
    path, ks = K.plan_path([still, walk], [(0, 50, 0), (50, 100, 1)], info, 1080, 1920, 0.5)
    assert ks[0]["nacin"] == "miruje" and np.ptp(path[:50]) == 0
    assert ks[1]["nacin"] == "prati" and np.all(np.diff(path[55:95]) > 0)            # glatko, jedan smjer
    assert abs(path[75] - K.crop_for(walk["x"][75], info, 1080, 1920)) < 0.03
    # nema lica: nepomični kadar iz prepare.py
    path, ks = K.plan_path([still], [(0, 100, -1)], info, 1080, 1920, 0.42)
    assert np.all(path == 0.42) and ks[0]["osoba"] is None
