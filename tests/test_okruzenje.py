"""Testovi okruženja i Windows sitnica: verzija ffmpega, concat lista, doctor.py."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from common import concat_line, filter_script_args, parse_ffmpeg_major  # noqa: E402


@pytest.mark.parametrize("text,major", [
    ("ffmpeg version 7.1-full_build-www.gyan.dev Copyright (c) 2000-2024", 7),
    ("ffmpeg version 8.0-essentials_build-www.gyan.dev", 8),
    ("ffmpeg version n6.1.1 Copyright", 6),
    ("ffmpeg version 6.1.1-3ubuntu5 Copyright", 6),
    ("ffmpeg version 2025-01-27-git-959b799c8d-full_build-www.gyan.dev\nlibavfilter    10.  9.100", 7),
    ("ffmpeg version N-118448-g1234abcd\nlibavfilter    11.  4.100", 8),
    ("nešto čudno", 6),
])
def test_parse_ffmpeg_major(text, major):
    assert parse_ffmpeg_major(text) == major


def test_filter_script_args_shape():
    args = filter_script_args("graf.txt")
    assert args[-1] == "graf.txt" and args[0] in ("-/filter_complex", "-filter_complex_script")


def test_concat_line_apostrof(tmp_path):
    line = concat_line(tmp_path / "Markov's klip.mp4")
    assert line.startswith("file '") and line.endswith("'\n")
    assert "Markov'\\''s klip.mp4" in line
    assert "\\" not in line.replace("'\\''", "")  # samo kose crte naprijed, i na Windowsu


def test_doctor_ffmpeg_ok():
    r = subprocess.run([sys.executable, str(SCRIPTS / "doctor.py")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout)
    assert "[OK] ffmpeg" in r.stdout, r.stdout + r.stderr
    assert "[OK] fontovi" in r.stdout and "[OK] stilovi" in r.stdout
