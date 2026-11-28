"""HTML grafika (M5.4): HyperFrames renderira kratki odsječak grafike, ffmpeg ga umeće natrag u gotov video.

  python grafika.py instaliraj      Node.js mora postojati (22+); instalira HyperFrames (Apache-2.0) i Chrome za render
  python grafika.py provjera        je li sve spremno (verzije, putanje)
  python grafika.py proba [mapa]    probni render jedne kartice (2 s) → grafika_proba.mp4

U edit.json je grafika efekt kao i ostali (efekti.py dodaj grafika 0:12-0:15 --html kartica.html):
  {"tip": "grafika", "od", "do", "parametri": {"html": "grafika/kartica.html" ili "<div>…</div>",
   "varijable": {"naslov": "200 eura"}, "pozadina": false}}

Dva načina:
  * preko (zadano): HTML se renderira **proziran** (ProRes 4444 s alfom) i ffmpeg ga položi preko gotovog videa.
    Video ispod ostaje netaknut (bez gubitka boje), a komad ne ovisi o ostatku videa, pa se nepromijenjena
    grafika pri sljedećem renderu ne renderira ponovno (predmemorija u _tmp/grafika/).
  * pozadina: HTML dobije taj odsječak gotovog videa kao <video id="pozadina"> (pozadina.mp4) i smije ga
    mijenjati (smanjiti u mobitel, zamutiti iza kartice, podijeliti ekran); rezultat zamijeni taj dio videa.

HTML može biti cijela HyperFrames kompozicija (ima data-composition-id) ili samo komad koji Shofe umota:
korijen #shofe veličine videa, fontovi Montserrat i Anton (č ć š ž đ), window.SHOFE = {sirina, visina,
trajanje, fps, varijable} i CSS varijable --sirina, --visina, --trajanje. Animacije: CSS @keyframes ili
Web Animations; HyperFrames ih vrti po sličicama (svaki render isti).
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from common import FONTS_DIR, data_dir, die, ffmpeg, ffprobe, find_tool

HF_VERZIJA = "0.9.104"        # zakucana verzija (isti izgled na svakom računalu); nova = provjera u CI-ju
VERZIJA_KOMADA = 1            # povećaj kad se promijeni omotač → stari komadi u predmemoriji ne vrijede
MAX_GRAFIKA = 20              # po renderu (svaka je jedan ulaz zadnjeg prolaza)
NODE_MIN = 22
POMAK = 0.25                  # sličice: komad ide ¼ sličice ranije, overlay uzme točno pravu sličicu
FONTOVI = [("Montserrat", 600, "Montserrat-SemiBold.ttf"), ("Montserrat", 800, "Montserrat-ExtraBold.ttf"),
           ("Montserrat", 900, "Montserrat-Black.ttf"), ("Anton", 400, "Anton-Regular.ttf")]
DATOTEKE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".js", ".mjs", ".json", ".ttf", ".otf",
            ".woff", ".woff2", ".mp4", ".webm", ".mov", ".wav", ".mp3"}


class Greska(Exception):
    pass


# ---------------------------------------------------------------- instalacija i pokretanje HyperFramesa
def hf_dir():
    """Gdje je HyperFrames: SHOFE_HYPERFRAMES ili <podaci>/hyperframes (preživi ponovnu instalaciju skilla)."""
    env = os.environ.get("SHOFE_HYPERFRAMES")
    return Path(env) if env else data_dir() / "hyperframes"


def node():
    """(putanja do node, glavna verzija) ili (None, None)."""
    p = find_tool("node")
    if not p and os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            c = Path(base) / "nodejs" / "node.exe"
            if base and c.exists():
                p = str(c)
                break
    if not p:
        return None, None
    try:
        out = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        return p, int(out.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return p, None


def cli():
    """Ulazna skripta HyperFramesa (pokreće se s node, bez .cmd omotača na Windowsu) ili None."""
    c = hf_dir() / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    return c if c.exists() else None


def instalirana_verzija():
    pj = hf_dir() / "node_modules" / "hyperframes" / "package.json"
    try:
        return json.loads(pj.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def okruzenje():
    """Varijable okruženja za HyperFrames: bez telemetrije i provjera novih verzija, naš ffmpeg."""
    env = dict(os.environ)
    env.update({"HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
                "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_NO_AUTO_INSTALL": "1", "NO_COLOR": "1",
                "HYPERFRAMES_FFMPEG_PATH": ffmpeg(), "HYPERFRAMES_FFPROBE_PATH": ffprobe()})
    if os.environ.get("SHOFE_PREGLEDNIK"):        # vlastiti Chrome/Chromium (npr. bez interneta)
        env["HYPERFRAMES_BROWSER_PATH"] = os.environ["SHOFE_PREGLEDNIK"]
    return env


def _npm(nodep):
    """npm kao (node, npm-cli.js) ako se nađe uz node (Windows instalacija, Linux), inače npm s PATH-a."""
    nd = Path(nodep).resolve().parent
    for c in (nd / "node_modules" / "npm" / "bin" / "npm-cli.js",
              nd.parent / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js"):
        if c.exists():
            return [nodep, str(c)]
    p = shutil.which("npm")
    return [p] if p else None


def stanje():
    """→ (spremno, poruka) za doctor.py i provjeru prije rendera."""
    nodep, major = node()
    if not nodep:
        return False, "Node.js nije instaliran (treba za HTML grafiku; winget install OpenJS.NodeJS.LTS)"
    if major is None or major < NODE_MIN:
        return False, f"Node.js {major} je prestar (treba {NODE_MIN}+; winget install OpenJS.NodeJS.LTS)"
    v = instalirana_verzija()
    if not cli() or not v:
        return False, "HyperFrames nije instaliran (python grafika.py instaliraj)"
    if v != HF_VERZIJA:
        return False, f"HyperFrames {v}, treba {HF_VERZIJA} (python grafika.py instaliraj)"
    return True, f"HyperFrames {v}, Node.js {major} ({hf_dir()})"


def instaliraj(ispis=True):
    nodep, major = node()
    if not nodep or major is None or major < NODE_MIN:
        raise Greska(stanje()[1])
    npm = _npm(nodep)
    if not npm:
        raise Greska("npm nije pronađen (dolazi s Node.js; ponovno instaliraj Node.js LTS)")
    d = hf_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "package.json").exists():
        (d / "package.json").write_text('{"name": "shofe-hyperframes", "private": true}\n', encoding="utf-8")
    if instalirana_verzija() != HF_VERZIJA:
        if ispis:
            print(f"Instaliram HyperFrames {HF_VERZIJA} u {d} ...")
        # --omit=optional: bez sharpa (njegov libvips je LGPL); HyperFrames radi i bez njega
        r = subprocess.run([*npm, "install", f"hyperframes@{HF_VERZIJA}", "--omit=optional", "--no-audit",
                            "--no-fund", "--loglevel=error", "--save-exact"], cwd=d, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=900)
        if r.returncode != 0 or instalirana_verzija() != HF_VERZIJA:
            raise Greska("npm install nije uspio:\n" + "\n".join((r.stderr or r.stdout).strip().splitlines()[-15:]))
    if not os.environ.get("SHOFE_PREGLEDNIK"):
        if ispis:
            print("Provjeravam Chrome za render (prvi put se skine, ~150 MB) ...")
        r = hf(["browser", "ensure"], cwd=d, timeout=900)
        if r.returncode != 0:
            raise Greska("Chrome za HyperFrames nije skinut:\n" + _rep(r))
    ok, msg = stanje()
    if not ok:
        raise Greska(msg)
    return msg


def _rep(r, n=15):
    lines = [x for x in (r.stderr or "").splitlines() + (r.stdout or "").splitlines()
             if x.strip() and not x.startswith("@hf-progress")]
    return "\n".join(lines[-n:])


def hf(args, cwd, timeout=1800):
    """Pokreni HyperFrames CLI (node hyperframes.mjs …) u mapi `cwd`."""
    nodep, _ = node()
    c = cli()
    if not nodep or not c:
        raise Greska(stanje()[1])
    return subprocess.run([nodep, str(c), *map(str, args)], cwd=cwd, env=okruzenje(), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


# ---------------------------------------------------------------- kompozicija
def fps_arg(fps):
    """HyperFrames prima cijeli broj ili razlomak (30000/1001)."""
    f = float(fps)
    if abs(f - round(f)) < 1e-3:
        return str(int(round(f)))
    fr = Fraction(f).limit_denominator(1001)
    return f"{fr.numerator}/{fr.denominator}"


def _f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def ucitaj_html(spec, proj):
    """parametri.html → (tekst, mapa s datotekama uz HTML ili None). Tekst s '<' je sam HTML."""
    s = str(spec or "").strip()
    if not s:
        raise Greska("grafika nema HTML (parametar html: datoteka ili <div>…</div>)")
    if "<" in s:
        return s, None
    p = Path(s)
    if not p.is_absolute():
        p = Path(proj) / p
    if not p.exists():
        raise Greska(f"HTML grafike ne postoji: {s}")
    return p.read_text(encoding="utf-8"), p.parent


def je_cijela(tekst):
    return "data-composition-id" in tekst


def _js_json(obj):
    """JSON za <script> (bez zatvaranja taga i bez problematičnih znakova)."""
    return (json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def omotaj(fragment, W, H, fps, n, pozadina, varijable):
    """Komad HTML-a → cijela HyperFrames kompozicija veličine videa, trajanja n sličica."""
    d = n / float(fps)
    ff = "\n".join(f"@font-face{{font-family:'{a}';font-weight:{w};src:url('fonts/{f}')}}" for a, w, f in FONTOVI)
    shofe = {"sirina": W, "visina": H, "trajanje": round(d, 4), "fps": float(fps), "varijable": varijable or {},
             "pozadina": bool(pozadina)}
    vid = (f'  <video id="pozadina" class="clip" src="pozadina.mp4" data-start="0" data-duration="{_f(d)}" '
           f'muted playsinline></video>\n') if pozadina else ""
    return f"""<!doctype html>
<html lang="hr"><head><meta charset="utf-8">
<style>
{ff}
html,body{{margin:0;padding:0;background:transparent;overflow:hidden}}
#shofe{{position:relative;width:{W}px;height:{H}px;overflow:hidden;font-family:'Montserrat',sans-serif;
 --sirina:{W}px;--visina:{H}px;--trajanje:{_f(d)}s}}
#pozadina{{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover}}
</style>
<script>window.SHOFE = {_js_json(shofe)};</script>
</head><body>
<div id="shofe" data-composition-id="shofe" data-width="{W}" data-height="{H}" data-fps="{fps_arg(fps)}" data-start="0" data-duration="{_f(d)}">
{vid}{fragment}
</div>
</body></html>
"""


def _datoteke_uz(mapa):
    """Slike, fontovi, CSS … iz mape HTML-a (ne podmape, ne veće od 50 MB) → [(ime, putanja)]."""
    if not mapa:
        return []
    out = []
    for p in sorted(Path(mapa).iterdir()):
        if p.is_file() and p.suffix.lower() in DATOTEKE and p.stat().st_size < 50 * 2 ** 20:
            out.append((p.name, p))
    return out


def _sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:12]


def _sha_file(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(2 ** 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------- vrijeme gotovog videa
def plan(fx, speed, fps, sp_r=None, ukupno=None):
    """Grafike iz efekti.plan (vrijeme prije brzine, bez špice) → [{id, s, n, p}] u vremenu gotovog videa:
    s = prva sličica (poravnata), n = broj sličica. Grafika koju bi prekinula uvodna špica završi na njoj."""
    import spica
    out, notes = [], []
    gx = [x for x in fx if x["tip"] == "grafika"]
    if len(gx) > MAX_GRAFIKA:
        notes.append(f"grafika je {len(gx)}; u videu je prvih {MAX_GRAFIKA}")
        gx = gx[:MAX_GRAFIKA]
    for x in gx:
        s, e = x["s"] / speed, x["e"] / speed
        if sp_r and sp_r.get("uvod") and s < sp_r["at"] - 1e-6 < e:
            e = sp_r["at"]
            notes.append(f"grafika {x['id']} skraćena: iza nje počinje špica")
        pred = bool(sp_r) and s < sp_r["at"] - 1e-6        # grafika prije uvodne špice ostaje gdje je
        s, e = spica.u_konacno(s, sp_r), (e if pred else spica.u_konacno(e, sp_r))
        k0 = int(round(s * fps))
        n = int(round(e * fps)) - k0
        if ukupno is not None:
            n = min(n, int(round(ukupno * fps)) - k0)
        if n < 2:
            notes.append(f"grafika {x['id']} preskočena: prekratka")
            continue
        out.append({"id": x["id"], "s": k0 / fps, "k0": k0, "n": n, "p": x["p"]})
    return out, notes


# ---------------------------------------------------------------- render komada
def _izvuci_pozadinu(video, g, fps, W, H, dst):
    """Taj dio gotovog videa (točno n sličica od sličice k0) → pozadina.mp4 u veličini kompozicije."""
    cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-ss", f"{max(0.0, g['s'] - 0.25 / fps):.4f}", "-i", str(video),
           "-an", "-vf", f"scale={W}:{H}:flags=bicubic,setsar=1", "-frames:v", str(g["n"]), "-r", fps_arg(fps),
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "8", "-pix_fmt", "yuv420p", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise Greska(f"pozadina grafike {g['id']} nije izrezana:\n{r.stderr[-800:]}")


def broj_slicica(p):
    r = subprocess.run([ffprobe(), "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except ValueError:
        return 0


def pripremi(proj, g, W, H, fps, video=None, ispis=False):
    """Jedna grafika → _tmp/grafika/<ključ>.mov (proziran) ili .mp4 (s pozadinom). Vraća putanju komada.
    video = gotov video (za način s pozadinom)."""
    proj = Path(proj)
    d = proj / "_tmp" / "grafika"
    d.mkdir(parents=True, exist_ok=True)
    p = g["p"]
    tekst, mapa = ucitaj_html(p.get("html"), proj)
    pozadina = bool(p.get("pozadina"))
    var = p.get("varijable") or {}
    if isinstance(var, str):
        try:
            var = json.loads(var)
        except ValueError:
            raise Greska(f"grafika {g['id']}: varijable nisu JSON")
    extra = _datoteke_uz(mapa)
    bg_hash = None
    work = d / f"_rad_{g['id']}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    if pozadina:
        if not video:
            shutil.rmtree(work, ignore_errors=True)
            raise Greska(f"grafika {g['id']} s pozadinom treba gotov video")
        _izvuci_pozadinu(video, g, fps, W, H, work / "pozadina.mp4")
        bg_hash = _sha_file(work / "pozadina.mp4")
    key = _sha(tekst, var, [W, H, fps_arg(fps), g["n"], pozadina], bg_hash,
               [[n, f.stat().st_size, int(f.stat().st_mtime)] for n, f in extra], VERZIJA_KOMADA, HF_VERZIJA)
    out = d / f"grafika_{key}{'.mp4' if pozadina else '.mov'}"
    if out.exists() and out.stat().st_size > 0:
        shutil.rmtree(work, ignore_errors=True)
        return out, False
    (work / "fonts").mkdir(exist_ok=True)
    for _, _, f in FONTOVI:
        shutil.copy2(FONTS_DIR / f, work / "fonts" / f)
    for n, f in extra:
        shutil.copy2(f, work / n)
    page = tekst if je_cijela(tekst) else omotaj(tekst, W, H, fps, g["n"], pozadina, var)
    if je_cijela(tekst):  # vlastita kompozicija: varijable i podaci ipak dostupni kao window.SHOFE
        shofe = {"sirina": W, "visina": H, "trajanje": round(g["n"] / float(fps), 4), "fps": float(fps),
                 "varijable": var, "pozadina": pozadina}
        page = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + f"<script>window.SHOFE = {_js_json(shofe)};</script>",
                      page, count=1)
    (work / "index.html").write_text(page, encoding="utf-8")
    tmp = d / ("_" + out.name)
    args = ["render", ".", "-o", str(tmp), "-f", fps_arg(fps), "--quiet", "--no-wait",
            "--frames-cache-dir", "off"]
    if pozadina:
        args += ["--format", "mp4", "-q", "delivery", "--video-frame-format", "png"]
    else:
        args += ["--format", "mov"]
    if ispis:
        print(f"  grafika {g['id']}: HyperFrames renderira {g['n']} sličica"
              f"{' (s pozadinom)' if pozadina else ''} ...")
    r = hf(args, cwd=work)
    if r.returncode != 0 or not tmp.exists():
        raise Greska(f"HyperFrames nije renderirao grafiku {g['id']} (izlazni kod {r.returncode}); "
                     f"HTML je u {work}:\n{_rep(r)}")
    tmp.replace(out)
    shutil.rmtree(work, ignore_errors=True)
    return out, True


def graf(gp, fps, Wo, Ho, W, H):
    """Filteri: komadi grafike (ulazi 1…n) preko gotovog videa (ulaz 0) → [v]."""
    g_, prev = [], "[0:v]"
    for i, (g, _) in enumerate(gp, start=1):
        t0 = g["s"] - POMAK / fps
        sc = f",scale={Wo}:{Ho}" if (Wo, Ho) != (W, H) else ""
        lab = f"[g{i}]"
        g_.append(f"[{i}:v]setpts=PTS-STARTPTS+{_f(t0)}/TB{sc}{lab}")
        en = f"between(t,{_f(t0)},{_f(t0 + g['n'] / fps - 1e-4)})"
        nxt = f"[v{i}]" if i < len(gp) else "[v]"
        g_.append(f"{prev}{lab}overlay=0:0:format=auto:eof_action=repeat:repeatlast=1:enable='{en}'{nxt}")
        prev = nxt
    g_[-1] = g_[-1][:-3] + ",format=yuv420p[v]"
    return g_


def umetni(proj, gx, out, W, H, fps, preset="veryfast", crf=18, ispis=True):
    """Svaka grafika: HyperFrames komad (predmemorija), pa jedan ffmpeg prolaz koji ih položi preko gotovog
    videa `out` (zvuk se samo kopira). Vraća popis linija za ispis."""
    proj, out = Path(proj), Path(out)
    (proj / "_tmp" / "grafika").mkdir(parents=True, exist_ok=True)
    from common import video_info
    info = video_info(out)
    Wo, Ho = info["w"], info["h"]
    gp, novi = [], 0
    for g in gx:
        f, nov = pripremi(proj, g, W, H, fps, video=out, ispis=ispis)
        k = broj_slicica(f)
        if k < g["n"]:
            raise Greska(f"grafika {g['id']}: HyperFrames dao {k} sličica, treba {g['n']}")
        gp.append((g, f))
        novi += nov
    keep = {f.name for _, f in gp}
    for old in (proj / "_tmp" / "grafika").glob("grafika_*.*"):   # komadi maknutih ili promijenjenih grafika
        if old.name not in keep and not _u_manifestu(proj, old.name):
            old.unlink()
    fc = proj / "_tmp" / "graf_grafika.txt"
    fc.write_text(";\n".join(graf(gp, fps, Wo, Ho, W, H)), encoding="utf-8")
    from common import filter_script_args
    tmp = out.with_name(out.stem + "_grafika" + out.suffix)
    ins = []
    for _, f in gp:
        ins += ["-i", f.relative_to(proj).as_posix()]
    cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-i", out.relative_to(proj).as_posix(), *ins,
           *filter_script_args(fc.relative_to(proj).as_posix()), "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-r", fps_arg(fps), "-movflags", "+faststart", tmp.relative_to(proj).as_posix()]
    r = subprocess.run(cmd, cwd=proj, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.exists():
        raise Greska(f"grafika nije umetnuta (ffmpeg, izlazni kod {r.returncode}):\n{r.stderr[-1500:]}")
    tmp.replace(out)
    _zapisi_manifest(proj, out, gp, fps)
    return [f"Grafika: {len(gp)} ({', '.join(g['id'] for g, _ in gp)}; HyperFrames renderirao {novi}, "
            f"{len(gp) - novi} iz predmemorije)"]


def _manifest_path(proj):
    return Path(proj) / "_tmp" / "grafika" / "zadnje.json"


def _zapisi_manifest(proj, out, gp, fps):
    data = {"video": Path(out).name, "fps": float(fps),
            "grafike": [{"id": g["id"], "s": g["s"], "n": g["n"], "komad": f.name,
                         "pozadina": bool(g["p"].get("pozadina"))} for g, f in gp]}
    _manifest_path(proj).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _u_manifestu(proj, name):
    try:
        m = json.loads(_manifest_path(proj).read_text(encoding="utf-8"))
        return any(x["komad"] == name for x in m.get("grafike", []))
    except (OSError, ValueError, KeyError):
        return False


# ---------------------------------------------------------------- jedna sličica (--kadar, pokazi)
def za_sliku(proj, gx, t, W, H, fps):
    """Grafika vidljiva u trenutku t gotovog videa → (komad, indeks sličice) ili (None, poruka).
    Prozirna se renderira odmah ako je nema; ona s pozadinom samo iz zadnjeg rendera."""
    g = next((g for g in gx if g["s"] - 1e-6 <= t < g["s"] + g["n"] / fps - 1e-6), None)
    if not g:
        return None, None
    j = max(0, min(g["n"] - 1, math.floor((t - g["s"]) * fps + POMAK + 1e-6)))
    if g["p"].get("pozadina"):
        try:
            m = json.loads(_manifest_path(proj).read_text(encoding="utf-8"))
            x = next(x for x in m["grafike"] if x["id"] == g["id"] and abs(x["s"] - g["s"]) < 1e-3
                     and x["n"] == g["n"])
            f = Path(proj) / "_tmp" / "grafika" / x["komad"]
            if f.exists():
                return (f, j), None
        except (OSError, ValueError, KeyError, StopIteration):
            pass
        return None, f"grafika {g['id']} (s pozadinom) vidi se na slici tek nakon rendera"
    try:
        f, _ = pripremi(proj, g, W, H, fps)
    except Greska as ex:
        return None, str(ex)
    return (f, j), None


def na_sliku(png, komad, j, cwd):
    """Sličica j komada grafike preko PNG-a (ista veličina) → isti PNG."""
    from PIL import Image
    png = Path(png)
    with Image.open(png) as im:
        w, h = im.size
    tmp = png.with_name("_g_" + png.name)
    cmd = [ffmpeg(), "-y", "-v", "error", "-nostdin", "-i", png.name, "-i", str(Path(komad).resolve()),
           "-filter_complex", f"[1:v]select='eq(n,{j})',setpts=PTS-STARTPTS,scale={w}:{h}[g];"
                              f"[0:v][g]overlay=0:0:format=auto",
           "-frames:v", "1", tmp.name]
    r = subprocess.run(cmd, cwd=png.parent, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0 and tmp.exists():
        tmp.replace(png)
        return True
    return False


# ---------------------------------------------------------------- naredbe
PROBA = """<div class="kartica">
  <div class="mali">Shofe grafika</div>
  <div class="veliki">Čćšžđ <span id="broj">0</span> eura</div>
</div>
<style>
.kartica{position:absolute;left:8%;right:8%;top:30%;padding:4% 5%;border-radius:28px;background:rgba(255,255,255,.94);
 color:#111;box-shadow:0 10px 40px rgba(0,0,0,.35);animation:ulaz .45s cubic-bezier(.2,.9,.3,1.2) both}
.mali{font-weight:600;font-size:calc(var(--sirina)*0.035);color:#FF7A00;text-transform:uppercase;letter-spacing:.06em}
.veliki{font-weight:900;font-size:calc(var(--sirina)*0.085);line-height:1.05}
@keyframes ulaz{from{transform:translateY(40%) scale(.9);opacity:0}to{transform:none;opacity:1}}
</style>
<script>document.getElementById('broj').textContent = (window.SHOFE.varijable.broj || '200');</script>
"""


def cmd_proba(mapa):
    mapa = Path(mapa or ".").resolve()
    mapa.mkdir(parents=True, exist_ok=True)
    g = {"id": "proba", "s": 0.0, "n": 60, "p": {"html": PROBA, "varijable": {"broj": "200"}}}
    import time
    t0 = time.time()
    f, _ = pripremi(mapa, g, 540, 960, 30, ispis=True)
    dst = mapa / "grafika_proba.mp4"
    cmd = [ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x3a6ea5:s=540x960:r=30:d=2", "-i", str(f),
           "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p", "-frames:v", "60", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Probna grafika: {dst} ({time.time() - t0:.1f} s)")


def main():
    ap = argparse.ArgumentParser(description="HTML grafika (HyperFrames)")
    ap.add_argument("naredba", help="instaliraj | provjera | proba")
    ap.add_argument("mapa", nargs="?")
    a = ap.parse_args()
    try:
        if a.naredba == "instaliraj":
            print(instaliraj())
        elif a.naredba == "provjera":
            ok, msg = stanje()
            print(("[OK] " if ok else "[!!] ") + msg)
            sys.exit(0 if ok else 1)
        elif a.naredba == "proba":
            cmd_proba(a.mapa)
        else:
            die(f"nepoznata naredba '{a.naredba}' (instaliraj, provjera, proba)")
    except Greska as ex:
        die(str(ex))
    except subprocess.TimeoutExpired:
        die("HyperFrames predugo radi (prekinuto)")


if __name__ == "__main__":
    main()
