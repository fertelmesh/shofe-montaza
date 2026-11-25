"""Testovi cijelog lanca na probnim snimkama (sintetski hrvatski govor, poznata vremena riječi).

Pokretanje:  python -m pytest tests -q
Treba: ffmpeg u PATH-u. Transkripcija se ovdje NE pokreće (mock transkript), vidi test_transcribe_smoke.py.
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


def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r.stdout


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    base = tmp_path_factory.mktemp("shofe test čćž Markov's")  # razmak, dijakritici, apostrof
    clips = base / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    proj = base / "shofe_projekt"
    run("prepare.py", clips, "--out", proj)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    mock = json.loads((FIX / "mock_words.json").read_text(encoding="utf-8"))
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                     ensure_ascii=False), encoding="utf-8")
    run("plan.py", proj, "--stil", "suncani")
    return proj


def test_prepare(projekt):
    pj = json.loads((projekt / "project.json").read_text(encoding="utf-8"))
    assert (pj["width"], pj["height"], pj["fps"]) == (1080, 1920, 30)
    assert len(pj["clips"]) == 2
    v = next(s for s in probe(projekt / "source.mp4")["streams"] if s["codec_type"] == "video")
    assert (int(v["width"]), int(v["height"])) == (1080, 1920)


def test_plan_finds_retake_and_filler(projekt):
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    dropped = {s["id"]: s.get("napomena", "") for s in edit["odsjecci"] if not s["zadrzi"]}
    assert 2 in dropped and "ponovljeno" in dropped[2]  # "Danas vam pokazujem kako" (prekinut pokušaj)
    assert 4 in dropped                                  # "eee"
    assert len(edit["odsjecci"]) == 7


def test_render_full(projekt):
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    edit["hook"] = "Klima smrdi? Očisti je sam"
    edit["naglasi"] = ["klimu", "filter"]
    edit["glazba"] = str(FIX / "glazba.mp3")
    (projekt / "edit.json").write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
    out = run("render.py", projekt, "--izlaz", "test_reel.mp4")
    assert "Gotovo" in out
    d = probe(projekt / "test_reel.mp4")
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next(s for s in d["streams"] if s["codec_type"] == "audio")
    vd, ad = float(v["duration"]), float(a["duration"])
    assert 13.0 < vd < 16.5, vd
    assert abs(vd - ad) < 0.15, (vd, ad)   # zvuk i slika usklađeni
    ass = (projekt / "captions.ass").read_text(encoding="utf-8")
    assert "OČISTI" in ass and "KLIMU" in ass


@pytest.mark.parametrize("stil", ["suncani", "podcast", "udarno", "cisto", "kino"])
def test_styles_still(projekt, stil):
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    edit["stil"] = stil
    (projekt / "edit.json").write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
    run("render.py", projekt, "--kadar", "1.2")
    assert (projekt / "kadar_1_1.2s.png").stat().st_size > 10_000


def test_build_cuts_frame_exact():
    from render import build_cuts
    words = [{"w": "a", "s": 1.0, "e": 1.4}, {"w": "b", "s": 1.45, "e": 1.9}, {"w": "eee", "s": 2.5, "e": 2.8},
             {"w": "c", "s": 3.5, "e": 3.9}]
    edit = {"odsjecci": [{"od": 1.0, "do": 1.9, "tekst": "a b", "zadrzi": True},
                         {"od": 2.5, "do": 2.8, "tekst": "eee", "zadrzi": False},
                         {"od": 3.5, "do": 3.9, "tekst": "c", "zadrzi": True}]}
    cuts, kept, total = build_cuts(words, edit, {"rezanje": [0.05, 0.1]}, 30, 5.0)
    assert len(cuts) == 2
    for c in cuts:  # granice na mreži sličica
        assert abs(c["a"] * 30 - round(c["a"] * 30)) < 1e-6 and abs(c["b"] * 30 - round(c["b"] * 30)) < 1e-6
    assert [w for w, _ in kept] == [0, 1, 3]
