"""M2.1: naredbe po vremenu gotovog videa (uredi.py) → izrezi u edit.json → render.

Probna snimka: klip1 + klip2 (mock transkript), plan.py izbacuje #2 (prekinut pokušaj) i #4 ("eee").
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

from uredi import parse_ranges, parse_time, source_spans, timeline  # noqa: E402


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


@pytest.fixture(scope="module")
def baza(tmp_path_factory):
    base = tmp_path_factory.mktemp("uredi čćž test")
    clips = base / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    proj = base / "shofe_projekt"
    run("prepare.py", clips, "--out", proj)
    pj = load(proj / "project.json")
    mock = load(FIX / "mock_words.json")
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj, "--stil", "suncani")
    return proj


@pytest.fixture
def projekt(baza, tmp_path):
    """Svježa kopija projekta za svaki test (bez videa za brze testove; source.mp4 se dijeli)."""
    p = tmp_path / "projekt s razmakom"
    p.mkdir()
    for f in ("project.json", "transcript.json", "edit.json"):
        shutil.copy(baza / f, p / f)
    return p


def words_of(proj):
    return load(proj / "transcript.json")["words"]


def out_text(proj, edit=None):
    tl, dur = timeline(words_of(proj), edit or load(proj / "edit.json"), load(proj / "project.json"))
    return [w["t"] for w in tl], tl, dur


# ---------------------------------------------------------------- raščlanjivanje
@pytest.mark.parametrize("s,exp", [("1:20", 80), ("1:20.5", 80.5), ("1:20,5", 80.5), ("0:01:20", 80),
                                   ("80", 80), ("7.5s", 7.5), ("01:05", 65)])
def test_parse_time(s, exp):
    assert parse_time(s) == pytest.approx(exp)


def test_parse_ranges_variants():
    assert parse_ranges(["1:20-1:45"]) == [(80, 105)]
    assert parse_ranges(["1:20–1:45"]) == [(80, 105)]          # crtica iz mobitela
    assert parse_ranges(["od", "1:20", "do", "1:45"]) == [(80, 105)]
    assert parse_ranges(["0:05", "-", "0:08", "i", "1:20-1:45"]) == [(5, 8), (80, 105)]
    assert parse_ranges(["1:20-1:45,", "2:00-2:10"]) == [(80, 105), (120, 130)]


@pytest.mark.parametrize("bad", [["1:45-1:20"], ["sutra"], ["1:70-1:80"], []])
def test_parse_ranges_errors(bad):
    with pytest.raises(ValueError):
        parse_ranges(bad)


# ---------------------------------------------------------------- makni / zadrži
def test_makni_removes_exact_words(projekt):
    toks, tl, dur = out_text(projekt)
    # gotovi video: "Bok, ja sam Marko iz Kutine. Danas vam pokazujem kako očistiti klimu. Prvi korak ..."
    i = toks.index("Prvi")
    j = toks.index("struju.")
    lo = (tl[i - 1]["e"] + tl[i]["s"]) / 2
    hi = (tl[j]["e"] + tl[j + 1]["s"]) / 2
    r = run("uredi.py", projekt, "makni", f"{lo:.2f}-{hi:.2f}")
    assert "Prvi korak je isključiti struju." in r.stdout
    toks2, _, dur2 = out_text(projekt)
    assert "struju." not in toks2 and "Prvi" not in toks2
    assert toks2 == toks[:i] + toks[j + 1:]
    assert dur2 < dur - 1.5
    iz = load(projekt / "edit.json")["izrezi"]
    assert len(iz) == 1 and iz[0]["n"] == 1 and "makni" in iz[0]["naredba"]


def test_boundary_inside_word_takes_whole_word(projekt):
    toks, tl, _ = out_text(projekt)
    w = tl[toks.index("Marko")]
    # počni u zadnjoj četvrtini riječi "Marko" → Marko ostaje; završi usred "Kutine." (> pola) → ide van
    k = tl[toks.index("Kutine.")]
    lo = w["s"] + 0.8 * (w["e"] - w["s"])
    hi = k["s"] + 0.7 * (k["e"] - k["s"])
    r = run("uredi.py", projekt, "makni", f"{lo:.3f}-{hi:.3f}")
    assert "usred riječi „Marko“ → cijela riječ ostaje" in r.stdout
    assert "usred riječi „Kutine.“ → cijela riječ ide van" in r.stdout
    toks2, _, _ = out_text(projekt)
    assert "Marko" in toks2 and "iz" not in toks2 and "Kutine." not in toks2


def test_cut_never_inside_word(projekt):
    words = words_of(projekt)
    for od, do, g in source_spans(words, [3, 4, 5, 10]):
        for w in words:  # nijedna riječ ne presijeca granicu
            assert not (w["s"] < od < w["e"]) and not (w["s"] < do < w["e"])
        assert all(od <= (words[i]["s"] + words[i]["e"]) / 2 < do for i in g)


def test_zadrzi_samo(projekt):
    toks, tl, _ = out_text(projekt)
    i, j = toks.index("Drugi"), toks.index("vodom.")
    lo = tl[i]["s"] - 0.05
    hi = tl[j]["e"] + 0.05
    run("uredi.py", projekt, "zadrži", f"{lo:.2f}", "do", f"{hi:.2f}")
    toks2, _, dur2 = out_text(projekt)
    assert toks2 == toks[i:j + 1]
    assert dur2 < 6


def test_vrati_undoes_in_order(projekt):
    orig = load(projekt / "edit.json")
    run("uredi.py", projekt, "makni", "0:00-0:02")
    one = load(projekt / "edit.json")
    run("uredi.py", projekt, "makni", "0:00-0:02", "--trenutno")
    assert len(load(projekt / "edit.json")["izrezi"]) > len(one["izrezi"])
    run("uredi.py", projekt, "vrati")
    assert load(projekt / "edit.json") == one
    run("uredi.py", projekt, "vrati")
    assert load(projekt / "edit.json") == orig
    r = run("uredi.py", projekt, "vrati", ok=False)
    assert r.returncode == 1 and "povijest je prazna" in r.stderr


def test_proba_changes_nothing(projekt):
    before = (projekt / "edit.json").read_bytes()
    r = run("uredi.py", projekt, "makni", "0:01-0:03", "--proba")
    assert "proba" in r.stdout and (projekt / "edit.json").read_bytes() == before


def test_times_refer_to_last_render(projekt):
    """Korisnik gleda reel_v1; dvije naredbe zaredom bez novog rendera obje se čitaju iz reel_v1."""
    edit = load(projekt / "edit.json")
    (projekt / "verzije").mkdir()
    save(projekt / "verzije" / "edit_v1.json", edit)
    toks, tl, _ = out_text(projekt)
    a = tl[toks.index("Drugi")]
    b = tl[toks.index("putu!")]
    # prvo makni početak (do "Kutine."), pa dio s "putu!" po vremenu iz reel_v1
    k = tl[toks.index("Kutine.")]
    run("uredi.py", projekt, "makni", f"0-{k['e'] + 0.05:.2f}")
    run("uredi.py", projekt, "makni", f"{b['s'] - 0.02:.2f}-{b['e'] + 0.02:.2f}")
    toks2, _, _ = out_text(projekt)
    assert "putu!" not in toks2 and "Kutine." not in toks2 and "Drugi" in toks2
    # --trenutno: ista vremena sada pokazuju na drugo mjesto
    r = run("uredi.py", projekt, "makni", f"{a['s']:.2f}-{a['e']:.2f}", "--trenutno", "--proba")
    assert "Drugi" not in r.stdout.split("Trajanje")[0]


def test_ranges_out_of_video(projekt):
    r = run("uredi.py", projekt, "makni", "9:00-9:10", ok=False)
    assert r.returncode == 1 and "iza kraja" in r.stderr


def test_popis_lists_output_times(projekt):
    r = run("uredi.py", projekt, "popis")
    assert "Bok, ja sam Marko" in r.stdout and "#1" in r.stdout
    run("uredi.py", projekt, "makni", "0:00-0:02")
    r = run("uredi.py", projekt, "popis")
    assert "Izrezano naredbama po vremenu" in r.stdout


# ---------------------------------------------------------------- render i ispravljeni tekst
def test_corrected_text_follows_cut():
    """Claude je ispravio tekst (2 riječi → 3 tokena); izrez usred odsječka miče i pripadne tokene."""
    from render import build_cuts
    words = [{"w": "Bok", "s": 0.0, "e": 0.3}, {"w": "Shofe", "s": 0.4, "e": 0.8},
             {"w": "montaza", "s": 0.9, "e": 1.4}, {"w": "radi.", "s": 1.5, "e": 1.9}]
    edit = {"odsjecci": [{"id": 1, "od": 0.0, "do": 1.9, "tekst": "Bok, Šofe montaža stvarno radi.", "zadrzi": True}],
            "izrezi": [{"od": 0.35, "do": 1.45}]}
    cuts, kept, total = build_cuts(words, edit, {"rezanje": [0.05, 0.1]}, 30, 2.0)
    flat = []
    for item in kept:
        flat += item[1] if isinstance(item[0], list) else [item[1]]
    assert flat == ["Bok,", "radi."]
    assert total < 1.0
    for c in cuts:  # ništa iz izrezanog dijela
        assert c["b"] <= 0.35 + 1e-6 or c["a"] >= 1.45 - 1e-6


def test_render_after_makni(baza, tmp_path):
    proj = tmp_path / "render"
    shutil.copytree(baza, proj, ignore=shutil.ignore_patterns("*.png", "reel_*", "verzije", "povijest"))
    run("render.py", proj, "--brzo")  # reel_v1_pregled + verzije/edit_v1.json
    toks, tl, dur = out_text(proj)
    i = toks.index("Drugi")
    run("uredi.py", proj, "makni", f"{tl[i]['s'] - 0.05:.2f}-{tl[toks.index('vodom.')]['e'] + 0.05:.2f}")
    r = run("render.py", proj, "--izlaz", "poslije.mp4")
    assert "Izrezano naredbama po vremenu" in r.stdout
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(proj / "poslije.mp4")], capture_output=True, text=True).stdout
    _, _, dur2 = out_text(proj)
    assert abs(float(out) - dur2) < 0.2
    assert dur - dur2 > 3.0
    ass = (proj / "captions.ass").read_text(encoding="utf-8")
    assert "FILTER" not in ass and "MLAKOM" not in ass and "KLIMU" in ass
