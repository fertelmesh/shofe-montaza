"""Izvoz u DaVinci Resolve: timeline (FCPXML 1.10) s istim rezovima kao Shofeov video + SRT titlovi.

  python davinci.py shofe_projekt                  verzija koju gledaš → reel_vN.fcpxml (+ reel_vN.srt)
  python davinci.py shofe_projekt --verzija 2      starija verzija
  python davinci.py shofe_projekt --trenutno       iz trenutnog edit.json (bez rendera)
  python davinci.py shofe_projekt --izvor priprema umjesto originalnih snimki koristi source.mp4
  python davinci.py shofe_projekt --ispis          ispiši kadrove (izvorna datoteka, od–do)

render.py ovo radi sam uz svaki video. U DaVinciju (i besplatnom): File > Import > Timeline >
reel_vN.fcpxml, zatim File > Import > Subtitle > reel_vN.srt i povuci titlove na timeline.

Timeline koristi ORIGINALNE snimke (mobitel, kamera) s istim rezovima, kadriranjem (9:16 iz
vodoravne snimke) i zumovima; zvuk i boja ostaju neobrađeni. Glazba ide na zasebnu traku.
Naslov (hook), stil i zumovi upisani su i kao oznake (markeri) da se vidi što je Shofe radio.
Ako originalna snimka više ne postoji, cijeli timeline koristi pripremljeni source.mp4.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path, PureWindowsPath

from common import GRADES, die, ffmpeg, fmt_time, load_json, probe, run

FCPXML_VERSION = "1.10"   # DaVinci Resolve 18+ uvozi 1.10 (17 samo do 1.8/1.9)
COMMON_RATES = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                Fraction(48), Fraction(50), Fraction(60000, 1001), Fraction(60), Fraction(100),
                Fraction(120000, 1001), Fraction(120)]
ZOOM_Y = 0.38             # render.zoom_chain kadrira zum na 38 % visine, ne na sredini


# ---------------------------------------------------------------- vrijeme
def ftime(x):
    """Fraction sekundi → FCPXML vrijeme ("1001/30000s", "5s")."""
    x = Fraction(x)
    return f"{x.numerator}s" if x.denominator == 1 else f"{x.numerator}/{x.denominator}s"


def parse_time(s):
    """FCPXML vrijeme → Fraction (za testove i provjeru)."""
    s = s.rstrip("s")
    if "/" in s:
        a, b = s.split("/")
        return Fraction(int(a), int(b))
    return Fraction(s)


def snap_rate(r):
    """Stvarni broj sličica (npr. 2997/100, 30/1, 90000/3001 kod promjenjivog) → uobičajeni (30000/1001)."""
    try:
        r = Fraction(r)
    except (ValueError, ZeroDivisionError):
        return None
    if r <= 0:
        return None
    best = min(COMMON_RATES, key=lambda c: abs(c - r))
    return best if abs(best - r) / best < 0.02 else None


def on_grid(t, fd):
    """Zaokruži vrijeme (sekunde) na najbližu sličicu trajanja fd."""
    return round(Fraction(t) / fd) * fd


# ---------------------------------------------------------------- izvorne datoteke
def file_uri(path):
    """Apsolutna putanja → file:// URI (Windows: file:///C:/Videi/Sun%C4%8Dani%20put/klip.mp4)."""
    s = str(path)
    if re.match(r"^[A-Za-z]:[\\/]", s) or s.startswith("\\\\"):
        return PureWindowsPath(s).as_uri()
    return Path(s).resolve().as_uri()


def parse_tc(tc, rate):
    """Vremenski kod "HH:MM:SS:FF" (ili ; za drop-frame) → Fraction sekundi."""
    m = re.match(r"^(\d+):(\d+):(\d+)[:;.](\d+)$", tc or "")
    if not m or not rate:
        return Fraction(0)
    h, mi, s, f = map(int, m.groups())
    nominal = round(rate)
    frames = ((h * 60 + mi) * 60 + s) * nominal + f
    if ";" in tc and nominal in (30, 60):   # drop-frame: preskače 2 (4) broja svake minute osim desete
        drop = 2 if nominal == 30 else 4
        mins = h * 60 + mi
        frames -= drop * (mins - mins // 10)
    return frames / rate


def media_info(path):
    """Što FCPXML treba znati o izvornoj datoteci: sličice, trajanje, vremenski kod, zvuk."""
    d = probe(path)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        die(f"{path} nema video zapis")
    rate = snap_rate(v.get("avg_frame_rate")) or snap_rate(v.get("r_frame_rate"))
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in (v.get("tags") or {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    tc = (v.get("tags") or {}).get("timecode") or (d["format"].get("tags") or {}).get("timecode")
    if not tc:
        tcs = next((s for s in d["streams"] if (s.get("tags") or {}).get("timecode")), None)
        tc = tcs["tags"]["timecode"] if tcs else None
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    return {"rate": rate, "w": w, "h": h, "dur": dur, "tc": parse_tc(tc, rate) if tc else Fraction(0),
            "audio": a is not None, "channels": int(a.get("channels", 2)) if a else 0,
            "audio_rate": int(a.get("sample_rate", 48000)) if a else 48000}


# ---------------------------------------------------------------- iz edit.json u kadrove
def pieces_for(cuts, clips, fps, use_originals):
    """Rezovi u vremenu source.mp4 → kadrovi po izvornim datotekama.
    Svaki kadar: {clip: indeks ili None (source.mp4), src: od (s, u toj datoteci), frames, out: početak u
    gotovom videu (sličice prije brzine)}. Rez koji prelazi spoj dvaju klipova dijeli se na dva kadra."""
    bounds = []
    if use_originals:
        for k, c in enumerate(clips):
            a = round(c["start"] * fps)
            b = round((c["start"] + c["dur"]) * fps)
            bounds.append((k, a, b))
    res = []
    for c in cuts:
        A, B, O = round(c["a"] * fps), round(c["b"] * fps), round(c["o"] * fps)
        if not bounds:
            res.append({"clip": None, "src": Fraction(A, fps), "frames": B - A, "out": O})
            continue
        pos = A
        while pos < B:
            k, ca, cb = next(((k, ca, cb) for k, ca, cb in bounds if ca <= pos < cb), bounds[-1])
            end = min(B, cb) if pos < cb else B
            if end <= pos:
                break
            res.append({"clip": k, "src": Fraction(pos - ca, fps), "frames": end - pos, "out": O + (pos - A)})
            pos = end
    res = split_by_framing(res, clips, fps) if use_originals else res
    # zaokruživanje početaka klipova (ms) zna dati kadar od 1 sličice na spoju: pripoji ga susjedu
    merged = []
    for p in res:
        if (merged and p["frames"] <= 1 and merged[-1]["out"] + merged[-1]["frames"] == p["out"]
                and merged[-1].get("crop_x") == p.get("crop_x")):
            merged[-1]["frames"] += p["frames"]
        else:
            merged.append(p)
    return merged


def split_by_framing(pieces, clips, fps):
    """Kadar prati govornika (kadar.py): kadar iz originala se dijeli na promjeni govornika, a svaki dio
    dobije svoj crop_x (kao rez u multicam montaži). Kadar u kojem kamera ide za licem dobije srednji položaj."""
    out = []
    for p in pieces:
        c = clips[p["clip"]] if p["clip"] is not None else {}
        ks = c.get("kadrovi") or []
        if not ks:
            out.append(p)
            continue
        a0 = round(p["src"] * fps)
        pos, end = a0, a0 + p["frames"]
        while pos < end:
            k = next((k for k in ks if round(k["od"] * fps) <= pos < round(k["do"] * fps)), ks[-1])
            stop = min(end, max(pos + 1, round(k["do"] * fps))) if k is not ks[-1] else end
            out.append({**p, "src": Fraction(pos, fps), "frames": stop - pos, "out": p["out"] + (pos - a0),
                        "crop_x": k["crop_x"]})
            pos = stop
    return out


def framing(clip, W, H, zoom=1.0):
    """Pomak slike (FCPXML adjust-transform position, postotak visine kadra) da se vidi isti dio
    snimke kao u Shofeovu videu: prepare.py reže širu snimku na crop_x/crop_y, render zumira na 38 %."""
    w, h = clip.get("w"), clip.get("h")
    px = py = 0.0
    if w and h:
        s = max(W / w, H / h)
        sw, sh = w * s, h * s
        px = (0.5 - float(clip.get("crop_x", 0.5))) * (sw - W)
        py = -(0.5 - float(clip.get("crop_y", 0.4))) * (sh - H)   # FCPXML: +y je gore
    px, py = px * zoom, py * zoom
    py -= (0.5 - ZOOM_Y) * (zoom - 1) * H
    return round(px / H * 100, 3) + 0.0, round(py / H * 100, 3) + 0.0   # + 0.0: bez „-0“


def music_path(proj, music):
    mp = Path(music)
    if not mp.is_absolute():
        mp = (proj / mp) if (proj / mp).exists() else Path.cwd() / mp
    return mp if mp.exists() else None


def loudness(path):
    """Integrirana glasnoća (LUFS) glazbe; render je normalizira na −16 LUFS prije glasnoće iz edit.json."""
    try:
        r = run([ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"])
        txt = (r.stderr or "") + (r.stdout or "")
        m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", txt)
        return float(m[-1]) if m else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- FCPXML
def build(proj, edit, use_originals=True, name=None):
    """Vrati (ElementTree korijen, sažetak). Ne piše ništa na disk."""
    import render  # rezovi, zumovi i stil točno kao u renderu

    proj = Path(proj)
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    W, H, fps = pj["width"], pj["height"], int(round(pj["fps"]))
    st = render.resolve_style(edit)
    cuts, _, total = render.build_cuts(words, edit, st, fps, pj["duration"])
    if not cuts:
        die("nema ničega za zadržati (svi odsječci su isključeni?)")
    speed = Fraction(str(float(edit.get("brzina") or 1.0)))
    factor, zr = render.zoom_ranges(cuts, st)

    clips = pj.get("clips") or []
    missing = [c["file"] for c in clips if not Path(c["file"]).exists()]
    notes = []
    if use_originals and (not clips or missing):
        if missing:
            notes.append(f"originalna snimka ne postoji ({Path(missing[0]).name}"
                         + (f" i još {len(missing) - 1}" if len(missing) > 1 else "") + ") → koristim source.mp4")
        use_originals = False
    pieces = pieces_for(cuts, clips, fps, use_originals)

    fd = Fraction(1, fps)
    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", frameDuration=ftime(fd), width=str(W), height=str(H),
                  colorSpace="1-1-1 (Rec. 709)")
    assets, n_res = {}, [1]

    def new_id():
        n_res[0] += 1
        return f"r{n_res[0]}"

    def asset_for(key, path, display_name):
        if key in assets:
            return assets[key]
        info = media_info(path)
        rate = info["rate"] or Fraction(fps)
        afd = 1 / rate
        fid = new_id()
        ET.SubElement(res, "format", id=fid, frameDuration=ftime(afd), width=str(info["w"]), height=str(info["h"]))
        aid = new_id()
        el = ET.SubElement(res, "asset", id=aid, name=display_name, start=ftime(on_grid(info["tc"], afd)),
                           duration=ftime(on_grid(info["dur"], afd)), hasVideo="1", format=fid,
                           hasAudio="1" if info["audio"] else "0", videoSources="1")
        if info["audio"]:
            el.set("audioSources", "1")
            el.set("audioChannels", str(info["channels"]))
            el.set("audioRate", str(info["audio_rate"]))
        ET.SubElement(el, "media-rep", kind="original-media", src=file_uri(Path(path).resolve()))
        assets[key] = {"id": aid, "afd": afd, "tc": on_grid(info["tc"], afd), "info": info, "name": display_name}
        return assets[key]

    lib = ET.SubElement(root, "library")
    event = ET.SubElement(lib, "event", name="Shofe")
    title = name or proj.name
    project = ET.SubElement(event, "project", name=title)
    seq = ET.SubElement(project, "sequence", format="r1", tcStart="0s", tcFormat="NDF",
                        audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")

    # gotov video u sličicama (nakon brzine): kadar n počinje tamo gdje završava n−1
    out_frames, t = [], 0
    for p in pieces:
        n = max(1, round(p["frames"] / speed)) if speed != 1 else p["frames"]
        out_frames.append((t, n))
        t += n
    total_frames = t

    clip_els = []
    zoomed_pieces = 0
    for p, (o, n) in zip(pieces, out_frames):
        if p["clip"] is None:
            a = asset_for("source", proj / "source.mp4", "source.mp4")
            clip = {}
        else:
            c = clips[p["clip"]]
            a = asset_for(p["clip"], c["file"], Path(c["file"]).name)
            clip = {**c, "crop_x": p["crop_x"]} if "crop_x" in p else c
        src_start = a["tc"] + on_grid(p["src"], a["afd"])
        mid = (p["out"] + p["frames"] / 2) / fps          # sredina kadra u vremenu prije brzine
        z = factor if factor and any(s <= mid < e for s, e in zr) else 1.0
        dur = n * fd
        if speed != 1:
            # timeMap: vrijeme kadra (time) ↔ vrijeme snimke (value); početak je u usporenom/ubrzanom vremenu
            start = on_grid(src_start / speed, fd)
            el = ET.SubElement(spine, "asset-clip", ref=a["id"], name=a["name"], offset=ftime(o * fd),
                               start=ftime(start), duration=ftime(dur), tcFormat="NDF")
            tm = ET.SubElement(el, "timeMap")
            adur = on_grid(a["info"]["dur"], a["afd"]) + a["tc"]
            ET.SubElement(tm, "timept", time="0s", value="0s", interp="linear")
            ET.SubElement(tm, "timept", time=ftime(on_grid(adur / speed, fd)), value=ftime(adur), interp="linear")
        else:
            el = ET.SubElement(spine, "asset-clip", ref=a["id"], name=a["name"], offset=ftime(o * fd),
                               start=ftime(src_start), duration=ftime(dur), tcFormat="NDF")
        if p["clip"] is not None:
            ET.SubElement(el, "adjust-conform", type="fill")
        if p["clip"] is not None or z != 1.0:
            px, py = framing(clip, W, H, z) if p["clip"] is not None else framing({}, W, H, z)
            attrs = {}
            if abs(px) >= 0.05 or abs(py) >= 0.05:
                attrs["position"] = f"{px:g} {py:g}"
            if z != 1.0:
                attrs["scale"] = f"{z:g} {z:g}"
                zoomed_pieces += 1
            if attrs:
                ET.SubElement(el, "adjust-transform", **attrs)
        clip_els.append((el, o, n, parse_time(el.get("start"))))

    # glazba: zasebna traka ispod (lane −1), usidrena na prvi kadar, ponavlja se do kraja videa
    music = edit.get("glazba")
    if music:
        mp = music_path(proj, music)
        if not mp:
            notes.append(f"glazba ne postoji: {music}")
        else:
            info = media_info_audio(mp)
            aid = new_id()
            mdur = on_grid(info["dur"], fd)
            el = ET.SubElement(res, "asset", id=aid, name=mp.name, start="0s", duration=ftime(mdur),
                               hasVideo="0", hasAudio="1", audioSources="1",
                               audioChannels=str(info["channels"]), audioRate=str(info["audio_rate"]))
            ET.SubElement(el, "media-rep", kind="original-media", src=file_uri(mp.resolve()))
            vol = float(edit.get("glazba_glasnoca") or -20)
            lufs = loudness(mp)
            gain = round(vol + (-16 - lufs), 1) if lufs is not None else vol
            first, _, _, fstart = clip_els[0]
            pos = Fraction(0)
            total_t = total_frames * fd
            anchors = []
            while pos < total_t and mdur > 0:
                d = min(mdur, total_t - pos)
                anchors.append((pos, d))
                pos += d
            for pos, d in anchors:
                m = ET.Element("asset-clip", ref=aid, name=mp.name, lane="-1", offset=ftime(fstart + pos),
                               start="0s", duration=ftime(d), audioRole="music")
                ET.SubElement(m, "adjust-volume", amount=f"{gain:g}dB")
                _insert_anchored(first, m)
            notes.append(f"glazba na traci ispod: {mp.name}, {gain:g} dB"
                         + (f", {len(anchors)}× zaredom" if len(anchors) > 1 else "")
                         + " (stišavanje ispod govora nije preneseno)")

    # oznake: što je Shofe dodao preko slike (naslov, stil, zumovi)
    def marker_at(frame, value, note=None, dur_frames=1):
        for el, o, n, start in clip_els:
            if o <= frame < o + n:
                attrs = {"start": ftime(start + (frame - o) * fd), "duration": ftime(max(1, dur_frames) * fd),
                         "value": value}
                if note:
                    attrs["note"] = note
                _insert_marker(el, ET.Element("marker", **attrs))
                return

    grade = st.get("boja_slike", "neutralno")
    marker_at(0, f"Shofe stil: {st.get('naziv', edit.get('stil'))}",
              f"boja slike: {grade} ({GRADES.get(grade, '')}); zvuk i boja u ovom timelineu su neobrađeni")
    hook = (edit.get("hook") or "").strip()
    if hook:
        hd = min(float(edit.get("hook_trajanje") or 3.0), total)
        marker_at(0, f"Naslov: {hook}", "naslov (hook) na vrhu slike u Shofeovu videu",
                  round(hd / float(speed) * fps))
    if zr:
        for s, e in zr:
            f0 = round(s / float(speed) * fps)
            marker_at(f0, f"Zum {round(factor * 100)} %", "Shofe: punch-in zum (već postavljen kao Zoom/Scale)",
                      round((e - s) / float(speed) * fps))

    seq.set("duration", ftime(total_frames * fd))
    ET.indent(root, space="  ")
    summary = {"kadrova": len(pieces), "sekundi": float(total_frames * fd), "izvor": "originali" if use_originals
               else "source.mp4", "datoteke": sorted({a["name"] for a in assets.values()}), "zumova": zoomed_pieces,
               "napomene": notes, "brzina": float(speed), "pieces": pieces, "fps": fps}
    return root, summary


def media_info_audio(path):
    d = probe(path)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not a:
        die(f"{path} nema zvuk")
    return {"dur": float(d["format"].get("duration") or a.get("duration") or 0),
            "channels": int(a.get("channels", 2)), "audio_rate": int(a.get("sample_rate", 48000))}


# redoslijed djece asset-clipa po DTD-u 1.10: timeMap, adjust-*, usidreni klipovi, markeri
_ORDER = {"note": 0, "conform-rate": 1, "timeMap": 2, "adjust-conform": 3, "adjust-transform": 4,
          "adjust-volume": 5, "asset-clip": 6, "marker": 7}


def _insert(parent, child):
    rank = _ORDER.get(child.tag, 9)
    for i, c in enumerate(list(parent)):
        if _ORDER.get(c.tag, 9) > rank:
            parent.insert(i, child)
            return
    parent.append(child)


_insert_anchored = _insert
_insert_marker = _insert


def write(root, path):
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    Path(path).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + body + "\n",
                          encoding="utf-8", newline="\n")


def export(proj, edit, base, use_originals=True, name=None):
    """Napiši <base>.fcpxml u projekt; vrati (putanja, sažetak)."""
    proj = Path(proj)
    root, summ = build(proj, edit, use_originals, name)
    out = proj / f"{base}.fcpxml"
    write(root, out)
    return out, summ


def for_render(proj, edit, out_video):
    """render.py: uz svaki video i .fcpxml. Greška ovdje nikad ne ruši render."""
    try:
        out, summ = export(proj, edit, Path(out_video).stem, name=f"{Path(proj).name} {Path(out_video).stem}")
        lines = [f"DaVinci timeline: {out.name}  ({summ['kadrova']} kadrova iz "
                 + ("originalnih snimki" if summ["izvor"] == "originali" else "source.mp4") + ")"]
        lines += [f"  ({n})" for n in summ["napomene"] if "ne postoji" in n]
        return lines
    except SystemExit as e:  # die() u izvozu
        return [f"(DaVinci timeline nije napravljen: {e})"]
    except Exception as e:  # noqa: BLE001
        return [f"(DaVinci timeline nije napravljen: {e})"]


def main():
    import titlovi

    ap = argparse.ArgumentParser(description="Izvoz u DaVinci Resolve (FCPXML + SRT)")
    ap.add_argument("projekt")
    ap.add_argument("--verzija", type=int, default=None, help="broj verzije (reel_vN); zadano: ona koju gledaš")
    ap.add_argument("--trenutno", action="store_true", help="iz trenutnog edit.json")
    ap.add_argument("--izvor", default="original", choices=["original", "priprema"],
                    help="original = snimke s mobitela/kamere (zadano); priprema = source.mp4")
    ap.add_argument("--izlaz", default=None, help="ime datoteke bez nastavka (zadano reel_vN)")
    ap.add_argument("--ispis", action="store_true", help="ispiši kadrove")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    edit, base, what = titlovi.pick(proj, a.verzija, a.trenutno)
    base = a.izlaz or base
    out, summ = export(proj, edit, base, a.izvor == "original", name=f"{proj.name} {base}")
    srt = proj / f"{base}.srt"
    if not srt.exists():
        cues, _ = titlovi.cues_for(proj, edit)
        titlovi.write_srt(srt, cues)
    if a.ispis:
        pj = load_json(proj / "project.json")
        clips = pj.get("clips") or []
        fps = summ["fps"]
        for i, p in enumerate(summ["pieces"], 1):
            f = Path(clips[p["clip"]]["file"]).name if p["clip"] is not None else "source.mp4"
            print(f"{i:3d}  {fmt_time(p['out'] / fps)}  {f}  {fmt_time(float(p['src']))}–"
                  f"{fmt_time(float(p['src']) + p['frames'] / fps)}")
        print()
    print(f"DaVinci ({what}): {summ['kadrova']} kadrova, {fmt_time(summ['sekundi'])}, izvor: "
          + ", ".join(summ["datoteke"]))
    for n in summ["napomene"]:
        print(f"  napomena: {n}")
    print(f"  {out}\n  {srt}")
    print("U DaVinciju: File > Import > Timeline > " + out.name + ", zatim File > Import > Subtitle > " + srt.name)


if __name__ == "__main__":
    sys.exit(main())
