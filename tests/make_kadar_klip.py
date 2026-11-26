"""Vodoravni probni klip s dvije nacrtane osobe koje govore glasovima iz razgovor.m4a.

  python tests/make_kadar_klip.py out.mp4        (treba ffmpeg i opencv-python-headless)

Osoba A sjedi lijevo (x ≈ 0,27), osoba B desno (x ≈ 0,72); usta se otvaraju po glasnoći zvuka
samo dok ta osoba govori (rečenice iz razgovor.json). Glas C (rečenica 5) je izvan kadra.
Obje glave se lagano njišu, a druga osoba ponekad malo pomakne usta (kao u stvarnoj snimci).
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

FIX = Path(__file__).resolve().parent / "fixtures"
RAZ = json.loads((FIX / "razgovor.json").read_text(encoding="utf-8"))
W, H, FPS = 960, 540, 15
SEATS = {"A": (0.27, 0.47, 82, (140, 170, 215), (40, 50, 60), (150, 80, 60)),
         "B": (0.72, 0.49, 78, (120, 150, 200), (30, 60, 110), (70, 110, 60))}
DUR = 27.2        # do kraja 6. rečenice (A); C govori 18,3–23,7 s izvan kadra


def envelope(audio, fps):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 16000 // fps
    n = len(a) // hop
    rms = np.sqrt(np.mean(a[:n * hop].reshape(n, hop) ** 2, axis=1))
    return rms / (np.percentile(rms, 95) + 1e-6)


def draw_face(img, cx, cy, s, skin, hair, shirt, mouth):
    import cv2
    cv2.rectangle(img, (cx - int(s * 1.3), cy + int(s * 1.1)), (cx + int(s * 1.3), H), shirt, -1)
    cv2.rectangle(img, (cx - int(s * .25), cy + int(s * .8)), (cx + int(s * .25), cy + int(s * 1.15)), skin, -1)
    cv2.ellipse(img, (cx, cy), (int(s * .8), s), 0, 0, 360, skin, -1)
    cv2.ellipse(img, (cx, cy - int(s * 1.05)), (int(s * .85), int(s * .45)), 0, 180, 360, hair, -1)
    for dx in (-1, 1):
        ex = cx + dx * int(s * .33)
        cv2.ellipse(img, (ex, cy - int(s * .2)), (int(s * .14), int(s * .07)), 0, 0, 360, (255, 255, 255), -1)
        cv2.circle(img, (ex, cy - int(s * .2)), int(s * .06), (40, 30, 20), -1)
        cv2.line(img, (cx + dx * int(s * .2), cy - int(s * .38)), (cx + dx * int(s * .48), cy - int(s * .4)),
                 hair, max(2, int(s * .05)))
    cv2.line(img, (cx, cy - int(s * .1)), (cx - int(s * .07), cy + int(s * .2)),
             tuple(int(c * .75) for c in skin), max(2, int(s * .05)))
    cv2.ellipse(img, (cx, cy + int(s * .48)), (int(s * .25), max(2, int(s * (.04 + .22 * mouth)))),
                0, 0, 360, (60, 50, 140), -1)
    if mouth > 0.3:
        cv2.ellipse(img, (cx, cy + int(s * .44)), (int(s * .18), max(1, int(s * .05 * mouth))),
                    0, 0, 360, (235, 235, 235), -1)


def make(dst, dur=DUR):
    import cv2
    dst = Path(dst)
    env = envelope(FIX / "razgovor.m4a", FPS)
    rng = np.random.default_rng(7)
    n = int(dur * FPS)
    speaking = {g: np.zeros(n, bool) for g in "ABC"}
    for r in RAZ["recenice"]:
        speaking[r["g"]][int(r["od"] * FPS):int(r["do"] * FPS) + 1] = True
    twitch = {g: np.convolve(rng.random(n) < 0.02, np.ones(4), "same") > 0 for g in SEATS}
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:] = (95, 110, 118)
    cv2.rectangle(bg, (0, int(H * .72)), (W, H), (70, 80, 90), -1)          # sjedalo
    cv2.rectangle(bg, (int(W * .42), int(H * .08)), (int(W * .58), int(H * .6)), (120, 135, 140), -1)  # prozor
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", str(FIX / "razgovor.m4a"), "-t", f"{dur:.2f}",
                          "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", str(dst)], stdin=subprocess.PIPE)
    for k in range(n):
        img = bg.copy()
        t = k / FPS
        for g, (fx, fy, s, skin, hair, shirt) in SEATS.items():
            sway = 6 * np.sin(2 * np.pi * (0.13 if g == "A" else 0.17) * t + (0 if g == "A" else 1.3))
            e = float(env[k]) if k < len(env) else 0.0
            m = min(1.0, 1.4 * e) if speaking[g][k] else (0.25 if twitch[g][k] else 0.0)
            draw_face(img, int(fx * W + sway), int(fy * H + sway / 3), s, skin, hair, shirt, m)
        noise = rng.integers(-3, 4, img.shape, dtype=np.int16)
        p.stdin.write(np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg nije uspio")
    return dst


def truth(dur=DUR):
    """Stvarni govornici do kraja klipa: [(od, do, 'A'|'B'|'C')]."""
    return [(r["od"], r["do"], r["g"]) for r in RAZ["recenice"] if r["do"] <= dur]


if __name__ == "__main__":
    print(make(sys.argv[1] if len(sys.argv) > 1 else "kadar_klip.mp4"))
