"""M2.5a: titlovi kao SRT/VTT datoteka (YouTube, DaVinci), u vremenu gotovog videa."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import titlovi  # noqa: E402
import verzije  # noqa: E402

TS = re.compile(r"^(\d\d):(\d\d):(\d\d)[,.](\d\d\d) --> (\d\d):(\d\d):(\d\d)[,.](\d\d\d)$")


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


def parse_srt(text):
    """Strogi čitač SRT-a: redni broj, vrijeme, 1–2 retka, prazan redak."""
    cues = []
    for n, block in enumerate(text.strip().split("\n\n"), 1):
        lines = block.split("\n")
        assert lines[0] == str(n), block
        m = TS.match(lines[1])
        assert m, lines[1]
        g = list(map(int, m.groups()))
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append((a, b, lines[2:]))
    return cues


def words_from(text, start=0.0, wdur=0.32, gap=0.08, pauses=None):
    """Sintetske riječi: svaka 0,32 s, razmak 0,08 s; pauses = {indeks_riječi: dodatna stanka prije}."""
    ws, t = [], start
    for i, tok in enumerate(text.split()):
        t += (pauses or {}).get(i, 0.0)
        ws.append({"t": tok, "s": round(t, 3), "e": round(t + wdur, 3)})
        t += wdur + gap
    return ws


# ---------------------------------------------------------------- pravila titlova
def test_sentence_breaks_and_short_cues():
    ws = words_from("Bok, ja sam Marko iz Kutine. Danas čistimo klimu. Može?")
    cues = titlovi.make_cues(ws, 20.0)
    assert [" ".join(c["retci"]) for c in cues] == ["Bok, ja sam Marko iz Kutine.", "Danas čistimo klimu.", "Može?"]
    for a, b in zip(cues, cues[1:]):
        assert a["do"] <= b["od"] - 2 / 30 + 1e-6      # razmak barem 2 sličice
    assert cues[-1]["do"] - cues[-1]["od"] >= titlovi.MIN_DUR - 2e-3  # i kratki „Može?" se stigne pročitati


def test_long_sentence_two_lines_max_42():
    txt = ("Kad klima počne smrdjeti, to je znak da je filter pun prašine i bakterija, "
           "a to se može riješiti za deset minuta bez majstora i bez posebnog alata koji košta.")
    cues = titlovi.make_cues(words_from(txt), 60.0)
    assert len(cues) >= 2
    for c in cues:
        assert 1 <= len(c["retci"]) <= 2
        assert all(len(line) <= 42 for line in c["retci"]), c["retci"]
        assert c["do"] - c["od"] <= titlovi.MAX_DUR + 1e-6
    joined = " ".join(" ".join(c["retci"]) for c in cues)
    assert joined == txt                                  # ništa izgubljeno, ništa dodano
    # prvi titl puca na zarezu, ne usred fraze
    assert " ".join(cues[0]["retci"]).endswith(",")


def test_line_split_balanced_not_on_preposition():
    ws = words_from("Filter se čisti toplom vodom i blagim deterdžentom u kadi")
    lines = titlovi.split_lines(ws)
    assert len(lines) == 2 and all(len(x) <= 42 for x in lines)
    assert lines[0].split()[-1] not in titlovi.WEAK_END


def test_pause_starts_new_cue_and_max_duration():
    ws = words_from("prvo drugo treće četvrto", pauses={2: 1.5})
    cues = titlovi.make_cues(ws, 10.0)
    assert [" ".join(c["retci"]) for c in cues] == ["prvo drugo", "treće četvrto"]
    slow = words_from(" ".join(["riječ"] * 14), wdur=0.6, gap=0.1)   # ~10 s bez interpunkcije
    for c in titlovi.make_cues(slow, 20.0):
        assert c["do"] - c["od"] <= titlovi.MAX_DUR + 1e-6


def test_cue_never_ends_before_last_word_and_not_past_video():
    ws = words_from("Pratite SF klimu za još savjeta.")
    total = ws[-1]["e"] + 0.1
    cues = titlovi.make_cues(ws, total)
    assert cues[-1]["do"] <= total + 1e-6
    assert cues[-1]["do"] >= ws[-1]["e"] - 1e-6


def test_srt_and_vtt_format(tmp_path):
    cues = titlovi.make_cues(words_from("Čišćenje klime: žica, ćelija, đon. Šteta!"), 10.0)
    titlovi.write_srt(tmp_path / "a.srt", cues)
    titlovi.write_vtt(tmp_path / "a.vtt", cues)
    raw = (tmp_path / "a.srt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                 # BOM za Windows programe
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")   # CRLF na svakom sustavu
    parsed = parse_srt(raw.decode("utf-8-sig").replace("\r\n", "\n"))
    assert len(parsed) == len(cues) and "Šteta!" in parsed[-1][2][0]
    assert b"\r" not in (tmp_path / "a.vtt").read_bytes()
    vtt = (tmp_path / "a.vtt").read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT\n\n") and "00:00:00.000 --> " in vtt
    assert titlovi._ts(3725.4567, ",") == "01:02:05,457"


# ---------------------------------------------------------------- na projektu
@pytest.fixture(scope="module")
def baza(tmp_path_factory):
    base = tmp_path_factory.mktemp("titlovi čćž test")
    clips = base / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    proj = base / "shofe_projekt"
    run("prepare.py", clips, "--out", proj)
    pj = load(proj / "project.json")
    mock = load(FIX / "mock_words.json")
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj, "--stil", "suncani")
    return proj


def test_render_writes_srt_matching_video(baza):
    edit = load(baza / "edit.json")
    edit["hook"] = "Klima smrdi? Očisti je sam"
    save(baza / "edit.json", edit)
    out = run("render.py", baza, "--brzo").stdout
    v = verzije.viewed(baza)
    srt = baza / f"reel_v{v}_pregled.srt"
    assert srt.exists() and srt.name in out
    cues = parse_srt(srt.read_text(encoding="utf-8-sig"))
    dur = float(json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(baza / f"reel_v{v}_pregled.mp4")],
        capture_output=True, text=True, encoding="utf-8").stdout)["format"]["duration"])
    assert cues[0][0] < 1.0 and cues[-1][1] <= dur + 0.05
    for a, b in zip(cues, cues[1:]):
        assert a[0] < a[1] <= b[0]
    text = " ".join(" ".join(c[2]) for c in cues)
    assert "Kutine" in text and "eee" not in text.split()   # izbačeni poluglas nije u titlovima
    assert "OČISTI" not in text                             # hook nije titl, a tekst nije u velikim slovima


def test_srt_follows_cuts_speed_and_corrections(baza, tmp_path):
    p = tmp_path / "projekt"
    p.mkdir()
    for f in ("project.json", "transcript.json", "edit.json"):
        shutil.copy(baza / f, p / f)
    edit = load(p / "edit.json")
    seg = next(s for s in edit["odsjecci"] if s.get("zadrzi", True) and "Kutine" in s["tekst"])
    seg["tekst"] = seg["tekst"].replace("Kutine", "Kutine (HR)")
    save(p / "edit.json", edit)
    c1, total1 = titlovi.cues_for(p, edit)
    assert any("Kutine (HR)" in " ".join(c["retci"]) for c in c1)   # Claudeov ispravak teksta
    edit["brzina"] = 1.25
    c2, total2 = titlovi.cues_for(p, edit)
    assert abs(total2 - total1 / 1.25) < 1e-6
    assert abs(c2[1]["od"] - c1[1]["od"] / 1.25) < 0.01
    # makni prvu rečenicu naredbom → nestaje i iz titlova, ostali se pomaknu naprijed
    save(p / "edit.json", dict(edit, brzina=1.0))
    first = " ".join(c1[0]["retci"]).split()
    run("uredi.py", p, "makni", "--od", " ".join(first[:2]), "--cijele-recenice", "--trenutno")
    r = run("titlovi.py", p, "--trenutno", "--format", "oba", "--ispis")
    assert "titlovi_trenutno.srt" in r.stdout and (p / "titlovi_trenutno.vtt").exists()
    c3 = parse_srt((p / "titlovi_trenutno.srt").read_text(encoding="utf-8-sig"))
    assert " ".join(c3[0][2]) != " ".join(c1[0]["retci"]) and c3[0][0] < 1.0


def test_cli_version_and_errors(baza):
    v = verzije.viewed(baza)
    r = run("titlovi.py", baza, "--verzija", v, "--izlaz", "za_youtube")
    assert (baza / "za_youtube.srt").exists() and f"verzija {v}" in r.stdout
    r = run("titlovi.py", baza, "--verzija", 99, ok=False)
    assert r.returncode != 0 and "nema verzije 99" in r.stderr
