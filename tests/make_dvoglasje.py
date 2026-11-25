"""Generira probni razgovor sa sintetskim glasovima (espeak-ng) i poznatim govornicima.

  python tests/make_dvoglasje.py   (iz korijena repozitorija; treba espeak-ng i ffmpeg)
Piše tests/fixtures/razgovor.m4a (mono 16 kHz) i tests/fixtures/razgovor.json:
  recenice: [{g, od, do, tekst}] stvarni govornik svake rečenice
  words:    riječi s procijenjenim vremenima (kao transcript.json), za test bez whispera
Govornici: A muški (hr), B ženski (hr+f3), C drugi muški glas (hr+edward, sporiji; glasovi su različiti koliko i kod stvarnih ljudi: sličnost glasa A i C 0,4, A i A pri drugoj brzini 0,98).
"""
import json
import subprocess
import tempfile
import wave
from pathlib import Path

VOICES = {"A": ["-v", "hr", "-p", "35", "-s", "150"],
          "B": ["-v", "hr+f3", "-p", "70", "-s", "165"],
          "C": ["-v", "hr+edward", "-p", "20", "-s", "140"]}
LINES = [
    ("A", "Bok svima, dobrodošli u novu epizodu podcasta Sunčani četiri M."),
    ("B", "Hvala na pozivu, drago mi je što sam danas ovdje s vama."),
    ("A", "Pričaj nam malo kako je počela tvoja priča s glazbom."),
    ("B", "Počelo je u garaži, svirali smo svaki vikend do kasno u noć."),
    ("C", "Ja sam tada svirao bubnjeve, a susjedi baš i nisu bili oduševljeni."),
    ("A", "I onda ste odlučili snimiti prvi album?"),
    ("B", "Da, ali trebalo nam je skoro dvije godine da ga završimo."),
    ("C", "Točno tako."),
    ("A", "To je dugo. Što je bilo najteže u cijelom tom procesu?"),
    ("C", "Najteže je bilo pronaći vrijeme, jer smo svi radili druge poslove."),
    ("B", "I novac, studio u Zagrebu nije bio jeftin."),
    ("A", "Razumijem. Hajde onda zasvirajte nešto za nas u autu."),
    ("B", "Može, ovo je pjesma o Kutini i ljetu na Moslavini."),
]
GAP = 0.35


def wav_dur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def main():
    out = Path(__file__).resolve().parent / "fixtures"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        sil = td / "sil.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                        "-t", str(GAP), str(sil)], check=True)
        parts, rec, words, t = [sil], [], [], GAP
        for i, (g, txt) in enumerate(LINES):
            f = td / f"p{i}.wav"
            subprocess.run(["espeak-ng", *VOICES[g], "-w", str(f), txt], check=True)
            d = wav_dur(f)
            rec.append({"g": g, "od": round(t, 3), "do": round(t + d, 3), "tekst": txt})
            toks = txt.split()
            tot = sum(len(x) for x in toks)
            a0, a1, acc = t + 0.08, t + d - 0.12, 0
            for x in toks:
                s = a0 + (a1 - a0) * acc / tot
                acc += len(x)
                e = a0 + (a1 - a0) * acc / tot
                words.append({"w": x, "s": round(s, 3), "e": round(e - 0.03, 3), "p": 0.95})
            parts += [f, sil]
            t += d + GAP
        lst = td / "l.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-ar", "16000", "-ac", "1", "-c:a", "aac", "-b:a", "48k",
                        str(out / "razgovor.m4a")], check=True)
    (out / "razgovor.json").write_text(json.dumps({"trajanje": round(t, 3), "recenice": rec, "words": words},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{t:.1f}s, {len(rec)} rečenica, {len(words)} riječi")


if __name__ == "__main__":
    main()
