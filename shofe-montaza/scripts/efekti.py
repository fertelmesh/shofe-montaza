"""Efekti (M5.1): zumovi, zamrznuti kadar s oznakom, film i retro; prijelazi na rezovima (M5.2a,
prijelazi.py) — upisuju se u edit.json `efekti`, render.py ih slaže ffmpegom u istom prolazu kodiranja.

  python efekti.py projekt tipovi                               koji efekti postoje i što rade
  python efekti.py projekt dodaj trzaj 0:12-0:14                vremena iz gotovog videa (kao uredi.py)
  python efekti.py projekt dodaj guranje --na "najvažnije je" [--do "filter."]   po citatu iz transkripta
  python efekti.py projekt dodaj zamrzni 0:20-0:22 --oznaka "Ovo je Ivan"
  python efekti.py projekt dodaj film 0:30-0:36   |   retro   |   pad   |   vertigo
  python efekti.py projekt rezovi                               rezovi gotovog videa (R1, R2 …) s riječima oko reza
  python efekti.py projekt dodaj iris R3   |   dodaj rolete 0:12   |   dodaj vrata --na "a sad"   (prijelaz na rezu)
  python efekti.py projekt dodaj brisanje R2 --smjer desno --trajanje 0.3
  python efekti.py projekt popis                                efekti s vremenima gotovog videa
  python efekti.py projekt makni E2   |   makni sve
  python efekti.py projekt pokazi E2                            slike efekta (početak, sredina, kraj) → efekt_E2.png
  python efekti.py projekt zvukovi                              zvučni efekti (biblioteka) → zvukovi_pregled.wav
  python efekti.py projekt dodaj zvuk 0:12 --zvuk udarac        samo zvuk na tom mjestu (ili --zvuk moj.wav)
  python efekti.py projekt zvuk E2 fijuk | ne | auto            drugi zvuk uz efekt E2 / bez zvuka / zadani
  python efekti.py projekt predlozi [--gustoca malo|puno]        Shofe predloži efekte po tekstu (predlozi.py)
  python efekti.py projekt predlozi primijeni [P1,P3]            upiše pregledane prijedloge u edit.json
  python efekti.py projekt dodaj grafika 0:12-0:15 --html grafika/kartica.html [--varijable '{"broj": "200"}']
  python efekti.py projekt dodaj grafika 0:20-0:24 --html mobitel.html --pozadina   HTML dobije taj dio videa
  python efekti.py projekt dodaj brojac 0:12-0:15 --varijable '{"broj": "350", "jedinica": "eura"}'
                                    gotov predložak (kartica, recenica, brojac, graf, popis, prije_poslije, komentar,
                                    mobitel, citat, poziv; popis: python grafika.py predlosci)

Parametri: --zum 1.3 (koliko zumira), --jacina 0.35 (vertigo), --oznaka "tekst" (zamrzni);
prijelazi: --trajanje 0.5, --smjer lijevo|desno|gore|dolje (brisanje, klizanje). Prijelaz ne mijenja trajanje.
Zvuk: uz prijelaze, trzaj, pad, zamrzni, vertigo i film ide zadani zvuk (zvukovi.py), uvijek tiši od glasa;
--zvuk IME|ne kod dodaj. Vremena se spremaju kao vremena izvornog videa (kao `izrezi`), pa efekt ostaje na istim riječima kad se
kasnije nešto izreže. Zum ide prema licu (YuNet na prvoj sličici efekta), lice ostaje na istom mjestu u kadru.
`python uredi.py projekt vrati` poništi i zadnju naredbu efekata.
"""
import argparse
import copy
from pathlib import Path

import prijelazi
import zvukovi
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
    "zvuk": {"skupina": "zvuk", "min": 0.02, "max": 30.0, "zadano": {"zvuk": "udarac"},
             "opis": "samo zvučni efekt na tom mjestu, bez slike (--zvuk ime ili --zvuk moj.wav)"},
    "grafika": {"skupina": "grafika", "min": 0.3, "max": 30.0, "zadano": {"pozadina": False},
                "opis": "HTML grafika preko videa (HyperFrames): kartica, brojka, popis … (--html, --pozadina)"},
}
# prijelazi na rezovima (prijelazi.py): skupina "prijelaz", min/max = trajanje prijelaza
for _k, _v in prijelazi.TIPOVI.items():
    TIPOVI[_k] = {"skupina": "prijelaz", "min": prijelazi.MIN_T, "max": prijelazi.MAX_T,
                  "zadano": {"trajanje": _v["zadano"]}, "opis": _v["opis"]}
ALIASI = dict(prijelazi.ALIASI)
ALIASI.update({"html": "grafika", "kartica": "grafika", "zum": "trzaj", "punch": "trzaj", "push": "guranje", "zamrzni_kadar": "zamrzni", "freeze": "zamrzni",
               "vhs": "retro", "zvucni_efekt": "zvuk", "sfx": "zvuk", "stari_film": "film", "zoom": "trzaj", "dolly": "vertigo", "pad_zuma": "pad"})
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
    if "trajanje" in p:
        p["trajanje"] = prijelazi.trajanje(p, e["tip"])
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
        if prijelazi.je_prijelaz(tip):
            x, note = prijelazi.plan_jedan(eid, tip, e, parametri(dict(e, tip=tip)), cuts, fps)
            if note:
                notes.append(note)
            if x:
                out.append(x)
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


def prijelaz_fx(fx):
    return [x for x in fx if TIPOVI[x["tip"]]["skupina"] == "prijelaz"]


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
def resolve_style(edit):
    from render import resolve_style as rs
    return rs(edit)


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
    print("Efekti (dodaj: python efekti.py projekt dodaj TIP 0:12-0:14; prijelaz: dodaj TIP R3 ili 0:12):")
    for k, v in TIPOVI.items():
        if v["skupina"] == "prijelaz" and k == next(iter(prijelazi.TIPOVI)):
            print("Prijelazi na rezu (popis rezova: python efekti.py projekt rezovi; --trajanje 0.5, --smjer):")
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
        if TIPOVI[x["tip"]]["skupina"] == "prijelaz":
            extra.append(f"prijelaz na rezu {fmt_time((a + b) / 2)}, {x['p']['trajanje']:.2f} s")
            if x["p"].get("smjer"):
                extra.append(x["p"]["smjer"])
        elif "zum" in x["p"] and x["tip"] not in ("film", "retro"):
            extra.append(f"zum {x['p']['zum']:g}")
        if x["p"].get("lice"):
            extra.append({"iris": "oko lica", "grafika": "mjesto bez lica"}.get(x["tip"], "prema licu"))
        if x["tip"] == "grafika" and x["p"].get("predlozak"):
            v = x["p"].get("varijable") or {}
            glavno = next((str(v[k]) for k in ("naslov", "tekst", "broj", "prije") if v.get(k)), "")
            extra.append(f"predložak {x['p']['predlozak']}" + (f" „{glavno[:40]}“" if glavno else ""))
            if x["p"].get("pozadina"):
                extra.append("s pozadinom")
        elif x["tip"] == "grafika":
            h = str(x["p"].get("html") or "")
            extra.append("HTML u edit.json" if "<" in h else h)
            if x["p"].get("pozadina"):
                extra.append("s pozadinom")
        z, _ = zvukovi.za_efekt(x)
        if z and zvukovi.ukljuceni(edit, resolve_style(edit)):
            extra.append(f"zvuk: {Path(str(z)).name}")
        print(f"  {x['id']:<4} {fmt_time(a)}-{fmt_time(b)}  {x['tip']:<8} {', '.join(extra)}")
    for n in notes:
        print(f"  ! {n}")


def overlap(a, b):
    return min(a[1], b[1]) - max(a[0], b[0]) > 1e-3


def cmd_dodaj(proj, words, edit, pj, a):
    import grafika
    import uredi
    if a.predlozak is not None:          # dodaj grafika … --predlozak brojac
        k = grafika.ime_predloska(a.predlozak)
        if not k:
            die(f"nema predloška '{a.predlozak}' (postoje: {', '.join(grafika.predlosci())})")
        a.predlozak = k
    elif a.html is None and grafika.ime_predloska(a.tip):   # dodaj brojac … = predložak
        a.predlozak = grafika.ime_predloska(a.tip)
        a.tip = "grafika"
    try:
        tip = tip_of(a.tip)
    except ValueError as ex:
        die(str(ex))
    ref, label = uredi.reference_edit(proj, edit, a)
    zv = None
    if a.zvuk is not None:
        try:
            zv = zvukovi.provjeri(a.zvuk, proj)
        except ValueError as ex:
            die(str(ex))
        if tip == "zvuk" and zv == "ne":
            die("zvuk bez zvuka? (--zvuk udarac, fijuk, … popis: python efekti.py projekt zvukovi)")
    a.zvuk_ok = zv
    if TIPOVI[tip]["skupina"] == "prijelaz":
        return dodaj_prijelaz(proj, words, edit, ref, label, pj, tip, a)
    if a.trajanje is not None or a.smjer is not None:
        die("--trajanje i --smjer idu uz prijelaze (python efekti.py projekt tipovi)")
    if tip != "grafika" and (a.html is not None or a.pozadina or a.varijable is not None or a.predlozak):
        die("--html, --predlozak, --pozadina i --varijable idu uz grafika")
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
        vr = list(a.vremena)
        if tip == "zvuk" and len(vr) == 1 and "-" not in vr[0]:   # zvuk na jednom mjestu: 0:12
            try:
                t0 = uredi.parse_time(vr[0])
            except ValueError as ex:
                die(str(ex))
            vr = [f"{t0:.3f}-{t0 + 0.3:.3f}"]
        try:
            ranges = uredi.parse_ranges(vr)
        except ValueError as ex:
            die(str(ex))
        if len(ranges) != 1:
            die("jedan efekt = jedan dio videa (za više dijelova pozovi dodaj više puta)")
        lo, hi = ranges[0]
        so, sd = src_range_from_times(proj, words, ref, pj, lo, hi)
        opis = f"{fmt_time(lo)}-{fmt_time(hi)} ({label})"
    if tip == "zvuk" and not a.na and len(ranges) == 1 and ranges[0][1] - ranges[0][0] > 30:
        die("zvuk ide na jedno mjesto (0:12), ne na dulji dio")
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
    if zv:
        params["zvuk"] = zv
    if tip == "grafika":
        params.update(grafika_parametri(proj, a))
        lice = None if (a.bez_lica or not params.get("predlozak")) else find_face(proj, (so + sd) / 2)
        if lice:     # predložak sjeda tamo gdje ne prekriva lice
            params["lice"] = lice
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
    # grafike smiju jedna preko druge (kartica + strelica), ostali efekti iste vrste ne
    clash = [y for y in cur if TIPOVI[y["tip"]]["skupina"] == T["skupina"] != "grafika"
             and overlap((x["s"], x["e"]), (y["s"], y["e"]))]
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
    lice_txt = (" (mjesto bez lica)" if tip == "grafika" else " prema licu") if params.get("lice") else ""
    print(f"Dodan {new['id']}: {tip}{lice_txt}, {fmt_time(fa)}-{fmt_time(fb)} ({d:.1f} s) u sljedećem renderu.")
    print(f"Provjeri slike: python efekti.py {proj.name} pokazi {new['id']}")


def grafika_parametri(proj, a):
    """--html (datoteka u projektu ili sam HTML) ili --predlozak, --varijable (JSON), --pozadina → parametri."""
    import json

    import grafika
    if a.predlozak:
        if a.html:
            die("ili --html ili predložak, ne oboje")
        var = {}
        if a.varijable is not None:
            try:
                var = json.loads(a.varijable)
            except ValueError as ex:
                die(f"--varijable nije JSON ({ex}); primjer: python grafika.py predlosci")
            if not isinstance(var, dict):
                die("--varijable mora biti JSON objekt, npr. {\"broj\": \"200\"}")
        var, gr = grafika.provjeri_varijable(a.predlozak, var)
        if gr:
            die("; ".join(gr) + f"\n(primjer: python grafika.py predlosci; slika: python grafika.py pokazi {a.predlozak})")
        out = {"predlozak": a.predlozak, "varijable": var}
        if a.pozadina or grafika.predlosci()[a.predlozak].get("pozadina"):
            out["pozadina"] = True
        return out
    if not a.html:
        die("koja grafika? gotov predložak (dodaj kartica|brojac|… --varijable '{…}'; python grafika.py predlosci) "
            "ili vlastiti --html grafika/kartica.html (u mapi projekta) ili --html '<div>…</div>'")
    h = a.html.strip()
    if "<" not in h:
        p = Path(h)
        if not p.is_absolute():
            p = proj / p
        if not p.exists():
            die(f"HTML grafike ne postoji: {h}")
        try:   # u edit.json relativno na projekt, kad je unutra (projekt se smije premjestiti)
            h = p.resolve().relative_to(proj).as_posix()
        except ValueError:
            h = str(p.resolve())
    out = {"html": h}
    if a.varijable is not None:
        try:
            v = json.loads(a.varijable)
        except ValueError as ex:
            die(f"--varijable nije JSON ({ex}); npr. --varijable '{{\"broj\": \"200\"}}'")
        if not isinstance(v, dict):
            die("--varijable mora biti JSON objekt, npr. {\"broj\": \"200\"}")
        out["varijable"] = v
    if a.pozadina:
        out["pozadina"] = True
    return out


# ---------------------------------------------------------------- prijelazi
def rez_opis(words, cuts, k, n=3):
    """Nekoliko riječi prije i iza reza k (kraj kadra k-1 | početak kadra k)."""
    A, B = cuts[k - 1], cuts[k]
    pre = [w["w"] for w in words if w["e"] <= A["b"] + 0.02 and w["s"] >= A["a"] - 0.02][-n:]
    post = [w["w"] for w in words if w["s"] >= B["a"] - 0.02 and w["e"] <= B["b"] + 0.02][:n]
    return f"…{' '.join(pre)} | {' '.join(post)}…"


def rezovi_finalno(words, edit, pj):
    """[(k, vrijeme reza u videu koji Marko gleda, cuts)] za `edit`."""
    cuts, _ = _ref_cuts(words, edit, pj)
    out = []
    for k, _, _, t in prijelazi.granice(cuts):
        out.append((k, to_final(edit, words, pj, {"s": t, "e": t})[0]))
    return out, cuts


def cmd_rezovi(proj, words, edit, pj, a):
    import uredi
    ref, label = uredi.reference_edit(proj, edit, a)
    rz, cuts = rezovi_finalno(words, ref, pj)
    if not rz:
        print("Video nema rezova (jedan kadar): prijelaz nema gdje ići.")
        return
    cc, tt = _ref_cuts(words, edit, pj)
    fx, _ = plan(edit, cc, pj["fps"], tt)
    have = {x["rez"]: x for x in prijelaz_fx(fx)}
    print(f"Rezovi ({label}); prijelaz: python efekti.py {proj.name} dodaj iris R1   (ili vrijeme 0:12)")
    for k, t in rz:
        x = have.get(k)
        extra = f"   [{x['id']} {x['tip']}]" if x else ""
        print(f"  R{k:<3} {fmt_time(t)}  {rez_opis(words, cuts, k)}{extra}")


def dodaj_prijelaz(proj, words, edit, ref, label, pj, tip, a):
    """Prijelaz na rezu: R3 (iz `rezovi`), vrijeme iz gotovog videa (najbliži rez unutar 1,5 s) ili --na citat
    (rez ispred citirane riječi)."""
    import re

    import uredi
    if a.zum is not None or a.jacina is not None or a.oznaka is not None:
        die(f"{tip} je prijelaz: ima samo --trajanje (i --smjer za brisanje/klizanje)")
    rz, cuts = rezovi_finalno(words, ref, pj)
    if not rz:
        die("video nema rezova (jedan kadar): prijelaz nema gdje ići")
    k = None
    if a.na:
        import sadrzaj
        try:
            tr = sadrzaj.Transkript(words, uredi.corrected_forms(words, ref))
            i, _ = sadrzaj.by_quote(tr, a.na, None, a.pojava)
        except sadrzaj.Greska as ex:
            die(str(ex))
        ws = words[i]["s"]
        cand = [(abs(cuts[kk]["a"] - ws), kk) for kk, _ in rz if cuts[kk]["a"] <= words[i]["e"]]
        if not cand or min(cand)[0] > 1.5:
            die(f"ispred „{a.na}“ nema reza (popis rezova: python efekti.py {proj.name} rezovi)")
        k = min(cand)[1]
        opis = f"ispred „{a.na}“"
    else:
        txt = " ".join(a.vremena).strip()
        if not txt:
            die(f"gdje? rez R3 (popis: python efekti.py {proj.name} rezovi), vrijeme 0:12 ili --na \"citat\"")
        m = re.fullmatch(r"[rR](\d+)", txt)
        if m:
            k = int(m.group(1))
            if k not in {kk for kk, _ in rz}:
                die(f"nema reza R{k} (popis: python efekti.py {proj.name} rezovi)")
            opis = f"R{k}"
        else:
            try:
                t = uredi.parse_time(txt.split("-")[0])
            except ValueError as ex:
                die(str(ex))
            dist, k = min((abs(tt - t), kk) for kk, tt in rz)
            if dist > 1.5:
                die(f"oko {fmt_time(t)} nema reza (najbliži je {dist:.1f} s dalje; popis: python efekti.py "
                    f"{proj.name} rezovi)")
            opis = f"rez u {fmt_time(dict(rz)[k])} ({label})"
    params = {}
    if a.trajanje is not None:
        params["trajanje"] = round(max(prijelazi.MIN_T, min(prijelazi.MAX_T, a.trajanje)), 3)
    if a.smjer is not None:
        if not prijelazi.TIPOVI[tip].get("smjer"):
            die(f"{tip} nema smjer (smjer imaju: brisanje, klizanje)")
        sm = a.smjer.strip().lower()
        if sm not in prijelazi.SMJEROVI:
            die(f"smjer: {', '.join(prijelazi.SMJEROVI)}")
        params["smjer"] = sm
    if getattr(a, "zvuk_ok", None):
        params["zvuk"] = a.zvuk_ok
    if tip == "iris" and not a.bez_lica:   # krug se otvara oko lica u novom kadru
        lice = find_face(proj, cuts[k]["a"] + 0.05)
        if lice:
            params["lice"] = lice
    new = {"id": None, "tip": tip, "od": round(cuts[k - 1]["b"], 3), "do": round(cuts[k]["a"], 3),
           "parametri": params, "naredba": f"{tip} {opis}"}
    edit2 = copy.deepcopy(edit)
    fxs = edit2.setdefault("efekti", [])
    n = max((int(str(e.get("id", "E0"))[1:] or 0) for e in fxs if str(e.get("id", "")).startswith("E")),
            default=0) + 1
    new["id"] = f"E{n}"
    cur_cuts, total = _ref_cuts(words, edit2, pj)
    x, note = prijelazi.plan_jedan(new["id"], tip, new, parametri(new), cur_cuts, pj["fps"])
    if not x:
        die(note.replace(f"prijelaz {new['id']} ({tip}) preskočen: ", "") if note else "tog reza nema")
    cur, _ = plan(edit2, cur_cuts, pj["fps"], total)
    clash = [y for y in prijelaz_fx(cur) if overlap((x["s"], x["e"]), (y["s"], y["e"]))]
    if clash and not a.zamijeni:
        y = clash[0]
        die(f"na tom rezu već je {y['id']} ({y['tip']}). Zamijeni ga: dodaj … --zamijeni, ili makni {y['id']}")
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
    uredi.save_history(proj, f"prijelaz {tip} {opis}")
    save_json(proj / "edit.json", edit2)
    fa, fb = to_final(edit2, words, pj, x)
    if note:
        print(f"  ! {note}")
    lice_txt = " oko lica" if params.get("lice") else ""
    print(f"Dodan {new['id']}: prijelaz {tip}{lice_txt} na rezu {fmt_time((fa + fb) / 2)} "
          f"({x['p']['trajanje']:.2f} s, {fmt_time(fa)}-{fmt_time(fb)}) u sljedećem renderu.")
    print(f"Provjeri slike: python efekti.py {proj.name} pokazi {new['id']}")


def cmd_zvukovi(proj):
    """Popis zvukova biblioteke + uz koji efekt idu; svi jedan za drugim u zvukovi_pregled.wav."""
    uz = {}
    for tip, (z, _) in zvukovi.PAROVI.items():
        if z and tip != "zvuk":
            uz.setdefault(z, []).append(tip)
    out = proj / "zvukovi_pregled.wav"
    marks = dict(zvukovi.pregled(out))
    print("Zvučni efekti (naši, sintetizirani, CC0; uvijek tiši od glasa):")
    for k, Z in zvukovi.ZVUKOVI.items():
        tips = f"  [uz: {', '.join(uz[k])}]" if k in uz else ""
        print(f"  {k:<13} {Z['opis']} ({Z['razina']:+.0f} LU naspram glasa){tips}  @{marks[k]:.1f}s")
    print(f"Poslušaj sve: {out}")
    print("Promijeni: python efekti.py projekt zvuk E2 fijuk | ne | auto; samo zvuk: dodaj zvuk 0:12 --zvuk udarac; "
          "vlastiti: --zvuk moj.wav; glasnije/tiše sve: edit.json \"zvucni_efekti_glasnoca\": 3 (dB); "
          "isključi: \"zvucni_efekti\": false")


def cmd_zvuk(proj, edit, eid, want):
    import uredi
    fxs = edit.get("efekti") or []
    e = next((e for e in fxs if str(e.get("id", "")).upper() == eid.upper()), None)
    if e is None:
        die(f"nema efekta {eid} (popis: python efekti.py {proj.name} popis)")
    if not want:
        die("koji zvuk? npr. zvuk E2 fijuk | ne | auto (popis: python efekti.py projekt zvukovi)")
    w = want.strip().lower()
    if w in ("auto", "zadano"):
        val = None
    else:
        try:
            val = zvukovi.provjeri(want, proj)
        except ValueError as ex:
            die(str(ex))
    if e.get("tip") == "zvuk" and val in (None, "ne"):
        die(f"{e['id']} je samo zvuk; makni ga: python efekti.py {proj.name} makni {e['id']}")
    uredi.save_history(proj, f"zvuk {e['id']} {want}")
    par = e.setdefault("parametri", {})
    if val is None:
        par.pop("zvuk", None)
    else:
        par["zvuk"] = val
    save_json(proj / "edit.json", edit)
    z, _ = zvukovi.za_efekt({"tip": tip_of(e["tip"]), "p": par})
    print(f"{e['id']} ({e['tip']}): " + (f"zvuk {Path(str(z)).name}" if z else "bez zvuka") + " u sljedećem renderu.")


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
    if TIPOVI[x["tip"]]["skupina"] == "prijelaz":   # prije, četvrtina, sredina, tri četvrtine, iza
        pts = [max(0.0, x["s"] - 0.2), x["s"] + d / 4, x["s"] + d / 2, x["s"] + 3 * d / 4,
               min(total - 1.0 / pj["fps"], x["e"] + 0.1)]
    else:
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
    ap = argparse.ArgumentParser(description="Efekti: zumovi, zamrzni + oznaka, film, retro, prijelazi")
    ap.add_argument("projekt")
    ap.add_argument("naredba", help="tipovi | dodaj | popis | rezovi | makni | pokazi | zvuk | zvukovi | predlozi")
    ap.add_argument("tip", nargs="?", help="za dodaj: guranje, trzaj, pad, vertigo, zamrzni, film, retro ili "
                                           "prijelaz (iris, rolete, vrata, …); za makni/pokazi: E1 (ili 'sve')")
    ap.add_argument("vremena", nargs="*", help="dio gotovog videa, npr. 0:12-0:14; prijelaz: R3 ili 0:12")
    ap.add_argument("--na", help="doslovni citat iz transkripta umjesto vremena")
    ap.add_argument("--do", help="citat: kraj dijela (iza --na)")
    ap.add_argument("--pojava", type=int, default=None)
    ap.add_argument("--zum", type=float, default=None, help="koliko zumira (1.0–2.0)")
    ap.add_argument("--jacina", type=float, default=None, help="vertigo: koliko se pozadina rasteže (0.05–0.6)")
    ap.add_argument("--oznaka", default=None, help="zamrzni: tekst oznake")
    ap.add_argument("--trajanje", type=float, default=None, help="prijelaz: trajanje u s (0.2–1.5)")
    ap.add_argument("--smjer", default=None, help="brisanje/klizanje: lijevo, desno, gore, dolje")
    ap.add_argument("--zvuk", default=None, help="zvuk uz efekt: ime (fijuk, udarac, …), ne, ili moj.wav")
    ap.add_argument("--html", default=None, help="grafika: HTML datoteka (u mapi projekta) ili sam HTML")
    ap.add_argument("--varijable", default=None, help="grafika: JSON s podacima za HTML (window.SHOFE.varijable)")
    ap.add_argument("--predlozak", default=None, help="grafika: gotov predložak (python grafika.py predlosci)")
    ap.add_argument("--pozadina", action="store_true", help="grafika: HTML dobije taj dio videa kao <video>")
    ap.add_argument("--bez-lica", action="store_true", help="zum prema sredini, ne prema licu")
    ap.add_argument("--zamijeni", action="store_true", help="zamijeni efekt iste vrste na tom mjestu")
    ap.add_argument("--verzija", type=int, default=None, help="vremena iz reel_vN (zadano: zadnji render)")
    ap.add_argument("--trenutno", action="store_true", help="vremena prema trenutnom edit.json")
    ap.add_argument("--proba", action="store_true")
    ap.add_argument("--gustoca", default=None, help="predlozi: malo | normalno | puno")
    ap.add_argument("--bez-pregleda", action="store_true", help="predlozi primijeni: bez Claudeova pregleda")
    a = ap.parse_args()
    proj = Path(a.projekt).resolve()
    nar = a.naredba.lower()
    if nar == "tipovi":
        cmd_tipovi()
        return
    if nar in ("zvukovi", "zvucni"):
        cmd_zvukovi(proj if proj.is_dir() else Path.cwd())
        return
    for f in ("project.json", "transcript.json", "edit.json"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    if nar in ("predlozi", "predloži", "prijedlog"):
        import predlozi
        if a.tip:
            a.vremena = [a.tip, *a.vremena]
        predlozi.cmd(proj, words, edit, pj, a)
    elif nar == "popis":
        cmd_popis(proj, words, edit, pj)
    elif nar == "rezovi":
        cmd_rezovi(proj, words, edit, pj, a)
    elif nar == "dodaj":
        if not a.tip:
            die("koji efekt? (python efekti.py projekt tipovi)")
        cmd_dodaj(proj, words, edit, pj, a)
    elif nar == "zvuk":
        if not a.tip:
            die("uz koji efekt? npr. zvuk E2 fijuk")
        cmd_zvuk(proj, edit, a.tip, " ".join(a.vremena))
    elif nar in ("makni", "obrisi", "obriši"):
        if not a.tip:
            die("koji? npr. makni E2 ili makni sve")
        cmd_makni(proj, edit, [a.tip, *a.vremena])
    elif nar in ("pokazi", "pokaži"):
        if not a.tip:
            die("koji? npr. pokazi E2")
        cmd_pokazi(proj, words, edit, pj, a.tip)
    else:
        die(f"nepoznata naredba '{a.naredba}' (tipovi, dodaj, popis, rezovi, makni, pokazi, zvuk, zvukovi, predlozi)")


if __name__ == "__main__":
    main()
