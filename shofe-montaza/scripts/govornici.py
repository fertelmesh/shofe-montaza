"""Tko govori (diarizacija): lokalno, na procesoru, bez interneta nakon prvog pokretanja.

  python govornici.py shofe_projekt                 → govornici.json (+ govornik uz svaku riječ)
  python govornici.py shofe_projekt --broj 3        ako znaš koliko ljudi govori (točnije)
  python govornici.py shofe_projekt --imena "G1=Marko,G2=Ivan"   samo preimenuj, bez ponovne analize

Prvo pokretanje skida dva mala modela (~36 MB) s GitHuba u mapu modela (Windows:
%LOCALAPPDATA%\\Shofe\\modeli, drugdje ~/.cache/shofe/modeli; ili SHOFE_MODELI).
Motor: sherpa-onnx (Apache-2.0) + pyannote segmentation-3.0 (MIT) + 3D-Speaker CAM++ (Apache-2.0).

Govornici se zovu G1, G2… redom kojim se prvi put jave; imena se mogu upisati (--imena).
transcript.json se ne mijenja: plan.py i analyze.py čitaju govornici.json i svakoj riječi
dodaju "g", a odsječak nikad ne prelazi s jednog govornika na drugog.
"""
import argparse
import datetime as _dt
import hashlib
import os
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from common import die, fmt_time, load_json, save_json, version

SR = 16000
REL = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEG_TAR = "sherpa-onnx-pyannote-segmentation-3-0"
MODELS = {
    # ime datoteke u mapi modela: (url, sha256 preuzete datoteke, licenca)
    "segmentacija.onnx": (f"{REL}/speaker-segmentation-models/{SEG_TAR}.tar.bz2",
                          "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488", "MIT (pyannote)"),
    "glas_campplus.onnx": (f"{REL}/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx",
                           "98daf9bcf1c8abf3db374fec4c27a5eda7c58705bb3f180d057b085a72a88bb5", "Apache-2.0 (3D-Speaker)"),
}
PRAG = 0.5          # prag sličnosti glasova kad broj govornika nije zadan (veći → manje govornika)
MIN_GOVOR = 0.3     # kraći komadi govora se zanemaruju (s)
MIN_PAUZA = 0.5     # kraće pauze istog govornika se spajaju (s)


# ---------------------------------------------------------------- modeli

def models_dir():
    env = os.environ.get("SHOFE_MODELI")
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Shofe" / "modeli"
    return Path.home() / ".cache" / "shofe" / "modeli"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _download(url, dest):
    tmp = dest.with_name(dest.name + ".dio")
    print(f"  skidam {url.rsplit('/', 1)[-1]} ...")
    req = urllib.request.Request(url, headers={"User-Agent": f"shofe/{version()}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def ensure_models(d=None):
    """Vrati (segmentacija, glas) putanje; skine što nedostaje. Kriva kontrolna suma → upozorenje
    (autori su modele već jednom zamijenili novom verzijom), ne prekid."""
    d = Path(d or models_dir())
    d.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (url, digest, _lic) in MODELS.items():
        dest = d / name
        if not dest.exists():
            print(f"Prvo pokretanje: skidam model za prepoznavanje govornika u {d}")
            raw = d / url.rsplit("/", 1)[-1]
            try:
                _download(url, raw)
            except Exception as e:
                die(f"ne mogu skinuti {url}: {e}\nProvjeri internet (treba samo prvi put).")
            if sha256(raw) != digest:
                print(f"  Upozorenje: {raw.name} ima drugu kontrolnu sumu nego što je Shofe provjerio "
                      f"(autor je možda objavio novu verziju). Nastavljam.")
            if raw.name.endswith(".tar.bz2"):
                with tarfile.open(raw, "r:bz2") as t:
                    m = t.getmember(f"{SEG_TAR}/model.onnx")  # int8 je brži, ali lošiji (vidi ODLUKE.md)
                    with t.extractfile(m) as src, open(dest, "wb") as f:
                        shutil.copyfileobj(src, f)
                    lic = t.getmember(f"{SEG_TAR}/LICENSE")
                    with t.extractfile(lic) as src:
                        (d / "segmentacija-LICENSE.txt").write_bytes(src.read())
                raw.unlink()
            else:
                raw.replace(dest)
        out[name] = dest
    return out["segmentacija.onnx"], out["glas_campplus.onnx"]


# ---------------------------------------------------------------- diarizacija

def diarize(samples, n_speakers=None, threshold=PRAG, threads=None, models=None, do_refine=True):
    """samples: mono float32 16 kHz. Vrati [(od, do, indeks_govornika)] po vremenu."""
    try:
        import sherpa_onnx as so
    except ImportError:
        die("sherpa-onnx nije instaliran. Pokreni: python doctor.py --popravi")
    seg, emb = models or ensure_models()
    threads = threads or max(1, min(8, (os.cpu_count() or 2)))
    cfg = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg)), num_threads=threads),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(emb), num_threads=threads),
        clustering=so.FastClusteringConfig(num_clusters=n_speakers or -1, threshold=threshold),
        min_duration_on=MIN_GOVOR, min_duration_off=MIN_PAUZA)
    if not cfg.validate():
        die("postavke za prepoznavanje govornika nisu ispravne (modeli oštećeni? obriši mapu modela)")
    sd = so.OfflineSpeakerDiarization(cfg)
    if len(samples) < SR:  # kraće od 1 s: nema se što dijeliti
        return []
    res = sd.process(samples).sort_by_start_time()
    raw = [(float(s.start), float(s.end), int(s.speaker)) for s in res]
    return refine(samples, raw, emb, threads) if do_refine else raw


def _embedder(model, threads):
    import sherpa_onnx as so
    return so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(model), num_threads=threads))


def _embed(ex, samples, od, do, max_len=12.0):
    import numpy as np
    if do - od > max_len:  # dugi odsječak: sredina je dovoljna i brža
        mid = (od + do) / 2
        od, do = mid - max_len / 2, mid + max_len / 2
    chunk = samples[int(od * SR):int(do * SR)]
    st = ex.create_stream()
    st.accept_waveform(SR, chunk)
    st.input_finished()
    e = np.asarray(ex.compute(st), dtype=np.float32)
    n = np.linalg.norm(e)
    return e / n if n > 0 else e


def refine(samples, raw, emb_model, threads=2, min_len=1.0, margin=0.05, rounds=2):
    """Druga provjera nakon brzog grupiranja sherpa-onnxa (vidi ODLUKE.md): svaki odsječak (≥ 1 s)
    uspoređuje se s prosječnim glasom svakog govornika (bez sebe samog) i prebacuje kad mu je drugi
    govornik jasno bliži. Tako kratko pitanje ne ostane pripisano prethodnom govorniku."""
    import numpy as np
    if len(set(k for *_, k in raw)) < 2:
        return raw
    ex = _embedder(emb_model, threads)
    segs = [list(x) for x in raw]
    embs = [(_embed(ex, samples, s, e) if e - s >= min_len else None) for s, e, _ in segs]
    sums = {}  # zbroj glasova po govorniku, težina = trajanje
    for (s, e, k), v in zip(segs, embs):
        if v is not None:
            sums[k] = sums.get(k, 0) + v * (e - s)
    unit = lambda x: x / (np.linalg.norm(x) or 1.0)
    for _ in range(rounds):
        moved = 0
        for seg, v in zip(segs, embs):
            if v is None:
                continue
            own = seg[2]
            w = v * (seg[1] - seg[0])
            rest = sums[own] - w
            if np.linalg.norm(rest) < 1e-6:  # jedini odsječak tog govornika s glasom
                continue
            sims = {k: float(unit(rest if k == own else c) @ v) for k, c in sums.items()}
            best = max(sims, key=sims.get)
            if best != own and sims[best] - sims[own] > margin:
                sums[own] = rest
                sums[best] = sums[best] + w
                seg[2] = best
                moved += 1
        if not moved:
            break
    return [tuple(x) for x in segs]


def relabel(raw):
    """Indekse modela → G1, G2… redom prvog javljanja. Vrati odsječke s 'govornik'."""
    names = {}
    out = []
    for s, e, k in sorted(raw):
        if k not in names:
            names[k] = f"G{len(names) + 1}"
        out.append({"od": round(s, 2), "do": round(e, 2), "govornik": names[k]})
    return out


def speaker_stats(segs, imena=None):
    tot = {}
    for s in segs:
        tot[s["govornik"]] = tot.get(s["govornik"], 0.0) + s["do"] - s["od"]
    allt = sum(tot.values()) or 1.0
    order = sorted(tot, key=lambda g: int(g[1:]))
    return [{"id": g, "ime": (imena or {}).get(g, ""), "govori_s": round(tot[g], 1),
             "udio": round(tot[g] / allt, 2)} for g in order]


# ---------------------------------------------------------------- riječi

def _overlap_speaker(w, segs):
    best, bo = None, 0.0
    for s in segs:
        if s["od"] >= w["e"]:
            break
        o = min(s["do"], w["e"]) - max(s["od"], w["s"])
        if o > bo:
            best, bo = s["govornik"], o
    if best:
        return best
    # riječ u rupi između odsječaka: najbliži odsječak
    mid = (w["s"] + w["e"]) / 2
    near = min(segs, key=lambda s: 0 if s["od"] <= mid <= s["do"] else min(abs(s["od"] - mid), abs(s["do"] - mid)))
    return near["govornik"]


def assign_words(words, segs, min_run=2, min_dur=0.5):
    """Svakoj riječi dodaj 'g'. Kratki otoci (manje od min_run riječi i kraći od min_dur s)
    unutar govora istog govornika pripisuju se tom govorniku: model zna promašiti granicu za riječ."""
    if not segs:
        return [dict(w) for w in words]
    segs = sorted(segs, key=lambda s: s["od"])
    labs = [_overlap_speaker(w, segs) for w in words]
    # izgladi otoke
    i = 0
    while i < len(labs):
        j = i
        while j + 1 < len(labs) and labs[j + 1] == labs[i]:
            j += 1
        if 0 < i and j < len(labs) - 1 and labs[i - 1] == labs[j + 1] != labs[i]:
            dur = words[j]["e"] - words[i]["s"]
            if j - i + 1 < min_run and dur < min_dur:
                for k in range(i, j + 1):
                    labs[k] = labs[i - 1]
        i = j + 1
    out = []
    for w, g in zip(words, labs):
        w = dict(w)
        w["g"] = g
        out.append(w)
    return out


def load_words(proj):
    """Riječi iz transcript.json; s govornicima ('g') ako postoji govornici.json."""
    proj = Path(proj)
    words = load_json(proj / "transcript.json").get("words") or []
    gp = proj / "govornici.json"
    if words and gp.exists():
        try:
            segs = load_json(gp).get("odsjecci") or []
        except Exception:
            segs = []
        if segs:
            return assign_words(words, segs)
    return words


def speaker_names(proj):
    gp = Path(proj) / "govornici.json"
    if not gp.exists():
        return {}
    try:
        return {g["id"]: g["ime"] for g in load_json(gp).get("govornici", []) if g.get("ime")}
    except Exception:
        return {}


def parse_names(s):
    out = {}
    for part in (s or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().upper()
            if k and not k.startswith("G"):
                k = "G" + k
            out[k] = v.strip()
    return out


# ---------------------------------------------------------------- glavno

def summary_lines(gov, words=None, names=None):
    names = names or {}
    L = [f"Govornika: {len(gov['govornici'])}"]
    for g in gov["govornici"]:
        ime = f" ({g['ime']})" if g.get("ime") else ""
        L.append(f"   {g['id']}{ime}: {g['govori_s']:.0f}s, {g['udio'] * 100:.0f}%")
    if words:
        L.append("")
        cur, start, txt = None, 0.0, []
        for w in words + [{"g": None, "s": 1e9, "w": ""}]:
            if w["g"] != cur:
                if cur:
                    lab = names.get(cur) or cur
                    L.append(f"{fmt_time(start)} {lab}: {' '.join(txt)}")
                cur, start, txt = w["g"], w["s"], []
            txt.append(w["w"])
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--broj", type=int, default=None, help="koliko ljudi govori (ako znaš)")
    ap.add_argument("--prag", type=float, default=PRAG,
                    help=f"sličnost glasova kad broj nije zadan (zadano {PRAG}; veći → manje govornika)")
    ap.add_argument("--imena", default=None, help='npr. "G1=Marko,G2=Ivan"')
    a = ap.parse_args()

    proj = Path(a.projekt)
    gp = proj / "govornici.json"
    names = parse_names(a.imena)
    if a.imena and gp.exists() and a.broj is None:
        gov = load_json(gp)
        for g in gov["govornici"]:
            if g["id"] in names:
                g["ime"] = names[g["id"]]
        save_json(gp, gov)
        print("Imena upisana: " + ", ".join(f"{g['id']}={g['ime']}" for g in gov["govornici"] if g.get("ime")))
        return

    src = proj / "source.mp4"
    if not src.exists():
        die(f"nema {src}. Prvo pokreni prepare.py")
    from transcribe import load_audio

    t0 = time.time()
    models = ensure_models()
    samples = load_audio(src, SR)
    dur = len(samples) / SR
    print(f"Tražim govornike u {fmt_time(dur)} zvuka...")
    raw = diarize(samples, n_speakers=a.broj, threshold=a.prag, models=models)
    segs = relabel(raw)
    old = {}
    if gp.exists():
        try:
            old = {g["id"]: g.get("ime", "") for g in load_json(gp).get("govornici", [])}
        except Exception:
            old = {}
    imena = {**{k: v for k, v in old.items() if v}, **names}
    took = time.time() - t0
    gov = {
        "shofe": version(),
        "napravljeno": _dt.datetime.now().isoformat(timespec="seconds"),
        "izvor": "source.mp4",
        "postavke": {"broj": a.broj, "prag": a.prag, "min_govor": MIN_GOVOR, "min_pauza": MIN_PAUZA,
                     "modeli": {k: v[2] for k, v in MODELS.items()}},
        "trajanje_s": round(took, 1),
        "govornici": speaker_stats(segs, imena),
        "odsjecci": segs,
    }
    save_json(gp, gov)
    words = load_words(proj) if (proj / "transcript.json").exists() else None
    lines = summary_lines(gov, words, imena)
    print("\n".join(lines[:60]))
    if len(lines) > 60:
        print(f"... (još {len(lines) - 60} redaka)")
    print(f"\nGotovo za {took:.0f}s ({dur / max(took, 0.01):.0f}× brže od stvarnog vremena) → {gp}")
    if not words:
        print("Napomena: nema transcript.json; govornici će se pridružiti riječima kad pokreneš transcribe.py.")
    print(f"Sljedeće: python analyze.py {proj}  (odsječci dobivaju govornika)")


if __name__ == "__main__":
    main()
