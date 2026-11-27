"""M4.3b3: najbolji refren pjesme → isječak od 30–60 s (refren.py, isjecci.py pjesma) + pjesme u pregled.html."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import make_nastup as MN  # noqa: E402
import refren  # noqa: E402
import ritam  # noqa: E402
import serija  # noqa: E402

PJESMA_DO_PLJESAK = 3.0


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


def to11k(y):
    t = np.arange(int(len(y) / MN.SR * refren.SR)) / refren.SR
    return np.interp(t, np.arange(len(y)) / MN.SR, y)


def bend_u_autu(y, seed=3):
    """Uživo u autu: šum motora i glasnoća koja polako valja."""
    rng = np.random.default_rng(seed)
    n = np.convolve(rng.normal(0, 1, len(y)), np.ones(40) / 40, "same")
    return y * (1 + 0.15 * np.sin(np.arange(len(y)) / MN.SR * 0.3)) + 0.08 * n / np.abs(n).max()


STRUKTURE = [
    MN.STRUKTURA,                                                                  # A B A B C B B
    [("I", 4), ("A", 8), ("B", 8), ("A", 8), ("B", 8), ("B", 8), ("C", 4), ("A", 4)],  # dupli refren pa outro
    [("A", 8), ("B", 4), ("A", 8), ("B", 4), ("C", 8), ("B", 4), ("B", 4), ("A", 4)],  # kratki refren, bez uvoda
]


# ---------------------------------------------------------------- bez videa
@pytest.mark.parametrize("k", range(len(STRUKTURE)))
def test_refren_sintetske_pjesme(k):
    struct = STRUKTURE[k]
    y = bend_u_autu(MN.pjesma_refren(seed=7 + 2 * k, struktura=struct))
    x = to11k(y)
    cs, db = refren.features(x)
    ch = refren.find_chorus(cs, db)
    assert ch and ch["ponavljanja"] >= 3
    b_starts = [a for o, a, _ in MN.odsjeci(struktura=struct) if o == "B"]
    for p in ch["pojave"]:   # svaka pronađena pojava je refren (±1,5 s)
        assert min(abs(p * refren.KORAK - b) for b in b_starts) < 1.5, (p * refren.KORAK, b_starts)
    r = ritam.analyse(x)
    dur = len(y) / MN.SR
    res = refren.choose_clip(0.0, dur, ch, db, r["udarci"], fino=refren.fine_db(x))
    assert 30 - 0.01 <= res["do"] - res["od"] <= 60 + 0.01
    # isječak krene točno na početku refrena (na udarcu, < 60 ms) i završi na kraju pjesme
    assert min(abs(res["od"] - b) for b in b_starts) < 0.06, (res, b_starts)
    assert res["do_kraja"] and abs(res["do"] - dur) < 0.01
    assert "refren" in res["razlog"]


def test_pravila_izbora_bez_zvuka():
    db = np.zeros(400)
    # kratka pjesma: cijela
    r = refren.choose_clip(10.0, 55.0, None, db)
    assert (r["od"], r["do"], r["do_kraja"]) == (10.0, 55.0, True)
    # refren nije jasan: najglasniji dio, 30–60 s
    db2 = np.full(400, -30.0)
    db2[200:330] = -10.0
    r = refren.choose_clip(0.0, 400 * refren.KORAK, None, db2)
    assert r["refren"] == [] and "nije jasan" in r["razlog"]
    assert 30 <= r["do"] - r["od"] <= 60 and 200 * refren.KORAK - 1 <= r["od"] <= 215 * refren.KORAK
    # refren pred kraj pjesme: isječak krene cijeli takt (4 udarca) ranije da traje barem 30 s
    beats = np.arange(0, 150, 0.5)
    ch = {"duljina": int(12 / refren.KORAK), "pojave": [int(round(130 / refren.KORAK))], "ocjena": 1.0}
    r = refren.choose_clip(0.0, 150.0, ch, np.zeros(410), beats)
    assert 30 <= r["do"] - r["od"] <= 60 and r["do"] == 150.0
    assert abs((130 - r["od"]) % 2.0) < 1e-6 or abs((130 - r["od"]) % 2.0 - 2.0) < 1e-6   # cijeli taktovi
    assert "prije" in r["razlog"]
    # kraj na cijelom taktu od početka isječka kad kraj pjesme nije blizu
    ch = {"duljina": int(12 / refren.KORAK), "pojave": [int(round(20 / refren.KORAK))], "ocjena": 1.0}
    r = refren.choose_clip(0.0, 200.0, ch, np.zeros(540), beats)
    assert r["od"] == 20.0 and abs(((r["do"] - r["od"]) / 2.0) - round((r["do"] - r["od"]) / 2.0)) < 1e-6
    assert 30 <= r["do"] - r["od"] <= 60 and not r["do_kraja"]


def test_edit_isjecka_pjesme_i_govora():
    words = [{"w": f"r{i}", "s": float(i), "e": i + 0.6} for i in range(0, 20)] + \
            [{"w": f"r{i}", "s": float(i), "e": i + 0.6} for i in range(100, 120)]
    base = {"stil": "podcast", "odsjecci": [{"id": 1, "od": 0, "do": 20, "tekst": "", "zadrzi": True},
                                            {"id": 2, "od": 100, "do": 120, "tekst": "", "zadrzi": True}],
            "nastupi": [{"id": "P1", "od": 22.0, "do": 95.0, "zadrzi": True, "titlovi": False}]}
    pj = {"id": "K3", "vrsta": "pjesma", "nastup": "P1", "od": 50.0, "do": 90.0, "hook": "Bend uživo"}
    e, _ = serija.edit_za_isjecak(base, words, pj, 125.0)
    assert e["nastupi"] == [{"id": "P1", "od": 50.0, "do": 90.0, "zadrzi": True, "titlovi": False}]
    assert e["izrezi"][0]["do"] == 50.0 and e["izrezi"][1]["od"] == 90.0
    assert e["pretapanje_zvuka"] == list(serija.PRETAPANJE_PJESME) and e["isjecak"]["vrsta"] == "pjesma"
    # isječak govora: pjesma iz glavnog edit.json ne smije ući u njega (render je uzima cijelu)
    gv = {"id": "K1", "od": 0.0, "do": 19.6, "rijeci": [0, 19], "hook": "x"}
    e, _ = serija.edit_za_isjecak(base, words, gv, 125.0)
    assert "nastupi" not in e and "pretapanje_zvuka" not in e


# ---------------------------------------------------------------- probni projekt
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    base = tmp_path_factory.mktemp("refren čž")
    proj, p0, p1 = MN.make_refren(base / "ep")
    save(proj / "nastupi.json", {"nastupi": [{"id": "P1", "od": p0, "do": round(p1 + PJESMA_DO_PLJESAK, 2),
                                              "izvor": "auto", "sigurnost": 0.9, "pjevanje": True}]})
    run("plan.py", proj, "--stil", "podcast")
    run("analyze.py", proj)
    return proj, p0, p1


def test_isjecak_iz_pjesme_u_isjeccima(projekt):
    proj, p0, p1 = projekt
    r = run("isjecci.py", proj, "predlozi", "--min", "5", "--max", "12", ok=False)
    assert "iz pjesme P1" in r.stdout, r.stdout + r.stderr
    cs = load(proj / "isjecci.json")["isjecci"]
    pj = [c for c in cs if c.get("vrsta") == "pjesma"]
    assert len(pj) == 1
    c = pj[0]
    b3 = p0 + [a for o, a, _ in MN.odsjeci() if o == "B"][2]
    assert abs(c["od"] - b3) < 0.06 and abs(c["do"] - (p1 + PJESMA_DO_PLJESAK)) < 0.01   # 3. refren do kraja s pljeskom
    assert c["nastup"] == "P1" and isinstance(c["ocjena"], int) and c["ocjena"] >= 7 and c["razlog"]
    assert len(c["refren"]) >= 3 and c["bpm"] and abs(c["bpm"] - 112) < 2
    # govor ne ide preko pjesme
    for g in cs:
        if g.get("vrsta") != "pjesma":
            assert g["do"] <= p0 + 0.01 or g["od"] >= p1 - 0.01
    txt = (proj / "isjecci.txt").read_text(encoding="utf-8")
    assert "pjesma: P1" in txt and "bez titlova" in txt
    # novi: pjesma koja već ima isječak ne dobije drugi
    run("isjecci.py", proj, "novi", ok=False)
    assert sum(x.get("vrsta") == "pjesma" for x in load(proj / "isjecci.json")["isjecci"]) == 1
    # pregled.html: pjesma, refren i isječak na vremenskoj crti
    html = (proj / "pregled.html").read_text(encoding="utf-8")
    assert '"pjesme":[{"id":"P1"' in html and '"isjecak":{"id":"' + c["id"] in html and '"refren":[[' in html


def test_rucne_granice_i_provjera(projekt, tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(projekt[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci"))
    p0 = projekt[1]
    if not (proj / "isjecci.json").exists():
        run("isjecci.py", proj, "predlozi", ok=False)
    kid = next(c["id"] for c in load(proj / "isjecci.json")["isjecci"] if c.get("vrsta") == "pjesma")
    r = run("isjecci.py", proj, "pjesma", "P1", "--od", "0:40", "--do", "1:20")
    assert kid in r.stdout   # isti isječak, nove granice
    c = next(c for c in load(proj / "isjecci.json")["isjecci"] if c["id"] == kid)
    assert (c["od"], c["do"]) == (40.0, 80.0) and "ručno" in c["heuristika"]["razlozi"][0]
    # Claude pomakne granice izvan pjesme → provjeri ih vrati unutra
    d = load(proj / "isjecci.json")
    for x in d["isjecci"]:
        if x["id"] == kid:
            x["od"] = p0 - 5
    save(proj / "isjecci.json", d)
    r = run("isjecci.py", proj, "provjeri", ok=False)
    assert "unutar pjesme P1" in r.stdout
    c = next(c for c in load(proj / "isjecci.json")["isjecci"] if c["id"] == kid)
    assert c["od"] == p0 and c["trajanje"] == round(80.0 - p0, 1)
    r = run("isjecci.py", proj, "pjesma", "P9", ok=False)
    assert r.returncode != 0 and "nema pjesme P9" in (r.stdout + r.stderr)


def _rms_db(path, t0, t1):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0}", "-t", f"{t1 - t0}", "-i", str(path), "-ac", "1",
                        "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, np.float32)
    return 20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-9)


def test_render_isjecka_iz_pjesme(projekt, tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(projekt[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci"))
    if not (proj / "isjecci.json").exists():
        run("isjecci.py", proj, "predlozi", ok=False)
    d = load(proj / "isjecci.json")
    d["isjecci"] = [c for c in d["isjecci"] if c.get("vrsta") == "pjesma"]   # samo pjesma (govor je prekratak)
    c = d["isjecci"][0]
    assert c["hook"] == ""   # pjesma bez naziva: hook piše Claude
    c["hook"] = "Bend uživo u autu"
    save(proj / "isjecci.json", d)
    run("isjecci.py", proj, "odobri", c["id"])
    r = run("isjecci.py", proj, "render")
    c = load(proj / "isjecci.json")["isjecci"][0]
    v = proj / c["render"]["datoteka"]
    assert abs(c["render"]["trajanje"] - (c["do"] - c["od"])) < 0.15, r.stdout
    assert v.with_suffix(".srt").read_text(encoding="utf-8-sig").strip() == ""      # pjesma bez titlova
    e = load(v.with_suffix(".edit.json"))
    assert e["nastupi"][0]["od"] == c["od"] and e["pretapanje_zvuka"]
    # krene odmah punom glasnoćom (na udarcu refrena), a na kraju se utiša
    start, mid, end = _rms_db(v, 0.0, 0.4), _rms_db(v, 5.0, 10.0), _rms_db(v, c["render"]["trajanje"] - 0.25,
                                                                           c["render"]["trajanje"])
    assert start > mid - 6 and end < mid - 12, (start, mid, end)
    # objava: Claude zna da je to pjesma bez govora
    r = run("objava.py", proj, c["id"], ok=False)
    assert "nastup benda uživo, bez govora" in r.stdout


def test_isjecak_govora_ne_vuce_pjesmu(projekt, tmp_path):
    import shutil
    proj = tmp_path / "p"
    shutil.copytree(projekt[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci", "isjecci.json"))
    run("isjecci.py", proj, "dodaj", "--od", "Bok svima", "--do", "kako je počela", "--min", "5")
    d = load(proj / "isjecci.json")
    d["isjecci"][0]["hook"] = "Kako je počelo"
    save(proj / "isjecci.json", d)
    run("isjecci.py", proj, "render", "K1", "--brzo")
    c = load(proj / "isjecci.json")["isjecci"][0]
    assert c["render"]["trajanje"] < 15, c["render"]   # prije: cijela pjesma (2 min) u isječku govora


def test_pregled_bez_pjesama_i_osvjezavanje(projekt, tmp_path):
    import shutil
    import pregled
    proj = tmp_path / "p"
    shutil.copytree(projekt[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci", "isjecci.json"))
    data = pregled.page_data(proj, load(proj / "analiza.json"), {"korak": 0, "v": []})
    assert data["pjesme"][0]["id"] == "P1" and "isjecak" not in data["pjesme"][0]
    (proj / "nastupi.json").unlink()
    assert pregled.page_data(proj, load(proj / "analiza.json"), {"korak": 0, "v": []})["pjesme"] == []
    # nastupi.py naziv → pregled.html se sam osvježi
    save(proj / "nastupi.json", {"nastupi": [{"id": "P1", "od": 12.0, "do": 130.0, "izvor": "auto"}]})
    r = run("nastupi.py", proj, "naziv", "P1", "Bend – Kutina")
    assert "Pregled osvježen" in r.stdout
    assert "Bend – Kutina" in (proj / "pregled.html").read_text(encoding="utf-8")
