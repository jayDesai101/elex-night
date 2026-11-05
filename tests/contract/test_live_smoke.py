"""Manual live check (make live-smoke): the real API still matches our contract."""

import httpx
import pytest

from elex.civic.models import CivicRace
from elex.config import Settings

pytestmark = pytest.mark.live
RACE_ID = 86922  # Arizona US House 6, recorded in Chunk 1


def test_status_ok() -> None:
    r = httpx.get(f"{Settings().civic_base_url}/status", timeout=20)
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_testdata_race_matches_contract() -> None:
    r = httpx.get(
        f"{Settings().civic_base_url}/race/{RACE_ID}", params={"testdata": "true"}, timeout=30
    )
    assert r.status_code == 200
    race = CivicRace.model_validate(r.json())
    keys = {(c.name, c.party) for c in race.candidates}
    for region in race.region_results.values():
        for c in region.candidates:
            assert (c.name, c.party) in keys
