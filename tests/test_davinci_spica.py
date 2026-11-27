"""M4.4d: špice i poglavlja epizode u DaVinci timelineu — uvodna špica na istom mjestu kao u Shofeovu videu
(kadar se podijeli, sve iza se pomakne, glazba i zvuk ispod ne prelaze preko špice), odjavna na kraju,
poglavlja kao chapter-marker oznake + EDL s oznakama za DaVinci (Chapters from Markers)."""
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
import make_nastup as MN  # noqa: E402
from test_davinci import _audio, dtd, validate  # noqa: E402,F401
from test_spica import SONG, TEME, env_with, intro_klip, load, run, save  # noqa: E402

T = davinci.parse_time


def spine_of(root):
    return list(root.find("library/event/project/sequence/spine"))


def abs_pos(parent, child):
    """Položaj usidrenog elementa (klip ili oznaka) na timelineu u sekundama."""
    key = "offset" if child.tag == "asset-clip" else "start"
    return float(T(parent.get("offset")) + T(child.get(key)) - T(parent.get("start")))


# ---------------------------------------------------------------- bez videa
def test_podjela_kadra_na_tocki_spice():
    pieces = [{"clip": None, "src": Fraction(0), "frames": 90, "out": 0, "cut": 0, "prog": 0,
               "alts": [(1, Fraction(5))]},
              {"clip": None, "src": Fraction(10), "frames": 60, "out": 90, "cut": 1, "prog": 300, "alts": []}]
    of, tot = davinci.frames_of(pieces, 1)
    res, idx = davinci.split_pieces_at(pieces, of, 30, 1, 30)
    assert idx == 1 and [p["frames"] for p in res] == [30, 60, 60]
    b = res[1]
    assert b["src"] == 1 and b["out"] == 30 and b["prog"] == 30 and b["alts"] == [(1, 6)]
    assert b["cut"] != res[0]["cut"] and res[2]["cut"] == 1           # zvuk iza špice je novi komad
    # točka na rezu: ništa se ne dijeli
    res, idx = davinci.split_pieces_at(pieces, of, 90, 1, 30)
    assert idx == 1 and len(res) == 2
    res, idx = davinci.split_pieces_at(pieces, of, 0, 1, 30)
    assert idx == 0 and len(res) == 2
    # ubrzano (1,5×): 20 sličica gotovog videa = 30 sličica snimke
    of, tot = davinci.frames_of(pieces, 1.5)
    res, idx = davinci.split_pieces_at(pieces, of, 20, 1.5, 30)
    assert [p["frames"] for p in res[:2]] == [30, 60]
    o2, t2 = davinci.frames_of(res, 1.5)
    assert o2[idx][0] == 20 and t2 == tot


def test_edl_oznaka_poglavlja():
    assert davinci.tc(0, 30) == "00:00:00:00" and davinci.tc(30 * 3661 + 7, 30) == "01:01:01:07"
    ch = [{"od": 0, "naslov": "Dobrodošli u auto"}, {"od": 75.48, "naslov": "Pjesma: Bend | Ljeto"},
          {"od": 3700.0, "naslov": "Što   dalje"}]
    t = davinci.marker_edl(ch, 25, "Sunčani4M ep/12")
    lines = t.split("\r\n")
    assert lines[:3] == ["TITLE: Sunčani4M ep_12", "FCM: NON-DROP FRAME", ""]
    ev = [ln for ln in lines if ln[:3].isdigit()]
    assert ev[1] == "002  001      V     C        00:01:15:12 00:01:15:13 00:01:15:12 00:01:15:13"
    com = [ln for ln in lines if ln.startswith(" |C:")]
    assert com == [" |C:ResolveColorGreen |M:Dobrodošli u auto |D:1",
                   " |C:ResolveColorGreen |M:Pjesma: Bend / Ljeto |D:1",
                   " |C:ResolveColorGreen |M:Što dalje |D:1"]
    assert ev[2].split()[4] == "01:01:40:00"


# ---------------------------------------------------------------- probna epizoda
@pytest.fixture(scope="module")
def ep(tmp_path_factory):
    base = tmp_path_factory.mktemp("davinci špica čž")
    proj = MN.make(base / "ep")
    save(proj / "nastupi.json", {"nastupi": [dict(SONG)]})
    save(proj / "analiza.json", {"teme": TEME})
    run("plan.py", proj, "--stil", "podcast")
    intro_klip(base / "moj intro.mp4")
    env = env_with(base)
    run("spica.py", proj, "dodaj", "--uvod", base / "moj intro.mp4", "--poslije", "0:10", "--odjava", "generirana",
        "--trajanje-odjave", "8", "--naslov", "Bend iz Kutine", "--broj", "12", env=env)
    r = run("render.py", proj, env=env)
    return proj, r.stdout, env


def test_timeline_sa_spicama_kao_shofeov_video(ep, dtd):
    proj, out, env = ep
    assert "špica u timelineu: uvodna na 00:" in out and "odjavna na kraju" in out
    assert "reel_v1.poglavlja.edl" in out
    x = proj / "reel_v1.fcpxml"
    validate(dtd, x)
    root = ET.parse(x).getroot()
    seq = root.find("library/event/project/sequence")
    spine = spine_of(root)
    assets = {a.get("id"): a for a in root.iter("asset")}
    names = [assets[c.get("ref")].get("name") for c in spine]
    assert "moj intro.mp4" in names and names[-1].startswith("spica_odjava_") and names[-1].endswith(".mov")
    assert (proj / "spica" / names[-1]).exists()
    # glavna traka bez rupa i preklapanja; trajanje = video sa špicom
    t = Fraction(0)
    for c in spine:
        assert T(c.get("offset")) == t
        t += T(c.get("duration"))
    assert t == T(seq.get("duration"))
    vid = proj / "reel_v1.mp4"
    dur = float(json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                                           str(vid)], capture_output=True, text=True).stdout)["format"]["duration"])
    assert float(t) == pytest.approx(dur, abs=0.08)
    # uvodna špica: Markova datoteka (4:3 → Fit kao crni rub), 3 s, na istom mjestu kao u videu (crvena slika)
    k = names.index("moj intro.mp4")
    intro = spine[k]
    at = float(T(intro.get("offset")))
    assert 7.0 <= at <= 13.0 and float(T(intro.get("duration"))) == pytest.approx(3.0, abs=0.04)
    assert intro.find("adjust-conform").get("type") == "fit"
    assert intro.find("marker").get("value") == "Uvodna špica"
    fr = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{at + 1.5:.3f}", "-i", str(vid), "-frames:v", "1",
                         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(fr, np.uint8).reshape(180, 320, 3).astype(float)
    assert f[:, 60:260, 0].mean() > 180 and f[:, 60:260, 1].mean() < 60
    # iza špice glavni video nastavlja točno gdje je stao (na rezu ili usred kadra koji se podijeli)
    import render
    edit = load(proj / "edit.json")
    pj = load(proj / "project.json")
    cuts, _, _ = render.build_cuts(load(proj / "transcript.json")["words"], edit, render.resolve_style(edit),
                                   pj["fps"], pj["duration"])
    before, after = spine[k - 1], spine[k + 1]
    assert float(T(after.get("start"))) == pytest.approx(davinci.out_to_source(at, cuts), abs=1.5 / 30)
    assert float(T(before.get("offset")) + T(before.get("duration"))) == pytest.approx(at)
    # svaki komad glavnog videa: isti zvuk na istom mjestu kao u Shofeovu videu
    lags = []
    for c in spine:
        a = assets[c.get("ref")]
        if a.get("name") != "source.mp4":
            continue
        pos, d = float(T(c.get("offset"))), min(3.0, float(T(c.get("duration"))))
        s0 = float(T(c.get("start")))
        if d < 1.0 or (s0 < SONG["do"] and s0 + d > SONG["od"]):   # ritam pjesme: korelacija dvoznačna
            continue
        xs = _audio(proj / "source.mp4", s0, d)
        ys = _audio(vid, pos, d)
        n = min(len(xs), len(ys))
        xs, ys = xs[:n] - xs[:n].mean(), ys[:n] - ys[:n].mean()
        if np.std(ys) < 50:
            continue
        cc = np.correlate(xs, ys, "full")[n - 1 - 400:n + 400]
        best = cc.max() / np.sqrt((xs ** 2).sum() * (ys ** 2).sum())
        assert best > 0.3, (pos, best)
        lags.append(int(cc.argmax()) - 400)
    # isti pomak svuda (AAC kasni ~25 ms), i prije i iza špice — sličica razlike bila bi 267 uzoraka
    assert len(lags) >= 4 and max(lags) - min(lags) <= 40 and abs(lags[0]) <= 320, lags
    # zvuk iz snimke ispod slike (pjesma A2 / govor A1) nikad ne svira ispod špice
    for c in spine:
        for m in c.findall("asset-clip"):
            s0 = abs_pos(c, m)
            e0 = s0 + float(T(m.get("duration")))
            assert e0 <= at + 1e-6 or s0 >= at + 3.0 - 1e-6, (m.get("name"), s0, e0)
    # poglavlja: oznake na istom mjestu kao u YouTube opisu (chapters.json) + EDL za DaVinci
    import epizoda
    chap = [{"title": c["naslov"], "startTime": c["od"]} for c in epizoda.poglavlja_za(proj, edit)[0]]
    assert len(chap) >= 3
    marks = sorted((abs_pos(c, m), m.get("value")) for c in spine for m in c.findall("chapter-marker"))
    assert [v for _, v in marks] == [c["title"] for c in chap]
    for (p, _), c in zip(marks, chap):
        assert p == pytest.approx(c["startTime"], abs=0.05)
    edl = (proj / "reel_v1.poglavlja.edl").read_text(encoding="utf-8")
    assert edl.count("|C:ResolveColorGreen") == len(chap) and "|M:Pjesma: Bend Kutina – Ljeto |D:1" in edl
    tcs = [ln.split()[4] for ln in edl.splitlines() if ln[:3].isdigit()]
    for tc_, c in zip(tcs, chap):
        h, m_, s_, fr_ = map(int, tc_.split(":"))
        assert (h * 3600 + m_ * 60 + s_ + fr_ / 30) == pytest.approx(c["startTime"], abs=0.04)


def test_spica_s_poglavljima_glazba_i_brzina(ep, dtd, tmp_path):
    """Duga uvodna (12 s) i odjavna (15 s) su svoja poglavlja; pozadinska glazba pauzira za špicu;
    ubrzani video: špica nije ubrzana; davinci.py iz naredbenog retka (SRT pomaknut za špicu)."""
    src, _, env = ep
    p = tmp_path / "p"
    shutil.copytree(src, p)
    run("spica.py", p, "dodaj", "--uvod", "generirana", "--trajanje-uvoda", "12", "--poslije", "0:10",
        "--odjava", "generirana", "--trajanje-odjave", "15", env=env)
    edit = load(p / "edit.json")
    edit["glazba"] = str(FIX / "glazba.mp3")
    edit["brzina"] = 1.25
    save(p / "edit.json", edit)
    root, summ = davinci.build(p, edit, glavni=True)
    sp = summ["spica"]
    assert sp["uvod"] == 12 * 30 and sp["odjava"] == 15 * 30
    spine = spine_of(root)
    names = [c.get("name") for c in spine]
    k = next(i for i, n in enumerate(names) if n.startswith("Uvodna špica"))
    intro = spine[k]
    at = float(T(intro.get("offset")))
    assert intro.find("timeMap") is None and float(T(intro.get("duration"))) == pytest.approx(12.0)
    assert names[-1].startswith("Odjavna špica")
    seq_d = float(T(root.find("library/event/project/sequence").get("duration")))
    assert seq_d == pytest.approx(summ["sekundi"])
    # glazba: ništa ispod uvodne špice, ukupno traje koliko glavni video (bez špica)
    music = [(abs_pos(c, m), float(T(m.get("duration"))), float(T(m.get("start"))))
             for c in spine for m in c.findall("asset-clip") if m.get("name") == "glazba.mp3"]
    assert music and all(e <= at + 1e-6 or s >= at + 12 - 1e-6 for s, e in ((s, s + d) for s, d, _ in music))
    assert sum(d for _, d, _ in music) == pytest.approx(seq_d - 27.0, abs=0.05)
    assert any(st > 0 for _, _, st in music)      # dio iza špice nastavlja istu pjesmu
    # poglavlja: Uvod i Odjava kao svoja poglavlja (≥ 10 s), isto kao u YouTube opisu
    ch = [(round(abs_pos(c, m), 2), m.get("value")) for c in spine for m in c.findall("chapter-marker")]
    vals = [v for _, v in sorted(ch)]
    import epizoda
    want = epizoda.poglavlja_za(p, edit)[0]
    assert vals == [c["naslov"] for c in want] and "Uvod" in vals and "Odjava" in vals
    for (t, _), c in zip(sorted(ch), want):
        assert t == pytest.approx(c["od"], abs=0.04)
    pos = dict((v, t) for t, v in ch)
    # (najava prije špice je kraća od 10 s pa ide u „Uvod" koji onda kreće od 00:00 — pravilo YouTubea)
    assert pos["Uvod"] == pytest.approx(0.0)
    assert pos["Odjava"] == pytest.approx(seq_d - 15.0, abs=0.04)
    # naredbeni redak: --trenutno → timeline, EDL i SRT u vremenu videa sa špicom
    r = run("davinci.py", p, "--trenutno", "--izlaz", "za_resolve", env=env)
    assert "Timeline Markers from EDL" in r.stdout and "u timelineu" in r.stdout
    validate(dtd, p / "za_resolve.fcpxml")
    assert (p / "za_resolve.poglavlja.edl").exists()
    srt = (p / "za_resolve.srt").read_text(encoding="utf-8-sig")
    spans = []
    for block in srt.strip().split("\n\n"):
        a, b = [sum(float(x) * m for x, m in zip(t.replace(",", ".").split(":"), (3600, 60, 1)))
                for t in block.splitlines()[1].split(" --> ")]
        spans.append((a, b))
    assert not any(a < at + 12 - 0.01 and b > at + 0.01 for a, b in spans)


def test_podcast_zvuk_ne_prelazi_spicu(podcast, dtd, tmp_path):
    """Podcast: program iz originalnih kamera; zvuk glavnog izvora (A1) podijeljen na točki špice, ostale kamere
    na trakama iznad nastavljaju iza špice u istom trenutku."""
    import sinkro as S
    p = tmp_path / "pod"
    shutil.copytree(podcast, p)
    env = env_with(tmp_path)
    run("spica.py", p, "dodaj", "--uvod", "generirana", "--trajanje-uvoda", "4", "--poslije", "0:20",
        "--odjava", "nema", env=env)
    run("davinci.py", p, "--trenutno", "--izlaz", "za_resolve", env=env)
    x = p / "za_resolve.fcpxml"
    validate(dtd, x)
    root = ET.parse(x).getroot()
    spine = spine_of(root)
    k = next(i for i, c in enumerate(spine) if c.get("name").startswith("Uvodna špica"))
    at = float(T(spine[k].get("offset")))
    assert 15.0 < at < 25.0 and not any(c.get("name").startswith("Odjavna") for c in spine)
    dialog = [(abs_pos(c, m), float(T(m.get("duration"))), c, m) for c in spine for m in c.findall("asset-clip")
              if m.get("lane") == "-1"]
    assert all(s + d <= at + 1e-6 or s >= at + 4 - 1e-6 for s, d, _, _ in dialog)
    seq_d = float(T(root.find("library/event/project/sequence").get("duration")))
    assert sum(d for _, d, _, _ in dialog) == pytest.approx(seq_d - 4.0, abs=1e-6)
    # zvuk iza špice nastavlja točno gdje je program stao (zvuk.wav u trenutku programa iza točke špice)
    import render
    sync = {e["ime"]: e for e in load(p / "sinkro.json")["izvori"]}
    edit = load(p / "edit.json")
    pj = load(p / "project.json")
    cuts, _, _ = render.build_cuts(load(p / "transcript.json")["words"], edit, render.resolve_style(edit),
                                   pj["fps"], pj["duration"])
    rp = load(p / "rezija.json")["pocetak"]
    master = next(e for e in sync.values() if e.get("glavni"))
    m_after = min((q for q in dialog if q[0] >= at), key=lambda q: q[0])
    assert m_after[0] == pytest.approx(at + 4.0, abs=1e-6)
    want = S.to_source(master, rp + davinci.out_to_source(at, cuts))
    assert float(T(m_after[3].get("start"))) == pytest.approx(want, abs=1.5 / 30)
    # ostale kamere iza špice u istom trenutku kao kadar programa
    after = spine[k + 1]
    assets = {a.get("id"): a for a in root.iter("asset")}
    main_t = S.to_master(sync[assets[after.get("ref")].get("name")],
                         float(T(after.get("start")) - T(assets[after.get("ref")].get("start"))))
    for alt in after.findall("asset-clip"):
        if int(alt.get("lane")) > 0:
            aa = assets[alt.get("ref")]
            t_alt = S.to_master(sync[aa.get("name")], float(T(alt.get("start")) - T(aa.get("start"))))
            assert t_alt == pytest.approx(main_t - rp, abs=1.5 / 30) or t_alt == pytest.approx(main_t, abs=1.5 / 30)
