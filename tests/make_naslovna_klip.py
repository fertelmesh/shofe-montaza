"""Uspravni probni klip (9:16) s jednom nacrtanom osobom za izbor naslovne sličice (M3.4b).

  python tests/make_naslovna_klip.py out.mp4        (treba ffmpeg i opencv-python-headless)

Pet dijelova po 2 s, ista osoba, mijenja se samo jedno svojstvo:
  0–2 s  lice malo i uz rub kadra       2–4 s  zatvorene oči
  4–6 s  najbolji kadar (veliko, oštro, otvorene oči, dobro osvijetljeno)
  6–8 s  mutno (kamera se trese)        8–10 s  tamno
Shofe mora izabrati kadar iz 4–6 s.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

W, H, FPS, DUR = 540, 960, 15, 10.0
DIJELOVI = {"malo": (0, 2), "zatvorene": (2, 4), "najbolje": (4, 6), "mutno": (6, 8), "tamno": (8, 10)}
SKIN, HAIR, SHIRT = (140, 170, 215), (40, 50, 60), (150, 80, 60)


def draw_face(img, cx, cy, s, eyes_open=True):
    import cv2
    h = img.shape[0]
    cv2.rectangle(img, (cx - int(s * 1.3), cy + int(s * 1.1)), (cx + int(s * 1.3), h), SHIRT, -1)
    cv2.rectangle(img, (cx - int(s * .25), cy + int(s * .8)), (cx + int(s * .25), cy + int(s * 1.15)), SKIN, -1)
    cv2.ellipse(img, (cx, cy), (int(s * .8), s), 0, 0, 360, SKIN, -1)
    cv2.ellipse(img, (cx, cy - int(s * 1.05)), (int(s * .85), int(s * .45)), 0, 180, 360, HAIR, -1)
    for dx in (-1, 1):
        ex, ey = cx + dx * int(s * .33), cy - int(s * .2)
        if eyes_open:
            cv2.ellipse(img, (ex, ey), (int(s * .14), int(s * .07)), 0, 0, 360, (255, 255, 255), -1)
            cv2.circle(img, (ex, ey), int(s * .06), (40, 30, 20), -1)
        else:   # kapak: koža malo tamnija + trepavice
            cv2.ellipse(img, (ex, ey), (int(s * .14), int(s * .07)), 0, 0, 360,
                        tuple(int(c * .92) for c in SKIN), -1)
            cv2.ellipse(img, (ex, ey + int(s * .02)), (int(s * .14), int(s * .03)), 0, 0, 180, (40, 30, 20),
                        max(2, int(s * .025)))
        cv2.line(img, (cx + dx * int(s * .2), cy - int(s * .38)), (cx + dx * int(s * .48), cy - int(s * .4)),
                 HAIR, max(2, int(s * .05)))
    cv2.line(img, (cx, cy - int(s * .1)), (cx - int(s * .07), cy + int(s * .2)),
             tuple(int(c * .75) for c in SKIN), max(2, int(s * .05)))
    cv2.ellipse(img, (cx, cy + int(s * .48)), (int(s * .25), int(s * .06)), 0, 0, 360, (60, 50, 140), -1)


def frame(t, rng, bg):
    import cv2
    img = bg.copy()
    sway = 4 * np.sin(2 * np.pi * 0.3 * t)
    if t < 2:
        draw_face(img, int(W * 0.2 + sway), int(H * 0.30), 45)
    else:
        draw_face(img, int(W * 0.5 + sway), int(H * 0.40), 120, eyes_open=not (2 <= t < 4))
    img = np.clip(img.astype(np.int16) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)  # šum senzora
    if 6 <= t < 8:
        k = np.zeros((15, 15), np.float32)
        k[7, :] = 1 / 15                      # vodoravno mutno (trešnja)
        img = cv2.filter2D(img, -1, k)
    if t >= 8:
        img = (img * 0.28).astype(np.uint8)
    return img


def make(dst, dur=DUR):
    import cv2
    rng = np.random.default_rng(3)
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:] = (120, 128, 110)
    cv2.rectangle(bg, (0, int(H * .75)), (W, H), (70, 80, 90), -1)
    for i in range(0, W, 60):   # polica iza osobe (detalji za oštrinu)
        cv2.rectangle(bg, (i + 5, 60), (i + 40, 200), (60 + i % 90, 90, 140), -1)
    n = int(dur * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", f"sine=f=200:sample_rate=48000:duration={dur}",
                          "-t", f"{dur:.2f}", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", str(dst)],
                         stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(frame(k / FPS, rng, bg).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg nije uspio")
    return Path(dst)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "naslovna_klip.mp4")
