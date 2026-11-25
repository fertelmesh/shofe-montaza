"""Pregled karte videa: jedna lokalna HTML stranica (pregled.html) u mapi projekta.

  python pregled.py shofe_projekt            → shofe_projekt/pregled.html
  python pregled.py shofe_projekt --otvori   (i otvori je u pregledniku)

Čita analiza.json (analyze.py) i source.mp4. Na stranici su: video, vremenska crta
(glasnoća s tišinama, govornici, teme, najjači trenuci, loši kadrovi, rezovi i spojevi),
popis trenutaka i tema, udio govornika i transkript po odsječcima. Klik bilo gdje skače
na to mjesto u videu. Radi bez interneta (sve je u jednoj datoteci; video se čita iz
iste mape). analyze.py je sam napravi nakon analize i nakon --provjeri.
"""
import argparse
import html
import json
import math
import sys
import webbrowser
from pathlib import Path

import numpy as np

from common import die, load_json, version

MAX_TOCAKA = 3000   # najviše stupaca u ovojnici zvuka (60 min → ~1,2 s po stupcu)
TOCAKA_U_S = 10     # za kratke snimke: 10 stupaca u sekundi


# ---------------------------------------------------------------- ovojnica zvuka

def envelope(db, win, duration):
    """Glasnoća po stupcima (0–100) iz razine zvuka u dB po prozorima od `win` s."""
    db = np.asarray(db, np.float32)
    if duration <= 0 or len(db) == 0:
        return {"korak": 0, "v": []}
    n = int(min(MAX_TOCAKA, max(1, math.ceil(duration * TOCAKA_U_S))))
    step = duration / n
    idx = np.minimum((np.arange(len(db)) * win / step).astype(int), n - 1)
    peak = np.full(n, -90.0, np.float32)
    np.maximum.at(peak, idx, db)
    lo = max(float(np.percentile(db, 2)), -60.0)
    hi = float(db.max())
    if hi - lo < 6:
        lo = hi - 6
    v = np.clip((peak - lo) / (hi - lo), 0, 1) * 100
    return {"korak": round(step, 4), "v": [int(round(x)) for x in v]}


def envelope_from_video(src, duration):
    from analyze import SR, WIN, decode_audio, window_db
    if not Path(src).exists():
        return {"korak": 0, "v": []}
    samples = decode_audio(src, SR)
    if samples is None or len(samples) == 0:
        return {"korak": 0, "v": []}
    return envelope(window_db(samples, SR, WIN), WIN, duration)


# ---------------------------------------------------------------- podaci za stranicu

def page_data(proj, an, env):
    proj = Path(proj)
    segs = []
    for s in an.get("odsjecci") or []:
        flags = [f for f in (s.get("glasnoca_oznaka"), s.get("losi_kadar")) if f]
        if s.get("tempo") in ("sporo", "brzo"):
            flags.append(s["tempo"])
        segs.append({"id": s.get("id"), "od": s["od"], "do": s["do"], "tekst": s.get("tekst", ""),
                     "g": s.get("govornik", ""), "oznake": flags})
    gov = []
    for g in an.get("govornici") or []:
        gov.append({"id": g["id"], "ime": g.get("ime") or "", "udio": g.get("udio", 0),
                    "govori_s": g.get("govori_s", 0)})
    video = (proj / "source.mp4").exists()
    return {
        "naziv": proj.resolve().name,
        "shofe": an.get("shofe") or version(),
        "napravljeno": an.get("napravljeno", ""),
        "trajanje": an.get("trajanje") or 0,
        "zvuk": an.get("zvuk") or {},
        "govor": an.get("govor"),
        "govornici": gov,
        "tisine": an.get("tisine") or [],
        "odsjecci": segs,
        "teme": [t for t in an.get("teme") or [] if isinstance(t, dict)],
        "trenuci": [m for m in an.get("trenuci") or [] if isinstance(m, dict)],
        "losi_kadrovi": an.get("losi_kadrovi") or [],
        "promjene_scene": an.get("promjene_scene") or [],
        "spojevi_klipova": an.get("spojevi_klipova") or [],
        "slika": bool(an.get("slika")),
        "ovojnica": env,
        "video": "source.mp4" if video else "",
    }


def embed_json(data):
    """JSON koji se smije staviti unutar <script> (bez zatvaranja oznake)."""
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return s.replace("<", "\\u003c")


def build_html(data):
    title = html.escape(f"Karta videa · {data['naziv']}")
    return (TEMPLATE.replace("__TITLE__", title)
            .replace("__DATA__", embed_json(data)))


def write_pregled(proj, an=None, db=None, win=None):
    """Napiši pregled.html. `db`/`win`: razina zvuka koju je analyze.py već izmjerio (štedi dekodiranje)."""
    proj = Path(proj)
    if an is None:
        p = proj / "analiza.json"
        if not p.exists():
            die("nema analiza.json. Prvo pokreni analyze.py")
        an = load_json(p)
    dur = float(an.get("trajanje") or 0)
    env = envelope(db, win, dur) if db is not None and win else envelope_from_video(proj / "source.mp4", dur)
    out = proj / "pregled.html"
    out.write_text(build_html(page_data(proj, an, env)), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--otvori", action="store_true", help="otvori stranicu u pregledniku")
    a = ap.parse_args()
    out = write_pregled(Path(a.projekt))
    print(f"Pregled: {out}")
    if a.otvori:
        try:
            webbrowser.open(out.resolve().as_uri())
        except Exception as e:  # pregled je napravljen i bez otvaranja
            print(f"Ne mogu otvoriti preglednik ({e}); otvori datoteku ručno.", file=sys.stderr)


# ---------------------------------------------------------------- stranica

TEMPLATE = r"""<!doctype html>
<html lang="hr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f6f5f2; --panel: #ffffff; --ink: #1d1d1b; --muted: #6b6a66; --line: #e3e1dc;
  --wave: #8a99ad; --silence: rgba(120, 120, 120, .16); --accent: #e0661f; --bad: #d23c3c;
  --cut: #4c4c4c; --join: #2f7de1; --play: #e0661f; --hover: rgba(224, 102, 31, .10);
  --chip: #efede8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --panel: #1f1f1d; --ink: #ecebe7; --muted: #9c9a94; --line: #34332f;
    --wave: #7d8ba0; --silence: rgba(200, 200, 200, .10); --cut: #b9b7b0; --hover: rgba(224, 102, 31, .16);
    --chip: #2b2a27;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { padding: 20px 24px 8px; }
h1 { margin: 0; font-size: 22px; font-weight: 700; }
h2 { margin: 0 0 10px; font-size: 15px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.meta { color: var(--muted); font-size: 13px; margin-top: 2px; }
main { padding: 8px 24px 40px; display: grid; gap: 16px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; min-width: 0; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.stat { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; }
.stat b { display: block; font-size: 20px; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 12.5px; }
.top { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }
.top.novideo { grid-template-columns: 1fr; }
video { width: 100%; max-height: 62vh; background: #000; border-radius: 8px; display: block; }
.tl-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.tl-head h2 { margin: 0 auto 0 0; }
button { font: inherit; font-size: 13px; color: var(--ink); background: var(--chip); border: 1px solid var(--line);
  border-radius: 6px; padding: 3px 10px; cursor: pointer; }
button:hover { border-color: var(--accent); }
.tl { display: grid; grid-template-columns: 84px minmax(0, 1fr); }
.tl-labels div { font-size: 12px; color: var(--muted); display: flex; align-items: center; }
.tl-scroll { overflow-x: auto; overflow-y: hidden; position: relative; }
.tl-scroll svg { display: block; cursor: pointer; }
.tl-scroll text { font-size: 11px; fill: var(--ink); pointer-events: none; }
.tl-scroll .axis text { fill: var(--muted); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--muted); margin-top: 8px; }
.legend .lg { display: inline-flex; flex-wrap: wrap; gap: 4px 10px; }
.legend .lg b { font-weight: 600; color: var(--ink); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }
ul.list { list-style: none; margin: 0; padding: 0; }
ul.list li { padding: 7px 6px; border-top: 1px solid var(--line); cursor: pointer; border-radius: 6px; }
ul.list li:first-child { border-top: 0; }
ul.list li:hover { background: var(--hover); }
.t { font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12.5px; white-space: nowrap; }
.chip { display: inline-block; font-size: 11.5px; padding: 0 7px; border-radius: 99px; background: var(--chip); margin: 0 4px; }
.stars { color: var(--accent); letter-spacing: 1px; font-size: 12px; }
.muted { color: var(--muted); }
.empty { color: var(--muted); font-size: 13.5px; padding: 4px 0; }
.bar { height: 8px; background: var(--chip); border-radius: 4px; overflow: hidden; margin: 3px 0 8px; }
.bar > div { height: 100%; }
.warn li { cursor: pointer; }
.tr-head { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.tr-head h2 { margin: 0 auto 0 0; }
input[type=search] { font: inherit; font-size: 13.5px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--bg); color: var(--ink); min-width: 220px; }
.transcript { max-height: 60vh; overflow-y: auto; }
.seg { display: grid; grid-template-columns: 44px 62px minmax(0, 1fr); gap: 8px; padding: 4px 6px; border-radius: 6px; cursor: pointer; align-items: baseline; }
.seg:hover { background: var(--hover); }
.seg.now { background: var(--hover); box-shadow: inset 3px 0 0 var(--accent); }
.seg .n { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.seg .who { font-weight: 600; font-size: 13px; }
.flag { font-size: 11px; color: var(--bad); margin-left: 6px; white-space: nowrap; }
@media (max-width: 900px) {
  header, main { padding-left: 12px; padding-right: 12px; }
  .top, .cols { grid-template-columns: 1fr; }
  .seg { grid-template-columns: 36px 54px minmax(0, 1fr); }
  .tl { grid-template-columns: 66px minmax(0, 1fr); }
}
</style>
</head>
<body>
<header>
  <h1 id="naslov"></h1>
  <div class="meta" id="meta"></div>
</header>
<main>
  <section class="stats" id="stats"></section>
  <section class="top" id="top">
    <div class="panel" id="videoPanel"><video id="video" controls preload="metadata"></video></div>
    <div class="panel"><h2>Najjači trenuci</h2><ul class="list" id="trenuci"></ul></div>
  </section>
  <section class="panel">
    <div class="tl-head">
      <h2>Vremenska crta</h2>
      <span class="t" id="zoomInfo"></span>
      <button id="zoomOut" title="Smanji">−</button>
      <button id="zoomIn" title="Povećaj">+</button>
      <button id="zoomFit">Cijelo</button>
    </div>
    <div class="tl">
      <div class="tl-labels" id="tlLabels"></div>
      <div class="tl-scroll" id="tlScroll"><svg id="tl" xmlns="http://www.w3.org/2000/svg"></svg></div>
    </div>
    <div class="legend" id="legend"></div>
  </section>
  <section class="cols">
    <div class="panel"><h2>Teme</h2><ul class="list" id="teme"></ul></div>
    <div class="panel">
      <h2>Govornici</h2><div id="govornici"></div>
      <h2 style="margin-top:14px">Upozorenja</h2><ul class="list warn" id="upozorenja"></ul>
    </div>
  </section>
  <section class="panel">
    <div class="tr-head"><h2>Transkript po odsječcima</h2>
      <input type="search" id="trazi" placeholder="Traži riječ…"></div>
    <div class="transcript" id="transkript"></div>
  </section>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const DUR = Math.max(D.trajanje || 0, 0.01);
const SPK = ["#2f7de1", "#8a5cd6", "#16a3a3", "#9a7b4f", "#5d8f2b", "#c2549d", "#5a6b85", "#b07c00"];
const VRSTA = {hook: "#e0661f", poanta: "#d6a100", smijeh: "#e8569a", emocija: "#b83a3a",
  savjet: "#2f9e5b", citat: "#7d55c7", akcija: "#1f8fb3", ostalo: "#8a8a8a"};
const VRSTA_HR = {hook: "hook", poanta: "poanta", smijeh: "smijeh", emocija: "emocija",
  savjet: "savjet", citat: "citat", akcija: "akcija", ostalo: "ostalo"};
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

function fmt(t) {
  t = Math.max(0, t || 0);
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = Math.floor(t % 60);
  const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
function el(tag, attrs, text) {
  const e = document.createElement(tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
}
function sv(tag, attrs, title) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (title) { const t = document.createElementNS(NS, "title"); t.textContent = title; e.appendChild(t); }
  return e;
}
const spkIndex = {};
(D.govornici || []).forEach((g, i) => { spkIndex[g.id] = i; });
function spkColor(id) { return SPK[(id in spkIndex ? spkIndex[id] : 0) % SPK.length]; }
function spkName(id) {
  const g = (D.govornici || []).find((x) => x.id === id);
  return g && g.ime ? g.ime : id;
}

// ------------------------------------------------------------ video i skakanje
const video = $("video");
if (D.video) { video.src = D.video; } else { $("videoPanel").remove(); $("top").classList.add("novideo"); }
let videoOk = !!D.video;
video.addEventListener("error", () => { videoOk = false; });
function seek(t) {
  t = Math.max(0, Math.min(DUR, t));
  if (videoOk) {
    video.currentTime = t;
    video.scrollIntoView({block: "nearest", behavior: "smooth"});
  }
  setNow(t, true);
}

// ------------------------------------------------------------ zaglavlje i brojke
$("naslov").textContent = "Karta videa · " + D.naziv;
$("meta").textContent = `Trajanje ${fmt(D.trajanje)} · Shofe ${D.shofe}` +
  (D.napravljeno ? ` · analiza ${D.napravljeno.replace("T", " ").slice(0, 16)}` : "");
function stat(big, small) {
  const d = el("div", {class: "stat"});
  d.appendChild(el("b", {}, big)); d.appendChild(el("span", {}, small)); $("stats").appendChild(d);
}
stat(fmt(D.trajanje), "trajanje");
if (D.zvuk && D.zvuk.glasnoca_lufs != null) stat(`${D.zvuk.glasnoca_lufs} LUFS`, D.zvuk.napomena || "glasnoća");
if (D.govor) stat(`${Math.round(D.govor.udio_govora * 100)} %`, `govora · ${D.govor.slogova_u_s} slogova/s (${D.govor.tempo})`);
const tisUk = D.tisine.reduce((a, t) => a + t.trajanje, 0);
stat(String(D.tisine.length), `tišina · ukupno ${tisUk.toFixed(1)} s`);
if (D.govornici.length) stat(String(D.govornici.length), D.govornici.length === 1 ? "govornik" : "govornika");
if (D.slika) stat(String(D.losi_kadrovi.length), "loših kadrova");
stat(String(D.teme.length), `tema · ${D.trenuci.length} trenutaka`);

// ------------------------------------------------------------ vremenska crta
const LANES = [["zvuk", "Zvuk", 58]];
if (D.govornici.length) LANES.push(["gov", "Govornici", 22]);
LANES.push(["teme", "Teme", 30], ["trenuci", "Trenuci", 28]);
if (D.slika) LANES.push(["slika", "Slika", 20]);
LANES.push(["os", "", 20]);
const GAP = 6;
let y = 0; const LY = {};
for (const [k, label, h] of LANES) {
  LY[k] = [y, h];
  const d = el("div", {}, label); d.style.height = h + "px"; d.style.marginBottom = GAP + "px";
  $("tlLabels").appendChild(d);
  y += h + GAP;
}
const H = y - GAP;
const scroller = $("tlScroll"), svg = $("tl");
let pps = 0;  // piksela po sekundi
function fitPps() { return Math.max(scroller.clientWidth - 2, 200) / DUR; }

function niceStep(secPerPx) {
  const want = secPerPx * 90;
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  return steps.find((s) => s >= want) || 3600;
}
let playhead = null;
function draw() {
  const W = Math.max(Math.round(DUR * pps), 10);
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const X = (t) => t * pps;
  const css = getComputedStyle(document.documentElement);
  const c = (v) => css.getPropertyValue(v).trim();

  // zvuk: tišine + ovojnica
  const [zy, zh] = LY.zvuk;
  for (const t of D.tisine) svg.appendChild(sv("rect", {x: X(t.od), y: zy, width: Math.max(X(t.do) - X(t.od), 1), height: zh,
    fill: c("--silence")}, `tišina ${fmt(t.od)}–${fmt(t.do)} (${t.trajanje.toFixed(1)} s)`));
  const env = D.ovojnica || {v: []};
  if (env.v.length) {
    const mid = zy + zh / 2; let top = "", bot = "";
    env.v.forEach((v, i) => {
      const x = X((i + 0.5) * env.korak).toFixed(1), a = (v / 100) * (zh / 2 - 1);
      top += `${i ? "L" : "M"}${x},${(mid - a).toFixed(1)}`;
      bot = `L${x},${(mid + a).toFixed(1)}` + bot;
    });
    svg.appendChild(sv("path", {d: top + bot + "Z", fill: c("--wave")}));
  } else {
    const tx = sv("text", {x: 6, y: zy + zh / 2 + 4}); tx.textContent = "(nema zvuka za prikaz)"; svg.appendChild(tx);
  }
  // govornici
  if (LY.gov) {
    const [gy, gh] = LY.gov;
    for (const s of D.odsjecci) if (s.g) svg.appendChild(sv("rect", {x: X(s.od), y: gy, width: Math.max(X(s.do) - X(s.od), 1),
      height: gh, rx: 2, fill: spkColor(s.g), "data-t": s.od}, `${spkName(s.g)} ${fmt(s.od)}: ${s.tekst}`));
  }
  // teme
  const [ty, th] = LY.teme;
  D.teme.forEach((t, i) => {
    const w = Math.max(X(t.do) - X(t.od) - 1, 1);
    svg.appendChild(sv("rect", {x: X(t.od), y: ty, width: w, height: th, rx: 4,
      fill: i % 2 ? c("--chip") : c("--hover"), stroke: c("--line"), "data-t": t.od},
      `${t.naslov} (${fmt(t.od)}–${fmt(t.do)})${t.sazetak ? "\n" + t.sazetak : ""}`));
    if (w > 40) {
      const cp = sv("clipPath", {id: "tc" + i}); cp.appendChild(sv("rect", {x: X(t.od), y: ty, width: w - 6, height: th}));
      svg.appendChild(cp);
      const tx = sv("text", {x: X(t.od) + 6, y: ty + th / 2 + 4, "clip-path": `url(#tc${i})`}); tx.textContent = t.naslov;
      svg.appendChild(tx);
    }
  });
  if (!D.teme.length) { const tx = sv("text", {x: 6, y: ty + th / 2 + 4}); tx.textContent = "Claude još nije upisao teme"; tx.style.fill = c("--muted"); svg.appendChild(tx); }
  // trenuci
  const [my, mh] = LY.trenuci;
  for (const m of D.trenuci) {
    const col = VRSTA[m.vrsta] || VRSTA.ostalo, oc = m.ocjena || 3;
    svg.appendChild(sv("rect", {x: X(m.od), y: my + mh - 5, width: Math.max(X(m.do) - X(m.od), 2), height: 4, fill: col, opacity: .55}));
    const r = 4 + oc * 1.3;
    svg.appendChild(sv("circle", {cx: X(m.od), cy: my + mh - 5 - r, r: r, fill: col, stroke: c("--panel"), "stroke-width": 1.5, "data-t": m.od},
      `${VRSTA_HR[m.vrsta] || m.vrsta} ${"★".repeat(Math.round(oc))} ${fmt(m.od)}–${fmt(m.do)}\n${m.opis || ""}`));
  }
  if (!D.trenuci.length) { const tx = sv("text", {x: 6, y: my + mh / 2 + 4}); tx.textContent = "Claude još nije upisao trenutke"; tx.style.fill = c("--muted"); svg.appendChild(tx); }
  // slika
  if (LY.slika) {
    const [sy, sh] = LY.slika;
    svg.appendChild(sv("rect", {x: 0, y: sy + sh / 2 - 1, width: W, height: 2, fill: c("--line")}));
    for (const b of D.losi_kadrovi) svg.appendChild(sv("rect", {x: X(b.od), y: sy + 2, width: Math.max(X(b.do) - X(b.od), 2), height: sh - 4, rx: 2,
      fill: c("--bad"), "data-t": b.od}, `${b.razlog} ${fmt(b.od)}–${fmt(b.do)}`));
    for (const t of D.promjene_scene) svg.appendChild(sv("rect", {x: X(t) - 0.75, y: sy, width: 1.5, height: sh, fill: c("--cut"), "data-t": t}, `rez ${fmt(t)}`));
    for (const t of D.spojevi_klipova) svg.appendChild(sv("rect", {x: X(t) - 1, y: sy - 2, width: 2, height: sh + 4, fill: c("--join"), "data-t": t}, `spoj klipova ${fmt(t)}`));
  }
  // os
  const [ay] = LY.os, step = niceStep(1 / pps), g = sv("g", {class: "axis"});
  for (let t = 0; t <= DUR + 1e-6; t += step) {
    g.appendChild(sv("rect", {x: X(t), y: ay, width: 1, height: 5, fill: c("--muted")}));
    const tx = sv("text", {x: X(t) + 3, y: ay + 15}); tx.textContent = fmt(t); g.appendChild(tx);
  }
  svg.appendChild(g);
  playhead = sv("rect", {x: 0, y: 0, width: 2, height: H, fill: c("--play"), "pointer-events": "none"});
  svg.appendChild(playhead);
  setNow(curT, false);
  $("zoomInfo").textContent = fit ? "" : `${Math.round(scroller.clientWidth / pps)} s na ekranu`;
}
function zoom(f) {
  const center = (scroller.scrollLeft + scroller.clientWidth / 2) / pps;
  pps = Math.min(Math.max(pps * f, fitPps()), 200);
  fit = pps <= fitPps() + 1e-9;
  draw();
  scroller.scrollLeft = center * pps - scroller.clientWidth / 2;
}
$("zoomIn").onclick = () => zoom(2);
$("zoomOut").onclick = () => zoom(0.5);
$("zoomFit").onclick = () => { pps = fitPps(); fit = true; draw(); };
scroller.addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.25 : 0.8); } }, {passive: false});
svg.addEventListener("click", (e) => {
  const t = e.target.getAttribute && e.target.getAttribute("data-t");
  if (t !== null && t !== undefined && t !== "") { seek(parseFloat(t)); return; }
  const r = svg.getBoundingClientRect();
  seek((e.clientX - r.left) / pps);
});
let lastW = 0, fit = true;
new ResizeObserver(() => {
  const w = scroller.clientWidth; if (w === lastW) return;
  lastW = w; if (fit || pps < fitPps()) pps = fitPps(); draw();
}).observe(scroller);

// legenda
let legGroup = null;
function group(name) { legGroup = el("span", {class: "lg"}); legGroup.appendChild(el("b", {}, name + ":")); $("legend").appendChild(legGroup); }
function leg(color, text) { const s = el("span"); const i = el("i"); i.style.background = color; s.appendChild(i); s.appendChild(document.createTextNode(text)); legGroup.appendChild(s); }
group("Zvuk"); leg("var(--wave)", "glasnoća"); leg("var(--silence)", "tišina");
if (D.govornici.length) { group("Govornici"); for (const g of D.govornici) leg(spkColor(g.id), spkName(g.id)); }
const vrsteUsed = [...new Set(D.trenuci.map((m) => m.vrsta))];
if (vrsteUsed.length) { group("Trenuci"); for (const v of vrsteUsed) leg(VRSTA[v] || VRSTA.ostalo, VRSTA_HR[v] || v); }
if (D.slika) { group("Slika"); leg("var(--bad)", "loš kadar"); leg("var(--cut)", "rez"); if (D.spojevi_klipova.length) leg("var(--join)", "spoj klipova"); }

// ------------------------------------------------------------ popisi
function li(parent, t, build) {
  const x = el("li"); build(x); x.addEventListener("click", () => seek(t)); parent.appendChild(x); return x;
}
const tren = [...D.trenuci].sort((a, b) => (b.ocjena || 0) - (a.ocjena || 0) || a.od - b.od);
if (!tren.length) $("trenuci").appendChild(el("li", {class: "empty"}, "Claude još nije upisao najjače trenutke. Reci mu: „upiši teme i najjače trenutke“."));
for (const m of tren) li($("trenuci"), m.od, (x) => {
  x.appendChild(el("span", {class: "t"}, `${fmt(m.od)}–${fmt(m.do)}`));
  const ch = el("span", {class: "chip"}, VRSTA_HR[m.vrsta] || m.vrsta); ch.style.color = VRSTA[m.vrsta] || ""; x.appendChild(ch);
  const oc = Math.round(m.ocjena || 0); if (oc) x.appendChild(el("span", {class: "stars"}, "★".repeat(oc) + "☆".repeat(5 - oc)));
  x.appendChild(el("div", {}, m.opis || ""));
});
if (!D.teme.length) $("teme").appendChild(el("li", {class: "empty"}, "Još nema tema."));
for (const t of D.teme) li($("teme"), t.od, (x) => {
  x.appendChild(el("span", {class: "t"}, `${fmt(t.od)}–${fmt(t.do)} `));
  x.appendChild(el("b", {}, t.naslov || ""));
  if (t.sazetak) x.appendChild(el("div", {class: "muted"}, t.sazetak));
});
if (!D.govornici.length) $("govornici").appendChild(el("div", {class: "empty"}, "Jedan govornik ili govornici nisu analizirani (govornici.py)."));
for (const g of D.govornici) {
  const row = el("div"); row.appendChild(el("b", {}, spkName(g.id)));
  row.appendChild(el("span", {class: "muted"}, `  ${Math.round(g.udio * 100)} % · ${fmt(g.govori_s)}`));
  const bar = el("div", {class: "bar"}), fill = el("div"); fill.style.width = (g.udio * 100) + "%"; fill.style.background = spkColor(g.id);
  bar.appendChild(fill); row.appendChild(bar); $("govornici").appendChild(row);
}
const warns = [];
if (D.zvuk && D.zvuk.napomena && !/u redu/i.test(D.zvuk.napomena)) warns.push([0, `Zvuk: ${D.zvuk.napomena}`]);
for (const b of D.losi_kadrovi) warns.push([b.od, `${fmt(b.od)}–${fmt(b.do)} ${b.razlog}`]);
for (const s of D.odsjecci) if (s.oznake.includes("tiho")) warns.push([s.od, `${fmt(s.od)} #${s.id} tiho (mikrofon?)`]);
for (const t of [...D.tisine].sort((a, b) => b.trajanje - a.trajanje).slice(0, 3)) if (t.trajanje >= 2) warns.push([t.od, `${fmt(t.od)} duga tišina ${t.trajanje.toFixed(1)} s`]);
if (!warns.length) $("upozorenja").appendChild(el("li", {class: "empty"}, "Nema upozorenja."));
for (const [t, txt] of warns.slice(0, 40)) li($("upozorenja"), t, (x) => x.appendChild(el("span", {}, txt)));

// transkript
const rows = [];
for (const s of D.odsjecci) {
  const r = el("div", {class: "seg"});
  r.appendChild(el("span", {class: "n"}, "#" + s.id));
  r.appendChild(el("span", {class: "t"}, fmt(s.od)));
  const body = el("span");
  if (s.g) { const w = el("span", {class: "who"}, spkName(s.g) + ": "); w.style.color = spkColor(s.g); body.appendChild(w); }
  body.appendChild(document.createTextNode(s.tekst || "(bez teksta)"));
  for (const f of s.oznake) body.appendChild(el("span", {class: "flag"}, f));
  r.appendChild(body);
  r.addEventListener("click", () => seek(s.od));
  $("transkript").appendChild(r); rows.push([s, r]);
}
if (!rows.length) $("transkript").appendChild(el("div", {class: "empty"}, "Nema transkripta (pokreni transcribe.py pa analyze.py)."));
$("trazi").addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  for (const [s, r] of rows) r.style.display = !q || (s.tekst || "").toLowerCase().includes(q) ? "" : "none";
});

// ------------------------------------------------------------ trenutno vrijeme
let curT = 0, curRow = null;
function setNow(t, follow) {
  curT = t;
  if (playhead) playhead.setAttribute("x", t * pps - 1);
  if (pps && follow !== false) {
    const x = t * pps;
    if (x < scroller.scrollLeft || x > scroller.scrollLeft + scroller.clientWidth - 20) scroller.scrollLeft = x - scroller.clientWidth * 0.2;
  }
  let hit = null;
  for (const [s, r] of rows) { if (s.od > t + 0.15) break; hit = r; }
  if (hit !== curRow) {
    if (curRow) curRow.classList.remove("now");
    if (hit) {
      hit.classList.add("now");
      const box = $("transkript"), top = hit.offsetTop - box.offsetTop;
      if (top < box.scrollTop || top > box.scrollTop + box.clientHeight - 30) box.scrollTop = top - 40;
    }
    curRow = hit;
  }
}
video.addEventListener("timeupdate", () => setNow(video.currentTime, !video.paused));
pps = fitPps(); lastW = scroller.clientWidth; draw();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
