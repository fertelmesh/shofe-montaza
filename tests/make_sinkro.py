"""Probna podcast snimka za sinkro.py (M4.1): zasebni zvuk + dvije kamere s poznatim pomakom i driftom.

Govor je razgovor.m4a (55 s, tri sintetska glasa) pa isti unatrag (još 55 s drugačijeg govora) i tri
pljeska (20, 50, 80 s glavnog zvuka). Svaka kamera čuje isti razgovor svojim „mikrofonom":
  zvuk.wav     glavni, čisti (lav mikrofon), 110 s
  kamera1.mp4  počela 7,3 s PRIJE glavnog (prije toga žamor), mutni mikrofon s jekom, tiša, šum
  kamera2.mp4  počela 9,6 s NAKON glavnog, sat brži 150 ppm, „mobitel" (bez basa, odrezani vrhovi),
               zvučni zapis počinje 0,2 s iza slike (kao kod nekih kamera)
  tudje.wav    nepovezani žamor (ne smije se „pronaći")
Na slici kamera bljesne bijelo točno u trenutku pljeska, pa se sinkronizacija vidi i očima.

  python tests/make_sinkro.py izlazna_mapa
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

FIX = Path(__file__).resolve().parent / "fixtures"
SR = 48000
PLJESAK = [20.0, 50.0, 80.0]
ISTINA = {
    "kamera1.mp4": {"pomak": -7.3, "brzina": 1.0},
    # zvuk počinje 0,2 s iza slike: početak zvuka (= glavni 9,6 s) je na 0,2 s datoteke → pomak 9,4
    "kamera2.mp4": {"pomak": 9.6 - 0.2 / 1.00015, "brzina": 1.00015},
}


def decode(path, sr=SR):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def write_wav(path, x, sr=SR):
    y = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())


def zamor(dur, seed, sr=SR):
    """Govoru sličan šum: obojeni šum s „slogovima" (4–6 Hz) i pauzama."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / sr)
    X *= np.exp(-((np.log(f + 1) - np.log(600)) ** 2) / 1.2)
    x = np.fft.irfft(X, n)
    t = np.arange(n) / sr
    env = np.clip(np.sin(2 * np.pi * rng.uniform(4, 6) * t + rng.uniform(0, 6)), 0, 1) ** 2
    slow = np.repeat(rng.random(int(dur * 2) + 2) > 0.3, sr // 2)[:n]
    x = x * env * slow
    return 0.25 * x / (np.abs(x).max() + 1e-9)


def lowpass(x, fc, sr=SR):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X *= 1 / np.sqrt(1 + (f / fc) ** 4)
    return np.fft.irfft(X, len(x))


def highpass(x, fc, sr=SR):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X *= 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** 4)
    return np.fft.irfft(X, len(x))


def govor():
    s = decode(FIX / "razgovor.m4a")
    s = np.concatenate([s, s[::-1]])
    s = 0.6 * s / np.abs(s).max()
    rng = np.random.default_rng(3)
    for t in PLJESAK:
        i = int(t * SR)
        n = int(0.03 * SR)
        s[i: i + n] += 0.9 * rng.standard_normal(n) * np.exp(-np.arange(n) / (0.006 * SR))
    return s


def video(path, audio_wav, dur, flashes, audio_delay=0.0):
    """Slika s pokretnim brojačem i bijelim bljeskom (80 ms) na zadanim vremenima datoteke."""
    boxes = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,{f:.3f},{f + 0.08:.3f})'"
                     for f in flashes)
    vf = f"[0:v]{boxes}[v]" if boxes else "[0:v]null[v]"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=30:d={dur:.3f}"]
    if audio_delay:
        cmd += ["-itsoffset", f"{audio_delay}"]
    cmd += ["-i", str(audio_wav), "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-t", f"{dur:.3f}", str(path)]
    subprocess.run(cmd, check=True)


def make(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_izvor"
    tmp.mkdir(exist_ok=True)
    rng = np.random.default_rng(11)
    s = govor()
    T = len(s) / SR
    write_wav(out / "zvuk.wav", s + 0.002 * rng.standard_normal(len(s)))

    # kamera 1: 7,3 s žamora prije, pa razgovor kroz mutni mikrofon s jekom
    pre = zamor(7.3, 5)
    k1 = lowpass(s, 2500)
    for d, g in ((0.023, 0.45), (0.061, 0.25), (0.13, 0.12)):
        k1[int(d * SR):] += g * k1[: len(k1) - int(d * SR)]
    k1 = np.concatenate([pre, 0.3 * k1 / np.abs(k1).max()])
    k1 += 0.01 * rng.standard_normal(len(k1))
    write_wav(tmp / "k1.wav", k1)
    video(out / "kamera1.mp4", tmp / "k1.wav", len(k1) / SR, [t + 7.3 for t in PLJESAK])

    # kamera 2: počinje na 9,6 s glavnog, sat brži 150 ppm (više uzoraka u istom stvarnom vremenu)
    b = ISTINA["kamera2.mp4"]["brzina"]
    dur2 = (T - 9.6) * b - 0.5
    tau = np.arange(int(dur2 * SR)) / SR             # vrijeme zvuka kamere 2
    tm = 9.6 + tau / b                               # isto u vremenu glavnog
    k2 = np.interp(tm * SR, np.arange(len(s)), s)
    k2 = highpass(k2, 400)
    k2 = np.clip(3.0 * k2 / np.abs(k2).max(), -0.7, 0.7)
    k2 += 0.005 * rng.standard_normal(len(k2))
    write_wav(tmp / "k2.wav", k2)
    fl2 = [0.2 + (t - 9.6) * b for t in PLJESAK if t > 9.6]
    video(out / "kamera2.mp4", tmp / "k2.wav", dur2 + 0.2, fl2, audio_delay=0.2)

    write_wav(out / "tudje.wav", zamor(60, 99) + 0.003 * rng.standard_normal(60 * SR))
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    (out / "istina.json").write_text(json.dumps(ISTINA, indent=2), encoding="utf-8")
    return ISTINA


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "sinkro_proba")
