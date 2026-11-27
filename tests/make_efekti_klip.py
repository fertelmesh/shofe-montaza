"""Uspravni probni klip za efekte (M5.1): nacrtana osoba ispred police s mrežom pločica, lice se polako
pomiče vodoravno (zamrznuti kadar se vidi), u kutu brojač sličica (crni kvadratić koji putuje).

  python tests/make_efekti_klip.py out.mp4

Uz klip: make_projekt(base) → projekt s transkriptom (mock riječi svakih 0,4 s) i edit.json (stil Čisto,
bez automatskog zuma), spreman za efekti.py i render.py.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_naslovna_klip import draw_face  # noqa: E402

W, H, FPS, DUR = 540, 960, 30, 8.0
LICE = (0.5, 0.36)       # sredina lica (udio širine/visine) u t = 0
POMAK = 40               # px vodoravno u sekundi
RIJECI = ("Bok ja sam Marko iz Kutine danas čistimo klimu i pokazujem vam kako se to radi brzo "
          "i jednostavno bez majstora pa krenimo odmah").split()


def background():
    import cv2
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:] = (110, 120, 105)
    rng = np.random.default_rng(5)
    for y in range(0, H, 48):            # pločice: vidi se zum i rastezanje rubova
        for x in range(0, W, 48):
            c = tuple(int(v) for v in rng.integers(60, 200, 3))
            cv2.rectangle(bg, (x + 3, y + 3), (x + 44, y + 44), c, -1)
    cv2.rectangle(bg, (0, int(H * .78)), (W, H), (70, 80, 90), -1)
    return bg


def frame(k, bg):
    img = bg.copy()
    t = k / FPS
    draw_face(img, int(W * LICE[0] + POMAK * (t - DUR / 2)), int(H * LICE[1]), 95)
    x = 10 + (k * 7) % (W - 40)          # „brojač": kvadratić koji svake sličice ide 7 px desno
    img[H - 40:H - 20, x:x + 20] = 0
    return img


def make(dst, dur=DUR):
    bg = background()
    n = int(dur * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", f"sine=f=220:sample_rate=48000:duration={dur}",
                          "-t", f"{dur:.2f}", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", str(dst)],
                         stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(frame(k, bg).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg nije uspio")
    return Path(dst)


def make_projekt(base, scripts):
    """Projekt iz probnog klipa: prepare.py + mock transkript + plan (stil Čisto, bez zuma stila)."""
    base = Path(base)
    clips = base / "klipovi"
    clips.mkdir(parents=True, exist_ok=True)
    make(clips / "efekti.mp4")
    proj = base / "projekt efekti"
    py = sys.executable
    subprocess.run([py, str(Path(scripts) / "prepare.py"), str(clips), "--out", str(proj)], check=True,
                   capture_output=True)
    words = [{"w": w, "s": round(0.2 + 0.4 * i, 3), "e": round(0.2 + 0.4 * i + 0.34, 3)} for i, w in enumerate(RIJECI)]
    words = [w for w in words if w["e"] < DUR - 0.1]
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                     ensure_ascii=False), encoding="utf-8")
    subprocess.run([py, str(Path(scripts) / "plan.py"), str(proj), "--stil", "cisto"], check=True, capture_output=True)
    edit = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    edit["zoom"] = "nema"
    edit["titlovi"] = False
    (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=1), encoding="utf-8")
    return proj


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "efekti_klip.mp4")
