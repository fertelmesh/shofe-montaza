"""Testovi prepoznavanja govornika (govornici.py) i njihovog ulaska u plan.py i analyze.py.

Probni razgovor tests/fixtures/razgovor.m4a (55 s, 13 rečenica, 3 sintetska glasa, vidi make_dvoglasje.py).
Testovi bez modela koriste točne govornike iz razgovor.json; test s pravim modelom
(sherpa-onnx, ~31 MB s GitHuba) pokreće se kad je SHOFE_GOVORNICI_TEST=1 ili su modeli već skinuti.
"""
import json
import os
import shutil
import subprocess
import sys
from itertools import permutations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import govornici as G  # noqa: E402
from plan import split_segments  # noqa: E402

RAZ = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))


def run(script, *args, ok=True, env=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONUTF8": "1", **(env or {})})
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def truth_segments():
    return [{"od": r["od"], "do": r["do"], "govornik": "G" + str("ABC".index(r["g"]) + 1)}
            for r in RAZ["recenice"]]


def make_project(base, with_video_audio=FIX / "razgovor.m4a"):
    proj = base / "razgovor čćž"
    proj.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=10",
                    "-i", str(with_video_audio), "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(proj / "source.mp4")], check=True)
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": RAZ["words"]},
                                                     ensure_ascii=False), encoding="utf-8")
    return proj


def sentence_accuracy(words):
    """Udio rečenica s točnim govornikom (većina riječi), uz najbolje uparivanje oznaka."""
    labs = []
    for r in RAZ["recenice"]:
        ws = [w["g"] for w in words if r["od"] <= w["s"] <= r["do"]]
        labs.append(max(set(ws), key=ws.count))
    found = sorted(set(labs))
    best = 0
    for p in permutations("ABCDEFG"[:max(3, len(found))], len(found)):
        m = dict(zip(found, p))
        best = max(best, sum(m[x] == r["g"] for x, r in zip(labs, RAZ["recenice"])))
    return best / len(labs), labs


# ---------------------------------------------------------------- bez modela

def test_relabel_po_redu_javljanja():
    segs = G.relabel([(5.0, 6.0, 0), (0.5, 2.0, 3), (2.5, 4.0, 0), (7.0, 8.0, 1)])
    assert [s["govornik"] for s in segs] == ["G1", "G2", "G2", "G3"]
    assert segs[0] == {"od": 0.5, "do": 2.0, "govornik": "G1"}


def test_rijeci_dobiju_govornika_i_otoci_se_izglade():
    segs = [{"od": 0.0, "do": 2.0, "govornik": "G1"}, {"od": 2.0, "do": 2.3, "govornik": "G2"},
            {"od": 2.3, "do": 5.0, "govornik": "G1"}, {"od": 5.2, "do": 8.0, "govornik": "G2"}]
    words = [{"w": f"r{i}", "s": s, "e": s + 0.25} for i, s in enumerate([0.2, 0.8, 2.05, 2.6, 3.5, 5.3, 6.0, 7.0])]
    out = G.assign_words(words, segs)
    # riječ na 2.05 (kratki otok G2 usred G1) ide G1; prava promjena na 5.2 ostaje
    assert [w["g"] for w in out] == ["G1", "G1", "G1", "G1", "G1", "G2", "G2", "G2"]
    assert "g" not in words[0], "ulazne riječi se ne smiju mijenjati"


def test_rijec_u_rupi_ide_najblizem():
    segs = [{"od": 0.0, "do": 1.0, "govornik": "G1"}, {"od": 3.0, "do": 4.0, "govornik": "G2"}]
    out = G.assign_words([{"w": "a", "s": 2.6, "e": 2.8}], segs)
    assert out[0]["g"] == "G2"


def test_odsjecak_ne_prelazi_na_drugog_govornika():
    w = [{"w": "jedan", "s": 0.0, "e": 0.3, "g": "G1"}, {"w": "dva", "s": 0.35, "e": 0.6, "g": "G1"},
         {"w": "tri", "s": 0.65, "e": 0.9, "g": "G2"}, {"w": "četiri", "s": 0.95, "e": 1.2, "g": "G2"}]
    assert split_segments(w, gap=0.3) == [[0, 1], [2, 3]]
    bez = [{k: v for k, v in x.items() if k != "g"} for x in w]
    assert split_segments(bez, gap=0.3) == [[0, 1, 2, 3]]


def test_druga_provjera_prebaci_krivo_grupirani_odsjecak(monkeypatch):
    import numpy as np
    glas = {0: np.array([1.0, 0, 0]), 1: np.array([0, 1.0, 0]), 2: np.array([0, 0, 1.0])}
    # stvarni govornici po vremenu: 0–10 s A, 10–20 B, 20–23 A (kratko pitanje), 23–30 C, 30–40 A
    def stvarni(t):
        return 0 if t < 10 or 20 <= t < 23 or t >= 30 else (1 if t < 20 else 2)
    monkeypatch.setattr(G, "_embedder", lambda m, t: None)
    monkeypatch.setattr(G, "_embed", lambda ex, a, s, e: glas[stvarni((s + e) / 2)] * 0.9 + 0.05)
    raw = [(0, 10, 0), (10, 20, 1), (20, 23, 2), (23, 30, 2), (30, 40, 0), (40, 40.5, 2)]
    out = G.refine(None, raw, "model")
    assert [k for *_, k in out] == [0, 1, 0, 2, 0, 2]  # pitanje vraćeno A-u; prekratki komad ostaje
    assert G.refine(None, [(0, 5, 0), (5, 9, 0)], "model") == [(0, 5, 0), (5, 9, 0)]


def test_imena():
    assert G.parse_names("G1=Marko, 2=Ivan ,g3=Ana") == {"G1": "Marko", "G2": "Ivan", "G3": "Ana"}


def test_plan_i_analiza_s_govornicima(tmp_path):
    proj = make_project(tmp_path)
    segs = truth_segments()
    (proj / "govornici.json").write_text(json.dumps({
        "govornici": G.speaker_stats(segs), "odsjecci": segs}), encoding="utf-8")
    run("govornici.py", proj, "--imena", "G1=Marko,G2=Ana")
    gov = json.loads((proj / "govornici.json").read_text(encoding="utf-8"))
    assert {g["id"]: g["ime"] for g in gov["govornici"]} == {"G1": "Marko", "G2": "Ana", "G3": ""}

    run("plan.py", proj)
    edit = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    for s in edit["odsjecci"]:
        # svaki odsječak ima jednog govornika i on je točan za sve njegove riječi
        rec = [r for r in RAZ["recenice"] if r["od"] - 0.01 <= s["od"] and s["do"] <= r["do"] + 0.01]
        assert len(rec) == 1, s
        assert s["govornik"] == "G" + str("ABC".index(rec[0]["g"]) + 1)
    txt = (proj / "transcript.txt").read_text(encoding="utf-8")
    assert "Marko: Bok svima" in txt and "Ana: Hvala na pozivu" in txt and "G3: Ja sam tada" in txt

    run("analyze.py", proj, "--bez-slike")
    an = json.loads((proj / "analiza.json").read_text(encoding="utf-8"))
    assert [g["id"] for g in an["govornici"]] == ["G1", "G2", "G3"]
    assert an["govornici"][0]["ime"] == "Marko"
    assert abs(sum(g["udio"] for g in an["govornici"]) - 1) < 0.02
    assert all(s.get("govornik") for s in an["odsjecci"])
    # isti brojevi odsječaka kao u edit.json
    assert [(s["id"], s["govornik"]) for s in an["odsjecci"]] == [(s["id"], s["govornik"]) for s in edit["odsjecci"]]
    assert "Govornici: G1 (Marko)" in (proj / "analiza.txt").read_text(encoding="utf-8")


def test_bez_govornika_sve_kao_prije(tmp_path):
    proj = make_project(tmp_path)
    run("analyze.py", proj, "--bez-slike")
    an = json.loads((proj / "analiza.json").read_text(encoding="utf-8"))
    assert an["govornici"] is None
    assert not any("govornik" in s for s in an["odsjecci"])


# ---------------------------------------------------------------- pravi model

def _models_ready():
    try:
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    if os.environ.get("SHOFE_GOVORNICI_TEST") == "1":
        return True
    d = G.models_dir()
    return all((d / n).exists() for n in G.MODELS)


needs_model = pytest.mark.skipif(not _models_ready(),
                                 reason="sherpa-onnx modeli nisu skinuti (postavi SHOFE_GOVORNICI_TEST=1)")


@needs_model
def test_pravi_model_razgovor_tri_glasa(tmp_path):
    proj = make_project(tmp_path)
    r = run("govornici.py", proj)
    gov = json.loads((proj / "govornici.json").read_text(encoding="utf-8"))
    assert len(gov["govornici"]) == 3, r.stdout
    words = G.load_words(proj)
    acc, labs = sentence_accuracy(words)
    # spec: govornik točan u 9 od 10 rečenica
    assert acc >= 0.9, f"točno {acc:.0%}: {labs}\n{r.stdout}"
    # imena preživljavaju ponovnu analizu
    run("govornici.py", proj, "--imena", "G1=Marko")
    run("govornici.py", proj, "--broj", "3")
    gov = json.loads((proj / "govornici.json").read_text(encoding="utf-8"))
    assert gov["govornici"][0]["ime"] == "Marko" and len(gov["govornici"]) == 3
    assert sentence_accuracy(G.load_words(proj))[0] >= 0.9


@needs_model
def test_pravi_model_jedan_govornik(tmp_path):
    proj = tmp_path / "jedan"
    proj.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(FIX / "klip1.mp4"), "-c", "copy",
                    str(proj / "source.mp4")], check=True)
    # modeli u mapi s č/ć/ž i razmakom (korisničko ime na Windowsu može imati dijakritike)
    G.ensure_models()
    md = tmp_path / "modeli čćž đš"
    md.mkdir()
    for n in G.MODELS:
        shutil.copy(G.models_dir() / n, md / n)
    run("govornici.py", proj, env={"SHOFE_MODELI": str(md)})
    gov = json.loads((proj / "govornici.json").read_text(encoding="utf-8"))
    assert [g["id"] for g in gov["govornici"]] == ["G1"]
