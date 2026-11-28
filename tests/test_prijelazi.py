"""Prijelazi na rezovima (M5.2a): iris, rolete, vrata, brisanje, klizanje, pretapanje, crno, bljesak, prolaz,
zamah, pikseli — centrirani na rezu, trajanje videa se ne mijenja."""
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
import prijelazi  # noqa: E402


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


# ---------------------------------------------------------------- bez rendera
CUTS = [{"a": 0.0, "b": 2.0, "o": 0.0}, {"a": 3.0, "b": 6.0, "o": 2.0}, {"a": 8.0, "b": 8.4, "o": 5.0}]


def test_rez_se_nade_po_oba_ili_jednom_vremenu():
    assert prijelazi.nadji_rez(2.0, 3.0, CUTS) == 1
    assert prijelazi.nadji_rez(6.0, 8.0, CUTS) == 2
    assert prijelazi.nadji_rez(2.0, 3.5, CUTS) == 1      # kadar B sad počinje kasnije: kraj A još vrijedi
    assert prijelazi.nadji_rez(1.2, 3.0, CUTS) == 1
    assert prijelazi.nadji_rez(4.0, 5.0, CUTS) is None   # tog reza više nema


def test_plan_centriran_na_rezu_i_skracen_uz_kratki_kadar():
    edit = {"efekti": [
        {"id": "E1", "tip": "iris", "od": 2.0, "do": 3.0},
        {"id": "E2", "tip": "zaluzine", "od": 6.0, "do": 8.0, "parametri": {"trajanje": 1.2}},   # alias rolete
        {"id": "E3", "tip": "vrata", "od": 4.0, "do": 5.0},
    ]}
    fx, notes = efekti.plan(edit, CUTS, 30, 5.4)
    assert [x["id"] for x in fx] == ["E1", "E2"]
    a, b = fx
    assert a["tip"] == "iris" and a["t"] == 2.0 and abs((a["s"] + a["e"]) / 2 - 2.0) < 1e-9
    assert a["n"] == 18 and abs(a["p"]["trajanje"] - 0.6) < 1e-9
    assert abs(a["a_src"] - (2.0 - 0.3)) < 1e-9 and abs(a["b_src"] - (3.0 - 0.3)) < 1e-9   # ručke
    # kadar iza reza traje 0,4 s: prijelaz se skrati da ne dira prethodni rez
    assert b["tip"] == "rolete" and b["e"] - 5.0 <= 0.4 * 0.45 + 1e-9 and b["n"] % 2 == 0
    assert any("E2" in n and "skraćen" in n for n in notes)
    assert any("E3" in n and "više nema" in n for n in notes)
    assert efekti.kamera_spans(fx) == [] and efekti.video_chain(fx, 540, 960, 30) == []
    for x in fx:
        assert abs(x["s"] * 30 - round(x["s"] * 30)) < 1e-6


def test_maske_iris_i_rolete():
    x = {"id": "E1", "tip": "iris", "n": 12, "p": {"lice": {"x": 0.3, "y": 0.4, "h": 0.2}}}
    W, H = 200, 360
    assert prijelazi.maska(x, 0, W, H).max() == 0           # prva sličica: samo stari kadar
    assert prijelazi.maska(x, 11, W, H).min() == 255        # zadnja: samo novi
    m = prijelazi.maska(x, 5, W, H)
    assert m[int(0.4 * H), int(0.3 * W)] == 255 and m[H - 1, W - 1] == 0   # krug oko lica
    r = dict(x, tip="rolete")
    m = prijelazi.maska(r, 5, W, H)
    h = H / prijelazi.ROLETE
    assert m[1, 5] == 255 and m[int(h) - 2, 5] == 0 and m[int(h) + 1, 5] == 255   # svaka traka odozgo
    assert (m == m[:, :1]).all()                            # vodoravne trake


def test_ugradeni_prijelazi_postoje_u_ffmpegu():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=xfade"], capture_output=True, text=True).stdout
    names = set(re.findall(r"^\s+(\w+)\s+-?\d+\s", out, re.M))
    for tip, T in prijelazi.TIPOVI.items():
        for sm in (prijelazi.SMJEROVI if T.get("smjer") else [None]):
            n = prijelazi.xfade_name({"tip": tip, "p": {"smjer": sm}})
            assert n is None or n in names, (tip, sm, n)


def test_graf_ulazi_se_poklapaju():
    px = [{"id": "E1", "tip": "brisanje", "s": 1.0, "e": 1.4, "t": 1.2, "n": 12, "a_src": 2.0, "b_src": 3.0,
           "p": {"smjer": "desno"}},
          {"id": "E2", "tip": "iris", "s": 3.0, "e": 3.6, "t": 3.3, "n": 18, "a_src": 5.0, "b_src": 7.0, "p": {}},
          {"id": "E3", "tip": "vrata", "s": 5.0, "e": 5.6, "t": 5.3, "n": 18, "a_src": 9.0, "b_src": 11.0, "p": {}}]
    # jedan prijelaz = svoja mala naredba (2 komada snimke, iris i maska)
    assert prijelazi.ulazi(px[:1], "source.mp4", 0.0, 30).count("-i") == 2
    assert prijelazi.ulazi(px[1:2], "source.mp4", 0.0, 30).count("-i") == 3
    one = ";".join(prijelazi._spoj(px[0], 0, 1, 2, 30, "null", None, None, 0, 540))
    assert "wiperight" in one and one.endswith("[px0]")
    assert "alphamerge" in ";".join(prijelazi._spoj(px[1], 0, 1, 2, 30, "null", None, None, 0, 540))
    # glavni prolaz: svi prijelazi kao JEDAN ulaz i jedan overlay (RAM ne raste s brojem prijelaza)
    g = ";".join(prijelazi.graf(px, 4, "[v1]", "[v1p]", 30))
    assert re.findall(r"\[(\d+):v\]", g) == ["4"] and g.count("overlay=") == 1 and g.endswith("[v1p]")


def _vrijeme(px, N, fps=30):
    """Vrijednost setpts izraza za sličicu N (bez ffmpega)."""
    expr = prijelazi.vremena_expr(px, fps)
    expr = re.sub(r"between\(N,(\d+),(\d+)\)", lambda m: str(int(int(m[1]) <= N <= int(m[2]))), expr)
    return eval(expr.replace("N", str(N)))  # noqa: S307 (naš izraz: brojevi, + - * /)


@pytest.mark.parametrize("pola", [0.0, 0.5])
def test_sličica_komada_uz_svaku_sličicu_glavne_trake(pola):
    """Overlay uzme zadnju sličicu komada koja nije poslije sličice glavne trake. Za svaku sličicu glavne
    trake u prozoru to mora biti prava sličica prijelaza (j = 0 … n-1, svaka jednom), i kad rez nije
    točno na sličici; isto pravilo vrijedi za --kadar (sl_indeks)."""
    fps = 30
    px = [{"s": (30 + pola) / fps, "e": (30 + pola + 12) / fps, "n": 12},
          {"s": (60 + pola) / fps, "e": (60 + pola + 18) / fps, "n": 18}]
    ts = [_vrijeme(px, N) for N in range(30)]
    d = prijelazi.POMAK / fps
    for k, x in enumerate(px):
        c = 0 if k == 0 else 12
        mine = [m for m in range(120) if x["s"] - d <= m / fps <= x["e"] - d - 1e-4]
        assert len(mine) == x["n"]
        got = []
        for m in mine:
            j = max(i for i, t in enumerate(ts) if t <= m / fps + 1e-9) - c   # overlay: zadnja ≤ t
            got.append(j)
            assert j == prijelazi.sl_indeks(x, m / fps, fps)
        assert got == list(range(x["n"]))


# ---------------------------------------------------------------- pravi render
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_prijelazi_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("prijelazi čž"), SCRIPTS)
    run("render.py", proj, "--izlaz", "ref.mp4")
    return proj


def frames(path, w=270, h=480):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3)


def audio_len(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())


def prizor(px):
    """Koji prizor probnog klipa je na pikselu pozadine (BGR): 1 crveni, 2 plavi, 3 zeleni."""
    b, g, r = (int(v) for v in px)
    if r > 150 and b < 110:
        return 1
    if b > 150 and r < 110:
        return 2
    if g > 130 and r < 110 and b < 110:
        return 3
    return 0


def test_cijeli_put(projekt):
    rz = run("efekti.py", projekt, "rezovi").stdout
    assert re.search(r"R1\s+00:02\.\d\d\s+….* \| .*…", rz) and "R2" in rz and "  R3 " not in rz
    out = run("efekti.py", projekt, "dodaj", "brisanje", "R1", "--smjer", "lijevo", "--trajanje", "0.6").stdout
    assert "Dodan E1: prijelaz brisanje" in out
    t2 = float(re.search(r"R2\s+00:(\d\d\.\d\d)", rz).group(1))
    out = run("efekti.py", projekt, "dodaj", "krug", f"0:{t2 + 0.4:05.2f}").stdout       # najbliži rez, alias
    assert "Dodan E2: prijelaz iris oko lica" in out
    # greške: isti rez, daleko od reza, smjer uz iris, trajanje uz zum
    r = run("efekti.py", projekt, "dodaj", "vrata", "R1", ok=False)
    assert r.returncode != 0 and "E1" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "vrata", "0:00.5", ok=False)
    assert r.returncode != 0 and "nema reza" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "iris", "R2", "--smjer", "gore", "--zamijeni", ok=False)
    assert r.returncode != 0 and "smjer" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "trzaj", "1-2", "--trajanje", "1", ok=False)
    assert r.returncode != 0 and "prijelaz" in r.stderr
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert [e["tip"] for e in edit["efekti"]] == ["brisanje", "iris"]
    assert edit["efekti"][1]["parametri"].get("lice")
    popis = run("efekti.py", projekt, "popis").stdout
    assert "prijelaz na rezu" in popis and "oko lica" in popis and "lijevo" in popis
    assert "[E1 brisanje]" in run("efekti.py", projekt, "rezovi").stdout

    out = run("render.py", projekt, "--izlaz", "px.mp4").stdout
    assert "Efekti: 2" in out
    ref, fx = frames(projekt / "ref.mp4"), frames(projekt / "px.mp4")
    assert len(ref) == len(fx)                                   # prijelaz ne mijenja trajanje
    assert abs(audio_len(projekt / "ref.mp4") - audio_len(projekt / "px.mp4")) < 0.03

    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    import render
    pj = json.loads((projekt / "project.json").read_text(encoding="utf-8"))
    words = json.loads((projekt / "transcript.json").read_text(encoding="utf-8"))["words"]
    cuts, _, total = render.build_cuts(words, edit, render.resolve_style(edit), 30, pj["duration"])
    p, _ = efekti.plan(edit, cuts, 30, total)
    w1, w2 = p
    fr = lambda t: int(round(t * 30))  # noqa: E731
    # izvan prijelaza: isto kao bez njih
    for t in (0.5, (w1["e"] + w2["s"]) / 2, total - 0.3):
        assert np.abs(ref[fr(t)].astype(int) - fx[fr(t)].astype(int)).mean() < 3, t
    # brisanje usred: jedna strana kadra je stari prizor (1), druga novi (2)
    m = fx[fr(w1["t"])]
    left, right = prizor(m[50, 8]), prizor(m[50, 262])
    assert {left, right} == {1, 2}, (m[50, 8], m[50, 262])
    assert prizor(ref[fr(w1["t"]) - 1][50, 8]) == 1 and prizor(ref[fr(w1["t"])][50, 8]) == 2
    # malo prije sredine: već se vidi dio novog prizora (ručka kadra B iz snimke prije reza)
    q = fx[fr(w1["s"]) + 4]
    assert {1, 2} <= {prizor(q[50, x]) for x in range(4, 270, 22)}
    # iris usred: krug novog prizora (3) oko lica, u dalekom kutu još stari (2)
    m = fx[fr(w2["t"])]
    lx, ly = w2["p"]["lice"]["x"], w2["p"]["lice"]["y"]
    assert prizor(m[max(5, int(ly * 480) - 70), int(lx * 270)]) == 3
    far = (470, 262) if lx < 0.5 else (470, 8)
    assert prizor(m[far]) == 2, m[far]
    # na kraju prijelaza samo novi prizor
    assert prizor(fx[fr(w2["e"]) - 1][far]) == 3

    # --kadar usred prijelaza = sličica iz videa
    import cv2
    tm = w1["t"] + 1 / 30
    run("render.py", projekt, "--kadar", f"{tm:.4f}")
    png = next(projekt.glob("kadar_1_*.png"))
    img = cv2.imdecode(np.fromfile(str(png), np.uint8), cv2.IMREAD_COLOR)
    img = cv2.resize(img, (270, 480), interpolation=cv2.INTER_AREA)
    assert np.abs(img.astype(int) - fx[fr(tm)].astype(int)).mean() < 6

    out = run("efekti.py", projekt, "pokazi", "E2").stdout
    assert (projekt / "efekt_E2.png").stat().st_size > 10_000 and "iris" in out


def test_vrata_rolete_zamah_i_izmjene(projekt):
    run("efekti.py", projekt, "dodaj", "vrata", "R1", "--zamijeni")
    run("efekti.py", projekt, "dodaj", "rolete", "R2", "--zamijeni", "--trajanje", "0.8")
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert sorted(e["tip"] for e in edit["efekti"]) == ["rolete", "vrata"]
    run("render.py", projekt, "--izlaz", "px2.mp4")
    ref, fx = frames(projekt / "ref.mp4"), frames(projekt / "px2.mp4")
    assert len(ref) == len(fx)
    run("efekti.py", projekt, "dodaj", "zamah", "R1", "--zamijeni", "--smjer", "gore")
    run("render.py", projekt, "--izlaz", "px3.mp4")
    assert len(frames(projekt / "px3.mp4")) == len(ref)
    # rez prije prijelaza: prijelaz ostaje na istom rezu (vremena snimke), samo ranije u videu
    before = run("efekti.py", projekt, "popis").stdout
    run("uredi.py", projekt, "makni", "0:00.3-0:00.9", "--trenutno")
    after = run("efekti.py", projekt, "popis").stdout
    t0 = float(re.search(r"rezu 00:(\d\d\.\d\d)", before).group(1))
    t1 = float(re.search(r"rezu 00:(\d\d\.\d\d)", after).group(1))
    assert 0.3 < t0 - t1 < 0.9 and after.count("prijelaz na rezu") == 2
    run("uredi.py", projekt, "vrati")
    run("efekti.py", projekt, "makni", "sve")
    assert not json.loads((projekt / "edit.json").read_text(encoding="utf-8"))["efekti"]


def test_pripremljeni_komadi_jedan_ulaz_i_predmemorija(projekt):
    """M5.2c: svaki prijelaz se renderira zasebno u _tmp/prijelaz_*.mp4 (točno n sličica), glavni prolaz ih
    čita kao jedan ulaz; nepromijenjen prijelaz se ne renderira ponovno, maknut se briše."""
    run("efekti.py", projekt, "makni", "sve", ok=False)
    run("efekti.py", projekt, "dodaj", "iris", "R1")
    run("efekti.py", projekt, "dodaj", "brisanje", "R2")
    out = run("render.py", projekt, "--izlaz", "c1.mp4").stdout
    assert "pripremljeno 2 od 2" in out
    tmp = projekt / "_tmp"
    komadi = sorted(tmp.glob("prijelaz_*.mp4"))
    assert len(komadi) == 2
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    import render
    pj = json.loads((projekt / "project.json").read_text(encoding="utf-8"))
    words = json.loads((projekt / "transcript.json").read_text(encoding="utf-8"))["words"]
    cuts, _, total = render.build_cuts(words, edit, render.resolve_style(edit), 30, pj["duration"])
    p, _ = efekti.plan(edit, cuts, 30, total)
    lst = (tmp / "prijelazi.ffconcat").read_text(encoding="utf-8")
    for x in p:  # svaki komad ima točno n sličica
        name = re.findall(r"file '([^']+)'", lst)[p.index(x)]
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(tmp / name)], capture_output=True, text=True)
        assert int(r.stdout.strip()) == x["n"]
    graf = (tmp / "graf.txt").read_text(encoding="utf-8")
    assert graf.count("overlay=0:0:eof_action=pass:repeatlast=0") == 1 and "xfade" not in graf
    assert not list(tmp.glob("maska_*.png"))                  # maske su obrisane nakon pripreme
    mt = {k.name: k.stat().st_mtime_ns for k in komadi}
    out = run("render.py", projekt, "--izlaz", "c2.mp4").stdout
    assert "pripremljeno" not in out                          # ništa novo: isti komadi
    assert {k.name: k.stat().st_mtime_ns for k in tmp.glob("prijelaz_*.mp4")} == mt
    assert np.abs(frames(projekt / "c1.mp4").astype(int) - frames(projekt / "c2.mp4").astype(int)).max() == 0
    run("efekti.py", projekt, "dodaj", "rolete", "R2", "--zamijeni")
    out = run("render.py", projekt, "--izlaz", "c3.mp4").stdout
    assert "pripremljeno 1 od 2" in out                       # samo promijenjeni
    novi = {k.name for k in tmp.glob("prijelaz_*.mp4")}
    assert len(novi) == 2 and len(novi & set(mt)) == 1        # stari komad brisanja je maknut
    run("efekti.py", projekt, "makni", "sve")
