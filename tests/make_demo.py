"""Demo za pregled prekretnice M1 → demo/ (videi ≤ 8 MB, slike).

  python tests/make_demo.py              sve
  python tests/make_demo.py --samo karta samo snimku karte videa

Što nastaje:
  demo/M1_reel.mp4         probni klipovi (vodoravni + okomiti) → gotov reel: izrezan prekinut pokušaj i „eee",
                           hook, naglasci, glazba, stil suncani
  demo/M1_stilovi.mp4      isti početak u svih 5 stilova, jedan za drugim
  demo/M1_karta_videa.mp4  snimka zaslona pregled.html na probnom razgovoru (3 glasa, 55 s): klikovi, zum, pretraga
  demo/M1_kadrovi.png      provjera izgleda (render.py --kadar)
  demo/M1_karta_videa.png  slika stranice karte videa

Treba ffmpeg; za kartu videa Playwright + Chromium; za govornike prvi put internet (modeli ~36 MB),
inače se govornici uzmu iz poznatih oznaka probnog razgovora.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FONTS = ROOT / "shofe-montaza" / "fonts"
FIX = ROOT / "tests" / "fixtures"
DEMO = ROOT / "demo"
MAX_MB = 8.0
STILOVI = ["suncani", "podcast", "udarno", "cisto", "kino"]


def run(script, *args, check=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"{script} pao:\n{r.stdout}\n{r.stderr}")
    return r


def ff(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, args)], check=True, cwd=cwd)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def mb(path):
    return path.stat().st_size / 1e6


def provjeri_velicinu(path):
    assert mb(path) <= MAX_MB, f"{path.name} ima {mb(path):.1f} MB > {MAX_MB} MB"
    print(f"  {path.relative_to(ROOT)}  {dur(path):.1f} s  {mb(path):.2f} MB")


# ------------------------------------------------------------------ reel
def napravi_reel_projekt(base):
    clips = base / "klipovi"
    clips.mkdir()
    for f in ("klip1.mp4", "klip2.mp4"):
        shutil.copy(FIX / f, clips / f)
    proj = base / "shofe_projekt"
    run("prepare.py", clips, "--out", proj)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    mock = json.loads((FIX / "mock_words.json").read_text(encoding="utf-8"))
    off = pj["clips"][1]["start"]
    words = mock["w1"] + [dict(w, s=round(w["s"] + off, 3), e=round(w["e"] + off, 3)) for w in mock["w2"]]
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                     ensure_ascii=False), encoding="utf-8")
    run("plan.py", proj, "--stil", "suncani")
    edit = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    edit["hook"] = "Klima smrdi? Očisti je sam"
    edit["naglasi"] = ["klimu", "filter", "struju"]
    edit["glazba"] = str(FIX / "glazba.mp3")
    (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=1), encoding="utf-8")
    return proj


def demo_reel(proj):
    run("render.py", proj, "--izlaz", "reel.mp4")
    out = DEMO / "M1_reel.mp4"
    # okomito 1080×1920 → 720×1280 za demo, da stane u par MB
    ff("-i", proj / "reel.mp4", "-vf", "scale=720:1280", "-c:v", "libx264", "-crf", "26", "-preset", "slow",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out)
    provjeri_velicinu(out)
    run("render.py", proj, "--kadar", "0.8,4,9")
    shutil.copy(proj / "kadrovi.png", DEMO / "M1_kadrovi.png")


def demo_stilovi(proj):
    edit0 = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    dijelovi = []
    for stil in STILOVI:
        edit = dict(edit0, stil=stil, glazba=None)
        # samo početak: prve tri zadržane rečenice
        kept = [s["id"] for s in edit["odsjecci"] if s["zadrzi"]][:3]
        edit["odsjecci"] = [dict(s, zadrzi=s["zadrzi"] and s["id"] in kept) for s in edit["odsjecci"]]
        (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=1), encoding="utf-8")
        run("render.py", proj, "--izlaz", f"stil_{stil}.mp4")
        lab = proj / f"lab_{stil}.mp4"
        # natpis sa stilom gore lijevo; font iz paketa, putanja relativna uz cwd (radi i na Windowsu)
        shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", proj / "natpis.ttf")
        vf = ("scale=720:1280,drawtext=fontfile=natpis.ttf:text='stil\\: " + stil + "':x=28:y=28:fontsize=40:"
              "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=14")
        ff("-i", f"stil_{stil}.mp4", "-vf", vf, "-c:v", "libx264", "-crf", "27", "-preset", "slow",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2", lab.name, cwd=proj)
        dijelovi.append(lab)
    (proj / "edit.json").write_text(json.dumps(edit0, ensure_ascii=False, indent=1), encoding="utf-8")
    lst = proj / "stilovi.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in dijelovi), encoding="utf-8")
    out = DEMO / "M1_stilovi.mp4"
    ff("-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "-movflags", "+faststart", out.resolve(), cwd=proj)
    provjeri_velicinu(out)


# ------------------------------------------------------------------ karta videa
TEME = [
    {"od": 0.3, "do": 13.7, "naslov": "Uvod i gost", "sazetak": "Voditelj otvara epizodu i pita gosta kako je počeo."},
    {"od": 13.7, "do": 32.7, "naslov": "Garaža i prvi album",
     "sazetak": "Počeci u garaži, bubnjevi i susjedi, dvije godine do prvog albuma."},
    {"od": 32.7, "do": 46.1, "naslov": "Što je bilo najteže",
     "sazetak": "Vrijeme uz druge poslove i skupi studio u Zagrebu."},
    {"od": 46.1, "do": 54.6, "naslov": "Pjesma u autu", "sazetak": "Najava pjesme o Kutini i Moslavini."},
]


def napravi_video_razgovora(proj, trajanje):
    """Slika za probni razgovor: tri „kadra" (rez na 18 s i 36 s) i tamni dio 40–44 s."""
    w, h = 1280, 720
    ff("-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=25:d=18",
       "-f", "lavfi", "-i", f"smptehdbars=s={w}x{h}:r=25:d=18",
       "-f", "lavfi", "-i", f"mandelbrot=s={w}x{h}:r=25,trim=duration={trajanje - 36 + 0.5}",
       "-i", FIX / "razgovor.m4a",
       "-filter_complex",
       "[0:v]setpts=PTS-STARTPTS,format=yuv420p[a];[1:v]setpts=PTS-STARTPTS,format=yuv420p[b];"
       "[2:v]setpts=PTS-STARTPTS,format=yuv420p,eq=brightness=-0.45:enable='between(t,4,8)'[c];"
       "[a][b][c]concat=n=3:v=1:a=0[v]",
       "-map", "[v]", "-map", "3:a", "-shortest", "-c:v", "libx264", "-crf", "30", "-preset", "veryfast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", proj / "source.mp4")


def trenuci_iz(raz):
    rec = raz["recenice"]

    def nadji(rijec):
        return next(r for r in rec if rijec.lower() in r["tekst"].lower())
    zelje = [("garaž", "hook", 5, "Slika garaže i vikenda do kasno u noć: odmah stvara znatiželju."),
             ("susjedi", "smijeh", 3, "Bubnjevi i nesretni susjedi, duhovito i kratko."),
             ("najteže je", "poanta", 4, "Iskren odgovor koji zaokružuje priču o albumu."),
             ("zasvirajte", "akcija", 4, "Najava nastupa u autu, dobar prijelaz na pjesmu.")]
    out = []
    for rijec, vrsta, ocjena, opis in zelje:
        try:
            r = nadji(rijec)
        except StopIteration:
            continue
        out.append({"od": r["od"], "do": r["do"], "vrsta": vrsta, "ocjena": ocjena, "opis": opis})
    if not out:
        out = [{"od": rec[3]["od"], "do": rec[3]["do"], "vrsta": "hook", "ocjena": 5, "opis": "Jak početak priče."}]
    return out


def govornici_iz_oznaka(proj, raz):
    """Rezerva bez interneta: govornici iz poznatih oznaka probnog razgovora (A, B, C → G1, G2, G3)."""
    mapa = {}
    segs = []
    for r in raz["recenice"]:
        g = mapa.setdefault(r["g"], f"G{len(mapa) + 1}")
        segs.append({"od": r["od"], "do": r["do"], "g": g})
    stats = []
    for g in dict.fromkeys(s["g"] for s in segs):
        t = sum(s["do"] - s["od"] for s in segs if s["g"] == g)
        stats.append({"id": g, "ime": "", "govori_s": round(t, 1)})
    tot = sum(s["govori_s"] for s in stats)
    for s in stats:
        s["udio"] = round(s["govori_s"] / tot, 3)
    (proj / "govornici.json").write_text(json.dumps({"govornici": stats, "odsjecci": segs}, ensure_ascii=False),
                                         encoding="utf-8")


def napravi_karta_projekt(base):
    raz = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))
    proj = base / "Sunčani4M epizoda (demo)"
    proj.mkdir()
    napravi_video_razgovora(proj, raz["trajanje"])
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": raz["words"]},
                                                     ensure_ascii=False), encoding="utf-8")
    r = run("govornici.py", proj, "--broj", "3", check=False)
    if r.returncode != 0:
        print("  (govornici.py bez modela – koristim oznake probnog razgovora)")
        govornici_iz_oznaka(proj, raz)
    run("govornici.py", proj, "--imena", "G1=Marko,G2=Ivana,G3=Tomo")
    run("analyze.py", proj)
    an = json.loads((proj / "analiza.json").read_text(encoding="utf-8"))
    an["teme"] = TEME
    an["trenuci"] = trenuci_iz(raz)
    (proj / "analiza.json").write_text(json.dumps(an, ensure_ascii=False, indent=1), encoding="utf-8")
    run("analyze.py", proj, "--provjeri")
    return proj


def demo_karta(proj):
    from playwright.sync_api import sync_playwright
    page_url = (proj / "pregled.html").resolve().as_uri()
    vid_dir = proj / "snimka"
    W, H = 1280, 800
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(vid_dir),
                            record_video_size={"width": W, "height": H})
        pg = ctx.new_page()
        greske = []
        pg.on("pageerror", lambda e: greske.append(str(e)))
        pg.goto(page_url)
        pg.wait_for_timeout(1800)
        pg.screenshot(path=str(DEMO / "M1_karta_videa.png"), full_page=True)

        def klik(sel, cekaj=1400):
            el = pg.locator(sel).first
            el.scroll_into_view_if_needed()
            el.hover()
            pg.wait_for_timeout(350)
            el.click()
            pg.wait_for_timeout(cekaj)

        # 1) najjači trenutak → video skoči i svira
        klik("#trenuci > *", 600)
        pg.evaluate("document.getElementById('video').play().catch(()=>{})")
        pg.wait_for_timeout(3500)
        # 2) vremenska crta: zum i klik na temu
        pg.locator("#tl").scroll_into_view_if_needed()
        pg.wait_for_timeout(600)
        klik("#zoomIn", 700)
        klik("#zoomIn", 900)
        klik("#zoomFit", 900)
        klik("#teme > *:nth-child(3)", 2500)
        # 3) govornici i transkript: pretraga
        pg.locator("#govornici").scroll_into_view_if_needed()
        pg.wait_for_timeout(1800)
        pg.locator("#trazi").scroll_into_view_if_needed()
        pg.locator("#trazi").click()
        pg.keyboard.type("album", delay=140)
        pg.wait_for_timeout(1800)
        klik("#transkript .seg:visible", 2500)
        pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        pg.wait_for_timeout(2000)
        snimka = pg.video.path()
        ctx.close()
        b.close()
    if greske:
        sys.exit("JS greške u pregled.html: " + "; ".join(greske))
    out = DEMO / "M1_karta_videa.mp4"
    ff("-i", snimka, "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "28", "-preset", "slow",
       "-an", "-movflags", "+faststart", out)
    provjeri_velicinu(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samo", choices=["reel", "stilovi", "karta"], default=None)
    a = ap.parse_args()
    DEMO.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shofe demo ") as tmp:
        base = Path(tmp)
        if a.samo in (None, "reel", "stilovi"):
            proj = napravi_reel_projekt(base)
            if a.samo in (None, "reel"):
                demo_reel(proj)
            if a.samo in (None, "stilovi"):
                demo_stilovi(proj)
        if a.samo in (None, "karta"):
            demo_karta(napravi_karta_projekt(base))
    print("Gotovo →", DEMO)


if __name__ == "__main__":
    main()
