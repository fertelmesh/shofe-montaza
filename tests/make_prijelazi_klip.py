"""Uspravni probni klip za prijelaze (M5.2a): tri prizora po 3 s, svaki s vlastitom bojom pozadine, velikim
brojem (1, 2, 3) i nacrtanom osobom na drugom mjestu — da se na slikama vidi koji dio kadra je stari, a koji
novi kadar. U kutu brojač sličica (kvadratić koji putuje).

  python tests/make_prijelazi_klip.py out.mp4

make_projekt(base, scripts) → projekt s mock transkriptom i dva reza (2,6–3,4 s i 5,6–6,4 s snimke), tako da
je svaki rez i promjena prizora.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_naslovna_klip import draw_face  # noqa: E402

W, H, FPS, DUR = 540, 960, 30, 9.0
# BGR boje pozadine prizora i položaj lica (udio širine, visine)
PRIZORI = [((40, 40, 200), (0.50, 0.36)), ((200, 120, 30), (0.35, 0.40)), ((40, 170, 60), (0.62, 0.33))]
IZREZI = [(2.6, 3.4), (5.6, 6.4)]
RIJECI = ("Bok ja sam Marko iz Kutine danas čistimo klimu i pokazujem vam kako se to radi brzo "
          "i jednostavno bez majstora pa krenimo odmah s prvim korakom").split()


def prizor(t):
    return min(2, int(t // 3))


def frame(k):
    import cv2
    t = k / FPS
    i = prizor(t)
    bg, (fx, fy) = PRIZORI[i]
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = bg
    for y in range(0, H, 120):           # vodoravne pruge: vide se rolete i klizanje
        img[y:y + 6] = tuple(min(255, c + 50) for c in bg)
    cv2.putText(img, str(i + 1), (int(W * 0.08), int(H * 0.93)), cv2.FONT_HERSHEY_SIMPLEX, 6, (255, 255, 255), 18)
    draw_face(img, int(W * fx), int(H * fy), 80)
    x = 10 + (k * 7) % (W - 40)
    img[H - 30:H - 12, x:x + 18] = 0
    return img


def make(dst, dur=DUR):
    n = int(dur * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-f", "lavfi", "-i", f"sine=f=220:sample_rate=48000:duration={dur}",
                          "-t", f"{dur:.2f}", "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", str(dst)],
                         stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(frame(k).tobytes())
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg nije uspio")
    return Path(dst)


def make_projekt(base, scripts, ime="projekt prijelazi"):
    """Projekt iz probnog klipa: prepare.py + mock transkript + plan (stil Čisto, bez zuma) + dva izreza."""
    base = Path(base)
    clips = base / "klipovi"
    clips.mkdir(parents=True, exist_ok=True)
    make(clips / "prijelazi.mp4")
    proj = base / ime
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
    edit["izrezi"] = [{"od": a, "do": b, "naredba": "proba"} for a, b in IZREZI]
    (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=1), encoding="utf-8")
    return proj


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "prijelazi_klip.mp4")
