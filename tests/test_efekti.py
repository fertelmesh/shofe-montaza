"""Efekti (M5.1): sustav u edit.json + ffmpeg zumovi, zamrznuti kadar s oznakom, film i retro."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import efekti  # noqa: E402


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def ff_eval(expr, **vals):
    """ffmpeg izraz (clip, pow, max, min, sin) izračunat u Pythonu."""
    env = {"clip": lambda x, a, b: max(a, min(b, x)), "pow": pow, "max": max, "min": min, "sin": np.sin}
    env.update(vals)
    return eval(expr, env)  # noqa: S307 (naš vlastiti izraz)


# ---------------------------------------------------------------- bez rendera
CUTS = [{"a": 0.0, "b": 2.0, "o": 0.0}, {"a": 3.0, "b": 6.0, "o": 2.0}, {"a": 8.0, "b": 10.0, "o": 5.0}]


def test_out_span_preko_reza_je_jedan_komad():
    assert efekti.out_span(1.0, 4.0, CUTS) == (1.0, 3.0)        # 2–3 s izrezano: efekt je 1–3 s gotovog
    assert efekti.out_span(2.2, 2.8, CUTS) is None               # sve izrezano
    s, e = efekti.out_span(5.0, 9.0, CUTS)
    assert (round(s, 3), round(e, 3)) == (4.0, 6.0)


def test_plan_preskace_skracuje_i_razumije_alias():
    edit = {"efekti": [
        {"id": "E1", "tip": "punch", "od": 0.5, "do": 1.5},
        {"id": "E2", "tip": "trzaj", "od": 2.1, "do": 2.9},                      # izrezano
        {"id": "E3", "tip": "zamrzni", "od": 3.0, "do": 5.9, "parametri": {"oznaka": "Ivan"}},  # 2,9 s ≤ 4
        {"id": "E4", "tip": "pad", "od": 8.0, "do": 9.0, "parametri": {"zum": 5}},
        {"id": "E5", "tip": "laser", "od": 1, "do": 2},
    ]}
    fx, notes = efekti.plan(edit, CUTS, 30, 7.0)
    assert [x["id"] for x in fx] == ["E1", "E3", "E4"]
    assert fx[0]["tip"] == "trzaj" and fx[0]["p"]["zum"] == 1.3
    assert fx[2]["p"]["zum"] == efekti.ZUM_MAX
    assert any("E2" in n and "izrezan" in n for n in notes)
    assert any("E5" in n and "nepoznat" in n for n in notes)
    for x in fx:   # poravnato na sličice
        assert abs(x["s"] * 30 - round(x["s"] * 30)) < 1e-6 and abs(x["e"] * 30 - round(x["e"] * 30)) < 1e-6


@pytest.mark.parametrize("tip,u,ocekivano", [
    ("guranje", 0.0, 1.0), ("guranje", 0.5, 1.075), ("guranje", 1.0, 1.15),
    ("trzaj", 0.0, 1.0), ("trzaj", 0.1, 1.3), ("trzaj", 0.9, 1.3),
    ("pad", 0.0, 1.4), ("pad", 0.45, 1.0), ("pad", 0.9, 1.0),
])
def test_krivulje_zuma(tip, u, ocekivano):
    x = {"tip": tip, "s": 2.0, "e": 3.0, "p": efekti.parametri({"tip": tip})}
    z = ff_eval(efekti.zoom_expr(x, "T"), T=2.0 + u)
    assert abs(z - ocekivano) < 1e-3, (tip, u, z)


def test_zum_oko_lica_drzi_lice_na_mjestu():
    x = {"tip": "trzaj", "s": 0.0, "e": 1.0, "p": dict(efekti.parametri({"tip": "trzaj"}),
                                                       lice={"x": 0.3, "y": 0.4, "h": 0.2})}
    f = efekti.perspective_zoom(x, 1080, 1920, "0.5")
    vals = dict(re.findall(r"(x0|x1|y0|y2)='([^']+)'", f))
    x0, x1 = ff_eval(vals["x0"]), ff_eval(vals["x1"])
    y0, y2 = ff_eval(vals["y0"]), ff_eval(vals["y2"])
    assert abs((x1 - x0) - 1080 / 1.3) < 0.01 and abs((y2 - y0) - 1920 / 1.3) < 0.01
    # točka lica (324, 768) iz izvora pada na isto mjesto gotove slike
    assert abs((324 - x0) / (x1 - x0) * 1080 - 324) < 0.01 and abs((768 - y0) / (y2 - y0) * 1920 - 768) < 0.01
    assert 0 <= x0 and x1 <= 1080 and 0 <= y0 and y2 <= 1920


def test_oznaka_iznad_lica_i_unutar_kadra():
    x = {"id": "E1", "tip": "zamrzni", "s": 1.0, "e": 2.0,
         "p": {"oznaka": "Čišćenje {klime}", "lice": {"x": 0.95, "y": 0.4, "h": 0.15}}}
    ev = efekti.ass_events([x], 1080, 1920)
    txt = ev[0][4]
    assert "ČIŠĆENJE (KLIME)" in txt
    px, py = map(float, re.search(r"\\pos\(([\d.]+),([\d.]+)\)", txt).groups())
    assert px < 1080 * 0.96 and py < 0.4 * 1920       # iznad lica, ne preko ruba
    low = {"id": "E2", "tip": "zamrzni", "s": 1.0, "e": 2.0, "p": {"oznaka": "Ivan", "lice": {"x": 0.5, "y": 0.12, "h": 0.15}}}
    ty = float(re.search(r"\\pos\([\d.]+,([\d.]+)\)", efekti.ass_events([low], 1080, 1920)[0][4]).group(1))
    assert 0.12 * 1920 < ty <= 0.6 * 1920              # lice pri vrhu: oznaka ispod lica, iznad titlova


# ---------------------------------------------------------------- pravi render
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_efekti_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("efekti čž"), SCRIPTS)
    run("render.py", proj, "--izlaz", "ref.mp4")
    return proj


def frames(path, w=270, h=480):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3)


def face(img):
    import kadar
    h, w = img.shape[:2]
    _, res = kadar.detector(w, h).detect(np.ascontiguousarray(img))
    assert res is not None and len(res), "lice nije nađeno"
    d = max(res, key=lambda r: r[2] * r[3])
    return (d[0] + d[2] / 2) / w, (d[1] + d[3] / 2) / h, d[3] / h


def test_cijeli_put(projekt):
    out = run("efekti.py", projekt, "tipovi").stdout
    assert all(t in out for t in efekti.TIPOVI)
    run("efekti.py", projekt, "dodaj", "trzaj", "1-2.5")
    run("efekti.py", projekt, "dodaj", "vertigo", "2.6-4", "--jacina", "0.3")
    run("efekti.py", projekt, "dodaj", "zamrzni", "5.2-6.6", "--oznaka", "Čišćenje klime")
    run("efekti.py", projekt, "dodaj", "film", "0.1-0.95")
    run("efekti.py", projekt, "dodaj", "retro", "6.7-7.7")
    r = run("efekti.py", projekt, "dodaj", "guranje", "2-3", ok=False)   # preko trzaja i vertiga
    assert r.returncode != 0 and "E1" in (r.stdout + r.stderr)
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert [e["tip"] for e in edit["efekti"]] == ["film", "trzaj", "vertigo", "zamrzni", "retro"]
    trz = next(e for e in edit["efekti"] if e["tip"] == "trzaj")
    assert "lice" in trz["parametri"]                       # lice nađeno na prvoj sličici
    popis = run("efekti.py", projekt, "popis").stdout
    assert "00:05.20-00:06.60  zamrzni" in popis and "prema licu" in popis

    out = run("render.py", projekt, "--izlaz", "fx.mp4").stdout
    assert "Efekti: 5" in out and "DaVinci" in out
    ass = (projekt / "captions.ass").read_text(encoding="utf-8")
    assert "ČIŠĆENJE KLIME" in ass and "Style: Oznaka" in ass

    ref, fx = frames(projekt / "ref.mp4"), frames(projekt / "fx.mp4")
    assert abs(len(ref) - len(fx)) <= 1                     # efekti ne mijenjaju trajanje
    fps = 30

    def at(t):
        return int(round(t * fps))

    # trzaj: lice 1,3× veće, na istom mjestu kadra
    rx, ry, rh = face(ref[at(2.0)])
    fx_, fy_, fh = face(fx[at(2.0)])
    assert 1.18 < fh / rh < 1.42, fh / rh
    assert abs(fx_ - rx) < 0.03 and abs(fy_ - ry) < 0.03
    # prije efekta: isto kao bez efekata
    assert np.abs(ref[at(0.98)].astype(int) - fx[at(0.98)].astype(int)).mean() < 4
    # vertigo: lice skoro iste veličine, rubovi kadra jako drukčiji
    _, _, rh2 = face(ref[at(3.9)])
    _, _, fh2 = face(fx[at(3.9)])
    assert fh2 / rh2 < 1.2
    edge = (slice(0, 60), slice(0, 60))
    assert np.abs(ref[at(3.9)][edge].astype(int) - fx[at(3.9)][edge].astype(int)).mean() > 15
    # zamrzni: donji dio (brojač sličica) stoji cijelo vrijeme, a bez efekta se mijenja
    low = (slice(400, 480), slice(0, 270))
    a, b = fx[at(5.45)][low].astype(int), fx[at(6.5)][low].astype(int)
    assert np.abs(a - b).mean() < 2.5
    assert np.abs(ref[at(5.45)][low].astype(int) - ref[at(6.5)][low].astype(int)).mean() > 3
    assert fx[at(5.21)].mean() > fx[at(5.6)].mean() + 8          # bljesak na početku

    # film: manje zasićeno od originala; retro: jače boje
    import cv2

    def sat(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].mean()

    assert sat(fx[at(0.5)]) < 0.8 * sat(ref[at(0.5)])
    assert sat(fx[at(7.2)]) > 1.05 * sat(ref[at(7.2)])


def test_slike_efekta_i_izmjene(projekt):
    out = run("efekti.py", projekt, "pokazi", "E3").stdout
    assert (projekt / "efekt_E3.png").stat().st_size > 10_000 and "zamrzni" in out
    # rez prije efekta: efekt ostaje na istim riječima (vrijeme izvornog videa)
    before = run("efekti.py", projekt, "popis").stdout
    run("uredi.py", projekt, "makni", "0:00.2-0:00.9", "--trenutno")
    after = run("efekti.py", projekt, "popis").stdout
    t0 = re.search(r"(\d\d):(\d\d\.\d\d)-\S+\s+zamrzni", before)
    t1 = re.search(r"(\d\d):(\d\d\.\d\d)-\S+\s+zamrzni", after)
    assert float(t1.group(2)) < float(t0.group(2)) - 0.3
    run("uredi.py", projekt, "vrati")
    run("efekti.py", projekt, "makni", "E1", "E3")
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in edit["efekti"]] == ["E4", "E2", "E5"]
    run("uredi.py", projekt, "vrati")                      # vrati vraća i naredbe efekata
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert len(edit["efekti"]) == 5
    r = run("efekti.py", projekt, "makni", "E9", ok=False)
    assert r.returncode != 0


def test_kadar_isti_kao_video(projekt):
    """--kadar (i efekti.py pokazi) pokazuje isto što je u videu: zamrznuti kadar, zum, vertigo."""
    import cv2
    fx = frames(projekt / "fx.mp4")
    times = [2.0, 3.8, 6.4]
    run("render.py", projekt, "--kadar", ",".join(map(str, times)))
    for k, t in enumerate(times):
        # imdecode: cv2.imread na Windowsu ne čita putanje s č/ž
        png = np.fromfile(projekt / f"kadar_{k + 1}_{t:g}s.png", np.uint8)
        img = cv2.resize(cv2.imdecode(png, cv2.IMREAD_COLOR), (270, 480),
                         interpolation=cv2.INTER_AREA).astype(int)
        diff = np.abs(img - fx[int(round(t * 30))].astype(int)).mean()
        assert diff < 6, (t, diff)
