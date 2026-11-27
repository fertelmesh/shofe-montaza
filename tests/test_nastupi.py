"""M4.3a: nastupi bendova — pjesma se pronađe i nikad ne reže iznutra (plan, render, uredi, isječci).

Logika se testira bez modela (izmišljene vjerojatnosti / ručni nastupi.json). Pravi model (CED-tiny, ~29 MB
s GitHuba) pokreće se kad je SHOFE_GOVORNICI_TEST=1 ili je model već skinut.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import nastupi as NA  # noqa: E402
import render  # noqa: E402
import make_nastup as MN  # noqa: E402


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


# ---------------------------------------------------------------- od vjerojatnosti do pjesama

def _P(parts, n):
    """parts: [(od, do, govor, glazba, pjevanje, pljesak)] po sekundi → (n, 4)."""
    P = np.zeros((n, 4), np.float32)
    P[:, 0] = 0.8
    for a, b, g, m, s, c in parts:
        P[a:b] = (g, m, s, c)
    return P


def test_pjesma_radio_dzingl():
    # 0–20 govor, 20–70 pjesma (s 4 s tišeg dijela), 70–90 govor uz radio, 90–100 džingl, 100–120 govor
    P = _P([(20, 45, 0.02, 0.9, 0.5, 0), (45, 49, 0.1, 0.4, 0, 0), (49, 70, 0.02, 0.9, 0.5, 0),
            (70, 90, 0.75, 0.65, 0, 0), (90, 100, 0.0, 0.9, 0, 0)], 117)
    songs = NA.find_songs(P, 120.0, korak=1.0, prozor=4.0)
    assert len(songs) == 1
    s = songs[0]
    assert abs(s["od"] - 21.5) < 1.5 and abs(s["do"] - 71.5) < 1.5
    assert s["pjevanje"] and not s["pljesak"] and s["sigurnost"] > 0.7


def test_pauza_u_pjesmi_spaja_a_duga_dijeli():
    P = _P([(10, 50, 0, 0.9, 0, 0), (54, 94, 0, 0.9, 0, 0)], 130)   # 4 s govora između → ista pjesma
    assert len(NA.find_songs(P, 133.0)) == 1
    P = _P([(10, 50, 0, 0.9, 0, 0), (70, 110, 0, 0.9, 0, 0)], 130)  # 20 s razgovora → dvije pjesme
    assert len(NA.find_songs(P, 133.0)) == 2


def test_pljesak_ide_uz_pjesmu():
    P = _P([(10, 50, 0, 0.9, 0, 0), (50, 56, 0.1, 0.05, 0, 0.8)], 80)
    s = NA.find_songs(P, 83.0)[0]
    assert s["pljesak"] and s["do"] >= 57.0


def test_rub_nije_usred_rijeci():
    words = [{"w": "svirao", "s": 18.4, "e": 19.7}, {"w": "a", "s": 69.0, "e": 69.4},
             {"w": "susjedi", "s": 69.5, "e": 70.2}]
    od, do = NA.snap_to_words(19.6, 69.2, words, 130.0, pre=0.5, post=1.0)
    assert od == 19.7            # „svirao" ostaje izvan pjesme, razmak ne ide preko govora
    assert do == 69.0            # „a" je iza pjesme, kraj ne ulazi u govor
    od, do = NA.snap_to_words(30.0, 60.0, [], 130.0)
    assert (od, do) == (29.5, 61.0)


def test_rucne_izmjene_prezive_novu_analizu():
    old = {"nastupi": [
        {"id": "P1", "od": 10.0, "do": 60.0, "izvor": "auto", "naziv": "Bend – Kutina"},
        {"od": 100.0, "do": 140.0, "izvor": "rucno"},
        {"od": 200.0, "do": 240.0, "izvor": "rucno", "odbijeno": True},
    ]}
    found = [{"od": 11.0, "do": 61.0, "sigurnost": 0.9}, {"od": 101.0, "do": 139.0, "sigurnost": 0.8},
             {"od": 200.5, "do": 239.0, "sigurnost": 0.6}, {"od": 300.0, "do": 340.0, "sigurnost": 0.7}]
    res = NA.merge_detection(old, found)
    act = NA.active({"nastupi": res})
    assert [(n["id"], n["od"]) for n in act] == [("P1", 11.0), ("P2", 100.0), ("P3", 300.0)]
    assert act[0]["naziv"] == "Bend – Kutina"     # naziv prelazi na novu granicu
    assert sum(1 for n in res if n.get("odbijeno")) == 1   # odbijena se ne vraća


def test_edit_pamti_izbacenu_pjesmu():
    data = {"nastupi": [{"id": "P1", "od": 10.0, "do": 60.0}, {"id": "P2", "od": 100.0, "do": 150.0}]}
    edit = {"nastupi": [{"id": "P1", "od": 10.0, "do": 60.0, "zadrzi": False, "titlovi": False}]}
    assert NA.apply_to_edit(edit, data)
    assert [(n["id"], n["zadrzi"]) for n in edit["nastupi"]] == [("P1", False), ("P2", True)]
    assert not NA.apply_to_edit(edit, data)
    NA.apply_to_edit(edit, {"nastupi": []})
    assert "nastupi" not in edit


# ---------------------------------------------------------------- render: rezovi i zvuk

def _edit(words, nastupi=None, izrezi=None):
    segs = [{"id": i + 1, "od": w["s"], "do": w["e"], "tekst": w["w"], "zadrzi": True} for i, w in enumerate(words)]
    e = {"stil": "podcast", "odsjecci": segs}
    if nastupi is not None:
        e["nastupi"] = nastupi
    if izrezi:
        e["izrezi"] = izrezi
    return e


WORDS = [{"w": "prije", "s": 1.0, "e": 1.5}, {"w": "pjesme.", "s": 1.6, "e": 2.0},
         {"w": "la", "s": 5.0, "e": 5.3}, {"w": "ljubavi", "s": 20.0, "e": 20.6},
         {"w": "poslije", "s": 40.0, "e": 40.5}, {"w": "pjesme.", "s": 40.6, "e": 41.0}]


def test_pjesma_ide_cijela_bez_titlova():
    st = render.resolve_style({"stil": "podcast"})
    cuts, kept, total = render.build_cuts(WORDS, _edit(WORDS), st, 30, 45.0)
    assert total < 6  # bez pjesme: samo riječi
    song = [{"id": "P1", "od": 3.0, "do": 35.0, "zadrzi": True, "titlovi": False}]
    cuts, kept, total = render.build_cuts(WORDS, _edit(WORDS, song), st, 30, 45.0)
    assert any(c["a"] <= 3.0 + 1 / 30 and c["b"] >= 35.0 - 1 / 30 for c in cuts)   # jedan komad, i bez riječi
    assert {k[0] for k in kept} == {0, 1, 4, 5}                                     # riječi pjesme bez titlova
    assert render.song_out_spans(_edit(WORDS, song), cuts)[0][1] - render.song_out_spans(_edit(WORDS, song), cuts)[0][0] > 31.9
    song[0]["titlovi"] = True
    _, kept, _ = render.build_cuts(WORDS, _edit(WORDS, song), st, 30, 45.0)
    assert {k[0] for k in kept} == {0, 1, 2, 3, 4, 5}
    song[0].update(zadrzi=False, titlovi=False)
    cuts, kept, total = render.build_cuts(WORDS, _edit(WORDS, song), st, 30, 45.0)
    assert {k[0] for k in kept} == {0, 1, 4, 5} and total < 6
    assert not any(c["a"] < 20.0 < c["b"] for c in cuts)


def test_izrez_ne_dira_pjesmu_osim_izricitog():
    st = render.resolve_style({"stil": "podcast"})
    song = [{"id": "P1", "od": 3.0, "do": 35.0, "zadrzi": True}]
    iz = [{"od": 10.0, "do": 15.0, "n": 1}]
    cuts, _, total = render.build_cuts(WORDS, _edit(WORDS, song, iz), st, 30, 45.0)
    assert total > 33
    iz[0]["u_pjesmi"] = True
    cuts, _, total2 = render.build_cuts(WORDS, _edit(WORDS, song, iz), st, 30, 45.0)
    assert abs((total - total2) - 5.0) < 0.1


def test_izraz_glasnoce_pjesme():
    assert render.song_gain_expr([]) == ""
    ex = render.song_gain_expr([(2.0, 10.0), (20.0, 30.0)])
    t = 5.0
    val = eval(ex.replace("clip", "_c"), {"_c": lambda x, a, b: max(a, min(b, x)), "t": t})  # noqa: S307
    assert val == 1.0
    for t, want in ((1.0, 0.0), (2.125, 0.5), (15.0, 0.0), (29.9, 0.4)):
        val = eval(ex.replace("clip", "_c"), {"_c": lambda x, a, b: max(a, min(b, x)), "t": t})  # noqa: S307
        assert abs(val - want) < 1e-6, (t, val)


# ---------------------------------------------------------------- uredi.py s pjesmom (bez modela)

@pytest.fixture(scope="module")
def epizoda(tmp_path_factory):
    base = tmp_path_factory.mktemp("nastup čž")
    proj = MN.make(base / "epizoda")
    save(proj / "nastupi.json", {"nastupi": [{"id": "P1", "od": 19.74, "do": 68.75, "izvor": "auto",
                                              "sigurnost": 0.85}]})
    run("plan.py", proj, "--stil", "podcast")
    return proj


def _proj(epizoda, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizoda, p)
    return p


def test_plan_upisuje_pjesmu(epizoda):
    e = load(epizoda / "edit.json")
    assert e["nastupi"] == [{"id": "P1", "od": 19.74, "do": 68.75, "zadrzi": True, "titlovi": False}]
    txt = (epizoda / "transcript.txt").read_text(encoding="utf-8")
    assert "PJESMA" in txt and "[u pjesmi P1]" in txt


def test_uredi_ne_reze_unutar_pjesme(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    r = run("uredi.py", p, "makni", "0:30-0:40", "--trenutno", ok=False)
    assert r.returncode != 0 and "ne reže iznutra" in r.stdout + r.stderr
    before = load(p / "edit.json")
    # dio s govorom i komadom pjesme: govor van, pjesma ostaje cijela
    r = run("uredi.py", p, "makni", "0:12-0:20", "--trenutno")
    assert "ostaje cijela" in r.stdout
    e = load(p / "edit.json")
    assert e["nastupi"][0]["zadrzi"] and all(not x.get("u_pjesmi") for x in e["izrezi"])
    assert before != e
    words = load(p / "transcript.json")["words"]
    cuts, _, _ = render.build_cuts(words, e, render.resolve_style(e), 30, 131.0)
    assert any(c["a"] <= 19.74 + 0.04 and c["b"] >= 68.75 - 0.04 for c in cuts)   # pjesma i dalje u komadu
    assert not any(c["a"] < 15.0 < c["b"] for c in cuts)                            # govor prije nje je van


def test_uredi_cijela_pjesma(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    run("uredi.py", p, "makni", "--nastup", "P1")
    assert load(p / "edit.json")["nastupi"][0]["zadrzi"] is False
    r = run("uredi.py", p, "popis", "--trenutno")
    assert "izbačena pjesma P1" in r.stdout and "PJESMA P1" not in r.stdout
    run("uredi.py", p, "dodaj", "--nastup", "P1")
    assert load(p / "edit.json")["nastupi"][0]["zadrzi"] is True
    # vremenski dio koji pokriva cijelu pjesmu makne je cijelu
    r = run("uredi.py", p, "popis", "--trenutno")
    line = next(x for x in r.stdout.splitlines() if "PJESMA P1" in x)
    od, do = line.split()[0].split("-")
    run("uredi.py", p, "makni", f"{od}-{do}", "--trenutno")
    assert load(p / "edit.json")["nastupi"][0]["zadrzi"] is False
    run("uredi.py", p, "vrati")
    assert load(p / "edit.json")["nastupi"][0]["zadrzi"] is True


def test_uredi_zadrzi_samo_pjesmu_i_izricit_rez(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    run("uredi.py", p, "zadrzi", "--nastup", "P1")
    from uredi import timeline
    e = load(p / "edit.json")
    tl, dur = timeline(load(p / "transcript.json")["words"], e, load(p / "project.json"))
    assert not tl and 48.0 < dur < 49.5          # samo pjesma, bez govora
    run("uredi.py", p, "vrati")
    run("uredi.py", p, "makni", "0:30-0:35", "--trenutno", "--u-pjesmi")
    iz = [x for x in load(p / "edit.json")["izrezi"] if x.get("u_pjesmi")]
    assert len(iz) == 1 and abs((iz[0]["do"] - iz[0]["od"]) - 5.0) < 0.1


def test_skrati_cuva_pjesmu(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    r = run("uredi.py", p, "skrati", "40", "--trenutno", ok=False)
    assert r.returncode != 0 and "same pjesme" in r.stdout + r.stderr
    r = run("uredi.py", p, "skrati", "80", "--trenutno")
    assert "ostaju cijele" in r.stdout
    e = load(p / "edit.json")
    assert e["nastupi"][0]["zadrzi"] and not any(x.get("u_pjesmi") for x in e.get("izrezi", []))


def test_isjecci_ne_idu_preko_pjesme(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    run("isjecci.py", p, "predlozi", "--min", "8", "--max", "30", ok=False)  # 1 = Claude još ocjenjuje
    for c in load(p / "isjecci.json")["isjecci"]:
        assert c["do"] <= 19.74 + 0.01 or c["od"] >= 68.75 - 0.01, c


def test_nastupi_rucno(epizoda, tmp_path):
    p = _proj(epizoda, tmp_path)
    run("nastupi.py", p, "naziv", "P1", "Bend", "–", "Kutina")
    run("nastupi.py", p, "dodaj", "1:50-2:05")
    d = load(p / "nastupi.json")
    assert [n["id"] for n in NA.active(d)] == ["P1", "P2"]
    assert load(p / "edit.json")["nastupi"][0]["naziv"] == "Bend – Kutina"   # edit.json se osvježi
    run("nastupi.py", p, "granice", "P2", "1:52-2:04")
    run("nastupi.py", p, "makni", "P2")
    assert len(load(p / "edit.json")["nastupi"]) == 1
    assert "nije pjesma" in run("nastupi.py", p, "popis").stdout
    assert (p / "nastupi.png").exists()


def test_render_pjesma_u_komadu(epizoda, tmp_path):
    """Gotovi video: zeleni kadar pjesme bez prekida, zvuk pjesme kroz glazbeni lanac, bez titlova pjesme."""
    p = _proj(epizoda, tmp_path)
    e = load(p / "edit.json")
    e["glazba"] = str(ROOT / "tests" / "fixtures" / "glazba.mp3")
    save(p / "edit.json", e)
    run("render.py", p)
    graf = (p / "_tmp" / "graf.txt").read_text(encoding="utf-8")
    assert render.MUSIC_CHAIN in graf and graf.count("eval=frame") == 3   # govor, pjesma, pozadinska glazba
    srt = (p / "reel_v1.srt").read_text(encoding="utf-8")
    assert "ljubavi" not in srt and "Ja sam tada svirao" in srt
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p / "reel_v1.mp4"), "-vf", "crop=20:20:240:120,scale=1:1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    px = np.frombuffer(r.stdout, np.uint8).reshape(-1, 3).astype(int)
    green = (px[:, 1] > 120) & (px[:, 2] < 110)
    runs, cur = [], 0
    for g in green:
        cur = cur + 1 if g else 0
        runs.append(cur)
    assert max(runs) / 30.0 > 47.5   # pjesma (20–68 s izvora) u jednom komadu


# ---------------------------------------------------------------- pravi model

def _model_ready():
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("SHOFE_GOVORNICI_TEST") == "1":
        return True
    import govornici as G
    return (G.models_dir() / NA.MODEL).exists()


@pytest.mark.skipif(not _model_ready(), reason="model za glazbu nije skinut (postavi SHOFE_GOVORNICI_TEST=1)")
def test_pravi_model_nalazi_pjesmu(tmp_path):
    proj = MN.make(tmp_path / "epizoda")
    r = run("nastupi.py", proj)
    d = load(proj / "nastupi.json")
    act = NA.active(d)
    assert len(act) == 1, r.stdout   # radio ispod govora i džingl od 10 s nisu pjesme
    s = act[0]
    assert 18.9 <= s["od"] <= 20.3 and 67.5 <= s["do"] <= 71.5, s
    assert s["od"] >= 19.74 - 0.01    # zadnja riječ prije pjesme („svirao" do 19,74) ostaje izvan
    assert len(d["krivulja"]["glazba"]) > 100
