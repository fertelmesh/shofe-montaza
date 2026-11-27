"""M4.3b1: glasnoća pjesme naspram govora — mjerenje po dijelu (EBU R128), stalno pojačanje pjesme,
cijeli video na −14 LUFS jednim pojačanjem + limiter (true peak ispod −1 dBTP), bez „pumpanja"."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import nastupi as NA  # noqa: E402
import render  # noqa: E402
import make_nastup as MN  # noqa: E402

SONG = [{"id": "P1", "od": 19.74, "do": 68.75, "izvor": "auto", "sigurnost": 0.85}]


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


# ---------------------------------------------------------------- bez videa

def test_glasnoca_iz_blokova():
    assert render.gated_loudness([]) is None
    assert render.gated_loudness([-80, -120]) is None                    # sve ispod −70 LUFS
    assert abs(render.gated_loudness([-20.0] * 50) - (-20.0)) < 1e-6
    # tihi blokovi (−40, više od 10 LU ispod) ne smiju spustiti glasnoću
    assert abs(render.gated_loudness([-20.0] * 50 + [-40.0] * 50) - (-20.0)) < 1e-6
    # dva glasna dijela: prosjek snage, ne prosjek LUFS-a
    v = render.gated_loudness([-20.0] * 10 + [-14.0] * 10)
    assert abs(v - (10 * np.log10((10 ** -2.0 + 10 ** -1.4) / 2))) < 1e-6


def test_citanje_momentarne_glasnoce():
    txt = ("frame:0    pts:0       pts_time:0\nlavfi.r128.M=-120.691\n"
           "frame:1    pts:1600    pts_time:0.1\nlavfi.r128.M=-23.5\n"
           "frame:2    pts:3200    pts_time:0.2\nlavfi.r128.M=nan\n")
    assert render.parse_momentary(txt) == [(0.1, -120.691), (0.2, -23.5)]


def test_plan_pojacanja():
    # 100 ms blokovi: govor −20 LUFS, pjesma 30–60 s −10 LUFS (10 LU preglasna)
    mom = [(t / 10, -10.0 if 30.2 <= t / 10 - 0.2 <= 60 else -20.0) for t in range(4, 900)]
    pl = render.loudness_plan(mom, [(30.0, 60.0, 0)], [0.0])
    assert pl["govor"] == -20.0 and pl["pjesme"][0]["izmjereno"] == -10.0
    assert abs(pl["pjesme"][0]["pojacanje"] + 10.0) < 0.01
    assert abs(pl["ukupno"] + 20.0) < 0.2 and abs(pl["pojacanje"] - 6.0) < 0.2
    # Marko želi pjesmu 2 LU glasniju od govora
    pl = render.loudness_plan(mom, [(30.0, 60.0, 0)], [2.0])
    assert abs(pl["pjesme"][0]["pojacanje"] + 8.0) < 0.01
    # bez govora (video je samo pjesma): pjesma ostaje kakva jest
    pl = render.loudness_plan([(t / 10, -12.0) for t in range(4, 300)], [(0.0, 40.0, 0)], [0.0])
    assert pl["govor"] is None and pl["pjesme"][0]["pojacanje"] == 0.0
    assert abs(pl["pojacanje"] + 2.0) < 0.1
    # granica pojačanja: jako tiha pjesma ne dobije više od +15 dB
    mom = [(t / 10, -45.0 if 30.2 <= t / 10 - 0.2 <= 60 else -20.0) for t in range(4, 900)]
    assert render.loudness_plan(mom, [(30.0, 60.0, 0)], [0.0])["pjesme"][0]["pojacanje"] == 15.0


def test_razina_po_pjesmi_i_izraz():
    edit = {"nastup_glasnoca": -1, "nastupi": [
        {"id": "P2", "od": 100, "do": 150, "zadrzi": True, "glasnoca": 3},
        {"id": "P1", "od": 10, "do": 50, "zadrzi": True},
        {"id": "PX", "od": 60, "do": 90, "zadrzi": False, "glasnoca": 5},
        {"id": "P3", "od": 200, "do": 260, "zadrzi": True, "glasnoca": 40}]}
    assert render.song_levels(edit, 3) == [-1.0, 3.0, 6.0]   # po vremenu; izbačena ne broji; najviše ±6
    ex = render.song_gain_expr([(2.0, 10.0), (20.0, 30.0)], gains=[0.5, 1.0])
    assert ex.startswith("0.50000*clip(") and "+clip(" in ex
    assert render.song_gain_expr([(2.0, 10.0)]) == render.song_gain_expr([(2.0, 10.0)], gains=[1.0])


def test_dijelovi_pjesme_u_videu():
    edit = {"nastupi": [{"id": "P1", "od": 10, "do": 40, "zadrzi": True},
                        {"id": "P2", "od": 40, "do": 70, "zadrzi": True}]}
    cuts = [{"a": 0, "b": 70, "o": 0}]
    parts = render.song_out_parts(edit, cuts)
    assert [(round(s), round(e), k) for s, e, k in parts] == [(10, 40, 0), (40, 70, 1)]  # dvije pjesme jedna do druge
    cuts = [{"a": 0, "b": 25, "o": 0}, {"a": 25.02, "b": 70, "o": 25}]                  # rez unutar P1 (ručni)
    assert [k for *_, k in render.song_out_parts(edit, cuts)] == [0, 1]
    assert render.song_out_spans(edit, cuts) == [(s, e) for s, e, _ in render.song_out_parts(edit, cuts)]


def test_naredba_glasnoca(tmp_path):
    p = tmp_path / "proj čž"
    p.mkdir()
    save(p / "project.json", {"duration": 131.0})
    save(p / "nastupi.json", {"nastupi": [dict(SONG[0]), {"id": "P2", "od": 90.0, "do": 125.0, "izvor": "auto"}]})
    save(p / "edit.json", {"odsjecci": [], "nastupi": [{"id": "P1", "od": 19.74, "do": 68.75, "zadrzi": True,
                                                         "titlovi": False}]})
    r = run("nastupi.py", p, "glasnoca", "P1", "+2")
    assert "P1: 2 LU glasnije od govora" in r.stdout and "+2 LU od govora" in r.stdout
    assert load(p / "nastupi.json")["nastupi"][0]["glasnoca"] == 2.0
    e = load(p / "edit.json")
    assert e["nastupi"][0]["glasnoca"] == 2.0 and "nastup_glasnoca" not in e
    r = run("nastupi.py", p, "glasnoca", "sve", "-1,5")
    d = load(p / "nastupi.json")
    assert d["glasnoca"] == -1.5 and all("glasnoca" not in n for n in d["nastupi"])
    e = load(p / "edit.json")
    assert e["nastup_glasnoca"] == -1.5 and "glasnoca" not in e["nastupi"][0]
    run("nastupi.py", p, "glasnoca", "isto")
    assert "nastup_glasnoca" not in load(p / "edit.json") and "glasnoca" not in load(p / "nastupi.json")
    r = run("nastupi.py", p, "glasnoca", "P1", "+9", ok=False)
    assert r.returncode != 0 and "±6" in r.stdout + r.stderr
    assert NA.parse_level("tiše") == -2.0 and NA.parse_level("+0,5 LU") == 0.5


# ---------------------------------------------------------------- pravi render

def momentary(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af",
                        "ebur128=metadata=1,ametadata=mode=print:key=lavfi.r128.M:file=-", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    mom = render.parse_momentary(r.stdout)
    return np.array([t - 0.2 for t, _ in mom]), np.array([m for _, m in mom])


def true_peak(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = r.stderr[r.stderr.rfind("True peak:"):]
    return float(txt.split("Peak:")[1].split()[0])


def song_vs_speech(proj, video):
    e = load(proj / "edit.json")
    pj = load(proj / "project.json")
    words = load(proj / "transcript.json")["words"]
    cuts, _, _ = render.build_cuts(words, e, render.resolve_style(e), pj["fps"], pj["duration"])
    (a, b), = render.song_out_spans(e, cuts)
    t, m = momentary(video)
    song = render.gated_loudness(m[(t > a + 0.5) & (t < b - 0.5)])
    speech = render.gated_loudness(m[(t < a - 0.5) | (t > b + 0.5)])
    return song, speech, render.gated_loudness(m), (a, b)


def gain_wobble(p):
    """Koliko se kroz pjesmu mijenja pojačanje video − snimka (std u dB, prozori od 3 s)."""
    _, _, _, (a, b) = song_vs_speech(p, p / "reel_v1.mp4")
    t, m = momentary(p / "reel_v1.mp4")
    t0, m0 = momentary(p / "source.mp4")
    off = SONG[0]["od"] - a                          # pjesma počinje na 19,74 s snimke, u videu na `a`

    def power(tt, mm, x):
        return 10 * np.log10(np.mean(10 ** (mm[(tt >= x) & (tt < x + 3)] / 10)))
    d = [power(t, m, x) - power(t0, m0, x + off) for x in np.arange(a + 2, b - 5, 1.0)]
    return float(np.std(d))


@pytest.fixture(scope="module")
def epizode(tmp_path_factory):
    base = tmp_path_factory.mktemp("glasnoca čž")
    out = {}
    for name, db in (("glasna", 8.0), ("tiha", -10.0)):
        proj = MN.make(base / name, pjesma_db=db)
        save(proj / "nastupi.json", {"nastupi": [dict(SONG[0])]})
        run("plan.py", proj, "--stil", "podcast")
        out[name] = proj
    return out


@pytest.mark.parametrize("name", ["glasna", "tiha"])
def test_pjesma_jednako_glasna_kao_govor(epizode, name, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizode[name], p)
    t0, m0 = momentary(p / "source.mp4")
    src_song = render.gated_loudness(m0[(t0 > 20.5) & (t0 < 67.5)])
    src_speech = render.gated_loudness(m0[(t0 < 19.5) | (t0 > 71.5)])
    assert abs(src_song - src_speech) > 5     # u snimci pjesma jako odskače od govora
    r = run("render.py", p)
    assert "Glasnoća P1" in r.stdout and ("stišana" if name == "glasna" else "pojačana") in r.stdout
    graf = (p / "_tmp" / "graf.txt").read_text(encoding="utf-8")
    assert "loudnorm=I=-14" not in graf and "alimiter" in graf   # bez dinamičkog loudnorma
    song, speech, total, _ = song_vs_speech(p, p / "reel_v1.mp4")
    assert abs(song - speech) < 1.0, (song, speech)
    assert abs(total - (-14.0)) < 1.0, total
    assert true_peak(p / "reel_v1.mp4") <= -1.0
    assert gain_wobble(p) < 0.8   # stalno pojačanje: pjesma ne „pumpa" (stari dinamički loudnorm ovdje 0,9–1,1)


def test_marko_hoce_glasniju_pjesmu(epizode, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizode["glasna"], p)
    run("nastupi.py", p, "glasnoca", "P1", "+3")
    r = run("render.py", p)
    assert "cilj: +3 LU" in r.stdout
    song, speech, total, _ = song_vs_speech(p, p / "reel_v1.mp4")
    assert abs(song - speech - 3.0) < 1.0, (song, speech)
    assert abs(total - (-14.0)) < 1.0, total


def test_bez_pjesme_kao_prije(epizode, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizode["tiha"], p)
    e = load(p / "edit.json")
    e["nastupi"][0]["zadrzi"] = False
    save(p / "edit.json", e)
    r = run("render.py", p)
    assert "Glasnoća" not in r.stdout
    assert "loudnorm=I=-14" in (p / "_tmp" / "graf.txt").read_text(encoding="utf-8")
