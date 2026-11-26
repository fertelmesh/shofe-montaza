"""M3.3: render odabranih isječaka u seriji (isjecci.py render → isjecci/K1_naslov.mp4).

Probna snimka je izmišljeni dio epizode Sunčani4M iz test_isjecci (≈ 4,5 min, dva govornika) s
uspravnim testnim videom (na slici brojač sekundi), tako da se vidi iz kojeg dijela snimke je isječak.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import serija as S  # noqa: E402
from common import ffmpeg, ffprobe  # noqa: E402
from test_isjecci import load, make_words, save  # noqa: E402


def run(script, *args, code=0):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if code is not None:
        assert r.returncode == code, f"{script} {args} → {r.returncode}:\n{r.stdout}\n{r.stderr}"
    return r


def probe_dur(p):
    r = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def srt_text(p):
    blocks = Path(p).read_text(encoding="utf-8").strip().split("\n\n")
    return [" ".join(b.splitlines()[2:]) for b in blocks]


@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    proj = tmp_path_factory.mktemp("isjecci render čć") / "epizoda"
    proj.mkdir()
    words, blocks, end = make_words()
    dur = round(end + 0.5, 3)
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    subprocess.run([ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=270x480:rate=30:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=f=220:sample_rate=48000:duration={dur}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(proj / "source.mp4")], check=True)
    save(proj / "project.json", {"width": 270, "height": 480, "fps": 30, "duration": dur, "format": "9:16",
                                 "clips": [{"file": str((proj / "source.mp4").resolve()), "start": 0.0, "dur": dur}]})
    save(proj / "analiza.json", {"trajanje": dur, "trenuci": [],
                                 "teme": [{"od": round(a, 2), "do": round(c, 2), "naslov": b["tema"], "sazetak": ""}
                                          for b, a, c in blocks]})
    run("plan.py", proj, "--stil", "podcast")
    run("isjecci.py", proj, "predlozi", "--broj", "4", code=1)
    data = load(proj / "isjecci.json")
    for n, c in enumerate(data["isjecci"]):
        c.update(ocjena=8 - n, razlog="Zaokružena misao s jasnim početkom.", naslov=f"Savjet broj {n + 1} čćž",
                 hook=f"Ovo nitko ne zna {n + 1}")
    save(proj / "isjecci.json", data)
    run("isjecci.py", proj, "provjeri")
    return proj


def test_edit_za_isjecak_rezovi_i_napomene():
    words = [{"w": f"r{i}.", "s": i * 1.0, "e": i * 1.0 + 0.6} for i in range(20)]
    base = {"stil": "cisto", "hook": "glavni", "naglasi": ["x"], "izrezi": [{"od": 6.0, "do": 7.0}],
            "odsjecci": [{"id": 1, "od": 0.0, "do": 4.6, "tekst": "a", "zadrzi": True},
                         {"id": 2, "od": 5.0, "do": 9.6, "tekst": "ponovljeno", "zadrzi": False, "napomena": "auto"},
                         {"id": 3, "od": 10.0, "do": 19.6, "tekst": "b", "zadrzi": True}]}
    c = {"id": "K2", "od": 5.0, "do": 12.6, "rijeci": [5, 12], "hook": "Novi hook", "stil": "udarno",
         "izrezi": [{"od": 8.0, "do": 8.7}]}
    e, notes = S.edit_za_isjecak(base, words, c, 20.0)
    assert e["izrezi"][0] == {"od": 0.0, "do": 4.6, "naredba": "isječak K2: prije"}
    assert e["izrezi"][1]["od"] == 13.0 and e["izrezi"][1]["do"] > 20
    assert e["izrezi"][2]["od"] == 8.0 and len(e["izrezi"]) == 3  # rez glavnog videa (6–7) nije prenesen
    assert e["stil"] == "udarno" and e["hook"] == "Novi hook" and e["naglasi"] == ["x"]
    assert any("glavnog videa" in n for n in notes) and any("#2" in n for n in notes)
    assert base["hook"] == "glavni" and len(base["izrezi"]) == 1  # glavni edit netaknut
    # pogrešne `rijeci` → granice po vremenu; prva riječ snimke → nema reza „prije"
    e2, _ = S.edit_za_isjecak(base, words, {"id": "K1", "od": 0.0, "do": 3.6, "rijeci": [7, 9]}, 20.0, stil="kino")
    assert len(e2["izrezi"]) == 1 and e2["izrezi"][0]["od"] == 4.0 and e2["stil"] == "kino" and e2["hook"] == ""


def test_imena_datoteka():
    assert S.slug("Kako očistiti filter? Đurđa & 300 €") == "kako-ocistiti-filter-djurdja-300"
    assert S.ime_datoteke({"id": "K3", "naslov": "Šuma i žaba"}) == "isjecci/K3_suma-i-zaba.mp4"
    assert S.ime_datoteke({"id": "K3", "naslov": ""}, brzo=True) == "isjecci/K3_pregled.mp4"


def test_render_bez_odobrenih_i_bez_hooka(projekt):
    r = run("isjecci.py", projekt, "render", code=1)
    assert "nijedan isječak nije odobren" in r.stderr
    data = load(projekt / "isjecci.json")
    hook = data["isjecci"][0]["hook"]
    data["isjecci"][0]["hook"] = ""
    save(projekt / "isjecci.json", data)
    kid = data["isjecci"][0]["id"]
    r = run("isjecci.py", projekt, "render", kid, code=1)
    assert f"{kid}: nema \"hook\"" in r.stdout
    data["isjecci"][0]["hook"] = hook
    save(projekt / "isjecci.json", data)


def test_render_serija(projekt):
    edit_before = hashlib.sha256((projekt / "edit.json").read_bytes()).hexdigest()
    data = load(projekt / "isjecci.json")
    k1, k2 = data["isjecci"][0], data["isjecci"][1]
    k2["stil"] = "udarno"
    save(projekt / "isjecci.json", data)
    run("isjecci.py", projekt, "odobri", f"{k1['id']},{k2['id']}")
    r = run("isjecci.py", projekt, "render")
    assert "Gotovo 2 isječka" in r.stdout, r.stdout
    data = load(projekt / "isjecci.json")
    by = {c["id"]: c for c in data["isjecci"]}
    words = load(projekt / "transcript.json")["words"]
    for cid, stil in ((k1["id"], "podcast"), (k2["id"], "udarno")):
        c = by[cid]
        rd = c["render"]
        video = projekt / rd["datoteka"]
        assert video.exists() and video.with_suffix(".srt").exists() and video.with_suffix(".fcpxml").exists()
        assert re.fullmatch(rf"isjecci/{cid}_savjet-broj-\d-ccz\.mp4", rd["datoteka"])
        assert rd["stil"] == stil and rd["hook"] == c["hook"]
        d = probe_dur(video)
        assert abs(d - rd["trajanje"]) < 0.2
        assert 0.75 * c["trajanje"] < d < 1.3 * c["trajanje"] + 1, (d, c["trajanje"])
        # titlovi = točno tekst isječka, od prve do zadnje riječi
        a, b = c["rijeci"]
        cues = " ".join(srt_text(video.with_suffix(".srt")))
        expect = " ".join(w["w"] for w in words[a:b + 1])
        assert cues.split() == expect.split()
        e = load(video.with_suffix(".edit.json"))
        assert e["hook"] == c["hook"] and e["isjecak"]["id"] == cid
    assert (projekt / "isjecci" / "pregled.png").exists()
    assert "video: isjecci/" in (projekt / "isjecci.txt").read_text(encoding="utf-8")
    # glavni projekt netaknut: edit.json isti, nema novih verzija, nema reel_v*.mp4
    assert hashlib.sha256((projekt / "edit.json").read_bytes()).hexdigest() == edit_before
    assert not list(projekt.glob("reel_v*.mp4")) and not (projekt / "verzije").exists()
    assert not list(projekt.glob("K*.fcpxml"))  # FCPXML je uz video u isjecci/


def test_novi_naslov_mice_stari_video_i_kadrovi(projekt):
    data = load(projekt / "isjecci.json")
    c = next(x for x in data["isjecci"] if x.get("render"))
    old = projekt / c["render"]["datoteka"]
    c["naslov"] = "Drugi naslov"
    save(projekt / "isjecci.json", data)
    run("isjecci.py", projekt, "render", c["id"], "--stil", "cisto")
    new = projekt / "isjecci" / f"{c['id']}_drugi-naslov.mp4"
    assert new.exists() and not old.exists() and not old.with_suffix(".srt").exists()
    assert load(projekt / "isjecci.json") and next(
        x for x in load(projekt / "isjecci.json")["isjecci"] if x["id"] == c["id"])["render"]["stil"] == "cisto"
    run("isjecci.py", projekt, "render", c["id"], "--kadar", "0.5,5")
    assert (projekt / "isjecci" / f"{c['id']}_kadrovi.png").exists()
    r = run("isjecci.py", projekt, "render", c["id"], "--stil", "nepostoji", code=1)
    assert "nepoznat stil" in r.stdout
