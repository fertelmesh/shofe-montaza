"""Prijedlog efekata po tekstu (M5.3): pravila iz teksta, gustoća, teme/trenuci iz analiza.json, Claudeov
pregled i `primijeni` u jednom koraku povijesti."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import efekti  # noqa: E402
import predlozi  # noqa: E402


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    import make_predlozi as M
    return M.make_projekt(tmp_path_factory.mktemp("predlozi čž"), SCRIPTS)


def ulaz(proj):
    return load(proj / "transcript.json")["words"], load(proj / "edit.json"), load(proj / "project.json")


def by_rule(data):
    return {(p["pravilo"], p["tip"]): p for p in data["prijedlozi"]}


def uzeti(data):
    return {p["tip"] for p in data["prijedlozi"] if p["uzmi"]}


def word_idx(words, w):
    return next(i for i, x in enumerate(words) if x["w"].strip(".,!?") == w)


def test_pravila_iz_teksta(projekt):
    words, edit, pj = ulaz(projekt)
    data = predlozi.napravi(projekt, words, edit, pj, analiza={})
    r = by_rule(data)
    assert set(r) >= {("predstavljanje", "zamrzni"), ("nabrajanje", "rolete"), ("nabrajanje", "vrata"),
                      ("naglasak", "guranje"), ("iznenađenje", "vertigo"), ("prošlost", "film"),
                      ("brojka", "trzaj"), ("otkrivanje", "pad")}
    assert r[("predstavljanje", "zamrzni")]["parametri"]["oznaka"] == "Marko iz Kutine"
    # trzaj točno na brojci i jedinici, ne prije
    t = r[("brojka", "trzaj")]
    i200, ieur = word_idx(words, "200"), word_idx(words, "eura")
    assert t["od"] <= words[i200]["s"] and t["do"] >= words[ieur]["e"] and t["od"] > words[i200 - 1]["s"]
    # prijelazi na rezu ispred rečenice: od = kraj kadra prije, do = početak kadra s „Prvo“
    rol = r[("nabrajanje", "rolete")]
    ip = word_idx(words, "Prvo")
    assert rol["od"] < rol["do"] <= words[ip]["s"] and rol["vrijeme"].startswith("rez")
    # Shofeov odabir (22 s videa: kamera 3, prijelaz 1, boja 1)
    assert data["najvise"] == {"kamera": 3, "prijelaz": 1, "boja": 1}
    assert uzeti(data) == {"zamrzni", "rolete", "guranje", "film", "trzaj"}
    ne = {p["tip"]: p["zasto_ne"] for p in data["prijedlozi"] if not p["uzmi"]}
    assert "preblizu" in ne["vertigo"] or "dosta" in ne["vertigo"]
    assert "dosta" in ne["vrata"]
    # u planu: efekti kamere 3 s razmaka, nijedan se ne preklapa, sve u videu
    v = predlozi.Video(words, edit, pj)
    e2 = copy.deepcopy(edit)
    e2["efekti"] = [{"id": f"E{k}", "tip": p["tip"], "od": p["od"], "do": p["do"], "parametri": p["parametri"]}
                    for k, p in enumerate(data["prijedlozi"], 1) if p["uzmi"]]
    fx, notes = efekti.plan(e2, v.cuts, pj["fps"], v.total)
    assert len(fx) == 5 and not [n for n in notes if "preskočen" in n]
    kam = sorted(x["s"] for x in fx if efekti.TIPOVI[x["tip"]]["skupina"] == "kamera")
    assert all(b - a >= predlozi.KAMERA_RAZMAK for a, b in zip(kam, kam[1:]))
    # tekst za Claudea: svaka rečenica gotovog videa s vremenom
    assert len(data["recenice"]) == 10 and data["recenice"][7]["tekst"].startswith("Tako uštedite")


def test_gustoca(projekt):
    words, edit, pj = ulaz(projekt)
    malo = predlozi.napravi(projekt, words, edit, pj, predlozi.GUSTOCA["malo"], analiza={})
    puno = predlozi.napravi(projekt, words, edit, pj, predlozi.GUSTOCA["puno"], analiza={})
    assert len(uzeti(malo)) < 5 and "zamrzni" in uzeti(malo)          # najjači znak ostaje
    assert "vrata" in uzeti(puno) and len([p for p in puno["prijedlozi"] if p["uzmi"]]) == 6
    # i kod „puno“ vertigo 2,6 s iza guranja ne prolazi (3 s razmaka)
    assert not by_rule(puno)[("iznenađenje", "vertigo")]["uzmi"]


def test_mirni_stil_teme_i_trenuci(projekt):
    words, edit, pj = ulaz(projekt)
    edit = dict(edit, stil="cisto")
    i_nek, i_got, i_dan = word_idx(words, "Nekad"), word_idx(words, "gotovo"), word_idx(words, "Danas")
    analiza = {"teme": [{"od": 0.0, "do": words[i_nek]["s"] - 0.5, "naslov": "Uvod i priprema"},
                        {"od": words[i_nek]["s"], "do": words[-1]["e"], "naslov": "Pranje filtera"}],
               "trenuci": [{"od": words[i_got - 1]["s"], "do": words[i_got + 4]["e"], "vrsta": "smijeh", "ocjena": 5,
                            "opis": "šala na kraju"},
                           {"od": words[i_dan]["s"], "do": words[i_dan + 5]["e"], "vrsta": "hook", "ocjena": 5,
                            "opis": "obećanje"}]}
    data = predlozi.napravi(projekt, words, edit, pj, analiza=analiza)
    r = by_rule(data)
    tema = r[("nova tema", "pretapanje")]                         # mirni stil: pretapanje, ne zamah
    assert "Pranje filtera" in tema["razlog"] and tema["do"] <= words[i_nek]["s"]
    assert ("trenutak: hook", "trzaj") in r and r[("trenutak: hook", "trzaj")]["ocjena"] == 8.0
    assert ("trenutak: smijeh", "pad") in r
    assert r[("otkrivanje", "pad")]["ocjena"] == 6.5               # unutar trenutka s ocjenom ≥ 4: +1
    energ = predlozi.napravi(projekt, words, dict(edit, stil="udarno"), pj, analiza=analiza)
    assert ("nova tema", "zamah") in by_rule(energ)


def test_hook_pjesma_i_postojeci_efekti(projekt):
    words, edit, pj = ulaz(projekt)
    i200 = word_idx(words, "200")
    e = dict(edit, hook="Klima kao nova", hook_trajanje=3.0)
    r = by_rule(predlozi.napravi(projekt, words, e, pj, analiza={}))
    assert not r[("predstavljanje", "zamrzni")]["uzmi"] and "hook" in r[("predstavljanje", "zamrzni")]["zasto_ne"]
    # rečenica s brojkom je pjesma benda: nema prijedloga u njoj
    s = next(x for x in words if x["w"] == "Tako")["s"] - 0.1
    e = dict(edit, nastupi=[{"id": "N1", "od": s, "do": words[i200 + 2]["e"] + 0.1, "zadrzi": True}])
    assert ("brojka", "trzaj") not in by_rule(predlozi.napravi(projekt, words, e, pj, analiza={}))
    # postojeći trzaj na istom mjestu: Shofe ne predlaže drugi zum preko njega
    e = dict(edit, efekti=[{"id": "E1", "tip": "pad", "od": words[i200]["s"] - 0.3, "do": words[i200]["s"] + 0.6}])
    d = predlozi.napravi(projekt, words, e, pj, analiza={})
    t = by_rule(d)[("brojka", "trzaj")]
    assert not t["uzmi"] and "E1" in t["zasto_ne"] and d["postojeci"] == ["E1 pad"]


def test_pregled_primijeni_i_vrati(projekt, tmp_path):
    import shutil
    proj = tmp_path / "kopija"
    shutil.copytree(projekt, proj)
    r = run("efekti.py", proj, "predlozi")
    assert "Shofe bi uzeo 5" in r.stdout and (proj / "efekti_prijedlog.txt").exists()
    r = run("efekti.py", proj, "predlozi", "primijeni", ok=False)
    assert r.returncode == 1 and "pregledao_claude" in r.stderr
    assert not load(proj / "edit.json").get("efekti")
    # Claudeov pregled: film ne (savjet nije priča iz prošlosti), drukčija oznaka, vertigo umjesto guranja,
    # prijelaz pretvoren u zum ne smije proći
    f = proj / "efekti_prijedlog.json"
    d = load(f)
    by = by_rule(d)
    by[("prošlost", "film")]["uzmi"] = False
    by[("predstavljanje", "zamrzni")]["parametri"]["oznaka"] = "Marko, SF klima"
    by[("naglasak", "guranje")]["tip"] = "vertigo"
    by[("nabrajanje", "rolete")]["tip"] = "trzaj"
    d["pregledao_claude"] = True
    save(f, d)
    r = run("efekti.py", proj, "predlozi", "primijeni")
    assert "Dodano 3 efekta" in r.stdout and "prijelaz ide samo na rez" in r.stdout
    fx = load(proj / "edit.json")["efekti"]
    assert [x["tip"] for x in fx] == ["zamrzni", "vertigo", "trzaj"]
    assert [x["id"] for x in fx] == ["E1", "E2", "E3"]
    assert fx[0]["parametri"]["oznaka"] == "Marko, SF klima"
    assert all(x["naredba"].startswith(x["tip"] + " (prijedlog P") for x in fx)
    assert {p["primijenjen"] for p in load(f)["prijedlozi"] if p.get("primijenjen")} == {"E1", "E2", "E3"}
    # ponovno primijeni ne duplicira; izričit P (bez pregleda) dodaje samo njega
    r = run("efekti.py", proj, "predlozi", "primijeni")
    assert "Ništa nije dodano" in r.stdout and len(load(proj / "edit.json")["efekti"]) == 3
    pv = by_rule(load(f))[("nabrajanje", "vrata")]["id"]
    r = run("efekti.py", proj, "predlozi", "primijeni", pv)
    assert "Dodano 1 efekt " in r.stdout
    assert any(x["tip"] == "vrata" for x in load(proj / "edit.json")["efekti"])
    # svaki primijeni je jedan korak povijesti: dva `vrati` = nazad na bez efekata
    run("uredi.py", proj, "vrati")
    assert len(load(proj / "edit.json")["efekti"]) == 3
    run("uredi.py", proj, "vrati")
    assert not load(proj / "edit.json").get("efekti")
    # popis i nepoznat P
    assert "P1" in run("efekti.py", proj, "predlozi", "popis").stdout
    r = run("efekti.py", proj, "predlozi", "primijeni", "P99", ok=False)
    assert r.returncode == 1 and "P99" in r.stderr
    r = run("efekti.py", proj, "predlozi", "--gustoca", "jako", ok=False)
    assert r.returncode == 1


def test_primijenjeni_efekti_rade_u_renderu(projekt, tmp_path):
    """Shofeov odabir upisan i slika jedne sličice usred svakog efekta se renderira (zum prema licu)."""
    pytest.importorskip("cv2")
    import shutil
    proj = tmp_path / "render"
    shutil.copytree(projekt, proj)
    run("efekti.py", proj, "predlozi")
    r = run("efekti.py", proj, "predlozi", "primijeni", "--bez-pregleda")
    assert "Dodano 5 efekata" in r.stdout
    edit = load(proj / "edit.json")
    assert all(x["parametri"].get("lice") for x in edit["efekti"] if x["tip"] in ("zamrzni", "guranje", "trzaj"))
    words, _, pj = ulaz(proj)
    v = predlozi.Video(words, edit, pj)
    fx, _ = efekti.plan(edit, v.cuts, pj["fps"], v.total)
    tt = ",".join(f"{(x['s'] + x['e']) / 2:.2f}" for x in fx)
    run("render.py", proj, "--kadar", tt)
    assert (proj / "kadrovi.png").exists()
