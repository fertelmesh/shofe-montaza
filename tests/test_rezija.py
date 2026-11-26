"""M4.2: režija podcasta (rezija.py) — tko govori → koja kamera, pravila (najkraći kadar, široki kadar kad
pričaju svi, umetci u monologu, kamera koja ne snima) i cijeli put s tri probne kamere."""
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

import rezija as R  # noqa: E402


# ---------------------------------------------------------------- pravila (bez videa)

def setup(cu=("G1", "G2"), wide=True, od=None, dur=200.0):
    """Lažne kamere na crti glavnog (pocetak 0): krupni po govorniku + široki."""
    od = od or {}
    cams, roles = [], []
    for g in cu:
        n = f"kam{g}.mp4"
        cams.append({"ime": n, "od": od.get(n, 0.0), "do": dur})
        roles.append({"ime": n, "uloga": "krupni", "govornik": g, "osobe": [{"x": .5, "w": .3}]})
    if wide:
        cams.append({"ime": "siroka.mp4", "od": od.get("siroka.mp4", 0.0), "do": dur})
        roles.append({"ime": "siroka.mp4", "uloga": "siroki", "govornik": None,
                      "osobe": [{"x": .3, "w": .1}, {"x": .7, "w": .1}]})
    return cams, roles


def at(shots, t):
    return next(s for s in shots if s["od"] <= t < s["do"])


def check_basic(shots, dur):
    assert shots[0]["od"] == 0 and shots[-1]["do"] == pytest.approx(dur)
    for a, b in zip(shots, shots[1:]):
        assert a["do"] == pytest.approx(b["od"]) and a["kamera"] != b["kamera"]


def test_izmjena_govornika_i_najkraci_kadar():
    segs = [(0.5, 6, "G1"), (6.3, 12, "G2"), (12.4, 18, "G1"), (18.2, 18.7, "G2"),   # „aha" od 0,5 s
            (18.9, 25, "G1"), (25.3, 31, "G2")]
    cams, roles = setup(dur=32)
    shots = R.direct(segs, cams, roles, 0.0, 32.0, {}, "nikad")
    check_basic(shots, 32)
    assert at(shots, 3)["kamera"] == "kamG1.mp4" and at(shots, 9)["kamera"] == "kamG2.mp4"
    assert at(shots, 18.5)["kamera"] == "kamG1.mp4"           # kratko dobacivanje ne prebacuje kadar
    assert at(shots, 28)["kamera"] == "kamG2.mp4"
    assert min(s["do"] - s["od"] for s in shots) >= R.MIN_KADAR - 1e-6
    # rez malo prije prve riječi novog govornika
    cut = next(s["od"] for s in shots if s["kamera"] == "kamG2.mp4")
    assert 6.3 - 0.35 <= cut <= 6.3
    assert "govori G2" in at(shots, 9)["zasto"]


def test_preklapanje_i_brza_izmjena_idu_u_siroki():
    segs = [(0, 8, "G1"), (6, 12, "G2"),                          # 2 s u isti glas
            (14, 20, "G1"),
            (20.2, 21.5, "G2"), (21.7, 23.0, "G1"), (23.2, 24.6, "G2"), (24.8, 26.0, "G1"),   # brza izmjena
            (26.2, 34, "G2")]
    cams, roles = setup(dur=35)
    shots = R.direct(segs, cams, roles, 0.0, 35.0, {}, "nikad")
    check_basic(shots, 35)
    assert at(shots, 7)["kamera"] == "siroka.mp4" and "isti glas" in at(shots, 7)["zasto"]
    assert at(shots, 17)["kamera"] == "kamG1.mp4"
    assert at(shots, 23)["kamera"] == "siroka.mp4" and "izmjena" in at(shots, 23)["zasto"]
    assert at(shots, 31)["kamera"] == "kamG2.mp4"


def test_umetci_u_dugom_monologu():
    segs = [(0.3 + 5 * k, 5 * k + 4.9, "G1") for k in range(28)] + [(140.5, 150, "G2")]
    cams, roles = setup(dur=151)
    n = {}
    for u in ("nikad", "rijetko", "povremeno", "cesto"):
        shots = R.direct(segs, cams, roles, 0.0, 151.0, {}, u)
        check_basic(shots, 151)
        cut = [s for s in shots if s["zasto"] == R.RAZLOZI[R.R_UMETAK]]
        assert all(s["kamera"] == "siroka.mp4" for s in cut)
        assert all(abs(s["do"] - s["od"] - R.UMETAK_TRAJANJE) < 0.11 for s in cut)
        n[u] = len(cut)
    assert n["nikad"] == 0 and 1 <= n["rijetko"] < n["povremeno"] < n["cesto"]
    assert n["rijetko"] == 2 and n["povremeno"] in (3, 4)    # 140 s monologa: svakih 45 / 30 s
    # umetak na pauzi između rečenica kad je ima blizu
    shots = R.direct(segs, cams, roles, 0.0, 151.0, {}, "povremeno")
    cut = [s for s in shots if s["zasto"] == R.RAZLOZI[R.R_UMETAK]]
    on_pause = [any(5 * k + 4.85 <= s["od"] <= 5 * k + 5.35 for k in range(28)) for s in cut]
    assert sum(on_pause) >= len(cut) - 1          # zadnji je preblizu kraju monologa da bi tražio pauzu


def test_bez_sirokog_umetak_je_reakcija_drugoga():
    segs = [(0.3, 70, "G1"), (70.3, 80, "G2"), (78, 80, "G1")]
    cams, roles = setup(wide=False, dur=81)
    shots = R.direct(segs, cams, roles, 0.0, 81.0, {}, "povremeno")
    check_basic(shots, 81)
    cut = [s for s in shots if s["zasto"] == R.RAZLOZI[R.R_UMETAK]]
    assert cut and all(s["kamera"] == "kamG2.mp4" for s in cut)
    assert all(s["kamera"] is not None for s in shots)


def test_gost_bez_kamere_tisina_i_kamera_koja_ne_snima():
    segs = [(0.5, 9, "G1"), (9.3, 15, "G3"), (15.3, 22, "G2"), (30, 40, "G1")]   # tišina 22–30
    cams, roles = setup(dur=41, od={"kamG1.mp4": 10.0})                          # kamera G1 krenula na 10 s
    shots = R.direct(segs, cams, roles, 0.0, 41.0, {"G1": "Marko"}, "nikad")
    check_basic(shots, 41)
    assert at(shots, 5)["kamera"] == "siroka.mp4"                                # G1 govori, njegova ne snima
    assert "ne snima" in at(shots, 5)["zasto"] and "Marko" in at(shots, 5)["zasto"]
    assert at(shots, 12)["kamera"] == "siroka.mp4"                               # G3 nema kameru
    assert at(shots, 18)["kamera"] == "kamG2.mp4"
    assert at(shots, 26)["kamera"] == "siroka.mp4" and at(shots, 26)["zasto"] == "tišina"
    assert at(shots, 35)["kamera"] == "kamG1.mp4"


def test_bez_govornika_sve_siroko_i_crno_bez_kamera():
    cams, roles = setup(dur=20)
    shots = R.direct([], cams, roles, 0.0, 20.0, {}, "povremeno")
    assert [s["kamera"] for s in shots] == ["siroka.mp4"]
    cams = [{"ime": "a.mp4", "od": 5.0, "do": 20.0}]
    roles = [{"ime": "a.mp4", "uloga": "krupni", "govornik": "G1", "osobe": []}]
    shots = R.direct([(1, 19, "G1")], cams, roles, 0.0, 20.0, {}, "nikad")
    assert shots[0]["kamera"] is None and shots[0]["uloga"] == "crno"
    assert at(shots, 10)["kamera"] == "a.mp4"


def test_rucne_kamere():
    cams = [{"ime": "kamera1.mp4"}, {"ime": "Kamera2.MP4"}, {"ime": "auto.mp4"}]
    names = {"G1": "Marko", "G2": "Ivan"}
    m = R.parse_manual("kamera1=marko, kamera2.mp4=G2 ,auto=siroki", cams, names)
    assert m == {"kamera1.mp4": ("krupni", "G1"), "Kamera2.MP4": ("krupni", "G2"), "auto.mp4": ("siroki", None)}
    assert R.parse_manual("auto.mp4=ostalo", cams, names) == {"auto.mp4": ("bez_lica", None)}
    with pytest.raises(SystemExit):
        R.parse_manual("kamera9=G1", cams, names)
    with pytest.raises(SystemExit):
        R.parse_manual("kamera1=Pero", cams, names)


def test_prozori_za_lica():
    segs = [(t, t + 4, "G1" if (t // 5) % 2 else "G2") for t in range(0, 300, 5)]
    w = R.pick_windows(10.0, 290.0, segs)
    assert len(w) == R.PROZORA and all(10 <= x <= 290 - R.PROZOR for x in w)
    assert w == sorted(w) and w[-1] - w[0] > 200                    # raspoređeni po cijeloj snimci
    assert R.pick_windows(3.0, 12.0, segs) == [3.0]


# ---------------------------------------------------------------- cijeli put s tri kamere

def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r.stdout


def pixel(video, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "crop=40:40:10:10,scale=1:1:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout[:3], np.uint8).astype(int)


@pytest.fixture(scope="module")
def podcast(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_rezija as MR
    base = tmp_path_factory.mktemp("rezija")
    MR.make(base / "snimke")
    proj = base / "podcast"
    run("sinkro.py", base / "snimke", "--out", proj, "--bez-provjere")
    first = run("rezija.py", proj)
    return MR, proj, first


def cam_at(proj, t):
    rez = json.loads((proj / "rezija.json").read_text(encoding="utf-8"))
    return at(rez["kadrovi"], t)["kamera"]


def test_prvo_pokretanje_bez_govornika(podcast):
    MR, proj, first = podcast
    assert "transcribe.py" in first and "govornici.py" in first
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    assert pj["format"] == "16:9" and pj["clips"] == [] and pj["podcast"]["pocetak"] == 0.0
    assert pj["duration"] == pytest.approx(55.6, abs=0.05)
    rez = json.loads((proj / "rezija.json").read_text(encoding="utf-8"))
    assert [s["kamera"] for s in rez["kadrovi"]] == ["siroka.mp4"]


def test_kamere_prate_govornika(podcast):
    MR, proj, _ = podcast
    MR.govornici_json(proj)
    out = run("rezija.py", proj)
    rez = json.loads((proj / "rezija.json").read_text(encoding="utf-8"))
    roles = {r["ime"]: (r["uloga"], r["govornik"]) for r in rez["kamere"]}
    assert roles == {"kamA.mp4": ("krupni", "G1"), "kamB.mp4": ("krupni", "G2"), "siroka.mp4": ("siroki", None)}
    assert "Marko (G1)" in out and "G3 nema svoju kameru" in out
    # svaka rečenica (sredina) na pravoj kameri
    for a, b, g in MR.truth():
        t = (a + b) / 2
        want = {"A": "kamA.mp4", "B": "kamB.mp4" if t < 44.9 else "siroka.mp4", "C": "siroka.mp4"}[g]
        if g == "C" and b - a < 2:
            continue                                            # kratka upadica ne mijenja kadar
        assert cam_at(proj, t) == want, (a, b, g, cam_at(proj, t))
    assert cam_at(proj, 1.0) == "siroka.mp4"                    # kamA krenula tek na 2 s
    for s in rez["kadrovi"]:
        e = next(r for r in rez["kamere"] if r["ime"] == s["kamera"])
        assert e["od"] - 1e-6 <= s["od"] and s["do"] <= e["do"] + 1e-6   # kamera stvarno snima
    assert min(s["do"] - s["od"] for s in rez["kadrovi"]) >= R.MIN_KADAR - 1e-6
    assert (proj / "rezija.png").stat().st_size > 10000 and (proj / "rezija.txt").exists()
    # program: trajanje, zvuk glavnog i boja pozadine kamere u sredini rečenica
    src = proj / "source.mp4"
    d = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(src)],
                                  capture_output=True, text=True, check=True).stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next(s for s in d["streams"] if s["codec_type"] == "audio")
    assert (int(v["width"]), int(v["height"])) == (1920, 1080)
    assert float(v["duration"]) == pytest.approx(55.6, abs=0.05)
    assert float(a["duration"]) == pytest.approx(55.6, abs=0.06)
    for t, cam in ((7.4, "kamB.mp4"), (11.6, "kamA.mp4"), (21.0, "siroka.mp4"), (48.4, "kamA.mp4"),
                   (52.6, "siroka.mp4")):
        want = np.array(MR.BOJE[cam][::-1])
        got = pixel(src, t)
        others = [np.abs(np.array(c[::-1]) - got).sum() for k, c in MR.BOJE.items() if k != cam]
        assert np.abs(want - got).sum() < min(others), (t, cam, got)


def test_rucno_i_samo_analiza(podcast):
    MR, proj, _ = podcast
    before = (proj / "source.mp4").stat().st_mtime
    out = run("rezija.py", proj, "--kamere", "kamB.mp4=Marko", "--analiza", "--umetci", "nikad")
    assert "RUČNO" in out and (proj / "source.mp4").stat().st_mtime == before
    rez = json.loads((proj / "rezija.json").read_text(encoding="utf-8"))
    assert rez["rucno"] == {"kamB.mp4": ["krupni", "G1"]} and rez["umetci"] == "nikad"
    assert cam_at(proj, 7.4) == "siroka.mp4"                    # Ivan više nema svoju kameru
    # ručna oznaka ostaje i kad se pokrene ponovno bez --kamere
    run("rezija.py", proj, "--analiza")
    rez = json.loads((proj / "rezija.json").read_text(encoding="utf-8"))
    assert next(r for r in rez["kamere"] if r["ime"] == "kamB.mp4")["govornik"] == "G1"
