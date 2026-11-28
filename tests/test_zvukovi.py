"""Zvučni efekti (M5.2b): vlastita biblioteka (sintetizirani zvukovi), parovi efekt → zvuk, pravila glasnoće
(zvuk nikad glasniji od glasa) i miks u renderu."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import efekti  # noqa: E402
import zvukovi  # noqa: E402

SR = 48000


def run(script, *args, ok=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


# ---------------------------------------------------------------- biblioteka
def test_biblioteka_svaki_zvuk_postoji_i_isti_je_svaki_put():
    for k, Z in zvukovi.ZVUKOVI.items():
        x = zvukovi.sintetiziraj(k, 1.0)
        assert np.isfinite(x).all() and abs(np.abs(x).max() - 0.5) < 1e-6, k
        d = max(0.08, Z["trajanje"] or 1.0)
        assert abs(len(x) / SR - d) < 0.01, k
        assert np.array_equal(x, zvukovi.sintetiziraj(k, 1.0)), f"{k} nije isti svaki put"
        assert np.abs(x[:20]).max() < 0.2, f"{k} počinje pucketanjem"
        assert np.abs(x[-20:]).max() < 0.05, f"{k} završava pucketanjem"
    # fijuk: vrh glasnoće je oko 62 % trajanja (tamo ide rez)
    x = zvukovi.sintetiziraj("fijuk")
    env = np.convolve(np.abs(x), np.ones(960) / 960, "same")
    assert 0.45 < env.argmax() / len(x) < 0.7
    # udarac: većina energije u basu, ali ima i srednjih frekvencija (čuje se na mobitelu)
    x = zvukovi.sintetiziraj("udarac")
    sp = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    assert sp[f < 150].sum() > sp[f >= 150].sum()
    assert sp[f >= 150].sum() > 0.1 * sp.sum() and sp[(f > 500) & (f < 4000)].sum() > 0.01 * sp.sum()


def test_imena_aliasi_i_datoteke(tmp_path):
    assert zvukovi.ime("Whoosh") == "fijuk" and zvukovi.ime("bum") == "udarac" and zvukovi.ime("ne") == "ne"
    assert zvukovi.ime("nesto") is None
    (tmp_path / "moj zvuk.wav").write_bytes(b"x")
    assert zvukovi.provjeri("moj zvuk.wav", tmp_path) == "moj zvuk.wav"
    with pytest.raises(ValueError):
        zvukovi.provjeri("nema.wav", tmp_path)
    with pytest.raises(ValueError):
        zvukovi.provjeri("truba", tmp_path)


# ---------------------------------------------------------------- parovi i plan
def fx(tip, s, e, **p):
    x = {"id": p.pop("id", "E1"), "tip": tip, "s": s, "e": e, "p": p}
    if efekti.TIPOVI[tip]["skupina"] == "prijelaz":
        x["t"] = (s + e) / 2
    return x


def test_parovi_sidra_i_iskljucivanje():
    lst = [fx("zamah", 1.8, 2.2, id="E1"), fx("trzaj", 3.0, 4.0, id="E2"), fx("pretapanje", 5.0, 5.4, id="E3"),
           fx("vertigo", 6.0, 9.0, id="E4"), fx("zamrzni", 10.0, 11.0, id="E5", zvuk="ne"),
           fx("guranje", 12.0, 14.0, id="E6", zvuk="zvonce"), fx("film", 15.0, 18.0, id="E7")]
    zv, notes = zvukovi.plan(lst, {}, {})
    by = {z["id"]: z for z in zv}
    assert set(by) == {"E1", "E2", "E4", "E6", "E7"}           # pretapanje bez zvuka, E5 "ne"
    assert by["E1"]["zvuk"] == "fijuk" and by["E1"]["vrh_t"] == 2.0    # vrh fijuka točno na rezu
    assert by["E2"]["zvuk"] == "udarac" and by["E2"]["vrh_t"] == 3.0   # udarac na početku trzaja
    assert by["E4"]["zvuk"] == "uspon" and by["E4"]["raspon"] and abs(by["E4"]["trajanje"] - 3.0) < 1e-9
    assert abs(by["E4"]["vrh_t"] - 9.0) < 1e-9                          # uspon raste do kraja vertiga
    assert by["E6"]["zvuk"] == "zvonce"                                 # Markov izbor umjesto zadanog (nema)
    assert by["E7"]["zvuk"] == "projektor" and by["E7"]["trajanje"] == 3.0
    assert zvukovi.plan(lst, {"zvucni_efekti": False}, {})[0] == []
    assert zvukovi.plan(lst, {}, {"zvucni_efekti": False})[0] == []
    assert len(zvukovi.plan(lst, {"zvucni_efekti": True}, {"zvucni_efekti": False})[0]) == 5


def test_pjesma_i_preblizu():
    lst = [fx("zamah", 1.8, 2.2, id="E1"), fx("trzaj", 2.1, 3.0, id="E2"), fx("trzaj", 5.0, 6.0, id="E3")]
    zv, notes = zvukovi.plan(lst, {}, {}, songs=[(4.5, 8.0)])
    assert [z["id"] for z in zv] == ["E1"]
    assert any("E2" in n and "preblizu" in n for n in notes)
    assert any("E3" in n and "pjesme" in n for n in notes)


def test_razine_nikad_glasnije_od_glasa():
    # govor: 0–4 s na −20 LUFS, 4–8 s tiši (−30), 8–9 s tišina
    mom = [(round(0.1 * i + 0.4, 2), -20.0 if i < 40 else (-30.0 if i < 80 else -90.0)) for i in range(90)]
    zv = [{"id": "E1", "zvuk": "fijuk", "vrh_t": 2.0, "trajanje": 0.6, "vrh": 0.62, "raspon": False, "glasnoca": -12.0},
          {"id": "E2", "zvuk": "udarac", "vrh_t": 6.0, "trajanje": 0.9, "vrh": 0.0, "raspon": False, "glasnoca": -10.0},
          {"id": "E3", "zvuk": "klik", "vrh_t": 8.9, "trajanje": 0.06, "vrh": 0.0, "raspon": False, "glasnoca": -25.0}]
    voice = zvukovi.razine(zv, mom, {})
    assert voice is not None and -23 < voice < -20
    e1, e2, e3 = zv
    assert e1["ref"] == round(voice, 1) and abs(e1["cilj"] - (voice - 9)) < 0.11
    assert e2["lokalno"] == -30.0 and e2["ref"] == -30.0 and abs(e2["cilj"] + 38) < 0.11   # prema tišem govoru
    assert e3["lokalno"] is None and e3["ref"] == round(voice, 1)                         # u tišini: cijeli govor
    for z in zv:
        assert abs(z["glasnoca"] + z["pojacanje"] - z["cilj"]) < 0.02
        assert z["cilj"] <= z["ref"] - zvukovi.MIN_ISPOD + 1e-9
    # „glasnije" (+20 dB) ne prelazi granicu ispod glasa
    zvukovi.razine(zv, mom, {"zvucni_efekti_glasnoca": 20})          # najviše +10 dB
    for z in (e1, e2):
        assert abs(z["cilj"] - (z["ref"] - zvukovi.MIN_ISPOD)) < 0.11
    assert abs(e3["cilj"] - (e3["ref"] - 6)) < 0.11                   # klik −16 + 10
    zvukovi.razine(zv, mom, {"zvucni_efekti_glasnoca": -6})
    assert abs(e1["cilj"] - (e1["ref"] - 15)) < 0.11


def test_graf_mjesta_zvukova():
    zv = [{"id": "E1", "zvuk": "fijuk", "vrh_t": 2.0, "trajanje": 0.6, "vrh": 0.62, "pojacanje": -3.0,
           "datoteka": "a.wav"},
          {"id": "E2", "zvuk": "fijuk", "vrh_t": 0.1, "trajanje": 0.6, "vrh": 0.62, "pojacanje": 1.5,
           "datoteka": "a.wav"}]
    g = zvukovi.graf(zv, 3, "[voice]", "[zmix]")
    assert "[3:a]" in g[0] and "adelay=1628|1628" in g[0] and "volume=-3.00dB" in g[0]
    assert "atrim=start=0.2720" in g[1] and "adelay=0|0" in g[1]
    assert g[-1].startswith("[voice][zv0][zv1]amix=inputs=3") and g[-1].endswith("[zmix]")
    assert zvukovi.ulazi(zv) == ["-i", "a.wav", "-i", "a.wav"]


# ---------------------------------------------------------------- pravi render
def govor(dur, gap=None):
    """Glas: ton 140 Hz s harmonicima, slogovi 4 Hz; prvi dio glasniji, drugi tiši (lokalno pravilo)."""
    t = np.arange(int(dur * SR)) / SR
    x = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 9))
    x *= np.sin(np.pi * 4 * t) ** 2
    x *= np.where(t < dur / 2, 0.30, 0.10)
    if gap:
        x[(t >= gap[0]) & (t < gap[1])] = 0
    return x


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def read_audio(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, np.float32).astype(float)


def max_momentary(x, tmp):
    f = tmp / "m.wav"
    write_wav(f, x)
    return max(v for _, v in zvukovi.momentarne(f))


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_prijelazi_klip as MK
    base = tmp_path_factory.mktemp("zvukovi čž")
    proj = MK.make_projekt(base, SCRIPTS, ime="projekt zvukovi")
    # pravi „glas" umjesto sinusa
    voice = base / "glas.wav"
    write_wav(voice, govor(MK.DUR))
    src = proj / "source.mp4"
    tmp = proj / "src2.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-i", str(voice), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(tmp)], check=True)
    tmp.replace(src)
    return proj


def test_render_zvukovi_ispod_glasa(projekt):
    proj = projekt
    r = run("efekti.py", proj, "rezovi")
    assert "R1" in r.stdout and "R2" in r.stdout
    run("efekti.py", proj, "dodaj", "zamah", "R1")
    run("efekti.py", proj, "dodaj", "trzaj", "0:01-0:02", "--zvuk", "udarac")
    run("efekti.py", proj, "dodaj", "zvuk", "0:06", "--zvuk", "okidac")
    run("efekti.py", proj, "dodaj", "pretapanje", "R2")
    p = run("efekti.py", proj, "popis").stdout
    assert "zvuk: fijuk" in p and "zvuk: udarac" in p and "zvuk: okidac" in p
    ed = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    bez = dict(ed, zvucni_efekti=False)
    (proj / "edit_bez.json").write_text(json.dumps(bez, ensure_ascii=False), encoding="utf-8")

    sys.path.insert(0, str(SCRIPTS))
    import render
    res = render.render(proj, ed, izlaz="sa.mp4", ispis=False, prevedi=False)
    ref = render.render(proj, bez, izlaz="bez.mp4", ispis=False, prevedi=False)
    assert ref["zvukovi"] == []
    zv = {z["id"]: z for z in res["zvukovi"]}
    assert {z["zvuk"] for z in zv.values()} == {"fijuk", "udarac", "okidac"}
    assert any("Zvučni efekti: 3" in line for line in res["ispis"])
    for z in zv.values():
        assert z["cilj"] <= z["ref"] - zvukovi.MIN_ISPOD + 1e-6
    # trajanje se ne mijenja
    a, b = read_audio(proj / "sa.mp4"), read_audio(proj / "bez.mp4")
    n = min(len(a), len(b))
    assert abs(len(a) - len(b)) < 0.03 * SR
    diff = a[:n] - b[:n]
    tmp = proj / "_tmp"
    voice_I = render.gated_loudness([v for _, v in zvukovi.momentarne(proj / "bez.mp4")])
    # svaki zvuk je na svom mjestu, čuje se, i tiši je od glasa (najglasniji blok razlike ≤ glas − 3 dB, +1 tol.)
    win = {}
    for z in zv.values():
        start = z["vrh_t"] - z["vrh"] * z["trajanje"]
        win[z["id"]] = int(max(0, start - 0.05) * SR), int((start + z["trajanje"] + 0.1) * SR)
    quiet = np.ones(n, bool)
    for lo, hi in win.values():
        quiet[lo:hi] = False
    rest = diff[quiet]
    for z in zv.values():
        lo, hi = win[z["id"]]
        part = diff[lo:hi]
        mm = max_momentary(part, tmp)
        assert voice_I - 30 < mm <= voice_I - zvukovi.MIN_ISPOD + 1.0, (z, mm, voice_I)
        assert np.sqrt((part ** 2).mean()) > 3 * np.sqrt((rest ** 2).mean()), z["id"]
    # fijuk: najglasniji dio na rezu R1
    z = zv["E1"]
    env = np.convolve(np.abs(diff), np.ones(480) / 480, "same")
    lo, hi = int((z["vrh_t"] - 0.4) * SR), int((z["vrh_t"] + 0.3) * SR)
    assert abs((lo + env[lo:hi].argmax()) / SR - z["vrh_t"]) < 0.12
    # izmjene: zvuk E1 → ne, auto
    run("efekti.py", proj, "zvuk", "E1", "ne")
    assert "zvuk: fijuk" not in run("efekti.py", proj, "popis").stdout
    run("efekti.py", proj, "zvuk", "E1", "auto")
    assert "zvuk: fijuk" in run("efekti.py", proj, "popis").stdout
    r = run("efekti.py", proj, "zvuk", "E1", "truba", ok=False)
    assert r.returncode != 0 and "nepoznat zvuk" in r.stderr + r.stdout
    r = run("efekti.py", proj, "zvuk", "E9", "fijuk", ok=False)
    assert r.returncode != 0


def test_vlastita_datoteka_i_glasnoca(projekt, tmp_path):
    proj = projekt
    x = zvukovi.sintetiziraj("zvonce") * 1.6                  # „Markov" zvuk, preglasan
    zvukovi.write_wav(proj / "moj ding.wav", x)
    ed = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    ed["efekti"] = [e for e in ed["efekti"] if e["tip"] == "zvuk"]
    ed["efekti"][0]["parametri"]["zvuk"] = "moj ding.wav"
    ed["zvucni_efekti_glasnoca"] = 30                          # „puno glasnije": granica ispod glasa ostaje
    import render
    res = render.render(proj, ed, izlaz="moj.mp4", ispis=False, prevedi=False)
    (z,) = res["zvukovi"]
    assert z["zvuk"] == "moj ding.wav" and abs(z["cilj"] - (z["ref"] - zvukovi.MIN_ISPOD)) < 0.11
    ed["efekti"][0]["parametri"]["zvuk"] = "nema.wav"
    r = subprocess.run([sys.executable, "-c", "import sys,json; sys.path.insert(0, sys.argv[1]); import render; "
                        "render.render(sys.argv[2], json.loads(sys.argv[3]), izlaz='x.mp4', ispis=False)",
                        str(SCRIPTS), str(proj), json.dumps(ed)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode != 0 and "ne postoji" in r.stderr + r.stdout


def test_naredba_zvukovi(tmp_path):
    r = run("efekti.py", tmp_path, "zvukovi")
    assert "fijuk" in r.stdout and "uz: zamah" in r.stdout
    f = tmp_path / "zvukovi_pregled.wav"
    with wave.open(str(f)) as w:
        assert w.getframerate() == SR and w.getnframes() / SR > 8
