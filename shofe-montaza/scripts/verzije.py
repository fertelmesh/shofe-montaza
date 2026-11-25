"""Verzije montaže: popis, vrati verziju N, usporedba što se promijenilo.

  python verzije.py shofe_projekt                   popis verzija (svaki render = nova verzija)
  python verzije.py shofe_projekt vrati 2           edit.json kao u verziji 2 (reel_v2)
  python verzije.py shofe_projekt usporedi          zadnja gledana verzija → trenutni edit.json
                                                    (ili, ako nema izmjena, pretposljednja → zadnja)
  python verzije.py shofe_projekt usporedi 2 4      verzija 2 → verzija 4
  python verzije.py shofe_projekt usporedi 3 trenutno
  python verzije.py shofe_projekt nazovi 3 "za Instagram"

Svaki render.py sprema verzije/edit_vN.json (točno ono od čega je reel_vN napravljen) i upisuje
datum, datoteku i trajanje u verzije/verzije.json. Ništa se ne briše: „vrati verziju 2" samo vrati
edit.json na stanje verzije 2 (prethodno stanje ide u povijest, pa `uredi.py vrati` to poništava),
a verzije 3, 4… ostaju. Nakon toga se vremena u naredbama čitaju iz reel_v2, jer korisnik gleda nju.
"""
import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from common import die, fmt_time, load_json, norm_word, save_json

META = "verzije.json"
TRENUTNO = {"trenutno", "sada", "sad", "edit", "t", "novo"}

# čitljiva imena postavki u edit.json (ostale se ispisuju pod svojim ključem)
POSTAVKE = {
    "stil": "stil", "boja": "boja isticanja", "velicina_titlova": "veličina titlova",
    "pozicija_titlova": "položaj titlova", "velika_slova": "velika slova", "titlovi": "titlovi",
    "zoom": "zumovi", "boja_slike": "boja slike", "brzina": "brzina", "glazba": "glazba",
    "glazba_glasnoca": "glasnoća glazbe", "hook": "naslov (hook)", "hook_trajanje": "trajanje naslova",
    "naglasi": "naglašene riječi", "traka_napretka": "traka napretka", "format": "format",
}
BEZ_USPOREDBE = {"odsjecci", "izrezi"}


# ---------------------------------------------------------------- spremište verzija
def vdir(proj):
    return Path(proj) / "verzije"


def found_versions(proj):
    """{N: putanja edit_vN.json}"""
    d = vdir(proj)
    if not d.exists():
        return {}
    return {int(m.group(1)): p for p in d.glob("edit_v*.json") if (m := re.fullmatch(r"edit_v(\d+)", p.stem))}


def load_meta(proj):
    p = vdir(proj) / META
    try:
        m = load_json(p) if p.exists() else {}
    except (ValueError, OSError):
        m = {}
    m.setdefault("verzije", {})
    m.setdefault("gledano", None)
    return m


def save_meta(proj, meta):
    vdir(proj).mkdir(exist_ok=True)
    save_json(vdir(proj) / META, meta)


def next_number(proj):
    """Sljedeći broj verzije: iza svih reel_vN*.mp4 i svih spremljenih edit_vN.json."""
    nums = [int(m.group(1)) for p in Path(proj).glob("reel_v*.mp4") if (m := re.match(r"reel_v(\d+)", p.stem))]
    nums += list(found_versions(proj))
    return max(nums, default=0) + 1


def record_render(proj, v, edit, datoteka, trajanje, brzo=False, kvaliteta="dobra"):
    """Poziva render.py nakon uspješnog rendera: spremi edit i podatke verzije, korisnik sada gleda nju."""
    vdir(proj).mkdir(exist_ok=True)
    save_json(vdir(proj) / f"edit_v{v}.json", edit)
    meta = load_meta(proj)
    old = meta["verzije"].get(str(v), {})
    meta["verzije"][str(v)] = {
        "datoteka": datoteka, "datum": dt.datetime.now().isoformat(timespec="seconds"),
        "trajanje": round(trajanje, 2), "brzi_pregled": bool(brzo), "kvaliteta": kvaliteta,
        **({"naziv": old["naziv"]} if old.get("naziv") else {}),
    }
    meta["gledano"] = v
    save_meta(proj, meta)


def viewed(proj):
    """Verzija koju korisnik gleda: zadnja vraćena („vrati verziju N") ili zadnja renderirana. None ako nema."""
    found = found_versions(proj)
    if not found:
        return None
    g = load_meta(proj).get("gledano")
    return g if g in found else max(found)


def set_viewed(proj, v):
    meta = load_meta(proj)
    meta["gledano"] = v
    save_meta(proj, meta)


def video_file(proj, v):
    """reel_vN.mp4 (ili reel_vN_pregled.mp4) ako postoji, inače None."""
    info = load_meta(proj)["verzije"].get(str(v), {})
    cands = [info.get("datoteka")] if info.get("datoteka") else []
    cands += [f"reel_v{v}.mp4", f"reel_v{v}_pregled.mp4"]
    for c in cands:
        if c and (Path(proj) / c).exists():
            return c
    return None


def version_date(proj, v):
    info = load_meta(proj)["verzije"].get(str(v), {})
    try:
        return dt.datetime.fromisoformat(info["datum"])
    except (KeyError, ValueError, TypeError):
        p = found_versions(proj).get(v)
        return dt.datetime.fromtimestamp(p.stat().st_mtime) if p else None


# ---------------------------------------------------------------- usporedba
def _fmt_val(v):
    if v is None or v == "" or v == []:
        return "—"
    if isinstance(v, bool):
        return "da" if v else "ne"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if isinstance(v, str):
        return f"„{v}“"
    return str(v)


def _cut_key(r):
    return (round(r["od"], 2), round(r["do"], 2), r.get("naredba", ""))


def _groups(seq, pos):
    """Uzastopne riječi (po mjestu u vremenskoj crti `pos`) → grupe."""
    out = []
    for i in sorted(seq, key=lambda i: pos[i]):
        if out and pos[i] == pos[out[-1][-1]] + 1:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def _why_gone(words, eb, i, owner, segs):
    """Zašto riječ i nije u verziji B. owner = uredi.segment_of(words, eb), segs = {id: odsječak}."""
    w = words[i]
    mid = (w["s"] + w["e"]) / 2
    for r in eb.get("izrezi") or []:
        if r["od"] <= mid < r["do"]:
            return r.get("naredba") or "izrez"
    seg = segs.get(owner.get(i))
    if seg is None:
        return "skraćen odsječak"
    if not seg.get("zadrzi", True):
        return f"isključen odsječak #{seg['id']}"
    if norm_word(w["w"]) in {norm_word(x) for x in seg.get("izbaci") or []}:
        return "poštapalica"
    return "ostalo"


def compare(words, pj, ea, eb):
    """Što se promijenilo od edit-a A do edit-a B (oba u istom projektu)."""
    from uredi import segment_of, timeline
    tla, dura = timeline(words, ea, pj)
    tlb, durb = timeline(words, eb, pj)
    pa = {w["i"]: k for k, w in enumerate(tla)}
    pb = {w["i"]: k for k, w in enumerate(tlb)}
    gone = [i for i in pa if i not in pb]
    added = [i for i in pb if i not in pa]

    def disp(tl, idxs):
        toks = [tl[k]["t"] for k in idxs if tl[k]["t"]]
        return toks

    owner = segment_of(words, eb) if gone else {}
    segs = {sg["id"]: sg for sg in eb["odsjecci"]}
    van = []
    for g in _groups(gone, pa):
        ks = [pa[i] for i in g]
        razlozi = []
        for i in g:
            r = _why_gone(words, eb, i, owner, segs)
            if r not in razlozi:
                razlozi.append(r)
        van.append({"od": tla[ks[0]]["s"], "do": tla[ks[-1]]["e"], "rijeci": disp(tla, ks), "razlog": razlozi})
    novo = []
    for g in _groups(added, pb):
        ks = [pb[i] for i in g]
        novo.append({"od": tlb[ks[0]]["s"], "do": tlb[ks[-1]]["e"], "rijeci": disp(tlb, ks)})

    postavke = []
    for k in sorted(set(ea) | set(eb)):
        if k in BEZ_USPOREDBE or k.startswith("_"):
            continue
        if ea.get(k) != eb.get(k):
            postavke.append((POSTAVKE.get(k, k), ea.get(k), eb.get(k)))

    sa = {s["id"]: s for s in ea["odsjecci"]}
    tekst = []
    for s in eb["odsjecci"]:
        o = sa.get(s["id"])
        if o and (o.get("tekst") or "") != (s.get("tekst") or "") and s.get("zadrzi", True):
            tekst.append((s["id"], o.get("tekst") or "", s.get("tekst") or ""))

    ka = {_cut_key(r) for r in ea.get("izrezi") or []}
    kb = {_cut_key(r) for r in eb.get("izrezi") or []}
    naredbe = []
    for r in eb.get("izrezi") or []:
        lab = r.get("naredba", "")
        if _cut_key(r) not in ka and lab and lab not in naredbe:
            naredbe.append(lab)
    vracene = []
    for r in ea.get("izrezi") or []:
        lab = r.get("naredba", "")
        if _cut_key(r) not in kb and lab and lab not in vracene and lab not in naredbe:
            vracene.append(lab)
    return {"trajanje": (dura, durb), "van": van, "novo": novo, "postavke": postavke, "tekst": tekst,
            "naredbe": naredbe, "ponisteno": vracene,
            "isto": not (van or novo or postavke or tekst) and ea == eb}


def _excerpt(toks, n=5):
    if len(toks) <= 2 * n:
        return " ".join(toks)
    return " ".join(toks[:n]) + " … " + " ".join(toks[-n:])


def summary(c):
    """Jedan redak: što se promijenilo (za popis verzija)."""
    if c["isto"]:
        return "bez promjena"
    parts = []
    if c["naredbe"]:
        parts.append("; ".join(c["naredbe"][:3]) + (" …" if len(c["naredbe"]) > 3 else ""))
    if c["ponisteno"]:
        parts.append("poništeno: " + "; ".join(c["ponisteno"][:3]))
    nv = sum(len(g["rijeci"]) for g in c["van"])
    nn = sum(len(g["rijeci"]) for g in c["novo"])
    if nv or nn:
        parts.append(" ".join(x for x in (f"−{nv} riječi" if nv else "", f"+{nn} riječi" if nn else "") if x))
    for name, a, b in c["postavke"][:3]:
        parts.append(f"{name} {_fmt_val(a)} → {_fmt_val(b)}")
    if len(c["postavke"]) > 3:
        parts.append(f"još {len(c['postavke']) - 3} postavki")
    if c["tekst"]:
        parts.append(f"ispravci teksta: {len(c['tekst'])}")
    return ", ".join(parts) or "sitne izmjene u edit.json"


def print_compare(c, la, lb):
    sa, sb = la.split(" (")[0], lb.split(" (")[0]  # kratko ime (v2 „naziv“) za naslove dijelova
    dura, durb = c["trajanje"]
    print(f"Usporedba: {la} → {lb}")
    print(f"Trajanje: {fmt_time(dura)} → {fmt_time(durb)} ({durb - dura:+.1f} s)")
    if c["isto"]:
        print("Nema razlike: obje verzije su iste.")
        return
    if c["naredbe"]:
        print("Naredbe: " + "; ".join(c["naredbe"]))
    if c["ponisteno"]:
        print("Više ne vrijedi: " + "; ".join(c["ponisteno"]))
    if c["van"]:
        print(f"Izbačeno (vrijeme u {sa}):")
        for g in c["van"]:
            print(f"  {fmt_time(g['od'])}-{fmt_time(g['do'])}  „{_excerpt(g['rijeci'])}“  ({'; '.join(g['razlog'])})")
    if c["novo"]:
        print(f"Dodano (vrijeme u {sb}):")
        for g in c["novo"]:
            print(f"  {fmt_time(g['od'])}-{fmt_time(g['do'])}  „{_excerpt(g['rijeci'])}“")
    if c["postavke"]:
        print("Postavke:")
        for name, a, b in c["postavke"]:
            print(f"  {name}: {_fmt_val(a)} → {_fmt_val(b)}")
    if c["tekst"]:
        print("Ispravljen tekst titlova:")
        for sid, a, b in c["tekst"]:
            print(f"  #{sid}: „{a}“ → „{b}“")
    if not (c["van"] or c["novo"] or c["postavke"] or c["tekst"]):
        print("Isti video i izgled; razlikuju se samo detalji u edit.json (npr. napomene).")


# ---------------------------------------------------------------- naredbe
def parse_version(s, found):
    s = s.strip().lower()
    if s in TRENUTNO:
        return "trenutno"
    m = re.fullmatch(r"(?:v|verzija|verziju)?\s*(\d+)", s)
    if not m:
        die(f"ne razumijem verziju '{s}' (primjer: 2, v2 ili trenutno)")
    n = int(m.group(1))
    if n not in found:
        die(f"nema verzije {n} (postoje: {', '.join(map(str, sorted(found))) or 'nijedna — još nije renderirano'})")
    return n


def label(proj, v):
    if v == "trenutno":
        return "trenutni edit.json"
    f = video_file(proj, v)
    naziv = load_meta(proj)["verzije"].get(str(v), {}).get("naziv")
    return f"v{v}" + (f" „{naziv}“" if naziv else "") + (f" ({f})" if f else "")


def cmd_popis(proj, words, pj, edit):
    from uredi import timeline
    found = found_versions(proj)
    if not found:
        print("Još nema verzija: svaki render (python render.py projekt) sprema novu.")
        return
    meta = load_meta(proj)
    g = viewed(proj)
    print(f"Verzije u {proj.name} (► = ona koju gledaš; vremena u naredbama čitaju se iz nje):")
    prev = None
    for n in sorted(found):
        e = load_json(found[n])
        info = meta["verzije"].get(str(n), {})
        d = version_date(proj, n)
        dur = timeline(words, e, pj)[1]
        f = video_file(proj, n) or "(video obrisan)"
        if info.get("brzi_pregled") or f.endswith("_pregled.mp4"):
            f += " [brzi pregled]"
        naziv = f" „{info['naziv']}“" if info.get("naziv") else ""
        what = "prva verzija" if prev is None else summary(compare(words, pj, prev, e))
        mark = "►" if n == g else " "
        when = d.strftime("%d.%m. %H:%M") if d else ""
        print(f" {mark} v{n:<3} {when:<12} {fmt_time(dur)}  {e.get('stil') or 'suncani':<8} {f}{naziv}")
        print(f"         {what}")
        prev = e
    cur = edit
    ref = load_json(found[g])
    if cur != ref:
        c = compare(words, pj, ref, cur)
        print(f"   trenutni edit.json (još nije renderiran), u odnosu na v{g}: {summary(c)}; "
              f"trajanje {fmt_time(c['trajanje'][1])}")
    else:
        print(f"   trenutni edit.json = v{g}")
    print(f"Usporedi: python verzije.py {proj.name} usporedi A B   ·   vrati: python verzije.py {proj.name} vrati N")


def cmd_vrati(proj, words, pj, edit, n, proba=False):
    from uredi import save_history
    found = found_versions(proj)
    target = load_json(found[n])
    g = viewed(proj)
    if target == edit:
        print(f"edit.json je već isti kao v{n}. Ništa za promijeniti.")
        if g != n and not proba:
            set_viewed(proj, n)
            print(f"Vremena u naredbama sada se čitaju iz {label(proj, n)}.")
        return
    c = compare(words, pj, edit, target)
    print(f"Vraćam edit.json na {label(proj, n)}.")
    print(f"U odnosu na trenutni edit.json: {summary(c)}; trajanje "
          f"{fmt_time(c['trajanje'][0])} → {fmt_time(c['trajanje'][1])}")
    if proba:
        print("(proba: edit.json nije promijenjen)")
        return
    save_history(proj, f"vrati verziju {n}", extra={"gledano": g})
    save_json(Path(proj) / "edit.json", target)
    set_viewed(proj, n)
    f = video_file(proj, n)
    if f and not f.endswith("_pregled.mp4"):
        print(f"Video te verzije već postoji: {f} — novi render nije potreban.")
    elif f:
        print(f"Te verzije postoji samo brzi pregled ({f}); za puni video: python render.py {proj.name}")
    else:
        print(f"Video te verzije je obrisan; napravi ga ponovno: python render.py {proj.name}")
    print(f"Vremena u sljedećim naredbama čitaju se iz v{n}. Novije verzije ostaju (popis: python verzije.py {proj.name}).")
    print(f"Poništi: python uredi.py {proj.name} vrati")


def default_pair(proj, edit):
    found = found_versions(proj)
    g = viewed(proj)
    if load_json(found[g]) != edit:
        return g, "trenutno"
    older = [n for n in sorted(found) if n < g]
    if older:
        return older[-1], g
    return None


def main():
    ap = argparse.ArgumentParser(description="Verzije montaže: popis, vrati, usporedi")
    ap.add_argument("projekt")
    ap.add_argument("naredba", nargs="?", default="popis", help="popis | vrati N | usporedi [A] [B] | nazovi N \"naziv\"")
    ap.add_argument("argumenti", nargs="*")
    ap.add_argument("--proba", action="store_true", help="vrati: samo pokaži što bi se promijenilo")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    for f in ("project.json", "transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    found = found_versions(proj)
    nar = a.naredba.lower()

    if nar in ("popis", "lista", "sve"):
        cmd_popis(proj, words, pj, edit)
    elif nar in ("vrati", "vrati_verziju"):
        if len(a.argumenti) != 1:
            die("koju verziju? primjer: python verzije.py projekt vrati 2")
        n = parse_version(a.argumenti[0], found)
        if n == "trenutno":
            die("vrati prima broj verzije (2, v2)")
        cmd_vrati(proj, words, pj, edit, n, a.proba)
    elif nar in ("usporedi", "razlika", "diff"):
        if not found:
            die("još nema verzija za usporedbu (svaki render.py sprema novu)")
        args = a.argumenti
        if len(args) > 2:
            die("usporedi prima najviše dvije verzije, npr. usporedi 2 4")
        if not args:
            pair = default_pair(proj, edit)
            if pair is None:
                print(f"Postoji samo v{viewed(proj)} i trenutni edit.json je isti. Nema što usporediti.")
                return
        elif len(args) == 1:
            pair = (parse_version(args[0], found), "trenutno")
        else:
            pair = (parse_version(args[0], found), parse_version(args[1], found))
        ea, eb = (edit if v == "trenutno" else load_json(found[v]) for v in pair)
        print_compare(compare(words, pj, ea, eb), label(proj, pair[0]), label(proj, pair[1]))
    elif nar in ("nazovi", "imenuj"):
        if len(a.argumenti) < 2:
            die("primjer: python verzije.py projekt nazovi 3 \"za Instagram\"")
        n = parse_version(a.argumenti[0], found)
        if n == "trenutno":
            die("nazovi prima broj verzije")
        meta = load_meta(proj)
        meta["verzije"].setdefault(str(n), {})["naziv"] = " ".join(a.argumenti[1:]).strip()
        save_meta(proj, meta)
        print(f"v{n} se sada zove „{meta['verzije'][str(n)]['naziv']}“.")
    else:
        die(f"nepoznata naredba '{a.naredba}' (popis, vrati N, usporedi [A] [B], nazovi N \"naziv\")")


if __name__ == "__main__":
    sys.exit(main())
