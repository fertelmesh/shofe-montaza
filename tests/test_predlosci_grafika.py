"""Gotovi HTML predlošci (M5.5): 10 predložaka u <skill>/predlosci/, varijable i provjera, efekti.py dodaj IME,
boja iz stila, mjesto bez lica unutar sigurnih zona reela.

Testovi s pravim HyperFramesom kao u test_grafika.py: bez instalacije se preskoče, osim kad je
SHOFE_GRAFIKA_TEST=1 (CI) — tada moraju proći."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import grafika  # noqa: E402

SVI = ["kartica", "recenica", "brojac", "graf", "popis", "prije_poslije", "komentar", "mobitel", "citat", "poziv"]


def run(script, *args, ok=True, env=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def hf_spreman():
    ok, msg = grafika.stanje()
    if not ok and os.environ.get("SHOFE_GRAFIKA_TEST"):
        pytest.fail(f"SHOFE_GRAFIKA_TEST=1, a HyperFrames nije spreman: {msg}")
    if not ok:
        pytest.skip(f"HyperFrames nije spreman: {msg}")


# ---------------------------------------------------------------- bez HyperFramesa
def test_deset_predlozaka_i_opisi():
    p = grafika.predlosci()
    assert list(p) == SVI
    osnova = (grafika.PREDLOSCI_DIR / "_osnova.html").read_text(encoding="utf-8")
    assert "buildReady" in osnova and "hf-seek" in osnova
    for k, m in p.items():
        assert (grafika.PREDLOSCI_DIR / f"{k}.html").exists(), k
        assert m["opis"] and m["varijable"] and len(m["trajanje"]) == 2
        assert any(v.get("obavezno") for v in m["varijable"].values()) or k in ("mobitel", "poziv")
        var, gr = grafika.provjeri_varijable(k, m["primjer"])
        assert gr == [], (k, gr)                                   # primjer je ispravan
        h = grafika.html_predloska(k)
        assert h.startswith("<!-- Shofe predlošci") and "SF.gradi" in h
        assert "gsap" not in h.lower() and "http" not in h       # bez GSAP-a i bez mreže
    assert p["mobitel"].get("pozadina") is True


def test_imena_i_provjera_varijabli():
    assert grafika.ime_predloska("Brojač") == "brojac"
    assert grafika.ime_predloska("prije-poslije") == "prije_poslije"
    assert grafika.ime_predloska("Ključna rečenica") == "recenica"
    assert grafika.ime_predloska("CTA") == "poziv"
    assert grafika.ime_predloska("iris") is None
    _, gr = grafika.provjeri_varijable("brojac", {"jedinica": "eura"})
    assert gr and "broj" in gr[0]
    _, gr = grafika.provjeri_varijable("brojac", {"broj": "350", "boja_x": 1})
    assert gr and "boja_x" in gr[0]
    _, gr = grafika.provjeri_varijable("kartica", {"naslov": "x", "polozaj": "lijevo"})
    assert gr and "polozaj" in gr[0]
    _, gr = grafika.provjeri_varijable("kartica", {"naslov": "x", "boja": "zelena"})
    assert gr and "boja" in gr[0]
    _, gr = grafika.provjeri_varijable("graf", {"stupci": 5})
    assert gr and "stupci" in gr[0]
    assert grafika.provjeri_varijable("graf", {"stupci": "Stara:1200|Nova:350", "polozaj": "gore"})[1] == []
    with pytest.raises(grafika.Greska):
        grafika.html_predloska("nema")


def test_boja_iz_stila_i_lice_u_kompoziciji():
    assert grafika.boje_stila({"boja_isticanja": "#3DFF6E", "naziv": "Udarno"})["isticanje"] == "#3DFF6E"
    assert grafika.boje_stila({"hook_pozadina": "#FF7A00"})["isticanje"] == "#FF7A00"
    assert grafika.boje_stila(None)["isticanje"] == "#FFC21A"
    assert grafika.boje_stila({"boja_isticanja": "crvena"})["isticanje"] == "#FFC21A"
    page = grafika.omotaj("<div></div>", 540, 960, 30, 60, False, {"naslov": "Čž"},
                          {"stil": {"isticanje": "#3DFF6E"}, "lice": {"x": 0.5, "y": 0.3, "h": 0.1}})
    shofe = json.loads(page.split("window.SHOFE = ")[1].split(";</script>")[0])
    assert shofe["stil"]["isticanje"] == "#3DFF6E" and shofe["lice"]["y"] == 0.3
    assert shofe["varijable"] == {"naslov": "Čž"}
    fx = [{"id": "E1", "tip": "grafika", "s": 1.0, "e": 3.0, "p": {"predlozak": "kartica"}}]
    gx, _ = grafika.plan(fx, 1.0, 30, stil={"boja_isticanja": "#FF7A00"})
    assert gx[0]["stil"]["isticanje"] == "#FF7A00"
    t, mapa = grafika.izvor({"predlozak": "brojac"}, ".")
    assert mapa is None and "Brojač" in t and "SF.uVremenu" in t


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_efekti_klip as MK
    return MK.make_projekt(tmp_path_factory.mktemp("predlosci čž"), SCRIPTS)


def efekti_json(proj):
    return json.loads((proj / "edit.json").read_text(encoding="utf-8")).get("efekti", [])


def test_efekti_dodaj_predlozak(projekt):
    r = run("efekti.py", projekt, "dodaj", "brojac", "1-3", ok=False)
    assert r.returncode != 0 and "broj" in r.stderr and "grafika.py predlosci" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "brojac", "1-3", "--varijable", '{"broj": "350", "boja": "plava"}',
            ok=False)
    assert r.returncode != 0 and "boja" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "grafika", "1-3", "--predlozak", "nema", ok=False)
    assert r.returncode != 0 and "nema predloška" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "grafika", "1-3", "--predlozak", "kartica", "--html", "<p>x</p>",
            ok=False)
    assert r.returncode != 0
    r = run("efekti.py", projekt, "dodaj", "trzaj", "1-2", "--predlozak", "kartica", ok=False)
    assert r.returncode != 0 and "idu uz grafika" in r.stderr
    run("efekti.py", projekt, "dodaj", "brojac", "1-3", "--varijable",
        '{"broj": "1.200", "jedinica": "eura", "polozaj": "gore"}')
    run("efekti.py", projekt, "dodaj", "grafika", "3.5-5", "--predlozak", "Prije/poslije", "--varijable",
        '{"prije": "180 €", "poslije": "65 €"}')
    run("efekti.py", projekt, "dodaj", "mobitel", "5.5-7", "--varijable", '{"naslov": "Ovako"}')
    run("efekti.py", projekt, "dodaj", "kartica", "1-2.5", "--varijable", '{"naslov": "Čćšžđ"}', "--bez-lica")
    g = [e for e in efekti_json(projekt) if e["tip"] == "grafika"]
    assert [x["parametri"]["predlozak"] for x in g] == ["brojac", "kartica", "prije_poslije", "mobitel"]
    assert g[0]["parametri"]["varijable"]["broj"] == "1.200"
    assert g[3]["parametri"]["pozadina"] is True and not g[2]["parametri"].get("pozadina")
    assert "lice" not in g[1]["parametri"]                         # --bez-lica
    assert "html" not in g[0]["parametri"]
    popis = run("efekti.py", projekt, "popis").stdout
    assert "predložak brojac „1.200“" in popis and "predložak mobitel „Ovako“, s pozadinom" in popis
    assert "predložak prije_poslije „180 €“" in popis


def test_grafika_py_predlosci_ispis():
    out = run("grafika.py", "predlosci").stdout
    for k in SVI:
        assert f"\n  {k}" in out
    assert "polozaj" in out and "primjer: --varijable" in out


# ---------------------------------------------------------------- pravi HyperFrames
LICE = {"x": 0.5, "y": 0.34, "h": 0.15}


def alfa_komada(f, W, H):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W, 4)


def test_svi_predlosci_renderiraju(tmp_path):
    """Svaki predložak se renderira (primjer iz predlosci.json), uđe, stoji, izađe; nije preko lica ni titlova."""
    hf_spreman()
    W, H, fps, n = 270, 480, 30, 75
    video = tmp_path / "pozadina.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r={fps}:d=3",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    fy0, fy1 = (LICE["y"] - 0.85 * LICE["h"]) * H, (LICE["y"] + 0.95 * LICE["h"]) * H
    for k, m in grafika.predlosci().items():
        poz = bool(m.get("pozadina"))
        g = {"id": k, "s": 0.0, "n": n, "p": {"predlozak": k, "varijable": m["primjer"], "pozadina": poz,
                                               "lice": LICE}, "stil": grafika.boje_stila(None)}
        f, nov = grafika.pripremi(tmp_path, g, W, H, fps, video=video)
        assert nov and grafika.broj_slicica(f) >= n, k
        if poz:
            continue
        a = alfa_komada(f, W, H)[..., 3]
        sred = a[int(n * 0.75)] > 128
        assert sred.mean() > 0.04, (k, sred.mean())                         # grafika se vidi
        assert (a[0] > 128).mean() < sred.mean() * 0.6, k                     # ulazi (prva sličica još nije puna)
        assert (a[n - 1] > 200).mean() < sred.mean() * 0.5, k                 # izlazi
        ys = np.where(sred.any(axis=1))[0]
        assert ys.min() >= H * 0.12 - 2 and ys.max() <= H * 0.74 + 8, (k, ys.min() / H, ys.max() / H)
        lice = sred[int(fy0) + 2:int(fy1) - 2, int(W * 0.45):int(W * 0.55)]
        assert lice.mean() < 0.02, (k, lice.mean())                           # lice slobodno


def test_predlozak_boja_polozaj_i_brojac(tmp_path):
    hf_spreman()
    W, H, fps, n = 270, 480, 30, 60

    def komad(k, var, stil=None, lice=None):
        g = {"id": k, "s": 0.0, "n": n, "p": {"predlozak": k, "varijable": var, "lice": lice},
             "stil": grafika.boje_stila(stil)}
        f, _ = grafika.pripremi(tmp_path, g, W, H, fps)
        return alfa_komada(f, W, H)

    # boja iz stila (Udarno: zelena) na traci brojača; brojanje: sredina ≠ kraj
    a = komad("brojac", {"broj": "350", "jedinica": "eura"}, {"boja_isticanja": "#3DFF6E"})
    kraj = a[n - 10].astype(int)
    zel = (kraj[..., 1] > 200) & (kraj[..., 0] < 120) & (kraj[..., 2] < 160) & (kraj[..., 3] > 200)
    assert zel.sum() > 30
    assert np.abs(a[12].astype(int) - a[n - 10].astype(int)).mean() > 0.5
    # polozaj gore / dolje
    gore = komad("kartica", {"naslov": "Gore", "polozaj": "gore"})[n // 2, ..., 3] > 128
    dolje = komad("kartica", {"naslov": "Dolje", "polozaj": "dolje"})[n // 2, ..., 3] > 128
    yg, yd = np.where(gore.any(axis=1))[0], np.where(dolje.any(axis=1))[0]
    assert yg.min() < H * 0.2 and yd.max() > H * 0.65 and yg.mean() < yd.mean()
    # auto: lice dolje → kartica gore
    a = komad("kartica", {"naslov": "Auto"}, lice={"x": 0.5, "y": 0.6, "h": 0.15})[n // 2, ..., 3] > 128
    assert np.where(a.any(axis=1))[0].max() < (0.6 - 0.85 * 0.15) * H


def test_vodoravni_video_blok_u_stranu(tmp_path):
    """16:9 (YouTube): blok ide u polovicu bez lica, ne preko lica ni preko titlova."""
    hf_spreman()
    W, H, fps, n = 480, 270, 30, 45
    for lx, strana in ((0.3, "desno"), (0.7, "lijevo")):
        g = {"id": "k", "s": 0.0, "n": n, "p": {"predlozak": "kartica", "varijable": {"naslov": "Čćšžđ i još malo"},
                                                 "lice": {"x": lx, "y": 0.35, "h": 0.25}},
             "stil": grafika.boje_stila(None)}
        f, _ = grafika.pripremi(tmp_path, g, W, H, fps)
        a = alfa_komada(f, W, H)[n // 2, ..., 3] > 128
        xs, ys = np.where(a.any(axis=0))[0], np.where(a.any(axis=1))[0]
        if strana == "desno":
            assert xs.min() > W * 0.5, xs.min()
        else:
            assert xs.max() < W * 0.5, xs.max()
        assert ys.max() <= H * 0.80 + 6


def test_predlozak_u_pravom_renderu(projekt):
    """efekti.py dodaj + render: predložak u videu, boja stila, druga verzija iz predmemorije."""
    hf_spreman()
    run("efekti.py", projekt, "makni", "sve")
    run("efekti.py", projekt, "dodaj", "popis", "1-3", "--varijable", '{"stavke": ["Filtere", "Odvod"]}')
    out = run("render.py", projekt, "--izlaz", "p.mp4").stdout
    assert "Grafika: 1" in out and "renderirao 1" in out
    out2 = run("render.py", projekt, "--izlaz", "p2.mp4").stdout
    assert "renderirao 0, 1 iz predmemorije" in out2
