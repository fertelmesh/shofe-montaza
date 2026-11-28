"""HTML grafika (M5.4): HyperFrames renderira odsječak grafike (proziran ili s pozadinskim videom), ffmpeg ga
umeće natrag u gotov video na točno te sličice; zvuk ostaje isti.

Testovi s pravim HyperFramesom traže Node.js 22+ i `python grafika.py instaliraj` (SHOFE_HYPERFRAMES = mapa
instalacije); bez toga se preskoče, osim kad je SHOFE_GRAFIKA_TEST=1 (CI) — tada moraju proći."""
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

import grafika  # noqa: E402

FPS = 30


def run(script, *args, ok=True, env=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if ok:
        assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r


def hf_spreman():
    ok, msg = grafika.stanje()
    if not ok and os.environ.get("SHOFE_GRAFIKA_TEST"):
        pytest.fail(f"SHOFE_GRAFIKA_TEST=1, a HyperFrames nije spreman: {msg}")
    if not ok:
        pytest.skip(f"HyperFrames nije spreman: {msg}")


# ---------------------------------------------------------------- bez rendera
def test_fps_i_omotac():
    assert grafika.fps_arg(30) == "30" and grafika.fps_arg(25.0) == "25"
    assert grafika.fps_arg(29.97002997) == "30000/1001"
    page = grafika.omotaj('<div class="x">Čćšžđ</div>', 1080, 1920, 30, 75, False,
                          {"naslov": "a </script><b>", "broj": "200"})
    assert 'data-composition-id="shofe"' in page and 'data-width="1080"' in page and 'data-height="1920"' in page
    assert 'data-duration="2.5"' in page and 'data-fps="30"' in page
    assert "<video" not in page and "Čćšžđ" in page
    assert "Montserrat-Black.ttf" in page and "Anton-Regular.ttf" in page
    js = page.split("window.SHOFE = ", 1)[1].split(";</script>", 1)[0]
    assert "</script>" not in js
    data = json.loads(js.replace("<\\/", "</"))
    assert data["varijable"]["naslov"] == "a </script><b>" and data["trajanje"] == 2.5 and data["sirina"] == 1080
    page2 = grafika.omotaj("<div></div>", 540, 960, 25, 50, True, {})
    assert 'id="pozadina"' in page2 and 'src="pozadina.mp4"' in page2 and 'data-duration="2"' in page2


def test_html_iz_datoteke_ili_teksta(tmp_path):
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "k.html").write_text("<div>k</div>", encoding="utf-8")
    (tmp_path / "g" / "logo.png").write_bytes(b"\x89PNG")
    t, mapa = grafika.ucitaj_html("g/k.html", tmp_path)
    assert t == "<div>k</div>" and mapa == tmp_path / "g"
    assert [n for n, _ in grafika._datoteke_uz(mapa)] == ["logo.png"]     # slike idu uz HTML, sam HTML ne
    assert grafika.ucitaj_html("<p>x</p>", tmp_path) == ("<p>x</p>", None)
    with pytest.raises(grafika.Greska):
        grafika.ucitaj_html("nema.html", tmp_path)
    with pytest.raises(grafika.Greska):
        grafika.ucitaj_html("", tmp_path)


def test_plan_brzina_spica_i_kraj():
    fx = [{"id": "E1", "tip": "grafika", "s": 1.0, "e": 3.0, "p": {}},
          {"id": "E2", "tip": "trzaj", "s": 1.0, "e": 2.0, "p": {}},
          {"id": "E3", "tip": "grafika", "s": 4.0, "e": 6.0, "p": {}}]
    gx, notes = grafika.plan(fx, 1.25, FPS)
    assert [g["id"] for g in gx] == ["E1", "E3"] and not notes
    assert gx[0]["k0"] == 24 and gx[0]["n"] == 48 and abs(gx[0]["s"] - 0.8) < 1e-9
    # uvodna špica od 2 s na 2,0 s gotovog videa: E3 je iza nje (pomak), E1 prelazi preko → skraćena
    sp = {"at": 2.0, "uvod": 2.0, "odjava": 0.0, "glavni": 5.0, "ukupno": 7.0}
    gx, notes = grafika.plan(fx, 1.0, FPS, sp)
    assert gx[0]["s"] == 1.0 and gx[0]["n"] == 30 and any("E1" in n and "špica" in n for n in notes)
    assert gx[1]["s"] == 6.0 and gx[1]["n"] == 60
    # kraj videa
    gx, _ = grafika.plan(fx, 1.0, FPS, None, ukupno=5.0)
    assert gx[1]["n"] == 30


def test_graf_slaze_komade_po_vremenu():
    gp = [({"id": "E1", "s": 1.0, "n": 60}, Path("a.mov")), ({"id": "E2", "s": 4.5, "n": 30}, Path("b.mp4"))]
    g = grafika.graf(gp, FPS, 540, 960, 540, 960)
    txt = ";".join(g)
    assert txt.count("overlay=") == 2 and "scale=" not in txt and txt.endswith("format=yuv420p[v]")
    assert "[1:v]setpts=PTS-STARTPTS+0.9917/TB" in txt and "[2:v]setpts=PTS-STARTPTS+4.4917/TB" in txt
    assert "between(t,0.9917,2.9916)" in txt
    g2 = grafika.graf(gp, FPS, 270, 480, 540, 960)       # brzi pregled (pola veličine)
    assert ";".join(g2).count("scale=270:480") == 2


def test_stanje_bez_instalacije(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOFE_HYPERFRAMES", str(tmp_path / "nema"))
    ok, msg = grafika.stanje()
    assert not ok and ("HyperFrames" in msg or "Node.js" in msg)


# ---------------------------------------------------------------- projekt (bez HyperFramesa)
@pytest.fixture(scope="module")
def projekt(tmp_path_factory):
    pytest.importorskip("cv2")
    import make_efekti_klip as MK
    proj = MK.make_projekt(tmp_path_factory.mktemp("grafika čž"), SCRIPTS)
    edit = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    edit["titlovi"] = True
    (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
    (proj / "grafika").mkdir()
    (proj / "grafika" / "kartica.html").write_text(grafika.PROBA, encoding="utf-8")
    (proj / "grafika" / "mobitel.html").write_text(
        "<style>#shofe{background:#FF7A00}#pozadina{transform-origin:50% 45%;animation:m .4s ease-out both}"
        "@keyframes m{to{transform:scale(.6)}}</style>", encoding="utf-8")
    run("render.py", proj, "--izlaz", "ref.mp4")
    return proj


def frames(path, w=135, h=240):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3).astype(np.int16)


def audio_md5(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
                       capture_output=True, text=True)
    return r.stdout.strip()


def razlike(a, b):
    return [float(np.abs(a[i] - b[i]).mean()) for i in range(min(len(a), len(b)))]


def test_efekti_dodaj_grafiku(projekt):
    r = run("efekti.py", projekt, "dodaj", "grafika", "1-3", ok=False)
    assert r.returncode != 0 and "--html" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "grafika", "1-3", "--html", "grafika/nema.html", ok=False)
    assert r.returncode != 0 and "ne postoji" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "grafika", "1-3", "--html", "grafika/kartica.html", "--varijable",
            "{broj: 2}", ok=False)
    assert r.returncode != 0 and "JSON" in r.stderr
    r = run("efekti.py", projekt, "dodaj", "trzaj", "1-2", "--html", "x.html", ok=False)
    assert r.returncode != 0 and "grafika" in r.stderr
    run("efekti.py", projekt, "dodaj", "grafika", "1-3", "--html", str(projekt / "grafika" / "kartica.html"),
        "--varijable", '{"broj": "350"}')
    run("efekti.py", projekt, "dodaj", "kartica", "2-2.5", "--html", "<div>ruka</div>")   # preko prve: smije
    run("efekti.py", projekt, "dodaj", "grafika", "4.5-6.5", "--html", "grafika/mobitel.html", "--pozadina")
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    g = [e for e in edit["efekti"] if e["tip"] == "grafika"]
    assert len(g) == 3
    assert g[0]["parametri"] == {"html": "grafika/kartica.html", "varijable": {"broj": "350"}}   # relativno
    assert g[2]["parametri"] == {"html": "grafika/mobitel.html", "pozadina": True}
    popis = run("efekti.py", projekt, "popis").stdout
    assert "grafika/kartica.html" in popis and "HTML u edit.json" in popis and "s pozadinom" in popis
    run("efekti.py", projekt, "makni", g[1]["id"])


def test_umetanje_na_tocne_slicice(projekt, monkeypatch, tmp_path):
    """Bez HyperFramesa: umjesto njega ffmpeg napravi prozirni komad (crveni kvadrat, ProRes 4444) — provjera
    da ga zadnji prolaz stavi točno na sličice grafike, a sve ostalo (i zvuk) ostane isto."""
    import shutil
    vid = tmp_path / "v.mp4"
    shutil.copy2(projekt / "ref.mp4", vid)

    def lazni(proj, g, W, H, fps, video=None, ispis=False):
        f = tmp_path / f"{g['id']}.mov"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"color=c=black@0.0:s={W}x{H}:r={fps},format=rgba",
                        "-vf", "drawbox=x=iw/4:y=ih/4:w=iw/2:h=ih/4:color=red@1:t=fill:replace=1",
                        "-frames:v", str(g["n"]), "-c:v", "prores_ks", "-profile:v", "4444",
                        "-pix_fmt", "yuva444p10le", str(f)], check=True)
        return f, True

    monkeypatch.setattr(grafika, "pripremi", lazni)
    gx = [{"id": "E1", "s": 1.0, "k0": 30, "n": 45, "p": {}}, {"id": "E2", "s": 5.0, "k0": 150, "n": 10, "p": {}}]
    lines = grafika.umetni(tmp_path, gx, vid, 540, 960, FPS, ispis=False)
    assert "Grafika: 2" in lines[0]
    a, b = frames(projekt / "ref.mp4"), frames(vid)
    assert len(a) == len(b)
    d = razlike(a, b)
    inside = set(range(30, 75)) | set(range(150, 160))
    assert all(d[i] > 10 for i in inside), [round(d[i], 1) for i in sorted(inside)]
    assert max(d[i] for i in range(len(d)) if i not in inside) < 1.0
    assert b[50][100, 67, 0] > 200 and b[50][100, 67, 1] < 60                # crveni kvadrat u sredini
    assert audio_md5(vid) == audio_md5(projekt / "ref.mp4")                  # zvuk se samo kopira
    m = json.loads((tmp_path / "_tmp" / "grafika" / "zadnje.json").read_text(encoding="utf-8"))
    assert [x["id"] for x in m["grafike"]] == ["E1", "E2"]


def test_render_bez_hyperframesa_ne_pada(projekt, tmp_path):
    env = dict(os.environ, SHOFE_HYPERFRAMES=str(tmp_path / "nema"))
    out = run("render.py", projekt, "--izlaz", "bez.mp4", env=env).stdout
    assert "grafika nije u videu" in out and (projekt / "bez.mp4").exists()


# ---------------------------------------------------------------- pravi HyperFrames
def test_pravi_render_grafike(projekt):
    hf_spreman()
    out = run("render.py", projekt, "--izlaz", "g.mp4").stdout
    assert "Grafika: 2" in out and "renderirao 2" in out
    ref, g = frames(projekt / "ref.mp4"), frames(projekt / "g.mp4")
    assert len(ref) == len(g)
    d = razlike(ref, g)
    kart, mob = range(30, 90), range(135, 195)          # 1–3 s i 4,5–6,5 s
    assert max(d[i] for i in range(len(d)) if i not in kart and i not in mob) < 1.0
    assert all(d[i] > 3 for i in range(33, 90)), [round(d[i], 1) for i in kart]      # kartica uđe i stoji
    assert all(d[i] > 15 for i in range(140, 195))                                    # video se smanji
    # kartica: bijela ploha u gornjoj trećini; mobitel: narančasti rub oko smanjenog videa
    band = g[60][int(240 * 0.30):int(240 * 0.40), 15:120]
    assert (band.min(axis=2) > 200).mean() > 0.4                              # bijela kartica
    assert (ref[60][int(240 * 0.30):int(240 * 0.40), 15:120].min(axis=2) > 200).mean() < 0.05
    assert g[180][5, 5, 0] > 220 and 90 < g[180][5, 5, 1] < 150 and g[180][5, 5, 2] < 40
    assert audio_md5(projekt / "g.mp4") == audio_md5(projekt / "ref.mp4")
    # drugi render: grafike iz predmemorije, isti video
    out2 = run("render.py", projekt, "--izlaz", "g2.mp4").stdout
    assert "renderirao 0, 2 iz predmemorije" in out2
    assert max(razlike(g, frames(projekt / "g2.mp4"))) < 0.5
    # slika usred kartice = video
    edit = json.loads((projekt / "edit.json").read_text(encoding="utf-8"))
    e1 = next(e["id"] for e in edit["efekti"] if not e["parametri"].get("pozadina"))
    r = run("efekti.py", projekt, "pokazi", e1)
    assert (projekt / f"efekt_{e1}.png").exists()
    run("render.py", projekt, "--kadar", "2.0")
    from PIL import Image
    png = np.asarray(Image.open(projekt / "kadar_1_2s.png").convert("RGB").resize((135, 240))).astype(np.int16)
    assert np.abs(png - g[60]).mean() < 6, r.stdout
