"""M2.5b: rječnik se sam nadopunjuje iz ispravaka teksta (edit.json `tekst` vs transkript)."""
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

import rjecnik  # noqa: E402


@pytest.fixture(autouse=True)
def podaci(tmp_path, monkeypatch):
    d = tmp_path / "podaci čž"
    monkeypatch.setenv("SHOFE_PODACI", str(d))
    return d


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


def words_from(text, start=0.0):
    ws, t = [], start
    for tok in text.split():
        ws.append({"w": tok, "s": round(t, 3), "e": round(t + 0.3, 3), "p": 0.9})
        t += 0.4
    return ws


def one_seg(orig, fixed, sid=1):
    """Riječi transkripta i edit s jednim odsječkom u kojem je tekst ispravljen u `fixed`."""
    ws = words_from(orig)
    return ws, {"odsjecci": [{"id": sid, "od": ws[0]["s"], "do": ws[-1]["e"], "tekst": fixed, "zadrzi": True}]}


def found(orig, fixed):
    ws, edit = one_seg(orig, fixed)
    return [(" ".join(a), " ".join(b)) for a, b, _ in rjecnik.find_corrections(ws, edit["odsjecci"])]


# ---------------------------------------------------------------- što se uči, a što ne
@pytest.mark.parametrize("orig,fixed,expected", [
    ("Ja sam Marko Fertelmes iz Kutine.", "Ja sam Marko Fertelmeš iz Kutine.", [("Fertelmes", "Fertelmeš")]),
    ("ovo je esef klima za vas", "ovo je SF klima za vas", [("esef", "SF")]),
    ("slušate sunčani četiri m podcast", "slušate Sunčani4M podcast", [("sunčani četiri m", "Sunčani4M")]),
    ("ja sam iz kutine, a vi?", "ja sam iz Kutine, a vi?", [("kutine", "Kutine")]),           # ime: veliko slovo
    ("dizalica topine radi", "dizalica topline radi", [("topine", "topline")]),
    ("to je cisto ok", "to je čisto ok", [("cisto", "čisto")]),                               # kvačice
    ("danas čistimo. filter je pun", "Danas čistimo. Filter je pun", []),                    # početak rečenice
    ("očistite klime filter", "očistite klima filter", []),                                  # padež: gramatika
    ("ja je bio tamo", "ja sam bio tamo", []),                                               # kratke riječi
    ("eee prvi korak je struja", "prvi korak je struja", []),                                # izbačen poluglas
    ("to ono što ja kažem", "to što kažem", []),                                             # preformulirano
    ("košta tristo eura", "košta 300 eura", []),                                             # stil brojeva
    ("Imam Klimu doma", "Imam klimu doma", []),                                              # prema malom slovu
    ("Fertelmes, pozdrav", "Fertelmeš, pozdrav", [("Fertelmes", "Fertelmeš")]),              # interpunkcija ostaje
])
def test_find_corrections(orig, fixed, expected):
    assert found(orig, fixed) == expected


def test_dropped_segment_and_unchanged_ignored():
    ws, edit = one_seg("Marko Fertelmes", "Marko Fertelmeš")
    edit["odsjecci"][0]["zadrzi"] = False
    assert rjecnik.find_corrections(ws, edit["odsjecci"]) == []
    ws, edit = one_seg("Marko Fertelmeš", "Marko Fertelmeš")
    assert rjecnik.find_corrections(ws, edit["odsjecci"]) == []


# ---------------------------------------------------------------- učenje kroz projekte
def test_learn_needs_two_sightings_and_never_double_counts(tmp_path):
    ws, edit = one_seg("Bok, ja sam Marko Fertelmes.", "Bok, ja sam Marko Fertelmeš.")
    a, b = tmp_path / "a", tmp_path / "b"
    new, lost, f = rjecnik.learn(a, edit, ws)
    assert len(f) == 1 and new == [] and rjecnik.active() == {}
    for _ in range(3):                       # isti projekt renderiran više puta: i dalje 1×
        new, _, _ = rjecnik.learn(a, edit, ws)
    assert new == [] and rjecnik.active() == {}
    new, _, _ = rjecnik.learn(b, edit, ws)   # drugi video s istim ispravkom → aktivan
    assert new == [("Fertelmes", "Fertelmeš")]
    assert rjecnik.active() == {"fertelmes": "Fertelmeš"}
    assert "Fertelmeš" in rjecnik.prompt_terms() or "Marko Fertelmeš" in rjecnik.prompt_terms()


def test_two_sightings_in_one_video_activate(tmp_path):
    ws, edit = one_seg("esef klima i opet esef klima", "SF klima i opet SF klima")
    new, _, _ = rjecnik.learn(tmp_path / "a", edit, ws)
    assert new == [("esef", "SF")]
    assert "SF" in rjecnik.prompt_terms()


def test_undoing_a_correction_in_project_forgets_its_count(tmp_path):
    ws, edit = one_seg("esef klima i opet esef klima", "SF klima i opet SF klima")
    rjecnik.learn(tmp_path / "a", edit, ws)
    edit["odsjecci"][0]["tekst"] = "esef klima i opet esef klima"   # Marko vratio stari tekst
    new, lost, _ = rjecnik.learn(tmp_path / "a", edit, ws)
    assert lost == [("esef", "SF")] and rjecnik.active() == {}
    assert rjecnik.load()["ispravci"] == {}


def test_dry_run_saves_nothing(tmp_path, podaci):
    ws, edit = one_seg("esef klima i opet esef klima", "SF klima i opet SF klima")
    new, _, _ = rjecnik.learn(tmp_path / "a", edit, ws, dry=True)
    assert new and not (podaci / "rjecnik.json").exists()


# ---------------------------------------------------------------- primjena
def test_apply_text_keeps_punctuation_and_case():
    act = {"fertelmes": "Fertelmeš", "esef": "SF", "sunčani četiri m": "Sunčani4M", "inverterski": "inverterski"}
    txt, ap = rjecnik.apply_text("fertelmes, esef klima! Sunčani četiri M? (fertelmes)", act)
    assert txt == "Fertelmeš, SF klima! Sunčani4M? (Fertelmeš)"
    assert [x["u"] for x in ap] == ["Fertelmeš", "SF", "Sunčani4M", "Fertelmeš"]
    txt, ap = rjecnik.apply_text("Fertelmeš je tu", act)         # već točno → ništa
    assert txt == "Fertelmeš je tu" and ap == []
    act = {"topine": "topline"}
    assert rjecnik.apply_text("Topine. dizalica topine", act)[0] == "Topline. dizalica topline"


def test_apply_edit_marks_segments():
    edit = {"odsjecci": [{"id": 1, "tekst": "Marko fertelmes."}, {"id": 2, "tekst": "Ništa."}]}
    ch = rjecnik.apply_edit(edit, {"fertelmes": "Fertelmeš"})
    assert ch == [(1, "Marko fertelmes.", "Marko Fertelmeš.")]
    assert edit["odsjecci"][0]["rjecnik"] == [{"iz": "fertelmes", "u": "Fertelmeš"}]
    assert "rjecnik" not in edit["odsjecci"][1]


def test_reverted_auto_correction_disables_it(tmp_path):
    ws, edit = one_seg("moja kima i tvoja kima", "moja Kima i tvoja Kima")     # npr. ime psa, 2×
    assert rjecnik.learn(tmp_path / "a", edit, ws)[0] == [("kima", "Kima")]
    ws2 = words_from("moja kima spava")
    e2 = {"odsjecci": [{"id": 1, "od": 0, "do": 9, "tekst": "moja kima spava", "zadrzi": True}]}
    rjecnik.apply_edit(e2)
    assert e2["odsjecci"][0]["tekst"] == "moja Kima spava"
    e2["odsjecci"][0]["tekst"] = "moja kima spava"           # u novom videu netko to vratio na staro
    new, lost, _ = rjecnik.learn(tmp_path / "b", e2, ws2)
    assert lost == [("kima", "Kima")] and rjecnik.active() == {}
    assert "vraćen na staro" in run("rjecnik.py", "popis").stdout


def test_manual_correction_stays_active_when_reverted(tmp_path):
    rjecnik.cmd_dodaj(type("A", (), {"krivo": "kima", "tocno": "Kima"})())
    ws = words_from("moja kima spava")
    edit = {"odsjecci": [{"id": 1, "od": 0, "do": 9, "tekst": "moja kima spava", "zadrzi": True}]}
    rjecnik.apply_edit(edit)
    edit["odsjecci"][0]["tekst"] = "moja kima spava"
    rjecnik.learn(tmp_path / "a", edit, ws)
    assert rjecnik.active() == {"kima": "Kima"}                # Marko ga je sam zadao
    rjecnik.cmd_zaboravi(type("A", (), {"krivo": "kima"})())
    assert rjecnik.active() == {}
    ws2, e2 = one_seg("moja kima i tvoja kima", "moja Kima i tvoja Kima")
    rjecnik.learn(tmp_path / "b", e2, ws2)
    assert rjecnik.active() == {}                              # isključen se više ne uči


# ---------------------------------------------------------------- whisper upit
def test_prompt_respects_token_budget_and_order():
    terms = rjecnik.prompt_terms()
    assert terms[0] == "Marko Fertelmeš"                     # osnovni rjecnik.txt prvi
    many = terms + [f"Pojam{i} Nešto" for i in range(300)]
    p = rjecnik.build_prompt(many)
    assert p.startswith("Marko Fertelmeš, Kutina") and p.endswith(".")
    assert len(p) // 3 + 1 <= rjecnik.MAX_TOKENA
    words_count = lambda s: len(s.split())                  # noqa: E731
    assert words_count(rjecnik.build_prompt(many, words_count, limit=10)) <= 10
    assert rjecnik.build_prompt([]) is None


def test_transcribe_uses_vocabulary():
    import transcribe
    rjecnik.cmd_dodaj(type("A", (), {"krivo": "Grga Čvarak", "tocno": None})())
    p = transcribe.vocabulary_prompt()
    assert "Sunčani4M" in p and "Grga Čvarak" in p


# ---------------------------------------------------------------- naredbe
def test_cli_dodaj_popis_zaboravi(podaci):
    r = run("rjecnik.py", "popis")
    assert "još nijedan" in r.stdout and "Sunčani4M" in r.stdout
    run("rjecnik.py", "dodaj", "Ivan Horvat")
    assert "već u rječniku" in run("rjecnik.py", "dodaj", "ivan horvat").stdout
    assert "aktivan odmah" in run("rjecnik.py", "dodaj", "esef", "SF").stdout
    r = run("rjecnik.py", "popis")
    assert "Ivan Horvat" in r.stdout and "✓ esef → SF" in r.stdout
    assert (podaci / "rjecnik.json").exists()
    assert "Isključen" in run("rjecnik.py", "zaboravi", "esef").stdout
    assert "Maknut pojam" in run("rjecnik.py", "zaboravi", "Ivan Horvat").stdout
    r = run("rjecnik.py", "popis")
    assert "· esef → SF" in r.stdout and "isključen" in r.stdout
    r = run("rjecnik.py", "zaboravi", "Kutina", ok=False)
    assert r.returncode != 0 and "osnovnom popisu" in r.stderr
    r = run("rjecnik.py", "zaboravi", "nepostoji", ok=False)
    assert r.returncode != 0 and "nije u rječniku" in r.stderr


# ---------------------------------------------------------------- cijeli put: ispravak → render → novi video
@pytest.fixture
def projekt(tmp_path):
    """Probni reel u kojem je whisper krivo čuo „Sunčanom" i „Kutine" (malo slovo)."""
    clips = tmp_path / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    proj = tmp_path / "projekt A"
    run("prepare.py", clips, "--out", proj)
    pj = load(proj / "project.json")
    mock = load(FIX / "mock_words.json")
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    for w in words:
        w["w"] = {"Kutine.": "kutine.", "Sunčanom": "sunčanon"}.get(w["w"], w["w"])
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj)
    return proj


def claude_fixes(proj):
    edit = load(proj / "edit.json")
    for s in edit["odsjecci"]:
        s["tekst"] = s["tekst"].replace("kutine.", "Kutine.").replace("sunčanon", "Sunčanom")
    save(proj / "edit.json", edit)


def copy_project(src, dst):
    dst.mkdir()
    for f in ("project.json", "transcript.json", "source.mp4"):
        shutil.copy(src / f, dst / f)


def test_end_to_end_render_learns_and_next_plan_corrects(projekt, tmp_path):
    claude_fixes(projekt)
    out = run("render.py", projekt, "--brzo").stdout
    assert "Rječnik naučio" not in out                       # viđeno tek jednom
    assert len(rjecnik.load()["ispravci"]) == 2
    b = tmp_path / "projekt B"                               # drugi video, isti ispravci
    copy_project(projekt, b)
    run("plan.py", b)
    claude_fixes(b)
    out = run("rjecnik.py", "nauci", b).stdout
    assert "Rječnik naučio: sunčanon → Sunčanom" in out and "Rječnik naučio: kutine → Kutine" in out
    c = tmp_path / "projekt C"                               # treći video: Shofe ispravi sam
    copy_project(projekt, c)
    out = run("plan.py", c).stdout
    assert "Rječnik ispravio 2 riječi" in out
    txt = (c / "transcript.txt").read_text(encoding="utf-8")
    assert "iz Kutine." in txt and "u Sunčanom putu!" in txt and "[rječnik: Kutine]" in txt
    edit = load(c / "edit.json")
    assert any(s.get("rjecnik") for s in edit["odsjecci"])
    out = run("render.py", c, "--brzo").stdout
    srt = next(c.glob("reel_v*_pregled.srt")).read_text(encoding="utf-8-sig")
    assert "Kutine." in srt and "Sunčanom" in srt and "sunčanon" not in srt
    # plan bez rječnika i primijeni na stari projekt
    d = tmp_path / "projekt D"
    copy_project(projekt, d)
    run("plan.py", d, "--bez-rjecnika")
    assert "sunčanon" in load(d / "edit.json")["odsjecci"][-1]["tekst"]
    assert "(proba" in run("rjecnik.py", "primijeni", d, "--proba").stdout
    assert "sunčanon" in load(d / "edit.json")["odsjecci"][-1]["tekst"]
    run("rjecnik.py", "primijeni", d)
    assert "Sunčanom" in load(d / "edit.json")["odsjecci"][-1]["tekst"]
    assert "Nema ničega" in run("rjecnik.py", "primijeni", d).stdout


def test_broken_vocabulary_file_never_breaks_render(projekt, podaci):
    podaci.mkdir(parents=True, exist_ok=True)
    (podaci / "rjecnik.json").write_text("{pokvareno", encoding="utf-8")
    claude_fixes(projekt)
    run("render.py", projekt, "--brzo")
    assert rjecnik.load()["ispravci"]                       # pokvarena datoteka zamijenjena novom
