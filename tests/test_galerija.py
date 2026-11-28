"""Galerija efekata (M5.6): odabir efekata i komada, probna snimka (isti komad, svako drugo ponavljanje krupno),
raspored efekata i prijelaza, natpisi, render s natpisom i slikom svih efekata. Pravi HyperFrames (predlošci u
galeriji) samo kad je instaliran; SHOFE_GRAFIKA_TEST=1 (CI) — tada mora proći."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import efekti  # noqa: E402
import galerija  # noqa: E402
import grafika  # noqa: E402
import prijelazi  # noqa: E402
from common import ffmpeg, video_info  # noqa: E402


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def frame(video, t, W, H):
    b = subprocess.run([ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(b[:W * H * 3], np.uint8).reshape(H, W, 3).astype(float)


def args(**kw):
    d = dict(samo=None, od=None, brzo=False, bez_grafike=True, bez_lica=False, proba=True)
    d.update(kw)
    return SimpleNamespace(**d)


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    import make_predlozi as M
    return M.make_projekt(tmp_path_factory.mktemp("galerija čž"), SCRIPTS)


# ---------------------------------------------------------------- odabir
def test_odabir_efekata():
    svi = galerija.odaberi(None, bez_grafike=False)
    imena = [i for _, i in svi]
    tipovi = {v for v, _ in svi}
    # svi efekti iz efekti.py (osim same „grafike“, koja ide kroz predloške) i svih 10 predložaka
    assert tipovi == set(efekti.TIPOVI)
    assert set(prijelazi.TIPOVI) <= set(imena)
    assert [i for v, i in svi if v == "grafika"] == list(grafika.predlosci())
    assert len(svi) == len(efekti.TIPOVI) - 1 + len(grafika.predlosci())
    assert all(v != "grafika" for v, _ in galerija.odaberi(None, bez_grafike=True))
    assert [i for _, i in galerija.odaberi("prijelazi")] == list(prijelazi.TIPOVI)
    assert galerija.odaberi("kamera") == [(t, t) for t in ("guranje", "trzaj", "pad", "vertigo", "zamrzni")]
    # imena, aliasi i predlošci; redoslijed galerije, ne redoslijed upita
    assert galerija.odaberi("brojač, Iris,zoom") == [("trzaj", "trzaj"), ("iris", "iris"), ("grafika", "brojac")]
    assert galerija.odaberi("vhs grafika")[0] == ("retro", "retro")
    assert len(galerija.odaberi("grafika")) == 11      # 10 predložaka + tekst iza osobe
    with pytest.raises(galerija.Greska, match="nepoznat"):
        galerija.odaberi("trzaj,nepostoji")
    with pytest.raises(galerija.Greska, match="bez-grafike"):
        galerija.odaberi("brojac", bez_grafike=True)


def test_odabir_komada(projekt):
    pj, words = load(projekt / "project.json"), load(projekt / "transcript.json")["words"]
    edit = load(projekt / "edit.json")
    i, j, a, b = galerija.odaberi_komad(words, edit, pj)
    txt = " ".join(w["w"] for w in words[i:j + 1])
    # cijela rečenica od 2,2–4,2 s (najbliža 3,4 s), prva takva
    assert txt == "Najvažnije je da isključite struju prije svega."
    assert a < words[i]["s"] and b > words[j]["e"]
    assert a >= words[i - 1]["e"] and b <= words[j + 1]["s"]          # bez komadića susjednih riječi
    # od zadanog vremena dalje
    i2, j2, _, _ = galerija.odaberi_komad(words, edit, pj, od=words[30]["s"])
    assert words[i2]["s"] >= words[30]["s"] - 0.3
    assert words[j2]["w"].endswith(".")
    # izbačena rečenica nije kandidat
    e2 = json.loads(json.dumps(edit))
    for s in e2["odsjecci"]:
        if s["tekst"].startswith("Najvažnije"):
            s["zadrzi"] = False
    i3, _, _, _ = galerija.odaberi_komad(words, e2, pj)
    assert words[i3]["w"] != "Najvažnije"


def test_natpisi_ass():
    st = {"boja_isticanja": "#FF7A00"}
    ev = galerija.ass_events([{"od": 1, "do": 2.5, "broj": 3, "ukupno": 20, "naziv": "prijelaz: iris",
                               "opis": "novi {kadar} se otvori u krugu oko lica i to je jako dugačak opis koji ide dalje"}],
                             st, 1080, 1920)
    (layer, s, e, sty, txt), = ev
    assert (s, e, sty) == (1.0, 2.5, "Galerija")
    assert "3/20" in txt and "PRIJELAZ: IRIS" in txt and "&H00007AFF" in txt     # broj u boji stila
    assert "{kadar}" not in txt and "(kadar)" in txt and txt.endswith("…")
    assert any(x.startswith("Style: Galerija,") for x in galerija.ass_styles(st, 1080, 1920))


# ---------------------------------------------------------------- raspored (bez rendera)
def test_raspored_i_probna_snimka(projekt):
    gal, g, popis, info = galerija.sastavi(projekt, args())
    pj = load(gal / "project.json")
    W, H, fps = pj["width"], pj["height"], pj["fps"]
    sel = galerija.odaberi(None, bez_grafike=True)
    stavke = [x for x in sel if galerija.skupina(x[0]) != "prijelaz"]
    N = info["ponavljanja"]
    assert N == max(len(stavke), len(prijelazi.TIPOVI)) + 1
    # probna snimka: N × komad, točno
    nf = int(round((info["komad"][1] - info["komad"][0]) * fps))
    vi = video_info(gal / "source.mp4")
    assert abs(vi["dur"] - N * nf / fps) < 0.06 and vi["has_audio"]
    L = nf / fps
    # parna ponavljanja = isti široki kadar, neparna = krupni kadar
    f0, f2, f1 = (frame(gal / "source.mp4", r * L + 1.0, W, H) for r in (0, 2, 1))
    assert np.abs(f0 - f2).mean() < 3
    assert np.abs(f0 - f1).mean() > 10
    # svaki efekt točno jednom; prijelazi na rezovima između ponavljanja; brojevi po vremenu
    from render import build_cuts, resolve_style
    words = load(gal / "transcript.json")["words"]
    cuts, _, total = build_cuts(words, g, resolve_style(g), fps, pj["duration"])
    assert len(cuts) == N
    fx, notes = efekti.plan(g, cuts, fps, total)
    assert not notes
    assert sorted(x["tip"] for x in fx) == sorted(v for v, _ in sel)
    assert [p["broj"] for p in popis] == list(range(1, len(sel) + 2))
    assert [p["s"] for p in popis] == sorted(p["s"] for p in popis)
    assert popis[0]["vrsta"] is None
    granice = [c["o"] for c in cuts[1:]]
    for x in fx:
        if galerija.skupina(x["tip"]) == "prijelaz":
            assert min(abs((x["s"] + x["e"]) / 2 - t) for t in granice) < 1.5 / fps
        else:   # cijeli efekt unutar jednog ponavljanja, ne dira prijelaz na rezu
            c = next(c for c in cuts if c["o"] <= x["s"] < c["o"] + c["b"] - c["a"])
            assert x["s"] >= c["o"] + 0.4 and x["e"] <= c["o"] + (c["b"] - c["a"]) - 0.2
    # zum prema licu (nacrtano lice), oznaka zamrznutog kadra
    zam = next(x for x in fx if x["tip"] == "zamrzni")
    assert zam["p"]["oznaka"] and zam["p"].get("lice")
    # natpisi: jedan po efektu (+ bez efekta), ne preklapaju se, isti brojevi
    nat = sorted(g["galerija_natpisi"], key=lambda n: n["od"])
    assert len(nat) == len(popis)
    assert all(b["od"] >= a["do"] - 1e-6 for a, b in zip(nat, nat[1:]))
    assert sorted(n["broj"] for n in nat) == [p["broj"] for p in popis]
    assert all(n["ukupno"] == len(popis) for n in nat)
    # natpis se vidi na slici iz galerija.png (slika je unutar natpisa svog efekta)
    po_broju = {n["broj"]: n for n in nat}
    for p in popis:
        assert po_broju[p["broj"]]["od"] <= p["slika"] <= po_broju[p["broj"]]["do"], p
    # glavni projekt netaknut
    assert "efekti" not in load(projekt / "edit.json")


def test_raspored_samo_prijelazi(projekt):
    _, g, popis, info = galerija.sastavi(projekt, args(samo="iris,rolete,crno"))
    assert info["ponavljanja"] == 4
    assert [p["ime"] for p in popis] == ["bez efekta", "crno", "iris", "rolete"]     # redoslijed galerije
    assert [e["tip"] for e in g["efekti"]] == ["crno", "iris", "rolete"]


# ---------------------------------------------------------------- render
def test_render_galerije(projekt):
    r = run("efekti.py", projekt, "galerija", "--samo", "trzaj,iris,film,zamrzni")
    out = r.stdout
    assert "Galerija:" in out and "galerija.png" in out
    video, png, txt = projekt / "galerija.mp4", projekt / "galerija.png", projekt / "galerija.txt"
    assert video.exists() and png.exists() and txt.exists()
    gal = projekt / galerija.MAPA
    pj = load(gal / "project.json")
    W, H = pj["width"], pj["height"]
    g = load(gal / "edit.json")
    t = txt.read_text(encoding="utf-8")
    assert "1. 00:00.00  bez efekta" in t and 'efekti.py "projekt predlozi" dodaj trzaj' in t
    assert "prijelaz: iris" in t
    popis = {ln.split(".")[0].strip(): ln for ln in t.splitlines()[2:] if ln.strip()}
    assert len(popis) == 5
    # slika svih efekata: 5 sličica u jednom redu
    from PIL import Image
    im = Image.open(png)
    assert im.width > 5 * 240 and 240 * H / W < im.height < 240 * H / W + 80
    from render import build_cuts, resolve_style
    cuts, _, total = build_cuts(load(gal / "transcript.json")["words"], g, resolve_style(g), pj["fps"],
                                pj["duration"])
    assert abs(video_info(video)["dur"] - total) < 0.1

    def isti_bez_efekta(t):     # ista sličica probne snimke (bez efekta, bez natpisa)
        c = next(c for c in cuts if c["o"] <= t < c["o"] + c["b"] - c["a"])
        return frame(gal / "source.mp4", c["a"] + t - c["o"], W, H)

    top, mid = slice(int(0.03 * H), int(0.09 * H)), slice(int(0.45 * H), int(0.6 * H))
    # natpis gore u kadru: na početku galerije gornji pojas se razlikuje od probne snimke, sredina ne
    v0, s0 = frame(video, 1.0, W, H), isti_bez_efekta(1.0)
    assert np.abs(v0[top] - s0[top]).mean() > 3 * max(1.0, np.abs(v0[mid] - s0[mid]).mean())
    nat = {n["naziv"]: n for n in g["galerija_natpisi"]}
    # trzaj: zum prema licu (sredina kadra drukčija nego ista sličica bez efekta)
    assert next(e for e in g["efekti"] if e["tip"] == "trzaj")["parametri"].get("lice")
    t = nat["trzaj"]["od"] + 0.8
    assert np.abs(frame(video, t, W, H)[mid] - isti_bez_efekta(t)[mid]).mean() > 5
    # film: toplije (manje plave) i drukčije od iste sličice bez efekta
    t = nat["film"]["od"] + 1.0
    film, ref = frame(video, t, W, H), isti_bez_efekta(t)
    assert np.abs(film[mid] - ref[mid]).mean() > 8
    assert film[..., 2].mean() < ref[..., 2].mean()


def test_galerija_s_predloscima(projekt):
    ok, msg = grafika.stanje()
    if not ok and os.environ.get("SHOFE_GRAFIKA_TEST"):
        pytest.fail(f"SHOFE_GRAFIKA_TEST=1, a HyperFrames nije spreman: {msg}")
    if not ok:
        r = run("efekti.py", projekt, "galerija", "--samo", "brojac", "--proba", ok=False)
        assert r.returncode != 0 and "nisu u galeriji" in r.stdout + r.stderr
        pytest.skip(f"HyperFrames nije spreman: {msg}")
    run("efekti.py", projekt, "galerija", "--samo", "trzaj,brojac,mobitel")
    gal = projekt / galerija.MAPA
    pj = load(gal / "project.json")
    W, H = pj["width"], pj["height"]
    g = load(gal / "edit.json")
    grf = [e for e in g["efekti"] if e["tip"] == "grafika"]
    assert [e["parametri"]["predlozak"] for e in grf] == ["brojac", "mobitel"]
    assert grf[1]["parametri"].get("pozadina")
    nat = {n["naziv"]: n for n in g["galerija_natpisi"]}
    video = projekt / "galerija.mp4"
    ref = frame(video, nat["bez efekta"]["od"] + 1.6, W, H)
    br = frame(video, nat["Brojač"]["od"] + 1.6, W, H)
    assert np.abs(br - ref).mean() > 3                               # brojač je u videu
