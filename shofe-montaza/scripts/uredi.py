"""Montaža po naredbi: vremena iz GOTOVOG videa → izmjene edit.json.

  python uredi.py shofe_projekt makni 1:20-1:45            makni taj dio gotovog videa
  python uredi.py shofe_projekt makni 0:05-0:08 1:20-1:45  više dijelova odjednom
  python uredi.py shofe_projekt zadrzi 0:10-0:40           zadrži samo taj dio (ostalo van)
  python uredi.py shofe_projekt popis                      što je gdje u gotovom videu
  python uredi.py shofe_projekt vrati                      poništi zadnju naredbu

Po sadržaju (Claude pronađe dio u transcript.txt i citira ga doslovno):
  python uredi.py shofe_projekt trazi "cijena"                       gdje se spominje (riječi, vremena)
  python uredi.py shofe_projekt makni --od "Koliko košta" --do "eura."  od citata do citata
  python uredi.py shofe_projekt makni --od "Radimo i subotom" --cijele-recenice
  python uredi.py shofe_projekt zadrzi --odsjecak 5-7 | --rijeci 40-62 | --tema "cijena"
  python uredi.py shofe_projekt dodaj --odsjecak 3                   vrati izbačeni dio (npr. drugi pokušaj)

Vremena su ona koja korisnik vidi u zadnjem renderiranom videu (reel_vN.mp4), jer on gleda taj video.
--verzija N  → vremena iz reel_vN;  --trenutno → vremena prema trenutnom edit.json (sljedeći render).
Rezovi se poravnaju na granice riječi (riječ ide van ako joj je sredina u dijelu), nikad usred riječi.
U edit.json se upisuju u `izrezi` kao vremena izvornog videa, pa ih kasnije izmjene ne pomiču.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

import copy

from common import die, fmt_time, load_json, save_json
from render import align_tokens, build_cuts, resolve_style, to_out
import sadrzaj

TIME = r"\d+(?::\d{1,2}){0,2}(?:[.,]\d+)?s?"
RANGE = re.compile(rf"(?:od\s+)?({TIME})\s*(?:-|do)\s*({TIME})")
NAREDBE = {"makni": "makni", "izrezi": "makni", "izreži": "makni", "obrisi": "makni", "obriši": "makni",
           "zadrzi": "zadrzi", "zadrži": "zadrzi", "popis": "popis", "vrati": "vrati", "ponisti": "vrati",
           "poništi": "vrati", "dodaj": "dodaj", "ubaci": "dodaj", "trazi": "trazi", "traži": "trazi",
           "nadji": "trazi", "nađi": "trazi"}


# ---------------------------------------------------------------- vrijeme
def parse_time(s):
    """'1:20', '1:20.5', '1:20,5', '0:01:20', '80', '80.5s' → sekunde."""
    s = s.strip().lower().rstrip("s").replace(",", ".")
    if not re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?", s):
        raise ValueError(f"ne razumijem vrijeme '{s}'")
    parts = s.split(":")
    sec = float(parts[-1])
    if len(parts) > 1 and sec >= 60:
        raise ValueError(f"sekunde moraju biti manje od 60: '{s}'")
    mult = 1
    total = 0.0
    for p in reversed(parts):
        total += float(p) * mult
        mult *= 60
    return total


def parse_ranges(args):
    """['1:20-1:45', 'i', 'od', '2:00', 'do', '2:10'] → [(80, 105), (120, 130)]"""
    text = " ".join(args).lower()
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    res = []
    for m in RANGE.finditer(text):
        a, b = parse_time(m.group(1)), parse_time(m.group(2))
        if b <= a:
            raise ValueError(f"kraj mora biti iza početka: '{m.group(0)}'")
        res.append((a, b))
    rest = RANGE.sub(" ", text)
    rest = re.sub(r"\b(od|do|i|te|dio|dijela)\b|[,;]", " ", rest).strip()
    if rest:
        raise ValueError(f"ne razumijem '{rest}' (primjer: 1:20-1:45 ili od 1:20 do 1:45)")
    if not res:
        raise ValueError("nema vremena (primjer: 1:20-1:45)")
    return res


# ---------------------------------------------------------------- vremenska crta gotovog videa
def segment_of(words, edit):
    owner = {}
    for seg in edit["odsjecci"]:
        for i, w in enumerate(words):
            if w["s"] >= seg["od"] - 0.01 and w["e"] <= seg["do"] + 0.01:
                owner.setdefault(i, seg["id"])
    return owner


def timeline(words, edit, pj):
    """Riječi koje su u gotovom videu: [{i, s, e, t, seg}] s vremenima gotovog videa (nakon brzine)."""
    st = resolve_style(edit)
    speed = float(edit.get("brzina") or 1.0)
    cuts, kept, total = build_cuts(words, edit, st, pj["fps"], pj["duration"])
    owner = segment_of(words, edit)
    out = []
    for item in kept:
        if isinstance(item[0], list):
            idxs, tokens = item
            pairs = [(i, " ".join(tokens) if k == 0 else "") for k, i in enumerate(idxs)]
        else:
            pairs = [item]
        for i, tok in pairs:
            s, e = to_out(words[i]["s"], cuts), to_out(words[i]["e"], cuts)
            if s is None or e is None:
                continue
            out.append({"i": i, "s": s / speed, "e": e / speed, "t": tok, "seg": owner.get(i)})
    out.sort(key=lambda w: w["s"])
    return out, total / speed


def source_spans(words, idxs):
    """Indeksi riječi za izbaciti → dijelovi izvornog videa, granice u pauzama između riječi."""
    idxs = sorted(set(idxs))
    groups = []
    for i in idxs:
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    spans = []
    for g in groups:
        first, last = words[g[0]], words[g[-1]]
        if g[0] > 0:
            od = first["s"] - min(0.3, max(first["s"] - words[g[0] - 1]["e"], 0) / 2)
        else:
            od = max(first["s"] - 0.3, 0.0)
        if g[-1] + 1 < len(words):
            do = last["e"] + min(0.3, max(words[g[-1] + 1]["s"] - last["e"], 0) / 2)
        else:
            do = last["e"] + 0.3
        spans.append((round(od, 3), round(do, 3), g))
    return spans


def n_rijeci(n):
    return f"{n} riječ" if n % 10 == 1 and n % 100 != 11 else f"{n} riječi"


def excerpt(ws, n=4):
    toks = [w["t"] for w in ws if w["t"]]
    if len(toks) <= 2 * n:
        return " ".join(toks)
    return " ".join(toks[:n]) + " … " + " ".join(toks[-n:])


# ---------------------------------------------------------------- povijest (za "vrati")
def save_history(proj, naredba):
    hist = proj / "povijest"
    hist.mkdir(exist_ok=True)
    nums = [int(m.group(1)) for p in hist.glob("*.json") if (m := re.match(r"(\d+)", p.stem))]
    n = max(nums, default=0) + 1
    slug = re.sub(r"[^\w]+", "_", naredba, flags=re.UNICODE).strip("_")[:40]
    shutil.copy2(proj / "edit.json", hist / f"{n:03d}_{slug}.json")


def undo(proj):
    hist = proj / "povijest"
    files = sorted(hist.glob("*.json"), key=lambda p: int(re.match(r"(\d+)", p.stem).group(1))) if hist.exists() else []
    if not files:
        die("nema ništa za vratiti (povijest je prazna)")
    last = files[-1]
    shutil.copy2(last, proj / "edit.json")
    last.unlink()
    label = last.stem.split("_", 1)[1].replace("_", " ") if "_" in last.stem else last.stem
    print(f"Vraćeno stanje prije naredbe: {label}")
    print(f"Preostalo koraka za vratiti: {len(files) - 1}")


# ---------------------------------------------------------------- po sadržaju
def corrected_forms(words, edit):
    """Claudeovi ispravci teksta iz edit.json po riječi (da citat iz ispravljenog teksta isto radi)."""
    alt = {}
    for seg in edit["odsjecci"]:
        idx = [i for i, w in enumerate(words) if w["s"] >= seg["od"] - 0.01 and w["e"] <= seg["do"] + 0.01]
        toks = (seg.get("tekst") or "").split()
        if not idx or not toks:
            continue
        for t, o in zip(toks, align_tokens(toks, [words[i]["w"] for i in idx])):
            alt.setdefault(idx[o], []).append(t)
    return alt


def select(words, edit, proj, a):
    """Odabir riječi po sadržaju → (indeksi, opis). Više odabira se zbraja."""
    tr = sadrzaj.Transkript(words, corrected_forms(words, edit))
    sel, opis = [], []
    if a.od:
        i, j = sadrzaj.by_quote(tr, a.od, a.do, a.pojava)
        sel += range(i, j + 1)
        opis.append(f"„{a.od}“" + (f" … „{a.do}“" if a.do else ""))
    elif a.do:
        raise sadrzaj.Greska("--do ide uz --od (početak citata)")
    if a.rijeci:
        nums = sadrzaj.parse_nums(a.rijeci, "riječ")
        bad = [n for n in nums if n >= len(words)]
        if bad:
            raise sadrzaj.Greska(f"nema riječi #{bad[0]} (riječi su 0–{len(words) - 1})")
        sel += nums
        opis.append(f"riječi {a.rijeci}")
    if a.odsjecak:
        sel += sadrzaj.by_segments(words, edit, a.odsjecak)
        opis.append(f"odsječak {a.odsjecak}")
    if a.tema:
        an = load_json(proj / "analiza.json") if (proj / "analiza.json").exists() else None
        got, t = sadrzaj.by_topic(words, an, a.tema)
        sel += got
        opis.append(f"tema „{t.get('naslov', '')}“")
    sel = sorted(set(sel))
    if not sel:
        raise sadrzaj.Greska("odabrani dio nema riječi")
    if a.cijele_recenice:
        full = set()
        for g in groups_of(sel):
            lo, hi = sadrzaj.sentence_bounds(words, g[0], g[-1])
            full.update(range(lo, hi + 1))
        sel = sorted(full)
    return sel, ", ".join(opis)


def groups_of(idxs):
    groups = []
    for i in sorted(set(idxs)):
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def segment_ids_of(words, edit, i):
    w = words[i]
    return [s["id"] for s in edit["odsjecci"] if w["s"] >= s["od"] - 0.01 and w["e"] <= s["do"] + 0.01]


def apply_target(words, edit, pj, target, label_cmd):
    """Novi edit.json u kojem gotovi video ima točno riječi iz `target` (osim poštapalica iz `izbaci`).

    Riječi koje se vraćaju: njihov odsječak dobiva zadrzi=true, a izrezi koji ih pokrivaju se skrate.
    Riječi koje odlaze: novi izrezi (vrijeme izvornog videa), kao kod naredbi po vremenu.
    """
    target = set(target)
    e2 = copy.deepcopy(edit)
    n = max((r.get("n", 0) for r in edit.get("izrezi") or []), default=0) + 1
    # 1) izrezi ne smiju pokrivati riječi koje trebaju ostati
    izrezi = []
    for r in e2.get("izrezi") or []:
        inside = [i for i, w in enumerate(words) if r["od"] <= (w["s"] + w["e"]) / 2 < r["do"]]
        if not any(i in target for i in inside):
            izrezi.append(r)
            continue
        for od, do, g in source_spans(words, [i for i in inside if i not in target]):
            izrezi.append(dict(r, od=od, do=do, tekst=excerpt([{"t": words[i]["w"]} for i in g], 3)))
    e2["izrezi"] = izrezi
    # 2) odsječci s riječima koje trebaju ostati moraju biti uključeni
    bez = []
    for i in sorted(target):
        ids = segment_ids_of(words, e2, i)
        if not ids:
            bez.append(i)
        for s in e2["odsjecci"]:
            if s["id"] in ids and not s.get("zadrzi", True):
                s["zadrzi"] = True
                s["napomena"] = (s.get("napomena", "") + f" | vraćeno [{n}]").strip(" |")
    # 3) sve ostalo van
    tl, _ = timeline(words, e2, pj)
    remove = [w["i"] for w in tl if w["i"] not in target]
    by_i = {w["i"]: w for w in tl}
    for od, do, g in source_spans(words, remove):
        e2["izrezi"].append({"od": od, "do": do, "n": n, "naredba": label_cmd,
                             "tekst": excerpt([by_i[i] for i in g if i in by_i], 3)})
    if not e2["izrezi"]:
        e2.pop("izrezi")
    return e2, bez


def cmd_trazi(words, edit, pj, ref, label, query, proj):
    tr = sadrzaj.Transkript(words, corrected_forms(words, edit))
    hits = tr.find(query)
    if not hits:  # cijeli citat nije pronađen → svaka riječ posebno
        for t in sadrzaj.tokens(query):
            hits += tr.find(t)
        hits = sorted(set(hits))
    if not hits:
        sug = tr.nearest(query)
        print(f"„{query}“ nije pronađeno." + (" Najsličnije:\n  " + "\n  ".join(sug) if sug else ""))
        return
    ref_t = {w["i"]: w["s"] for w in timeline(words, ref, pj)[0]}
    cur = {w["i"] for w in timeline(words, edit, pj)[0]}
    print(f"„{query}“: {len(hits)} pojava. Vrijeme u videu prema: {label}")
    for a, b, _ in hits:
        vid = f"video {fmt_time(ref_t[a])}" if a in ref_t else "video —   "
        state = "" if a in cur else "  (nije u videu)"
        seg = ",".join(f"#{x}" for x in segment_ids_of(words, edit, a))
        print(f"  riječ {a:<5} izvor {fmt_time(words[a]['s'])}  {vid}  {seg:<5} {tr.context(a, b)}{state}")
    print(f"Za rez: python uredi.py {proj.name} makni --od \"…\" --do \"…\"  (ili --rijeci {hits[0][0]}-…)")


def cmd_sadrzaj(proj, naredba, words, edit, pj, a):
    try:
        sel, opis = select(words, edit, proj, a)
    except sadrzaj.Greska as e:
        die(str(e))
    cur_tl, cur_dur = timeline(words, edit, pj)
    cur = [w["i"] for w in cur_tl]
    cur_set = set(cur)
    sel_set = set(sel)
    if naredba == "makni":
        target = [i for i in cur if i not in sel_set]
        changed = [i for i in sel if i in cur_set]
        if not changed:
            print(f"Ništa za promijeniti: {opis} već nije u videu.")
            return
    elif naredba == "zadrzi":
        target = sel
        changed = [i for i in cur if i not in sel_set] + [i for i in sel if i not in cur_set]
    else:  # dodaj
        target = sorted(cur_set | sel_set)
        changed = [i for i in sel if i not in cur_set]
        if not changed:
            print(f"Ništa za promijeniti: {opis} je već u videu.")
            return
    label_cmd = f"{naredba} {opis}"
    edit2, bez = apply_target(words, edit, pj, target, label_cmd)
    new_tl, new_dur = timeline(words, edit2, pj)
    new_set = {w["i"] for w in new_tl}
    by_i = {w["i"]: w for w in cur_tl}
    disp = lambda i: by_i.get(i, {"t": words[i]["w"]})  # noqa: E731
    gone = [i for i in cur if i not in new_set]
    added = [i for i in sorted(new_set) if i not in cur_set]

    print(f"Odabrano ({opis}): izvor {fmt_time(words[sel[0]]['s'])}-{fmt_time(words[sel[-1]]['e'])}, "
          f"{n_rijeci(len(sel))}: „{excerpt([disp(i) for i in sel], 6)}“")
    for g in groups_of(gone):
        print(f"  van:   video {fmt_time(by_i[g[0]]['s'])}-{fmt_time(by_i[g[-1]]['e'])}  „{excerpt([by_i[i] for i in g], 5)}“")
    new_by = {w["i"]: w for w in new_tl}
    for g in groups_of(added):
        print(f"  vraća: video {fmt_time(new_by[g[0]]['s'])}-{fmt_time(new_by[g[-1]]['e'])}  „{excerpt([new_by[i] for i in g], 5)}“")
    for i in bez:
        print(f"  napomena: riječ „{words[i]['w']}“ nije ni u jednom odsječku (od/do su skraćeni) — proširi odsječak ručno")
    edges = sel if naredba != "makni" else [i for i in sel if i in cur_set]
    for note in sadrzaj.edge_notes(words, edges):
        print(f"  napomena: odabir {note} — ako je to cijela misao, dodaj --cijele-recenice")
    print(f"Trajanje: {fmt_time(cur_dur)} → {fmt_time(new_dur)} ({new_dur - cur_dur:+.1f} s)")
    if not new_tl:
        die("nakon ovoga u videu ne bi ostalo ništa")
    if a.proba:
        print("(proba: edit.json nije promijenjen)")
        return
    save_history(proj, label_cmd)
    save_json(proj / "edit.json", edit2)
    print(f"Upisano u edit.json. Poništi: python uredi.py {proj.name} vrati")
    print(f"Sljedeće: python render.py {proj.name} --kadar ... ili render")


# ---------------------------------------------------------------- glavno
def reference_edit(proj, edit, a):
    """Prema kojoj verziji se čitaju vremena: zadnji render (ono što je korisnik gledao)."""
    if a.trenutno:
        return edit, "trenutni edit.json (sljedeći render)"
    vdir = proj / "verzije"
    found = {int(m.group(1)): p for p in vdir.glob("edit_v*.json") if (m := re.fullmatch(r"edit_v(\d+)", p.stem))} \
        if vdir.exists() else {}
    if a.verzija is not None:
        if a.verzija not in found:
            die(f"nema verzije {a.verzija} (postoje: {', '.join(map(str, sorted(found))) or 'nijedna'})")
        return load_json(found[a.verzija]), f"reel_v{a.verzija}"
    if not found:
        return edit, "trenutni edit.json (još nije renderiran)"
    n = max(found)
    return load_json(found[n]), f"reel_v{n} (zadnji render)"


def cmd_popis(words, edit, pj, label):
    tl, dur = timeline(words, edit, pj)
    print(f"Gotovi video prema: {label}, trajanje {fmt_time(dur)}")
    rows, cur = [], None
    for w in tl:
        if cur is None or w["seg"] != cur["seg"] or w["s"] - cur["e"] > 0.6:
            cur = {"seg": w["seg"], "s": w["s"], "e": w["e"], "ws": []}
            rows.append(cur)
        cur["e"] = w["e"]
        cur["ws"].append(w)
    for r in rows:
        sid = f"#{r['seg']}" if r["seg"] is not None else ""
        print(f"  {fmt_time(r['s'])}-{fmt_time(r['e'])}  {sid:<4} {' '.join(w['t'] for w in r['ws'] if w['t'])}")
    iz = edit.get("izrezi") or []
    if iz:
        print("\nIzrezano naredbama (makni/zadrži; vrijeme izvornog videa):")
        for r in iz:
            print(f"  [{r.get('n', '?')}] {fmt_time(r['od'])}-{fmt_time(r['do'])}  {r.get('naredba', '')}  „{r.get('tekst', '')}“")


def main():
    ap = argparse.ArgumentParser(description="Montaža po naredbi s vremenima iz gotovog videa")
    ap.add_argument("projekt")
    ap.add_argument("naredba", help="makni | zadrzi | dodaj | trazi | popis | vrati")
    ap.add_argument("vremena", nargs="*", help="npr. 1:20-1:45 (vrijeme u gotovom videu); za trazi: riječi")
    g = ap.add_argument_group("po sadržaju (umjesto vremena)")
    g.add_argument("--od", help="doslovni citat iz transkripta: početak dijela (ili cijeli dio bez --do)")
    g.add_argument("--do", help="doslovni citat: kraj dijela (traži se iza --od)")
    g.add_argument("--pojava", type=int, default=None, help="koja pojava citata --od, ako ih ima više (1, 2, …)")
    g.add_argument("--rijeci", help="brojevi riječi iz 'trazi', npr. 40-62 ili 40-62,70")
    g.add_argument("--odsjecak", help="brojevi odsječaka iz transcript.txt, npr. 5 ili 5-7,9")
    g.add_argument("--tema", help="tema iz analiza.json: broj ili riječi iz naslova")
    g.add_argument("--cijele-recenice", action="store_true", help="proširi odabir na cijele rečenice")
    ap.add_argument("--verzija", type=int, default=None, help="vremena iz reel_vN (zadano: zadnji render)")
    ap.add_argument("--trenutno", action="store_true", help="vremena prema trenutnom edit.json")
    ap.add_argument("--proba", action="store_true", help="samo pokaži što bi se promijenilo")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    for f in ("project.json", "transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    naredba = NAREDBE.get(a.naredba.lower())
    if not naredba:
        die(f"nepoznata naredba '{a.naredba}' (makni, zadrzi, dodaj, trazi, popis, vrati)")
    if naredba == "vrati":
        undo(proj)
        return
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    ref, label = reference_edit(proj, edit, a)
    content = any([a.od, a.do, a.rijeci, a.odsjecak, a.tema])
    if naredba == "trazi":
        if not a.vremena:
            die("što tražiti? primjer: python uredi.py projekt trazi cijena")
        cmd_trazi(words, edit, pj, ref, label, " ".join(a.vremena), proj)
        return
    if content:
        if naredba not in ("makni", "zadrzi", "dodaj"):
            die("--od/--rijeci/--odsjecak/--tema idu uz makni, zadrzi ili dodaj")
        if a.vremena:
            die("navedi ili vremena ili sadržaj (--od/--rijeci/--odsjecak/--tema), ne oboje")
        cmd_sadrzaj(proj, naredba, words, edit, pj, a)
        return
    if naredba == "dodaj":
        die("dodaj radi po sadržaju: --od \"citat\" [--do \"citat\"], --odsjecak N, --rijeci a-b ili --tema")
    if naredba == "popis":
        cmd_popis(words, ref if (a.verzija is not None) else edit, pj,
                  label if a.verzija is not None else "trenutni edit.json (sljedeći render)")
        return

    try:
        ranges = parse_ranges(a.vremena)
    except ValueError as e:
        die(str(e))
    ref_tl, ref_dur = timeline(words, ref, pj)
    cur_tl, cur_dur = timeline(words, edit, pj)
    cur_idx = {w["i"] for w in cur_tl}

    def inside(w, lo, hi):
        return lo <= (w["s"] + w["e"]) / 2 < hi

    print(f"Vremena prema: {label}, trajanje {fmt_time(ref_dur)}")
    for lo, hi in ranges:
        if lo >= ref_dur:
            die(f"{fmt_time(lo)} je iza kraja videa ({fmt_time(ref_dur)})")
        if hi > ref_dur + 0.5:
            print(f"  napomena: {fmt_time(hi)} je iza kraja videa, uzimam do kraja ({fmt_time(ref_dur)})")
        for t in (lo, hi):
            for w in ref_tl:
                if w["s"] < t < w["e"] and w["t"]:
                    side = "ide van" if inside(w, lo, hi) else "ostaje"
                    print(f"  napomena: {fmt_time(t)} pada usred riječi „{w['t']}“ → cijela riječ {side}")

    picked = [w for w in ref_tl if any(inside(w, lo, hi) for lo, hi in ranges)]
    if naredba == "makni":
        if not picked:
            die("u tom dijelu nema govora koji bi se mogao maknuti (provjeri vremena: python uredi.py "
                f"{proj.name} popis)")
        remove = [w["i"] for w in picked if w["i"] in cur_idx]
        shown = picked
    else:  # zadrzi
        if not picked:
            die("u tom dijelu nema govora; ništa ne bi ostalo")
        keep = {w["i"] for w in picked}
        remove = [w["i"] for w in cur_tl if w["i"] not in keep]
        shown = [w for w in cur_tl if w["i"] not in keep]
    if not remove:
        print("Ništa za promijeniti: taj dio je već izrezan.")
        return

    label_cmd = f"{naredba} " + " ".join(f"{fmt_time(lo)}-{fmt_time(hi)}" for lo, hi in ranges)
    n = max((r.get("n", 0) for r in edit.get("izrezi") or []), default=0) + 1
    by_i = {w["i"]: w for w in cur_tl}
    new = []
    for od, do, g in source_spans(words, remove):
        new.append({"od": od, "do": do, "n": n, "naredba": label_cmd,
                    "tekst": excerpt([by_i[i] for i in g if i in by_i], 3)})
    edit2 = dict(edit)
    edit2["izrezi"] = list(edit.get("izrezi") or []) + new
    _, new_dur = timeline(words, edit2, pj)

    if naredba == "makni":
        for lo, hi in ranges:
            part = [w for w in picked if inside(w, lo, hi)]
            if part:
                print(f"Makni {fmt_time(lo)}-{fmt_time(hi)}: stvarno {fmt_time(part[0]['s'])}-{fmt_time(part[-1]['e'])}, "
                      f"{n_rijeci(len(part))}: „{excerpt(part)}“")
    else:
        print(f"Zadrži samo: „{excerpt(picked)}“ ({fmt_time(picked[0]['s'])}-{fmt_time(picked[-1]['e'])})")
        print(f"Ide van {len(shown)} riječi: „{excerpt(shown)}“")
    print(f"Trajanje: {fmt_time(cur_dur)} → {fmt_time(new_dur)} (−{cur_dur - new_dur:.1f} s), rezova u izvornom videu: {len(new)}")
    if a.proba:
        print("(proba: edit.json nije promijenjen)")
        return
    save_history(proj, label_cmd)
    save_json(proj / "edit.json", edit2)
    print(f"Upisano u edit.json (izrezi, naredba [{n}]). Poništi: python uredi.py {proj.name} vrati")
    print(f"Sljedeće: python render.py {proj.name} --kadar ... ili render")


if __name__ == "__main__":
    sys.exit(main())
