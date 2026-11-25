"""Dimni test prave transkripcije (faster-whisper, model tiny). Preskače se bez interneta/modela.

  SHOFE_WHISPER_TEST=1 python -m pytest tests/test_transcribe_smoke.py -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"
FIX = ROOT / "tests" / "fixtures"


@pytest.mark.skipif(os.environ.get("SHOFE_WHISPER_TEST") != "1", reason="postavi SHOFE_WHISPER_TEST=1")
def test_transcribe_tiny(tmp_path):
    import faster_whisper  # noqa: F401  (sa SHOFE_WHISPER_TEST=1 mora biti instaliran, ne preskače se)
    clips = tmp_path / "k"
    clips.mkdir()
    shutil.copy(FIX / "klip2.mp4", clips / "klip2.mp4")
    proj = tmp_path / "p"
    for cmd in (["prepare.py", clips, "--out", proj], ["transcribe.py", proj, "--model", "tiny"]):
        r = subprocess.run([sys.executable, str(SCRIPTS / cmd[0]), *map(str, cmd[1:])], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert r.returncode == 0, r.stderr
    words = json.loads((proj / "transcript.json").read_text(encoding="utf-8"))["words"]
    assert len(words) >= 5
