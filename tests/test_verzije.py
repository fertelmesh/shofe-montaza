"""M2.4: verzije montaže — popis, „vrati verziju N", usporedba što se promijenilo.

Probna snimka kao u test_uredi.py: klip1 + klip2 s mock transkriptom.
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

import verzije  # noqa: E402
from uredi import timeline  # noqa: E402


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
    base = tmp_path_factory.mktemp("verzije čćž test")
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
    p = tmp_path / "projekt s razmakom"
    p.mkdir()
    for f in ("project.json", "transcript.json", "edit.json"):
        shutil.copy(baza / f, p / f)
    return p


def fake_render(proj, brzo=False):
    """Kao render.py, bez ffmpega: prazna datoteka videa + verzije/edit_vN.json + verzije.json."""
    edit = load(proj / "edit.json")
    v = verzije.next_number(proj)
    name = f"reel_v{v}_pregled.mp4" if brzo else f"reel_v{v}.mp4"
    (proj / name).write_bytes(b"")
    dur = timeline(load(proj / "transcript.json")["words"], edit, load(proj / "project.json"))[1]
    verzije.record_render(proj, v, edit, name, dur, brzo)
    return v


def toks(proj, edit=None):
    tl, _ = timeline(load(proj / "transcript.json")["words"], edit or load(proj / "edit.json"),
                     load(proj / "project.json"))
    return [w["t"] for w in tl], tl


def three_versions(projekt):
    """v1 = plan; v2 = makni „Prvi korak … struju."; v3 = stil kino + veći titlovi + ispravak teksta."""
    fake_render(projekt)
    run("uredi.py", projekt, "makni", "--od", "Prvi korak", "--do", "struju.")
    fake_render(projekt)
    e = load(projekt / "edit.json")
    e["stil"] = "kino"
    e["velicina_titlova"] = 1.2
    seg = next(s for s in e["odsjecci"] if s.get("zadrzi", True))
    seg["tekst"] = "Bok, ja sam Marko iz Kutine!"
    save(projekt / "edit.json", e)
    fake_render(projekt)
    return seg["id"]


# ---------------------------------------------------------------- popis
def test_popis_without_versions(projekt):
    r = run("verzije.py", projekt)
    assert "Još nema verzija" in r.stdout


def test_popis_lists_versions_with_changes(projekt):
    three_versions(projekt)
    r = run("verzije.py", projekt, "popis")
    out = r.stdout
    for n in (1, 2, 3):
        assert f"v{n} " in out and f"reel_v{n}.mp4" in out
    assert "prva verzija" in out
    assert "makni „Prvi korak“ … „struju.“" in out          # v2: naredba
    assert "stil „suncani“ → „kino“" in out                 # v3: postavke
    assert "ispravci teksta: 1" in out
    assert "► v3" in out
    assert "trenutni edit.json = v3" in out
    # nerenderirane izmjene se vide
    run("uredi.py", projekt, "makni", "0:00-0:01")
    r = run("verzije.py", projekt)
    assert "još nije renderiran" in r.stdout and "makni 00:00.00-00:01.00" in r.stdout


def test_popis_marks_preview_and_deleted_video(projekt):
    fake_render(projekt, brzo=True)
    fake_render(projekt)
    (projekt / "reel_v2.mp4").unlink()
    r = run("verzije.py", projekt)
    assert "reel_v1_pregled.mp4 [brzi pregled]" in r.stdout
    assert "(video obrisan)" in r.stdout


# ---------------------------------------------------------------- vrati verziju N
def test_vrati_verziju_and_undo(projekt):
    three_versions(projekt)
    v3 = load(projekt / "edit.json")
    r = run("verzije.py", projekt, "vrati", "1")
    assert load(projekt / "edit.json") == load(projekt / "verzije" / "edit_v1.json")
    assert "reel_v1.mp4" in r.stdout and "novi render nije potreban" in r.stdout
    assert verzije.viewed(projekt) == 1
    # novije verzije ostaju
    assert set(verzije.found_versions(projekt)) == {1, 2, 3}
    # vremena se sada čitaju iz v1 (u v1 "Prvi korak" još postoji)
    r = run("uredi.py", projekt, "makni", "0:00-0:01", "--proba")
    assert "reel_v1 (vraćena verzija)" in r.stdout
    # uredi.py vrati poništava „vrati verziju" i vraća koju verziju korisnik gleda
    r = run("uredi.py", projekt, "vrati")
    assert "vrati verziju 1" in r.stdout
    assert load(projekt / "edit.json") == v3
    assert "_shofe" not in load(projekt / "edit.json")
    assert verzije.viewed(projekt) == 3


def test_vrati_proba_and_same(projekt):
    fake_render(projekt)
    run("uredi.py", projekt, "makni", "--od", "Prvi korak", "--do", "struju.")
    before = (projekt / "edit.json").read_bytes()
    r = run("verzije.py", projekt, "vrati", "v1", "--proba")
    assert "proba" in r.stdout and (projekt / "edit.json").read_bytes() == before
    assert "+" in r.stdout and "riječi" in r.stdout          # vraća izrezane riječi
    run("verzije.py", projekt, "vrati", "1")
    r = run("verzije.py", projekt, "vrati", "1")
    assert "već isti" in r.stdout


def test_render_after_vrati_is_new_version(projekt):
    three_versions(projekt)
    run("verzije.py", projekt, "vrati", "2")
    v = fake_render(projekt)
    assert v == 4 and verzije.viewed(projekt) == 4
    assert load(projekt / "verzije" / "edit_v4.json") == load(projekt / "verzije" / "edit_v2.json")
    r = run("verzije.py", projekt, "usporedi", "2", "4")
    assert "Nema razlike" in r.stdout


@pytest.mark.parametrize("args,msg", [(["vrati"], "koju verziju"), (["vrati", "9"], "nema verzije 9"),
                                      (["vrati", "sutra"], "ne razumijem verziju"),
                                      (["usporedi", "1", "2", "3"], "najviše dvije"), (["bla"], "nepoznata naredba")])
def test_errors(projekt, args, msg):
    fake_render(projekt)
    fake_render(projekt)
    r = run("verzije.py", projekt, *args, ok=False)
    assert r.returncode == 1 and msg in r.stderr


# ---------------------------------------------------------------- usporedba
def test_usporedi_words_settings_text(projekt):
    sid = three_versions(projekt)
    t1, tl1 = toks(projekt, load(projekt / "verzije" / "edit_v1.json"))
    r = run("verzije.py", projekt, "usporedi", "1", "3")
    out = r.stdout
    assert "v1 (reel_v1.mp4) → v3 (reel_v3.mp4)" in out
    assert "Izbačeno (vrijeme u v1):" in out
    i, j = t1.index("Prvi"), t1.index("struju.")
    # izbačeni dio s vremenom u v1 i razlogom (naredba)
    assert f"{verzije.fmt_time(tl1[i]['s'])}-{verzije.fmt_time(tl1[j]['e'])}" in out
    assert "„Prvi korak je isključiti struju.“" in out
    assert "(makni „Prvi korak“ … „struju.“)" in out
    assert "stil: „suncani“ → „kino“" in out
    assert "veličina titlova: 1.0 → 1.2" in out
    assert f"#{sid}:" in out and "Kutine!" in out
    assert "Dodano" not in out


def test_usporedi_reverse_shows_added(projekt):
    three_versions(projekt)
    r = run("verzije.py", projekt, "usporedi", "3", "1")
    assert "Dodano (vrijeme u v1):" in r.stdout and "Prvi korak je isključiti struju." in r.stdout
    assert "Više ne vrijedi: makni" in r.stdout


def test_usporedi_default_pair(projekt):
    fake_render(projekt)
    r = run("verzije.py", projekt, "usporedi")
    assert "Nema što usporediti" in r.stdout
    run("uredi.py", projekt, "makni", "--od", "Prvi korak", "--do", "struju.")
    r = run("verzije.py", projekt, "usporedi")          # nerenderirano → v1 vs trenutno
    assert "v1 (reel_v1.mp4) → trenutni edit.json" in r.stdout and "Prvi korak" in r.stdout
    fake_render(projekt)
    r = run("verzije.py", projekt, "usporedi")          # sve renderirano → v1 vs v2
    assert "v1 (reel_v1.mp4) → v2 (reel_v2.mp4)" in r.stdout
    r = run("verzije.py", projekt, "usporedi", "1")     # jedna verzija → prema trenutnom
    assert "→ trenutni edit.json" in r.stdout


def test_usporedi_reason_segment_off(projekt):
    fake_render(projekt)
    e = load(projekt / "edit.json")
    seg = next(s for s in e["odsjecci"] if s.get("zadrzi", True))
    seg["zadrzi"] = False
    save(projekt / "edit.json", e)
    r = run("verzije.py", projekt, "usporedi", "1", "trenutno")
    assert f"isključen odsječak #{seg['id']}" in r.stdout


def test_nazovi(projekt):
    fake_render(projekt)
    run("verzije.py", projekt, "nazovi", "1", "za", "Instagram")
    r = run("verzije.py", projekt)
    assert "„za Instagram“" in r.stdout
    r = run("verzije.py", projekt, "usporedi", "1")
    assert "v1 „za Instagram“ (reel_v1.mp4)" in r.stdout


def test_next_number_survives_deleted_videos(projekt):
    fake_render(projekt)
    fake_render(projekt)
    for f in projekt.glob("reel_v*.mp4"):
        f.unlink()
    assert verzije.next_number(projekt) == 3     # ne prepisuje verzije/edit_v1.json i edit_v2.json


def test_corrupt_meta_is_ignored(projekt):
    fake_render(projekt)
    (projekt / "verzije" / "verzije.json").write_text("{pokvareno", encoding="utf-8")
    r = run("verzije.py", projekt)
    assert "► v1" in r.stdout


# ---------------------------------------------------------------- pravi render
def test_real_render_records_versions(baza, tmp_path):
    proj = tmp_path / "render"
    shutil.copytree(baza, proj, ignore=shutil.ignore_patterns("*.png", "reel_*", "verzije", "povijest"))
    e0 = load(proj / "edit.json")
    run("render.py", proj, "--brzo")
    e = load(proj / "edit.json")
    e["stil"] = "kino"
    save(proj / "edit.json", e)
    r = run("render.py", proj, "--brzo")
    assert "verzija 2" in r.stdout
    meta = load(proj / "verzije" / "verzije.json")
    assert meta["gledano"] == 2 and set(meta["verzije"]) == {"1", "2"}
    assert meta["verzije"]["1"]["datoteka"] == "reel_v1_pregled.mp4" and meta["verzije"]["1"]["brzi_pregled"]
    assert load(proj / "verzije" / "edit_v1.json") == e0        # točno edit.json, ništa dodano
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(proj / "reel_v2_pregled.mp4")], capture_output=True, text=True).stdout)
    assert abs(dur - meta["verzije"]["2"]["trajanje"]) < 0.2
    # --izlaz ne stvara verziju
    run("render.py", proj, "--izlaz", "probni.mp4")
    assert set(load(proj / "verzije" / "verzije.json")["verzije"]) == {"1", "2"}
    r = run("verzije.py", proj, "usporedi")
    assert "stil: „suncani“ → „kino“" in r.stdout


def test_sat_snimke_brzo(tmp_path):
    """Sat snimke (~6500 riječi, 1000 odsječaka), 6 verzija: popis i usporedba za par sekundi."""
    import random
    import time
    random.seed(3)
    sents = [s for s, _ in json.loads((FIX / "naredbe_sadrzaj.json").read_text("utf-8"))["recenice"]]
    words, t = [], 0.5
    for _ in range(1000):
        for tok in random.choice(sents).split():
            d = 0.10 + 0.055 * len(tok)
            words.append({"w": tok, "s": round(t, 3), "e": round(t + d, 3), "p": 0.95})
            t += d + 0.06
        t += random.choice([0.3, 0.5, 0.9])
    proj = tmp_path / "dugo"
    proj.mkdir()
    save(proj / "project.json", {"fps": 30, "duration": round(t + 0.5, 3), "width": 1080, "height": 1920,
                                 "format": "9:16", "clips": []})
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj, "--stil", "cisto")
    for k in range(6):
        fake_render(proj)
        run("uredi.py", proj, "makni", f"{k * 5}:00-{k * 5}:40")
    t0 = time.time()
    r = run("verzije.py", proj)
    r2 = run("verzije.py", proj, "usporedi", "1", "6")
    assert time.time() - t0 < 15
    assert "► v6" in r.stdout and r2.stdout.count("(makni ") == 5
