from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated ELEX_DATA_DIR for a test; never touches the real archive."""
    d = tmp_path / "data"
    monkeypatch.setenv("ELEX_DATA_DIR", str(d))
    from elex.config import get_settings

    get_settings.cache_clear()
    yield d
    get_settings.cache_clear()
