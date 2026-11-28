"""Nova pozadina iza osobe (M5.7b): efekt `pozadina` (zamućena, boja, slika, video) i HTML grafika iza osobe
(`--iza`); titlovi i natpisi ostaju ispred.

Bez modela: slaganje uz nacrtanu masku, čišćenje ruba, umetanje na točne sličice (lažni maskirač), dvije faze
(pozadina pa tekst iza osobe). S pravim modelom (SHOFE_OSOBA_TEST=1 u CI-ju) render bez HyperFramesa; s pravim
HyperFramesom (SHOFE_GRAFIKA_TEST=1) predložak iza osobe."""
import json
import os
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

import grafika  # noqa: E402
import osoba  # noqa: E402
from test_osoba import LazniMaskirac, audio_md5, frames, maska_osobe, model_spreman, run  # noqa: E402

FPS = 30
PLAVA = (0x1E, 0x3A, 0x5F)


# ---------------------------------------------------------------- bez modela
def test_parametri_i_pokrivanje(tmp_path):
    P = osoba.pozadina_parametri
    assert P({})["vrsta"] == "zamuti" and P({})["zamuti"] == osoba.ZAMUTI
    assert P({"boja": "#102030"}) == {"vrsta": "boja", "boja": "#102030", "datoteka": None, "zamuti": 0.0}
    p = P({"vrsta": "slika", "slika": "poz/ured.jpg", "zamuti": 0.3}, tmp_path)
    assert p["datoteka"] == tmp_path / "poz" / "ured.jpg" and p["zamuti"] == 0.3
    assert P({"video": "more.mp4"})["vrsta"] == "video"
    with pytest.raises(osoba.Greska):
        osoba.provjeri_datoteku(p)                                     # slika ne postoji
    # slika bilo koje veličine pokrije cijeli kadar (bez crnih traka), po sredini
    img = np.zeros((100, 400, 3), np.uint8)
    img[:, 190:210] = 255
    c = osoba._pokrij(img, 90, 160)
    assert c.shape == (160, 90, 3) and c[:, 45].min() > 200 and c[:, 0].max() < 30
    b = osoba._boja_slika("#1E3A5F", 20, 40)
    assert b.shape == (40, 20, 3) and b[0, 0, 2] > b[-1, 0, 2]        # gore svjetlije, dolje tamnije
    assert abs(int(b[20, 5, 2]) - 0x5F) < 12


def test_zamucenje_bez_osobe():
    """Zamućena pozadina ne uzima boju osobe: oko crvene osobe na plavoj pozadini zamućenje ostaje plavo."""
    W, H = 200, 300
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[:] = (20, 40, 220)
    m = maska_osobe(W, H, vrh=0.3, glava_r=0.15)
    rgb[m > 0.5] = (230, 20, 20)
    z = osoba.zamuti_bez_osobe(rgb, m, 12)
    oko = (m < 0.5) & (osoba._gauss(m, 6) > 0.2)                      # pozadina tik uz osobu
    assert oko.sum() > 100
    assert z[oko][:, 0].mean() < 50 and z[oko][:, 2].mean() > 180
    obicno = osoba.zamuti(rgb, 12)
    assert obicno[oko][:, 0].mean() > z[oko][:, 0].mean() + 20        # obično zamućenje bi „procurilo"


def test_slaganje_i_cisti_rub():
    W, H = 200, 300
    m = np.zeros((H, W), np.float32)
    m[:, 100:] = 1.0
    m[:, 95:100] = 0.5                                                 # mekan rub (kosa)
    sivo = np.array([200, 200, 200], np.float32)
    crveno = np.array([255, 0, 0], np.float32)
    fr = (crveno * m[..., None] + sivo * (1 - m[..., None])).astype(np.uint8)
    bg = np.zeros_like(fr)
    bg[:] = PLAVA
    out = osoba.slozi_pozadinu(fr, m, bg)
    assert np.abs(out[:, 10:80].astype(int) - PLAVA).max() <= 2       # stara pozadina zamijenjena
    assert np.abs(out[:, 130:].astype(int) - fr[:, 130:]).max() <= 2  # osoba ista
    rub = out[:, 95:100].astype(int)
    assert rub[..., 1].mean() < 70                                    # rub ne nosi sivu staru pozadinu
    assert (osoba.slozi_pozadinu(fr, m, bg, a=0.0) == fr).all()
    pola = osoba.slozi_pozadinu(fr, m, bg, a=0.5)
    assert abs(int(pola[5, 10, 0]) - (200 + PLAVA[0]) // 2) <= 3      # pretapanje
    # bez osobe: maska prazna → efekt se ne radi
    assert osoba.bez_osobe(np.zeros((3, 10, 10), np.float32)) and not osoba.bez_osobe(m[None])


def test_prozirnost_pretapanje():
    g = {"n": 60, "k0": 30, "do_kraja": False}
    assert osoba.prozirnost_pozadine(0, g, FPS) < 0.3 and osoba.prozirnost_pozadine(30, g, FPS) == 1.0
    assert osoba.prozirnost_pozadine(59, g, FPS) < 0.3
    g0 = {"n": 60, "k0": 0, "do_kraja": True}                         # cijeli video: bez pretapanja
    assert osoba.prozirnost_pozadine(0, g0, FPS) == 1.0 and osoba.prozirnost_pozadine(59, g0, FPS) == 1.0


ASS = """[Script Info]
PlayResX: 200
PlayResY: 300

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, \
StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: D,DejaVu Sans,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,4,0,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,D,,0,0,0,,ČĆŠ
"""


def test_titlovi_ostaju_ispred(tmp_path):
    (tmp_path / "captions.ass").write_text(ASS, encoding="utf-8")
    al = list(osoba.titlovi_alfa(tmp_path, 0.9, 6, 200, 300, FPS))
    assert len(al) == 6
    assert al[0].max() == 0 and al[5].max() > 0.9                     # 0,9 s nema titla, 1,0667 s ima
    ys = np.nonzero(al[5].max(axis=1) > 0.5)[0]
    assert ys.min() > 150                                             # titl dolje
    fr = np.full((300, 200, 3), 77, np.uint8)
    out = np.zeros_like(fr)
    v = osoba.vrati_titlove(out, fr, al[5])
    assert (v[al[5] > 0.99] == 77).all() and (v[al[5] == 0] == 0).all()
    assert list(osoba.titlovi_alfa(tmp_path / "nema", 0, 2, 200, 300, FPS)) == []
    assert osoba.vrati_titlove(out, fr, None) is out


# ---------------------------------------------------------------- projekt
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_efekti_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("pozadina čž"), SCRIPTS)
    run("render.py", proj, "--izlaz", "ref.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=1", "-frames:v", "1",
                    str(proj / "ured.jpg")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x00FF00:s=160x90:r=30:d=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(proj / "kratki.mp4")], check=True)
    return proj


def test_efekti_dodaj_pozadina(projekt):
    def ne(*args, poruka):
        r = run("efekti.py", projekt, "dodaj", *args, ok=False)
        assert r.returncode != 0 and poruka in r.stderr, r.stderr

    ne("pozadina", "1-3", "--boja", "#123456", "--slika", "ured.jpg", poruka="jedna pozadina")
    ne("pozadina", "1-3", "--zamuti", "2", poruka="0 (oštro)")
    ne("pozadina", "1-3", "--boja", "#123456", "--zamuti", "0.3", poruka="ne zamućuje")
    ne("pozadina", "1-3", "--boja", "plava", poruka="#RRGGBB")
    ne("pozadina", "1-3", "--slika", "nema.jpg", poruka="ne postoji")
    ne("pozadina", "1-3", "--slika", "kratki.mp4", poruka=".jpg")
    ne("pozadina", "1-3", "--tekst", "A", poruka="--tekst")
    ne("trzaj", "1-2", "--slika", "ured.jpg", poruka="pozadina")
    ne("trzaj", "1-2", "--boja", "#123456", poruka="--boja")
    ne("trzaj", "1-2", "--iza", poruka="--iza")
    ne("mobitel", "1-3", "--varijable", '{"naslov": "A"}', "--iza", poruka="iza osobe")
    out = run("efekti.py", projekt, "dodaj", "zamuti", "1-3").stdout          # alias, zadano zamućena
    assert "pozadina (zamućena)" in out
    ne("pozadina", "2-4", "--boja", "#123456", poruka="već je")                # dvije pozadine jedna preko druge
    run("efekti.py", projekt, "dodaj", "pozadina", "2-4", "--slika", str(projekt / "ured.jpg"), "--zamuti",
        "--zamijeni")
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    e = [x for x in edit["efekti"] if x["tip"] == "pozadina"]
    assert len(e) == 1 and e[0]["parametri"] == {"vrsta": "slika", "slika": "ured.jpg", "zamuti": 0.5}
    assert "slika ured.jpg, zamućenje 0.5" in run("efekti.py", projekt, "popis").stdout
    run("efekti.py", projekt, "makni", e[0]["id"])
    r = run("efekti.py", projekt, "dodaj", "kartica", "1-3", "--varijable", '{"naslov": "Čisto"}', "--iza")
    assert "iza osobe" in r.stdout
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    k = next(x for x in edit["efekti"] if x["tip"] == "grafika")
    assert k["parametri"]["iza"] is True
    assert "iza osobe" in run("efekti.py", projekt, "popis").stdout
    run("efekti.py", projekt, "makni", "sve")


def _gx(tip, p, s=1.0, n=60):
    return {"id": "E1", "tip": tip, "s": s, "s0": s, "k0": int(round(s * FPS)), "n": n, "p": p, "fps": 30.0}


def test_umetanje_pozadine(projekt, monkeypatch, tmp_path):
    vid = tmp_path / "v.mp4"
    shutil.copy2(projekt / "ref.mp4", vid)
    monkeypatch.setattr(osoba, "Maskirac", LazniMaskirac)
    LazniMaskirac.poziva = 0
    gx = [_gx("pozadina", {"vrsta": "boja", "boja": "#1E3A5F"})]
    lines = grafika.umetni(tmp_path, gx, vid, 540, 960, FPS, ispis=False)
    assert "Grafika: 1" in lines[0] and "renderirao 1" in lines[0]
    a, b = frames(projekt / "ref.mp4"), frames(vid)
    assert len(a) == len(b)
    poz = (slice(5, 40), slice(3, 25))                                  # gore lijevo: pozadina
    lice = (slice(int(240 * 0.30), int(240 * 0.40)), slice(57, 78))
    for i in range(40, 84):                                             # iza pretapanja
        assert np.abs(b[i][poz] - PLAVA).mean() < 12, i
        assert np.abs(b[i][lice] - a[i][lice]).mean() < 4, i
    assert np.abs(b[31][poz] - PLAVA).mean() > 20                       # prva sličica: tek počinje pretapanje
    izvan = [i for i in range(len(a)) if not 30 <= i < 90]
    assert max(float(np.abs(a[i] - b[i]).mean()) for i in izvan) < 1.0
    assert audio_md5(vid) == audio_md5(projekt / "ref.mp4")
    # predmemorija
    shutil.copy2(projekt / "ref.mp4", vid)
    LazniMaskirac.poziva = 0
    assert "renderirao 0" in grafika.umetni(tmp_path, gx, vid, 540, 960, FPS, ispis=False)[0]
    assert LazniMaskirac.poziva == 0
    # pozadina + tekst iza osobe u istom dijelu: tekst stoji na novoj pozadini (dvije faze)
    shutil.copy2(projekt / "ref.mp4", vid)
    gx2 = gx + [dict(_gx("iza", {"tekst": "SUNČANO", "polozaj": "gore"}, s=1.2, n=40), id="E2")]
    lines = grafika.umetni(tmp_path, gx2, vid, 540, 960, FPS, ispis=False)
    assert "Grafika: 2" in lines[0]
    c = frames(vid)
    pojas = (slice(int(240 * 0.12), int(240 * 0.20)), slice(5, 130))
    for i in range(50, 70):
        bijelo = (c[i][pojas].min(axis=-1) > 200).mean()
        plavo = (np.abs(c[i][pojas] - PLAVA).max(axis=-1) < 25).mean()
        assert bijelo > 0.05 and plavo > 0.2, (i, bijelo, plavo)          # slova na plavoj pozadini


def test_slika_video_i_bez_osobe(projekt, monkeypatch, tmp_path):
    vid = projekt / "v_poz.mp4"                                         # unutar projekta (slika/video relativno)
    monkeypatch.setattr(osoba, "Maskirac", LazniMaskirac)
    for p, boja in (({"vrsta": "video", "video": "kratki.mp4"}, (0, 255, 0)),          # 0,5 s videa u krug
                    ({"vrsta": "slika", "slika": "ured.jpg"}, None)):
        shutil.copy2(projekt / "ref.mp4", vid)
        lines = grafika.umetni(projekt, [_gx("pozadina", p)], vid, 540, 960, FPS, ispis=False)
        assert "Grafika: 1" in lines[0], lines
        b, a = frames(vid), frames(projekt / "ref.mp4")
        poz = (slice(5, 40), slice(3, 25))
        for i in (45, 60, 80):
            if boja:
                assert np.abs(b[i][poz] - boja).mean() < 25
            else:
                assert np.abs(b[i][poz] - a[i][poz]).mean() > 20
    # maska prazna (nema osobe): napomena, video isti
    class Prazna(LazniMaskirac):
        def __call__(self, rgb):
            return np.zeros(rgb.shape[:2], np.float32)
    monkeypatch.setattr(osoba, "Maskirac", Prazna)
    shutil.copy2(projekt / "ref.mp4", vid)
    lines = grafika.umetni(projekt, [_gx("pozadina", {"vrsta": "boja", "boja": "#000001"}, s=2.0)], vid, 540, 960,
                           FPS, ispis=False)
    assert any("ne vidi osobu" in x for x in lines)
    assert float(np.abs(frames(vid)[70] - frames(projekt / "ref.mp4")[70]).mean()) < 1.0
    # slika ne postoji: napomena, ne pada
    lines = grafika.umetni(projekt, [_gx("pozadina", {"vrsta": "slika", "slika": "nema.jpg"})], vid, 540, 960,
                           FPS, ispis=False)
    assert any("ne postoji" in x for x in lines)


def test_kadar_pozadina(projekt, monkeypatch, tmp_path):
    monkeypatch.setattr(osoba, "Maskirac", LazniMaskirac)
    from PIL import Image
    png = tmp_path / "k.png"
    rgb = np.asarray(frames(projekt / "ref.mp4", 270, 480)[60], np.uint8)
    Image.fromarray(rgb).save(png)
    g = _gx("pozadina", {"vrsta": "boja", "boja": "#1E3A5F"})
    assert grafika.na_sliku(png, ("osoba", g), 30, projekt)
    out = np.asarray(Image.open(png).convert("RGB")).astype(int)
    assert np.abs(out[10:60, 5:40] - PLAVA).mean() < 12
    lice = (slice(int(480 * 0.30), int(480 * 0.40)), slice(115, 155))
    assert np.abs(out[lice] - rgb[lice]).mean() < 4


# ---------------------------------------------------------------- pravi model / HyperFrames
def test_pravi_model_render(projekt):
    """Pravi MODNet na nacrtanoj osobi ne nađe čovjeka: render ne pada, napomena da nema osobe, video isti;
    zamućena pozadina na pravoj slici bez HyperFramesa; --kadar radi."""
    model_spreman()
    run("efekti.py", projekt, "dodaj", "pozadina", "1-3")
    env = dict(os.environ, SHOFE_HYPERFRAMES=str(projekt / "nema_hf"))
    out = run("render.py", projekt, "--izlaz", "poz.mp4", env=env).stdout
    assert "grafika nije u videu" not in out
    assert "ne vidi osobu" in out or "Grafika: 1" in out
    a, b = frames(projekt / "ref.mp4"), frames(projekt / "poz.mp4")
    assert len(a) == len(b) and max(float(np.abs(a[i] - b[i]).mean()) for i in range(28)) < 1.0
    assert run("render.py", projekt, "--kadar", "2", env=env).returncode == 0
    run("efekti.py", projekt, "makni", "sve")


def test_html_iza_osobe(projekt, monkeypatch, tmp_path):
    """Pravi HyperFrames: predložak iza osobe — grafika se vidi oko osobe, lice ostaje ispred."""
    from test_predlosci_grafika import hf_spreman
    hf_spreman()
    monkeypatch.setattr(osoba, "Maskirac", LazniMaskirac)
    vid = tmp_path / "v.mp4"
    shutil.copy2(projekt / "ref.mp4", vid)
    g = _gx("grafika", {"predlozak": "recenica", "iza": True,
                        "varijable": {"tekst": "ČISTA KLIMA ZDRAV DOM", "polozaj": "gore"}})
    g["stil"] = grafika.boje_stila(None)
    lines = grafika.umetni(tmp_path, [g], vid, 540, 960, FPS, ispis=False)
    assert "Grafika: 1" in lines[0] and not any("preko osobe" in x for x in lines), lines
    a, b = frames(projekt / "ref.mp4"), frames(vid)
    lice = (slice(int(240 * 0.30), int(240 * 0.40)), slice(57, 78))
    assert max(float(np.abs(a[i][lice] - b[i][lice]).mean()) for i in range(30, 90)) < 4
    assert max(float(np.abs(a[i] - b[i]).mean()) for i in range(40, 80)) > 2     # grafika se vidi
    assert list(tmp_path.glob("_tmp/grafika/grafika_izah_*.mp4"))


def test_maska_iz_slike_bez_titlova(projekt, monkeypatch, tmp_path):
    """Render zapiše sliku bez titlova (cisto) kad ima efekata s maskom; maska se računa iz nje (vrijeme s0)."""
    import efekti
    assert grafika.treba_cisto([{"tip": "pozadina", "p": {}}]) and grafika.treba_cisto([{"tip": "iza", "p": {}}])
    assert grafika.treba_cisto([{"tip": "grafika", "p": {"iza": True}}])
    assert not grafika.treba_cisto([{"tip": "grafika", "p": {"iza": True, "pozadina": True}}])
    assert not grafika.treba_cisto([{"tip": "trzaj", "p": {}}]) and efekti.TIPOVI["pozadina"]["skupina"] == "grafika"
    vid = tmp_path / "v.mp4"
    shutil.copy2(projekt / "ref.mp4", vid)
    cisto = tmp_path / "cisto.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x102030:s=540x960:r=30:d=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cisto)], check=True)
    vidjeno = []

    class Biljezi(LazniMaskirac):
        def __call__(self, rgb):
            vidjeno.append(float(rgb.mean()))
            return super().__call__(rgb)
    monkeypatch.setattr(osoba, "Maskirac", Biljezi)
    lines = grafika.umetni(tmp_path, [_gx("pozadina", {"vrsta": "boja"})], vid, 540, 960, FPS, ispis=False,
                           cisto=cisto)
    assert "Grafika: 1" in lines[0]
    assert len(vidjeno) == 60 and max(abs(v - (0x10 + 0x20 + 0x30) / 3) for v in vidjeno) < 3


def test_render_pise_i_brise_cisto(projekt):
    """Pravi render s efektom pozadina: cisto.mp4 nastane za umetanje i obriše se poslije (nacrtana osoba ili
    bez modela: napomena, render ne pada)."""
    run("efekti.py", projekt, "dodaj", "pozadina", "1-3", "--boja", "#1E3A5F")
    env = dict(os.environ, SHOFE_HYPERFRAMES=str(projekt / "nema_hf"))
    try:
        r = run("render.py", projekt, "--izlaz", "c.mp4", env=env, ok=False)
        assert r.returncode == 0, r.stderr
        assert not (projekt / "_tmp" / "grafika" / "cisto.mp4").exists()
        a, b = frames(projekt / "ref.mp4"), frames(projekt / "c.mp4")
        assert len(a) == len(b)
    finally:
        run("efekti.py", projekt, "makni", "sve")
