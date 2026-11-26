"""Demo za pregled prekretnice M2 (montaža po naredbi) → demo/ (videi ≤ 8 MB, slike).

  python tests/make_demo_m2.py                 sve
  python tests/make_demo_m2.py --radna MAPA    radna mapa ostaje (za provjeru)

Što nastaje:
  demo/M2_naredbe.mp4     probni reel „SF klima" (2 klipa, sintetski glas): automatski plan → „zadrži drugi
                          pokušaj uvoda" + „izreži dio o cijeni" → „makni od … do …" (po vremenu) →
                          „skrati na 20 sekundi"; prije svakog koraka kartica s naredbom i odgovorom alata
  demo/M2_engleski.mp4    zadnja verzija s hrvatskim titlovima (Shofe) i engleskim SRT-om (VLC/YouTube)
  demo/M2_verzije.png     ono što Claude vidi: popis verzija, usporedba, rječnik
  demo/M2_davinci.png     timeline iz reel_vN.fcpxml nacrtan kao u DaVinciju (kadrovi iz originalnih klipova)

Treba ffmpeg, espeak-ng (sintetski govor) i Playwright s Chromiumom (kartice i slike).
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FONTS = ROOT / "shofe-montaza" / "fonts"
FIX = ROOT / "tests" / "fixtures"
DEMO = ROOT / "demo"
MAX_MB = 8.0
W, H = 720, 1280  # demo videi u pola rezolucije

# Isti izmišljeni reel kao testni skup naredbi (tests/fixtures/naredbe_sadrzaj.json): tri pokušaja uvoda,
# zabuna u cijeni. Prvih 7 rečenica je klip 1 (vodoravni, mobitel položeno), ostalo klip 2 (okomiti).
SKUP = json.loads((FIX / "naredbe_sadrzaj.json").read_text(encoding="utf-8"))
REZ_KLIPA = 7

# Claudeov prijevod (ono što bi Claude upisao u prijevod_en.json), po hrvatskom tekstu rečenice.
EN = {
    "Bok ekipa, ovdje Marko iz SF klime.": "Hi everyone, Marko from SF klima here.",
    "Danas vam pokazujem tri stvari o klima uređajima.": "Today I'll show you three things about air conditioners.",
    "Danas vam pokazujem tri stvari koje morate znati o klima uređajima.":
        "Today I'll show you three things you need to know about air conditioners.",
    "Prvo, koliko košta klima uređaj?": "First, how much does an AC cost?",
    "Dobar uređaj za dnevni boravak košta oko tisuću eura.": "A good unit for a living room costs about €1,000.",
    "Ugradnja je još dvjesto, ne, tristo eura.": "Installation is another two, no, three hundred euros.",
    "Drugo, ugradnja.": "Second, installation.",
    "Ugradnja traje jedan dan i radimo je mi.": "Installation takes one day and we do it ourselves.",
    "Radimo i subotom ako vam radnim danom ne odgovara.": "We also work Saturdays if weekdays don't suit you.",
    "Ugradnja zimi nije problem.": "Installing in winter is no problem.",
    "Treće, održavanje.": "Third, maintenance.",
    "Filter čistite svakih mjesec dana.": "Clean the filter every month.",
    "Samo ga isperite pod mlakom vodom i osušite.": "Just rinse it in lukewarm water and let it dry.",
    "Servis jednom godišnje produljuje život uređaja.": "A yearly service extends the unit's life.",
    "Zimi klima i grije, i to jeftinije od radijatora.": "In winter the AC heats too, and cheaper than radiators.",
    "Pratite SF klimu za još savjeta!": "Follow SF klima for more tips!",
}


def run(script, *args, check=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        sys.exit(f"{script} {args} pao:\n{r.stdout}\n{r.stderr}")
    return r


def ff(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, args)], check=True, cwd=cwd)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def provjeri_velicinu(path):
    mb = path.stat().st_size / 1e6
    assert mb <= MAX_MB, f"{path.name} ima {mb:.1f} MB > {MAX_MB} MB"
    print(f"  {path.relative_to(ROOT)}  {dur(path):.1f} s  {mb:.2f} MB")


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}".replace(".", ",")


# ------------------------------------------------------------------ probne snimke
def wavdur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def napravi_klipove(base):
    """Dva klipa sa sintetskim govorom (espeak-ng) i poznatim vremenom riječi. Slika ima vremenski kod
    izvornog klipa, da se u demu vidi što je izrezano."""
    rec = SKUP["recenice"]
    dijelovi = [rec[:REZ_KLIPA], rec[REZ_KLIPA:]]
    klipovi = base / "klipovi"
    klipovi.mkdir()
    rad = base / "tts"
    rad.mkdir()
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", rad / "f.ttf")
    words_po_klipu, trajanja = [], []
    for k, recenice in enumerate(dijelovi, 1):
        parts, words, t = [], [], 0.5
        sil = rad / f"s{k}_0.wav"
        ff("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.5", sil)
        parts.append(sil)
        for i, (txt, pauza) in enumerate(recenice):
            f = rad / f"k{k}_{i}.wav"
            subprocess.run(["espeak-ng", "-v", "hr", "-s", "155", "-w", str(f), txt], check=True)
            d = wavdur(f)
            toks = txt.split()
            tot = sum(len(x) for x in toks)
            a0, a1, acc = t + 0.08, t + d - 0.12, 0
            for x in toks:
                s = a0 + (a1 - a0) * acc / tot
                acc += len(x)
                e = a0 + (a1 - a0) * acc / tot
                words.append({"w": x, "s": round(s, 3), "e": round(e - 0.03, 3), "p": 0.95})
            parts.append(f)
            t += d
            g = rad / f"k{k}_{i}g.wav"
            ff("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", str(pauza), g)
            parts.append(g)
            t += pauza
        lst = rad / f"k{k}.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        ff("-f", "concat", "-safe", "0", "-i", lst.name, "-ar", "48000", f"k{k}.wav", cwd=rad)
        if k == 1:  # vodoravni 1920×1080, 29,97 fps (kao mobitel položeno)
            src = f"gradients=s=1920x1080:r=30000/1001:d={t:.3f}:speed=0.015:c0=0x1b4965:c1=0x62b6cb"
            fs, ry, cx = 40, 0.25, 0.602  # u 9:16 se vidi samo pojas oko 0.60 širine (crop-x 0.65)
        else:  # okomiti 1080×1920, 30 fps
            src = f"gradients=s=1080x1920:r=30:d={t:.3f}:speed=0.015:c0=0x3d2c5e:c1=0xf4a259"
            fs, ry, cx = 60, 0.25, 0.5
        vf = (f"drawgrid=w=120:h=120:t=2:c=white@0.25,"
              f"drawtext=fontfile=f.ttf:text='KLIP {k}':x=w*{cx}-tw/2:y=h*{ry}:fontsize={fs * 2}:fontcolor=white@0.85,"
              f"drawtext=fontfile=f.ttf:text='izvorno %{{pts\\:hms}}':x=w*{cx}-tw/2:y=h*{ry}+{fs * 2.6:.0f}:"
              f"fontsize={fs}:fontcolor=white:box=1:boxcolor=black@0.45:boxborderw=16")
        ff("-f", "lavfi", "-i", src, "-i", f"k{k}.wav", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", (klipovi / f"klip{k}.mp4").resolve(),
           cwd=rad)
        words_po_klipu.append(words)
        trajanja.append(t)
    return klipovi, words_po_klipu


def napravi_projekt(base):
    klipovi, wk = napravi_klipove(base)
    proj = base / "SF klima reel"
    # klip 1 je vodoravan: Marko stoji desno od sredine → crop-x 0.65
    run("prepare.py", klipovi, "--out", proj, "--crop", "klip1=0.65")
    pj = load(proj / "project.json")
    words = []
    for c, ws in zip(pj["clips"], wk):
        words += [dict(w, s=round(w["s"] + c["start"], 3), e=round(w["e"] + c["start"], 3)) for w in ws]
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    run("plan.py", proj, "--stil", "suncani")
    # teme kao da ih je Claude upisao iz transkripta (za „makni dio o održavanju" itd.)
    granice, i = [], 0
    for txt, _ in SKUP["recenice"]:
        n = len(txt.split())
        granice.append((words[i]["s"], words[i + n - 1]["e"]))
        i += n
    teme = [{"od": granice[t["recenice"][0]][0], "do": granice[t["recenice"][1]][1], "naslov": t["naslov"],
             "sazetak": t.get("sazetak", "")} for t in SKUP["teme"]]
    save(proj / "analiza.json", {"teme": teme, "trenuci": []})
    edit = load(proj / "edit.json")
    edit["hook"] = "3 stvari prije kupnje klime"
    edit["naglasi"] = ["tisuću", "filter", "jeftinije"]
    edit["glazba"] = str(FIX / "glazba.mp3")
    save(proj / "edit.json", edit)
    return proj


# ------------------------------------------------------------------ koraci montaže
def izbaceno_u_planu(proj):
    edit = load(proj / "edit.json")
    return [s["tekst"] for s in edit["odsjecci"] if not s["zadrzi"]]


def render(proj):
    before = set(proj.glob("reel_v*.mp4"))
    run("render.py", proj)
    novi = sorted(set(proj.glob("reel_v*.mp4")) - before)
    assert len(novi) == 1, novi
    return novi[0]


def odgovor(r):
    """Kratki odgovor alata (ono što Claude prepriča Marku): retci s izbačenim/dodanim i trajanjem."""
    out = []
    for ln in r.stdout.splitlines():
        ln = ln.rstrip()
        if ln.strip():
            out.append(ln)
    return out




def t_str(s):
    """'00:43.17' (ispis alata) → '0:43,2' (za karticu)."""
    m, sec = s.split(":")
    return f"{int(m)}:{float(sec):04.1f}".replace(".", ",")


def trajanje(r):
    m = re.search(r"Trajanje: (\d\d:\d\d\.\d\d) → (\d\d:\d\d\.\d\d)", r.stdout)
    assert m, r.stdout
    return t_str(m.group(1)), t_str(m.group(2))


def popis(proj, *extra):
    """uredi.py popis → [(od, do, tekst)] u vremenu gotovog videa."""
    r = run("uredi.py", proj, "popis", *extra)
    out = []
    for ln in r.stdout.splitlines():
        m = re.match(r"\s+(\d\d):(\d\d\.\d\d)-(\d\d):(\d\d\.\d\d)\s+#\d+\s+(.*)", ln)
        if m:
            out.append((int(m[1]) * 60 + float(m[2]), int(m[3]) * 60 + float(m[4]), m[5]))
    return out


def koraci(proj):
    """Izvede cijeli niz naredbi kao što bi ih Claude izveo za Marka; vrati podatke za kartice i isječke."""
    k = {}
    # 1) automatski plan
    k["plan_van"] = izbaceno_u_planu(proj)
    k["v1"] = render(proj)
    k["v1_dur"] = t_str(f"{int(dur(k['v1']) // 60):02d}:{dur(k['v1']) % 60:05.2f}")
    # 2) naredbe po sadržaju: Claude nađe citate u transcript.txt
    r1 = run("uredi.py", proj, "dodaj", "--od", "Danas vam pokazujem tri stvari o klima uređajima.")
    run("uredi.py", proj, "makni", "--od", "tri stvari koje morate znati", "--cijele-recenice")
    r3 = run("uredi.py", proj, "makni", "--od", "Prvo, koliko košta", "--do", "tristo eura.")
    k["v2_od"], k["v2_do"] = trajanje(r1)[0], trajanje(r3)[1]
    k["v2"] = render(proj)
    # 3) naredba po vremenu: Marko gleda v2 i vidi rečenicu o suboti na ~0:10,5–0:13,7
    sub = next(p for p in popis(proj) if p[2].startswith("Radimo i subotom"))
    od, do = int(sub[0] * 10) / 10, int(sub[1] * 10 + 1) / 10
    k["sub_cmd"] = f"{mmss(od)}-{mmss(do)}"
    r = run("uredi.py", proj, "makni", k["sub_cmd"])
    m = re.search(r"stvarno (\d\d:\d\d\.\d\d)-(\d\d:\d\d\.\d\d)", r.stdout)
    k["sub_stvarno"] = (t_str(m[1]), t_str(m[2]))
    k["sub_rez"] = od
    k["v3_od"], k["v3_do"] = trajanje(r)
    k["v3"] = render(proj)
    # 4) „skrati na 20 sekundi, savjet o filteru mora ostati": Claude pročita misli (--proba) i ocijeni ih
    proba = run("uredi.py", proj, "skrati", "20", "--proba").stdout
    misli = re.findall(r"#(\d+)\s+\d\d:\d\d\.\d\d\s+[\d.]+s\s+[\d.]+(?: \([^)]*\))?\s+(.*)", proba)
    ocjene = []
    for n, txt in misli:
        o = 3
        if "Filter" in txt or "isperite" in txt:
            o = 5
        elif txt.startswith(("Bok", "Pratite", "Danas")):
            o = 4
        elif "Servis" in txt or "zimi nije" in txt:
            o = 1
        ocjene.append(f"{n}:{o}")
    r = run("uredi.py", proj, "skrati", "20", "--ocjene", ",".join(ocjene))
    k["skr_van"] = re.findall(r"(?m)^\s*X\s+#\d+\s+\d\d:\d\d\.\d\d\s+[\d.]+s\s+[\d.]+(?: \([^)]*\))?\s+(.*)$",
                              r.stdout)
    k["skrati_ispis"] = r.stdout
    k["skr_misli"] = len(misli)
    k["v4_od"], k["v4_do"] = trajanje(r)
    k["v4"] = render(proj)
    k["verzije"] = run("verzije.py", proj).stdout
    k["usporedi"] = run("verzije.py", proj, "usporedi", "1", "4").stdout
    return k


# ------------------------------------------------------------------ kartice (HTML → PNG)
CSS = """
@font-face{font-family:M;src:url('%(f)s/Montserrat-SemiBold.ttf');font-weight:600}
@font-face{font-family:M;src:url('%(f)s/Montserrat-ExtraBold.ttf');font-weight:800}
@font-face{font-family:M;src:url('%(f)s/Montserrat-Black.ttf');font-weight:900}
*{box-sizing:border-box;margin:0;padding:0}
body{width:%(w)dpx;height:%(h)dpx;background:#11161d;color:#e9eef3;font-family:M,sans-serif;font-weight:600;
 padding:70px 48px;display:flex;flex-direction:column;gap:34px;overflow:hidden}
.top{font-size:22px;letter-spacing:.14em;color:#7f8c99;font-weight:800}
.korak{font-size:30px;color:#f4a259;font-weight:800;letter-spacing:.04em}
h1{font-size:62px;line-height:1.12;font-weight:900}
.tko{font-size:22px;color:#7f8c99;font-weight:800;letter-spacing:.1em;margin-bottom:12px}
.bubble{align-self:flex-end;max-width:92%%;background:#f4a259;color:#1b1206;font-size:44px;line-height:1.22;
 font-weight:800;padding:26px 30px;border-radius:30px 30px 6px 30px}
.odg{display:flex;flex-direction:column;gap:16px}
.ln{font-size:31px;line-height:1.3;padding-left:46px;position:relative;color:#d5dde5}
.ln b{position:absolute;left:0;top:1px;width:34px;height:34px;border-radius:17px;text-align:center;
 font-weight:900;font-size:26px;line-height:34px}
.van b{background:#c8553d;color:#fff}.plus b{background:#4caf7a;color:#fff}.i b{background:#3d5a80;color:#fff}
q{quotes:none}.ln q{color:#fff}
.dno{margin-top:auto;display:flex;justify-content:space-between;align-items:flex-end;border-top:2px solid #26303b;
 padding-top:26px}
.ver{font-size:30px;font-weight:900;color:#f4a259}
.dur{font-size:44px;font-weight:900}
.dur small{font-size:24px;color:#7f8c99;font-weight:600;display:block;text-align:right}
p{font-size:34px;line-height:1.35;color:#cfd8e0}
pre{font-family:'DejaVu Sans Mono',Consolas,monospace;font-size:15px;line-height:1.45;color:#d5dde5;
 white-space:pre-wrap;background:#0b0f14;border-radius:14px;padding:18px 20px}
"""


def e(s):
    return html.escape(s)


def ln(kind, text):
    znak = {"van": "−", "plus": "+", "i": "i"}[kind]
    return f'<div class="ln {kind}"><b>{znak}</b>{text}</div>'


def q(s):
    return f"<q>„{e(s)}“</q>"


def kartica(n, korak, naredba, linije, verzija, od_do, naslov=None, tekst=None):
    body = f'<div class="top">PREGLED M2 · MONTAŽA PO NAREDBI</div><div class="korak">{e(korak)}</div>'
    if naslov:
        body += f"<h1>{e(naslov)}</h1>"
    if tekst:
        body += "".join(f"<p>{t}</p>" for t in tekst)
    if naredba:
        body += f'<div><div class="tko" style="text-align:right">MARKO</div><div class="bubble">{e(naredba)}</div></div>'
    if linije:
        body += f'<div><div class="tko">SHOFE</div><div class="odg">{"".join(linije)}</div></div>'
    if verzija:
        od, do = od_do
        strel = f"{od} → {do}" if od else do
        body += (f'<div class="dno"><div class="ver">{e(verzija)}</div>'
                 f'<div class="dur"><small>trajanje</small>{e(strel)}</div></div>')
    return body


def snimi_kartice(kartice, out_dir, size=(W, H), extra_css="", full=False):
    from playwright.sync_api import sync_playwright
    css = CSS % {"f": FONTS.resolve().as_uri(), "w": size[0], "h": size[1]} + extra_css
    paths = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": size[0], "height": size[1]})
        for i, body in enumerate(kartice):
            f = out_dir / f"kartica_{i}.html"
            f.write_text(f"<!doctype html><meta charset='utf-8'><style>{css}</style><body>{body}</body>",
                         encoding="utf-8")
            pg.goto(f.resolve().as_uri())
            pg.wait_for_timeout(150)
            png = out_dir / f"kartica_{i}.png"
            pg.screenshot(path=str(png), full_page=full)
            paths.append(png)
        b.close()
    return paths


# ------------------------------------------------------------------ slaganje videa
ENC = ["-c:v", "libx264", "-crf", "25", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]


def dio_kartica(png, sekundi, out):
    ff("-loop", "1", "-framerate", "30", "-t", sekundi, "-i", png, "-f", "lavfi", "-t", sekundi,
       "-i", "anullsrc=r=48000:cl=stereo", "-vf", f"scale={W}:{H},fade=in:d=0.25", "-shortest", *ENC, out)


def dio_video(src, od, do, out):
    d = do - od
    ff("-ss", f"{od:.3f}", "-t", f"{d:.3f}", "-i", src,
       "-vf", f"scale={W}:{H},fade=in:d=0.2,fade=out:st={d - 0.25:.3f}:d=0.25",
       "-af", f"afade=in:d=0.15,afade=out:st={d - 0.25:.3f}:d=0.25", *ENC, out)


def spoji(dijelovi, out, rad):
    lst = rad / "dijelovi.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in dijelovi), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "-movflags", "+faststart", out.resolve(), cwd=rad)


def demo_naredbe(proj, k, rad):
    plan_van = k["plan_van"]
    kartice = [
        kartica(0, "SIROVA SNIMKA", None, [], None, None, naslov="Probni reel „SF klima“",
                tekst=["2 klipa: jedan vodoravni, jedan okomiti. Tri pokušaja uvoda i zabuna u cijeni.",
                       "Glas je sintetski, a na slici je <b>vremenski kod izvornog klipa</b> — tako se vidi što je "
                       "izrezano.", "Prije svakog videa: što je Marko rekao i što je Shofe napravio."]),
        kartica(1, "1 · AUTOMATSKI PLAN", None,
                [ln("van", f"prekinut pokušaj {q(plan_van[0])}"),
                 ln("van", f"ponovljen pokušaj {q(plan_van[1])}"),
                 ln("i", "ostaje zadnji pokušaj uvoda, pauze skraćene; hook, titlovi, glazba, stil Sunčani")],
                "verzija 1", (None, k["v1_dur"])),
        kartica(2, "2 · NAREDBE PO SADRŽAJU", "Zadrži drugi pokušaj uvoda, a izreži dio gdje pričam o cijeni.",
                [ln("plus", f"vraćen {q('Danas vam pokazujem tri stvari o klima uređajima.')}"),
                 ln("van", f"{q('Danas vam pokazujem tri stvari koje morate znati …')}"),
                 ln("van", f"{q('Prvo, koliko košta klima uređaj? … ne, tristo eura.')}"),
                 ln("i", "Claude nađe citate u transkriptu; Shofe ih provjeri i reže po cijelim riječima")],
                "verzija 2", (k["v2_od"], k["v2_do"])),
        kartica(3, "3 · NAREDBA PO VREMENU", f"Makni od {k['sub_cmd'].replace('-', ' do ')}.",
                [ln("van", f"{q('Radimo i subotom ako vam radnim danom ne odgovara.')}"),
                 ln("i", f"rez poravnat na cijele riječi: {k['sub_stvarno'][0]}–{k['sub_stvarno'][1]}"),
                 ln("i", "vrijeme se čita iz verzije koju Marko gleda (v2)")],
                "verzija 3", (k["v3_od"], k["v3_do"])),
        kartica(4, "4 · SKRATI", "Skrati na 20 sekundi, savjet o filteru mora ostati.",
                [ln("i", f"Shofe podijeli video na {k['skr_misli']} cijelih misli; Claude ih ocijeni 1–5")]
                + [ln("van", q(t if len(t) < 60 else t[:56] + " …")) for t in k["skr_van"]]
                + [ln("i", "filter ostaje; nijedna rečenica nije prerezana")],
                "verzija 4", (k["v4_od"], k["v4_do"])),
        kartica(5, "UZ SVAKU VERZIJU", None,
                [ln("i", "<q>reel_v4.mp4</q> — video"),
                 ln("i", "<q>reel_v4.srt</q> — titlovi za YouTube / VLC"),
                 ln("i", "<q>reel_v4.en.srt</q> — engleski titlovi (Claude prevodi)"),
                 ln("i", "<q>reel_v4.fcpxml</q> — timeline za DaVinci, originalne snimke"),
                 ln("plus", "„vrati verziju 2“ uvijek radi; „što se promijenilo“ usporedi verzije")],
                None, None, naslov="Ništa se ne gubi"),
    ]
    png = snimi_kartice(kartice, rad)
    v1, v2, v3, v4 = k["v1"], k["v2"], k["v3"], k["v4"]
    rez = k["sub_rez"]
    plan = [("k", png[0], 5.5), ("k", png[1], 5.0), ("v", v1, 0, 13.0),
            ("k", png[2], 6.5), ("v", v2, 0, 10.5),
            ("k", png[3], 5.5), ("v", v3, max(rez - 5.5, 0), rez + 5.0),
            ("k", png[4], 6.5), ("v", v4, 0, dur(v4)),
            ("k", png[5], 5.5)]
    dijelovi = []
    for i, p in enumerate(plan):
        out = rad / f"dio_{i:02d}.mp4"
        if p[0] == "k":
            dio_kartica(p[1], p[2], out)
        else:
            dio_video(p[1], p[2], p[3], out)
        dijelovi.append(out)
    out = DEMO / "M2_naredbe.mp4"
    spoji(dijelovi, out, rad)
    provjeri_velicinu(out)


# ------------------------------------------------------------------ engleski titlovi
def demo_engleski(proj, k, rad):
    run("prijevod.py", proj, check=False)  # napravi prijevod_en.json za zadnju verziju
    pf = proj / "prijevod_en.json"
    d = load(pf)
    for t in d["titlovi"]:
        t["en"] = EN[t["hr"]]  # ono što bi Claude upisao
    save(pf, d)
    run("prijevod.py", proj)
    srt = k["v4"].with_suffix(".en.srt")
    assert srt.exists(), srt
    shutil.copy(srt, rad / "en.srt")
    shutil.copytree(FONTS, rad / "fonts", dirs_exist_ok=True)
    stil = ("FontName=Montserrat SemiBold,Fontsize=10.5,PrimaryColour=&H00FFFFFF,BorderStyle=3,Outline=1.2,"
            "Shadow=0,BackColour=&H99000000,OutlineColour=&H99000000,Alignment=2,MarginV=10")
    out = DEMO / "M2_engleski.mp4"
    ff("-i", k["v4"].resolve(), "-vf", f"scale={W}:{H},subtitles=en.srt:fontsdir=fonts:force_style='{stil}'",
       *ENC[:-8], "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out.resolve(), cwd=rad)
    provjeri_velicinu(out)


# ------------------------------------------------------------------ verzije (što Claude vidi)
def demo_verzije(proj, k, rad):
    body = ('<div class="top">PREGLED M2 · ŠTO CLAUDE VIDI KAD KAŽEŠ „POKAŽI VERZIJE“ I „ŠTO SE PROMIJENILO“</div>'
            f'<div class="tko">verzije.py — popis</div><pre>{e(k["verzije"].strip())}</pre>'
            f'<div class="tko">verzije.py usporedi 1 4</div><pre>{e(k["usporedi"].strip())}</pre>'
            f'<div class="tko">uredi.py skrati 20 --ocjene … (Claude je ocijenio misli)</div>'
            f'<pre>{e(k["skrati_ispis"].strip())}</pre>')
    png = snimi_kartice([body], rad, size=(1280, 900), full=True,
                        extra_css="body{height:auto;padding:40px 40px;gap:14px;overflow:visible}")[0]
    out = DEMO / "M2_verzije.png"
    shutil.copy(png, out)
    print(f"  {out.relative_to(ROOT)}")


# ------------------------------------------------------------------ DaVinci timeline iz FCPXML-a
def sek(v):
    v = (v or "0s").rstrip("s")
    return float(Fraction(v))


def tc(s, fps):
    f = round(s * fps)
    n = round(fps)
    return f"{f // (n * 3600):02d}:{f // (n * 60) % 60:02d}:{f // n % 60:02d}:{f % n:02d}"


def demo_davinci(proj, k, rad):
    xml_path = k["v4"].with_suffix(".fcpxml")
    root = ET.parse(xml_path).getroot()
    fps_po_assetu = {}
    formats = {f.get("id"): f for f in root.iter("format")}
    for a in root.iter("asset"):
        f = formats.get(a.get("format"))
        if f is not None and f.get("frameDuration"):
            fps_po_assetu[a.get("id")] = 1 / sek(f.get("frameDuration"))
    seq = root.find(".//sequence")
    ukupno = sek(seq.get("duration"))
    v1, a2, oznake = [], [], []
    for c in seq.find("spine"):
        if c.tag != "asset-clip":
            continue
        off, d, st = sek(c.get("offset")), sek(c.get("duration")), sek(c.get("start"))
        zum = c.find("adjust-transform")
        v1.append({"ime": c.get("name"), "od": off, "d": d, "src": tc(st, fps_po_assetu.get(c.get("ref"), 30)),
                   "zum": zum is not None and zum.get("scale") is not None})
        for sub in c.findall("asset-clip"):  # glazba (lane -1), vrijeme u izvornom vremenu roditelja
            a2.append({"od": off + sek(sub.get("offset")) - st, "d": sek(sub.get("duration"))})
        for m in c.findall("marker"):
            oznake.append({"od": off + sek(m.get("start")) - st, "txt": m.get("value")})
    PX = 1500 / ukupno
    boje = {"klip1.mp4": "#3d7ea6", "klip2.mp4": "#b5734a"}

    def blok(x, w, boja, txt, h=64):
        return (f'<div style="position:absolute;left:{x * PX:.1f}px;width:{max(w * PX - 2, 2):.1f}px;height:{h}px;'
                f'background:{boja};border-radius:4px;overflow:hidden;font-size:12px;line-height:15px;'
                f'padding:5px 6px;color:#fff;white-space:nowrap">{txt}</div>')

    ravnalo = "".join(f'<div style="position:absolute;left:{s * PX:.1f}px;top:0;font-size:11px;color:#8a96a3">'
                      f'|{s}s</div>' for s in range(0, int(ukupno) + 1, 2))
    v = "".join(blok(c["od"], c["d"], boje.get(c["ime"], "#5a6b7c"),
                     f'<b>{e(c["ime"])}</b>{" · zum" if c["zum"] else ""}<br>{c["src"]}') for c in v1)
    a1 = "".join(blok(c["od"], c["d"], "#2f6b4f", f'{e(c["ime"])}', 34) for c in v1)
    a2h = "".join(blok(c["od"], c["d"], "#6a4c93", "glazba.mp3", 34) for c in a2)
    mk = "".join(f'<div style="position:absolute;left:{m["od"] * PX:.1f}px;top:{(i % 3) * 20}px;font-size:12px;'
                 f'color:#f4c542;white-space:nowrap">▼ {e(m["txt"])}</div>' for i, m in enumerate(oznake))

    def traka(ime, sadrzaj, h):
        return (f'<div style="display:flex;align-items:center;gap:10px;margin:6px 0">'
                f'<div style="width:40px;color:#8a96a3;font-weight:800;font-size:14px">{ime}</div>'
                f'<div style="position:relative;height:{h}px;width:1500px;background:#1a2029">{sadrzaj}</div></div>')

    body = (f'<div style="padding:28px 30px;font-family:M,sans-serif;background:#11161d;color:#e9eef3;width:1600px">'
            f'<div class="top">PREGLED M2 · {e(xml_path.name)} → DAVINCI RESOLVE (FILE › IMPORT › TIMELINE)</div>'
            f'<p style="font-size:18px;margin:10px 0 18px">Timeline nacrtan iz XML-a koji Shofe izvozi (nije snimka '
            f'DaVincija): {len(v1)} kadrova iz <b>originalnih</b> klipova, isti rezovi kao <b>{e(k["v4"].name)}</b> '
            f'({ukupno:.1f} s). Ispod imena: vremenski kod u originalnom klipu. Titlovi: File › Import › Subtitle → '
            f'{e(k["v4"].with_suffix(".srt").name)}.</p>'
            f'{traka("", ravnalo, 16)}{traka("", mk, 60)}{traka("V1", v, 64)}{traka("A1", a1, 34)}'
            f'{traka("A2", a2h, 34)}</div>')
    png = snimi_kartice([body], rad, size=(1660, 420), full=True,
                        extra_css="body{height:auto;padding:0;display:block;overflow:visible}")[0]
    out = DEMO / "M2_davinci.png"
    shutil.copy(png, out)
    print(f"  {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radna", type=Path, default=None, help="radna mapa (ostaje nakon kraja)")
    a = ap.parse_args()
    if not shutil.which("espeak-ng"):
        sys.exit("Treba espeak-ng (sintetski govor): apt install espeak-ng")
    DEMO.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shofe demo m2 ") as tmp:
        base = a.radna or Path(tmp)
        if a.radna:
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        proj = napravi_projekt(base)
        k = koraci(proj)
        rad = base / "demo_rad"
        rad.mkdir()
        demo_naredbe(proj, k, rad)
        demo_engleski(proj, k, rad)
        demo_verzije(proj, k, rad)
        demo_davinci(proj, k, rad)
    print("Gotovo →", DEMO)


if __name__ == "__main__":
    main()
