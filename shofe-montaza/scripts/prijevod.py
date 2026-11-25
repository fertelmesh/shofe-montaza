"""Prijevod titlova (zadano engleski): Claude prevodi titl po titl, Shofe pamti prijevode i piše
reel_vN.en.srt uz video (isto vrijeme kao hrvatski titlovi).

  python prijevod.py shofe_projekt                  pripremi prijevod_en.json / napiši reel_vN.en.srt
  python prijevod.py shofe_projekt --format oba     SRT + VTT
  python prijevod.py shofe_projekt --verzija 2      za reel_v2 (zadano: verzija koju gledaš)
  python prijevod.py shofe_projekt --trenutno       iz trenutnog edit.json (prije rendera)
  python prijevod.py shofe_projekt --ispis          ispiši hrvatski i engleski jedan uz drugi
  python prijevod.py shofe_projekt --jezik de       drugi jezik (prijevod_de.json, .de.srt)

Postupak:
  1. Prvo pokretanje napravi prijevod_en.json: popis titlova verzije s vremenom, najvećim brojem
     znakova i hrvatskim tekstom; polje "en" je prazno.
  2. Claude upiše prijevod u "en" za svaki titl (ne dira "hr").
  3. Ponovno pokretanje provjeri prijevode (2 × 42 znaka, brzina čitanja, neprevedeno) i napiše
     reel_vN.en.srt. Izlazni kod 1 dok neki titl nema prijevod ili je predug.

Prijevodi se pamte po hrvatskom tekstu titla, pa nakon novih rezova Claude prevodi samo titlove koji
su se promijenili. Kad prijevod_<jezik>.json postoji, render.py sam napiše i <video>.<jezik>.srt
(ako su svi titlovi prevedeni) i upiše nove titlove u datoteku.
"""
import argparse
import difflib
import re
import sys
from pathlib import Path

import titlovi
from common import fmt_time, load_json, save_json

CPS_PRIJEVOD = 20      # znakova u sekundi za engleske titlove odraslih (Netflix English)
FUZZY = 0.88           # sličnost hrvatskog teksta za preuzimanje starog prijevoda (uz napomenu)
WEAK = {"en": titlovi.WEAK_END_EN}
UPUTE = ("Upiši prijevod u polje jezika za svaki titl (ne mijenjaj 'hr'). Prirodan govorni jezik, ne doslovno; "
         "titl prevodi ono što se kaže u tom titlu; imena, brendove i nazive (Sunčani4M, SF klima, Kutina) ne prevodi; "
         "najviše 'max_znakova' znakova (2 retka × 42); prelom retka po želji s ' | '. "
         "Kad provjeriš titl s 'napomena', obriši napomenu. Zatim ponovno pokreni prijevod.py.")


def key(text):
    """Hrvatski tekst titla → ključ (bez interpunkcije i velikih slova)."""
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def cue_text(c):
    return " ".join(c["retci"])


def path_for(proj, lang):
    return Path(proj) / f"prijevod_{lang}.json"


def existing_languages(proj):
    return sorted(p.stem.split("_", 1)[1] for p in Path(proj).glob("prijevod_*.json")
                  if re.fullmatch(r"[a-z]{2,3}", p.stem.split("_", 1)[1]))


def load_memory(path, lang):
    """{ključ: (hr, prijevod)} iz titlova u datoteci i ranijih prijevoda."""
    mem = {}
    if not Path(path).exists():
        return mem
    data = load_json(path)
    for hr, tr in (data.get("ranije") or {}).items():
        if str(tr).strip():
            mem[key(hr)] = (hr, str(tr).strip())
    for e in data.get("titlovi") or []:
        tr = str(e.get(lang) or "").strip()
        if tr and e.get("hr"):
            mem[key(e["hr"])] = (e["hr"], tr)  # titlovi imaju prednost (Claude ih je zadnji uređivao)
    return mem


def max_chars(c):
    dur = c["do"] - c["od"]
    return int(min(titlovi.MAX_LINE * titlovi.MAX_LINES, max(dur * CPS_PRIJEVOD, 16)))


def sync(proj, cues, lang="en", za=""):
    """Upiši titlove verzije u prijevod_<lang>.json, s već poznatim prijevodima.
    Vraća (entries, nedostaju[indeksi], preuzeto_slicno[indeksi])."""
    path = path_for(proj, lang)
    mem = load_memory(path, lang)
    # napomena „provjeri" ostaje dok Claude ne promijeni prijevod ili ne obriše napomenu
    notes = {}
    if path.exists():
        for e in load_json(path).get("titlovi") or []:
            if e.get("napomena") and e.get("hr") and e.get("preuzeto"):
                notes[key(e["hr"])] = (e["preuzeto"], e["napomena"])
    keys = list(mem)
    entries, missing, fuzzy, used = [], [], [], set()
    for i, c in enumerate(cues):
        hr = cue_text(c)
        k = key(hr)
        e = {"br": i + 1, "vrijeme": f"{fmt_time(c['od'])}–{fmt_time(c['do'])}", "max_znakova": max_chars(c),
             "hr": hr, lang: ""}
        if k in mem:
            e[lang] = mem[k][1]
            used.add(k)
            if k in notes and notes[k][0] == e[lang]:   # Claude ga još nije dirao
                e["napomena"], e["preuzeto"] = notes[k][1], notes[k][0]
                fuzzy.append(i)
        else:
            best = difflib.get_close_matches(k, keys, n=1, cutoff=FUZZY) if k else []
            if best and abs(len(best[0].split()) - len(k.split())) <= 2:
                e[lang] = mem[best[0]][1]
                e["napomena"] = f"preuzeto iz sličnog titla „{mem[best[0]][0]}“ — provjeri"
                e["preuzeto"] = e[lang]
                fuzzy.append(i)
            else:
                missing.append(i)
        entries.append(e)
    ranije = {hr: tr for k, (hr, tr) in mem.items() if k not in used}
    save_json(path, {"jezik": lang, "za": za, "upute": UPUTE, "titlovi": entries, "ranije": ranije})
    return entries, missing, fuzzy


def build(entries, cues, lang="en"):
    """Prevedeni titlovi (ista vremena) + (greške, upozorenja) po titlu."""
    weak = WEAK.get(lang, set())
    out, errors, warnings = [], [], []
    for i, (e, c) in enumerate(zip(entries, cues)):
        tr = " ".join(str(e.get(lang) or "").split())
        if not tr:
            continue
        cap = titlovi.MAX_LINE * titlovi.MAX_LINES
        if "|" in tr:
            lines = [" ".join(x.split()) for x in tr.split("|") if x.strip()]
            if len(lines) > titlovi.MAX_LINES or any(len(x) > titlovi.MAX_LINE for x in lines):
                lines = titlovi.split_tokens(" ".join(lines).split(), weak)
        else:
            lines = titlovi.split_tokens(tr.split(), weak)
        flat = " ".join(lines)
        if len(flat) > cap or any(len(x) > titlovi.MAX_LINE for x in lines):
            errors.append((i, f"predugo ({len(flat)} znakova, najviše {cap}) — skrati"))
        dur = max(c["do"] - c["od"], 1e-3)
        cps, hr_cps = len(flat) / dur, len(cue_text(c)) / dur
        if cps > max(CPS_PRIJEVOD, hr_cps * 1.1) + 1e-9:
            warnings.append((i, f"brzo za čitanje ({cps:.0f} zn/s) — bolje ≤ {e.get('max_znakova', max_chars(c))} znakova"))
        if key(flat) == key(cue_text(c)) and len(key(flat).split()) >= 3:
            warnings.append((i, "isto kao hrvatski — nije prevedeno?"))
        out.append({"od": c["od"], "do": c["do"], "retci": lines})
    return out, errors, warnings


def export(proj, cues, base, lang="en", fmt="srt", za=""):
    """Sinkroniziraj datoteku i, ako je sve prevedeno i ispravno, napiši <base>.<lang>.srt/.vtt.
    Vraća rječnik sa stanjem: written (putanje), missing, fuzzy, errors, warnings, entries, tcues."""
    proj = Path(proj)
    entries, missing, fuzzy = sync(proj, cues, lang, za)
    tcues, errors, warnings = build(entries, cues, lang)
    res = {"written": [], "missing": missing, "fuzzy": fuzzy, "errors": errors, "warnings": warnings,
           "entries": entries, "tcues": tcues, "path": path_for(proj, lang)}
    if missing or errors:
        return res
    if fmt in ("srt", "oba"):
        p = proj / f"{base}.{lang}.srt"
        titlovi.write_srt(p, tcues)
        res["written"].append(p)
    if fmt in ("vtt", "oba"):
        p = proj / f"{base}.{lang}.vtt"
        titlovi.write_vtt(p, tcues)
        res["written"].append(p)
    return res


def for_render(proj, cues, out):
    """render.py: za svaki jezik koji projekt već prevodi napiši <video>.<jezik>.srt. Vraća retke za ispis."""
    lines = []
    for lang in existing_languages(proj):
        try:
            r = export(proj, cues, Path(out).stem, lang, "srt", za=Path(out).stem)
        except Exception as ex:  # prijevod nikad ne ruši render
            lines.append(f"Prijevod ({lang}): nije uspio ({ex})")
            continue
        if r["written"]:
            extra = f"; {len(r['fuzzy'])} preuzeto iz sličnih titlova, provjeri" if r["fuzzy"] else ""
            lines.append(f"Titlovi ({lang}): {r['written'][0].name}{extra}")
        else:
            n = len(r["missing"]) + len(r["errors"])
            lines.append(f"Titlovi ({lang}): {n} titlova treba prevesti/popraviti u {r['path'].name} "
                         f"→ zatim python prijevod.py {Path(proj).name} --jezik {lang}")
    return lines


def _print_list(res, idxs, lang):
    by = {}
    for it in idxs:
        i, m = it if isinstance(it, tuple) else (it, "")
        by[i] = "; ".join(x for x in (by.get(i), m) if x)
    for i in sorted(by):
        e = res["entries"][i]
        note = f"  ← {by[i]}" if by[i] else ""
        print(f"  {i + 1:3d}  {e['vrijeme']}  (≤ {e['max_znakova']})  {e['hr']}{note}")
        if e.get(lang):
            print(f"       {lang}: {e[lang]}")


def main():
    ap = argparse.ArgumentParser(description="Prijevod titlova (engleski) → reel_vN.en.srt")
    ap.add_argument("projekt")
    ap.add_argument("--jezik", default="en", help="kod jezika (zadano en)")
    ap.add_argument("--format", default="srt", choices=["srt", "vtt", "oba"])
    ap.add_argument("--verzija", type=int, default=None, help="broj verzije (reel_vN); zadano: ona koju gledaš")
    ap.add_argument("--trenutno", action="store_true", help="iz trenutnog edit.json")
    ap.add_argument("--izlaz", default=None, help="ime datoteke bez nastavka (zadano reel_vN)")
    ap.add_argument("--ispis", action="store_true", help="ispiši hrvatski i prijevod jedan uz drugi")
    a = ap.parse_args()
    lang = a.jezik.lower()
    if not re.fullmatch(r"[a-z]{2,3}", lang):
        print("Jezik je kod od 2–3 slova, npr. en, de, it.", file=sys.stderr)
        return 1

    proj = Path(a.projekt).resolve()
    edit, base, what = titlovi.pick(proj, a.verzija, a.trenutno)
    cues, total = titlovi.cues_for(proj, edit)
    if not cues:
        print("Nema riječi za titlove.", file=sys.stderr)
        return 1
    res = export(proj, cues, a.izlaz or base, lang, a.format, za=base)
    n = len(cues)

    if a.ispis:
        for i, e in enumerate(res["entries"]):
            print(f"{i + 1:3d}  {e['vrijeme']}  {e['hr']}\n     {lang}: {e[lang] or '—'}")
        print()
    if res["fuzzy"]:
        print(f"Preuzeto iz sličnih titlova ({len(res['fuzzy'])}) — provjeri da prijevod još odgovara:")
        _print_list(res, res["fuzzy"], lang)
    if res["missing"]:
        done = n - len(res["missing"])
        print(f"Prijevod ({lang}, {what}): prevedeno {done}/{n}. Treba prevesti {len(res['missing'])}:")
        _print_list(res, res["missing"], lang)
        print(f"\nUpiši prijevode u \"{lang}\" u {res['path']}\nzatim ponovno: python prijevod.py \"{proj}\""
              + (f" --jezik {lang}" if lang != "en" else ""))
    if res["errors"]:
        print(f"Treba popraviti ({len(res['errors'])}):")
        _print_list(res, res["errors"], lang)
    if res["warnings"]:
        print(f"Upozorenja ({len(res['warnings'])}):")
        _print_list(res, res["warnings"], lang)
    if not res["written"]:
        return 1
    print(f"Titlovi ({lang}, {what}): {n} titlova, video {fmt_time(total)}")
    for p in res["written"]:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
