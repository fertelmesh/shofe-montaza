"""Probni reel za prijedlog efekata (M5.3): savjet za čišćenje klime u 10 rečenica, svaka sa znakom za neko
pravilo (predstavljanje, nabrajanje, naglasak, iznenađenje, prošlost, brojka, otkrivanje), stanka 0,9 s između
rečenica (plan je izreže, pa je ispred svake rečenice rez). Slika: make_efekti_klip (nacrtana osoba).

make_projekt(base, scripts, stil) → projekt s transkriptom i edit.json (bez titlova, bez zuma stila).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_efekti_klip as MK  # noqa: E402

RECENICE = [
    "Bok, ja sam Marko iz Kutine.",
    "Danas vam pokazujem kako očistiti klimu.",
    "Prvo, skinite masku i filtere.",
    "Najvažnije je da isključite struju prije svega.",
    "Čekaj, vidi koliko je ovo prljavo!",
    "Nekad smo to radili bez ikakve opreme.",
    "Drugi korak, isperite filtere vodom.",
    "Tako uštedite i do 200 eura godišnje.",
    "I gotovo, klima je kao nova.",
    "Pratite za još savjeta.",
]
KORAK, STANKA = 0.36, 0.9


def rijeci():
    words, t = [], 0.3
    for r in RECENICE:
        for w in r.split():
            words.append({"w": w, "s": round(t, 3), "e": round(t + 0.30, 3)})
            t += KORAK
        t += STANKA
    return words, t


def make_projekt(base, scripts, stil="suncani", ime="projekt predlozi"):
    base = Path(base)
    clips = base / "klipovi"
    clips.mkdir(parents=True, exist_ok=True)
    words, dur = rijeci()
    MK.POMAK = 0          # lice miruje (snimka je dulja od 8 s probnog klipa)
    MK.make(clips / "savjet.mp4", dur=round(dur + 0.5, 1))
    proj = base / ime
    py = sys.executable
    subprocess.run([py, str(Path(scripts) / "prepare.py"), str(clips), "--out", str(proj)], check=True,
                   capture_output=True)
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": words},
                                                     ensure_ascii=False), encoding="utf-8")
    subprocess.run([py, str(Path(scripts) / "plan.py"), str(proj), "--stil", stil], check=True, capture_output=True)
    edit = json.loads((proj / "edit.json").read_text(encoding="utf-8"))
    edit["zoom"] = "nema"
    edit["titlovi"] = False
    edit["hook"] = ""
    edit["glazba"] = None
    (proj / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=1), encoding="utf-8")
    return proj
