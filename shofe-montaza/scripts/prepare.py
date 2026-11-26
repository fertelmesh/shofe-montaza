"""Korak 1: pripremi klipove (okret, HDR, kadriranje, 30 fps) i spoji ih u source.mp4.

Primjer:
  python prepare.py klip1.mp4 klip2.mp4 --out shofe_projekt
  python prepare.py "C:/Videi/snimanje" --format 9:16
"""
import argparse
import sys
from pathlib import Path

from common import FORMATS, die, ffmpeg, natural_key, run, save_json, video_info

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp"}

HDR_CHAIN = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def collect(inputs):
    files = []
    for i in inputs:
        p = Path(i)
        if p.is_dir():
            files += sorted((f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT), key=natural_key)
        elif p.exists():
            files.append(p)
        else:
            die(f"ne postoji: {i}")
    if not files:
        die("nema video datoteka")
    return files


def norm_clip(f, info, dst, W, H, fps, cx, cy, cmd_file=None):
    """Jedan klip → norm_NN.mp4 u formatu projekta. cmd_file: sendcmd datoteka (ime u istoj mapi kao dst)
    s pomacima kadra kroz vrijeme (kadar.py: kadar prati govornika); tada je cx samo početni položaj."""
    vf = []
    if info["hdr"]:
        vf.append(HDR_CHAIN)
    vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos")
    if cmd_file:
        # ffmpeg čita datoteku iz radne mape (cwd), tako put nema dvotočke ni razmake (Windows)
        vf += [f"sendcmd=f={Path(cmd_file).name}", f"crop@kadar={W}:{H}:(iw-{W})*{cx}:(ih-{H})*{cy}"]
    else:
        vf.append(f"crop={W}:{H}:(iw-{W})*{cx}:(ih-{H})*{cy}")
    vf += [f"fps={fps}", "setsar=1", "format=yuv420p"]
    dst = Path(dst)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", Path(f).resolve()]
    if not info["has_audio"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
    cmd += [
        "-vf", ",".join(vf),
        "-map", "0:v:0", "-map", "0:a:0" if info["has_audio"] else "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "15",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-video_track_timescale", "15360",
        dst.resolve(),
    ]
    run(cmd, cwd=dst.parent)
    return video_info(dst)["dur"]


def concat(parts, tmp, src):
    lst = Path(tmp) / "concat.txt"
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
         "-movflags", "+faststart", src])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("klipovi", nargs="+", help="video datoteke ili mapa (redoslijed = redoslijed u reelu)")
    ap.add_argument("--out", default="shofe_projekt")
    ap.add_argument("--format", default="9:16", choices=list(FORMATS))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crop-x", type=float, default=0.5, help="0=lijevo, 0.5=sredina, 1=desno (kad se reže širi kadar)")
    ap.add_argument("--crop-y", type=float, default=0.4, help="0=gore, 1=dolje (kad se reže viši kadar)")
    ap.add_argument("--crop", action="append", default=[], help="po klipu: ime_klipa=0.3 (crop-x samo za taj klip)")
    a = ap.parse_args()

    W, H = FORMATS[a.format]
    out = Path(a.out)
    (out / "_tmp").mkdir(parents=True, exist_ok=True)
    per_clip = {}
    for c in a.crop:
        k, _, v = c.partition("=")
        per_clip[k.strip().lower()] = float(v)

    files = collect(a.klipovi)
    parts, clips, offset = [], [], 0.0
    for i, f in enumerate(files, 1):
        info = video_info(f)
        cx = per_clip.get(f.name.lower(), per_clip.get(f.stem.lower(), a.crop_x))
        dst = out / "_tmp" / f"norm_{i:02d}.mp4"
        print(f"[{i}/{len(files)}] {f.name}  {info['w']}x{info['h']}  {info['dur']:.1f}s" + ("  HDR→SDR" if info["hdr"] else ""))
        d = norm_clip(f, info, dst, W, H, a.fps, cx, a.crop_y)
        # kadriranje se pamti za izvoz u DaVinci (davinci.py: isti kadar iz originalne snimke)
        clips.append({"file": str(f.resolve()), "start": round(offset, 3), "dur": round(d, 3),
                      "w": info["w"], "h": info["h"], "crop_x": cx, "crop_y": a.crop_y})
        offset += d
        parts.append(dst)

    src = out / "source.mp4"
    concat(parts, out / "_tmp", src)

    save_json(out / "project.json", {
        "format": a.format, "width": W, "height": H, "fps": a.fps,
        "duration": round(video_info(src)["dur"], 3), "clips": clips,
    })
    print(f"\nGotovo: {src}  ({offset:.1f}s, {W}x{H})")
    print(f"Sljedeće: python transcribe.py {out}")


if __name__ == "__main__":
    main()
