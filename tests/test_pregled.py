"""Testovi pregleda karte videa (pregled.py → pregled.html)."""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import pregled as P  # noqa: E402

RAZ = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))
ZLO = "</script><script>alert(1)</script><!--"


def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def page_json(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert m, "nema podataka u stranici"
    return json.loads(m.group(1))


def mini_analiza():
    return {
        "shofe": "0.5.0", "trajanje": 20.0, "zvuk": {"glasnoca_lufs": -16.0, "napomena": "u redu"},
        "govor": {"udio_govora": 0.7, "slogova_u_s": 5.0, "tempo": "normalno", "rijeci_u_minuti": 140},
        "govornici": [{"id": "G1", "ime": "Marko", "udio": 0.6, "govori_s": 8.0},
                      {"id": "G2", "ime": "", "udio": 0.4, "govori_s": 5.0}],
        "tisine": [{"od": 5.0, "do": 6.0, "trajanje": 1.0}],
        "odsjecci": [{"id": 1, "od": 0.5, "do": 4.8, "tekst": "Bok, ovo je Šibenik i čćž", "govornik": "G1",
                      "glasnoca_db": -20, "tempo": "brzo"},
                     {"id": 2, "od": 6.2, "do": 9.0, "tekst": ZLO, "govornik": "G2", "glasnoca_db": -30,
                      "glasnoca_oznaka": "tiho", "losi_kadar": "tamno"}],
        "slika": {"svjetlina": 100}, "promjene_scene": [3.0], "spojevi_klipova": [10.0],
        "losi_kadrovi": [{"od": 6.0, "do": 8.0, "razlog": "tamno"}],
        "teme": [{"od": 0, "do": 10, "naslov": "Uvod <b>", "sazetak": ZLO}, "nije objekt"],
        "trenuci": [{"od": 1, "do": 3, "vrsta": "hook", "ocjena": 5, "opis": "Jak početak"}],
    }


def test_ovojnica_tisina_i_raspon():
    win = 0.05
    db = np.full(int(10 / win), -20.0, np.float32)
    db[int(4 / win):int(6 / win)] = -90.0       # tišina 4–6 s
    env = P.envelope(db, win, 10.0)
    assert len(env["v"]) == 100 and abs(env["korak"] - 0.1) < 1e-9
    v = env["v"]
    assert all(0 <= x <= 100 for x in v)
    assert max(v[42:58]) == 0 and min(v[:38]) == 100 and min(v[62:]) == 100


def test_ovojnica_dugi_video_ogranicena():
    env = P.envelope(np.random.uniform(-40, -10, 72000).astype(np.float32), 0.05, 3600.0)
    assert len(env["v"]) == P.MAX_TOCAKA
    assert P.envelope([], 0.05, 10.0)["v"] == [] and P.envelope([-20.0], 0.05, 0)["v"] == []


def test_stranica_bez_videa_i_sigurni_tekst(tmp_path):
    proj = tmp_path / "projekt čćž s razmakom"
    proj.mkdir()
    out = P.write_pregled(proj, mini_analiza(), np.full(400, -20.0, np.float32), 0.05)
    html = out.read_text(encoding="utf-8")
    # tekst iz transkripta ne smije zatvoriti <script> ni otvoriti komentar
    assert html.count("</script>") == 2 and "<!--" not in html
    assert "<title>Karta videa · projekt čćž s razmakom</title>" in html
    d = page_json(html)
    assert d["video"] == "" and d["naziv"] == "projekt čćž s razmakom"
    assert d["odsjecci"][1]["tekst"] == ZLO and d["odsjecci"][0]["tekst"].endswith("čćž")
    assert set(d["odsjecci"][1]["oznake"]) == {"tiho", "tamno"} and d["odsjecci"][0]["oznake"] == ["brzo"]
    assert d["odsjecci"][0]["g"] == "G1" and d["govornici"][0]["ime"] == "Marko"
    assert len(d["teme"]) == 1, "neispravne teme se preskaču"
    assert len(d["ovojnica"]["v"]) == 200
    assert d["slika"] is True and d["promjene_scene"] == [3.0]


def test_analyze_napravi_pregled_i_provjeri_ga_osvjezi(tmp_path):
    proj = tmp_path / "razgovor čćž"
    proj.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=10",
                    "-i", str(FIX / "razgovor.m4a"), "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(proj / "source.mp4")], check=True)
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": RAZ["words"]},
                                                     ensure_ascii=False), encoding="utf-8")
    r = run("analyze.py", proj, "--bez-slike")
    assert "pregled.html" in r.stdout
    d = page_json((proj / "pregled.html").read_text(encoding="utf-8"))
    an = json.loads((proj / "analiza.json").read_text(encoding="utf-8"))
    assert d["video"] == "source.mp4" and d["trajanje"] == an["trajanje"]
    assert len(d["odsjecci"]) == len(an["odsjecci"]) and d["teme"] == []
    v = d["ovojnica"]["v"]
    assert len(v) > 100 and max(v) == 100
    # tišine u ovojnici: prije prve rečenice (0–0,35 s) je tiho
    assert v[0] < 30

    an["teme"] = [{"od": 0.3, "do": 13.6, "naslov": "Uvod", "sazetak": "Pozdrav."}]
    an["trenuci"] = [{"od": 13.9, "do": 17.9, "vrsta": "hook", "ocjena": 5, "opis": "Garaža."}]
    (proj / "analiza.json").write_text(json.dumps(an, ensure_ascii=False), encoding="utf-8")
    run("analyze.py", proj, "--provjeri")
    d = page_json((proj / "pregled.html").read_text(encoding="utf-8"))
    assert d["teme"][0]["naslov"] == "Uvod" and d["trenuci"][0]["vrsta"] == "hook"
    assert len(d["ovojnica"]["v"]) == len(v)

    (proj / "pregled.html").unlink()
    run("pregled.py", proj)
    assert (proj / "pregled.html").exists()


def _browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return sync_playwright


def test_stranica_u_pregledniku(tmp_path):
    """Ako je Playwright s Chromiumom instaliran: stranica se prikaže bez JS grešaka i klik skače."""
    sp = _browser()
    if sp is None:
        pytest.skip("nema Playwrighta")
    proj = tmp_path / "p"
    proj.mkdir()
    out = P.write_pregled(proj, mini_analiza(), np.full(400, -20.0, np.float32), 0.05)
    with sp() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium se ne pokreće: {e}")
        pg = b.new_page(viewport={"width": 1200, "height": 800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("dialog", lambda d: (errs.append("dialog " + d.message), d.dismiss()))
        pg.goto(out.resolve().as_uri())
        pg.wait_for_timeout(300)
        assert errs == []
        assert pg.locator(".seg").count() == 2
        assert pg.locator("#trenuci li").count() == 1
        assert pg.locator("#tl path").count() == 1            # ovojnica zvuka
        assert pg.locator("#tlLabels div").count() == 6        # zvuk, govornici, teme, trenuci, slika, os
        assert ZLO in pg.locator(".seg").nth(1).text_content()  # prikazano kao tekst
        pg.locator(".seg").nth(1).click()
        assert "now" in pg.locator(".seg").nth(1).get_attribute("class")
        pg.click("#zoomIn")
        assert "na ekranu" in pg.text_content("#zoomInfo")
        assert errs == []
        b.close()
