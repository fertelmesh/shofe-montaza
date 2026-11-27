"""Demo za pregled prekretnice M4 (podcast Sunčani4M) → demo/ (videi ≤ 8 MB, slika).

  python tests/make_demo_m4.py                 sve
  python tests/make_demo_m4.py --radna MAPA    radna mapa ostaje (za provjeru)

Probna epizoda 12 (izmišljena): Marko i Ivan u Renaultu 4, na stražnjem sjedalu bend Kutina koji usred
epizode zasvira pjesmu. Snimaju TRI kamere i diktafon, svaki uključen u drugom trenutku (kao u autu):
  GOPR0412.MP4             široka kamera (sva trojica), krenula 4,2 s PRIJE diktafona, zvuk s jekom
  MVI_2203.MP4             krupni kadar Marka, krenula 2,5 s NAKON diktafona
  VID_20261127_ivan.mp4    Ivanov mobitel USPRAVNO (720×1280), krenuo 6,1 s nakon, ugasio se 9 s prije kraja
  ZOOM0012.WAV             diktafon (najbolji zvuk) = glavni izvor
Glasovi su sintetski (espeak-ng), bend je sintetski (make_nastup), usta se miču po glasu. Na svakoj kameri je
oznaka kamere i vrijeme U TOJ DATOTECI, pa se vidi da su kamere krenule u različito vrijeme.

Cijeli put kao na Markovom laptopu: sinkro.py → rezija.py → (transkript + govornici iz scenarija: modeli nisu
u sandboxu) → rezija.py → nastupi.py dodaj (pjesma) → rezija.py → analyze.py + Claudeove teme → plan.py (Podcast)
→ spica.py (uvodna iza najave + odjavna) → render.py (video, SRT, poglavlja, DaVinci + EDL) → epizoda.py mp3 →
objava.py epizoda (Claudeov tekst) → isjecci.py (razgovor + pjesma, 9:16 iz originalnih kamera).

Što nastaje:
  demo/M4_epizoda.mp4   kartice + mozaik (tri kamere i program: tko govori → koja kamera, pjesma u ritmu) +
                        dijelovi gotove epizode (najava → uvodna špica, pjesma, odjava) s oznakom poglavlja
  demo/M4_isjecci.mp4   dva uspravna isječka iz podcasta: razgovor (krupni kadrovi, podijeljen kadar) i pjesma
  demo/M4_paket.png     sve ostalo za objavu: poglavlja, YouTube opis, tekst za Spotify/Apple, MP3, DaVinci timeline

Treba ffmpeg, espeak-ng, opencv-python-headless, Pillow i Playwright s Chromiumom (~10 min).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_demo_m2 as M2  # noqa: E402  (ff, run, kartice, slaganje videa)
import make_kadar_klip as MK  # noqa: E402  (crtanje lica)
import make_nastup as MN  # noqa: E402  (sintetski bend, pljesak)

ROOT, FONTS, DEMO = M2.ROOT, M2.FONTS, M2.DEMO
sys.path.insert(0, str(ROOT / "shofe-montaza" / "scripts"))
ff, run, load, save, e, dur = M2.ff, M2.run, M2.load, M2.save, M2.e, M2.dur

SR = 48000
FPS = 25
GLAS = {"A": ["-v", "hr", "-s", "145", "-p", "40"], "B": ["-v", "hr+f3", "-s", "155", "-p", "60"]}
IME = {"A": "Marko", "B": "Ivan"}
PJESMA_NAZIV = "Bend Kutina – Ljeto u Renaultu"
BPM = 112
STRUKTURA = [("I", 2), ("A", 4), ("B", 4), ("A", 4), ("B", 4), ("C", 2), ("B", 4)]   # 24 takta ≈ 51 s

# Scenarij epizode: blok = tema (Claude bi je napisao iz transkripta), rečenice (tko, tekst, pauza poslije).
EPIZODA = [
    {"oznaka": "najava", "tema": None, "recenice": [
        ("B", "Ljudi su na semaforu otvorili prozore i pjevali s nama.", 0.4),
        ("A", "To je bio najbolji trenutak cijelog ljeta.", 1.6)]},
    {"oznaka": "dobrodosli", "tema": "Dobrodošli u Renault",
     "sazetak": "Marko i Ivan kreću kroz Kutinu, na stražnjem sjedalu je bend Kutina.", "recenice": [
        ("A", "Dobro došli u novu epizodu podcasta Sunčani četiri M.", 0.4),
        ("A", "Ja sam Marko, a sa mnom je, kao i uvijek, Ivan.", 0.5),
        ("B", "Bok svima! Danas se vozimo kroz Kutinu po lijepom suncu.", 0.5),
        ("A", "Na stražnjem sjedalu imamo goste, bend Kutina.", 0.4),
        ("B", "Kasnije će nam zasvirati jednu svoju pjesmu, uživo u autu.", 0.5),
        ("A", "Ali prvo, Ivane, kako je prošlo ljeto?", 0.6)]},
    {"oznaka": "klima", "tema": "Vruće ljeto i klima",
     "sazetak": "Ljeto je bilo rekordno vruće, cijelo ljeto su ugrađivali klime po Kutini.", "recenice": [
        ("B", "Ljeto je bilo stvarno vruće, u autu je bilo i četrdeset stupnjeva.", 0.5),
        ("B", "Cijelo ljeto smo ugrađivali klime po Kutini i okolici.", 0.4),
        ("A", "Koliko ste klima ugradili?", 0.4),
        ("B", "Preko dvjesto, a najviše poziva bilo je u srpnju.", 0.5),
        ("A", "Jesu li ljudi čekali na red?", 0.4),
        ("B", "Jesu, neki i po dva tjedna.", 0.3),
        ("A", "Dva tjedna?", 0.2),
        ("B", "Da.", 0.2),
        ("A", "Po toj vrućini!", 0.2),
        ("B", "Baš tako.", 0.7)]},
    {"oznaka": "greska", "tema": "Najveća greška kod kupnje klime",
     "sazetak": "Ivan objašnjava zašto loše ugrađena klima troši dvostruko više struje i što pitati prije kupnje.",
     "recenice": [
        ("A", "Koja je najveća greška kad netko kupuje klimu?", 0.5),
        ("B", "Ljudi gledaju samo cijenu uređaja, a ne tko ga ugrađuje.", 0.4),
        ("B", "Loše ugrađena klima troši dvostruko više struje.", 0.4),
        ("B", "Prošle godine smo u Kutini imali četrdeset takvih slučajeva.", 0.5),
        ("A", "Što onda treba pitati prije kupnje?", 0.4),
        ("B", "Pitajte tko ugrađuje i daje li garanciju na ugradnju.", 0.4),
        ("B", "I jednom godišnje napravite servis, to je oko osamdeset eura.", 0.4),
        ("A", "Osamdeset eura sada, ili kvar od tristo eura kasnije.", 0.9)]},
    {"oznaka": "najava_pjesme", "tema": "Bend Kutina",
     "sazetak": "Najava benda Kutina i njihove pjesme o ljetu u Renaultu.", "recenice": [
        ("A", "A sada ono na što svi čekate.", 0.4),
        ("B", "Bend Kutina i pjesma Ljeto u Renaultu!", 0.8)]},
    {"oznaka": "pjesma"},
    {"oznaka": "bend", "tema": "Priča o bendu",
     "sazetak": "Bend svira zajedno pet godina, prvi koncert imali su baš u ovom autu.", "recenice": [
        ("A", "Bravo, dečki, to je bilo odlično!", 0.5),
        ("B", "Oni sviraju zajedno već pet godina.", 0.4),
        ("A", "A prvi koncert su imali baš u ovom autu.", 0.4),
        ("B", "Na semaforu su ljudi otvarali prozore i pjevali s njima.", 0.5),
        ("A", "Sljedeći petak sviraju na trgu u Kutini.", 0.4),
        ("B", "Ulaz je besplatan, dođite svi!", 0.7)]},
    {"oznaka": "odjava", "tema": "Odjava",
     "sazetak": "Zahvala bendu i slušateljima, poziv na koncert i sljedeću epizodu.", "recenice": [
        ("A", "To je sve za danas. Hvala bendu Kutina!", 0.4),
        ("B", "I hvala vama što ste se vozili s nama.", 0.4),
        ("A", "Pretplatite se, a vidimo se sljedeći petak.", 0.4),
        ("B", "Bok!", 1.2)]},
]

# Kamere: pomak (gdje je 0 s datoteke na crti diktafona), kraj na crti diktafona (None = do kraja + 1 s),
# veličina, osobe [(tko, x, y, veličina lica)], boja pozadine (BGR), zvuk ('jeka' | 'blizu' | 'mobitel').
KAMERE = {
    "GOPR0412.MP4": dict(pomak=-4.2, kraj=None, w=1280, h=720, oznaka="KAM 1 · ŠIROKA",
                         osobe=[("C", 0.5, 0.36, 78), ("A", 0.24, 0.53, 104), ("B", 0.76, 0.54, 100)],
                         boja=(96, 108, 116), zvuk="jeka"),
    "MVI_2203.MP4": dict(pomak=2.5, kraj=None, w=1280, h=720, oznaka="KAM 2 · MARKO",
                         osobe=[("A", 0.5, 0.47, 210)], boja=(92, 120, 100), zvuk="blizu"),
    "VID_20261127_ivan.mp4": dict(pomak=6.1, kraj=-9.0, w=720, h=1280, oznaka="MOBITEL · IVAN",
                                  osobe=[("B", 0.5, 0.42, 200)], boja=(100, 96, 132), zvuk="mobitel"),
}
LICA = {"A": ((140, 170, 215), (40, 50, 60), (150, 80, 60)), "B": ((120, 150, 200), (30, 60, 110), (70, 110, 60)),
        "C": ((110, 140, 190), (25, 25, 30), (60, 60, 150))}
GLAVNI = "ZOOM0012.WAV"

# Što bi Claude napisao: opis epizode (bez vremena — poglavlja dodaje Shofe).
YOUTUBE = {"naslov": "Bend Kutina svira uživo u Renaultu 4 + najveća greška kod kupnje klime",
           "opis": "Marko i Ivan voze se kroz Kutinu po vrućem ljetu: zašto loše ugrađena klima troši dvostruko "
                   "više struje i što pitati prije kupnje. Na stražnjem sjedalu bend Kutina — i usred vožnje "
                   "zasviraju pjesmu „Ljeto u Renaultu”, uživo u autu.\n\nKoncert benda Kutina je sljedeći petak "
                   "na trgu, ulaz besplatan. Pretplati se za nove vožnje!",
           "hashtagovi": ["#suncani4m", "#kutina", "#podcast"]}
PODCAST = {"naslov": "Bend Kutina uživo u autu i najveća greška kod kupnje klime",
           "opis": "Marko i Ivan voze se kroz Kutinu nakon najvrućeg ljeta dosad. Ivan priča kako su ugradili "
                   "preko dvjesto klima i zašto loše ugrađena klima troši dvostruko više struje — i što pitati "
                   "prije kupnje da vas servis ne košta tristo eura. Na stražnjem sjedalu je bend Kutina, koji "
                   "usred vožnje zasvira pjesmu „Ljeto u Renaultu”. Za kraj: gdje ih sljedeći petak čuti uživo.",
           "broj": "12"}
EPIZODA_NASLOV = "Bend Kutina u Renaultu"

# Claudeove ocjene kandidata za isječke (po bloku epizode); pjesma ima svoj kandidat.
OCJENE = {
    "greska": dict(ocjena=9, razlog="Jasna greška s brojem iz Kutine i savjetom koji štedi novac; stoji sama.",
                   naslov="Najveća greška kod kupnje klime", hook="Ne gledaj samo cijenu klime"),
    "klima": dict(ocjena=7, razlog="Brza izmjena i dobar broj (dvjesto klima), ali bez poante.",
                  naslov="Dva tjedna čekanja na klimu", hook="Dva tjedna čekanja po vrućini"),
    "bend": dict(ocjena=6, razlog="Lijepa priča o prvom koncertu, ali bolje uz pjesmu.",
                 naslov="Prvi koncert u Renaultu", hook="Prvi koncert u autu"),
    "dobrodosli": dict(ocjena=3, razlog="Uvod epizode, nema poante za mreže."),
    "najava": dict(ocjena=3, razlog="Najava epizode, ponavlja se kasnije."),
    "najava_pjesme": dict(ocjena=2, razlog="Samo najava pjesme."),
    "odjava": dict(ocjena=1, razlog="Odjava epizode."),
    "pjesma": dict(ocjena=9, razlog="Refren uživo u autu, najjači trenutak epizode.",
                   naslov="Ljeto u Renaultu (uživo)", hook="Bend uživo u Renaultu 4"),
}
ODOBRI = ["greska", "klima", "pjesma"]


# ------------------------------------------------------------------ zvuk epizode (diktafon)
def decode(path, sr=SR):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def write_wav(path, x, sr=SR):
    import wave
    y = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())


def napravi_zvuk(rad):
    """Sintetski govor + pjesma + pljesak na crti diktafona → (zvuk, riječi, rečenice, blokovi, pjesma)."""
    rad.mkdir(parents=True, exist_ok=True)
    MN.SR = SR
    komadi, words, recenice, blokovi, t = [], [], [], [], 0.8
    pjesma = None
    n = 0
    for b in EPIZODA:
        b0 = t
        if b["oznaka"] == "pjesma":
            y = MN.pjesma_refren(seed=11, bpm=BPM, struktura=STRUKTURA, kraj=2.5) * 1.25   # bend glasniji od govora
            komadi.append((t, y))
            od = t
            t += len(y) / SR
            pl = MN.pljesak(3.5)
            komadi.append((t - 0.3, pl * 1.6))
            pjesma = {"od": round(od, 3), "do": round(t + 3.2, 3), "sviranje_do": round(t, 3)}
            t += 3.5
            blokovi.append(("pjesma", round(od, 3), round(t, 3)))
            continue
        for g, txt, pauza in b["recenice"]:
            f = rad / f"r{n}.wav"
            subprocess.run(["espeak-ng", *GLAS[g], "-w", str(f), txt], check=True)
            y = decode(f)
            y = 0.5 * y / (np.abs(y).max() + 1e-9)
            d = len(y) / SR
            toks = txt.split()
            tot = sum(len(x) for x in toks)
            a0, a1, acc = t + 0.08, t + d - 0.12, 0
            for x in toks:
                s = a0 + (a1 - a0) * acc / tot
                acc += len(x)
                words.append({"w": x, "s": round(s, 3), "e": round(a0 + (a1 - a0) * acc / tot - 0.03, 3), "p": 0.95})
            recenice.append((g, round(a0, 3), round(a1, 3), txt))
            komadi.append((t, y))
            t += d + pauza
            n += 1
        blokovi.append((b["oznaka"], round(b0, 3), round(words[-1]["e"], 3)))
    total = t + 0.6
    x = np.zeros(int(total * SR) + SR)
    for a, y in komadi:
        i = int(a * SR)
        x[i:i + len(y)] += y
    x = x[:int(total * SR)]
    x += np.random.default_rng(1).normal(0, 0.002, len(x))       # šum auta
    return x, words, recenice, blokovi, pjesma


def zvuk_kamere(x, pomak, kraj, vrsta, seed):
    """Zvuk mikrofona kamere: isti događaji na crti diktafona [pomak, kraj] + boja mikrofona + šum."""
    import make_sinkro as MS
    MS.SR = SR
    n = int(round((kraj - pomak) * SR))
    out = np.zeros(n)
    i0 = int(round(pomak * SR))
    lo, hi = max(0, i0), min(len(x), i0 + n)
    out[lo - i0:hi - i0] = x[lo:hi]
    if vrsta == "jeka":
        d = int(0.023 * SR)
        out[d:] += 0.35 * out[:-d]
        out = MS.lowpass(out, 6000)
    elif vrsta == "mobitel":
        out = MS.highpass(MS.lowpass(out, 3400), 250) * 1.4
    rng = np.random.default_rng(seed)
    return 0.7 * out + rng.normal(0, 0.006, n)


# ------------------------------------------------------------------ kamere
def ovojnica(x, fps=FPS):
    hop = SR // fps
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1))
    return rms / (np.percentile(rms, 95) + 1e-6)


def nacrtaj_kameru(ime, k, x, recenice, pjesma, rad, dst):
    import cv2
    W, H = k["w"], k["h"]
    total = len(x) / SR
    pomak = k["pomak"]
    kraj = total + 1.0 if k["kraj"] is None else total + k["kraj"]
    trajanje = kraj - pomak
    wav = rad / f"_{ime}.wav"
    write_wav(wav, zvuk_kamere(x, pomak, kraj, k["zvuk"], seed=len(ime)))
    env = ovojnica(x)
    govor = {g: np.zeros(len(env) + 1, bool) for g in "AB"}
    for g, a, b, _ in recenice:
        govor[g][int(a * FPS):int(b * FPS) + 1] = True
    p_od, p_do = pjesma["od"], pjesma["sviranje_do"]
    beat = 60.0 / BPM
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:] = k["boja"]
    if W > H:   # unutrašnjost auta: sjedala, prozor
        cv2.rectangle(bg, (0, int(H * .8)), (W, H), tuple(int(c * .62) for c in k["boja"]), -1)
        cv2.rectangle(bg, (int(W * .38), int(H * .05)), (int(W * .62), int(H * .22)), (170, 185, 190), -1)
    else:
        cv2.rectangle(bg, (0, int(H * .82)), (W, H), tuple(int(c * .62) for c in k["boja"]), -1)
    rng = np.random.default_rng(len(ime))
    sumovi = [rng.integers(-3, 4, bg.shape, dtype=np.int16) for _ in range(6)]
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", rad / "f.ttf")
    fs = 26 if W > H else 30
    vf = (f"drawtext=fontfile=f.ttf:text='{k['oznaka']}  %{{pts\\:hms}}':x=24:y=22:fontsize={fs}:"
          f"fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8")
    MK.H = H
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav.name, "-t", f"{trajanje:.3f}", "-map", "0:v",
                          "-map", "1:a", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                          "-g", "50", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(dst.resolve())],
                         stdin=subprocess.PIPE, cwd=rad)
    for fr in range(int(trajanje * FPS)):
        img = bg.copy()
        t = pomak + fr / FPS                   # vrijeme na crti diktafona
        kk = int(round(t * FPS))
        en = float(env[kk]) if 0 <= kk < len(env) else 0.0
        u_pjesmi = p_od <= t <= p_do
        ritam = np.sin(2 * np.pi * (t - p_od) / (2 * beat)) if u_pjesmi else 0.0
        for g, fx, fy, s in k["osobe"]:
            if g == "C":
                m = min(1.0, 1.2 * en) if u_pjesmi and (t - p_od) > 4.3 else 0.0     # pjeva (bez uvoda)
                sway = 10 * ritam
            else:
                m = min(1.0, 1.4 * en) if 0 <= kk < len(govor[g]) and govor[g][kk] else 0.0
                sway = (6 * ritam if u_pjesmi else 6 * np.sin(2 * np.pi * (0.12 if g == "A" else 0.16) * t))
            cx, cy = int(fx * W + sway), int(fy * H + abs(sway) / 4)
            MK.draw_face(img, cx, cy, s, *LICA[g], m)
            if g == "C":   # gitara
                gx, gy = cx + int(s * 0.9), cy + int(s * 1.9)
                cv2.ellipse(img, (gx, gy), (int(s * .75), int(s * .5)), -20, 0, 360, (40, 90, 150), -1)
                cv2.circle(img, (gx, gy), int(s * .16), (20, 30, 40), -1)
                cv2.line(img, (gx, gy), (gx - int(s * 1.9), gy - int(s * .7)), (30, 60, 90), max(3, s // 9))
                ruka = int(s * .35 * np.sin(2 * np.pi * (t - p_od) / (beat / 2))) if u_pjesmi else 0
                cv2.circle(img, (gx + int(s * .1), gy + ruka), int(s * .14), LICA["C"][0], -1)
        img = np.clip(img.astype(np.int16) + sumovi[fr % 6], 0, 255).astype(np.uint8)
        p.stdin.write(img.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg nije uspio: {ime}")
    wav.unlink()


def napravi_snimke(base):
    rad = base / "tts"
    x, words, recenice, blokovi, pjesma = napravi_zvuk(rad)
    snim = base / "Sunčani4M ep12 snimke"
    snim.mkdir()
    write_wav(snim / GLAVNI, x)
    for ime, k in KAMERE.items():
        nacrtaj_kameru(ime, k, x, recenice, pjesma, rad, snim / ime)
    return snim, words, recenice, blokovi, pjesma


# ------------------------------------------------------------------ projekt (put kao na laptopu)
def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def napravi_projekt(base):
    snim, words, recenice, blokovi, pjesma = napravi_snimke(base)
    proj = base / "Sunčani4M ep12"
    log = {}
    log["sinkro"] = run("sinkro.py", snim, "--out", proj).stdout
    run("rezija.py", proj)
    poc = float(load(proj / "rezija.json").get("pocetak", 0.0)) if (proj / "rezija.json").exists() else 0.0
    sh = lambda v: round(v - poc, 3)  # noqa: E731  crta diktafona → vrijeme epizode (source.mp4)
    words = [dict(w, s=sh(w["s"]), e=sh(w["e"])) for w in words]
    recenice = [(g, sh(a), sh(b), txt) for g, a, b, txt in recenice]
    blokovi = [(o, sh(a), sh(b)) for o, a, b in blokovi]
    pjesma = {k: sh(v) for k, v in pjesma.items()}
    save(proj / "transcript.json", {"language": "hr", "model": "mock", "words": words})
    # govornici.py bi to našao iz glasa; ovdje iz scenarija (modeli nisu u sandboxu)
    save(proj / "govornici.json", {"govornici": [{"id": "G1", "ime": "Marko"}, {"id": "G2", "ime": "Ivan"}],
                                   "odsjecci": [{"od": a, "do": b, "govornik": "G1" if g == "A" else "G2"}
                                                for g, a, b, _ in recenice]})
    run("rezija.py", proj, "--analiza")
    run("nastupi.py", proj, "dodaj", f"{mmss(pjesma['od'])}-{mmss(pjesma['do'])}", "--naziv", PJESMA_NAZIV)
    log["rezija"] = run("rezija.py", proj).stdout
    run("analyze.py", proj, check=False)
    an = load(proj / "analiza.json")
    an["teme"] = []
    for b in EPIZODA:
        if b.get("tema"):
            o, a, z = next(x for x in blokovi if x[0] == b["oznaka"])
            an["teme"].append({"od": a, "do": z, "naslov": b["tema"], "sazetak": b["sazetak"]})
    an["teme"][0]["od"] = 0.0          # najava pripada prvoj temi
    an["trenuci"] = []
    for o, prva, tip, opis in [("greska", "Loše", "hook", "Loše ugrađena klima troši dvostruko više struje"),
                               ("najava", "Ljudi", "emocija", "Ljudi na semaforu pjevaju s bendom")]:
        _, a, z = next(x for x in blokovi if x[0] == o)
        w0 = next(w for w in words if a - 0.01 <= w["s"] <= z and w["w"] == prva)
        an["trenuci"].append({"od": w0["s"], "do": round(w0["s"] + 4, 2), "vrsta": tip, "ocjena": 5, "opis": opis})
    save(proj / "analiza.json", an)
    run("analyze.py", proj, "--provjeri", check=False)
    run("plan.py", proj, "--stil", "podcast")
    # uvodna špica iza najave: kraj zadnje riječi najave u vremenu gotovog videa
    import render
    edit = load(proj / "edit.json")
    pj = load(proj / "project.json")
    cuts, _, _ = render.build_cuts(words, edit, render.resolve_style(edit), pj["fps"], pj["duration"])
    _, _, najava_do = blokovi[0]
    t_najava = render.to_out(najava_do, cuts) or najava_do
    log["spica"] = run("spica.py", proj, "dodaj", "--poslije", f"{t_najava + 0.3:.1f}", "--naslov", EPIZODA_NASLOV,
                       "--broj", "12", "--ime", "Sunčani4M").stdout
    run("spica.py", proj, "pokazi")
    log["render"] = run("render.py", proj).stdout
    log["mp3"] = run("epizoda.py", proj, "mp3", "--naslov", PODCAST["naslov"], "--autor", "Sunčani4M").stdout
    r = run("objava.py", proj, "epizoda", check=False)
    assert r.returncode == 1, r.stdout + r.stderr
    ob = load(proj / "objava.json")
    m = ob["videi"]["reel_v1"]["mreze"]
    m["youtube"], m["podcast"] = json.loads(json.dumps(YOUTUBE)), json.loads(json.dumps(PODCAST))
    save(proj / "objava.json", ob)
    log["objava"] = run("objava.py", proj, "epizoda").stdout
    return proj, snim, blokovi, pjesma, log


# ------------------------------------------------------------------ isječci iz podcasta
def blok_isjecka(c, blokovi):
    def prek(a, b):
        return max(0.0, min(c["do"], b) - max(c["od"], a))
    return max(blokovi, key=lambda x: prek(x[1], x[2]))[0]


def isjecci(proj, blokovi):
    r = run("isjecci.py", proj, check=False)
    assert r.returncode == 1, r.stdout + r.stderr
    data = load(proj / "isjecci.json")
    po_bloku = {}
    for c in data["isjecci"]:
        o = "pjesma" if c.get("vrsta") == "pjesma" else blok_isjecka(c, blokovi)
        cl = dict(OCJENE[o])
        if o in po_bloku:
            cl = dict(ocjena=max(1, cl["ocjena"] - 3), razlog="Isti dio kao " + po_bloku[o] + ", slabiji početak.")
        else:
            po_bloku[o] = c["id"]
        c.update(cl)
    save(proj / "isjecci.json", data)
    run("isjecci.py", proj, "provjeri")
    run("isjecci.py", proj, "odobri", ",".join(po_bloku[o] for o in ODOBRI))
    out = run("isjecci.py", proj, "render").stdout
    return po_bloku, out


# ------------------------------------------------------------------ kartice i slaganje (16:9 i 9:16)
EW, EH = 1280, 720          # M4_epizoda.mp4
VW, VH = M2.W, M2.H         # M4_isjecci.mp4 (720×1280)
TOP = "PREGLED M4 · PODCAST SUNČANI4M"
CSS4 = """
body .land{display:none}
body:has(.land){padding:46px 64px;gap:20px}
body:has(.land) h1{font-size:50px}
body:has(.land) p{font-size:27px}
body:has(.land) .ln{font-size:25px;padding-left:40px}
body:has(.land) .ln b{width:28px;height:28px;line-height:28px;font-size:21px}
body:has(.land) .bubble{font-size:32px;padding:16px 24px}
body:has(.land) .odg{gap:11px}
.mono{font-family:'DejaVu Sans Mono',Consolas,monospace;font-size:22px;line-height:1.5;color:#e9eef3;
 background:#0b0f14;border-radius:12px;padding:12px 18px;white-space:pre}
.dva{display:flex;gap:36px;align-items:flex-start}
"""
ENC4 = ["-c:v", "libx264", "-crf", "27", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "112k", "-ar", "48000", "-ac", "2"]


def kartica(korak, naslov=None, tekst=(), naredba=None, linije=(), extra="", top=TOP):
    body = f'<div class="top">{e(top)}</div><div class="korak">{e(korak)}</div>'
    if naslov:
        body += f"<h1>{e(naslov)}</h1>"
    body += "".join(f"<p>{t}</p>" for t in tekst)
    if naredba:
        body += f'<div><div class="tko" style="text-align:right">MARKO</div><div class="bubble">{e(naredba)}</div></div>'
    if linije:
        body += f'<div><div class="tko">SHOFE</div><div class="odg">{"".join(linije)}</div></div>'
    return body + extra


def snimi(kartice, rad, size, ime):
    d = rad / ime
    d.mkdir(exist_ok=True)
    if size[0] > size[1]:                       # vodoravne kartice: manji razmaci i slova (body:has(.land))
        kartice = ['<i class="land"></i>' + k for k in kartice]
    return M2.snimi_kartice(kartice, d, size=size, extra_css=CSS4)


def dio_kartica(png, sekundi, out, size):
    ff("-loop", "1", "-framerate", "30", "-t", sekundi, "-i", png, "-f", "lavfi", "-t", sekundi,
       "-i", "anullsrc=r=48000:cl=stereo", "-vf", f"scale={size[0]}:{size[1]},fade=in:d=0.25", "-shortest",
       *ENC4, out)


def dio_video(src, od, do, out, size, vf_extra="", cwd=None):
    d = do - od
    vf = f"scale={size[0]}:{size[1]}{vf_extra},fade=in:d=0.2,fade=out:st={d - 0.25:.3f}:d=0.25"
    ff("-ss", f"{od:.3f}", "-t", f"{d:.3f}", "-i", Path(src).resolve(), "-vf", vf,
       "-af", f"afade=in:d=0.15,afade=out:st={d - 0.25:.3f}:d=0.25", *ENC4, Path(out).resolve(), cwd=cwd)


def slozi(plan, out, rad, size):
    dijelovi = []
    for i, p in enumerate(plan):
        f = rad / f"{out.stem}_{i:02d}.mp4"
        if p[0] == "k":
            dio_kartica(p[1], p[2], f, size)
        elif p[0] == "v":
            dio_video(p[1], p[2], p[3], f, size, *p[4:])
        else:
            p[1](f)
        dijelovi.append(f)
    M2.spoji(dijelovi, out, rad)
    M2.provjeri_velicinu(out)


# ------------------------------------------------------------------ mozaik: tri kamere + program
MOZ_KAM = [(28, 24), (28, 252), (28, 480)]          # 384×216 svaka
MOZ_PROG = (440, 150, 812, 457)                     # x, y, w, h


def aktivne(kadrovi, od, do, imena):
    """[(a, b, indeks kamere)] u vremenu od početka dijela."""
    out = []
    for k in kadrovi:
        a, b = max(k["od"], od), min(k["do"], do)
        if b > a and k["kamera"] in imena:
            out.append((round(a - od, 3), round(b - od, 3), imena.index(k["kamera"])))
    return out


def tekst_datoteka(rad, ime, tekst):
    f = rad / ime
    f.write_text(tekst, encoding="utf-8")
    return f.name


def mozaik(proj, snim, od, do, naslov, opis, out, rad):
    sk = load(proj / "sinkro.json")
    rez = load(proj / "rezija.json")
    poc = float(rez.get("pocetak", 0.0))
    imena = list(KAMERE)
    pomak = {Path(x["datoteka"]).name: float(x.get("pomak", 0.0)) for x in sk["izvori"]}
    d = do - od
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", rad / "f.ttf")
    ins, fc = [], [f"color=c=0x11161d:s={EW}x{EH}:r=30:d={d:.3f}[bg]"]
    for i, ime in enumerate(imena):
        t0 = od + poc - pomak[ime]               # vrijeme u datoteci kamere
        pad = max(0.0, -t0)
        ins += ["-ss", f"{max(0.0, t0):.3f}", "-t", f"{d:.3f}", "-i", (snim / ime).resolve()]
        fc.append(f"[{i}:v]scale=384:216:force_original_aspect_ratio=decrease,pad=384:216:(ow-iw)/2:(oh-ih)/2:"
                  f"color=black,tpad=start_duration={pad:.3f}:color=black,setpts=PTS-STARTPTS[c{i}]")
    ins += ["-ss", f"{od:.3f}", "-t", f"{d:.3f}", "-i", (proj / "source.mp4").resolve()]
    x, y, w, h = MOZ_PROG
    fc.append(f"[3:v]scale={w}:{h}[pr]")
    cur = "bg"
    for i, (cx, cy) in enumerate(MOZ_KAM):
        fc.append(f"[{cur}][c{i}]overlay={cx}:{cy}[m{i}]")
        cur = f"m{i}"
    boxes = ",".join(f"drawbox=x={MOZ_KAM[k][0] - 5}:y={MOZ_KAM[k][1] - 5}:w=394:h=226:color=0xf4a259:t=5:"
                     f"enable='between(t,{a},{b})'" for a, b, k in aktivne(rez["kadrovi"], od, do, imena))
    lab = "drawtext=fontfile=f.ttf:textfile={f}:x={x}:y={y}:fontsize={s}:fontcolor={c}"
    fc.append(f"[{cur}][pr]overlay={x}:{y},{boxes},"
              + lab.format(f=tekst_datoteka(rad, "moz_t.txt", naslov), x=x, y=38, s=22, c="0x7f8c99") + ","
              + lab.format(f=tekst_datoteka(rad, "moz_o.txt", opis), x=x, y=80, s=24, c="0xe9eef3") + ","
              + lab.format(f=tekst_datoteka(rad, "moz_p.txt", "PROGRAM (gotova režija)"), x=x, y=y + h + 16, s=20,
                           c="0xf4a259") + ","
              + lab.format(f=tekst_datoteka(rad, "moz_k.txt", "narančasto = kamera u programu"), x=x + w - 330,
                           y=y + h + 16, s=20, c="0x7f8c99")
              + f",fade=in:d=0.2,fade=out:st={d - 0.25:.3f}:d=0.25[v]")
    ff(*ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "3:a",
       "-af", f"afade=in:d=0.15,afade=out:st={d - 0.25:.3f}:d=0.25", *ENC4, out.resolve(), cwd=rad)


# ------------------------------------------------------------------ M4_epizoda.mp4
def ln(kind, text):
    return M2.ln(kind, text)


def sinkro_linije(log):
    out = []
    for r in log.splitlines():
        m = re.match(r"(\S+)\s+počinje ([\d,]+) s (prije|nakon) glavnog; sigurnost (\w+)", r)
        if m:
            out.append(ln("i", f"<q>{e(m.group(1))}</q> krenula {m.group(2)} s {m.group(3)} diktafona "
                               f"<span style='color:#7f8c99'>· sigurnost {m.group(4)}</span>"))
    return out


def poglavlja(proj):
    return load(proj / "reel_v1.chapters.json")["chapters"]


def demo_epizoda(proj, snim, blokovi, pjesma, log, rad):
    b = {o: (a, z) for o, a, z in blokovi}
    ch = poglavlja(proj)
    total = dur(proj / "reel_v1.mp4")
    istina = {ime: k["pomak"] for ime, k in KAMERE.items()}
    sp = load(proj / "edit.json")["spica"]
    sp_at = re.search(r"uvodna [\d.]+ s \(generirana\) na (\d+):([\d.]+)", log["render"])
    sp_txt = f"{int(sp_at.group(1))}:{float(sp_at.group(2)):04.1f}".replace(".", ",") if sp_at else "?"
    glas = re.search(r"Glasnoća P1: (.*)", log["render"])
    mp3 = re.search(r"Glasnoća (-?[\d.]+) LUFS \(cilj -16\), vrh (-?[\d.]+) dBTP, (\d+) poglavlja", log["mp3"])
    kamere_txt = {"GOPR0412.MP4": "široki kadar (sva trojica)", "MVI_2203.MP4": "krupni kadar Marka",
                  "VID_20261127_ivan.mp4": "krupni kadar Ivana (mobitel uspravno)"}
    rez_kam = [ln("i", f"<q>{e(k)}</q> → {e(kamere_txt[k])}") for k in KAMERE]
    prosj = re.search(r"Kadrova: (\d+), prosječno ([\d,]+) s", log["rezija"])
    pj_linija = re.search(r"Pjesma P1 .*?: (\d+) kadrova, prosječno ([\d,]+) s, (\d+) BPM", log["rezija"])
    pog_txt = "\n".join(f"{int(c['startTime'] // 60):02d}:{int(c['startTime'] % 60):02d} {c['title']}" for c in ch)
    kartice = [
        kartica("PROBNA EPIZODA 12", "Tri kamere, diktafon i bend u Renaultu 4",
                ["Marko, Ivan i bend Kutina. Svaka kamera i diktafon uključeni su u <b>drugom trenutku</b>, kao u "
                 "autu. Na slici svake kamere piše koja je i vrijeme <b>u toj datoteci</b>.",
                 "Glasovi i bend su sintetski. Sve dalje napravio je Shofe; Claude je napisao teme, opis epizode i "
                 "ocjene isječaka."]),
        kartica("1 · SINKRONIZACIJA PO ZVUKU", naredba="Ovo su snimke epizode, sinkroniziraj ih.",
                linije=sinkro_linije(log["sinkro"]) + [
                    ln("plus", "točno kako su stvarno krenule (" + ", ".join(
                        f"{'+' if v > 0 else '−'}{abs(v):.1f} s".replace(".", ",") for v in istina.values())
                       + ") — bez pljeska i timecodea")]),
        kartica("2 · KAMERA NA ONOME TKO GOVORI", naredba="Montiraj epizodu, kamera neka prati onoga tko priča.",
                linije=rez_kam + [
                    ln("plus", f"{prosj.group(1)} kadrova, prosječno {prosj.group(2)} s; Marko i Ivan su u kadru "
                               "dok govore 100 %"),
                    ln("plus", "brza izmjena („Dva tjedna?” „Da.”) → široki kadar"),
                    ln("i", "mobitel uključen tek na 0:06 → do tada se ne bira")]),
        kartica("3 · PJESMA SE NE REŽE", naredba="Bend svira od 1:44, ne reži pjesmu.",
                linije=[ln("plus", f"pjesma cijela, {pj_linija.group(3)} BPM: počinje i završava u širokom kadru, "
                                   f"{pj_linija.group(1)} kadrova, svaki rez na početku takta"),
                        ln("plus", "bez titlova preko pjesme, zvuk obrađen kao glazba"),
                        ln("i", e(glas.group(1)) if glas else "glasnoća pjesme = glasnoća govora")]),
        kartica("4 · GOTOVA EPIZODA", naredba="Dodaj špicu iza najave i napravi poglavlja.",
                linije=[ln("plus", f"uvodna špica ({sp['uvod']['trajanje']:g} s) "
                                   f"iza najave, na {sp_txt}; odjavna {sp['odjava']['trajanje']:g} s (mjesto za YouTube završni zaslon)"),
                        ln("plus", "video −14 LUFS; dolje lijevo vidiš u kojem si poglavlju")],
                extra=f'<div class="mono">{e(pog_txt)}</div>'),
        kartica("5 · SVE ZA OBJAVU", "Uz epizodu je spremno:", linije=[
            ln("i", "<q>reel_v1.mp4</q> + <q>.srt</q> — video i titlovi za YouTube"),
            ln("i", "<q>reel_v1.objava.txt</q> — YouTube opis s poglavljima + tekst za Spotify/Apple"),
            ln("i", f"<q>reel_v1.mp3</q> — {mp3.group(1).replace('.', ',')} LUFS, {mp3.group(3)} poglavlja u MP3-u"
               if mp3 else "<q>reel_v1.mp3</q> — za podcast platforme"),
            ln("i", "<q>reel_v1.fcpxml</q> + <q>.poglavlja.edl</q> — DaVinci: kamere na trakama, špica, poglavlja"),
            ln("plus", "i isječci 9:16 iz originalnih kamera (sljedeći video)")]),
    ]
    png = snimi(kartice, rad, (EW, EH), "kartice_ep")
    # dijelovi gotove epizode s oznakom poglavlja (kao na YouTubeu)
    fs = rad / "f.ttf"
    shutil.copy(FONTS / "Montserrat-ExtraBold.ttf", fs)

    def ep_dio(od, do):
        def f(out):
            parts = []
            for i, c in enumerate(ch):
                a = c["startTime"]
                z = ch[i + 1]["startTime"] if i + 1 < len(ch) else total + 1
                if z <= od or a >= do:
                    continue
                tf = tekst_datoteka(rad, f"pog_{i}.txt", f"{int(a // 60):02d}:{int(a % 60):02d} • {c['title']}")
                parts.append(f"drawtext=fontfile=f.ttf:textfile={tf}:x=24:y=h-56:fontsize=24:fontcolor=white:"
                             f"box=1:boxcolor=black@0.6:boxborderw=10:enable='between(t+{od:.3f},{a},{z})'")
            dio_video(proj / "reel_v1.mp4", od, do, out, (EW, EH), "," + ",".join(parts) if parts else "", cwd=rad)
        return f
    t_p = next(c["startTime"] for c in ch if c["title"].startswith("Pjesma"))
    t_b = next((c["startTime"] for c in ch if c["startTime"] > t_p), t_p + 58)
    od_k, do_k = b["klima"][0] + 24.5, b["klima"][1] + 1.0      # brza izmjena
    plan = [("k", png[0], 7.0), ("k", png[1], 8.0), ("k", png[2], 8.0),
            ("f", lambda f: mozaik(proj, snim, b["klima"][0] - 2.0, do_k, "2 · REŽIJA",
                                   "Ivan i Marko pričaju o ljetu, pa brza izmjena.", f, rad)),
            ("k", png[3], 6.5),
            ("f", lambda f: mozaik(proj, snim, pjesma["od"] - 5.0, pjesma["od"] + 30.0, "3 · PJESMA",
                                   "Najava, pa pjesma: široki kadar, sporiji rezovi na takt.", f, rad)),
            ("k", png[4], 8.0),
            ("f", ep_dio(0.0, 17.0)), ("f", ep_dio(t_p - 4.0, t_p + 12.0)), ("f", ep_dio(t_b - 5.0, t_b + 6.0)),
            ("f", ep_dio(total - 16.0, total - 10.0)),
            ("k", png[5], 7.0)]
    assert do_k > od_k
    slozi(plan, DEMO / "M4_epizoda.mp4", rad, (EW, EH))
    return png


# ------------------------------------------------------------------ M4_isjecci.mp4 (9:16)
def demo_isjecci(proj, ids, rad):
    data = {c["id"]: c for c in load(proj / "isjecci.json")["isjecci"]}
    k4, k5 = data[ids["klima"]], data[ids["pjesma"]]
    top = "PREGLED M4 · ISJEČCI IZ PODCASTA"
    kartice = [
        kartica("ISJEČCI 9:16 IZ ORIGINALNIH KAMERA", "Ne izrezani iz vodoravnog programa",
                ["Svaki isječak Shofe ponovno režira za uspravni kadar: lice onoga tko govori iz <b>njegove</b> "
                 "kamere, mobitel uspravno kakav jest."], naredba="Napravi isječke iz epizode.", top=top),
        kartica(f"{k4['id']} · RAZGOVOR", k4["naslov"],
                linije=[ln("plus", "svatko iz svoje kamere (Marko: kamera 2, Ivan: mobitel)"),
                        ln("plus", "brza izmjena → podijeljen kadar, titlovi na spoju"),
                        ln("i", f"Claude {k4['ocjena']}/10: {e(k4['razlog'])}")], top=top),
        kartica(f"{k5['id']} · PJESMA", k5["naslov"],
                linije=[ln("plus", "bend iz širokog kadra cijeli u kadru, mutna pozadina"),
                        ln("plus", "krupni kadrovi naizmjence, rez na početku takta"),
                        ln("plus", "bez titlova, zvuk za glazbu; demo pokazuje prvih 35 s"),
                        ln("i", f"Claude {k5['ocjena']}/10: {e(k5['razlog'])}")], top=top),
    ]
    png = snimi(kartice, rad, (VW, VH), "kartice_is")
    v4, v5 = proj / k4["render"]["datoteka"], proj / k5["render"]["datoteka"]
    plan = [("k", png[0], 6.0), ("k", png[1], 5.5), ("v", v4, 0, dur(v4)), ("k", png[2], 6.0),
            ("v", v5, 0, min(35.0, dur(v5)))]
    slozi(plan, DEMO / "M4_isjecci.mp4", rad, (VW, VH))
    return png


# ------------------------------------------------------------------ M4_paket.png
CSS_P = """
body{height:auto;padding:30px 34px;display:block;overflow:visible}
.red{display:flex;gap:24px;align-items:flex-start;margin-top:16px}
.st{flex:1;display:flex;flex-direction:column;gap:14px}
.box{background:#18202a;border-radius:14px;padding:14px 18px}
.box h3{font-size:16px;letter-spacing:.1em;color:#f4a259;font-weight:900;margin-bottom:8px}
.box .t{font-size:15px;line-height:1.42;color:#e9eef3;white-space:pre-wrap;font-weight:600}
.box .t b{color:#fff;font-weight:900}
.cap{font-size:14px;color:#7f8c99;margin-top:6px}
.tl{position:relative;background:#0b0f14;border-radius:10px;padding:8px 0 4px 0}
.tr{position:relative;height:20px;margin:3px 0 3px 70px}
.tr .n{position:absolute;left:-64px;top:1px;font-size:12px;color:#7f8c99;font-weight:800}
.tr i{position:absolute;top:0;height:20px;border-radius:3px;opacity:.95}
.tr i.off{opacity:.28}
.mk{position:absolute;top:0;width:2px;background:#4caf7a}
.mk span{position:absolute;top:-2px;left:4px;font-size:11px;color:#4caf7a;font-weight:800;white-space:nowrap}
"""
BOJE_KAM = {"GOPR0412.MP4": "#e5603f", "MVI_2203.MP4": "#3b82f6", "VID_20261127_ivan.mp4": "#22a06b"}


def davinci_trake(fcpxml):
    """[(traka, od, do, ime)] glavne crte (lane 0 = V1, ostale po lane) + poglavlja [(t, naziv)] + trajanje."""
    import davinci
    T = davinci.parse_time
    root = ET.parse(fcpxml).getroot()
    seq = root.find("library/event/project/sequence")
    total = float(T(seq.get("duration")))
    out, pogl = [], []
    for c in seq.find("spine"):
        o, d = float(T(c.get("offset"))), float(T(c.get("duration")))
        out.append((0, o, o + d, c.get("name") or c.get("ref") or ""))
        for a in c.findall("asset-clip"):
            ao = o + float(T(a.get("offset")) - T(c.get("start") or "0s"))
            out.append((int(a.get("lane") or 0), ao, ao + float(T(a.get("duration"))), a.get("name") or "",
                        a.get("enabled", "1") == "1"))
        for m in c.findall("chapter-marker"):
            pogl.append((o + float(T(m.get("start")) - T(c.get("start") or "0s")), m.get("value")))
    return out, pogl, total


def html_timeline(fcpxml):
    trake, pogl, total = davinci_trake(fcpxml)
    lanes = sorted({x[0] for x in trake}, reverse=True)
    W = 1080

    def boja(ime):
        for k, v in BOJE_KAM.items():
            if ime.startswith(k):
                return v
        if "spica" in ime:
            return "#f4a259"
        if "pjesma" in ime:
            return "#eab308"
        return "#94a3b8"
    rows = ""
    for ln_ in lanes:
        ime = "V1" if ln_ == 0 else (f"V{ln_ + 1}" if ln_ > 0 else f"A{-ln_}")
        bars = "".join(f'<i class="{"" if (len(x) < 5 or x[4]) and x[0] <= 0 else "off"}" style="left:{x[1] / total * W:.1f}px;'
                       f'width:{max(1.5, (x[2] - x[1]) / total * W - 1):.1f}px;background:{boja(x[3])}"></i>'
                       for x in trake if x[0] == ln_)
        rows += f'<div class="tr"><span class="n">{ime}</span>{bars}</div>'
    marks = "".join(f'<div class="mk" style="left:{70 + t / total * W:.1f}px;height:100%"><span>{e(n[:22])}</span></div>'
                    for t, n in pogl)
    return f'<div class="tl" style="width:{W + 80}px;padding-top:22px">{marks}{rows}</div>', len(pogl)


def demo_paket(proj, rad):
    txt = (proj / "reel_v1.objava.txt").read_text(encoding="utf-8-sig")

    def izmedju(oznaka):
        dio = txt.split(oznaka, 1)[1]
        return dio.split("-" * 40 + "\n", 1)[1].split("\n" + "-" * 40, 1)[0]
    yt_n, yt_o = izmedju("=== YOUTUBE"), izmedju("Opis:")
    pod_n, pod_o = izmedju("Naslov epizode:"), izmedju("Opis epizode:")
    tl, n_pogl = html_timeline(proj / "reel_v1.fcpxml")
    uvod = (proj / "spica_uvod.png").resolve().as_uri()
    odj = (proj / "spica_odjava.png").resolve().as_uri()
    mp3 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate:format_tags=title,artist",
                          "-show_chapters", "-of", "json", str(proj / "reel_v1.mp3")], capture_output=True, text=True,
                         encoding="utf-8")
    mj = json.loads(mp3.stdout)
    mp3_txt = (f"<b>{e(mj['format']['tags'].get('title', ''))}</b> — {e(mj['format']['tags'].get('artist', ''))}\n"
               f"{int(mj['format']['bit_rate']) // 1000} kbps, {int(float(mj['format']['duration']) // 60)}:"
               f"{int(float(mj['format']['duration']) % 60):02d}, −16 LUFS, {len(mj['chapters'])} poglavlja (ID3 CHAP):\n"
               + "\n".join(f"  {int(float(c['start_time']) // 60):02d}:{int(float(c['start_time']) % 60):02d} "
                           f"{e(c['tags']['title'])}" for c in mj["chapters"]))
    body = (f'<div class="top">PREGLED M4 · SVE ZA OBJAVU EPIZODE 12 (iz jedne naredbe po koraku)</div>'
            f'<div class="red"><div class="st" style="flex:0 0 480px">'
            f'<div class="box"><h3>UVODNA I ODJAVNA ŠPICA (GENERIRANE)</h3><img src="{uvod}" width="444" '
            f'style="border-radius:8px;display:block"><div class="cap">uvodna 5 s iza najave</div>'
            f'<img src="{odj}" width="444" style="border-radius:8px;display:block;margin-top:8px">'
            f'<div class="cap">odjavna 15 s — donji dio slobodan za YouTube završni zaslon</div></div>'
            f'<div class="box"><h3>MP3 ZA SPOTIFY / APPLE (reel_v1.mp3)</h3><div class="t">{mp3_txt}</div></div>'
            f'</div><div class="st">'
            f'<div class="box"><h3>YOUTUBE · reel_v1.objava.txt</h3><div class="t"><b>{e(yt_n)}</b>\n\n{e(yt_o)}</div></div>'
            f'<div class="box"><h3>SPOTIFY / APPLE PODCASTS · broj epizode 12</h3><div class="t"><b>{e(pod_n)}</b>\n\n'
            f'{e(pod_o)}</div></div></div></div>'
            f'<div class="box" style="margin-top:16px"><h3>DAVINCI · reel_v1.fcpxml (trake kako ih Resolve otvori)</h3>'
            f'{tl}<div class="cap">V1 = program iz originalnih kamera (crveno široka, plavo Marko, zeleno Ivanov '
            f'mobitel, narančasto špica); trake iznad = ostale kamere u istom trenutku (isključene, uključiš ih za '
            f'ručnu promjenu kadra); A = diktafon i pjesma na svojoj traci; zelene crte = {n_pogl} poglavlja '
            f'(i u reel_v1.poglavlja.edl za Deliver → Chapters from Markers).</div></div>')
    png = M2.snimi_kartice([body], rad, size=(1220, 900), full=True, extra_css=CSS_P)[0]
    out = DEMO / "M4_paket.png"
    shutil.copy(png, out)
    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.2f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--radna", type=Path, default=None, help="radna mapa (ostaje nakon kraja)")
    ap.add_argument("--samo-demo", action="store_true", help="radna mapa već ima projekt: samo složi demo")
    a = ap.parse_args()
    if not shutil.which("espeak-ng"):
        sys.exit("Treba espeak-ng (sintetski govor): apt install espeak-ng")
    DEMO.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shofe demo m4 ") as tmp:
        base = a.radna or Path(tmp)
        os.environ["SHOFE_PODACI"] = str(base / "podaci")
        stanje = base / "stanje.json"
        if a.samo_demo and stanje.exists():
            s = load(stanje)
            proj, snim = Path(s["proj"]), Path(s["snim"])
            blokovi, pjesma, log, ids = [tuple(x) for x in s["blokovi"]], s["pjesma"], s["log"], s["ids"]
        else:
            if a.radna:
                shutil.rmtree(base, ignore_errors=True)
            base.mkdir(parents=True, exist_ok=True)
            proj, snim, blokovi, pjesma, log = napravi_projekt(base)
            ids, log["isjecci"] = isjecci(proj, blokovi)
            save(stanje, {"proj": str(proj), "snim": str(snim), "blokovi": blokovi, "pjesma": pjesma, "log": log,
                          "ids": ids})
        rad = base / "demo_rad"
        shutil.rmtree(rad, ignore_errors=True)
        rad.mkdir()
        for f in DEMO.glob("M3_*"):        # stari demo ostaje u povijesti (link u demo/README.md)
            f.unlink()
        demo_epizoda(proj, snim, blokovi, pjesma, log, rad)
        demo_isjecci(proj, ids, rad)
        demo_paket(proj, rad)
    print("Gotovo →", DEMO)


if __name__ == "__main__":
    main()
