import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture()
def base(monkeypatch, tmp_path):
    monkeypatch.setenv("REA_DIR", str(tmp_path))
    # rea.config lit REA_DIR à l'import : on force un rechargement propre.
    for module in list(sys.modules):
        if module == "rea" or module.startswith("rea."):
            del sys.modules[module]
    from rea.db import Base

    b = Base()
    yield b
    b.fermer()
