"""dbt build on a fixture warehouse: clean data passes; each injected fault trips its test."""

import json
from datetime import timedelta
from pathlib import Path

import duckdb
import pytest

from elex.ingest.archive import Archive
from elex.ingest.fixture_wh import T0, build
from elex.pipeline.transform import run_dbt_build

CIVIC = Path("tests/fixtures/civicapi")


def _status(result, name: str) -> str:
    return next(c["status"] for c in result.checks if c["name"] == name)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory) -> Path:
    db = tmp_path_factory.mktemp("wh") / "dbt_test.duckdb"
    assert build(db) > 0
    return db


@pytest.fixture(scope="module")
def clean_build(warehouse):
    return run_dbt_build(warehouse, target="test")


def test_clean_build_passes(clean_build) -> None:
    assert clean_build.success, clean_build.error
    assert clean_build.errors == 0
    assert len(clean_build.checks) >= 20


def test_gold_non_empty_and_no_test_data(warehouse, clean_build) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    races = con.execute(
        "select count(*), count(*) filter (where test_data) from gold.fct_race_latest"
    )
    assert races.fetchone() == (7, 0)  # 7 real fixture races; testdata snapshots filtered
    assert con.execute("select count(*) from gold.fct_county_latest").fetchone()[0] > 200
    # recap replay: every county of the latest map has at least its first appearance
    missing = con.execute(
        "select count(*) from gold.fct_county_latest l where l.office in "
        "('senate', 'governor') and not exists (select 1 from gold.fct_county_timeseries t "
        "where t.office = l.office and t.county_fips = l.county_fips)"
    ).fetchone()[0]
    assert missing == 0
    seats = con.execute(
        "select d_total + r_total + o_total + uncalled from gold.fct_chamber_summary "
        "where office = 'senate'"
    ).fetchone()[0]
    assert seats == 65 + 3  # holdovers + the 3 Senate fixture races (GA, ME, AK)
    con.close()


def test_injected_faults_trip_their_tests(warehouse, clean_build) -> None:
    con = duckdb.connect(str(warehouse))
    con.execute("SET TimeZone='UTC'")
    archive = Archive(con, warehouse.parent / "fixture_raw")
    later = T0 + timedelta(minutes=5)

    def load(name: str) -> dict:
        return json.loads((CIVIC / f"{name}.json").read_text())

    bad_pct = load("race_86922")
    bad_pct["percent_reporting"] = 101
    archive.persist(86922, bad_pct, later, False)

    negative = load("race_87393")
    negative["candidates"][0]["votes"] = -5
    archive.persist(87393, negative, later, False)

    unjoinable = load("race_87087")
    first_region = next(iter(unjoinable["region_results"].values()))
    first_region["candidates"][0]["name"] = "Nobody Matches"
    archive.persist(87087, unjoinable, later, False)
    con.close()

    faulty = run_dbt_build(warehouse, target="test")
    assert _status(faulty, "assert_pct_reporting_bounds") == "fail"
    assert _status(faulty, "assert_non_negative_votes") == "fail"
    assert _status(faulty, "assert_region_candidates_join") == "fail"
    assert faulty.errors >= 3

    # test-data leak: force a gold row to test data, then run only that check
    con = duckdb.connect(str(warehouse))
    con.execute("update gold.fct_race_latest set test_data = true where race_id = 87087")
    con.close()
    leak = run_dbt_build(
        warehouse, target="test", extra_args=["--select", "assert_no_test_data_in_gold"]
    )
    assert _status(leak, "assert_no_test_data_in_gold") == "fail"


def test_chunked_rebuild_matches_a_full_build(tmp_path_factory) -> None:
    """Rebuilding the region model in time windows yields the same rows as one build.
    Uses its own warehouse: the shared one gets faults injected by an earlier test."""
    from elex.pipeline.transform import rebuild_in_chunks

    db = tmp_path_factory.mktemp("wh_chunks") / "dbt_test.duckdb"
    assert build(db) > 0
    full = run_dbt_build(db, target="test")
    assert full.success and full.errors == 0, full.error
    con = duckdb.connect(str(db), read_only=True)
    before = con.execute(
        "select count(*), sum(votes) from silver.stg_civic__region_results"
    ).fetchone()
    con.close()
    # 11 fixture snapshots: 4 per chunk means three windows plus the final build
    tr = rebuild_in_chunks(db, target="test", chunk_snapshots=4)
    assert tr.success and tr.errors == 0, tr.error
    con = duckdb.connect(str(db), read_only=True)
    after = con.execute(
        "select count(*), sum(votes) from silver.stg_civic__region_results"
    ).fetchone()
    con.close()
    assert after == before and after[0] > 0
