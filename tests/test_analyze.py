"""Testovi karte videa (analyze.py).

Sintetski video s poznatim događajima (generira se ffmpegom, ~13 s, 320x180):
  0–3 s testsrc2 | 3–6 s trake (rez u 3.0) | 6–9 s testsrc2 (rez u 6.0), 7–8 s jako zamućen
  9–11 s skoro crno (tamno) | 11–13 s testsrc2
  zvuk: ton, tišine 4.0–5.5 s i 10.0–11.0 s
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def near(a, b, tol):
    return abs(a - b) <= tol


@pytest.fixture(scope="module")
def sint(tmp_path_factory):
    proj = tmp_path_factory.mktemp("analiza čćž") / "moj projekt"
    proj.mkdir()
    src = lambda kind, d: ["-f", "lavfi", "-i", f"{kind}=s=320x180:r=30:d={d}"]
    cmd = ["ffmpeg", "-y", "-v", "error",
           *src("testsrc2", 3), *src("smptehdbars", 3), *src("testsrc2", 1), *src("testsrc2", 1),
           *src("testsrc2", 1), *src("testsrc2", 2), *src("testsrc2", 2),
           "-f", "lavfi", "-i",
           "aevalsrc=0.3*sin(2*PI*440*t)*gt(t\\,0.3)*(1-between(t\\,4\\,5.5))*(1-between(t\\,10\\,11)):s=48000:d=13",
           "-filter_complex",
           "[3:v]boxblur=8:2[b];[5:v]eq=brightness=-0.75[d];"
           "[0:v][1:v][2:v][b][4:v][d][6:v]concat=n=7:v=1:a=0,format=yuv420p[v]",
           "-map", "[v]", "-map", "7:a", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest",
           str(proj / "source.mp4")]
    subprocess.run(cmd, check=True)
    (proj / "project.json").write_text(json.dumps({
        "format": "16:9", "width": 320, "height": 180, "fps": 30, "duration": 13.0,
        "clips": [{"file": "a.mp4", "start": 0.0, "dur": 6.0}, {"file": "b.mp4", "start": 6.0, "dur": 7.0}]}),
        encoding="utf-8")
    run("analyze.py", proj)
    return proj


def load(proj):
    return json.loads((proj / "analiza.json").read_text(encoding="utf-8"))


def test_tisine(sint):
    t = load(sint)["tisine"]
    assert len(t) == 2, t
    assert near(t[0]["od"], 4.0, 0.1) and near(t[0]["do"], 5.5, 0.1)
    assert near(t[1]["od"], 10.0, 0.1) and near(t[1]["do"], 11.0, 0.1)


def test_rezovi_i_kadrovi(sint):
    an = load(sint)
    cuts = an["promjene_scene"]
    for expected in (3.0, 6.0):
        assert any(near(c, expected, 0.1) for c in cuts), cuts
    # nema lažnih rezova usred mirnih dijelova
    assert not any(0.2 < c < 2.8 or 11.2 < c < 12.8 for c in cuts), cuts
    assert an["spojevi_klipova"] == [6.0]
    k = an["kadrovi"]
    assert k[0]["od"] == 0.0 and near(k[-1]["do"], 13.0, 0.05)
    assert all(a["do"] == b["od"] for a, b in zip(k, k[1:]))


def test_losi_kadrovi(sint):
    bad = load(sint)["losi_kadrovi"]
    mutno = [b for b in bad if b["razlog"] == "mutno"]
    tamno = [b for b in bad if b["razlog"] == "tamno"]
    assert len(mutno) == 1 and near(mutno[0]["od"], 7.0, 0.25) and near(mutno[0]["do"], 8.0, 0.25), bad
    assert len(tamno) == 1 and near(tamno[0]["od"], 9.0, 0.1) and near(tamno[0]["do"], 11.0, 0.1), bad
    assert not [b for b in bad if b["razlog"] == "presvijetlo"]


def test_zvuk_i_sazetak(sint):
    an = load(sint)
    z = an["zvuk"]
    assert z["glasnoca_lufs"] is not None and -30 < z["glasnoca_lufs"] < -5
    assert z["prag_tisine_db"] < z["govor_db"]
    # bez transkripta: odsječci = dijelovi sa zvukom
    assert an["govor"] is None and len(an["odsjecci"]) == 3
    txt = (sint / "analiza.txt").read_text(encoding="utf-8")
    assert "KARTA VIDEA" in txt and "tamno" in txt and "mutno" in txt


def test_bez_slike(sint, tmp_path):
    p = tmp_path / "p"
    p.mkdir()
    shutil.copy(sint / "source.mp4", p / "source.mp4")
    run("analyze.py", p, "--bez-slike")
    an = load(p)
    assert an["slika"] is None and an["kadrovi"] == [] and len(an["tisine"]) == 2


# ---- s transkriptom (probne snimke + mock riječi, kao test_pipeline)

@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    base = tmp_path_factory.mktemp("karta s govorom")
    proj = base / "shofe_projekt"
    run("prepare.py", FIX / "klip1.mp4", FIX / "klip2.mp4", "--out", proj)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    mock = json.loads((FIX / "mock_words.json").read_text(encoding="utf-8"))
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                     ensure_ascii=False), encoding="utf-8")
    run("plan.py", proj)
    run("analyze.py", proj)
    return proj


def test_odsjecci_kao_edit(projekt):
    an = load(projekt)
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    assert [(s["id"], s["tekst"]) for s in an["odsjecci"]] == [(s["id"], s["tekst"]) for s in edit["odsjecci"]]
    for s in an["odsjecci"]:
        assert -60 < s["glasnoca_db"] < 0
    g = an["govor"]
    assert 3.0 < g["slogova_u_s"] < 8.0 and g["tempo"] in ("sporo", "normalno", "brzo")
    assert 0.3 < g["udio_govora"] <= 1.0
    assert len(an["spojevi_klipova"]) == 1
    # klip 2 (rešetka) ima manje detalja od klipa 1, ali nije mutan
    assert not [b for b in an["losi_kadrovi"] if b["razlog"] == "mutno"], an["losi_kadrovi"]


def test_claude_dopune_se_cuvaju_i_provjeravaju(projekt):
    p = projekt / "analiza.json"
    an = load(projekt)
    an["teme"] = [{"od": 0.4, "do": 9.3, "naslov": "Uvod i čišćenje klime", "sazetak": "Marko najavljuje temu."}]
    an["trenuci"] = [{"od": 6.4, "do": 9.3, "vrsta": "hook", "ocjena": 4, "opis": "obećanje: očistiti klimu"}]
    p.write_text(json.dumps(an, ensure_ascii=False), encoding="utf-8")
    r = run("analyze.py", projekt, "--provjeri")
    assert "U redu" in r.stdout
    run("analyze.py", projekt, "--bez-slike")      # ponovna analiza čuva Claudeove dopune
    an2 = load(projekt)
    assert an2["teme"] == an["teme"] and an2["trenuci"] == an["trenuci"]
    assert "Uvod i čišćenje klime" in (projekt / "analiza.txt").read_text(encoding="utf-8")
    an2["trenuci"].append({"od": 50, "do": 40, "vrsta": "vic", "opis": ""})
    p.write_text(json.dumps(an2, ensure_ascii=False), encoding="utf-8")
    r = run("analyze.py", projekt, "--provjeri", ok=False)
    assert r.returncode == 1 and "vrsta" in r.stdout and "od" in r.stdout and "opis" in r.stdout


@pytest.mark.parametrize("rijec,slogova", [
    ("Kutine.", 3), ("prst", 1), ("krv", 1), ("trgovina", 4), ("rijeka", 2), ("Hrvatska", 3),
    ("grlo", 2), ("očistiti", 4), ("isključiti", 4), ("je", 1), ("Sunčanom", 3), ("2026", 8)])
def test_slogovi(rijec, slogova):
    from analyze import syllables
    assert syllables(rijec) == slogova


def test_detect_cuts_ignores_motion():
    from analyze import detect_cuts
    # stalno kretanje (~10) bez reza; jedan skok na 60 usred mirnog dijela
    diff = [0.0] + [10.0] * 60 + [1.0] * 30 + [60.0] + [1.0] * 30
    assert detect_cuts(diff, 30) == [round(91 / 30, 2)]
