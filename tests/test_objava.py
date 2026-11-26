"""M3.4a: tekstovi za objavu po mreži (objava.py → objava.json, <video>.objava.txt)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import objava as O  # noqa: E402
import verzije  # noqa: E402

SRT = """1
00:00:00,000 --> 00:00:02,500
Znate li koliko struje troši klima

2
00:00:02,600 --> 00:00:05,000
na 26 stupnjeva? Manje nego frižider.
"""


def run(*args, env=None, code=0):
    r = subprocess.run([sys.executable, str(SCRIPTS / "objava.py"), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    if code is not None:
        assert r.returncode == code, f"objava.py {args} → {r.returncode}:\n{r.stdout}\n{r.stderr}"
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


@pytest.fixture()
def projekt(tmp_path):
    proj = tmp_path / "projekt čć"
    (proj / "isjecci").mkdir(parents=True)
    save(proj / "project.json", {"format": "9:16", "width": 1080, "height": 1920})
    # reel v2 (gledan) — video ne mora biti pravi, trajanje je u verzijama
    (proj / "reel_v2.mp4").write_bytes(b"")
    (proj / "reel_v2.srt").write_text(SRT, encoding="utf-8-sig")
    verzije.record_render(proj, 2, {"hook": "Klima troši manje od frižidera"}, "reel_v2.mp4", 34.2)
    # dva renderirana isječka + jedan nerenderiran
    for k in ("K1", "K2"):
        (proj / "isjecci" / f"{k}_savjet.mp4").write_bytes(b"")
        (proj / "isjecci" / f"{k}_savjet.srt").write_text(SRT, encoding="utf-8-sig")
    save(proj / "isjecci.json", {"isjecci": [
        {"id": "K1", "naslov": "Struja i klima", "hook": "Koliko troši klima?", "razlog": "Jasan broj.",
         "render": {"datoteka": "isjecci/K1_savjet.mp4", "trajanje": 31.0, "hook": "Koliko troši klima?"}},
        {"id": "K2", "naslov": "Filter", "hook": "Čisti filter", "render": {"datoteka": "isjecci/K2_savjet.mp4",
                                                                            "trajanje": 44.0, "hook": "Čisti filter"}},
        {"id": "K3", "naslov": "Nije gotov", "hook": "x"},
    ]})
    return proj


DOBRO = {
    "instagram": {"opis": "Klima na 26 °C troši manje struje nego frižider. 🌞\n\nSpremi za ljeto i pošalji "
                          "nekome tko se boji računa.", "hashtagovi": ["#klima", "#ustedastruje", "#ljeto"]},
    "tiktok": {"opis": "Klima ili frižider — tko troši više? 🤔", "hashtagovi": ["#klima", "#struja", "#savjeti"]},
    "youtube": {"naslov": "Koliko struje troši klima na 26 °C?",
                "opis": "Klima na 26 stupnjeva troši manje nego frižider. Kratki savjet za ljeto.",
                "hashtagovi": ["#klima", "#shorts"]},
}


def ispuni(proj, vid, mreze=DOBRO):
    d = load(proj / "objava.json")
    d["videi"][vid]["mreze"] = json.loads(json.dumps(mreze))
    save(proj / "objava.json", d)


def test_prvi_poziv_napravi_kostur_i_trazi_tekstove(projekt, env):
    r = run(projekt, env=env, code=1)
    d = load(projekt / "objava.json")
    assert list(d["videi"]) == ["reel_v2"]          # zadano: video koji se gleda
    e = d["videi"]["reel_v2"]
    assert e["mreze_popis"] == ["instagram", "tiktok", "youtube"]
    assert e["govor"].startswith("Znate li koliko struje") and "frižider" in e["govor"]
    assert e["hook"] == "Klima troši manje od frižidera"
    assert set(e["mreze"]["youtube"]) == {"naslov", "opis", "hashtagovi"}
    assert "youtube.naslov" in r.stdout and "instagram.opis" in r.stdout
    assert "YouTube Shorts" in r.stdout and "govor: Znate li" in r.stdout


def test_gotovi_tekstovi_daju_datoteku_za_kopiranje(projekt, env):
    run(projekt, env=env, code=1)
    ispuni(projekt, "reel_v2")
    r = run(projekt, "--ispis", env=env, code=0)
    txt = (projekt / "reel_v2.objava.txt").read_text(encoding="utf-8-sig")
    assert "=== INSTAGRAM ===" in txt and "=== TIKTOK ===" in txt and "=== YOUTUBE (Shorts) ===" in txt
    assert "Koliko struje troši klima na 26 °C?" in txt
    assert "#klima #ustedastruje #ljeto" in txt
    assert (projekt / "objava.txt").exists()
    assert "=== INSTAGRAM ===" in r.stdout
    # drugi poziv ne briše Claudeove tekstove
    run(projekt, env=env, code=0)
    assert load(projekt / "objava.json")["videi"]["reel_v2"]["mreze"]["tiktok"]["opis"].startswith("Klima ili")


def test_pravila_mreza(projekt, env):
    run(projekt, env=env, code=1)
    lose = json.loads(json.dumps(DOBRO))
    lose["instagram"]["hashtagovi"] = ["#a1", "#b2", "#c3", "#d4", "#e5", "#f6"]
    lose["tiktok"]["hashtagovi"] = ["#dobar dan"]
    lose["youtube"]["naslov"] = "Klima <3 " + "x" * 100
    lose["youtube"]["opis"] = "Opis [ubaci cijenu]"
    ispuni(projekt, "reel_v2", lose)
    r = run(projekt, env=env, code=1)
    out = r.stdout
    assert "Instagram: 6 hashtagova — Instagram dopušta najviše 5" in out
    assert "TikTok: hashtag „#dobar”" not in out  # razmak razdvaja → dva hashtaga, oba valjana
    assert "YouTube: naslov ima" in out and "najviše 100" in out
    assert "< i > nisu dopušteni" in out
    assert "zamjenski tekst „[ubaci cijenu]”" in out
    assert not (projekt / "reel_v2.objava.txt").exists()


def test_upozorenja(projekt, env):
    run(projekt, env=env, code=1)
    m = json.loads(json.dumps(DOBRO))
    m["instagram"]["opis"] = "A" * 140 + "\nDrugi redak 300 eura."
    m["tiktok"]["opis"] = m["youtube"]["opis"]
    m["tiktok"]["hashtagovi"] = ["#sunčaniput", "#klima", "#kutina"]
    ispuni(projekt, "reel_v2", m)
    r = run(projekt, env=env, code=0)   # upozorenja ne zaustavljaju
    out = r.stdout
    assert "prvi redak ima 140 znakova" in out
    assert "broj 300 se ne čuje u videu" in out
    assert "broj 26" not in out                       # 26 je u govoru
    assert "isti opis na više mreža" in out
    assert "#sunčaniput — hashtag s kvačicama" in out


def test_isjecci_i_odabir(projekt, env):
    r = run(projekt, "isjecci", env=env, code=1)
    d = load(projekt / "objava.json")
    assert set(d["videi"]) == {"K1", "K2"}
    assert d["videi"]["K1"]["naslov_isjecka"] == "Struja i klima"
    assert "zašto je dobar: Jasan broj." in r.stdout
    ispuni(projekt, "K1")
    r = run(projekt, "K1", env=env, code=0)
    assert (projekt / "isjecci" / "K1_savjet.objava.txt").exists()
    assert not (projekt / "isjecci" / "K2_savjet.objava.txt").exists()
    r = run(projekt, "K3", env=env, code=1)
    assert "K3 još nije renderiran" in r.stderr
    r = run(projekt, "K9", env=env, code=1)
    assert "nema isječka K9" in r.stderr


def test_mreze_po_formatu_i_izboru(projekt, env):
    save(projekt / "project.json", {"format": "16:9"})
    run(projekt, env=env, code=1)
    assert load(projekt / "objava.json")["videi"]["reel_v2"]["mreze_popis"] == ["youtube"]
    run(projekt, "--mreze", "ig, yt", env=env, code=1)
    e = load(projekt / "objava.json")["videi"]["reel_v2"]
    assert e["mreze_popis"] == ["instagram", "youtube"]
    run(projekt, "--mreze", "facebook", env=env, code=1)


def test_serija_potpis_i_stalni_hashtagovi(projekt, env):
    run("serija", "SF klima", "--hashtagovi", "#sfklima, kutina", "--potpis", "SF klima Kutina · montaža i servis",
        "--napomena", "ti-forma, poziv na poruku za ponudu", env=env)
    run("serija", "SF klima", "--mreza", "youtube", "--potpis", "Ponuda: poruka na Instagramu @sfklima", env=env)
    r = run("serija", env=env)
    assert "#sfklima #kutina" in r.stdout and "ti-forma" in r.stdout
    r = run("serija", "Druga", "--hashtagovi", "#a,#b,#c,#d", env=env, code=1)
    assert "najviše 3 stalna" in r.stderr
    r = run(projekt, "--serija", "sf KLIMA", env=env, code=1)
    assert "stalni hashtagovi #sfklima #kutina → dodaj još najviše 3" in r.stdout
    assert "napomena serije: ti-forma" in r.stdout
    ispuni(projekt, "reel_v2")
    r = run(projekt, env=env, code=0)   # 3 vlastita + 2 stalna = 5: dopušteno na IG i TikToku
    assert "dopušta najviše" not in r.stdout
    d = load(projekt / "objava.json")
    assert d["serija"] == "SF klima"
    m = json.loads(json.dumps(DOBRO))
    m["instagram"]["hashtagovi"].append("#cetvrti")
    ispuni(projekt, "reel_v2", m)
    r = run(projekt, env=env, code=1)
    assert "6 hashtagova — Instagram dopušta najviše 5 (sa stalnima iz serije)" in r.stdout
    ispuni(projekt, "reel_v2")
    run(projekt, env=env, code=0)
    txt = (projekt / "reel_v2.objava.txt").read_text(encoding="utf-8-sig")
    assert "SF klima Kutina · montaža i servis\n\n#klima #ustedastruje #ljeto #sfklima #kutina" in txt
    assert "Ponuda: poruka na Instagramu @sfklima" in txt   # YouTube ima svoj potpis
    run(projekt, "--serija", "Nepostojeća", env=env, code=1)


def test_promjena_govora_upozori(projekt, env):
    run(projekt, env=env, code=1)
    ispuni(projekt, "reel_v2")
    run(projekt, env=env, code=0)
    (projekt / "reel_v2.srt").write_text(SRT.replace("frižider", "bojler"), encoding="utf-8-sig")
    r = run(projekt, env=env, code=0)
    assert "govor u videu se promijenio" in r.stdout


def test_slozi_ne_duplicira_hashtagove():
    e = {"mreze": {"instagram": {"opis": "Tekst #Klima", "hashtagovi": ["klima", "#Ljeto", "#ljeto"]}}}
    _, full, tags = O.slozi(e, "instagram", {"hashtagovi": ["#ljeto", "#sf"], "potpis": {"sve": "Potpis"}})
    assert full == "Tekst #Klima\n\nPotpis\n\n#Ljeto #sf"
    assert tags == ["#Klima", "#Ljeto", "#sf"]
    assert O.provjeri_hashtagove(["#123", "#ok_1", "#čćž", "#a-b"]) == [
        "hashtag „#123” je samo broj — mreže ga ne prikazuju kao hashtag",
        "hashtag „#a-b” smije imati samo slova, brojke i _ (bez razmaka, crtica i točaka)"]


def test_hrvatska_mnozina_i_redni_brojevi():
    assert [O.hashtaga(n) for n in (1, 2, 5, 11, 22)] == ["1 hashtag", "2 hashtaga", "5 hashtagova",
                                                         "11 hashtagova", "22 hashtaga"]
    assert {"1", "2", "300"} <= O._brojevi_u_govoru("Prvi korak… Drugi korak, tristo eura")
