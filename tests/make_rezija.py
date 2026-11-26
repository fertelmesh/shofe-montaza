"""Probna podcast snimka za rezija.py (M4.2): zasebni zvuk + tri kamere u autu.

Govor je razgovor.m4a (55 s): A (Marko) i B (Ivan) sjede u autu, C je gost izvan kadra.
  zvuk.wav       glavni zvuk, 0–56 s
  siroka.mp4     široki kadar, oboje u kadru (plava pozadina), krenula 1,5 s PRIJE glavnog
  kamA.mp4       krupni kadar A (zelena pozadina), krenula 2,0 s NAKON glavnog
  kamB.mp4       krupni kadar B, USPRAVNI mobitel 360×640 (crvenkasta pozadina), od 0,7 s do 45 s glavnog
Usta se miču po glasnoći samo dok ta osoba govori. Boja pozadine govori koja je kamera u programu.

  python tests/make_rezija.py izlazna_mapa
"""
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_kadar_klip as MK  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
RAZ = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))
SR = 48000
FPS = 15
KRAJ = 55.6
LICA = {"A": ((140, 170, 215), (40, 50, 60), (150, 80, 60)), "B": ((120, 150, 200), (30, 60, 110), (70, 110, 60))}
# ime: (pomak na crti glavnog, kraj na crti glavnog, w, h, boja pozadine BGR, [(osoba, x, y, veličina)])
KAMERE = {
    "siroka.mp4": (-1.5, KRAJ, 640, 360, (135, 105, 85), [("A", 0.28, 0.47, 56), ("B", 0.72, 0.49, 54)]),
    "kamA.mp4": (2.0, KRAJ, 640, 360, (85, 125, 85), [("A", 0.5, 0.45, 105)]),
    "kamB.mp4": (0.7, 45.0, 360, 640, (85, 85, 135), [("B", 0.5, 0.42, 95)]),
}
BOJE = {k: v[4] for k, v in KAMERE.items()}
IMENA = {"A": "G1", "B": "G2", "C": "G3"}


def decode(path, sr=SR):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def write_wav(path, x, sr=SR):
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())


def segment(audio, a, b, sr=SR, seed=0):
    """Zvuk glavnog od a do b (s; izvan snimke tišina) + malo šuma (mikrofon kamere)."""
    n = int(round((b - a) * sr))
    out = np.zeros(n)
    i0 = int(round(a * sr))
    lo, hi = max(0, i0), min(len(audio), i0 + n)
    if hi > lo:
        out[lo - i0:hi - i0] = audio[lo:hi] * 0.7
    return out + np.random.default_rng(seed).normal(0, 0.003, n)


def truth():
    return [(r["od"], r["do"], r["g"]) for r in RAZ["recenice"]]


def make(out):
    import cv2
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    audio = decode(FIX / "razgovor.m4a")
    write_wav(out / "zvuk.wav", segment(audio, 0.0, 56.0, seed=1) / 0.7)
    env = MK.envelope(FIX / "razgovor.m4a", FPS)
    for ci, (name, (pomak, kraj, W, H, bgc, osobe)) in enumerate(KAMERE.items()):
        dur = kraj - pomak
        wav = out / f"_{name}.wav"
        write_wav(wav, segment(audio, pomak, kraj, seed=ci + 2))
        n = int(dur * FPS)
        rng = np.random.default_rng(ci)
        bg = np.zeros((H, W, 3), np.uint8)
        bg[:] = bgc
        cv2.rectangle(bg, (0, int(H * .78)), (W, H), tuple(int(c * .6) for c in bgc), -1)
        MK.H = H
        p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                              "-r", str(FPS), "-i", "-", "-i", str(wav), "-t", f"{dur:.3f}", "-map", "0:v",
                              "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-g", "30",
                              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", str(out / name)],
                             stdin=subprocess.PIPE)
        for k in range(n):
            img = bg.copy()
            t = pomak + k / FPS                     # vrijeme glavnog
            kk = int(round(t * FPS))
            for g, fx, fy, s in osobe:
                speaking = any(a <= t <= b for a, b, gg in truth() if gg == g)
                e = float(env[kk]) if 0 <= kk < len(env) else 0.0
                m = min(1.0, 1.4 * e) if speaking else 0.0
                sway = 5 * np.sin(2 * np.pi * (0.13 if g == "A" else 0.17) * t)
                MK.draw_face(img, int(fx * W + sway), int(fy * H), s, *LICA[g], m)
            noise = rng.integers(-3, 4, img.shape, dtype=np.int16)
            p.stdin.write(np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8).tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError("ffmpeg nije uspio")
        wav.unlink()
    return out


def govornici_json(proj, pocetak=0.0, imena=True):
    """Govornici iz scenarija (modeli za diarizaciju nisu u sandboxu): G1 = A (Marko), G2 = B (Ivan), G3 = C."""
    segs = [{"od": round(a - pocetak, 3), "do": round(b - pocetak, 3), "govornik": IMENA[g]} for a, b, g in truth()]
    gov = [{"id": "G1", "ime": "Marko" if imena else ""}, {"id": "G2", "ime": "Ivan" if imena else ""},
           {"id": "G3", "ime": ""}]
    (Path(proj) / "govornici.json").write_text(json.dumps({"govornici": gov, "odsjecci": segs}, ensure_ascii=False),
                                               encoding="utf-8")


if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else "rezija_snimke"))
