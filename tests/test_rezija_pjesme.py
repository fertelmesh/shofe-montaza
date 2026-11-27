"""M4.3b2: režija za vrijeme pjesme (široki kadar, spori rezovi na udarac) i pjesme u DaVinciju (oznaka cijelom
duljinom, zvuk pjesme na vlastitoj traci). Ritam (ritam.py) na sintetskom bendu iz make_nastup."""
import json
import shutil
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

import davinci  # noqa: E402
import make_nastup as MN  # noqa: E402
import rezija as R  # noqa: E402
import ritam  # noqa: E402
from conftest import run_script as run  # noqa: E402
from test_davinci import dtd, validate  # noqa: E402,F401
from test_rezija import at, check_basic, setup  # noqa: E402

T = davinci.parse_time


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def band(dur, bpm, sr=ritam.SR, **kw):
    x = MN.band(dur, bpm=bpm, **kw)
    t = np.arange(int(len(x) / MN.SR * sr)) / sr
    return np.interp(t, np.arange(len(x)) / MN.SR, x)


# ---------------------------------------------------------------- ritam

@pytest.mark.parametrize("bpm", [84, 112])
def test_tempo_i_udarci_benda(bpm):
    r = ritam.analyse(band(40.0, bpm))
    assert r["jasno"] and r["bpm"] == pytest.approx(bpm, abs=2)
    d = np.diff(r["udarci"])
    assert np.median(d) == pytest.approx(60 / bpm, abs=0.02)
    # udarci na pravim mjestima: bend udara na k · 60/bpm (+ sredina okvira analize)
    beat = 60 / bpm
    off = [(t % beat) for t in r["udarci"]]
    err = [min(o, beat - o) for o in off]
    assert np.median(err) < 0.05
    assert r["udarci"][0] < 1.5 and r["udarci"][-1] > 37


def test_govor_nema_jasan_ritam():
    x = ritam.decode(ROOT / "tests" / "fixtures" / "razgovor.m4a")
    r = ritam.analyse(x)
    assert not r["jasno"]
    assert ritam.analyse(np.zeros(1000))["bpm"] is None


# ---------------------------------------------------------------- pravila (bez videa)

BEATS = [round(30.33 + k * 60 / 112, 3) for k in range(int(59.5 / (60 / 112)))]


def test_rezovi_u_pjesmi_na_taktu():
    cuts, per = R.song_cuts(30.03, 89.87, 8.0, BEATS)
    assert per == 4 and len(cuts) >= 5
    grid = BEATS[::4]
    for c in cuts:
        assert min(abs(c - g) for g in grid) < 1e-6          # svaki rez na početku takta (4 udarca)
    lens = np.diff([30.03] + cuts + [89.87])
    assert lens.min() >= R.PJESMA_MIN - 1e-6
    assert lens[0] > lens[1] and np.mean(lens) == pytest.approx(8.0, abs=1.5)
    # bez ritma: po sekundama; 0 = bez rezova; pola tempa (70 BPM) → 2 udarca su takt
    c2, p2 = R.song_cuts(30.0, 90.0, 8.0, [])
    assert p2 is None and c2[0] == pytest.approx(30 + 8 * R.PJESMA_UVOD)
    assert R.song_cuts(30.0, 90.0, 0, BEATS) == ([], None)
    assert R.song_cuts(0, 60, 8.0, [k * 60 / 70 for k in range(70)])[1] == 2


def test_rezija_za_vrijeme_pjesme():
    cams, roles = setup(dur=150)
    # „govornik" G1 u pjesmi = pjevanje: ne prati se
    segs = [(1, 18, "G1"), (18.5, 30, "G2"), (31, 90, "G1"), (92, 140, "G2")]
    songs = [{"id": "P1", "od": 30.03, "do": 89.87, "udarci": BEATS}]
    shots = R.direct(segs, cams, roles, 0.0, 150.0, {}, "nikad", songs=songs)
    check_basic(shots, 150)
    inside = [s for s in shots if s.get("pjesma") == "P1"]
    assert inside[0]["od"] == pytest.approx(30.03) and inside[-1]["do"] == pytest.approx(89.87)
    assert inside[0]["kamera"] == inside[-1]["kamera"] == "siroka.mp4"          # počne i završi široko
    assert all(s["do"] - s["od"] >= R.PJESMA_MIN - 1e-6 for s in inside)
    assert {s["kamera"] for s in inside} == {"siroka.mp4", "kamG1.mp4", "kamG2.mp4"}   # izmjena svih kamera
    wide = sum(s["do"] - s["od"] for s in inside if s["kamera"] == "siroka.mp4")
    assert wide > 0.55 * (89.87 - 30.03)                                     # široki prevladava
    for x in inside[1:]:
        assert min(abs(x["od"] - b) for b in BEATS[::4]) < 1e-6              # rez točno na udarcu
    assert "pjesma P1: široki kadar" == inside[0]["zasto"]
    assert at(shots, 10)["kamera"] == "kamG1.mp4" and at(shots, 100)["kamera"] == "kamG2.mp4"  # govor kao prije
    # 0 = cijela pjesma u širokom; bez širokog kadra kamere idu redom
    shots0 = R.direct(segs, cams, roles, 0.0, 150.0, {}, "nikad", songs=[dict(songs[0])], pjesma_kadar=0)
    assert at(shots0, 30.1)["kamera"] == "siroka.mp4" and at(shots0, 30.1)["do"] == pytest.approx(89.87)
    cams2, roles2 = setup(wide=False, dur=150)
    shots2 = R.direct(segs, cams2, roles2, 0.0, 150.0, {}, "nikad", songs=[dict(songs[0])])
    ins2 = [s["kamera"] for s in shots2 if s.get("pjesma")]
    assert len(ins2) >= 4 and set(ins2) == {"kamG1.mp4", "kamG2.mp4"}


def test_pjesma_i_kamera_koja_ne_snima():
    cams, roles = setup(dur=120, od={"kamG2.mp4": 60.0})          # kamG2 krene tek na 60 s
    songs = [{"id": "P1", "od": 20.0, "do": 80.0, "udarci": []}]
    shots = R.direct([(1, 19, "G1"), (81, 119, "G2")], cams, roles, 0.0, 120.0, {}, "nikad", songs=songs)
    check_basic(shots, 120)
    for s in shots:
        if s["kamera"] == "kamG2.mp4":
            assert s["od"] >= 60.0 - 1e-6
    assert all(s["do"] - s["od"] >= R.MIN_KADAR - 1e-6 for s in shots)


# ---------------------------------------------------------------- cijeli put: podcast s bendom

@pytest.fixture(scope="module")
def bend(podcast, tmp_path_factory):
    """Kopija probne epizode u kojoj od 20 do 45 s glavni zvuk svira bend (112 BPM); pjesma ručno u nastupi.json."""
    import make_rezija as MR
    base = tmp_path_factory.mktemp("bend")
    snim = base / "snimke"
    shutil.copytree(podcast.parent / "Sunčani4M snimke", snim)
    proj = base / "epizoda"
    shutil.copytree(podcast, proj, ignore=shutil.ignore_patterns("_tmp", "isjecci"))
    x = MR.decode(snim / "zvuk.wav")
    y = band(25.0, 112, sr=MR.SR, intro=2.0)
    i0 = int(20.0 * MR.SR)
    x[i0:i0 + len(y)] = 0.8 * y + 0.05 * x[i0:i0 + len(y)]
    MR.write_wav(snim / "zvuk.wav", x)
    sp = proj / "sinkro.json"
    s = load(sp)
    for e in s["izvori"]:
        e["datoteka"] = str((snim / Path(e["datoteka"]).name).resolve())
    sp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    assert "ponovno pokreni rezija.py" in run("nastupi.py", proj, "dodaj", "0:20-0:45", "--naziv", "Bend – Kutina")
    out = run("rezija.py", proj)
    assert load(proj / "edit.json")["nastupi"][0]["id"] == "P1"     # nastupi.py osvježio edit.json
    return proj, out


def test_podcast_bend_rezija(bend):
    proj, out = bend
    rez = load(proj / "rezija.json")
    p = rez["pjesme"][0]
    assert p["id"] == "P1" and p["bpm"] == pytest.approx(112, abs=2) and p["takt"] == 4
    assert "Pjesma P1 „Bend – Kutina“" in out and "rez na početku takta" in out
    inside = [s for s in rez["kadrovi"] if s.get("pjesma") == "P1"]
    assert inside[0]["kamera"] == inside[-1]["kamera"] == "siroka.mp4" and len(inside) >= 3
    assert all(s["do"] - s["od"] >= R.PJESMA_MIN - 1e-6 for s in inside)
    beat = 60 / 112
    for s in inside[1:]:                                              # rez na udarac benda (od 20 s)
        o = (s["od"] - 20.0) % beat
        assert min(o, beat - o) < 0.06, s
    assert (proj / "rezija.png").stat().st_size > 10000
    # program: u pjesmi na 21 s široki kadar (plava pozadina), slika se mijenja tek nakon ≥ 4 s
    from test_rezija import pixel
    import make_rezija as MR
    got = pixel(proj / "source.mp4", 21.0)
    want = np.array(MR.BOJE["siroka.mp4"][::-1])
    assert np.abs(want - got).sum() < min(np.abs(np.array(c[::-1]) - got).sum()
                                          for k, c in MR.BOJE.items() if k != "siroka.mp4")
    # --pjesma-kadar 0: cijela pjesma u širokom; vrijednost se pamti
    run("rezija.py", proj, "--analiza", "--pjesma-kadar", "0")
    rez0 = load(proj / "rezija.json")
    assert rez0["pjesma_kadar"] == 0
    assert [s["kamera"] for s in rez0["kadrovi"] if s.get("pjesma")] == ["siroka.mp4"]
    run("rezija.py", proj, "--analiza", "--pjesma-kadar", "8")


def test_podcast_bend_davinci(bend, dtd):
    proj, _ = bend
    out = run("davinci.py", proj, "--trenutno", "--izlaz", "bend")
    assert "zvuk pjesme na traci A2" in out
    x = proj / "bend.fcpxml"
    validate(dtd, x)
    root = ET.parse(x).getroot()
    seq = root.find("library/event/project/sequence")
    spine = list(seq.find("spine"))
    clips = [a for c in spine for a in c.findall("asset-clip")]
    dialog = [a for a in clips if a.get("lane") == "-1"]
    song = [a for a in clips if a.get("lane") == "-2"]
    assert all(a.get("audioRole") == "dialogue" for a in dialog)
    assert song and all(a.get("audioRole") == "music" and "pjesma P1" in a.get("name") for a in song)
    # govor + pjesma = cijeli timeline, bez rupa; pjesma ≈ 25 s
    assert sum(T(a.get("duration")) for a in dialog + song) == T(seq.get("duration"))
    assert float(sum(T(a.get("duration")) for a in song)) == pytest.approx(25.0, abs=0.1)
    # zvuk pjesme iz glavnog izvora u pravom trenutku: početak pjesme u zvuk.wav na 20 s
    first = min(song, key=lambda a: T(a.get("start")))
    assert float(T(first.get("start"))) == pytest.approx(20.0, abs=0.05)
    marks = {m.get("value"): m for m in root.iter("marker")}
    m = marks["Pjesma P1: Bend – Kutina"]
    assert float(T(m.get("duration"))) == pytest.approx(25.0, abs=0.1) and "ne reže" in m.get("note")
    assert "Kraj pjesme P1" in marks


def test_obican_projekt_pjesma_na_svojoj_traci(tmp_path, dtd):
    """Projekt bez podcasta (jedan izvor): kadar koji zahvaća pjesmu daje samo sliku, zvuk ispod podijeljen."""
    proj = MN.make(tmp_path / "nastup")
    run("nastupi.py", proj, "dodaj", "0:20-1:11")
    run("plan.py", proj, "--stil", "podcast")
    root, summ = davinci.build(proj, load(proj / "edit.json"))
    assert summ["pjesama"] == 1 and summ["zvuk_pjesme"] >= 1
    x = tmp_path / "t.fcpxml"
    davinci.write(root, x)
    validate(dtd, x)
    spine = list(root.find("library/event/project/sequence/spine"))
    song = [a for c in spine for a in c.findall("asset-clip") if a.get("lane") == "-2"]
    assert float(sum(T(a.get("duration")) for a in song)) == pytest.approx(51.0, abs=0.1)
    # kadrovi s pjesmom: slika bez zvuka; ostali kadrovi zadrže svoj zvuk
    with_song = [c for c in spine if any(a.get("lane") == "-2" for a in c.findall("asset-clip"))]
    assert with_song and all(c.get("srcEnable") == "video" for c in with_song)
    assert any(c.get("srcEnable") is None for c in spine)
    # isti zvuk: dio pjesme na traci = isti trenutak snimke kao slika iznad
    for c in with_song:
        for a in c.findall("asset-clip"):
            if a.get("lane") in ("-1", "-2"):
                d = T(a.get("offset")) - T(c.get("start"))
                assert T(a.get("start")) - T(c.get("start")) == d


def test_podcast_bend_isjecak_pjesme_9x16(bend, tmp_path):
    """M4.3b3: isječak iz pjesme podcasta ide kroz uspravni izvor iz kamera (9:16) bez greške."""
    proj = tmp_path / "ep"
    shutil.copytree(bend[0], proj, ignore=shutil.ignore_patterns("_tmp", "isjecci", "isjecci.json"))
    out = run("isjecci.py", proj, "pjesma", "P1")
    d = load(proj / "isjecci.json")
    c = d["isjecci"][0]
    assert c["vrsta"] == "pjesma" and (c["od"], c["do"]) == pytest.approx((20.0, 45.0), abs=0.6), out
    assert c["hook"] == "Bend – Kutina uživo"          # iz naziva pjesme
    out = run("isjecci.py", proj, "render", c["id"], "--kadar", "2,15")
    assert "9:16" in out
    from PIL import Image
    assert (proj / "isjecci" / f"{c['id']}_kadrovi.png").exists()
    im = Image.open(proj / "kadar_1_2s.png")
    assert im.height > im.width                         # uspravni kadar
