"""M4.4b: opis epizode — YouTube opis s poglavljima i tekst za podcast platforme (objava.py epizoda)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import epizoda as EP  # noqa: E402
import objava as O  # noqa: E402
import make_nastup as MN  # noqa: E402

SONG = {"id": "P1", "od": 19.74, "do": 68.75, "izvor": "auto", "sigurnost": 0.85, "naziv": "Bend Kutina – Ljeto"}
TEME = [{"od": 0, "do": 25, "naslov": "Dobrodošli u auto", "sazetak": "Marko i gost kreću iz Kutine."},
        {"od": 25, "do": 95, "naslov": "Priča o bendu", "sazetak": "Garaža, prvi album."},
        {"od": 95, "do": 131, "naslov": "Što dalje", "sazetak": "Planovi za ljeto."}]

YT = {"naslov": "Bend iz Kutine svira uživo u Renaultu 4",
      "opis": "Marko i gost voze se po Moslavini i pričaju kako je bend nastao u garaži — i onda zasviraju "
              "pjesmu o Kutini i ljetu, uživo u autu.\n\nPretplati se za nove vožnje.",
      "hashtagovi": ["#suncani4m", "#kutina", "#podcast"]}
POD = {"naslov": "Bend iz garaže svira u autu",
       "opis": "Marko i gost voze se po Moslavini i pričaju kako je bend nastao u garaži i zašto je prvi album "
               "trajao skoro dvije godine. Na kraju bend zasvira pjesmu o Kutini i ljetu, uživo u autu.",
       "broj": "12"}


def run(*args, env=None, code=0, script="objava.py"):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    if code is not None:
        assert r.returncode == code, f"{script} {args} → {r.returncode}:\n{r.stdout}\n{r.stderr}"
    return r


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import os
    podaci = tmp_path / "podaci"
    monkeypatch.setenv("SHOFE_PODACI", str(podaci))
    e = dict(os.environ)
    e["SHOFE_PODACI"] = str(podaci)
    return e


@pytest.fixture(scope="module")
def epizoda_src(tmp_path_factory):
    base = tmp_path_factory.mktemp("epizoda objava čž")
    proj = MN.make(base / "ep")
    save(proj / "nastupi.json", {"nastupi": [dict(SONG)]})
    save(proj / "analiza.json", {"teme": TEME, "govornici": [{"id": "G1", "ime": "Marko"}, {"id": "G2", "ime": ""}]})
    run(proj, "--stil", "podcast", script="plan.py")
    run(proj, script="render.py")
    return proj


@pytest.fixture()
def ep(epizoda_src, tmp_path):
    p = tmp_path / "ep"
    shutil.copytree(epizoda_src, p)
    return p


def ispuni(proj, yt=YT, pod=POD, vid="reel_v1"):
    d = load(proj / "objava.json")
    m = d["videi"][vid]["mreze"]
    if yt is not None:
        m["youtube"] = json.loads(json.dumps(yt))
    if pod is not None:
        m["podcast"] = json.loads(json.dumps(pod))
    save(proj / "objava.json", d)


# ---------------------------------------------------------------- cijeli put na probnoj epizodi
def test_epizoda_kostur_kontekst_i_gotov_tekst(ep, env):
    r = run(ep, "epizoda", env=env, code=1)
    e = load(ep / "objava.json")["videi"]["reel_v1"]
    assert e["vrsta"] == "epizoda" and e["mreze_popis"] == ["youtube", "podcast"]
    assert set(e["mreze"]["podcast"]) == {"naslov", "opis", "broj"}
    lines = e["poglavlja_youtube"].splitlines()
    assert lines[0] == "00:00 Dobrodošli u auto" and lines[1].endswith("Pjesma: Bend Kutina – Ljeto")
    assert e["pjesme"] == ["Bend Kutina – Ljeto"] and e["govornici"] == ["Marko", "G2"]
    assert e["teme"][1] == {"naslov": "Priča o bendu", "sazetak": "Garaža, prvi album."}
    assert e["podcast_ime"] == "Sunčani4M" and e["mp3"] == ""
    assert "EPIZODA" in r.stdout and "podcast.naslov" in r.stdout and "ne piši vremena" in r.stdout
    assert "govornici: Marko, G2" in r.stdout
    # 110 s video: poglavlja od ≥ 30 s su manje od 3 → podcast opis bez poglavlja, s upozorenjem
    assert e["poglavlja_podcast"] == "" and "Spotify ih iz opisa prikaže tek od 3" in r.stdout

    ispuni(ep)
    r = run(ep, "epizoda", env=env, code=0)
    txt = (ep / "reel_v1.objava.txt").read_text(encoding="utf-8-sig")
    assert "=== YOUTUBE (epizoda) ===" in txt and "=== PODCAST PLATFORME" in txt
    yt_opis = txt.split("Opis:\n" + "-" * 40 + "\n", 1)[1].split("\n" + "-" * 40, 1)[0]
    # redoslijed: Claudeov opis, poglavlja, hashtagovi
    assert yt_opis.index("Pretplati se") < yt_opis.index("Poglavlja:\n00:00 Dobrodošli u auto") < \
        yt_opis.index("#suncani4m #kutina #podcast")
    assert "Broj epizode (zasebno polje „Episode number”): 12" in txt
    pod = txt.split("Opis epizode:\n" + "-" * 40 + "\n", 1)[1].split("\n" + "-" * 40, 1)[0]
    assert pod == POD["opis"]            # bez hashtagova serije, bez poglavlja (prekratko)
    assert "MP3 još nije napravljen" in txt
    assert "naslov u MP3-u nije upisan" in r.stdout and 'mp3 --naslov "Bend iz garaže svira u autu"' in r.stdout
    # drugi poziv ne dira tekstove, ne duplicira poglavlja
    run(ep, "epizoda", env=env, code=0)
    assert load(ep / "objava.json")["videi"]["reel_v1"]["mreze"]["podcast"]["naslov"] == POD["naslov"]
    assert (ep / "reel_v1.objava.txt").read_text(encoding="utf-8-sig").count("Poglavlja:") == 1


def test_epizoda_sama_prepoznata_i_mp3(ep, env):
    """Vodoravni ≥ 3 min u projektu s nastupima = epizoda i bez riječi „epizoda"; reel koji je prije imao samo
    YouTube dobije i podcast; MP3 naslov iz epizoda.json."""
    run(ep, env=env, code=1)                           # 110 s: obični vodoravni video, samo YouTube
    e = load(ep / "objava.json")["videi"]["reel_v1"]
    assert e["vrsta"] == "reel" and e["mreze_popis"] == ["youtube"] and "poglavlja_youtube" not in e
    meta = load(ep / "verzije" / "verzije.json")
    meta["verzije"]["1"]["trajanje"] = 300.0           # „dugačka" epizoda
    save(ep / "verzije" / "verzije.json", meta)
    run(ep, env=env, code=1)
    e = load(ep / "objava.json")["videi"]["reel_v1"]
    assert e["vrsta"] == "epizoda" and e["mreze_popis"] == ["youtube", "podcast"] and e["poglavlja_youtube"]
    # isti dugi video bez oznaka epizode: samo YouTube, ali s poglavljima
    (ep / "nastupi.json").unlink()
    (ep / "objava.json").unlink()
    run(ep, env=env, code=1)
    e = load(ep / "objava.json")["videi"]["reel_v1"]
    assert e["vrsta"] == "reel" and e["mreze_popis"] == ["youtube"] and e["poglavlja_youtube"].startswith("00:00")
    assert "poglavlja_podcast" not in e
    # MP3 već napravljen s drugim naslovom → upozori
    save(ep / "nastupi.json", {"nastupi": [dict(SONG)]})
    (ep / "reel_v1.mp3").write_bytes(b"")
    save(ep / "epizoda.json", {"naslov": "Stari naslov", "autor": "Sunčani4M"})
    run(ep, "epizoda", env=env, code=1)
    ispuni(ep)
    r = run(ep, "epizoda", env=env, code=0)
    assert "naslov u MP3-u je „Stari naslov”" in r.stdout
    txt = (ep / "reel_v1.objava.txt").read_text(encoding="utf-8-sig")
    assert "Zvuk: reel_v1.mp3 (poglavlja su već u MP3-u" in txt


def test_pravila_podcasta(ep, env):
    run(ep, "epizoda", env=env, code=1)
    loš = dict(POD, naslov="Sunčani4M #12: " + "jako " * 30 + "dugačak naslov",
               opis=POD["opis"] + " #kutina\n00:00 Uvod\n05:10 Bend", broj="#12")
    ispuni(ep, pod=loš)
    r = run(ep, "epizoda", env=env, code=1)
    assert "naslov epizode ima" in r.stdout and "najviše 150" in r.stdout
    assert "broj epizode „#12” mora biti cijeli broj" in r.stdout
    assert "Apple ga želi u zasebnom polju" in r.stdout
    assert "ime podcasta „Sunčani4M” je u naslovu" in r.stdout
    assert "podcast aplikacije ih ne koriste" in r.stdout
    assert "vremena napisana rukom" in r.stdout          # podcast bez poglavlja (kratko): samo upozorenje
    # YouTube ima poglavlja → vremena koja je Claude sam napisao su greška
    ispuni(ep, yt=dict(YT, opis=YT["opis"] + "\n\n0:00 Uvod\n1:10 Pjesma"), pod=POD)
    r = run(ep, "epizoda", env=env, code=1)
    assert "YouTube: u opisu su vremena" in r.stdout and "Shofe sam dodaje poglavlja" in r.stdout
    # predug opis epizode
    ispuni(ep, pod=dict(POD, opis="Marko priča. " * 400))
    r = run(ep, "epizoda", env=env, code=1)
    assert "opis ima" in r.stdout and "najviše 4000" in r.stdout


def test_serija_potpis_na_podcastu(ep, env):
    run("serija", "Sunčani4M", "--hashtagovi", "#suncani4m", "--potpis", "Sunčani4M — podcast iz Renaulta 4",
        env=env)
    run("serija", "Sunčani4M", "--mreza", "spotify", "--potpis", "Slušaj nas svaki petak.", env=env)
    run(ep, "epizoda", "--serija", "Sunčani4M", env=env, code=1)
    ispuni(ep, yt=dict(YT, hashtagovi=["#kutina", "#podcast"]))
    run(ep, "epizoda", env=env, code=0)
    txt = (ep / "reel_v1.objava.txt").read_text(encoding="utf-8-sig")
    pod = txt.split("Opis epizode:\n" + "-" * 40 + "\n", 1)[1].split("\n" + "-" * 40, 1)[0]
    assert pod.endswith("Slušaj nas svaki petak.") and "#" not in pod
    assert "Sunčani4M — podcast iz Renaulta 4\n\n#kutina #podcast #suncani4m" in txt


# ---------------------------------------------------------------- bez videa
def test_poglavlja_podcasta_spotify_oblik():
    ch = [{"od": 0, "naslov": "Uvod"}, {"od": 95.4, "naslov": "Bend"}, {"od": 2525, "naslov": "Kraj"}]
    assert EP.podcast_tekst(ch, 3000) == "00:00 Uvod\n01:35 Bend\n42:05 Kraj\n"
    ch[2]["od"] = 3725
    assert EP.podcast_tekst(ch, 3800).splitlines() == ["00:00:00 Uvod", "00:01:35 Bend", "01:02:05 Kraj"]
    # Spotify: ≥ 30 s između poglavlja — kratko poglavlje ode u susjedno
    cuts = [{"a": 0, "b": 600, "o": 0}]
    teme = [{"od": 0, "do": 200, "naslov": "A"}, {"od": 200, "do": 220, "naslov": "B kratka"},
            {"od": 220, "do": 600, "naslov": "C"}]
    assert [c["naslov"] for c in EP.slozi(teme, [], cuts, 600)] == ["A", "B kratka", "C"]
    assert [c["naslov"] for c in EP.slozi(teme, [], cuts, 600, min_len=O.PODCAST_POGLAVLJE_MIN)] == ["A", "C"]


def test_slozi_i_provjeri_bez_videa():
    e = {"vrsta": "epizoda", "mreze_popis": ["youtube", "podcast"], "govor": "Bok, dobrodošli.",
         "brojevi_govora": ["2", "1990"], "teme": [{"naslov": "Album iz 2003", "sazetak": ""}],
         "poglavlja_youtube": "00:00 Uvod\n00:40 Bend\n02:00 Kraj\n",
         "poglavlja_podcast": "00:00 Uvod\n00:40 Bend\n02:00 Kraj\n", "podcast_ime": "Sunčani4M",
         "mreze": {"youtube": {"naslov": "Bend iz 1990.", "opis": "Priča o albumu iz 2003.",
                               "hashtagovi": ["#kutina"]},
                   "podcast": {"naslov": "Bend iz 1990.", "opis": "Priča o albumu iz 2003. i 7 pjesama.",
                               "broj": "5"}}}
    n, full, tags = O.slozi(e, "podcast", None)
    assert full == "Priča o albumu iz 2003. i 7 pjesama.\n\nPoglavlja:\n00:00 Uvod\n00:40 Bend\n02:00 Kraj"
    assert tags == []
    fali, gr, up = O.provjeri(e, None)
    assert not fali and not gr
    assert any("broj 7 se ne čuje" in u for u in up)                  # 1990 iz govora, 2003 iz teme: u redu
    assert not any("1990" in u or "2003" in u or "broj 5" in u for u in up)
    assert not any("isti opis" in u for u in up)                       # podcast smije biti sličan YouTubeu
    assert O.BROJ_EPIZODE_RE.search("Epizoda 12: Bend") and O.BROJ_EPIZODE_RE.search("12. epizoda")
    assert O.BROJ_EPIZODE_RE.search("Ep. 3 — gost") and not O.BROJ_EPIZODE_RE.search("Renault 4 i bend")
