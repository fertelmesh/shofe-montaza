"""Podcast (M4.2b2): uspravni isječci (9:16) iz ORIGINALNIH kamera, ne iz 16:9 programa.

  python uspravno.py podcast_projekt              popis kadrova 9:16 za odobrene isječke (bez rendera)
  python uspravno.py podcast_projekt K1,K3        isto za navedene isječke
  (render: python isjecci.py podcast_projekt render  → kod podcasta isječci su zadano 9:16 iz ovog modula)

Program epizode (rezija.py) je 16:9: široki kadar s dvoje ljudi izrezan na 9:16 ne pokazuje nikoga dobro.
Zato uspravni isječak ima svoju režiju (kao Opus Clip, Riverside, Descript; vidi ODLUKE.md):
- govori jedan → cijeli kadar je njegovo lice: iz njegove krupne kamere (najbolja kvaliteta), a ako je nema
  (ili ne snima), izrez iz širokog kadra oko njegova lica (kadar.py po govorniku, uz blagi zum);
- pričaju u isti glas ili se brzo izmjenjuju → podijeljen kadar: gore jedan, dolje drugi (svaki iz svoje kamere);
- gost bez kamere i izvan kadra → podijeljen kadar onih koji slušaju (reakcije);
- tišina → kadar ostaje; kadar traje barem MIN_KADAR s; umetaka širokog kadra nema (isječak je kratak).
Za vrijeme pjesme (nastupi.json, M4.3b4) govornici se ne prate (pjevanje nije govor): kadrovi idu u ritmu kao u
programu (rezija.song_plan) — počne i završi bend u širokom kadru, između krupni kadrovi redom, rez na početku
takta, prosječno USPRAVNO_PJESMA × kadar pjesme iz režije (isječak je kratak, za mreže). Bend iz širokog kadra:
ako cijela skupina stane u izrez 9:16, izrez oko skupine; inače slika skalirana tako da cijela skupina stane u
širinu, a iznad i ispod ista kamera zamućena i potamnjena (raspored „bend", kao „Fit" s mutnom pozadinom).
Izvor isječka (`isjecci/izvor_9x16/K1.mp4`) sadrži samo vrijeme isječka (± 1 s) sa zvukom programa;
render.py ga čita s pomakom pa vrijede isti transkript, rezovi i titlovi kao za 16:9.
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np

import kadar as K
import rezija as R
import sinkro as S
from common import FORMATS, die, ffmpeg, fmt_time, load_json, run, save_json, video_info

W9, H9 = FORMATS["9:16"]
MIN_KADAR = 2.0                             # s
RUB = 1.0                                   # s izvora prije i poslije isječka
LICE_SIRINA = {"jedan": 0.30, "dvoje": 0.26}  # koliki dio širine kadra zauzima lice (ako se smije zumirati)
LICE_Y = {"jedan": 0.36, "dvoje": 0.42}     # gdje je lice po visini kadra (ostatak za titlove)
MAX_ZUM = 1.6                               # najviše toliko preko „popuni kadar" (dalje je slika mutna)
CRF = 18
RAZMAK = 6                                  # px tamne crte između gornjeg i donjeg dijela
USPRAVNO_PJESMA = 0.75                      # × kadar pjesme iz rezija.json (8 s → 6 s): isječak za mreže je brži
BEND_RUB = 1.2                              # × najšire lice, lijevo i desno od skupine (ramena, instrumenti)
BEND_POPUNA = 0.96                          # skupina zauzme toliko širine kadra
BEND_Y = 0.45                               # središte slike benda po visini kadra
BEND_MUTNO = 4                              # mutna pozadina se računa na 1/4 veličine (brže), pa poveća


class Greska(Exception):
    pass


# ---------------------------------------------------------------- ulaz

def je_podcast(pj):
    return bool(pj.get("podcast")) and pj.get("width", 0) > pj.get("height", 0)


def ucitaj(proj):
    """Kontekst podcasta: kamere, glavni izvor, režija, govornici. Greska ako nešto nedostaje."""
    proj = Path(proj)
    pj = load_json(proj / "project.json")
    if not pj.get("podcast"):
        raise Greska("projekt nije podcast (nema rezija.py)")
    for f in ("sinkro.json", "rezija.json"):
        if not (proj / f).exists():
            raise Greska(f"nema {f}")
    sync, rez = load_json(proj / "sinkro.json"), load_json(proj / "rezija.json")
    src = {e["ime"]: e for e in sync["izvori"]}
    cams, roles = [], []
    for r in rez.get("kamere", []):
        e = src.get(r["ime"])
        if not e or e.get("vrsta") != "video" or not e.get("pronaden", True):
            continue
        if not Path(e["datoteka"]).exists():
            raise Greska(f"originalna snimka ne postoji: {Path(e['datoteka']).name}")
        info = video_info(e["datoteka"])            # s okretom mobitela
        cams.append(dict(e, w=info["w"], h=info["h"]))
        roles.append(r)
    if not cams:
        raise Greska("u rezija.json nema nijedne kamere")
    segs, names = R.speakers(proj)
    pocetak = float(rez.get("pocetak", pj["podcast"].get("pocetak", 0.0)))
    trajanje = float(rez.get("trajanje", pj["duration"]))
    return {"proj": proj, "pj": pj, "cams": cams, "roles": roles, "names": names,
            "pocetak": pocetak, "trajanje": trajanje, "segs": segs,
            "lica": izvori_lica(roles, segs),
            "pjesme": pjesme(proj, rez, sync, pocetak, trajanje),
            "pjesma_kadar": float(rez.get("pjesma_kadar", R.PJESMA_KADAR))}


def pjesme(proj, rez, sync, pocetak, trajanje):
    """Pjesme iz nastupi.json (vrijeme programa) s udarcima: iz rezija.json, a ako ih tamo nema (stara režija ili
    pjesma dodana nakon režije) iz zvuka glavnog izvora (ritam.py). [{id, od, do, naziv, udarci}]"""
    import nastupi
    act = nastupi.active(nastupi.load(proj))
    if not act:
        return []
    known = {p["id"]: p for p in rez.get("pjesme") or []}
    out, missing = [], False
    for n in act:
        od, do = max(0.0, float(n["od"])), min(trajanje, float(n["do"]))
        if do - od < 1:
            continue
        k = known.get(n["id"])
        same = k is not None and abs(k["od"] - od) < 0.05 and abs(k["do"] - do) < 0.05 and "udarci" in k
        out.append({"id": n["id"], "od": od, "do": do, "naziv": n.get("naziv") or "",
                    "udarci": list(k["udarci"]) if same else None})
        missing |= not same
    if missing:
        master = next((e for e in sync["izvori"] if e.get("glavni")), None)
        got = {}
        if master and Path(master["datoteka"]).exists():
            try:
                got = {s["id"]: s["udarci"] for s in R.load_songs(proj, master, pocetak, trajanje, log=None)}
            except Exception:  # noqa: BLE001  (bez ritma: rez po sekundama)
                got = {}
        for s in out:
            if s["udarci"] is None:
                s["udarci"] = got.get(s["id"], [])
    return out


def izvori_lica(roles, segs):
    """{govornik: [{kam, x, y, w, vrsta}]}: najprije krupne kamere (najveće lice), zatim široki kadrovi."""
    ids = sorted({g for *_, g in segs}, key=lambda g: (len(g), g))
    out = {g: [] for g in ids}
    for i, r in enumerate(roles):
        y = r.get("lice_y") if r.get("lice_y") is not None else 0.42
        for o in r.get("osobe") or []:
            g = o.get("govornik") or (r.get("govornik") if r["uloga"] == "krupni" else None)
            if g in out and r["uloga"] in ("krupni", "siroki"):
                out[g].append({"kam": i, "x": o["x"], "y": y, "w": o.get("w"), "vrsta": r["uloga"]})
        if r["uloga"] == "krupni" and r.get("govornik") in out and not r.get("osobe"):
            out[r["govornik"]].append({"kam": i, "x": r.get("crop_x", 0.5), "y": y, "w": None, "vrsta": "krupni"})
    for g in out:
        out[g].sort(key=lambda s: (s["vrsta"] != "krupni", -(s["w"] or 0)))
    return out


# ---------------------------------------------------------------- režija 9:16

def rezija(ctx, od, do, min_kadar=MIN_KADAR):
    """Kadrovi 9:16 od `od` do `do` (vrijeme programa): [{od, do, raspored, dijelovi: [{kamera, govornik, x, y,
    w}], zasto}]. raspored: jedan | dvoje | siroki (nitko nema lice: sredina kamere) | crno."""
    KO = R.KORAK
    n = max(1, int(math.ceil((do - od) / KO - 1e-9)))
    songs = [p for p in ctx.get("pjesme") or [] if p["do"] > od + 1e-6 and p["od"] < do - 1e-6]
    src_segs = R.outside_songs(ctx["segs"], songs) if songs else ctx["segs"]   # pjevanje nije govor
    segs = [(max(0.0, a - od), min(do - od, b - od), g) for a, b, g in src_segs if b > od and a < do]
    lica = ctx["lica"]
    ids = sorted(lica, key=lambda g: (len(g), g))
    has = {g: bool(lica[g]) for g in ids}
    s_ids = sorted({g for *_, g in segs}, key=lambda g: (len(g), g))
    lab, why, act = R.desired(segs, n, s_ids, has) if s_ids else (np.zeros(n, int), np.full(n, R.R_POCETAK), None)
    talk = {g: float(sum(b - a for a, b, gg in segs if gg == g)) for g in ids}
    visible = sorted([g for g in ids if has[g]], key=lambda g: -talk[g])

    keys = [None] * n
    k = 0
    while k < n:
        e = k
        while e < n and lab[e] == lab[k] and why[e] == why[k]:
            e += 1
        w = int(why[k])
        key = None
        if lab[k] > 0:
            key = ("jedan", s_ids[lab[k] - 1])
        elif w in (R.R_PREKLOP, R.R_IZMJENA):
            cnt = act[:, k:e].sum(axis=1)
            who = [s_ids[i] for i in np.argsort(-cnt) if cnt[i] > 0 and has[s_ids[i]]][:2]
            if len(who) == 2:
                key = ("dvoje", *sorted(who, key=lambda g: (len(g), g)))
            elif who:
                key = ("jedan", who[0])
        elif w == R.R_BEZ_KAMERE:
            if len(visible) >= 2:
                key = ("dvoje", *sorted(visible[:2], key=lambda g: (len(g), g)))
            elif visible:
                key = ("jedan", visible[0])
        keys[k:e] = [key] * (e - k)
        k = e
    # tišina i početak: drži prethodni kadar; na početku prvi koji slijedi
    first = next((x for x in keys if x), None) or (("jedan", visible[0]) if visible else ("siroki",))
    cur = first
    for i in range(n):
        if keys[i] is None:
            keys[i] = cur
        else:
            cur = keys[i]

    codes = {}
    arr = np.array([codes.setdefault(x, len(codes)) for x in keys])
    inv = {v: x for x, v in codes.items()}
    runs = K.shots(arr, min_len=int(round(min_kadar / KO)))

    out = []
    for a, b, c in runs:
        key = inv[c]
        # izvor po sličici (kamera mora snimati); dijeli kadar gdje se izvor promijeni
        pieces, k = [], a
        while k < b:
            parts = choose(ctx, key, od + k * KO)
            e = k + 1
            while e < b and choose(ctx, key, od + e * KO) == parts:
                e += 1
            pieces.append((k, e, parts))
            k = e
        if len(pieces) > 1 and min(e - k for k, e, _ in pieces) * KO < min_kadar:
            # kamera se gasi/pali usred kadra i ostao bi komadić: cijeli kadar iz izvora koji snima cijelo vrijeme
            full = choose(ctx, key, od + a * KO, od + (b - 1) * KO)
            if full and len(full) == max(len(p[2]) for p in pieces):
                pieces = [(a, b, full)]
        for k, e, parts in pieces:
            out.append({"od": round(od + k * KO, 3), "do": round(min(do, od + e * KO), 3), "dijelovi": parts,
                        "raspored": rasp(parts), "zasto": opis(key, parts, ctx["names"])})
    for p in songs:
        out = umetni_pjesmu(ctx, out, p, od, do, min_kadar)
    # spoji susjedne iste
    merged = []
    for s in out:
        if merged and merged[-1]["dijelovi"] == s["dijelovi"] and merged[-1].get("pjesma") == s.get("pjesma") \
                and merged[-1]["raspored"] == s["raspored"]:
            merged[-1]["do"] = s["do"]
        else:
            merged.append(s)
    return merged


# ---------------------------------------------------------------- pjesma (M4.3b4)

def pokrivenost(ctx):
    """cov[kamera, k]: kamera snima sličicu programa k · KORAK (kao rezija.choose_cameras)."""
    KO = R.KORAK
    n = int(math.ceil(ctx["trajanje"] / KO - 1e-9)) + 1
    t = ctx["pocetak"] + np.arange(n) * KO
    return np.array([(t >= e["od"] - 1e-6) & (t <= e["do"] - KO + 1e-6) for e in ctx["cams"]])


def dio_pjesme(ctx, i):
    """Kamera i za vrijeme pjesme → (dio, raspored). Krupni kadar: lice te osobe (raspored jedan). Široki: cijela
    skupina (bend) — izrez oko skupine ako stane u 9:16, inače raspored bend (cijela skupina u širini, mutna
    pozadina). Kamera bez lica: sredina."""
    r, cam = ctx["roles"][i], ctx["cams"][i]
    if r["uloga"] == "krupni":
        g = r.get("govornik")
        s = next((s for s in ctx["lica"].get(g, []) if s["kam"] == i), None) if g else None
        if s:
            return (i, g, s["x"], s["y"], s["w"]), "jedan"
        return (i, None, float(r.get("crop_x", 0.5)), 0.42, None), "siroki"
    if r["uloga"] != "siroki":
        return (i, None, 0.5, 0.42, None), "siroki"
    os_ = r.get("osobe") or []
    y = r.get("lice_y") if r.get("lice_y") is not None else 0.42
    if os_:
        m = BEND_RUB * max(float(o.get("w") or 0.1) for o in os_)
        lo = max(0.0, min(o["x"] - (o.get("w") or 0.1) / 2 for o in os_) - m)
        hi = min(1.0, max(o["x"] + (o.get("w") or 0.1) / 2 for o in os_) + m)
    else:
        lo, hi = 0.0, 1.0
    part = (i, None, round((lo + hi) / 2, 4), y, round(hi - lo, 4))
    if geometrija_bend(cam, part) is None:          # skupina stane u izrez 9:16
        return (i, None, part[2], y, None), "siroki"
    return part, "bend"


def kadrovi_pjesme(ctx, p, a, b):
    """Kadrovi 9:16 za dio pjesme p od a do b (vrijeme programa), u ritmu: rezija.song_plan na granicama
    isječka (počne i završi bend), kadar USPRAVNO_PJESMA × kadar pjesme, rez točno na udarcu."""
    KO = R.KORAK
    k = ctx.get("pjesma_kadar", R.PJESMA_KADAR)
    kadar = 0.0 if not k else max(R.PJESMA_MIN, k * USPRAVNO_PJESMA)
    song = {"id": p["id"], "od": a, "do": b, "udarci": p.get("udarci") or []}
    plan, per = R.song_plan(song, ctx["cams"], ctx["roles"], pokrivenost(ctx), kadar)
    exact = [a, b] + song.get("_rezovi", [])
    tm = lambda x: min(exact, key=lambda v: abs(v - x * KO)) if min(abs(v - x * KO) for v in exact) <= KO / 2 + 1e-6 \
        else x * KO  # noqa: E731
    out = []
    for x, y, c in plan:
        t0, t1 = max(a, tm(x)), min(b, tm(y))
        if t1 - t0 < 1e-3:
            continue
        part, r = dio_pjesme(ctx, c)
        kto = "bend" if r == "bend" or (r == "siroki" and ctx["roles"][c]["uloga"] == "siroki") \
            else R.label(part[1], ctx["names"]) if part[1] else ctx["cams"][c]["ime"]
        out.append({"od": round(t0, 3), "do": round(t1, 3), "dijelovi": (part,), "raspored": r,
                    "zasto": f"pjesma {p['id']}: {kto}", "pjesma": p["id"]})
    if out:
        out[0]["od"], out[-1]["do"] = round(a, 3), round(b, 3)
        if per:
            out[0]["takt"] = per
    return out


def umetni_pjesmu(ctx, shots, p, od, do, min_kadar):
    """Kadrove govora u vremenu pjesme zamijeni kadrovima pjesme; komadić govora uz pjesmu kraći od najkraćeg
    kadra preuzme susjedni kadar pjesme (kao rezija.fix_song_edges)."""
    a, b = max(od, p["od"]), min(do, p["do"])
    song = kadrovi_pjesme(ctx, p, a, b)
    if not song:
        return shots
    before = [dict(s, do=min(s["do"], a)) for s in shots if s["od"] < a - 1e-6]
    after = [dict(s, od=max(s["od"], b)) for s in shots if s["do"] > b + 1e-6]
    if before and before[-1]["do"] - before[-1]["od"] < min_kadar - 1e-6 and not before[-1].get("pjesma"):
        song[0]["od"] = before.pop()["od"]
    if after and after[0]["do"] - after[0]["od"] < min_kadar - 1e-6 and not after[0].get("pjesma"):
        song[-1]["do"] = after.pop(0)["do"]
    return before + song + after


def covering(ctx, i, t):
    e = ctx["cams"][i]
    tt = ctx["pocetak"] + t
    return e["od"] - 1e-6 <= tt <= e["do"] - R.KORAK + 1e-6


def choose(ctx, key, t, t_do=None):
    """Ključ rasporeda + trenutak (ili cijeli raspon t…t_do) → popis dijelova (n-torke, da se mogu uspoređivati)."""
    def cov(i):
        return covering(ctx, i, t) and (t_do is None or covering(ctx, i, t_do))

    def src(g):
        s = next((s for s in ctx["lica"].get(g, []) if cov(s["kam"])), None)
        return None if s is None else (s["kam"], g, s["x"], s["y"], s["w"])
    if key[0] == "jedan":
        p = src(key[1])
        if p:
            return (p,)
    elif key[0] == "dvoje":
        ps = [p for p in (src(key[1]), src(key[2])) if p]
        if ps:
            return tuple(ps)
    # nitko iz ključa nema kameru koja snima: netko drugi s licem, inače sredina bilo koje kamere
    for g in ctx["lica"]:
        p = src(g)
        if p:
            return (p,)
    order = sorted(range(len(ctx["cams"])), key=lambda i: ctx["roles"][i]["uloga"] != "siroki")
    i = next((i for i in order if cov(i)), None)
    return () if i is None else ((i, None, 0.5, 0.42, None),)


def rasp(parts):
    if not parts:
        return "crno"
    if len(parts) == 2:
        return "dvoje"
    return "jedan" if parts[0][1] else "siroki"


def opis(key, parts, names):
    lab = lambda g: R.label(g, names)  # noqa: E731
    if not parts:
        return "nijedna kamera ne snima"
    if len(parts) == 2:
        return "dvoje: " + " / ".join(lab(p[1]) for p in parts)
    if parts[0][1] is None:
        return "nitko s licem — sredina kamere"
    txt = lab(parts[0][1])
    if key[0] == "dvoje":
        txt += " (drugi nema kameru koja snima)"
    return txt


# ---------------------------------------------------------------- slika

def geometrija(cam, part, Wt, Ht, rasp_):
    """→ (sw, sh, x, y): skaliraj snimku na sw×sh i izreži Wt×Ht od (x, y) tako da je lice dobro postavljeno."""
    _, g, fx, fy, fw = part
    w0, h0 = cam["w"], cam["h"]
    s0 = max(Wt / w0, Ht / h0)
    s = s0
    if fw:
        s = float(np.clip(LICE_SIRINA[rasp_] * Wt / (fw * w0), s0, s0 * MAX_ZUM))
    sw = max(Wt, int(math.ceil(w0 * s / 2)) * 2)
    sh = max(Ht, int(math.ceil(h0 * s / 2)) * 2)
    x = int(round(np.clip(fx * sw - Wt / 2, 0, sw - Wt)))
    y = int(round(np.clip(fy * sh - LICE_Y[rasp_] * Ht, 0, sh - Ht))) if g else int(round((sh - Ht) * 0.4))
    return sw, sh, x, y


def geometrija_bend(cam, part, W=W9, H=H9):
    """Bend iz širokog kadra → (sw, sh, x, oy) ili None ako skupina stane u običan izrez 9:16 (popuni kadar).
    Snimka skalirana na sw×sh (sh < H) tako da skupina (dio[4] = širina skupine, 0–1) zauzme BEND_POPUNA širine,
    izrez W×sh od x oko središta skupine, na kadru od visine oy; iznad i ispod mutna pozadina."""
    _, _, fx, _, span = part
    w0, h0 = cam["w"], cam["h"]
    s_fill = max(W / w0, H / h0)
    s = max(W / w0, BEND_POPUNA * W / (max(0.05, span or 1.0) * w0))
    if s >= s_fill - 1e-9:
        return None
    sw = max(W, int(math.ceil(w0 * s / 2)) * 2)
    sh = min(H, int(math.ceil(h0 * s / 2)) * 2)
    x = int(round(np.clip(fx * sw - W / 2, 0, sw - W)))
    oy = int(round(np.clip(BEND_Y * H - sh / 2, 0, H - sh))) // 2 * 2
    return sw, sh, x, oy


def pozadina_bend(cam, part, W=W9, H=H9):
    """Dio za mutnu pozadinu benda: ista kamera, običan izrez 9:16 (popuni kadar) oko središta skupine."""
    return (part[0], None, part[2], part[3], None)


def vf_bend(cam, part, fps, W=W9, H=H9):
    """filter_complex za raspored bend iz ulaza [0:v] → [v]."""
    sw, sh, x, oy = geometrija_bend(cam, part, W, H)
    bw, bh, bx, by = geometrija(cam, pozadina_bend(cam, part, W, H), W, H, "jedan")
    q = BEND_MUTNO
    ev = lambda v: max(2, int(round(v / q / 2)) * 2)  # noqa: E731
    return (f"[0:v]split=2[b0][f0];"
            f"[b0]scale={ev(bw)}:{ev(bh)},crop={ev(W)}:{ev(H)}:{min(bx // q, ev(bw) - ev(W))}:"
            f"{min(by // q, ev(bh) - ev(H))},gblur=sigma=10,"
            f"eq=brightness=-0.10:saturation=0.8,scale={W}:{H}[bg];"
            f"[f0]scale={sw}:{sh}:flags=lanczos,crop={W}:{sh}:{x}:0[fg];"
            f"[bg][fg]overlay=0:{oy},fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration=2,format=yuv420p[v]")


def vf_dio(cam, part, Wt, Ht, rasp_, fps):
    sw, sh, x, y = geometrija(cam, part, Wt, Ht, rasp_)
    return (f"scale={sw}:{sh}:flags=lanczos,crop={Wt}:{Ht}:{x}:{y},fps={fps},setsar=1,"
            f"tpad=stop_mode=clone:stop_duration=2")


def pripremi(ctx, c, dst, fps=30, log=None):
    """Izvor 9:16 za isječak c ({od, do}) → {"datoteka", "pomak", "W", "H", "kadrovi"}.
    Video traje od `pomak` do kraja isječka + RUB (vrijeme programa); zvuk je zvuk programa (source.mp4)."""
    proj = ctx["proj"]
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = math.floor(max(0.0, float(c["od"]) - RUB) * fps) / fps
    t1 = min(ctx["trajanje"], float(c["do"]) + RUB)
    shots = rezija(ctx, t0, t1)
    tmp = proj / "_tmp" / "uspravno"
    tmp.mkdir(parents=True, exist_ok=True)
    for old in tmp.glob("u_*.mp4"):
        old.unlink()
    parts = []
    for i, s in enumerate(shots):
        f0, f1 = round((s["od"] - t0) * fps), round((s["do"] - t0) * fps)
        if f1 <= f0:
            continue
        name = f"u_{i:04d}.mp4"
        out = ["-frames:v", str(f1 - f0), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF),
               "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", name]
        ins, fc = [], []
        if not s["dijelovi"]:
            cmd = [ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={W9}x{H9}:r={fps}", *out]
        elif s["raspored"] == "bend":
            p = s["dijelovi"][0]
            e = ctx["cams"][p[0]]
            ts = S.to_source(e, ctx["pocetak"] + t0 + f0 / fps)
            cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, ts):.4f}", "-i", Path(e["datoteka"]).resolve(),
                   "-filter_complex", vf_bend(e, p, fps), "-map", "[v]", *out]
        else:
            Ht = H9 if len(s["dijelovi"]) == 1 else H9 // 2
            r = "dvoje" if len(s["dijelovi"]) == 2 else "jedan"
            for j, p in enumerate(s["dijelovi"]):
                e = ctx["cams"][p[0]]
                ts = S.to_source(e, ctx["pocetak"] + t0 + f0 / fps)
                ins += ["-ss", f"{max(0.0, ts):.4f}", "-i", Path(e["datoteka"]).resolve()]
                fc.append(f"[{j}:v]{vf_dio(e, p, W9, Ht, r, fps)}[d{j}]")
            if len(s["dijelovi"]) == 2:
                fc.append(f"[d0][d1]vstack=inputs=2,drawbox=x=0:y={Ht - RAZMAK // 2}:w={W9}:h={RAZMAK}"
                          f":color=0x111111:t=fill,format=yuv420p[v]")
            else:
                fc.append("[d0]format=yuv420p[v]")
            cmd = [ffmpeg(), "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", "[v]", *out]
        run(cmd, cwd=tmp)
        parts.append(name)
    lst = tmp / "lista.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "slika.mp4"],
        cwd=tmp)
    run([ffmpeg(), "-y", "-v", "error", "-i", "slika.mp4", "-ss", f"{t0:.4f}", "-t", f"{t1 - t0:.3f}",
         "-i", (proj / "source.mp4").resolve(), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{t1 - t0:.3f}", "-movflags", "+faststart",
         dst.resolve()], cwd=tmp)
    info = {"datoteka": dst, "pomak": t0, "W": W9, "H": H9, "kadrovi": shots}
    save_json(dst.with_suffix(".json"), {"pomak": t0, "do": round(t1, 3), "kadrovi": za_json(ctx, shots)})
    return info


# ---------------------------------------------------------------- ispis

def za_json(ctx, shots):
    def dio(p, r):
        d = {"kamera": ctx["cams"][p[0]]["ime"], "govornik": p[1], "x": p[2], "y": p[3]}
        d["skupina" if r == "bend" else "lice"] = p[4]          # bend: širina skupine, inače širina lica
        return d
    return [dict(s, dijelovi=[dio(p, s["raspored"]) for p in s["dijelovi"]]) for s in shots]


def sazetak(shots):
    n = {"jedan": 0, "dvoje": 0, "siroki": 0, "crno": 0, "bend": 0}
    pj = [s for s in shots if s.get("pjesma")]
    for s in shots:
        if not s.get("pjesma"):
            n[s["raspored"]] += 1
    bits = [f"{n['jedan']} × lice govornika"] if len(pj) < len(shots) else []
    if n["dvoje"]:
        bits.append(f"{n['dvoje']} × podijeljen kadar")
    if n["siroki"]:
        bits.append(f"{n['siroki']} × sredina kamere (nitko s licem)")
    if n["crno"]:
        bits.append(f"{n['crno']} × crno (nijedna kamera ne snima)")
    if pj:
        nb = sum(s["raspored"] in ("bend", "siroki") for s in pj)
        takt = next((s["takt"] for s in pj if s.get("takt")), None)
        bits.append(f"{len(pj)} u pjesmi ({nb} × bend, {len(pj) - nb} × krupno"
                    + (", rez na početku takta)" if takt else ", rez po sekundama)"))
    return f"{len(shots)} kadrova 9:16: " + ", ".join(bits)


def popis(ctx, shots):
    cams = ctx["cams"]
    lines = [sazetak(shots)]
    for s in shots:
        src = " + ".join(f"{cams[p[0]]['ime']}" for p in s["dijelovi"]) or "—"
        lines.append(f"  {fmt_time(s['od'])}–{fmt_time(s['do'])}  {s['raspored']:6s} {s['zasto']}  [{src}]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("projekt")
    ap.add_argument("ids", nargs="?", help="isječci, npr. K1,K3 (zadano: odobreni)")
    a = ap.parse_args()
    proj = Path(a.projekt)
    try:
        ctx = ucitaj(proj)
    except Greska as e:
        die(f"uspravni isječci podcasta: {e}")
    import isjecci
    import serija
    data = isjecci.load(proj)
    if data is None:
        die(f"nema isjecci.json. Prvo: python isjecci.py {proj} predlozi")
    try:
        cs = serija.odaberi_isjecke(data, a.ids, isjecci.find)
    except (serija.Greska, Exception) as e:  # noqa: BLE001
        die(str(e))
    for c in cs:
        shots = rezija(ctx, float(c["od"]), float(c["do"]))
        print(f"{c['id']} {fmt_time(c['od'])}–{fmt_time(c['do'])}")
        print(popis(ctx, shots))
        print()


if __name__ == "__main__":
    sys.exit(main())
