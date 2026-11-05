"""Full offline cycle: respx serves recorded races -> temp DuckDB -> dbt -> Parquet export ->
FastAPI TestClient returns schema-valid JSON from all six endpoints.

The *_testdata fixtures are served as ordinary races: they carry real vote counts, and
civicAPI leaves test_data=false in them (see docs/api_contract.md), so staging keeps them.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from elex.civic.client import CivicClient
from elex.config import Settings
from elex.db import connect
from elex.pipeline.cycle import Pipeline
from elex.pipeline.export import current_version, export
from elex.serve import schemas as s
from elex.serve.api import create_app

BASE = "https://civicapi.test/api/v2"
CIVIC = Path("tests/fixtures/civicapi")
GA_SEN, PA_GOV, AZ_06 = 87087, 87393, 86922
BODIES = {
    GA_SEN: "race_87087_testdata",
    PA_GOV: "race_87393_testdata",
    AZ_06: "race_86922_testdata",
}


def _load(name: str) -> dict:
    return json.loads((CIVIC / f"{name}.json").read_text())


async def _nosleep(_: float) -> None:
    return None


def run_cycle(data_dir: Path, bodies: dict[int, dict]):
    """One full cycle (ingest, dbt on the fixture target, export) against mocked civicAPI."""
    rows = _load("search_general_p0")["races"] + _load("search_20261103_p0")["races"]
    page = {"races": [r for r in rows if r["id"] in bodies]}
    tracked = data_dir / "tracked.csv"
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text(f"race_id,label,tier,baseline_proxy\n{GA_SEN},GA-Sen,A,\n")
    off = data_dir / "model_off.yaml"
    off.write_text("enabled: false\n")
    with respx.mock:
        respx.get(f"{BASE}/status").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        respx.get(f"{BASE}/race/search").mock(return_value=httpx.Response(200, json=page))
        for rid, body in bodies.items():
            respx.get(f"{BASE}/race/{rid}").mock(return_value=httpx.Response(200, json=body))
        pipeline = Pipeline(
            Settings(_env_file=None, data_dir=data_dir),
            CivicClient(BASE, jitter_s=0, sleep=_nosleep),
            tracked_csv=tracked,
            dbt_target="test",  # the live seat-total check needs the full 509-race catalog
            model_config=off,  # independent of the live kill switch in config/model.yaml
        )
        return asyncio.run(pipeline.run_once())


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("cycle")
    result = run_cycle(data_dir, {rid: _load(name) for rid, name in BODIES.items()})
    return data_dir, result


@pytest.fixture(scope="module")
def client(served):
    return TestClient(create_app(served[0]))


def test_cycle_ok_and_exported(served) -> None:
    data_dir, result = served
    assert result.status == "ok", result.errors
    assert result.new_snapshots == 3
    version = current_version(data_dir)
    assert version and version.startswith("v")
    con = connect(data_dir, read_only=True)
    row = con.execute(
        "select status, new_snapshots, dq_errors, serving_version from ops.pipeline_runs"
    ).fetchone()
    con.close()
    assert row == ("ok", 3, 0, version)


def test_health(client, served) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = s.Health.model_validate(r.json())
    assert body.serving_version == current_version(served[0])
    assert body.status == "ok" and 0 <= body.age_seconds < 300
    assert body.last_ingest_at.endswith("Z")
    assert r.headers["etag"] == f'"{body.serving_version}"'
    assert r.headers["cache-control"] == "max-age=15"


def test_etag_304_and_cors(client) -> None:
    etag = client.get("/api/health").headers["etag"]
    r = client.get("/api/health", headers={"If-None-Match": etag})
    assert r.status_code == 304 and r.content == b"" and r.headers["etag"] == etag
    stale = client.get("/api/health", headers={"If-None-Match": '"v-old"'})
    assert stale.status_code == 200
    cors = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_summary(client) -> None:
    rows = [s.Summary.model_validate(r) for r in client.get("/api/summary").json()]
    by = {r.office: r for r in rows}
    assert set(by) == {"senate", "house", "governor"}
    sen = by["senate"]
    assert (sen.d_total - sen.d_called, sen.r_total - sen.r_called) == (32, 31)  # holdovers
    assert sen.o_total - sen.o_called == 2
    assert sen.seats_up == 1 and sen.majority_line == 51
    assert sen.d_total + sen.r_total + sen.o_total + sen.uncalled == 65 + 1
    assert by["house"].majority_line == 218 and by["governor"].majority_line is None
    assert sen.est_pct_counted is None  # no model tables yet
    assert sen.mean_pct_reporting is not None
    only = client.get("/api/summary", params={"office": "house"}).json()
    assert [r["office"] for r in only] == ["house"]


def test_map_matches_fixture_math(client) -> None:
    counties = [s.MapCounty.model_validate(r) for r in client.get("/api/map?office=senate").json()]
    assert len(counties) == 159 and all(len(c.fips) == 5 for c in counties)
    payload = _load("race_87087_testdata")
    appling = payload["region_results"]["appling"]
    votes = {c["party"]: c["votes"] for c in appling["candidates"]}
    d, r = votes["Democratic"], votes["Republican"]
    got = next(c for c in counties if c.fips == "13001")
    assert got.total_votes == sum(votes.values())
    assert got.margin_pp == pytest.approx(100 * (d - r) / (d + r))
    assert got.pct_reporting == appling["percent_reporting"]
    assert len(client.get("/api/map?office=governor").json()) == 67
    assert len(client.get("/api/map?office=house").json()) == 5
    assert client.get("/api/map?office=president").status_code == 422


def test_recap_replays_to_the_latest_map(client) -> None:
    rc = s.Recap.model_validate(client.get("/api/recap?office=senate").json())
    n = len(rc.t)
    assert n > 0 and all(len(col) == n for col in (rc.race_id, rc.fips, rc.d, rc.r, rc.total))
    assert rc.t == sorted(rc.t)
    # the last update of each county equals the live map
    last: dict[str, tuple[int, int, int]] = {}
    for i in range(n):
        last[rc.fips[i]] = (rc.d[i], rc.r[i], rc.total[i])
    live = {c["fips"]: c for c in client.get("/api/map?office=senate").json()}
    assert set(last) == set(live)
    d, r, total = last["13001"]
    assert total == live["13001"]["total_votes"]
    assert 100 * (d - r) / (d + r) == pytest.approx(live["13001"]["margin_pp"])
    assert client.get("/api/recap?office=president").status_code == 422


def test_races(client) -> None:
    tracked = client.get("/api/races", params={"tracked": "true"}).json()
    # is_tracked comes from the dbt seed tracked_races.csv, where GA-Sen and PA-Gov are
    # key races; the House race AZ-06 is not
    assert [r["label"] for r in tracked] == ["GA-Sen", "PA-Gov"]
    race = s.Race.model_validate(tracked[0])
    fixture = {c["name"]: c["votes"] for c in _load("race_87087_testdata")["candidates"]}
    assert {c.name: c.votes for c in race.candidates} == fixture
    votes = [c.votes for c in race.candidates]
    assert votes == sorted(votes, reverse=True)
    assert sum(c.pct for c in race.candidates) == pytest.approx(100)
    assert race.projection == s.Projection()  # model tables absent: all null
    assert race.margin_pp is not None and race.office == "senate"
    assert race.polls_close == "2026-11-04T00:00:00Z"  # 7 PM ET, from the fixture
    assert race.last_updated and race.last_updated.endswith("Z")
    assert len(client.get("/api/races").json()) == 3
    house = client.get("/api/races", params={"office": "house"}).json()
    assert [r["label"] for r in house] == ["Arizona US House 6"]


def test_race_votes_timeline(client) -> None:
    pts = [s.VotePoint.model_validate(p) for p in client.get(f"/api/races/{GA_SEN}/votes").json()]
    fixture = {c["name"]: c["votes"] for c in _load("race_87087_testdata")["candidates"]}
    assert {p.name: p.votes for p in pts} == fixture  # one snapshot, every candidate
    assert all(p.t.endswith("Z") for p in pts)
    assert client.get("/api/races/999/votes").json() == []


def test_race_history_empty_without_model(client) -> None:
    r = client.get(f"/api/races/{GA_SEN}/history")
    assert r.status_code == 200 and r.json() == []


def test_pipeline(client) -> None:
    body = s.Pipeline.model_validate(client.get("/api/pipeline").json())
    assert body.rows_processed > 0
    names = {c.name: c.status for c in body.checks}
    assert {"assert_pct_reporting_bounds", "assert_votes_monotonic", "source_freshness"} <= set(
        names
    )
    assert set(names.values()) <= {"pass", "warn"}
    assert body.last_ingest_at.endswith("Z")


def test_openapi_lists_all_six_endpoints(client) -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {
        "/api/health",
        "/api/summary",
        "/api/map",
        "/api/recap",
        "/api/races",
        "/api/races/{race_id}/history",
        "/api/races/{race_id}/votes",
        "/api/pipeline",
    }


def test_projection_fields_and_new_version(served, client) -> None:
    """Model tables, once present, flow into races/summary/history, and a new export is
    picked up without restarting the API."""
    data_dir, _ = served
    before = client.get("/api/health").json()["serving_version"]
    con = connect(data_dir)
    con.execute("CREATE SCHEMA IF NOT EXISTS model")
    con.execute(
        "CREATE OR REPLACE TABLE model.projection_latest AS SELECT ? AS race_id, "
        "1.5 AS proj_margin_median, -0.5 AS p10, 3.5 AS p90, 0.4 AS est_pct_counted, "
        "1000 AS est_expected_votes, 'ok' AS status",
        [GA_SEN],
    )
    con.execute(
        "CREATE OR REPLACE TABLE model.projection_history AS "
        "SELECT ? AS race_id, TIMESTAMPTZ '2026-11-04 01:30:00+00' AS as_of, "
        "1.5 AS proj_margin_median, -0.5 AS p10, 3.5 AS p90, 0.4 AS est_pct_counted",
        [GA_SEN],
    )
    export(con, data_dir, datetime.now(UTC) + timedelta(seconds=5))
    con.close()
    assert client.get("/api/health").json()["serving_version"] != before
    race = client.get("/api/races", params={"tracked": "true"}).json()[0]
    assert race["projection"] == {"median": 1.5, "p10": -0.5, "p90": 3.5, "status": "ok"}
    sen = next(r for r in client.get("/api/summary").json() if r["office"] == "senate")
    assert sen["est_pct_counted"] == pytest.approx(0.4)
    hist = client.get(f"/api/races/{GA_SEN}/history").json()
    assert hist == [
        {
            "as_of": "2026-11-04T01:30:00Z",
            "median": 1.5,
            "p10": -0.5,
            "p90": 3.5,
            "est_pct_counted": 0.4,
        }
    ]


def test_503_before_first_export(tmp_path) -> None:
    c = TestClient(create_app(tmp_path))
    for path in (
        "/api/health",
        "/api/summary",
        "/api/map",
        "/api/races",
        f"/api/races/{GA_SEN}/history",
        "/api/pipeline",
    ):
        r = c.get(path)
        assert r.status_code == 503 and r.json() == {"detail": "no data yet"}, path
    assert c.get("/docs").status_code == 200


def test_dq_error_blocks_export_but_keeps_ingest(tmp_path) -> None:
    bad = _load("race_86922_testdata")
    bad["percent_reporting"] = 101
    result = run_cycle(tmp_path, {AZ_06: bad})
    assert result.status == "partial" and result.new_snapshots == 1
    assert current_version(tmp_path) is None  # nothing was exported
    from elex.pipeline.export import read_heartbeat

    assert read_heartbeat(tmp_path) is None  # a blocked export must not look current
    con = connect(tmp_path, read_only=True)
    assert con.execute("select count(*) from bronze.race_snapshots").fetchone()[0] == 1
    run = con.execute("select status, dq_errors, serving_version from ops.pipeline_runs").fetchone()
    failed = con.execute(
        "select status from ops.dq_results where name = 'assert_pct_reporting_bounds'"
    ).fetchone()
    con.close()
    assert run[0] == "partial" and run[1] >= 1 and run[2] is None
    assert failed == ("fail",)


def test_serves_built_dashboard_at_root(served, tmp_path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Election Night</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(served[0], web_dist=dist))
    assert "Election Night" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/health").json()["status"] == "ok"  # API still wins


def test_health_uses_newer_heartbeat(served) -> None:
    from elex.pipeline.export import write_heartbeat

    data_dir, _ = served
    write_heartbeat(data_dir, datetime.now(UTC) - timedelta(seconds=5))
    body = TestClient(create_app(data_dir)).get("/api/health").json()
    assert body["status"] == "ok" and body["age_seconds"] < 30
    write_heartbeat(data_dir, datetime(2020, 1, 1, tzinfo=UTC))  # older: ignored
    assert TestClient(create_app(data_dir)).get("/api/health").json()["age_seconds"] < 300
