"""M2.2: naredbe po sadržaju (uredi.py --od/--do, --tema, --odsjecak, --rijeci, dodaj, trazi).

Testni skup od 10+ naredbi je u tests/fixtures/naredbe_sadrzaj.json: izmišljeni reel s tri pokušaja
uvoda, a za svaku naredbu argumenti koje Claude preda alatu i točan očekivani tekst gotovog videa.
Cilj iz SPEC-a: 9 od 10 naredbi pogodi pravi dio → ovdje moraju sve.
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

import sadrzaj  # noqa: E402
from uredi import timeline  # noqa: E402

SKUP = json.loads((FIX / "naredbe_sadrzaj.json").read_text(encoding="utf-8"))


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} {args} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def make_words(start=0.5):
    """Rečenice iz testnog skupa → riječi s vremenima (trajanje po broju slova) + granice rečenica."""
    words, bounds, t = [], [], start
    for text, pause in SKUP["recenice"]:
        first = len(words)
        for k, tok in enumerate(text.split()):
            d = 0.10 + 0.055 * len(tok)
            words.append({"w": tok, "s": round(t, 3), "e": round(t + d, 3), "p": 0.95})
            t += d + 0.06
        t += pause - 0.06
        bounds.append((first, len(words) - 1))
    return words, bounds, t


def write_project(proj, duration=None, video=False):
    words, bounds, end = make_words()
    if not video:
        proj.mkdir(parents=True, exist_ok=True)
        save(proj / "project.json", {"fps": 30, "duration": round(end + 0.5, 3), "width": 1080, "height": 1920,
                                     "format": "9:16", "clips": []})
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj, "--stil", "cisto")
    teme = []
    for t in SKUP["teme"]:
        a, b = t["recenice"]
        teme.append({"od": words[bounds[a][0]]["s"], "do": words[bounds[b][1]]["e"], "naslov": t["naslov"],
                     "sazetak": t.get("sazetak", "")})
    save(proj / "analiza.json", {"teme": teme, "trenuci": []})
    return words, bounds


@pytest.fixture(scope="module")
def baza(tmp_path_factory):
    proj = tmp_path_factory.mktemp("sadržaj čćž") / "shofe_projekt"
    write_project(proj)
    return proj


@pytest.fixture
def projekt(baza, tmp_path):
    p = tmp_path / "projekt s razmakom"
    shutil.copytree(baza, p)
    return p


def video_words(proj):
    tl, dur = timeline(load(proj / "transcript.json")["words"], load(proj / "edit.json"), load(proj / "project.json"))
    return tl, dur


def text_of(tl, idxs):
    by = {w["i"]: w["t"] for w in tl}
    return " ".join(by[i] for i in sorted(idxs))


# ---------------------------------------------------------------- testni skup od 10 naredbi
def test_baseline_plan(baza):
    """Početni plan: plan.py izbaci prva dva pokušaja uvoda, a svaka rečenica je svoj odsječak."""
    tl, _ = video_words(baza)
    txt = " ".join(w["t"] for w in tl)
    assert "tri stvari o klima" not in txt and "tri stvari koje morate znati" in txt
    edit = load(baza / "edit.json")
    assert len(edit["odsjecci"]) == len(SKUP["recenice"])
    assert edit["odsjecci"][8]["tekst"] == SKUP["recenice"][8][0]


@pytest.mark.parametrize("case", SKUP["naredbe"], ids=[c["naredba"][:40] for c in SKUP["naredbe"]])
def test_skup_naredbi(projekt, case):
    words = load(projekt / "transcript.json")["words"]
    before, _ = video_words(projekt)
    for step in case["koraci"]:
        if isinstance(step, dict):
            r = run("uredi.py", projekt, *step["args"], ok=False)
            assert r.returncode != 0, f"trebala je biti greška: {r.stdout}"
            assert step["greska"] in r.stdout + r.stderr
        else:
            run("uredi.py", projekt, *step)
    after, _ = video_words(projekt)
    b_set, a_set = {w["i"] for w in before}, {w["i"] for w in after}
    disp = {w["i"]: w["t"] for w in before + after}
    van = " ".join(disp[i] for i in sorted(b_set - a_set))
    vraca = " ".join(disp[i] for i in sorted(a_set - b_set))
    if "ostaje" in case:
        assert " ".join(w["t"] for w in after) == case["ostaje"]
    else:
        assert van == case.get("van", ""), case["naredba"]
        assert vraca == case.get("vraca", ""), case["naredba"]
    assert all(w["e"] > w["s"] for w in after)
    assert len(words) == len(load(projekt / "transcript.json")["words"])  # transkript netaknut


def test_skup_ima_bar_10_naredbi():
    assert len(SKUP["naredbe"]) >= 10


# ---------------------------------------------------------------- pojedinosti
def test_fold_and_match():
    assert sadrzaj.fold("Uređaja?") == "uredjaja"
    assert sadrzaj.tok_score("kosta", sadrzaj.fold("košta")) == 2
    assert sadrzaj.tok_score("cijenu", "cijena") == 1
    assert sadrzaj.tok_score("uredaja", "uredjaja") == 1
    assert sadrzaj.tok_score("ne", "na") == 0
    assert sadrzaj.tok_score("radimo", "radijatora") == 0


def test_corrected_text_is_searchable(projekt):
    """Claude je u edit.json ispravio 'SF klime' → 'Esef klime'; citat iz ispravljenog teksta radi."""
    edit = load(projekt / "edit.json")
    edit["odsjecci"][0]["tekst"] = "Bok ekipa, ovdje Marko iz Esef klime."
    save(projekt / "edit.json", edit)
    r = run("uredi.py", projekt, "makni", "--od", "Esef klime")
    assert "Esef klime" in r.stdout
    tl, _ = video_words(projekt)
    assert [w["t"] for w in tl][:5] == ["Bok", "ekipa,", "ovdje", "Marko", "iz"]


def test_trazi_lists_hits_with_times(projekt):
    r = run("uredi.py", projekt, "trazi", "ugradnja")
    assert "4 pojava" in r.stdout  # Ugradnja je…, Drugo, ugradnja., Ugradnja traje…, Ugradnja zimi…
    r = run("uredi.py", projekt, "trazi", "tri stvari o")
    assert "nije u videu" in r.stdout and "riječ" in r.stdout
    r = run("uredi.py", projekt, "trazi", "helikopter")
    assert "nije pronađeno" in r.stdout


def test_rijeci_from_trazi(projekt):
    words = load(projekt / "transcript.json")["words"]
    i = next(k for k, w in enumerate(words) if w["w"] == "jeftinije")
    run("uredi.py", projekt, "makni", "--rijeci", f"{i - 2}-{i + 1}")
    tl, _ = video_words(projekt)
    txt = " ".join(w["t"] for w in tl)
    assert "Zimi klima i grije, radijatora." in txt


def test_proba_and_vrati(projekt):
    orig = (projekt / "edit.json").read_text(encoding="utf-8")
    r = run("uredi.py", projekt, "makni", "--tema", "ugradnja", "--proba")
    assert "proba" in r.stdout and (projekt / "edit.json").read_text(encoding="utf-8") == orig
    run("uredi.py", projekt, "dodaj", "--odsjecak", "2-3")
    run("uredi.py", projekt, "makni", "--tema", "2")
    assert (projekt / "edit.json").read_text(encoding="utf-8") != orig
    run("uredi.py", projekt, "vrati")
    run("uredi.py", projekt, "vrati")
    assert load(projekt / "edit.json") == json.loads(orig)


def test_notes_for_half_sentence(projekt):
    r = run("uredi.py", projekt, "makni", "--od", "i to jeftinije od radijatora.", "--proba")
    assert "počinje usred rečenice" in r.stdout


def test_errors(projekt):
    r = run("uredi.py", projekt, "makni", "--od", "Danas vam pokazujem tri", ok=False)
    assert r.returncode != 0 and "puta" in r.stdout + r.stderr
    r = run("uredi.py", projekt, "makni", "1:00-1:10", "--tema", "1", ok=False)
    assert "ne oboje" in r.stdout + r.stderr
    r = run("uredi.py", projekt, "zadrzi", "--tema", "helikopteri", ok=False)
    assert "Teme:" in r.stdout + r.stderr
    r = run("uredi.py", projekt, "makni", "--odsjecak", "99", ok=False)
    assert "nema odsječka" in r.stdout + r.stderr
    r = run("uredi.py", projekt, "makni", "--odsjecak", "2", ok=True)
    assert "Ništa za promijeniti" in r.stdout  # odsječak 2 je već izbačen (prekinut pokušaj)
    r = run("uredi.py", projekt, "dodaj", "1:00-1:10", ok=False)
    assert "po sadržaju" in r.stdout + r.stderr


def test_content_after_time_cut(projekt):
    """Naredba po vremenu pa 'dodaj' istih riječi: izrez se skrati, riječi se vrate."""
    tl, _ = video_words(projekt)
    i = next(k for k, w in enumerate(tl) if w["t"] == "Filter")
    j = next(k for k, w in enumerate(tl) if w["t"] == "osušite.")
    run("uredi.py", projekt, "makni", "--trenutno", f"{tl[i]['s'] - 0.03:.2f}-{tl[j]['e'] + 0.03:.2f}")
    txt = " ".join(w["t"] for w in video_words(projekt)[0])
    assert "Filter" not in txt and "mlakom" not in txt
    run("uredi.py", projekt, "dodaj", "--od", "Samo ga isperite", "--cijele-recenice")
    txt = " ".join(w["t"] for w in video_words(projekt)[0])
    assert "Filter" not in txt and "Samo ga isperite pod mlakom vodom i osušite." in txt


# ---------------------------------------------------------------- pravi render
def test_render_drugi_pokusaj(tmp_path):
    words, _, end = make_words()
    clip = tmp_path / "klipovi" / "snimka.mp4"
    clip.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=360x640:r=30:d={end + 1:.2f}",
                    "-f", "lavfi", "-i", f"sine=f=220:d={end + 1:.2f}", "-shortest", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", str(clip)], check=True)
    proj = tmp_path / "shofe_projekt"
    run("prepare.py", clip, "--out", proj)
    write_project(proj, video=True)
    run("uredi.py", proj, "dodaj", "--od", "tri stvari o klima uređajima.", "--cijele-recenice")
    run("uredi.py", proj, "makni", "--od", "koje morate znati", "--cijele-recenice")
    run("render.py", proj, "--brzo", "--izlaz", "poslije.mp4")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(proj / "poslije.mp4")], capture_output=True, text=True).stdout
    _, dur = video_words(proj)
    assert abs(float(out) - dur) < 0.2
    ass = (proj / "captions.ass").read_text(encoding="utf-8").lower()
    assert "morate" not in ass and "stvari" in ass and "uređajima" in ass
    assert ass.count("pokazujem") == 1
