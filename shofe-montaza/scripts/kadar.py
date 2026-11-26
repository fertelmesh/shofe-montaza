"""Kadar prati govornika: vodoravna snimka u 9:16 (ili 4:5, 1:1) uvijek pokazuje onoga tko govori.

  python kadar.py shofe_projekt              → kadar.json + ponovno složen source.mp4 (kadar prati govornika)
  python kadar.py shofe_projekt --analiza    samo kadar.json i ispis kadrova (video se ne mijenja)
  python kadar.py shofe_projekt --vrati      natrag na nepomični kadar iz prepare.py (crop_x)

Najbolje nakon govornici.py (tko govori i kada); bez njega Shofe gleda samo tko miče usnama.
Lica: YuNet (MIT, 230 kB, models/yunet.onnx) u OpenCV-u (Apache-2.0), na procesoru, ~10 sličica u sekundi.

Kako se kadar ponaša (kao montažer u podcastu, vidi ODLUKE.md):
- prijelaz s jednog govornika na drugoga je rez, nikad švenk preko praznog prostora;
- kadar traje barem MIN_KADAR sekundi (kratko „da" ili smijeh ne prebacuje kadar);
- unutar kadra kamera miruje dok se lice drži blizu sredine, a ide za licem tek kad se osoba pomakne.
Vrijeme u kadar.json je vrijeme izvornog klipa; isto je i u source.mp4 od početka tog klipa.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import FORMATS, SKILL_DIR, die, ffmpeg, fmt_time, load_json, probe, save_json, version, video_info

MODEL = SKILL_DIR / "models" / "yunet.onnx"
FPS_ANALIZE = 10        # sličica u sekundi za traženje lica
SIRINA_ANALIZE = 640    # px; lice u širokom kadru podcasta je i tada 40–100 px
MIN_LICE = 0.6          # najmanja sigurnost detekcije
MIN_KADAR = 1.5         # s; kraći dio drugog govornika ne mijenja kadar
MIN_OSOBA = 0.10        # osoba mora biti u kadru barem toliki udio klipa
MIRNO = 0.30            # kamera miruje dok se lice drži unutar ±MIRNO/2 širine kadra
GLADENJE = 0.7          # s (sigma) za kadrove u kojima kamera ide za licem
PREDNOST = 0.15         # s; rez na novog govornika malo prije prve riječi


# ---------------------------------------------------------------- lica

def detector(w, h):
    try:
        import cv2
    except ImportError:
        die("OpenCV nije instaliran. Pokreni: python doctor.py --popravi")
    if not MODEL.exists():
        die(f"nema modela za lica: {MODEL}")
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:  # noqa: BLE001
        pass
    try:
        return cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), MIN_LICE, 0.3, 50)
    except Exception as e:  # noqa: BLE001
        die(f"OpenCV ne može učitati model lica ({e})")


def frames(path, w, h, fps=FPS_ANALIZE):
    """Sličice (BGR, w×h) svakih 1/fps s izvornog klipa; okret iz metapodataka primijeni ffmpeg."""
    cmd = [ffmpeg(), "-v", "error", "-i", str(path), "-an", "-vf", f"fps={fps},scale={w}:{h}:flags=area",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * 3
    try:
        while True:
            b = p.stdout.read(n)
            if len(b) < n:
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


def mouth_patch(gray, lm):
    """Područje usana poravnato po kutovima usana (pomak glave se poništi), normirano (koža, svjetlo)."""
    import cv2
    r, l = np.array(lm[6:8]), np.array(lm[8:10])     # YuNet: oči (0–3), nos (4–5), usta d/l (6–9)
    c, mw = (r + l) / 2, max(4.0, float(np.linalg.norm(l - r)))
    x0, x1 = int(c[0] - 0.75 * mw), int(c[0] + 0.75 * mw)
    y0, y1 = int(c[1] - 0.45 * mw), int(c[1] + 0.65 * mw)
    H, W = gray.shape
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 - x0 < 4 or y1 - y0 < 3:
        return None
    p = cv2.resize(gray[y0:y1, x0:x1], (24, 16), interpolation=cv2.INTER_AREA).astype(np.float32)
    return (p - p.mean()) / (p.std() + 4.0)


def detect(path, info):
    """Vrati (vremena, lica po sličici). Lice: dict x, y (središte), w, h (0–1 slike), p (usta), s."""
    import cv2
    aw = SIRINA_ANALIZE if info["w"] >= info["h"] else int(round(SIRINA_ANALIZE * info["w"] / info["h"] / 2)) * 2
    ah = int(round(aw * info["h"] / info["w"] / 2)) * 2
    det = detector(aw, ah)
    out = []
    for fr in frames(path, aw, ah):
        _, res = det.detect(fr)
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        faces = []
        for d in (res if res is not None else []):
            x, y, w, h = map(float, d[:4])
            lm = [float(v) for v in d[4:14]]
            faces.append({"x": (x + w / 2) / aw, "y": (y + h / 2) / ah, "w": w / aw, "h": h / ah,
                          "p": mouth_patch(gray, lm), "s": float(d[14])})
        out.append(faces)
    t = np.arange(len(out)) / FPS_ANALIZE
    return t, out


# ---------------------------------------------------------------- osobe

def tracks(dets, max_gap=int(1.5 * FPS_ANALIZE)):
    """Poveži lica kroz sličice (najbliže središte) → osobe. Vrati popis osoba:
    {"x": [po sličici ili nan], "w": [...], "akt": [pokret usana ili nan]}."""
    n = len(dets)
    live, done = [], []
    for k, faces in enumerate(dets):
        pairs = []
        for i, tr in enumerate(live):
            for j, f in enumerate(faces):
                d = abs(f["x"] - tr["lx"]) + abs(f["y"] - tr["ly"])
                if d < 0.6 * max(tr["lw"], f["w"]) + 0.02:
                    pairs.append((d, i, j))
        used_t, used_f = set(), set()
        for d, i, j in sorted(pairs):
            if i in used_t or j in used_f:
                continue
            used_t.add(i)
            used_f.add(j)
            live[i]["hits"].append((k, faces[j]))
            live[i].update(lx=faces[j]["x"], ly=faces[j]["y"], lw=faces[j]["w"], last=k)
        for j, f in enumerate(faces):
            if j not in used_f:
                live.append({"hits": [(k, f)], "lx": f["x"], "ly": f["y"], "lw": f["w"], "last": k})
        still = []
        for tr in live:
            (still if k - tr["last"] <= max_gap else done).append(tr)
        live = still
    done += live

    # komadi iste osobe (izašla iz kadra, okrenula se) spajaju se po položaju ako se ne preklapaju u vremenu
    done.sort(key=lambda tr: -len(tr["hits"]))
    persons = []
    for tr in done:
        ks = {k for k, _ in tr["hits"]}
        mx = float(np.median([f["x"] for _, f in tr["hits"]]))
        mw = float(np.median([f["w"] for _, f in tr["hits"]]))
        for p in persons:
            if abs(p["mx"] - mx) < 0.7 * max(p["mw"], mw) and not (ks & p["ks"]):
                p["hits"] += tr["hits"]
                p["ks"] |= ks
                break
        else:
            persons.append({"hits": list(tr["hits"]), "ks": set(ks), "mx": mx, "mw": mw})

    out = []
    for p in persons:
        if len(p["ks"]) < max(FPS_ANALIZE, MIN_OSOBA * n):
            continue
        x, w, akt = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
        patch = {}
        for k, f in sorted(p["hits"], key=lambda h: h[0]):
            x[k], w[k] = f["x"], f["w"]
            if f["p"] is not None:
                patch[k] = f["p"]
        for k, pt in patch.items():
            if k - 1 in patch:
                akt[k] = float(np.mean(np.abs(pt - patch[k - 1])))
        out.append({"x": x, "w": w, "akt": akt, "udio": len(p["ks"]) / max(1, n)})
    out.sort(key=lambda p: np.nanmedian(p["x"]))
    return out


def smooth(a, sigma_frames):
    """Gaussovo gladenje s rupama (nan): rupe se popune interpolacijom."""
    a = np.asarray(a, float)
    ok = ~np.isnan(a)
    if not ok.any():
        return a
    idx = np.arange(len(a))
    b = np.interp(idx, idx[ok], a[ok])
    if sigma_frames <= 0:
        return b
    r = int(3 * sigma_frames) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_frames) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(b, r, mode="edge"), k, mode="valid")


# ---------------------------------------------------------------- tko govori

def speaker_segments(proj, start, dur):
    """Govor iz govornici.json (s oznakom) ili transcript.json (bez oznake), u vremenu klipa."""
    gj, tj = proj / "govornici.json", proj / "transcript.json"
    segs = []
    if gj.exists():
        for s in load_json(gj).get("odsjecci", []):
            a, b = s["od"] - start, s["do"] - start
            if b > 0 and a < dur:
                segs.append((max(0.0, a), min(dur, b), s["govornik"]))
        if segs:
            return segs, True
    if tj.exists():
        for w in load_json(tj).get("words", []):
            a, b = w["s"] - start, w["e"] - start
            if b > 0 and a < dur:
                segs.append((max(0.0, a), min(dur, b), None))
    return segs, False


def match_speakers(persons, segs, t):
    """Govornik → osoba: čije se usne miču kad taj govornik govori (u odnosu na druge govornike)."""
    labels = sorted({g for *_, g in segs if g})
    akt = [smooth(p["akt"], 0) for p in persons]
    score = {}
    for g in labels:
        mine = np.zeros(len(t), bool)
        other = np.zeros(len(t), bool)
        for a, b, gg in segs:
            m = (t >= a) & (t < b)
            if gg == g:
                mine |= m
            else:
                other |= m
        other &= ~mine
        if mine.sum() < 3:
            continue
        for i, ak in enumerate(akt):
            ok = ~np.isnan(persons[i]["x"])
            if (mine & ok).sum() < 3:
                continue
            ref = float(np.mean(ak[other & ok])) if (other & ok).sum() >= 3 else float(np.mean(ak[ok]))
            score[(g, i)] = float(np.mean(ak[mine & ok])) - ref
    mapping, used = {}, set()
    for (g, i), s in sorted(score.items(), key=lambda kv: -kv[1]):
        if s <= 0 or g in mapping or i in used:
            continue
        mapping[g] = i
        used.add(i)
    return mapping, score


def active_person(persons, segs, labelled, t):
    """Po sličici: indeks osobe koja govori ili -1 (ne zna se)."""
    n = len(t)
    act = np.full(n, -1)
    if len(persons) == 1:
        return np.zeros(n, int), {}
    if not persons:
        return act, {}
    mapping = {}
    if labelled:
        mapping, _ = match_speakers(persons, segs, t)
        for a, b, g in segs:
            if g in mapping:
                act[(t >= a - PREDNOST) & (t < b)] = mapping[g]
        if mapping:
            return act, mapping
    # bez oznaka govornika: tko najviše miče usnama dok se govori (izglađeno ~0,8 s)
    speech = np.zeros(n, bool)
    for a, b, _ in segs:
        speech |= (t >= a - 0.2) & (t < b + 0.2)
    if not segs:
        speech[:] = True
    ak = np.vstack([smooth(p["akt"], 0.4 * FPS_ANALIZE) for p in persons])
    vis = np.vstack([~np.isnan(p["x"]) for p in persons])
    ak[~vis] = -1
    best = ak.argmax(axis=0)
    act[speech] = best[speech]
    return act, mapping


def shots(act, min_len=int(MIN_KADAR * FPS_ANALIZE)):
    """Niz osoba po sličici → kadrovi [(od_k, do_k, osoba)]: rupe preuzmu prethodnu osobu,
    prekratki kadrovi se pripoje susjedu."""
    a = np.array(act)
    if (a >= 0).any():
        first = a[np.argmax(a >= 0)]
        cur = first
        for k in range(len(a)):
            if a[k] < 0:
                a[k] = cur
            else:
                cur = a[k]
    runs = []
    for k, v in enumerate(a):
        if runs and runs[-1][2] == v:
            runs[-1][1] = k + 1
        else:
            runs.append([k, k + 1, int(v)])
    changed = True
    while changed and len(runs) > 1:
        changed = False
        i = min(range(len(runs)), key=lambda j: runs[j][1] - runs[j][0])
        if runs[i][1] - runs[i][0] < min_len:
            j = i - 1 if i > 0 else i + 1
            if 0 < i < len(runs) - 1 and runs[i - 1][2] != runs[i + 1][2]:
                # između dva različita: pripoji duljem susjedu
                j = i - 1 if (runs[i - 1][1] - runs[i - 1][0]) >= (runs[i + 1][1] - runs[i + 1][0]) else i + 1
            lo, hi = min(runs[i][0], runs[j][0]), max(runs[i][1], runs[j][1])
            runs[min(i, j)] = [lo, hi, runs[j][2]]
            del runs[max(i, j)]
            merged = []
            for r in runs:
                if merged and merged[-1][2] == r[2]:
                    merged[-1][1] = r[1]
                else:
                    merged.append(r)
            runs = merged
            changed = True
    return [tuple(r) for r in runs]


# ---------------------------------------------------------------- put kadra

def crop_for(fx, info, W, H):
    """Središte lica (0–1 širine snimke) → crop_x kao u prepare.py (0 = lijevi rub, 1 = desni)."""
    sw = info["w"] * max(W / info["w"], H / info["h"])
    if sw - W < 1:
        return 0.5
    return float(np.clip((fx * sw - W / 2) / (sw - W), 0.0, 1.0))


def plan_path(persons, runs, info, W, H, default_cx):
    """Vrati (put crop_x po sličici, kadrovi s opisom)."""
    n = len(persons[0]["x"]) if persons else 0
    path = np.full(n, float(default_cx))
    out = []
    win = W / (info["w"] * max(W / info["w"], H / info["h"]))     # širina kadra kao udio snimke
    for a, b, i in runs:
        if i < 0 or i >= len(persons):
            out.append({"od": a, "do": b, "osoba": None, "nacin": "miruje", "crop_x": float(default_cx)})
            continue
        x = smooth(persons[i]["x"], 0)[a:b]
        lo, hi = np.percentile(x, 5), np.percentile(x, 95)
        if hi - lo <= MIRNO * win:
            cx = crop_for(float(np.median(x)), info, W, H)
            path[a:b] = cx
            out.append({"od": a, "do": b, "osoba": i, "nacin": "miruje", "crop_x": round(cx, 4)})
        else:
            xs = smooth(x, GLADENJE * FPS_ANALIZE)
            path[a:b] = [crop_for(v, info, W, H) for v in xs]
            out.append({"od": a, "do": b, "osoba": i, "nacin": "prati",
                        "crop_x": round(float(np.median(path[a:b])), 4)})
    return path, out


def needs_tracking(info, W, H):
    return info["w"] / info["h"] > W / H * 1.02


def analyse_clip(proj, clip, W, H, log=print):
    info = video_info(clip["file"])
    t, dets = detect(clip["file"], info)
    persons = tracks(dets)
    segs, labelled = speaker_segments(proj, clip["start"], clip["dur"])
    act, mapping = active_person(persons, segs, labelled, t)
    runs = shots(act) if persons else [(0, len(t), -1)]
    path, kad = plan_path(persons, runs, info, W, H, clip.get("crop_x", 0.5)) if persons else \
        (np.full(len(t), float(clip.get("crop_x", 0.5))), [{"od": 0, "do": len(t), "osoba": None,
                                                          "nacin": "miruje", "crop_x": clip.get("crop_x", 0.5)}])
    inv = {i: g for g, i in mapping.items()}
    names = [f"O{i + 1}" for i in range(len(persons))]
    res = {
        "file": clip["file"], "start": clip["start"], "dur": clip["dur"], "fps_analize": FPS_ANALIZE,
        "nacin": "govornici" if mapping else ("usne" if len(persons) > 1 else ("jedna osoba" if persons else "nema lica")),
        "osobe": [{"ime": names[i], "x": round(float(np.nanmedian(p["x"])), 4), "udio": round(p["udio"], 3),
                   "govornik": inv.get(i)} for i, p in enumerate(persons)],
        "kadrovi": [{"od": round(k["od"] / FPS_ANALIZE, 2), "do": round(min(k["do"] / FPS_ANALIZE, clip["dur"]), 2),
                     "osoba": names[k["osoba"]] if k["osoba"] is not None else None,
                     "govornik": inv.get(k["osoba"]), "nacin": k["nacin"], "crop_x": k["crop_x"]} for k in kad],
        "put": [round(float(v), 4) for v in path],
    }
    return res


def cmd_file(res, info, W, H, out_fps, dst, t0=0.0):
    """sendcmd datoteka za prepare.norm_clip: novi crop x na svakoj sličici izlaza kad se promijeni."""
    path = np.array(res["put"], float)
    if not len(path):
        return False
    sw = info["w"] * max(W / info["w"], H / info["h"])
    tk = np.arange(len(path)) / res["fps_analize"]
    cuts = {round(k["od"], 2) for k in res["kadrovi"]}
    lines, last = [], None
    n_out = int(np.ceil(res["dur"] * out_fps)) + 1
    for j in range(n_out):
        tt = j / out_fps
        k = min(len(path) - 1, int(tt * res["fps_analize"] + 1e-6))
        # unutar kadra glatko (interpolacija), na rezu skok bez međupoložaja
        cx = path[k] if any(abs(tt - c) < 1.5 / res["fps_analize"] for c in cuts) else float(np.interp(tt, tk, path))
        # isti izraz kao crop u prepare.py (iw = stvarna širina nakon scale); bez zareza (sendcmd ih ne voli)
        if last is None or abs(cx - last) * (sw - W) >= 0.5:
            lines.append(f"{t0 + tt:.4f} crop@kadar x (iw-{W})*{cx:.4f};")
            last = cx
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def video_start(path):
    try:
        v = next(s for s in probe(path)["streams"] if s["codec_type"] == "video")
        return float(v.get("start_time") or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def rebuild(proj, pj, results, restore=False):
    """Ponovno složi source.mp4 iz originala (isti klipovi i trajanja; mijenja se samo kadar)."""
    import prepare
    W, H, fps = pj["width"], pj["height"], int(round(pj["fps"]))
    tmp = proj / "_tmp"
    tmp.mkdir(exist_ok=True)
    parts = []
    by_file = {r["file"]: r for r in results}
    for i, c in enumerate(pj["clips"], 1):
        info = video_info(c["file"])
        dst = tmp / f"norm_{i:02d}.mp4"
        r = None if restore else by_file.get(c["file"])
        cf = None
        if r and len({k["crop_x"] for k in r["kadrovi"]}) + any(k["nacin"] == "prati" for k in r["kadrovi"]) > 1:
            cf = tmp / f"kadar_{i:02d}.txt"
            cmd_file(r, info, W, H, fps, cf, t0=video_start(c["file"]))
        cx = r["kadrovi"][0]["crop_x"] if r else c.get("crop_x", 0.5)
        print(f"  [{i}/{len(pj['clips'])}] {Path(c['file']).name}" + ("  (kadar prati govornika)" if cf else ""))
        d = prepare.norm_clip(c["file"], info, dst, W, H, fps, cx, c.get("crop_y", 0.4), cmd_file=cf)
        if abs(d - c["dur"]) > 0.1:
            print(f"  Upozorenje: {Path(c['file']).name} sad traje {d:.2f} s umjesto {c['dur']:.2f} s")
        parts.append(dst)
    prepare.concat(parts, tmp, proj / "source.mp4")


# ---------------------------------------------------------------- ispis i glavni program

def describe(res):
    lines = [f"{Path(res['file']).name}: {len(res['osobe'])} osob" + ("a" if len(res["osobe"]) == 1 else "e")
             + f", način: {res['nacin']}"]
    for o in res["osobe"]:
        lines.append(f"  {o['ime']}: {'lijevo' if o['x'] < 0.4 else 'desno' if o['x'] > 0.6 else 'sredina'}"
                     f" (x {o['x']:.2f}), u kadru {o['udio'] * 100:.0f} %" + (f", govornik {o['govornik']}" if o["govornik"] else ""))
    for k in res["kadrovi"]:
        who = k["osoba"] or "—"
        if k["govornik"]:
            who += f" ({k['govornik']})"
        lines.append(f"  {fmt_time(k['od'])}–{fmt_time(k['do'])}  {who:10s} {k['nacin']:7s} crop_x {k['crop_x']:.2f}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Kadar prati govornika (vodoravna snimka → 9:16)")
    ap.add_argument("projekt")
    ap.add_argument("--analiza", action="store_true", help="samo kadar.json i ispis, video se ne mijenja")
    ap.add_argument("--vrati", action="store_true", help="natrag na nepomični kadar (crop_x iz prepare.py)")
    a = ap.parse_args()

    proj = Path(a.projekt)
    pj_path = proj / "project.json"
    if not pj_path.exists():
        die(f"nema {pj_path}. Prvo: python prepare.py ... --out {proj}")
    pj = load_json(pj_path)
    W, H = pj["width"], pj["height"]
    clips = pj.get("clips") or []
    missing = [c["file"] for c in clips if not Path(c["file"]).exists()]
    if not clips or missing:
        die("originalne snimke nisu pronađene (" + (Path(missing[0]).name if missing else "project.json bez klipova")
            + "); kadar se računa iz originala. Ponovi prepare.py.")

    if a.vrati:
        rebuild(proj, pj, [], restore=True)
        for c in clips:
            c.pop("kadrovi", None)
            c.pop("kadar", None)
        save_json(pj_path, pj)
        print("Vraćen nepomični kadar. source.mp4 ponovno složen; transkript i edit.json vrijede i dalje.")
        return

    results = []
    for c in clips:
        info = video_info(c["file"])
        if not needs_tracking(info, W, H):
            print(f"{Path(c['file']).name}: snimka već stane po širini ({info['w']}×{info['h']} → {W}×{H}), preskačem")
            continue
        print(f"Tražim lica: {Path(c['file']).name} ({c['dur']:.0f} s) ...")
        r = analyse_clip(proj, c, W, H)
        results.append(r)
        print(describe(r))
    if not results:
        print("Nijedan klip ne treba praćenje (nema vodoravnih snimki za uži format).")
        return
    has_gov = (proj / "govornici.json").exists()
    save_json(proj / "kadar.json", {"verzija": version(), "format": pj["format"], "govornici": has_gov,
                                    "klipovi": results})
    print(f"\nZapisano: {proj / 'kadar.json'}")
    if not has_gov and any(len(r["osobe"]) > 1 for r in results):
        print("Savjet: python govornici.py " + str(proj) + " pa ponovno kadar.py — s govornicima je kadar sigurniji.")
    if a.analiza:
        return
    print("Slažem source.mp4 s kadrom koji prati govornika ...")
    rebuild(proj, pj, results)
    by_file = {r["file"]: r for r in results}
    for c in clips:
        r = by_file.get(c["file"])
        if r:
            c["kadar"] = "prati"
            c["kadrovi"] = [{"od": k["od"], "do": k["do"], "crop_x": k["crop_x"]} for k in r["kadrovi"]]
    save_json(pj_path, pj)
    print("Gotovo. Vremena se nisu promijenila: transkript, govornici i edit.json vrijede i dalje.")
    print(f"Sljedeće: python render.py {proj}  (ili plan.py ako još nema edit.json)")


if __name__ == "__main__":
    main()
