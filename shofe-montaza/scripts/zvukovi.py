"""Zvučni efekti (M5.2b): vlastita biblioteka zvukova (sintetizirani u numpyju, CC0 — naši su) i pravila
glasnoće. render.py ih miješa ispod govora uz prijelaze, trzaj, zamrzni … ili kao samostalan zvuk.

Pravila (EFEKTI.md: „zvuk efekta nije glasniji od glasa"):
  * svaki zvuk ima svoju razinu naspram glasa (npr. fijuk −9 LU, projektor −20 LU);
  * referenca je glas: integrirana glasnoća govora u videu, a ako je govor oko efekta tiši, onda taj
    lokalni govor (glasnoća govora u ±0,6 s oko zvuka);
  * tvrda granica: najglasniji blok zvuka (momentarna glasnoća, EBU R128) najmanje MIN_ISPOD dB ispod
    reference — i kad Marko traži „glasnije" (`zvucni_efekti_glasnoca`);
  * dva zvuka nisu bliže od RAZMAK s (drugi otpada), najviše MAX_ZVUKOVA po videu;
  * za vrijeme pjesme benda nema zvučnih efekata.

edit.json: efekt.parametri.zvuk = ime iz biblioteke | "ne" | putanja do vlastite .wav/.mp3 datoteke
(relativno na projekt); bez toga vrijedi zadani par iz PAROVI. `zvucni_efekti`: false isključi sve,
`zvucni_efekti_glasnoca`: ±dB naspram zadanog (granica ispod glasa ostaje).
"""
import json
import math
import wave
import zlib
from pathlib import Path

import numpy as np

SR = 48000
MIN_ISPOD = 3.0        # dB: zvuk je uvijek barem toliko tiši od glasa (najglasniji blok)
RAZMAK = 0.30          # s između vrhova dvaju zvukova
MAX_ZVUKOVA = 40
LOKALNO = 0.6          # s oko vrha zvuka u kojima se gleda govor
TISINA = -50.0         # LUFS: ispod toga blok nije govor

# ime → opis, razina naspram glasa (LU), trajanje (None = koliko traje efekt), vrh (udio trajanja)
ZVUKOVI = {
    "fijuk": {"opis": "zamah zraka (whoosh), vrh na rezu", "razina": -9.0, "trajanje": 0.60, "vrh": 0.62},
    "fijuk_kratki": {"opis": "kratki brzi zamah", "razina": -10.0, "trajanje": 0.34, "vrh": 0.60},
    "udarac": {"opis": "dubok udarac / bum (trzaj, pad)", "razina": -8.0, "trajanje": 0.90, "vrh": 0.0},
    "okidac": {"opis": "okidač fotoaparata (zamrzni, bljesak)", "razina": -10.0, "trajanje": 0.26, "vrh": 0.0},
    "pop": {"opis": "mekani „pop“ (iris, nešto iskoči)", "razina": -12.0, "trajanje": 0.14, "vrh": 0.0},
    "klik": {"opis": "kratki klik", "razina": -16.0, "trajanje": 0.06, "vrh": 0.0},
    "zvonce": {"opis": "zvonce (ding) — točan odgovor, ideja", "razina": -12.0, "trajanje": 1.20, "vrh": 0.0},
    "uspon": {"opis": "napetost raste do vrha (vertigo)", "razina": -12.0, "trajanje": None, "vrh": 1.0},
    "rolete": {"opis": "niz klikova roleta", "razina": -12.0, "trajanje": None, "vrh": 0.5},
    "digitalno": {"opis": "digitalni kvar, bipovi (pikseli)", "razina": -13.0, "trajanje": 0.32, "vrh": 0.0},
    "projektor": {"opis": "zujanje i kloparanje filmskog projektora (film)", "razina": -20.0, "trajanje": None,
                  "vrh": 0.5},
}
ALIASI = {"whoosh": "fijuk", "swoosh": "fijuk", "zamah": "fijuk", "fiju": "fijuk", "bum": "udarac", "boom": "udarac",
          "impact": "udarac", "hit": "udarac", "shutter": "okidac", "okidač": "okidac", "foto": "okidac",
          "ding": "zvonce", "zvono": "zvonce", "riser": "uspon", "glitch": "digitalno", "kvar": "digitalno",
          "click": "klik", "kratki_fijuk": "fijuk_kratki"}
# tip efekta → (zvuk, sidro): "rez" = vrh na rezu prijelaza, "pocetak" = vrh na početku efekta,
# "raspon" = zvuk traje koliko i efekt
PAROVI = {
    "zamah": ("fijuk", "rez"), "prolaz": ("fijuk", "rez"), "klizanje": ("fijuk_kratki", "rez"),
    "brisanje": ("fijuk_kratki", "rez"), "vrata": ("fijuk_kratki", "rez"), "iris": ("pop", "rez"),
    "rolete": ("rolete", "raspon"), "pikseli": ("digitalno", "rez"), "bljesak": ("okidac", "rez"),
    "crno": (None, None), "pretapanje": (None, None),
    "trzaj": ("udarac", "pocetak"), "pad": ("udarac", "pocetak"), "zamrzni": ("okidac", "pocetak"),
    "vertigo": ("uspon", "raspon"), "guranje": (None, None),
    "film": ("projektor", "raspon"), "retro": (None, None),
    "zvuk": ("udarac", "pocetak"),
}
DATOTEKE = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac")


# ---------------------------------------------------------------- sinteza (deterministička: isti zvuk svaki put)
def _rng(name):
    return np.random.default_rng(zlib.crc32(name.encode("utf-8")))


def _sweep_noise(n, fc, bw, rng):
    """Šum kroz pojasni filtar kojemu se sredina mijenja u vremenu: fc(u) i bw(u), u = 0…1 (overlap-add FFT)."""
    N, hop = 1024, 256
    win = np.hanning(N)
    noise = rng.standard_normal(n + N)
    out = np.zeros(n + N)
    freqs = np.fft.rfftfreq(N, 1.0 / SR)
    for start in range(0, n, hop):
        u = min(1.0, start / max(1, n - 1))
        f0, b = max(40.0, fc(u)), max(30.0, bw(u))
        spec = np.fft.rfft(noise[start:start + N] * win)
        spec *= np.exp(-0.5 * ((freqs - f0) / b) ** 2)
        out[start:start + N] += np.fft.irfft(spec, N) * win
    return out[:n]


def _decay(n, tau, delay=0):
    t = np.arange(n) / SR
    e = np.exp(-np.maximum(0.0, t - delay / SR) / tau)
    e[:delay] = 0.0
    return e


def _fade(x, a=0.004, b=0.02):
    na, nb = max(1, int(a * SR)), max(1, int(b * SR))
    x[:na] *= np.linspace(0, 1, na)
    x[-nb:] *= np.linspace(1, 0, nb)
    return x


def _klik(n, rng, f=3200.0, tau=0.012, at=0):
    t = np.arange(n) / SR
    x = np.zeros(n)
    m = n - at
    if m <= 0:
        return x
    tt = t[:m]
    burst = rng.standard_normal(m) * np.exp(-tt / 0.0025)
    x[at:] = 0.6 * burst + np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
    return x


def sintetiziraj(name, dur=None):
    """Zvuk iz biblioteke → mono float64 (vrh ~0,5). dur samo za zvukove promjenjive duljine."""
    Z = ZVUKOVI[name]
    d = float(dur if Z["trajanje"] is None and dur else (Z["trajanje"] or 1.0))
    d = max(0.08, min(d, 12.0))
    n = int(round(d * SR))
    t = np.arange(n) / SR
    u = t / d
    rng = _rng(name)
    if name in ("fijuk", "fijuk_kratki"):
        v = Z["vrh"]
        top = 2600.0 if name == "fijuk" else 3400.0
        fc = lambda q: 350 + (top - 350) * (q / v) ** 1.6 if q < v else top - (top - 700) * ((q - v) / (1 - v))
        x = _sweep_noise(n, fc, lambda q: 0.35 * fc(q), rng)
        env = np.where(u < v, (u / v) ** 2.2, np.exp(-(u - v) * d / (0.09 if name == "fijuk" else 0.05)))
        x = x * env
        x += 0.15 * _sweep_noise(n, lambda q: 180.0, lambda q: 80.0, rng) * env   # malo tijela
    elif name == "udarac":
        f = 42 + 58 * np.exp(-t / 0.06)                       # ton pada s 100 na 42 Hz
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = 0.55 * np.sin(ph) * np.exp(-t / 0.25)
        x += 0.5 * np.sin(2 * ph) * np.exp(-t / 0.15)
        x += 0.4 * np.sin(3 * ph) * np.exp(-t / 0.10)
        # tijelo i „krak" koji se čuju i na zvučniku mobitela (bas se tamo ne čuje)
        body = _sweep_noise(n, lambda q: 280.0, lambda q: 140.0, rng)
        crack = _sweep_noise(n, lambda q: 1500.0, lambda q: 1000.0, rng)
        x += 1.2 * body / (np.abs(body).max() + 1e-9) * np.exp(-t / 0.09)
        x += 1.0 * crack / (np.abs(crack).max() + 1e-9) * np.exp(-t / 0.03)
        x = np.tanh(2.2 * x)
    elif name == "okidac":
        x = np.zeros(n)
        for at, f in ((0, 2600.0), (int(0.085 * SR), 2100.0)):
            x += _klik(n, rng, f=f, tau=0.010, at=at)
            m = n - at
            x[at:] += 0.5 * np.sin(2 * np.pi * 190 * t[:m]) * np.exp(-t[:m] / 0.018)
        x += 0.25 * _sweep_noise(n, lambda q: 4500.0, lambda q: 2000.0, rng) * np.exp(-t / 0.05)
    elif name == "pop":
        f = 260 + 900 * (1 - np.exp(-t / 0.02))
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035)
        x[: int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
    elif name == "klik":
        x = _klik(n, rng)
    elif name == "zvonce":
        x = sum(a * np.sin(2 * np.pi * 1318.5 * r * t) * np.exp(-t / tau)
                for r, a, tau in ((1.0, 1.0, 0.45), (2.0, 0.45, 0.25), (2.76, 0.3, 0.16), (5.4, 0.12, 0.08)))
        x[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    elif name == "uspon":
        x = _sweep_noise(n, lambda q: 300 + 3700 * q ** 1.5, lambda q: 250 + 900 * q, rng)
        f = 180 + 520 * u ** 1.4
        x += 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR)
        x *= u ** 2.0
        tail = min(n, int(0.04 * SR))
        x[-tail:] *= np.linspace(1, 0, tail)
    elif name == "rolete":
        x = 0.25 * _sweep_noise(n, lambda q: 1500.0, lambda q: 700.0, rng) * np.sin(np.pi * u) ** 2
        k = 7
        for i in range(k):
            at = int((0.08 + 0.84 * i / (k - 1)) * (n - 1))
            x += 0.8 * _klik(n, rng, f=2400 - 120 * i, tau=0.008, at=at)
    elif name == "digitalno":
        x = np.zeros(n)
        step = int(0.032 * SR)
        for i, at in enumerate(range(0, n - step, step)):
            f = float(rng.choice([440, 660, 880, 1320, 1760, 2640]))
            seg = np.sign(np.sin(2 * np.pi * f * t[:step])) * (0.7 if i % 3 else 1.0)
            seg *= rng.uniform(0.4, 1.0)
            x[at:at + step] += seg
        x = np.round(x * 6) / 6                               # „bitcrush"
        x *= np.exp(-u * 1.5)
    elif name == "projektor":
        x = np.zeros(n)
        per = SR / 24.0                                       # 24 sličice u sekundi: klak-klak
        for i in range(int(n / per)):
            at = int(i * per + rng.uniform(-30, 30))
            if 0 <= at < n:
                m = min(n - at, int(0.02 * SR))
                x[at:at + m] += rng.uniform(0.5, 1.0) * _klik(m, rng, f=1800.0, tau=0.004)
        x += 0.10 * np.sin(2 * np.pi * 110 * t) + 0.05 * np.sin(2 * np.pi * 220 * t + 0.3)   # motor
        x *= 1 + 0.15 * np.sin(2 * np.pi * 3.1 * t)
        f = min(n // 3, int(0.15 * SR))
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
    else:
        raise ValueError(name)
    x = _fade(np.asarray(x, float), a=0.002 if Z["vrh"] == 0.0 else 0.01)
    peak = np.abs(x).max()
    return x * (0.5 / peak) if peak > 0 else x


def write_wav(path, x):
    """Stereo 16-bit 48 kHz (oba kanala ista: u stereo miksu zvuk je točno onoliko glasan koliko je izmjeren)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.repeat(pcm, 2).tobytes())
    return path


# ---------------------------------------------------------------- imena
def ime(name):
    """Ime zvuka iz biblioteke, "ne", ili None ako to nije ime (možda je datoteka)."""
    k = (name or "").strip().lower().replace(" ", "_")
    if k in ("ne", "bez", "nista", "ništa", "off", "none", "0"):
        return "ne"
    k = ALIASI.get(k, k)
    return k if k in ZVUKOVI else None


def je_datoteka(name):
    return Path(str(name or "")).suffix.lower() in DATOTEKE


def provjeri(name, proj=None):
    """Za naredbe: ime zvuka / "ne" / postojeća datoteka → normalizirana vrijednost; ValueError inače."""
    k = ime(name)
    if k:
        return k
    if je_datoteka(name):
        p = Path(name)
        if not p.is_absolute() and proj is not None:
            p = Path(proj) / p
        if not p.exists():
            raise ValueError(f"nema datoteke {name}")
        return str(name)
    raise ValueError(f"nepoznat zvuk '{name}' (postoje: {', '.join(ZVUKOVI)}; ili \"ne\", ili moj.wav)")


def za_efekt(x):
    """Koji zvuk ide uz efekt iz efekti.plan() → (zvuk ili None, sidro)."""
    par = PAROVI.get(x["tip"], (None, None))
    want = (x.get("p") or {}).get("zvuk")
    if want is None or str(want).strip().lower() in ("", "auto", "zadano"):
        return par
    k = ime(want)
    if k == "ne":
        return None, None
    sidro = par[1] or "pocetak"
    if k:
        if ZVUKOVI[k]["trajanje"] is None and sidro != "raspon":
            sidro = "raspon"
        return k, sidro
    return (str(want), sidro if sidro != "raspon" else "pocetak") if je_datoteka(want) else (None, None)


# ---------------------------------------------------------------- plan (vrijeme gotovog videa, prije brzine)
def ukljuceni(edit, st):
    v = edit.get("zvucni_efekti")
    if v is None:
        v = st.get("zvucni_efekti", True)
    return bool(v)


def plan(fx, edit, st, songs=(), total=None):
    """Zvukovi uz efekte → ([{id, zvuk, vrh_t, trajanje, vrh, raspon}], napomene). Bez glasnoće (to je razine())."""
    if not ukljuceni(edit, st):
        return [], []
    out, notes = [], []
    for x in fx:
        z, sidro = za_efekt(x)
        if not z:
            continue
        lib = z in ZVUKOVI
        if sidro == "rez":
            t = x.get("t", (x["s"] + x["e"]) / 2)
        elif sidro == "raspon":
            t = x["s"]
        else:
            t = x["s"]
        if lib and ZVUKOVI[z]["trajanje"] is None:
            d = max(0.25, min(x["e"] - x["s"], 6.0 if z == "uspon" else 30.0))
            if z == "uspon" and x["e"] - x["s"] > d:
                t = x["e"] - d
        else:
            d = ZVUKOVI[z]["trajanje"] if lib else None
        vrh = ZVUKOVI[z]["vrh"] if lib else 0.0
        peak = (t + vrh * d) if (lib and sidro == "raspon") else t
        if any(s - 0.05 <= peak <= e + 0.05 for s, e in songs):
            notes.append(f"zvuk uz {x['id']} preskočen: za vrijeme pjesme nema zvučnih efekata")
            continue
        out.append({"id": x["id"], "zvuk": z, "vrh_t": round(peak, 4), "trajanje": d, "vrh": vrh,
                    "raspon": sidro == "raspon"})
    out.sort(key=lambda z: z["vrh_t"])
    kept = []
    for z in out:
        if kept and z["vrh_t"] - kept[-1]["vrh_t"] < RAZMAK and not z["raspon"] and not kept[-1]["raspon"]:
            notes.append(f"zvuk uz {z['id']} preskočen: preblizu zvuku uz {kept[-1]['id']}")
            continue
        if len(kept) >= MAX_ZVUKOVA:
            notes.append(f"zvukova je više od {MAX_ZVUKOVA}; ostali preskočeni")
            break
        kept.append(z)
    return kept, notes


# ---------------------------------------------------------------- datoteke i glasnoća zvuka
def _ffmpeg():
    from common import ffmpeg
    return ffmpeg()


def momentarne(path):
    """Momentarne glasnoće (EBU R128, 400 ms) datoteke → [(kraj bloka, M)]."""
    from common import run
    from render import parse_momentary
    r = run([_ffmpeg(), "-nostdin", "-v", "error", "-i", Path(path),
             "-af", "aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur=0.5,"
                    "ebur128=metadata=1,ametadata=mode=print:key=lavfi.r128.M:file=-", "-f", "null", "-"])
    return parse_momentary(r.stdout)


def pripremi(proj, zv):
    """Za svaki zvuk: datoteka (biblioteka → _tmp/zvukovi/*.wav), trajanje i najglasniji blok (LUFS).
    Mjerenja se pamte u _tmp/zvukovi/razine.json."""
    proj = Path(proj)
    d = proj / "_tmp" / "zvukovi"
    d.mkdir(parents=True, exist_ok=True)
    cache_f = d / "razine.json"
    try:
        cache = json.loads(cache_f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    for z in zv:
        if z["zvuk"] in ZVUKOVI:
            dur = z["trajanje"]
            tag = z["zvuk"] if ZVUKOVI[z["zvuk"]]["trajanje"] is not None else f"{z['zvuk']}_{int(round(dur * 1000))}"
            f = d / f"{tag}.wav"
            if not f.exists():
                write_wav(f, sintetiziraj(z["zvuk"], dur))
        else:
            f = Path(z["zvuk"])
            if not f.is_absolute():
                f = proj / f
            if not f.exists():
                raise FileNotFoundError(f"zvuk {z['zvuk']} (uz {z['id']}) ne postoji")
        st = f.stat()
        key = f"{f.resolve()}|{st.st_size}|{int(st.st_mtime)}"
        if key not in cache:
            m = momentarne(f)
            from common import probe
            try:
                dur = float(probe(f)["format"]["duration"])
            except (KeyError, ValueError):
                dur = 1.0
            cache[key] = {"m": max((v for _, v in m), default=-70.0), "trajanje": dur}
        z["datoteka"] = f
        z["glasnoca"] = cache[key]["m"]
        if z["trajanje"] is None:
            z["trajanje"] = cache[key]["trajanje"]
    cache_f.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return zv


def razine(zv, mom, edit, songs=()):
    """Pojačanje svakog zvuka (dB) po pravilima glasnoće. mom = momentarne glasnoće samo govora
    [(kraj bloka, M)] u vremenu gotovog videa (prije brzine). Vraća glasnoću govora (LUFS) ili None."""
    from render import gated_loudness
    t = np.array([a for a, _ in mom]) - 0.2 if mom else np.zeros(0)       # sredina bloka
    m = np.array([b for _, b in mom]) if mom else np.zeros(0)
    near = np.zeros(len(t), bool)
    for s, e in songs:
        near |= (t >= s - 0.5) & (t <= e + 0.5)
    voice = gated_loudness(m[~near]) if len(m) else None
    off = float(edit.get("zvucni_efekti_glasnoca") or 0.0)
    off = max(-20.0, min(10.0, off))
    for z in zv:
        lib = ZVUKOVI.get(z["zvuk"])
        rel = (lib["razina"] if lib else -10.0) + off
        if voice is None:              # nema govora: zvuk na −30 LUFS (video se poslije ionako normalizira)
            ref = -30.0
            z["lokalno"] = None
        else:
            lo, hi = z["vrh_t"] - LOKALNO, z["vrh_t"] + LOKALNO
            if z["raspon"]:
                lo, hi = z["vrh_t"] - z["trajanje"] * z["vrh"] - LOKALNO, z["vrh_t"] + LOKALNO
            w = m[(t >= lo) & (t <= hi)]
            w = w[w > TISINA]
            loc = gated_loudness(w) if len(w) else None     # prosjek govora oko zvuka (ne najglasniji slog)
            z["lokalno"] = None if loc is None else round(loc, 1)
            ref = voice if loc is None else min(voice, loc)
        target = min(ref + rel, ref - MIN_ISPOD)
        z["ref"] = round(ref, 1)
        z["cilj"] = round(target, 1)
        z["pojacanje"] = round(max(-60.0, min(24.0, target - z["glasnoca"])), 2)
    return voice


# ---------------------------------------------------------------- ffmpeg
def ulazi(zv):
    return [a for z in zv for a in ("-i", z["datoteka"])]


def graf(zv, prvi, ulaz, izlaz):
    """Zvukovi na svoja mjesta (vrh zvuka na vrh_t) i miks s govorom → popis filtera."""
    g, labs = [], []
    for i, z in enumerate(zv):
        start = z["vrh_t"] - (z["vrh"] * z["trajanje"] if z["zvuk"] in ZVUKOVI else 0.0)
        pre = ""
        if start < 0:
            pre = f"atrim=start={-start:.4f},asetpts=PTS-STARTPTS,"
            start = 0.0
        ms = int(round(start * 1000))
        g.append(f"[{prvi + i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,{pre}"
                 f"volume={z['pojacanje']:.2f}dB,adelay={ms}|{ms}[zv{i}]")
        labs.append(f"[zv{i}]")
    g.append(f"{ulaz}{''.join(labs)}amix=inputs={len(zv) + 1}:duration=first:dropout_transition=0:normalize=0"
             f"{izlaz}")
    return g


def opis_linija(zv):
    if not zv:
        return None
    parts = [f"{z['id']} {Path(str(z['zvuk'])).name}" for z in zv]
    return f"Zvučni efekti: {len(zv)} ({', '.join(parts)}), ispod glasa najmanje {MIN_ISPOD:g} dB"


# ---------------------------------------------------------------- pregled biblioteke
def pregled(path, gap=0.6):
    """Svi zvukovi biblioteke jedan za drugim (za slušanje) → wav; vraća [(ime, od s)]."""
    parts, marks, t = [], [], 0.0
    for k, Z in ZVUKOVI.items():
        x = sintetiziraj(k, 1.2)
        marks.append((k, round(t, 2)))
        parts += [x, np.zeros(int(gap * SR))]
        t += len(x) / SR + gap
    write_wav(path, np.concatenate(parts) * 0.9)
    return marks


def db(x):
    return 20 * math.log10(max(1e-9, x))
