"""Korak 4: montaža prema edit.json → reel_vN.mp4

  python render.py shofe_projekt                 puni render (nova verzija)
  python render.py shofe_projekt --brzo          brzi pregled u pola rezolucije
  python render.py shofe_projekt --kadar 1,5,12  samo slike kadrova (sekunde gotovog reela) za provjeru izgleda
"""
import argparse
import bisect
import shutil
from pathlib import Path

import titlovi
import verzije
from common import (FONTS_DIR, GRADES, die, ffmpeg, filter_script_args, fmt_time, load_json,
                    load_style, norm_word, run)

ZOOM = {"nema": None, "blago": (1.08, 1.6), "jako": (1.16, 0.7)}
POS_FRAC = {"dolje": 0.24, "gore": 0.20}


# ---------------------------------------------------------------- stil
def resolve_style(edit):
    st = load_style(edit.get("stil") or "suncani")
    acc = edit.get("boja")
    if acc:
        if st.get("hook_pozadina") == st["boja_isticanja"]:
            st["hook_pozadina"] = acc
        st["boja_isticanja"] = acc
        st["boja_naglaska"] = acc
        st["boja_trake"] = acc
    for k_edit, k_style in [("pozicija_titlova", "pozicija"), ("velika_slova", "velika_slova"),
                            ("zoom", "zoom"), ("boja_slike", "boja_slike"), ("traka_napretka", "traka_napretka")]:
        if edit.get(k_edit) is not None:
            st[k_style] = edit[k_edit]
    st["velicina"] = st["velicina"] * float(edit.get("velicina_titlova") or 1.0)
    st.setdefault("boja_naglaska", st["boja_isticanja"])
    st.setdefault("boja_trake", st["boja_isticanja"])
    return st


def ass_color(hexstr):
    h = hexstr.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    opacity = int(h[6:8], 16) if len(h) >= 8 else 255
    return f"&H{255 - opacity:02X}{b}{g}{r}".upper()


def ass_time(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    cs = int(round((s - int(s)) * 100))
    s = int(s)
    if cs == 100:
        s, cs = s + 1, 0
    return f"{int(h)}:{int(m):02d}:{s:02d}.{cs:02d}"


def esc(t):
    return t.replace("\\", "/").replace("{", "(").replace("}", ")")


# ---------------------------------------------------------------- rezovi
def cut_spans(edit):
    """Izrezani dijelovi izvornog videa (`izrezi` u edit.json, upisuje ih uredi.py): [(od, do), ...]."""
    res = []
    for r in edit.get("izrezi") or []:
        a, b = float(r["od"]), float(r["do"])
        if b > a:
            res.append((a, b))
    return sorted(res)


def in_spans(t, spans):
    return any(a <= t < b for a, b in spans)


def subtract_spans(ranges, spans):
    out = []
    for a, b in ranges:
        parts = [[a, b]]
        for x, y in spans:
            nxt = []
            for p, q in parts:
                if y <= p or x >= q:
                    nxt.append([p, q])
                    continue
                if x > p:
                    nxt.append([p, x])
                if y < q:
                    nxt.append([y, q])
            parts = nxt
        out += parts
    return out


def align_tokens(tokens, wtexts):
    """Za svaki token (ispravljeni tekst iz edit.json) indeks riječi iz transkripta kojoj pripada."""
    if len(tokens) == len(wtexts):
        return list(range(len(tokens)))
    import difflib
    a = [norm_word(t) for t in tokens]
    b = [norm_word(w) for w in wtexts]
    owner = [None] * len(tokens)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                owner[i1 + k] = j1 + k
        elif op == "replace":
            for k in range(i2 - i1):
                owner[i1 + k] = j1 + min(int(k * (j2 - j1) / (i2 - i1)), j2 - j1 - 1)
    for k in range(len(owner)):  # umetnuti tokeni idu uz susjednu riječ
        if owner[k] is None:
            owner[k] = owner[k - 1] if k > 0 and owner[k - 1] is not None else None
    nxt = next((o for o in owner if o is not None), 0)
    return [o if o is not None else nxt for o in owner]


def words_in(words, od, do, starts=None):
    """Indeksi riječi unutar [od, do] (±10 ms). `starts` = početci riječi (ubrzanje za duge snimke)."""
    if starts is None or len(starts) != len(words):
        return [i for i, w in enumerate(words) if w["s"] >= od - 0.01 and w["e"] <= do + 0.01]
    res = []
    for i in range(bisect.bisect_left(starts, od - 0.01), len(words)):
        w = words[i]
        if w["s"] > do + 0.01:
            break
        if w["e"] <= do + 0.01:
            res.append(i)
    return res


def word_starts(words):
    """Početci riječi ako su poredane po vremenu (inače None → spori, ali sigurni put)."""
    st = [w["s"] for w in words]
    return st if all(a <= b for a, b in zip(st, st[1:])) else None


def song_spans(edit):
    """Pjesme (nastupi bendova) iz edit.json: (zadržane [(od, do, titlovi)], izbačene [(od, do)])."""
    keep, drop = [], []
    for n in edit.get("nastupi") or []:
        a, b = float(n["od"]), float(n["do"])
        if b <= a:
            continue
        if n.get("zadrzi", True):
            keep.append((a, b, bool(n.get("titlovi", False))))
        else:
            drop.append((a, b))
    return sorted(keep), sorted(drop)


# zvuk pjesme: samo makni tutnjavu (auto) i ukroti vrhove; bez afftdn (pojede činele i jeku) i govornog kompresora
MUSIC_CHAIN = "highpass=f=30,acompressor=threshold=-14dB:ratio=1.6:attack=25:release=300"
SONG_RAMP = 0.25


def song_out_parts(edit, cuts):
    """Zadržane pjesme u vremenu gotovog videa (prije brzine): [(od, do, k)], k = redni broj pjesme
    među zadržanima (isti k za dijelove iste pjesme koje rez razdvoji)."""
    keep, _ = song_spans(edit)
    out = []
    for k, (a, b, _) in enumerate(keep):
        for c in cuts:
            lo, hi = max(a, c["a"]), min(b, c["b"])
            if hi - lo > 1e-3:
                s, e = c["o"] + lo - c["a"], c["o"] + hi - c["a"]
                if out and out[-1][2] == k and s - out[-1][1] < 0.05:
                    out[-1][1] = e
                else:
                    out.append([s, e, k])
    return [(s, e, k) for s, e, k in out if e - s > 2 * SONG_RAMP]


def song_out_spans(edit, cuts):
    """Zadržane pjesme u vremenu gotovog videa (prije brzine): [(od, do)]."""
    return [(s, e) for s, e, _ in song_out_parts(edit, cuts)]


def song_gain_expr(spans, r=SONG_RAMP, gains=None):
    """ffmpeg izraz po t: 1 u pjesmi, 0 izvan, linearno pretapanje r s na rubovima.
    gains = faktor po dijelu (pojačanje pjesme naspram govora); None = 1."""
    if not spans:
        return ""
    terms = []
    for i, (s, e) in enumerate(spans):
        t = f"clip(min((t-{s:.3f})/{r},({e:.3f}-t)/{r}),0,1)"
        g = 1.0 if gains is None else float(gains[i])
        terms.append(t if abs(g - 1.0) < 1e-4 else f"{g:.5f}*{t}")
    return "+".join(terms)


# ---------------------------------------------------------------- glasnoća pjesme naspram govora (M4.3b1)
# Kad u videu ima pjesma: prvi prolaz izmjeri glasnoću (EBU R128, blokovi od 400 ms svakih 100 ms) govora i
# svake pjesme posebno, pjesma dobije stalno pojačanje da bude jednako glasna kao govor (± nastup_glasnoca),
# a cijeli video jedno stalno pojačanje do −14 LUFS + limiter vrhova. Bez dinamičkog loudnorma: pjesma zadrži
# svoje tihe i glasne dijelove, a ne „pumpa".
TARGET_I = -14.0          # LUFS gotovog videa (mreže)
LIMIT_DB = -2.0           # vrh uzorka iza limitera (true peak ostaje ispod ~−1 dBTP)
SONG_GAIN_MAX = (-20.0, 15.0)
SONG_LU_MAX = 6.0         # Markova razlika pjesma − govor (LU), najviše ±6
EDGE = 0.5                # s uz rub pjesme koji se ne mjeri (pretapanje, pljesak)


def final_gain(db):
    """Stalno pojačanje + limiter na 192 kHz (vrhovi između uzoraka; limiter na 16/48 kHz pa preuzorkovanje
    daje i +3 dB preko granice)."""
    return (f"aresample=192000,volume={db:.2f}dB,"
            f"alimiter=limit={10 ** (LIMIT_DB / 20):.4f}:attack=1:release=80:level=0")


def loudness_lines(plan, edit):
    """Ispis za Marka: koliko je pjesma bila glasna naspram govora i koliko je pojačana/stišana."""
    keep = [n for n in sorted(edit.get("nastupi") or [], key=lambda n: float(n["od"]))
            if n.get("zadrzi", True) and float(n["do"]) > float(n["od"])]
    out = []
    for x in plan["pjesme"]:
        n = keep[x["k"]] if x["k"] < len(keep) else {}
        name = n.get("id", f"P{x['k'] + 1}")
        if x["izmjereno"] is None or plan["govor"] is None:
            out.append(f"Glasnoća {name}: nema govora za usporedbu, pjesma ostaje kakva jest")
            continue
        diff = x["izmjereno"] - plan["govor"]
        what = "glasnija" if diff > 0 else "tiša"
        g = x["pojacanje"]
        act = "ostaje" if abs(g) < 0.5 else (f"pojačana {g:+.1f} dB" if g > 0 else f"stišana {g:+.1f} dB")
        out.append(f"Glasnoća {name}: u snimci {abs(diff):.1f} LU {what} od govora → {act}"
                   + (f" (cilj: {float(n.get('glasnoca', edit.get('nastup_glasnoca') or 0)):+.0f} LU)"
                      if (n.get("glasnoca") or edit.get("nastup_glasnoca")) else " (cilj: jednako glasno)"))
    return out


def gated_loudness(m):
    """Integrirana glasnoća (LUFS) iz momentarnih glasnoća 400 ms blokova (BS.1770: −70 LUFS i −10 LU)."""
    import numpy as np
    m = np.asarray(m, float)
    m = m[m > -70.0]
    if not len(m):
        return None
    p = 10 ** ((m + 0.691) / 10)
    rel = -0.691 + 10 * np.log10(p.mean()) - 10.0
    p = p[m > rel]
    return float(-0.691 + 10 * np.log10(p.mean()))


def parse_momentary(txt):
    """Izlaz ametadata=print (ebur128 metadata=1): [(kraj bloka u s, M u LUFS)]."""
    out, t = [], None
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("frame:") and "pts_time:" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
            except ValueError:
                t = None
        elif line.startswith("lavfi.r128.M=") and t is not None:
            try:
                m = float(line.split("=", 1)[1])
            except ValueError:
                continue
            if m == m and abs(m) != float("inf"):   # bez nan/inf
                out.append((round(t + 0.1, 3), m))
    return out


def song_levels(edit, n_songs):
    """Željena razlika pjesma − govor u LU za svaku zadržanu pjesmu (edit.json nastup_glasnoca / nastupi[].glasnoca)."""
    base = float(edit.get("nastup_glasnoca") or 0.0)
    kept = [n for n in sorted(edit.get("nastupi") or [], key=lambda n: float(n["od"]))
            if n.get("zadrzi", True) and float(n["do"]) > float(n["od"])]
    out = []
    for k in range(n_songs):
        v = kept[k].get("glasnoca") if k < len(kept) else None
        v = base if v is None else float(v)
        out.append(max(-SONG_LU_MAX, min(SONG_LU_MAX, v)))
    return out


def loudness_plan(mom, parts, levels, target=TARGET_I):
    """Iz momentarnih glasnoća prvog prolaza: pojačanje svake pjesme (dB) i cijelog videa (dB).

    mom = [(kraj bloka, M)], parts = [(od, do, k)] u istom vremenu, levels[k] = pjesma − govor (LU).
    Vraća {"govor", "pjesme": [{k, izmjereno, pojacanje}], "ukupno", "pojacanje"}."""
    import numpy as np
    if not mom:
        return None
    t = np.array([x[0] for x in mom]) - 0.2          # sredina bloka od 400 ms
    m = np.array([x[1] for x in mom])
    which = np.full(len(t), -1)
    near = np.zeros(len(t), bool)
    for s, e, k in parts:
        which[(t >= s + EDGE) & (t <= e - EDGE)] = k
        near |= (t >= s - EDGE) & (t <= e + EDGE)
    speech = gated_loudness(m[~near])
    songs, gain_db = [], {}
    for k in sorted({k for _, _, k in parts}):
        lk = gated_loudness(m[which == k])
        if lk is None or speech is None:
            g = 0.0
        else:
            g = max(SONG_GAIN_MAX[0], min(SONG_GAIN_MAX[1], speech + levels[k] - lk))
        gain_db[k] = g
        songs.append({"k": k, "izmjereno": None if lk is None else round(lk, 1), "pojacanje": round(g, 2)})
    adj = m.copy()
    for s, e, k in parts:   # blokovi u pjesmi (i na rubovima, približno) dobiju pojačanje pjesme
        adj[(t >= s) & (t <= e)] += gain_db.get(k, 0.0)
    total = gated_loudness(adj)
    G = 0.0 if total is None else max(-30.0, min(30.0, target - total))
    return {"govor": None if speech is None else round(speech, 1), "pjesme": songs,
            "ukupno": None if total is None else round(total, 1), "pojacanje": round(G, 2)}


def build_cuts(words, edit, st, fps, total):
    pre, post = st.get("rezanje", [0.05, 0.12])
    spans = cut_spans(edit)
    # pjesma se nikad ne reže iznutra: zadržana ide cijela (i dijelovi bez riječi), izbačena cijela van;
    # izrezi (naredbe) je ne diraju, osim izričitih s "u_pjesmi" (uredi.py --u-pjesmi)
    songs, songs_out = song_spans(edit)
    song_cuts = sorted((float(r["od"]), float(r["do"])) for r in edit.get("izrezi") or [] if r.get("u_pjesmi"))
    all_songs = [(a, b) for a, b, _ in songs] + songs_out
    ranges, kept = [], []  # kept: (word_index, display_text)
    segs = sorted((s for s in edit["odsjecci"] if s.get("zadrzi", True)), key=lambda s: s["od"])
    starts = word_starts(words)
    for seg in segs:
        idx = words_in(words, seg["od"], seg["do"], starts)
        if not idx:
            continue
        cut = {norm_word(x) for x in seg.get("izbaci", [])}
        base_idx = [i for i in idx if norm_word(words[i]["w"]) not in cut]
        if not base_idx:
            continue
        tokens = [t for t in seg.get("tekst", "").split() if norm_word(t) not in cut] or [words[i]["w"] for i in base_idx]
        gone = {i for i in base_idx if in_spans((words[i]["s"] + words[i]["e"]) / 2, spans)}
        if all_songs:  # riječi u pjesmi: rez je cijela pjesma; titlovi samo ako ih pjesma traži
            for i in base_idx:
                mid = (words[i]["s"] + words[i]["e"]) / 2
                if in_spans(mid, all_songs):
                    gone.add(i)
                    if any(a <= mid < b and sub for a, b, sub in songs) and not in_spans(mid, song_cuts):
                        kept.append((i, words[i]["w"]))
        if gone:  # dio odsječka izrezan naredbom po vremenu: makni i pripadni ispravljeni tekst
            owner = align_tokens(tokens, [words[i]["w"] for i in base_idx])
            tokens = [t for t, o in zip(tokens, owner) if base_idx[o] not in gone]
        keep_idx = [i for i in base_idx if i not in gone]
        if not keep_idx:
            continue
        tokens = tokens or [words[i]["w"] for i in keep_idx]
        # tekst je ispravljen u edit.json: 1:1 ili proporcionalno po slovima
        if len(tokens) == len(keep_idx):
            kept += list(zip(keep_idx, tokens))
        else:
            kept.append((keep_idx, tokens))
        run_start = keep_idx[0]
        for j, i in enumerate(keep_idx):
            last = j == len(keep_idx) - 1 or keep_idx[j + 1] != i + 1
            if last:
                a_w, b_w = words[run_start], words[i]
                lo = a_w["s"] - pre
                if run_start > 0:
                    lo = max(lo, words[run_start - 1]["e"])
                hi = b_w["e"] + post
                if i + 1 < len(words):
                    hi = min(hi, words[i + 1]["s"])
                ranges.append([max(lo, 0.0), min(hi, total)])
                if j + 1 < len(keep_idx):
                    run_start = keep_idx[j + 1]
    if spans:
        ranges = subtract_spans(ranges, spans)
    if all_songs:
        ranges = subtract_spans(ranges, all_songs)
        song_r = [[max(a, 0.0), min(b, total)] for a, b, _ in songs]
        ranges += subtract_spans(song_r, song_cuts) if song_cuts else song_r
        kept.sort(key=lambda k: words[k[0][0] if isinstance(k[0], list) else k[0]]["s"])
    ranges.sort()
    merged = []
    for a, b in ranges:
        if merged and a - merged[-1][1] < 1.0 / fps:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out, off = [], 0.0
    for a, b in merged:
        a, b = round(a * fps) / fps, round(b * fps) / fps
        if b - a < 2.0 / fps:
            continue
        out.append({"a": a, "b": b, "o": off})
        off += b - a
    return out, kept, off


def to_out(t, cuts, starts=None):
    """Vrijeme izvornog videa → vrijeme gotovog videa (None ako je izrezano). Rezovi su poredani i
    razmaknuti barem jedan okvir, pa je kandidat samo zadnji rez koji počinje prije t.
    `starts` = [c["a"] for c in cuts], za mnogo poziva na istim rezovima."""
    k = bisect.bisect_right(starts if starts is not None else [c["a"] for c in cuts], t + 1e-6) - 1
    if k >= 0 and t <= cuts[k]["b"] + 1e-6:
        return cuts[k]["o"] + (t - cuts[k]["a"])
    return None


def out_words(words, kept, cuts, highlights):
    res = []
    starts = [c["a"] for c in cuts]
    for item in kept:
        if isinstance(item[0], list):  # proporcionalna raspodjela ispravljenog teksta
            idxs, tokens = item
            spans = [(to_out(words[i]["s"], cuts, starts), to_out(words[i]["e"], cuts, starts)) for i in idxs]
            spans = [(s, e) for s, e in spans if s is not None and e is not None]
            if not spans:
                continue
            t0, t1 = spans[0][0], spans[-1][1]
            total_chars = sum(len(t) for t in tokens) or 1
            acc = 0
            for t in tokens:
                s = t0 + (t1 - t0) * acc / total_chars
                acc += len(t)
                e = t0 + (t1 - t0) * acc / total_chars
                res.append({"t": t, "s": s, "e": e, "hl": norm_word(t) in highlights})
        else:
            i, t = item
            s, e = to_out(words[i]["s"], cuts, starts), to_out(words[i]["e"], cuts, starts)
            if s is None or e is None:
                continue
            res.append({"t": t, "s": s, "e": max(e, s + 0.05), "hl": norm_word(t) in highlights})
    res.sort(key=lambda w: w["s"])
    return res


def chunk_words(ws, st):
    max_w, max_c = st["max_rijeci"], st.get("max_znakova", 30)
    chunks, cur = [], []
    for w in ws:
        if cur:
            prev = cur[-1]
            chars = sum(len(x["t"]) + 1 for x in cur) + len(w["t"])
            if (len(cur) >= max_w or chars > max_c or w["s"] - prev["e"] > 0.5
                    or prev["t"][-1:] in ".!?" or (prev["t"][-1:] in ",;:" and len(cur) >= 2)):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- titlovi
def split_spans(izvor, cuts):
    """Uspravni izvor podcasta: gdje je u gotovom videu (prije `brzina`) podijeljen kadar (gore/dolje) →
    [(od, do)]. Vrijeme kadrova u izvor["kadrovi"] je vrijeme programa (source.mp4)."""
    shots = [(float(k["od"]), float(k["do"])) for k in (izvor or {}).get("kadrovi") or []
             if k.get("raspored") == "dvoje"]
    out = []
    for c in cuts:
        for a, b in shots:
            lo, hi = max(a, c["a"]), min(b, c["b"])
            if hi - lo > 1e-3:
                s, e = c["o"] + lo - c["a"], c["o"] + hi - c["a"]
                if out and s - out[-1][1] < 1e-3:
                    out[-1] = (out[-1][0], e)
                else:
                    out.append((s, e))
    return out


def split_at(s, e, spans):
    """Događaj titla [s, e] razdijeljen na granicama podijeljenog kadra → [(s, e, na_spoju)]."""
    cuts_t = sorted({x for a, b in spans for x in (a, b) if s + 1e-3 < x < e - 1e-3})
    pts = [s, *cuts_t, e]
    out = []
    for a, b in zip(pts, pts[1:]):
        m = (a + b) / 2
        out.append((a, b, any(x <= m < y for x, y in spans)))
    return out


def write_ass(path, ws, st, edit, W, H, total, spoj=()):
    """spoj = [(od, do)] u vremenu gotovog videa gdje je podijeljen kadar: titlovi idu na spoj (sredina
    visine, između gornjeg i donjeg lica), inače bi stajali preko usta donje osobe."""
    portrait = H > W
    scale = min(W, H) / 1080 * (1.0 if portrait else 0.8)
    fs = round(st["velicina"] * scale)
    up = st.get("velika_slova", False)
    pos = st.get("pozicija", "dolje")
    align = {"dolje": 2, "sredina": 5, "gore": 8}.get(pos, 2)
    mv = round(H * (POS_FRAC.get(pos, 0.24) if portrait else 0.07))
    ml = round(W * 0.08)
    box = st.get("pozadina", False)
    border_style = 3 if box else 1
    outline = round((14 if box else st.get("obrub", 6)) * scale)
    out_col = ass_color(st.get("boja_pozadine", "#000000B0") if box else st.get("boja_obruba", "#000000"))
    shadow = 0 if box else round(st.get("sjena", 0) * scale)
    spacing = st.get("razmak", 0)

    hook_fs = round(st.get("hook_velicina", 68) * scale)
    hook_mv = round(H * (0.12 if portrait else 0.06))
    styles = [
        f"Style: Cap,{st['font']},{fs},{ass_color(st['boja_teksta'])},&H000000FF,{out_col},&H80000000,0,0,0,0,100,100,{spacing},0,{border_style},{outline},{shadow},{align},{ml},{ml},{mv},1",
        f"Style: Hook,{st.get('hook_font', st['font'])},{hook_fs},{ass_color(st.get('hook_boja', '#111111'))},&H000000FF,{ass_color(st.get('hook_pozadina', '#FFFFFF'))},&H00000000,0,0,0,0,100,100,0,0,3,{round(18 * scale)},0,8,{ml},{ml},{hook_mv},1",
        f"Style: Bar,Arial,10,{ass_color(st['boja_trake'])},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    hl_c = ass_color(st["boja_isticanja"])
    acc_c = ass_color(st["boja_naglaska"])
    pop = st.get("pop", 1.0)
    reveal = st.get("otkrivanje", False)
    mode = st.get("nacin", "karaoke")

    def T(w):
        return esc(w["t"].upper() if up else w["t"])

    ev = []
    if edit.get("titlovi", True):
        chunks = chunk_words(ws, st)
        for n, ch in enumerate(chunks):
            start = ch[0]["s"]
            nxt = chunks[n + 1][0]["s"] if n + 1 < len(chunks) else total
            end = ch[-1]["e"] + 0.35
            if nxt - ch[-1]["e"] < 0.3:
                end = nxt
            end = max(min(end, nxt), start + 0.3)
            if mode == "linija":
                txt = " ".join((f"{{\\c{acc_c}}}{T(w)}{{\\r}}" if w["hl"] else T(w)) for w in ch)
                ev.append((0, start, end, "Cap", txt))
            elif mode == "rijec":
                for j, w in enumerate(ch):
                    s = start if j == 0 else w["s"]
                    e = ch[j + 1]["s"] if j + 1 < len(ch) else end
                    big = 115 if w["hl"] else 100
                    col = f"\\c{acc_c}" if w["hl"] else ""
                    txt = f"{{{col}\\fscx{int(big * 0.7)}\\fscy{int(big * 0.7)}\\t(0,90,\\fscx{big}\\fscy{big})}}{T(w)}"
                    ev.append((0, s, max(e, s + 0.1), "Cap", txt))
            else:  # karaoke
                for j, w in enumerate(ch):
                    s = start if j == 0 else w["s"]
                    e = ch[j + 1]["s"] if j + 1 < len(ch) else end
                    parts = []
                    for k, x in enumerate(ch):
                        if k == j:
                            p = int(pop * 100)
                            parts.append(f"{{\\c{hl_c}\\fscx{p}\\fscy{p}}}{T(x)}{{\\r}}")
                        elif k > j and reveal:
                            parts.append(f"{{\\alpha&HFF&}}{T(x)}{{\\r}}")
                        elif x["hl"]:
                            parts.append(f"{{\\c{acc_c}}}{T(x)}{{\\r}}")
                        else:
                            parts.append(T(x))
                    ev.append((0, s, max(e, s + 0.05), "Cap", " ".join(parts)))

    hook = (edit.get("hook") or "").strip()
    if hook:
        hd = min(float(edit.get("hook_trajanje") or 3.0), total)
        ht = esc(hook.upper() if st.get("hook_velika_slova", True) else hook)
        ev.append((2, 0, hd, "Hook", f"{{\\fad(100,220)\\fscx85\\fscy85\\t(0,160,\\fscx100\\fscy100)}}{ht}"))
    if st.get("traka_napretka"):
        bh = max(6, round(H * 0.006))
        ev.append((5, 0, total, "Bar",
                   f"{{\\an7\\pos(0,0)\\p1\\clip(0,0,0,{bh})\\t(\\clip(0,0,{W},{bh}))}}m 0 0 l {W} 0 {W} {bh} 0 {bh}{{\\p0}}"))

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if spoj:
        seam = f"{{\\an5\\pos({W // 2},{H // 2})}}"
        moved = []
        for layer, s, e, sty, txt in ev:
            if sty != "Cap":
                moved.append((layer, s, e, sty, txt))
                continue
            for a, b, na_spoju in split_at(s, e, spoj):
                moved.append((layer, a, b, sty, seam + txt if na_spoju else txt))
        ev = moved
    for layer, s, e, sty, txt in sorted(ev, key=lambda x: x[1]):
        lines.append(f"Dialogue: {layer},{ass_time(s)},{ass_time(e)},{sty},,0,0,0,,{txt}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- zoom
def zoom_ranges(cuts, st):
    z = ZOOM.get(st.get("zoom", "nema"))
    if not z:
        return None, []
    factor, min_gap = z
    on, last, res = False, 0.0, []
    for n, c in enumerate(cuts):
        if n > 0 and c["o"] - last >= min_gap:
            on, last = not on, c["o"]
        if on:
            s, e = c["o"], c["o"] + (c["b"] - c["a"])
            if res and abs(res[-1][1] - s) < 1e-6:
                res[-1][1] = e
            else:
                res.append([s, e])
    return factor, res


def zoom_chain(factor, W, H):
    return f"scale=w='trunc(iw*{factor}/2)*2':h=-2:flags=bicubic,crop={W}:{H}:(iw-{W})/2:(ih-{H})*0.38"


# ---------------------------------------------------------------- glavno
def learn_vocabulary(proj, edit, words):
    """Rječnik uči iz ispravaka teksta u ovoj verziji; greška u rječniku nikad ne ruši render."""
    try:
        import rjecnik
        new, lost, _ = rjecnik.learn(proj, edit, words)
        rjecnik.report_learned(new, lost)
    except Exception as e:  # noqa: BLE001
        print(f"(rječnik nije ažuriran: {e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--brzo", action="store_true", help="brzi pregled u pola rezolucije")
    ap.add_argument("--kvaliteta", default="dobra", choices=["dobra", "visoka"])
    ap.add_argument("--kadar", default=None, help="sekunde gotovog reela, npr. 1,4.5,12 → PNG slike")
    ap.add_argument("--izlaz", default=None, help="ime izlazne datoteke")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    if not (proj / "edit.json").exists():
        die(f"nedostaje {proj / 'edit.json'}")
    render(proj, load_json(proj / "edit.json"), izlaz=a.izlaz, brzo=a.brzo, kvaliteta=a.kvaliteta, kadar=a.kadar)


def render(proj, edit_raw, izlaz=None, brzo=False, kvaliteta="dobra", kadar=None, verzija=None,
           prevedi=True, ispis=True, izvor=None):
    """Montaža po `edit_raw` (rječnik u formatu edit.json) → video + SRT (+ FCPXML).

    izlaz   = putanja izlaza relativno na projekt (npr. "isjecci/K1.mp4"); None = nova verzija reel_vN.
    verzija = upiši u verzije/ (zadano: samo kad nema `izlaz`); prevedi = i prijevodi titlova.
    izvor   = drugi video umjesto source.mp4 (uspravni isječak podcasta): {"datoteka", "pomak", "W", "H"};
              njegova 0 s je `pomak` s source.mp4, pa vremena transkripta i rezova vrijede bez promjene.
    Vraća {"video", "srt", "trajanje", "kadrova", "zumova"} (za `kadar`: {"slike": [...]}).
    """
    import copy
    proj = Path(proj).resolve()
    for f in ("project.json", "transcript.json", "source.mp4"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    if verzija is None:
        verzija = not izlaz
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = copy.deepcopy(edit_raw)
    edit_raw = copy.deepcopy(edit_raw)  # neizmijenjena kopija za verzije/edit_vN.json
    W, H, fps = pj["width"], pj["height"], pj["fps"]
    if izvor:
        W, H = izvor["W"], izvor["H"]
        src_in = ["-itsoffset", f"{float(izvor['pomak']):.4f}", "-i", Path(izvor["datoteka"]).resolve()]
    else:
        src_in = ["-i", proj / "source.mp4"]
    st = resolve_style(edit)
    speed = float(edit.get("brzina") or 1.0)
    if not 0.5 <= speed <= 2.0:
        die("brzina mora biti između 0.5 i 2.0")

    cuts, kept, total = build_cuts(words, edit, st, fps, pj["duration"])
    if not cuts:
        die("nema ničega za zadržati (svi odsječci su isključeni?)")
    highlights = {norm_word(x) for p in edit.get("naglasi", []) for x in p.split()}
    ws = out_words(words, kept, cuts, highlights)

    # fontovi i titlovi u mapi projekta (izbjegava Windows probleme s putanjama u ffmpeg filterima)
    fdir = proj / "fonts"
    fdir.mkdir(exist_ok=True)
    for f in FONTS_DIR.glob("*.ttf"):
        if not (fdir / f.name).exists():
            shutil.copy2(f, fdir / f.name)
    write_ass(proj / "captions.ass", ws, st, edit, W, H, total, spoj=split_spans(izvor, cuts))
    subs = "subtitles=filename=captions.ass:fontsdir=fonts"
    grade = GRADES.get(st.get("boja_slike", "neutralno"), GRADES["neutralno"])
    factor, zr = zoom_ranges(cuts, st)

    if kadar:
        return {"slike": stills_mode(kadar, proj, cuts, zr, factor, grade, subs, speed, W, H, total, izvor)}

    eps = 0.5 / fps
    sel = "+".join(f"between(t,{c['a'] - eps:.4f},{c['b'] - eps:.4f})" for c in cuts)
    g = [f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB,{grade}" + (",split=2[base][zs]" if zr else "[v1]")]
    if zr:
        en = "+".join(f"between(t,{s:.4f},{e - eps:.4f})" for s, e in zr)
        g.append(f"[zs]{zoom_chain(factor, W, H)}[zz]")
        g.append(f"[base][zz]overlay=0:0:enable='{en}'[v1]")
    vtail = f"[v1]{subs}"
    if speed != 1.0:
        vtail += f",setpts=PTS/{speed}"
    if brzo:
        vtail += f",scale={W // 2}:-2"
    g.append(vtail + ",format=yuv420p[vout]")

    n = len(cuts)
    inputs = list(src_in)
    parts = song_out_parts(edit, cuts)
    music = edit.get("glazba")
    if music:
        mp = Path(music)
        if not mp.is_absolute():
            mp = (proj / mp) if (proj / mp).exists() else Path.cwd() / mp
        if not mp.exists():
            die(f"glazba ne postoji: {music}")
        inputs += ["-stream_loop", "-1", "-i", mp]

    def measure(lines, label, name):
        """Zvučni graf bez slike → momentarne glasnoće (EBU R128) u vremenu gotovog videa (prije brzine)."""
        fm = proj / "_tmp" / f"graf_{name}.txt"
        fm.parent.mkdir(exist_ok=True)
        fm.write_text(";\n".join(lines + [f"{label}ebur128=metadata=1,"
                                          "ametadata=mode=print:key=lavfi.r128.M:file=-[am]"]), encoding="utf-8")
        r = run([ffmpeg(), "-v", "error", "-nostdin", *inputs, *filter_script_args(fm), "-map", "[am]",
                 "-f", "null", "-"], cwd=proj)
        return parse_momentary(r.stdout)

    glasnoca, gains = None, None
    if parts:  # pjesma u videu: prvi prolaz izmjeri govor i pjesme, drugi ih izjednači (bez dinamičkog loudnorma)
        if ispis:
            print("Mjerim glasnoću govora i pjesama ...")
        ga, last = audio_graph(cuts, st, edit, total, parts, None, bool(music))
        glasnoca = loudness_plan(measure(ga, last, "glasnoca"), parts, song_levels(edit, len(song_spans(edit)[0])))
    if glasnoca:
        levels = song_levels(edit, len(song_spans(edit)[0]))
        for _ in range(2):
            # limiter vrhova stisne glasne dijelove (bubanj!) pa su pjesma i video tiši od cilja: izmjeri što je
            # izašlo iz limitera i ispravi pojačanja (najviše dvaput)
            gk = {x["k"]: 10 ** (x["pojacanje"] / 20) for x in glasnoca["pjesme"]}
            gains = [gk.get(k, 1.0) for _, _, k in parts]
            ga, last = audio_graph(cuts, st, edit, total, parts, gains, bool(music))
            chk = loudness_plan(measure(ga + [f"{last}{final_gain(glasnoca['pojacanje'])}[lim]"], "[lim]",
                                        "provjera"), parts, levels)
            if not chk:
                break
            glasnoca["provjera"] = {"govor": chk["govor"], "ukupno": chk["ukupno"],
                                    "pjesme": [x["izmjereno"] for x in chk["pjesme"]]}
            fix = {x["k"]: x["pojacanje"] for x in chk["pjesme"] if x["izmjereno"] is not None}
            if max([abs(v) for v in fix.values()] + [abs(chk["pojacanje"])]) < 0.4:
                break
            for x in glasnoca["pjesme"]:
                x["pojacanje"] = round(max(SONG_GAIN_MAX[0], min(SONG_GAIN_MAX[1],
                                                                 x["pojacanje"] + 1.2 * fix.get(x["k"], 0.0))), 2)
            glasnoca["pojacanje"] = round(glasnoca["pojacanje"] + max(-6.0, min(6.0, 1.15 * chk["pojacanje"])), 2)
        gk = {x["k"]: 10 ** (x["pojacanje"] / 20) for x in glasnoca["pjesme"]}
        gains = [gk.get(k, 1.0) for _, _, k in parts]
        ga, last = audio_graph(cuts, st, edit, total, parts, gains, bool(music))
        if ispis:
            for line in loudness_lines(glasnoca, edit):
                print(line)
    else:
        ga, last = audio_graph(cuts, st, edit, total, parts, None, bool(music))
    g += ga
    atail = f"{last}"
    atail += f"atempo={speed}," if speed != 1.0 else ""
    fades = audio_fades(edit, total / speed)
    if glasnoca:  # jedno stalno pojačanje do −14 LUFS + limiter vrhova (4× nadotipkavanje = true peak)
        g.append(f"{atail}{final_gain(glasnoca['pojacanje'])},aresample=48000{fades}[aout]")
    else:
        g.append(f"{atail}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000{fades}[aout]")

    fg = proj / "_tmp" / "graf.txt"
    fg.parent.mkdir(exist_ok=True)
    fg.write_text(";\n".join(g), encoding="utf-8")

    v = None
    if izlaz:
        out = proj / izlaz
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        v = verzije.next_number(proj)
        out = proj / (f"reel_v{v}_pregled.mp4" if brzo else f"reel_v{v}.mp4")
    rel = out.relative_to(proj).as_posix()  # ffmpeg radi u mapi projekta

    preset, crf = ("ultrafast", 26) if brzo else (("medium", 17) if kvaliteta == "visoka" else ("veryfast", 18))
    cmd = [ffmpeg(), "-y", "-v", "error", *inputs, *filter_script_args(fg),
           "-map", "[vout]", "-map", "[aout]", "-r", fps,
           "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", rel]
    if ispis:
        print(f"Renderiram {rel} ({st.get('naziv', edit.get('stil'))}, {n} rezova)...")
    run(cmd, cwd=proj)

    final = total / speed
    # titlovi kao datoteka uz video (isto ime → YouTube, VLC i DaVinci ih nađu)
    srt = out.with_suffix(".srt")
    cues = titlovi.make_cues([dict(w, s=w["s"] / speed, e=w["e"] / speed) for w in ws], final, fps)
    titlovi.write_srt(srt, cues)
    translated = []
    if prevedi:
        import prijevod  # engleski (ili drugi) titlovi, ako ih projekt već prevodi
        translated = prijevod.for_render(proj, cues, out)
    import davinci  # timeline za DaVinci Resolve s istim rezovima (originalne snimke)
    resolve_lines = davinci.for_render(proj, edit_raw, out, izvor=izvor)
    if verzija and v is not None:  # nova verzija: točno ovaj edit.json, datum, trajanje; korisnik sada gleda nju
        verzije.record_render(proj, v, edit_raw, out.name, final, brzo, kvaliteta)
        learn_vocabulary(proj, edit_raw, words)
    res = {"video": out, "srt": srt, "trajanje": final, "kadrova": n, "zumova": len(zr), "glasnoca": glasnoca,
           "ispis": translated + resolve_lines}
    if not ispis:
        return res
    removed = [s["id"] for s in edit["odsjecci"] if not s.get("zadrzi", True)]
    print(f"\nGotovo: {out}" + (f"  (verzija {v}; popis i usporedba: python verzije.py {proj.name})" if v else ""))
    print(f"Titlovi za YouTube: {srt.name}")
    for line in translated:
        print(line)
    for line in resolve_lines:
        print(line)
    print(f"Trajanje: {fmt_time(pj['duration'])} → {fmt_time(final)}  (izrezano {pj['duration'] - final:.1f}s, {n} kadrova, {len(zr)} zumova)")
    if removed:
        print(f"Izbačeni odsječci: {', '.join('#' + str(i) for i in removed)}")
    if edit.get("izrezi"):
        print(f"Izrezano naredbama (dijelova: {len(edit['izrezi'])}), popis: python uredi.py {proj.name} popis")
    return res


def audio_fades(edit, dur):
    """edit.json "pretapanje_zvuka": [ulaz s, izlaz s] (isječak iz pjesme: krene na udarac, utiša se na kraju)."""
    p = edit.get("pretapanje_zvuka")
    if not p:
        return ""
    try:
        a, b = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError):
        return ""
    a, b = max(0.0, min(a, dur / 4)), max(0.0, min(b, dur / 3))
    out = f",afade=t=in:d={a:.3f}" if a > 0 else ""
    if b > 0:
        out += f",afade=t=out:st={max(0.0, dur - b):.3f}:d={b:.3f}"
    return out


def audio_graph(cuts, st, edit, total, parts, gains, music):
    """Zvučni dio filtergrafa do miksa (bez završne glasnoće) → (filteri, oznaka izlaza).
    parts = pjesme u videu [(od, do, k)], gains = faktor po dijelu pjesme (None = 1), music = ulaz 1:a."""
    g = []
    n = len(cuts)
    if n <= 250:  # svaki rez s mikro-pretapanjem da nema pucketanja
        g.append(f"[0:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n)))
        for i, c in enumerate(cuts):
            d = c["b"] - c["a"]
            g.append(f"[s{i}]atrim={c['a']:.4f}:{c['b']:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=0.008,afade=t=out:st={max(d - 0.012, 0):.4f}:d=0.012[c{i}]")
        g.append("".join(f"[c{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[vraw]")
    else:
        asel = "+".join(f"between(t,{c['a']:.4f},{c['b']:.4f})" for c in cuts)
        g.append(f"[0:a]aselect='{asel}',asetpts=N/SR/TB[vraw]")
    clean = ",afftdn=nf=-25" if st.get("zvuk_ciscenje", True) else ""
    speech_chain = f"highpass=f=70{clean},acompressor=threshold=-21dB:ratio=3:attack=5:release=120:makeup=2"
    spans = [(s, e) for s, e, _ in parts]
    gm = song_gain_expr(spans)
    if gm:  # pjesme: zvuk za glazbu (bez čišćenja šuma i govornog kompresora), pretapanje 0,25 s
        gw = song_gain_expr(spans, gains=gains)
        g.append("[vraw]asplit=2[vsp][vmu]")
        g.append(f"[vsp]{speech_chain},volume='1-({gm})':eval=frame[vs]")
        g.append(f"[vmu]{MUSIC_CHAIN},volume='{gw}':eval=frame[vm]")
        g.append("[vs][vm]amix=inputs=2:duration=first:normalize=0[voice]")
    else:
        g.append(f"[vraw]{speech_chain}[voice]")
    if not music:
        return g, "[voice]"
    vol = float(edit.get("glazba_glasnoca") or -20)
    g.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
             f"loudnorm=I=-16:TP=-2,aresample=48000,volume={vol}dB,afade=t=in:d=0.6,"
             f"afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5"
             + (f",volume='1-({gm})':eval=frame" if gm else "") + "[mus]")  # pozadinska glazba šuti dok bend svira
    g.append("[voice]asplit=2[vo][sc]")
    g.append("[mus][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck]")
    g.append("[vo][duck]amix=inputs=2:duration=first:normalize=0[mix]")
    return g, "[mix]"


def stills_mode(kadar, proj, cuts, zr, factor, grade, subs, speed, W, H, total, izvor=None):
    times = [float(x) for x in str(kadar).split(",") if x.strip()]
    pngs = []
    for k, t in enumerate(times):
        pre = min(max(t * speed, 0), total - 0.01)
        c = next((c for c in cuts if c["o"] <= pre < c["o"] + (c["b"] - c["a"])), cuts[-1])
        src_t = c["a"] + (pre - c["o"])
        chain = [grade]
        if any(s <= pre < e for s, e in zr):
            chain.append(zoom_chain(factor, W, H))
        chain += [f"setpts=PTS-STARTPTS+{pre:.3f}/TB", subs]
        png = proj / f"kadar_{k + 1}_{t:g}s.png"
        src, off = (Path(izvor["datoteka"]).resolve(), float(izvor["pomak"])) if izvor else ("source.mp4", 0.0)
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, src_t - off):.3f}", "-i", src, "-frames:v", "1",
             "-vf", ",".join(chain), png.name], cwd=proj)
        pngs.append(png)
    if len(pngs) > 1:
        tw = 360
        args = []
        for p in pngs:
            args += ["-i", p.name]
        fc = "".join(f"[{i}:v]scale={tw}:-2[s{i}];" for i in range(len(pngs)))
        fc += "".join(f"[s{i}]" for i in range(len(pngs))) + f"hstack=inputs={len(pngs)}"
        run([ffmpeg(), "-y", "-v", "error", *args, "-filter_complex", fc, "kadrovi.png"], cwd=proj)
        print(f"Kadrovi: {proj / 'kadrovi.png'}")
        return pngs + [proj / "kadrovi.png"]
    print(f"Kadar: {pngs[0]}")
    return pngs


if __name__ == "__main__":
    main()
