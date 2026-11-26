"""Podcast (M4.1): sinkronizacija više kamera i zasebnog zvuka po zvuku, bez klapne i bez ručnog rada.

  python sinkro.py kamera1.mp4 kamera2.mp4 zvuk.wav --out podcast        → podcast/sinkro.json (+ .txt, .png, provjera)
  python sinkro.py "C:/Snimanje/epizoda12" --out podcast                 cijela mapa (video + zvuk)
  python sinkro.py podcast --provjera 12:30                              ponovno samo video za provjeru oko 12:30
  python sinkro.py podcast --pomak kamera2.mp4=-3.25                     ručni ispravak jednog izvora (iznimka)

Glavni izvor (vremenska crta epizode) je zasebni zvuk ako postoji (najdulji audio), inače najdulji video;
`--glavni ime` bira drugi. Za svaki drugi izvor Shofe nađe:
  pomak   – gdje na vremenskoj crti glavnog izvora počinje taj izvor (s; negativno = počeo je prije glavnog),
  brzina  – koliko sekundi izvora prođe u jednoj sekundi glavnog (sat kamere nije savršen: 50 ppm ≈ 0,18 s na sat).
Vrijeme u izvoru: t_izvor = (t_glavni − pomak) × brzina.

Kako (vidi ODLUKE.md):
1. grubo: ovojnica glasnoće (log-energija u 10 ms, bez sporih promjena razine) cijelog izvora i glavnog,
   unakrsna korelacija preko FFT-a → pomak na ±10 ms i ocjena istaknutosti vrha (z);
2. fino: 3–16 prozora od 8 s s najviše govora raspoređenih po cijelom preklapanju, GCC-PHAT na 8 kHz
   u ±0,5 s oko grubog pomaka → pomak svakog prozora na ~0,1 ms;
3. pravac kroz fine pomake (s odbacivanjem odstupanja) → pomak + brzina; sigurnost iz z i slaganja prozora.
Sve je numpy + ffmpeg, na procesoru; sat snimke ~1 min (najviše traje čitanje zvuka iz videa).
"""
import argparse
import math
import subprocess
from pathlib import Path

import numpy as np

from common import FONTS_DIR, die, ffmpeg, fmt_time, load_json, natural_key, probe, run, save_json, version

SR = 8000               # Hz za fino poravnanje
HOP = 80                # uzoraka po okviru ovojnice (10 ms)
FR = SR // HOP          # okvira u sekundi
PROZOR = 8.0            # s, prozor za fino poravnanje
MARGINA = 0.5           # s, fino traži ±MARGINA oko grubog pomaka (pokriva i 140 ppm na sat)
MIN_PREKLOP = 20.0      # s, najmanje preklapanje koje se uzima u obzir (ili pola kraćeg izvora)
PRAG_Z = 8.0            # istaknutost grubog vrha za „visoku" sigurnost
PRAG_Z_MIN = 5.0        # ispod ovoga izvor nije pronađen (osim ako se fini prozori slože)
PRAG_PROZOR = 6.0       # istaknutost vrha u jednom finom prozoru
TOL_PROZOR = 0.004      # s; prozor se slaže s pravcem ako je unutar 4 ms
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".3gp", ".insv"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aif", ".aiff"}


# ---------------------------------------------------------------- izvori

def collect(inputs):
    files = []
    for i in inputs:
        p = Path(i)
        if p.is_dir():
            files += sorted((f for f in p.iterdir() if f.suffix.lower() in VIDEO_EXT | AUDIO_EXT),
                            key=natural_key)
        elif p.exists():
            files.append(p)
        else:
            die(f"ne postoji: {i}")
    if len(files) < 2:
        die("za sinkronizaciju trebaju barem dva izvora (npr. dvije kamere ili kamera + zasebni zvuk)")
    names = [f.name.lower() for f in files]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        die(f"isto ime datoteke dvaput ({', '.join(sorted(dup))}); preimenuj jednu (npr. kamera1_…)")
    return files


def source_info(path):
    d = probe(path)
    streams = d.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    if a is None:
        die(f"{Path(path).name} nema zvuk — bez zvuka se ne može sinkronizirati")
    dur = float(d["format"].get("duration") or a.get("duration") or 0)
    info = {"vrsta": "video" if v is not None else "zvuk", "trajanje": round(dur, 3)}
    if v is not None:
        info["w"], info["h"] = int(v["width"]), int(v["height"])
    return info


def decode(path, sr=SR):
    """Zvuk u vremenu datoteke kako ga vidi ffmpeg (-ss, render): first_pts=0 doda tišinu kad zvuk počinje
    iza slike (neke kamere) i makne uzorke prije početka (kašnjenje AAC kodera), pa je uzorak 0 = 0 s datoteke."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-acodec", "pcm_s16le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        die(f"ne mogu pročitati zvuk iz {Path(path).name}:\n{r.stderr.decode('utf-8', 'replace')[-800:]}")
    return np.frombuffer(r.stdout, np.int16)


def pick_master(files, infos, glavni=None):
    if glavni:
        for f in files:
            if glavni.lower() in (f.name.lower(), f.stem.lower()):
                return f
        die(f"--glavni '{glavni}' nije među izvorima: {', '.join(f.name for f in files)}")
    audio = [f for f in files if infos[f]["vrsta"] == "zvuk"]
    pool = audio or files
    return max(pool, key=lambda f: infos[f]["trajanje"])


# ---------------------------------------------------------------- mjerenje

def envelope(x):
    """Log-energija u okvirima od 10 ms bez sporih promjena razine (drugi mikrofon, drugo pojačanje),
    standardizirana i odrezana na ±3: korelira se oblik govora, ne glasnoća."""
    n = len(x) // HOP
    if n < 4:
        return np.zeros(max(n, 1), np.float32)
    f = x[: n * HOP].astype(np.float32).reshape(n, HOP)
    e = np.log10(np.mean(f * f, axis=1) + 1.0)
    k = FR  # 1 s pomični prosjek
    c = np.concatenate([[0.0], np.cumsum(e, dtype=np.float64)])
    lo = np.clip(np.arange(n) - k // 2, 0, n)
    hi = np.clip(np.arange(n) + k // 2 + 1, 0, n)
    hp = e - (c[hi] - c[lo]) / (hi - lo)
    s = hp.std()
    if s < 1e-9:
        return np.zeros(n, np.float32)
    return np.clip((hp - hp.mean()) / s, -3, 3).astype(np.float32)


def coarse(env_ref, env_src, min_overlap=None):
    """Grubi pomak (s) izvora prema glavnom + z istaknutosti vrha + omjer prema drugom vrhu.
    Pomak ℓ: okvir j izvora = okvir j+ℓ glavnog."""
    na, nb = len(env_ref), len(env_src)
    if min_overlap is None:
        min_overlap = min(MIN_PREKLOP * FR, 0.5 * min(na, nb))
    n = 1 << int(math.ceil(math.log2(na + nb + 1)))
    c = np.fft.irfft(np.fft.rfft(env_ref, n) * np.conj(np.fft.rfft(env_src, n)), n)
    lags = np.arange(-(nb - 1), na)
    vals = c[lags % n]
    overlap = np.minimum(na, lags + nb) - np.maximum(0, lags)
    ok = overlap >= max(min_overlap, 1)
    if not ok.any():
        return None
    lags, vals, overlap = lags[ok], vals[ok], overlap[ok]
    # sumu dijelimo s korijenom preklapanja: kratko slučajno preklapanje ne pobijedi dugo pravo
    score = vals / np.sqrt(overlap)
    i = int(np.argmax(score))
    med = float(np.median(score))
    mad = float(np.median(np.abs(score - med))) * 1.4826 + 1e-9
    z = (score[i] - med) / mad
    far = np.abs(lags - lags[i]) > FR  # drugi vrh dalje od 1 s
    second = float(score[far].max()) if far.any() else med
    ratio = (score[i] - med) / max(second - med, 1e-9)
    return {"pomak": lags[i] / FR, "z": float(z), "omjer": float(ratio)}


def gcc_phat(ref, src, sr=SR, band=(150.0, 3800.0)):
    """Pomak (uzorci) prozora ref unutar duljeg src: src[k + j] ≈ ref[j]. Vraća (k, istaknutost)."""
    nr, ns = len(ref), len(src)
    n = 1 << int(math.ceil(math.log2(nr + ns)))
    R = np.fft.rfft(ref.astype(np.float64) * np.hanning(nr), n)
    S = np.fft.rfft(src.astype(np.float64), n)
    X = S * np.conj(R)
    X /= np.abs(X) + 1e-12
    f = np.fft.rfftfreq(n, 1.0 / sr)
    X[(f < band[0]) | (f > band[1])] = 0
    cc = np.fft.irfft(X, n)[: ns - nr + 1]
    if len(cc) < 3:
        return None, 0.0
    k = int(np.argmax(cc))
    away = np.ones(len(cc), bool)
    away[max(0, k - int(0.002 * sr)): k + int(0.002 * sr) + 1] = False
    rest = cc[away] if away.any() else cc
    z = (cc[k] - rest.mean()) / (rest.std() + 1e-12)
    frac = 0.0
    if 0 < k < len(cc) - 1:
        a, b, c3 = cc[k - 1], cc[k], cc[k + 1]
        den = a - 2 * b + c3
        if abs(den) > 1e-12:
            frac = float(np.clip(0.5 * (a - c3) / den, -0.5, 0.5))
    return k + frac, float(z)


def pick_windows(env_ref, t0, t1, length=PROZOR):
    """Početci prozora (s, glavni) između t0 i t1: po jedan u svakom dijelu, ondje gdje ima najviše govora."""
    span = t1 - t0
    if span < 2.0:
        return [], length
    length = min(length, span)
    k = int(np.clip(span // 30, 3, 16))
    act = np.abs(env_ref)
    c = np.concatenate([[0.0], np.cumsum(act, dtype=np.float64)])
    L = int(length * FR)
    starts = []
    for i in range(k):
        a = t0 + span * i / k
        b = t0 + span * (i + 1) / k - length
        if b < a:
            b = a
        fa, fb = int(a * FR), int(b * FR)
        fa = min(max(fa, 0), len(env_ref) - L)
        fb = min(max(fb, fa), len(env_ref) - L)
        if fa < 0:
            continue
        cand = np.arange(fa, fb + 1)
        energy = c[cand + L] - c[cand]
        starts.append(float(cand[int(np.argmax(energy))]) / FR)
    return sorted(set(round(s, 2) for s in starts)), length


def robust_line(ts, tr, tol=TOL_PROZOR):
    """t_glavni = a + b·t_izvor; odbaci prozore koji se ne slažu (jeka, glazba, šum)."""
    ts, tr = np.asarray(ts, float), np.asarray(tr, float)
    n = len(ts)
    if n == 0:
        return None
    best = None
    # kandidati: svaki par (i medijan bez nagiba za jedan prozor) → najviše slaganja
    cands = [(float(np.median(tr - ts)), 1.0)]
    for i in range(n):
        for j in range(i + 1, n):
            if abs(ts[j] - ts[i]) > 30:
                b = (tr[j] - tr[i]) / (ts[j] - ts[i])
                if abs(b - 1) < 0.002:  # > 2000 ppm nije sat kamere nego greška
                    cands.append((tr[i] - b * ts[i], b))
    for a, b in cands:
        inl = np.abs(tr - (a + b * ts)) <= tol
        key = (int(inl.sum()), -float(np.abs(tr - (a + b * ts))[inl].sum()) if inl.any() else 0.0)
        if best is None or key > best[0]:
            best = (key, inl)
    inl = best[1]
    if inl.sum() >= 3 and np.ptp(ts[inl]) > 30:
        b, a = np.polyfit(ts[inl], tr[inl], 1)
        if abs(b - 1) > 0.002:
            a, b = float(np.median(tr[inl] - ts[inl])), 1.0
    else:
        a, b = float(np.median(tr[inl] - ts[inl])) if inl.any() else float(np.median(tr - ts)), 1.0
    res = tr[inl] - (a + b * ts[inl]) if inl.any() else np.array([])
    return {"a": float(a), "b": float(b), "slozni": int(inl.sum()), "ukupno": n,
            "odstupanje_ms": round(float(np.sqrt(np.mean(res ** 2))) * 1000, 2) if len(res) else None}


def fine(ref, src, starts, L, pred):
    """GCC-PHAT u svakom prozoru; pred(t_glavni) = očekivano vrijeme u izvoru. Vraća (t_izvor, t_glavni)."""
    ts, tr = [], []
    M = int(MARGINA * SR)
    for s in starts:
        r0 = int(s * SR)
        seg_r = ref[r0: r0 + L]
        s0 = int(round(pred(s) * SR)) - M
        if s0 < 0 or len(seg_r) < L:
            continue
        seg_s = src[s0: s0 + L + 2 * M]
        if len(seg_s) < L + 2 * M or not seg_r.any() or not seg_s.any():
            continue
        k, z = gcc_phat(seg_r, seg_s)
        if k is None or z < PRAG_PROZOR:
            continue
        ts.append((s0 + k) / SR)   # gdje je u izvoru početak prozora
        tr.append(s)               # … a gdje u glavnom
    return ts, tr


def align(ref, src, env_ref=None, env_src=None):
    """Cijelo mjerenje jednog izvora prema glavnom (oba 8 kHz int16). Vraća rječnik ili None."""
    env_ref = envelope(ref) if env_ref is None else env_ref
    env_src = envelope(src) if env_src is None else env_src
    g = coarse(env_ref, env_src)
    if g is None:
        return {"pronaden": False, "razlog": "izvori se ne preklapaju dovoljno dugo"}
    p0 = g["pomak"]
    dur_ref, dur_src = len(ref) / SR, len(src) / SR
    t0 = max(0.0, p0) + MARGINA + 0.05
    t1 = min(dur_ref, p0 + dur_src) - MARGINA - 0.05
    starts, length = pick_windows(env_ref, t0, t1)
    L = int(length * SR)
    ts, tr = fine(ref, src, starts, L, lambda t: t - p0)
    line = robust_line(ts, tr) if ts else None
    if line and line["slozni"] >= 3 and line["slozni"] < len(starts) and abs(line["b"] - 1) > 2e-6:
        # sat izvora je toliko kriv da krajnji prozori ispadnu iz ±MARGINA: drugi put uz izmjereni drift
        a, bb = line["a"], line["b"]
        ts2, tr2 = fine(ref, src, starts, L, lambda t: (t - a) / bb)
        line2 = robust_line(ts2, tr2) if ts2 else None
        if line2 and line2["slozni"] > line["slozni"]:
            line = line2
    out = {"grubi_pomak": round(p0, 3), "z": round(g["z"], 1), "omjer": round(g["omjer"], 2),
           "prozora": len(starts)}
    if line and line["slozni"] >= 1:
        out.update(pomak=line["a"], brzina=1.0 / line["b"], slozni=line["slozni"],
                   ukupno=len(starts), odstupanje_ms=line["odstupanje_ms"])
        # fino i grubo se moraju složiti u sredini preklapanja (grubi je prosjek preko cijele snimke)
        mid_src = (t0 + t1) / 2 - p0
        if abs(line["a"] + (line["b"] - 1) * mid_src - p0) > 0.05 + MARGINA:
            out["slozni"] = 0
    else:
        out.update(pomak=p0, brzina=1.0, slozni=0, ukupno=len(starts), odstupanje_ms=None)
    n = max(out["ukupno"], 1)
    if (g["z"] >= PRAG_Z and out["slozni"] >= max(2, math.ceil(0.6 * n))) or \
            (out["slozni"] >= 5 and out["slozni"] >= 0.8 * n):  # slučajno slaganje 5 prozora na 4 ms nije moguće
        out["sigurnost"] = "visoka"
    elif (g["z"] >= PRAG_Z_MIN and out["slozni"] >= 2) or (out["slozni"] >= 3 and out["slozni"] >= 0.6 * n):
        out["sigurnost"] = "srednja"
    elif g["z"] >= PRAG_Z_MIN and g["omjer"] >= 1.5:
        out["sigurnost"] = "niska"
    else:
        out["sigurnost"] = "nije pronađen"
    out["pronaden"] = out["sigurnost"] != "nije pronađen"
    return out


# ---------------------------------------------------------------- vrijeme

def fmt_t(t):
    return ("−" if t < -0.005 else "") + fmt_time(abs(t))


def to_source(src, t):
    """Vrijeme na crti glavnog izvora → vrijeme u datoteci izvora (s)."""
    return (t - src["pomak"]) * src.get("brzina", 1.0)


def to_master(src, t):
    return src["pomak"] + t / src.get("brzina", 1.0)


def covers(src, t):
    return src.get("pronaden", True) and src["od"] - 1e-6 <= t <= src["do"] + 1e-6


def finish_source(e, info):
    """Pomak u vremenu datoteke (ne zvučnog zapisa), raspon na crti glavnog, drift u ppm i ms na sat."""
    e["od"] = round(to_master(e, 0.0), 3)
    e["do"] = round(to_master(e, info["trajanje"]), 3)
    e["drift_ppm"] = round((e.get("brzina", 1.0) - 1.0) * 1e6, 1)
    e["drift_ms_na_sat"] = round((e.get("brzina", 1.0) - 1.0) * 3600 * 1000, 1)
    e["pomak"] = round(e["pomak"], 4)
    e["brzina"] = round(e.get("brzina", 1.0), 8)
    return e


def describe(e):
    if e.get("glavni"):
        return f"{e['ime']:<24} GLAVNI  ({e['vrsta']}, {fmt_time(e['trajanje'])})"
    if not e.get("pronaden"):
        return f"{e['ime']:<24} NIJE PRONAĐEN — {e.get('razlog') or 'zvuk se ne poklapa s glavnim'}"
    p = e["pomak"]
    kad = f"počinje {abs(p):.3f} s {'nakon' if p >= 0 else 'prije'} glavnog".replace(".", ",")
    drift = ""
    if abs(e["drift_ms_na_sat"]) >= 5:
        drift = f", sat {'brži' if e['drift_ppm'] > 0 else 'sporiji'} {abs(e['drift_ppm']):.0f} ppm (≈{abs(e['drift_ms_na_sat']):.0f} ms na sat)"
    extra = " (RUČNO)" if e.get("rucno") else ""
    slozni = f", prozora {e.get('slozni', 0)}/{e.get('ukupno', 0)}" if not e.get("rucno") else ""
    return (f"{e['ime']:<24} {kad}{drift}; sigurnost {e['sigurnost']}{slozni}{extra}"
            f"  [{fmt_t(e['od'])}–{fmt_t(e['do'])} na crti glavnog]")


def summary(data):
    lines = [f"Sinkronizacija (Shofe {data.get('shofe', '?')}) — glavni izvor: {data['glavni']}",
             f"Vremenska crta: {fmt_t(data['od'])}–{fmt_t(data['do'])} (svi izvori zajedno; 0 = početak glavnog), "
             f"svi istodobno: {fmt_t(data['zajedno'][0])}–{fmt_t(data['zajedno'][1])}"
             if data.get("zajedno") else
             f"Vremenska crta: {fmt_t(data['od'])}–{fmt_t(data['do'])}; nema dijela gdje snimaju svi izvori",
             ""]
    lines += [describe(e) for e in data["izvori"]]
    warn = [e for e in data["izvori"] if not e.get("glavni") and e["sigurnost"] in ("niska", "nije pronađen")]
    if warn:
        lines += ["", "PROVJERI: " + ", ".join(e["ime"] for e in warn)
                  + " — možda nije iz iste snimke ili je zvuk preloš; pogledaj sinkro.png i sinkro_provjera.mp4."
                  " Ako je iz iste epizode, ručno: --pomak ime=sekunde"]
    return "\n".join(lines) + "\n"


def timeline(data):
    ok = [e for e in data["izvori"] if e.get("pronaden", True)]
    data["od"] = round(min(e["od"] for e in ok), 3)
    data["do"] = round(max(e["do"] for e in ok), 3)
    a, b = max(e["od"] for e in ok), min(e["do"] for e in ok)
    data["zajedno"] = [round(a, 3), round(b, 3)] if b > a else None
    return data


# ---------------------------------------------------------------- slika i provjera

def best_check_time(data, env_master):
    """Trenutak za provjeru: u dijelu gdje snimaju svi, s puno govora (usne!), ne na samom rubu."""
    a, b = data["zajedno"] or (data["od"], data["do"])
    a, b = max(a, 0.0) + 2, min(b, len(env_master) / FR) - 10
    if b <= a:
        return max(data["zajedno"][0] if data["zajedno"] else 0.0, 0.0)
    L = 8 * FR
    act = np.abs(env_master)
    c = np.concatenate([[0.0], np.cumsum(act, dtype=np.float64)])
    fa, fb = int(a * FR), int(b * FR)
    cand = np.arange(fa, max(fa, min(fb, len(act) - L)) + 1)
    if not len(cand):
        return a
    # sredina snimke ima prednost (tamo je drift najveći u odnosu na početak)
    mid = (a + b) / 2
    e = (c[cand + L] - c[cand]) / L - 0.002 * np.abs(cand / FR - mid)
    return float(cand[int(np.argmax(e))]) / FR + 1


def draw_png(data, envs, path, width=1600):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    rows = data["izvori"]
    rh, top, left = 70, 50, 260
    H = top + rh * len(rows) + 40
    img = Image.new("RGB", (width, H), (24, 24, 28))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 17)
        small = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 13)
    except Exception:
        font = small = ImageFont.load_default()
    t0, t1 = data["od"], data["do"]
    span = max(t1 - t0, 1e-3)
    X = lambda t: left + (t - t0) / span * (width - left - 20)  # noqa: E731
    d.text((20, 14), f"Sinkronizacija — glavni: {data['glavni']}", fill=(235, 235, 235), font=font)
    step = 10 ** math.floor(math.log10(span / 6)) if span > 6 else 1
    while span / step > 12:
        step *= 2
    t = math.ceil(t0 / step) * step
    while t <= t1:
        x = X(t)
        d.line([(x, top - 6), (x, H - 30)], fill=(55, 55, 62))
        d.text((x + 2, H - 26), fmt_time(t).rstrip("0").rstrip("."), fill=(150, 150, 160), font=small)
        t += step
    if data.get("zajedno"):
        a, b = data["zajedno"]
        d.rectangle([X(a), top - 6, X(b), top - 2], fill=(90, 200, 120))
    colors = [(255, 196, 0), (80, 170, 255), (255, 110, 110), (120, 220, 140), (200, 140, 255), (255, 160, 90)]
    for i, e in enumerate(rows):
        y = top + i * rh
        col = colors[i % len(colors)] if e.get("pronaden", True) else (110, 110, 110)
        name = e["ime"] if len(e["ime"]) <= 22 else e["ime"][:21] + "…"
        d.text((20, y + 12), name, fill=col, font=font)
        sub = "glavni" if e.get("glavni") else (f"{e['pomak']:+.3f} s · {e['sigurnost']}".replace(".", ",")
                                               if e.get("pronaden") else "nije pronađen")
        d.text((20, y + 36), sub, fill=(170, 170, 180), font=small)
        env = envs.get(e["ime"])
        if env is None or not e.get("pronaden", True):
            continue
        # ovojnica izvora iscrtana u vremenu glavnog: tako se vidi poklapaju li se vrhovi
        px = np.arange(int(X(e["od"])), int(X(e["do"])))
        if not len(px):
            continue
        tm = t0 + (px - left) / (width - left - 20) * span
        fr = np.clip((to_source(e, tm) * FR).astype(int), 0, len(env) - 1)
        # najviša vrijednost između susjednih piksela, da se vide vrhovi
        frn = np.clip(np.append(fr[1:], fr[-1]), 0, len(env) - 1)
        vals = np.array([env[a: max(a + 1, b)].max() for a, b in zip(fr, frn)])
        h = np.clip((vals + 1.5) / 4.5, 0, 1) * (rh - 14)
        mid = y + rh - 8
        for x, hh in zip(px, h):
            d.line([(x, mid - hh), (x, mid)], fill=col)
    img.save(path)
    return path


def render_check(proj, data, t, dur=10.0, out_name="sinkro_provjera.mp4"):
    """Mozaik svih kamera oko trenutka t (crta glavnog) sa zvukom glavnog izvora: usne moraju pratiti glas.
    Ispod svake slike: ime i vrijeme u toj datoteci."""
    proj = Path(proj)
    tmp = proj / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    vids = [e for e in data["izvori"] if e["vrsta"] == "video"]
    master = next(e for e in data["izvori"] if e.get("glavni"))
    if not vids:
        return None
    n = len(vids)
    cols = 1 if n == 1 else 2 if n <= 4 else 3
    rows = math.ceil(n / cols)
    W, H = 640, 360
    font = tmp / "sinkro_font.ttf"
    font.write_bytes((FONTS_DIR / "Montserrat-SemiBold.ttf").read_bytes())
    cmd = [ffmpeg(), "-y", "-v", "error"]
    fc, labels = [], []
    for i, e in enumerate(vids):
        ts = to_source(e, t) if e.get("pronaden", True) else None
        lab = tmp / f"sinkro_oznaka_{i}.txt"
        if ts is None or ts < 0 or ts > e["trajanje"] - 0.5:
            lab.write_text(f"{e['ime']} — nema snimke u ovom dijelu", encoding="utf-8")
            cmd += ["-f", "lavfi", "-t", str(dur), "-i", f"color=c=0x202024:s={W}x{H}:r=30"]
        else:
            lab.write_text(f"{e['ime']}  ·  {fmt_time(ts)}", encoding="utf-8")
            cmd += ["-ss", f"{ts:.3f}", "-t", str(dur), "-i", Path(e["datoteka"]).resolve()]
        labels.append(lab.name)
        fc.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                  f"fps=30,setsar=1,setpts=PTS-STARTPTS,"
                  f"drawtext=fontfile={font.name}:textfile={lab.name}:fontsize=22:fontcolor=white:"
                  f"box=1:boxcolor=black@0.6:boxborderw=6:x=10:y=h-th-14[v{i}]")
    for j in range(n, rows * cols):
        fc.append(f"color=c=0x202024:s={W}x{H}:r=30:d={dur}[v{j}]")
    k = rows * cols
    if k == 1:
        fc.append("[v0]null[vout]")
    else:
        layout = "|".join(f"{(j % cols) * W}_{(j // cols) * H}" for j in range(k))
        fc.append("".join(f"[v{j}]" for j in range(k)) + f"xstack=inputs={k}:layout={layout}[vout]")
    ma = to_source(master, t)
    cmd += ["-ss", f"{max(ma, 0):.3f}", "-t", str(dur), "-i", Path(master["datoteka"]).resolve()]
    fc.append(f"[{len(vids)}:a]asetpts=PTS-STARTPTS,aresample=48000[aout]")
    script = tmp / "sinkro_provjera.txt"
    script.write_text(";\n".join(fc), encoding="utf-8")
    from common import filter_script_args
    out = (proj / out_name).resolve()
    cmd += [*filter_script_args(script.name), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-t", str(dur), "-movflags", "+faststart", out]
    run(cmd, cwd=tmp)
    return out


# ---------------------------------------------------------------- glavno

def sync(files, glavni=None, log=print):
    infos = {f: source_info(f) for f in files}
    master = pick_master(files, infos, glavni)
    log(f"Glavni izvor: {master.name} ({infos[master]['vrsta']}, {fmt_time(infos[master]['trajanje'])})")
    log(f"[1/{len(files)}] čitam zvuk: {master.name}")
    ref = decode(master)
    env_ref = envelope(ref)
    envs = {master.name: env_ref}
    izvori = []
    for i, f in enumerate(files, 1):
        info = infos[f]
        e = {"ime": f.name, "datoteka": str(f.resolve()), "vrsta": info["vrsta"], "trajanje": info["trajanje"]}
        if "w" in info:
            e["w"], e["h"] = info["w"], info["h"]
        if f == master:
            # crta glavnog = vrijeme glavne datoteke
            e.update(glavni=True, pronaden=True, sigurnost="glavni", pomak=0.0, brzina=1.0)
            izvori.append(finish_source(e, info))
            continue
        log(f"[{len([x for x in izvori if not x.get('glavni')]) + 2}/{len(files)}] čitam zvuk i tražim pomak: {f.name}")
        src = decode(f)
        env = envelope(src)
        envs[f.name] = env
        r = align(ref, src, env_ref, env)
        e.update(r)
        izvori.append(finish_source(e, info))
    izvori.sort(key=lambda e: not e.get("glavni"))
    data = {"shofe": version(), "glavni": master.name, "izvori": izvori}
    return timeline(data), envs, ref


def apply_manual(data, pomaci):
    for p in pomaci:
        name, _, val = p.partition("=")
        name = name.strip().lower()
        e = next((x for x in data["izvori"] if name in (x["ime"].lower(), Path(x["ime"]).stem.lower())), None)
        if e is None:
            die(f"--pomak: nema izvora '{name}'")
        if e.get("glavni"):
            die("--pomak: glavni izvor je uvijek 0; promijeni glavni s --glavni")
        try:
            e["pomak"] = float(val.replace(",", "."))
        except ValueError:
            die(f"--pomak: '{val}' nije broj sekundi (npr. kamera2.mp4=-3.25)")
        e.update(rucno=True, pronaden=True, sigurnost="ručno")
        e.setdefault("brzina", 1.0)
        finish_source(e, {"trajanje": e["trajanje"]})
    return timeline(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("izvori", nargs="+", help="video i zvučne datoteke ili mapa; ili postojeći projekt")
    ap.add_argument("--out", default=None, help="mapa projekta (zadano: podcast_projekt uz prvi izvor)")
    ap.add_argument("--glavni", help="ime datoteke koja daje vremensku crtu (zadano: zasebni zvuk ili najdulji video)")
    ap.add_argument("--pomak", action="append", default=[], help="ručno: ime=sekunde (gdje izvor počinje na crti glavnog)")
    ap.add_argument("--provjera", help="vrijeme na crti glavnog za video provjere (zadano: dio s puno govora)")
    ap.add_argument("--bez-provjere", action="store_true", help="bez sinkro_provjera.mp4")
    a = ap.parse_args()

    single = Path(a.izvori[0])
    if len(a.izvori) == 1 and (single / "sinkro.json").exists():
        proj = single
        data = load_json(proj / "sinkro.json")
        if a.pomak:
            data = apply_manual(data, a.pomak)
            save_json(proj / "sinkro.json", data)
            (proj / "sinkro.txt").write_text(summary(data), encoding="utf-8")
        envs = {}
        master = next(e for e in data["izvori"] if e.get("glavni"))
        env_m = None
        if a.pomak or not a.provjera:
            for e in data["izvori"]:
                envs[e["ime"]] = envelope(decode(e["datoteka"]))
            env_m = envs[master["ime"]]
            draw_png(data, envs, proj / "sinkro.png")
    else:
        files = collect(a.izvori)
        proj = Path(a.out) if a.out else files[0].parent / "podcast_projekt"
        proj.mkdir(parents=True, exist_ok=True)
        data, envs, _ = sync(files, a.glavni)
        if a.pomak:
            data = apply_manual(data, a.pomak)
        save_json(proj / "sinkro.json", data)
        (proj / "sinkro.txt").write_text(summary(data), encoding="utf-8")
        draw_png(data, envs, proj / "sinkro.png")
        env_m = envs[data["glavni"]]

    print()
    print(summary(data), end="")
    if not a.bez_provjere and any(e["vrsta"] == "video" for e in data["izvori"]):
        if a.provjera:
            from uredi import parse_time
            try:
                t = parse_time(a.provjera)
            except ValueError as ex:
                die(str(ex))
        else:
            t = best_check_time(data, env_m)
        out = render_check(proj, data, t)
        if out:
            print(f"\nProvjera: {out.name} (10 s od {fmt_time(t)} na crti glavnog, zvuk glavnog izvora) i sinkro.png")
    print(f"\nGotovo: {proj / 'sinkro.json'}")


if __name__ == "__main__":
    main()
