"""Zajedničke pomoćne funkcije za Shofe montažu."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = SKILL_DIR / "fonts"
STYLES_DIR = SKILL_DIR / "styles"
REQUIREMENTS = SKILL_DIR / "requirements.txt"


def data_dir():
    """Korisnikovi podaci koji moraju preživjeti ponovnu instalaciju skilla (npr. naučeni rječnik).
    %LOCALAPPDATA%\\Shofe na Windowsu, ~/.local/share/shofe drugdje; SHOFE_PODACI za testove."""
    env = os.environ.get("SHOFE_PODACI")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Shofe"
    return Path.home() / ".local" / "share" / "shofe"


def version():
    try:
        return (SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"

# Windows konzola zna pasti na č/ć/š/ž/đ
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FORMATS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

# Kolor korekcije (ffmpeg filteri)
GRADES = {
    "neutralno": "eq=contrast=1.03:saturation=1.04",
    "toplo": "eq=contrast=1.06:saturation=1.12:gamma=1.02,colorbalance=rs=0.04:gs=0.01:bs=-0.05:rm=0.03:bm=-0.03",
    "hladno": "eq=contrast=1.05:saturation=1.0,colorbalance=rs=-0.03:bs=0.05:rm=-0.02:bm=0.03",
    "zivo": "eq=contrast=1.10:saturation=1.28:gamma=1.01",
    "kino": "eq=contrast=1.08:saturation=0.86:gamma=0.98,colorbalance=rs=-0.04:gs=0.0:bs=0.06:rh=0.06:gh=0.02:bh=-0.05,vignette=angle=PI/5",
    "crnobijelo": "hue=s=0,eq=contrast=1.15",
}


def die(msg, code=1):
    print(f"GREŠKA: {msg}", file=sys.stderr)
    sys.exit(code)


def find_tool(name):
    p = shutil.which(name)
    if p:
        return p
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        pats = [
            os.path.join(local, "Microsoft", "WinGet", "Links", f"{name}.exe"),
            os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin", f"{name}.exe"),
            os.path.join("C:\\", "ffmpeg", "bin", f"{name}.exe"),
            os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "ffmpeg", "bin", f"{name}.exe"),
        ]
        for pat in pats:
            hits = glob.glob(pat, recursive=True)
            if hits:
                return hits[0]
    return None


def ffmpeg():
    p = find_tool("ffmpeg")
    if not p:
        die("ffmpeg nije pronađen. Pokreni: python scripts/doctor.py --popravi")
    return p


def ffprobe():
    p = find_tool("ffprobe")
    if not p:
        die("ffprobe nije pronađen. Pokreni: python scripts/doctor.py --popravi")
    return p


def ffmpeg_major():
    try:
        out = subprocess.run([ffmpeg(), "-version"], capture_output=True, text=True).stdout
        m = re.search(r"ffmpeg version n?(\d+)", out)
        return int(m.group(1)) if m else 6
    except Exception:
        return 6


def filter_script_args(path):
    """ffmpeg 7+ koristi -/filter_complex <datoteka>, starije -filter_complex_script."""
    if ffmpeg_major() >= 7:
        return ["-/filter_complex", str(path)]
    return ["-filter_complex_script", str(path)]


def run(cmd, cwd=None, quiet=True):
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-25:])
        die(f"naredba nije uspjela ({Path(cmd[0]).name}):\n{tail}")
    if not quiet:
        print(r.stdout)
    return r


def probe(path):
    r = run([ffprobe(), "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    return json.loads(r.stdout)


def video_info(path):
    d = probe(path)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        die(f"{path} nema video zapis")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in (v.get("tags") or {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084")
    return {"w": w, "h": h, "dur": dur, "has_audio": a is not None, "hdr": hdr}


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_styles():
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def load_style(name):
    p = STYLES_DIR / f"{name}.json"
    if not p.exists():
        die(f"nepoznat stil '{name}'. Dostupni: {', '.join(list_styles())}")
    return load_json(p)


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def fmt_time(t):
    m, s = divmod(max(t, 0), 60)
    return f"{int(m):02d}:{s:05.2f}"


def norm_word(w):
    return re.sub(r"[^\wčćšžđ]", "", w.lower())
