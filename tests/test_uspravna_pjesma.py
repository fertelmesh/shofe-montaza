"""M4.3b4: uspravni (9:16) isječak pjesme iz podcasta — za vrijeme pjesme režija u ritmu (bend iz širokog kadra,
krupni kadrovi redom, rez na početku takta) umjesto praćenja „govornika" (pjevanja); bend cijeli u širini kadra
s mutnom pozadinom; DaVinci 9:16: bend kao dvije trake (pozadina V1, skupina V2)."""
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import uspravno as U  # noqa: E402
from conftest import run_script as run  # noqa: E402
from test_davinci import dtd, validate  # noqa: E402,F401
from test_rezija_pjesme import BEATS, bend  # noqa: E402,F401
from test_uspravno import TRI, _kadar_iz_sloja, ctx_za  # noqa: E402

SEGS = [(1, 18, "G1"), (18.5, 30, "G2"), (31, 90, "G1"), (92, 140, "G2")]   # 31–90 G1 „govori" = pjeva


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ctx_pjesma(kamere=TRI, kadar=8.0, udarci=BEATS):
    ctx = ctx_za(SEGS, kamere)
    ctx["pjesme"] = [{"id": "P1", "od": 30.03, "do": 89.87, "naziv": "Bend", "udarci": list(udarci)}]
    ctx["pjesma_kadar"] = kadar
    return ctx


# ---------------------------------------------------------------- pravila (bez videa)

def test_pjesma_u_ritmu_ne_prati_pjevaca():
    ctx = ctx_pjesma()
    shots = U.rezija(ctx, 10.0, 100.0)
    assert shots[0]["od"] == 10.0 and shots[-1]["do"] == 100.0
    for x, y in zip(shots, shots[1:]):
        assert x["do"] == y["od"]
    inside = [s for s in shots if s.get("pjesma") == "P1"]
    assert inside[0]["od"] == pytest.approx(30.03) and inside[-1]["do"] >= 89.87
    # počne i završi bend (cijela skupina iz širokog kadra), između krupni kadrovi obiju osoba
    assert inside[0]["raspored"] == inside[-1]["raspored"] == "bend"
    assert inside[0]["zasto"] == "pjesma P1: bend"
    closeups = {s["dijelovi"][0][1] for s in inside if s["raspored"] == "jedan"}
    assert closeups == {"G1", "G2"}                   # ne samo „pjevač" G1: kamere idu redom
    assert all(len(s["dijelovi"]) == 1 for s in inside)                 # nema podijeljenog kadra u pjesmi
    # rez točno na početku takta (svaki 4. udarac), kadrovi ≥ PJESMA_MIN, prosjek ≈ 0,75 × 8 s
    for s in inside[1:]:
        assert min(abs(s["od"] - g) for g in BEATS[::4]) < 1e-6
    lens = [min(s["do"], 89.87) - s["od"] for s in inside]
    assert min(lens) >= 4.0 - 1e-6 and 5.0 < np.mean(lens) < 9.5
    assert inside[0]["takt"] == 4
    # govor prije i poslije pjesme kao prije
    assert shots[0]["raspored"] == "jedan" and shots[0]["dijelovi"][0][1] == "G1" and not shots[0].get("pjesma")
    assert shots[-1]["dijelovi"][0][1] == "G2" and not shots[-1].get("pjesma")
    s = U.sazetak(shots)
    assert "u pjesmi" in s and "rez na početku takta" in s and "× bend" in s


def test_isjecak_samo_iz_pjesme_i_postavke():
    ctx = ctx_pjesma()
    # isječak refrena usred pjesme: i on počne i završi bendom, rez na taktu
    shots = U.rezija(ctx, 50.0, 80.0)
    assert all(s.get("pjesma") == "P1" for s in shots)
    assert shots[0]["raspored"] == shots[-1]["raspored"] == "bend" and len(shots) >= 3
    # 0 = cijela pjesma u širokom kadru (Markova postavka iz rezija.py --pjesma-kadar 0)
    shots0 = U.rezija(ctx_pjesma(kadar=0), 30.03, 89.87)
    assert [s["raspored"] for s in shots0] == ["bend"]
    # bez ritma: rez po sekundama
    shots2 = U.rezija(ctx_pjesma(udarci=[]), 30.03, 89.87)
    assert len(shots2) >= 5 and "rez po sekundama" in U.sazetak(shots2)
    # bez širokog kadra: krupni kadrovi redom
    shots3 = U.rezija(ctx_pjesma(kamere=TRI[1:]), 30.03, 89.87)
    assert {s["dijelovi"][0][1] for s in shots3} == {"G1", "G2"} and all(s["raspored"] == "jedan" for s in shots3)


def test_komadic_govora_uz_pjesmu_preuzme_pjesma():
    ctx = ctx_pjesma()
    shots = U.rezija(ctx, 29.0, 91.0)            # 29–30,03 govor (1 s) i 89,87–91 (1,1 s): prekratko
    assert shots[0]["od"] == 29.0 and shots[0].get("pjesma") == "P1" and shots[0]["raspored"] == "bend"
    assert shots[-1]["do"] == 91.0 and shots[-1].get("pjesma") == "P1"


def test_geometrija_benda():
    cam = {"w": 1920, "h": 1080}
    # dvoje na 0,3 i 0,7: ne stanu u izrez 9:16 → cijela skupina u širini, iznad i ispod pozadina
    part, r = U.dio_pjesme(ctx_pjesma(), 0)
    assert r == "bend" and part[4] == pytest.approx(0.4 + 0.08 + 2 * U.BEND_RUB * 0.08, abs=1e-3)
    sw, sh, x, oy = U.geometrija_bend(cam, part)
    assert sh < 1920 and oy > 0 and oy + sh <= 1920
    assert (part[4] * sw) == pytest.approx(U.BEND_POPUNA * 1080, rel=0.01)       # skupina = 96 % širine
    lo, hi = (part[2] - part[4] / 2) * sw - x, (part[2] + part[4] / 2) * sw - x
    assert lo >= 0 and hi <= 1080                                                 # cijela skupina u kadru
    assert oy + sh / 2 == pytest.approx(U.BEND_Y * 1920, abs=2)
    # uska skupina (jedna osoba u širokom) → običan izrez oko nje
    one = [("siroka", "siroki", None, [("G1", 0.62, 0.05)], 0, 600, 1920, 1080)] + TRI[1:]
    part, r = U.dio_pjesme(ctx_pjesma(kamere=one), 0)
    assert r == "siroki" and part[2] == pytest.approx(0.62, abs=0.01) and part[4] is None
    # široki bez lica: cijela slika
    none = [("siroka", "siroki", None, [], 0, 600, 1920, 1080)] + TRI[1:]
    part, r = U.dio_pjesme(ctx_pjesma(kamere=none), 0)
    assert r == "bend" and part[4] == 1.0


def test_davinci_sloj_benda():
    import davinci
    cam = {"w": 1920, "h": 1080}
    part = (0, None, 0.5, 0.45, 0.67)
    sw, sh, x, oy = U.geometrija_bend(cam, part)
    zx, zy, px, py = davinci.vertical_layer_bend(cam, part, 1080, 1920)
    c = 1920 / 1080
    assert zx * 1920 * c == pytest.approx(sw, abs=1) and zy * 1080 * c == pytest.approx(sh, abs=1)
    assert py == pytest.approx(-((oy + sh / 2) - 960) / 1920 * 100, abs=0.01) and py > 0   # malo iznad sredine


# ---------------------------------------------------------------- cijeli put: podcast s bendom

def _frame(path, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(1920, 1080, 3).astype(float)


@pytest.fixture(scope="module")
def isjecak(bend, tmp_path_factory):
    proj = tmp_path_factory.mktemp("usp") / "ep"
    shutil.copytree(bend[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci", "isjecci.json"))
    run("isjecci.py", proj, "pjesma", "P1")
    out = run("isjecci.py", proj, "render", "K1")
    return proj, out


def test_uspravni_isjecak_pjesme_u_ritmu(isjecak):
    proj, out = isjecak
    assert "u pjesmi" in out and "× bend" in out and "rez na početku takta" in out
    info = load(proj / "isjecci" / "izvor_9x16" / "K1.json")
    shots = [s for s in info["kadrovi"] if s["do"] > 20.0 and s["od"] < 45.0]
    assert all(s.get("pjesma") == "P1" for s in shots) and len(shots) >= 3
    assert shots[0]["raspored"] == shots[-1]["raspored"] == "bend"
    assert shots[0]["dijelovi"][0]["kamera"] == "siroka.mp4" and "skupina" in shots[0]["dijelovi"][0]
    assert any(s["raspored"] == "jedan" for s in shots)
    beat = 60 / 112
    for s in shots[1:]:                                   # rez na udarac benda (bend svira od 20 s)
        o = (s["od"] - 20.0) % beat
        assert min(o, beat - o) < 0.06, s
    # slika benda: obje osobe u kadru (lica na ~0,28 i ~0,72 širine kamere), iznad i ispod tamnija mutna pozadina
    t = (shots[0]["od"] + shots[0]["do"]) / 2 - info["pomak"]
    img = _frame(proj / "isjecci" / "izvor_9x16" / "K1.mp4", t)
    cam = {"w": 640, "h": 360}
    p = shots[0]["dijelovi"][0]
    sw, sh, x, oy = U.geometrija_bend(cam, (0, None, p["x"], p["y"], p["skupina"]))
    for fx in (0.28, 0.72):
        X, Y = int(fx * sw - x), int(oy + 0.47 * sh)
        assert 0 < X < 1080
        skin = img[Y - 4:Y + 4, X - 4:X + 4].mean(axis=(0, 1))
        assert skin[0] > 150 and skin[0] > skin[2] + 30, (fx, skin)       # boja lica, ne pozadina
    top, mid = img[: oy - 20], img[oy + 20: oy + sh - 20]
    assert top.mean() < mid.mean()                                        # pozadina potamnjena
    assert np.abs(np.diff(top, axis=1)).mean() < np.abs(np.diff(mid, axis=1)).mean()   # i mutna


def test_davinci_9x16_bend_dvije_trake(isjecak, dtd):
    import davinci
    T = davinci.parse_time
    proj, _ = isjecak
    x = next((proj / "isjecci").glob("K1*.fcpxml"))
    validate(dtd, x)
    root = ET.parse(x).getroot()
    assets = {a.get("id"): a for a in root.iter("asset")}
    spine = list(root.find("library/event/project/sequence/spine"))
    bends = [c for c in spine if "bend (pozadina)" in (c.get("name") or "")]
    assert len(bends) >= 2
    sync = {e["ime"]: e for e in load(proj / "sinkro.json")["izvori"]}
    info = load(proj / "isjecci" / "izvor_9x16" / "K1.json")
    edit = load(next((proj / "isjecci").glob("K1*.edit.json")))
    import render
    pj = load(proj / "project.json")
    cuts, _, _ = render.build_cuts(load(proj / "transcript.json")["words"], edit, render.resolve_style(edit),
                                   int(pj["fps"]), pj["duration"])
    c = bends[0]
    lanes = {a.get("lane"): a for a in c.findall("asset-clip")}
    fg = lanes["1"]
    assert fg.get("name") == "siroka.mp4 bend" and assets[fg.get("ref")].get("name") == "siroka.mp4"
    assert lanes["2"].get("enabled") == "0"                                # rezerva: gotova slika
    d = float(T(c.get("duration")))
    tr = fg.find("adjust-transform")
    zx, zy = map(float, tr.get("scale").split())
    px, py = map(float, tr.get("position").split())
    local = float(T(fg.get("start")) - T(assets[fg.get("ref")].get("start"))) + d / 2
    cam = dict(sync["siroka.mp4"], w=640, h=360)
    canvas, m = _kadar_iz_sloja(cam, local, zx, zy, px, py, None)
    out_t = float(T(c.get("offset"))) + d / 2
    k = next(k for k in cuts if k["o"] <= out_t < k["o"] + k["b"] - k["a"] + 1e-6)
    prog = k["a"] + out_t - k["o"]
    want = _frame(proj / "isjecci" / "izvor_9x16" / "K1.mp4", prog - info["pomak"])
    rows = np.where(m.any(axis=1))[0]
    assert 300 < rows.min() and rows.max() < 1620                           # skupina je traka u sredini
    assert float(np.mean(np.abs(canvas[m] - want[m]))) < 6                   # ista slika kao Shofeova
