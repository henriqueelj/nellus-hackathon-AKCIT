import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "agent"))

DATA_FIXA = "2026-10-24"


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    """Cada teste usa uma CÓPIA do JSON fixo (nunca o original) e NELLUS_HOJE fixo."""
    copia = tmp_path / "rebanho.json"
    shutil.copy(RAIZ / "data" / "rebanho.json", copia)
    monkeypatch.setenv("NELLUS_HOJE", DATA_FIXA)
    monkeypatch.setenv("NELLUS_DATA", str(copia))
    monkeypatch.setenv("NELLUS_OUT", str(tmp_path / "out"))
    import tools
    tools.PENDENTES.clear()
    yield copia
    tools.PENDENTES.clear()
