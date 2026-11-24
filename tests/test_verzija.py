"""Verzija, requirements.txt proizvoda i instalacijska skripta."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "shofe-montaza"


def test_version_format():
    v = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), v


def test_doctor_prints_version():
    r = subprocess.run([sys.executable, str(SKILL / "scripts" / "doctor.py"), "--verzija"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    v = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
    assert f"Shofe {v}" in r.stdout


def test_requirements_proizvoda():
    reqs = [l.split("#")[0].strip() for l in (SKILL / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    names = {re.split(r"[<>=!~ ]", r)[0].lower() for r in reqs if r}
    assert {"faster-whisper", "numpy"} <= names
    # korijenski requirements.txt (CI, razvoj) mora pokazivati na isti popis
    assert "shofe-montaza/requirements.txt" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_install_ps1_koristi_requirements():
    raw = (SKILL / "install.ps1").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "Windows PowerShell 5.1 treba BOM za č/ć/ž"
    text = raw.decode("utf-8-sig")
    assert "requirements.txt" in text
    assert "exit $doctor" in text
