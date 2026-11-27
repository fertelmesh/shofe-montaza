"""Podcast (M4.2): režija — kamera prati onoga tko govori, široki kadar kad pričaju svi.

  python rezija.py podcast_projekt                       → rezija.json (+ .txt, .png) i source.mp4 (gotov 16:9 program)
  python rezija.py podcast_projekt --analiza             samo rezija.json/.txt/.png, bez videa
  python rezija.py podcast_projekt --kamere "kamera1.mp4=Marko,kamera3.mp4=siroki"   ručno: koja kamera koga snima
  python rezija.py podcast_projekt --umetci cesto        široki kadar usred dugog monologa: nikad|rijetko|povremeno|cesto

Ide nakon sinkro.py (isti projekt). Prvo pokretanje (još nema govornici.json) složi source.mp4 iz širokog kadra sa
zvukom glavnog izvora; zatim transcribe.py i govornici.py na tom projektu, pa ponovno rezija.py → kadar prati
govornika. Vrijeme u source.mp4 je vrijeme glavnog izvora minus `pocetak`, pa transkript i govornici vrijede i nakon
nove režije, a projekt je običan Shofe projekt (plan.py, render.py, titlovi, isječci…).

Koja kamera koga snima (vidi ODLUKE.md): u nekoliko prozora od 15 s svake kamere YuNet nađe lica, a usne se
usporede s tim kada tko govori (isto kao kadar.py). Kamera s jednim licem = krupni kadar tog govornika;
s dvoje ili više = široki kadar; bez lica = samo zamjena kad druge kamere ne snimaju.

Pravila režije (kao montažer podcasta):
- govori jedan → njegov krupni kadar (rez PREDNOST s prije prve riječi);
- pričaju dvoje u isti glas, ili se brzo izmjenjuju (≥ 3 kratke izmjene zaredom) → široki kadar;
- govornik bez svoje kamere (gost izvan kadra) → široki kadar; tišina dulja od TISINA s → široki kadar;
- svaki kadar traje barem MIN_KADAR s (kratko „aha" ne prebacuje kameru);
- dugi monolog: povremeno UMETAK_TRAJANJE s širokog kadra (ili reakcije drugoga ako nema širokog);
- kamera koja u tom trenutku ne snima (počela kasnije, prekinula) se ne bira.

Za vrijeme pjesme (nastupi.json iz nastupi.py, M4.3b2) režija je drukčija: govornici se ne prate (pjevanje nije
govor), pjesma počne i završi u širokom kadru, a kamere se izmjenjuju sporo (prosječno PJESMA_KADAR s, široki dulje,
ostale kamere kraće) i to na udarac, svakih nekoliko taktova (ritam.py). Bez jasnog ritma rez ide po sekundama.
  python rezija.py podcast_projekt --pjesma-kadar 12     sporije (0 = cijela pjesma u širokom kadru)
"""
import argparse
import math
import subprocess
from pathlib import Path

import numpy as np

import kadar as K
import sinkro as S
from common import FONTS_DIR, FORMATS, die, ffmpeg, fmt_time, load_json, run, save_json, version

KORAK = 0.1             # s; mreža na kojoj se odlučuje
MIN_KADAR = 2.0         # s; najkraći kadar
PREDNOST = 0.2          # s; rez na novog govornika malo prije prve riječi
BRZA_IZMJENA = 2.5      # s; izmjena kraća od ovoga, ≥ 3 zaredom → široki kadar
SPOJI_IZMJENU = 1.0     # s; pauza istog govornika kraća od ovoga je ista izmjena
PREKLOP_MIN = 0.6       # s; kraće preklapanje (dobacivanje „da", „aha") se ne broji
TISINA = 3.0            # s; dulja tišina → široki kadar
UMETCI = {"nikad": None, "rijetko": 45.0, "povremeno": 30.0, "cesto": 12.0}
UMETAK_TRAJANJE = 3.5   # s
PROZORA = 8             # prozora po kameri za traženje lica
PROZOR = 15.0           # s
MIN_VIDLJIV = 0.15      # osoba se broji ako je vidljiva u barem toliko sličica
CRF = 18
PJESMA_KADAR = 8.0      # s; prosječni kadar za vrijeme pjesme
PJESMA_MIN = 4.0        # s; najkraći kadar u pjesmi
PJESMA_UVOD = 1.5       # × PJESMA_KADAR: prvi (široki) kadar pjesme

# razlozi (po sličici mreže)
R_GOVORI, R_PREKLOP, R_IZMJENA, R_TISINA, R_BEZ_KAMERE, R_UMETAK, R_POCETAK, R_PJESMA = range(8)
RAZLOZI = {R_GOVORI: "govori", R_PREKLOP: "pričaju u isti glas", R_IZMJENA: "brza izmjena",
           R_TISINA: "tišina", R_BEZ_KAMERE: "govornik nema svoju kameru", R_UMETAK: "umetak u monologu",
           R_POCETAK: "početak", R_PJESMA: "pjesma"}


# ---------------------------------------------------------------- ulaz

def load_sync(proj):
    sp = proj / "sinkro.json"
    if not sp.exists():
        die(f"nema {sp.name} u {proj} — prvo: python sinkro.py <mapa sa snimkama> --out {proj}")
    data = load_json(sp)
    cams = [e for e in data["izvori"] if e["vrsta"] == "video" and e.get("pronaden", True)]
    if not cams:
        die("u sinkro.json nema nijedne kamere (videa) koja je pronađena na crti glavnog izvora")
    master = next(e for e in data["izvori"] if e.get("glavni"))
    return data, cams, master


def span(cams, master):
    """Dio crte glavnog izvora koji postaje epizoda: gdje ima zvuka glavnog i barem jedne kamere."""
    a = max(master["od"], min(e["od"] for e in cams))
    b = min(master["do"], max(e["do"] for e in cams))
    if b - a < 1:
        die("kamere i glavni zvuk se ne preklapaju (provjeri sinkro.txt)")
    return round(a, 3), round(b - a, 3)


def speakers(proj):
    """(odsječci [(od, do, id)] u vremenu source.mp4, imena {id: ime}) iz govornici.json."""
    gp = proj / "govornici.json"
    if not gp.exists():
        return [], {}
    g = load_json(gp)
    segs = [(float(s["od"]), float(s["do"]), s["govornik"]) for s in g.get("odsjecci", [])]
    names = {x["id"]: x.get("ime") or "" for x in g.get("govornici", [])}
    return sorted(segs), names


def label(g, names):
    return f"{names[g]} ({g})" if names.get(g) else g


# ---------------------------------------------------------------- koja kamera koga snima

def cam_range(e, pocetak, dur):
    """Dio programa (s) koji kamera pokriva."""
    return max(0.0, e["od"] - pocetak), min(dur, e["do"] - pocetak)


def pick_windows(a, b, segs, n=PROZORA, L=PROZOR):
    """Početci prozora (vrijeme programa) između a i b: raspoređeni po snimci, ondje gdje govori više ljudi."""
    if b - a <= L:
        return [a]
    starts = np.arange(a, b - L + 1e-6, 2.5)
    score = np.zeros(len(starts))
    for i, s in enumerate(starts):
        tot, who = 0.0, set()
        for x, y, g in segs:
            o = min(y, s + L) - max(x, s)
            if o > 0:
                tot += o
                who.add(g)
        score[i] = len(who) * 10 + tot
    n = min(n, max(1, int((b - a) // L)))
    out = []
    edges = np.linspace(a, b - L, n + 1)
    for j in range(n):
        m = (starts >= edges[j] - 1e-6) & (starts <= edges[j + 1] + 1e-6)
        if m.any():
            idx = np.flatnonzero(m)
            out.append(float(starts[idx[np.argmax(score[idx])]]))
    return sorted(set(out))


def window_frames(path, t0, L, w, h, fps=K.FPS_ANALIZE):
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{max(0.0, t0):.3f}", "-t", f"{L:.3f}", "-i", str(path), "-an",
           "-vf", f"fps={fps},scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    r = subprocess.run(cmd, capture_output=True)
    n = w * h * 3
    b = r.stdout
    return [np.frombuffer(b[i:i + n], np.uint8).reshape(h, w, 3) for i in range(0, len(b) - n + 1, n)]


def analyse_camera(e, segs, pocetak, dur, log=print):
    """Lica u prozorima kamere → osobe, i za svaku osobu koji govornik je to (po usnama)."""
    import cv2
    a, b = cam_range(e, pocetak, dur)
    W0, H0 = e.get("w") or 1920, e.get("h") or 1080
    aw = K.SIRINA_ANALIZE if W0 >= H0 else int(round(K.SIRINA_ANALIZE * W0 / H0 / 2)) * 2
    ah = int(round(aw * H0 / W0 / 2)) * 2
    det = K.detector(aw, ah)
    dets, ts = [], []
    wins = pick_windows(a, b, segs)
    for w0 in wins:
        L = min(PROZOR, b - w0)
        for k, fr in enumerate(window_frames(e["datoteka"], S.to_source(e, pocetak + w0), L, aw, ah)):
            _, res = det.detect(fr)
            gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            faces = []
            for d in (res if res is not None else []):
                x, y, fw, fh = map(float, d[:4])
                lm = [float(v) for v in d[4:14]]
                faces.append({"x": (x + fw / 2) / aw, "y": (y + fh / 2) / ah, "w": fw / aw, "h": fh / ah,
                              "p": K.mouth_patch(gray, lm), "s": float(d[14])})
            dets.append(faces)
            ts.append(w0 + k / K.FPS_ANALIZE)
        dets.append([])                 # razmak između prozora: usne se ne uspoređuju preko reza
        ts.append(np.nan)
    t = np.array(ts, float)
    persons = K.tracks(dets) if dets else []
    labelled = [s for s in segs if s[2]]
    mapping = K.match_speakers(persons, labelled, t)[0] if (persons and labelled) else {}
    who = {i: g for g, i in mapping.items()}
    osobe = []
    for i, p in enumerate(persons):
        osobe.append({"x": round(float(np.nanmedian(p["x"])), 3), "w": round(float(np.nanmedian(p["w"])), 3),
                      "vidljiv": round(float(p["udio"]), 2), "govornik": who.get(i)})
    vis = [o for o in osobe if o["vidljiv"] >= MIN_VIDLJIV]
    ys = [max(f, key=lambda q: q["w"])["y"] for f in dets if f]
    if len(vis) >= 2:
        uloga, gov = "siroki", None
    elif len(vis) == 1:
        uloga, gov = "krupni", vis[0]["govornik"]
    else:
        uloga, gov = "bez_lica", None
    log(f"  {e['ime']}: {len(wins)} prozora, osoba {len(vis)} → {uloga}" + (f" {gov}" if gov else ""))
    return {"ime": e["ime"], "uloga": uloga, "govornik": gov, "osobe": vis,
            "lice_y": round(float(np.median(ys)), 3) if ys else None, "od": round(a, 3), "do": round(b, 3)}


def parse_manual(s, cams, names):
    """"kamera1.mp4=Marko,kamera3=siroki" → {ime kamere: ("krupni", id) | ("siroki", None) | ("bez_lica", None)}."""
    out = {}
    by_name = {v.lower(): k for k, v in names.items() if v}
    for part in [p for p in (s or "").split(",") if p.strip()]:
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip()
        e = next((c for c in cams if k in (c["ime"].lower(), Path(c["ime"]).stem.lower())), None)
        if e is None:
            die(f"--kamere: nema kamere '{k}' (kamere: {', '.join(c['ime'] for c in cams)})")
        vl = v.lower()
        if vl in ("siroki", "široki", "svi", "wide"):
            out[e["ime"]] = ("siroki", None)
        elif vl in ("ostalo", "bez_lica", "nista", "ništa"):
            out[e["ime"]] = ("bez_lica", None)
        elif v.upper() in names or v.upper().startswith("G"):
            out[e["ime"]] = ("krupni", v.upper())
        elif vl in by_name:
            out[e["ime"]] = ("krupni", by_name[vl])
        else:
            die(f"--kamere: ne znam tko je '{v}' (govornici: "
                + ", ".join(label(g, names) for g in names) + "; ili 'siroki', 'ostalo')")
    return out


# ---------------------------------------------------------------- pravila režije

def turns(segs, gap=SPOJI_IZMJENU):
    """Odsječci → izmjene [(od, do, id)] (isti govornik s kratkom pauzom = ista izmjena)."""
    out = []
    for a, b, g in sorted(segs):
        if out and out[-1][2] == g and a - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b, g])
    return [tuple(x) for x in out]


def runs_of(mask):
    """Bool niz → [(od_k, do_k)] uzastopnih True."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def desired(segs, n, speaker_ids, has_cu):
    """Po sličici mreže: oznaka (0 = široki, i+1 = krupni kadar govornika i) i razlog."""
    t = np.arange(n) * KORAK
    act = np.zeros((len(speaker_ids), n), bool)
    lead = np.zeros((len(speaker_ids), n), bool)
    idx = {g: i for i, g in enumerate(speaker_ids)}
    for a, b, g in segs:
        act[idx[g]] |= (t >= a) & (t < b)
        lead[idx[g]] |= (t >= a - PREDNOST) & (t < b)
    lab = np.full(n, -2)                 # -2 = drži prethodni
    why = np.full(n, R_TISINA)
    cnt = act.sum(axis=0)
    over = cnt >= 2
    for a, b in runs_of(over):
        if (b - a) * KORAK < PREKLOP_MIN:
            over[a:b] = False
    # jedan govornik (s prednošću); kod kratkog preklapanja kadar dobije onaj tko je zadnji počeo
    for a, b, g in sorted(segs):
        m = (t >= a - PREDNOST) & (t < b)
        lab[m] = idx[g] + 1 if has_cu.get(g) else 0
        why[m] = R_GOVORI if has_cu.get(g) else R_BEZ_KAMERE
    lab[over] = 0
    why[over] = R_PREKLOP
    # brza izmjena: ≥ 3 kratke izmjene zaredom
    tr = turns(segs)
    i = 0
    while i < len(tr):
        j = i
        while j < len(tr) and tr[j][1] - tr[j][0] < BRZA_IZMJENA:
            j += 1
        if j - i >= 3:
            a, b = int(round(tr[i][0] / KORAK - PREDNOST / KORAK)), int(round(tr[j - 1][1] / KORAK))
            lab[max(0, a):b] = 0
            why[max(0, a):b] = R_IZMJENA
        i = max(j, i + 1)
    # tišina: nakon 1 s duge tišine široki kadar (do PREDNOST prije sljedećeg govora)
    quiet = ~lead.any(axis=0)
    for a, b in runs_of(quiet):
        if (b - a) * KORAK >= TISINA:
            s = a + int(1.0 / KORAK) if a > 0 else a
            lab[s:b] = 0
            why[s:b] = R_POCETAK if a == 0 else R_TISINA
    # drži prethodni kadar kroz kratke pauze
    cur, cw = 0, R_POCETAK
    for k in range(n):
        if lab[k] == -2:
            lab[k], why[k] = cur, cw
        else:
            cur, cw = lab[k], why[k]
    return lab, why, act


def covers(e, pocetak, k):
    t = pocetak + k * KORAK
    return e["od"] - 1e-6 <= t <= e["do"] - KORAK + 1e-6


def choose_cameras(lab, why, cams, roles, pocetak, speaker_ids):
    """Oznaka po sličici → indeks kamere (len(cams) = crno, nijedna kamera ne snima)."""
    n = len(lab)
    BLACK = len(cams)
    cov = np.array([[covers(e, pocetak, k) for k in range(n)] for e in cams])
    wide = sorted([i for i, r in enumerate(roles) if r["uloga"] == "siroki"],
                  key=lambda i: (-len(roles[i]["osobe"]), -cov[i].sum()))
    cu = {g: sorted([i for i, r in enumerate(roles) if r["uloga"] == "krupni" and r["govornik"] == g],
                    key=lambda i: -max([o["w"] for o in roles[i]["osobe"]] or [0]))
          for g in speaker_ids}
    order = sorted(range(len(cams)), key=lambda i: ({"siroki": 0, "krupni": 1}.get(roles[i]["uloga"], 2),
                                                    -cov[i].sum()))
    cam = np.full(n, BLACK)
    prev = BLACK
    for k in range(n):
        c = None
        if lab[k] > 0:
            c = next((i for i in cu[speaker_ids[lab[k] - 1]] if cov[i, k]), None)
        if c is None:
            c = next((i for i in wide if cov[i, k]), None)
        if c is None and prev != BLACK and cov[prev, k]:
            c = prev
        if c is None:
            c = next((i for i in order if cov[i, k]), BLACK)
        cam[k] = c
        prev = c
    return cam, cov, wide, cu


def merge_short(cam, cov, min_len):
    """Prekratki kadrovi se pripoje susjedu (kadar.shots), pa se provjeri da kamera stvarno snima."""
    runs = K.shots(cam, min_len=min_len)
    out = np.array(cam)
    for a, b, c in runs:
        out[a:b] = c
    BLACK = cov.shape[0]
    for k in range(len(out)):
        if out[k] != BLACK and not cov[out[k], k]:
            out[k] = cam[k]
    # komadići nastali na rubu snimanja kamere: susjed koji tu snima ih preuzme
    for _ in range(3):
        k, n, changed = 0, len(out), False
        while k < n:
            e = k
            while e < n and out[e] == out[k]:
                e += 1
            if e - k < min_len:
                for c in ([out[k - 1]] if k > 0 else []) + ([out[e]] if e < n else []):
                    if c == BLACK or cov[c, k:e].all():
                        out[k:e] = c
                        changed = True
                        break
            k = e
        if not changed:
            break
    return out


def add_cutaways(cam, why, act, roles, wide, cu, cov, speaker_ids, every):
    """Dugi krupni kadar: svakih `every` s umetak širokog kadra (ili reakcije drugoga), na pauzi u govoru."""
    if not every:
        return cam, why
    cam, why = cam.copy(), why.copy()
    L = int(round(UMETAK_TRAJANJE / KORAK))
    step = int(round(every / KORAK))
    mn = int(round(MIN_KADAR / KORAK))
    speaking = act.any(axis=0)
    k, n = 0, len(cam)
    while k < n:
        e = k
        while e < n and cam[e] == cam[k]:
            e += 1
        c = cam[k]
        if c < len(roles) and roles[c]["uloga"] == "krupni" and e - k >= step + L + mn:
            g = roles[c]["govornik"]
            pos = k + step
            while pos + L + mn <= e:
                # najbliža pauza u govoru (± 3 s)
                best = pos
                for d in range(0, int(3 / KORAK)):
                    for p in (pos - d, pos + d):
                        if k + mn <= p < e - L - mn and not speaking[p]:
                            best = p
                            break
                    else:
                        continue
                    break
                alt = [i for i in wide if cov[i, best:best + L].all()]
                if not alt:
                    alt = [i for gg in speaker_ids if gg != g for i in cu[gg] if cov[i, best:best + L].all()]
                if alt:
                    cam[best:best + L] = alt[0]
                    why[best:best + L] = R_UMETAK
                pos = best + L + step
        k = e
    return cam, why


def outside_songs(segs, songs):
    """Odsječci govora bez dijelova koji su u pjesmi (pjevanje nije govor, ne prati se)."""
    out = []
    for a, b, g in segs:
        parts = [(a, b)]
        for s in songs:
            nxt = []
            for x, y in parts:
                if y <= s["od"] or x >= s["do"]:
                    nxt.append((x, y))
                    continue
                if x < s["od"]:
                    nxt.append((x, s["od"]))
                if y > s["do"]:
                    nxt.append((s["do"], y))
            parts = nxt
        out += [(x, y, g) for x, y in parts if y - x > 0.05]
    return out


def song_cuts(od, do, kadar, udarci):
    """Vremena rezova unutar pjesme [od, do]: prvi (široki) kadar dulji, zatim naizmjence široki ~1,25× i
    ostali ~0,75× prosječnog kadra. S jasnim ritmom rez je na udarcu i uvijek isti broj udaraca (cijeli taktovi)
    od prvog udarca pjesme. Vrati (rezovi, broj udaraca u koraku ili None)."""
    if kadar <= 0 or do - od < 2 * PJESMA_MIN:
        return [], None
    lens = lambda i: kadar * (PJESMA_UVOD if i == 0 else 1.25 if i % 2 == 0 else 0.75)  # noqa: E731
    b = [t for t in (udarci or []) if od - 0.05 <= t <= do]
    grid, per = None, None
    if len(b) >= 8:
        period = float(np.median(np.diff(b)))
        per = 4 if 60.0 / period >= 90 else 2           # pola tempa: 2 udarca = takt
        grid = b[::per]
    cuts, t, i = [], od, 0
    while True:
        want = t + lens(i)
        if grid:
            cand = [g for g in grid if g >= t + PJESMA_MIN and g <= do - PJESMA_MIN]
            if not cand:
                break
            c = min(cand, key=lambda g: abs(g - want))
            if c < want - 0.6 * kadar and c == cand[-1]:   # do kraja pjesme ostaje premalo
                break
        else:
            c = want
            if c > do - PJESMA_MIN:
                break
        cuts.append(round(c, 3))
        t, i = c, i + 1
    return cuts, per


def song_plan(song, cams, roles, cov, kadar):
    """Kadrovi pjesme [(od_k, do_k, kamera)] na mreži KORAK: počne i završi u širokom kadru, između široki i
    ostale kamere naizmjence (ostale redom). Kamera koja u tom dijelu ne snima preskoči se."""
    n = cov.shape[1]
    a, b = max(0, int(round(song["od"] / KORAK))), min(n, int(round(song["do"] / KORAK)))
    if b <= a:
        return [], None
    wide = sorted([i for i, r in enumerate(roles) if r["uloga"] == "siroki"],
                  key=lambda i: (-len(roles[i]["osobe"]), -cov[i, a:b].sum()))
    rest = sorted([i for i, r in enumerate(roles) if r["uloga"] != "siroki"],
                  key=lambda i: ({"krupni": 0}.get(roles[i]["uloga"], 1), roles[i]["ime"]))
    cuts, per = song_cuts(song["od"], song["do"], kadar, song.get("udarci"))
    song["_rezovi"] = cuts
    edges = [a] + [int(round(c / KORAK)) for c in cuts] + [b]
    if wide and rest and len(edges) >= 4 and (len(edges) - 2) % 2 == 1:
        edges.pop(-2)                                     # zadnji kadar pjesme neka bude široki
    out, j = [], 0
    for k, (x, y) in enumerate(zip(edges, edges[1:])):
        if y <= x:
            continue
        if wide and (k % 2 == 0 or not rest):
            pref = wide + rest
        elif rest:
            pref = rest[j % len(rest):] + rest[:j % len(rest)] + wide
            j += 1
        else:
            pref = list(range(len(cams)))
        c = next((i for i in pref if cov[i, x:y].all()), None)
        if c is None:   # nitko ne snima cijeli dio: najviše pokriven
            c = max(pref, key=lambda i: cov[i, x:y].sum()) if pref else None
            if c is None or not cov[c, x:y].any():
                continue
        if out and out[-1][2] == c and out[-1][1] == x:
            out[-1] = (out[-1][0], y, c)
        else:
            out.append((x, y, c))
    return out, per


def fix_song_edges(cam, cov, in_song, min_len):
    """Komadić govora kraći od najkraćeg kadra uz rub pjesme preuzme susjedni kadar koji tu snima."""
    BLACK = cov.shape[0]
    out = cam.copy()
    k, n = 0, len(out)
    while k < n:
        e = k
        while e < n and out[e] == out[k] and in_song[e] == in_song[k]:
            e += 1
        if not in_song[k] and e - k < min_len and ((k > 0 and in_song[k - 1]) or (e < n and in_song[e])):
            nb = ([out[k - 1]] if k > 0 and not in_song[k - 1] else []) + ([out[e]] if e < n else []) \
                + ([out[k - 1]] if k > 0 else [])
            for c in nb:
                if c == BLACK or cov[c, k:e].all():
                    out[k:e] = c
                    break
        k = e
    return out


def shots_from(cam, why, lab, cams, roles, speaker_ids, names, song_of=None, songs=()):
    BLACK = len(cams)
    out = []
    k, n = 0, len(cam)
    while k < n:
        e = k
        while e < n and cam[e] == cam[k]:
            e += 1
        c = int(cam[k])
        rs = np.bincount(why[k:e], minlength=len(RAZLOZI))
        r = int(np.argmax(rs))
        txt = RAZLOZI[r]
        if r == R_GOVORI:
            ls = [int(x) for x in lab[k:e] if x > 0]
            if ls:
                g = speaker_ids[max(set(ls), key=ls.count) - 1]
                txt = f"govori {label(g, names)}"
        if c != BLACK and r == R_GOVORI and roles[c]["uloga"] != "krupni":
            txt += " (njegova kamera ne snima)"
        sh = {"od": round(k * KORAK, 3), "do": round(e * KORAK, 3),
              "kamera": cams[c]["ime"] if c != BLACK else None,
              "uloga": roles[c]["uloga"] if c != BLACK else "crno", "zasto": txt}
        if r == R_PJESMA and song_of is not None:
            ids = [int(x) for x in song_of[k:e] if x >= 0]
            if ids:
                sg = songs[max(set(ids), key=ids.count)]
                sh["pjesma"] = sg["id"]
                sh["zasto"] = f"pjesma {sg['id']}" + (": široki kadar" if sh["uloga"] == "siroki" else "")
        out.append(sh)
        k = e
    return out


def direct(segs, cams, roles, pocetak, dur, names, umetci="povremeno", min_kadar=MIN_KADAR, songs=None,
           pjesma_kadar=PJESMA_KADAR):
    """Cijela režija: kadrovi [{od, do, kamera, uloga, zasto}] u vremenu programa.
    songs = [{id, od, do, udarci}] (vrijeme programa): za vrijeme pjesme široki kadar i spori rezovi na udarac."""
    n = int(math.ceil(dur / KORAK - 1e-9))
    songs = sorted((s for s in songs or [] if s["do"] > 0 and s["od"] < dur), key=lambda s: s["od"])
    if songs:
        segs = outside_songs(segs, songs)
    speaker_ids = sorted({g for *_, g in segs}, key=lambda g: (len(g), g))
    has_cu = {g: any(r["uloga"] == "krupni" and r["govornik"] == g for r in roles) for g in speaker_ids}
    lab, why, act = desired(segs, n, speaker_ids, has_cu)
    cam, cov, wide, cu = choose_cameras(lab, why, cams, roles, pocetak, speaker_ids)
    cam = merge_short(cam, cov, int(round(min_kadar / KORAK)))
    cam, why = add_cutaways(cam, why, act, roles, wide, cu, cov, speaker_ids, UMETCI.get(umetci))
    song_of = np.full(n, -1)
    for i, s in enumerate(songs):
        plan, per = song_plan(s, cams, roles, cov, pjesma_kadar)
        s["_takt"] = per
        for x, y, c in plan:
            cam[x:y] = c
            why[x:y] = R_PJESMA
            song_of[x:y] = i
    if songs:
        cam = fix_song_edges(cam, cov, song_of >= 0, int(round(min_kadar / KORAK)))
    shots = shots_from(cam, why, lab, cams, roles, speaker_ids, names, song_of, songs)
    # rez u pjesmi točno na udarcu (mreža odlučivanja je KORAK s, a sličica je ~33 ms)
    exact = [t for s in songs for t in [s["od"], s["do"]] + s.get("_rezovi", [])]
    for x, y in zip(shots, shots[1:]):
        t = min(exact, key=lambda v: abs(v - y["od"]), default=None)
        if t is not None and abs(t - y["od"]) <= KORAK / 2 + 1e-6 and x["od"] < t < y["do"]:
            x["do"] = y["od"] = round(t, 3)
    if shots:
        shots[-1]["do"] = round(dur, 3)
    return shots


# ---------------------------------------------------------------- program (source.mp4)

def render_program(proj, shots, cams, roles, master, pocetak, dur, W, H, fps, log=print):
    tmp = proj / "_tmp" / "rezija"
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.glob("k_*.mp4"):
        old.unlink()
    by = {e["ime"]: e for e in cams}
    rl = {r["ime"]: r for r in roles}
    parts = []
    for i, s in enumerate(shots):
        f0, f1 = round(s["od"] * fps), round(s["do"] * fps)
        nfr = f1 - f0
        if nfr <= 0:
            continue
        dst = tmp / f"k_{i:05d}.mp4"
        common_out = ["-frames:v", str(nfr), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF),
                      "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", dst.name]
        if s["kamera"] is None:
            cmd = [ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={fps}",
                   *common_out]
        else:
            e = by[s["kamera"]]
            ts = S.to_source(e, pocetak + f0 / fps)
            cx, cy = rl[e["ime"]].get("crop_x", 0.5), rl[e["ime"]].get("crop_y", 0.4)
            vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={W}:{H}:(iw-{W})*{cx}:(ih-{H})*{cy},fps={fps},setsar=1,"
                  f"tpad=stop_mode=clone:stop_duration=2,format=yuv420p")
            cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, ts):.4f}", "-i", Path(e["datoteka"]).resolve(),
                   "-vf", vf, *common_out]
        run(cmd, cwd=tmp)
        parts.append(dst)
        if log and (i + 1) % 25 == 0:
            log(f"  {i + 1}/{len(shots)} kadrova")
    lst = tmp / "lista.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "slika.mp4"],
        cwd=tmp)
    ms = S.to_source(master, pocetak)
    out = (proj / "source.mp4").resolve()
    run([ffmpeg(), "-y", "-v", "error", "-i", "slika.mp4", "-ss", f"{max(0.0, ms):.4f}", "-t", f"{dur:.3f}",
         "-i", Path(master["datoteka"]).resolve(), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-af", "apad", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", "-t", f"{dur:.3f}",
         "-movflags", "+faststart", out], cwd=tmp)
    return out


def crop_for_role(r, e, W, H):
    """Krupni kadar iz snimke drugog omjera (npr. uspravni mobitel): izrez oko lica. Vraća (crop_x, crop_y)."""
    cx, cy = 0.5, 0.4
    if r["uloga"] == "krupni" and r["osobe"] and e.get("w"):
        cx = round(K.crop_for(r["osobe"][0]["x"], {"w": e["w"], "h": e["h"]}, W, H), 3)
        if r.get("lice_y") is not None:
            sh = e["h"] * max(W / e["w"], H / e["h"])
            if sh - H >= 1:
                cy = round(float(np.clip((r["lice_y"] * sh - H / 2) / (sh - H), 0.0, 1.0)), 3)
    return cx, cy


# ---------------------------------------------------------------- ispis i slika

def load_songs(proj, master, pocetak, dur, log=print):
    """Pjesme iz nastupi.json (vrijeme programa) + udarci iz zvuka glavnog izvora (ritam.py)."""
    import nastupi
    import ritam
    out = []
    for n in nastupi.active(nastupi.load(proj)):
        od, do = max(0.0, float(n["od"])), min(dur, float(n["do"]))
        if do - od < 1:
            continue
        s = {"id": n["id"], "od": od, "do": do, "naziv": n.get("naziv") or "", "udarci": [], "bpm": None}
        try:
            f0 = S.to_source(master, pocetak + od)
            r = ritam.of_file(Path(master["datoteka"]), max(0.0, f0), S.to_source(master, pocetak + do))
            if r["jasno"]:
                s["udarci"] = [round(S.to_master(master, t) - pocetak, 3) for t in r["udarci"]]
                s["bpm"] = r["bpm"]
        except SystemExit:
            pass
        if log:
            log(f"Pjesma {s['id']} {fmt_time(od)}–{fmt_time(do)}: "
                + (f"{s['bpm']:.0f} BPM, rez na udarac" if s["bpm"] else "ritam nije jasan, rez po sekundama"))
        out.append(s)
    return out


def song_summary(songs, shots):
    res = []
    for s in songs:
        sh = [x for x in shots if x.get("pjesma") == s["id"]]
        lens = [min(x["do"], s["do"]) - max(x["od"], s["od"]) for x in sh]
        res.append({"id": s["id"], "od": round(s["od"], 3), "do": round(s["do"], 3), "naziv": s.get("naziv", ""),
                    "bpm": s.get("bpm"), "takt": s.get("_takt"), "kadrova": len(sh),
                    "prosjek_s": round(float(np.mean(lens)), 1) if lens else 0.0})
    return res


def stats(shots, segs, roles, names):
    lens = [s["do"] - s["od"] for s in shots]
    st = {"kadrova": len(shots), "prosjek_s": round(float(np.mean(lens)), 1) if lens else 0,
          "najkraci_s": round(min(lens), 1) if lens else 0,
          "umetaka": sum(1 for s in shots if s["zasto"] == RAZLOZI[R_UMETAK])}
    on_cam = {}
    rl = {r["ime"]: r for r in roles}
    for a, b, g in segs:
        tot = good = 0.0
        for s in shots:
            o = min(b, s["do"]) - max(a, s["od"])
            if o > 0:
                tot += o
                r = rl.get(s["kamera"])
                if r and (r["govornik"] == g or (r["uloga"] == "siroki")):
                    good += o
        x = on_cam.setdefault(g, [0.0, 0.0])
        x[0] += tot
        x[1] += good
    st["govornik_u_kadru"] = {g: round(v[1] / v[0], 3) if v[0] else None for g, v in on_cam.items()}
    return st


def kadrova(n):
    """1 kadar, 2–4 kadra, 5+ kadrova (11–14 kadrova)."""
    if n % 10 == 1 and n % 100 != 11:
        return "kadar"
    return "kadra" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "kadrova"


def summary(rez, names):
    L = [f"Režija (Shofe {rez['shofe']}) — epizoda {fmt_time(rez['trajanje'])}, "
         f"od {fmt_time(rez['pocetak'])} na crti glavnog izvora", "", "Kamere:"]
    for r in rez["kamere"]:
        u = {"krupni": "krupni kadar", "siroki": "široki kadar", "bez_lica": "bez lica (samo zamjena)"}[r["uloga"]]
        who = ""
        if r["uloga"] == "krupni":
            who = " — " + (label(r["govornik"], names) if r["govornik"] else "NE ZNAM TKO (upiši --kamere)")
        elif r["uloga"] == "siroki":
            gs = [label(o["govornik"], names) for o in r["osobe"] if o.get("govornik")]
            who = f" — {len(r['osobe'])} osobe" + (f" ({', '.join(gs)})" if gs else "")
        L.append(f"  {r['ime']:<26} {u}{who}{' (RUČNO)' if r.get('rucno') else ''}  "
                 f"[{fmt_time(r['od'])}–{fmt_time(r['do'])}]")
    st = rez["statistika"]
    L += ["", f"Kadrova: {st['kadrova']}, prosječno {st['prosjek_s']:.1f} s, najkraći {st['najkraci_s']:.1f} s, "
              f"umetaka širokog kadra: {st['umetaka']} (umetci: {rez['umetci']})".replace(".", ",")]
    for g, v in st["govornik_u_kadru"].items():
        if v is not None:
            L.append(f"  {label(g, names)}: u kadru dok govori {round(v * 100)} %")
    for p in rez.get("pjesme") or []:
        naziv = f" „{p['naziv']}“" if p.get("naziv") else ""
        rit = (f"{p['bpm']:.0f} BPM, rez na početku takta" if p.get("bpm") and p.get("takt")
               else "rez po sekundama (ritam nije jasan)" if p["kadrova"] > 1 else "cijela u širokom kadru")
        L.append(f"  Pjesma {p['id']}{naziv} {fmt_time(p['od'])}–{fmt_time(p['do'])}: {p['kadrova']} {kadrova(p['kadrova'])}, "
                 f"prosječno {str(p['prosjek_s']).replace('.', ',')} s, {rit}")
    warn = rez.get("upozorenja") or []
    if warn:
        L += ["", "PROVJERI:"] + [f"  - {w}" for w in warn]
    L += ["", "Kadrovi:"]
    for s in rez["kadrovi"]:
        L.append(f"  {fmt_time(s['od'])}–{fmt_time(s['do'])}  {s['kamera'] or 'CRNO':<26} {s['zasto']}")
    return "\n".join(L) + "\n"


PALETA = [(232, 93, 63), (58, 134, 255), (46, 175, 125), (245, 183, 0), (155, 93, 229), (255, 112, 166),
          (0, 187, 199), (140, 140, 140)]


def thumb(e, t, w, h):
    cmd = [ffmpeg(), "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(e["datoteka"]), "-frames:v", "1",
           "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    b = subprocess.run(cmd, capture_output=True).stdout
    if len(b) < w * h * 3:
        return None
    return np.frombuffer(b[:w * h * 3], np.uint8).reshape(h, w, 3)


def draw_png(proj, rez, cams, segs, names, path, width=1600):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    dur = rez["trajanje"]
    by = {e["ime"]: e for e in cams}
    roles = rez["kamere"]
    col = {r["ime"]: PALETA[i % len(PALETA)] for i, r in enumerate(roles)}
    speaker_ids = sorted({g for *_, g in segs}, key=lambda g: (len(g), g))
    tw, th = 300, 169
    pad = 24
    rows_h = 34
    H = pad + th + 70 + rows_h * (len(speaker_ids) + 1 + bool(rez.get("pjesme"))) + 60
    img = Image.new("RGB", (width, H), (24, 24, 28))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 18)
    fb = ImageFont.truetype(str(FONTS_DIR / "Montserrat-ExtraBold.ttf"), 18)
    x = pad
    for r in roles:
        e = by[r["ime"]]
        mid = (r["od"] + r["do"]) / 2
        im = thumb(e, S.to_source(e, rez["pocetak"] + mid), tw, th)
        if im is not None:
            img.paste(Image.fromarray(im), (x, pad))
        d.rectangle([x - 3, pad - 3, x + tw + 2, pad + th + 2], outline=col[r["ime"]], width=4)
        u = {"krupni": "krupni", "siroki": "široki", "bez_lica": "bez lica"}[r["uloga"]]
        who = label(r["govornik"], names) if r.get("govornik") else ""
        d.text((x, pad + th + 8), r["ime"][:30], font=fb, fill=col[r["ime"]])
        d.text((x, pad + th + 32), f"{u} {who}".strip(), font=f, fill=(230, 230, 230))
        x += tw + pad
        if x + tw > width:
            break
    y0 = pad + th + 70
    lx = 150
    sc = (width - lx - pad) / max(dur, 1e-6)
    gcol = [(200, 200, 200), (120, 200, 255), (255, 200, 120), (180, 255, 160), (255, 160, 200)]
    for i, g in enumerate(speaker_ids):
        y = y0 + i * rows_h
        d.text((pad, y + 4), label(g, names)[:14], font=f, fill=gcol[i % len(gcol)])
        for a, b, gg in segs:
            if gg == g:
                d.rectangle([lx + a * sc, y + 6, lx + max(b * sc, a * sc + 1), y + rows_h - 6], fill=gcol[i % len(gcol)])
    y = y0 + len(speaker_ids) * rows_h
    if rez.get("pjesme"):                # red s pjesmama (nastupi.json) iznad programa
        d.text((pad, y + 4), "pjesme", font=f, fill=(245, 183, 0))
        for p in rez["pjesme"]:
            d.rectangle([lx + p["od"] * sc, y + 6, lx + p["do"] * sc - 1, y + rows_h - 6], fill=(245, 183, 0))
            d.text((lx + p["od"] * sc + 6, y + 7), p["id"], font=fb, fill=(24, 24, 28))
        y += rows_h
    d.text((pad, y + 4), "program", font=fb, fill=(255, 255, 255))
    for s in rez["kadrovi"]:
        c = col.get(s["kamera"], (0, 0, 0))
        d.rectangle([lx + s["od"] * sc, y + 2, lx + s["do"] * sc - 1, y + rows_h - 2], fill=c)
        if s["zasto"] == RAZLOZI[R_UMETAK]:
            d.rectangle([lx + s["od"] * sc, y + rows_h - 6, lx + s["do"] * sc - 1, y + rows_h - 2], fill=(255, 255, 255))
    step = 10 if dur <= 120 else 60 if dur <= 900 else 300
    for t in np.arange(0, dur + 1e-6, step):
        xx = lx + t * sc
        d.line([xx, y + rows_h + 2, xx, y + rows_h + 10], fill=(160, 160, 160))
        d.text((xx - 14, y + rows_h + 12), fmt_time(t), font=f, fill=(160, 160, 160))
    img.save(path)
    return path


# ---------------------------------------------------------------- glavno

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt", help="mapa projekta sa sinkro.json")
    ap.add_argument("--kamere", help='ručno: "kamera1.mp4=Marko,kamera2.mp4=G2,kamera3.mp4=siroki"')
    ap.add_argument("--umetci", choices=list(UMETCI), default=None,
                    help="široki kadar usred dugog monologa (zadano: povremeno = svakih 30 s)")
    ap.add_argument("--min-kadar", type=float, default=None, help=f"najkraći kadar u s (zadano {MIN_KADAR})")
    ap.add_argument("--pjesma-kadar", type=float, default=None,
                    help=f"prosječni kadar za vrijeme pjesme u s (zadano {PJESMA_KADAR:g}; 0 = cijela pjesma u širokom)")
    ap.add_argument("--format", choices=list(FORMATS), default=None, help="zadano 16:9")
    ap.add_argument("--fps", type=int, default=None, help="zadano 30")
    ap.add_argument("--analiza", action="store_true", help="samo rezija.json/.txt/.png, bez videa")
    a = ap.parse_args()

    proj = Path(a.projekt)
    data, cams, master = load_sync(proj)
    pocetak, dur = span(cams, master)
    pj_path = proj / "project.json"
    pj = load_json(pj_path) if pj_path.exists() else {}
    old_p = (pj.get("podcast") or {}).get("pocetak")
    if old_p is not None and abs(old_p - pocetak) > 0.01 and (proj / "transcript.json").exists():
        print(f"Upozorenje: epizoda sad počinje na {pocetak:.2f} s umjesto {old_p:.2f} s glavnog izvora "
              "(nova sinkronizacija?) — ponovno pokreni transcribe.py i govornici.py nakon ove režije.")
    rp = proj / "rezija.json"
    old = load_json(rp) if rp.exists() else {}
    umetci = a.umetci or old.get("umetci") or "povremeno"
    min_kadar = a.min_kadar or old.get("min_kadar") or MIN_KADAR
    pjesma_kadar = a.pjesma_kadar if a.pjesma_kadar is not None else old.get("pjesma_kadar", PJESMA_KADAR)
    if pjesma_kadar and pjesma_kadar < PJESMA_MIN:
        die(f"--pjesma-kadar: najmanje {PJESMA_MIN:g} s (ili 0 = cijela pjesma u širokom kadru)")
    fmt = a.format or pj.get("format") or "16:9"
    W, H = FORMATS[fmt]
    fps = a.fps or int(pj.get("fps") or 30)

    segs, names = speakers(proj)
    segs = [(max(0.0, x), min(dur, y), g) for x, y, g in segs if y > 0 and x < dur]
    manual = dict(old.get("rucno") or {})
    for k, v in parse_manual(a.kamere, cams, names).items():
        manual[k] = list(v)

    print(f"Epizoda: {fmt_time(dur)} (od {pocetak:.2f} s glavnog izvora), kamera {len(cams)}, "
          f"govornika {len({g for *_, g in segs})}" + ("" if segs else " (još nema govornici.json)"))
    print("Tražim tko je na kojoj kameri…")
    roles = []
    for e in cams:
        if e["ime"] in manual:
            u, g = manual[e["ime"]]
            r = {"ime": e["ime"], "uloga": u, "govornik": g, "osobe": [], "rucno": True}
            r["od"], r["do"] = [round(v, 3) for v in cam_range(e, pocetak, dur)]
            if u == "krupni":
                auto = analyse_camera(e, segs, pocetak, dur, log=lambda *_: None)
                r["osobe"], r["lice_y"] = auto["osobe"][:1], auto["lice_y"]
            print(f"  {e['ime']}: ručno → {u}" + (f" {g}" if g else ""))
        else:
            r = analyse_camera(e, segs, pocetak, dur)
        r["crop_x"], r["crop_y"] = crop_for_role(r, e, W, H)
        roles.append(r)

    warn = []
    speaker_ids = sorted({g for *_, g in segs}, key=lambda g: (len(g), g))
    for r in roles:
        if r["uloga"] == "krupni" and not r["govornik"] and segs:
            warn.append(f"{r['ime']}: krupni kadar, ali ne znam čiji — upiši npr. --kamere \"{r['ime']}=G1\"")
    for g in speaker_ids:
        if not any(r["uloga"] == "krupni" and r["govornik"] == g for r in roles):
            warn.append(f"{label(g, names)} nema svoju kameru → dok govori, široki kadar")
    if not any(r["uloga"] == "siroki" for r in roles):
        warn.append("nema širokog kadra: kad pričaju svi, ostaje kadar onoga tko je počeo; umetci su reakcije drugoga")
    if not segs:
        warn.append("još nema govornici.json: cijela epizoda je u širokom kadru. Sljedeće: transcribe.py i "
                    "govornici.py na ovom projektu, pa ponovno rezija.py")

    songs = load_songs(proj, master, pocetak, dur)
    shots = direct(segs, cams, roles, pocetak, dur, names, umetci, min_kadar, songs, pjesma_kadar)
    rez = {"shofe": version(), "pocetak": pocetak, "trajanje": dur, "format": fmt, "fps": fps,
           "umetci": umetci, "min_kadar": min_kadar, "pjesma_kadar": pjesma_kadar, "rucno": manual,
           "kamere": roles, "kadrovi": shots, "upozorenja": warn}
    if songs:
        rez["pjesme"] = song_summary(songs, shots)
        if not any(r["uloga"] == "siroki" for r in roles):
            warn.append("nema širokog kadra: za vrijeme pjesme kamere se izmjenjuju redom")
    rez["statistika"] = stats(shots, outside_songs(segs, songs) if songs else segs, roles, names)
    save_json(rp, rez)
    (proj / "rezija.txt").write_text(summary(rez, names), encoding="utf-8")
    draw_png(proj, rez, cams, segs, names, proj / "rezija.png")
    print()
    txt = summary(rez, names)
    print(txt.split("\nKadrovi:")[0])
    print(f"Svi kadrovi ({len(shots)}) u rezija.txt, slika rezija.png")

    if a.analiza:
        print(f"\nGotovo (samo analiza): {rp}")
        return
    print(f"\nSlažem program ({len(shots)} kadrova, {W}x{H}, {fps} fps)…")
    render_program(proj, shots, cams, roles, master, pocetak, dur, W, H, fps)
    pj.update({"format": fmt, "width": W, "height": H, "fps": fps, "duration": round(dur, 3), "clips": [],
               "podcast": {"rezija": "rezija.json", "pocetak": pocetak, "glavni": master["ime"]}})
    save_json(pj_path, pj)
    print(f"\nGotovo: {proj / 'source.mp4'} ({fmt_time(dur)}) — kamera prati govornika, zvuk glavnog izvora.")
    if not segs:
        print(f"Sljedeće: python transcribe.py {proj}  →  python govornici.py {proj}  →  python rezija.py {proj}")
    else:
        print(f"Sljedeće: pogledaj rezija.png i source.mp4; dalje kao svaki projekt (plan.py, render.py, isjecci.py).")


if __name__ == "__main__":
    main()
