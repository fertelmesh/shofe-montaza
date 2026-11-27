"""Izvoz u DaVinci Resolve: timeline (FCPXML 1.10) s istim rezovima kao Shofeov video + SRT titlovi.

  python davinci.py shofe_projekt                  verzija koju gledaš → reel_vN.fcpxml (+ reel_vN.srt)
  python davinci.py shofe_projekt --verzija 2      starija verzija
  python davinci.py shofe_projekt --trenutno       iz trenutnog edit.json (bez rendera)
  python davinci.py shofe_projekt --izvor priprema umjesto originalnih snimki koristi source.mp4
  python davinci.py shofe_projekt --ispis          ispiši kadrove (izvorna datoteka, od–do)

render.py ovo radi sam uz svaki video. U DaVinciju (i besplatnom): File > Import > Timeline >
reel_vN.fcpxml, zatim File > Import > Subtitle > reel_vN.srt i povuci titlove na timeline.

Timeline koristi ORIGINALNE snimke (mobitel, kamera) s istim rezovima, kadriranjem (9:16 iz
vodoravne snimke) i zumovima; zvuk i boja ostaju neobrađeni. Glazba ide na zasebnu traku.
Naslov (hook), stil i zumovi upisani su i kao oznake (markeri) da se vidi što je Shofe radio.
Ako originalna snimka više ne postoji, cijeli timeline koristi pripremljeni source.mp4.

Podcast (projekt iz rezija.py, M4.2b): V1 = program iz ORIGINALNIH kamera (kadar po kadar iz rezija.json, vrijeme
iz sinkro.json, isti izrez; zvuk kamere isključen), iznad svakog kadra ostale kamere u istom trenutku, svaka na
svojoj traci (lane = 1 + redni broj kamere) i isključene (enabled=0) — u DaVinciju se uključe za ručnu promjenu
kadra; ispod zvuk glavnog izvora (lane −1, uloga dialogue), glazba još niže. Multicam (mc-clip) namjerno ne:
DaVinci ga iz FCPXML-a ne uvozi pouzdano (vidi ODLUKE.md).

Uspravni isječak podcasta (uspravno.py, M4.2b3b): timeline 9:16 iz ORIGINALNIH kamera po kadrovima iz
izvor_9x16/K1.json — kamera govornika s istim izrezom (adjust-transform scale/position), podijeljen kadar kao dva
klipa (gornji na V1, donji na V2, svaki s adjust-crop trim na svoju polovicu), Shofeova gotova slika (izvor) na V3
isključena kao rezerva, zvuk glavnog izvora ispod. Bez originala → cijeli timeline iz izvor_9x16/K1.mp4.
Bend za vrijeme pjesme (raspored „bend", M4.3b4): široka kamera dvaput — na V1 izrez 9:16 kao pozadina, na V2
cijela skupina u širini (FCPXML nema prenosivo zamućenje, pa je pozadina oštra; Blur se doda u DaVinciju).

Pjesme (nastupi bendova, nastupi.py, M4.3b2): svaka pjesma koja ostaje u videu ima oznaku (marker) cijelom duljinom
„Pjesma P1: naziv", a njezin zvuk ide na vlastitu traku ispod govora (A2, uloga music), pa se u DaVinciju pjesma
obrađuje za glazbu, a govor za govor. Pozadinska glazba tada ide traku niže (A3).

Špice i poglavlja epizode (M4.4d): uvodna špica (spica.py) je klip na glavnoj traci točno tamo gdje je u Shofeovu
videu (kadar na toj točki se podijeli, sve iza se pomakne; glazba i zvuk ispod ne prelaze preko špice), odjavna na
kraju. Markova datoteka ide kao original (cijela slika, Fit), generirana kartica kao spica/<ime>.mov. Poglavlja
(epizoda.py, iste kao u YouTube opisu) su chapter-marker oznake u timelineu, a uz timeline ide i
reel_vN.poglavlja.edl: u DaVinciju desni klik na timeline u Media Poolu > Timelines > Import > Timeline Markers from
EDL → zelene oznake; Deliver > „Chapters from Markers" (boja Green) ih upiše kao poglavlja u MP4/MOV.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path, PureWindowsPath

from common import GRADES, die, ffmpeg, fmt_time, load_json, probe, run

EDL_BOJA = "ResolveColorGreen"   # boja oznaka poglavlja (DaVinci: Deliver > Chapters from Markers > Green)

FCPXML_VERSION = "1.10"   # DaVinci Resolve 18+ uvozi 1.10 (17 samo do 1.8/1.9)
COMMON_RATES = [Fraction(15), Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001), Fraction(30),
                Fraction(48), Fraction(50), Fraction(60000, 1001), Fraction(60), Fraction(100),
                Fraction(120000, 1001), Fraction(120)]
ZOOM_Y = 0.38             # render.zoom_chain kadrira zum na 38 % visine, ne na sredini


# ---------------------------------------------------------------- vrijeme
def ftime(x):
    """Fraction sekundi → FCPXML vrijeme ("1001/30000s", "5s")."""
    x = Fraction(x)
    return f"{x.numerator}s" if x.denominator == 1 else f"{x.numerator}/{x.denominator}s"


def parse_time(s):
    """FCPXML vrijeme → Fraction (za testove i provjeru)."""
    s = s.rstrip("s")
    if "/" in s:
        a, b = s.split("/")
        return Fraction(int(a), int(b))
    return Fraction(s)


def snap_rate(r):
    """Stvarni broj sličica (npr. 2997/100, 30/1, 90000/3001 kod promjenjivog) → uobičajeni (30000/1001)."""
    try:
        r = Fraction(r)
    except (ValueError, ZeroDivisionError):
        return None
    if r <= 0:
        return None
    best = min(COMMON_RATES, key=lambda c: abs(c - r))
    return best if abs(best - r) / best < 0.02 else None


def on_grid(t, fd):
    """Zaokruži vrijeme (sekunde) na najbližu sličicu trajanja fd."""
    return round(Fraction(t) / fd) * fd


# ---------------------------------------------------------------- izvorne datoteke
def file_uri(path):
    """Apsolutna putanja → file:// URI (Windows: file:///C:/Videi/Sun%C4%8Dani%20put/klip.mp4)."""
    s = str(path)
    if re.match(r"^[A-Za-z]:[\\/]", s) or s.startswith("\\\\"):
        return PureWindowsPath(s).as_uri()
    return Path(s).resolve().as_uri()


def parse_tc(tc, rate):
    """Vremenski kod "HH:MM:SS:FF" (ili ; za drop-frame) → Fraction sekundi."""
    m = re.match(r"^(\d+):(\d+):(\d+)[:;.](\d+)$", tc or "")
    if not m or not rate:
        return Fraction(0)
    h, mi, s, f = map(int, m.groups())
    nominal = round(rate)
    frames = ((h * 60 + mi) * 60 + s) * nominal + f
    if ";" in tc and nominal in (30, 60):   # drop-frame: preskače 2 (4) broja svake minute osim desete
        drop = 2 if nominal == 30 else 4
        mins = h * 60 + mi
        frames -= drop * (mins - mins // 10)
    return frames / rate


def media_info(path):
    """Što FCPXML treba znati o izvornoj datoteci: sličice, trajanje, vremenski kod, zvuk."""
    d = probe(path)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        die(f"{path} nema video zapis")
    rate = snap_rate(v.get("avg_frame_rate")) or snap_rate(v.get("r_frame_rate"))
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if "rotate" in (v.get("tags") or {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    tc = (v.get("tags") or {}).get("timecode") or (d["format"].get("tags") or {}).get("timecode")
    if not tc:
        tcs = next((s for s in d["streams"] if (s.get("tags") or {}).get("timecode")), None)
        tc = tcs["tags"]["timecode"] if tcs else None
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    return {"rate": rate, "w": w, "h": h, "dur": dur, "tc": parse_tc(tc, rate) if tc else Fraction(0),
            "audio": a is not None, "channels": int(a.get("channels", 2)) if a else 0,
            "audio_rate": int(a.get("sample_rate", 48000)) if a else 48000}


# ---------------------------------------------------------------- iz edit.json u kadrove
def pieces_for(cuts, clips, fps, use_originals):
    """Rezovi u vremenu source.mp4 → kadrovi po izvornim datotekama.
    Svaki kadar: {clip: indeks ili None (source.mp4), src: od (s, u toj datoteci), frames, out: početak u
    gotovom videu (sličice prije brzine)}. Rez koji prelazi spoj dvaju klipova dijeli se na dva kadra."""
    bounds = []
    if use_originals:
        for k, c in enumerate(clips):
            a = round(c["start"] * fps)
            b = round((c["start"] + c["dur"]) * fps)
            bounds.append((k, a, b))
    res = []
    for c in cuts:
        A, B, O = round(c["a"] * fps), round(c["b"] * fps), round(c["o"] * fps)
        if not bounds:
            res.append({"clip": None, "src": Fraction(A, fps), "frames": B - A, "out": O})
            continue
        pos = A
        while pos < B:
            k, ca, cb = next(((k, ca, cb) for k, ca, cb in bounds if ca <= pos < cb), bounds[-1])
            end = min(B, cb) if pos < cb else B
            if end <= pos:
                break
            res.append({"clip": k, "src": Fraction(pos - ca, fps), "frames": end - pos, "out": O + (pos - A)})
            pos = end
    res = split_by_framing(res, clips, fps) if use_originals else res
    # zaokruživanje početaka klipova (ms) zna dati kadar od 1 sličice na spoju: pripoji ga susjedu
    merged = []
    for p in res:
        if (merged and p["frames"] <= 1 and merged[-1]["out"] + merged[-1]["frames"] == p["out"]
                and merged[-1].get("crop_x") == p.get("crop_x")):
            merged[-1]["frames"] += p["frames"]
        else:
            merged.append(p)
    return merged


def split_by_framing(pieces, clips, fps):
    """Kadar prati govornika (kadar.py): kadar iz originala se dijeli na promjeni govornika, a svaki dio
    dobije svoj crop_x (kao rez u multicam montaži). Kadar u kojem kamera ide za licem dobije srednji položaj."""
    out = []
    for p in pieces:
        c = clips[p["clip"]] if p["clip"] is not None else {}
        ks = c.get("kadrovi") or []
        if not ks:
            out.append(p)
            continue
        a0 = round(p["src"] * fps)
        pos, end = a0, a0 + p["frames"]
        while pos < end:
            k = next((k for k in ks if round(k["od"] * fps) <= pos < round(k["do"] * fps)), ks[-1])
            stop = min(end, max(pos + 1, round(k["do"] * fps))) if k is not ks[-1] else end
            out.append({**p, "src": Fraction(pos, fps), "frames": stop - pos, "out": p["out"] + (pos - a0),
                        "crop_x": k["crop_x"]})
            pos = stop
    return out


# ---------------------------------------------------------------- pjesme (M4.3b2)
def song_parts(a, b, songs):
    """Dio [a, b) (sličice) podijeljen po pjesmama → [(od, do, pjesma ili None)]; songs = [(od, do, nastup)]."""
    out, pos = [], a
    for x, y, n in sorted(songs, key=lambda q: q[0]):
        if y <= pos or x >= b:
            continue
        if x > pos:
            out.append((pos, x, None))
        out.append((max(pos, x), min(b, y), n))
        pos = min(b, y)
    if pos < b:
        out.append((pos, b, None))
    return [q for q in out if q[1] > q[0]]


def source_to_out(t, cuts):
    """Vrijeme source.mp4 → vrijeme gotovog videa (prije brzine); None ako je taj trenutak izrezan."""
    for c in cuts:
        if c["a"] - 1e-6 <= t <= c["b"] + 1e-6:
            return c["o"] + (min(max(t, c["a"]), c["b"]) - c["a"])
    return None


def out_to_source(o, cuts):
    for c in cuts:
        if c["o"] - 1e-6 <= o < c["o"] + (c["b"] - c["a"]) - 1e-6:   # kraj reza = početak sljedećeg
            return c["a"] + (o - c["o"])
    return None


# ---------------------------------------------------------------- podcast (M4.2b): originalne kamere
def podcast_sources(proj, pj):
    """Podcast projekt (rezija.py): kamere i glavni zvuk iz sinkro.json + uloge iz rezija.json.
    Vrati None ako projekt nije podcast; (None, napomena) ako originali ne postoje."""
    pc = pj.get("podcast")
    if not pc:
        return None
    sp, rp = proj / "sinkro.json", proj / "rezija.json"
    if not sp.exists() or not rp.exists():
        return None, "nema sinkro.json ili rezija.json → koristim source.mp4"
    sync, rez = load_json(sp), load_json(rp)
    src = {e["ime"]: e for e in sync["izvori"]}
    master = next((e for e in sync["izvori"] if e.get("glavni")), None)
    clips = []
    for r in rez.get("kamere", []):
        e = src.get(r["ime"])
        if not e or e.get("vrsta") != "video" or not e.get("pronaden", True):
            continue
        uloga = r.get("uloga") or ""
        tko = f" {r['govornik']}" if r.get("govornik") else ""
        clips.append({"file": e["datoteka"], "ime": e["ime"], "w": e.get("w"), "h": e.get("h"),
                      "crop_x": r.get("crop_x", 0.5), "crop_y": r.get("crop_y", 0.4), "sync": e,
                      "uloga": uloga, "naziv": f"{e['ime']} ({uloga}{tko})" if uloga else e["ime"]})
    files = [c["file"] for c in clips] + ([master["datoteka"]] if master else [])
    missing = [f for f in files if not Path(f).exists()]
    if not clips or not master or missing:
        what = Path(missing[0]).name if missing else "kamere/glavni zvuk"
        return None, f"originalna snimka podcasta ne postoji ({what}) → koristim source.mp4"
    return {"clips": clips, "master": master, "pocetak": float(rez.get("pocetak", pc.get("pocetak", 0.0))),
            "kadrovi": rez.get("kadrovi", [])}, None


def podcast_pieces(cuts, pc, fps):
    """Rezovi u vremenu programa (source.mp4) → kadrovi iz originalnih kamera. Rez se dijeli na svakoj
    promjeni kamere iz rezija.json. Svaki kadar: clip (indeks kamere ili None za crno → source.mp4), src u
    datoteci kamere, frames, out, cut (indeks reza), prog (početak u programu, sličice) i alts: ostale kamere
    koje u tom dijelu snimaju [(indeks, src)] — idu na gornje trake, isključene, za ručnu promjenu kadra."""
    clips, p0 = pc["clips"], pc["pocetak"]
    by = {c["ime"]: k for k, c in enumerate(clips)}
    shots = [(round(s["od"] * fps), round(s["do"] * fps), by.get(s.get("kamera"))) for s in pc["kadrovi"]]
    import sinkro as S

    def src_of(k, frame):
        return Fraction(max(0.0, S.to_source(clips[k]["sync"], p0 + frame / fps)))

    def films(k, a, b):  # kamera snima cijeli dio [a, b) sličica programa
        e = clips[k]["sync"]
        return e["od"] - 1e-3 <= p0 + a / fps and p0 + b / fps <= e["do"] + 1e-3

    res = []
    for ci, c in enumerate(cuts):
        A, B, O = round(c["a"] * fps), round(c["b"] * fps), round(c["o"] * fps)
        pos = A
        while pos < B:
            sh = next((s for s in shots if s[0] <= pos < s[1]), None)
            end = min(B, sh[1]) if sh else B
            if sh is None:  # izvan režije (ne bi se smjelo dogoditi): kamera koja snima, inače crno
                k = next((k for k in range(len(clips)) if films(k, pos, end)), None)
            else:
                k = sh[2]
            if k is not None and not films(k, pos, end):
                k = None
            alts = [(j, src_of(j, pos)) for j in range(len(clips)) if j != k and films(j, pos, end)]
            res.append({"clip": k, "src": src_of(k, pos) if k is not None else Fraction(pos, fps),
                        "frames": end - pos, "out": O + (pos - A), "cut": ci, "prog": pos, "alts": alts})
            pos = end
    # dio od 1 sličice na spoju reza i promjene kamere pripoji prethodnom kadru iste kamere
    merged = []
    for p in res:
        if (merged and p["frames"] <= 1 and merged[-1]["clip"] == p["clip"] and merged[-1]["cut"] == p["cut"]
                and merged[-1]["out"] + merged[-1]["frames"] == p["out"]):
            merged[-1]["frames"] += p["frames"]
        else:
            merged.append(p)
    return merged


def framing(clip, W, H, zoom=1.0):
    """Pomak slike (FCPXML adjust-transform position, postotak visine kadra) da se vidi isti dio
    snimke kao u Shofeovu videu: prepare.py reže širu snimku na crop_x/crop_y, render zumira na 38 %."""
    w, h = clip.get("w"), clip.get("h")
    px = py = 0.0
    if w and h:
        s = max(W / w, H / h)
        sw, sh = w * s, h * s
        px = (0.5 - float(clip.get("crop_x", 0.5))) * (sw - W)
        py = -(0.5 - float(clip.get("crop_y", 0.4))) * (sh - H)   # FCPXML: +y je gore
    px, py = px * zoom, py * zoom
    py -= (0.5 - ZOOM_Y) * (zoom - 1) * H
    return round(px / H * 100, 3) + 0.0, round(py / H * 100, 3) + 0.0   # + 0.0: bez „-0“


# ---------------------------------------------------------------- uspravni isječak podcasta (M4.2b3b)
def vertical_sources(proj, izvor):
    """Uspravni isječak podcasta (uspravno.py) → kamere, glavni zvuk i kadrovi 9:16 s dijelovima kao
    (indeks kamere, govornik, x, y, w). Vrati (None, napomena) ako originala nema (timeline iz izvora)."""
    import uspravno as U
    shots = (izvor or {}).get("kadrovi") or []
    if not shots:
        return None, None
    try:
        ctx = U.ucitaj(proj)
    except U.Greska as e:
        return None, f"originalne kamere: {e} → slika iz uspravnog izvora isječka"
    except Exception as e:  # noqa: BLE001  (npr. nema govornika)
        return None, f"originalne kamere nisu dostupne ({e}) → slika iz uspravnog izvora isječka"
    sync = load_json(Path(proj) / "sinkro.json")
    master = next((e for e in sync["izvori"] if e.get("glavni")), None)
    if not master or not Path(master["datoteka"]).exists():
        return None, "glavni zvuk ne postoji → slika i zvuk iz uspravnog izvora isječka"
    by = {c["ime"]: i for i, c in enumerate(ctx["cams"])}
    norm = []
    for s in shots:
        parts = []
        for p in s.get("dijelovi") or []:
            if isinstance(p, dict):     # iz izvor_9x16/K1.json
                k = by.get(p.get("kamera"))
                w = p.get("lice") if p.get("lice") is not None else p.get("skupina")   # bend: širina skupine
                p = None if k is None else (k, p.get("govornik"), p.get("x", 0.5), p.get("y", 0.42), w)
            parts.append(p)
        if any(p is None for p in parts):
            return None, "kamera iz uspravnog izvora više nije u režiji → slika iz uspravnog izvora isječka"
        rasp = s.get("raspored")
        if rasp == "bend" and (len(parts) != 1 or U.geometrija_bend(ctx["cams"][parts[0][0]], parts[0]) is None):
            rasp = "jedan"
        norm.append({"od": float(s["od"]), "do": float(s["do"]), "dijelovi": tuple(parts), "raspored": rasp})
    return {"cams": ctx["cams"], "master": master, "pocetak": ctx["pocetak"], "kadrovi": norm}, None


def vertical_pieces(pieces, vc, fps):
    """Kadrovi gotovog videa (vrijeme programa, jedan po rezu) → dijelovi po kadrovima 9:16: svaki dobije
    prog (sličica programa), cut (indeks reza) i parts (dijelovi kadra; prazno = crno → slika iz izvora)."""
    shots = [(round(s["od"] * fps), round(s["do"] * fps), s["dijelovi"], s.get("raspored")) for s in vc["kadrovi"]]
    res = []
    for ci, p in enumerate(pieces):
        a0 = round(p["src"] * fps)
        pos, end = a0, a0 + p["frames"]
        while pos < end:
            sh = next((s for s in shots if s[0] <= pos < s[1]), None)
            stop = min(end, sh[1]) if sh else end
            if sh is None:     # izvan kadrova (rub): najbliži kadar
                sh = min(shots, key=lambda s: min(abs(s[0] - pos), abs(s[1] - pos)))
            res.append({**p, "src": Fraction(pos, fps), "frames": stop - pos, "out": p["out"] + (pos - a0),
                        "prog": pos, "cut": ci, "parts": sh[2], "bend": sh[3] == "bend"})
            pos = stop
    merged = []
    for p in res:   # komadić od 1 sličice (zaokruživanje) pripoji prethodnom u istom rezu
        if merged and p["frames"] <= 1 and merged[-1]["cut"] == p["cut"]:
            merged[-1]["frames"] += p["frames"]
        else:
            merged.append(p)
    return merged


def vertical_layer(cam, part, W, H, idx, n, zoom=1.0):
    """Jedan dio kadra 9:16 kao FCPXML sloj: (scale x, scale y, position x, position y, trim ili None).
    Ista geometrija kao uspravno.pripremi: snimka skalirana na sw×sh, izrez Wt×Ht od (x, y); kod podijeljenog
    kadra (n = 2) gornji dio (idx 0) ide u gornju polovicu, donji u donju, s tamnom crtom između (trim).
    Mjere: scale je preko adjust-conform fill; position u postotku visine kadra, +y gore; trim-rect u
    postotku visine ORIGINALNE snimke (FCPXML DTD), u koordinatama snimke prije skaliranja. Zum stila
    (render.zoom_chain: oko točke W/2, 38 % visine) množi cijelu sliku, kao u renderu."""
    import uspravno as U
    Ht = H if n == 1 else H // 2
    sw, sh, x, y = U.geometrija(cam, part, W, Ht, "jedan" if n == 1 else "dvoje")
    w0, h0 = cam["w"], cam["h"]
    c = max(W / w0, H / h0)                         # adjust-conform fill
    zx, zy = sw / (w0 * c), sh / (h0 * c)
    ty = 0 if idx == 0 else Ht                      # vrh dijela na ekranu (px, dolje +)
    dx = sw / 2 - x - W / 2                         # središte slike − središte kadra (px)
    dy = (ty - y + sh / 2) - H / 2
    trim = None
    if n == 2:
        gap = U.RAZMAK / 2
        top = y + (gap if idx == 1 else 0)
        bot = y + Ht - (gap if idx == 0 else 0)
        sx, sy = sw / w0, sh / h0
        vals = (x / sx, top / sy, w0 - (x + W) / sx, h0 - bot / sy)   # lijevo, gore, desno, dolje (px snimke)
        trim = tuple(round(max(0.0, v) / h0 * 100, 4) + 0.0 for v in vals)
    if zoom != 1.0:
        cx, cy = W / 2, ZOOM_Y * H
        lx, ly = W / 2 + dx, H / 2 + dy
        dx = cx + zoom * (lx - cx) - W / 2
        dy = cy + zoom * (ly - cy) - H / 2
        zx, zy = zx * zoom, zy * zoom
    return (round(zx, 5), round(zy, 5), round(dx / H * 100, 3) + 0.0, round(-dy / H * 100, 3) + 0.0, trim)


def vertical_layer_bend(cam, part, W, H, zoom=1.0):
    """Bend (uspravno.geometrija_bend) kao FCPXML sloj: snimka skalirana tako da cijela skupina stane u širinu,
    iznad i ispod prazno (tamo je na V1 ista kamera kao pozadina). → (scale x, scale y, position x, position y)."""
    import uspravno as U
    sw, sh, x, oy = U.geometrija_bend(cam, part, W, H)
    w0, h0 = cam["w"], cam["h"]
    c = max(W / w0, H / h0)                         # adjust-conform fill
    zx, zy = sw / (w0 * c), sh / (h0 * c)
    dx = sw / 2 - x - W / 2
    dy = (oy + sh / 2) - H / 2
    if zoom != 1.0:
        cx, cy = W / 2, ZOOM_Y * H
        lx, ly = W / 2 + dx, H / 2 + dy
        dx = cx + zoom * (lx - cx) - W / 2
        dy = cy + zoom * (ly - cy) - H / 2
        zx, zy = zx * zoom, zy * zoom
    return (round(zx, 5), round(zy, 5), round(dx / H * 100, 3) + 0.0, round(-dy / H * 100, 3) + 0.0)


def music_path(proj, music):
    mp = Path(music)
    if not mp.is_absolute():
        mp = (proj / mp) if (proj / mp).exists() else Path.cwd() / mp
    return mp if mp.exists() else None


def loudness(path):
    """Integrirana glasnoća (LUFS) glazbe; render je normalizira na −16 LUFS prije glasnoće iz edit.json."""
    try:
        r = run([ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-af", "ebur128", "-f", "null", "-"])
        txt = (r.stderr or "") + (r.stdout or "")
        m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", txt)
        return float(m[-1]) if m else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- špice i poglavlja (M4.4d)
def split_pieces_at(pieces, out_frames, frame, speed, fps):
    """Podijeli kadar koji sadrži sličicu `frame` gotovog videa (prije špice) → (kadrovi, indeks prvog kadra
    od `frame` nadalje). Drugi dio nastavlja u istoj snimci (src, out, prog, ostale kamere)."""
    res, idx = [], None
    for p, (o, n) in zip(pieces, out_frames):
        if idx is None and o < frame < o + n:
            k = frame - o
            f1 = max(1, min(p["frames"] - 1, round(k * speed) if speed != 1 else k))
            a = dict(p, frames=f1)
            b = dict(p, frames=p["frames"] - f1, src=p["src"] + Fraction(f1, fps), out=p["out"] + f1)
            if "prog" in p:
                b["prog"] = p["prog"] + f1
            if "alts" in p:
                b["alts"] = [(j, s + Fraction(f1, fps)) for j, s in p["alts"]]
            if "cut" in p:   # zvuk ispod ide po komadima istog reza: drugi dio je novi komad (iza špice)
                b["cut"] = (p["cut"], "iza_spice")
            res += [a, b]
            idx = len(res) - 1
            continue
        if idx is None and o >= frame:
            idx = len(res)
        res.append(p)
    return res, (len(res) if idx is None else idx)


def frames_of(pieces, speed):
    out, t = [], 0
    for p in pieces:
        n = max(1, round(p["frames"] / speed)) if speed != 1 else p["frames"]
        out.append((t, n))
        t += n
    return out, t


def spica_media(proj, path):
    """Generirana špica (_tmp/spica_*.mkv) → spica/<ime>.mov u projektu (isti sadržaj, bez ponovnog kodiranja):
    DaVinci MOV uvozi uvijek, a _tmp se smije obrisati."""
    path = Path(path)
    if path.suffix.lower() != ".mkv":
        return path
    dest = Path(proj) / "spica" / (path.stem + ".mov")
    if not dest.exists():
        dest.parent.mkdir(exist_ok=True)
        run([ffmpeg(), "-y", "-v", "error", "-i", path.resolve(), "-map", "0", "-c", "copy", "-movflags", "+faststart",
             dest.relative_to(proj).as_posix()], cwd=proj)
    return dest


def spica_za(proj, edit, W, H, fps):
    """Špica koju render stavlja u glavni video → {"r": raspored, "files": {uvod, odjava}} ili None."""
    import render
    import spica as SP
    if not SP.aktivna(edit):
        return None
    pj = load_json(Path(proj) / "project.json")
    words = load_json(Path(proj) / "transcript.json")["words"]
    st = render.resolve_style(edit)
    cuts, kept, total = render.build_cuts(words, edit, st, pj["fps"], pj["duration"])
    speed = float(edit.get("brzina") or 1.0)
    r = SP.raspored(edit, cuts, speed, pj["fps"], total / speed, render.out_words(words, kept, cuts, set()))
    files = SP.pripremi(proj, edit, W, H, pj["fps"], st.get("boja_isticanja", "#FF7A00"), ispis=False)
    return {"r": r, "files": files}


def poglavlja_za(proj, edit, W, H):
    """Poglavlja epizode (kao u YouTube opisu, vrijeme videa sa špicom) za vodoravni video s temama; inače []."""
    proj = Path(proj)
    if W <= H or not (proj / "analiza.json").exists() or not load_json(proj / "analiza.json").get("teme"):
        return []
    import epizoda
    ch, _, _ = epizoda.poglavlja_za(proj, edit)
    return ch


def tc(frame, fps):
    """Sličica → vremenski kod HH:MM:SS:FF (NDF, cijeli fps)."""
    f = int(frame)
    return f"{f // (3600 * fps):02d}:{f // (60 * fps) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def marker_edl(ch, fps, title, boja=EDL_BOJA):
    """EDL s oznakama za DaVinci (Timelines > Import > Timeline Markers from EDL): jedna oznaka po poglavlju,
    vrijeme timelinea od 00:00:00:00 (kao tcStart u FCPXML-u)."""
    safe = "".join(ch_ if ch_.isalnum() or ch_ in " _-." else "_" for ch_ in title).strip() or "Shofe"
    lines = [f"TITLE: {safe}", "FCM: NON-DROP FRAME", ""]
    for i, c in enumerate(ch, 1):
        f = round(float(c["od"]) * fps)
        a, b = tc(f, fps), tc(f + 1, fps)
        name = " ".join(str(c["naslov"]).replace("|", "/").split())
        lines += [f"{i:03d}  001      V     C        {a} {b} {a} {b}", f" |C:{boja} |M:{name} |D:1", ""]
    return "\r\n".join(lines)


# ---------------------------------------------------------------- FCPXML
def build(proj, edit, use_originals=True, name=None, izvor=None, glavni=False, spica="auto"):
    """Vrati (ElementTree korijen, sažetak). Ne piše ništa na disk.
    izvor = uspravni izvor isječka podcasta (uspravno.py): timeline 9:16 iz te datoteke (slika i zvuk).
    glavni = glavni video (reel_vN, ne isječak): špice i poglavlja epizode. spica = {"r", "files"} iz rendera
    (spica.raspored / spica.pripremi), "auto" = izračunaj iz edit.json, None = bez špice."""
    import render  # rezovi, zumovi i stil točno kao u renderu

    proj = Path(proj)
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    W, H, fps = pj["width"], pj["height"], int(round(pj["fps"]))
    if izvor:
        W, H, use_originals = izvor["W"], izvor["H"], False
    st = render.resolve_style(edit)
    cuts, _, total = render.build_cuts(words, edit, st, fps, pj["duration"])
    if not cuts:
        die("nema ničega za zadržati (svi odsječci su isključeni?)")
    speed = Fraction(str(float(edit.get("brzina") or 1.0)))
    factor, zr = render.zoom_ranges(cuts, st)
    import nastupi
    songs = [(a, b, n) for a, b, n in nastupi.edit_songs(edit) if not izvor]   # vrijeme source.mp4 (s)
    song_frames = [(round(a * fps), round(b * fps), n) for a, b, n in songs]

    clips = pj.get("clips") or []
    notes = []
    pc = podcast_sources(proj, pj) if use_originals else None
    if izvor:
        clips = []
    if pc is not None:
        pc, note = pc
        if note:
            notes.append(note)
    if pc:
        clips = pc["clips"]
        pieces = podcast_pieces(cuts, pc, fps)
    else:
        missing = [c["file"] for c in clips if not Path(c["file"]).exists()]
        if use_originals and (not clips or missing):
            if missing:
                notes.append(f"originalna snimka ne postoji ({Path(missing[0]).name}"
                             + (f" i još {len(missing) - 1}" if len(missing) > 1 else "") + ") → koristim source.mp4")
            use_originals = False
        pieces = pieces_for(cuts, clips, fps, use_originals)
    vc = None
    if izvor and izvor.get("originali", True):
        vc, note = vertical_sources(proj, izvor)
        if note:
            notes.append(note)
    if vc:     # uspravni isječak podcasta iz ORIGINALNIH kamera (M4.2b3b)
        pieces = vertical_pieces(pieces, vc, fps)
    if izvor:   # izvor počinje na `pomak` s programa
        off = Fraction(round(float(izvor["pomak"]) * fps), fps)
        for p in pieces:
            p["src"] = max(Fraction(0), p["src"] - off)
        if not vc:
            notes.append("uspravni isječak podcasta: slika iz uspravnog izvora isječka (kamere su već izrezane)")

    fd = Fraction(1, fps)
    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", frameDuration=ftime(fd), width=str(W), height=str(H),
                  colorSpace="1-1-1 (Rec. 709)")
    assets, n_res = {}, [1]

    def new_id():
        n_res[0] += 1
        return f"r{n_res[0]}"

    def asset_for(key, path, display_name):
        if key in assets:
            return assets[key]
        info = media_info(path)
        rate = info["rate"] or Fraction(fps)
        afd = 1 / rate
        fid = new_id()
        ET.SubElement(res, "format", id=fid, frameDuration=ftime(afd), width=str(info["w"]), height=str(info["h"]))
        aid = new_id()
        el = ET.SubElement(res, "asset", id=aid, name=display_name, start=ftime(on_grid(info["tc"], afd)),
                           duration=ftime(on_grid(info["dur"], afd)), hasVideo="1", format=fid,
                           hasAudio="1" if info["audio"] else "0", videoSources="1")
        if info["audio"]:
            el.set("audioSources", "1")
            el.set("audioChannels", str(info["channels"]))
            el.set("audioRate", str(info["audio_rate"]))
        ET.SubElement(el, "media-rep", kind="original-media", src=file_uri(Path(path).resolve()))
        assets[key] = {"id": aid, "afd": afd, "tc": on_grid(info["tc"], afd), "info": info, "name": display_name}
        return assets[key]

    def audio_asset(key, path):
        if key in assets:
            return assets[key]
        info = media_info_audio(path)
        aid = new_id()
        afd = Fraction(1, info["audio_rate"])
        el = ET.SubElement(res, "asset", id=aid, name=Path(path).name, start="0s",
                           duration=ftime(on_grid(info["dur"], fd)), hasVideo="0", hasAudio="1",
                           audioSources="1", audioChannels=str(info["channels"]), audioRate=str(info["audio_rate"]))
        ET.SubElement(el, "media-rep", kind="original-media", src=file_uri(Path(path).resolve()))
        assets[key] = {"id": aid, "afd": afd, "tc": Fraction(0), "info": info, "name": Path(path).name}
        return assets[key]

    lib = ET.SubElement(root, "library")
    event = ET.SubElement(lib, "event", name="Shofe")
    title = name or proj.name
    project = ET.SubElement(event, "project", name=title)
    seq = ET.SubElement(project, "sequence", format="r1", tcStart="0s", tcFormat="NDF",
                        audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")

    # gotov video u sličicama (nakon brzine): kadar n počinje tamo gdje završava n−1
    out_frames, total_frames = frames_of(pieces, speed)

    # špice (M4.4d): samo u glavnom videu, kao u renderu; kadar na točki uvodne špice se podijeli
    sp = None
    if glavni and not izvor:
        sp = spica_za(proj, edit, W, H, fps) if spica == "auto" else spica
    sp_files = {k: v for k, v in ((sp or {}).get("files") or {}).items() if k in ("uvod", "odjava") and v}
    sp_r = sp["r"] if sp and sp.get("r") and sp_files else None
    uvod_n = round(sp_r["uvod"] * fps) if sp_r and sp_files.get("uvod") else 0
    odjava_n = round(sp_r["odjava"] * fps) if sp_r and sp_files.get("odjava") else 0
    at_idx, at_o = len(pieces), total_frames
    if uvod_n:
        pieces, at_idx = split_pieces_at(pieces, out_frames, round(sp_r["at"] * fps), speed, fps)
        out_frames, total_frames = frames_of(pieces, speed)
        at_o = out_frames[at_idx][0] if at_idx < len(pieces) else total_frames

    def tl(o):
        """Sličica gotovog videa bez špice → sličica timelinea (iza uvodne špice pomak za njezino trajanje)."""
        return o + uvod_n if uvod_n and o >= at_o else o

    def make_clip(parent, a, offset, src_start, dur, name, **extra):
        """asset-clip od src_start (vrijeme u datoteci, s vremenskim kodom) u trajanju dur gotovog videa.
        parent = spine (offset u vremenu timelinea) ili kadar u spineu (offset u njegovu lokalnom vremenu)."""
        if speed != 1:
            # timeMap: vrijeme kadra (time) ↔ vrijeme snimke (value); početak je u usporenom/ubrzanom vremenu
            el = ET.Element("asset-clip", ref=a["id"], name=name, **extra, offset=ftime(offset),
                            start=ftime(on_grid(src_start / speed, fd)), duration=ftime(dur), tcFormat="NDF")
            tm = ET.SubElement(el, "timeMap")
            adur = on_grid(a["info"]["dur"], a["afd"]) + a["tc"]
            ET.SubElement(tm, "timept", time="0s", value="0s", interp="linear")
            ET.SubElement(tm, "timept", time=ftime(on_grid(adur / speed, fd)), value=ftime(adur), interp="linear")
        else:
            el = ET.Element("asset-clip", ref=a["id"], name=name, **extra, offset=ftime(offset),
                            start=ftime(src_start), duration=ftime(dur), tcFormat="NDF")
        if parent is spine:
            spine.append(el)
        else:
            _insert_anchored(parent, el)
        return el

    def place(el, clip, z):
        """Kadriranje kao u Shofeovu videu: popuni kadar, pomakni na izrez, zum."""
        ET.SubElement(el, "adjust-conform", type="fill")
        px, py = framing(clip, W, H, z)
        attrs = {}
        if abs(px) >= 0.05 or abs(py) >= 0.05:
            attrs["position"] = f"{px:g} {py:g}"
        if z != 1.0:
            attrs["scale"] = f"{z:g} {z:g}"
        if attrs:
            ET.SubElement(el, "adjust-transform", **attrs)

    mute = {"srcEnable": "video"} if (pc or vc) else {}   # podcast: zvuk je glavni izvor na traci ispod
    song_audio = [0]   # komada zvuka pjesme na vlastitoj traci
    clip_els = []
    zoomed_pieces = 0
    import sinkro as S
    split_shots = 0
    bend_shots = 0

    def vertical_clip(parent, part, idx, nparts, p, o, n, z, bend=None, **extra):
        cam = vc["cams"][part[0]]
        a = asset_for(("v", part[0]), cam["datoteka"], Path(cam["datoteka"]).name)
        t = Fraction(max(0.0, S.to_source(cam, vc["pocetak"] + p["prog"] / fps)))
        who = f" {part[1]}" if part[1] else ""
        name = f"{cam['ime']}{who}" + ("" if nparts == 1 else " (gore)" if idx == 0 else " (dolje)")
        if bend:
            name = f"{cam['ime']} bend" + (" (pozadina)" if bend == "pozadina" else "")
        start = a["tc"] + on_grid(t, a["afd"])
        off = tl(o) * fd if parent is spine else parse_time(parent.get("start"))   # usidreni: lokalno vrijeme
        el = make_clip(parent, a, off, start, n * fd, name, srcEnable="video", **extra)
        if bend == "prednja":
            zx, zy, px, py, trim = *vertical_layer_bend(cam, part, W, H, z), None
        else:
            zx, zy, px, py, trim = vertical_layer(cam, part, W, H, idx, nparts, z)
        if trim:
            cr = ET.SubElement(el, "adjust-crop", mode="trim")
            ET.SubElement(cr, "trim-rect", left=f"{trim[0]:g}", top=f"{trim[1]:g}", right=f"{trim[2]:g}",
                          bottom=f"{trim[3]:g}")
        ET.SubElement(el, "adjust-conform", type="fill")
        ET.SubElement(el, "adjust-transform", position=f"{px:g} {py:g}", scale=f"{zx:g} {zy:g}")
        ET.SubElement(el, "adjust-volume", amount="-96dB")
        return el

    sp_els = {}

    def spica_clip(vrsta, at_frame, nfr):
        """Špica na glavnoj traci: Markova datoteka kao original (Fit, kao crni rub u Shofeu) ili generirana
        kartica (spica/*.mov). Bez brzine: špica u Shofeovu videu nije ubrzana."""
        dio = (edit.get("spica") or {}).get(vrsta) or {}
        own = bool(dio.get("datoteka"))
        path = Path(dio["datoteka"]) if own else spica_media(proj, sp_files[vrsta])
        if own and not path.is_absolute():
            path = proj / path
        if not path.exists():
            path = spica_media(proj, sp_files[vrsta])
            own = False
        a = asset_for(("spica", vrsta), path, path.name)
        ime = "Uvodna špica" if vrsta == "uvod" else "Odjavna špica"
        el = ET.SubElement(spine, "asset-clip", ref=a["id"], name=f"{ime} ({path.name})", offset=ftime(at_frame * fd),
                           start=ftime(a["tc"]), duration=ftime(nfr * fd), tcFormat="NDF")
        ET.SubElement(el, "adjust-conform", type="fit")
        note = ("Markova datoteka; u Shofeovu videu zvuk je izjednačen na −14 LUFS kao epizoda" if own else
                "generirana kartica (spica.py)") + ("; zadnjih 5–20 s je mjesto za YouTube završni zaslon"
                                                     if vrsta == "odjava" else "")
        _insert_marker(el, ET.Element("marker", start=ftime(a["tc"]), duration=ftime(nfr * fd), value=ime, note=note))
        sp_els[vrsta] = (at_frame, nfr, el, a["tc"])
        return el

    for idx, (p, (o, n)) in enumerate(zip(pieces, out_frames)):
        if uvod_n and idx == at_idx:
            spica_clip("uvod", at_o, uvod_n)
        if vc and p.get("parts"):
            mid = (p["out"] + p["frames"] / 2) / fps
            z = factor if factor and any(s <= mid < e for s, e in zr) else 1.0
            parts = p["parts"]
            if p.get("bend"):     # bend: V1 ista kamera kao pozadina (izrez 9:16), V2 cijela skupina u širini
                import uspravno as U
                cam0 = vc["cams"][parts[0][0]]
                el = vertical_clip(spine, U.pozadina_bend(cam0, parts[0]), 0, 1, p, o, n, z, bend="pozadina")
                vertical_clip(el, parts[0], 0, 1, p, o, n, z, bend="prednja", lane="1")
                bend_shots += 1
            else:
                el = vertical_clip(spine, parts[0], 0, len(parts), p, o, n, z)
            if len(parts) == 2:
                vertical_clip(el, parts[1], 1, 2, p, o, n, z, lane="1")
                split_shots += 1
            if z != 1.0:
                zoomed_pieces += 1
            # gotova Shofeova slika 9:16 na traci iznad, isključena: rezerva ako DaVinci drukčije složi izrez
            ia = asset_for("source", izvor["datoteka"], Path(izvor["datoteka"]).name)
            ref = make_clip(el, ia, parse_time(el.get("start")), ia["tc"] + on_grid(p["src"], ia["afd"]), n * fd,
                            "Shofe 9:16 (gotova slika)", lane="2", enabled="0", srcEnable="video")
            if z != 1.0:
                zpx, zpy = framing({}, W, H, z)
                ET.SubElement(ref, "adjust-transform", position=f"{zpx:g} {zpy:g}", scale=f"{z:g} {z:g}")
            ET.SubElement(ref, "adjust-volume", amount="-96dB")
            clip_els.append((el, o, n, parse_time(el.get("start"))))
            continue
        if p["clip"] is None:
            a = asset_for("source", izvor["datoteka"], Path(izvor["datoteka"]).name) if izvor \
                else asset_for("source", proj / "source.mp4", "source.mp4")
            clip = {}
        else:
            c = clips[p["clip"]]
            a = asset_for(p["clip"], c["file"], Path(c["file"]).name)
            clip = {**c, "crop_x": p["crop_x"]} if "crop_x" in p else c
        src_start = a["tc"] + on_grid(p["src"], a["afd"])
        mid = (p["out"] + p["frames"] / 2) / fps          # sredina kadra u vremenu prije brzine
        z = factor if factor and any(s <= mid < e for s, e in zr) else 1.0
        name = clip.get("naziv", a["name"])
        el = make_clip(spine, a, tl(o) * fd, src_start, n * fd, name, **mute)
        if p["clip"] is not None:
            place(el, clip, z)
        elif z != 1.0:
            px, py = framing({}, W, H, z)
            attrs = {"scale": f"{z:g} {z:g}"}
            if abs(px) >= 0.05 or abs(py) >= 0.05:
                attrs["position"] = f"{px:g} {py:g}"
            ET.SubElement(el, "adjust-transform", **attrs)
        if z != 1.0:
            zoomed_pieces += 1
        if mute:
            # ako DaVinci ipak donese i zvuk kamere, neka bude utišan (zvuk je glavni izvor ispod)
            ET.SubElement(el, "adjust-volume", amount="-96dB")
        clip_els.append((el, o, n, parse_time(el.get("start"))))

    if uvod_n and at_idx >= len(pieces):
        spica_clip("uvod", at_o, uvod_n)
    if odjava_n:
        spica_clip("odjava", total_frames + uvod_n, odjava_n)

    if song_frames and not pc and not vc:
        # obični projekt: kadar koji zahvaća pjesmu daje samo sliku, zvuk ide ispod iz iste snimke —
        # govor na A1 (dialogue), pjesma na A2 (music)
        for p, (el, o, n, start) in zip(pieces, clip_els):
            t0 = out_to_source(p["out"] / fps, cuts)
            if t0 is None:
                continue
            A = round(t0 * fps)
            parts = song_parts(A, A + p["frames"], song_frames)
            if not any(sg for *_, sg in parts):
                continue
            el.set("srcEnable", "video")
            a = next(v for v in assets.values() if v["id"] == el.get("ref"))
            bounds = [round((x - A) / speed) if x > A else 0 for x, _, _ in parts] + [n]
            for (x, y, sg), f0, f1 in zip(parts, bounds, bounds[1:]):
                if f1 <= f0:
                    continue
                src = a["tc"] + on_grid(p["src"] + Fraction(x - A, fps), a["afd"])
                make_clip(el, a, start + f0 * fd, src, (f1 - f0) * fd,
                          a["name"] + (f" (pjesma {sg['id']})" if sg else ""), lane="-2" if sg else "-1",
                          srcEnable="audio", audioRole="music" if sg else "dialogue")
                song_audio[0] += bool(sg)

    if pc:
        # gornje trake: svaka kamera na svojoj traci (V2 = prva kamera…), isključeno — u DaVinciju uključi
        # kadar na traci iznad (ili ga povuci dolje) i program pokazuje tu kameru umjesto Shofeova izbora
        alt_clips = 0
        for p, (el, o, n, start) in zip(pieces, clip_els):
            for j, src in p.get("alts", []):
                c = clips[j]
                a = asset_for(j, c["file"], Path(c["file"]).name)
                mid = (p["out"] + p["frames"] / 2) / fps
                z = factor if factor and any(s <= mid < e for s, e in zr) else 1.0
                alt = make_clip(el, a, start, a["tc"] + on_grid(src, a["afd"]), n * fd, c["naziv"],
                                lane=str(j + 1), enabled="0", srcEnable="video")
                place(alt, c, z)
                ET.SubElement(alt, "adjust-volume", amount="-96dB")
                alt_clips += 1
        # zvuk glavnog izvora (zasebni mikrofon ili glavna kamera) ispod slike, jedan komad po rezu
        m = pc["master"]
        same = next((j for j, c in enumerate(clips) if c["ime"] == m["ime"]), "master")
        ma = asset_for(same, m["datoteka"], Path(m["datoteka"]).name) if m.get("vrsta") == "video" \
            else audio_asset("master", m["datoteka"])
        import sinkro as S
        k = 0
        while k < len(pieces):
            ci = pieces[k]["cut"]
            e = k
            while e < len(pieces) and pieces[e]["cut"] == ci:
                e += 1
            el, o, n, start = clip_els[k]
            nfr = sum(clip_els[i][2] for i in range(k, e))
            A = pieces[k]["prog"]
            B = A + sum(pieces[i]["frames"] for i in range(k, e))
            # pjesma na svojoj traci (A2, music), govor na A1 (dialogue); granice u sličicama gotovog videa
            parts = song_parts(A, B, song_frames)
            bounds = [round((x - A) / speed) if x > A else 0 for x, _, _ in parts] + [nfr]
            for (x, y, sg), f0, f1 in zip(parts, bounds, bounds[1:]):
                if f1 <= f0:
                    continue
                src = Fraction(max(0.0, S.to_source(m, pc["pocetak"] + x / fps)))
                make_clip(el, ma, start + f0 * fd, ma["tc"] + on_grid(src, ma["afd"]), (f1 - f0) * fd,
                          ma["name"] + (f" (pjesma {sg['id']})" if sg else ""), lane="-2" if sg else "-1",
                          srcEnable="audio", audioRole="music" if sg else "dialogue")
                song_audio[0] += bool(sg)
            k = e
        notes.append(f"podcast: program iz {len(clips)} originalnih kamera (V1), ostale kamere na trakama iznad "
                     f"(isključeno, {alt_clips} kadrova), zvuk: {ma['name']}")

    if vc:
        # zvuk glavnog izvora ispod slike, jedan komad po rezu (kao u timelineu epizode)
        m = vc["master"]
        same = next((i for i, c in enumerate(vc["cams"]) if c["ime"] == m["ime"]), None)
        ma = asset_for(("v", same), m["datoteka"], Path(m["datoteka"]).name) if same is not None \
            else audio_asset("master", m["datoteka"])
        k = 0
        while k < len(pieces):
            ci = pieces[k]["cut"]
            e = k
            while e < len(pieces) and pieces[e]["cut"] == ci:
                e += 1
            el, o, n, start = clip_els[k]
            nfr = sum(clip_els[i][2] for i in range(k, e))
            src = Fraction(max(0.0, S.to_source(m, vc["pocetak"] + pieces[k]["prog"] / fps)))
            make_clip(el, ma, start, ma["tc"] + on_grid(src, ma["afd"]), nfr * fd, ma["name"],
                      lane="-1", srcEnable="audio", audioRole="dialogue")
            k = e
        notes.append(f"uspravni isječak podcasta iz {len({p[0] for q in pieces for p in q.get('parts') or ()})} "
                     f"originalnih kamera ({split_shots} podijeljenih kadrova: gornja osoba na V1, donja na V2), "
                     f"gotova Shofeova slika na V3 (isključeno), zvuk: {ma['name']}")
        if bend_shots:
            notes.append(f"pjesma: {bend_shots} kadrova benda — cijela skupina na V2, ista kamera kao pozadina na V1 "
                         "(nije zamućena: za izgled kao u Shofeu dodaj Gaussian Blur na V1)")

    # glazba: zasebna traka ispod (lane −1), usidrena na prvi kadar, ponavlja se do kraja videa
    music = edit.get("glazba")
    if music:
        mp = music_path(proj, music)
        if not mp:
            notes.append(f"glazba ne postoji: {music}")
        else:
            info = media_info_audio(mp)
            aid = new_id()
            mdur = on_grid(info["dur"], fd)
            el = ET.SubElement(res, "asset", id=aid, name=mp.name, start="0s", duration=ftime(mdur),
                               hasVideo="0", hasAudio="1", audioSources="1",
                               audioChannels=str(info["channels"]), audioRate=str(info["audio_rate"]))
            ET.SubElement(el, "media-rep", kind="original-media", src=file_uri(mp.resolve()))
            vol = float(edit.get("glazba_glasnoca") or -20)
            lufs = loudness(mp)
            gain = round(vol + (-16 - lufs), 1) if lufs is not None else vol
            first, _, _, fstart = clip_els[0]
            pos = Fraction(0)
            total_t = total_frames * fd
            anchors = []
            while pos < total_t and mdur > 0:
                d = min(mdur, total_t - pos)
                anchors.append((pos, d))
                pos += d
            loops = len(anchors)
            if uvod_n and at_o > 0:   # glazba ne svira ispod uvodne špice: dio iza nje pomakne se za špicu
                cut_t, split = at_o * fd, []
                for pos, d in anchors:
                    if pos < cut_t < pos + d:
                        split += [(pos, cut_t - pos, Fraction(0)), (pos, pos + d - cut_t, cut_t - pos)]
                    else:
                        split.append((pos, d, Fraction(0)))
                anchors = [(pos + skip + (uvod_n * fd if pos + skip >= cut_t else 0), d, skip)
                           for pos, d, skip in split]
            else:
                anchors = [(pos, d, Fraction(0)) for pos, d in anchors]
            for pos, d, skip in anchors:
                m = ET.Element("asset-clip", ref=aid, name=mp.name,
                               lane="-3" if song_audio[0] else "-2" if (pc or vc) else "-1",
                               offset=ftime(fstart + pos),
                               start=ftime(skip), duration=ftime(d), audioRole="music")
                ET.SubElement(m, "adjust-volume", amount=f"{gain:g}dB")
                _insert_anchored(first, m)
            notes.append(f"glazba na traci ispod: {mp.name}, {gain:g} dB"
                         + (f", {loops}× zaredom" if loops > 1 else "")
                         + " (stišavanje ispod govora nije preneseno)")

    # oznake: što je Shofe dodao preko slike (naslov, stil, zumovi)
    def marker_at(frame, value, note=None, dur_frames=1):
        for el, o, n, start in clip_els:
            if o <= frame < o + n:
                attrs = {"start": ftime(start + (frame - o) * fd), "duration": ftime(max(1, dur_frames) * fd),
                         "value": value}
                if note:
                    attrs["note"] = note
                _insert_marker(el, ET.Element("marker", **attrs))
                return

    grade = st.get("boja_slike", "neutralno")
    marker_at(0, f"Shofe stil: {st.get('naziv', edit.get('stil'))}",
              f"boja slike: {grade} ({GRADES.get(grade, '')}); zvuk i boja u ovom timelineu su neobrađeni")
    hook = (edit.get("hook") or "").strip()
    if hook:
        hd = min(float(edit.get("hook_trajanje") or 3.0), total)
        marker_at(0, f"Naslov: {hook}", "naslov (hook) na vrhu slike u Shofeovu videu",
                  round(hd / float(speed) * fps))
    if zr:
        for s, e in zr:
            f0 = round(s / float(speed) * fps)
            marker_at(f0, f"Zum {round(factor * 100)} %", "Shofe: punch-in zum (već postavljen kao Zoom/Scale)",
                      round((e - s) / float(speed) * fps))

    for a, b, n in songs:
        oa, ob = source_to_out(a, cuts), source_to_out(b, cuts)
        if oa is None or ob is None or ob <= oa:
            continue
        f0 = round(oa / float(speed) * fps)
        naziv = f": {n['naziv']}" if n.get("naziv") else ""
        lvl = n.get("glasnoca", edit.get("nastup_glasnoca"))
        note = ("nastup benda — Shofe ga ne reže (cijela izvedba); "
                + ("zvuk pjesme je na traci ispod govora (A2, uloga music)" if song_audio[0] else "zvuk u klipu")
                + "; u Shofeovu videu pjesma je izjednačena s govorom"
                + (f" ({float(lvl):+g} LU)" if lvl not in (None, 0) else "") + ", bez titlova")
        marker_at(f0, f"Pjesma {n['id']}{naziv}", note, round((ob - oa) / float(speed) * fps))
        f1 = round(ob / float(speed) * fps)
        marker_at(min(f1, total_frames - 1), f"Kraj pjesme {n['id']}", "nakon ovoga opet razgovor")
    if songs:
        notes.append(f"pjesme: {len(songs)} (oznaka cijelom duljinom"
                     + (", zvuk pjesme na traci A2" if song_audio[0] else "") + ")")

    # poglavlja epizode (iste kao u YouTube opisu i MP3-u) kao chapter-marker oznake na mjestu u timelineu
    segs = [(tl(o), n, el, start) for el, o, n, start in clip_els] + list(sp_els.values())
    ch = poglavlja_za(proj, edit, W, H) if glavni and not izvor else []
    ch_placed = 0
    for c in ch:
        F = round(float(c["od"]) * fps)
        for f0, n, el, start in segs:
            if f0 <= F < f0 + n:
                _insert_marker(el, ET.Element("chapter-marker", start=ftime(start + (F - f0) * fd),
                                              duration=ftime(fd), value=str(c["naslov"])))
                ch_placed += 1
                break
    if ch:
        notes.append(f"poglavlja: {ch_placed} oznaka (chapter-marker) u timelineu")
    if sp_els:
        import spica as SP
        notes.append(SP.opis(sp_r, edit) + " — u timelineu")

    full = total_frames + uvod_n + odjava_n
    seq.set("duration", ftime(full * fd))
    ET.indent(root, space="  ")
    summary = {"kadrova": len(pieces), "sekundi": float(full * fd), "izvor": "uspravno_kamere" if vc else "uspravno" if izvor else "podcast" if pc else
               "originali" if use_originals else "source.mp4", "datoteke": sorted({a["name"] for a in assets.values()}), "zumova": zoomed_pieces,
               "napomene": notes, "brzina": float(speed), "pieces": pieces, "fps": fps,
               "pjesama": len(songs), "zvuk_pjesme": song_audio[0], "bend": bend_shots,
               "poglavlja": ch, "spica": ({"r": sp_r, "uvod": uvod_n, "odjava": odjava_n, "at": at_o}
                                          if sp_els else None)}
    return root, summary


def media_info_audio(path):
    d = probe(path)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not a:
        die(f"{path} nema zvuk")
    return {"dur": float(d["format"].get("duration") or a.get("duration") or 0),
            "channels": int(a.get("channels", 2)), "audio_rate": int(a.get("sample_rate", 48000))}


# redoslijed djece asset-clipa po DTD-u 1.10: timeMap, adjust-*, usidreni klipovi, markeri
_ORDER = {"note": 0, "conform-rate": 1, "timeMap": 2, "adjust-crop": 2.5, "adjust-conform": 3, "adjust-transform": 4,
          "adjust-volume": 5, "asset-clip": 6, "marker": 7, "chapter-marker": 7}


def _insert(parent, child):
    rank = _ORDER.get(child.tag, 9)
    for i, c in enumerate(list(parent)):
        if _ORDER.get(c.tag, 9) > rank:
            parent.insert(i, child)
            return
    parent.append(child)


_insert_anchored = _insert
_insert_marker = _insert


def write(root, path):
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    Path(path).write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + body + "\n",
                          encoding="utf-8", newline="\n")


def export(proj, edit, base, use_originals=True, name=None, izvor=None, glavni=False, spica="auto"):
    """Napiši <base>.fcpxml u projekt (+ <base>.poglavlja.edl ako ima poglavlja); vrati (putanja, sažetak)."""
    proj = Path(proj)
    root, summ = build(proj, edit, use_originals, name, izvor=izvor, glavni=glavni, spica=spica)
    out = proj / f"{base}.fcpxml"
    write(root, out)
    edl = proj / f"{base}.poglavlja.edl"
    if summ["poglavlja"]:
        edl.write_bytes(marker_edl(summ["poglavlja"], summ["fps"], name or base).encode("utf-8"))
        summ["edl"] = edl
    elif edl.exists():
        edl.unlink()
    return out, summ


def for_render(proj, edit, out_video, izvor=None, glavni=False, spica=None):
    """render.py: uz svaki video i .fcpxml. Greška ovdje nikad ne ruši render.
    glavni = reel_vN (ne isječak); spica = {"r", "files"} kakvu je render stavio u video (ili None)."""
    try:
        ov = Path(out_video)
        try:  # isti folder kao video (npr. isjecci/K1.fcpxml)
            base = ov.resolve().relative_to(Path(proj).resolve()).with_suffix("").as_posix()
        except ValueError:
            base = ov.stem
        out, summ = export(proj, edit, base, name=f"{Path(proj).name} {ov.stem}", izvor=izvor, glavni=glavni,
                           spica=spica)
        lines = [f"DaVinci timeline: {out.name}  ({summ['kadrova']} kadrova iz "
                 + {"originali": "originalnih snimki", "podcast": "originalnih kamera, ostale kamere na trakama iznad",
                    "uspravno": "uspravnog izvora isječka",
                    "uspravno_kamere": "originalnih kamera, uspravno 9:16"}
                 .get(summ["izvor"], "source.mp4") + ")"]
        lines += [f"  ({n})" for n in summ["napomene"] if "ne postoji" in n]
        if summ["spica"]:
            s = summ["spica"]
            lines.append("  (špica u timelineu: " + ", ".join(
                ([f"uvodna na {fmt_time(s['at'] / summ['fps'])}"] if s["uvod"] else []) + (["odjavna na kraju"] if s["odjava"] else []))
                + ")")
        if summ.get("edl"):
            lines.append(f"  (poglavlja: {len(summ['poglavlja'])} oznaka u timelineu + {summ['edl'].name} → u DaVinciju "
                         "Timelines > Import > Timeline Markers from EDL, pa Deliver > Chapters from Markers: Green)")
        return lines
    except SystemExit as e:  # die() u izvozu
        return [f"(DaVinci timeline nije napravljen: {e})"]
    except Exception as e:  # noqa: BLE001
        return [f"(DaVinci timeline nije napravljen: {e})"]


def main():
    import titlovi

    ap = argparse.ArgumentParser(description="Izvoz u DaVinci Resolve (FCPXML + SRT)")
    ap.add_argument("projekt")
    ap.add_argument("--verzija", type=int, default=None, help="broj verzije (reel_vN); zadano: ona koju gledaš")
    ap.add_argument("--trenutno", action="store_true", help="iz trenutnog edit.json")
    ap.add_argument("--izvor", default="original", choices=["original", "priprema"],
                    help="original = snimke s mobitela/kamere (zadano); priprema = source.mp4")
    ap.add_argument("--izlaz", default=None, help="ime datoteke bez nastavka (zadano reel_vN)")
    ap.add_argument("--ispis", action="store_true", help="ispiši kadrove")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    edit, base, what = titlovi.pick(proj, a.verzija, a.trenutno)
    base = a.izlaz or base
    out, summ = export(proj, edit, base, a.izvor == "original", name=f"{proj.name} {base}", glavni=True)
    srt = proj / f"{base}.srt"
    if not srt.exists():
        cues, _ = titlovi.cues_for(proj, edit)
        if summ["spica"]:
            import spica as SP
            cues = SP.pomakni_cues(cues, summ["spica"]["r"])
        titlovi.write_srt(srt, cues)
    if a.ispis:
        pj = load_json(proj / "project.json")
        clips = pj.get("clips") or []
        fps = summ["fps"]
        for i, p in enumerate(summ["pieces"], 1):
            f = Path(clips[p["clip"]]["file"]).name if p["clip"] is not None else "source.mp4"
            print(f"{i:3d}  {fmt_time(p['out'] / fps)}  {f}  {fmt_time(float(p['src']))}–"
                  f"{fmt_time(float(p['src']) + p['frames'] / fps)}")
        print()
    print(f"DaVinci ({what}): {summ['kadrova']} kadrova, {fmt_time(summ['sekundi'])}, izvor: "
          + ", ".join(summ["datoteke"]))
    for n in summ["napomene"]:
        print(f"  napomena: {n}")
    print(f"  {out}\n  {srt}")
    print("U DaVinciju: File > Import > Timeline > " + out.name + ", zatim File > Import > Subtitle > " + srt.name)
    if summ.get("edl"):
        print(f"Poglavlja ({len(summ['poglavlja'])}): desni klik na timeline u Media Poolu > Timelines > Import > "
              f"Timeline Markers from EDL > {summ['edl'].name} (zelene oznake); Deliver > Chapters from Markers: Green")


if __name__ == "__main__":
    sys.exit(main())
