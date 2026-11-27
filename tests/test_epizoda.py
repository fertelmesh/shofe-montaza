"""M4.4a: poglavlja za YouTube (teme + pjesme u vremenu gotovog videa) i MP3 za podcast platforme
(−16 LUFS, true peak ≤ −1 dBTP, 128 kbps stereo 44,1 kHz, poglavlja u ID3 CHAP)."""
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

import epizoda as EP  # noqa: E402
import render  # noqa: E402
import make_nastup as MN  # noqa: E402

SONG = {"id": "P1", "od": 19.74, "do": 68.75, "izvor": "auto", "sigurnost": 0.85, "naziv": "Bend Kutina – Ljeto"}
TEME = [{"od": 0, "do": 25, "naslov": "Dobrodošli u auto", "sazetak": "."},
        {"od": 25, "do": 95, "naslov": "Priča o bendu", "sazetak": "."},
        {"od": 95, "do": 131, "naslov": "Što dalje", "sazetak": "."}]


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


def cuts_of(*spans):
    out, o = [], 0.0
    for a, b in spans:
        out.append({"a": a, "b": b, "o": o})
        o += b - a
    return out, o


# ---------------------------------------------------------------- bez videa
def test_pjesma_je_svoje_poglavlje_tema_se_nastavlja():
    cuts, total = cuts_of((0, 300))
    teme = [{"od": 0, "do": 120, "naslov": "Uvod"}, {"od": 120, "do": 300, "naslov": "Glavna priča"}]
    ch = EP.slozi(teme, [{"od": 150, "do": 200, "naziv": "Bend – Pjesma"}], cuts, total)
    assert [(round(c["od"]), c["naslov"]) for c in ch] == [
        (0, "Uvod"), (120, "Glavna priča"), (150, "Pjesma: Bend – Pjesma"), (200, "Glavna priča (nastavak)")]
    assert [c["vrsta"] for c in ch] == ["tema", "tema", "pjesma", "tema"]
    # pjesma bez naziva; tema koja počinje u pjesmi nije „nastavak"
    ch = EP.slozi([{"od": 0, "do": 100, "naslov": "A"}, {"od": 120, "do": 300, "naslov": "B"}],
                  [{"od": 100, "do": 160}], cuts, total)
    assert [c["naslov"] for c in ch] == ["A", "Nastup benda", "B"]
    assert round(ch[2]["od"]) == 160


def test_kratka_tema_iza_pjesme_ide_u_sljedecu_temu():
    """Pregled M4: kratki razgovor iza pjesme ne nestane u poglavlju pjesme ako iza njega ima tema
    (inače bi „Pjesma" trajala do kraja epizode); zadnja kratka tema ima samo pjesmu za susjeda."""
    cuts, total = cuts_of((0, 193))
    teme = [{"od": 0, "do": 35, "naslov": "Dobrodošli"}, {"od": 35, "do": 57, "naslov": "Klima"},
            {"od": 57, "do": 92, "naslov": "Greška"}, {"od": 150, "do": 168, "naslov": "Priča o bendu"},
            {"od": 168, "do": 193, "naslov": "Odjava"}]
    song = [{"od": 92, "do": 150, "naziv": "Bend"}]
    ch = EP.slozi(teme, song, cuts, total, min_len=30)
    assert [(round(c["od"]), c["naslov"]) for c in ch] == [
        (0, "Dobrodošli"), (57, "Greška"), (92, "Pjesma: Bend"), (150, "Odjava")]
    ch = EP.slozi(teme[:4], song, cuts, 170.0, min_len=30)      # bez odjave: priča (20 s) ostane uz pjesmu
    assert [c["naslov"] for c in ch][-1] == "Pjesma: Bend"


def test_vrijeme_gotovog_videa_izrezi_i_brzina():
    cuts, total = cuts_of((0, 50), (80, 200), (260, 400))   # izrezano 50–80 i 200–260
    teme = [{"od": 5, "do": 60, "naslov": "A"}, {"od": 60, "do": 90, "naslov": "B"},
            {"od": 90, "do": 210, "naslov": "C"}, {"od": 210, "do": 255, "naslov": "D (sva izrezana)"},
            {"od": 255, "do": 400, "naslov": "E"}]
    ch = EP.slozi(teme, [], cuts, total)
    # A počinje na 5 s, ali prvo poglavlje je uvijek 00:00; B počinje u izrezu → prvi zadržani trenutak (80 → 50)
    assert [(round(c["od"], 2), c["naslov"]) for c in ch] == [(0, "A"), (50, "B"), (60, "C"), (170, "E")]
    ch2 = EP.slozi(teme, [], cuts, total / 1.25, brzina=1.25)
    # B traje 8 s u bržem videu (< 10 s, YouTube ga ne bi prihvatio) → ide u dulji susjedni A
    assert [(round(c["od"], 2), c["naslov"]) for c in ch2] == [(0, "A"), (48, "C"), (136, "E")]


def test_kratka_poglavlja_spojena_youtube_pravila():
    cuts, total = cuts_of((0, 200))
    teme = [{"od": 0, "do": 4, "naslov": "Pozdrav"}, {"od": 4, "do": 60, "naslov": "Prva"},
            {"od": 60, "do": 66, "naslov": "Kratka"}, {"od": 66, "do": 150, "naslov": "Druga"},
            {"od": 150, "do": 195, "naslov": "Treća"}, {"od": 195, "do": 200, "naslov": "Odjava"}]
    ch = EP.slozi(teme, [], cuts, total)
    starts = [c["od"] for c in ch] + [total]
    assert starts[0] == 0 and all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    assert [c["naslov"] for c in ch] == ["Prva", "Druga", "Treća"]   # kratki dijelovi u duljem susjedu
    txt = EP.youtube_tekst(ch, total)
    assert txt.splitlines() == ["00:00 Prva", "01:06 Druga", "02:30 Treća"]


def test_format_vremena_i_naslovi():
    ch = [{"od": 0, "naslov": "a"}, {"od": 59.99, "naslov": "b"}, {"od": 3723.6, "naslov": "c"}]
    assert EP.youtube_tekst(ch, 4000).splitlines() == ["0:00:00 a", "0:00:59 b", "1:02:03 c"]
    assert EP.youtube_tekst(ch[:2], 120).splitlines() == ["00:00 a", "00:59 b"]
    assert EP._cist("  <Cijena>   klima  ") == "Cijena klima"
    j = EP.chapters_json([{"od": 0.0, "naslov": "a"}, {"od": 12.345, "naslov": "b"}], 30.0)
    assert j == {"version": "1.2.0", "chapters": [{"startTime": 0.0, "endTime": 12.35, "title": "a"},
                                                  {"startTime": 12.35, "endTime": 30.0, "title": "b"}]}
    meta = EP.ffmetadata({"title": "A=B; #1 čž"}, [{"od": 0, "naslov": "x"}, {"od": 1.5, "naslov": "y"}], 3.0)
    assert "title=A\\=B\\; \\#1 čž" in meta
    assert "START=1500\nEND=3000\ntitle=y" in meta


# ---------------------------------------------------------------- probna epizoda
@pytest.fixture(scope="module")
def epizoda(tmp_path_factory):
    base = tmp_path_factory.mktemp("epizoda čž")
    proj = MN.make(base / "ep")
    save(proj / "nastupi.json", {"nastupi": [dict(SONG)]})
    save(proj / "analiza.json", {"teme": TEME})
    run("plan.py", proj, "--stil", "podcast")
    r = run("render.py", proj)
    assert "Poglavlja za YouTube" not in r.stdout      # 131 s: prekratko za poglavlja uz render
    return proj


def test_poglavlja_iz_projekta(epizoda, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizoda, p)
    r = run("epizoda.py", p, "poglavlja")
    edit = load(p / "verzije" / "edit_v1.json") if (p / "verzije" / "edit_v1.json").exists() else load(p / "edit.json")
    pj, words = load(p / "project.json"), load(p / "transcript.json")["words"]
    cuts, _, total = render.build_cuts(words, edit, render.resolve_style(edit), pj["fps"], pj["duration"])
    song_out = render.to_out(SONG["od"], cuts)
    lines = (p / "reel_v1.poglavlja.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "00:00 Dobrodošli u auto"
    assert lines[1] == f"00:{int(song_out):02d} Pjesma: Bend Kutina – Ljeto"
    assert [x.split(" ", 1)[1] for x in lines] == ["Dobrodošli u auto", "Pjesma: Bend Kutina – Ljeto",
                                                   "Priča o bendu", "Što dalje"]
    j = load(p / "reel_v1.chapters.json")
    assert abs(j["chapters"][1]["startTime"] - song_out) < 0.02
    assert abs(j["chapters"][-1]["endTime"] - total) < 0.02
    # „Priča o bendu" počinje kad pjesma završi (25–68,75 je u pjesmi)
    assert abs(j["chapters"][2]["startTime"] - render.to_out(SONG["do"] - 0.05, cuts)) < 0.1
    assert "4" in r.stdout and "zalijepi u opis" in r.stdout


def test_poglavlja_uz_render_epizode(epizoda, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizoda, p)
    edit = load(p / "edit.json")
    assert EP.for_render(p, edit, p / "reel_v1.mp4", 1080, 1920, 300) == []          # uspravno: ne
    assert EP.for_render(p, edit, p / "reel_v1.mp4", 1920, 1080, 120) == []          # kratko: ne
    lines = EP.for_render(p, edit, p / "reel_v1.mp4", 1920, 1080, 300)
    assert lines and "reel_v1.poglavlja.txt (4;" in lines[0]
    save(p / "analiza.json", {"teme": []})
    assert EP.for_render(p, edit, p / "reel_v1.mp4", 1920, 1080, 300) == []          # bez tema: ne
    save(p / "analiza.json", {"teme": [TEME[0]]})                                    # samo 1 tema + pjesma
    r = run("epizoda.py", p, "poglavlja")
    assert "YouTube ih prikazuje tek od 3" in r.stdout


def ffprobe_json(path, *what):
    r = subprocess.run(["ffprobe", "-v", "error", *what, "-of", "json", str(path)], capture_output=True, text=True,
                       encoding="utf-8", check=True)
    return json.loads(r.stdout)


def envelope(path, sr=8000, hop=80):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, np.float32)
    n = len(x) // hop
    return np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-9)


def test_mp3_za_podcast(epizoda, tmp_path):
    p = tmp_path / "p"
    shutil.copytree(epizoda, p)
    slika = tmp_path / "naslovna.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=600x600", "-frames:v", "1",
                    str(slika)], check=True)
    r = run("epizoda.py", p, "mp3", "--naslov", "Epizoda 1: Bend u autu", "--slika", slika)
    mp3 = p / "reel_v1.mp3"
    assert mp3.exists() and "MP3 za podcast platforme" in r.stdout
    I, tp = EP.izmjeri(mp3)
    assert abs(I - (-16.0)) <= 0.5, I
    assert tp <= -1.0, tp
    d = ffprobe_json(mp3, "-show_streams", "-show_format", "-show_chapters")
    a = next(s for s in d["streams"] if s["codec_type"] == "audio")
    assert a["codec_name"] == "mp3" and int(a["sample_rate"]) == 44100 and int(a["channels"]) == 2
    assert abs(int(a["bit_rate"]) - 128000) < 2000
    cover = [s for s in d["streams"] if s["codec_type"] == "video"]
    assert cover and cover[0]["disposition"]["attached_pic"] == 1
    tags = {k.lower(): v for k, v in d["format"]["tags"].items()}
    assert tags["title"] == "Epizoda 1: Bend u autu" and tags["artist"] == "Sunčani4M"
    j = load(p / "reel_v1.chapters.json")["chapters"]
    assert [c["tags"]["title"] for c in d["chapters"]] == [c["title"] for c in j]
    assert all(abs(float(c["start_time"]) - x["startTime"]) < 0.01 for c, x in zip(d["chapters"], j))
    vdur = float(ffprobe_json(p / "reel_v1.mp4", "-show_format")["format"]["duration"])
    assert abs(float(d["format"]["duration"]) - vdur) < 0.15
    # zvuk MP3-a poravnat sa zvukom videa (poglavlja padaju na isto mjesto): pomak ovojnice < 20 ms
    ev, em = envelope(p / "reel_v1.mp4"), envelope(mp3)
    n = min(len(ev), len(em))
    ev, em = np.log(ev[:n]), np.log(em[:n])
    lags = range(-10, 11)
    cc = [np.corrcoef(ev[max(0, k):n + min(0, k)], em[max(0, -k):n - max(0, k)])[0, 1] for k in lags]
    assert abs(list(lags)[int(np.argmax(cc))]) <= 2 and max(cc) > 0.95
    assert load(p / "epizoda.json")["naslov"] == "Epizoda 1: Bend u autu"   # pamti se
    r = run("epizoda.py", p, "mp3")
    assert ffprobe_json(mp3, "-show_format")["format"]["tags"]["title"] == "Epizoda 1: Bend u autu"


def test_mp3_glasni_vrhovi_limiter(tmp_path):
    """Tihi video s oštrim vrhovima (pljesak, udarac vratima): pojačanje do −16 LUFS + limiter, TP ≤ −1."""
    sr = 48000
    t = np.arange(int(sr * 30)) / sr
    x = 0.06 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.5 * t))
    for k in range(1, 30, 3):
        i = k * sr
        x[i:i + 24] += 0.95 * np.sign(np.sin(np.arange(24) * 0.9))
    x = np.clip(x, -0.99, 0.99).astype(np.float32)
    raw = tmp_path / "a.f32"
    raw.write_bytes(np.stack([x, x], 1).tobytes())
    vid = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=30",
                    "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", str(raw), "-shortest", "-c:v", "libx264",
                    "-c:a", "aac", "-b:a", "192k", str(vid)], check=True)
    I0, tp0 = EP.izmjeri(vid)
    assert I0 < -22 and tp0 > -1.0
    res = EP.napravi_mp3(tmp_path, vid, "test", [], 30.0, ispis=False)
    assert res["limiter"] and abs(res["lufs"] - (-16.0)) <= 0.5, res
    assert res["tp"] <= -1.0, res


def test_bez_videa_jasna_poruka(tmp_path):
    proj = MN.make(tmp_path / "ep")
    save(proj / "analiza.json", {"teme": TEME})
    run("plan.py", proj, "--stil", "podcast")
    r = run("epizoda.py", proj, "mp3", ok=False)
    assert r.returncode != 0 and "prvo render.py" in (r.stdout + r.stderr)
    assert (proj / "trenutno.poglavlja.txt").exists()
