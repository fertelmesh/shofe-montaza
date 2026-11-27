"""M4.4c: uvodna i odjavna špica epizode (Markova datoteka ili generirana kartica), uvodna iza najave;
titlovi, poglavlja, MP3 i naredbe po vremenu pomaknu se za špicu; isječci je nemaju."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import epizoda as EP  # noqa: E402
import render  # noqa: E402
import spica as SP  # noqa: E402
import make_nastup as MN  # noqa: E402

SONG = {"id": "P1", "od": 19.74, "do": 68.75, "izvor": "auto", "sigurnost": 0.85, "naziv": "Bend Kutina – Ljeto"}
TEME = [{"od": 0, "do": 25, "naslov": "Dobrodošli u auto", "sazetak": "."},
        {"od": 25, "do": 95, "naslov": "Priča o bendu", "sazetak": "."},
        {"od": 95, "do": 131, "naslov": "Što dalje", "sazetak": "."}]


def run(script, *args, ok=True, env=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def W(t, s, e):
    return {"t": t, "s": s, "e": e}


# ---------------------------------------------------------------- bez videa
def test_tocka_nikad_usred_rijeci_radije_kraj_recenice():
    ws = [W("Bok", 0.0, 0.5), W("svima.", 0.6, 1.2), W("Danas", 2.0, 2.4), W("pričamo", 2.5, 3.0),
          W("o", 3.1, 3.2), W("glazbi", 3.3, 4.0), W("i", 4.2, 4.3), W("autu.", 4.4, 5.0), W("Kreni", 6.0, 6.5)]
    cuts = [{"a": 0, "b": 1.5, "o": 0}, {"a": 2.0, "b": 10, "o": 1.5}]   # rez u stanci iza „svima."
    # traženo 3,9 (usred riječi „glazbi"): najbliži kraj rečenice unutar 3 s → iza „autu." (5,5)
    assert SP.tocka(3.9, ws, cuts, 1.0) == pytest.approx(5.5)
    # traženo 1,6: „svima." završava u 1,2, rez glavnog videa je u 1,5 → špica točno na rezu
    assert SP.tocka(1.6, ws, cuts, 1.0) == pytest.approx(1.5)
    # bez kraja rečenice u blizini: najbliža stanka, nikad usred riječi
    ws2 = [W(f"r{i}", i * 1.0, i * 1.0 + 0.8) for i in range(30)]
    t = SP.tocka(12.3, ws2, [{"a": 0, "b": 31, "o": 0}], 1.0)
    assert t == pytest.approx(11.9) and not any(w["s"] < t < w["e"] for w in ws2)


def _edit(poslije=0.0, uvod=4.0, odjava=15.0):
    sp = {"poslije": poslije}
    if uvod:
        sp["uvod"] = {"generirana": True, "trajanje": uvod}
    if odjava:
        sp["odjava"] = {"generirana": True, "trajanje": odjava}
    return {"spica": sp}


def test_raspored_i_pretvorba_vremena():
    cuts = [{"a": 0, "b": 100, "o": 0}]
    ws = [W("Prva.", 9.0, 9.8), W("Druga", 10.4, 11.0)]
    r = SP.raspored(_edit(10.0, 4.0, 15.0), cuts, 1.0, 30, 100.0, ws)
    assert r["at"] == pytest.approx(10.1) and r["ukupno"] == pytest.approx(119.0)
    assert SP.u_konacno(5.0, r) == 5.0 and SP.u_konacno(50.0, r) == pytest.approx(54.0)
    assert SP.iz_konacnog(5.0, r) == (5.0, None)
    assert SP.iz_konacnog(12.0, r) == (None, "uvod")
    assert SP.iz_konacnog(54.0, r)[0] == pytest.approx(50.0)
    assert SP.iz_konacnog(110.0, r) == (None, "odjava")
    # trajanje u cijelim okvirima; bez špice ništa se ne mijenja
    r2 = SP.raspored(_edit(0, 3.3333, None), cuts, 1.0, 25, 100.0)
    assert r2["uvod"] == pytest.approx(83 / 25) and r2["at"] == 0 and r2["odjava"] == 0
    assert SP.raspored({}, cuts, 1.0, 30, 100.0) is None and SP.u_konacno(7.0, None) == 7.0
    # „poslije" iza kraja glavnog videa → na početak
    assert SP.raspored(_edit(200.0), cuts, 1.0, 30, 100.0)["at"] == 0


def test_titlovi_ne_ulaze_u_spicu():
    r = {"at": 10.0, "uvod": 5.0, "odjava": 15.0, "glavni": 60.0, "ukupno": 80.0}
    cues = [{"od": 8.0, "do": 11.0, "retci": ["a"]}, {"od": 10.2, "do": 12.0, "retci": ["b"]},
            {"od": 9.98, "do": 10.01, "retci": ["c"]}]
    out = SP.pomakni_cues(cues, r)
    assert [(c["od"], c["do"], c["retci"][0]) for c in out] == [(8.0, 10.0, "a"), (15.2, 17.0, "b")]


def test_poglavlja_sa_spicom():
    cuts = [{"a": 0, "b": 300, "o": 0}]
    teme = [{"od": 0, "do": 120, "naslov": "Najava i uvod"}, {"od": 120, "do": 300, "naslov": "Glavna priča"}]
    # kratka generirana uvodna (5 s) iza najave od 30 s: ide u temu, a „nastavak" se ne ponavlja
    r = {"at": 30.0, "uvod": 5.0, "odjava": 15.0, "glavni": 300.0, "ukupno": 320.0}
    ch = EP.slozi(teme, [], cuts, r["ukupno"], spica_r=r)
    assert [(round(c["od"], 2), c["naslov"]) for c in ch] == [
        (0, "Najava i uvod"), (125, "Glavna priča"), (305, "Odjava")]
    # Markova uvodna od 20 s: svoje poglavlje, tema se nastavlja iza nje
    r = {"at": 30.0, "uvod": 20.0, "odjava": 0.0, "glavni": 300.0, "ukupno": 320.0}
    ch = EP.slozi(teme, [], cuts, r["ukupno"], spica_r=r)
    assert [(round(c["od"], 2), c["naslov"]) for c in ch] == [
        (0, "Najava i uvod"), (30, "Uvod"), (50, "Najava i uvod (nastavak)"), (140, "Glavna priča")]
    starts = [c["od"] for c in ch] + [r["ukupno"]]
    assert all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    # uvodna na početku: poglavlja iza nje pomaknuta
    r = {"at": 0.0, "uvod": 12.0, "odjava": 0.0, "glavni": 300.0, "ukupno": 312.0}
    ch = EP.slozi(teme, [], cuts, r["ukupno"], spica_r=r)
    assert [(round(c["od"], 2), c["naslov"]) for c in ch] == [(0, "Uvod"), (12, "Najava i uvod"), (132, "Glavna priča")]


def test_kartica_ass(tmp_path):
    p = tmp_path / "k.ass"
    SP.kartica_ass(p, "uvod", {"ime": "Sunčani4M", "naslov": "Bend {x}", "broj": 12}, 1920, 1080, 5.0)
    t = p.read_text(encoding="utf-8")
    assert "SUNČANI4M" in t and "Bend (x)" in t and "Epizoda 12" in t and "Style: Ime,Anton" in t
    SP.kartica_ass(p, "odjava", {}, 1920, 1080, 15.0)
    t = p.read_text(encoding="utf-8")
    assert "Hvala što ste gledali!" in t and "Pretplati se" in t
    # odjava: sav tekst u gornjoj polovici, ostatak slobodan za završni zaslon YouTubea
    import re
    ys = [int(m.group(1)) for m in re.finditer(r"\\move\(\d+,\d+,\d+,(\d+),", t)]
    assert ys and max(ys) < 1080 * 0.5


# ---------------------------------------------------------------- probna epizoda
def intro_klip(path, dur=3.0, db=-6.0):
    """Markov „intro": 4:3, crveno, glasni ton (treba ga utišati na −14 LUFS)."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s=240x180:r=25:d={dur}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={dur}:sample_rate=44100", "-af", f"volume={db}dB",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def ep(tmp_path_factory):
    base = tmp_path_factory.mktemp("špica čž")
    proj = MN.make(base / "ep")
    save(proj / "nastupi.json", {"nastupi": [dict(SONG)]})
    save(proj / "analiza.json", {"teme": TEME})
    run("plan.py", proj, "--stil", "podcast")
    intro_klip(base / "moj intro.mp4")
    return proj


def env_with(tmp_path):
    e = dict(os.environ)
    e["SHOFE_PODACI"] = str(tmp_path / "podaci")
    return e


def decode(path, sr=8000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.int16).astype(float) / 32768


def frame_rgb(video, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(180, 320, 3).astype(float)


def test_render_sa_spicom(ep, tmp_path):
    import shutil
    p = tmp_path / "p"
    shutil.copytree(ep, p)
    env = env_with(tmp_path)
    intro = ep.parent / "moj intro.mp4"
    # zapamćeni Markov intro vrijedi za sve epizode
    run("spica.py", "postavi", "--uvod", intro, env=env)
    r = run("spica.py", p, "dodaj", "--poslije", "0:10", "--odjava", "generirana", "--trajanje-odjave", "8",
            "--naslov", "Bend iz Kutine", "--broj", "12", env=env)
    assert "moj intro.mp4" in r.stdout and "iza najave" in r.stdout
    sp = load(p / "edit.json")["spica"]
    assert sp["uvod"]["datoteka"].endswith("moj intro.mp4") and sp["uvod"]["trajanje"] == pytest.approx(3.0, abs=0.05)
    assert sp["odjava"] == {"generirana": True, "trajanje": 8.0} and sp["broj"] == "12"

    # bez špice (za usporedbu vremena)
    base_edit = load(p / "edit.json")
    base_edit.pop("spica")
    pj, words = load(p / "project.json"), load(p / "transcript.json")["words"]
    cuts, kept, total = render.build_cuts(words, base_edit, render.resolve_style(base_edit), pj["fps"], pj["duration"])

    r = run("render.py", p, env=env)
    assert "Špica: uvodna 3.0 s (moj intro.mp4)" in r.stdout and "odjavna 8.0 s (generirana)" in r.stdout
    assert "DaVinci timeline je još bez špice" in r.stdout
    edit = load(p / "edit.json")
    ws = render.out_words(words, kept, cuts, set())
    rr = SP.raspored(edit, cuts, 1.0, pj["fps"], total, ws)
    at = rr["at"]
    assert abs(at - 10.0) <= 3.0 and not any(w["s"] < at < w["e"] for w in ws)   # u stanci, ne usred riječi
    vid = p / "reel_v1.mp4"
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                                      str(vid)], capture_output=True, text=True).stdout)
    assert float(info["format"]["duration"]) == pytest.approx(total + 3.0 + 8.0, abs=0.08)

    # slika: Markov intro (crveno, s crnim rubovima jer je 4:3), pa nastavak epizode, na kraju kartica
    f = frame_rgb(vid, at + 1.5)
    mid = f[:, 60:260]
    assert mid[..., 0].mean() > 180 and mid[..., 1].mean() < 60 and f[:, :15].mean() < 20
    assert frame_rgb(vid, at + 3.4)[..., 0].mean() < 150       # opet epizoda
    # zvuk: intro na −14 LUFS (bio je glasniji), bez rupe na spoju
    x = decode(vid)
    sr = 8000
    seg = x[int((at + 0.3) * sr):int((at + 2.7) * sr)]
    rms_db = 20 * np.log10(np.sqrt((seg ** 2).mean()))
    assert -19 < rms_db < -11
    full = x[int((at - 0.0) * sr):int((at + 3.0) * sr)]
    assert np.abs(full).max() > 0.05
    # titlovi: ništa u špici, sve iza nje pomaknuto za 3 s
    srt = (p / "reel_v1.srt").read_text(encoding="utf-8-sig")
    times = []
    for block in srt.strip().split("\n\n"):
        ln = block.splitlines()[1]
        a, b = [sum(float(x) * m for x, m in zip(t.replace(",", ".").split(":"), (3600, 60, 1)))
                for t in ln.split(" --> ")]
        times.append((a, b))
    assert not any(a < at + 3.0 - 0.01 and b > at + 0.01 for a, b in times)
    assert times[-1][1] <= total + 3.0 + 0.01

    # naredbe po vremenu gledaju video sa špicom
    r = run("uredi.py", p, "popis")
    assert "UVODNA ŠPICA" in r.stdout and "ODJAVNA ŠPICA" in r.stdout
    r = run("uredi.py", p, "makni", f"{at + 0.5:.1f}-{at + 2.5:.1f}", ok=False)
    assert r.returncode != 0 and "uvodna špica" in r.stderr
    import uredi
    tl, dur = uredi.timeline(words, edit, pj)
    assert dur == pytest.approx(total + 11.0, abs=0.01)
    w_after = next(w for w in tl if w["s"] > at)
    w_main = next(w for w in ws if w["s"] > at)
    assert w_after["s"] == pytest.approx(w_main["s"] + 3.0, abs=0.01)

    # poglavlja i MP3 u vremenu videa sa špicom
    r = run("epizoda.py", p, "mp3", "--naslov", "Ep 12", env=env)
    j = load(p / "reel_v1.chapters.json")
    titles = [c["title"] for c in j["chapters"]]
    # kratka uvodna (3 s) ide u prvu temu; odjava od 8 s (< 10 s, YouTube) ide u zadnju temu
    assert titles == ["Dobrodošli u auto", "Pjesma: Bend Kutina – Ljeto", "Priča o bendu", "Što dalje"]
    song = next(c for c in j["chapters"] if c["title"].startswith("Pjesma"))
    assert song["startTime"] == pytest.approx(render.to_out(SONG["od"], cuts) + 3.0, abs=0.05)
    assert j["chapters"][-1]["endTime"] == pytest.approx(total + 11.0, abs=0.05)
    ch = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(p / "reel_v1.mp3")],
                                   capture_output=True, text=True).stdout)["chapters"]
    assert len(ch) == 4 and float(ch[-1]["end_time"]) == pytest.approx(total + 11.0, abs=0.05)

    # kadrovi za provjeru: iz špice i iz epizode
    r = run("render.py", p, "--kadar", f"{at + 1.5:.2f},{total + 3.0 + 4.0:.2f}", env=env)
    k1 = sorted(p.glob("kadar_1_*.png"))[0]
    assert k1.exists() and (p / "kadrovi.png").exists()

    # isječci nemaju špicu
    import serija
    e2, _ = serija.edit_za_isjecak(edit, words, {"id": "K1", "od": words[0]["s"], "do": words[10]["e"]},
                                   pj["duration"])
    assert "spica" not in e2

    # makni → bez špice
    run("spica.py", p, "makni")
    assert "spica" not in load(p / "edit.json")
    run("uredi.py", p, "vrati")
    assert "spica" in load(p / "edit.json")


def test_generirana_kartica_slika(ep, tmp_path):
    import shutil
    p = tmp_path / "p"
    shutil.copytree(ep, p)
    env = env_with(tmp_path)
    run("spica.py", p, "dodaj", "--naslov", "Bend iz Kutine", "--broj", "12", "--odjava", "nema", env=env)
    sp = load(p / "edit.json")["spica"]
    assert sp["uvod"] == {"generirana": True, "trajanje": 5.0} and "odjava" not in sp and sp["poslije"] == 0
    r = run("spica.py", p, "pokazi", env=env)
    png = p / "spica_uvod.png"
    assert png.exists() and "Uvodna špica" in r.stdout
    from PIL import Image
    im = np.asarray(Image.open(png).convert("RGB")).astype(float)
    # narančasto ime podcasta u sredini, tamnija mutna pozadina
    orange = (im[..., 0] > 180) & (im[..., 1] > 70) & (im[..., 1] < 170) & (im[..., 2] < 80)
    ys = np.nonzero(orange)[0]
    assert orange.sum() > 150 and 0.3 * 180 < ys.mean() < 0.55 * 180
    # loši unosi
    assert run("spica.py", p, "dodaj", "--odjava", "generirana", "--trajanje-odjave", "30", ok=False,
               env=env).returncode != 0
    assert run("spica.py", p, "dodaj", "--uvod", "nema", "--odjava", "nema", ok=False, env=env).returncode != 0
