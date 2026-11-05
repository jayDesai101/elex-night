import json
from pathlib import Path

import pytest

from elex.civic.classify import classify_office
from elex.civic.models import CivicRace

CIVIC = Path(__file__).resolve().parents[1] / "fixtures" / "civicapi"
RACE_FILES = sorted(CIVIC.glob("race_*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_enough_fixtures() -> None:
    assert len(list(CIVIC.glob("*.json"))) >= 8


@pytest.mark.parametrize("path", RACE_FILES, ids=lambda p: p.stem)
def test_race_fixture_parses(path: Path) -> None:
    race = CivicRace.model_validate(_load(path))
    assert race.election_date.tzinfo is not None
    if not path.stem.endswith("_light"):
        assert race.region_results


@pytest.mark.parametrize("path", RACE_FILES, ids=lambda p: p.stem)
def test_region_candidates_join_on_name_party(path: Path) -> None:
    race = CivicRace.model_validate(_load(path))
    keys = {(c.name, c.party) for c in race.candidates}
    for slug, region in race.region_results.items():
        for c in region.candidates:
            assert (c.name, c.party) in keys, f"{slug}: {c.name} ({c.party})"


def test_county_regions_have_fips_in_2026_races() -> None:
    race = CivicRace.model_validate(_load(CIVIC / "race_87087.json"))
    counties = [r for r in race.region_results.values() if r.type == "County"]
    assert len(counties) == 159
    assert all(r.fips and len(r.fips) == 5 for r in counties)


@pytest.mark.parametrize(
    ("fname", "office"),
    [("race_87087", "senate"), ("race_87393", "governor"), ("race_86922", "house")],
)
def test_classify_real_races(fname: str, office: str) -> None:
    d = _load(CIVIC / f"{fname}.json")
    assert classify_office(d["election_type"], d["province"]) == office


def test_search_rows_classify() -> None:
    rows = _load(CIVIC / "search_general_p0.json")["races"]
    tonight = [r for r in rows if r["election_date"].startswith("2026-11-03")]
    offices = [classify_office(r["type"], r["province"]) for r in tonight]
    assert offices.count("house") >= 400
    assert offices.count("senate") >= 30


def test_history_list_and_snapshot() -> None:
    hist = _load(CIVIC / "history_160886.json")
    assert hist["id"] == 160886 and hist["count"] == len(hist["timestamps"])
    snap = _load(CIVIC / "history_160886_snapshot.json")
    assert snap["timestamp"] in hist["timestamps"]
    race = CivicRace.model_validate(snap["data"])
    assert race.election_name == "Guam Governor"
