"""Render odabranih isječaka u seriji (M3.3): svaki isječak iz isjecci.json → isjecci/K1_naslov.mp4.

Pozva ga `isjecci.py shofe_projekt render [K1,K3]`. Za svaki isječak napravi zaseban edit (kopija
glavnog edit.json: ispravljeni tekst, izbačene poštapalice, ponovljeni pokušaji, stil, glazba) u kojem
je sve izvan isječka izrezano, s Claudeovim hookom i naslovom isječka, i montira ga istim render.py
kao glavni video (titlovi, stil, zum, glazba, SRT, FCPXML). Glavni edit.json i verzije se ne mijenjaju.
"""
import copy
import datetime as _dt
import re
from pathlib import Path

from common import die, ffmpeg, fmt_time, load_json, run, save_json
from sadrzaj import fold

MAPA = "isjecci"
# ključevi koje isječak smije imati sam za sebe (inače vrijedi glavni edit.json)
PREUZMI = ("stil", "hook", "hook_trajanje", "naglasi", "boja", "velicina_titlova", "pozicija_titlova",
           "velika_slova", "zoom", "boja_slike", "glazba", "glazba_glasnoca", "brzina", "traka_napretka", "titlovi")


class Greska(Exception):
    pass


def slug(text, n=40):
    s = fold_keep_spaces(text or "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-")


def fold_keep_spaces(s):
    return " ".join(fold(x) for x in s.split())


def ime_datoteke(c, brzo=False):
    base = str(c["id"])
    sl = slug(c.get("naslov") or "")
    if sl:
        base += "_" + sl
    return f"{MAPA}/{base}{'_pregled' if brzo else ''}.mp4"


def granice(words, c):
    """Indeksi prve i zadnje riječi isječka u transcript.json (po `rijeci`, provjereno po vremenu)."""
    od, do = float(c["od"]), float(c["do"])
    a, b = (c.get("rijeci") or [None, None])[:2]
    ok = (isinstance(a, int) and isinstance(b, int) and 0 <= a <= b < len(words)
          and abs(words[a]["s"] - od) < 0.06 and abs(words[b]["e"] - do) < 0.06)
    if not ok:
        idx = [i for i, w in enumerate(words) if w["s"] >= od - 0.06 and w["e"] <= do + 0.06]
        if not idx:
            raise Greska(f"{c['id']}: između {fmt_time(od)} i {fmt_time(do)} nema riječi u transkriptu")
        a, b = idx[0], idx[-1]
    return a, b


def edit_za_isjecak(base, words, c, duration, stil=None):
    """→ (edit, napomene). Sve izvan isječka ide u `izrezi`; vlastiti rezovi isječka (`izrezi` u
    isjecci.json, sekunde snimke) dodaju se; rezovi glavnog videa (uredi.py) se ne prenose."""
    a, b = granice(words, c)
    e = copy.deepcopy(base)
    notes = []
    glavni = e.pop("izrezi", None) or []
    od, do = words[a]["s"], words[b]["e"]
    preklop = [r for r in glavni if float(r["do"]) > od and float(r["od"]) < do]
    if preklop:
        notes.append(f"{len(preklop)} rez(ova) iz glavnog videa (uredi.py) unutar isječka nije preneseno "
                     f"— isječak ima cijeli tekst kakav je Marko odobrio")
    izrezi = []
    if a > 0:
        izrezi.append({"od": 0.0, "do": round(words[a - 1]["e"], 3), "naredba": f"isječak {c['id']}: prije"})
    if b + 1 < len(words):
        izrezi.append({"od": round(words[b + 1]["s"], 3), "do": round(max(duration, words[-1]["e"]) + 1, 3),
                       "naredba": f"isječak {c['id']}: poslije"})
    for r in c.get("izrezi") or []:
        try:
            x, y = float(r["od"]), float(r["do"])
        except (KeyError, TypeError, ValueError):
            raise Greska(f"{c['id']}: 'izrezi' moraju biti [{{\"od\": s, \"do\": s}}] u sekundama snimke")
        if y > x:
            izrezi.append({"od": x, "do": y, "naredba": r.get("naredba") or f"isječak {c['id']}"})
    e["izrezi"] = izrezi
    for k in PREUZMI:
        if k in c and c[k] not in (None, "") and not (k == "naglasi" and not c[k]):
            e[k] = c[k]
    if stil:
        e["stil"] = stil
    e["hook"] = (c.get("hook") or "").strip()
    # odsječci glavnog edita koji su unutar isječka a isključeni (ponovljeni pokušaj, poštapalica, Claude)
    for s in e.get("odsjecci", []):
        if not s.get("zadrzi", True) and float(s["do"]) > od + 0.05 and float(s["od"]) < do - 0.05:
            why = f" ({s['napomena']})" if s.get("napomena") else ""
            notes.append(f"odsječak #{s['id']} isključen u edit.json{why}: „{_kratko(s.get('tekst', ''))}”")
    e["isjecak"] = {"id": c["id"], "od": c["od"], "do": c["do"], "naslov": c.get("naslov", "")}
    return e, notes


def _kratko(t, n=60):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1] + "…"


def odaberi_isjecke(data, ids=None, find=None):
    """ids = 'K1,K3' ili None (svi odobreni). → popis isječaka."""
    if ids:
        return find(data, ids)
    cs = [c for c in data.get("isjecci", []) if c.get("status") == "odobren"]
    if not cs:
        raise Greska("nijedan isječak nije odobren. Marko bira: isjecci.py <projekt> odobri K1,K3 "
                     "(ili navedi isječke: isjecci.py <projekt> render K1,K3)")
    return cs


def provjeri_spremnost(cs, bez_hooka=False):
    """Greške prije rendera (bez hooka, odbačen, nepoznat stil…) → popis poruka."""
    from common import list_styles
    stilovi = set(list_styles())
    gr = []
    for c in cs:
        if c.get("stil") and c["stil"] not in stilovi:
            gr.append(f"{c['id']}: nepoznat stil '{c['stil']}' (postoje: {', '.join(sorted(stilovi))})")
        if c.get("status") == "odbacen":
            gr.append(f"{c['id']} je odbačen (vrati ga: isjecci.py <projekt> vrati {c['id']})")
        if not bez_hooka and not (c.get("hook") or "").strip():
            gr.append(f"{c['id']}: nema \"hook\" (3–7 riječi za prve sekunde) — Claude ga upiše u isjecci.json")
    return gr


def ukloni_stare(proj, c, novo):
    """Ako je isječak prije renderiran pod drugim imenom (promijenjen naslov), makni stare datoteke."""
    old = (c.get("render") or {}).get("datoteka")
    if not old or old == novo:
        return
    p = Path(proj) / old
    for ext in (".mp4", ".srt", ".fcpxml"):
        q = p.with_suffix(ext)
        if q.exists() and q.resolve().parent == (Path(proj) / MAPA).resolve():
            q.unlink()


def sliku_iz(proj, video, t, png):
    run([ffmpeg(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
         "-vf", "scale=360:-2", str(png)], cwd=proj)


def pregled(proj, gotovi):
    """isjecci/pregled.png: prva sekunda (s hookom) i sredina svakog isječka, jedan stupac po isječku."""
    proj = Path(proj).resolve()
    if not gotovi:
        return None
    tmp = proj / "_tmp"
    tmp.mkdir(exist_ok=True)
    cols = []
    for n, (c, res) in enumerate(gotovi):
        p1, p2 = tmp / f"pr_{n}_a.png", tmp / f"pr_{n}_b.png"
        sliku_iz(proj, res["video"], min(1.0, res["trajanje"] / 3), p1)
        sliku_iz(proj, res["video"], res["trajanje"] / 2, p2)
        cols.append((p1, p2))
    args, fc = [], []
    for i, (p1, p2) in enumerate(cols):
        args += ["-i", p1.name, "-i", p2.name]
        fc.append(f"[{2 * i}:v][{2 * i + 1}:v]vstack=inputs=2,pad=iw+12:ih:6:0:white[c{i}]")
    if len(cols) > 1:
        fc.append("".join(f"[c{i}]" for i in range(len(cols))) + f"hstack=inputs={len(cols)}[out]")
    else:
        fc[-1] = fc[-1].replace("[c0]", "[out]")
    out = proj / MAPA / "pregled.png"
    run([ffmpeg(), "-y", "-v", "error", *args, "-filter_complex", ";".join(fc), "-map", "[out]",
         "-frames:v", "1", out.resolve().as_posix()], cwd=tmp)
    return out


def renderiraj(proj, data, cs, brzo=False, kvaliteta="dobra", stil=None, kadar=None, ispis=True, oblik=None):
    """Renderiraj isječke `cs` (dio data["isjecci"]) → [(isječak, rezultat)]. Upisuje c["render"].
    oblik = "9:16" | "16:9" | None. Podcast (rezija.py, 16:9 program): zadano 9:16 iz originalnih kamera
    (uspravno.py); kod ostalih projekata isječak ima oblik projekta."""
    import render  # tek ovdje: render uvozi ffmpeg-alate
    proj = Path(proj).resolve()
    if not (proj / "edit.json").exists():
        raise Greska(f"nema edit.json. Prvo: python plan.py {proj.name} --stil podcast (i pregledaj ga), "
                     f"pa ponovo render isječaka")
    base = load_json(proj / "edit.json")
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    usp = None
    if pj["width"] > pj["height"] and pj.get("podcast") and (oblik or "9:16") == "9:16":
        import uspravno
        try:
            usp = uspravno.ucitaj(proj)
        except uspravno.Greska as e:
            if ispis:
                print(f"Napomena: uspravni isječci iz kamera nisu mogući ({e}) — isječci će biti vodoravni (16:9).")
        else:
            if ispis:
                print("Podcast: isječci 9:16 iz originalnih kamera (lice onoga tko govori; podijeljen kadar kad "
                      "pričaju dvoje). Vodoravno: --format 16:9")
    elif ispis and pj["width"] > pj["height"] and not pj.get("podcast"):
        print(f"Napomena: projekt je vodoravan ({pj['width']}×{pj['height']}); za Instagram/TikTok/Shorts "
              f"pripremi snimku u 9:16 (prepare.py --format 9:16, pa kadar.py) — isječci će biti vodoravni.")
    (proj / MAPA).mkdir(exist_ok=True)
    gotovi = []
    for k, c in enumerate(cs, 1):
        e, notes = edit_za_isjecak(base, words, c, pj["duration"], stil)
        izvor = None
        if usp is not None:
            import uspravno
            izvor = uspravno.pripremi(usp, c, proj / MAPA / "izvor_9x16" / f"{c['id']}.mp4",
                                      fps=int(round(pj["fps"])))
            if ispis:
                print(f"{c['id']}: {uspravno.sazetak(izvor['kadrovi'])}")
        if kadar:
            if ispis:
                print(f"{c['id']}: kadrovi na {kadar} s")
            res = render.render(proj, e, kadar=kadar, verzija=False, prevedi=False, ispis=False, izvor=izvor)
            zadnja = Path(res["slike"][-1])
            cilj = proj / MAPA / f"{c['id']}_kadrovi.png"
            zadnja.replace(cilj)
            res["slike"][-1] = cilj
            if ispis:
                print(f"     → {cilj}")
            gotovi.append((c, res))
            continue
        izlaz = ime_datoteke(c, brzo)
        if ispis:
            print(f"[{k}/{len(cs)}] {c['id']} {fmt_time(c['od'])}–{fmt_time(c['do'])} "
                  f"„{c.get('naslov') or _kratko(c.get('pocetak', ''), 40)}” → {izlaz}")
            for n in notes:
                print(f"     napomena: {n}")
        res = render.render(proj, e, izlaz=izlaz, brzo=brzo, kvaliteta=kvaliteta, verzija=False,
                            prevedi=False, ispis=False, izvor=izvor)
        save_json((proj / izlaz).with_suffix(".edit.json"), e)
        if not brzo:
            ukloni_stare(proj, c, izlaz)
        c["render"] = {"datoteka": izlaz, "trajanje": round(res["trajanje"], 1), "stil": e.get("stil"),
                       "hook": e["hook"], "brzo": brzo, "oblik": "9:16" if izvor else
                       f"{pj['width']}x{pj['height']}",
                       "datum": _dt.datetime.now().isoformat(timespec="seconds")}
        if ispis:
            print(f"     gotovo: {res['trajanje']:.1f} s, {res['kadrova']} kadrova, stil {e.get('stil')}, "
                  f"hook „{e['hook'] or '—'}”, titlovi {Path(res['srt']).name}"
                  + "".join(f"\n     {x}" for x in res["ispis"]))
        gotovi.append((c, res))
    return gotovi


def jedan_redak(c):
    r = c.get("render") or {}
    if not r:
        return ""
    return f"  ▶ {r['datoteka']} ({r['trajanje']:.0f} s, {r.get('stil')})"


def provjera_trajanja(gotovi, lo=20.0, hi=60.0):
    up = []
    for c, res in gotovi:
        t = res.get("trajanje")
        if t is not None and not lo - 1 <= t <= hi + 1:
            up.append(f"{c['id']} traje {t:.0f} s (cilj {lo:.0f}–{hi:.0f} s)")
    return up


def die_greska(e):
    die(str(e))
