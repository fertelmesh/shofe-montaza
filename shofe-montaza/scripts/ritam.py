"""Ritam pjesme: udarci (beatovi) i tempo iz zvuka, samo numpy (M4.3b2).

  python ritam.py snimka.mp4 [--od 20 --do 68]     ispiše tempo (BPM), sigurnost i prve udarce

Koristi ga rezija.py: za vrijeme pjesme kamera se mijenja na udarac, svakih nekoliko taktova.
Postupak (vidi ODLUKE.md): ovojnica početaka tonova (spektralni tok, log-magnituda, samo porast), tempo iz
autokorelacije ovojnice s blagom prednošću oko 120 BPM, udarci dinamičkim programiranjem (Ellis 2007, isto
kao librosa.beat), pa i bend koji malo ubrza ili uspori ostane na udarcu.
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np

from common import die, ffmpeg

SR = 11025
NFFT = 1024
HOP = 256                    # ~23 ms
BPM_MIN, BPM_MAX = 60.0, 180.0
BPM_SREDINA = 120.0          # prednost tempa (log-Gauss, širina 1 oktava)
TIJESNO = 100.0              # koliko udarci moraju držati tempo (librosa: tightness)
MIN_SIGURNOST = 0.12         # ispod ovoga ritam nije jasan (govor, šum) → bez reza na udarac


def decode(path, od=0.0, trajanje=None, sr=SR):
    """Mono zvuk datoteke od `od` s (float32, −1..1)."""
    cmd = [ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, od):.3f}"]
    if trajanje is not None:
        cmd += ["-t", f"{max(0.01, trajanje):.3f}"]
    cmd += ["-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        die(f"ne mogu pročitati zvuk iz {Path(path).name}:\n{r.stderr.decode('utf-8', 'replace')[-600:]}")
    return np.frombuffer(r.stdout, np.float32).astype(np.float64)


def onset_envelope(x, sr=SR, nfft=NFFT, hop=HOP):
    """Snaga početaka tonova po okviru (fps = sr / hop): zbroj porasta log-spektra, bez lokalnog prosjeka."""
    if len(x) < nfft:
        return np.zeros(0)
    n = 1 + (len(x) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    win = np.hanning(nfft)
    env = np.empty(n)
    for i in range(0, n, 2048):                    # u komadima: sat zvuka ne puni memoriju
        S = np.abs(np.fft.rfft(x[idx[i:i + 2048]] * win, axis=1))
        L = np.log1p(1000.0 * S)
        if i == 0:
            d = np.diff(L, axis=0, prepend=L[:1])
        else:
            d = np.diff(np.vstack([prev, L]), axis=0)
        prev = L[-1:]
        env[i:i + len(L)] = np.maximum(d, 0).mean(axis=1)
    k = max(1, int(round(0.5 * sr / hop)))         # lokalni prosjek ~0,5 s
    loc = np.convolve(env, np.ones(k) / k, mode="same")
    env = np.maximum(env - loc, 0)
    s = env.std()
    return env / s if s > 0 else env


def tempo(env, fps, bpm_min=BPM_MIN, bpm_max=BPM_MAX, sredina=BPM_SREDINA):
    """(BPM, sigurnost 0–1, period u okvirima). Sigurnost = normirana autokorelacija na tom periodu."""
    if len(env) < fps * 4 or not env.any():
        return None, 0.0, None
    e = env - env.mean()
    n = len(e)
    f = np.fft.rfft(e, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    if ac[0] <= 0:
        return None, 0.0, None
    ac = ac / ac[0]
    lo = int(np.floor(60.0 * fps / bpm_max))
    hi = min(n - 1, int(np.ceil(60.0 * fps / bpm_min)))
    if hi <= lo + 1:
        return None, 0.0, None
    lags = np.arange(lo, hi + 1)
    bpm = 60.0 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpm / sredina)) ** 2)
    score = ac[lo:hi + 1] * prior
    i = int(np.argmax(score))
    L = lags[i]
    # točniji period: parabola kroz susjede
    if 0 < i < len(lags) - 1:
        y0, y1, y2 = ac[L - 1], ac[L], ac[L + 1]
        den = y0 - 2 * y1 + y2
        Lf = L + (0.5 * (y0 - y2) / den if den < 0 else 0.0)
    else:
        Lf = float(L)
    return round(60.0 * fps / Lf, 1), float(max(0.0, ac[L])), Lf


def track(env, period, tijesno=TIJESNO):
    """Udarci (indeksi okvira) dinamičkim programiranjem: jak početak + razmak blizu perioda."""
    n = len(env)
    if n == 0 or not period:
        return np.zeros(0, int)
    # lokalno zaglađena ovojnica (Gauss širine period/32, kao librosa)
    w = np.arange(-int(period), int(period) + 1)
    g = np.exp(-0.5 * (w * 32.0 / period) ** 2)
    loc = np.convolve(env, g, mode="same")
    score = np.zeros(n)
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(2 * period))
    offs = np.arange(lo, hi + 1)
    pen = -tijesno * np.log(offs / period) ** 2
    for t in range(n):
        p = t - offs
        ok = p >= 0
        if ok.any():
            cand = score[p[ok]] + pen[ok]
            j = int(np.argmax(cand))
            if cand[j] > 0:
                score[t] = loc[t] + cand[j]
                back[t] = p[ok][j]
                continue
        score[t] = loc[t]
    # zadnji udarac: najbolji među okvirima čija je vrijednost blizu lokalnog maksimuma pri kraju
    tail = score[max(0, n - int(round(period))):]
    t = n - len(tail) + int(np.argmax(tail))
    out = []
    while t >= 0:
        out.append(t)
        t = back[t]
    beats = np.array(out[::-1], int)
    # rubovi: bez udaraca u tišini na početku/kraju
    if len(beats):
        thr = 0.5 * np.median(loc[beats])
        good = np.flatnonzero(loc[beats] >= thr)
        if len(good):
            beats = beats[good[0]:good[-1] + 1]
    return beats


def analyse(x, sr=SR):
    """Zvuk → {"bpm", "sigurnost", "udarci": [s], "jasno": bool}."""
    fps = sr / HOP
    env = onset_envelope(x, sr)
    bpm, conf, period = tempo(env, fps)
    if not bpm:
        return {"bpm": None, "sigurnost": 0.0, "udarci": [], "jasno": False}
    beats = track(env, period)
    times = [round(float(b) / fps + NFFT / 2 / sr, 3) for b in beats]   # sredina okvira
    return {"bpm": bpm, "sigurnost": round(conf, 3), "udarci": times, "jasno": conf >= MIN_SIGURNOST}


def of_file(path, od=0.0, do=None):
    """Ritam dijela datoteke; vremena udaraca u vremenu datoteke."""
    x = decode(path, od, None if do is None else do - od)
    r = analyse(x)
    r["udarci"] = [round(t + od, 3) for t in r["udarci"]]
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datoteka")
    ap.add_argument("--od", type=float, default=0.0)
    ap.add_argument("--do", type=float, default=None)
    a = ap.parse_args()
    r = of_file(Path(a.datoteka), a.od, a.do)
    if not r["bpm"]:
        print("Ritam: nije pronađen (prekratko ili tišina)")
        return
    print(f"Tempo: {r['bpm']:.0f} BPM, sigurnost {r['sigurnost']:.2f}" + ("" if r["jasno"] else " (ritam nije jasan)"))
    print("Udarci: " + ", ".join(f"{t:.2f}" for t in r["udarci"][:16]) + (" …" if len(r["udarci"]) > 16 else ""))


if __name__ == "__main__":
    main()
