"""Dekodiranje zvuka za transkripciju vlastitim ffmpegom (bez PyAV-a). Radi bez interneta i modela."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def test_load_audio_mono_16k(tmp_path):
    np = pytest.importorskip("numpy")
    from transcribe import SAMPLE_RATE, load_audio

    src = tmp_path / "mapa s razmakom čćž" / "klip đ.mp4"  # kao na Windowsu
    src.parent.mkdir()
    shutil.copy(FIX / "klip2.mp4", src)
    audio = load_audio(src)
    assert audio.dtype == np.float32 and audio.ndim == 1
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(src)], capture_output=True, text=True).stdout)
    assert abs(len(audio) / SAMPLE_RATE - dur) < 0.2
    assert 0.001 < float(np.abs(audio).mean()) and float(np.abs(audio).max()) <= 1.0  # ima govora, nije prazno


def test_load_audio_bez_zvuka(tmp_path):
    pytest.importorskip("numpy")
    from transcribe import load_audio

    silent = tmp_path / "bez_zvuka.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
                    str(silent)], check=True)
    with pytest.raises(SystemExit):
        load_audio(silent)
