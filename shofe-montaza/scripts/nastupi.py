"""Nastupi bendova (pjesme) u snimci: pronađi ih i zaštiti od rezanja.

  python nastupi.py shofe_projekt                        → nastupi.json (+ .txt, .png): gdje se svira
  python nastupi.py shofe_projekt popis                  popis pjesama
  python nastupi.py shofe_projekt dodaj 12:30-16:10 [--naziv "Bend – Pjesma"]   ručno dodaj pjesmu
  python nastupi.py shofe_projekt granice P1 12:28-16:15 ispravi početak/kraj
  python nastupi.py shofe_projekt naziv P1 "Bend – Pjesma"
  python nastupi.py shofe_projekt makni P2               to nije pjesma (ponovna analiza je više ne dodaje)
  python nastupi.py shofe_projekt glasnoca P1 +2         P1 2 LU glasnija od govora (zadano 0 = jednako glasno)
  python nastupi.py shofe_projekt glasnoca sve -1        sve pjesme 1 LU tiše od govora

Vremena su vremena izvornog videa (source.mp4, kao u transcript.txt). Pjesma je dio gdje se svira i pjeva
(glazba je jača od govora) najmanje 30 s; radio ispod razgovora nije pjesma. Uz kraj pjesme ide i pljesak.

Pjesma se nikad ne reže iznutra: plan.py je upisuje u edit.json (`nastupi`) kao jedan komad, render.py je
uzima cijelu (i instrumentalne dijelove bez riječi), bez titlova, a uredi.py pjesmu ili makne cijelu ili ostavi
cijelu. Ako edit.json već postoji, ovaj alat ga odmah osvježi. Glasnoću render.py izjednači sam: izmjeri govor i
svaku pjesmu (EBU R128) i pjesmu stalnim pojačanjem dovede na glasnoću govora (± `glasnoca`), bez „pumpanja".

Prvo pokretanje skida mali model (~29 MB arhiva, ostaje 6 MB) s GitHuba u mapu modela (Windows:
%LOCALAPPDATA%\\Shofe\\modeli, drugdje ~/.cache/shofe/modeli; ili SHOFE_MODELI).
Motor: sherpa-onnx (Apache-2.0) + CED-tiny (Apache-2.0), oznake zvuka AudioSet (govor, glazba, pjevanje, pljesak).
"""
import argparse
import re
import shutil
import sys
import tarfile
from pathlib import Path

import numpy as np

from common import FONTS_DIR, die, fmt_time, load_json, save_json, version

SR = 16000
PROZOR = 4.0     # s zvuka koje model gleda odjednom
KORAK = 1.0      # s između prozora
MIN_PJESMA = 30.0
SPOJI = 6.0      # kraće pauze unutar pjesme (između strofa, ugađanje) se spajaju
PRAG = 0.5       # glazba barem toliko vjerojatna da pjesma počne
PRAG_DALJE = 0.35
PREDNOST = 0.15  # glazba mora biti jača od govora barem toliko (radio ispod razgovora nije pjesma)
PLJESAK_MAX = 10.0

# AudioSet indeksi (class_labels_indices.csv uz model)
I_GOVOR, I_PJEVANJE, I_GLAZBA = 0, 27, 137
I_PJEVANJE_SVE = (27, 32, 33, 34)   # pjevanje, muško, žensko, dječje
I_PLJESAK = (63, 66, 67)            # pljeskanje, navijanje, aplauz

REL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/audio-tagging-models"
TAR = "sherpa-onnx-ced-tiny-audio-tagging-2024-04-19"
MODEL = "glazba_ced_tiny.onnx"
MODEL_URL = f"{REL}/{TAR}.tar.bz2"
MODEL_SHA = "84baf315b57d61aa69480c4fee878dab54cbc7be3e877db334e65d8b087e23c3"
MODEL_LIC = "Apache-2.0 (CED, RicherMans/CED; ONNX k2-fsa/sherpa-onnx)"


# ---------------------------------------------------------------- model

def ensure_model(d=None):
    import govornici as G
    d = Path(d or G.models_dir())
    d.mkdir(parents=True, exist_ok=True)
    dest = d / MODEL
    if dest.exists():
        return dest
    print(f"Prvo pokretanje: skidam model za prepoznavanje glazbe u {d}")
    raw = d / MODEL_URL.rsplit("/", 1)[-1]
    try:
        G._download(MODEL_URL, raw)
    except Exception as e:
        die(f"ne mogu skinuti {MODEL_URL}: {e}\nProvjeri internet (treba samo prvi put).")
    if G.sha256(raw) != MODEL_SHA:
        print(f"  Upozorenje: {raw.name} ima drugu kontrolnu sumu nego što je Shofe provjerio. Nastavljam.")
    with tarfile.open(raw, "r:bz2") as t:
        with t.extractfile(t.getmember(f"{TAR}/model.int8.onnx")) as src, open(dest, "wb") as f:
            shutil.copyfileobj(src, f)  # int8 daje iste vjerojatnosti (±0,02) kao float, 4× manji (ODLUKE.md)
    (d / "glazba-LICENSE.txt").write_text(
        f"{MODEL}: CED-tiny audio tagging, {MODEL_LIC}\nIzvor: {MODEL_URL}\n", encoding="utf-8")
    raw.unlink()
    return dest


def tagger(model, threads=2):
    import sherpa_onnx as so
    labels = Path(model).with_name("glazba_oznake.csv")
    if not labels.exists():  # sherpa-onnx traži datoteku s oznakama; trebaju nam samo indeksi
        labels.write_text("index,mid,display_name\n" + "".join(f'{i},/m/{i},"k{i}"\n' for i in range(527)),
                          encoding="utf-8")
    cfg = so.AudioTaggingConfig(model=so.AudioTaggingModelConfig(ced=str(model), num_threads=threads),
                                labels=str(labels), top_k=527)
    return so.AudioTagging(cfg)


def probabilities(samples, at, prozor=PROZOR, korak=KORAK):
    """Po prozoru [govor, glazba, pjevanje, pljesak]; prozor i pokriva [i*korak, i*korak+prozor]."""
    x = samples.astype(np.float32)
    if samples.dtype == np.int16:
        x /= 32768.0
    win, hop = int(prozor * SR), int(korak * SR)
    n = max(1, int(np.ceil(max(len(x) - win, 0) / hop)) + 1)
    out = np.zeros((n, 4), np.float32)
    for i in range(n):
        seg = x[i * hop: i * hop + win]
        if len(seg) < SR // 2:
            seg = np.pad(seg, (0, SR // 2 - len(seg)))
        st = at.create_stream()
        st.accept_waveform(SR, seg)
        p = np.zeros(527, np.float32)
        for e in at.compute(st, top_k=527):
            p[e.index] = e.prob
        out[i] = (p[I_GOVOR], p[I_GLAZBA], max(p[j] for j in I_PJEVANJE_SVE), max(p[j] for j in I_PLJESAK))
    return out


# ---------------------------------------------------------------- od vjerojatnosti do pjesama

def _median(v, k=5):
    if len(v) < k:
        return v.copy()
    pad = np.pad(v, (k // 2, k // 2), mode="edge")
    return np.array([np.median(pad[i:i + k]) for i in range(len(v))])


def find_songs(P, trajanje, korak=KORAK, prozor=PROZOR, min_len=MIN_PJESMA, spoji=SPOJI, prag=PRAG):
    """P: (n, 4) iz probabilities() → [(od, do, sigurnost, pjevanje)] u sekundama."""
    if not len(P):
        return []
    gov = _median(P[:, 0])
    glz = _median(np.maximum(P[:, 1], P[:, 2]))
    pjev = _median(P[:, 2])
    plj = P[:, 3]
    n = len(P)
    centar = np.arange(n) * korak + min(prozor, trajanje) / 2
    jak = (glz >= prag) & (glz - gov >= PREDNOST)
    dalje = (glz >= PRAG_DALJE) & (glz - gov >= 0)
    # histereza: dio počinje na jakom, traje dok je barem "dalje"
    on = np.zeros(n, bool)
    i = 0
    while i < n:
        if jak[i]:
            a = i
            while a > 0 and dalje[a - 1]:
                a -= 1
            b = i
            while b + 1 < n and dalje[b + 1]:
                b += 1
            on[a:b + 1] = True
            i = b + 1
        else:
            i += 1
    parts = []
    i = 0
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and on[j + 1]:
                j += 1
            parts.append([i, j])
            i = j + 1
        else:
            i += 1
    merged = []
    for a, b in parts:
        if merged and (centar[a] - centar[merged[-1][1]]) - korak < spoji:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        od = max(0.0, centar[a] - korak / 2)
        do = min(trajanje, centar[b] + korak / 2)
        if do - od < min_len:
            continue
        # pljesak odmah iza pjesme je dio nastupa
        k, aplauz = b + 1, False
        while k < n and plj[k] >= 0.4 and centar[k] - centar[b] <= PLJESAK_MAX:
            do = min(trajanje, centar[k] + korak / 2)
            k, aplauz = k + 1, True
        sig = float(np.mean(glz[a:b + 1]))
        out.append({"od": round(od, 2), "do": round(do, 2), "sigurnost": round(sig, 2),
                    "pjevanje": bool(np.mean(pjev[a:b + 1] >= 0.3) >= 0.2), "pljesak": aplauz})
    return out


def _music_run(P, need=3):
    ok = (np.maximum(P[:, 1], P[:, 2]) >= PRAG) & (np.maximum(P[:, 1], P[:, 2]) - P[:, 0] >= PREDNOST)
    runs, i = [], 0
    while i < len(ok):
        if ok[i]:
            j = i
            while j + 1 < len(ok) and ok[j + 1]:
                j += 1
            if j - i + 1 >= need:
                runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def refine_edges(song, samples, at, trajanje, oko=3.0, prozor=1.0, korak=0.25):
    """Grubi rub (prozori od 4 s) → točniji iz prozora od 1 s oko ruba: prvi/zadnji niz od 3 glazbena prozora."""
    def probs(t0):
        t0 = max(0.0, t0)
        seg = samples[int(t0 * SR):int(min(trajanje, t0 + 2 * oko + prozor) * SR)]
        return t0, probabilities(seg, at, prozor, korak) if len(seg) >= SR else None
    t0, P = probs(song["od"] - oko)
    if P is not None and (runs := _music_run(P)):
        song["od"] = round(max(0.0, t0 + runs[0][0] * korak + prozor / 2), 2)
    if not song.get("pljesak"):
        t0, P = probs(song["do"] - oko - prozor)
        if P is not None and (runs := _music_run(P)):
            song["do"] = round(min(trajanje, t0 + runs[-1][1] * korak + prozor / 2), 2)
    return song


def snap_to_words(od, do, words, trajanje, pre=0.5, post=1.0):
    """Mali razmak na početku i kraju (prvi ton, zadnji akord), ali ne preko govora prije/poslije pjesme,
    i nikad usred riječi: riječ na rubu ide na onu stranu na kojoj joj je veći dio."""
    for w in words:
        mid = (w["s"] + w["e"]) / 2
        if w["s"] < od < w["e"]:
            od = w["e"] if mid <= od else w["s"]
        if w["s"] < do < w["e"]:
            do = w["s"] if mid >= do else w["e"]
    prev_end = max((w["e"] for w in words if w["e"] <= od + 1e-6), default=0.0)
    next_start = min((w["s"] for w in words if w["s"] >= do - 1e-6), default=trajanje)
    od = max(0.0, od - pre, min(prev_end, od))
    do = min(trajanje, do + post, max(next_start, do))
    return round(od, 2), round(do, 2)


# ---------------------------------------------------------------- nastupi.json

def load(proj):
    p = Path(proj) / "nastupi.json"
    return load_json(p) if p.exists() else None


def active(data):
    """Pjesme koje vrijede (bez odbijenih), poredane po vremenu."""
    if not data:
        return []
    return sorted((n for n in data.get("nastupi", []) if not n.get("odbijeno")), key=lambda n: n["od"])


def _renumber(lst):
    lst.sort(key=lambda n: n["od"])
    for k, n in enumerate([n for n in lst if not n.get("odbijeno")]):
        n["id"] = f"P{k + 1}"


def _overlap(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def merge_detection(old, found):
    """Nova analiza + stare ručne izmjene: ručno dodane/ispravljene ostaju, odbijene se ne vraćaju,
    nazivi se prenose na pjesmu koja se preklapa."""
    old = old or {"nastupi": []}
    keep = [n for n in old.get("nastupi", []) if n.get("izvor") == "rucno" or n.get("odbijeno")]
    res = [dict(n) for n in keep]
    for f in found:
        od, do = f["od"], f["do"]
        if any(_overlap(od, do, n["od"], n["do"]) > 0.3 * (do - od) for n in keep):
            continue
        n = {"od": od, "do": do, "sigurnost": f.get("sigurnost", 0), "pjevanje": f.get("pjevanje", False),
             "pljesak": f.get("pljesak", False), "izvor": "auto"}
        for o in old.get("nastupi", []):
            if o.get("naziv") and _overlap(od, do, o["od"], o["do"]) > 0.5 * (do - od):
                n["naziv"] = o["naziv"]
        res.append(n)
    _renumber(res)
    return res


def apply_to_edit(edit, data):
    """edit["nastupi"] = pjesme iz nastupi.json; zadrži/titlovi iz edit.json se pamte po preklapanju."""
    old = edit.get("nastupi") or []
    new = []
    for n in active(data):
        e = {"id": n["id"], "od": n["od"], "do": n["do"], "zadrzi": True, "titlovi": False}
        if n.get("naziv"):
            e["naziv"] = n["naziv"]
        if n.get("glasnoca") is not None:
            e["glasnoca"] = n["glasnoca"]
        for o in old:
            if _overlap(n["od"], n["do"], o["od"], o["do"]) > 0.5 * (n["do"] - n["od"]):
                e["zadrzi"] = o.get("zadrzi", True)
                e["titlovi"] = o.get("titlovi", False)
                if o.get("napomena"):
                    e["napomena"] = o["napomena"]
                break
        new.append(e)
    changed = new != old
    if new:
        edit["nastupi"] = new
    else:
        edit.pop("nastupi", None)
    lvl = data.get("glasnoca") if data else None   # pjesme naspram govora (LU), za sve pjesme
    if lvl != edit.get("nastup_glasnoca"):
        changed = True
        if lvl is None:
            edit.pop("nastup_glasnoca", None)
        else:
            edit["nastup_glasnoca"] = lvl
    return changed


def edit_songs(edit, kept_only=True):
    """Pjesme iz edit.json [(od, do, nastup)]; kept_only → samo one koje ostaju u videu."""
    res = []
    for n in edit.get("nastupi") or []:
        a, b = float(n["od"]), float(n["do"])
        if b > a and (n.get("zadrzi", True) or not kept_only):
            res.append((a, b, n))
    return sorted(res, key=lambda x: x[0])


# ---------------------------------------------------------------- izlaz

def lines(data):
    out = []
    lst = active(data)
    if not lst:
        out.append("Nema pjesama (nastupa) u snimci.")
    for n in lst:
        d = n["do"] - n["od"]
        what = "pjesma s pjevanjem" if n.get("pjevanje") else "glazba"
        src = "ručno" if n.get("izvor") == "rucno" else f"sigurnost {n.get('sigurnost', 0):.2f}"
        name = f"  „{n['naziv']}“" if n.get("naziv") else ""
        lvl = n.get("glasnoca", data.get("glasnoca"))
        vol = f", {lvl:+g} LU od govora" if lvl else ""
        out.append(f"{n['id']}  {fmt_time(n['od'])}-{fmt_time(n['do'])}  ({fmt_time(d)}, {what}, {src}{vol}){name}")
    odb = [n for n in data.get("nastupi", []) if n.get("odbijeno")] if data else []
    for n in odb:
        out.append(f"--  {fmt_time(n['od'])}-{fmt_time(n['do'])}  nije pjesma (odbijeno)")
    return out


def draw_png(data, path, width=1600):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    curve = data.get("krivulja") or {}
    glz, gov = curve.get("glazba") or [], curve.get("govor") or []
    total = float(data.get("trajanje") or (len(glz) * KORAK))
    H, left, top, h = 300, 30, 60, 170
    img = Image.new("RGB", (width, H), (24, 24, 28))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 17)
        small = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 13)
    except Exception:
        font = small = ImageFont.load_default()
    X = lambda t: left + t / max(total, 1e-3) * (width - 2 * left)  # noqa: E731
    Y = lambda p: top + h - p * h  # noqa: E731
    d.text((left, 16), f"Nastupi — {len(active(data))} pjesama · žuto glazba, plavo govor · zeleno = pjesma (ne reže se)",
           fill=(235, 235, 235), font=font)
    for n in active(data):
        d.rectangle([X(n["od"]), top, X(n["do"]), top + h], fill=(40, 90, 55))
        d.text((X(n["od"]) + 4, top + 4), n["id"], fill=(160, 240, 170), font=small)
    for n in [n for n in data.get("nastupi", []) if n.get("odbijeno")]:
        d.rectangle([X(n["od"]), top + h - 6, X(n["do"]), top + h], fill=(120, 60, 60))
    d.line([(left, Y(PRAG)), (width - left, Y(PRAG))], fill=(80, 80, 90))
    c0 = min(PROZOR, total) / 2
    for vals, col in ((gov, (80, 170, 255)), (glz, (255, 196, 0))):
        pts = [(X(c0 + i * KORAK), Y(v)) for i, v in enumerate(vals)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2)
    step = 10
    while total / step > 12:
        step = {10: 30, 30: 60, 60: 300, 300: 600}.get(step, step * 2)
    t = 0
    while t <= total:
        d.line([(X(t), top + h), (X(t), top + h + 6)], fill=(150, 150, 160))
        d.text((X(t) + 2, top + h + 10), fmt_time(t).split(".")[0], fill=(150, 150, 160), font=small)
        t += step
    img.save(path)
    return path


def write_outputs(proj, data):
    save_json(proj / "nastupi.json", data)
    (proj / "nastupi.txt").write_text("\n".join(lines(data)) + "\n", encoding="utf-8")
    draw_png(data, proj / "nastupi.png")
    ep = proj / "edit.json"
    if ep.exists():
        edit = load_json(ep)
        if apply_to_edit(edit, data):
            import uredi
            uredi.save_history(proj, "nastupi")
            save_json(ep, edit)
            print(f"edit.json osvježen: pjesme se ne režu (poništi: python uredi.py {proj.name} vrati)")
    rp = proj / "rezija.json"
    if rp.exists():   # podcast: režija za vrijeme pjesme (široki kadar, spori rezovi na takt) ide iz nastupi.json
        had = [(round(p["od"], 2), round(p["do"], 2)) for p in load_json(rp).get("pjesme") or []]
        now = [(round(n["od"], 2), round(n["do"], 2)) for n in active(data)]
        if had != now:
            print(f"Podcast: ponovno pokreni rezija.py {proj.name} — za vrijeme pjesme kamera ide sporije "
                  "(široki kadar, rez na takt)")


# ---------------------------------------------------------------- naredbe

def detect(proj, a):
    import analyze
    pj = load_json(proj / "project.json") if (proj / "project.json").exists() else {}
    src = proj / "source.mp4"
    if not src.exists():
        die(f"nema {src}. Prvo prepare.py (ili rezija.py za podcast)")
    samples = analyze.decode_audio(src, SR)
    if samples is None or not len(samples):
        die("u videu nema zvuka")
    trajanje = float(pj.get("duration") or len(samples) / SR)
    model = ensure_model()
    print(f"Tražim glazbu u {fmt_time(trajanje)} zvuka ...")
    at = tagger(model, a.dretve)
    P = probabilities(samples, at)
    found = [refine_edges(f, samples, at, trajanje) for f in find_songs(P, trajanje, min_len=a.min, prag=a.prag)]
    words = load_json(proj / "transcript.json")["words"] if (proj / "transcript.json").exists() else []
    for f in found:
        f["od"], f["do"] = snap_to_words(f["od"], f["do"], words, trajanje)
    old = load(proj)
    data = {
        "verzija": version(),
        "model": {MODEL: MODEL_LIC},
        "trajanje": round(trajanje, 2),
        "postavke": {"min": a.min, "prag": a.prag, "prozor": PROZOR, "korak": KORAK},
        "nastupi": merge_detection(old, found),
        "krivulja": {"govor": [round(float(v), 2) for v in P[:, 0]],
                     "glazba": [round(float(v), 2) for v in np.maximum(P[:, 1], P[:, 2])]},
    }
    write_outputs(proj, data)
    print("\n".join(lines(data)))
    print(f"\nPregled: {proj / 'nastupi.png'}")
    if active(data):
        print("Pjesme se ne režu iznutra (plan.py/render.py/uredi.py). Naziv pjesme: "
              f"python nastupi.py {proj.name} naziv P1 \"Bend – Pjesma\"")


def _parse_range(s):
    import uredi
    m = uredi.RANGE.fullmatch(s.strip())
    if not m:
        die(f"ne razumijem '{s}' (primjer: 12:30-16:10)")
    od, do = uredi.parse_time(m.group(1)), uredi.parse_time(m.group(2))
    if do <= od:
        die("kraj mora biti iza početka")
    return od, do


GLASNOCA_MAX = 6.0


def parse_level(v):
    """„+2", „-1,5", „0", „glasnije", „tiše" → LU pjesme naspram govora (−6…+6)."""
    t = str(v).strip().lower().replace(",", ".").replace("lu", "").replace("db", "").strip()
    words = {"glasnije": 2.0, "jače": 2.0, "jace": 2.0, "tise": -2.0, "tiše": -2.0, "isto": 0.0, "jednako": 0.0}
    if t in words:
        return words[t]
    try:
        x = float(t)
    except ValueError:
        die(f"glasnoća '{v}' nije broj (primjer: +2 ili -1.5; LU naspram govora)")
    if abs(x) > GLASNOCA_MAX:
        die(f"glasnoća pjesme naspram govora najviše ±{GLASNOCA_MAX:g} LU (zadano 0 = jednako glasno)")
    return round(x, 1)


def describe_level(x):
    if not x:
        return "jednako glasno kao govor"
    return f"{abs(x):g} LU {'glasnije' if x > 0 else 'tiše'} od govora"


def _find(data, pid):
    for n in active(data):
        if n["id"].lower() == pid.lower():
            return n
    die(f"nema pjesme {pid} (python nastupi.py projekt popis)")


def manual(proj, a):
    data = load(proj) or {"verzija": version(), "nastupi": []}
    pj = load_json(proj / "project.json") if (proj / "project.json").exists() else {}
    dur = float(pj.get("duration") or data.get("trajanje") or 1e9)
    args = a.args
    if a.naredba == "popis":
        print("\n".join(lines(data)))
        return
    if a.naredba == "dodaj":
        if not args:
            die("primjer: python nastupi.py projekt dodaj 12:30-16:10")
        od, do = _parse_range(" ".join(args))
        do = min(do, dur)
        lst = [n for n in data["nastupi"] if n.get("odbijeno") or _overlap(od, do, n["od"], n["do"]) <= 0]
        n = {"od": round(od, 2), "do": round(do, 2), "izvor": "rucno", "pjevanje": True}
        if a.naziv:
            n["naziv"] = a.naziv
        lst.append(n)
        data["nastupi"] = lst
        msg = f"Dodano: {fmt_time(od)}-{fmt_time(do)}"
    elif a.naredba in ("makni", "granice", "naziv"):
        if not args:
            die(f"primjer: python nastupi.py projekt {a.naredba} P1 ...")
        n = _find(data, args[0])
        if a.naredba == "makni":
            n["odbijeno"] = True
            n["izvor"] = "rucno"
            msg = f"{args[0]} više nije pjesma ({fmt_time(n['od'])}-{fmt_time(n['do'])}); ponovna analiza je ne vraća"
        elif a.naredba == "granice":
            if len(args) < 2:
                die("primjer: python nastupi.py projekt granice P1 12:28-16:15")
            od, do = _parse_range(" ".join(args[1:]))
            n.update(od=round(od, 2), do=round(min(do, dur), 2), izvor="rucno")
            msg = f"{args[0]}: {fmt_time(n['od'])}-{fmt_time(n['do'])}"
        else:
            name = " ".join(args[1:]) or a.naziv
            if not name:
                die("primjer: python nastupi.py projekt naziv P1 \"Bend – Pjesma\"")
            n["naziv"] = name
            msg = f"{args[0]}: „{name}“"
    elif a.naredba == "glasnoca":
        if len(args) < 1:
            die("primjer: python nastupi.py projekt glasnoca P1 +2   (ili: glasnoca sve -1, glasnoca P1 0)")
        if len(args) == 1:
            target, val = "sve", args[0]
        else:
            target, val = args[0], args[1]
        lvl = parse_level(val)
        if target.lower() in ("sve", "svi", "*"):
            if lvl == 0:
                data.pop("glasnoca", None)
            else:
                data["glasnoca"] = lvl
            for n in data["nastupi"]:
                n.pop("glasnoca", None)
            msg = f"Sve pjesme: {describe_level(lvl)}"
        else:
            n = _find(data, target)
            n["glasnoca"] = lvl
            msg = f"{target}: {describe_level(lvl)}"
        msg += f". Vrijedi od sljedećeg rendera (python render.py {proj.name})"
    else:
        die(f"nepoznata naredba '{a.naredba}' (popis, dodaj, granice, naziv, glasnoca, makni)")
    _renumber(data["nastupi"])
    write_outputs(proj, data)
    print(msg)
    print("\n".join(lines(data)))


def main():
    ap = argparse.ArgumentParser(description="Nastupi bendova: pjesme se ne režu")
    ap.add_argument("projekt")
    ap.add_argument("naredba", nargs="?", default="analiza", help="(ništa) | popis | dodaj | granice | naziv | glasnoca | makni")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--naziv", help="naziv pjesme (uz dodaj)")
    ap.add_argument("--min", type=float, default=MIN_PJESMA, help="najkraća pjesma u sekundama (zadano 30)")
    ap.add_argument("--prag", type=float, default=PRAG, help="koliko sigurno mora biti glazba (0–1, zadano 0,5)")
    ap.add_argument("--dretve", type=int, default=2)
    a, extra = ap.parse_known_args()
    if extra:  # „-1,5" (decimalni zarez) argparse ne prepozna kao broj
        if not all(re.fullmatch(r"-[\d.,]+(lu|db)?", x, re.I) for x in extra):
            ap.error(f"nepoznati argumenti: {' '.join(extra)}")
        a.args += extra
    proj = Path(a.projekt).resolve()
    if not proj.is_dir():
        die(f"nema mape {proj}")
    if a.naredba in ("analiza", "analiziraj"):
        detect(proj, a)
    else:
        manual(proj, a)


if __name__ == "__main__":
    sys.exit(main())
