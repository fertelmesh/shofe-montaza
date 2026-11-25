"""„Skrati na N sekundi": izbaci najmanje važne cijele misli dok gotovi video ne stane u N sekundi.

Koristi ga uredi.py (naredba `skrati`). Koraci:
  1. misli    — riječi koje su sada u gotovom videu podijele se na rečenice (. ! ? ili pauza > 0,8 s
                ili promjena govornika); rečenica se nikad ne reže na pola.
  2. veze     — pitanje i odgovor, rečenica koja završava dvotočkom ili bez interpunkcije a nastavlja se
                malim slovom → nedjeljiva cjelina. Rečenica koja počinje veznikom ili pokaznom riječju
                („A", „Ali", „Zato", „To"…) ne smije ostati bez prethodne: takve čine lanac iz kojeg se
                smije zadržati samo početak (A, A+B, A+B+C), nikad B bez A.
  3. važnost  — Claudeove ocjene (--ocjene) imaju prednost; inače: najjači trenuci iz analiza.json,
                koliko je misao središnja za cijeli video (TF-IDF), uvod i kraj videa malo više,
                poštapalice i loši kadrovi manje.
  4. odabir   — naprtnjača (knapsack) s izborom po lancu: najveći zbroj važnost² × trajanje koji stane u
                N sekundi; zatim se izmjeri pravo trajanje gotovog videa i po potrebi ponovi s manjim
                proračunom.
"""
import math
import re
from collections import Counter

import numpy as np

import sadrzaj
from sadrzaj import SENT_END, fold

# riječi s kojima rečenica ovisi o prethodnoj (veznici, pokazne riječi, „isto tako"…)
VEZNICI = {
    "a", "ali", "al", "i", "pa", "te", "no", "nego", "vec", "zato", "jer", "dakle", "onda", "stoga",
    "medjutim", "takodjer", "isto", "to", "taj", "ta", "tu", "tamo", "ovo", "ono", "toga", "tome",
    "znaci", "naime", "inace", "ili", "kao", "zbog", "time", "ondje", "tad", "tada", "osim", "jos",
}
STOP = {
    "sam", "smo", "ste", "su", "je", "jesu", "biti", "bio", "bila", "bilo", "bili", "bude", "budu",
    "ovaj", "ova", "ovo", "taj", "ta", "to", "onaj", "ona", "ono", "koji", "koja", "koje", "kojeg",
    "kako", "kada", "kad", "gdje", "sto", "tko", "jer", "ali", "nego", "samo", "jos", "vec", "vam",
    "vas", "nas", "nam", "mi", "vi", "oni", "one", "ja", "ti", "on", "mene", "meni", "tebe", "njega",
    "njemu", "ima", "imam", "imate", "imamo", "nije", "nisu", "neki", "neka", "neko", "svaki", "sve",
    "svi", "evo", "eto", "dakle", "znaci", "zapravo", "stvarno", "jako", "puno", "malo", "onda",
    "tako", "ovdje", "tamo", "danas", "sada", "sad", "bok", "ekipa", "hvala",
}
# kratka najava („Drugo, ugradnja.") ide uz ono što najavljuje
NAJAVA = {"prvo", "drugo", "trece", "cetvrto", "peto", "sesto", "zadnje", "posljednje", "bonus", "savjet",
          "korak", "pitanje"}
FILLER = re.compile(r"^(e+|e+m+|m+|mhm|hm+|a+|a+m+|ovaj+|ono+|znaci|kao)$")

TEZINA_OCJENE = 2.0  # važnost² × trajanje: ocjena 5 vrijedi ~2,8× više po sekundi od ocjene 3


class Misao:
    __slots__ = ("n", "idx", "od", "do", "trajanje", "tekst", "vaznost", "razlog", "obavezno")

    def __init__(self, idx, words, pad):
        self.idx = idx
        self.od = words[idx[0]]["s"]
        self.do = words[idx[-1]]["e"]
        self.trajanje = (self.do - self.od) + pad
        self.tekst = " ".join(words[i]["w"] for i in idx)
        self.vaznost = 2.5
        self.razlog = []
        self.obavezno = False
        self.n = 0


# ---------------------------------------------------------------- 1. i 2. misli i veze
def _first_tok(words, i):
    return fold(words[i]["w"])


def split_sentences(words, idxs, gap=0.8):
    """Indeksi riječi u gotovom videu (rastući) → rečenice (popisi indeksa)."""
    out, cur = [], []
    for k, i in enumerate(idxs):
        if cur:
            p = cur[-1]
            brk = (i != p + 1                                   # između je izrezano
                   or SENT_END.search(words[p]["w"])
                   or words[i]["s"] - words[p]["e"] > gap
                   or words[i].get("g") != words[p].get("g"))
            if brk:
                out.append(cur)
                cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _ends(words, s):
    return words[s[-1]]["w"].rstrip("\"'”“»)")


def atomic(words, a, b):
    """True ako rečenice a i b moraju ostati ili otići zajedno."""
    end = _ends(words, a)
    if end.endswith("?") or end.endswith(":"):
        return True  # pitanje bez odgovora / najava bez nastavka nema smisla
    if b[0] != a[-1] + 1:
        return False
    if len(a) <= 4 and _first_tok(words, a[0]) in NAJAVA and words[b[0]].get("g") == words[a[-1]].get("g"):
        return True  # najava bez sadržaja nema smisla
    first = words[b[0]]["w"].lstrip("\"'„“«(")
    if not SENT_END.search(end) and first[:1].islower() and words[b[0]].get("g") == words[a[-1]].get("g"):
        return True  # misao se nastavlja preko pauze
    return False


def depends(words, a, b):
    """True ako rečenica b ne smije ostati bez a (počinje veznikom ili pokaznom riječju)."""
    if b[0] != a[-1] + 1 and words[b[0]]["s"] - words[a[-1]]["e"] > 3.0:
        return False
    return _first_tok(words, b[0]) in VEZNICI


def build_thoughts(words, idxs, pad):
    """→ (misli, lanci). Lanac = popis brojeva misli; smije se zadržati samo njegov početak."""
    sents = split_sentences(words, idxs)
    units = []  # spoji nedjeljive rečenice
    for s in sents:
        if units and atomic(words, units[-1][-1], s):
            units[-1].append(s)
        else:
            units.append([s])
    misli = []
    for u in units:
        m = Misao([i for s in u for i in s], words, pad)
        m.n = len(misli) + 1
        misli.append(m)
    lanci = []
    for k, m in enumerate(misli):
        if lanci and depends(words, misli[k - 1].idx, m.idx):
            lanci[-1].append(k)
        else:
            lanci.append([k])
    return misli, lanci


# ---------------------------------------------------------------- 3. važnost
def _terms(text):
    return [t[:5] for t in sadrzaj.tokens(text) if len(t) >= 4 and t not in STOP and not t.isdigit()]


def centrality(misli):
    """Kosinusna sličnost TF-IDF vektora misli s ostatkom videa → rang 0..1 (1 = najsredišnija)."""
    docs = [Counter(_terms(m.tekst)) for m in misli]
    n = len(docs)
    if n < 3:
        return [0.5] * n
    df = Counter(t for d in docs for t in d)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    vecs = [{t: (1 + math.log(c)) * idf[t] for t, c in d.items()} for d in docs]
    total = Counter()
    for v in vecs:
        total.update(v)
    raw = []
    for v in vecs:
        rest = {t: total[t] - x for t, x in v.items()}
        dot = sum(x * rest[t] for t, x in v.items())
        nv = math.sqrt(sum(x * x for x in v.values())) or 1.0
        nr = math.sqrt(sum(x * x for x in total.values())) or 1.0
        raw.append(dot / (nv * nr))
    order = sorted(range(n), key=lambda k: raw[k])
    rank = [0.0] * n
    for r, k in enumerate(order):
        rank[k] = r / (n - 1)
    return rank


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def score(misli, words, analiza=None, ocjene=None, obavezno=(), nebitno=()):
    """Upiše m.vaznost (0,3–5,5) i m.razlog. ocjene: {broj misli: 1–5} od Claudea (imaju prednost)."""
    analiza = analiza or {}
    ocjene = ocjene or {}
    cen = centrality(misli)
    trenuci = analiza.get("trenuci") or []
    losi = analiza.get("losi_kadrovi") or []
    for k, m in enumerate(misli):
        if m.n in ocjene:
            m.vaznost = float(ocjene[m.n])
            m.razlog = [f"Claude {ocjene[m.n]:g}"]
        else:
            v = 2.2 + 1.2 * cen[k]
            r = []
            if cen[k] >= 0.75:
                r.append("središnja")
            best = None
            for t in trenuci:
                try:
                    od, do = float(t["od"]), float(t["do"])
                except (KeyError, TypeError, ValueError):
                    continue
                ov = _overlap(m.od, m.do, od, do)
                if ov >= 0.5 * min(m.do - m.od, do - od) and ov > 0:
                    oc = int(t.get("ocjena") or 3)
                    if best is None or oc > best[0]:
                        best = (oc, t)
            if best:
                v = max(v, 2.0 + 0.6 * best[0])
                r.append(f"{best[1].get('vrsta', 'trenutak')} {best[0]}")
            if k == 0:
                v += 1.0
                r.append("uvod")
            elif k == len(misli) - 1:
                v += 0.6
                r.append("kraj")
            toks = [fold(words[i]["w"]) for i in m.idx]
            fill = sum(bool(FILLER.match(t)) for t in toks if t)
            if toks and fill / len(toks) > 0.3:
                v -= 1.0
                r.append("poštapalice")
            if any(_overlap(m.od, m.do, float(b["od"]), float(b["do"])) > 0.5 * (m.do - m.od) for b in losi
                   if "od" in b and "do" in b):
                v -= 0.7
                r.append("loš kadar")
            m.vaznost = v
            m.razlog = r
        if m.n in nebitno:
            m.vaznost = 0.5
            m.razlog = ["nebitno"]
        if m.n in obavezno:
            m.obavezno = True
            m.razlog = ["obavezno"] + m.razlog
        m.vaznost = min(max(m.vaznost, 0.3), 5.5)


# ---------------------------------------------------------------- 4. odabir
def choose(misli, lanci, budget):
    """Naprtnjača s izborom po lancu (zadrži prvih j misli lanca, j = 0..len).

    budget: sekunde (procjena trajanja misli). → skup indeksa misli koje ostaju, ili None ako
    obavezne misli ne stanu.
    """
    res = max(0.05, budget / 4000.0)
    W = int(budget / res + 1e-9)
    if W <= 0:
        return None
    BIG = 1e6
    NEG = -1e18
    dp = np.full(W + 1, NEG)
    dp[0] = 0.0
    picks = []
    for lanac in lanci:
        opts = [(0, 0.0)]
        w = 0
        v = 0.0
        for k in lanac:
            m = misli[k]
            w += int(math.ceil(m.trajanje / res - 1e-9))
            v += m.vaznost ** TEZINA_OCJENE * max(m.do - m.od, 0.3) + (BIG if m.obavezno else 0.0)
            opts.append((w, v))
        # ako je obavezna misao u lancu, opcije bez nje nisu dopuštene
        last_must = max((j + 1 for j, k in enumerate(lanac) if misli[k].obavezno), default=0)
        new = np.full(W + 1, NEG)
        choice = np.zeros(W + 1, dtype=np.int16)
        for j, (wj, vj) in enumerate(opts):
            if j < last_must or wj > W:
                continue
            cand = np.full(W + 1, NEG)
            cand[wj:] = dp[: W + 1 - wj] + vj
            better = cand > new
            new[better] = cand[better]
            choice[better] = j
        dp = new
        picks.append(choice)
    best_w = int(np.argmax(dp))
    if dp[best_w] <= NEG / 2:
        return None
    keep = set()
    w = best_w
    for lanac, choice in zip(reversed(lanci), reversed(picks)):
        j = int(choice[w])
        w -= sum(int(math.ceil(misli[k].trajanje / res - 1e-9)) for k in lanac[:j])
        keep.update(lanac[:j])
    return keep


def parse_ocjene(spec, n_max):
    """'3:5,7-9:1' → {3: 5, 7: 1, 8: 1, 9: 1}"""
    out = {}
    for part in re.split(r"[,;\s]+", (spec or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?[:=]([1-5](?:\.\d)?)", part)
        if not m:
            raise sadrzaj.Greska(f"ne razumijem ocjenu „{part}“ (primjer: 3:5,7-9:1 — misao:ocjena 1–5)")
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if b < a:
            raise sadrzaj.Greska(f"„{part}“: kraj je prije početka")
        for k in range(a, b + 1):
            if not 1 <= k <= n_max:
                raise sadrzaj.Greska(f"nema misli #{k} (misli su 1–{n_max})")
            out[k] = float(m.group(3))
    return out
