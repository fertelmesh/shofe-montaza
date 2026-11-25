"""M2.6: izvoz u DaVinci Resolve — FCPXML 1.10 s originalnim snimkama i istim rezovima + SRT."""
import json
import shutil
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
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import davinci  # noqa: E402
import render  # noqa: E402
import verzije  # noqa: E402

# Appleov DTD za FCPXML 1.10 (ne nosimo ga u repozitoriju: Appleov je); bez interneta test se preskače
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


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


T = davinci.parse_time


@pytest.fixture(scope="module")
def dtd(tmp_path_factory):
    try:
        from lxml import etree
    except ImportError:
        pytest.skip("lxml nije instaliran")
    p = tmp_path_factory.mktemp("dtd") / "FCPXMLv1_10.dtd"
    try:
        with urllib.request.urlopen(DTD_URL, timeout=20) as r:
            p.write_bytes(r.read())
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DTD nije dostupan ({e})")
    return etree.DTD(str(p))


def validate(dtd, path):
    from lxml import etree
    ok = dtd.validate(etree.parse(str(path)))
    assert ok, dtd.error_log.filter_from_errors()


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    """Vodoravni 29,97 fps klip (izrezan lijevo, crop-x 0.3) + uspravni 30 fps klip, u mapi s razmacima i kvačicama."""
    base = tmp_path_factory.mktemp("davinci čćž")
    clips = base / "Sunčani put snimke"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    p = base / "shofe_projekt"
    run("prepare.py", clips, "--out", p, "--crop", "klip1=0.3")
    pj = load(p / "project.json")
    mock = load(FIX / "mock_words.json")
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    save(p / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", p, "--stil", "suncani")
    edit = load(p / "edit.json")
    edit["hook"] = "Klima smrdi? Očisti je sam"
    edit["glazba"] = str(FIX / "glazba.mp3")
    save(p / "edit.json", edit)
    return p


def spine_clips(root):
    return list(root.find("library/event/project/sequence/spine"))


# ---------------------------------------------------------------- pomoćne funkcije
def test_time_and_rates():
    assert davinci.ftime(Fraction(1001, 30000)) == "1001/30000s" and davinci.ftime(5) == "5s"
    assert T("1001/30000s") == Fraction(1001, 30000) and T("5s") == 5
    assert davinci.snap_rate("2997/100") == Fraction(30000, 1001)
    assert davinci.snap_rate("30/1") == 30 and davinci.snap_rate("1798/60") == Fraction(30000, 1001)
    assert davinci.snap_rate("0/0") is None and davinci.snap_rate("1000/1") is None
    assert davinci.parse_tc("01:00:00:00", Fraction(25)) == 3600
    assert davinci.parse_tc("00:01:00;02", Fraction(30000, 1001)) == Fraction(1800, Fraction(30000, 1001))
    assert davinci.file_uri("C:\\Videi\\Sunčani put\\klip 1.mp4") == "file:///C:/Videi/Sun%C4%8Dani%20put/klip%201.mp4"


def test_pieces_split_at_clip_join():
    clips = [{"start": 0.0, "dur": 10.0}, {"start": 10.0, "dur": 5.0}]
    cuts = [{"a": 1.0, "b": 2.0, "o": 0.0}, {"a": 9.0, "b": 11.0, "o": 1.0}]
    ps = davinci.pieces_for(cuts, clips, 30, True)
    assert [(p["clip"], p["src"], p["frames"], p["out"]) for p in ps] == [
        (0, 1, 30, 0), (0, 9, 30, 30), (1, 0, 30, 60)]
    ps = davinci.pieces_for(cuts, clips, 30, False)
    assert [(p["clip"], p["src"], p["frames"]) for p in ps] == [(None, 1, 30), (None, 9, 60)]


def test_framing_matches_prepare_crop_and_zoom():
    W, H = 1080, 1920
    assert davinci.framing({"w": 1080, "h": 1920, "crop_x": 0.5, "crop_y": 0.4}, W, H) == (0.0, 0.0)
    px, py = davinci.framing({"w": 1280, "h": 720, "crop_x": 0.3, "crop_y": 0.4}, W, H)
    # 1280×720 → 3413×1920, prepare reže od x = 0.3·2333 umjesto sredine 0.5·2333 → slika ide 467 px desno
    assert abs(px / 100 * H - 0.2 * (1280 * H / 720 - W)) < 1 and py == 0
    _, pz = davinci.framing({"w": 1080, "h": 1920}, W, H, zoom=1.16)
    assert abs(pz / 100 * H + 0.12 * 0.16 * H) < 0.5       # zum kadrira na 38 % visine → slika malo dolje


# ---------------------------------------------------------------- na projektu
def test_render_writes_valid_fcpxml_with_originals(proj, dtd):
    out = run("render.py", proj, "--brzo").stdout
    v = verzije.viewed(proj)
    x = proj / f"reel_v{v}_pregled.fcpxml"
    assert x.exists() and x.name in out and "originalnih snimki" in out
    assert (proj / f"reel_v{v}_pregled.srt").exists()
    validate(dtd, x)
    root = ET.parse(x).getroot()
    assert root.get("version") == "1.10"
    srcs = [m.get("src") for m in root.iter("media-rep")]
    assert any(s.endswith("/Sun%C4%8Dani%20put%20snimke/klip1.mp4") for s in srcs), srcs
    assert all(s.startswith("file:///") for s in srcs)
    pj = load(proj / "project.json")
    seq = root.find("library/event/project/sequence")
    fmt = root.find(f"resources/format[@id='{seq.get('format')}']")
    assert (fmt.get("width"), fmt.get("height"), fmt.get("frameDuration")) == ("1080", "1920", "1/30s")

    # kadrovi slijede jedan za drugim bez rupa, sve na sličicama, ukupno = trajanje Shofeova videa
    clips = spine_clips(root)
    pos = Fraction(0)
    for c in clips:
        assert T(c.get("offset")) == pos
        assert (T(c.get("duration")) * 30).denominator == 1
        pos += T(c.get("duration"))
    assert pos == T(seq.get("duration"))
    dur = float(json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-print_format", "json", "-show_streams",
         str(proj / f"reel_v{v}_pregled.mp4")], capture_output=True, text=True, encoding="utf-8").stdout)
        ["streams"][0]["duration"])
    assert abs(float(pos) - dur) < 0.05   # slika Shofeova videa (zvuk AAC ima par ms viška)

    # isti rezovi kao render: svaki kadar = rez iz render.build_cuts, preveden u vrijeme originalne datoteke
    edit = load(verzije.found_versions(proj)[v])
    st = render.resolve_style(edit)
    cuts, _, _ = render.build_cuts(load(proj / "transcript.json")["words"], edit, st, 30, pj["duration"])
    assets = {a.get("id"): a for a in root.iter("asset")}
    src_spans = []
    for c in clips:
        a = assets[c.get("ref")]
        k = next(i for i, cl in enumerate(pj["clips"]) if Path(cl["file"]).name == a.get("name"))
        s = pj["clips"][k]["start"] + float(T(c.get("start")) - T(a.get("start")))
        src_spans.append((s, s + float(T(c.get("duration")))))
    merged = []
    for s, e in src_spans:
        if merged and abs(merged[-1][1] - s) < 0.04:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    assert len(merged) == len(cuts)
    for (s, e), c in zip(merged, cuts):
        assert abs(s - c["a"]) < 0.04 and abs(e - c["b"]) < 0.04, (s, e, c)

    # vodoravni klip: popunjava kadar i pomaknut je kao u prepare.py (crop-x 0.3); oznake i glazba
    k1 = [c for c in clips if c.get("name") == "klip1.mp4"]
    assert k1 and all(c.find("adjust-conform").get("type") == "fill" for c in k1)
    assert all(float(c.find("adjust-transform").get("position").split()[0]) > 20 for c in k1)
    marks = [m.get("value") for m in root.iter("marker")]
    assert "Naslov: Klima smrdi? Očisti je sam" in marks and any(m.startswith("Shofe stil:") for m in marks)
    assert any(m.startswith("Zum ") for m in marks)
    zoomed = [c for c in clips if c.find("adjust-transform") is not None and c.find("adjust-transform").get("scale")]
    assert zoomed and all(c.find("adjust-transform").get("scale") == "1.16 1.16" for c in zoomed)
    music = [c for c in clips[0].findall("asset-clip") if c.get("lane") == "-1"]
    assert music and sum(T(m.get("duration")) for m in music) == T(seq.get("duration"))
    assert music[0].find("adjust-volume").get("amount").endswith("dB")


def _audio(path, start, dur, sr=8000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.4f}", "-t", f"{dur:.4f}", "-i", str(path),
                        "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)


def _frame(path, t, vf):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", str(path), "-frames:v", "1",
                        "-vf", vf + ",scale=108:192,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.uint8).astype(np.float32)


def test_timeline_shows_same_picture_and_sound_as_shofe(proj):
    """Iz FCPXML-a složi sliku i zvuk iz ORIGINALNIH snimki (kao DaVinci) i usporedi s pripremljenim
    source.mp4 na mjestima Shofeovih rezova: isti zvuk (isti trenutak) i ista slika (isti izrez kadra, zum)."""
    v = verzije.viewed(proj)
    root = ET.parse(proj / f"reel_v{v}_pregled.fcpxml").getroot()
    pj = load(proj / "project.json")
    W, H = pj["width"], pj["height"]
    assets = {a.get("id"): a for a in root.iter("asset")}
    for c in spine_clips(root):
        a = assets[c.get("ref")]
        orig = next(Path(cl["file"]) for cl in pj["clips"] if Path(cl["file"]).name == a.get("name"))
        k = next(i for i, cl in enumerate(pj["clips"]) if Path(cl["file"]) == orig)
        local = float(T(c.get("start")) - T(a.get("start")))
        d = float(T(c.get("duration")))
        src_t = pj["clips"][k]["start"] + local
        # zvuk: isti trenutak (najbolja korelacija unutar ±50 ms; AAC u source.mp4 kasni ~21 ms)
        x, y = _audio(orig, local, d), _audio(proj / "source.mp4", src_t, d)
        n = min(len(x), len(y))
        x, y = x[:n] - x[:n].mean(), y[:n] - y[:n].mean()
        if np.std(y) > 50:
            cc = np.correlate(x, y, "full")[n - 1 - 400:n + 400]
            best = cc.max() / np.sqrt((x ** 2).sum() * (y ** 2).sum())
            assert best > 0.8 and abs(int(cc.argmax()) - 400) <= 400, (a.get("name"), local, best)
        # slika: popuni kadar, zum oko sredine, pomak (postotak visine) kao u DaVinciju
        tr = c.find("adjust-transform")
        px, py = map(float, (tr.get("position", "0 0") if tr is not None else "0 0").split())
        z = float((tr.get("scale", "1 1") if tr is not None else "1 1").split()[0])
        w, h = pj["clips"][k]["w"], pj["clips"][k]["h"]
        s = max(W / w, H / h) * z
        sw, sh = round(w * s / 2) * 2, round(h * s / 2) * 2
        cx = (sw - W) / 2 - px / 100 * H
        cy = (sh - H) / 2 + py / 100 * H
        mid = local + d / 2
        got = _frame(orig, mid, f"scale={sw}:{sh},crop={W}:{H}:{cx:.1f}:{cy:.1f}")
        ref_vf = render.zoom_chain(z, W, H) if z != 1 else "null"
        want = _frame(proj / "source.mp4", src_t + d / 2, ref_vf)
        assert np.mean(np.abs(got - want)) < 8, (a.get("name"), mid, np.mean(np.abs(got - want)))


def test_speed_missing_original_and_cli(proj, dtd, tmp_path):
    p = tmp_path / "kopija"
    p.mkdir()
    for f in ("project.json", "transcript.json", "edit.json", "source.mp4"):
        shutil.copy(proj / f, p / f)
    edit = load(p / "edit.json")
    edit["brzina"] = 1.25
    save(p / "edit.json", edit)
    r = run("davinci.py", p, "--trenutno", "--ispis")
    x = p / "titlovi_trenutno.fcpxml"
    assert x.exists() and (p / "titlovi_trenutno.srt").exists() and "File > Import > Timeline" in r.stdout
    validate(dtd, x)
    root = ET.parse(x).getroot()
    clips = spine_clips(root)
    assert all(c.find("timeMap") is not None for c in clips)
    tp = clips[0].find("timeMap").findall("timept")
    assert T(tp[1].get("value")) / T(tp[1].get("time")) == pytest.approx(1.25, rel=0.01)
    _, total = __import__("titlovi").finished_words(p, edit, load(p / "project.json"),
                                                   load(p / "transcript.json")["words"])
    seq = root.find("library/event/project/sequence")
    assert abs(float(T(seq.get("duration"))) - total) < 0.1
    # originali premješteni → timeline iz source.mp4, uz napomenu
    pj = load(p / "project.json")
    pj["clips"][0]["file"] = str(tmp_path / "nema" / "klip1.mp4")
    save(p / "project.json", pj)
    edit["brzina"] = 1.0
    save(p / "edit.json", edit)
    r = run("davinci.py", p, "--trenutno", "--izlaz", "za_resolve")
    assert "ne postoji" in r.stdout and "source.mp4" in r.stdout
    root = ET.parse(p / "za_resolve.fcpxml").getroot()
    validate(dtd, p / "za_resolve.fcpxml")
    assert {a.get("name") for a in root.iter("asset") if a.get("hasVideo") == "1"} == {"source.mp4"}
    # --izvor priprema i greška za nepostojeću verziju
    r = run("davinci.py", proj, "--izvor", "priprema", "--izlaz", "priprema")
    assert "source.mp4" in r.stdout
    r = run("davinci.py", proj, "--verzija", 99, ok=False)
    assert r.returncode != 0 and "nema verzije 99" in r.stderr
