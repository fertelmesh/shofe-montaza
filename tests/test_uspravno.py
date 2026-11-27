"""M4.2b2: uspravni (9:16) isječci podcasta iz ORIGINALNIH kamera — lice onoga tko govori, podijeljen kadar kad
pričaju dvoje, izrez iz širokog kadra za govornika bez svoje kamere; isti zvuk, titlovi i rezovi kao 16:9."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import uspravno as U  # noqa: E402
from conftest import run_script as run  # noqa: E402
from test_davinci import _audio, dtd, validate  # noqa: E402,F401


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- režija bez videa

def ctx_za(segs, kamere, pocetak=0.0):
    """kamere: [(ime, uloga, govornik, osobe [(govornik, x, w)], od, do, w, h)]"""
    cams, roles = [], []
    for ime, uloga, gov, osobe, od, do, w, h in kamere:
        cams.append({"ime": ime, "datoteka": ime, "od": od, "do": do, "w": w, "h": h, "pomak": 0.0})
        roles.append({"ime": ime, "uloga": uloga, "govornik": gov, "lice_y": 0.45,
                      "osobe": [{"govornik": g, "x": x, "w": fw, "vidljiv": 1.0} for g, x, fw in osobe]})
    return {"cams": cams, "roles": roles, "pocetak": pocetak, "trajanje": 600.0, "segs": segs,
            "names": {"G1": "Marko", "G2": "Ivan"}, "lica": U.izvori_lica(roles, segs)}


TRI = [("siroka", "siroki", None, [("G1", 0.3, 0.08), ("G2", 0.7, 0.08)], 0, 600, 1920, 1080),
       ("kamA", "krupni", "G1", [("G1", 0.5, 0.18)], 0, 600, 1920, 1080),
       ("kamB", "krupni", "G2", [("G2", 0.5, 0.3)], 0, 600, 1080, 1920)]


def kamere(shots, ctx):
    return [(s["raspored"], [ctx["cams"][p[0]]["ime"] for p in s["dijelovi"]]) for s in shots]


def test_govornik_dobije_svoju_krupnu_kameru_i_kratko_da_ne_mijenja_kadar():
    segs = [(0.5, 8.0, "G1"), (8.3, 8.8, "G2"), (9.0, 15.0, "G1"), (15.3, 22.0, "G2")]
    ctx = ctx_za(segs, TRI)
    shots = U.rezija(ctx, 0.0, 22.0)
    assert kamere(shots, ctx) == [("jedan", ["kamA"]), ("jedan", ["kamB"])]
    assert abs(shots[1]["od"] - (15.3 - 0.2)) < 0.15                    # rez malo prije prve riječi
    assert shots[0]["od"] == 0.0 and shots[-1]["do"] == 22.0


def test_preklapanje_i_brza_izmjena_podijeljen_kadar():
    segs = [(0.0, 6.0, "G1"), (3.5, 10.0, "G2"),                              # pričaju u isti glas 2,5 s
            (12.0, 13.5, "G1"), (13.7, 15.0, "G2"), (15.2, 16.5, "G1"), (16.7, 18.0, "G2"), (18.2, 25.0, "G1")]
    ctx = ctx_za(segs, TRI)
    shots = U.rezija(ctx, 0.0, 25.0)
    rs = [s["raspored"] for s in shots]
    assert "dvoje" in rs
    sp = [s for s in shots if s["raspored"] == "dvoje"]
    for s in sp:                                       # gore G1 iz kamA, dolje G2 iz kamB (svatko svoja kamera)
        assert [ctx["cams"][p[0]]["ime"] for p in s["dijelovi"]] == ["kamA", "kamB"]
        assert [p[1] for p in s["dijelovi"]] == ["G1", "G2"]
    assert any(s["od"] <= 5.0 < s["do"] for s in sp)                   # preklapanje
    assert any(s["od"] <= 15.5 < s["do"] for s in sp)                  # brza izmjena
    assert shots[-1]["raspored"] == "jedan" and shots[-1]["dijelovi"][0][1] == "G1"


def test_bez_krupne_kamere_izrez_iz_sirokog_i_gost_bez_kamere():
    segs = [(0.0, 6.0, "G1"), (6.3, 12.0, "G2"), (12.3, 18.0, "G3")]
    ctx = ctx_za(segs, TRI[:2])                                         # G2 nema svoju kameru
    shots = U.rezija(ctx, 0.0, 18.0)
    assert kamere(shots, ctx) == [("jedan", ["kamA"]), ("jedan", ["siroka"]), ("dvoje", ["kamA", "siroka"])]
    assert shots[1]["dijelovi"][0][1] == "G2" and shots[1]["dijelovi"][0][2] == 0.7   # lice G2 u širokom
    assert "Ivan" in shots[1]["zasto"]


def test_kamera_se_ugasi_bez_komadica_i_crno():
    segs = [(0.0, 6.0, "G1"), (6.3, 10.0, "G2")]
    kam = [TRI[0], TRI[1], ("kamB", "krupni", "G2", [("G2", 0.5, 0.3)], 0, 9.0, 1080, 1920)]
    ctx = ctx_za(segs, kam)
    shots = U.rezija(ctx, 0.0, 10.0)
    # kamB snima do 9 s: radije cijeli kadar iz širokog nego 1 s komadić
    assert kamere(shots, ctx) == [("jedan", ["kamA"]), ("jedan", ["siroka"])]
    # dugi kadar: kamB dok snima, zatim široki
    ctx = ctx_za([(0.0, 3.0, "G1"), (3.3, 20.0, "G2")], kam)
    assert kamere(U.rezija(ctx, 0.0, 20.0), ctx) == [("jedan", ["kamA"]), ("jedan", ["kamB"]), ("jedan", ["siroka"])]
    # nijedna kamera ne snima
    ctx = ctx_za([(0.0, 5.0, "G1")], [("kamA", "krupni", "G1", [("G1", 0.5, 0.2)], 0, 3.0, 1920, 1080)])
    assert [s["raspored"] for s in U.rezija(ctx, 0.0, 5.0)] == ["jedan", "crno"]


def test_geometrija_lice_u_kadru_i_ogranicen_zum():
    cam = {"w": 1920, "h": 1080}
    sw, sh, x, y = U.geometrija(cam, (0, "G1", 0.3, 0.45, 0.06), 1080, 1920, "jedan")
    assert sh >= 1920 and sw >= 1080 and 0 <= x <= sw - 1080 and 0 <= y <= sh - 1920
    assert sw / 1920 <= 1920 / 1080 * U.MAX_ZUM + 0.01                  # najviše MAX_ZUM preko „popuni"
    assert abs((0.3 * sw - x) - 540) < 2                                # lice na sredini širine
    # krupni kadar: bez zuma, cijela visina; lice uz rub → izrez stane uz rub
    sw, sh, x, y = U.geometrija(cam, (0, "G1", 0.97, 0.45, 0.2), 1080, 1920, "jedan")
    assert sh == 1920 and x == sw - 1080
    # polovica podijeljenog kadra
    sw, sh, x, y = U.geometrija({"w": 1080, "h": 1920}, (0, "G2", 0.5, 0.4, 0.3), 1080, 960, "dvoje")
    assert sw == 1080 and abs((0.4 * sh - y) - 0.42 * 960) < 2


# ---------------------------------------------------------------- cijeli put na probnoj epizodi

BOJE = {"siroka": (85, 105, 135), "kamA": (85, 125, 85), "kamB": (135, 85, 85)}      # RGB pozadine kamere


def _rgb(path, t, x, y):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "-vf", f"crop=24:24:{x - 12}:{y - 12}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, 3).astype(float).mean(axis=0)


def _kamera(path, t, x, y):
    c = _rgb(path, t, x, y)
    return min(BOJE, key=lambda k: float(np.sum((c - BOJE[k]) ** 2)))


@pytest.fixture(scope="module")
def isjecci(podcast):
    run("isjecci.py", podcast, "dodaj", "--od", "Pričaj nam malo", "--do", "dvije godine da ga završimo")
    run("isjecci.py", podcast, "dodaj", "--od", "To je dugo", "--do", "Zagrebu nije bio jeftin")
    d = load(podcast / "isjecci.json")
    for c in d["isjecci"]:
        c["hook"] = "Kako je sve počelo"
        c["naslov"] = ""
    (podcast / "isjecci.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    out = run("isjecci.py", podcast, "render", "K1,K2")
    return podcast, out


def test_isjecci_podcasta_su_9x16_iz_kamera(isjecci):
    proj, out = isjecci
    assert "isječci 9:16 iz originalnih kamera" in out and "podijeljen kadar" in out
    k1 = proj / "isjecci" / "K1.mp4"
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(k1)], capture_output=True, text=True)
    assert r.stdout.strip() == "1080,1920"
    info = load(proj / "isjecci" / "izvor_9x16" / "K1.json")
    rs = [(s["raspored"], [p["kamera"] for p in s["dijelovi"]], [p["govornik"] for p in s["dijelovi"]])
          for s in info["kadrovi"]]
    # Marko (kamA) → Ivan (uspravni mobitel kamB) → gost bez kamere: Marko gore / Ivan dolje → Marko → Ivan
    assert rs == [("jedan", ["kamA.mp4"], ["G1"]), ("jedan", ["kamB.mp4"], ["G2"]),
                  ("dvoje", ["kamA.mp4", "kamB.mp4"], ["G1", "G2"]), ("jedan", ["kamA.mp4"], ["G1"]),
                  ("jedan", ["kamB.mp4"], ["G2"])]
    # u gotovom videu boje pozadine pokazuju kameru (lijevi rub, izvan titlova i hooka)
    edit = load(proj / "isjecci" / "K1.edit.json")
    import render
    st = render.resolve_style(edit)
    words = load(proj / "transcript.json")["words"]
    pj = load(proj / "project.json")
    cuts, _, _ = render.build_cuts(words, edit, st, int(pj["fps"]), pj["duration"])

    def out_t(t):
        c = next(c for c in cuts if c["a"] <= t < c["b"])
        return c["o"] + t - c["a"]
    assert _kamera(k1, out_t(11.5), 30, 1000) == "kamA"
    assert _kamera(k1, out_t(16.0), 30, 1000) == "kamB"
    assert _kamera(k1, out_t(21.0), 30, 400) == "kamA" and _kamera(k1, out_t(21.0), 30, 1400) == "kamB"
    # K2: kamB se gasi na 45 s → Ivanov zadnji kadar je izrez iz širokog kadra (cijeli, bez komadića)
    k2 = load(proj / "isjecci" / "izvor_9x16" / "K2.json")["kadrovi"]
    assert k2[-1]["raspored"] == "jedan" and k2[-1]["dijelovi"][0]["kamera"] == "siroka.mp4"
    assert k2[-1]["do"] - k2[-1]["od"] >= U.MIN_KADAR


def test_isti_zvuk_i_titlovi_kao_vodoravni(isjecci, tmp_path):
    proj, _ = isjecci
    import render
    e = load(proj / "isjecci" / "K1.edit.json")
    h = render.render(proj, e, izlaz="vodoravno/K1.mp4", verzija=False, prevedi=False, ispis=False)
    v = proj / "isjecci" / "K1.mp4"
    assert (proj / "isjecci" / "K1.srt").read_text(encoding="utf-8") == Path(h["srt"]).read_text(encoding="utf-8")
    a, b = _audio(v, 0, 19), _audio(h["video"], 0, 19)
    n = min(len(a), len(b))
    corr = float(np.corrcoef(a[:n], b[:n])[0, 1])
    assert corr > 0.95, corr                                          # isti trenutak zvuka (pomak izvora točan)


def test_davinci_timeline_9x16(isjecci, dtd):
    proj, out = isjecci
    assert "uspravnog izvora isječka" in out
    x = proj / "isjecci" / "K1.fcpxml"
    validate(dtd, x)
    root = ET.parse(x).getroot()
    fmt = root.find("resources/format")
    assert (fmt.get("width"), fmt.get("height")) == ("1080", "1920")
    assert {a.get("name") for a in root.iter("asset")} == {"K1.mp4"}
    assert "izvor_9x16" in next(root.iter("media-rep")).get("src")


def test_kadrovi_vodoravno_i_ispis(isjecci):
    proj, _ = isjecci
    run("isjecci.py", proj, "render", "K1", "--kadar", "1,8")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(proj / "kadar_1_1s.png")], capture_output=True, text=True)
    assert r.stdout.strip() == "1080,1920"
    out = run("isjecci.py", proj, "render", "K2", "--format", "16:9", "--brzo")
    assert "9:16" not in out.split("\n")[1]
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(proj / "isjecci" / "K2_pregled.mp4")], capture_output=True, text=True)
    w, h = map(int, r.stdout.split()[0].split(","))
    assert w > h
    out = run("uspravno.py", proj, "K1")
    assert "podijeljen kadar" in out and "kamB.mp4" in out


# ---------------------------------------------------------------- M4.2b3a: titlovi na spoju, naslovna iz kamera

def test_titlovi_na_spoju_bez_videa(tmp_path):
    import render
    cuts = [{"a": 10.0, "b": 14.0, "o": 0.0}, {"a": 20.0, "b": 30.0, "o": 4.0}]
    izvor = {"kadrovi": [{"od": 9.0, "do": 12.0, "raspored": "dvoje"}, {"od": 12.0, "do": 22.0, "raspored": "jedan"},
                         {"od": 22.0, "do": 25.0, "raspored": "dvoje"}]}
    spans = render.split_spans(izvor, cuts)
    assert [(round(a, 3), round(b, 3)) for a, b in spans] == [(0.0, 2.0), (6.0, 9.0)]
    assert render.split_spans(None, cuts) == [] and render.split_spans({"kadrovi": []}, cuts) == []
    # događaj preko granice dijeli se točno na rezu kadra
    assert render.split_at(1.0, 3.0, spans) == [(1.0, 2.0, True), (2.0, 3.0, False)]
    assert render.split_at(3.0, 5.0, spans) == [(3.0, 5.0, False)]
    st = render.resolve_style({"stil": "podcast"})
    ws = [{"t": f"riječ{i}", "s": i * 0.5, "e": i * 0.5 + 0.4, "hl": False} for i in range(20)]
    ass = tmp_path / "c.ass"
    render.write_ass(ass, ws, st, {"hook": "Hook"}, 1080, 1920, 10.0, spoj=spans)
    ev = [line for line in ass.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue")]
    cap = [line for line in ev if ",Cap," in line]
    seam = [line for line in cap if "\\an5\\pos(540,960)" in line]

    def t(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    assert seam and len(seam) < len(cap)
    for line in cap:
        s0, s1 = (t(x) for x in line.split(",")[1:3])
        mid = (s0 + s1) / 2
        assert ("\\pos(540,960)" in line) == any(a <= mid < b for a, b in spans), line
    assert not any("\\pos(" in line for line in ev if ",Hook," in line)        # hook ostaje gore


def _sl(path, t=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{t:.3f}"] if t is not None else []) + [
        "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.uint8).reshape(1920, 1080, 3)


def _titl(proj, edit, video, t, y0, y1):
    """Udio piksela u traci y0–y1 (sredina širine) koje mijenjaju titlovi: gotovi video naspram iste
    sličice bez titlova (render --kadar, ista boja i zum)."""
    import render
    bez = render.render(proj, dict(edit, titlovi=False, hook=""), kadar=f"{t:.3f}", verzija=False,
                        prevedi=False, ispis=False, izvor=_izvor(proj, "K1"))["slike"][0]
    a, b = _sl(video, t)[y0:y1, 190:890].astype(int), _sl(bez)[y0:y1, 190:890].astype(int)
    return float(np.mean(np.abs(a - b).max(axis=2) > 90))


def _izvor(proj, kid):
    d = load(proj / "isjecci" / "izvor_9x16" / f"{kid}.json")
    return {"datoteka": proj / "isjecci" / "izvor_9x16" / f"{kid}.mp4", "pomak": d["pomak"], "W": 1080, "H": 1920,
            "kadrovi": d["kadrovi"]}


def test_titlovi_podijeljenog_kadra_su_na_spoju(isjecci):
    proj, _ = isjecci
    import render
    run("isjecci.py", proj, "render", "K1")
    edit = load(proj / "isjecci" / "K1.edit.json")
    st = render.resolve_style(edit)
    words = load(proj / "transcript.json")["words"]
    pj = load(proj / "project.json")
    cuts, _, _ = render.build_cuts(words, edit, st, int(pj["fps"]), pj["duration"])
    izvor = load(proj / "isjecci" / "izvor_9x16" / "K1.json")
    spans = render.split_spans(izvor, cuts)
    assert spans
    # trenutak usred titla na spoju (captions.ass je od zadnjeg rendera, K1)
    ev = [line.split(",", 9) for line in (proj / "captions.ass").read_text(encoding="utf-8").splitlines()
          if line.startswith("Dialogue") and "\\pos(540,960)" in line]
    assert ev

    def t(x):
        h, m, sec = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)
    s0, s1 = max(((t(e[1]), t(e[2])) for e in ev), key=lambda x: x[1] - x[0])
    k1 = proj / "isjecci" / "K1.mp4"
    tm = (s0 + s1) / 2
    assert _titl(proj, edit, k1, tm, 890, 1030) > 0.01           # titl na spoju gornjeg i donjeg dijela
    assert _titl(proj, edit, k1, tm, 1250, 1560) < 0.002         # ne preko usta donje osobe
    # izvan podijeljenog kadra titl je dolje kao i inače
    gaps = list(zip([0.0] + [b for _, b in spans], [a for a, _ in spans] + [spans[-1][1] + 5.0]))
    lo, hi = next(g for g in gaps if g[1] - g[0] > 3.0)
    tt = (lo + hi) / 2
    assert _titl(proj, edit, k1, tt, 890, 1030) < 0.002, tt
    assert _titl(proj, edit, k1, tt, 1350, 1560) > 0.01, tt


def test_naslovna_uspravnog_isjecka_iz_kamere_govornika(isjecci):
    proj, _ = isjecci
    import naslovna as N
    run("isjecci.py", proj, "render", "K2")             # drugi test je K2 renderirao vodoravno (brzi pregled)
    run("naslovna.py", proj, "K1,K2")
    d = load(proj / "naslovna.json")["videi"]
    for kid in ("K1", "K2"):
        e = d[kid]
        usp = N.uspravni_izvor(proj, {"id": kid, "vrsta": "isjecak", "video": f"isjecci/{kid}.mp4"})
        assert usp and usp["kadrovi"]
        assert N.kadar_u(usp, e["izbor"]["izvor"])["raspored"] == "jedan"     # jedno lice, ne podijeljen kadar
        assert all("podijeljen kadar" in k["razlog"]
                   for k in e["kandidati"] if N.kadar_u(usp, k["izvor"])["raspored"] == "dvoje")
        lice = e["raspored"]["9x16"]["lice"]
        assert lice and 300 < (lice[0] + lice[2]) / 2 < 780                  # lice govornika na sredini
    # K2: Ivan nakon 45 s (kamB ne snima) → 16:9 iz široke kamere, ali Ivan, ne Marko pokraj njega
    from PIL import Image
    e = d["K2"]
    k = N.kadar_u(N.uspravni_izvor(proj, {"id": "K2", "vrsta": "isjecak", "video": "isjecci/K2.mp4"}),
                  e["izbor"]["izvor"])
    assert k["dijelovi"][0]["kamera"] == "siroka.mp4" and k["dijelovi"][0]["govornik"] == "G2"
    x0, y0, x1, y1 = e["raspored"]["16x9"]["lice"]
    with Image.open(proj / e["datoteke"]["16x9"]) as im:
        r, g, b = im.convert("RGB").getpixel((int((x0 + x1) / 2), min(int(y1 + 80), 715)))
    assert g > b + 30, (r, g, b)                                             # Ivanova zelena majica


def test_naslovna_16x9_krupno_lice_u_sredini():
    from PIL import Image
    import naslovna as N
    img = Image.new("RGB", (1920, 1080), (80, 120, 80))
    face = (760, 170, 1160, 760)                                              # krupni kadar, lice u sredini
    out, rez = N.napravi_16x9(img, face, "Kako je sve počelo", {"font": "Montserrat ExtraBold"})
    assert out.size == (1280, 720)
    assert rez["lice"][0] > 1280 * 0.5 and rez["tekst"][2] <= rez["lice"][0] + 5   # osoba desno, tekst lijevo


def test_sinkro_okret_mobitela(tmp_path):
    import sinkro
    src = tmp_path / "a.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1", "-f", "lavfi",
                    "-i", "sine=d=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
    dst = tmp_path / "b.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-display_rotation", "90", "-i", str(src), "-c", "copy", str(dst)])
    if r.returncode != 0:
        pytest.skip("ovaj ffmpeg ne zna -display_rotation")
    info = sinkro.source_info(dst)
    assert (info["w"], info["h"]) == (180, 320)
