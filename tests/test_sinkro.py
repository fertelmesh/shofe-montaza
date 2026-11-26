"""M4.1: sinkronizacija više izvora po zvuku (sinkro.py) — sintetski pomak ±10 s, drift sata, nepovezan zvuk,
cijeli put s kamerama (bljesak na slici = pljesak u zvuku) i ručni ispravak."""
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

import make_sinkro as MS  # noqa: E402
import sinkro as S  # noqa: E402

SR = S.SR


def run(*args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / "sinkro.py"), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"sinkro.py pao:\n{r.stdout}\n{r.stderr}"
    return r


@pytest.fixture(scope="module")
def govor():
    s = MS.decode(MS.FIX / "razgovor.m4a", SR)
    s = np.concatenate([s, s[::-1]])
    return s / np.abs(s).max()


def i16(x, gain=12000):
    return np.clip(x / (np.abs(x).max() + 1e-9) * gain, -32767, 32767).astype(np.int16)


def kamera(s, pomak, ppm=0.0, seed=0):
    """Izvor koji je počeo `pomak` s nakon glavnog (negativno = prije), drugi mikrofon, šum, jeka."""
    rng = np.random.default_rng(seed)
    b = 1 + ppm * 1e-6
    T = len(s) / SR
    dur = (T - max(pomak, 0.0)) * b - 0.3
    tau = np.arange(int(dur * SR)) / SR
    x = np.interp((pomak + tau / b) * SR, np.arange(len(s)), s, left=0.0)
    if pomak < 0:
        x[: int(-pomak * SR)] = MS.zamor(-pomak, seed + 1, SR)[: int(-pomak * SR)]
    x = MS.lowpass(x, 2200, SR)
    k = int(0.031 * SR)
    x[k:] += 0.5 * x[:-k]
    x = x / np.abs(x).max() + 0.02 * rng.standard_normal(len(x))
    return i16(x, 6000)


@pytest.mark.parametrize("pomak", [-10.0, -4.37, 0.0, 3.21, 10.0])
def test_pomak_do_10_sekundi(govor, pomak):
    r = S.align(i16(govor), kamera(govor, pomak, seed=int(abs(pomak) * 10)))
    assert r["pronaden"] and r["sigurnost"] == "visoka", r
    assert abs(r["pomak"] - pomak) < 0.002, r          # 2 ms (desetina sličice)
    assert abs(r["brzina"] - 1) < 30e-6, r


def test_drift_sata(govor):
    r = S.align(i16(govor), kamera(govor, -6.0, ppm=250, seed=4))
    assert r["sigurnost"] == "visoka", r
    assert abs(r["pomak"] + 6.0) < 0.002, r
    assert abs((r["brzina"] - 1) * 1e6 - 250) < 25, r
    # na kraju snimke (100 s) pogreška bez drifta bila bi 25 ms; s izmjerenom brzinom < 2 ms
    e = S.finish_source({"pomak": r["pomak"], "brzina": r["brzina"]}, {"trajanje": 100.0})
    assert abs(S.to_source(e, 100.0) - (100.0 + 6.0) * 1.00025) < 0.002


def test_nepovezan_i_prekratak(govor):
    r = S.align(i16(govor), i16(MS.zamor(60, 7, SR)))
    assert not r["pronaden"] and r["sigurnost"] == "nije pronađen", r
    r = S.align(i16(govor), i16(np.zeros(3 * SR) + 1e-3))
    assert not r["pronaden"]


def test_kratki_isjecak_usred_snimke(govor):
    """Kamera je snimila samo 25 s usred epizode (npr. ugašena pa upaljena)."""
    a = int(61.5 * SR)
    src = i16(MS.lowpass(govor[a: a + 25 * SR], 3000, SR))
    r = S.align(i16(govor), src)
    assert r["sigurnost"] in ("visoka", "srednja"), r
    assert abs(r["pomak"] - 61.5) < 0.002, r


def test_vrijeme_tamo_i_natrag():
    e = S.finish_source({"pomak": -7.25, "brzina": 1.0001}, {"trajanje": 50.0})
    for t in (-7.25, 0.0, 12.3, 40.0):
        assert abs(S.to_master(e, S.to_source(e, t)) - t) < 1e-9
    assert e["od"] == -7.25 and abs(e["do"] - (-7.25 + 50 / 1.0001)) < 1e-3
    assert e["drift_ppm"] == 100.0 and e["drift_ms_na_sat"] == 360.0


@pytest.fixture(scope="module")
def snimka(tmp_path_factory):
    d = tmp_path_factory.mktemp("sinkro_snimka")
    MS.make(d)
    return d


def test_cijeli_put(snimka, tmp_path):
    proj = tmp_path / "podcast"
    r = run(snimka, "--out", proj, "--provjera", "0:49")
    data = json.loads((proj / "sinkro.json").read_text(encoding="utf-8"))
    iz = {e["ime"]: e for e in data["izvori"]}
    assert data["glavni"] == "zvuk.wav" and data["izvori"][0]["ime"] == "zvuk.wav"
    for ime, ist in MS.ISTINA.items():
        e = iz[ime]
        assert e["sigurnost"] == "visoka", e
        assert abs(e["pomak"] - ist["pomak"]) < 0.003, (ime, e["pomak"], ist)
        assert abs(e["brzina"] - ist["brzina"]) < 25e-6, (ime, e["brzina"], ist)
    assert iz["tudje.wav"]["sigurnost"] == "nije pronađen"
    assert "PROVJERI: tudje.wav" in r.stdout and "počinje 7,300 s prije glavnog" in r.stdout
    assert abs(data["od"] + 7.3) < 0.01 and data["zajedno"][0] == pytest.approx(9.4, abs=0.01)
    assert (proj / "sinkro.txt").exists() and (proj / "sinkro.png").stat().st_size > 5000

    # provjera: u mozaiku obje kamere bljesnu u istoj sličici u kojoj se u zvuku čuje pljesak (50 s glavnog)
    out = proj / "sinkro_provjera.mp4"
    a = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                       capture_output=True, check=True).stdout
    klik = np.argmax(np.abs(np.frombuffer(a, np.int16).astype(float))) / 8000
    assert klik == pytest.approx(1.0, abs=0.02)
    v = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-vf", "scale=64:18,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(v, np.uint8).reshape(-1, 18, 64)
    assert len(f) == pytest.approx(300, abs=2)
    for tile in (f[:, :9, :32], f[:, :9, 32:]):
        bright = np.nonzero(tile.reshape(len(f), -1).mean(1) > 200)[0]
        assert len(bright) and abs(bright[0] / 30 - klik) <= 1 / 30 + 0.01, (bright, klik)


def test_rucni_pomak_i_drugi_glavni(snimka, tmp_path):
    proj = tmp_path / "podcast"
    run(snimka / "kamera1.mp4", snimka / "kamera2.mp4", snimka / "tudje.wav", "--out", proj,
        "--glavni", "kamera1", "--bez-provjere")
    data = json.loads((proj / "sinkro.json").read_text(encoding="utf-8"))
    iz = {e["ime"]: e for e in data["izvori"]}
    assert iz["kamera1.mp4"]["glavni"] and iz["kamera1.mp4"]["pomak"] == 0
    # kamera2 na crti kamere 1: 9,4 + 7,3 s
    assert iz["kamera2.mp4"]["pomak"] == pytest.approx(9.4 + 7.3, abs=0.003)
    assert iz["tudje.wav"]["sigurnost"] == "nije pronađen"

    r = run(proj, "--pomak", "tudje.wav=5,5", "--bez-provjere")
    data = json.loads((proj / "sinkro.json").read_text(encoding="utf-8"))
    e = next(x for x in data["izvori"] if x["ime"] == "tudje.wav")
    assert e["rucno"] and e["pomak"] == 5.5 and e["od"] == 5.5 and e["sigurnost"] == "ručno"
    assert "(RUČNO)" in r.stdout
    r = run(proj, "--pomak", "kamera1=3", ok=False)
    assert r.returncode == 1 and "glavni" in r.stderr


def test_greske(tmp_path, snimka):
    r = run(snimka / "zvuk.wav", ok=False)
    assert r.returncode == 1 and "barem dva izvora" in r.stderr
    r = run(snimka / "zvuk.wav", tmp_path / "nema.mp4", ok=False)
    assert r.returncode == 1 and "ne postoji" in r.stderr
