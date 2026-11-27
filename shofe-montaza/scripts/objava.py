"""Tekstovi za objavu po mreži (M3.4a): naslov, opis i hashtagovi za Instagram, TikTok i YouTube.

  python objava.py shofe_projekt                 video koji gledaš (reel_vN), inače svi gotovi isječci
  python objava.py shofe_projekt isjecci         svi renderirani isječci (isjecci/K1_….mp4)
  python objava.py shofe_projekt K1,K3           ti isječci;  v3 = reel_v3
  python objava.py shofe_projekt --serija "SF klima"   potpis i stalni hashtagovi serije
  python objava.py shofe_projekt --mreze instagram,youtube
  python objava.py shofe_projekt --ispis         ispiši gotove tekstove
  python objava.py shofe_projekt epizoda         podcast epizoda (gledana verzija): YouTube opis s poglavljima
                                                 + naslov i opis za podcast platforme (Spotify, Apple…)

  python objava.py serija                        popis serija (Markove stalne postavke)
  python objava.py serija "SF klima" --hashtagovi "#sfklima,#kutina" --potpis "SF klima Kutina · 091 …"
        [--mreza youtube] [--napomena "ton, publika, poziv na akciju"] [--brisi]

Tekstove piše Claude u objava.json (polja `opis`, `hashtagovi`, za YouTube i `naslov`); ovaj alat
napravi objava.json s kontekstom (govor iz SRT-a, hook, naslov isječka), provjeri pravila mreža
(duljina, najviše 5 hashtagova na Instagramu i TikToku, < > na YouTubeu, prvi redak, brojevi kojih
nema u govoru…) i složi gotov tekst za kopiranje u `<video>.objava.txt` uz video i `objava.txt`
u projektu. Izlazni kod 1 dok nešto fali ili ne valja.

Epizoda (M4.4b): vodoravni video ≥ 3 min s temama dobije poglavlja na kraju YouTube opisa (Shofe ih dodaje
sam, iz epizoda.py); epizoda podcasta (više kamera, nastupi, MP3 ili `epizoda`) još i „podcast": naslov i
opis epizode za Spotify for Creators / Apple Podcasts, s poglavljima u Spotifyjevu obliku (≥ 30 s), bez
hashtagova.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

from common import data_dir, die, load_json, save_json, video_info
from sadrzaj import fold

DATOTEKA = "objava.json"
SERIJE = "objava_serije.json"
MREZE = ("instagram", "tiktok", "youtube")
PODCAST = "podcast"
SVE_MREZE = MREZE + (PODCAST,)
IME_MREZE = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", PODCAST: "Podcast"}
SHORTS_MAX = 180.0  # YouTube Shorts: do 3 min uspravno ili kvadratno
POGLAVLJA_OD = 180.0  # vodoravni video od 3 min s temama: poglavlja u YouTube opisu

# Podcast platforme (provjereno studeni 2026, izvori u ODLUKE.md)
PODCAST_NASLOV_MAX = 150      # Apple Podcasts Connect: Name do 150 znakova
PODCAST_OPIS_MAX = 4000       # najstroži host (Spotify for Creators / RSS.com 4000; Apple 10 000)
PODCAST_POGLAVLJE_MIN = 30.0  # Spotify: poglavlja iz opisa najmanje 30 s razmaka, barem 3
PODCAST_POGLAVLJE_NASLOV = 40  # Spotify: naslov poglavlja do 40 znakova (Apple preporuča 45)
VRIJEME_RED_RE = re.compile(r"^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s+\S", re.MULTILINE)
BROJ_EPIZODE_RE = re.compile(r"(#\s*\d+|\b(?:ep|epizoda|epizode|episode)\.?\s*(?:br\.?\s*)?\d+|\b\d+\.\s*epizod\w*)",
                             re.IGNORECASE)

# Ograničenja mreža (provjereno studeni 2026, izvori u ODLUKE.md)
MAX_OPIS = {"instagram": 2200, "tiktok": 4000, "youtube": 5000, PODCAST: PODCAST_OPIS_MAX}
MAX_HASH = {"instagram": 5, "tiktok": 5, "youtube": 60}   # IG od 12/2025, TikTok od 8/2025; YT >60 → sve zanemari
PREPORUKA_HASH = {"instagram": (3, 5), "tiktok": (3, 5), "youtube": (1, 5)}  # YT: prva 3 iznad naslova
YT_NASLOV_MAX = 100
YT_NASLOV_VIDLJIVO = 70     # dulje se reže u popisu i na Shortsima
PRVI_REDAK = 125            # Instagram prije „… više"; TikTok pokazuje još manje

HASH_RE = re.compile(r"(?<![\w&])#(\w+)", re.UNICODE)
ZAMJENSKI_RE = re.compile(r"\b(TODO|XXX|lorem ipsum)\b|\[[^\]]{0,40}\]|<[^>]{0,40}>|\{\w*\}", re.IGNORECASE)


class Greska(Exception):
    pass


# ---------------------------------------------------------------- serije (Markove stalne postavke)
def serije_path():
    return data_dir() / SERIJE


def ucitaj_serije():
    p = serije_path()
    try:
        d = load_json(p) if p.exists() else {}
    except (ValueError, OSError):
        d = {}
    d.setdefault("serije", {})
    return d


def spremi_serije(d):
    serije_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(serije_path(), d)


def nadi_seriju(d, ime):
    if not ime:
        return None, None
    for k, v in d["serije"].items():
        if fold(k) == fold(ime):
            return k, v
    return None, None


def parse_hashtagovi(spec):
    """'#a, b #c' → ['#a', '#b', '#c'] (bez duplikata, redoslijed ostaje)."""
    if spec is None:
        return []
    if isinstance(spec, str):
        parts = re.split(r"[,\s]+", spec)
    else:
        parts = [str(x) for x in spec]
    out, seen = [], set()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not p.startswith("#"):
            p = "#" + p
        if p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def potpis_za(serija, mreza):
    if not serija:
        return ""
    p = serija.get("potpis") or {}
    if isinstance(p, str):
        return p.strip()
    return (p.get(mreza) if p.get(mreza) is not None else p.get("sve", "")).strip()


def cmd_serija(a):
    d = ucitaj_serije()
    if not a.ime:
        if not d["serije"]:
            print("Nema spremljenih serija. Primjer: objava.py serija \"SF klima\" --hashtagovi \"#sfklima\" "
                  "--potpis \"SF klima Kutina\"")
            return 0
        print(f"Serije ({serije_path()}):")
        for k, v in d["serije"].items():
            print(ispis_serije(k, v))
        return 0
    key, s = nadi_seriju(d, a.ime)
    if a.brisi:
        if not key:
            raise Greska(f"nema serije „{a.ime}”")
        del d["serije"][key]
        spremi_serije(d)
        print(f"Serija „{key}” obrisana.")
        return 0
    if not key:
        key, s = a.ime.strip(), {"hashtagovi": [], "potpis": {}, "napomena": ""}
        d["serije"][key] = s
    if isinstance(s.get("potpis"), str):
        s["potpis"] = {"sve": s["potpis"]}
    s.setdefault("potpis", {})
    if a.hashtagovi is not None:
        h = parse_hashtagovi(a.hashtagovi)
        for g in provjeri_hashtagove(h):
            raise Greska(g)
        if len(h) > 3:
            raise Greska(f"serija smije imati najviše 3 stalna hashtaga (ima {len(h)}): Instagram i TikTok "
                         "dopuštaju samo 5 po objavi, a bar 2 trebaju biti o samom videu")
        s["hashtagovi"] = h
    if a.potpis is not None:
        mreza = a.mreza or "sve"
        mreza = {"spotify": PODCAST, "apple": PODCAST}.get(fold(mreza), mreza)
        if mreza != "sve" and mreza not in SVE_MREZE:
            raise Greska(f"nepoznata mreža '{a.mreza}' ({', '.join(SVE_MREZE)})")
        if a.potpis.strip():
            s["potpis"][mreza] = a.potpis.replace("\\n", "\n").strip()
        else:
            s["potpis"].pop(mreza, None)
    if a.napomena is not None:
        s["napomena"] = a.napomena.strip()
    spremi_serije(d)
    print("Spremljeno:")
    print(ispis_serije(key, s))
    return 0


def ispis_serije(k, v):
    lines = [f"  {k}"]
    if v.get("hashtagovi"):
        lines.append(f"    hashtagovi: {' '.join(v['hashtagovi'])}")
    p = v.get("potpis") or {}
    if isinstance(p, str):
        p = {"sve": p}
    for m, t in p.items():
        lines.append(f"    potpis ({'sve mreže' if m == 'sve' else IME_MREZE.get(m, m)}): "
                     + t.replace("\n", " ⏎ "))
    if v.get("napomena"):
        lines.append(f"    napomena: {v['napomena']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- videi u projektu
def srt_tekst(srt):
    try:
        raw = Path(srt).read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    out = []
    for b in re.split(r"\n\s*\n", raw.strip()):
        lines = b.splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            out.append(" ".join(l.strip() for l in lines[2:]))
    return " ".join(out).strip()


def _format(proj):
    try:
        return load_json(Path(proj) / "project.json").get("format") or "9:16"
    except (OSError, ValueError):
        return "9:16"


def _trajanje(path, poznato=None):
    if poznato:
        return float(poznato)
    try:
        return round(video_info(path)["dur"], 1)
    except SystemExit:
        return 0.0


def zadane_mreze(fmt, trajanje, vrsta=None):
    if vrsta == "epizoda":
        return ["youtube", PODCAST]
    if fmt == "16:9" or trajanje > SHORTS_MAX:
        return ["youtube"]
    return list(MREZE)


OZNAKE_EPIZODE = ("sinkro.json", "rezija.json", "epizoda.json", "nastupi.json")


def je_epizoda(proj, fmt, trajanje):
    """Vodoravna epizoda podcasta: ≥ 3 min i projekt s više kamera / režijom / nastupima / MP3 postavkama."""
    return fmt == "16:9" and trajanje >= POGLAVLJA_OD and any((Path(proj) / f).exists() for f in OZNAKE_EPIZODE)


def videi_isjecaka(proj, spec=None):
    p = Path(proj) / "isjecci.json"
    if not p.exists():
        raise Greska("nema isjecci.json — prvo isjecci.py (predlozi, odobri, render)")
    data = load_json(p)
    by = {str(c["id"]).upper(): c for c in data.get("isjecci", [])}
    if spec:
        ids = []
        for part in re.split(r"[,;\s]+", spec.strip()):
            if part:
                key = part.upper() if part.upper().startswith("K") else f"K{part}"
                if key not in by:
                    raise Greska(f"nema isječka {part} (postoje: {', '.join(by) or 'nijedan'})")
                ids.append(key)
    else:
        ids = [k for k, c in by.items() if (c.get("render") or {}).get("datoteka")]
    out = []
    for k in ids:
        c = by[k]
        r = c.get("render") or {}
        f = r.get("datoteka")
        if not f or not (Path(proj) / f).exists():
            raise Greska(f"{k} još nije renderiran — prvo: isjecci.py {proj} render {k}")
        if r.get("brzo"):
            raise Greska(f"{k} je renderiran samo kao brzi pregled — prvo pravi render: isjecci.py {proj} render {k}")
        out.append({"id": k, "vrsta": "isjecak", "video": f, "trajanje": _trajanje(Path(proj) / f, r.get("trajanje")),
                    "hook": r.get("hook") or c.get("hook") or "", "naslov": c.get("naslov") or "",
                    "razlog": c.get("razlog") or ""})
        if c.get("vrsta") == "pjesma":   # isječak iz pjesme: bez govora, Claude piše o nastupu
            out[-1]["pjesma"] = c.get("naslov") or c.get("tema") or c.get("nastup") or "nastup benda"
    if not out:
        raise Greska("nema renderiranih isječaka — prvo: isjecci.py <projekt> render")
    return out


def video_reela(proj, v=None):
    import verzije
    if v is None:
        v = verzije.viewed(proj)
        if v is None:
            return None
    f = verzije.video_file(proj, v)
    if not f:
        raise Greska(f"nema videa verzije {v} (reel_v{v}.mp4)")
    info = verzije.load_meta(proj)["verzije"].get(str(v), {})
    hook = ""
    ep = verzije.vdir(proj) / f"edit_v{v}.json"
    if ep.exists():
        try:
            hook = load_json(ep).get("hook") or ""
        except (OSError, ValueError):
            pass
    return {"id": Path(f).stem.replace("_pregled", ""), "vrsta": "reel", "video": f, "v": v,
            "trajanje": _trajanje(Path(proj) / f, info.get("trajanje")), "hook": hook, "naslov": "",
            "razlog": "", "brzo": bool(info.get("brzi_pregled"))}


def odaberi_videe(proj, cilj):
    c = fold(cilj or "")
    if not c:
        r = video_reela(proj)
        if r:
            return [r]
        return videi_isjecaka(proj)
    if c in ("isjecci", "isjecke", "sve"):
        return videi_isjecaka(proj)
    if c in ("epizoda", "epizodu", "podcast"):
        r = video_reela(proj)
        if not r:
            raise Greska("nema renderirane epizode — prvo render.py (epizoda se opisuje iz gotovog videa)")
        r["vrsta"] = "epizoda"
        return [r]
    if c in ("reel", "video"):
        r = video_reela(proj)
        if not r:
            raise Greska("nema renderiranog videa — prvo render.py")
        return [r]
    m = re.fullmatch(r"(?:reel_)?v(\d+)", c)
    if m:
        return [video_reela(proj, int(m.group(1)))]
    return videi_isjecaka(proj, cilj)


def prazna_mreza(m):
    if m == PODCAST:
        return {"naslov": "", "opis": "", "broj": ""}
    return {"naslov": "", "opis": "", "hashtagovi": []} if m == "youtube" else {"opis": "", "hashtagovi": []}


GOVOR_KRATKO = 1500   # epizoda: početak govora u objava.json, cijeli tekst je u SRT-u


def kontekst_epizode(proj, v, epizoda_je):
    """Poglavlja (YouTube ≥ 10 s, podcast ≥ 30 s), teme, pjesme i govornici gotove verzije v. → (dict, upozorenja)."""
    import epizoda
    proj = Path(proj)
    out, upoz = {}, []
    try:
        edit = epizoda.odaberi(proj, v)[0]
        ch, final, _ = epizoda.poglavlja_za(proj, edit)
        out["poglavlja_youtube"] = epizoda.youtube_tekst(ch, final) if len(ch) >= epizoda.MIN_BROJ else ""
        if epizoda_je:
            chp, _, _ = epizoda.poglavlja_za(proj, edit, PODCAST_POGLAVLJE_MIN)
            out["poglavlja_podcast"] = epizoda.podcast_tekst(chp, final) if len(chp) >= epizoda.MIN_BROJ else ""
            if len(chp) < epizoda.MIN_BROJ:
                upoz.append(f"samo {poglavlja(len(chp))} od ≥ 30 s — Spotify ih iz opisa prikaže tek od 3; "
                            "opis epizode ide bez poglavlja")
            duga = [c["naslov"] for c in chp if len(c["naslov"]) > PODCAST_POGLAVLJE_NASLOV]
            if duga:
                upoz.append(f"poglavlje „{duga[0]}” ima > {PODCAST_POGLAVLJE_NASLOV} znakova — Spotify ga skraćuje; "
                            "skrati naslov teme u analiza.json")
        if len(ch) < epizoda.MIN_BROJ:
            upoz.append(f"samo {poglavlja(len(ch))} — YouTube ih prikazuje tek od 3, opis ide bez poglavlja"
                        + ("" if ch else " (u analiza.json nema tema: Claude ih treba upisati)"))
        an = epizoda.load_json(proj / "analiza.json") if (proj / "analiza.json").exists() else {}
        out["teme"] = [{"naslov": t.get("naslov", ""), "sazetak": t.get("sazetak", "")}
                       for t in an.get("teme") or [] if isinstance(t, dict)]
        out["pjesme"] = [n.get("naziv") or n.get("id", "pjesma") for n in edit.get("nastupi") or []
                         if n.get("zadrzi", True)]
        out["govornici"] = [g.get("ime") or g.get("id") for g in an.get("govornici") or []]
    except SystemExit:
        upoz.append("poglavlja nisu izračunata (nema transcript.json/project.json te verzije)")
    except Exception as ex:   # opis je važniji od poglavlja
        upoz.append(f"poglavlja nisu izračunata: {ex}")
    if epizoda_je:
        import epizoda as _e
        cfg = _e.postavke(proj)
        mp3 = (proj / f"reel_v{v}.mp3")
        out["mp3"] = mp3.name if mp3.exists() else ""
        out["mp3_naslov"] = cfg.get("naslov") or ""
        out["podcast_ime"] = cfg.get("autor") or _e.ZADANI_AUTOR
    return out, upoz


def ucitaj(proj):
    p = Path(proj) / DATOTEKA
    if p.exists():
        try:
            d = load_json(p)
        except ValueError as e:
            raise Greska(f"{DATOTEKA} nije ispravan JSON ({e}) — popravi zarez/navodnike")
    else:
        d = {}
    d.setdefault("serija", None)
    d.setdefault("videi", {})
    return d


def uskladi(proj, d, videi, mreze=None):
    """Upiši/osvježi videe u objava.json; tekstove koje je Claude napisao ne dira. → upozorenja."""
    fmt = _format(proj)
    upoz = []
    for v in videi:
        tekst = srt_tekst((Path(proj) / v["video"]).with_suffix(".srt"))
        h = hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:12]
        e = d["videi"].setdefault(v["id"], {})
        old_h = e.get("tekst_hash")
        if v["vrsta"] == "reel" and (e.get("vrsta") == "epizoda" or je_epizoda(proj, fmt, v["trajanje"])):
            v["vrsta"] = "epizoda"
        e.update({"video": v["video"], "vrsta": v["vrsta"], "trajanje": v["trajanje"], "format": fmt,
                  "hook": v["hook"]})
        for k in ("poglavlja_youtube", "poglavlja_podcast", "teme", "pjesme", "govornici", "mp3", "mp3_naslov",
                  "podcast_ime", "brojevi_govora"):
            e.pop(k, None)
        if v.get("v") is not None and (v["vrsta"] == "epizoda" or (fmt == "16:9" and v["trajanje"] >= POGLAVLJA_OD)):
            ctx, up = kontekst_epizode(proj, v["v"], v["vrsta"] == "epizoda")
            e.update(ctx)
            upoz += [f"{v['id']}: {u}" for u in up]
        if v["vrsta"] == "epizoda" and len(tekst) > GOVOR_KRATKO:
            e["brojevi_govora"] = sorted(_brojevi_u_govoru(tekst), key=lambda x: (len(x), x))
            cut = tekst.rfind(" ", 0, GOVOR_KRATKO)
            tekst_kratko = tekst[:cut if cut > 0 else GOVOR_KRATKO] + \
                f" … (početak; cijeli govor: {Path(v['video']).with_suffix('.srt').name} ili transcript.txt)"
        else:
            tekst_kratko = tekst
        if v.get("naslov"):
            e["naslov_isjecka"] = v["naslov"]
        if v.get("razlog"):
            e["razlog"] = v["razlog"]
        if v.get("pjesma") and not tekst.strip():
            tekst_kratko = f"(isječak iz pjesme „{v['pjesma']}“ — nastup benda uživo, bez govora)"
        e["govor"] = tekst_kratko
        e["tekst_hash"] = h
        if mreze:
            e["mreze_popis"] = list(mreze)
            e["mreze_izabrane"] = True
        elif v["vrsta"] == "epizoda" and not e.get("mreze_izabrane") and PODCAST not in e.get("mreze_popis", []):
            e["mreze_popis"] = zadane_mreze(fmt, v["trajanje"], "epizoda")   # reel koji je postao epizoda
        e.setdefault("mreze_popis", zadane_mreze(fmt, v["trajanje"], v["vrsta"]))
        e.setdefault("mreze", {})
        for m in e["mreze_popis"]:
            e["mreze"].setdefault(m, prazna_mreza(m))
            for k, val in prazna_mreza(m).items():
                e["mreze"][m].setdefault(k, val)
        if old_h and old_h != h and ispunjeno(e):
            upoz.append(f"{v['id']}: govor u videu se promijenio otkad su tekstovi napisani — pročitaj ih "
                        "ponovno i ispravi ako spominju nešto čega više nema")
        if v.get("brzo"):
            upoz.append(f"{v['id']}: {v['video']} je brzi pregled (pola rezolucije) — za objavu renderiraj pravi video")
    return upoz


def ispunjeno(e):
    return any((e.get("mreze") or {}).get(m, {}).get("opis") for m in SVE_MREZE)


# ---------------------------------------------------------------- slaganje i provjera
def hashtagovi_u(text):
    return ["#" + h for h in HASH_RE.findall(text or "")]


def slozi(e, m, serija):
    """Gotov tekst za mrežu m: (naslov ili None, opis s potpisom i hashtagovima, popis hashtagova)."""
    n = (e.get("mreze") or {}).get(m) or {}
    opis = (n.get("opis") or "").strip()
    if m == PODCAST:     # podcast platforme: opis + poglavlja + potpis, bez hashtagova
        dijelovi = [opis] if opis else []
        if e.get("poglavlja_podcast"):
            dijelovi.append("Poglavlja:\n" + e["poglavlja_podcast"].strip())
        pot = potpis_za(serija, m)
        if pot:
            dijelovi.append(pot)
        full = "\n\n".join(dijelovi)
        return (n.get("naslov") or "").strip(), full, hashtagovi_u(full)
    vlastiti = parse_hashtagovi(n.get("hashtagovi") or [])
    stalni = parse_hashtagovi((serija or {}).get("hashtagovi") or [])
    u_opisu = {h.lower() for h in hashtagovi_u(opis)}
    tagovi, seen = [], set(u_opisu)
    for h in vlastiti + stalni:
        if h.lower() not in seen:
            seen.add(h.lower())
            tagovi.append(h)
    dijelovi = [opis] if opis else []
    if m == "youtube" and e.get("poglavlja_youtube"):
        dijelovi.append("Poglavlja:\n" + e["poglavlja_youtube"].strip())
    pot = potpis_za(serija, m)
    if pot:
        dijelovi.append(pot)
    if tagovi:
        dijelovi.append(" ".join(tagovi))
    full = "\n\n".join(dijelovi)
    naslov = (n.get("naslov") or "").strip() if m == "youtube" else None
    return naslov, full, hashtagovi_u(full)


def provjeri_hashtagove(tags):
    gr = []
    for t in tags:
        body = t[1:]
        if not body or not re.fullmatch(r"\w+", body, re.UNICODE):
            gr.append(f"hashtag „{t}” smije imati samo slova, brojke i _ (bez razmaka, crtica i točaka)")
        elif body.isdigit():
            gr.append(f"hashtag „{t}” je samo broj — mreže ga ne prikazuju kao hashtag")
        elif len(body) > 40:
            gr.append(f"hashtag „{t}” je predug")
    return gr


def _brojevi(text):
    text = HASH_RE.sub(" ", text or "")
    return {re.sub(r"[.,]", "", b) for b in re.findall(r"\d+(?:[.,]\d+)*", text)}


def _brojevi_u_govoru(govor):
    """Brojke iz govora, i kao znamenke i kao riječi koje whisper ostavi slovima (do tisuću)."""
    out = _brojevi(govor)
    rijeci = {
        "jedan": 1, "jedna": 1, "jedno": 1, "dva": 2, "dvije": 2, "tri": 3, "četiri": 4, "pet": 5, "šest": 6,
        "sedam": 7, "osam": 8, "devet": 9, "deset": 10, "jedanaest": 11, "dvanaest": 12, "petnaest": 15,
        "dvadeset": 20, "trideset": 30, "četrdeset": 40, "pedeset": 50, "šezdeset": 60, "sto": 100,
        "dvjesto": 200, "tristo": 300, "četiristo": 400, "petsto": 500, "tisuću": 1000, "tisuća": 1000,
    }
    redni = {"prv": 1, "drug": 2, "trec": 3, "treć": 3, "četvrt": 4, "pet": 5, "šest": 6, "sedm": 7, "osm": 8,
             "devet": 9, "deset": 10}
    for w in re.findall(r"\w+", (govor or "").lower()):
        if w in rijeci:
            out.add(str(rijeci[w]))
        for k, n in redni.items():   # „Prvi korak… Drugi korak" → „u 2 koraka" nije izmišljeno
            if w.startswith(k) and len(w) <= len(k) + 3:
                out.add(str(n))
    return out


def poglavlja(n):
    return f"{n} poglavlje" if n % 10 == 1 and n % 100 != 11 else f"{n} poglavlja"


def hashtaga(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} hashtag"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} hashtaga"
    return f"{n} hashtagova"


def _vremena_u_opisu(e, m, opis, gr, up):
    """Poglavlja dodaje Shofe: vremena koja je Claude sam napisao bila bi kriva nakon svake promjene montaže."""
    if not VRIJEME_RED_RE.search(opis or ""):
        return
    ima = e.get("poglavlja_podcast" if m == PODCAST else "poglavlja_youtube")
    if ima:
        gr.append(f"{IME_MREZE[m]}: u opisu su vremena (npr. „{VRIJEME_RED_RE.search(opis).group(0).strip()}…”) — "
                  "ne piši ih, Shofe sam dodaje poglavlja iz gotovog videa")
    elif e.get("vrsta") == "epizoda" or "poglavlja_youtube" in e:
        up.append(f"{IME_MREZE[m]}: u opisu su vremena napisana rukom — provjeri da odgovaraju gotovom videu "
                  "(bolje: teme u analiza.json, Shofe složi poglavlja)")


def provjeri_podcast(e, n, naslov, full, gr, up):
    ime = "Podcast"
    if len(naslov) > PODCAST_NASLOV_MAX:
        gr.append(f"{ime}: naslov epizode ima {len(naslov)} znakova, najviše {PODCAST_NASLOV_MAX} (Apple)")
    if len(full) > PODCAST_OPIS_MAX:
        gr.append(f"{ime}: opis ima {len(full)} znakova, najviše {PODCAST_OPIS_MAX} (Spotify for Creators)")
    m = BROJ_EPIZODE_RE.search(naslov)
    if m:
        up.append(f"{ime}: broj epizode („{m.group(0)}”) je u naslovu — Apple ga želi u zasebnom polju: "
                  "upiši ga u \"broj\" i makni iz naslova")
    show = (e.get("podcast_ime") or "").strip()
    if show and fold(show) in fold(naslov):
        up.append(f"{ime}: ime podcasta „{show}” je u naslovu epizode — aplikacije ga već prikazuju iznad, "
                  "Apple traži da se ne ponavlja")
    b = str(n.get("broj") or "").strip()
    if b and not re.fullmatch(r"[1-9]\d{0,4}", b):
        gr.append(f"{ime}: broj epizode „{b}” mora biti cijeli broj veći od 0 (bez #, točke ili decimala)")
    if hashtagovi_u(n.get("opis")):
        up.append(f"{ime}: hashtagovi u opisu epizode — podcast aplikacije ih ne koriste, makni ih")
    if naslov and naslov.isupper() and len(naslov) > 12:
        up.append(f"{ime}: naslov je sav velikim slovima — istakni najviše 1–2 riječi")


def provjeri(e, serija):
    """→ (fali, greske, upozorenja) za jedan video."""
    fali, gr, up = [], [], []
    popis = e.get("mreze_popis") or []
    opisi = {}
    govor_br = _brojevi_u_govoru(e.get("govor", "")) | _brojevi(" ".join(
        potpis_za(serija, m) for m in SVE_MREZE)) | _brojevi(e.get("hook", "")) | \
        _brojevi(e.get("naslov_isjecka", "")) | set(e.get("brojevi_govora") or []) | \
        _brojevi(" ".join(t.get("naslov", "") + " " + t.get("sazetak", "") for t in e.get("teme") or [])) | \
        _brojevi(" ".join(e.get("pjesme") or []))
    for m in popis:
        n = (e.get("mreze") or {}).get(m) or {}
        ime = IME_MREZE[m]
        if m in ("youtube", PODCAST) and not (n.get("naslov") or "").strip():
            fali.append(f"{m}.naslov")
        if not (n.get("opis") or "").strip():
            fali.append(f"{m}.opis")
            continue
        naslov, full, tags = slozi(e, m, serija)
        _vremena_u_opisu(e, m, n.get("opis"), gr, up)
        for polje, t in (("naslov", naslov), ("opis", n.get("opis"))):
            if t and ZAMJENSKI_RE.search(t):
                gr.append(f"{ime}: {polje} ima zamjenski tekst „{ZAMJENSKI_RE.search(t).group(0)}” — napiši pravi tekst")
        for t in (naslov or "", n.get("opis") or ""):
            for b in sorted(_brojevi(t) - govor_br - {"1", str(n.get("broj") or "").strip()}):
                up.append(f"{ime}: broj {b} se ne čuje u videu — provjeri da je točan (ne izmišljaj cijene i brojke)")
        if m == PODCAST:
            provjeri_podcast(e, n, naslov, full, gr, up)
            continue
        opisi[m] = (n.get("opis") or "").strip()
        raw = n.get("hashtagovi") or []
        gr += [f"{ime}: {g}" for g in provjeri_hashtagove(parse_hashtagovi(raw) + hashtagovi_u(n.get("opis")))]
        if len(full) > MAX_OPIS[m]:
            gr.append(f"{ime}: opis ima {len(full)} znakova, najviše {MAX_OPIS[m]}")
        lo, hi = PREPORUKA_HASH[m]
        if len(tags) > MAX_HASH[m]:
            gr.append(f"{ime}: {hashtaga(len(tags))} — {ime} dopušta najviše {MAX_HASH[m]}"
                      + (" (sa stalnima iz serije)" if serija and serija.get("hashtagovi") else ""))
        elif len(tags) > hi:
            up.append(f"{ime}: {hashtaga(len(tags))} — preporuka {lo}–{hi}"
                      + (" (na Shortsima se iznad naslova vide samo prva 3)" if m == "youtube" else ""))
        elif len(tags) < lo:
            up.append(f"{ime}: {hashtaga(len(tags))} — preporuka {lo}–{hi}")
        prvi = (n.get("opis") or "").strip().split("\n", 1)[0]
        if m in ("instagram", "tiktok") and len(prvi) > PRVI_REDAK:
            up.append(f"{ime}: prvi redak ima {len(prvi)} znakova — vidi se samo ~{PRVI_REDAK} prije „više”; "
                      "skrati ga ili prelomi redak iza glavne misli")
        if m == "youtube":
            if naslov and len(naslov) > YT_NASLOV_MAX:
                gr.append(f"YouTube: naslov ima {len(naslov)} znakova, najviše {YT_NASLOV_MAX}")
            elif naslov and len(naslov) > YT_NASLOV_VIDLJIVO:
                up.append(f"YouTube: naslov ima {len(naslov)} znakova — na mobitelu se vidi ~{YT_NASLOV_VIDLJIVO}; "
                          "važno stavi na početak")
            if "<" in (naslov or "") + full or ">" in (naslov or "") + full:
                gr.append("YouTube: znakovi < i > nisu dopušteni u naslovu ni opisu")
            if naslov and naslov.isupper() and len(naslov) > 12:
                up.append("YouTube: naslov je sav velikim slovima — djeluje kao vikanje, istakni najviše 1–2 riječi")
        dij = [h for h in tags if re.search(r"[čćšžđ]", h.lower())]
        if dij:
            up.append(f"{ime}: {' '.join(dij)} — hashtag s kvačicama; provjeri koji oblik ljudi stvarno koriste "
                      "(često bez kvačica)")
    vals = list(opisi.values())
    if len(vals) >= 2 and len({fold(v) for v in vals}) < len(vals):
        up.append("isti opis na više mreža — prilagodi ga svakoj mreži (TikTok kraće, YouTube s ključnim riječima)")
    return fali, list(dict.fromkeys(gr)), list(dict.fromkeys(up))


def naslovne(proj, video):
    """Naslovne sličice uz video (naslovna.py) → [(ime datoteke, za što)]."""
    out = []
    stem = (Path(proj) / video).with_suffix("")
    for suf, za in (("9x16", "Instagram, TikTok, YouTube Shorts"), ("16x9", "YouTube")):
        f = Path(f"{stem}.naslovna_{suf}.jpg")
        if f.exists():
            out.append((f.name, za))
    return out


def tekst_datoteke(vid, e, serija, proj=None):
    zag = e.get("naslov_isjecka") or e.get("hook") or ""
    lines = [f"OBJAVA — {vid}" + (f" „{zag}”" if zag else "") + f" ({e['video']}, {e['trajanje']:.0f} s)",
             "Kopiraj tekst između crta.", ""]
    if proj is not None:
        nsl = naslovne(proj, e["video"])
        for ime, za in nsl:
            lines.insert(-1, f"Naslovna sličica ({za}): {ime}")
    for m in e.get("mreze_popis") or []:
        naslov, full, tags = slozi(e, m, serija)
        if m == PODCAST:
            n = (e.get("mreze") or {}).get(m) or {}
            lines += ["=== PODCAST PLATFORME (Spotify for Creators, Apple Podcasts…) ===", "Naslov epizode:",
                      "-" * 40, naslov, "-" * 40]
            if str(n.get("broj") or "").strip():
                lines += [f"Broj epizode (zasebno polje „Episode number”): {str(n['broj']).strip()}"]
            lines += ["Opis epizode:", "-" * 40, full, "-" * 40,
                      f"({len(full)}/{PODCAST_OPIS_MAX} znakova"
                      + (", poglavlja iz opisa vidi Spotify" if e.get("poglavlja_podcast") else "") + ")"]
            if e.get("mp3"):
                lines += [f"Zvuk: {e['mp3']} (poglavlja su već u MP3-u za Apple Podcasts i ostale aplikacije)"]
            else:
                lines += ["Zvuk: MP3 još nije napravljen — epizoda.py <projekt> mp3"]
            lines.append("")
            continue
        if m == "youtube":
            vrsta = ("Shorts" if e.get("format") != "16:9" and e["trajanje"] <= SHORTS_MAX else
                     "epizoda" if e.get("vrsta") == "epizoda" else "video")
            lines += [f"=== YOUTUBE ({vrsta}) ===", "Naslov:", "-" * 40, naslov, "-" * 40, "Opis:"]
        else:
            lines += [f"=== {IME_MREZE[m].upper()} ==="]
        lines += ["-" * 40, full, "-" * 40,
                  f"({len(full)}/{MAX_OPIS[m]} znakova, {hashtaga(len(tags))})", ""]
    return "\n".join(lines).rstrip() + "\n"


def napisi(proj, d, ids, serija):
    """Napiši <video>.objava.txt za ids i objava.txt za sve ispravne videe u projektu."""
    out = []
    for vid in ids:
        e = d["videi"][vid]
        p = (Path(proj) / e["video"]).with_suffix(".objava.txt")
        p.write_text(tekst_datoteke(vid, e, serija, proj), encoding="utf-8-sig")
        out.append(p)
    svi = []
    for vid, e in d["videi"].items():
        if not (Path(proj) / e.get("video", "")).exists():
            continue
        fali, gr, _ = provjeri(e, serija)
        if not fali and not gr:
            svi.append(tekst_datoteke(vid, e, serija, proj))
    if svi:
        (Path(proj) / "objava.txt").write_text(("\n" + "=" * 60 + "\n\n").join(svi), encoding="utf-8-sig")
    return out


def opis_videa(vid, e, serija, d_serija_ime):
    m = e.get("mreze_popis") or []
    yt = ("YouTube Shorts" if e.get("format") != "16:9" and e["trajanje"] <= SHORTS_MAX else "YouTube")
    ime = {"youtube": yt, PODCAST: "podcast platforme (Spotify, Apple…)"}
    mreze = ", ".join(ime.get(x, IME_MREZE[x]) for x in m)
    lines = [f"{vid}  {e['video']}  {e['trajanje']:.0f} s  {e.get('format')}"
             + ("  EPIZODA" if e.get("vrsta") == "epizoda" else "") + f"  → {mreze}"]
    if e.get("podcast_ime"):
        lines.append(f"  podcast: {e['podcast_ime']}" + (f"; naslov u MP3: {e['mp3_naslov']}" if e.get("mp3_naslov") else ""))
    if e.get("govornici"):
        lines.append(f"  govornici: {', '.join(e['govornici'])}")
    if e.get("teme"):
        lines.append("  teme: " + " · ".join(t["naslov"] + (f" ({t['sazetak']})" if t.get("sazetak") else "")
                                           for t in e["teme"]))
    if e.get("pjesme"):
        lines.append(f"  pjesme: {', '.join(e['pjesme'])}")
    if e.get("poglavlja_youtube"):
        lines.append("  poglavlja (Shofe ih dodaje sam na kraj YouTube" + (" i podcast" if e.get("poglavlja_podcast")
                                                                         else "") + " opisa — ne piši vremena):")
        lines += [f"    {x}" for x in e["poglavlja_youtube"].strip().splitlines()]
    if e.get("naslov_isjecka"):
        lines.append(f"  naslov isječka: {e['naslov_isjecka']}")
    if e.get("hook"):
        lines.append(f"  hook u videu: {e['hook']}")
    if e.get("razlog"):
        lines.append(f"  zašto je dobar: {e['razlog']}")
    if serija:
        st = serija.get("hashtagovi") or []
        if st:
            lines.append(f"  serija {d_serija_ime}: stalni hashtagovi {' '.join(st)} → dodaj još najviše "
                         f"{MAX_HASH['instagram'] - len(st)} za Instagram/TikTok")
        if serija.get("napomena"):
            lines.append(f"  napomena serije: {serija['napomena']}")
        pot = potpis_za(serija, "sve") or potpis_za(serija, "instagram")
        if pot:
            lines.append(f"  potpis (dodaje se sam): {pot.replace(chr(10), ' ⏎ ')}")
    g = e.get("govor") or "(nema SRT-a uz video — tekst govora nepoznat)"
    lines.append(f"  govor: {g}")
    return "\n".join(lines)


def cmd_projekt(proj, a):
    d = ucitaj(proj)
    sv = ucitaj_serije()
    if a.serija is not None:
        if a.serija.strip() == "" or fold(a.serija) == "nijedna":
            d["serija"] = None
        else:
            key, s = nadi_seriju(sv, a.serija)
            if not key:
                imena = ", ".join(sv["serije"]) or "nijedna"
                raise Greska(f"nema serije „{a.serija}” (postoje: {imena}). Napravi je: objava.py serija "
                             f"\"{a.serija}\" --hashtagovi … --potpis …")
            d["serija"] = key
    sk, serija = nadi_seriju(sv, d.get("serija"))
    if d.get("serija") and not sk:
        print(f"Upozorenje: serija „{d['serija']}” više ne postoji — radim bez potpisa i stalnih hashtagova")
    mreze = None
    if a.mreze:
        mreze = [fold(x) for x in re.split(r"[,;\s]+", a.mreze) if fold(x)]
        alias = {"ig": "instagram", "insta": "instagram", "tt": "tiktok", "yt": "youtube", "shorts": "youtube",
                 "spotify": PODCAST, "apple": PODCAST}
        mreze = list(dict.fromkeys(alias.get(x, x) for x in mreze))
        bad = [x for x in mreze if x not in SVE_MREZE]
        if bad:
            raise Greska(f"nepoznata mreža {', '.join(bad)} (instagram, tiktok, youtube, podcast)")
    videi = odaberi_videe(proj, a.cilj)
    upoz = uskladi(proj, d, videi, mreze)
    save_json(Path(proj) / DATOTEKA, d)
    ids = [v["id"] for v in videi]

    nedovrseno, gotovi = [], []
    for vid in ids:
        e = d["videi"][vid]
        fali, gr, up = provjeri(e, serija)
        upoz += [f"{vid}: {u}" for u in up]
        if fali or gr:
            nedovrseno.append((vid, e, fali, gr))
        else:
            gotovi.append(vid)
    if nedovrseno:
        print(f"Tekstovi za objavu — napiši ih u {Path(proj) / DATOTEKA} "
              f"(videi → <id> → mreze → instagram/tiktok/youtube/podcast):\n")
        for vid, e, fali, gr in nedovrseno:
            print(opis_videa(vid, e, serija, sk))
            if fali:
                print(f"  fali: {', '.join(fali)}")
            for g in gr:
                print(f"  GREŠKA: {g}")
            print()
    for vid in ids:   # MP3 naslov = naslov epizode na podcast platformama
        e = d["videi"][vid]
        pn = ((e.get("mreze") or {}).get(PODCAST) or {}).get("naslov", "").strip()
        if pn and PODCAST in (e.get("mreze_popis") or []) and pn != (e.get("mp3_naslov") or ""):
            upoz.append(f"{vid}: naslov u MP3-u " + (f"je „{e['mp3_naslov']}”" if e.get("mp3_naslov") else "nije upisan")
                        + f" — da bude isti kao na platformama: epizoda.py \"{proj}\" mp3 --naslov \"{pn}\"")
    for u in upoz:
        print(f"Upozorenje: {u}")
    if gotovi:
        files = napisi(proj, d, gotovi, serija)
        print(f"\nGotovo ({len(gotovi)}): " + ", ".join(str(f) for f in files))
        print(f"Svi gotovi tekstovi zajedno: {Path(proj) / 'objava.txt'}")
        bez = [vid for vid in gotovi if not naslovne(proj, d["videi"][vid]["video"])]
        if bez:
            print(f"Naslovne sličice još nema za {', '.join(bez)}: python naslovna.py \"{proj}\" "
                  + (bez[0] if len(bez) == 1 else "isjecci" if all(b.startswith("K") for b in bez) else ""))
        if a.ispis:
            for vid in gotovi:
                print()
                print(tekst_datoteke(vid, d["videi"][vid], serija, proj))
    return 1 if nedovrseno else 0


def main():
    ap = argparse.ArgumentParser(description="Tekstovi za objavu po mreži (objava.json → <video>.objava.txt)")
    ap.add_argument("projekt", help="mapa projekta, ili 'serija' za stalne postavke serija")
    ap.add_argument("cilj", nargs="?", default="",
                    help="isjecci | K1,K3 | reel | v3 | epizoda (projekt); ime serije (serija)")
    ap.add_argument("--serija", help="projekt: serija čiji se potpis i stalni hashtagovi dodaju (\"\" = bez)")
    ap.add_argument("--mreze", help="projekt: npr. instagram,tiktok,youtube,podcast (zadano: po vrsti videa)")
    ap.add_argument("--ispis", action="store_true", help="projekt: ispiši gotove tekstove")
    ap.add_argument("--hashtagovi", help="serija: stalni hashtagovi (najviše 3), npr. \"#sfklima,#kutina\"")
    ap.add_argument("--potpis", help="serija: redak na kraju opisa (\\n = novi red, \"\" = makni)")
    ap.add_argument("--mreza", help="serija: potpis samo za ovu mrežu (instagram, tiktok, youtube, podcast)")
    ap.add_argument("--napomena", help="serija: ton, publika, poziv na akciju — Claude to čita prije pisanja")
    ap.add_argument("--brisi", action="store_true", help="serija: obriši seriju")
    a = ap.parse_args()
    try:
        if fold(a.projekt) in ("serija", "serije") and not Path(a.projekt).is_dir():
            a.ime = a.cilj
            code = cmd_serija(a)
        else:
            proj = Path(a.projekt)
            if not proj.is_dir():
                die(f"nema mape projekta {proj}")
            code = cmd_projekt(proj, a)
    except Greska as e:
        die(str(e))
    sys.exit(code)


if __name__ == "__main__":
    main()
