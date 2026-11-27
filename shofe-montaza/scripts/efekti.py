"""Efekti (M5.1): zumovi, zamrznuti kadar s oznakom, film i retro — upisuju se u edit.json `efekti`,
render.py ih slaže ffmpegom u istom prolazu kodiranja.

  python efekti.py projekt tipovi                               koji efekti postoje i što rade
  python efekti.py projekt dodaj trzaj 0:12-0:14                vremena iz gotovog videa (kao uredi.py)
  python efekti.py projekt dodaj guranje --na "najvažnije je" [--do "filter."]   po citatu iz transkripta
  python efekti.py projekt dodaj zamrzni 0:20-0:22 --oznaka "Ovo je Ivan"
  python efekti.py projekt dodaj film 0:30-0:36   |   retro   |   pad   |   vertigo
  python efekti.py projekt popis                                efekti s vremenima gotovog videa
  python efekti.py projekt makni E2   |   makni sve
  python efekti.py projekt pokazi E2                            slike efekta (početak, sredina, kraj) → efekt_E2.png

Parametri: --zum 1.3 (koliko zumira), --jacina 0.35 (vertigo), --oznaka "tekst" (zamrzni).
Vremena se spremaju kao vremena izvornog videa (kao `izrezi`), pa efekt ostaje na istim riječima kad se
kasnije nešto izreže. Zum ide prema licu (YuNet na prvoj sličici efekta), lice ostaje na istom mjestu u kadru.
`python uredi.py projekt vrati` poništi i zadnju naredbu efekata.
"""
import argparse
import copy
from pathlib import Path

from common import die, ffmpeg, fmt_time, load_json, run, save_json

# skupina "kamera": najviše jedan u isto vrijeme (zum na zum ne izgleda kao rez kamere)
TIPOVI = {
    "guranje": {"skupina": "kamera", "min": 0.8, "max": 12.0, "zadano": {"zum": 1.15},
                "opis": "polagani zum prema licu kroz cijeli dio (naglasak na važnoj rečenici)"},
    "trzaj": {"skupina": "kamera", "min": 0.3, "max": 8.0, "zadano": {"zum": 1.30},
              "opis": "nagli zum u 0,1 s i drži do kraja (udarna riječ, punchline)"},
    "pad": {"skupina": "kamera", "min": 0.3, "max": 6.0, "zadano": {"zum": 1.40},
            "opis": "krene jako zumirano i u 0,45 s padne natrag na kadar (iznenađenje, „bum“)"},
    "vertigo": {"skupina": "kamera", "min": 1.0, "max": 6.0, "zadano": {"jacina": 0.28, "zum": 1.06},
                "opis": "lice ostaje, pozadina se rasteže prema rubovima (šok, „čekaj, što?“)"},
    "zamrzni": {"skupina": "kamera", "min": 0.4, "max": 4.0, "zadano": {"oznaka": "", "zum": 1.05},
                "opis": "kadar stane (zvuk ide dalje), bljesak + oznaka uz lice (tko je to, što je to)"},
    "film": {"skupina": "boja", "min": 0.5, "max": 600.0, "zadano": {},
             "opis": "stari film: toplo izblijeđeno, zrno, treperenje, titranje slike, tamni rub"},
    "retro": {"skupina": "boja", "min": 0.5, "max": 600.0, "zadano": {},
              "opis": "VHS kaseta: razmaknute boje, jače boje, linije ekrana, šum"},
}
ALIASI = {"zum": "trzaj", "punch": "trzaj", "push": "guranje", "zamrzni_kadar": "zamrzni", "freeze": "zamrzni",
          "vhs": "retro", "stari_film": "film", "zoom": "trzaj", "dolly": "vertigo", "pad_zuma": "pad"}
SREDINA = (0.5, 0.38)      # bez lica: zum prema gornjoj trećini (tamo su lica u reelu)
TRZAJ_T = 0.10             # s do punog zuma (trzaj)
PAD_T = 0.45               # s od zuma do kadra (pad)
BLJESAK_T = 0.18           # s bijelog bljeska kod zamrzni
ZUM_MAX = 2.0


def tip_of(name):
    t = (name or "").strip().lower()
    t = ALIASI.get(t, t)
    if t not in TIPOVI:
        raise ValueError(f"nepoznat efekt '{name}' (postoje: {', '.join(TIPOVI)})")
    return t


def parametri(e):
    p = dict(TIPOVI[e["tip"]]["zadano"])
    p.update({k: v for k, v in (e.get("parametri") or {}).items() if v is not None})
    if "zum" in p:
        p["zum"] = max(1.0, min(ZUM_MAX, float(p["zum"])))
    if "jacina" in p:
        p["jacina"] = max(0.05, min(0.6, float(p["jacina"])))
    return p


# ---------------------------------------------------------------- vrijeme
def out_span(od, do, cuts):
    """Dio izvornog videa [od, do] → (s, e) u vremenu gotovog videa (prije brzine) ili None ako je izrezan.
    Izrezani dijelovi unutar efekta nestanu, efekt ostaje jedan neprekinut komad gotovog videa."""
    s = e = None
    for c in cuts:
        lo, hi = max(od, c["a"]), min(do, c["b"])
        if hi - lo <= 1e-3:
            continue
        if s is None:
            s = c["o"] + lo - c["a"]
        e = c["o"] + hi - c["a"]
    return None if s is None else (s, e)


def plan(edit, cuts, fps, total):
    """Efekti iz edit.json u vremenu gotovog videa (prije brzine), poravnati na sličice.
    Vraća ([{id, tip, s, e, p}], napomene)."""
    out, notes = [], []
    for k, e in enumerate(edit.get("efekti") or []):
        eid = e.get("id") or f"E{k + 1}"
        try:
            tip = tip_of(e.get("tip"))
            od, do = float(e["od"]), float(e["do"])
        except (KeyError, TypeError, ValueError) as ex:
            notes.append(f"efekt {eid} preskočen: {ex}")
            continue
        sp = out_span(od, do, cuts) if do > od else None
        if sp is None:
            notes.append(f"efekt {eid} ({tip}) preskočen: taj dio je izrezan")
            continue
        s, en = round(sp[0] * fps) / fps, min(round(sp[1] * fps) / fps, total)
        T = TIPOVI[tip]
        if en - s < 0.5 * T["min"] or en - s < 2.0 / fps:
            notes.append(f"efekt {eid} ({tip}) preskočen: ostalo je samo {en - s:.2f} s (najmanje {T['min']} s)")
            continue
        if en - s > T["max"]:
            en = round((s + T["max"]) * fps) / fps
            notes.append(f"efekt {eid} ({tip}) skraćen na {T['max']:g} s")
        out.append({"id": eid, "tip": tip, "s": s, "e": en, "p": parametri(dict(e, tip=tip))})
    out.sort(key=lambda x: x["s"])
    return out, notes


def kamera_spans(fx):
    """Dijelovi s efektom kamere: tu stil ne radi svoj automatski zum na rezu (zum na zum)."""
    return [(x["s"], x["e"]) for x in fx if TIPOVI[x["tip"]]["skupina"] == "kamera"]


# ---------------------------------------------------------------- ffmpeg
def _f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _smooth(u):
    """Glatko 0→1 (smoothstep) za u = izraz u [0, 1]."""
    return f"({u})*({u})*(3-2*({u}))"


def _ease_out(u):
    return f"(1-pow(1-({u}),3))"


def zoom_expr(x, T):
    """Faktor zuma kao ffmpeg izraz; T = izraz za vrijeme gotovog videa (prije brzine)."""
    s, e, p = x["s"], x["e"], x["p"]
    d, Z = e - s, p.get("zum", 1.0)
    lt = f"({T}-{_f(s)})"
    if x["tip"] == "guranje":
        u = f"clip({lt}/{_f(d)},0,1)"
        return f"(1+{_f(Z - 1)}*{_smooth(u)})"
    if x["tip"] == "trzaj":
        u = f"clip({lt}/{_f(min(TRZAJ_T, d / 2))},0,1)"
        return f"(1+{_f(Z - 1)}*{_ease_out(u)})"
    if x["tip"] == "pad":
        u = f"clip({lt}/{_f(min(PAD_T, d))},0,1)"
        return f"(1+{_f(Z - 1)}*(1-{_ease_out(u)}))"
    if x["tip"] in ("vertigo", "zamrzni"):
        u = f"clip({lt}/{_f(d)},0,1)"
        return f"(1+{_f(Z - 1)}*{_smooth(u)})"
    return "1"


def centre(x, W, H):
    lice = x["p"].get("lice")
    if lice:
        return float(lice["x"]) * W, float(lice["y"]) * H
    sr = x["p"].get("sredina") or SREDINA
    return float(sr[0]) * W, float(sr[1]) * H


def perspective_zoom(x, W, H, T):
    """Zum oko nepomične točke (lice ostaje na istom mjestu kadra), podpikselno (bez titranja)."""
    z = zoom_expr(x, T)
    fx, fy = centre(x, W, H)
    l, r = f"{_f(fx)}-{_f(fx)}/{z}", f"{_f(fx)}+{_f(W - fx)}/{z}"
    t, b = f"{_f(fy)}-{_f(fy)}/{z}", f"{_f(fy)}+{_f(H - fy)}/{z}"
    return (f"perspective=x0='{l}':y0='{t}':x1='{r}':y1='{t}':x2='{l}':y2='{b}':x3='{r}':y3='{b}'"
            f":interpolation=cubic:eval=frame")


def _en(x):
    return f"enable='between(t,{_f(x['s'])},{_f(x['e'] - 1e-3)})'"


def freeze_chain(fx, fps):
    """Zamrznuti kadrovi: sličice iza prve izbace se i zamijene njom (broj sličica i zvuk ostaju isti)."""
    out = []
    for x in fx:
        if x["tip"] != "zamrzni":
            continue
        f1, f2 = int(round(x["s"] * fps)), int(round(x["e"] * fps))
        if f2 - f1 < 2:
            continue
        out.append(f"select='not(between(n,{f1 + 1},{f2 - 1}))',loop=loop={f2 - f1 - 1}:size=1:start={f1},"
                   f"setpts=N/FRAME_RATE/TB")
    return out


def video_chain(fx, W, H, fps, T=None, cmd_dir=None):
    """Filteri efekata za glavnu traku (iza boje i zuma stila, prije titlova) → popis filtera za ','.

    T = izraz za vrijeme (zadano: broj sličice/fps, vrijedi za neprekinut niz sličica od 0); za jednu
    sličicu (--kadar) broj sekundi. cmd_dir = mapa projekta za naredbe vertiga (sendcmd)."""
    T = T or f"(in/{_f(float(fps))})"
    sc = min(W, H) / 1080
    chain = []
    for x in fx:
        en = _en(x)
        tip = x["tip"]
        if tip in ("guranje", "trzaj", "pad"):
            chain.append(f"{perspective_zoom(x, W, H, T)}:{en}")
        elif tip == "zamrzni":
            chain.append(f"{perspective_zoom(x, W, H, T)}:{en}")
            flash = f"0.32*max(0,1-(t-{_f(x['s'])})/{_f(BLJESAK_T)})"
            chain.append(f"eq=brightness='{flash}':saturation=0.72:contrast=1.06:eval=frame:{en}")
            chain.append(f"vignette=angle=PI/5:{en}")
        elif tip == "vertigo":
            fx_, fy_ = centre(x, W, H)
            name = f"lenscorrection@{x['id'].lower()}"
            chain.append(f"{perspective_zoom(x, W, H, T)}:{en}")
            if cmd_dir is not None:
                f = Path(cmd_dir) / "_tmp" / f"vertigo_{x['id']}.txt"
                f.parent.mkdir(exist_ok=True)
                n = max(2, int(round((x["e"] - x["s"]) * fps)))
                lines = []
                for k in range(n + 1):
                    u = k / n
                    k1 = -x["p"]["jacina"] * u * u * (3 - 2 * u)
                    lines.append(f"{x['s'] + k / fps:.4f} {name} k1 {k1:.4f};")
                f.write_text("\n".join(lines) + "\n", encoding="utf-8")
                chain.append(f"sendcmd=f=_tmp/{f.name}")
            chain.append(f"{name}=cx={_f(fx_ / W)}:cy={_f(fy_ / H)}:k1=0:k2=0:i=bilinear:{en}")
        elif tip == "film":
            m = round(0.006 * W, 2)
            jx, jy = f"{_f(1.2 * sc)}*sin({T}*53)*sin({T}*7)", f"{_f(1.6 * sc)}*sin({T}*61)*sin({T}*5)"
            chain.append(f"perspective=x0='{m}+{jx}':y0='{m}+{jy}':x1='{W - m}+{jx}':y1='{m}+{jy}'"
                         f":x2='{m}+{jx}':y2='{H - m}+{jy}':x3='{W - m}+{jx}':y3='{H - m}+{jy}'"
                         f":interpolation=linear:eval=frame:{en}")
            # 45 % sepije + blijede boje, treperenje svjetla, zrno, tamniji rubovi
            chain.append(f"colorchannelmixer=.727:.346:.085:0:.157:.859:.076:0:.122:.240:.609:0:{en}")
            chain.append(f"eq=saturation=0.78:contrast=1.08:gamma=1.04:"
                         f"brightness='0.025+0.022*sin(t*41)*sin(t*17)':eval=frame:{en}")
            chain.append(f"noise=alls=24:allf=t+u:{en}")
            chain.append(f"vignette=angle=PI/4.5:{en}")
            chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t={max(2, round(0.014 * min(W, H)))}:{en}")
        elif tip == "retro":
            sh = max(2, round(4 * sc))
            chain.append(f"rgbashift=rh=-{sh}:bh={sh}:rv={max(1, sh // 3)}:{en}")
            chain.append(f"eq=saturation=1.38:contrast=1.12:brightness=0.02:{en}")
            chain.append(f"gblur=sigma={_f(0.9 * sc)}:{en}")
            chain.append(f"noise=alls=12:allf=t:{en}")
            chain.append(f"drawgrid=w=iw:h={max(3, round(4 * H / 1920))}:t=1:color=black@0.22:{en}")
    return chain


def still_time(fx, pre):
    """Za sliku jedne sličice: zamrznuti kadar pokazuje prvu sličicu efekta."""
    for x in fx:
        if x["tip"] == "zamrzni" and x["s"] <= pre < x["e"]:
            return x["s"]
    return pre


# ---------------------------------------------------------------- oznaka (titlovi .ass)
def _ass_color(hexstr):
    h = hexstr.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ass_styles(st, W, H):
    scale = min(W, H) / 1080 * (1.0 if H > W else 0.8)
    fs = round(76 * scale)
    acc = _ass_color(st.get("boja_isticanja", "#FF7A00"))
    return [f"Style: Oznaka,Montserrat ExtraBold,{fs},&H00111111,&H000000FF,{acc},&H00000000,0,0,0,0,100,100,0,0,3,"
            f"{round(16 * scale)},0,5,0,0,0,1",
            f"Style: Strelica,Arial,10,{acc},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"]


def ass_events(fx, W, H):
    """Oznake zamrznutih kadrova: (sloj, od, do, stil, tekst) u vremenu gotovog videa (prije brzine)."""
    scale = min(W, H) / 1080 * (1.0 if H > W else 0.8)
    fs, pad = 76 * scale, 16 * scale
    ev = []
    for x in fx:
        txt = (x["p"].get("oznaka") or "").strip()
        if x["tip"] != "zamrzni" or not txt:
            continue
        txt = txt.replace("\\", "/").replace("{", "(").replace("}", ")").upper()
        fx_, fy_ = centre(x, W, H)
        fh = float((x["p"].get("lice") or {}).get("h", 0.16)) * H
        half = fs * 0.62 + pad
        above = fy_ - 0.85 * fh - half - 30 * scale
        y = above if above - half > 0.10 * H else min(fy_ + 0.95 * fh + half + 30 * scale, 0.60 * H)
        width = min(len(txt) * fs * 0.68 + 2 * pad, 0.9 * W)
        xx = max(width / 2 + 0.04 * W, min(W - width / 2 - 0.04 * W, fx_))
        s, e = x["s"] + 0.08, x["e"]
        anim = "\\fscx30\\fscy30\\t(0,150,\\fscx108\\fscy108)\\t(150,230,\\fscx100\\fscy100)\\fad(0,120)"
        ev.append((4, s, e, "Oznaka", f"{{\\an5\\pos({xx:.0f},{y:.0f})\\frz2{anim}}}{txt}"))
        # trokut prema licu (ispod ili iznad oznake)
        a = 22 * scale
        if y < fy_:
            ty = y + half - 2
            pts = f"m {fx_ - a:.0f} {ty:.0f} l {fx_ + a:.0f} {ty:.0f} {fx_:.0f} {ty + 1.4 * a:.0f}"
        else:
            ty = y - half + 2
            pts = f"m {fx_ - a:.0f} {ty:.0f} l {fx_ + a:.0f} {ty:.0f} {fx_:.0f} {ty - 1.4 * a:.0f}"
        if abs(fx_ - xx) < width / 2 - a:
            ev.append((4, s + 0.1, e, "Strelica", f"{{\\an7\\pos(0,0)\\fad(80,120)\\p1}}{pts}{{\\p0}}"))
    return ev


# ---------------------------------------------------------------- lice za zum
def find_face(proj, src_t, info=None):
    """Najveće lice na sličici izvornog videa u trenutku src_t → {x, y, h} (0–1) ili None."""
    try:
        import subprocess

        import numpy as np

        import kadar
        pj = load_json(Path(proj) / "project.json")
        W, H = pj["width"], pj["height"]
        aw = 640 if W >= H else 360
        ah = int(round(aw * H / W / 2)) * 2
        cmd = [ffmpeg(), "-v", "error", "-ss", f"{max(0.0, src_t):.3f}", "-i", str(Path(proj) / "source.mp4"),
               "-frames:v", "1", "-vf", f"scale={aw}:{ah}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        b = subprocess.run(cmd, capture_output=True).stdout
        if len(b) < aw * ah * 3:
            return None
        fr = np.frombuffer(b[:aw * ah * 3], np.uint8).reshape(ah, aw, 3)
        det = kadar.detector(aw, ah)
        _, res = det.detect(fr)
        if res is None or not len(res):
            return None
        d = max(res, key=lambda r: r[2] * r[3])
        x, y, w, h = map(float, d[:4])
        return {"x": round((x + w / 2) / aw, 4), "y": round((y + h / 2) / ah, 4), "h": round(h / ah, 4)}
    except SystemExit:
        return None
    except Exception:  # noqa: BLE001  (bez OpenCV-a ili modela: zum prema gornjoj trećini)
        return None


# ---------------------------------------------------------------- naredbe
def _ref_cuts(words, ref, pj):
    from render import build_cuts, resolve_style
    cuts, kept, total = build_cuts(words, ref, resolve_style(ref), pj["fps"], pj["duration"])
    return cuts, total


def src_range_from_times(proj, words, ref, pj, lo, hi):
    import spica
    from uredi import out_to_source, spica_of
    cuts, _ = _ref_cuts(words, ref, pj)
    sp = float(ref.get("brzina") or 1.0)
    sr = spica_of(words, ref, pj)
    a, da = spica.iz_konacnog(lo, sr)
    b, db = spica.iz_konacnog(max(lo, hi - 1e-3), sr)
    if a is None or b is None:
        die(f"{fmt_time(lo)}-{fmt_time(hi)} je u špici; efekti idu samo na snimku")
    so, sd = out_to_source(a, cuts, sp), out_to_source(b, cuts, sp)
    if so is None or sd is None or sd <= so:
        die(f"{fmt_time(lo)}-{fmt_time(hi)} nije u videu (provjeri: python uredi.py {proj.name} popis)")
    return so, sd


def to_final(edit, words, pj, x):
    """(s, e) efekta iz plan() → vremena videa koji Marko gleda (brzina, špica)."""
    import spica
    from uredi import spica_of
    sp = float(edit.get("brzina") or 1.0)
    sr = spica_of(words, edit, pj)
    return spica.u_konacno(x["s"] / sp, sr), spica.u_konacno(x["e"] / sp, sr)


def cmd_tipovi():
    print("Efekti (dodaj: python efekti.py projekt dodaj TIP 0:12-0:14):")
    for k, v in TIPOVI.items():
        z = ", ".join(f"{a}={b}" for a, b in v["zadano"].items() if b != "")
        print(f"  {k:<8} {v['opis']}  [{v['min']:g}–{v['max']:g} s{'; ' + z if z else ''}]")


def cmd_popis(proj, words, edit, pj):
    cuts, total = _ref_cuts(words, edit, pj)
    fx, notes = plan(edit, cuts, pj["fps"], total)
    if not fx and not notes:
        print("Nema efekata. Dodaj: python efekti.py projekt dodaj trzaj 0:12-0:14 (popis: tipovi)")
        return
    print("Efekti (vrijeme gotovog videa prema trenutnom edit.json):")
    for x in fx:
        a, b = to_final(edit, words, pj, x)
        extra = []
        if x["p"].get("oznaka"):
            extra.append(f"oznaka „{x['p']['oznaka']}“")
        if "zum" in x["p"] and x["tip"] not in ("film", "retro"):
            extra.append(f"zum {x['p']['zum']:g}")
        if x["p"].get("lice"):
            extra.append("prema licu")
        print(f"  {x['id']:<4} {fmt_time(a)}-{fmt_time(b)}  {x['tip']:<8} {', '.join(extra)}")
    for n in notes:
        print(f"  ! {n}")


def overlap(a, b):
    return min(a[1], b[1]) - max(a[0], b[0]) > 1e-3


def cmd_dodaj(proj, words, edit, pj, a):
    import uredi
    try:
        tip = tip_of(a.tip)
    except ValueError as ex:
        die(str(ex))
    ref, label = uredi.reference_edit(proj, edit, a)
    if a.na:
        import sadrzaj
        try:
            tr = sadrzaj.Transkript(words, uredi.corrected_forms(words, edit))
            i, j = sadrzaj.by_quote(tr, a.na, a.do, a.pojava)
        except sadrzaj.Greska as ex:
            die(str(ex))
        so, sd = words[i]["s"] - 0.05, words[j]["e"] + 0.12
        opis = f"„{a.na}“" + (f" … „{a.do}“" if a.do else "")
    else:
        if not a.vremena:
            die("gdje? vrijeme iz gotovog videa (0:12-0:14) ili --na \"citat iz transkripta\"")
        try:
            ranges = uredi.parse_ranges(a.vremena)
        except ValueError as ex:
            die(str(ex))
        if len(ranges) != 1:
            die("jedan efekt = jedan dio videa (za više dijelova pozovi dodaj više puta)")
        lo, hi = ranges[0]
        so, sd = src_range_from_times(proj, words, ref, pj, lo, hi)
        opis = f"{fmt_time(lo)}-{fmt_time(hi)} ({label})"
    T = TIPOVI[tip]
    params = {}
    if a.zum is not None:
        if tip in ("film", "retro"):
            die(f"{tip} nema zum")
        params["zum"] = max(1.0, min(ZUM_MAX, a.zum))
    if a.jacina is not None:
        params["jacina"] = a.jacina
    if a.oznaka is not None:
        if tip != "zamrzni":
            die("--oznaka ide uz zamrzni")
        params["oznaka"] = a.oznaka.strip()
    if T["skupina"] == "kamera":
        lice = None if a.bez_lica else find_face(proj, so + 0.05)
        if lice:
            params["lice"] = lice
    edit2 = copy.deepcopy(edit)
    fxs = edit2.setdefault("efekti", [])
    n = max((int(str(e.get("id", "E0"))[1:] or 0) for e in fxs if str(e.get("id", "")).startswith("E")),
            default=0) + 1
    new = {"id": f"E{n}", "tip": tip, "od": round(so, 3), "do": round(sd, 3), "parametri": params,
           "naredba": f"{tip} {opis}"}
    # provjera u vremenu gotovog videa (trenutni edit.json)
    cuts, total = _ref_cuts(words, edit2, pj)
    fx_new, _ = plan({"efekti": [new]}, cuts, pj["fps"], total)
    if not fx_new:
        die("taj dio nije u videu ili je prekratak za efekt")
    x = fx_new[0]
    d = x["e"] - x["s"]
    if d < T["min"] - 1e-3:
        die(f"{tip} treba barem {T['min']:g} s (dio je {d:.2f} s)")
    if d > T["max"] + 1e-3:
        die(f"{tip} može najviše {T['max']:g} s (dio je {d:.1f} s)")
    cur, _ = plan(edit2, cuts, pj["fps"], total)
    clash = [y for y in cur if TIPOVI[y["tip"]]["skupina"] == T["skupina"] and overlap((x["s"], x["e"]), (y["s"], y["e"]))]
    if clash and not a.zamijeni:
        y = clash[0]
        die(f"u tom dijelu već je {y['id']} ({y['tip']}); dva efekta iste vrste ne idu jedan preko drugog. "
            f"Zamijeni ga: dodaj … --zamijeni, ili makni {y['id']}")
    if clash:
        gone = {y["id"] for y in clash}
        edit2["efekti"] = [e for e in fxs if e.get("id") not in gone]
        print(f"Zamijenjen: {', '.join(sorted(gone))}")
        fxs = edit2["efekti"]
    fxs.append(new)
    fxs.sort(key=lambda e: float(e["od"]))
    if a.proba:
        print(f"(proba) dodao bih {new['id']} {tip}: {opis}")
        return
    uredi.save_history(proj, f"efekt {tip} {opis}")
    save_json(proj / "edit.json", edit2)
    fa, fb = to_final(edit2, words, pj, x)
    lice_txt = " prema licu" if params.get("lice") else ""
    print(f"Dodan {new['id']}: {tip}{lice_txt}, {fmt_time(fa)}-{fmt_time(fb)} ({d:.1f} s) u sljedećem renderu.")
    print(f"Provjeri slike: python efekti.py {proj.name} pokazi {new['id']}")


def cmd_makni(proj, edit, ids):
    import uredi
    fxs = edit.get("efekti") or []
    if not fxs:
        die("nema efekata")
    if [i.lower() for i in ids] == ["sve"]:
        gone = [e.get("id") for e in fxs]
    else:
        want = {i.upper() for i in ids}
        gone = [e.get("id") for e in fxs if str(e.get("id", "")).upper() in want]
        missing = want - {str(g).upper() for g in gone}
        if missing:
            die(f"nema efekta {', '.join(sorted(missing))} (popis: python efekti.py {proj.name} popis)")
    uredi.save_history(proj, f"makni efekt {' '.join(ids)}")
    edit["efekti"] = [e for e in fxs if e.get("id") not in gone]
    save_json(proj / "edit.json", edit)
    print(f"Maknuto: {', '.join(map(str, gone))}")


def cmd_pokazi(proj, words, edit, pj, eid):
    import render
    cuts, total = _ref_cuts(words, edit, pj)
    fx, _ = plan(edit, cuts, pj["fps"], total)
    x = next((x for x in fx if x["id"].upper() == eid.upper()), None)
    if not x:
        die(f"nema efekta {eid} u videu (popis: python efekti.py {proj.name} popis)")
    sp = float(edit.get("brzina") or 1.0)
    d = x["e"] - x["s"]
    pts = [x["s"] + 0.5 / pj["fps"], x["s"] + min(0.25, d / 3), x["s"] + d / 2, x["e"] - 1.5 / pj["fps"]]
    if x["s"] > 0.3:
        pts.insert(0, x["s"] - 0.2)
    times = [to_final(edit, words, pj, {"s": t, "e": t})[0] for t in pts]
    res = render.render(proj, edit, kadar=",".join(f"{t:.3f}" for t in times), ispis=False)
    pngs = res["slike"]
    out = proj / f"efekt_{x['id']}.png"
    if len(pngs) > 1 and (proj / "kadrovi.png").exists():
        (proj / "kadrovi.png").replace(out)
    else:
        Path(pngs[0]).replace(out)
    print(f"Efekt {x['id']} ({x['tip']}): {out}  (slike u {', '.join(fmt_time(t) for t in times)})")


def main():
    ap = argparse.ArgumentParser(description="Efekti: zumovi, zamrzni + oznaka, film, retro")
    ap.add_argument("projekt")
    ap.add_argument("naredba", help="tipovi | dodaj | popis | makni | pokazi")
    ap.add_argument("tip", nargs="?", help="za dodaj: guranje, trzaj, pad, vertigo, zamrzni, film, retro; "
                                           "za makni/pokazi: E1 (ili 'sve')")
    ap.add_argument("vremena", nargs="*", help="dio gotovog videa, npr. 0:12-0:14")
    ap.add_argument("--na", help="doslovni citat iz transkripta umjesto vremena")
    ap.add_argument("--do", help="citat: kraj dijela (iza --na)")
    ap.add_argument("--pojava", type=int, default=None)
    ap.add_argument("--zum", type=float, default=None, help="koliko zumira (1.0–2.0)")
    ap.add_argument("--jacina", type=float, default=None, help="vertigo: koliko se pozadina rasteže (0.05–0.6)")
    ap.add_argument("--oznaka", default=None, help="zamrzni: tekst oznake")
    ap.add_argument("--bez-lica", action="store_true", help="zum prema sredini, ne prema licu")
    ap.add_argument("--zamijeni", action="store_true", help="zamijeni efekt iste vrste na tom mjestu")
    ap.add_argument("--verzija", type=int, default=None, help="vremena iz reel_vN (zadano: zadnji render)")
    ap.add_argument("--trenutno", action="store_true", help="vremena prema trenutnom edit.json")
    ap.add_argument("--proba", action="store_true")
    a = ap.parse_args()
    proj = Path(a.projekt).resolve()
    nar = a.naredba.lower()
    if nar == "tipovi":
        cmd_tipovi()
        return
    for f in ("project.json", "transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    if nar == "popis":
        cmd_popis(proj, words, edit, pj)
    elif nar == "dodaj":
        if not a.tip:
            die("koji efekt? (python efekti.py projekt tipovi)")
        cmd_dodaj(proj, words, edit, pj, a)
    elif nar in ("makni", "obrisi", "obriši"):
        if not a.tip:
            die("koji? npr. makni E2 ili makni sve")
        cmd_makni(proj, edit, [a.tip, *a.vremena])
    elif nar in ("pokazi", "pokaži"):
        if not a.tip:
            die("koji? npr. pokazi E2")
        cmd_pokazi(proj, words, edit, pj, a.tip)
    else:
        die(f"nepoznata naredba '{a.naredba}' (tipovi, dodaj, popis, makni, pokazi)")


if __name__ == "__main__":
    main()
