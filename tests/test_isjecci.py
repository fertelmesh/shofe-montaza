"""M3.1: kandidati za isječke iz dulje snimke (isjecci.py → isjecci.json).

Probna snimka je izmišljeni dio epizode Sunčani4M (tests/fixtures/isjecci_razgovor.json): četiri bloka
su prirodni isječci (jak početak, zaokružena misao), a ostali su čavrljanje, lutanje, nedovršena
priča i odjava. Shofe mora predložiti upravo ta četiri, s granicama na cijelim rečenicama.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import isjecci as I  # noqa: E402
from sadrzaj import SENT_END  # noqa: E402

RAZGOVOR = json.loads((FIX / "isjecci_razgovor.json").read_text(encoding="utf-8"))


def run(*args, code=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / "isjecci.py"), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if code is not None:
        assert r.returncode == code, f"isjecci.py {args} → {r.returncode}:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def make_words(ponavljanja=1):
    """Blokovi → riječi (trajanje po broju slova, govornik G1/G2) + [(blok, od, do)]."""
    words, blocks, t = [], [], 0.5
    for _ in range(ponavljanja):
        for b in RAZGOVOR["blokovi"]:
            b0 = t
            for g, text, pause in b["recenice"]:
                for tok in text.split():
                    d = 0.10 + 0.055 * len(tok)
                    words.append({"w": tok, "s": round(t, 3), "e": round(t + d, 3), "p": 0.95,
                                  "g": "G1" if g == "A" else "G2"})
                    t += d + 0.06
                t += pause - 0.06
            blocks.append((b, b0, words[-1]["e"]))
    return words, blocks, t


def write_project(proj, teme=True, trenuci=()):
    proj.mkdir(parents=True, exist_ok=True)
    words, blocks, end = make_words()
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    save(proj / "project.json", {"fps": 30, "duration": round(end + 0.5, 3), "clips": []})
    if teme or trenuci:
        save(proj / "analiza.json", {
            "trajanje": round(end + 0.5, 3),
            "teme": [{"od": round(a, 2), "do": round(c, 2), "naslov": b["tema"], "sazetak": ""}
                     for b, a, c in blocks] if teme else [],
            "trenuci": list(trenuci)})
    return words, blocks


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def block_of(c, blocks):
    """Blok s kojim se isječak najviše preklapa i udio isječka u njemu."""
    best = max(blocks, key=lambda x: overlap(c["od"], c["do"], x[1], x[2]))
    return best[0]["oznaka"], overlap(c["od"], c["do"], best[1], best[2]) / (c["do"] - c["od"])


DOBRI = {b["oznaka"] for b in RAZGOVOR["blokovi"] if b["dobar"]}


@pytest.fixture
def projekt(tmp_path):
    proj = tmp_path / "isječci čćž" / "shofe projekt"
    words, blocks = write_project(proj)
    return proj, words, blocks


def ocijeni_sve(proj, ocjene=None):
    data = load(proj / "isjecci.json")
    for n, c in enumerate(data["isjecci"]):
        c["ocjena"] = (ocjene or {}).get(c["id"], 8 - n)
        c["razlog"] = "Jak početak i jasna poanta koja stoji sama za sebe."
        c["naslov"] = "Probni naslov"
        c["hook"] = "Najveća greška kod klime"
    save(proj / "isjecci.json", data)
    return data


# ---------------------------------------------------------------- dijelovi
def test_mnozina():
    assert [I.isjecaka(n) for n in (1, 2, 4, 5, 11, 12, 21, 22, 25)] == [
        "isječak", "isječka", "isječka", "isječaka", "isječaka", "isječaka", "isječak", "isječka", "isječaka"]


def test_fmt():
    assert I.fmt(5) == "0:05" and I.fmt(83.4) == "1:23" and I.fmt(3725) == "1:02:05"


# ---------------------------------------------------------------- prijedlozi
@pytest.mark.parametrize("teme", [True, False], ids=["s_temama", "bez_analize"])
def test_predlozi_pogodi_dobre_blokove(tmp_path, teme):
    proj = tmp_path / "p"
    words, blocks = write_project(proj, teme=teme)
    r = run(proj, code=1)  # 1 = čeka Claudeove ocjene
    assert "Claude:" in r.stdout and "4 isječka" in r.stdout
    data = load(proj / "isjecci.json")
    cs = data["isjecci"]
    assert [c["id"] for c in cs] == ["K1", "K2", "K3", "K4"]
    found = set()
    for c in cs:
        oznaka, share = block_of(c, blocks)
        assert oznaka in DOBRI, f"{c['id']} je u lošem bloku {oznaka}: {c['tekst']}"
        assert share > 0.97, f"{c['id']} izlazi iz bloka {oznaka}: {c['tekst']}"
        found.add(oznaka)
        assert 20 <= c["trajanje"] <= 60
        a, b = c["rijeci"]
        # počinje na početku rečenice (interpunkcija ili duga pauza prije)
        assert a == 0 or SENT_END.search(words[a - 1]["w"]) or words[a]["s"] - words[a - 1]["e"] >= 0.8
        assert SENT_END.search(words[b]["w"])                   # završava krajem rečenice
        assert c["ocjena"] is None and c["status"] == "prijedlog" and c["heuristika"]["ocjena"] > 7
        assert c["tekst"].startswith(c["pocetak"])
    assert found == DOBRI
    # cijeli blok, ne samo dio: početak i kraj bloka su u isječku
    for c in cs:
        oznaka, _ = block_of(c, blocks)
        blok = next(b for b in RAZGOVOR["blokovi"] if b["oznaka"] == oznaka)
        assert c["pocetak"] == blok["recenice"][0][1]
        assert c["tekst"].endswith(blok["recenice"][-1][1])
    assert (proj / "isjecci.txt").read_text(encoding="utf-8").count("│") > 10
    if teme:
        assert {c["tema"] for c in cs} == {b["tema"] for b in RAZGOVOR["blokovi"] if b["dobar"]}
        assert set(cs[0]["govornici"]) <= {"G1", "G2"}


def test_nikad_ne_pocinje_nastavkom(projekt):
    proj, words, _ = projekt
    sn = I.ucitaj(proj)
    for h, a, b in I.svi_prozori(sn):
        assert not sn.nastavlja(a), I._text(words, a, a + 5)
        assert (a == 0 or SENT_END.search(words[a - 1]["w"]) or words[a]["s"] - words[a - 1]["e"] >= 0.8
                or words[a]["g"] != words[a - 1]["g"])
    # „A zaboravljaju…" i „Zato uvijek pitajte…" nastavljaju prethodnu rečenicu, „A onda smo…" iza 1,8 s ne
    starts = {I._text(words, i, i + 1) for i in range(len(words)) if sn.nastavlja(i) and SENT_END.search(words[i - 1]["w"])}
    assert "A zaboravljaju" in starts and "Zato uvijek" in starts
    assert "A onda" not in starts


def test_losi_dijelovi_nisko(projekt):
    proj, words, blocks = projekt
    sn = I.ucitaj(proj)
    pro = I.svi_prozori(sn)
    best = max(h for h, a, b in pro)
    for h, a, b in pro:
        c = {"od": words[a]["s"], "do": words[b]["e"]}
        oznaka, share = block_of(c, blocks)
        if share > 0.6 and oznaka not in DOBRI:
            assert h < best - 2.5, f"loš blok {oznaka} ima {h}: {I._text(words, a, b)}"
    # pola dobrog bloka (završava prije „To je savjet…") je slabije od cijelog
    h_cijeli = next(h for h, a, b in pro if I._text(words, a, a + 1) == "Znate li"
                    and words[b]["w"] == "eura." and words[b - 1]["w"] == "stotine")
    h_pola = next(h for h, a, b in pro if I._text(words, a, a + 1) == "Znate li" and words[b]["w"] == "ugradnju."
                  and words[b - 1]["w"] == "na")
    assert h_cijeli > h_pola + 1


def test_trenuci_dizu_ocjenu(tmp_path):
    words, blocks, _ = make_words()
    koncert = next((a, c) for b, a, c in blocks if b["oznaka"] == "prvi_koncert")
    proj = tmp_path / "p"
    write_project(proj, trenuci=[{"od": koncert[0], "do": koncert[0] + 4, "vrsta": "emocija", "ocjena": 5,
                                  "opis": "prvi koncert"},
                                 {"od": koncert[1] - 6, "do": koncert[1], "vrsta": "poanta", "ocjena": 5,
                                  "opis": "zajednica"}])
    run(proj, code=1)
    cs = load(proj / "isjecci.json")["isjecci"]
    assert block_of(cs[0], blocks)[0] == "prvi_koncert"
    assert any("najjači trenutak 5/5" in r for r in cs[0]["heuristika"]["razlozi"])


def test_predlozi_ne_brise_postojece(projekt):
    proj, _, _ = projekt
    run(proj, "predlozi", code=1)
    ocijeni_sve(proj)
    r = run(proj, "predlozi", code=1)
    assert "već postoji" in r.stderr
    assert load(proj / "isjecci.json")["isjecci"][0]["ocjena"] is not None
    run(proj, "predlozi", "--ponovo", code=1)
    assert load(proj / "isjecci.json")["isjecci"][0]["ocjena"] is None


def test_kratka_snimka(tmp_path):
    proj = tmp_path / "p"
    write_project(proj)
    r = run(proj, "predlozi", "--min", "200", "--max", "300", code=1)
    assert "Nema nijednog niza" in r.stdout


# ---------------------------------------------------------------- Claudeove ocjene i provjera
def test_provjeri_trazi_ocjene_i_poreda(projekt):
    proj, words, blocks = projekt
    run(proj, code=1)
    r = run(proj, "provjeri", code=1)
    assert "nema Claudeove ocjene" in r.stdout and "nema razloga" in r.stdout
    data = load(proj / "isjecci.json")
    ids = [c["id"] for c in data["isjecci"]]
    ocjene = {ids[0]: 6, ids[1]: 9, ids[2]: 11, ids[3]: 7}
    ocijeni_sve(proj, ocjene)
    r = run(proj, code=1)  # bez naredbe kad datoteka postoji = provjeri
    assert "ocjena mora biti broj 1–10" in r.stdout
    data = load(proj / "isjecci.json")
    next(c for c in data["isjecci"] if c["id"] == ids[2])["ocjena"] = 8
    data["isjecci"][0]["razlog"] = "Prva rečenica. Druga rečenica."
    data["isjecci"][1]["hook"] = "jedan dva tri četiri pet šest sedam osam devet"
    save(proj / "isjecci.json", data)
    r = run(proj, "provjeri", code=0)
    assert "jedna rečenica" in r.stdout and "hook ima 9 riječi" in r.stdout
    data = load(proj / "isjecci.json")
    assert [c["id"] for c in data["isjecci"]] == [ids[1], ids[2], ids[3], ids[0]]  # 9, 8, 7, 6
    assert f"Za objavu (ocjena ≥ 7): {ids[1]}, {ids[2]}, {ids[3]}" in r.stdout
    txt = (proj / "isjecci.txt").read_text(encoding="utf-8")
    assert "Claude 9/10" in txt and "zašto:" in txt and "hook:" in txt
    assert txt.index(ids[1]) < txt.index(ids[0])


def test_rucne_granice_se_poravnaju(projekt):
    proj, words, blocks = projekt
    run(proj, code=1)
    data = ocijeni_sve(proj)
    c = data["isjecci"][0]
    a, b = c["rijeci"]
    # Claude pomakne početak usred druge rečenice i kraj usred zadnje
    c["od"] = round((words[a + 12]["s"] + words[a + 12]["e"]) / 2, 2)
    c["do"] = round(words[b - 2]["e"] - 0.01, 2)
    save(proj / "isjecci.json", data)
    r = run(proj, "provjeri", code=0)
    assert "granice poravnate na cijele rečenice" in r.stdout
    c2 = next(x for x in load(proj / "isjecci.json")["isjecci"] if x["id"] == c["id"])
    a2, b2 = c2["rijeci"]
    assert a < a2 and SENT_END.search(words[a2 - 1]["w"])
    assert b2 == b  # kraj se proširi do kraja rečenice
    assert c2["ocjena"] == c["ocjena"] and c2["naslov"] == "Probni naslov"
    assert c2["trajanje"] < c["trajanje"]


def test_dodaj_umjesto_i_greske(projekt):
    proj, words, blocks = projekt
    run(proj, code=1)
    ocijeni_sve(proj)
    r = run(proj, "dodaj", "--od", "Kad smo kod toga", "--do", "drugi put", code=0)
    assert "Dodan K5" in r.stdout
    data = load(proj / "isjecci.json")
    k5 = next(c for c in data["isjecci"] if c["id"] == "K5")
    assert k5["izvor"] == "claude" and block_of(k5, blocks)[0] == "nedovrseno"
    assert k5["heuristika"]["ocjena"] < 6 and k5["ocjena"] is None
    run(proj, "provjeri", code=1)  # K5 još nema ocjenu
    # Claude skrati K1 na prve tri rečenice istog bloka
    k1 = next(c for c in data["isjecci"] if c["id"] == "K1")
    blok = next(b for b in RAZGOVOR["blokovi"] if b["oznaka"] == block_of(k1, blocks)[0])
    od = " ".join(blok["recenice"][1][1].split()[:3])
    do = " ".join(blok["recenice"][-2][1].split()[-2:])
    r = run(proj, "dodaj", "--od", od, "--do", do, "--umjesto", "k1", code=0)
    assert "K1 sada" in r.stdout
    k1b = next(c for c in load(proj / "isjecci.json")["isjecci"] if c["id"] == "K1")
    assert k1b["pocetak"] == blok["recenice"][1][1] and k1b["naslov"] == "Probni naslov"
    assert k1b["ocjena"] is None and k1b["trajanje"] < k1["trajanje"]
    r = run(proj, "dodaj", "--od", "ovo nitko nije rekao", code=1)
    assert "nije u transkriptu" in r.stderr
    r = run(proj, "dodaj", "--od", "Bok", "--umjesto", "K99", code=1)
    assert "nema isječka K99" in r.stderr


def test_odobri_odbaci_novi(tmp_path):
    proj = tmp_path / "p"
    write_project(proj)
    run(proj, "predlozi", "--broj", "2", code=1)
    first = load(proj / "isjecci.json")["isjecci"]
    assert len(first) == 2
    r = run(proj, "novi", "--broj", "2", code=1)
    assert "K3, K4" in r.stdout
    data = load(proj / "isjecci.json")
    assert len(data["isjecci"]) == 4
    for x in data["isjecci"][2:]:
        for y in first:
            assert overlap(x["od"], x["do"], y["od"], y["do"]) < 1.0
    ocijeni_sve(proj)
    run(proj, "odobri", "K1,3", code=0)
    r = run(proj, "odbaci", "K2", "--razlog", "već smo objavili nešto slično", code=0)
    assert "Odobreni isječci: K1, K3" in r.stdout
    data = load(proj / "isjecci.json")
    st = {c["id"]: c["status"] for c in data["isjecci"]}
    assert st == {"K1": "odobren", "K2": "odbacen", "K3": "odobren", "K4": "prijedlog"}
    assert data["isjecci"][-1]["id"] == "K2"  # odbačeni na kraju
    k2 = data["isjecci"][-1]
    k2["ocjena"] = None  # odbačenom ne treba ocjena
    save(proj / "isjecci.json", data)
    run(proj, "provjeri", code=0)
    txt = (proj / "isjecci.txt").read_text(encoding="utf-8")
    assert "✗ odbačen" in txt and "Marko:  već smo objavili" in txt and "✓ ODOBREN" in txt
    # novi kandidati se ne preklapaju ni s odbačenima; fixture ima samo 4 dobra mjesta
    r = run(proj, "novi", code=None)
    for c in load(proj / "isjecci.json")["isjecci"][4:]:
        assert all(overlap(c["od"], c["do"], y["od"], y["do"]) <= 0.15 * (c["do"] - c["od"]) + 0.01
                   for y in data["isjecci"])
    run(proj, "vrati", "K2", code=0)
    assert next(c for c in load(proj / "isjecci.json")["isjecci"] if c["id"] == "K2")["status"] == "prijedlog"
    r = run(proj, "odobri", "K42", code=1)
    assert "nema isječka K42" in r.stderr


def test_sat_snimke_brzo():
    """Epizoda od ~60 min: svi prozori i odabir u nekoliko sekundi."""
    words, blocks, end = make_words(ponavljanja=21)
    an = {"trajanje": end, "teme": [{"od": a, "do": c, "naslov": b["tema"]} for b, a, c in blocks],
          "trenuci": [{"od": a, "do": a + 5, "vrsta": "hook", "ocjena": 4} for b, a, c in blocks if b["dobar"]],
          "odsjecci": [{"od": a, "do": c, "glasnoca_db": -20.0, "tempo": "normalno"} for b, a, c in blocks]}
    assert end > 3600
    t = time.time()
    sn = I.Snimka(words, an)
    chosen = I.odaberi(sn, I.svi_prozori(sn), 10)
    assert time.time() - t < 30
    assert len(chosen) == 10
    for a, b in chosen:
        oznaka, share = block_of({"od": words[a]["s"], "do": words[b]["e"]}, blocks)
        assert oznaka in DOBRI and share > 0.97
