"""Korak 4: montaža prema edit.json → reel_vN.mp4

  python render.py shofe_projekt                 puni render (nova verzija)
  python render.py shofe_projekt --brzo          brzi pregled u pola rezolucije
  python render.py shofe_projekt --kadar 1,5,12  samo slike kadrova (sekunde gotovog reela) za provjeru izgleda
"""
import argparse
import re
import shutil
from pathlib import Path

from common import (FONTS_DIR, GRADES, die, ffmpeg, filter_script_args, fmt_time, load_json,
                    load_style, norm_word, run, save_json)

ZOOM = {"nema": None, "blago": (1.08, 1.6), "jako": (1.16, 0.7)}
POS_FRAC = {"dolje": 0.24, "gore": 0.20}


# ---------------------------------------------------------------- stil
def resolve_style(edit):
    st = load_style(edit.get("stil") or "suncani")
    acc = edit.get("boja")
    if acc:
        if st.get("hook_pozadina") == st["boja_isticanja"]:
            st["hook_pozadina"] = acc
        st["boja_isticanja"] = acc
        st["boja_naglaska"] = acc
        st["boja_trake"] = acc
    for k_edit, k_style in [("pozicija_titlova", "pozicija"), ("velika_slova", "velika_slova"),
                            ("zoom", "zoom"), ("boja_slike", "boja_slike"), ("traka_napretka", "traka_napretka")]:
        if edit.get(k_edit) is not None:
            st[k_style] = edit[k_edit]
    st["velicina"] = st["velicina"] * float(edit.get("velicina_titlova") or 1.0)
    st.setdefault("boja_naglaska", st["boja_isticanja"])
    st.setdefault("boja_trake", st["boja_isticanja"])
    return st


def ass_color(hexstr):
    h = hexstr.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    opacity = int(h[6:8], 16) if len(h) >= 8 else 255
    return f"&H{255 - opacity:02X}{b}{g}{r}".upper()


def ass_time(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    cs = int(round((s - int(s)) * 100))
    s = int(s)
    if cs == 100:
        s, cs = s + 1, 0
    return f"{int(h)}:{int(m):02d}:{s:02d}.{cs:02d}"


def esc(t):
    return t.replace("\\", "/").replace("{", "(").replace("}", ")")


# ---------------------------------------------------------------- rezovi
def cut_spans(edit):
    """Izrezani dijelovi izvornog videa (`izrezi` u edit.json, upisuje ih uredi.py): [(od, do), ...]."""
    res = []
    for r in edit.get("izrezi") or []:
        a, b = float(r["od"]), float(r["do"])
        if b > a:
            res.append((a, b))
    return sorted(res)


def in_spans(t, spans):
    return any(a <= t < b for a, b in spans)


def subtract_spans(ranges, spans):
    out = []
    for a, b in ranges:
        parts = [[a, b]]
        for x, y in spans:
            nxt = []
            for p, q in parts:
                if y <= p or x >= q:
                    nxt.append([p, q])
                    continue
                if x > p:
                    nxt.append([p, x])
                if y < q:
                    nxt.append([y, q])
            parts = nxt
        out += parts
    return out


def align_tokens(tokens, wtexts):
    """Za svaki token (ispravljeni tekst iz edit.json) indeks riječi iz transkripta kojoj pripada."""
    if len(tokens) == len(wtexts):
        return list(range(len(tokens)))
    import difflib
    a = [norm_word(t) for t in tokens]
    b = [norm_word(w) for w in wtexts]
    owner = [None] * len(tokens)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                owner[i1 + k] = j1 + k
        elif op == "replace":
            for k in range(i2 - i1):
                owner[i1 + k] = j1 + min(int(k * (j2 - j1) / (i2 - i1)), j2 - j1 - 1)
    for k in range(len(owner)):  # umetnuti tokeni idu uz susjednu riječ
        if owner[k] is None:
            owner[k] = owner[k - 1] if k > 0 and owner[k - 1] is not None else None
    nxt = next((o for o in owner if o is not None), 0)
    return [o if o is not None else nxt for o in owner]


def build_cuts(words, edit, st, fps, total):
    pre, post = st.get("rezanje", [0.05, 0.12])
    spans = cut_spans(edit)
    ranges, kept = [], []  # kept: (word_index, display_text)
    segs = sorted((s for s in edit["odsjecci"] if s.get("zadrzi", True)), key=lambda s: s["od"])
    for seg in segs:
        idx = [i for i, w in enumerate(words) if w["s"] >= seg["od"] - 0.01 and w["e"] <= seg["do"] + 0.01]
        if not idx:
            continue
        cut = {norm_word(x) for x in seg.get("izbaci", [])}
        base_idx = [i for i in idx if norm_word(words[i]["w"]) not in cut]
        if not base_idx:
            continue
        tokens = [t for t in seg.get("tekst", "").split() if norm_word(t) not in cut] or [words[i]["w"] for i in base_idx]
        gone = {i for i in base_idx if in_spans((words[i]["s"] + words[i]["e"]) / 2, spans)}
        if gone:  # dio odsječka izrezan naredbom po vremenu: makni i pripadni ispravljeni tekst
            owner = align_tokens(tokens, [words[i]["w"] for i in base_idx])
            tokens = [t for t, o in zip(tokens, owner) if base_idx[o] not in gone]
        keep_idx = [i for i in base_idx if i not in gone]
        if not keep_idx:
            continue
        tokens = tokens or [words[i]["w"] for i in keep_idx]
        # tekst je ispravljen u edit.json: 1:1 ili proporcionalno po slovima
        if len(tokens) == len(keep_idx):
            kept += list(zip(keep_idx, tokens))
        else:
            kept.append((keep_idx, tokens))
        run_start = keep_idx[0]
        for j, i in enumerate(keep_idx):
            last = j == len(keep_idx) - 1 or keep_idx[j + 1] != i + 1
            if last:
                a_w, b_w = words[run_start], words[i]
                lo = a_w["s"] - pre
                if run_start > 0:
                    lo = max(lo, words[run_start - 1]["e"])
                hi = b_w["e"] + post
                if i + 1 < len(words):
                    hi = min(hi, words[i + 1]["s"])
                ranges.append([max(lo, 0.0), min(hi, total)])
                if j + 1 < len(keep_idx):
                    run_start = keep_idx[j + 1]
    if spans:
        ranges = subtract_spans(ranges, spans)
    ranges.sort()
    merged = []
    for a, b in ranges:
        if merged and a - merged[-1][1] < 1.0 / fps:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out, off = [], 0.0
    for a, b in merged:
        a, b = round(a * fps) / fps, round(b * fps) / fps
        if b - a < 2.0 / fps:
            continue
        out.append({"a": a, "b": b, "o": off})
        off += b - a
    return out, kept, off


def to_out(t, cuts):
    for c in cuts:
        if c["a"] - 1e-6 <= t <= c["b"] + 1e-6:
            return c["o"] + (t - c["a"])
    return None


def out_words(words, kept, cuts, highlights):
    res = []
    for item in kept:
        if isinstance(item[0], list):  # proporcionalna raspodjela ispravljenog teksta
            idxs, tokens = item
            spans = [(to_out(words[i]["s"], cuts), to_out(words[i]["e"], cuts)) for i in idxs]
            spans = [(s, e) for s, e in spans if s is not None and e is not None]
            if not spans:
                continue
            t0, t1 = spans[0][0], spans[-1][1]
            total_chars = sum(len(t) for t in tokens) or 1
            acc = 0
            for t in tokens:
                s = t0 + (t1 - t0) * acc / total_chars
                acc += len(t)
                e = t0 + (t1 - t0) * acc / total_chars
                res.append({"t": t, "s": s, "e": e, "hl": norm_word(t) in highlights})
        else:
            i, t = item
            s, e = to_out(words[i]["s"], cuts), to_out(words[i]["e"], cuts)
            if s is None or e is None:
                continue
            res.append({"t": t, "s": s, "e": max(e, s + 0.05), "hl": norm_word(t) in highlights})
    res.sort(key=lambda w: w["s"])
    return res


def chunk_words(ws, st):
    max_w, max_c = st["max_rijeci"], st.get("max_znakova", 30)
    chunks, cur = [], []
    for w in ws:
        if cur:
            prev = cur[-1]
            chars = sum(len(x["t"]) + 1 for x in cur) + len(w["t"])
            if (len(cur) >= max_w or chars > max_c or w["s"] - prev["e"] > 0.5
                    or prev["t"][-1:] in ".!?" or (prev["t"][-1:] in ",;:" and len(cur) >= 2)):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- titlovi
def write_ass(path, ws, st, edit, W, H, total):
    portrait = H > W
    scale = min(W, H) / 1080 * (1.0 if portrait else 0.8)
    fs = round(st["velicina"] * scale)
    up = st.get("velika_slova", False)
    pos = st.get("pozicija", "dolje")
    align = {"dolje": 2, "sredina": 5, "gore": 8}.get(pos, 2)
    mv = round(H * (POS_FRAC.get(pos, 0.24) if portrait else 0.07))
    ml = round(W * 0.08)
    box = st.get("pozadina", False)
    border_style = 3 if box else 1
    outline = round((14 if box else st.get("obrub", 6)) * scale)
    out_col = ass_color(st.get("boja_pozadine", "#000000B0") if box else st.get("boja_obruba", "#000000"))
    shadow = 0 if box else round(st.get("sjena", 0) * scale)
    spacing = st.get("razmak", 0)

    hook_fs = round(st.get("hook_velicina", 68) * scale)
    hook_mv = round(H * (0.12 if portrait else 0.06))
    styles = [
        f"Style: Cap,{st['font']},{fs},{ass_color(st['boja_teksta'])},&H000000FF,{out_col},&H80000000,0,0,0,0,100,100,{spacing},0,{border_style},{outline},{shadow},{align},{ml},{ml},{mv},1",
        f"Style: Hook,{st.get('hook_font', st['font'])},{hook_fs},{ass_color(st.get('hook_boja', '#111111'))},&H000000FF,{ass_color(st.get('hook_pozadina', '#FFFFFF'))},&H00000000,0,0,0,0,100,100,0,0,3,{round(18 * scale)},0,8,{ml},{ml},{hook_mv},1",
        f"Style: Bar,Arial,10,{ass_color(st['boja_trake'])},&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    ]
    hl_c = ass_color(st["boja_isticanja"])
    acc_c = ass_color(st["boja_naglaska"])
    pop = st.get("pop", 1.0)
    reveal = st.get("otkrivanje", False)
    mode = st.get("nacin", "karaoke")

    def T(w):
        return esc(w["t"].upper() if up else w["t"])

    ev = []
    if edit.get("titlovi", True):
        chunks = chunk_words(ws, st)
        for n, ch in enumerate(chunks):
            start = ch[0]["s"]
            nxt = chunks[n + 1][0]["s"] if n + 1 < len(chunks) else total
            end = ch[-1]["e"] + 0.35
            if nxt - ch[-1]["e"] < 0.3:
                end = nxt
            end = max(min(end, nxt), start + 0.3)
            if mode == "linija":
                txt = " ".join((f"{{\\c{acc_c}}}{T(w)}{{\\r}}" if w["hl"] else T(w)) for w in ch)
                ev.append((0, start, end, "Cap", txt))
            elif mode == "rijec":
                for j, w in enumerate(ch):
                    s = start if j == 0 else w["s"]
                    e = ch[j + 1]["s"] if j + 1 < len(ch) else end
                    big = 115 if w["hl"] else 100
                    col = f"\\c{acc_c}" if w["hl"] else ""
                    txt = f"{{{col}\\fscx{int(big * 0.7)}\\fscy{int(big * 0.7)}\\t(0,90,\\fscx{big}\\fscy{big})}}{T(w)}"
                    ev.append((0, s, max(e, s + 0.1), "Cap", txt))
            else:  # karaoke
                for j, w in enumerate(ch):
                    s = start if j == 0 else w["s"]
                    e = ch[j + 1]["s"] if j + 1 < len(ch) else end
                    parts = []
                    for k, x in enumerate(ch):
                        if k == j:
                            p = int(pop * 100)
                            parts.append(f"{{\\c{hl_c}\\fscx{p}\\fscy{p}}}{T(x)}{{\\r}}")
                        elif k > j and reveal:
                            parts.append(f"{{\\alpha&HFF&}}{T(x)}{{\\r}}")
                        elif x["hl"]:
                            parts.append(f"{{\\c{acc_c}}}{T(x)}{{\\r}}")
                        else:
                            parts.append(T(x))
                    ev.append((0, s, max(e, s + 0.05), "Cap", " ".join(parts)))

    hook = (edit.get("hook") or "").strip()
    if hook:
        hd = min(float(edit.get("hook_trajanje") or 3.0), total)
        ht = esc(hook.upper() if st.get("hook_velika_slova", True) else hook)
        ev.append((2, 0, hd, "Hook", f"{{\\fad(100,220)\\fscx85\\fscy85\\t(0,160,\\fscx100\\fscy100)}}{ht}"))
    if st.get("traka_napretka"):
        bh = max(6, round(H * 0.006))
        ev.append((5, 0, total, "Bar",
                   f"{{\\an7\\pos(0,0)\\p1\\clip(0,0,0,{bh})\\t(\\clip(0,0,{W},{bh}))}}m 0 0 l {W} 0 {W} {bh} 0 {bh}{{\\p0}}"))

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for layer, s, e, sty, txt in sorted(ev, key=lambda x: x[1]):
        lines.append(f"Dialogue: {layer},{ass_time(s)},{ass_time(e)},{sty},,0,0,0,,{txt}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- zoom
def zoom_ranges(cuts, st):
    z = ZOOM.get(st.get("zoom", "nema"))
    if not z:
        return None, []
    factor, min_gap = z
    on, last, res = False, 0.0, []
    for n, c in enumerate(cuts):
        if n > 0 and c["o"] - last >= min_gap:
            on, last = not on, c["o"]
        if on:
            s, e = c["o"], c["o"] + (c["b"] - c["a"])
            if res and abs(res[-1][1] - s) < 1e-6:
                res[-1][1] = e
            else:
                res.append([s, e])
    return factor, res


def zoom_chain(factor, W, H):
    return f"scale=w='trunc(iw*{factor}/2)*2':h=-2:flags=bicubic,crop={W}:{H}:(iw-{W})/2:(ih-{H})*0.38"


# ---------------------------------------------------------------- glavno
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--brzo", action="store_true", help="brzi pregled u pola rezolucije")
    ap.add_argument("--kvaliteta", default="dobra", choices=["dobra", "visoka"])
    ap.add_argument("--kadar", default=None, help="sekunde gotovog reela, npr. 1,4.5,12 → PNG slike")
    ap.add_argument("--izlaz", default=None, help="ime izlazne datoteke")
    a = ap.parse_args()

    proj = Path(a.projekt).resolve()
    for f in ("project.json", "transcript.json", "edit.json", "source.mp4"):
        if not (proj / f).exists():
            die(f"nedostaje {proj / f}")
    pj = load_json(proj / "project.json")
    words = load_json(proj / "transcript.json")["words"]
    edit = load_json(proj / "edit.json")
    W, H, fps = pj["width"], pj["height"], pj["fps"]
    st = resolve_style(edit)
    speed = float(edit.get("brzina") or 1.0)
    if not 0.5 <= speed <= 2.0:
        die("brzina mora biti između 0.5 i 2.0")

    cuts, kept, total = build_cuts(words, edit, st, fps, pj["duration"])
    if not cuts:
        die("nema ničega za zadržati (svi odsječci su isključeni?)")
    highlights = {norm_word(x) for p in edit.get("naglasi", []) for x in p.split()}
    ws = out_words(words, kept, cuts, highlights)

    # fontovi i titlovi u mapi projekta (izbjegava Windows probleme s putanjama u ffmpeg filterima)
    fdir = proj / "fonts"
    fdir.mkdir(exist_ok=True)
    for f in FONTS_DIR.glob("*.ttf"):
        if not (fdir / f.name).exists():
            shutil.copy2(f, fdir / f.name)
    write_ass(proj / "captions.ass", ws, st, edit, W, H, total)
    subs = "subtitles=filename=captions.ass:fontsdir=fonts"
    grade = GRADES.get(st.get("boja_slike", "neutralno"), GRADES["neutralno"])
    factor, zr = zoom_ranges(cuts, st)

    if a.kadar:
        stills_mode(a, proj, cuts, zr, factor, grade, subs, speed, W, H, total)
        return

    eps = 0.5 / fps
    sel = "+".join(f"between(t,{c['a'] - eps:.4f},{c['b'] - eps:.4f})" for c in cuts)
    g = [f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB,{grade}" + (",split=2[base][zs]" if zr else "[v1]")]
    if zr:
        en = "+".join(f"between(t,{s:.4f},{e - eps:.4f})" for s, e in zr)
        g.append(f"[zs]{zoom_chain(factor, W, H)}[zz]")
        g.append(f"[base][zz]overlay=0:0:enable='{en}'[v1]")
    vtail = f"[v1]{subs}"
    if speed != 1.0:
        vtail += f",setpts=PTS/{speed}"
    if a.brzo:
        vtail += f",scale={W // 2}:-2"
    g.append(vtail + ",format=yuv420p[vout]")

    # zvuk: svaki rez s mikro-pretapanjem da nema pucketanja
    n = len(cuts)
    if n <= 250:
        g.append(f"[0:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n)))
        for i, c in enumerate(cuts):
            d = c["b"] - c["a"]
            g.append(f"[s{i}]atrim={c['a']:.4f}:{c['b']:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=0.008,afade=t=out:st={max(d - 0.012, 0):.4f}:d=0.012[c{i}]")
        g.append("".join(f"[c{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[vraw]")
    else:
        asel = "+".join(f"between(t,{c['a']:.4f},{c['b']:.4f})" for c in cuts)
        g.append(f"[0:a]aselect='{asel}',asetpts=N/SR/TB[vraw]")
    clean = ",afftdn=nf=-25" if st.get("zvuk_ciscenje", True) else ""
    g.append(f"[vraw]highpass=f=70{clean},acompressor=threshold=-21dB:ratio=3:attack=5:release=120:makeup=2[voice]")

    inputs = ["-i", proj / "source.mp4"]
    music = edit.get("glazba")
    if music:
        mp = Path(music)
        if not mp.is_absolute():
            mp = (proj / mp) if (proj / mp).exists() else Path.cwd() / mp
        if not mp.exists():
            die(f"glazba ne postoji: {music}")
        inputs += ["-stream_loop", "-1", "-i", mp]
        vol = float(edit.get("glazba_glasnoca") or -20)
        g.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                 f"loudnorm=I=-16:TP=-2,aresample=48000,volume={vol}dB,afade=t=in:d=0.6,"
                 f"afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5[mus]")
        g.append("[voice]asplit=2[vo][sc]")
        g.append("[mus][sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck]")
        g.append("[vo][duck]amix=inputs=2:duration=first:normalize=0[mix]")
        last = "[mix]"
    else:
        last = "[voice]"
    atail = f"{last}"
    atail += f"atempo={speed}," if speed != 1.0 else ""
    g.append(f"{atail}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    fg = proj / "_tmp" / "graf.txt"
    fg.parent.mkdir(exist_ok=True)
    fg.write_text(";\n".join(g), encoding="utf-8")

    if a.izlaz:
        out = proj / a.izlaz
    else:
        nums = [int(m.group(1)) for p in proj.glob("reel_v*.mp4") if (m := re.match(r"reel_v(\d+)", p.stem))]
        v = max(nums, default=0) + 1
        out = proj / (f"reel_v{v}_pregled.mp4" if a.brzo else f"reel_v{v}.mp4")
        (proj / "verzije").mkdir(exist_ok=True)
        save_json(proj / "verzije" / f"edit_v{v}.json", edit)

    preset, crf = ("ultrafast", 26) if a.brzo else (("medium", 17) if a.kvaliteta == "visoka" else ("veryfast", 18))
    cmd = [ffmpeg(), "-y", "-v", "error", *inputs, *filter_script_args(fg),
           "-map", "[vout]", "-map", "[aout]", "-r", fps,
           "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out.name]
    print(f"Renderiram {out.name} ({st.get('naziv', edit.get('stil'))}, {n} rezova)...")
    run(cmd, cwd=proj)

    final = total / speed
    removed = [s["id"] for s in edit["odsjecci"] if not s.get("zadrzi", True)]
    print(f"\nGotovo: {out}")
    print(f"Trajanje: {fmt_time(pj['duration'])} → {fmt_time(final)}  (izrezano {pj['duration'] - final:.1f}s, {n} kadrova, {len(zr)} zumova)")
    if removed:
        print(f"Izbačeni odsječci: {', '.join('#' + str(i) for i in removed)}")
    if edit.get("izrezi"):
        print(f"Izrezano naredbama po vremenu (dijelova: {len(edit['izrezi'])}), popis: python uredi.py {proj.name} popis")


def stills_mode(a, proj, cuts, zr, factor, grade, subs, speed, W, H, total):
    times = [float(x) for x in a.kadar.split(",") if x.strip()]
    pngs = []
    for k, t in enumerate(times):
        pre = min(max(t * speed, 0), total - 0.01)
        c = next((c for c in cuts if c["o"] <= pre < c["o"] + (c["b"] - c["a"])), cuts[-1])
        src_t = c["a"] + (pre - c["o"])
        chain = [grade]
        if any(s <= pre < e for s, e in zr):
            chain.append(zoom_chain(factor, W, H))
        chain += [f"setpts=PTS-STARTPTS+{pre:.3f}/TB", subs]
        png = proj / f"kadar_{k + 1}_{t:g}s.png"
        run([ffmpeg(), "-y", "-v", "error", "-ss", f"{src_t:.3f}", "-i", "source.mp4", "-frames:v", "1",
             "-vf", ",".join(chain), png.name], cwd=proj)
        pngs.append(png)
    if len(pngs) > 1:
        tw = 360
        args = []
        for p in pngs:
            args += ["-i", p.name]
        fc = "".join(f"[{i}:v]scale={tw}:-2[s{i}];" for i in range(len(pngs)))
        fc += "".join(f"[s{i}]" for i in range(len(pngs))) + f"hstack=inputs={len(pngs)}"
        run([ffmpeg(), "-y", "-v", "error", *args, "-filter_complex", fc, "kadrovi.png"], cwd=proj)
        print(f"Kadrovi: {proj / 'kadrovi.png'}")
    else:
        print(f"Kadar: {pngs[0]}")


if __name__ == "__main__":
    main()
