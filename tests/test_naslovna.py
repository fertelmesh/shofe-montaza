"""M3.4b: naslovna sličica (naslovna.py → <video>.naslovna_9x16.jpg, _16x9.jpg, kandidati, pregled)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import naslovna as N  # noqa: E402


def run(script, *args, code=0):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if code is not None:
        assert r.returncode == code, f"{script} {args} → {r.returncode}:\n{r.stdout}\n{r.stderr}"
    return r


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- bez videa
def test_tokeni_i_isticanje():
    assert N.tokeni("Čista klima za *5 minuta*") == [("ČISTA", False), ("KLIMA", False), ("ZA", False),
                                                    ("5", True), ("MINUTA", True)]
    assert N.tokeni("  ") == []


def test_tekst_stane_u_okvir():
    pytest.importorskip("PIL")
    box = (70, 270, 1010, 700)
    f, lines, lh = N.slozi_tekst("Najveća greška kod čišćenja klime", N.font_datoteka("Montserrat Black"), box)
    assert 1 <= len(lines) <= 3 and len(lines) * lh <= box[3] - box[1]
    assert all(f.getlength(" ".join(w for w, _ in ln)) <= box[2] - box[0] for ln in lines)
    big = N.slozi_tekst("KLIMA", N.font_datoteka("Anton"), box)[0]
    assert big.size > f.size            # kraći tekst = veća slova
    assert N.font_datoteka("Anton").name == "Anton-Regular.ttf"
    assert N.font_datoteka("Nepoznat").name == "Montserrat-Black.ttf"


def test_vrijeme_videa_i_snimke():
    cuts = [{"a": 2.0, "b": 5.0, "o": 0.0}, {"a": 10.0, "b": 12.0, "o": 3.0}]
    assert N.u_izvor(1.0, cuts) == 3.0
    assert N.u_izvor(4.0, cuts) == 11.0
    assert N.u_video(11.0, cuts) == 4.0
    assert N.u_video(7.0, cuts) is None
    assert N.u_izvor(2.0, cuts, speed=2.0) == 11.0      # ubrzani video: 2 s videa = 4 s snimke
    d = N.dijelovi_za_ocjenu(cuts + [{"a": 12.5, "b": 14.0, "o": 5.0}])
    assert len(d) == 2 and d[1][0] == pytest.approx(10.25) and d[1][1] == pytest.approx(13.75)


def lice(h=0.25, ostrina=500, oci=2.4, svjetlo=160, x=0.5, frontalno=0.95):
    return {"x": x, "y": 0.4, "w": h * 0.6, "h": h, "s": 0.9, "box": [0, 0, 1, 1], "ostrina": ostrina,
            "oci": oci, "svjetlo": svjetlo, "frontalno": frontalno, "u_kadru": True}


def test_ocjena_kadrova():
    mj = {1.0: {"lice": lice(), "lica": 1, "svjetlo": 150, "ostrina_slike": 300},
          2.0: {"lice": lice(oci=1.5), "lica": 1, "svjetlo": 150, "ostrina_slike": 300},      # trepće
          3.0: {"lice": lice(ostrina=80), "lica": 1, "svjetlo": 150, "ostrina_slike": 60},     # mutno
          4.0: {"lice": lice(svjetlo=40), "lica": 1, "svjetlo": 40, "ostrina_slike": 300},     # tamno
          5.0: {"lice": lice(h=0.08), "lica": 1, "svjetlo": 150, "ostrina_slike": 300},        # malo lice
          6.0: {"lice": lice(frontalno=0.1), "lica": 1, "svjetlo": 150, "ostrina_slike": 300},  # profil
          7.0: {"lice": None, "lica": 0, "svjetlo": 150, "ostrina_slike": 300}}
    oc = N.ocijeni(mj)
    best = max(oc, key=lambda t: oc[t]["ocjena"])
    assert best == 1.0 and oc[1.0]["ocjena"] > 9
    assert all(oc[t]["ocjena"] < oc[1.0]["ocjena"] - 0.5 for t in (2.0, 3.0, 4.0, 5.0))
    assert "oči zatvorene" in oc[2.0]["razlog"] and "mutno" in oc[3.0]["razlog"]
    assert "tamno" in oc[4.0]["razlog"] and "lice malo" in oc[5.0]["razlog"] and "profil" in oc[6.0]["razlog"]
    assert oc[7.0]["ocjena"] < 5 and oc[7.0]["razlog"] == "nema lica"
    # Claudeov najjači trenutak malo pomaže
    oc2 = N.ocijeni(mj, [{"od": 5.8, "do": 6.5, "ocjena": 5}])
    assert oc2[6.0]["ocjena"] > oc[6.0]["ocjena"] and "jak trenutak" in oc2[6.0]["razlog"]
    # kandidati: najbolji prvi, razmak barem 1,5 s
    k = N.najbolji({1.0: {"ocjena": 9, "razlog": ""}, 1.5: {"ocjena": 8.9, "razlog": ""},
                    3.0: {"ocjena": 7, "razlog": ""}}, n=5)
    assert [x["izvor"] for x in k] == [1.0, 3.0]


def test_edit_isjecka(tmp_path):
    (tmp_path / "isjecci").mkdir()
    save(tmp_path / "isjecci" / "K1_savjet.edit.json", {"hook": "isjecak"})
    save(tmp_path / "edit.json", {"hook": "glavni"})
    assert N.edit_videa(tmp_path, {"vrsta": "isjecak", "video": "isjecci/K1_savjet.mp4"})["hook"] == "isjecak"
    assert N.edit_videa(tmp_path, {"vrsta": "reel", "video": "reel_v9.mp4"})["hook"] == "glavni"


# ---------------------------------------------------------------- pravi kadrovi
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    pytest.importorskip("PIL")
    import make_naslovna_klip as M
    proj = tmp_path_factory.mktemp("naslovna čć") / "reel"
    proj.mkdir()
    M.make(proj / "source.mp4")
    words = [{"w": "Riječ." if i % 8 == 7 else f"riječ{i}", "s": round(i * 0.5 + 0.02, 3),
              "e": round(i * 0.5 + 0.42, 3)} for i in range(20)]
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    save(proj / "project.json", {"format": "9:16", "width": M.W, "height": M.H, "fps": M.FPS, "duration": M.DUR,
                                 "clips": [{"file": str((proj / "source.mp4").resolve()), "start": 0.0,
                                            "dur": M.DUR, "w": M.W, "h": M.H}]})
    run("plan.py", proj, "--stil", "suncani")
    e = load(proj / "edit.json")
    e["hook"] = "Klima bez muke"
    save(proj / "edit.json", e)
    run("render.py", proj)
    return proj


def unutra(box, okvir):
    return box[0] >= okvir[0] and box[1] >= okvir[1] and box[2] <= okvir[2] and box[3] <= okvir[3]


def preklapa(a, b):
    return a[2] > b[0] and a[0] < b[2] and a[3] > b[1] and a[1] < b[3]


def test_najbolji_kadar_i_sličice(projekt):
    from PIL import Image
    r = run("naslovna.py", projekt, "--tekst", "Čista klima za *5 minuta*")
    d = load(projekt / "naslovna.json")
    e = d["videi"]["reel_v1"]
    assert 4.0 <= e["izbor"]["izvor"] <= 6.0, r.stdout      # najbolji dio probnog klipa
    assert not e["izbor"]["rucno"]
    k = e["kandidati"]
    assert 4.0 <= k[0]["izvor"] <= 6.0 and len(k) >= 4
    assert all(not (2.0 <= x["izvor"] < 4.0) or x["ocjena"] < k[0]["ocjena"] - 0.5 for x in k)  # zatvorene oči
    for x in k:
        if 6.0 <= x["izvor"] < 8.0:
            assert "mutno" in x["razlog"]
        if x["izvor"] >= 8.0:
            assert "tamno" in x["razlog"]
    with Image.open(projekt / e["datoteke"]["9x16"]) as im:
        assert im.size == (1080, 1920)
    with Image.open(projekt / e["datoteke"]["16x9"]) as im:
        assert im.size == (1280, 720)
    assert (projekt / e["datoteke"]["pregled"]).exists() and (projekt / e["datoteke"]["kandidati"]).exists()
    assert (projekt / "reel_v1.naslovna_9x16.jpg").stat().st_size < 2_000_000
    # raspored 9:16: lice i tekst u dijelu koji Instagram pokazuje na profilu (3:4), tekst ne preko lica
    r9 = e["raspored"]["9x16"]
    zona = (N.RUB - 10, N.MREZA_34, 1080 - N.RUB + 10, 1920 - N.MREZA_34)
    assert r9["lice"] and unutra(r9["lice"], (0, N.MREZA_34, 1080, 1920 - N.MREZA_34))
    assert r9["tekst"] and unutra(r9["tekst"], zona), r9
    assert not preklapa(r9["tekst"], r9["lice"])
    r16 = e["raspored"]["16x9"]
    assert r16["lice"] and r16["tekst"] and not preklapa(r16["tekst"], r16["lice"])
    assert r16["tekst"][2] <= 1280 and r16["tekst"][0] >= 30
    assert "Čista klima" in r.stdout and "Upozorenje" not in r.stdout


def test_izbor_kadra_i_teksta_ostaje(projekt):
    run("naslovna.py", projekt, "--kadar", "3")
    d = load(projekt / "naslovna.json")["videi"]["reel_v1"]
    k3 = d["kandidati"][2]
    assert d["izbor"]["izvor"] == k3["izvor"] and d["izbor"]["rucno"]
    assert d["tekst"] == "Čista klima za *5 minuta*"          # tekst ostaje
    run("naslovna.py", projekt, "--tekst", "Novi tekst")
    d = load(projekt / "naslovna.json")["videi"]["reel_v1"]
    assert d["izbor"]["izvor"] == k3["izvor"] and d["tekst"] == "Novi tekst"   # kadar ostaje
    run("naslovna.py", projekt, "--vrijeme", "0:05,1")
    d = load(projekt / "naslovna.json")["videi"]["reel_v1"]
    assert d["izbor"]["vrijeme"] == 5.1 and d["izbor"]["izvor"] == pytest.approx(5.1, abs=0.05)
    r = run("naslovna.py", projekt, "--tekst", "Ovo je predugačak tekst za naslovnu sličicu na mobitelu")
    assert "tekst je dug" in r.stdout
    r = run("naslovna.py", projekt, "--kadar", "99", code=1)
    assert "nema kandidata 99" in r.stderr
    r = run("naslovna.py", projekt, "--vrijeme", "5:00", code=1)
    assert "izvan videa" in r.stderr
    run("naslovna.py", projekt, "--bez-teksta")
    d = load(projekt / "naslovna.json")["videi"]["reel_v1"]
    assert d["tekst"] == "" and d["raspored"]["9x16"]["tekst"] is None


def test_objava_spominje_naslovnu(projekt):
    import objava
    run("naslovna.py", projekt)
    nsl = objava.naslovne(projekt, "reel_v1.mp4")
    assert [x[0] for x in nsl] == ["reel_v1.naslovna_9x16.jpg", "reel_v1.naslovna_16x9.jpg"]
    e = {"video": "reel_v1.mp4", "trajanje": 10.0, "mreze_popis": [], "hook": "x"}
    t = objava.tekst_datoteke("reel_v1", e, None, projekt)
    assert "Naslovna sličica (YouTube): reel_v1.naslovna_16x9.jpg" in t


def test_16x9_iz_vodoravne_snimke(tmp_path):
    """Uspravni reel iz vodoravnog klipa: 16:9 sličica se uzima iz originala (širi kadar, krupno lice)."""
    pytest.importorskip("cv2")
    pytest.importorskip("PIL")
    import make_kadar_klip as KK
    src = tmp_path / "razgovor.mp4"
    KK.make(src, dur=6.0)
    proj = tmp_path / "p"
    run("prepare.py", src, "--out", proj, "--format", "9:16", "--crop-x", "0.27")
    pj = load(proj / "project.json")
    save(proj / "transcript.json", {"language": "hr", "model": "mock",
                                    "words": [{"w": f"r{i}.", "s": i * 0.5 + 0.02, "e": i * 0.5 + 0.4}
                                              for i in range(int(pj["duration"] * 2) - 1)]})
    run("plan.py", proj, "--stil", "udarno")
    run("render.py", proj, "--brzo")
    run("naslovna.py", proj, "--tekst", "Što *Renault 4* krije?")
    e = load(proj / "naslovna.json")["videi"]["reel_v1"]
    r16 = e["raspored"]["16x9"]
    lice = r16["lice"]
    assert lice and (lice[3] - lice[1]) > 0.35 * 720          # zum na govornika
    assert (lice[0] + lice[2]) / 2 < 640 and r16["tekst"][0] > (lice[0] + lice[2]) / 2   # lice lijevo, tekst desno
    # kadar.py je u toj sekundi pokazivao osobu B (desno) → 16:9 zumira nju, tekst lijevo
    pj = load(proj / "project.json")
    pj["clips"][0]["kadrovi"] = [{"od": 0.0, "do": pj["duration"], "crop_x": 1.0}]
    save(proj / "project.json", pj)
    run("naslovna.py", proj)
    r16 = load(proj / "naslovna.json")["videi"]["reel_v1"]["raspored"]["16x9"]
    lice = r16["lice"]
    assert (lice[0] + lice[2]) / 2 > 640 and r16["tekst"][2] < (lice[0] + lice[2]) / 2


def test_sredina_izreza():
    pj = {"width": 1080, "height": 1920}
    c = {"w": 1920, "h": 1080, "crop_x": 0.5}
    assert N.sredina_izreza(pj, c, 3.0) == pytest.approx(0.5)
    c["kadrovi"] = [{"od": 0.0, "do": 2.0, "crop_x": 0.0}, {"od": 2.0, "do": 9.0, "crop_x": 1.0}]
    assert N.sredina_izreza(pj, c, 1.0) < 0.2 and N.sredina_izreza(pj, c, 3.0) > 0.8
