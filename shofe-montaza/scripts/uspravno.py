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
    return {"proj": proj, "pj": pj, "cams": cams, "roles": roles, "names": names,
            "pocetak": float(rez.get("pocetak", pj["podcast"].get("pocetak", 0.0))),
            "trajanje": float(rez.get("trajanje", pj["duration"])), "segs": segs,
            "lica": izvori_lica(roles, segs)}


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
    segs = [(max(0.0, a - od), min(do - od, b - od), g) for a, b, g in ctx["segs"] if b > od and a < do]
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
    # spoji susjedne iste
    merged = []
    for s in out:
        if merged and merged[-1]["dijelovi"] == s["dijelovi"]:
            merged[-1]["do"] = s["do"]
        else:
            merged.append(s)
    return merged


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
    return [dict(s, dijelovi=[{"kamera": ctx["cams"][p[0]]["ime"], "govornik": p[1], "x": p[2], "y": p[3],
                               "lice": p[4]} for p in s["dijelovi"]]) for s in shots]


def sazetak(shots):
    n = {"jedan": 0, "dvoje": 0, "siroki": 0, "crno": 0}
    for s in shots:
        n[s["raspored"]] += 1
    bits = [f"{n['jedan']} × lice govornika"]
    if n["dvoje"]:
        bits.append(f"{n['dvoje']} × podijeljen kadar")
    if n["siroki"]:
        bits.append(f"{n['siroki']} × sredina kamere (nitko s licem)")
    if n["crno"]:
        bits.append(f"{n['crno']} × crno (nijedna kamera ne snima)")
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
