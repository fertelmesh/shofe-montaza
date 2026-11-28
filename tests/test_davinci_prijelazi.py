"""M5.2c2: prijelazi i efekti u DaVinci timelineu — prijelaz kao FCPXML <transition> (Cross Dissolve) na istom
rezu, centriran, s ručkama iz originalne snimke (kadrovi ne mijenjaju mjesto ni trajanje); oznake za prijelaze i efekte."""
import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import davinci  # noqa: E402
import efekti  # noqa: E402
import render  # noqa: E402

T = davinci.parse_time
DTD_URL = ("https://raw.githubusercontent.com/CommandPost/CommandPost/develop/"
           "src/extensions/cp/apple/fcpxml/dtd/FCPXMLv1_10.dtd")


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_prijelazi_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("davinci prijelazi čž"), SCRIPTS)
    run("efekti.py", proj, "dodaj", "pretapanje", "R1", "--trajanje", "0.6")
    run("efekti.py", proj, "dodaj", "rolete", "R2")
    run("efekti.py", proj, "dodaj", "trzaj", "0:00.5-0:01.5")
    run("efekti.py", proj, "dodaj", "zamrzni", "0:04.0-0:04.8", "--oznaka", "Marko, SF klima")
    return proj


def plan(proj, edit):
    pj = load(proj / "project.json")
    words = load(proj / "transcript.json")["words"]
    cuts, _, total = render.build_cuts(words, edit, render.resolve_style(edit), 30, pj["duration"])
    fx, _ = efekti.plan(edit, cuts, 30, total)
    return [x for x in fx if x["tip"] in ("pretapanje", "rolete")]


def spine(root):
    return list(root.find("library/event/project/sequence/spine"))


def frame(path, t, w=135, h=240):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", str(path), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3).astype(float)


def test_prijelazi_kao_transition_na_istom_rezu(projekt):
    edit = load(projekt / "edit.json")
    root, summ = davinci.build(projekt, edit)
    assert summ["prijelaza"] == 2 and summ["efekata"] == 2
    els = spine(root)
    clips = [e for e in els if e.tag == "asset-clip"]
    trs = [e for e in els if e.tag == "transition"]
    assert len(trs) == 2 and len(clips) == 3
    # kadrovi i dalje slijede jedan za drugim bez rupa: prijelaz ne mijenja mjesta ni trajanje videa
    pos = Fraction(0)
    for c in clips:
        assert T(c.get("offset")) == pos
        pos += T(c.get("duration"))
    seq = root.find("library/event/project/sequence")
    assert pos == T(seq.get("duration"))
    # Cross Dissolve (FCP-ov ugrađeni) u resursima, bez prijelaza zvuka (zvuk na rezu ostaje čisti rez)
    eff = root.findall("resources/effect")
    assert len(eff) == 1 and eff[0].get("uid") == "FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265"
    assert eff[0].get("name") == "Cross Dissolve"
    assets = {a.get("id"): a for a in root.iter("asset")}
    for tr, x in zip(trs, plan(projekt, edit)):
        j = els.index(tr)
        a, b = els[j - 1], els[j + 1]
        assert a.tag == b.tag == "asset-clip"
        assert tr.find("filter-video").get("ref") == eff[0].get("id") and tr.find("filter-audio") is None
        off, d = T(tr.get("offset")), T(tr.get("duration"))
        # centriran na rezu, ista duljina i isto mjesto kao u Shofeovu videu
        assert off + d / 2 == T(b.get("offset")) == T(a.get("offset")) + T(a.get("duration"))
        assert abs(float(off) - x["s"]) < 1e-6 and abs(float(off + d) - x["e"]) < 1e-6
        assert d * 30 == x["n"]
        # ručke: snimka postoji iza kraja kadra A i prije početka kadra B
        for el, kraj in ((a, True), (b, False)):
            ast = assets[el.get("ref")]
            lo, hi = T(ast.get("start")), T(ast.get("start")) + T(ast.get("duration"))
            if kraj:
                assert T(el.get("start")) + T(el.get("duration")) + d / 2 <= hi
            else:
                assert T(el.get("start")) - d / 2 >= lo
    marks = {m.get("value"): m.get("note") for m in root.iter("marker")}
    assert "Prijelaz E1: pretapanje (0,6 s)" in marks
    assert "Cross Dissolve 0,6 s" in marks["Prijelaz E1: pretapanje (0,6 s)"]
    rol = next(k for k in marks if k.startswith("Prijelaz E2: rolete"))
    assert "Venetian Blind" in marks[rol] and "zvuk: rolete" in marks[rol]
    assert "Efekt E3: trzaj" in marks and "zvuk: udarac" in marks["Efekt E3: trzaj"]
    assert "Efekt E4: zamrzni „Marko, SF klima“" in marks
    assert any("Cross Dissolve" in n for n in summ["napomene"])


def test_fcpxml_valjan_i_ispis(projekt, tmp_path_factory):
    p = tmp_path_factory.mktemp("dtd") / "FCPXMLv1_10.dtd"
    try:
        with urllib.request.urlopen(DTD_URL, timeout=20) as r:
            p.write_bytes(r.read())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DTD nije dostupan ({e})")
    from lxml import etree
    out = run("davinci.py", projekt, "--trenutno", "--izlaz", "px").stdout
    assert "prijelazi: 2 kao Cross Dissolve" in out and "efekti: 2 kao oznake" in out
    dtd = etree.DTD(str(p))
    assert dtd.validate(etree.parse(str(projekt / "px.fcpxml"))), dtd.error_log.filter_from_errors()


def test_slika_usred_pretapanja_ista_kao_u_shofeu(projekt):
    """Cross Dissolve iz timelinea usred prijelaza = pola kraja kadra A (ručka) + pola početka kadra B,
    isto kao Shofeovo pretapanje na toj sličici."""
    out = run("render.py", projekt, "--izlaz", "px.mp4").stdout
    assert "prijelazi kao Cross Dissolve" in out
    edit = load(projekt / "edit.json")
    root, _ = davinci.build(projekt, edit)
    els = spine(root)
    tr = next(e for e in els if e.tag == "transition")
    j = els.index(tr)
    a, b = els[j - 1], els[j + 1]
    src = next(m.get("src") for m in root.iter("media-rep"))
    assert src.endswith("/prijelazi.mp4")
    orig = projekt.parent / "klipovi" / "prijelazi.mp4"
    cut = T(b.get("offset"))
    ta = float(T(a.get("start")) + (cut - T(a.get("offset"))))        # ručka kadra A na rezu (iza njegova kraja)
    tb = float(T(b.get("start")))
    fa, fb = frame(orig, ta), frame(orig, tb)
    assert fa[5, 5, 0] > 150 and fb[5, 5, 2] > 150                     # A je još crveni prizor, B plavi
    sim = 0.5 * fa + 0.5 * fb
    shofe = frame(projekt / "px.mp4", float(cut) + 0.2 / 30)
    assert np.abs(sim - shofe).mean() < 10, np.abs(sim - shofe).mean()
    assert np.abs(fa - shofe).mean() > 30 and np.abs(fb - shofe).mean() > 30   # stvarno pola-pola


def test_malo_snimke_uz_rez_skrati_prijelaz(projekt, monkeypatch):
    edit = load(projekt / "edit.json")
    root, _ = davinci.build(projekt, edit)
    els = spine(root)
    a = els[els.index(next(e for e in els if e.tag == "transition")) - 1]
    kraj_a = float(T(a.get("start")) + T(a.get("duration")))
    real = davinci.media_info

    def kratka(path):  # snimka završava 3 sličice iza kraja kadra A
        info = dict(real(path))
        info["dur"] = kraj_a + 3 / 30
        return info

    monkeypatch.setattr(davinci, "media_info", kratka)
    root, summ = davinci.build(projekt, dict(edit, efekti=[e for e in edit["efekti"] if e["tip"] == "pretapanje"]))
    trs = [e for e in spine(root) if e.tag == "transition"]
    assert len(trs) == 1 and T(trs[0].get("duration")) == Fraction(6, 30)
    assert any("skraćeni" in n and "E1" in n for n in summ["napomene"])

    def bez(path):  # snimka završava točno na kraju kadra A: nema prijelaza, samo oznaka
        info = dict(real(path))
        info["dur"] = kraj_a
        return info

    monkeypatch.setattr(davinci, "media_info", bez)
    root, summ = davinci.build(projekt, dict(edit, efekti=[e for e in edit["efekti"] if e["tip"] == "pretapanje"]))
    assert not [e for e in spine(root) if e.tag == "transition"] and not root.findall("resources/effect")
    marks = {m.get("value"): m.get("note") for m in root.iter("marker")}
    assert "nema snimke uz rez" in marks["Prijelaz E1: pretapanje (0,6 s)"]


def test_brzina_i_bez_efekata(projekt):
    edit = load(projekt / "edit.json")
    root, summ = davinci.build(projekt, dict(edit, brzina=1.25))
    els = spine(root)
    trs = [e for e in els if e.tag == "transition"]
    assert len(trs) == 2
    for tr in trs:
        b = els[els.index(tr) + 1]
        assert T(tr.get("offset")) + T(tr.get("duration")) / 2 == T(b.get("offset"))
        assert T(tr.get("duration")) == Fraction(2 * round(9 / 1.25), 30)     # 0,6 s Shofeova videa ubrzano 1,25×
    root, summ = davinci.build(projekt, dict(edit, efekti=[]))
    assert summ["prijelaza"] == 0 and not [e for e in spine(root) if e.tag == "transition"]
    assert not any((m.get("value") or "").startswith(("Prijelaz", "Efekt")) for m in root.iter("marker"))
