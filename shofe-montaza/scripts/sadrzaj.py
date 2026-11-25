"""Naredbe po sadržaju: pronađi dio transkripta po citatu, broju riječi, odsječku ili temi.

Claude razumije što korisnik želi („izreži dio gdje pričam o cijeni"), pronađe to u transcript.txt i
alatu preda doslovni citat početka i kraja (`--od "Koliko košta" --do "tisuću eura."`). Ovaj modul
provjeri da citat stvarno postoji u transkriptu (nema izmišljenih rezova) i vrati točne riječi.

Usporedba riječi ne pazi na velika slova, interpunkciju ni kvačice (c = č = ć), a dopušta drugi
padež/oblik iste riječi (cijena ~ cijenu ~ cijene) i sitne pogreške prepoznavanja govora.
"""
import difflib
import re

FOLD = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z"})
SENT_END = re.compile(r"[.!?…]+[\"'”“»]*$")


class Greska(ValueError):
    """Odabir se ne može provesti; poruka je za korisnika (hrvatski)."""


def fold(s):
    s = s.lower().replace("đ", "dj").translate(FOLD)
    return re.sub(r"[^\w]", "", s)


def tokens(text):
    return [t for t in (fold(x) for x in re.split(r"[\s\-–—/]+", text)) if t]


def tok_score(q, w):
    """2 = ista riječ, 1 = isti korijen / sitna pogreška, 0 = ne."""
    if not q or not w:
        return 0
    if q == w:
        return 2
    n = min(len(q), len(w))
    if n >= 4:
        pre = 0
        while pre < n and q[pre] == w[pre]:
            pre += 1
        if pre >= max(4, n - 2) and abs(len(q) - len(w)) <= 3:  # drugi padež / oblik iste riječi
            return 1
        if difflib.SequenceMatcher(None, q, w).ratio() >= 0.84:
            return 1
    return 0


class Transkript:
    """Riječi transkripta s inačicama teksta (izvorna riječ + Claudeov ispravak iz edit.json)."""

    def __init__(self, words, alt=None):
        self.words = words
        self.alts = []
        for i, w in enumerate(words):
            forms = {fold(w["w"])}
            for t in (alt or {}).get(i, []):
                forms.add(fold(t))
            forms.discard("")
            self.alts.append(forms)
        self.idx = [i for i, f in enumerate(self.alts) if f]  # riječi koje nisu samo interpunkcija

    def score(self, q, i):
        return max((tok_score(q, f) for f in self.alts[i]), default=0)

    def find(self, phrase, start=0):
        """Sve pojave citata: [(prva, zadnja, točno)] — točno=True ako su sve riječi iste."""
        q = tokens(phrase)
        if not q:
            raise Greska(f"citat „{phrase}“ nema riječi")
        hits = []
        pos = [k for k, i in enumerate(self.idx) if i >= start]
        for k in pos:
            if k + len(q) > len(self.idx):
                break
            sc = [self.score(t, self.idx[k + j]) for j, t in enumerate(q)]
            if all(sc):
                hits.append((self.idx[k], self.idx[k + len(q) - 1], all(s == 2 for s in sc)))
        if any(h[2] for h in hits):
            hits = [h for h in hits if h[2]]
        return hits

    def context(self, a, b, n=5):
        lo, hi = max(0, a - n), min(len(self.words), b + n + 1)
        parts = []
        for i in range(lo, hi):
            t = self.words[i]["w"]
            if i == a:
                t = "[" + t
            if i == b:
                t = t + "]"
            parts.append(t)
        return ("… " if lo > 0 else "") + " ".join(parts) + (" …" if hi < len(self.words) else "")

    def nearest(self, phrase, k=3):
        """Prijedlozi kad citat nije pronađen: dijelovi transkripta koji mu najviše sliče."""
        q = tokens(phrase)
        best = []
        for k0 in range(len(self.idx)):
            seg = self.idx[k0:k0 + len(q)]
            if len(seg) < len(q):
                break
            s = sum(self.score(t, i) for t, i in zip(q, seg))
            if s:
                best.append((s, seg[0], seg[-1]))
        best.sort(key=lambda x: -x[0])
        return [self.context(a, b, 2) for _, a, b in best[:k]]


def _fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def _pick(tr, phrase, hits, pojava, what):
    if not hits:
        sug = tr.nearest(phrase)
        hint = ("\n  Najsličnije: " + "\n               ".join(sug)) if sug else ""
        raise Greska(f"{what} „{phrase}“ nije u transkriptu (citiraj točno iz transcript.txt){hint}")
    if pojava is not None:
        if not 1 <= pojava <= len(hits):
            raise Greska(f"{what} „{phrase}“ ima {len(hits)} pojava, nema pojave {pojava}")
        return hits[pojava - 1]
    if len(hits) > 1:
        rows = "\n".join(f"  {n}. {_fmt(tr.words[a]['s'])}  {tr.context(a, b)}" for n, (a, b, _) in enumerate(hits, 1))
        raise Greska(f"{what} „{phrase}“ se pojavljuje {len(hits)} puta — dodaj još riječi ili --pojava N:\n{rows}")
    return hits[0]


def by_quote(tr, od, do=None, pojava=None):
    """--od "početak" [--do "kraj"] → (prva, zadnja) riječ, uključivo."""
    starts = tr.find(od)
    if do is None:
        a, b, _ = _pick(tr, od, starts, pojava, "Citat")
        return a, b
    pairs = []
    for a, b0, _ in starts:
        ends = tr.find(do, start=a)
        ends = [e for e in ends if e[1] >= b0]
        if ends:
            pairs.append((a, ends[0][1], True))  # najbliži kraj iza početka
    if not starts:
        _pick(tr, od, starts, None, "Početak")
    if not pairs:
        _pick(tr, do, [], None, f"Kraj (iza „{od}“)")
    a, b, _ = _pick(tr, od, pairs, pojava, "Početak")
    return a, b


def parse_nums(spec, what):
    """'12-30,45' → [12..30, 45]"""
    out = []
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"#?(\d+)(?:[-–](\d+))?", part)
        if not m:
            raise Greska(f"ne razumijem {what} „{part}“ (primjer: 12-30,45)")
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if b < a:
            raise Greska(f"{what} „{part}“: kraj je prije početka")
        out += range(a, b + 1)
    if not out:
        raise Greska(f"nema brojeva za {what}")
    return out


def words_in(words, od, do):
    return [i for i, w in enumerate(words) if od - 0.01 <= (w["s"] + w["e"]) / 2 <= do + 0.01]


def by_segments(words, edit, spec):
    segs = {s["id"]: s for s in edit["odsjecci"]}
    out = []
    for n in parse_nums(spec, "odsječak"):
        if n not in segs:
            raise Greska(f"nema odsječka #{n} (postoje 1–{max(segs)})")
        out += words_in(words, segs[n]["od"], segs[n]["do"])
    return out


def by_topic(words, analiza, spec):
    teme = (analiza or {}).get("teme") or []
    if not teme:
        raise Greska("analiza.json nema tema (pokreni analyze.py i upiši teme)")
    if re.fullmatch(r"\d+", spec.strip()):
        n = int(spec)
        if not 1 <= n <= len(teme):
            raise Greska(f"nema teme {n} (postoje 1–{len(teme)})")
        t = teme[n - 1]
    else:
        q = tokens(spec)
        scored = []
        for t in teme:
            hay = tokens(t.get("naslov", "") + " " + t.get("sazetak", ""))
            s = sum(max((tok_score(x, h) for h in hay), default=0) for x in q)
            ok = all(max((tok_score(x, h) for h in hay), default=0) for x in q)
            if ok:
                scored.append((s, t))
        if not scored:
            names = "; ".join(f"{i}. {t.get('naslov', '')}" for i, t in enumerate(teme, 1))
            raise Greska(f"nijedna tema ne odgovara „{spec}“. Teme: {names}")
        scored.sort(key=lambda x: -x[0])
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            names = "; ".join(f"„{t.get('naslov', '')}“" for _, t in scored)
            raise Greska(f"„{spec}“ odgovara za više tema ({names}) — navedi broj teme")
        t = scored[0][1]
    return words_in(words, float(t["od"]), float(t["do"])), t


def sentence_bounds(words, a, b):
    """Proširi [a, b] na cijele rečenice (granica: . ! ? ili pauza dulja od 0,8 s)."""
    while a > 0 and not SENT_END.search(words[a - 1]["w"]) and words[a]["s"] - words[a - 1]["e"] < 0.8:
        a -= 1
    while b + 1 < len(words) and not SENT_END.search(words[b]["w"]) and words[b + 1]["s"] - words[b]["e"] < 0.8:
        b += 1
    return a, b


def edge_notes(words, idxs):
    """Upozorenja kad odabir počinje ili završava usred rečenice."""
    notes = []
    groups = []
    for i in sorted(set(idxs)):
        if groups and i == groups[-1][1] + 1:
            groups[-1][1] = i
        else:
            groups.append([i, i])
    for a, b in groups:
        if a > 0 and not SENT_END.search(words[a - 1]["w"]) and words[a]["s"] - words[a - 1]["e"] < 0.8:
            notes.append(f"počinje usred rečenice („… {words[a - 1]['w']} | {words[a]['w']} …“)")
        if b + 1 < len(words) and not SENT_END.search(words[b]["w"]) and words[b + 1]["s"] - words[b]["e"] < 0.8:
            notes.append(f"završava usred rečenice („… {words[b]['w']} | {words[b + 1]['w']} …“)")
    return notes
