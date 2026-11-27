"""Isječci za mreže: kandidati od 20–60 s iz dulje snimke → isjecci.json (ocjena + razlog za svaki).

  python isjecci.py shofe_projekt                     prvi put: predloži kandidate; poslije: provjeri
  python isjecci.py shofe_projekt predlozi [--broj 10] [--min 20] [--max 60] [--ponovo]
  python isjecci.py shofe_projekt provjeri            provjeri Claudeove ocjene, poredaj, isjecci.txt
  python isjecci.py shofe_projekt popis               ispiši popis (bez provjere)
  python isjecci.py shofe_projekt novi [--broj 5]     još kandidata, bez preklapanja s postojećima
  python isjecci.py shofe_projekt dodaj --od "citat" [--do "citat"] [--umjesto K3]
  python isjecci.py shofe_projekt pjesma P1 [--od 12:40 --do 13:25] [--umjesto K3]
                                                      isječak iz pjesme: najbolji refren 30–60 s (refren.py)
  python isjecci.py shofe_projekt odobri K1,K3        Marko je odabrao
  python isjecci.py shofe_projekt odbaci K2 [--razlog "…"]
  python isjecci.py shofe_projekt render [K1,K3] [--brzo] [--stil podcast] [--kadar 1,10] [--format 16:9]
                                                      odobreni (ili navedeni) → isjecci/K1_naslov.mp4

Postupak (isti duh kao Spotifyjevi pregledi epizoda i PodReels, vidi ODLUKE.md):
  1. rečenice → misli (skrati.build_thoughts): pitanje ostaje s odgovorom, rečenica s „A/Ali/To…"
     ne smije biti prva u isječku (treba joj ono prije);
  2. svaki niz cijelih misli koji traje 20–60 s (procjena trajanja kad se izrežu pauze) je kandidat;
  3. heuristička ocjena 0–10: jak početak (pitanje, broj, obraćanje gledatelju, jake riječi, pauza
     prije), zaokruženost (kraj rečenice, misao se ne nastavlja, pauza poslije, jedna tema),
     sadržaj (Claudeovi najjači trenuci iz analiza.json, gustoća sadržajnih riječi), energija
     (glasnoća, tempo, malo tišine); trajanje 25–45 s je idealno;
  4. odabir bez preklapanja (najbolji prvi), zadano 10 kandidata;
  5. Claude pročita svaki kandidat i upiše "ocjena" (1–10), "razlog" (jedna rečenica), po želji
     "naslov" i "hook"; može dodati svoje kandidate (dodaj) ili pomaknuti granice (od/do).
  6. provjeri: konačni poredak po Claudeovoj ocjeni (heuristika samo kod jednakih ocjena).
Pjesme (nastupi.json): isječak govora ne ide preko pjesme, a iz svake pjesme Shofe predloži jedan isječak
(vrsta „pjesma"): najbolji refren 30–60 s, na udarcu, do kraja refrena ili pjesme; bez titlova.
"""
import argparse
import datetime as _dt
import math
import re
import sys
import textwrap
from pathlib import Path

import numpy as np

import sadrzaj
import serija
import skrati as sk
from common import die, load_json, save_json, version
from govornici import load_words, speaker_names
from sadrzaj import SENT_END, fold

MIN_S, MAX_S = 20.0, 60.0
PJESMA_S = (30.0, 60.0)  # isječak iz pjesme (refren.py)
IDEAL = (25.0, 45.0)
PAUZA_REZ = 0.35        # pauza dulja od ovoga se u isječku skrati na ovoliko (procjena trajanja)
PAUZA_GRANICA = 1.0     # pauza prije/poslije koja znači prirodan početak/kraj
PREKLAPANJE = 0.15      # najviše toliki dio kraćeg isječka smije se preklapati s drugim
DATOTEKA = "isjecci.json"
STATUSI = ("prijedlog", "odobren", "odbacen")

# jake riječi za početak (bez kvačica, kao fold())
HOOK = {
    "nikad", "nikada", "uvijek", "najveca", "najveci", "najvece", "najvaznije", "najvazniji", "najbolji",
    "najbolje", "najgori", "najgore", "greska", "greske", "gresku", "tajna", "tajnu", "istina", "problem",
    "problema", "savjet", "savjeta", "trik", "trikova", "zasto", "nemojte", "morate", "trebate", "zapamtite",
    "pazite", "zamislite", "nitko", "besplatno", "eura", "kuna", "posto", "prvi", "jedini", "jedina",
    "nevjerojatno", "sok", "nikome", "ludo", "opasno", "stedi", "ustedjeti", "ustedite", "stvari", "razloga",
    "nacina", "koraka", "lekcija", "shvatio", "shvatila", "zaboraviti",
}
OBRACANJE = {"vi", "vam", "vas", "vama", "znate", "jeste", "jesi", "znas", "morate", "trebate", "nemojte",
             "zamislite", "pazite", "zapamtite", "pogledajte", "probajte", "pitajte", "recite", "vidite"}
BROJEVI = {"jedan", "jedna", "dva", "dvije", "tri", "cetiri", "pet", "sest", "sedam", "osam", "devet", "deset",
           "dvadeset", "trideset", "cetrdeset", "pedeset", "sto", "tristo", "petsto", "tisucu", "tisuce",
           "milijun", "pola", "osamdeset", "sezdeset", "sedamdeset", "devedeset", "dvjesto"}
UPITNE = {"zasto", "kako", "koliko", "sto", "tko", "gdje", "kada", "koji", "koja", "koje", "je", "jeste", "znate"}
CAVRLJANJE = {"bok", "pozdrav", "snima", "snimamo", "dobrodosli", "cujes", "cujete", "mikrofon", "kamera"}
ZAMJENICE = {"on", "ona", "oni", "one", "ono", "to", "taj", "ta", "tu", "tamo", "njega", "njoj", "njih", "tog",
             "toga", "tome", "ovo", "ovaj", "ova", "onaj", "onda"}
POSTAPALICE = re.compile(r"^(e+|e+m+|m+|mhm|hm+|a+m+|ovaj+|ono+|znaci|eto|mislim|znas|kao)$")
ODJAVA = {"hvala", "vidimo", "bok", "pozdrav", "pozdravljamo", "slusamo", "cujemo", "doslusanja"}
GRANICA_UNUTRA = 1.5    # pauza unutar isječka dulja od ovoga = vjerojatno dvije odvojene cjeline
NASTAVAK_PAUZA = 1.2    # rečenica s veznikom iza dulje pauze (ili drugog govornika) ne nastavlja misao

UPUTE = ("Za svaki isječak upiši \"ocjena\" (1–10: 9–10 objavio bih odmah, 7–8 dobar, 5–6 osrednji, ≤4 ne) i "
         "\"razlog\" (jedna rečenica: zašto radi ili ne radi samostalno na mrežama), po želji \"naslov\" "
         "(3–6 riječi) i \"hook\" (3–7 riječi za prve sekunde). Ocjenjuj: drži li prva rečenica pažnju, je li "
         "razumljivo bez ostatka epizode, ima li poantu/emociju/korisnu informaciju, završava li zaokruženo. "
         "Granice mijenjaj s 'dodaj --od … --do … --umjesto K'. Zatim: isjecci.py provjeri.")


# ---------------------------------------------------------------- pomoćno
def fmt(t):
    t = max(float(t), 0.0)
    h, r = divmod(int(round(t)), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def isjecaka(n):
    """Hrvatska množina: 1 isječak, 2–4 isječka, 5+ isječaka (11–14 isječaka)."""
    if n % 10 == 1 and n % 100 != 11:
        return "isječak"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "isječka"
    return "isječaka"


def _clamp(x, lo=0.0, hi=1.0):
    return min(max(x, lo), hi)


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _toks(words, a, b):
    return [t for t in (fold(words[i]["w"]) for i in range(a, b + 1)) if t]


def _first_sentence(words, a, b):
    j = a
    while j < b and not SENT_END.search(words[j]["w"]):
        j += 1
    return a, j


def _last_sentence(words, a, b):
    j = b
    while j > a and not SENT_END.search(words[j - 1]["w"]):
        j -= 1
    return j, b


def _text(words, a, b):
    return " ".join(words[i]["w"] for i in range(a, b + 1)).strip()


class Snimka:
    """Riječi snimke s pomoćnim nizovima za brzu procjenu trajanja isječka."""

    def __init__(self, words, analiza=None, imena=None):
        self.words = words
        self.an = analiza or {}
        self.imena = imena or {}
        s = np.array([w["s"] for w in words], float)
        e = np.array([w["e"] for w in words], float)
        dur = np.maximum(e - s, 0.0)
        gap = np.zeros(len(words))
        if len(words) > 1:
            gap[:-1] = np.clip(s[1:] - e[:-1], 0.0, PAUZA_REZ)
        self.cd = np.concatenate([[0.0], np.cumsum(dur)])
        self.cg = np.concatenate([[0.0], np.cumsum(gap)])
        self.misli, self.lanci = sk.build_thoughts(words, list(range(len(words))), 0.0) if words else ([], [])
        segs = self.an.get("odsjecci") or []
        dbs = [x["glasnoca_db"] for x in segs if isinstance(x.get("glasnoca_db"), (int, float))]
        self.med_db = float(np.median(dbs)) if dbs else None
        self.trajanje = float(self.an.get("trajanje") or (words[-1]["e"] if words else 0.0))
        self.idf = self._idf()
        self.pjesme = []  # [(od, do)] nastupi bendova: isječak govora ne ide preko pjesme (nastupi.py)

    def _idf(self):
        docs = [set(sk._terms(m.tekst)) for m in self.misli]
        n = max(len(docs), 1)
        df = {}
        for d in docs:
            for t in d:
                df[t] = df.get(t, 0) + 1
        return {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}

    def est(self, a, b):
        """Procjena trajanja isječka od riječi a do b kad se pauze skrate (kao u montaži)."""
        return float(self.cd[b + 1] - self.cd[a] + self.cg[b] - self.cg[a]) + 0.3

    def nastavlja(self, i):
        """True ako rečenica koja počinje riječju i nastavlja prethodnu (veznik/zamjenica, isti govornik,
        kratka pauza) — isječak ne smije početi njome niti završiti tik prije nje."""
        if i <= 0 or i >= len(self.words):
            return False
        w = self.words
        if self.pause_before(i) >= NASTAVAK_PAUZA or w[i].get("g") != w[i - 1].get("g"):
            return False
        if not SENT_END.search(w[i - 1]["w"]):
            return True  # rečenica još nije završila
        return fold(w[i]["w"]) in sk.VEZNICI

    def pause_before(self, a):
        return self.words[a]["s"] - self.words[a - 1]["e"] if a > 0 else 99.0

    def pause_after(self, b):
        return self.words[b + 1]["s"] - self.words[b]["e"] if b + 1 < len(self.words) else 99.0


# ---------------------------------------------------------------- ocjena
def ocijeni(sn, a, b):
    """Heuristička ocjena isječka [a, b] (indeksi riječi) → (0–10, dijelovi, razlozi)."""
    w = sn.words
    od, do = w[a]["s"], w[b]["e"]
    dur = sn.est(a, b)
    r_plus, r_minus = [], []

    # --- početak
    fa, fb = _first_sentence(sn.words, a, b)
    first = _toks(w, fa, fb)
    p = 0.4
    if w[fb]["w"].rstrip("\"'”“»)").endswith("?") or (first and first[0] in UPITNE and len(first) <= 14
                                                        and w[fb]["w"].endswith("?")):
        p += 0.25
        r_plus.append("počinje pitanjem")
    if any(t in HOOK for t in first):
        p += 0.2
        r_plus.append("jake riječi na početku")
    if any(t.isdigit() or t in BROJEVI for t in first):
        p += 0.1
    if any(t in OBRACANJE for t in first):
        p += 0.1
        r_plus.append("obraća se gledatelju")
    if sn.pause_before(a) >= PAUZA_GRANICA:
        p += 0.15
    if first:
        if first[0] in sk.VEZNICI or first[0] in ZAMJENICE:
            p -= 0.35
            r_minus.append(f"počinje s „{w[a]['w']}“ (treba kontekst)")
        if POSTAPALICE.match(first[0]):
            p -= 0.2
            r_minus.append("počinje poštapalicom")
        if any(t in CAVRLJANJE for t in first):
            p -= 0.3
            r_minus.append("čavrljanje na početku")
    trenuci = sn.an.get("trenuci") or []
    for t in trenuci:
        try:
            t0, t1, oc = float(t["od"]), float(t["do"]), int(t.get("ocjena") or 3)
        except (KeyError, TypeError, ValueError):
            continue
        if t.get("vrsta") in ("hook", "citat", "emocija", "smijeh") and oc >= 4 and od - 1.0 <= t0 <= od + 5.0:
            p += 0.3
            r_plus.append(f"otvara ga trenutak ({t.get('vrsta')} {oc})")
            break
    p = _clamp(p)

    # --- zaokruženost
    z = 0.5
    last_w = w[b]["w"].rstrip("\"'”“»)")
    if last_w.endswith("?"):
        z -= 0.2
        r_minus.append("završava pitanjem")
    elif SENT_END.search(last_w):
        z += 0.2
    else:
        z -= 0.3
        r_minus.append("završava bez kraja rečenice")
    if b + 1 < len(w) and sn.nastavlja(b + 1):
        z -= 0.4
        r_minus.append("misao se nastavlja iza kraja")
    la, lb = _last_sentence(w, a, b)
    if any(t in ODJAVA for t in _toks(w, la, lb)):
        z -= 0.3
        r_minus.append("završava odjavom/pozdravom")
    unutra = sum(1 for i in range(a, b) if w[i + 1]["s"] - w[i]["e"] >= GRANICA_UNUTRA)
    if unutra:
        z -= 0.2 * min(unutra, 2)
        r_minus.append("duga stanka u sredini (dvije cjeline?)")
    if sn.pause_after(b) >= PAUZA_GRANICA:
        z += 0.2
    teme = sn.an.get("teme") or []
    if teme:
        shares = []
        for t in teme:
            try:
                shares.append(_overlap(od, do, float(t["od"]), float(t["do"])) / max(do - od, 0.1))
            except (KeyError, TypeError, ValueError):
                pass
        if shares:
            big = sorted(shares, reverse=True)
            if big[0] >= 0.95:
                z += 0.1
            elif len(big) > 1 and big[1] >= 0.08 and big[1] * (do - od) >= 3.0:
                z -= 0.25
                r_minus.append("prelazi u drugu temu")
    for t in trenuci:
        try:
            t0, t1 = float(t["od"]), float(t["do"])
        except (KeyError, TypeError, ValueError):
            continue
        if t.get("vrsta") in ("poanta", "savjet", "smijeh", "citat", "akcija") and od + 0.6 * (do - od) <= t1 <= do + 1.0:
            z += 0.15
            r_plus.append(f"završava poantom ({t.get('vrsta')})")
            break
    z = _clamp(z)

    # --- sadržaj
    toks = _toks(w, a, b)
    terms = [t[:5] for t in toks if len(t) >= 4 and t not in sk.STOP and not t.isdigit()]
    dens = len(set(terms)) / max(len(toks), 1)
    spec = sum(sn.idf.get(t, 0.0) for t in set(terms)) / max(len(toks), 1)
    gust = _clamp((dens - 0.25) / 0.4) * 0.6 + _clamp((spec - 0.6) / 1.4) * 0.4
    if any(t.isdigit() or t in BROJEVI for t in toks):
        gust = _clamp(gust + 0.1)
    best, extra = 0, 0
    for t in trenuci:
        try:
            t0, t1, oc = float(t["od"]), float(t["do"]), int(t.get("ocjena") or 3)
        except (KeyError, TypeError, ValueError):
            continue
        if _overlap(od, do, t0, t1) >= 0.5 * max(t1 - t0, 0.1):
            if oc > best:
                extra += 1 if best >= 3 else 0
                best = oc
            elif oc >= 3:
                extra += 1
    if trenuci:
        s = 0.65 * (best / 5.0) + 0.35 * gust + 0.08 * min(extra, 2)
        if best >= 4:
            r_plus.append(f"najjači trenutak {best}/5")
        elif best == 0:
            r_minus.append("nema označenih trenutaka")
    else:
        s = gust
    fill = sum(bool(POSTAPALICE.match(t)) for t in toks) / max(len(toks), 1)
    if fill > 0.08:
        s -= min(0.5, (fill - 0.08) * 4)
        r_minus.append("puno poštapalica")
    s = _clamp(s)

    # --- energija
    raw = max(do - od, 0.1)
    govor = (sn.cd[b + 1] - sn.cd[a]) / raw
    e = 0.5 + 0.6 * (govor - 0.75)
    if govor < 0.6:
        r_minus.append("puno tišine")
    if sn.med_db is not None:
        segs = [x for x in sn.an.get("odsjecci") or [] if _overlap(od, do, x.get("od", 0), x.get("do", 0)) > 0
                and isinstance(x.get("glasnoca_db"), (int, float))]
        if segs:
            rel = float(np.mean([x["glasnoca_db"] for x in segs])) - sn.med_db
            e += _clamp(rel / 6.0, -0.25, 0.25)
            brzo = sum(x.get("tempo") == "brzo" for x in segs) / len(segs)
            sporo = sum(x.get("tempo") == "sporo" for x in segs) / len(segs)
            e += 0.1 * brzo - 0.15 * sporo
    e = _clamp(e)

    # --- ukupno
    ukupno = 10.0 * (0.30 * p + 0.25 * z + 0.30 * s + 0.15 * e)
    lo, hi = IDEAL
    if dur < lo:
        ukupno *= 1.0 - 0.15 * _clamp((lo - dur) / max(lo - MIN_S, 1.0))
    elif dur > hi:
        ukupno *= 1.0 - 0.15 * _clamp((dur - hi) / max(MAX_S - hi, 1.0))
    losi = sn.an.get("losi_kadrovi") or []
    bad = sum(_overlap(od, do, float(x["od"]), float(x["do"])) for x in losi if "od" in x and "do" in x)
    if bad > 0.3 * raw:
        ukupno -= 1.0
        r_minus.append("loš kadar")
    dijelovi = {"pocetak": round(p * 10, 1), "zaokruzenost": round(z * 10, 1), "sadrzaj": round(s * 10, 1),
                "energija": round(float(e) * 10, 1)}
    razlozi = list(dict.fromkeys(r_plus)) + ["−" + x for x in dict.fromkeys(r_minus)]
    return round(_clamp(ukupno, 0.0, 10.0), 2), dijelovi, razlozi


# ---------------------------------------------------------------- kandidati
def kandidat(sn, a, b, izvor="shofe"):
    w = sn.words
    h, dijelovi, razlozi = ocijeni(sn, a, b)
    fa, fb = _first_sentence(w, a, b)
    la, lb = _last_sentence(w, a, b)
    gov = list(dict.fromkeys(w[i].get("g") for i in range(a, b + 1) if w[i].get("g")))
    od, do = w[a]["s"], w[b]["e"]
    tema = ""
    best = 0.0
    for t in sn.an.get("teme") or []:
        try:
            ov = _overlap(od, do, float(t["od"]), float(t["do"]))
        except (KeyError, TypeError, ValueError):
            continue
        if ov > best:
            best, tema = ov, t.get("naslov", "")
    return {
        "id": "",
        "od": round(od, 2), "do": round(do, 2),
        "trajanje": round(sn.est(a, b), 1),
        "rijeci": [a, b],
        "pocetak": _text(w, fa, fb), "kraj": _text(w, la, lb) if la > fb else "",
        "tekst": _text(w, a, b),
        "govornici": [sn.imena.get(g, g) for g in gov],
        "tema": tema,
        "heuristika": {"ocjena": h, **dijelovi, "razlozi": razlozi},
        "ocjena": None, "razlog": "", "naslov": "", "hook": "",
        "status": "prijedlog", "izvor": izvor,
    }


def svi_prozori(sn, min_s=MIN_S, max_s=MAX_S):
    """Svi nizovi cijelih misli od min_s do max_s sekundi → [(ocjena, a, b)] (indeksi riječi)."""
    out = []
    M = sn.misli
    for k0, m0 in enumerate(M):
        a = m0.idx[0]
        if sn.nastavlja(a):
            continue  # počinje rečenicom koja ovisi o prethodnoj
        for k1 in range(k0, len(M)):
            b = M[k1].idx[-1]
            d = sn.est(a, b)
            if d > max_s:
                break
            if sn.pjesme and any(_overlap(sn.words[a]["s"], sn.words[b]["e"], p0, p1) > 0 for p0, p1 in sn.pjesme):
                break  # dalje bi isječak uključio pjesmu
            if d >= min_s:
                h, _, _ = ocijeni(sn, a, b)
                out.append((h, a, b))
    return out


def odaberi(sn, prozori, broj, zauzeto=()):
    """Najbolji prvi, bez (velikog) preklapanja međusobno i sa zauzetim [(od, do)]."""
    taken = [tuple(x) for x in zauzeto]
    chosen = []
    for h, a, b in sorted(prozori, key=lambda x: (-x[0], x[1])):
        od, do = sn.words[a]["s"], sn.words[b]["e"]
        if any(_overlap(od, do, t0, t1) > PREKLAPANJE * min(do - od, t1 - t0) for t0, t1 in taken):
            continue
        chosen.append((a, b))
        taken.append((od, do))
        if len(chosen) >= broj:
            break
    return chosen


def next_id(data):
    nums = [int(m.group(1)) for c in data.get("isjecci", []) if (m := re.fullmatch(r"K(\d+)", str(c.get("id"))))]
    return max(nums, default=0) + 1


def find(data, spec):
    """'K3' / '3' / 'K1,K4' → popis isječaka."""
    out = []
    by = {str(c["id"]).upper(): c for c in data.get("isjecci", [])}
    for part in re.split(r"[,;\s]+", spec.strip()):
        if not part:
            continue
        key = part.upper() if part.upper().startswith("K") else f"K{part}"
        if key not in by:
            raise sadrzaj.Greska(f"nema isječka {part} (postoje: {', '.join(by) or 'nijedan'})")
        out.append(by[key])
    if not out:
        raise sadrzaj.Greska("koji isječak? primjer: K1,K3")
    return out


# ---------------------------------------------------------------- učitavanje
def ucitaj(proj):
    proj = Path(proj)
    if not (proj / "transcript.json").exists():
        die(f"nema {proj / 'transcript.json'}. Prvo pokreni transcribe.py")
    words = load_words(proj)
    if not words:
        die("transkript je prazan — nema govora za isječke")
    an = {}
    if (proj / "analiza.json").exists():
        try:
            an = load_json(proj / "analiza.json")
        except Exception:  # noqa: BLE001
            an = {}
    sn = Snimka(words, an, speaker_names(proj))
    import nastupi
    sn.nastupi = nastupi.active(nastupi.load(proj))
    sn.pjesme = [(n["od"], n["do"]) for n in sn.nastupi]
    sn.proj = proj
    return sn


# ---------------------------------------------------------------- isječak iz pjesme (M4.3b3)
def je_pjesma(c):
    return c.get("vrsta") == "pjesma"


def _nastup(sn, pid):
    for n in getattr(sn, "nastupi", []):
        if str(n["id"]).upper() == str(pid).upper():
            return n
    raise sadrzaj.Greska(f"nema pjesme {pid} (pjesme: {', '.join(n['id'] for n in getattr(sn, 'nastupi', [])) or 'nijedna'})")


def kandidat_pjesme(sn, n, od=None, do=None):
    """Isječak iz pjesme n (nastupi.json): najbolji refren 30–60 s (refren.py) ili zadane granice."""
    import refren
    src = Path(sn.proj) / "source.mp4"
    if od is None:
        r = refren.analyse_song(src, float(n["od"]), float(n["do"]))
    else:
        od, do = max(float(n["od"]), od), min(float(n["do"]), do)
        if do - od < 5:
            raise sadrzaj.Greska(f"isječak iz pjesme {n['id']} mora biti unutar pjesme "
                                 f"({fmt(n['od'])}–{fmt(n['do'])}) i trajati barem 5 s")
        r = {"od": round(od, 3), "do": round(do, 3), "refren": [], "razlog": "granice zadane ručno",
             "do_kraja": abs(do - float(n["do"])) < 0.05, "refren_sigurnost": 0.0, "na_taktu": False, "bpm": None}
    dur = r["do"] - r["od"]
    h = refren.heuristic_score(r, dur)
    naziv = n.get("naziv") or ""
    ime = f"„{naziv}“" if naziv else n["id"]
    return {
        "id": "", "vrsta": "pjesma", "nastup": n["id"],
        "od": r["od"], "do": r["do"], "trajanje": round(dur, 1),
        "pocetak": f"♪ pjesma {ime}", "kraj": "", "tekst": "",
        "govornici": [], "tema": naziv or "nastup benda",
        "refren": [list(x) for x in r["refren"]], "bpm": r.get("bpm"),
        "heuristika": {"ocjena": h, "pocetak": round(10 * r.get("refren_sigurnost", 0), 1),
                       "zaokruzenost": 10.0 if r.get("do_kraja") else 7.0, "sadrzaj": 7.0, "energija": 8.0,
                       "razlozi": [r["razlog"]] + (["rez na udarac"] if r.get("na_taktu") else [])},
        # Claude ne čuje pjesmu: Shofeova ocjena vrijedi dok je Claude ili Marko ne promijene
        "ocjena": round(h), "razlog": f"Nastup benda: {r['razlog']}.",
        "naslov": naziv, "hook": f"{naziv} uživo" if naziv else "", "status": "prijedlog", "izvor": "shofe",
    }


def kandidati_pjesama(sn, data=None, ispis=True):
    """Po jedan kandidat iz svake pjesme koja ga još nema."""
    have = {str(c.get("nastup")) for c in (data or {}).get("isjecci", []) if je_pjesma(c)}
    out = []
    for n in getattr(sn, "nastupi", []):
        if n["id"] in have:
            continue
        if ispis:
            print(f"Tražim refren u pjesmi {n['id']} ({fmt(n['od'])}–{fmt(n['do'])}) ...")
        out.append(kandidat_pjesme(sn, n))
    return out


def path_of(proj):
    return Path(proj) / DATOTEKA


def load(proj):
    p = path_of(proj)
    if not p.exists():
        return None
    return load_json(p)


def resnap(sn, c):
    """Ako je Claude ručno promijenio od/do, poravnaj na cijele rečenice i preračunaj. → poruka ili None."""
    w = sn.words
    a, b = (c.get("rijeci") or [None, None])[:2]
    try:
        od, do = float(c["od"]), float(c["do"])
    except (KeyError, TypeError, ValueError):
        raise sadrzaj.Greska(f"{c.get('id')}: 'od'/'do' moraju biti sekunde")
    if je_pjesma(c):   # isječak iz pjesme: po vremenu, unutar pjesme (bez riječi)
        n = _nastup(sn, c.get("nastup"))
        od2, do2 = max(od, float(n["od"])), min(do, float(n["do"]))
        if do2 - od2 < 5:
            raise sadrzaj.Greska(f"{c.get('id')}: isječak iz pjesme {n['id']} mora biti unutar pjesme "
                                 f"({fmt(n['od'])}–{fmt(n['do'])})")
        c["od"], c["do"], c["trajanje"] = round(od2, 3), round(do2, 3), round(do2 - od2, 1)
        if (od2, do2) != (od, do):
            return f"{c['id']}: granice pomaknute unutar pjesme {n['id']} ({fmt(od2)}–{fmt(do2)})"
        return None
    if a is not None and b is not None and 0 <= a <= b < len(w) and abs(w[a]["s"] - od) < 0.06 and abs(w[b]["e"] - do) < 0.06:
        return None
    idx = sadrzaj.words_in(w, od, do)
    if not idx:
        raise sadrzaj.Greska(f"{c.get('id')}: između {fmt(od)} i {fmt(do)} nema riječi")
    a, b = sadrzaj.sentence_bounds(w, idx[0], idx[-1])
    new = kandidat(sn, a, b, c.get("izvor", "shofe"))
    for key in ("id", "ocjena", "razlog", "naslov", "hook", "status", "napomena_marka", *serija.PREUZMI, "izrezi"):
        if key in c:
            new[key] = c[key]
    c.clear()
    c.update(new)
    return f"{c['id']}: granice poravnate na cijele rečenice ({fmt(c['od'])}–{fmt(c['do'])}, {c['trajanje']:.0f} s)"


# ---------------------------------------------------------------- provjera i ispis
def konacna(c):
    oc = c.get("ocjena")
    return (oc if isinstance(oc, (int, float)) else -1, c["heuristika"]["ocjena"])


def provjeri(sn, data, min_s=MIN_S, max_s=MAX_S):
    """→ (greške, upozorenja). Poravna ručno promijenjene granice i poreda isječke."""
    gr, up = [], []
    ids = set()
    for c in data.get("isjecci", []):
        cid = c.get("id")
        if not cid or cid in ids:
            gr.append(f"isječak bez jedinstvenog 'id' ({cid!r})")
        ids.add(cid)
        try:
            msg = resnap(sn, c)
            if msg:
                up.append(msg)
        except sadrzaj.Greska as e:
            gr.append(str(e))
            continue
        if c.get("status") not in STATUSI:
            gr.append(f"{cid}: status mora biti {', '.join(STATUSI)}")
        d = c["trajanje"]
        lo, hi = (PJESMA_S if je_pjesma(c) else (min_s, max_s))
        if d < 10 or d > 90:
            gr.append(f"{cid}: traje {d:.0f} s — isječak mora imati 10–90 s (cilj {lo:.0f}–{hi:.0f})")
        elif d < lo or d > hi:
            up.append(f"{cid}: traje {d:.0f} s (cilj {lo:.0f}–{hi:.0f} s)")
        if c.get("status") == "odbacen":
            continue
        oc = c.get("ocjena")
        if oc is None or oc == "":
            gr.append(f"{cid}: nema Claudeove ocjene (1–10)")
        elif not isinstance(oc, (int, float)) or isinstance(oc, bool) or not 1 <= oc <= 10:
            gr.append(f"{cid}: ocjena mora biti broj 1–10 (sada {oc!r})")
        raz = (c.get("razlog") or "").strip()
        if not raz:
            gr.append(f"{cid}: nema razloga (jedna rečenica zašto)")
        elif len(raz) > 220:
            up.append(f"{cid}: razlog je predug ({len(raz)} znakova) — jedna kratka rečenica")
        elif len(re.findall(r"[.!?](?:\s|$)", raz)) > 1:
            up.append(f"{cid}: razlog neka bude jedna rečenica")
        hook = (c.get("hook") or "").strip()
        if hook and len(hook.split()) > 8:
            up.append(f"{cid}: hook ima {len(hook.split())} riječi (3–7 je najbolje)")
    # preklapanja među onima koji nisu odbačeni
    live = [c for c in data.get("isjecci", []) if c.get("status") != "odbacen" and "trajanje" in c]
    for i, x in enumerate(live):
        for y in live[i + 1:]:
            ov = _overlap(x["od"], x["do"], y["od"], y["do"])
            if ov > 0.5 * min(x["do"] - x["od"], y["do"] - y["od"]):
                up.append(f"{x['id']} i {y['id']} se uvelike preklapaju — odbaci jedan ako govore isto")
    data["isjecci"].sort(key=lambda c: (c.get("status") == "odbacen", tuple(-v for v in konacna(c))))
    return gr, up


def tekst_popisa(data, cijeli=True):
    L = []
    cs = data.get("isjecci", [])
    rated = [c for c in cs if c.get("status") != "odbacen" and isinstance(c.get("ocjena"), (int, float))]
    L.append(f"Isječci: {len(cs)} kandidata ({sum(c['status'] == 'odobren' for c in cs)} odobreno, "
             f"{sum(c['status'] == 'odbacen' for c in cs)} odbačeno, {len(rated)} s Claudeovom ocjenom)")
    L.append("")
    for n, c in enumerate(cs, 1):
        oc = c.get("ocjena")
        ocs = f"{oc:g}/10" if isinstance(oc, (int, float)) else "—/10"
        stat = {"odobren": "  ✓ ODOBREN", "odbacen": "  ✗ odbačen"}.get(c.get("status"), "")
        gov = f"  [{', '.join(c['govornici'])}]" if c.get("govornici") else ""
        L.append(f"{c['id']:>4}  {fmt(c['od'])}–{fmt(c['do'])}  {c['trajanje']:4.0f} s  Claude {ocs}  "
                 f"Shofe {c['heuristika']['ocjena']:.1f}{gov}{stat}")
        if c.get("naslov"):
            L.append(f"      naslov: {c['naslov']}")
        if c.get("hook"):
            L.append(f"      hook:   {c['hook']}")
        if c.get("razlog"):
            L.append(f"      zašto:  {c['razlog']}")
        if c.get("tema"):
            L.append(f"      tema:   {c['tema']}")
        h = c["heuristika"]
        L.append(f"      Shofe:  početak {h['pocetak']:.0f}, zaokruženost {h['zaokruzenost']:.0f}, sadržaj "
                 f"{h['sadrzaj']:.0f}, energija {h['energija']:.0f}" + (f" — {'; '.join(h['razlozi'])}" if h['razlozi'] else ""))
        if c.get("napomena_marka"):
            L.append(f"      Marko:  {c['napomena_marka']}")
        if c.get("render"):
            L.append(f"      video: {serija.jedan_redak(c).strip()[2:]}")
        if je_pjesma(c):
            ref = ", ".join(f"{fmt(x)}–{fmt(y)}" for x, y in c.get("refren") or [])
            L.append(f"      pjesma: {c.get('nastup')}" + (f", {c['bpm']:.0f} BPM" if c.get("bpm") else "")
                     + (f", refren {ref}" if ref else "") + " — bez titlova, zvuk za glazbu")
        if cijeli and c.get("status") != "odbacen":
            for line in textwrap.wrap(c["tekst"], 100):
                L.append(f"      │ {line}")
        L.append("")
    return "\n".join(L)


def spremi(proj, data, pregled=False):
    save_json(path_of(proj), data)
    (Path(proj) / "isjecci.txt").write_text(tekst_popisa(data), encoding="utf-8")
    if pregled:   # isječak iz pjesme i refren na vremenskoj crti pregled.html
        import pregled as P
        P.refresh(proj)


# ---------------------------------------------------------------- naredbe
def cmd_predlozi(proj, sn, a):
    old = load(proj)
    if old and not a.ponovo:
        die(f"{DATOTEKA} već postoji. Za još kandidata: isjecci.py {proj} novi; "
            f"za sve ispočetka (gubi ocjene i odabir): predlozi --ponovo")
    pro = svi_prozori(sn, a.min, a.max)
    chosen = odaberi(sn, pro, a.broj)
    data = {"shofe": version(), "napravljeno": _dt.datetime.now().isoformat(timespec="seconds"),
            "postavke": {"min_s": a.min, "max_s": a.max}, "upute": UPUTE, "isjecci": []}
    for n, (x, y) in enumerate(chosen, 1):
        c = kandidat(sn, x, y)
        c["id"] = f"K{n}"
        data["isjecci"].append(c)
    pj = kandidati_pjesama(sn, data)
    for c in pj:
        c["id"] = f"K{next_id(data)}"
        data["isjecci"].append(c)
        print(f"{c['id']}: iz pjesme {c['nastup']} {fmt(c['od'])}–{fmt(c['do'])} ({c['trajanje']:.0f} s) — "
              f"{c['heuristika']['razlozi'][0]}")
    spremi(proj, data, pregled=bool(pj))
    dur = sn.words[-1]["e"] - sn.words[0]["s"]
    print(f"Snimka {fmt(dur)}, {len(sn.misli)} misli, {len(pro)} mogućih isječaka od {a.min:.0f}–{a.max:.0f} s.")
    if not chosen and not data["isjecci"]:
        print(f"Nema nijednog niza cijelih misli od {a.min:.0f}–{a.max:.0f} s (snimka prekratka?). "
              f"Probaj --min 10 ili napravi običan reel (plan.py).")
        return 1
    if len(chosen) < 5:
        print(f"Napomena: samo {len(chosen)} {isjecaka(len(chosen))} bez preklapanja — snimka je kratka za 5–10 isječaka.")
    print(f"Predloženo {len(chosen)} kandidata → {path_of(proj)} (čitljivo: isjecci.txt)\n")
    print(tekst_popisa(data))
    print("Claude: " + UPUTE)
    return 1  # Claude još treba ocijeniti


def cmd_provjeri(proj, sn, a, quiet=False):
    data = load(proj)
    if data is None:
        die(f"nema {DATOTEKA}. Prvo: python isjecci.py {proj} predlozi")
    st = data.get("postavke") or {}
    gr, up = provjeri(sn, data, st.get("min_s", MIN_S), st.get("max_s", MAX_S))
    spremi(proj, data)
    if not quiet:
        print(tekst_popisa(data, cijeli=a.naredba != "provjeri"))
    for u in up:
        print(f"Upozorenje: {u}")
    if gr:
        print(f"\n{len(gr)} grešaka u {DATOTEKA}:")
        for g in gr:
            print(f"  - {g}")
        return 1
    live = [c for c in data["isjecci"] if c["status"] != "odbacen"]
    top = [c["id"] for c in live if c["ocjena"] >= 7]
    print(f"\nU redu: {len(live)} isječaka ocijenjeno. Za objavu (ocjena ≥ 7): {', '.join(top) or 'nijedan'}.")
    if len(top) < 5 and len(live) >= 5:
        print("Manje od 5 dobrih — predloži još: isjecci.py novi")
    return 0


def cmd_novi(proj, sn, a):
    data = load(proj)
    if data is None:
        return cmd_predlozi(proj, sn, a)
    st = data.get("postavke") or {}
    lo, hi = st.get("min_s", a.min), st.get("max_s", a.max)
    zauzeto = [(c["od"], c["do"]) for c in data.get("isjecci", [])]
    chosen = odaberi(sn, svi_prozori(sn, lo, hi), a.broj, zauzeto)
    pj = kandidati_pjesama(sn, data)
    for c in pj:
        c["id"] = f"K{next_id(data)}"
        data["isjecci"].append(c)
    if pj and not chosen:
        spremi(proj, data, pregled=True)
        print(f"Dodano {len(pj)} isječaka iz pjesama: {', '.join(c['id'] for c in pj)}")
        return 0
    if not chosen:
        print("Nema novih isječaka koji se ne preklapaju s postojećima (i odbačenima). "
              "Dodaj svoj: isjecci.py dodaj --od … --do …")
        return 0
    n = next_id(data)
    new = []
    for x, y in chosen:
        c = kandidat(sn, x, y)
        c["id"] = f"K{n}"
        n += 1
        data["isjecci"].append(c)
        new.append(c)
    spremi(proj, data, pregled=bool(pj))
    new = pj + new
    print(f"Dodano {len(new)} novih kandidata: {', '.join(c['id'] for c in new)}\n")
    print(tekst_popisa({"isjecci": new}))
    print("Claude: ocijeni nove (ocjena, razlog), zatim isjecci.py provjeri.")
    return 1


def cmd_dodaj(proj, sn, a):
    data = load(proj) or {"shofe": version(), "napravljeno": _dt.datetime.now().isoformat(timespec="seconds"),
                          "postavke": {"min_s": a.min, "max_s": a.max}, "upute": UPUTE, "isjecci": []}
    if not a.od:
        raise sadrzaj.Greska("dodaj treba --od \"početak citata\" (i po želji --do \"kraj citata\")")
    old = find(data, a.umjesto)[0] if a.umjesto else None
    alt = None
    if (Path(proj) / "edit.json").exists():
        try:
            from uredi import corrected_forms
            alt = corrected_forms(sn.words, load_json(Path(proj) / "edit.json"))
        except Exception:  # noqa: BLE001
            alt = None
    tr = sadrzaj.Transkript(sn.words, alt)
    i, j = sadrzaj.by_quote(tr, a.od, a.do, a.pojava)
    i, j = sadrzaj.sentence_bounds(sn.words, i, j)
    c = kandidat(sn, i, j, izvor="claude")
    if old:
        for key in ("naslov", "hook", "status", "napomena_marka", *serija.PREUZMI, "izrezi"):
            if old.get(key):
                c[key] = old[key]
        c["id"] = old["id"]
        c["izvor"] = old.get("izvor", "shofe")
        data["isjecci"][data["isjecci"].index(old)] = c
        print(f"{c['id']} sada: {fmt(c['od'])}–{fmt(c['do'])}, {c['trajanje']:.0f} s (ocjenu upiši ponovno)")
    else:
        c["id"] = f"K{next_id(data)}"
        data["isjecci"].append(c)
        print(f"Dodan {c['id']}: {fmt(c['od'])}–{fmt(c['do'])}, {c['trajanje']:.0f} s")
    st = data.get("postavke") or {}
    if not st.get("min_s", MIN_S) <= c["trajanje"] <= st.get("max_s", MAX_S):
        print(f"Napomena: traje {c['trajanje']:.0f} s, izvan cilja {st.get('min_s', MIN_S):.0f}–{st.get('max_s', MAX_S):.0f} s")
    for note in sadrzaj.edge_notes(sn.words, list(range(i, j + 1))):
        print(f"Napomena: {note}")
    print(f"  početak: {c['pocetak']}\n  kraj:    {c['kraj'] or c['pocetak']}")
    spremi(proj, data)
    print("Claude: upiši ocjenu i razlog, zatim isjecci.py provjeri.")
    return 0


def cmd_pjesma(proj, sn, a):
    """isjecci.py projekt pjesma P1 [--od 1:20 --do 2:05] [--umjesto K3]: isječak iz pjesme (refren ili granice)."""
    if not getattr(sn, "nastupi", None):
        raise sadrzaj.Greska(f"u snimci nema pjesama (prvo: python nastupi.py {proj})")
    n = _nastup(sn, a.ids or sn.nastupi[0]["id"])
    data = load(proj) or {"shofe": version(), "napravljeno": _dt.datetime.now().isoformat(timespec="seconds"),
                          "postavke": {"min_s": a.min, "max_s": a.max}, "upute": UPUTE, "isjecci": []}
    od = do = None
    if a.od or a.do:
        import uredi
        try:
            od = uredi.parse_time(a.od) if a.od else float(n["od"])
            do = uredi.parse_time(a.do) if a.do else float(n["do"])
        except Exception:  # noqa: BLE001
            raise sadrzaj.Greska("pjesma: --od/--do su vremena snimke, npr. --od 12:40 --do 13:25")
    c = kandidat_pjesme(sn, n, od, do)
    old = find(data, a.umjesto)[0] if a.umjesto else next(
        (x for x in data["isjecci"] if je_pjesma(x) and x.get("nastup") == n["id"] and x.get("status") != "odbacen"),
        None)
    if old:
        for key in ("naslov", "hook", "status", "napomena_marka", *serija.PREUZMI, "izrezi"):
            if old.get(key):
                c[key] = old[key]
        c["id"] = old["id"]
        data["isjecci"][data["isjecci"].index(old)] = c
    else:
        c["id"] = f"K{next_id(data)}"
        data["isjecci"].append(c)
    spremi(proj, data, pregled=True)
    print(f"{c['id']}: iz pjesme {n['id']} {fmt(c['od'])}–{fmt(c['do'])} ({c['trajanje']:.0f} s) — "
          f"{c['heuristika']['razlozi'][0]}")
    if c.get("refren"):
        print("   refren: " + ", ".join(f"{fmt(x)}–{fmt(y)}" for x, y in c["refren"]))
    if not (c.get("hook") or "").strip():
        print(f"Claude: upiši \"naslov\" i \"hook\" za {c['id']} (npr. naziv pjesme i benda) — "
              f"naziv pjesme: python nastupi.py {proj} naziv {n['id']} \"Bend – Pjesma\"")
    return 0


def cmd_status(proj, sn, a, status):
    data = load(proj)
    if data is None:
        die(f"nema {DATOTEKA}. Prvo: python isjecci.py {proj} predlozi")
    cs = find(data, a.ids or "")
    for c in cs:
        c["status"] = status
        if a.razlog:
            c["napomena_marka"] = a.razlog
    provjeri(sn, data)
    spremi(proj, data)
    rijec = "Odobreno" if status == "odobren" else "Odbačeno" if status == "odbacen" else "Vraćeno"
    print(f"{rijec}: {', '.join(c['id'] for c in cs)}")
    odob = [c["id"] for c in data["isjecci"] if c["status"] == "odobren"]
    print(f"Odobreni isječci: {', '.join(odob) or 'nijedan'}")
    return 0


def cmd_render(proj, sn, a):
    data = load(proj)
    if data is None:
        die(f"nema {DATOTEKA}. Prvo: python isjecci.py {proj} predlozi")
    st = data.get("postavke") or {}
    gr, _ = provjeri(sn, data, st.get("min_s", MIN_S), st.get("max_s", MAX_S))
    gr = [g for g in gr if "ocjen" not in g and "razlog" not in g]  # ocjene nisu nužne za render
    try:
        cs = serija.odaberi_isjecke(data, a.ids or None, find)
        gr += [g.replace("<projekt>", str(proj)) for g in serija.provjeri_spremnost(cs, a.bez_hooka)]
        if a.stil:
            gr += [g for g in serija.provjeri_spremnost([{"id": "--stil", "stil": a.stil}], True)]
    except serija.Greska as e:
        raise sadrzaj.Greska(str(e))
    if gr:
        print(f"Ne mogu renderirati ({len(gr)}):")
        for g in gr:
            print(f"  - {g}")
        return 1
    nije = [c["id"] for c in cs if c.get("status") != "odobren"]
    if nije and not a.kadar:
        print(f"Napomena: {', '.join(nije)} {'nije odobren' if len(nije) == 1 else 'nisu odobreni'} "
              f"(renderiram jer je izričito navedeno)")
    try:
        gotovi = serija.renderiraj(proj, data, cs, brzo=a.brzo, kvaliteta=a.kvaliteta, stil=a.stil, kadar=a.kadar,
                                   oblik=a.format)
    except serija.Greska as e:
        raise sadrzaj.Greska(str(e))
    if a.kadar:
        return 0
    spremi(proj, data)
    pr = serija.pregled(proj, gotovi)
    print(f"\nGotovo {len(gotovi)} {isjecaka(len(gotovi))} u {Path(proj) / serija.MAPA}:")
    for c, res in gotovi:
        print(f"  {c['id']}  {res['trajanje']:4.0f} s  {Path(res['video']).name}")
    for u in serija.provjera_trajanja(gotovi, st.get("min_s", MIN_S), st.get("max_s", MAX_S)):
        print(f"Upozorenje: {u}")
    if pr:
        print(f"Pregled (prva sekunda s hookom + sredina svakog isječka): {pr}")
    print("Uz svaki video: .srt (titlovi za YouTube), .fcpxml (DaVinci), .edit.json (što je montirano).")
    print(f"Tekstovi za objavu (Instagram, TikTok, YouTube): python objava.py \"{proj}\" isjecci")
    print(f"Naslovne sličice (najbolji kadar + tekst, 9:16 i 16:9): python naslovna.py \"{proj}\" isjecci")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Kandidati za isječke za mreže (isjecci.json)")
    ap.add_argument("projekt")
    ap.add_argument("naredba", nargs="?", default="",
                    help="predlozi | provjeri | popis | novi | dodaj | pjesma | odobri | odbaci | vrati | render")
    ap.add_argument("ids", nargs="?", default="", help="za odobri/odbaci/vrati: npr. K1,K3; za pjesma: P1")
    ap.add_argument("--broj", type=int, default=None, help="koliko kandidata (predlozi: 10, novi: 5)")
    ap.add_argument("--min", type=float, default=MIN_S, help="najkraći isječak u sekundama (20)")
    ap.add_argument("--max", type=float, default=MAX_S, help="najdulji isječak u sekundama (60)")
    ap.add_argument("--ponovo", action="store_true", help="predlozi: sve ispočetka (briše ocjene i odabir)")
    ap.add_argument("--od", help="dodaj: doslovni citat početka; pjesma: vrijeme snimke (12:40)")
    ap.add_argument("--do", help="dodaj: doslovni citat kraja; pjesma: vrijeme snimke (13:25)")
    ap.add_argument("--pojava", type=int, help="dodaj: koja pojava citata (ako ih ima više)")
    ap.add_argument("--umjesto", help="dodaj: zamijeni granice postojećeg isječka (npr. K3)")
    ap.add_argument("--razlog", help="odbaci/odobri: Markova napomena")
    ap.add_argument("--brzo", action="store_true", help="render: brzi pregled u pola rezolucije")
    ap.add_argument("--kvaliteta", default="dobra", choices=["dobra", "visoka"], help="render: kvaliteta")
    ap.add_argument("--stil", help="render: isti stil za sve isječke u ovom renderu")
    ap.add_argument("--kadar", help="render: samo slike kadrova (sekunde isječka, npr. 1,10)")
    ap.add_argument("--bez-hooka", action="store_true", help="render: dopusti isječke bez hooka")
    ap.add_argument("--format", choices=["9:16", "16:9"], default=None,
                    help="render podcasta: 9:16 iz originalnih kamera (zadano) ili 16:9 iz programa")
    a = ap.parse_args()
    proj = Path(a.projekt)
    if not proj.is_dir():
        die(f"nema mape projekta {proj}")
    nar = fold(a.naredba) or ("provjeri" if path_of(proj).exists() else "predlozi")
    alias = {"predlozi": "predlozi", "predlozii": "predlozi", "provjeri": "provjeri", "popis": "popis",
             "novi": "novi", "jos": "novi", "dodaj": "dodaj", "odobri": "odobri", "odbaci": "odbaci",
             "vrati": "vrati", "render": "render", "renderiraj": "render", "napravi": "render",
             "pjesma": "pjesma", "refren": "pjesma"}
    if nar not in alias:
        die(f"nepoznata naredba '{a.naredba}' (predlozi, provjeri, popis, novi, dodaj, pjesma, odobri, odbaci, vrati, "
            "render)")
    a.naredba = alias[nar]
    if a.min < 5 or a.max <= a.min:
        die("--min mora biti barem 5 s, a --max veći od --min")
    if a.broj is None:
        a.broj = 5 if a.naredba == "novi" else 10
    sn = ucitaj(proj)
    try:
        if a.naredba == "predlozi":
            code = cmd_predlozi(proj, sn, a)
        elif a.naredba in ("provjeri", "popis"):
            code = cmd_provjeri(proj, sn, a)
            if a.naredba == "popis":
                code = 0
        elif a.naredba == "novi":
            code = cmd_novi(proj, sn, a)
        elif a.naredba == "dodaj":
            code = cmd_dodaj(proj, sn, a)
        elif a.naredba == "render":
            code = cmd_render(proj, sn, a)
        elif a.naredba == "pjesma":
            code = cmd_pjesma(proj, sn, a)
        else:
            code = cmd_status(proj, sn, a, {"odobri": "odobren", "odbaci": "odbacen", "vrati": "prijedlog"}[a.naredba])
    except sadrzaj.Greska as e:
        die(str(e))
    sys.exit(code)


if __name__ == "__main__":
    main()
