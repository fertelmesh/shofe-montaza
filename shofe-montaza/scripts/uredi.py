"""Montaža po naredbi: vremena iz GOTOVOG videa → izmjene edit.json.

  python uredi.py shofe_projekt makni 1:20-1:45            makni taj dio gotovog videa
  python uredi.py shofe_projekt makni 0:05-0:08 1:20-1:45  više dijelova odjednom
  python uredi.py shofe_projekt zadrzi 0:10-0:40           zadrži samo taj dio (ostalo van)
  python uredi.py shofe_projekt popis                      što je gdje u gotovom videu
  python uredi.py shofe_projekt vrati                      poništi zadnju naredbu

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

from common import die, fmt_time, load_json, save_json
from render import build_cuts, resolve_style, to_out

TIME = r"\d+(?::\d{1,2}){0,2}(?:[.,]\d+)?s?"
RANGE = re.compile(rf"(?:od\s+)?({TIME})\s*(?:-|do)\s*({TIME})")
NAREDBE = {"makni": "makni", "izrezi": "makni", "izreži": "makni", "obrisi": "makni", "obriši": "makni",
           "zadrzi": "zadrzi", "zadrži": "zadrzi", "popis": "popis", "vrati": "vrati", "ponisti": "vrati",
           "poništi": "vrati"}


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
        print("\nIzrezano naredbama po vremenu (vrijeme izvornog videa):")
        for r in iz:
            print(f"  [{r.get('n', '?')}] {fmt_time(r['od'])}-{fmt_time(r['do'])}  {r.get('naredba', '')}  „{r.get('tekst', '')}“")


def main():
    ap = argparse.ArgumentParser(description="Montaža po naredbi s vremenima iz gotovog videa")
    ap.add_argument("projekt")
    ap.add_argument("naredba", help="makni | zadrzi | popis | vrati")
    ap.add_argument("vremena", nargs="*", help="npr. 1:20-1:45 (vrijeme u gotovom videu)")
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
        die(f"nepoznata naredba '{a.naredba}' (makni, zadrzi, popis, vrati)")
    if naredba == "vrati":
        undo(proj)
        return
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    ref, label = reference_edit(proj, edit, a)
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
                      f"{len(part)} riječi: „{excerpt(part)}“")
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
