"""Korak 3: iz transkripta napravi edit.json (odsječci, poštapalice, ponovljeni pokušaji).

  python plan.py shofe_projekt --stil suncani
Piše:
  edit.json       - plan montaže (Claude ga uređuje)
  transcript.txt  - čitljiv transkript s brojevima odsječaka
"""
import argparse
import difflib
import re
from pathlib import Path

from common import die, fmt_time, list_styles, load_json, norm_word, save_json

FILLER = re.compile(r"^(e+|ee+m+|m+|mhm|hm+|a+|aa+m+|ovaj+|ono+)$")
HESITATION = re.compile(r"^(e+|ee+m+|m+|mhm|hm+|aa+|aa+m+)$")  # sigurno za izbaciti


def split_segments(words, gap=0.30, max_words=14):
    segs, cur = [], []
    for i, w in enumerate(words):
        if cur:
            prev = words[i - 1]
            pause = w["s"] - prev["e"]
            sentence_end = prev["w"][-1:] in ".!?" and pause > 0.15
            if pause > gap or sentence_end or len(cur) >= max_words:
                segs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        segs.append(cur)
    return segs


def is_retake(a, b):
    """a = raniji odsječak, b = kasniji. True ako je a vjerojatno odbačeni pokušaj."""
    if len(a) < 2 or len(b) < 2:
        return False
    k = min(len(a), len(b), 4)
    if a[:2] != b[:2] and difflib.SequenceMatcher(None, a[:k], b[:k]).ratio() < 0.75:
        return False
    return difflib.SequenceMatcher(None, a, b[: len(a) + 2]).ratio() > 0.6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--stil", default="suncani", help="|".join(list_styles()))
    ap.add_argument("--pauza", type=float, default=0.30, help="pauza (s) nakon koje počinje novi odsječak")
    ap.add_argument("--prepisi", action="store_true", help="prepiši postojeći edit.json")
    a = ap.parse_args()

    proj = Path(a.projekt)
    tr = proj / "transcript.json"
    if not tr.exists():
        die("nema transcript.json. Prvo pokreni transcribe.py")
    if (proj / "edit.json").exists() and not a.prepisi:
        die("edit.json već postoji (dodaj --prepisi da ga napraviš ispočetka)")
    words = load_json(tr)["words"]
    if not words:
        die("transkript je prazan: u videu nema prepoznatog govora")

    groups = split_segments(words, a.pauza)
    normed = [[norm_word(words[i]["w"]) for i in g] for g in groups]
    segs = []
    for n, g in enumerate(groups):
        toks = [words[i]["w"] for i in g]
        seg = {
            "id": n + 1,
            "od": words[g[0]]["s"],
            "do": words[g[-1]]["e"],
            "tekst": " ".join(toks),
            "zadrzi": True,
        }
        hes = sorted({t for t in toks if HESITATION.match(norm_word(t))})
        if hes:
            seg["izbaci"] = hes
        if all(FILLER.match(x) for x in normed[n] if x):
            seg["zadrzi"] = False
            seg["napomena"] = "samo poštapalica (auto)"
        else:
            for m in range(n + 1, min(n + 3, len(groups))):
                if is_retake(normed[n], normed[m]):
                    seg["zadrzi"] = False
                    seg["napomena"] = f"ponovljeno u #{m + 1}? (auto)"
                    break
        segs.append(seg)

    edit = {
        "stil": a.stil,
        "hook": "",
        "hook_trajanje": 3.0,
        "naglasi": [],
        "boja": None,
        "velicina_titlova": 1.0,
        "pozicija_titlova": None,
        "velika_slova": None,
        "zoom": None,
        "boja_slike": None,
        "glazba": None,
        "glazba_glasnoca": -20,
        "brzina": 1.0,
        "traka_napretka": None,
        "titlovi": True,
        "odsjecci": segs,
    }
    save_json(proj / "edit.json", edit)

    lines = []
    for s, g in zip(segs, groups):
        unsure = [words[i]["w"] for i in g if words[i].get("p", 1) < 0.5]
        mark = "   " if s["zadrzi"] else " X "
        line = f"{mark}#{s['id']:<3} {fmt_time(s['od'])}-{fmt_time(s['do'])}  {s['tekst']}"
        if s.get("napomena"):
            line += f"   <- {s['napomena']}"
        if unsure:
            line += f"   [nesigurno: {', '.join(unsure)}]"
        lines.append(line)
    (proj / "transcript.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    dropped = sum(not s["zadrzi"] for s in segs)
    kept = sum(s["do"] - s["od"] for s in segs if s["zadrzi"])
    print("\n".join(lines))
    print(f"\n{len(segs)} odsječaka, {dropped} označeno za izbacivanje, ~{kept:.1f}s govora ostaje.")
    print(f"Pregledaj {proj / 'edit.json'}, zatim: python render.py {proj}")


if __name__ == "__main__":
    main()
