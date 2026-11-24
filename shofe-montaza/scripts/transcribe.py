"""Korak 2: lokalna transkripcija (faster-whisper) s vremenom svake riječi.

Prvo pokretanje skida model (~1,6 GB za large-v3-turbo), poslije radi bez interneta.

  python transcribe.py shofe_projekt
  python transcribe.py shofe_projekt --model medium      (brže, malo lošije)
"""
import argparse
import time
from pathlib import Path

from common import SKILL_DIR, die, fmt_time, save_json


def vocabulary_prompt():
    p = SKILL_DIR / "rjecnik.txt"
    if not p.exists():
        return None
    words = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return ", ".join(words) + "." if words else None


def load_model(name, device):
    from faster_whisper import WhisperModel

    if device in ("auto", "cuda"):
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                return WhisperModel(name, device="cuda", compute_type="float16"), "cuda"
        except Exception as e:
            if device == "cuda":
                print(f"CUDA ne radi ({e}), prelazim na procesor.")
    return WhisperModel(name, device="cpu", compute_type="int8"), "cpu"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("projekt")
    ap.add_argument("--model", default="large-v3-turbo", help="large-v3-turbo | large-v3 | medium | small")
    ap.add_argument("--jezik", default="hr", help="hr | sr | bs | en ... ili auto")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--prompt", default=None, help="imena i pojmovi za bolji pravopis (inače rjecnik.txt)")
    a = ap.parse_args()

    proj = Path(a.projekt)
    src = proj / "source.mp4"
    if not src.exists():
        die(f"nema {src}. Prvo pokreni prepare.py")
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        die("faster-whisper nije instaliran. Pokreni: python doctor.py --popravi")

    t0 = time.time()
    model, dev = load_model(a.model, a.device)
    print(f"Model {a.model} na {dev} učitan ({time.time() - t0:.0f}s). Transkribiram...")
    segs, info = model.transcribe(
        str(src),
        language=None if a.jezik == "auto" else a.jezik,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        condition_on_previous_text=False,
        initial_prompt=a.prompt or vocabulary_prompt(),
        beam_size=5,
    )
    words = []
    for s in segs:
        for w in s.words or []:
            txt = w.word.strip()
            if txt:
                words.append({"w": txt, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 2)})
        print(f"  {fmt_time(s.start)}  {s.text.strip()}")
    save_json(proj / "transcript.json", {"language": info.language, "model": a.model, "words": words})
    print(f"\n{len(words)} riječi za {time.time() - t0:.0f}s → {proj / 'transcript.json'}")
    print(f"Sljedeće: python plan.py {proj}")


if __name__ == "__main__":
    main()
