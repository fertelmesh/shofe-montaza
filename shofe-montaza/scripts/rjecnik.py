"""Rječnik koji uči iz ispravaka: što Claude ili Marko isprave u titlovima, Shofe sljedeći put ispravi sam.

Dva dijela:
  pojmovi  - imena i izrazi koje transkripcija (whisper) treba pisati točno: rjecnik.txt u skillu
             (osnovni popis) + ručno dodani + naučeni. Idu u whisperov početni upit (najviše ~200 tokena).
  ispravci - "krivo → točno" (npr. "Fertelmes → Fertelmeš", "esef klima → SF klima"). Uče se iz razlike
             između transkripta i ispravljenog `tekst` u edit.json nakon svakog rendera. Ispravak postaje
             aktivan kad je viđen barem 2 puta (u jednom ili više videa) ili kad je dodan ručno; aktivne
             plan.py sam primijeni na novi edit.json.

Naučeni rječnik je u %LOCALAPPDATA%\\Shofe\\rjecnik.json (ponovna instalacija ga ne briše).

  python rjecnik.py popis
  python rjecnik.py nauci shofe_projekt [--proba]       (render.py to radi sam)
  python rjecnik.py primijeni shofe_projekt [--proba]   (aktivne ispravke na postojeći edit.json)
  python rjecnik.py dodaj "Sunčana Baraka"              (pojam za transkripciju)
  python rjecnik.py dodaj "Fertelmes" "Fertelmeš"       (ispravak, odmah aktivan)
  python rjecnik.py zaboravi "Fertelmes"                (isključi ispravak ili makni pojam)
"""
import argparse
import difflib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from common import SKILL_DIR, data_dir, die, load_json, norm_word

PRAG = 2          # koliko puta ispravak mora biti viđen da postane aktivan
MAX_RIJECI = 3    # najdulji ispravak (riječi s jedne strane)
MAX_TOKENA = 200  # whisper gleda najviše 224 tokena upita
HESITATION = re.compile(r"^(e+|ee+m+|m+|mhm|hm+|aa+|aa+m+)$")
SENT_END = re.compile(r"[.!?…:]+[\"'”“»)]*$")
EDGE = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


# ---------------------------------------------------------------- spremanje

def path():
    return data_dir() / "rjecnik.json"


def load():
    p = path()
    if p.exists():
        try:
            d = load_json(p)
            d.setdefault("pojmovi", [])
            d.setdefault("ispravci", {})
            return d
        except (OSError, ValueError):
            pass
    return {"verzija": 1, "pojmovi": [], "ispravci": {}}


def save(d):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def base_terms():
    p = SKILL_DIR / "rjecnik.txt"
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]


# ---------------------------------------------------------------- pomoćno

def core(tok):
    """Riječ bez interpunkcije na rubovima (unutarnja ostaje: "l'", "4M")."""
    return EDGE.match(tok).group(2)


def key_of(toks):
    return " ".join(norm_word(t) for t in toks)


def strip_diacritics(s):
    s = s.replace("đ", "dj").replace("Đ", "Dj")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def learnable(wrong, right):
    """Je li zamjena riječi `wrong` → `right` vjerojatno pogrešno prepoznata riječ/ime (a ne gramatički
    ili stilski ispravak koji se ne smije primjenjivati na sve buduće videe)."""
    w = " ".join(wrong)
    r = " ".join(right)
    if not w or not r or w == r:
        return False
    wl, rl = w.lower(), r.lower()
    if wl == rl:  # samo velika slova: uči se samo prema velikom (ime), nikad prema malom
        return r != w and sum(c.isupper() for c in r) > sum(c.isupper() for c in w)
    if len(wrong) == 1 and HESITATION.match(norm_word(wrong[0])):
        return False
    if all(len(norm_word(t)) <= 3 for t in wrong + right):  # "je" → "sam", "i" → "a": gramatika
        return False
    if difflib.SequenceMatcher(None, wl.replace(" ", ""), rl.replace(" ", "")).ratio() < 0.5:
        return False  # preformulirano, ne krivo čuto
    if len(wrong) == 1 and len(right) == 1 and r == r.lower() and strip_diacritics(wl) != strip_diacritics(rl):
        n = min(len(wl), len(rl))
        pre = len(os.path.commonprefix([wl, rl]))
        if pre >= n - 2:  # drugi padež / nastavak ("klime" → "klima"): gramatika, ne rječnik
            return False
    return True


def segment_words(words, seg, starts=None):
    import render
    return render.words_in(words, seg["od"], seg["do"], starts)


def find_corrections(words, segs):
    """Ispravci u zadržanim odsječcima: [(krivo_riječi, točno_riječi, id_odsječka)]."""
    import render
    starts = render.word_starts(words)
    out = []
    for seg in segs:
        if not seg.get("zadrzi", True) or not seg.get("tekst"):
            continue
        idx = segment_words(words, seg, starts)
        orig = [words[i]["w"] for i in idx]
        corr = seg["tekst"].split()
        if not orig or orig == corr:
            continue
        a = [norm_word(t) for t in orig]
        b = [norm_word(t) for t in corr]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):
                    co, cc = core(orig[i1 + k]), core(corr[j1 + k])
                    if co == cc or not cc:
                        continue
                    j = j1 + k
                    initial = j == 0 or bool(SENT_END.search(corr[j - 1]))
                    if initial and cc == co[:1].upper() + co[1:]:
                        continue  # veliko slovo na početku rečenice nije ime
                    if learnable([co], [cc]):
                        out.append(([co], [cc], seg["id"]))
            elif op == "replace" and i2 - i1 <= MAX_RIJECI and j2 - j1 <= MAX_RIJECI:
                wrong = [core(t) for t in orig[i1:i2]]
                right = [core(t) for t in corr[j1:j2]]
                wrong, right = [t for t in wrong if t], [t for t in right if t]
                if wrong and right and learnable(wrong, right):
                    out.append((wrong, right, seg["id"]))
    return out


def rejections(segs):
    """Ispravci koje je rječnik sam primijenio (plan.py), a netko ih je vratio na staro: kljuc → broj."""
    out = {}
    for seg in segs:
        if not seg.get("zadrzi", True):
            continue
        toks = seg.get("tekst", "").split()
        cores = [core(t) for t in toks]
        normed = [norm_word(t) for t in toks]
        for ap in seg.get("rjecnik", []):
            right = ap["u"].split()
            wrong_key = ap["iz"].split()
            n, m = len(right), len(wrong_key)
            has_right = any(cores[i:i + n] == right for i in range(len(cores) - n + 1))
            has_wrong = any(normed[i:i + m] == wrong_key for i in range(len(normed) - m + 1))
            if not has_right and has_wrong:
                out[ap["iz"]] = out.get(ap["iz"], 0) + 1
    return out


# ---------------------------------------------------------------- stanje ispravaka

def counts(entry):
    """{točno: broj potvrda} po svim projektima."""
    res = {}
    for var, info in entry.get("varijante", {}).items():
        res[var] = sum(info.get("projekti", {}).values())
    return res


def status(entry):
    """(aktivan, točno, broj potvrda, razlog)."""
    c = counts(entry)
    best = max(c, key=lambda v: (c[v], v == entry.get("rucno")), default=None)
    if entry.get("rucno"):
        best = entry["rucno"]
    best = best or entry.get("bilo")  # isključen ručni ispravak: pokaži što je bio
    n = c.get(best, 0) if best else 0
    if entry.get("iskljuceno"):
        return False, best, n, "isključen"
    if entry.get("rucno"):
        return True, best, n, "ručno"
    if sum(entry.get("odbijeno", {}).values()):
        return False, best, n, "vraćen na staro u videu"
    if n >= PRAG:
        return True, best, n, ""
    return False, best, n, f"viđen {n}/{PRAG}"


def active(d=None):
    """{kljuc (riječi bez interpunkcije, mala slova): točno}."""
    d = d if d is not None else load()
    res = {}
    for k, e in d["ispravci"].items():
        ok, best, _, _ = status(e)
        if ok and best:
            res[k] = best
    return res


def learn(proj, edit, words, dry=False):
    """Zapamti ispravke iz ovog projekta (zamjenjuje prijašnje brojanje istog projekta, pa ponovljeni
    render ne broji dvaput). Vraća (novo_aktivni [(krivo, točno)], svi_ispravci_projekta)."""
    proj = Path(proj).resolve()
    pkey = str(proj)
    d = load()
    before = active(d)
    found = find_corrections(words, edit.get("odsjecci", []))
    rej = rejections(edit.get("odsjecci", []))
    for e in d["ispravci"].values():  # ovaj projekt se broji ispočetka
        for info in e.get("varijante", {}).values():
            info.get("projekti", {}).pop(pkey, None)
        e.get("odbijeno", {}).pop(pkey, None)
    for wrong, right, _sid in found:
        k = key_of(wrong)
        e = d["ispravci"].setdefault(k, {"krivo": " ".join(wrong), "varijante": {}})
        var = e["varijante"].setdefault(" ".join(right), {"projekti": {}})
        var["projekti"][pkey] = var["projekti"].get(pkey, 0) + 1
        e["zadnje"] = datetime.now().isoformat(timespec="seconds")
    for k, n in rej.items():
        if k in d["ispravci"]:
            d["ispravci"][k].setdefault("odbijeno", {})[pkey] = n
    # počisti prazno (ispravak koji više nigdje nije viđen i nije ručni)
    for k in list(d["ispravci"]):
        e = d["ispravci"][k]
        e["varijante"] = {v: i for v, i in e.get("varijante", {}).items() if i.get("projekti")}
        e["odbijeno"] = {p: n for p, n in e.get("odbijeno", {}).items() if n}
        if not e["varijante"] and not e.get("rucno") and not e.get("iskljuceno") and not e["odbijeno"]:
            del d["ispravci"][k]
    after = active(d)
    if not dry:
        save(d)
    new = [(d["ispravci"][k]["krivo"], v) for k, v in after.items() if before.get(k) != v]
    lost = [(k, before[k]) for k in before if k not in after]
    return new, lost, found


# ---------------------------------------------------------------- primjena

def match_case(src_first, target):
    if src_first[:1].isupper() and target[:1].islower():
        return target[:1].upper() + target[1:]
    return target


def apply_text(text, act):
    """Primijeni aktivne ispravke na tekst odsječka. Vraća (novi_tekst, [{"iz": kljuc, "u": točno}])."""
    toks = text.split()
    if not toks or not act:
        return text, []
    by_len = {}
    for k, v in act.items():
        by_len.setdefault(len(k.split()), {})[k] = v
    out, applied, i = [], [], 0
    while i < len(toks):
        hit = False
        for n in sorted(by_len, reverse=True):
            if i + n > len(toks):
                continue
            k = key_of(toks[i:i + n])
            target = by_len[n].get(k)
            if not target:
                continue
            lead = EDGE.match(toks[i]).group(1)
            trail = EDGE.match(toks[i + n - 1]).group(3)
            new = match_case(core(toks[i]), target)
            if " ".join(core(t) for t in toks[i:i + n]) == new:
                continue  # već točno
            out += (lead + new + trail).split()
            applied.append({"iz": k, "u": target})
            i += n
            hit = True
            break
        if not hit:
            out.append(toks[i])
            i += 1
    return " ".join(out), applied


def apply_edit(edit, act=None):
    """Primijeni na sve odsječke edit.json (na mjestu). Vraća popis (id, staro, novo)."""
    act = active() if act is None else act
    changes = []
    for seg in edit.get("odsjecci", []):
        new, applied = apply_text(seg.get("tekst", ""), act)
        if applied:
            changes.append((seg["id"], seg["tekst"], new))
            seg["tekst"] = new
            seg["rjecnik"] = seg.get("rjecnik", []) + applied
    return changes


# ---------------------------------------------------------------- whisper upit

def prompt_terms(d=None):
    """Pojmovi za whisper: osnovni rjecnik.txt, ručno dodani, pa naučeni (najčešći prvi)."""
    d = d if d is not None else load()
    terms = base_terms() + list(d.get("pojmovi", []))
    learned = []
    for k, e in d["ispravci"].items():
        ok, best, n, _ = status(e)
        if ok and best and (any(c.isupper() or c.isdigit() for c in best) or " " in best):
            learned.append((n, best))
    terms += [t for _, t in sorted(learned, key=lambda x: -x[0])]
    seen, res = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            res.append(t)
    return res


def build_prompt(terms, count_tokens=None, limit=MAX_TOKENA):
    """", ".join(terms) + "." uz najviše `limit` tokena (bez brojača: ~3 znaka po tokenu)."""
    count = count_tokens or (lambda s: len(s) // 3 + 1)
    picked = []
    for t in terms:
        if count(", ".join(picked + [t]) + ".") > limit:
            break
        picked.append(t)
    return ", ".join(picked) + "." if picked else None


# ---------------------------------------------------------------- naredbe

def cmd_popis(_a):
    d = load()
    print(f"Rječnik: {path()}")
    print(f"\nPojmovi za transkripciju ({len(prompt_terms(d))}):")
    print("  " + ", ".join(prompt_terms(d)))
    items = sorted(d["ispravci"].values(), key=lambda e: (not status(e)[0], -status(e)[2], e["krivo"].lower()))
    if not items:
        print("\nIspravci: još nijedan (uči se iz ispravaka u titlovima nakon svakog rendera).")
        return
    print(f"\nIspravci (aktivan = plan.py ga sam primijeni; postaje aktivan kad je viđen {PRAG}×):")
    for e in items:
        ok, best, n, why = status(e)
        mark = "✓" if ok else "·"
        projs = len({p for v in e.get("varijante", {}).values() for p in v.get("projekti", {})})
        extra = f"  ({why})" if why else ""
        print(f"  {mark} {e['krivo']} → {best}   {n}× u {projs} vid.{extra}")


def load_project(p):
    proj = Path(p)
    for f in ("transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    return proj, load_json(proj / "transcript.json")["words"], load_json(proj / "edit.json")


def cmd_nauci(a):
    proj, words, edit = load_project(a.projekt)
    new, lost, found = learn(proj, edit, words, dry=a.proba)
    if not found:
        print("U ovom videu nema ispravaka imena ni krivo čutih riječi.")
    for wrong, right, sid in found:
        print(f"  #{sid}: {' '.join(wrong)} → {' '.join(right)}")
    report_learned(new, lost)
    if a.proba:
        print("(proba: ništa nije spremljeno)")


def report_learned(new, lost):
    for w, r in new:
        print(f"Rječnik naučio: {w} → {r} (sljedeći put se ispravlja samo)")
    for k, r in lost:
        print(f"Rječnik više ne ispravlja: {k} → {r}")


def cmd_primijeni(a):
    from common import save_json
    proj, _words, edit = load_project(a.projekt)
    changes = apply_edit(edit)
    if not changes:
        print("Nema ničega za ispraviti.")
        return
    for sid, old, new in changes:
        print(f"  #{sid}: {old}\n     → {new}")
    if a.proba:
        print("(proba: edit.json nije promijenjen)")
    else:
        save_json(proj / "edit.json", edit)
        print(f"Ispravljeno odsječaka: {len(changes)}. Sljedeće: render.py")


def cmd_dodaj(a):
    d = load()
    if a.tocno is None:
        term = a.krivo.strip()
        if term.lower() in {t.lower() for t in base_terms() + d["pojmovi"]}:
            print(f"„{term}“ je već u rječniku.")
            return
        d["pojmovi"].append(term)
        save(d)
        print(f"Dodan pojam za transkripciju: {term}")
        return
    wrong, right = a.krivo.split(), a.tocno.split()
    if not wrong or not right or len(wrong) > MAX_RIJECI:
        die(f"ispravak treba 1–{MAX_RIJECI} riječi s lijeve strane")
    k = key_of(wrong)
    e = d["ispravci"].setdefault(k, {"krivo": " ".join(core(t) for t in wrong), "varijante": {}})
    e["rucno"] = " ".join(core(t) for t in right)
    e.pop("iskljuceno", None)
    e["odbijeno"] = {}
    save(d)
    print(f"Dodan ispravak: {e['krivo']} → {e['rucno']} (aktivan odmah)")


def cmd_zaboravi(a):
    d = load()
    k = key_of(a.krivo.split())
    hit = False
    if k in d["ispravci"]:
        e = d["ispravci"][k]
        e["iskljuceno"] = True
        e["bilo"] = status(e)[1]
        e.pop("rucno", None)
        hit = True
        print(f"Isključen ispravak: {e['krivo']} (više se neće ni učiti ni primjenjivati)")
    before = len(d["pojmovi"])
    d["pojmovi"] = [t for t in d["pojmovi"] if t.lower() != a.krivo.strip().lower()]
    if len(d["pojmovi"]) != before:
        hit = True
        print(f"Maknut pojam: {a.krivo}")
    if not hit:
        if a.krivo.strip().lower() in {t.lower() for t in base_terms()}:
            die(f"„{a.krivo}“ je u osnovnom popisu {SKILL_DIR / 'rjecnik.txt'}; makni ga tamo")
        die(f"„{a.krivo}“ nije u rječniku (popis: python rjecnik.py popis)")
    save(d)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rječnik koji uči iz ispravaka titlova.")
    sub = ap.add_subparsers(dest="naredba", required=True)
    sub.add_parser("popis", help="pojmovi i naučeni ispravci")
    p = sub.add_parser("nauci", help="nauči iz ispravaka u projektu (render.py to radi sam)")
    p.add_argument("projekt")
    p.add_argument("--proba", action="store_true")
    p = sub.add_parser("primijeni", help="aktivne ispravke primijeni na edit.json projekta")
    p.add_argument("projekt")
    p.add_argument("--proba", action="store_true")
    p = sub.add_parser("dodaj", help='"Pojam" ili "krivo" "točno"')
    p.add_argument("krivo")
    p.add_argument("tocno", nargs="?")
    p = sub.add_parser("zaboravi", help="isključi ispravak / makni pojam")
    p.add_argument("krivo")
    a = ap.parse_args(argv)
    {"popis": cmd_popis, "nauci": cmd_nauci, "primijeni": cmd_primijeni,
     "dodaj": cmd_dodaj, "zaboravi": cmd_zaboravi}[a.naredba](a)


if __name__ == "__main__":
    sys.exit(main())
