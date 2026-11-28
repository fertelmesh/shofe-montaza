"""Prijedlog efekata po tekstu (M5.3): Shofe pročita gotov video (riječi koje ostaju, rezovi, teme i trenuci
iz analiza.json) i predloži efekte po pravilima montažera; Claude pregleda svaki prijedlog (smisao, ton,
ime u oznaci), pa `primijeni` upiše odabrane u edit.json jednom naredbom (jedan `uredi.py vrati` sve poništi).

  python efekti.py projekt predlozi [--gustoca malo|normalno|puno]   → efekti_prijedlog.json + .txt
  python efekti.py projekt predlozi popis                            ponovno ispiši prijedlog
  python efekti.py projekt predlozi primijeni [P1,P4]                upiši odabrane (uzmi: true) u edit.json

Pravila (iz teksta, hrvatski):
  brojka (cijena, posto, godine, kW …)            → trzaj na brojci i jedinici
  predstavljanje („ja sam Marko“, „ovo je Ivan“)  → zamrzni s oznakom (ime)
  naglasak („najvažnije“, „zapamti“, „nikad“ …)   → guranje kroz rečenicu (kratka rečenica: trzaj)
  iznenađenje („čekaj“, „zamisli“, „nevjerojatno“) → vertigo kroz rečenicu
  otkrivanje („i gotovo“, „eto ga“, „bum“)        → pad
  prošlost („nekad“, „sjećam se“, „prije 20 godina“) → film kroz rečenicu
  nabrajanje („prvo“, „drugi korak“, „na kraju“) na rezu → rolete / vrata / klizanje
  nova tema (teme iz analiza.json, „a sad“, „idemo dalje“) na rezu → zamah (energično) ili pretapanje (mirno)
  trenuci iz analiza.json: hook → trzaj, poanta/citat/emocija/savjet → guranje, smijeh → pad
Gustoća (iz vodiča za kratke videe: 2–3 „prekida“ na 15–30 s, ne svakih pola sekunde): kamera najviše
1 na ~8 s i 3 s razmaka, prijelaz najviše 1 na ~20 s, boja (film/retro) 1 + 1 na 2 min; ista vrsta zuma ne
dvaput unutar 6 s; ništa za vrijeme pjesme; zamrzni s oznakom ne za vrijeme hook naslova.
"""
import copy
import re

import efekti
import prijelazi
from common import die, fmt_time, load_json, save_json
from sadrzaj import SENT_END, fold

DATOTEKA = "efekti_prijedlog.json"
TEKST = "efekti_prijedlog.txt"
GUSTOCA = {"malo": 0.6, "normalno": 1.0, "puno": 1.6}
MIRNI_STILOVI = {"cisto", "kino", "podcast"}
PRAG = 5.0                  # ocjena ispod ovoga Shofe sam ne uzima (Claude može)
KAMERA_RAZMAK = 3.0         # s od početka do početka dvaju efekata kamere
ISTI_RAZMAK = 6.0           # ista vrsta zuma ne ponavlja se unutar 6 s
PRIJELAZ_RAZMAK = 1.0       # prijelaz i efekt kamere ne odmah jedan uz drugi
REZ_BLIZU = 1.5             # rez smije biti najviše 1,5 s ispred rečenice/teme

# ---------------------------------------------------------------- rječnik pravila (presavijeni oblici)
NAGLASAK = {"najvaznije", "najvazniji", "najvaznija", "kljucno", "kljucna", "kljucni", "zapamti", "zapamtite",
            "obavezno", "obavezni", "nikad", "nikada", "uvijek", "tajna", "trik", "greska", "greske",
            "pogreska", "besplatno", "besplatna", "jedini", "jedina", "jedino", "najbolji", "najbolja",
            "najbolje", "najgore", "najgori", "bitno", "pazite", "garantiram", "definitivno"}
IZNENADJENJE = [("cekaj",), ("cekajte",), ("zamisli",), ("zamislite",), ("nevjerojatno",), ("nevjerojatan",),
                ("vjerovali", "ili", "ne"), ("ne", "bi", "vjerovali"), ("sok",), ("ludo",), ("ludilo",), ("wow",),
                ("ozbiljno",)]
OTKRIVANJE = [("bum",), ("eto", "ga"), ("evo", "ga"), ("i", "gotovo"), ("i", "to", "je", "to"), ("voila",),
              ("tadaa",), ("eto", "vidite")]
PROSLOST = [("nekad",), ("nekada",), ("sjecam", "se"), ("u", "moje", "vrijeme"), ("kad", "sam", "bio", "mali"),
            ("kad", "sam", "bila", "mala"), ("davno",), ("davne",), ("prije", "*", "godina"),
            ("kao", "klinac"), ("u", "mladosti"), ("tih", "godina")]
PREDSTAVLJANJE = [("ja", "sam"), ("zovem", "se"), ("ovo", "je"), ("s", "nama", "je"), ("nas", "gost"),
                  ("moj", "gost"), ("nasa", "gosca"), ("nasa", "gost"), ("upoznajte",)]
NABRAJANJE = [("prvo",), ("drugo",), ("trece",), ("cetvrto",), ("peto",), ("prvi", "korak"), ("drugi", "korak"),
              ("treci", "korak"), ("sljedeci", "korak"), ("zadnji", "korak"), ("korak", "broj"), ("na", "kraju"),
              ("za", "kraj"), ("i", "za", "kraj")]
NOVA_TEMA = [("a", "sad"), ("e", "sad"), ("idemo", "dalje"), ("sad", "idemo"), ("druga", "stvar"),
             ("sto", "se", "tice"), ("promjena", "teme"), ("prijedjimo", "na"), ("sljedeca", "stvar")]
BROJ_RIJECI = {"dva", "dvije", "tri", "cetiri", "pet", "sest", "sedam", "osam", "devet", "deset", "jedanaest",
               "dvanaest", "petnaest", "dvadeset", "trideset", "cetrdeset", "pedeset", "sezdeset", "sedamdeset",
               "osamdeset", "devedeset", "sto", "stotinu", "dvjesto", "tristo", "petsto", "tisucu", "tisuca",
               "tisuce", "milijun", "milijuna", "pola", "polovicu", "jedan", "jedna", "jednu"}
JEDINICE = {"eura", "euro", "eur", "kuna", "kune", "posto", "postotak", "godina", "godine", "godinu", "mjeseci",
            "mjeseca", "dana", "sati", "sat", "minuta", "minute", "sekundi", "kilograma", "kila", "kg", "kilovata",
            "kw", "kwh", "vata", "stupnjeva", "metara", "metra", "kvadrata", "puta", "litara", "dolara",
            "komada", "ljudi", "klima", "klime", "kn"}
CAP_POVEZNICE = {"iz", "s", "sa", "od"}       # „Marko iz Kutine“


def _match(fs, k, pat):
    """Odgovara li niz presavijenih riječi fs od k uzorku (`*` = bilo koja riječ)."""
    if k + len(pat) > len(fs):
        return False
    return all(p == "*" or fs[k + j] == p for j, p in enumerate(pat))


def _find(fs, pats):
    for k in range(len(fs)):
        for pat in pats:
            if _match(fs, k, pat):
                return k, k + len(pat) - 1
    return None


def _je_broj(f, w):
    return bool(re.search(r"\d", w)) or f in BROJ_RIJECI


# ---------------------------------------------------------------- gotov video
class Video:
    """Riječi koje ostaju u videu (s ispravljenim tekstom), rečenice, rezovi i trajanje gotovog videa."""

    def __init__(self, words, edit, pj, analiza=None):
        import render
        self.words, self.edit, self.pj = words, edit, pj
        self.analiza = analiza or {}
        st = render.resolve_style(edit)
        self.stil = (edit.get("stil") or "suncani").lower()
        self.cuts, kept, self.total = render.build_cuts(words, edit, st, pj["fps"], pj["duration"])
        self.speed = float(edit.get("brzina") or 1.0)
        songs, _ = render.song_spans(edit)
        self.songs = [(a, b) for a, b, _ in songs]
        starts = [c["a"] for c in self.cuts]
        vw = []
        for item in kept:
            # ispravljen tekst koji nije 1:1 s riječima: izvorne riječi (vrijeme i tekst)
            pairs = [(i, words[i]["w"]) for i in item[0]] if isinstance(item[0], list) else [item]
            for i, txt in pairs:
                w = words[i]
                mid = (w["s"] + w["e"]) / 2
                if any(a <= mid < b for a, b in self.songs):
                    continue
                os_ = render.to_out(w["s"], self.cuts, starts)
                oe = render.to_out(w["e"], self.cuts, starts)
                if os_ is None or oe is None:
                    continue
                vw.append({"i": i, "w": txt or w["w"], "f": fold(txt or w["w"]), "s": w["s"], "e": w["e"],
                           "os": os_, "oe": oe})
        vw.sort(key=lambda x: x["s"])
        self.vw = [x for x in vw if x["f"]]
        self.recenice = []
        cur = []
        for k, x in enumerate(self.vw):
            if cur and (SENT_END.search(cur[-1]["w"]) or x["s"] - cur[-1]["e"] > 0.8):
                self.recenice.append(cur)
                cur = []
            cur.append(x)
        if cur:
            self.recenice.append(cur)
        self.rezovi = prijelazi.granice(self.cuts)    # (k, kraj A, početak B, vrijeme reza)
        self.hook_do = min(float(edit.get("hook_trajanje") or 3.0), self.total) if (edit.get("hook") or "").strip() \
            else 0.0

    def konacno(self, t):
        """Vrijeme gotovog videa (prije brzine) → vrijeme koje Marko gleda (brzina, špica)."""
        return efekti.to_final(self.edit, self.words, self.pj, {"s": t, "e": t})[0]

    def rez_ispred(self, x):
        """Rez neposredno ispred riječi x (najviše REZ_BLIZU s): (k, od, do, t) ili None."""
        best = None
        for k, a, b, t in self.rezovi:
            d = x["os"] - t
            if -0.05 <= d <= REZ_BLIZU and (best is None or d < best[0]):
                best = (d, (k, a, b, t))
        return best[1] if best else None


def _tekst(sent, a=None, b=None):
    out = []
    for k, x in enumerate(sent):
        t = x["w"]
        if k == a:
            t = "[" + t
        if k == b:
            t = t + "]"
        out.append(t)
    return " ".join(out)


def _kandidat(v, tip, sent, a, b, pravilo, ocjena, razlog, od=None, do=None, parametri=None, rez=None):
    """Prijedlog: izvorna vremena od/do (kao edit.json), vremena gotovog videa s/e za pravila gustoće."""
    if rez:
        k, ra, rb, t = rez
        return {"tip": tip, "od": round(ra, 3), "do": round(rb, 3), "s": t, "e": t, "pravilo": pravilo,
                "ocjena": ocjena, "razlog": razlog, "parametri": parametri or {},
                "tekst": "… " + _tekst(sent, a, b), "rez": k}
    x0, x1 = sent[a], sent[b]
    od = x0["s"] - 0.05 if od is None else od
    do = x1["e"] + 0.12 if do is None else do
    return {"tip": tip, "od": round(od, 3), "do": round(do, 3), "s": x0["os"] - 0.05, "e": x1["oe"] + 0.12,
            "pravilo": pravilo, "ocjena": ocjena, "razlog": razlog, "parametri": parametri or {},
            "tekst": _tekst(sent, a, b)}


def _do_kraja(sent, k, najvise):
    """Indeks zadnje riječi od k do kraja rečenice, a da dio ne bude dulji od `najvise` s."""
    j = k
    while j + 1 < len(sent) and sent[j + 1]["oe"] - sent[k]["os"] <= najvise:
        j += 1
    return j


def _ime(sent, k):
    """Ime iza „ja sam“ / „ovo je“: riječi s velikim slovom (+ „iz Kutine“) → (zadnji indeks, tekst)."""
    j, parts = k, []
    while j < len(sent):
        w = sent[j]["w"].strip(",.!?;:„“\"'()")
        if w[:1].isupper():
            parts.append(w)
        elif w.lower() in CAP_POVEZNICE and parts and j + 1 < len(sent) and sent[j + 1]["w"][:1].isupper():
            parts.append(w.lower())
        else:
            break
        if sent[j]["w"].endswith((",", ".", "!", "?")) or len(parts) >= 4:
            break
        j += 1
    if not parts or parts[-1] in CAP_POVEZNICE:
        return None
    return k + len(parts) - 1, " ".join(parts)


def kandidati(v):
    """Svi kandidati iz teksta, trenutaka i tema (prije pravila gustoće)."""
    out = []
    energicno = v.stil not in MIRNI_STILOVI
    nab_tipovi = ["rolete", "vrata", "klizanje"]
    n_nab = 0
    teme_od = sorted(float(t["od"]) for t in (v.analiza.get("teme") or [])[1:] if "od" in t)
    for si, sent in enumerate(v.recenice):
        fs = [x["f"] for x in sent]
        # brojke (+ jedinica): trzaj na brojci
        for k, x in enumerate(sent):
            if not _je_broj(x["f"], x["w"]):
                continue
            j = k
            while j + 1 < len(sent) and _je_broj(sent[j + 1]["f"], sent[j + 1]["w"]):
                j += 1
            unit = next((u for u in range(j + 1, min(j + 3, len(sent))) if sent[u]["f"] in JEDINICE), None)
            ima_broj = any(re.search(r"\d", sent[q]["w"]) for q in range(k, j + 1))
            if unit is None and not ima_broj:
                continue
            if unit is None and x["f"] in {"jedan", "jedna", "jednu"}:
                continue
            b = unit if unit is not None else j
            c = _kandidat(v, "trzaj", sent, k, b, "brojka", 7.0,
                          f"brojka „{' '.join(s['w'] for s in sent[k:b + 1])}“: trzaj je istakne")
            c["do"] = round(max(c["do"], sent[k]["s"] + 0.8), 3)
            c["e"] = max(c["e"], sent[k]["os"] + 0.8)
            out.append(c)
            break
        # predstavljanje: zamrzni + oznaka s imenom
        h = _find(fs, PREDSTAVLJANJE)
        if h and h[1] + 1 < len(sent):
            im = _ime(sent, h[1] + 1)
            if im:
                j, ime = im
                c = _kandidat(v, "zamrzni", sent, h[1] + 1, j, "predstavljanje", 8.0,
                              f"predstavlja se „{ime}“: zamrzni s imenom", parametri={"oznaka": ime})
                c["do"] = round(sent[h[1] + 1]["s"] + 1.4, 3)
                c["e"] = sent[h[1] + 1]["os"] + 1.4
                c["od"] = round(sent[h[1] + 1]["s"] - 0.05, 3)
                c["s"] = sent[h[1] + 1]["os"] - 0.05
                out.append(c)
        # naglasak: guranje kroz rečenicu (kratka: trzaj na riječi)
        k = next((q for q, f in enumerate(fs) if f in NAGLASAK), None)
        if k is not None:
            a = 0 if sent[k]["os"] - sent[0]["os"] < 2.5 else k
            b = _do_kraja(sent, a, 5.0)
            dur = sent[b]["oe"] - sent[a]["os"]
            if dur >= 1.5:
                out.append(_kandidat(v, "guranje", sent, a, b, "naglasak", 6.0,
                                     f"naglašena rečenica („{sent[k]['w']}“): polagani zum prema licu"))
            else:
                out.append(_kandidat(v, "trzaj", sent, k, _do_kraja(sent, k, 1.2), "naglasak", 6.0,
                                     f"udarna riječ „{sent[k]['w']}“: trzaj"))
        # iznenađenje: vertigo
        h = _find(fs, IZNENADJENJE)
        if h:
            b = _do_kraja(sent, h[0], 3.0)
            c = _kandidat(v, "vertigo", sent, h[0], b, "iznenađenje", 6.0,
                          f"iznenađenje („{' '.join(s['w'] for s in sent[h[0]:h[1] + 1])}“): vertigo")
            if c["e"] - c["s"] < 1.0:
                c["do"] = round(sent[h[0]]["s"] + 1.1, 3)
                c["e"] = sent[h[0]]["os"] + 1.1
            out.append(c)
        # otkrivanje: pad
        h = _find(fs, OTKRIVANJE)
        if h:
            c = _kandidat(v, "pad", sent, h[0], h[1], "otkrivanje", 5.5,
                          f"„{' '.join(s['w'] for s in sent[h[0]:h[1] + 1])}“: pad zuma kao „bum“")
            c["do"] = round(max(c["do"], sent[h[0]]["s"] + 0.8), 3)
            c["e"] = max(c["e"], sent[h[0]]["os"] + 0.8)
            out.append(c)
        # prošlost: film kroz rečenicu
        h = _find(fs, PROSLOST)
        if h:
            b = _do_kraja(sent, 0, 8.0)
            out.append(_kandidat(v, "film", sent, 0, b, "prošlost", 5.0,
                                 f"priča iz prošlosti („{' '.join(s['w'] for s in sent[h[0]:h[1] + 1])}“): stari film"))
        # nabrajanje / nova tema na rezu ispred rečenice
        rez = v.rez_ispred(sent[0])
        if rez:
            if _find(fs[:4], NABRAJANJE) and _find(fs[:4], NABRAJANJE)[0] <= 1:
                tip = nab_tipovi[n_nab % len(nab_tipovi)]
                n_nab += 1
                out.append(_kandidat(v, tip, sent, 0, min(2, len(sent) - 1), "nabrajanje", 7.0,
                                     f"novi korak („{sent[0]['w']}…“): prijelaz {tip}", rez=rez))
            elif _find(fs[:3], NOVA_TEMA) and _find(fs[:3], NOVA_TEMA)[0] == 0:
                tip = "zamah" if energicno else "pretapanje"
                out.append(_kandidat(v, tip, sent, 0, min(2, len(sent) - 1), "nova tema", 6.0,
                                     f"prijelaz na novu temu („{sent[0]['w']}…“): {tip}", rez=rez))
            elif any(abs(sent[0]["s"] - t) <= REZ_BLIZU for t in teme_od):
                tip = "zamah" if energicno else "pretapanje"
                tema = next(t for t in v.analiza["teme"] if abs(sent[0]["s"] - float(t["od"])) <= REZ_BLIZU)
                out.append(_kandidat(v, tip, sent, 0, min(2, len(sent) - 1), "nova tema", 7.0,
                                     f"nova tema „{tema.get('naslov', '')}“: prijelaz {tip}", rez=rez))
    # trenuci iz analiza.json (Claude ih je napisao)
    for tr in v.analiza.get("trenuci") or []:
        try:
            od, do, oc = float(tr["od"]), float(tr["do"]), float(tr.get("ocjena") or 3)
        except (KeyError, TypeError, ValueError):
            continue
        vr = (tr.get("vrsta") or "").lower()
        sent = next((s for s in v.recenice if s[0]["s"] <= od + 0.3 and s[-1]["e"] >= od - 0.3), None)
        if not sent or oc < 3:
            continue
        a = min(range(len(sent)), key=lambda q: abs(sent[q]["s"] - od))
        bnd = [q for q in range(a, len(sent)) if sent[q]["e"] <= do + 0.3] or [a]
        opis = (tr.get("opis") or vr).strip()
        if vr == "hook":
            b = _do_kraja(sent, a, 2.5)
            out.append(_kandidat(v, "trzaj", sent, a, b, "trenutak: hook", 4.0 + oc * 0.8, f"hook: {opis}"))
        elif vr in ("poanta", "citat", "emocija", "savjet"):
            b = min(bnd[-1], _do_kraja(sent, a, 6.0))
            if sent[b]["oe"] - sent[a]["os"] >= 1.2:
                out.append(_kandidat(v, "guranje", sent, a, b, f"trenutak: {vr}", 3.5 + oc * 0.8, f"{vr}: {opis}"))
        elif vr == "smijeh":
            c = _kandidat(v, "pad", sent, a, a, "trenutak: smijeh", 3.5 + oc * 0.7, f"smijeh: {opis}")
            c["do"] = round(sent[a]["s"] + 0.8, 3)
            c["e"] = sent[a]["os"] + 0.8
            out.append(c)
    # pojačanje: kandidat unutar Claudeova trenutka s ocjenom ≥ 4 vrijedi više
    for c in out:
        if c["pravilo"].startswith("trenutak"):
            continue
        for tr in v.analiza.get("trenuci") or []:
            try:
                if float(tr["od"]) - 0.3 <= c["od"] <= float(tr["do"]) + 0.3 and float(tr.get("ocjena") or 0) >= 4:
                    c["ocjena"] += 1.0
                    break
            except (KeyError, TypeError, ValueError):
                continue
    for c in out:
        c["ocjena"] = round(min(10.0, c["ocjena"]), 1)
    return out


def odaberi(v, cands, gustoca=1.0, postojeci=()):
    """Pravila gustoće: Shofe označi koje bi uzeo (`shofe`), ostali dobiju razlog (`zasto_ne`)."""
    D = v.total / v.speed
    budget = {"kamera": max(1, round(D / 8 * gustoca)), "prijelaz": max(1, round(D / 20 * gustoca)),
              "boja": max(1, int((1 + D / 120) * min(1.0, gustoca)))}
    uzeti = [dict(x, postojeci=True) for x in postojeci]
    count = {g: sum(1 for x in uzeti if x["skupina"] == g) for g in budget}
    for c in cands:
        c["skupina"] = efekti.TIPOVI[c["tip"]]["skupina"]
    seen = set()
    for c in sorted(cands, key=lambda c: (-c["ocjena"], c["s"])):
        g = c["skupina"]
        key = (c["tip"], c["od"])
        why = None
        if key in seen:
            why = "isti prijedlog već postoji"
        elif c["ocjena"] < PRAG:
            why = f"slabiji znak (ocjena {c['ocjena']:g})"
        elif any(a - 0.3 <= c["od"] <= b for a, b in v.songs):
            why = "za vrijeme pjesme"
        elif c["tip"] == "zamrzni" and c["s"] < v.hook_do:
            why = "za vrijeme hook naslova (oznaka bi se tukla s naslovom)"
        elif count[g] >= budget[g]:
            why = f"dosta efekata te vrste za ovu duljinu ({budget[g]})"
        else:
            for y in uzeti:
                if g == "kamera" and y["skupina"] == "kamera" and (
                        abs(y["s"] - c["s"]) < KAMERA_RAZMAK or efekti.overlap((c["s"], c["e"]), (y["s"], y["e"]))):
                    why = f"preblizu {y.get('id', 'drugom zumu')} ({y['tip']})"
                elif g == "kamera" and y["tip"] == c["tip"] and abs(y["s"] - c["s"]) < ISTI_RAZMAK:
                    why = f"isti efekt ({c['tip']}) malo prije"
                elif g == y["skupina"] == "boja" and efekti.overlap((c["s"], c["e"]), (y["s"], y["e"])):
                    why = f"preklapa {y.get('id', 'drugi efekt boje')} ({y['tip']})"
                elif g == y["skupina"] == "prijelaz" and abs(y["s"] - c["s"]) < 1e-3:
                    why = "na tom rezu već je prijelaz"
                elif {g, y["skupina"]} == {"kamera", "prijelaz"} and (
                        min(abs(y["s"] - c["e"]), abs(c["s"] - y["e"]), abs(y["s"] - c["s"])) < PRIJELAZ_RAZMAK
                        or efekti.overlap((c["s"], c["e"]), (y["s"] - 0.5, y["e"] + 0.5))):
                    why = f"odmah uz {y.get('id', 'drugi efekt')} ({y['tip']})"
                if why:
                    break
        seen.add(key)
        c["shofe"] = why is None
        if why:
            c["zasto_ne"] = why
        else:
            uzeti.append(c)
            count[g] += 1
    return budget


def napravi(proj, words, edit, pj, gustoca=1.0, analiza=None):
    """Cijeli prijedlog → dict za efekti_prijedlog.json (analiza: zadano analiza.json projekta)."""
    if analiza is None:
        analiza = load_json(proj / "analiza.json") if (proj / "analiza.json").exists() else {}
    v = Video(words, edit, pj, analiza)
    cands = kandidati(v)
    fx, _ = efekti.plan(edit, v.cuts, pj["fps"], v.total)
    post = [{"id": x["id"], "tip": x["tip"], "s": x["s"], "e": x["e"], "skupina": efekti.TIPOVI[x["tip"]]["skupina"]}
            for x in fx]
    budget = odaberi(v, cands, gustoca, post)
    cands.sort(key=lambda c: (c["s"], c["tip"]))
    pr = []
    for n, c in enumerate(cands, 1):
        a, b = v.konacno(c["s"]), v.konacno(c["e"])
        if c["skupina"] == "prijelaz":
            vrijeme = f"rez {fmt_time(a)}"
        else:
            vrijeme = f"{fmt_time(max(0.0, a))}-{fmt_time(b)}"
        p = {"id": f"P{n}", "tip": c["tip"], "od": c["od"], "do": c["do"], "vrijeme": vrijeme,
             "pravilo": c["pravilo"], "ocjena": c["ocjena"], "razlog": c["razlog"], "tekst": c["tekst"],
             "parametri": c["parametri"], "skupina": c["skupina"], "shofe": c["shofe"], "uzmi": c["shofe"]}
        if c.get("zasto_ne"):
            p["zasto_ne"] = c["zasto_ne"]
        pr.append(p)
    recenice = [{"vrijeme": fmt_time(v.konacno(s[0]["os"])), "tekst": _tekst(s)} for s in v.recenice]
    return {"trajanje": round(v.total / v.speed, 2), "stil": v.stil, "gustoca": gustoca,
            "najvise": budget, "postojeci": [f"{x['id']} {x['tip']}" for x in fx],
            "pregledao_claude": False, "prijedlozi": pr, "recenice": recenice}


def tekst(data):
    L = [f"Prijedlog efekata po tekstu (video {fmt_time(data['trajanje'])}, stil {data['stil']}; najviše: kamera "
         f"{data['najvise']['kamera']}, prijelazi {data['najvise']['prijelaz']}, boja {data['najvise']['boja']})"]
    if data.get("postojeci"):
        L.append(f"Već u edit.json: {', '.join(data['postojeci'])}")
    L.append("✓ = Shofe bi uzeo (uzmi: true), ✗ = ne bi (razlog u zagradi). Vremena: sljedeći render.")
    for p in data["prijedlozi"]:
        znak = "✓" if p.get("uzmi") else "✗"
        ozn = f" oznaka „{p['parametri']['oznaka']}“" if p["parametri"].get("oznaka") else ""
        extra = f"  ({p['zasto_ne']})" if not p.get("uzmi") and p.get("zasto_ne") else ""
        st = f"  → {p['primijenjen']}" if p.get("primijenjen") else ""
        L.append(f"  {p['id']:<4}{znak} {p['vrijeme']:<19} {p['tip']:<10} {p['ocjena']:>4}  [{p['pravilo']}]{ozn}"
                 f"  {p['razlog']}{extra}{st}")
        L.append(f"        „{p['tekst']}“")
    L.append("")
    L.append("Tekst gotovog videa (za efekte koje Shofe nije našao: efekti.py projekt dodaj TIP --na \"citat\"):")
    for r in data.get("recenice") or []:
        L.append(f"  {r['vrijeme']}  {r['tekst']}")
    return "\n".join(L)


def spremi(proj, data):
    save_json(proj / DATOTEKA, data)
    (proj / TEKST).write_text(tekst(data) + "\n", encoding="utf-8")


DOZVOLJENI = {"zum", "jacina", "oznaka", "trajanje", "smjer", "zvuk"}


def primijeni(proj, words, edit, pj, data, ids=None):
    """Upiši odabrane prijedloge u edit.json (jedan korak povijesti). Vraća (dodani [(P, E, x)], preskočeni)."""
    import uredi
    import zvukovi
    from render import build_cuts, resolve_style
    edit2 = copy.deepcopy(edit)
    fxs = edit2.setdefault("efekti", [])
    cuts, _, total = build_cuts(words, edit2, resolve_style(edit2), pj["fps"], pj["duration"])
    fps = pj["fps"]
    if ids:
        want = {i.upper() for i in ids}
        chosen = [p for p in data["prijedlozi"] if p["id"].upper() in want]
        missing = want - {p["id"].upper() for p in chosen}
        if missing:
            die(f"nema prijedloga {', '.join(sorted(missing))} (popis: python efekti.py {proj.name} predlozi popis)")
    else:
        chosen = [p for p in data["prijedlozi"] if p.get("uzmi")]
    n = max((int(str(e.get("id", "E0"))[1:] or 0) for e in fxs if re.fullmatch(r"E\d+", str(e.get("id", "")))),
            default=0) + 1
    dodani, preskoceni = [], []
    for p in sorted(chosen, key=lambda p: float(p["od"])):
        if p.get("primijenjen"):
            preskoceni.append((p, f"već je u edit.json kao {p['primijenjen']}"))
            continue
        try:
            tip = efekti.tip_of(p["tip"])
        except ValueError as ex:
            preskoceni.append((p, str(ex)))
            continue
        par = {k: v for k, v in (p.get("parametri") or {}).items() if k in DOZVOLJENI and v not in (None, "")}
        if "zvuk" in par:
            try:
                par["zvuk"] = zvukovi.provjeri(par["zvuk"], proj)
            except ValueError as ex:
                preskoceni.append((p, str(ex)))
                continue
        g = efekti.TIPOVI[tip]["skupina"]
        bio = p.get("skupina") or g
        if (g == "prijelaz") != (bio == "prijelaz"):
            preskoceni.append((p, "prijelaz ide samo na rez, a efekt na dio rečenice (promijeni tip u istoj vrsti)"))
            continue
        if tip == "zamrzni" and not par.get("oznaka"):
            par.pop("oznaka", None)
        if g == "kamera" and not par.get("lice"):
            lice = efekti.find_face(proj, float(p["od"]) + 0.1)
            if lice:
                par["lice"] = lice
        if tip == "iris":
            lice = efekti.find_face(proj, float(p["do"]) + 0.05)
            if lice:
                par["lice"] = lice
        new = {"id": f"E{n}", "tip": tip, "od": round(float(p["od"]), 3), "do": round(float(p["do"]), 3),
               "parametri": par, "naredba": f"{tip} (prijedlog {p['id']}: {p.get('pravilo', '')})"}
        fx_new, notes = efekti.plan({"efekti": [new]}, cuts, fps, total)
        if not fx_new:
            preskoceni.append((p, (notes[0] if notes else "nije u videu").replace(f"efekt {new['id']} ", "")))
            continue
        x = fx_new[0]
        T = efekti.TIPOVI[tip]
        if g != "prijelaz" and x["e"] - x["s"] < T["min"] - 1e-3:
            preskoceni.append((p, f"{tip} treba barem {T['min']:g} s"))
            continue
        cur, _ = efekti.plan(edit2, cuts, fps, total)
        clash = [y for y in cur if efekti.TIPOVI[y["tip"]]["skupina"] == g and efekti.overlap(
            (x["s"], x["e"]), (y["s"], y["e"]))]
        if clash:
            preskoceni.append((p, f"preklapa {clash[0]['id']} ({clash[0]['tip']})"))
            continue
        fxs.append(new)
        fxs.sort(key=lambda e: float(e["od"]))
        p["primijenjen"] = new["id"]
        dodani.append((p, new, x))
        n += 1
    if dodani:
        uredi.save_history(proj, f"prijedlog efekata: {', '.join(p['id'] for p, _, _ in dodani)}")
        save_json(proj / "edit.json", edit2)
        spremi(proj, data)
    return dodani, preskoceni, edit2


def _efekata(n):
    if n % 10 == 1 and n % 100 != 11:
        return "efekt"
    return "efekta" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "efekata"


def cmd(proj, words, edit, pj, a):
    sub = (a.vremena[0].lower() if a.vremena else "")
    f = proj / DATOTEKA
    if sub in ("popis", "pokazi", "pokaži"):
        if not f.exists():
            die(f"nema prijedloga (napravi ga: python efekti.py {proj.name} predlozi)")
        print(tekst(load_json(f)))
        return
    if sub == "primijeni":
        if not f.exists():
            die(f"nema prijedloga (napravi ga: python efekti.py {proj.name} predlozi)")
        data = load_json(f)
        ids = [i for s in a.vremena[1:] for i in re.split(r"[,\s]+", s) if i]
        if not data.get("pregledao_claude") and not a.bez_pregleda and not ids:
            die(f"prijedlog nije pregledan: provjeri svaki prijedlog u {f.name} (uzmi: true/false, tip, oznaka), "
                f"pa stavi \"pregledao_claude\": true")
        dodani, presk, edit2 = primijeni(proj, words, edit, pj, data, ids or None)
        for p, new, x in dodani:
            fa, fb = efekti.to_final(edit2, words, pj, x)
            gdje = f"na rezu {fmt_time((fa + fb) / 2)}" if efekti.TIPOVI[new["tip"]]["skupina"] == "prijelaz" \
                else f"{fmt_time(fa)}-{fmt_time(fb)}"
            ozn = f" „{new['parametri']['oznaka']}“" if new["parametri"].get("oznaka") else ""
            print(f"  {p['id']} → {new['id']}: {new['tip']}{ozn} {gdje}")
        for p, why in presk:
            print(f"  ! {p['id']} ({p['tip']}) preskočen: {why}")
        if dodani:
            print(f"Dodano {len(dodani)} {_efekata(len(dodani))} u sljedećem renderu (sve poništi: python uredi.py {proj.name} vrati). "
                  f"Provjeri slike: python efekti.py {proj.name} pokazi {dodani[0][1]['id']}")
        else:
            print("Ništa nije dodano.")
        return
    if sub and sub != "novo":
        die(f"predlozi {sub}? (predlozi | predlozi popis | predlozi primijeni [P1,P3])")
    g = (a.gustoca or "normalno").lower()
    if g not in GUSTOCA:
        die(f"--gustoca: {', '.join(GUSTOCA)}")
    data = napravi(proj, words, edit, pj, GUSTOCA[g])
    spremi(proj, data)
    print(tekst(data) if len(data["recenice"]) <= 120 else "\n".join(tekst(data).split("\n")[:len(data["prijedlozi"]) * 2 + 4]))
    n = sum(1 for p in data["prijedlozi"] if p["uzmi"])
    np_ = len(data["prijedlozi"])
    print(f"\n{f.name}: {np_} {'prijedlog' if np_ % 10 == 1 and np_ % 100 != 11 else 'prijedloga'}, Shofe bi uzeo {n}. Pregledaj, stavi "
          f"\"pregledao_claude\": true, pa: python efekti.py {proj.name} predlozi primijeni")
    if not (proj / "analiza.json").exists():
        print("  (bez analiza.json: nema tema ni trenutaka — s analyze.py + teme/trenuci prijedlog je bolji)")
