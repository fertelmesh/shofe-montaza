"""Probna epizoda s nastupom benda (M4.3): govor, pjesma, pljesak, govor uz radio, kratki džingl, govor.

Glazba je sintetski „bend" (bubanj, bas, gitara Karplus-Strong, pjevanje formantima), govor je razgovor.m4a.
  0,0–20,0   govor (razgovor 0–20 s)
  20,0–68,0  PJESMA: 6 s uvoda bez pjevanja, strofe, 4 s tihog dijela samo gitara, završni akord
  68,0–71,0  pljesak
  71,0–91,0  govor (razgovor 20–40 s)
  91,0–106,0 govor uz radio (glazba 12 dB ispod govora: nije pjesma)
  106,0–116,0 džingl 10 s (prekratko za pjesmu)
  116,0–131,0 govor (razgovor 40–54,6 s)
Transkript: riječi razgovora na novim vremenima + nekoliko „riječi" koje whisper izmisli u pjesmi.
Slika: boja po dijelu (pjesma zelena) i vrijeme, 320×180, 30 fps.

  python tests/make_nastup.py izlazna_mapa   → mapa projekta (source.mp4, project.json, transcript.json)
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

FIX = Path(__file__).resolve().parent / "fixtures"
SR = 16000
PJESMA = (20.0, 68.0)
PLJESAK = (68.0, 71.0)
RADIO = (91.0, 106.0)
DZINGL = (106.0, 116.0)
TRAJANJE = 131.0
# (izvor od, izvor do, cilj od) za govor iz razgovor.m4a
GOVOR = [(0.0, 20.0, 0.0), (20.0, 40.0, 71.0), (40.0, 54.6, 116.0)]
RADIO_GOVOR = (0.0, 15.0)   # isti razgovor ispod radija (druga kopija)
IZMISLJENO = [("la", 30.2, 30.6), ("ljubavi", 33.0, 33.8), ("moja", 41.1, 41.5), ("noći", 52.0, 52.9)]


def decode(path, sr=SR):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def write_wav(path, x, sr=SR):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _ks(rng, freq, dur, decay=0.996):
    n, p = int(dur * SR), max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, p)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = decay * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out


def _note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _formant(v, F, bw):
    r = np.exp(-np.pi * bw / SR)
    c = 2 * r * np.cos(2 * np.pi * F / SR)
    o = np.zeros_like(v)
    for q in range(2, len(v)):
        o[q] = v[q] + c * o[q - 1] - r * r * o[q - 2]
    return o / (np.abs(o).max() + 1e-9)


def band(dur, seed=1, bpm=112, intro=6.0, tiho=None, vokal=True):
    """Sintetska pjesma: Am F C G. `tiho` = (od, do) samo tiha gitara (bez bubnja i pjevanja)."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    y = np.zeros(n + SR)
    beat = 60.0 / bpm
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
    t, k = 0.0, 0
    while t < dur - beat:
        ch = chords[(k // 4) % 4]
        i = int(t * SR)
        quiet = tiho and tiho[0] <= t < tiho[1]
        if not quiet:
            if k % 2 == 0:
                tt = np.arange(int(0.25 * SR)) / SR
                f = 50 + 70 * np.exp(-tt * 30)
                y[i:i + len(tt)] += 0.8 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 12)
            else:
                tt = np.arange(int(0.2 * SR)) / SR
                s = np.convolve(rng.normal(0, 1, len(tt)), [1, -0.8], "same")
                y[i:i + len(tt)] += 0.35 * s * np.exp(-tt * 20)
            for h in (0.0, 0.5):
                j = int((t + h * beat) * SR)
                tt = np.arange(int(0.05 * SR)) / SR
                y[j:j + len(tt)] += 0.08 * np.diff(rng.normal(0, 1, len(tt) + 1)) * np.exp(-tt * 60)
            tt = np.arange(int(beat * SR)) / SR
            y[i:i + len(tt)] += 0.25 * (2 * ((tt * _note(ch[0] - 24)) % 1) - 1) * np.exp(-tt * 3)
        for m, nn in enumerate(ch + [ch[0] + 12]):
            g = _ks(rng, _note(nn), beat * 0.95)
            j = i + int(m * 0.012 * SR)
            y[j:j + len(g)] += (0.12 if quiet else 0.25) * g
        if vokal and not quiet and t >= intro and (k // 8) % 2 == 0:
            mel = [69, 67, 65, 64, 65, 67, 69, 72][k % 8]
            tt = np.arange(int(beat * SR)) / SR
            ph = np.cumsum(_note(mel) * (1 + 0.01 * np.sin(2 * np.pi * 5.5 * tt))) / SR
            v = 2 * (ph % 1) - 1
            env = np.minimum(1, tt * 20) * np.minimum(1, (beat - tt) * 10)
            out = sum(a * _formant(v, F, bw) for F, bw, a in ((800, 80, 1), (1150, 90, 0.5), (2900, 120, 0.3)))
            y[i:i + len(v)] += 0.3 * out * env
        t += beat
        k += 1
    # završni akord koji zvoni
    i = int((dur - 1.6) * SR)
    for nn in (57, 60, 64, 69):
        g = _ks(rng, _note(nn), 1.6, 0.999)
        y[i:i + len(g)] += 0.25 * g
    y = y[:n]
    return 0.6 * y / (np.abs(y).max() + 1e-9)


def pljesak(dur, seed=5):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    y = np.zeros(n)
    for _ in range(int(dur * 60)):  # puno ljudi plješće
        j = rng.integers(0, n - 400)
        tt = np.arange(400) / SR
        y[j:j + 400] += rng.normal(0, 1, 400) * np.exp(-tt * 300) * rng.uniform(0.3, 1)
    y = np.convolve(y, [1, -0.6], "same")
    env = np.minimum(1, np.arange(n) / (0.2 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.8 * SR))
    return 0.35 * y * env / (np.abs(y).max() + 1e-9)


def audio(pjesma_db=0.0):
    sp = decode(FIX / "razgovor.m4a")
    sp = 0.5 * sp / (np.abs(sp).max() + 1e-9)
    y = np.zeros(int(TRAJANJE * SR))

    def put(x, at):
        i = int(at * SR)
        y[i:i + len(x)] += x[:len(y) - i]

    for a, b, c in GOVOR:
        put(sp[int(a * SR):int(b * SR)], c)
    put(band(PJESMA[1] - PJESMA[0], tiho=(36.0, 40.0)) * 10 ** (pjesma_db / 20), PJESMA[0])
    put(pljesak(PLJESAK[1] - PLJESAK[0]), PLJESAK[0])
    r0, r1 = RADIO_GOVOR
    put(sp[int(r0 * SR):int(r1 * SR)], RADIO[0])
    put(band(RADIO[1] - RADIO[0], seed=3, intro=0.0) * 10 ** (-12 / 20), RADIO[0])
    put(band(DZINGL[1] - DZINGL[0], seed=4, intro=2.0), DZINGL[0])
    return y


def words():
    raz = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))["words"]
    out = []
    for a, b, c in GOVOR:
        for w in raz:
            if a <= w["s"] and w["e"] <= b:
                out.append(dict(w, s=round(w["s"] - a + c, 3), e=round(w["e"] - a + c, 3)))
    r0, r1 = RADIO_GOVOR
    for w in raz:
        if r0 <= w["s"] and w["e"] <= r1:
            out.append(dict(w, s=round(w["s"] - r0 + RADIO[0], 3), e=round(w["e"] - r0 + RADIO[0], 3)))
    for t, s, e in IZMISLJENO:
        out.append({"w": t, "s": s, "e": e, "p": 0.3})
    return sorted(out, key=lambda w: w["s"])


def make(out, pjesma_db=0.0):
    """pjesma_db = koliko je pjesma glasnija (+) ili tiša (−) nego inače (glasnoća pjesme naspram govora)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "_zvuk.wav"
    write_wav(wav, audio(pjesma_db))
    parts = [(0, PJESMA[0], "0x3a5a8c"), (PJESMA[0], PJESMA[1], "0x2e8b57"), (PJESMA[1], RADIO[0], "0x3a5a8c"),
             (RADIO[0], DZINGL[0], "0x8c6a3a"), (DZINGL[0], DZINGL[1], "0x8c3a6a"), (DZINGL[1], TRAJANJE, "0x3a5a8c")]
    boje = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color={c}:t=fill:enable='between(t,{a},{b - 0.001})'"
                    for a, b, c in parts)
    vf = (f"{boje},drawtext=text='%{{pts\\:hms}}':x=10:y=10:fontsize=28:fontcolor=white")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=30:d={TRAJANJE}",
                    "-i", str(wav), "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(out / "source.mp4")], check=True)
    wav.unlink()
    (out / "project.json").write_text(json.dumps({"format": "16:9", "width": 320, "height": 180, "fps": 30,
                                                  "duration": TRAJANJE, "clips": []}), encoding="utf-8")
    (out / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words()},
                                                    ensure_ascii=False), encoding="utf-8")
    return out


# pjesma sa strukturom (M4.3b3, refren): uvod, strofa A, refren B, A, B, most C, B, B — 112 BPM, odsjek 8 taktova
STRUKTURA = [("I", 4), ("A", 8), ("B", 8), ("A", 8), ("B", 8), ("C", 4), ("B", 8), ("B", 8)]
AKORDI = {"I": [[57, 60, 64], [53, 57, 60]], "A": [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]],
          "B": [[53, 57, 60], [55, 59, 62], [48, 52, 55], [52, 56, 59]], "C": [[50, 53, 57], [52, 55, 59]]}
MELODIJA = {"A": [69, 67, 65, 64, 65, 67, 69, 72], "B": [72, 74, 76, 74, 72, 71, 72, 79],
            "C": [65, 64, 62, 64, 65, 67, 65, 64]}


def odsjeci(bpm=112, struktura=STRUKTURA):
    """[(oznaka, od, do)] u sekundama od početka pjesme."""
    bar = 4 * 60.0 / bpm
    out, t = [], 0.0
    for o, n in struktura:
        out.append((o, round(t, 4), round(t + n * bar, 4)))
        t += n * bar
    return out


def pjesma_refren(seed=7, bpm=112, struktura=STRUKTURA, kraj=2.5):
    """Sintetska pjesma s refrenom: refren B ima druge akorde, višu melodiju, gušći bubanj i 4 dB je glasniji."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    parts = odsjeci(bpm, struktura)
    dur = parts[-1][2] + kraj
    n = int(dur * SR)
    y = np.zeros(n + SR)
    k = 0
    for o, a, b in parts:
        t, kk = a, 0
        while t < b - 1e-6:
            ch = AKORDI[o][(kk // 4) % len(AKORDI[o])]
            g = 10 ** ((4.0 if o == "B" else 0.0) / 20)
            i = int(t * SR)
            if o != "I" or kk >= 8:
                tt = np.arange(int(0.25 * SR)) / SR
                if kk % 2 == 0 or o == "B":
                    f = 50 + 70 * np.exp(-tt * 30)
                    y[i:i + len(tt)] += g * 0.8 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 12)
                if kk % 2 == 1:
                    tt = np.arange(int(0.2 * SR)) / SR
                    s = np.convolve(rng.normal(0, 1, len(tt)), [1, -0.8], "same")
                    y[i:i + len(tt)] += g * 0.35 * s * np.exp(-tt * 20)
                tt = np.arange(int(beat * SR)) / SR
                y[i:i + len(tt)] += g * 0.25 * (2 * ((tt * _note(ch[0] - 24)) % 1) - 1) * np.exp(-tt * 3)
            for m, nn in enumerate(ch + [ch[0] + 12]):
                gg = _ks(rng, _note(nn), beat * 0.95)
                j = i + int(m * 0.012 * SR)
                y[j:j + len(gg)] += g * 0.25 * gg
            if o in MELODIJA:
                mel = MELODIJA[o][kk % 8]
                tt = np.arange(int(beat * SR)) / SR
                ph = np.cumsum(_note(mel) * (1 + 0.01 * np.sin(2 * np.pi * 5.5 * tt))) / SR
                v = 2 * (ph % 1) - 1
                env = np.minimum(1, tt * 20) * np.minimum(1, (beat - tt) * 10)
                out = sum(aa * _formant(v, F, bw) for F, bw, aa in ((800, 80, 1), (1150, 90, 0.5), (2900, 120, 0.3)))
                y[i:i + len(v)] += g * 0.3 * out * env
            t += beat
            kk += 1
            k += 1
    i = int(parts[-1][2] * SR)
    for nn in (53, 57, 60, 65):
        gg = _ks(rng, _note(nn), kraj, 0.9995)
        y[i:i + len(gg)] += 0.3 * gg
    y = y[:n]
    return 0.6 * y / (np.abs(y).max() + 1e-9)


def make_refren(out, govor_prije=12.0, govor_poslije=10.0):
    """Probni projekt: govor, pjesma s refrenom (≈ 123 s), pljesak, govor. → (mapa, početak pjesme, kraj pjesme)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sp = decode(FIX / "razgovor.m4a")
    sp = 0.5 * sp / (np.abs(sp).max() + 1e-9)
    song = pjesma_refren()
    p0 = govor_prije
    p1 = p0 + len(song) / SR
    clap = pljesak(3.0)
    total = p1 + 3.0 + govor_poslije
    y = np.zeros(int(total * SR) + 1)

    def put(x, at):
        i = int(at * SR)
        y[i:i + len(x)] += x[:len(y) - i]

    put(sp[:int(govor_prije * SR)], 0.0)
    put(song, p0)
    put(clap, p1)
    put(sp[int(20 * SR):int((20 + govor_poslije) * SR)], p1 + 3.0)
    wav = out / "_zvuk.wav"
    write_wav(wav, y)
    vf = ("drawbox=x=0:y=0:w=iw:h=ih:color=0x2e8b57:t=fill:"
          f"enable='between(t,{p0},{p1})',drawtext=text='%{{pts\\:hms}}':x=10:y=10:fontsize=28:fontcolor=white")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x3a5a8c:s=320x180:r=30:d={total}",
                    "-i", str(wav), "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", str(out / "source.mp4")], check=True)
    wav.unlink()
    raz = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))["words"]
    words = [dict(w) for w in raz if w["e"] <= govor_prije]
    words += [dict(w, s=round(w["s"] - 20 + p1 + 3.0, 3), e=round(w["e"] - 20 + p1 + 3.0, 3))
              for w in raz if 20 <= w["s"] and w["e"] <= 20 + govor_poslije]
    (out / "project.json").write_text(json.dumps({"format": "16:9", "width": 320, "height": 180, "fps": 30,
                                                  "duration": round(total, 3), "clips": []}), encoding="utf-8")
    (out / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                    ensure_ascii=False), encoding="utf-8")
    return out, p0, p1


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "nastup_projekt")
