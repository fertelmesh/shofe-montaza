"""M2.5c: engleski prijevod titlova — Claude prevodi titl po titl, Shofe pamti i piše reel_vN.en.srt."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prijevod  # noqa: E402
import titlovi  # noqa: E402
import verzije  # noqa: E402
from test_titlovi import load, parse_srt, run, save  # noqa: E402

EN = {
    "bok ja sam marko iz kutine": "Hi, I'm Marko from Kutina.",
    "danas vam pokazujem kako očistiti klimu": "Today I'll show you how to clean your air conditioner.",
    "prvi korak je isključiti struju": "Step one: switch off the power.",
    "drugi korak skinite filter i operite ga mlakom vodom": "Step two: take out the filter and wash it in lukewarm water.",
    "to je to vidimo se u sunčanom putu": "That's it, see you on Sunčani put!",
}


def cue(od, do, text):
    return {"od": od, "do": do, "retci": [text]}


def fill(path, table, lang="en"):
    d = load(path)
    for e in d["titlovi"]:
        if not e[lang] and prijevod.key(e["hr"]) in table:
            e[lang] = table[prijevod.key(e["hr"])]
    save(path, d)


# ---------------------------------------------------------------- pravila prevedenih titlova
def test_english_lines_balanced_and_checked():
    cues = [cue(0, 4, "Drugi korak, skinite filter i operite ga mlakom vodom."),
            cue(4.1, 6, "Bok."),
            cue(6.1, 8, "Ovo je jako dugačka rečenica."),
            cue(8.1, 9, "Kratko.")]
    entries = [{"en": "Step two: take out the filter and wash it in the lukewarm water."},
               {"en": "Hi | there."},
               {"en": "Ovo je jako dugačka rečenica."},
               {"en": "This one is far too long to read in a single second, so it should be flagged."}]
    out, errors, warnings = prijevod.build(entries, cues, "en")
    lines = out[0]["retci"]
    assert len(lines) == 2 and all(len(x) <= 42 for x in lines)
    assert lines[0].split()[-1].lower() not in titlovi.WEAK_END_EN     # redak ne završava s „the"/„and"
    assert out[1]["retci"] == ["Hi", "there."]                          # Claudeov prelom s „|"
    assert out[0]["od"] == 0 and out[0]["do"] == 4                      # vremena kao hrvatski titl
    msgs = {i: m for i, m in warnings}
    assert "nije prevedeno" in msgs[2]
    assert "brzo za čitanje" in msgs[3]
    assert not errors
    _, errors, _ = prijevod.build([{"en": "word " * 30}], [cue(0, 7, "x")], "en")
    assert errors and "predugo" in errors[0][1]


def test_memory_survives_new_cuts_and_flags_similar(tmp_path):
    a = [cue(0, 2, "Bok, ja sam Marko iz Kutine."), cue(2.1, 5, "Danas vam pokazujem kako očistiti klimu."),
         cue(5.1, 8, "Drugi korak, skinite filter i operite ga mlakom vodom.")]
    entries, missing, fuzzy = prijevod.sync(tmp_path, a, "en", "reel_v1")
    assert missing == [0, 1, 2] and not fuzzy and (tmp_path / "prijevod_en.json").exists()
    fill(tmp_path / "prijevod_en.json", EN)
    # nova verzija: prvi titl izrezan, treći ispravljen („toplom"), novi titl na kraju
    b = [cue(0, 3, "Danas vam pokazujem kako očistiti klimu!"),
         cue(3.1, 6, "Drugi korak, skinite filter i operite ga toplom vodom."),
         cue(6.1, 8, "Pratite SF klimu.")]
    entries, missing, fuzzy = prijevod.sync(tmp_path, b, "en", "reel_v2")
    assert entries[0]["en"] == EN["danas vam pokazujem kako očistiti klimu"]   # interpunkcija ne smeta
    assert fuzzy == [1] and "provjeri" in entries[1]["napomena"] and entries[1]["en"]
    assert missing == [2]
    data = load(tmp_path / "prijevod_en.json")
    assert "Bok, ja sam Marko iz Kutine." in data["ranije"]                    # izrezano se ne zaboravlja
    # napomena ostaje dok Claude ne promijeni prijevod
    _, _, fuzzy = prijevod.sync(tmp_path, b, "en")
    assert fuzzy == [1]
    data = load(tmp_path / "prijevod_en.json")
    data["titlovi"][1]["en"] = "Step two: take out the filter and wash it in warm water."
    data["titlovi"][2]["en"] = "Follow SF klima."
    save(tmp_path / "prijevod_en.json", data)
    entries, missing, fuzzy = prijevod.sync(tmp_path, b, "en")
    assert not missing and not fuzzy and "napomena" not in entries[1]
    # povratak na staru verziju: svi prijevodi su tu
    entries, missing, _ = prijevod.sync(tmp_path, a, "en")
    assert not missing and entries[0]["en"] == "Hi, I'm Marko from Kutina."


# ---------------------------------------------------------------- na projektu
@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    base = tmp_path_factory.mktemp("prijevod čćž test")
    clips = base / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    p = base / "shofe_projekt"
    run("prepare.py", clips, "--out", p)
    pj = load(p / "project.json")
    mock = load(FIX / "mock_words.json")
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    save(p / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", p, "--stil", "suncani")
    return p


def test_full_flow_render_translate_recut(proj):
    out = run("render.py", proj, "--brzo").stdout
    v1 = verzije.viewed(proj)
    assert "Titlovi (en)" not in out and not list(proj.glob("*.en.srt"))      # bez prijevoda dok se ne traži
    r = run("prijevod.py", proj, ok=False)
    assert r.returncode == 1 and "Treba prevesti" in r.stdout and "Bok, ja sam Marko iz Kutine." in r.stdout
    fill(proj / "prijevod_en.json", EN)
    r = run("prijevod.py", proj, "--format", "oba")
    srt = proj / f"reel_v{v1}_pregled.en.srt"
    assert srt.exists() and (proj / f"reel_v{v1}_pregled.en.vtt").exists() and srt.name in r.stdout
    raw = srt.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    en = parse_srt(raw.decode("utf-8-sig").replace("\r\n", "\n"))
    hr = parse_srt((proj / f"reel_v{v1}_pregled.srt").read_text(encoding="utf-8-sig"))
    assert [(a, b) for a, b, _ in en] == [(a, b) for a, b, _ in hr]                # ista vremena
    assert en[0][2] == ["Hi, I'm Marko from Kutina."] and "Sunčani put" in " ".join(en[-1][2])
    assert all(len(line) <= 42 and len(c[2]) <= 2 for c in en for line in c[2])

    # makni rečenicu + novi render → engleski titlovi nastaju sami, bez ponovnog prevođenja
    run("uredi.py", proj, "makni", "--od", "Prvi korak", "--cijele-recenice")
    out = run("render.py", proj, "--brzo").stdout
    v2 = verzije.viewed(proj)
    srt2 = proj / f"reel_v{v2}_pregled.en.srt"
    assert v2 != v1 and srt2.exists() and f"Titlovi (en): {srt2.name}" in out
    en2 = parse_srt(srt2.read_text(encoding="utf-8-sig"))
    assert len(en2) == len(en) - 1 and "switch off" not in srt2.read_text(encoding="utf-8-sig")

    # Claudeov ispravak teksta → prijevod preuzet uz napomenu; novi tekst → render javi što treba prevesti
    edit = load(proj / "edit.json")
    for s in edit["odsjecci"]:
        s["tekst"] = s["tekst"].replace("mlakom", "toplom").replace("To je to,", "E pa to bi bilo to,")
    save(proj / "edit.json", edit)
    out = run("render.py", proj, "--brzo").stdout
    assert "treba prevesti" in out and "prijevod.py" in out
    r = run("prijevod.py", proj, ok=False)
    assert r.returncode == 1 and "E pa to bi bilo to" in r.stdout and "Preuzeto iz sličnih" in r.stdout
    # starija verzija i dalje radi iz zapamćenih prijevoda
    r = run("prijevod.py", proj, "--verzija", v1)
    assert f"verzija {v1}" in r.stdout


def test_cli_other_language_and_errors(proj):
    r = run("prijevod.py", proj, "--jezik", "engleski", ok=False)
    assert r.returncode != 0 and "kod od 2–3 slova" in r.stderr
    r = run("prijevod.py", proj, "--jezik", "de", "--trenutno", ok=False)
    assert r.returncode == 1 and (proj / "prijevod_de.json").exists()
    d = load(proj / "prijevod_de.json")
    for e in d["titlovi"]:
        e["de"] = "Hallo zusammen."
    save(proj / "prijevod_de.json", d)
    r = run("prijevod.py", proj, "--jezik", "de", "--trenutno", "--ispis")
    assert (proj / "titlovi_trenutno.de.srt").exists() and "de: Hallo zusammen." in r.stdout
    assert prijevod.existing_languages(proj) == ["de", "en"]
    r = run("prijevod.py", proj, "--verzija", 99, ok=False)
    assert "nema verzije 99" in r.stderr
