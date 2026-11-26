"""Demo za pregled prekretnice M3 (isječci za mreže) → demo/ (videi ≤ 8 MB, slike).

  python tests/make_demo_m3.py                 sve
  python tests/make_demo_m3.py --radna MAPA    radna mapa ostaje (za provjeru)

Probna snimka: izmišljeni dio epizode Sunčani4M (tests/fixtures/isjecci_razgovor.json, ~4 min), dva
nacrtana voditelja u vodoravnom kadru, sintetski glasovi (espeak-ng), usta se miču po glasu. Na slici je
vremenski kod snimke, pa se vidi iz kojeg dijela epizode je isječak. Cijeli put kao na Markovom laptopu:
prepare (9:16) → govornici → analiza + Claudeove teme i trenuci → kadar.py (kadar prati govornika) →
isjecci.py (kandidati) → Claudeove ocjene → odobri/odbaci → isjecci.py render → objava.py → naslovna.py.

Što nastaje:
  demo/M3_isjecci.mp4   kartice (epizoda, kandidati s ocjenama) + tri odobrena isječka kako izlaze iz Shofea
  demo/M3_kadar.mp4     vodoravna snimka s okvirom koji Shofe izreže + gotov 9:16 kadar, jedno uz drugo
  demo/M3_objava.png    naslovne sličice (9:16 i 16:9) i tekstovi za Instagram, TikTok i YouTube za isječak
  demo/M3_naslovna.jpg  kandidati za naslovnu sličicu s ocjenom i razlogom (što Claude pogleda)

Treba ffmpeg, espeak-ng (sintetski govor), opencv-python-headless, Pillow i Playwright s Chromiumom.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_demo_m2 as M2  # noqa: E402  (ff, run, kartice, slaganje videa)
import make_kadar_klip as MK  # noqa: E402  (crtanje lica)

ROOT, FONTS, FIX, DEMO = M2.ROOT, M2.FONTS, M2.FIX, M2.DEMO
ff, run, load, save, e, dur = M2.ff, M2.run, M2.load, M2.save, M2.e, M2.dur
W, H = M2.W, M2.H
RAZGOVOR = json.loads((FIX / "isjecci_razgovor.json").read_text(encoding="utf-8"))

VW, VH, VFPS = 1280, 720, 25        # izvorna vodoravna snimka (kao kamera u autu)
GLAS = {"A": ["-v", "hr", "-s", "150", "-p", "40"], "B": ["-v", "hr+f3", "-s", "160", "-p", "60"]}
SJEDALA = {"A": (0.27, 0.46, 112, (140, 170, 215), (40, 50, 60), (150, 80, 60)),
           "B": (0.72, 0.48, 106, (120, 150, 200), (30, 60, 110), (70, 110, 60))}

# Ono što bi Claude napisao: ocjena, razlog, naslov, hook, stil po bloku epizode.
CLAUDE = {
    "greska_klima": dict(ocjena=9, razlog="Jasna greška s brojem iz Kutine i savjetom koji štedi novac; stoji sama "
                         "za sebe.", naslov="Najveća greška kod kupnje klime", hook="Najveća greška kod kupnje klime",
                         stil="cisto", naglasi=["dvostruko", "četrdeset", "garanciju"]),
    "prvi_koncert": dict(ocjena=8, razlog="Osobna priča s emocijom koja u pola minute objasni što je Sunčani4M.",
                         naslov="Prvi koncert u Renaultu", hook="Bend na stražnjem sjedalu", stil="kino",
                         naglasi=["Renaultu", "zajednica", "glazbu"]),
    "odrzavanje": dict(ocjena=8, razlog="Pitanje i odgovor s dva konkretna broja: 80 eura servis ili 300 eura kvar.",
                       naslov="Koliko košta održavanje klime", hook="80 € ili 300 €?", stil="podcast",
                       naglasi=["osamdeset", "tristo", "osiguranje"]),
    "tri_stvari": dict(ocjena=7, razlog="Koristan popis, ali bez priče; dobar za kasnije u sezoni.",
                       naslov="Tri stvari prije ljeta", hook="Napravi ovo prije ljeta"),
    "cavrljanje": dict(ocjena=2, razlog="Čavrljanje na početku snimanja, nema poante."),
    "lutanje": dict(ocjena=2, razlog="Priča bez poante, gledatelj ne zna o čemu je riječ."),
    "nedovrseno": dict(ocjena=3, razlog="Priča o čovjeku iz Popovače ostaje nedovršena."),
    "odjava": dict(ocjena=1, razlog="Odjava epizode."),
}
ODOBRI = ["greska_klima", "prvi_koncert", "odrzavanje"]
ODBACI = {"tri_stvari": "imamo već sličan savjet za ljeto"}

# Ono što bi Claude napisao za objavu (po bloku), serija Sunčani4M.
OBJAVA = {
    "greska_klima": {
        "instagram": {"opis": "Jeftina klima može vas skupo koštati. ❄️\n\nLoše ugrađena troši dvostruko više struje "
                              "— prošle godine smo u Kutini imali 40 takvih slučajeva. Prije kupnje pitajte tko "
                              "ugrađuje i daje li garanciju na ugradnju.\n\nSpremi za ljeto i pošalji nekome tko "
                              "kupuje klimu.", "hashtagovi": ["#klima", "#ugradnjaklime", "#savjeti"]},
        "tiktok": {"opis": "Ovu grešku radi skoro svatko tko kupuje klimu 😬 Jesi li ti pitao tko ugrađuje?",
                   "hashtagovi": ["#klima", "#savjeti", "#ljeto"]},
        "youtube": {"naslov": "Najveća greška kod kupnje klime (nije cijena)",
                    "opis": "Loše ugrađena klima troši dvostruko više struje. Što pitati prije kupnje — iz "
                            "Sunčani4M podcasta.", "hashtagovi": ["#klima", "#shorts"]},
    },
    "prvi_koncert": {
        "instagram": {"opis": "Bend na stražnjem sjedalu, a Kutina pjeva na semaforu. 🎸\n\nTako je počeo "
                              "Sunčani4M — i zato svaki tjedan opet sjednemo u stari Renault.\n\nOznači nekoga s "
                              "kim bi pjevao na semaforu.", "hashtagovi": ["#podcast", "#zivaglazba", "#renault4"]},
        "tiktok": {"opis": "Koncert u Renaultu 4 kroz Kutinu 🎶 Bi li otvorio prozor i pjevao s nama?",
                   "hashtagovi": ["#renault4", "#glazba", "#podcast"]},
        "youtube": {"naslov": "Prvi koncert u Renaultu 4 | Sunčani4M",
                    "opis": "Bend na stražnjem sjedalu i Kutina koja pjeva na semaforu: kako je počeo Sunčani4M.",
                    "hashtagovi": ["#renault4", "#shorts"]},
    },
    "odrzavanje": {
        "instagram": {"opis": "Servis klime: 80 eura sada ili kvar od 300 eura za tri godine? 🔧\n\nČišćenje "
                              "filtera, provjera plina i dezinfekcija — jednom godišnje.\n\nSpremi i podsjeti se "
                              "na proljeće.", "hashtagovi": ["#klima", "#servisklime", "#savjeti"]},
        "tiktok": {"opis": "Koliko košta održavanje klime? Odgovor će te iznenaditi 👀",
                   "hashtagovi": ["#klima", "#servis", "#ustedi"]},
        "youtube": {"naslov": "Koliko košta održavanje klime godišnje?",
                    "opis": "Redovni servis klime je oko 80 eura i štedi kvar od 300 eura. Što uključuje.",
                    "hashtagovi": ["#klima", "#shorts"]},
    },
}
NASLOVNA = {"greska_klima": "NAJVEĆA *GREŠKA* S KLIMOM", "prvi_koncert": "KONCERT U *RENAULTU*",
            "odrzavanje": "*80 €* ILI 300 €?"}


# ------------------------------------------------------------------ probna epizoda
def napravi_epizodu(base):
    """Sintetski govor po rečenicama → wav + riječi s vremenom + tko govori; zatim vodoravni video s dva
    nacrtana voditelja kojima se usta miču po glasu. Vraća (video, riječi, blokovi[(oznaka, od, do)], rečenice)."""
    rad = base / "tts"
    rad.mkdir(parents=True)
    parts, words, blokovi, recenice, t = [], [], [], [], 0.6
    sil = rad / "s0.wav"
    ff("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.6", sil)
    parts.append(sil)
    n = 0
    for b in RAZGOVOR["blokovi"]:
        b0 = t
        for g, txt, pauza in b["recenice"]:
            f = rad / f"r{n}.wav"
            subprocess.run(["espeak-ng", *GLAS[g], "-w", str(f), txt], check=True)
            d = M2.wavdur(f)
            toks = txt.split()
            tot = sum(len(x) for x in toks)
            a0, a1, acc = t + 0.08, t + d - 0.12, 0
            for x in toks:
                s = a0 + (a1 - a0) * acc / tot
                acc += len(x)
                words.append({"w": x, "s": round(s, 3), "e": round(a0 + (a1 - a0) * acc / tot - 0.03, 3), "p": 0.95})
            recenice.append((g, round(a0, 3), round(a1, 3), txt))
            parts.append(f)
            t += d
            p = rad / f"r{n}p.wav"
            ff("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", str(pauza), p)
            parts.append(p)
            t += pauza
            n += 1
        blokovi.append((b["oznaka"], round(b0, 3), round(words[-1]["e"], 3)))
    lst = rad / "lista.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", lst.name, "-ar", "48000", "-ac", "1", "epizoda.wav", cwd=rad)
    video = base / "Sunčani4M snimke" / "epizoda 12 auto.mp4"
    video.parent.mkdir()
    nacrtaj_video(rad / "epizoda.wav", recenice, t + 0.4, video, rad)
    return video, words, blokovi, recenice


def nacrtaj_video(wav, recenice, trajanje, dst, rad):
    import cv2
    MK.H = VH  # draw_face crta majicu do dna kadra
    env = MK.envelope(wav, VFPS)
    n = int(trajanje * VFPS)
    govori = {g: np.zeros(n, bool) for g in SJEDALA}
    for g, a, b, _ in recenice:
        govori[g][int(a * VFPS):int(b * VFPS) + 1] = True
    rng = np.random.default_rng(12)
    trzaj = {g: np.convolve(rng.random(n) < 0.015, np.ones(4), "same") > 0 for g in SJEDALA}
    bg = np.zeros((VH, VW, 3), np.uint8)
    bg[:] = (88, 104, 112)
    cv2.rectangle(bg, (0, int(VH * .74)), (VW, VH), (60, 70, 82), -1)                       # sjedala
    cv2.rectangle(bg, (int(VW * .43), int(VH * .06)), (int(VW * .57), int(VH * .58)), (150, 170, 175), -1)  # prozor
    cv2.rectangle(bg, (int(VW * .43), int(VH * .06)), (int(VW * .57), int(VH * .58)), (50, 55, 60), 6)
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", rad / "f.ttf")
    # vremenski kod snimke iznad svake glave (vidi se i u 9:16 isječku)
    vf = ",".join(f"drawtext=fontfile=f.ttf:text='snimka %{{pts\\:hms}}':x=w*{x}-tw/2:y=h*0.045:fontsize=24:"
                  f"fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8" for x in (0.27, 0.72))
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{VW}x{VH}",
                          "-r", str(VFPS), "-i", "-", "-i", str(wav.resolve()), "-t", f"{trajanje:.2f}",
                          "-map", "0:v", "-map", "1:a", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(dst.resolve())],
                         stdin=subprocess.PIPE, cwd=rad)
    for k in range(n):
        img = bg.copy()
        tt = k / VFPS
        for g, (fx, fy, s, skin, hair, shirt) in SJEDALA.items():
            sway = 7 * np.sin(2 * np.pi * (0.11 if g == "A" else 0.15) * tt + (0 if g == "A" else 1.3))
            en = float(env[k]) if k < len(env) else 0.0
            m = min(1.0, 1.4 * en) if govori[g][k] else (0.25 if trzaj[g][k] else 0.0)
            MK.draw_face(img, int(fx * VW + sway), int(fy * VH + sway / 3), s, skin, hair, shirt, m)
        noise = rng.integers(-3, 4, img.shape, dtype=np.int16)
        p.stdin.write(np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg nije uspio")


def napravi_projekt(base):
    video, words, blokovi, recenice = napravi_epizodu(base)
    proj = base / "Sunčani4M ep12"
    run("prepare.py", video.parent, "--out", proj)          # 9:16 (zadano)
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    # govornici.py bi to našao iz glasa; ovdje iz poznatog scenarija (modeli nisu u sandboxu)
    save(proj / "govornici.json", {"govornici": [], "odsjecci": [
        {"od": a, "do": b, "govornik": "G1" if g == "A" else "G2"} for g, a, b, _ in recenice]})
    run("analyze.py", proj, check=False)
    an = load(proj / "analiza.json")
    tema = {b["oznaka"]: b["tema"] for b in RAZGOVOR["blokovi"]}
    an["teme"] = [{"od": a, "do": b, "naslov": tema[o], "sazetak": ""} for o, a, b in blokovi]
    # Claudeovi najjači trenuci (po jedan u dobrim blokovima)
    trenuci = {"greska_klima": ("Jeftina", "hook", "Loše ugrađena klima troši dvostruko više"),
               "prvi_koncert": ("Ljudi", "emocija", "Kutina pjeva s bendom na semaforu"),
               "odrzavanje": ("Ako", "savjet", "300 eura kvara ako preskočite servis")}
    an["trenuci"] = []
    for o, a, b in blokovi:
        if o in trenuci:
            prva, tip, opis = trenuci[o]
            w0 = next(w for w in words if a <= w["s"] <= b and w["w"] == prva)
            an["trenuci"].append({"od": w0["s"], "do": round(w0["s"] + 4, 2), "vrsta": tip, "ocjena": 5, "opis": opis})
    save(proj / "analiza.json", an)
    r = run("kadar.py", proj)
    run("plan.py", proj, "--stil", "podcast")
    return proj, blokovi, r.stdout


# ------------------------------------------------------------------ isječci (Claudeov dio simuliran)
def blok_isjecka(c, blokovi):
    def prek(a, b):
        return max(0.0, min(c["do"], b) - max(c["od"], a))
    return max(blokovi, key=lambda x: prek(x[1], x[2]))[0]


def isjecci(proj, blokovi):
    r = run("isjecci.py", proj, check=False)
    assert r.returncode == 1, r.stdout + r.stderr
    data = load(proj / "isjecci.json")
    shofe_redom = [(c["id"], c["heuristika"]["ocjena"]) for c in data["isjecci"]]
    po_bloku = {}
    for c in data["isjecci"]:
        o = blok_isjecka(c, blokovi)
        cl = CLAUDE[o]
        if o in po_bloku:  # drugi kandidat iz istog bloka: Claude ga ocijeni niže
            cl = dict(cl, ocjena=max(1, cl["ocjena"] - 3), razlog="Isti dio kao " + po_bloku[o] + ", slabiji početak.")
            cl.pop("naslov", None), cl.pop("hook", None)
        else:
            po_bloku[o] = c["id"]
        c.update({k: v for k, v in cl.items()})
    save(proj / "isjecci.json", data)
    run("isjecci.py", proj, "provjeri")
    ids = {o: i for o, i in po_bloku.items()}
    run("isjecci.py", proj, "odobri", ",".join(ids[o] for o in ODOBRI))
    for o, razlog in ODBACI.items():
        if o in ids:
            run("isjecci.py", proj, "odbaci", ids[o], "--razlog", razlog)
    r = run("isjecci.py", proj, "render")
    return ids, shofe_redom, r.stdout


def objava_i_naslovne(proj, ids):
    data = {c["id"]: c for c in load(proj / "isjecci.json")["isjecci"]}
    run("objava.py", "serija", "Sunčani4M", "--hashtagovi", "#suncani4m,#kutina",
        "--potpis", "Sunčani4M · podcast iz Renaulta 4, Kutina", "--napomena", "topao, lokalni ton; poziv na dijeljenje")
    odobreni = ",".join(ids[o] for o in ODOBRI)
    run("objava.py", proj, odobreni, "--serija", "Sunčani4M", check=False)
    ob = load(proj / "objava.json")
    for o in ODOBRI:
        vid = next(k for k in ob["videi"] if k.startswith(ids[o]))
        ob["videi"][vid]["mreze"] = json.loads(json.dumps(OBJAVA[o]))
    save(proj / "objava.json", ob)
    r = run("objava.py", proj, odobreni, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    for o in ODOBRI:
        run("naslovna.py", proj, ids[o], "--tekst", NASLOVNA[o])
    return data


# ------------------------------------------------------------------ kartice
CSS3 = """
.kand{display:flex;flex-direction:column;gap:14px}
.k{background:#18202a;border-radius:18px;padding:16px 20px;display:grid;grid-template-columns:62px 1fr auto;
 column-gap:14px;align-items:center}
.k .id{font-size:34px;font-weight:900;color:#f4a259}
.k .nas{font-size:26px;font-weight:800;line-height:1.2}
.k .sit{font-size:19px;color:#7f8c99;margin-top:4px}
.k .oc{font-size:34px;font-weight:900;text-align:right}
.k .oc small{display:block;font-size:16px;color:#7f8c99;font-weight:600}
.k.da{outline:3px solid #4caf7a}.k.ne{opacity:.55}
.zn{font-size:20px;font-weight:900;letter-spacing:.08em}.zn.da{color:#4caf7a}.zn.ne{color:#c8553d}
.bubble.mali{font-size:34px;padding:18px 24px}
.hook{display:inline-block;background:#f4a259;color:#1b1206;font-weight:900;font-size:34px;padding:10px 18px;
 border-radius:12px}
"""


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def kartica_kandidati(cands, preskoceno):
    rows = ""
    for c in cands:
        st = c.get("status")
        cls, zn = ("da", "✓ ODOBREN") if st == "odobren" else (("ne", "✗ ODBAČEN") if st == "odbacen" else ("", ""))
        rows += (f'<div class="k {cls}"><div class="id">{e(c["id"])}</div><div><div class="nas">{e(c["naslov"])}</div>'
                 f'<div class="sit">snimka {mmss(c["od"])}–{mmss(c["do"])} · {round(c["trajanje"])} s · '
                 f'<span class="zn {cls}">{zn}</span></div></div>'
                 f'<div class="oc">{c["ocjena"]}/10<small>Shofe {c["heuristika"]["ocjena"]:.1f}</small></div></div>')
    body = ('<div class="top">PREGLED M3 · ISJEČCI ZA MREŽE</div><div class="korak">1 · KANDIDATI</div>'
            '<div><div class="tko" style="text-align:right">MARKO</div>'
            '<div class="bubble">Napravi isječke iz ove epizode.</div></div>'
            '<div><div class="tko">SHOFE + CLAUDE</div>'
            f'<div class="kand">{rows}</div></div>'
            f'<div class="odg">{M2.ln("i", "nije predložio: " + e(", ".join(preskoceno)))}</div>'
            '<div><div class="tko" style="text-align:right">MARKO</div>'
            '<div class="bubble mali">Uzmi K1, K2 i K3. K4 ne.</div></div>')
    return body


def kartica_isjecak(n, c, rd):
    linije = [M2.ln("i", f"iz snimke {mmss(c['od'])}–{mmss(c['do'])} → {rd['trajanje']:.0f} s (pauze izrezane)"),
              M2.ln("i", f"stil {e(rd['stil'])}, titlovi, kadar prati onoga tko govori"),
              M2.ln("plus", f"Claude {c['ocjena']}/10: {e(c['razlog'])}")]
    return (f'<div class="top">PREGLED M3 · ISJEČCI ZA MREŽE</div><div class="korak">{n} · {e(c["id"])}</div>'
            f'<h1>{e(c["naslov"])}</h1><div><div class="tko">HOOK</div><div class="hook">{e(c["hook"])}</div></div>'
            f'<div class="odg">{"".join(linije)}</div>')


def demo_isjecci(proj, ids, rad):
    data = load(proj / "isjecci.json")
    cands = data["isjecci"]
    by = {c["id"]: c for c in cands}
    dobri = set(ids)
    preskoceno = [{"cavrljanje": "čavrljanje na početku", "lutanje": "priču bez poante",
                   "nedovrseno": "nedovršenu priču", "odjava": "odjavu"}[b["oznaka"]]
                  for b in RAZGOVOR["blokovi"] if b["oznaka"] not in dobri]
    trajanje = dur(next((proj.parent / "Sunčani4M snimke").glob("*.mp4")))
    kartice = [
        M2.kartica(0, "PROBNA EPIZODA", None, [], None, None, naslov="Sunčani4M u Renaultu 4",
                   tekst=[f"{mmss(trajanje)} razgovora, dva voditelja, vodoravna kamera. Glasovi su sintetski, a "
                          "na slici je <b>vrijeme snimke</b> — vidi se odakle je isječak.",
                          "U epizodi su 4 dijela za mreže i 4 koja to nisu: čavrljanje, lutanje, nedovršena priča "
                          "i odjava.", "Sve dalje je napravio Shofe, a Claude je ocijenio kandidate i napisao "
                          "hookove."]).replace("PREGLED M2 · MONTAŽA PO NAREDBI", "PREGLED M3 · ISJEČCI ZA MREŽE"),
        kartica_kandidati(cands, preskoceno),
    ]
    odob = [c for c in cands if c.get("status") == "odobren"]
    for n, c in enumerate(odob, 2):
        kartice.append(kartica_isjecak(n, c, c["render"]))
    kartice.append(M2.kartica(0, "UZ SVAKI ISJEČAK", None,
                              [M2.ln("i", "<q>K1_….mp4</q> — video 9:16 za Reels, TikTok, Shorts"),
                               M2.ln("i", "<q>K1_….srt</q> i <q>K1_….fcpxml</q> — titlovi i DaVinci timeline"),
                               M2.ln("i", "<q>K1_….objava.txt</q> — tekst za Instagram, TikTok i YouTube"),
                               M2.ln("i", "<q>K1_….naslovna_9x16.jpg</q> i <q>_16x9.jpg</q> — naslovne sličice"),
                               M2.ln("plus", "glavni video i njegove verzije ostaju netaknuti")],
                              None, None, naslov="Spremno za objavu")
                   .replace("PREGLED M2 · MONTAŽA PO NAREDBI", "PREGLED M3 · ISJEČCI ZA MREŽE"))
    png = M2.snimi_kartice(kartice, rad, extra_css=CSS3)
    plan = [("k", png[0], 6.0), ("k", png[1], 9.0)]
    for i, c in enumerate(odob):
        v = proj / c["render"]["datoteka"]
        plan += [("k", png[2 + i], 5.0), ("v", v, 0, dur(v))]
    plan.append(("k", png[-1], 5.5))
    dijelovi = []
    for i, p in enumerate(plan):
        out = rad / f"i_dio_{i:02d}.mp4"
        if p[0] == "k":
            M2.dio_kartica(p[1], p[2], out)
        else:
            M2.dio_video(p[1], p[2], p[3], out)
        dijelovi.append(out)
    out = DEMO / "M3_isjecci.mp4"
    M2.spoji(dijelovi, out, rad)
    M2.provjeri_velicinu(out)
    return png


# ------------------------------------------------------------------ kadar: izvorno 16:9 + gotovo 9:16
KW, KH = 1280, 720
OW, OH, OX, OY = 832, 468, 28, 150            # izvorna snimka na platnu
RW, RH, RX, RY = 351, 624, 900, 70            # gotov 9:16 na platnu


def okviri_kadra(kadrovi, od, do, vw=VW, vh=VH):
    """Pravokutnici (x, w) izreza u koordinatama umanjene izvorne snimke za kadrove u [od, do), s vremenom
    od početka isječka: [(a, b, x, w)]."""
    cw = vh * 9 / 16
    s = OW / vw
    out = []
    for k in kadrovi:
        a, b = max(k["od"], od), min(k["do"], do)
        if b <= a:
            continue
        x = k["crop_x"] * (vw - cw)
        out.append((round(a - od, 3), round(b - od, 3), round(x * s), round(cw * s)))
    return out


def kadar_dio(proj, orig, kadrovi, od, do, out, rad):
    d = do - od
    boxes = ",".join(f"drawbox=x={x}:y=0:w={w}:h={OH}:color=0xf4a259:t=5:enable='between(t,{a},{b})'"
                     for a, b, x, w in okviri_kadra(kadrovi, od, do))
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", rad / "f.ttf")
    lab = ("drawtext=fontfile=f.ttf:text='{t}':x={x}:y={y}:fontsize={s}:fontcolor={c}")
    fc = (f"color=c=0x11161d:s={KW}x{KH}:r=30:d={d:.3f}[bg];"
          f"[0:v]scale={OW}:{OH},{boxes}[o];[1:v]scale={RW}:{RH}[r];"
          f"[bg][o]overlay={OX}:{OY}[t1];[t1][r]overlay={RX}:{RY},"
          + lab.format(t="PREGLED M3 · KADAR PRATI GOVORNIKA", x=OX, y=40, s=22, c="0x7f8c99") + ","
          + lab.format(t="Vodoravna snimka iz auta. Narančasti okvir je dio koji Shofe izreže za 9\\:16.",
                       x=OX, y=80, s=21, c="0xe9eef3") + ","
          + lab.format(t="Kad progovori drugi, rez na njega — nikad švenk preko praznog prostora.",
                       x=OX, y=OY + OH + 30, s=21, c="0xcfd8e0") + ","
          + lab.format(t="IZVORNO 16\\:9", x=OX, y=OY - 30, s=18, c="0xf4a259") + ","
          + lab.format(t="REEL 9\\:16", x=RX, y=RY + RH + 14, s=18, c="0xf4a259")
          + f",fade=in:d=0.2,fade=out:st={d - 0.25:.3f}:d=0.25[v]")
    ff("-ss", f"{od:.3f}", "-t", f"{d:.3f}", "-i", orig.resolve(), "-ss", f"{od:.3f}", "-t", f"{d:.3f}",
       "-i", (proj / "source.mp4").resolve(), "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
       "-af", f"afade=in:d=0.15,afade=out:st={d - 0.25:.3f}:d=0.25", *M2.ENC, out.resolve(), cwd=rad)


def demo_kadar(proj, blokovi, rad):
    kj = load(proj / "kadar.json")
    (c,) = kj["klipovi"]
    orig = Path(c.get("file") or next((proj.parent / "Sunčani4M snimke").glob("*.mp4")))
    if not orig.exists():
        orig = next((proj.parent / "Sunčani4M snimke").glob("*.mp4"))
    b = {o: (a, z) for o, a, z in blokovi}
    dijelovi = []
    # uvodno čavrljanje (brze izmjene) + pitanje i odgovor o održavanju klime
    for i, (od, do) in enumerate([(0.0, b["cavrljanje"][1] + 1.0), (b["odrzavanje"][0] - 0.3, b["odrzavanje"][0] + 12.0)]):
        out = rad / f"k_dio_{i}.mp4"
        kadar_dio(proj, orig, c["kadrovi"], od, do, out, rad)
        dijelovi.append(out)
    out = DEMO / "M3_kadar.mp4"
    M2.spoji(dijelovi, out, rad)
    M2.provjeri_velicinu(out)


# ------------------------------------------------------------------ objava + naslovne (slika)
CSS_OB = """
body{height:auto;padding:30px 34px;display:block;overflow:visible}
.red{display:flex;gap:26px;align-items:flex-start;margin-top:18px}
.slike{display:flex;flex-direction:column;gap:14px}
.slike img{border-radius:10px;display:block}
.mr{flex:1;display:flex;flex-direction:column;gap:14px}
.mreza{background:#18202a;border-radius:14px;padding:14px 18px}
.mreza h3{font-size:17px;letter-spacing:.1em;color:#f4a259;font-weight:900;margin-bottom:8px}
.mreza .t{font-size:16px;line-height:1.42;color:#e9eef3;white-space:pre-wrap;font-weight:600}
.mreza .t b{color:#fff;font-weight:900}
.mreza .h{color:#62b6cb}
.cap{font-size:14px;color:#7f8c99;margin-top:4px}
"""


def demo_objava(proj, ids, rad):
    data = {c["id"]: c for c in load(proj / "isjecci.json")["isjecci"]}
    ob = load(proj / "objava.json")
    kid = ids["greska_klima"]
    c = data[kid]
    video = proj / c["render"]["datoteka"]
    vid = next(k for k in ob["videi"] if k.startswith(kid))
    m = ob["videi"][vid]["mreze"]
    txt = video.with_suffix(".objava.txt").read_text(encoding="utf-8-sig")

    def blok(ime):  # gotov tekst za kopiranje iz .objava.txt (s potpisom i stalnim hashtagovima)
        dio = txt.split(f"=== {ime}")[1].split("\n=== ")[0]
        komadi = [x.strip("\n") for x in dio.split("-" * 40)]
        return [k for k in komadi[1::2]]

    def fmt(s):
        return "<br>".join(e(r) if not r.startswith("#") else f'<span class="h">{e(r)}</span>'
                           for r in s.split("\n"))
    ig, tt, yt = blok("INSTAGRAM")[0], blok("TIKTOK")[0], blok("YOUTUBE")
    n9 = video.with_name(video.stem + ".naslovna_9x16.jpg").resolve().as_uri()
    n16 = video.with_name(video.stem + ".naslovna_16x9.jpg").resolve().as_uri()
    body = (f'<div class="top">PREGLED M3 · OBJAVA ZA {e(kid)} „{e(c["naslov"])}“ — SERIJA SUNČANI4M</div>'
            f'<p style="font-size:17px;margin-top:10px">Marko: „napiši tekstove za objavu i napravi naslovne“. Claude '
            f'piše posebno za svaku mrežu; Shofe provjeri pravila (najviše 5 hashtagova, duljine) i doda potpis i '
            f'stalne hashtagove serije. Ovo je <b>{e(video.stem)}.objava.txt</b> i dvije naslovne sličice.</p>'
            f'<div class="red"><div class="slike"><img src="{n9}" width="300">'
            f'<div class="cap">9:16 (Reels, TikTok, Shorts) — lice i tekst u sredini 3:4 za Instagram profil</div>'
            f'</div><div class="mr"><img src="{n16}" width="560" style="border-radius:10px">'
            f'<div class="cap">16:9 za YouTube — krupno lice iz izvorne vodoravne snimke</div>'
            f'<div class="mreza"><h3>INSTAGRAM</h3><div class="t">{fmt(ig)}</div></div>'
            f'<div class="mreza"><h3>TIKTOK</h3><div class="t">{fmt(tt)}</div></div>'
            f'<div class="mreza"><h3>YOUTUBE SHORTS</h3><div class="t"><b>{e(yt[0])}</b><br><br>{fmt(yt[1])}'
            f'</div></div></div></div>')
    assert m["instagram"]["opis"].split("\n")[0] in ig
    png = M2.snimi_kartice([body], rad, size=(980, 900), full=True, extra_css=CSS_OB)[0]
    out = DEMO / "M3_objava.png"
    shutil.copy(png, out)
    shutil.copy(video.with_name(video.stem + ".naslovna_kandidati.jpg"), DEMO / "M3_naslovna.jpg")
    for f in (out, DEMO / "M3_naslovna.jpg"):
        print(f"  {f.relative_to(ROOT)}  {f.stat().st_size / 1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radna", type=Path, default=None, help="radna mapa (ostaje nakon kraja)")
    a = ap.parse_args()
    if not shutil.which("espeak-ng"):
        sys.exit("Treba espeak-ng (sintetski govor): apt install espeak-ng")
    DEMO.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shofe demo m3 ") as tmp:
        base = a.radna or Path(tmp)
        if a.radna:
            shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        os.environ["SHOFE_PODACI"] = str(base / "podaci")  # serija Sunčani4M ne ide u Markove postavke
        proj, blokovi, _ = napravi_projekt(base)
        ids, _, _ = isjecci(proj, blokovi)
        objava_i_naslovne(proj, ids)
        rad = base / "demo_rad"
        rad.mkdir()
        demo_isjecci(proj, ids, rad)
        demo_kadar(proj, blokovi, rad)
        demo_objava(proj, ids, rad)
    print("Gotovo →", DEMO)


if __name__ == "__main__":
    main()
