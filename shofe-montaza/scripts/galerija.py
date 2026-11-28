"""Galerija efekata (M5.6): jedan render koji pokaže svaki Shofeov efekt na istom komadu snimke.

  python efekti.py projekt galerija                       svi efekti (zumovi, boja, zvuk, prijelazi, 10 predložaka)
  python efekti.py projekt galerija --samo prijelazi      samo jedna skupina: kamera, boja, zvuk, prijelazi, grafika
  python efekti.py projekt galerija --samo trzaj,iris,brojac   samo ti efekti
  python efekti.py projekt galerija --od 0:05 --brzo     komad od 0:05 gotovog videa; brzi pregled (pola rezolucije)
  python efekti.py projekt galerija --bez-grafike         bez HTML predložaka (brže, ne treba HyperFrames)

Kako radi: Shofe izabere jedan komad gotovog videa (2,2–4,2 s govora, cijela rečenica, bez reza unutra) i složi
probnu snimku u kojoj se taj komad ponavlja. Svako ponavljanje dobije jedan efekt (prvo je bez efekta, za
usporedbu), a prijelazi idu na rezove između ponavljanja. Gore u kadru piše koji je efekt (broj, ime, što radi).
Render je običan render.py (isti stil, titlovi, zvučni efekti i HTML grafika kao u pravom videu), u mapi
projekt/_galerija, pa se pripremljeni prijelazi i grafike drugi put uzmu iz predmemorije.

Izlaz (u mapi projekta): galerija.mp4, galerija.png (po jedna sličica svakog efekta u najjačem trenutku, s imenom
i vremenom) i galerija.txt (popis: vrijeme u galeriji, efekt, naredba kojom se dodaje u pravi video).
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from common import FONTS_DIR, die, ffmpeg, fmt_time, load_json, probe, run, save_json

MAPA = "_galerija"
KOMAD_MIN, KOMAD_MAX, KOMAD_IDEAL = 2.2, 4.2, 3.4   # s govora u komadu
PAD_A, PAD_B = 0.25, 0.30                          # s snimke prije prve i iza zadnje riječi komada
UVOD = 0.5                                         # s od početka ponavljanja do efekta (pola prijelaza + mir)
KRAJ = 0.3                                         # s od kraja efekta do kraja ponavljanja
NATPIS_PRIJELAZ = (0.4, 0.45)                      # natpis prijelaza: s prije i iza reza
KRUPNI = 1.3                                       # svako drugo ponavljanje: krupni kadar (zum prema licu)
SKUPINE = {"kamera": "kamera", "zum": "kamera", "zumovi": "kamera", "boja": "boja", "zvuk": "zvuk",
           "prijelaz": "prijelaz", "prijelazi": "prijelaz", "grafika": "grafika", "predlosci": "grafika",
           "predlošci": "grafika", "html": "grafika"}
OZNAKA_ZAMRZNI = "Ovo je oznaka"
REDOSLIJED = ["guranje", "trzaj", "pad", "vertigo", "zamrzni", "film", "retro", "zvuk"]


class Greska(Exception):
    pass


# ---------------------------------------------------------------- odabir efekata
def svi_efekti(bez_grafike=False):
    """[(vrsta, ime)] po redu galerije; vrsta = tip iz efekti.TIPOVI ili 'grafika' (ime = predložak)."""
    import efekti
    import grafika
    out = [(t, t) for t in REDOSLIJED if t in efekti.TIPOVI]
    out += [(t, t) for t, v in efekti.TIPOVI.items() if v["skupina"] == "prijelaz"]
    if not bez_grafike:
        out += [("grafika", k) for k in grafika.predlosci()]
    return out


def skupina(vrsta):
    import efekti
    return efekti.TIPOVI[vrsta]["skupina"]


def odaberi(samo=None, bez_grafike=False):
    """--samo 'prijelazi' | 'kamera,boja' | 'trzaj,iris,brojac' → [(vrsta, ime)] (redoslijed galerije)."""
    import efekti
    import grafika
    svi = svi_efekti(bez_grafike)
    if not samo:
        return svi
    want_sk, want = set(), set()
    for tok in re.split(r"[,\s]+", str(samo).strip().lower()):
        if not tok:
            continue
        if tok in SKUPINE:
            want_sk.add(SKUPINE[tok])
            continue
        p = grafika.ime_predloska(tok)
        if p:
            want.add(("grafika", p))
            continue
        try:
            t = efekti.tip_of(tok)
        except ValueError:
            raise Greska(f"nepoznat efekt ili skupina '{tok}' (skupine: kamera, boja, zvuk, prijelazi, grafika; "
                         f"efekti: python efekti.py projekt tipovi; predlošci: python grafika.py predlosci)")
        if t == "grafika":
            want_sk.add("grafika")
        else:
            want.add((t, t))
    if bez_grafike and (("grafika" in want_sk) or any(v == "grafika" for v, _ in want)):
        raise Greska("--bez-grafike i grafika u --samo ne idu zajedno")
    svi = svi_efekti(False)
    return [x for x in svi if x in want or skupina(x[0]) in want_sk]


# ---------------------------------------------------------------- komad snimke
def _kraj_recenice(w):
    return bool(re.search(r"[.!?…]$", w.strip()))


def odaberi_komad(words, edit, pj, od=None):
    """Komad izvornog videa za galeriju → (i, j, a, b): riječi i..j (cijela misao, bez reza unutra),
    snimka [a, b) s malo mira prije i iza. od = najraniji početak (s izvornog videa)."""
    from render import build_cuts, resolve_style
    cuts, _, _ = build_cuts(words, edit, resolve_style(edit), pj["fps"], pj["duration"])
    if not cuts:
        raise Greska("gotov video je prazan (nema zadržanih odsječaka)")
    best = None
    for c in cuts:
        idx = [k for k, w in enumerate(words) if w["s"] >= c["a"] - 0.01 and w["e"] <= c["b"] + 0.01]
        # samo nizovi uzastopnih riječi (riječ izbačena unutra = rez)
        for n, i in enumerate(idx):
            if od is not None and words[i]["s"] < od - 0.3:
                continue
            j = i
            for m in range(n, len(idx)):
                if idx[m] != i + (m - n):
                    break
                d = words[idx[m]]["e"] - words[i]["s"]
                if d > KOMAD_MAX:
                    break
                j = idx[m]
                if d < KOMAD_MIN:
                    continue
                poc = i == 0 or _kraj_recenice(words[i - 1]["w"]) or words[i]["s"] - words[i - 1]["e"] > 0.5
                kraj = _kraj_recenice(words[j]["w"]) or j + 1 >= len(words) or words[j + 1]["s"] - words[j]["e"] > 0.5
                score = 2.0 * poc + 2.0 * kraj - abs(d - KOMAD_IDEAL) - 0.002 * words[i]["s"]
                if od is not None:
                    score -= 0.05 * max(0.0, words[i]["s"] - od)
                if best is None or score > best[0]:
                    best = (score, i, j)
    if best is None:   # kratka snimka: najdulji neprekinut niz riječi
        for c in cuts:
            idx = [k for k, w in enumerate(words) if w["s"] >= c["a"] - 0.01 and w["e"] <= c["b"] + 0.01]
            if not idx:
                continue
            i, j = idx[0], idx[0]
            for k in idx[1:]:
                if k != j + 1 or words[k]["e"] - words[i]["s"] > KOMAD_MAX:
                    break
                j = k
            d = words[j]["e"] - words[i]["s"]
            if d >= 1.0 and (best is None or d > best[0]):
                best = (d, i, j)
        if best is None:
            raise Greska("u gotovom videu nema ni sekunde neprekinutog govora za galeriju")
    _, i, j = best
    a = max(0.0, words[i]["s"] - PAD_A, (words[i - 1]["e"] + 0.02) if i > 0 else 0.0)
    b = min(pj["duration"], words[j]["e"] + PAD_B, (words[j + 1]["s"] - 0.02) if j + 1 < len(words) else 1e9)
    return i, j, a, b


def _kljuc(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


def krupni_izrez(lice, W, H, Z=KRUPNI):
    """ffmpeg filter: krupni kadar (zum Z prema licu, lice ostaje na istom mjestu kadra)."""
    fx, fy = (lice["x"], lice["y"]) if lice else (0.5, 0.38)
    w, h = int(W / Z) // 2 * 2, int(H / Z) // 2 * 2
    x, y = int(round(fx * (W - w))), int(round(fy * (H - h)))
    return f"crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,setsar=1"


def napravi_snimku(proj, gal, a, nf, N, fps, W, H, lice=None):
    """gal/source.mp4 = komad [a, a + nf/fps) izvornog videa N puta zaredom (točno nf sličica i isto toliko zvuka
    svaki put); svako drugo ponavljanje je krupni kadar (kao druga kamera), da se prijelaz između dva
    ponavljanja vidi. Kodiranja: dva kratka komada (PCM zvuk, bez gubitka vremena) pa spajanje."""
    src = proj / "source.mp4"
    stv = src.stat()
    key = _kljuc(stv.st_size, int(stv.st_mtime), f"{a:.3f}", nf, N, fps, W, H, json.dumps(lice), 2)
    meta = gal / "snimka.json"
    if (gal / "source.mp4").exists() and meta.exists() and load_json(meta).get("kljuc") == key:
        return
    sr = 48000
    try:
        au = next((s for s in probe(src)["streams"] if s["codec_type"] == "audio"), None)
        if au and int(au.get("sample_rate") or 0) > 0:
            sr = int(au["sample_rate"])
    except Exception:  # noqa: BLE001
        au = None
    L = nf / fps
    ns = int(round(L * sr))
    tmp = gal / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    if au:
        af = f"[0:a]atrim=end_sample={ns},asetpts=PTS-STARTPTS,aresample={sr},apad=whole_len={ns}[a]"
    else:
        af = f"anullsrc=r={sr}:cl=stereo,atrim=end_sample={ns}[a]"
    for ime, extra in (("komad_a.mkv", ""), ("komad_b.mkv", "," + krupni_izrez(lice, W, H))):
        vf = f"[0:v]trim=end_frame={nf},setpts=PTS-STARTPTS{extra}[v]"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{a:.4f}", "-t", f"{L + 0.5:.4f}", "-i", src,
             "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "10", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", ime], cwd=tmp)
    (tmp / "komadi.txt").write_text("".join(f"file 'komad_{'ab'[r % 2]}.mkv'\n" for r in range(N)), encoding="utf-8")
    run([ffmpeg(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "komadi.txt",
         "-filter_complex", f"[0:v]setpts=N/{fps}/TB[v];[0:a]asetpts=N/SR/TB,atrim=end_sample={ns * N}[a]",
         "-map", "[v]", "-map", "[a]", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "14",
         "-g", str(int(round(fps))), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "../source.mp4"], cwd=tmp)
    save_json(meta, {"kljuc": key, "od": round(a, 3), "slicica": nf, "ponavljanja": N, "krupni": KRUPNI})


# ---------------------------------------------------------------- galerija = projekt
def opis_efekta(vrsta, ime):
    import efekti
    import grafika
    if vrsta == "grafika":
        m = grafika.predlosci()[ime]
        return m.get("naziv", ime), m.get("opis", "")
    o = efekti.TIPOVI[vrsta]["opis"]
    o = re.sub(r"\s*\((--|--smjer|--html|--zvuk)[^)]*\)", "", o).strip()
    naziv = vrsta
    if skupina(vrsta) == "prijelaz":
        naziv = f"prijelaz: {vrsta}"
    return naziv, o


def naredba(vrsta, ime):
    """Kako se taj efekt doda u pravi video (za galerija.txt)."""
    import grafika
    if vrsta == "grafika":
        prim = grafika.predlosci()[ime].get("primjer") or {}
        return f"dodaj {ime} 0:12-0:15 --varijable '{json.dumps(prim, ensure_ascii=False)}'"
    if skupina(vrsta) == "prijelaz":
        return f"dodaj {vrsta} R1   (rezovi: efekti.py projekt rezovi)"
    if vrsta == "zamrzni":
        return 'dodaj zamrzni 0:12-0:14 --oznaka "Ovo je Ivan"'
    if vrsta == "zvuk":
        return "dodaj zvuk 0:12 --zvuk udarac"
    return f"dodaj {vrsta} 0:12-0:14"


def sastavi(proj, a):
    """Probni projekt galerije u proj/_galerija → (gal, edit, popis stavki)."""
    import efekti
    import grafika
    from render import build_cuts, resolve_style
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    fps = int(pj["fps"])
    od = None
    if a.od:
        import uredi
        try:
            t0 = uredi.parse_time(a.od)
        except ValueError as ex:
            raise Greska(str(ex))
        od, _ = efekti.src_range_from_times(proj, words, edit, pj, t0, t0 + 0.2)
    try:
        sel = odaberi(a.samo, a.bez_grafike)
    except Greska:
        raise
    napomene = []
    if any(v == "grafika" for v, _ in sel):
        ok, msg = grafika.stanje()
        if not ok:
            sel = [x for x in sel if x[0] != "grafika"]
            napomene.append(f"HTML predlošci nisu u galeriji: {msg} (python grafika.py instaliraj)")
    if not sel:
        raise Greska("nema efekata za galeriju" + (f" ({napomene[0]})" if napomene else ""))
    i, j, ka, kb = odaberi_komad(words, edit, pj, od)
    nf = int(round((kb - ka) * fps))
    L = nf / fps
    stavke = [x for x in sel if skupina(x[0]) != "prijelaz"]
    prijelazi_ = [x for x in sel if skupina(x[0]) == "prijelaz"]
    N = max(len(stavke) + 1, len(prijelazi_) + 1)
    gal = proj / MAPA
    gal.mkdir(exist_ok=True)
    lice0 = None if a.bez_lica else efekti.find_face(proj, (ka + kb) / 2)
    napravi_snimku(proj, gal, ka, nf, N, fps, pj["width"], pj["height"], lice0)

    # transkript: riječi komada u svakom ponavljanju; ispravljen tekst iz edit.json
    import uredi
    alt = uredi.corrected_forms(words, edit)
    gw, segs = [], []
    for r in range(N):
        off = r * L - ka
        toks = []
        for k in range(i, j + 1):
            w = words[k]
            gw.append({"w": w["w"], "s": round(w["s"] + off, 3), "e": round(w["e"] + off, 3)})
            toks += alt.get(k) or [w["w"]]
        segs.append({"id": r + 1, "od": round(words[i]["s"] + off, 3), "do": round(words[j]["e"] + off, 3),
                     "tekst": " ".join(toks), "zadrzi": True})
    gpj = dict(pj, duration=round(N * L, 3), clips=[], galerija={"projekt": proj.name, "od": round(ka, 3),
                                                                  "do": round(kb, 3)})
    save_json(gal / "project.json", gpj)
    save_json(gal / "transcript.json", {"language": "hr", "model": "galerija", "words": gw})
    for f in ("analiza.json",):
        (gal / f).unlink(missing_ok=True)

    g = {k: edit.get(k) for k in ("stil", "boja", "velicina_titlova", "pozicija_titlova", "velika_slova",
                                  "boja_slike", "naglasi", "zvucni_efekti", "zvucni_efekti_glasnoca")
         if edit.get(k) is not None}
    g.update({"hook": "", "glazba": None, "brzina": 1.0, "zoom": "nema", "traka_napretka": False,
              "titlovi": edit.get("titlovi", True), "odsjecci": segs,
              # rez između ponavljanja (2 sličice mira): prijelaz uvijek ima rez, i kad stil ne reže tišinu
              "izrezi": [{"od": round(r * L - 1.0 / fps, 4), "do": round(r * L + 1.0 / fps, 4), "galerija": True}
                         for r in range(1, N)]})
    cuts, _, total = build_cuts(gw, g, resolve_style(g), fps, gpj["duration"])
    if len(cuts) != N:
        raise Greska(f"galerija: očekivao sam {N} kadrova, ispalo ih je {len(cuts)}")

    # lice u širokom (parna ponavljanja) i krupnom kadru (neparna); zum, iris i predlošci idu prema njemu
    lica = [None, None]
    if not a.bez_lica:
        for p_ in range(min(2, N)):
            lica[p_] = efekti.find_face(gal, cuts[p_]["a"] + 0.05)
    lica_g = [None, None]
    if not a.bez_lica:
        for p_ in range(min(2, N)):
            lica_g[p_] = efekti.find_face(gal, (cuts[p_]["a"] + cuts[p_]["b"]) / 2)
    fx, popis, nat = [], [], []
    prijelaz_na = {k: x for k, x in enumerate(prijelazi_, start=1)}     # rez k (1..) → (vrsta, ime)

    def stavka(s_, x, **kw):
        p_ = {"vrsta": None if x is None else x[0], "ime": "bez efekta" if x is None else x[1], "s": s_}
        p_.update(kw)
        popis.append(p_)
        return p_

    def dodaj_natpis(s_, e_, p_):
        x = None if p_["vrsta"] is None else (p_["vrsta"], p_["ime"])
        naziv, opis = ("bez efekta", "isti komad bez efekta, za usporedbu") if x is None else opis_efekta(*x)
        nat.append({"od": round(s_, 3), "do": round(e_, 3), "stavka": p_, "naziv": naziv, "opis": opis})

    for r, c in enumerate(cuts):
        o, ln = c["o"], c["b"] - c["a"]
        x = None if r == 0 else (stavke[r - 1] if r - 1 < len(stavke) else None)
        s_nat = o + (NATPIS_PRIJELAZ[1] if r in prijelaz_na else 0.0)
        e_nat = o + ln - (NATPIS_PRIJELAZ[0] if (r + 1) in prijelaz_na else 0.0)
        if r in prijelaz_na:
            vrsta, ime = prijelaz_na[r]
            eid = f"E{len(fx) + 1}"
            par = {}
            if vrsta == "iris" and lica[r % 2]:
                par["lice"] = lica[r % 2]
            fx.append({"id": eid, "tip": vrsta, "od": round(cuts[r - 1]["b"], 3), "do": round(c["a"], 3),
                       "parametri": par, "naredba": f"galerija {ime}"})
            import prijelazi
            d = prijelazi.TIPOVI[vrsta]["zadano"]
            p_ = stavka(o, prijelaz_na[r], e=o, slika=o + 0.05 * d, id=eid)   # slika: sredina prijelaza
            dodaj_natpis(o - NATPIS_PRIJELAZ[0], o + NATPIS_PRIJELAZ[1], p_)
        if r == 0:
            dodaj_natpis(s_nat, e_nat, stavka(o, None, e=o + ln, slika=o + ln / 2))
        if x is None:
            continue
        vrsta, ime = x
        eid = f"E{len(fx) + 1}"
        s_src, e_src = c["a"] + UVOD, c["b"] - KRAJ
        par = {}
        if vrsta == "zvuk":
            s_src = c["a"] + min(1.0, ln / 3)
            e_src = s_src + 0.3
            par["zvuk"] = "udarac"
        elif vrsta == "grafika":
            m = grafika.predlosci()[ime]
            var, _ = grafika.provjeri_varijable(ime, m.get("primjer") or {})
            par = {"predlozak": ime, "varijable": var}
            if m.get("pozadina"):
                par["pozadina"] = True
            if lica_g[r % 2]:
                par["lice"] = lica_g[r % 2]
            s_src, e_src = c["a"] + UVOD - 0.1, c["b"] - 0.15
        else:
            if vrsta == "zamrzni":
                par["oznaka"] = OZNAKA_ZAMRZNI
                e_src = min(e_src, s_src + efekti.TIPOVI["zamrzni"]["max"])
            if skupina(vrsta) == "kamera" and lica[r % 2]:
                par["lice"] = lica[r % 2]
        fx.append({"id": eid, "tip": vrsta, "od": round(s_src, 3), "do": round(e_src, 3), "parametri": par,
                   "naredba": f"galerija {ime}"})
        s_out, e_out = o + (s_src - c["a"]), o + (e_src - c["a"])
        t_sl = {"guranje": e_out - 0.25, "vertigo": e_out - 0.25, "pad": s_out + 0.06, "trzaj": s_out + 0.5,
                "zvuk": s_out}.get(vrsta, (s_out + e_out) / 2)
        dodaj_natpis(s_nat, e_nat, stavka(s_out, x, e=e_out, slika=t_sl, id=eid, kadar="krupni" if r % 2 else "široki"))
    # brojevi po vremenu u galeriji (natpis „7/20“ = sedmi efekt koji vidiš)
    popis.sort(key=lambda p_: p_["s"])
    for n, p_ in enumerate(popis, start=1):
        p_["broj"] = n
    for n_ in nat:
        n_["broj"] = n_.pop("stavka")["broj"]
        n_["ukupno"] = len(popis)
    g["efekti"] = fx
    g["galerija_natpisi"] = nat
    save_json(gal / "edit.json", g)
    info = {"komad": (ka, kb), "rijeci": (i, j), "ponavljanja": N, "trajanje": total, "napomene": napomene,
            "tekst": " ".join(alt.get(k, [words[k]["w"]])[0] for k in range(i, j + 1))}
    return gal, g, popis, info


# ---------------------------------------------------------------- natpisi (render.write_ass)
def _boja(st):
    h = st.get("boja_isticanja", "#FF7A00").lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_styles(st, W, H):
    scale = min(W, H) / 1080 * (1.0 if H > W else 0.8)
    fs = round(46 * scale)
    m = round(40 * scale)
    return [f"Style: Galerija,Montserrat ExtraBold,{fs},&H00FFFFFF,&H000000FF,&H30111111,&H00000000,0,0,0,0,"
            f"100,100,0,0,3,{round(14 * scale)},0,8,{m},{m},{round(0.035 * H)},1"]


def ass_events(natpisi, st, W, H):
    """Natpis gore u kadru: „7/29 TRZAJ“ i ispod manjim slovima što efekt radi (vrijeme gotovog videa)."""
    scale = min(W, H) / 1080 * (1.0 if H > W else 0.8)
    small = round(30 * scale)
    acc = _boja(st)
    ev = []
    for n in natpisi or []:
        naziv = str(n.get("naziv", "")).upper().replace("{", "(").replace("}", ")").replace("\\", "/")
        opis = str(n.get("opis", "")).replace("{", "(").replace("}", ")").replace("\\", "/")
        if len(opis) > 60:
            opis = opis[:58].rsplit(" ", 1)[0] + " …"
        txt = (f"{{\\fad(80,80)\\c{acc}}}{n.get('broj')}/{n.get('ukupno')}{{\\c&H00FFFFFF&}}  {naziv}"
               + (f"\\N{{\\fs{small}\\fnMontserrat SemiBold}}{opis}" if opis else ""))
        ev.append((6, float(n["od"]), float(n["do"]), "Galerija", txt))
    return ev


# ---------------------------------------------------------------- slika i popis
def slika_galerije(video, popis, dst, W, H, fps):
    """Po jedna sličica svakog efekta (iz gotove galerije, isto što se vidi u videu) u mreži s imenom i vremenom."""
    from PIL import Image, ImageDraw, ImageFont
    tmp = Path(video).parent / MAPA / "_tmp" / "slike"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    tw = 240 if H > W else 400
    th = int(round(tw * H / W))
    files = []
    for k, p in enumerate(popis):
        f = tmp / f"s{k:02d}.png"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{max(0.0, p['slika']):.3f}", "-i", Path(video).resolve(),
             "-frames:v", "1", "-vf", f"scale={tw}:{th}", f.name], cwd=tmp)
        files.append(f)
    cols = min(6 if H > W else 4, len(files))
    rows = (len(files) + cols - 1) // cols
    cap = 44
    gap = 8
    sheet = Image.new("RGB", (cols * (tw + gap) + gap, rows * (th + cap + gap) + gap), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    try:
        f1 = ImageFont.truetype(str(FONTS_DIR / "Montserrat-ExtraBold.ttf"), 17)
        f2 = ImageFont.truetype(str(FONTS_DIR / "Montserrat-SemiBold.ttf"), 14)
    except OSError:
        f1 = f2 = ImageFont.load_default()
    for k, (f, p) in enumerate(zip(files, popis)):
        x = gap + (k % cols) * (tw + gap)
        y = gap + (k // cols) * (th + cap + gap)
        try:
            im = Image.open(f).convert("RGB")
        except OSError:
            continue
        sheet.paste(im, (x, y))
        ime = "bez efekta" if p["vrsta"] is None else opis_efekta(p["vrsta"], p["ime"])[0]
        d.text((x + 2, y + th + 4), f"{p['broj']}. {ime}", font=f1, fill=(255, 255, 255))
        d.text((x + 2, y + th + 24), fmt_time(p["s"]), font=f2, fill=(200, 200, 200))
    sheet.save(dst)
    return dst


def zapisi_popis(dst, popis, info, proj_name):
    lines = [f"Galerija efekata ({len(popis)}): komad „{info['tekst']}“ ({fmt_time(info['komad'][0])}–"
             f"{fmt_time(info['komad'][1])} izvorne snimke), {info['ponavljanja']} ponavljanja, "
             f"{fmt_time(info['trajanje'])}", ""]
    for p in popis:
        naziv = "bez efekta" if p["vrsta"] is None else opis_efekta(p["vrsta"], p["ime"])[0]
        ime = f'"{proj_name}"' if " " in proj_name else proj_name
        cmd = "" if p["vrsta"] is None else f"   →  python efekti.py {ime} {naredba(p['vrsta'], p['ime'])}"
        lines.append(f"{p['broj']:>3}. {fmt_time(p['s'])}  {naziv}{cmd}")
    for n in info["napomene"]:
        lines.append(f"  ! {n}")
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


# ---------------------------------------------------------------- naredba
def cmd(proj, a):
    import render
    proj = Path(proj).resolve()
    for f in ("project.json", "transcript.json", "edit.json", "source.mp4"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    try:
        gal, g, popis, info = sastavi(proj, a)
    except Greska as ex:
        die(str(ex))
    pj = load_json(gal / "project.json")
    print(f"Galerija: {len(popis)} (s „bez efekta“), komad „{info['tekst']}“ "
          f"({info['komad'][1] - info['komad'][0]:.1f} s) × {info['ponavljanja']}")
    if a.proba:
        for p in popis:
            print(f"  {p['broj']:>3}. {fmt_time(p['s'])}  {p['ime']}")
        return {"popis": popis, "info": info}
    res = render.render(gal, g, izlaz="galerija.mp4", brzo=a.brzo, verzija=False, prevedi=False, ispis=False)
    for line in res.get("ispis") or []:
        if line.strip().startswith("!"):
            print(line)
    out = proj / "galerija.mp4"
    shutil.copy2(res["video"], out)
    png = slika_galerije(out, popis, proj / "galerija.png", pj["width"], pj["height"], pj["fps"])
    lines = zapisi_popis(proj / "galerija.txt", popis, info, proj.name)
    print("\n".join(lines[2:]))
    print(f"\nGalerija: {out} ({fmt_time(res['trajanje'])})\nSlika svih efekata: {png}\nPopis: {proj / 'galerija.txt'}")
    return {"video": out, "slika": png, "popis": popis, "info": info}


def dodaj_argumente(ap):
    ap.add_argument("--samo", default=None, help="skupine (kamera, boja, zvuk, prijelazi, grafika) ili efekti")
    ap.add_argument("--od", default=None, help="komad od tog vremena gotovog videa (npr. 0:05)")
    ap.add_argument("--brzo", action="store_true", help="brzi pregled u pola rezolucije")
    ap.add_argument("--bez-grafike", action="store_true", help="bez HTML predložaka")
    ap.add_argument("--bez-lica", action="store_true", help="zum prema sredini, ne prema licu")
    ap.add_argument("--proba", action="store_true", help="samo popis, bez rendera")


def main():
    ap = argparse.ArgumentParser(description="Galerija efekata: svi efekti na istom komadu snimke")
    ap.add_argument("projekt")
    dodaj_argumente(ap)
    a = ap.parse_args()
    cmd(Path(a.projekt), a)


if __name__ == "__main__":
    main()
