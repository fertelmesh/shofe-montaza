"""Provjera i popravak okruženja.

  python doctor.py            provjeri sve
  python doctor.py --popravi  instaliraj što nedostaje (ffmpeg preko wingeta, Python pakete iz requirements.txt)
  python doctor.py --verzija  samo ispiši verziju Shofea
"""
import argparse
import os
import subprocess
import sys

from common import FONTS_DIR, REQUIREMENTS, STYLES_DIR, find_tool, ffmpeg_major, version

OK, BAD = "[OK]", "[!!]"


def check_ffmpeg():
    p = find_tool("ffmpeg")
    if not p or not find_tool("ffprobe"):
        return False, "ffmpeg/ffprobe nije pronađen"
    out = subprocess.run([p, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    enc = subprocess.run([p, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    missing = [f for f in ("subtitles", "loudnorm", "sidechaincompress", "afftdn", "zscale") if f" {f} " not in out]
    if "libx264" not in enc:
        missing.append("libx264")
    if missing:
        return False, f"ffmpeg {ffmpeg_major()} nema: {', '.join(missing)} (instaliraj puni build: winget install Gyan.FFmpeg)"
    return True, f"ffmpeg {ffmpeg_major()} ({p})"


def check_whisper():
    try:
        import faster_whisper
        return True, f"faster-whisper {faster_whisper.__version__}"
    except ImportError:
        return False, "faster-whisper nije instaliran"


def check_sherpa():
    try:
        import sherpa_onnx
        return True, f"sherpa-onnx {getattr(sherpa_onnx, '__version__', '?')} (prepoznavanje govornika)"
    except ImportError:
        return False, "sherpa-onnx nije instaliran (treba za prepoznavanje govornika)"


def check_opencv():
    try:
        import cv2
        ok = hasattr(cv2, "FaceDetectorYN")
        return ok, f"OpenCV {cv2.__version__} (lica: kadar prati govornika)" + ("" if ok else " — prestar, treba 4.8+")
    except ImportError:
        return False, "OpenCV nije instaliran (treba za kadar koji prati govornika)"


def check_pillow():
    try:
        import PIL
        return True, f"Pillow {PIL.__version__} (naslovne sličice)"
    except ImportError:
        return False, "Pillow nije instaliran (treba za naslovne sličice)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--popravi", action="store_true")
    ap.add_argument("--verzija", action="store_true")
    a = ap.parse_args()

    print(f"Shofe {version()}")
    if a.verzija:
        return

    checks = {
        "python": (sys.version_info >= (3, 9), f"Python {sys.version.split()[0]}"),
        "ffmpeg": check_ffmpeg(),
        "whisper": check_whisper(),
        "govornici": check_sherpa(),
        "lica": check_opencv(),
        "slike": check_pillow(),
        "fontovi": (len(list(FONTS_DIR.glob("*.ttf"))) >= 3, f"{len(list(FONTS_DIR.glob('*.ttf')))} fontova"),
        "stilovi": (len(list(STYLES_DIR.glob("*.json"))) >= 1, f"{len(list(STYLES_DIR.glob('*.json')))} stilova"),
    }
    for k, (ok, msg) in checks.items():
        print(f"{OK if ok else BAD} {k}: {msg}")
    # HTML grafika (HyperFrames + Node.js) nije nužna za montažu: bez nje video izađe bez grafike
    import grafika
    g_ok, g_msg = grafika.stanje()
    print(f"{OK if g_ok else '[--]'} grafika: {g_msg}" + ("" if g_ok else " — montaža radi i bez toga"))
    # model za izdvajanje osobe (tekst iza osobe): skine se sam pri prvom efektu
    import osoba
    o_ok, o_msg = osoba.stanje()
    print(f"{OK if o_ok else '[--]'} osoba: {o_msg}")

    if a.popravi:
        if not (checks["whisper"][0] and checks["govornici"][0] and checks["lica"][0] and checks["slike"][0]):
            print("\nInstaliram Python pakete...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(REQUIREMENTS)])
        if not g_ok and grafika.node()[1] and grafika.node()[1] >= grafika.NODE_MIN:
            print("\nInstaliram HyperFrames (HTML grafika)...")
            try:
                print(grafika.instaliraj())
            except grafika.Greska as ex:
                print(f"HyperFrames nije instaliran: {ex}")
        if not o_ok:
            try:
                print(f"\nModel osobe: {osoba.ensure_model()}")
            except osoba.Greska as ex:
                print(f"Model osobe nije skinut: {ex}")
        if not checks["ffmpeg"][0]:
            if os.name == "nt":
                print("\nInstaliram ffmpeg preko wingeta...")
                subprocess.run(["winget", "install", "-e", "--id", "Gyan.FFmpeg",
                                "--accept-source-agreements", "--accept-package-agreements"])
                print("Ako ffmpeg i dalje nije pronađen, zatvori i ponovno otvori Claude (novi PATH).")
            else:
                print("\nInstaliraj ffmpeg: brew install ffmpeg (Mac) ili sudo apt install ffmpeg (Linux)")
        print("\nPonovna provjera:")
        # ne os.execv: na Windowsu razbija putanje s razmacima
        sys.exit(subprocess.run([sys.executable, __file__]).returncode)

    bad = [k for k, (ok, _) in checks.items() if not ok]
    if bad:
        print(f"\nNedostaje: {', '.join(bad)}. Pokreni: python doctor.py --popravi")
        sys.exit(1)
    print("\nSve spremno za montažu.")


if __name__ == "__main__":
    main()
