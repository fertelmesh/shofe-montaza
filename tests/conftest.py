"""Zajedničko za sve testove: naučeni rječnik i ostali korisnikovi podaci idu u privremenu mapu,
nikad u pravi %LOCALAPPDATA%\\Shofe ili ~/.local/share/shofe."""
import os
import tempfile

os.environ["SHOFE_PODACI"] = tempfile.mkdtemp(prefix="shofe_podaci_")
