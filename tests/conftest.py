"""Zajedničko za sve testove: naučeni rječnik i ostali korisnikovi podaci idu u privremenu mapu,
nikad u pravi %LOCALAPPDATA%\\Shofe ili ~/.local/share/shofe."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "shofe-montaza" / "scripts"

os.environ["SHOFE_PODACI"] = tempfile.mkdtemp(prefix="shofe_podaci_")


def run_script(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"{script} pao:\n{r.stdout}\n{r.stderr}"
    return r.stdout


@pytest.fixture(scope="session")
def podcast(tmp_path_factory):
    """Probna epizoda podcasta iz make_rezija (zasebni zvuk + široka, kamA, uspravni kamB do 45 s), mapa s
    kvačicama, režija s govornicima iz scenarija, transkript iz razgovor.json, plan stila Podcast.
    Dijele je test_davinci_podcast i test_uspravno (~1 min za napraviti)."""
    pytest.importorskip("cv2")
    sys.path.insert(0, str(ROOT / "tests"))
    import make_rezija as MR
    base = tmp_path_factory.mktemp("podcast čž")
    MR.make(base / "Sunčani4M snimke")
    proj = base / "epizoda"
    run_script("sinkro.py", base / "Sunčani4M snimke", "--out", proj, "--bez-provjere")
    run_script("rezija.py", proj)
    MR.govornici_json(proj)
    raz = json.loads((ROOT / "tests" / "fixtures" / "razgovor.json").read_text(encoding="utf-8"))
    (proj / "transcript.json").write_text(json.dumps({"language": "hr", "model": "mock", "words": raz["words"]},
                                                     ensure_ascii=False), encoding="utf-8")
    run_script("rezija.py", proj)
    run_script("plan.py", proj, "--stil", "podcast")
    return proj
