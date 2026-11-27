"""Najbolji refren pjesme za isječak od 30–60 s (M4.3b3), samo numpy.

  python refren.py shofe_projekt            za svaku pjesmu iz nastupi.json: refren i prijedlog isječka
  python refren.py shofe_projekt P1         samo ta pjesma

Koristi ga isjecci.py: iz svake pjesme jedan kandidat (vrsta „pjesma") koji počinje na refrenu.
Postupak (vidi ODLUKE.md, „audio thumbnailing" kao Goto 2003 / Müller i Jiang 2012, pojednostavljeno):
  1. kroma (12 tonova) iz spektra, zaglađena ~2 s (otporna na sitne razlike izvedbi uživo), i glasnoća;
  2. matrica sličnosti svakog trenutka sa svakim (kosinus kroma vektora);
  3. za dijelove dulje 10–24 s: koliko se puta i koliko vjerno ponavljaju drugdje u pjesmi (srednja sličnost
     po dijagonali, ne preklapaju se) + koliko su glasni naspram ostatka pjesme → refren = dio koji se najviše
     ponavlja i najjači je (strofa se obično ponovi 2×, refren 3–4× i glasniji je);
  4. isječak počne na udarcu na početku jednog ponavljanja refrena (najglasnijeg), traje cijele taktove
     (30–60 s) i završi na kraju refrena ili na kraju pjesme (s pljeskom) kad je dovoljno blizu.
"""
import argparse
from pathlib import Path

import numpy as np

from common import die, fmt_time

SR = 11025
NFFT = 4096
HOP = 1024                     # ~93 ms
GLADI = 2.0                    # s zaglađivanja kroma (CENS-ovski)
KORAK = 0.372                  # s po okviru nakon zaglađivanja (4 × HOP)
DULJINE = (10.0, 14.0, 18.0, 24.0)   # s, moguće duljine refrena
MIN_S, MAX_S = 30.0, 60.0
IDEAL = (34.0, 46.0)
KRAJ_PJESME = 8.0              # ako je kraj pjesme najviše toliko iza najbližeg dobrog kraja, isječak ide do kraja
PRETAPANJE_UL, PRETAPANJE_IZ = 0.08, 1.2


# ---------------------------------------------------------------- značajke

def features(x, sr=SR):
    """Zvuk → (kroma [N, 12] normirana, glasnoća dB [N]) po okvirima od KORAK s."""
    x = np.asarray(x, np.float64)
    if len(x) < NFFT:
        x = np.pad(x, (0, NFFT - len(x)))
    n = 1 + (len(x) - NFFT) // HOP
    win = np.hanning(NFFT)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / sr)
    band = (freqs >= 60) & (freqs <= 2100)
    pc = (np.round(12 * np.log2(freqs[band] / 440.0)).astype(int) + 9) % 12   # 0 = C
    M = np.zeros((12, band.sum()))
    M[pc, np.arange(band.sum())] = 1.0
    chroma = np.zeros((n, 12))
    rms = np.zeros(n)
    step = 2048
    for a in range(0, n, step):
        idx = np.arange(a, min(n, a + step))
        fr = np.lib.stride_tricks.sliding_window_view(x, NFFT)[idx * HOP] * win
        sp = np.abs(np.fft.rfft(fr, axis=1)) ** 2
        chroma[idx] = np.log1p(1000.0 * sp[:, band] / (sp[:, band].sum(axis=1, keepdims=True) + 1e-12)) @ M.T
        rms[idx] = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    chroma /= np.linalg.norm(chroma, axis=1, keepdims=True) + 1e-9
    k = max(1, int(round(GLADI * sr / HOP)))
    ker = np.hanning(k + 2)[1:-1]
    ker /= ker.sum()
    cs = np.stack([np.convolve(chroma[:, j], ker, "same") for j in range(12)], axis=1)
    db = 20 * np.log10(np.convolve(rms, ker, "same") + 1e-9)
    d = max(1, int(round(KORAK * sr / HOP)))
    cs, db = cs[::d], db[::d]
    cs /= np.linalg.norm(cs, axis=1, keepdims=True) + 1e-9
    return cs, db


def similarity(cs):
    S = np.clip(cs @ cs.T, 0.0, 1.0)
    return S


def diag_means(S, L):
    """M[s, t] = srednja sličnost S[s+i, t+i], i < L (−1 gdje ne stane)."""
    N = len(S)
    out = np.full((N, N), -1.0)
    if L > N:
        return out
    for k in range(-(N - L), N - L + 1):
        d = np.diagonal(S, k)
        c = np.concatenate([[0.0], np.cumsum(d)])
        m = (c[L:] - c[:-L]) / L
        if k >= 0:
            s = np.arange(len(m))
            out[s, s + k] = m
        else:
            t = np.arange(len(m))
            out[t - k, t] = m
    return out


def repetitions(Mrow, s, L, base, najvise=4):
    """Ponavljanja dijela koji počinje u okviru s: [(t, sličnost)] bez preklapanja (ni sa s)."""
    order = np.argsort(-Mrow)
    taken = [s]
    out = []
    for t in order:
        v = Mrow[t]
        if v <= base:
            break
        if any(abs(int(t) - q) < L for q in taken):
            continue
        taken.append(int(t))
        out.append((int(t), float(v)))
        if len(out) >= najvise:
            break
    return out


def find_chorus(cs, db, korak=KORAK, duljine=DULJINE):
    """→ {"duljina", "pojave": [okviri početaka, poredani], "slicnost", "ocjena", "ponavljanja"} ili None."""
    N = len(cs)
    S = similarity(cs)
    off = S[~np.eye(N, dtype=bool)] if N > 1 else S.ravel()
    best = None
    loud = db - np.percentile(db, 90)
    for Ls in duljine:
        L = int(round(Ls / korak))
        if 2 * L > N:
            continue
        M = diag_means(S, L)
        base = float(np.percentile(off, 75)) if len(off) else 0.0
        top = float(np.percentile(off, 99)) if len(off) else 1.0
        span = max(top - base, 0.05)
        c = np.concatenate([[0.0], np.cumsum(loud)])
        en = (c[L:] - c[:-L]) / L          # glasnoća dijela naspram glasnih dijelova pjesme (dB, ≤ 0)
        thr = base + 0.35 * span
        for s in range(0, N - L + 1):
            reps = repetitions(M[s], s, L, thr)
            if not reps:
                continue
            rep = sum(min(1.0, (v - base) / span) for _, v in reps[:3])
            e = float(np.clip(1 + en[s] / 12.0, 0, 1))
            score = rep * (0.55 + 0.45 * e) * (1 + 0.04 * Ls / 10)
            if best is None or score > best["ocjena"] + 1e-9:
                pojave = sorted([s] + [t for t, _ in reps])
                best = {"duljina": L, "pojave": pojave, "slicnost": round(float(np.mean([v for _, v in reps])), 3),
                        "ocjena": score, "ponavljanja": len(reps) + 1, "pocetak": s, "_prag": base + 0.5 * span}
    if best:
        extend(S, best)
        refine_starts(cs, db, best)
    return best


def novelty(cs, db, w=6):
    """Koliko se glazba promijeni u okviru t (kroma i glasnoća w okvira poslije naspram prije); rast glasnoće
    se broji više (refren obično krene jače)."""
    N = len(cs)
    nov = np.zeros(N)
    for t in range(w, N - w):
        a, b = cs[t - w:t].mean(axis=0), cs[t:t + w].mean(axis=0)
        rise = db[t:t + w].mean() - db[t - w:t].mean()
        nov[t] = np.linalg.norm(a - b) + max(0.0, rise) / 6.0
    return nov


def refine_starts(cs, db, ch, oko=4.0, korak=KORAK):
    """Početak svake pojave refrena pomakni (najviše ±oko s) na najveću promjenu glazbe: ako strofa prije
    refrena uvijek završi isto, ponavljanje počne prerano."""
    nov = novelty(cs, db)
    r = int(round(oko / korak))
    if not nov.any():
        return
    thr = max(0.08, float(np.percentile(nov, 80)))
    P = ch["pojave"]
    shifts = []
    for p in P:
        lo, hi = max(0, p - r), min(len(nov), p + r + 1)
        q = lo + int(np.argmax(nov[lo:hi]))
        shifts.append(q - p if nov[q] >= thr else None)
    good = [d for d in shifts if d is not None]
    if not good:
        return
    d = int(np.median(good))   # isti pomak za sve pojave (refren je uvijek iste duljine)
    ch["pojave"] = [max(0, p + d) for p in P]


def extend(S, ch, najvise=None):
    """Proširi pojave refrena lijevo i desno dok su sve pojave i dalje slične (prozor je mogao početi usred refrena)."""
    N = len(S)
    P, L, thr = ch["pojave"], ch["duljina"], ch.pop("_prag")
    najvise = najvise or L

    def ok(d):
        idx = [p + d for p in P]
        if min(idx) < 0 or max(idx) >= N:
            return False
        v = [S[a, b] for i, a in enumerate(idx) for b in idx[i + 1:]]
        return float(np.mean(v)) >= thr

    lo = 0
    while -lo < najvise and ok(lo - 1):
        lo -= 1
    hi = L - 1
    gaps = [b - a for a, b in zip(P, P[1:])]
    lim = min(gaps) if gaps else L
    while hi + 1 < min(lim, L + najvise) and ok(hi + 1):
        hi += 1
    ch["pojave"] = [p + lo for p in P]
    ch["duljina"] = hi - lo + 1


# ---------------------------------------------------------------- isječak

FINO = 0.05   # s po okviru fine glasnoće (za izbor udarca na kojem refren krene)


def fine_db(x, sr=SR, hop=FINO):
    h = max(1, int(hop * sr))
    n = len(x) // h
    if n == 0:
        return np.zeros(0)
    fr = np.asarray(x[:n * h], np.float64).reshape(n, h)
    return 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-10)


def _rise(fino, t, song_od, w=1.0):
    """Porast glasnoće u trenutku t (dB: sekunda poslije naspram sekunde prije)."""
    if fino is None or not len(fino):
        return 0.0
    i = int(round((t - song_od) / FINO))
    k = int(round(w / FINO))
    if i - k < 0 or i + k > len(fino):
        return 0.0
    return float(fino[i:i + k].mean() - fino[i - k:i].mean())


def _snap(t, beats, tol=0.6, fino=None, song_od=0.0):
    """Najbliži udarac; s `fino` udarac uz najveći porast glasnoće među onima do `tol` s (refren krene jače)."""
    if beats is None or not len(beats):
        return t
    near = [float(b) for b in beats if abs(b - t) <= tol]
    if not near:
        return t
    if fino is None:
        return min(near, key=lambda b: abs(b - t))
    return max(near, key=lambda b: (_rise(fino, b, song_od) - 0.5 * abs(b - t), -abs(b - t)))


def choose_clip(song_od, song_do, chorus, db, beats=None, korak=KORAK, min_s=MIN_S, max_s=MAX_S,
                po_taktu=4, fino=None):
    """Pojava refrena + kraj → {"od", "do", "refren": [(od, do)], "razlog", "do_kraja"} (vrijeme snimke)."""
    dur = song_do - song_od
    beats = None if beats is None or len(beats) < 8 else np.asarray(beats, float)
    if dur <= max_s:
        return {"od": round(song_od, 3), "do": round(song_do, 3), "refren": _occ(song_od, chorus, korak),
                "razlog": "cijela pjesma stane u isječak", "do_kraja": True}
    c = np.concatenate([[0.0], np.cumsum(db)])
    if chorus is None:   # refren nije jasan: najglasniji dio od ~46 s, na taktu
        L = int(round(IDEAL[1] / korak))
        s = int(np.argmax((c[L:] - c[:-L]) / L)) if len(db) > L else 0
        od = min(_snap(song_od + s * korak, beats), song_do - min_s)
        do = _end(od, song_do, beats, [], po_taktu, min_s, max_s)
        return {"od": round(od, 3), "do": round(do, 3), "refren": [], "do_kraja": abs(do - song_do) < 0.05,
                "razlog": "refren nije jasan: najglasniji dio pjesme"}
    L = chorus["duljina"]
    occ = _occ(song_od, chorus, korak)
    cands = []
    for k, (a, b) in enumerate(occ):
        fa = int(round((a - song_od) / korak))
        fb = min(len(db), fa + L)
        loud = (c[fb] - c[fa]) / max(1, fb - fa)
        start, ranije = _snap(a, beats, 0.8, fino, song_od), 0
        while song_do - start < min_s and start > song_od:   # premalo do kraja: cijeli takt ranije
            start, ranije = _bar_before(start, beats, po_taktu, song_od), ranije + 1
        end = _end(start, song_do, beats, [y for _, y in occ if y > start + min_s - 0.5], po_taktu, min_s, max_s)
        n_ref = 1 + sum(1 for x, y in occ[k + 1:] if x >= start and y <= end + 0.5)
        kraj = abs(end - song_do) < 0.05
        score = loud + 1.5 * (n_ref - 1) + (1.0 if kraj else 0.0) - 0.5 * ranije
        cands.append((score, -k, start, end, n_ref, ranije, kraj))
    _, mk, od, do, n_ref, ranije, kraj = max(cands)
    k = -mk
    razlog = (f"refren ({occ[0][1] - occ[0][0]:.0f} s) se ponavlja {len(occ)}×; isječak počinje "
              + (f"{ranije} takt{'a' if 2 <= ranije <= 4 else 'ova' if ranije > 4 else ''} prije " if ranije else "na ")
              + f"{_redni(k)} refren{'a' if ranije else 'u'}"
              + (f", u njemu {n_ref} refrena" if n_ref > 1 else "") + (", do kraja pjesme" if kraj else ""))
    return {"od": round(od, 3), "do": round(do, 3), "refren": occ, "razlog": razlog, "do_kraja": kraj}


def _bar_before(t, beats, po_taktu, lo):
    if beats is not None:
        i = int(np.argmin(np.abs(beats - t)))
        if i - po_taktu >= 0:
            return float(max(lo, beats[i - po_taktu]))
    return max(lo, t - 2.0)


def _occ(song_od, chorus, korak):
    if not chorus:
        return []
    return [(round(song_od + p * korak, 2), round(song_od + (p + chorus["duljina"]) * korak, 2))
            for p in chorus["pojave"]]


def _end(od, song_do, beats, ends, po_taktu, min_s, max_s):
    """Kraj isječka: kraj pjesme ako je blizu, inače kraj refrena u 30–60 s, inače ~40 s; na cijeli takt."""
    if min_s <= song_do - od <= max_s:
        return song_do
    good = [e for e in ends if min_s <= e - od <= max_s]
    if good:
        t = min(good, key=lambda e: abs((e - od) - IDEAL[1]))
        if 0 < song_do - t <= KRAJ_PJESME and song_do - od <= max_s:
            return song_do
    else:
        t = od + IDEAL[1]
    if beats is not None:
        bars = beats[(beats >= od - 0.05)]
        if len(bars) > po_taktu:
            i0 = int(np.argmin(np.abs(beats - od)))
            bars = beats[i0::po_taktu]
            bars = bars[(bars - od >= min_s) & (bars - od <= max_s) & (bars <= song_do)]
            if len(bars):
                t = float(bars[int(np.argmin(np.abs(bars - t)))])
    return float(min(song_do, max(od + min_s, min(od + max_s, t))))


def _redni(k):
    return ["prvom", "drugom", "trećem", "četvrtom", "petom", "šestom"][k] if k < 6 else f"{k + 1}."


# ---------------------------------------------------------------- cijela pjesma

def analyse_song(src, od, do, beats=None):
    """Pjesma od–do u datoteci src → prijedlog isječka (choose_clip) + "bpm", "refren_sigurnost"."""
    import ritam
    x = ritam.decode(src, od, do - od, SR)
    cs, db = features(x)
    ch = find_chorus(cs, db) if do - od > MAX_S else None
    if beats is None:
        r = ritam.analyse(x, SR) if len(x) else {"jasno": False}
        beats = [od + t for t in r.get("udarci", [])] if r.get("jasno") else None
        bpm = r.get("bpm") if r.get("jasno") else None
    else:
        bpm = None
    po = 4
    if bpm and bpm < 90:
        po = 2
    res = choose_clip(od, do, ch, db, beats, po_taktu=po, fino=fine_db(x))
    res["bpm"] = None if bpm is None else round(float(bpm), 1)
    res["refren_sigurnost"] = round(min(1.0, ch["ocjena"] / 3.0), 2) if ch else 0.0
    res["na_taktu"] = beats is not None
    return res


def heuristic_score(res, dur):
    """Ocjena 0–10 za popis isječaka (refren koji se ponavlja, cijeli takt, dobar kraj, trajanje)."""
    s = 5.0 + 3.0 * float(res.get("refren_sigurnost", 0))
    if res.get("do_kraja"):
        s += 0.5
    if res.get("na_taktu"):
        s += 0.5
    if IDEAL[0] <= dur <= IDEAL[1]:
        s += 0.5
    return round(min(10.0, s), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("pjesma", nargs="?", default="")
    a = ap.parse_args()
    import nastupi
    proj = Path(a.projekt)
    songs = nastupi.active(nastupi.load(proj))
    if a.pjesma:
        songs = [n for n in songs if n["id"].upper() == a.pjesma.upper()]
    if not songs:
        die("nema pjesama (prvo nastupi.py)" if not a.pjesma else f"nema pjesme {a.pjesma}")
    for n in songs:
        r = analyse_song(proj / "source.mp4", float(n["od"]), float(n["do"]))
        name = f" „{n['naziv']}“" if n.get("naziv") else ""
        print(f"{n['id']}{name} {fmt_time(n['od'])}–{fmt_time(n['do'])}: isječak {fmt_time(r['od'])}–"
              f"{fmt_time(r['do'])} ({r['do'] - r['od']:.0f} s) — {r['razlog']}")
        if r["refren"]:
            print("   refren: " + ", ".join(f"{fmt_time(x)}–{fmt_time(y)}" for x, y in r["refren"]))


if __name__ == "__main__":
    main()
