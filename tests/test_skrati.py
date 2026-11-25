"""M2.3: „skrati na N sekundi" (uredi.py skrati): cijele misli, važnost, naprtnjača, pravo trajanje.

Probni projekt je izmišljeni reel SF klima iz tests/fixtures/naredbe_sadrzaj.json (isti kao za M2.2):
plan.py već izbaci dva odbačena pokušaja uvoda, a `skrati` smije samo izbacivati cijele misli.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import skrati as sk  # noqa: E402
from test_sadrzaj import load, make_words, run, save, video_words, write_project  # noqa: E402
from uredi import parse_target  # noqa: E402

# Claudeove ocjene za scenarij „skrati na 20 s, najvažnije su cijena i održavanje"
OCJENE = "1:4,2:2,3:5,4:3,5:2,6:1,7:1,8:5,9:4,10:3,11:1,12:4"


@pytest.fixture(scope="module")
def baza(tmp_path_factory):
    proj = tmp_path_factory.mktemp("skrati čćž") / "shofe_projekt"
    write_project(proj)
    return proj


@pytest.fixture
def projekt(baza, tmp_path):
    p = tmp_path / "projekt s razmakom"
    shutil.copytree(baza, p)
    return p


def text_of(proj):
    return " ".join(w["t"] for w in video_words(proj)[0] if w["t"])


def kept_sentences(proj):
    """Za svaku rečenicu testnog skupa: 'cijela' / 'nema' / 'dio' u gotovom videu."""
    words, bounds, _ = make_words()
    vid = {w["i"] for w in video_words(proj)[0]}
    out = []
    for a, b in bounds:
        n = sum(i in vid for i in range(a, b + 1))
        out.append("cijela" if n == b - a + 1 else "nema" if n == 0 else "dio")
    return out


# ---------------------------------------------------------------- dijelovi
def test_parse_target():
    assert parse_target(["60"], 90) == 60
    assert parse_target(["1:00"], 90) == 60
    assert parse_target(["na", "45s"], 90) == 45
    assert parse_target(["za", "15"], 90) == 75
    assert parse_target(["0:59,5"], 90) == 59.5
    with pytest.raises(ValueError):
        parse_target(["šezdeset"], 90)
    with pytest.raises(ValueError):
        parse_target(["za", "2:00"], 90)


def test_parse_ocjene():
    assert sk.parse_ocjene("3:5, 7-9:1", 10) == {3: 5, 7: 1, 8: 1, 9: 1}
    assert sk.parse_ocjene("2=4.5", 3) == {2: 4.5}
    for bad in ("3:7", "11:2", "x:3", "5-3:2"):
        with pytest.raises(sk.sadrzaj.Greska):
            sk.parse_ocjene(bad, 10)


def mk(texts, gap=0.5):
    words, t = [], 0.0
    for text in texts:
        for tok in text.split():
            words.append({"w": tok, "s": round(t, 3), "e": round(t + 0.3, 3)})
            t += 0.35
        t += gap
    return words


def test_misli_i_veze():
    words = mk(["Koliko košta servis?", "Sto eura.", "Drugo, filter.", "Čistite ga svaki mjesec.",
                "A to je besplatno.", "Zato zovite nas.", "Pratite nas!"])
    misli, lanci = sk.build_thoughts(words, list(range(len(words))), 0.2)
    texts = [m.tekst for m in misli]
    assert texts == ["Koliko košta servis? Sto eura.", "Drugo, filter. Čistite ga svaki mjesec.",
                     "A to je besplatno.", "Zato zovite nas.", "Pratite nas!"]
    assert lanci == [[0], [1, 2, 3], [4]]  # „A to…" i „Zato…" ne mogu bez prethodne


def test_misao_se_nastavlja_preko_pauze():
    words = mk(["Kad dođe ljeto", "onda svi zovu odjednom.", "Nazovite ranije."], gap=1.0)
    misli, _ = sk.build_thoughts(words, list(range(len(words))), 0.2)
    assert [m.tekst for m in misli] == ["Kad dođe ljeto onda svi zovu odjednom.", "Nazovite ranije."]


def test_izrezano_razdvaja_misli():
    words = mk(["Jedan dva tri četiri pet."])
    misli, _ = sk.build_thoughts(words, [0, 1, 3, 4], 0.2)  # „tri" je već izrezan
    assert [m.tekst for m in misli] == ["Jedan dva", "četiri pet."]


def test_lanac_samo_pocetak():
    """B je vrijedan, ali ovisi o A: ako stane samo B, ne smije ostati B bez A."""
    words = mk(["Ovo je dugi uvod koji nitko ne treba slušati.", "A ovo je zlatna rečenica.", "Kratko."])
    misli, lanci = sk.build_thoughts(words, list(range(len(words))), 0.0)
    assert lanci == [[0, 1], [2]]
    sk.score(misli, words, ocjene={1: 1, 2: 5, 3: 2})
    keep = sk.choose(misli, lanci, misli[1].trajanje + 0.05)
    assert 1 not in keep
    keep = sk.choose(misli, lanci, misli[0].trajanje + misli[1].trajanje + 0.1)
    assert keep == {0, 1}


def test_obavezno_ne_stane():
    words = mk(["Ovo je jedna duga misao koju moramo zadržati.", "Kratko."])
    misli, lanci = sk.build_thoughts(words, list(range(len(words))), 0.0)
    sk.score(misli, words, obavezno={1})
    assert sk.choose(misli, lanci, 1.0) is None


# ---------------------------------------------------------------- cijeli alat
@pytest.mark.parametrize("n", [12, 15, 20, 30, 40])
def test_svojstva(projekt, n):
    run("uredi.py", projekt, "skrati", n)
    _, dur = video_words(projekt)
    assert dur <= n + 1e-3
    assert dur >= n - 2.5, f"cilj {n} s, a ostalo samo {dur:.1f} s"
    stanje = kept_sentences(projekt)
    assert "dio" not in stanje, stanje                    # nikad pola rečenice
    assert stanje[0:3] == ["nema", "nema", "nema"] or stanje[1:3] == ["nema", "nema"]  # pokušaji ostaju vani
    assert stanje[4] == stanje[5]                          # pitanje „koliko košta?" uvijek s odgovorom
    assert stanje[7] == stanje[8]                          # „Drugo, ugradnja." uz ono što najavljuje
    assert stanje[11] == stanje[12]                        # „Treće, održavanje." isto


def test_claudeove_ocjene(projekt):
    r = run("uredi.py", projekt, "skrati", "20", "--ocjene", OCJENE)
    assert "Claude 5" in r.stdout
    txt = text_of(projekt)
    for must in ("Bok ekipa", "koliko košta klima uređaj? Dobar uređaj", "Treće, održavanje. Filter čistite",
                 "Pratite SF klimu"):
        assert must in txt
    for gone in ("Radimo i subotom", "Ugradnja zimi", "Zimi klima i grije", "Danas vam"):
        assert gone not in txt
    assert video_words(projekt)[1] <= 20


def test_trenutak_iz_analize(projekt):
    words, bounds, _ = make_words()
    a, b = bounds[14]  # „Servis jednom godišnje produljuje život uređaja."
    an = load(projekt / "analiza.json")
    an["trenuci"] = [{"od": words[a]["s"], "do": words[b]["e"], "vrsta": "savjet", "ocjena": 5,
                      "opis": "servis"}]
    save(projekt / "analiza.json", an)
    r = run("uredi.py", projekt, "skrati", "12")
    assert "savjet 5" in r.stdout
    assert "Servis jednom godišnje produljuje život uređaja." in text_of(projekt)


def test_obavezno_i_nebitno(projekt):
    run("uredi.py", projekt, "skrati", "15", "--obavezno", "Zimi klima i grije", "--nebitno", "Bok ekipa")
    txt = text_of(projekt)
    assert "Zimi klima i grije, i to jeftinije od radijatora." in txt
    assert "Bok ekipa" not in txt


def test_samo_izbacuje_i_vrati(projekt):
    before = load(projekt / "edit.json")
    run("uredi.py", projekt, "makni", "--od", "Radimo i subotom", "--cijele-recenice")
    mid = load(projekt / "edit.json")
    vid_before = {w["i"] for w in video_words(projekt)[0]}
    run("uredi.py", projekt, "skrati", "za", "10")
    vid_after = {w["i"] for w in video_words(projekt)[0]}
    assert vid_after < vid_before                          # ništa izbačeno se ne vraća
    run("uredi.py", projekt, "vrati")
    assert load(projekt / "edit.json") == mid
    run("uredi.py", projekt, "vrati")
    assert load(projekt / "edit.json") == before


def test_proba_i_vec_kratko(projekt):
    before = (projekt / "edit.json").read_bytes()
    r = run("uredi.py", projekt, "skrati", "20", "--proba")
    assert "proba" in r.stdout and (projekt / "edit.json").read_bytes() == before
    r = run("uredi.py", projekt, "skrati", "5:00")
    assert "Ništa za skratiti" in r.stdout
    assert (projekt / "edit.json").read_bytes() == before


def test_greske(projekt):
    r = run("uredi.py", projekt, "skrati", "0.5", ok=False)
    assert r.returncode != 0 and "ne stane" in r.stdout + r.stderr
    r = run("uredi.py", projekt, "skrati", "10", "--obavezno", "ovo nitko nije rekao", ok=False)
    assert r.returncode != 0
    r = run("uredi.py", projekt, "skrati", ok=False)
    assert r.returncode != 0 and "na koliko" in r.stdout + r.stderr


def test_brzina(projekt):
    e = load(projekt / "edit.json")
    e["brzina"] = 1.25
    save(projekt / "edit.json", e)
    run("uredi.py", projekt, "skrati", "20")
    _, dur = video_words(projekt)
    assert 17.5 <= dur <= 20


def test_dugi_video_brzo(tmp_path):
    """Sat snimke (~6500 riječi) → skrati na 10 min u razumnom vremenu."""
    import random
    import time
    random.seed(3)
    sents = [s for s, _ in json.loads((ROOT / "tests/fixtures/naredbe_sadrzaj.json").read_text("utf-8"))["recenice"]]
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
    t0 = time.time()
    run("uredi.py", proj, "skrati", "10:00")
    assert time.time() - t0 < 90
    _, dur = video_words(proj)
    assert 590 <= dur <= 600


# ---------------------------------------------------------------- pravi render
def test_render_skrati(tmp_path):
    words, _, end = make_words()
    clip = tmp_path / "klipovi" / "snimka.mp4"
    clip.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=360x640:r=30:d={end + 1:.2f}",
                    "-f", "lavfi", "-i", f"sine=f=220:d={end + 1:.2f}", "-shortest", "-c:v", "libx264",
                    "-preset", "ultrafast", "-c:a", "aac", str(clip)], check=True)
    proj = tmp_path / "shofe_projekt"
    run("prepare.py", clip, "--out", proj)
    write_project(proj, video=True)
    run("uredi.py", proj, "skrati", "20", "--ocjene", OCJENE)
    run("render.py", proj, "--brzo", "--izlaz", "kratko.mp4")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(proj / "kratko.mp4")], capture_output=True, text=True).stdout
    assert float(out) <= 20.2
    ass = (proj / "captions.ass").read_text(encoding="utf-8").lower()
    assert "subotom" not in ass and "filter" in ass and "pratite" in ass
