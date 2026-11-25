"""Karta videa: što se u videu događa, bez gledanja cijelog videa.

  python analyze.py shofe_projekt              → analiza.json + analiza.txt
  python analyze.py shofe_projekt --bez-slike  (samo zvuk i govor, brže)
  python analyze.py shofe_projekt --provjeri   (provjeri teme/trenutke koje je Claude upisao)

Mjeri: tišine, glasnoću (cijelo i po odsječku), tempo govora (slogova u sekundi),
promjene scene, mutne / tamne / presvijetle kadrove, spojeve klipova.
Teme i najjače trenutke dopisuje Claude u analiza.json ("teme", "trenuci");
ponovno pokretanje ih čuva.
Sva vremena su u sekundama izvornog videa (source.mp4), ista kao u transcript.json i edit.json.
"""
import argparse
import datetime as _dt
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from common import die, ffmpeg, fmt_time, load_json, probe, save_json, version

SR = 16000          # zvuk za analizu: mono 16 kHz
WIN = 0.05          # prozor za razinu zvuka (s)
ANALYSIS_SIDE = 256  # dulja stranica sličice za analizu slike (px)
BLUR_PER_SEC = 5    # koliko puta u sekundi mjerimo oštrinu

TRENUTAK_VRSTE = ("hook", "poanta", "smijeh", "emocija", "savjet", "citat", "akcija", "ostalo")


# ---------------------------------------------------------------- zvuk

def decode_audio(path, sr=SR):
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-acodec", "pcm_s16le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        return None
    return np.frombuffer(r.stdout, np.int16)


def window_db(samples, sr=SR, win=WIN):
    """RMS razina u dBFS po prozorima od `win` sekundi (tišina = -90)."""
    n = int(sr * win)
    k = len(samples) // n
    if k == 0:
        return np.zeros(0, np.float32)
    x = samples[: k * n].astype(np.float32).reshape(k, n) / 32768.0
    rms = np.sqrt((x * x).mean(axis=1))
    return np.maximum(20 * np.log10(rms + 1e-12), -90.0).astype(np.float32)


def segment_db(samples, od, do, sr=SR):
    a, b = int(od * sr), int(do * sr)
    x = samples[max(a, 0): max(b, a + 1)].astype(np.float32) / 32768.0
    if len(x) == 0:
        return -90.0
    return round(max(20 * float(np.log10(np.sqrt((x * x).mean()) + 1e-12)), -90.0), 1)


def silence_threshold(db):
    """Prag tišine prilagođen snimci: između šuma u pozadini i razine govora."""
    floor = float(np.percentile(db, 5))
    speech = float(np.percentile(db, 95))
    thr = floor + 0.35 * (speech - floor)
    thr = min(max(thr, -55.0), speech - 12.0)
    return round(thr, 1), round(floor, 1), round(speech, 1)


def runs(mask):
    """[(početak, kraj)) indeksa gdje je mask True."""
    if len(mask) == 0:
        return []
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def merge_intervals(iv, gap):
    out = []
    for a, b in iv:
        if out and a - out[-1][1] <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def find_silences(db, thr, min_len, win=WIN, bridge=0.15):
    iv = [(a * win, b * win) for a, b in runs(db < thr)]
    iv = merge_intervals(iv, bridge)
    return [{"od": round(a, 2), "do": round(b, 2), "trajanje": round(b - a, 2)} for a, b in iv if b - a >= min_len]


def ebur128(path):
    """Ukupna glasnoća (LUFS), raspon (LU) i vršna razina (dBTP) iz ffmpeg ebur128."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
           "-af", "ebur128=peak=true", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = r.stderr
    summary = txt[txt.rfind("Summary:"):] if "Summary:" in txt else ""

    def grab(label, unit):
        m = re.search(rf"{label}:\s*(-?[\d.]+|-inf)\s*{unit}", summary)
        if not m or m.group(1) == "-inf":
            return None
        return round(float(m.group(1)), 1)

    return grab("I", "LUFS"), grab("LRA", "LU"), grab("Peak", "dBFS")


def loudness_note(lufs, peak):
    notes = []
    if lufs is None:
        return "nema zvuka"
    if lufs < -30:
        notes.append("vrlo tiho (pojačati)")
    elif lufs < -20:
        notes.append("tiše od mreža (render normalizira)")
    elif lufs > -9:
        notes.append("vrlo glasno")
    if peak is not None and peak > -0.5:
        notes.append("vrhovi blizu 0 dB, moguće pucketanje")
    return ", ".join(notes) or "u redu"


# ---------------------------------------------------------------- govor

_VOWEL = "aeiou"


def syllables(word):
    """Broj slogova hrvatske riječi: samoglasnici (+ 'ije' kao jedan) + slogotvorno r."""
    w = re.sub(r"[^a-zčćšžđ0-9]", "", word.lower())
    if not w:
        return 0
    if w.isdigit():
        return 2 * len(w)  # brojke: gruba procjena
    w = w.replace("ije", "e")
    n = sum(c in _VOWEL for c in w)
    for i, c in enumerate(w):
        if c == "r":
            prev_v = i > 0 and w[i - 1] in _VOWEL
            next_v = i + 1 < len(w) and w[i + 1] in _VOWEL
            if not prev_v and not next_v and len(w) > 1:
                n += 1
    return max(n, 1)


def tempo_label(sps):
    if sps is None:
        return None
    if sps < 4.0:
        return "sporo"
    if sps > 6.5:
        return "brzo"
    return "normalno"


def group_words(words, gap):
    from plan import split_segments  # ista podjela kao edit.json → isti brojevi odsječaka
    return split_segments(words, gap)


# ---------------------------------------------------------------- slika

def video_stream_info(path):
    d = probe(path)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if not v:
        return None
    num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(num or 0) > 0 else 30.0
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {"fps": fps, "w": w, "h": h}


def analysis_size(w, h, side=ANALYSIS_SIDE):
    s = side / max(w, h)
    return max(16, int(round(w * s / 8)) * 8), max(16, int(round(h * s / 8)) * 8)


def laplacian_var(y):
    lap = 4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:]
    return float(lap.var())


def scan_video(path, info):
    """Jedan prolaz kroz video u maloj sivoj slici: svjetlina i promjena po sličici, oštrina 5×/s."""
    W, H = analysis_size(info["w"], info["h"])
    fps = info["fps"]
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "0", "-i", str(path),
           "-map", "0:v:0", "-vf", f"scale={W}:{H}:flags=fast_bilinear,format=gray",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    size = W * H
    step = max(1, int(round(fps / BLUR_PER_SEC)))
    bh, bw = H // 8, W // 8
    bright, diff, sharp_t, sharp = [], [], [], []
    prev = None
    i = 0
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        y = np.frombuffer(buf, np.uint8).reshape(H, W).astype(np.float32)
        bright.append(float(y.mean()))
        small = y[: bh * 8, : bw * 8].reshape(bh, 8, bw, 8).mean(axis=(1, 3))
        diff.append(float(np.abs(small - prev).mean()) if prev is not None else 0.0)
        prev = small
        if i % step == 0:
            sharp_t.append(i / fps)
            sharp.append(laplacian_var(y))
        i += 1
    p.stdout.close()
    err = p.stderr.read().decode("utf-8", "replace")
    p.wait()
    if p.returncode != 0 and i == 0:
        die(f"ffmpeg ne može pročitati sliku iz {path}: {err.strip()[-300:]}")
    return {
        "fps": fps,
        "bright": np.array(bright, np.float32),
        "diff": np.array(diff, np.float32),
        "sharp_t": np.array(sharp_t, np.float32),
        "sharp": np.array(sharp, np.float32),
    }


def detect_cuts(diff, fps, ratio=3.0, min_diff=12.0, window=2, min_scene=0.5):
    """Rezovi: promjena sličice puno veća od susjednih (kao PySceneDetect AdaptiveDetector)."""
    cuts = []
    n = len(diff)
    min_gap = int(round(min_scene * fps))
    last = -min_gap
    for i in range(1, n):
        if diff[i] < min_diff:
            continue
        nb = np.concatenate([diff[max(1, i - window): i], diff[i + 1: i + 1 + window]])
        avg = float(nb.mean()) if len(nb) else 0.0
        if diff[i] / (avg + 1.0) >= ratio and i - last >= min_gap:
            cuts.append(i)
            last = i
    return [round(i / fps, 2) for i in cuts]


def bad_shots(scan, duration, bounds=(), min_len=0.5, dark=40.0, bright=230.0, blur_rel=0.35, blur_abs=3.0):
    """Mutni, tamni i presvijetli dijelovi (najmanje `min_len` s).

    Oštrina ovisi o sadržaju (zid je "mutniji" od police s knjigama), pa se mutno mjeri
    unutar svakog kadra: sličica je mutna kad pada ispod 35 % najoštrijih trenutaka
    istog kadra (90. percentil). `bounds` = vremena rezova i spojeva klipova.
    """
    fps = scan["fps"]
    out = []
    b = scan["bright"]
    for name, mask in (("tamno", b < dark), ("presvijetlo", b > bright)):
        for a, e in merge_intervals(runs(mask), int(0.3 * fps)):
            if (e - a) / fps >= min_len:
                out.append({"od": round(a / fps, 2), "do": round(min(e / fps, duration), 2), "razlog": name})
    s, st = scan["sharp"], scan["sharp_t"]
    if len(s) and len(b):
        # tamne sličice su i "mutne"; ne brojimo ih dvaput i ne kvare referencu
        idx = np.clip(np.round(st * fps).astype(int), 0, len(b) - 1)
        lit = (b[idx] >= dark) & (b[idx] <= bright)
        edges = [0.0] + sorted(float(x) for x in bounds) + [float(st[-1]) + 1.0]
        shot = np.searchsorted(np.array(edges[1:-1]), st, side="right")
        blurry = np.zeros(len(s), bool)
        for k in np.unique(shot):
            sel = (shot == k) & lit
            if sel.sum() < 2:
                continue
            ref = float(np.percentile(s[sel], 90))
            blurry |= sel & ((s < blur_rel * ref) | (s < blur_abs))
        dt = 1.0 / BLUR_PER_SEC
        for a, e in merge_intervals(runs(blurry), 1):
            t0, t1 = float(st[a]), float(st[e - 1]) + dt
            if t1 - t0 >= min_len:
                out.append({"od": round(t0, 2), "do": round(min(t1, duration), 2), "razlog": "mutno"})
    return sorted(out, key=lambda x: x["od"])


# ---------------------------------------------------------------- provjera Claudeovih dopuna

def validate_claude_parts(an):
    """Vrati popis grešaka u "teme" i "trenuci" (prazan popis = sve u redu)."""
    errs = []
    dur = an.get("trajanje") or 0

    def t_ok(v):
        return isinstance(v, (int, float)) and 0 <= v <= dur + 0.5

    for i, t in enumerate(an.get("teme") or [], 1):
        if not isinstance(t, dict):
            errs.append(f"teme[{i}] nije objekt")
            continue
        if not str(t.get("naslov", "")).strip():
            errs.append(f"teme[{i}]: nema 'naslov'")
        if not (t_ok(t.get("od")) and t_ok(t.get("do")) and t["od"] < t["do"]):
            errs.append(f"teme[{i}]: 'od'/'do' moraju biti sekunde unutar videa, od < do")
    for i, m in enumerate(an.get("trenuci") or [], 1):
        if not isinstance(m, dict):
            errs.append(f"trenuci[{i}] nije objekt")
            continue
        if m.get("vrsta") not in TRENUTAK_VRSTE:
            errs.append(f"trenuci[{i}]: 'vrsta' mora biti jedno od {', '.join(TRENUTAK_VRSTE)}")
        if not (t_ok(m.get("od")) and t_ok(m.get("do")) and m["od"] < m["do"]):
            errs.append(f"trenuci[{i}]: 'od'/'do' moraju biti sekunde unutar videa, od < do")
        oc = m.get("ocjena")
        if oc is not None and not (isinstance(oc, (int, float)) and 1 <= oc <= 5):
            errs.append(f"trenuci[{i}]: 'ocjena' je 1–5")
        if not str(m.get("opis", "")).strip():
            errs.append(f"trenuci[{i}]: nema 'opis'")
    return errs


# ---------------------------------------------------------------- sažetak

def summary_text(an):
    L = []
    z = an["zvuk"]
    L.append(f"KARTA VIDEA  {fmt_time(an['trajanje'])}  (Shofe {an['shofe']}, analiza {an['trajanje_analize_s']:.0f}s)")
    L.append("")
    L.append(f"Zvuk: {z['glasnoca_lufs']} LUFS, vrh {z['vrh_dbtp']} dB → {z['napomena']}")
    g = an.get("govor")
    if g:
        L.append(f"Govor: {g['udio_govora'] * 100:.0f}% vremena, {g['rijeci_u_minuti']} riječi/min, "
                 f"{g['slogova_u_s']} slogova/s ({g['tempo']})")
    ts = an["tisine"]
    L.append(f"Tišine ≥ {an['postavke']['tisina_min']}s: {len(ts)}, ukupno {sum(t['trajanje'] for t in ts):.1f}s")
    for t in sorted(ts, key=lambda x: -x["trajanje"])[:5]:
        L.append(f"   {fmt_time(t['od'])}-{fmt_time(t['do'])}  {t['trajanje']:.1f}s")
    if an.get("slika"):
        L.append(f"Kadrovi: {len(an['kadrovi'])} (rezova {len(an['promjene_scene'])}, spojeva klipova {len(an['spojevi_klipova'])})")
        if an["losi_kadrovi"]:
            L.append("Loši kadrovi:")
            for b in an["losi_kadrovi"]:
                L.append(f"   {fmt_time(b['od'])}-{fmt_time(b['do'])}  {b['razlog']}")
        else:
            L.append("Loši kadrovi: nema")
    L.append("")
    if an["odsjecci"]:
        L.append("Odsječci (dB = glasnoća, s/s = slogova u sekundi; ! = odstupa):")
        for s in an["odsjecci"]:
            flags = []
            if s.get("glasnoca_oznaka"):
                flags.append(s["glasnoca_oznaka"])
            if s.get("tempo") in ("sporo", "brzo"):
                flags.append(s["tempo"])
            if s.get("losi_kadar"):
                flags.append(s["losi_kadar"])
            tempo = f"{s['slogova_u_s']:>4.1f}s/s" if s.get("slogova_u_s") is not None else "      "
            line = f"#{s['id']:<3} {fmt_time(s['od'])}-{fmt_time(s['do'])} {s['glasnoca_db']:>6.1f}dB {tempo}"
            if s.get("tekst"):
                line += f"  {s['tekst']}"
            if flags:
                line += f"   ! {', '.join(flags)}"
            L.append(line.rstrip())
    L.append("")
    L.append(f"Teme: {len(an.get('teme') or [])}, trenuci: {len(an.get('trenuci') or [])}"
             + ("" if an.get("teme") else "  ← Claude ih dopisuje u analiza.json"))
    for t in an.get("teme") or []:
        L.append(f"   [{fmt_time(t['od'])}-{fmt_time(t['do'])}] {t['naslov']}")
    for m in an.get("trenuci") or []:
        L.append(f"   * {fmt_time(m['od'])} {m['vrsta']} ({m.get('ocjena', '-')}) {m['opis']}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- glavno

def analyze(proj, with_video=True, min_silence=0.5, gap=0.30):
    t0 = time.time()
    src = proj / "source.mp4"
    if not src.exists():
        die(f"nema {src}. Prvo pokreni prepare.py")
    pj = load_json(proj / "project.json") if (proj / "project.json").exists() else {}
    duration = float(pj.get("duration") or float(probe(src)["format"].get("duration") or 0))

    # zvuk
    samples = decode_audio(src)
    if samples is None or len(samples) == 0:
        samples = np.zeros(int(duration * SR), np.int16)
    db = window_db(samples)
    thr, floor, speech = silence_threshold(db) if len(db) else (-50.0, -90.0, -90.0)
    silences = find_silences(db, thr, min_silence) if len(db) else []
    lufs, lra, peak = ebur128(src)
    print(f"Zvuk: {lufs} LUFS, {len(silences)} tišina ({time.time() - t0:.0f}s)")

    # odsječci
    words = []
    tr = proj / "transcript.json"
    if tr.exists():
        words = load_json(tr).get("words") or []
    segs = []
    if words:
        for n, g in enumerate(group_words(words, gap), 1):
            ws = [words[i] for i in g]
            od, do = ws[0]["s"], ws[-1]["e"]
            syl = sum(syllables(w["w"]) for w in ws)
            sps = round(syl / (do - od), 1) if do - od > 0.25 else None
            segs.append({"id": n, "od": round(od, 2), "do": round(do, 2),
                         "tekst": " ".join(w["w"] for w in ws),
                         "glasnoca_db": segment_db(samples, od, do),
                         "slogova_u_s": sps, "tempo": tempo_label(sps)})
    else:
        # bez transkripta: dijelovi sa zvukom između tišina, najviše 10 s
        edges, prev = [], 0.0
        for s in silences:
            if s["od"] > prev:
                edges.append((prev, s["od"]))
            prev = s["do"]
        if duration > prev:
            edges.append((prev, duration))
        for a, b in edges:
            k = max(1, int(np.ceil((b - a) / 10.0)))
            for j in range(k):
                x0, x1 = a + (b - a) * j / k, a + (b - a) * (j + 1) / k
                segs.append({"id": len(segs) + 1, "od": round(x0, 2), "do": round(x1, 2),
                             "glasnoca_db": segment_db(samples, x0, x1)})
    if segs:
        med = float(np.median([s["glasnoca_db"] for s in segs]))
        for s in segs:
            if s["glasnoca_db"] < med - 6:
                s["glasnoca_oznaka"] = "tiho"
            elif s["glasnoca_db"] > med + 6:
                s["glasnoca_oznaka"] = "glasno"

    govor = None
    if words:
        speak = sum(s["do"] - s["od"] for s in segs)
        syl = sum(syllables(w["w"]) for w in words)
        sps = round(syl / speak, 1) if speak > 0 else None
        govor = {"udio_govora": round(min(speak / duration, 1.0), 2) if duration else 0,
                 "rijeci_u_minuti": round(len(words) / (speak / 60), 0) if speak > 0 else 0,
                 "slogova_u_s": sps, "tempo": tempo_label(sps)}

    # slika
    slika, kadrovi, cuts, bad = None, [], [], []
    if with_video:
        info = video_stream_info(src)
        if info:
            t1 = time.time()
            scan = scan_video(src, info)
            cuts = detect_cuts(scan["diff"], scan["fps"])
            joins_t = [c["start"] for c in pj.get("clips", [])[1:]]
            bad = bad_shots(scan, duration, bounds=sorted(set(cuts) | set(joins_t)))
            bounds = [0.0] + cuts + [duration]
            kadrovi = [{"od": round(a, 2), "do": round(b, 2)} for a, b in zip(bounds, bounds[1:]) if b > a]
            slika = {"svjetlina": round(float(scan["bright"].mean()), 1) if len(scan["bright"]) else None,
                     "ostrina_medijan": round(float(np.median(scan["sharp"])), 1) if len(scan["sharp"]) else None,
                     "slicica": len(scan["bright"]), "fps": round(scan["fps"], 3)}
            print(f"Slika: {len(cuts)} rezova, {len(bad)} loših dijelova ({time.time() - t1:.0f}s)")
            for s in segs:
                hit = [b for b in bad if b["od"] < s["do"] and b["do"] > s["od"]]
                if hit:
                    s["losi_kadar"] = "/".join(sorted({b["razlog"] for b in hit}))

    joins = [round(c["start"], 2) for c in pj.get("clips", [])[1:]]

    old = {}
    if (proj / "analiza.json").exists():
        try:
            old = load_json(proj / "analiza.json")
        except Exception:
            old = {}
    an = {
        "shofe": version(),
        "napravljeno": _dt.datetime.now().isoformat(timespec="seconds"),
        "izvor": "source.mp4",
        "trajanje": round(duration, 2),
        "trajanje_analize_s": 0.0,
        "postavke": {"tisina_min": min_silence, "pauza_odsjecka": gap},
        "zvuk": {"glasnoca_lufs": lufs, "raspon_lu": lra, "vrh_dbtp": peak,
                 "sum_db": floor, "govor_db": speech, "prag_tisine_db": thr,
                 "napomena": loudness_note(lufs, peak)},
        "govor": govor,
        "tisine": silences,
        "odsjecci": segs,
        "slika": slika,
        "kadrovi": kadrovi,
        "promjene_scene": cuts,
        "spojevi_klipova": joins,
        "losi_kadrovi": bad,
        # dopisuje Claude (vidi SKILL.md); čuvaju se kod ponovne analize
        "teme": old.get("teme") or [],
        "trenuci": old.get("trenuci") or [],
    }
    an["trajanje_analize_s"] = round(time.time() - t0, 1)
    return an


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--bez-slike", action="store_true", help="preskoči analizu slike (brže)")
    ap.add_argument("--tisina", type=float, default=0.5, help="najkraća tišina koja se bilježi (s)")
    ap.add_argument("--pauza", type=float, default=0.30, help="pauza koja dijeli odsječke (kao plan.py)")
    ap.add_argument("--provjeri", action="store_true", help="samo provjeri 'teme' i 'trenuci' u analiza.json")
    a = ap.parse_args()

    proj = Path(a.projekt)
    if a.provjeri:
        p = proj / "analiza.json"
        if not p.exists():
            die("nema analiza.json. Prvo pokreni analyze.py")
        an = load_json(p)
        errs = validate_claude_parts(an)
        if errs:
            print("\n".join(errs))
            sys.exit(1)
        (proj / "analiza.txt").write_text(summary_text(an), encoding="utf-8")
        print(f"U redu: {len(an.get('teme') or [])} tema, {len(an.get('trenuci') or [])} trenutaka. analiza.txt osvježen.")
        return

    an = analyze(proj, with_video=not a.bez_slike, min_silence=a.tisina, gap=a.pauza)
    save_json(proj / "analiza.json", an)
    txt = summary_text(an)
    (proj / "analiza.txt").write_text(txt, encoding="utf-8")
    print()
    print(txt)
    print(f"Gotovo za {an['trajanje_analize_s']:.0f}s → {proj / 'analiza.json'}")
    if not (proj / "transcript.json").exists():
        print("Napomena: nema transcript.json, pa nema teksta ni tempa govora. Pokreni transcribe.py pa ponovno analyze.py.")


if __name__ == "__main__":
    main()
