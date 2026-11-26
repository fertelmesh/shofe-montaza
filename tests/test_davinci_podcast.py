"""M4.2b: DaVinci timeline podcasta — program iz ORIGINALNIH kamera (V1), ostale kamere na trakama iznad
(isključene, za ručnu promjenu kadra), zvuk glavnog izvora ispod; ista slika i zvuk kao Shofeov program."""
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import davinci  # noqa: E402
import render  # noqa: E402
import sinkro as S  # noqa: E402
from test_davinci import _audio, _frame, dtd, validate  # noqa: E402,F401

T = davinci.parse_time


def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r.stdout


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# fixture `podcast` (probna epizoda) je u conftest.py: dijele je test_davinci_podcast i test_uspravno


def build(proj, **kw):
    return davinci.build(proj, load(proj / "edit.json"), **kw)


def test_program_iz_originalnih_kamera_valjan_xml(podcast, dtd, tmp_path):
    out = run("davinci.py", podcast, "--trenutno", "--izlaz", "za_resolve")
    assert "ostale kamere na trakama iznad" in out and "zvuk: zvuk.wav" in out
    x = podcast / "za_resolve.fcpxml"
    validate(dtd, x)
    root = ET.parse(x).getroot()
    names = {a.get("name") for a in root.iter("asset")}
    assert names == {"siroka.mp4", "kamA.mp4", "kamB.mp4", "zvuk.wav"}       # bez source.mp4
    assert all("%C4%8D" in m.get("src") for m in root.iter("media-rep"))    # „č" u putanji
    spine = list(root.find("library/event/project/sequence/spine"))
    assert len(spine) > 5
    for c in spine:                                                          # slika kamere, zvuk ide ispod
        assert c.get("srcEnable") == "video" and c.find("adjust-volume").get("amount") == "-96dB"
    # svaka kamera ima svoju traku iznad (stalnu), isključenu
    lanes = {}
    for c in spine:
        for a in c.findall("asset-clip"):
            if int(a.get("lane")) > 0:
                assert a.get("enabled") == "0" and a.get("srcEnable") == "video"
                lanes.setdefault(a.get("ref"), set()).add(a.get("lane"))
                assert a.get("ref") != c.get("ref")                          # ne ponavlja kameru iz programa
    assert len(lanes) == 3 and all(len(v) == 1 for v in lanes.values())
    # zvuk glavnog: bez rupa i preklapanja, točno trajanje timelinea
    seq = root.find("library/event/project/sequence")
    dialog = [a for c in spine for a in c.findall("asset-clip") if a.get("lane") == "-1"]
    assert all(a.get("audioRole") == "dialogue" for a in dialog)
    assert sum(T(a.get("duration")) for a in dialog) == T(seq.get("duration"))


def test_ista_slika_i_zvuk_kao_program(podcast):
    """Iz FCPXML-a složi sliku iz originalnih kamera i zvuk iz zvuk.wav (kao DaVinci) i usporedi sa Shofeovim
    programom (source.mp4) na istom mjestu: ista kamera, isti izrez (uspravni mobitel, zum stila), isti zvuk."""
    root, summ = build(podcast)
    pj = load(podcast / "project.json")
    W, H, fps = pj["width"], pj["height"], summ["fps"]
    sync = {e["ime"]: e for e in load(podcast / "sinkro.json")["izvori"]}
    assets = {a.get("id"): a for a in root.iter("asset")}
    spine = list(root.find("library/event/project/sequence/spine"))
    assert len(spine) == len(summ["pieces"])
    checked = 0
    for c, p in zip(spine, summ["pieces"]):
        a = assets[c.get("ref")]
        e = sync[a.get("name")]
        local = float(T(c.get("start")) - T(a.get("start")))
        d = float(T(c.get("duration")))
        prog = p["prog"] / fps
        # isti trenutak: vrijeme u kameri → crta glavnog → program
        assert abs(S.to_master(e, local) - (load(podcast / "rezija.json")["pocetak"] + prog)) < 1.5 / fps
        # isti trenutak i za kamere na trakama iznad
        for alt in c.findall("asset-clip"):
            if int(alt.get("lane")) > 0:
                aa = assets[alt.get("ref")]
                assert abs(S.to_master(sync[aa.get("name")], float(T(alt.get("start")) - T(aa.get("start"))))
                           - prog) < 1.5 / fps
        if d < 0.5:
            continue
        tr = c.find("adjust-transform")
        px, py = map(float, (tr.get("position", "0 0") if tr is not None else "0 0").split())
        z = float((tr.get("scale", "1 1") if tr is not None else "1 1").split()[0])
        w, h = e["w"], e["h"]
        s = max(W / w, H / h) * z
        sw, sh = round(w * s / 2) * 2, round(h * s / 2) * 2
        cx = (sw - W) / 2 - px / 100 * H
        cy = (sh - H) / 2 + py / 100 * H
        got = _frame(Path(e["datoteka"]), local + d / 2, f"scale={sw}:{sh},crop={W}:{H}:{cx:.1f}:{cy:.1f}")
        ref_vf = render.zoom_chain(z, W, H) if z != 1 else "null"
        want = _frame(podcast / "source.mp4", prog + d / 2, ref_vf)
        assert np.mean(np.abs(got - want)) < 8, (a.get("name"), prog, np.mean(np.abs(got - want)))
        checked += 1
    assert checked >= 5
    # zvuk: komad zvuk.wav na traci ispod = zvuk programa u istom trenutku
    k = 0
    for c in spine:
        for m in c.findall("asset-clip"):
            if m.get("lane") != "-1":
                continue
            s0, d = float(T(m.get("start"))), min(4.0, float(T(m.get("duration"))))
            p = next(q for q in summ["pieces"] if abs(q["out"] / fps - float(T(c.get("offset")))) < 1.5 / fps)
            x = _audio(Path(sync["zvuk.wav"]["datoteka"]), s0, d)
            y = _audio(podcast / "source.mp4", p["prog"] / fps, d)
            n = min(len(x), len(y))
            x, y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
            if np.std(y) > 50:
                cc = np.correlate(x, y, "full")[n - 1 - 400:n + 400]
                best = cc.max() / np.sqrt((x ** 2).sum() * (y ** 2).sum())
                assert best > 0.8 and abs(int(cc.argmax()) - 400) <= 200, (s0, best, int(cc.argmax()) - 400)
                k += 1
    assert k >= 3


def test_kamera_koja_ne_snima_i_nedostaje_original(podcast, tmp_path):
    root, summ = build(podcast)
    rez = load(podcast / "rezija.json")
    kamb = next(i for i, r in enumerate(rez["kamere"]) if r["ime"] == "kamB.mp4")
    for p in summ["pieces"]:
        if p["prog"] / summ["fps"] > 45.2:                                  # kamB se ugasila na 45 s
            assert p["clip"] != kamb and all(j != kamb for j, _ in p["alts"])
    # original nestao → cijeli timeline iz source.mp4, s napomenom; DaVinci uz render i dalje radi
    copy = tmp_path / "kopija"
    shutil.copytree(podcast, copy, ignore=shutil.ignore_patterns("_tmp", "verzije"))
    sync = load(copy / "sinkro.json")
    for e in sync["izvori"]:
        if e["ime"] == "kamA.mp4":
            e["datoteka"] = str(tmp_path / "nema" / "kamA.mp4")
    (copy / "sinkro.json").write_text(json.dumps(sync), encoding="utf-8")
    root, summ = build(copy)
    assert summ["izvor"] == "source.mp4" and any("kamA.mp4" in n for n in summ["napomene"])
    assert {a.get("name") for a in root.iter("asset")} == {"source.mp4"}
    # --izvor priprema: source.mp4 i kad originali postoje
    root, summ = build(podcast, use_originals=False)
    assert summ["izvor"] == "source.mp4"


def test_podcast_pieces_rez_preko_promjene_kamere():
    """Bez videa: rez programa koji prelazi promjenu kamere dijeli se na dva kadra; kamera izvan svog raspona
    ne ulazi ni u program ni na gornje trake; crno → source.mp4."""
    cams = [{"ime": "a.mp4", "pomak": -1.0, "od": -1.0, "do": 30.0},
            {"ime": "b.mp4", "pomak": 5.0, "od": 5.0, "do": 30.0}]
    pc = {"clips": [{"ime": c["ime"], "sync": c} for c in cams], "pocetak": 0.0,
          "kadrovi": [{"od": 0.0, "do": 5.0, "kamera": "a.mp4"}, {"od": 5.0, "do": 10.0, "kamera": "b.mp4"},
                      {"od": 10.0, "do": 12.0, "kamera": None}, {"od": 12.0, "do": 30.0, "kamera": "a.mp4"}]}
    cuts = [{"a": 2.0, "b": 8.0, "o": 0.0}, {"a": 9.0, "b": 13.0, "o": 6.0}]
    ps = davinci.podcast_pieces(cuts, pc, 30)
    got = [(p["clip"], p["prog"], p["frames"], p["out"], p["cut"]) for p in ps]
    assert got == [(0, 60, 90, 0, 0), (1, 150, 90, 90, 0), (1, 270, 30, 180, 1), (None, 300, 60, 210, 1),
                   (0, 360, 30, 270, 1)]
    assert ps[0]["src"] == Fraction(3)                     # a.mp4 krenula 1 s prije glavnog
    assert ps[1]["src"] == Fraction(0)                     # b.mp4 od 5 s
    assert ps[0]["alts"] == []                             # b.mp4 još ne snima: nije ni na traci iznad
    assert ps[1]["alts"] == [(0, Fraction(6))]
    assert ps[3]["alts"] == [(0, Fraction(11)), (1, Fraction(5))]   # crno u programu, kamere iznad
    # kamera koju je režija izabrala, a ne snima cijeli dio (ručno mijenjan rezija.json) → crno, ne kriva slika
    pc["kadrovi"][1]["od"], pc["kadrovi"][0]["do"] = 4.0, 4.0
    ps = davinci.podcast_pieces([{"a": 4.0, "b": 6.0, "o": 0.0}], pc, 30)
    assert [p["clip"] for p in ps] == [None]
