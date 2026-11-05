"""Offline ingest: respx serves recorded fixtures; a fake clock drives two cycles."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import respx

from elex.civic.client import CivicClient
from elex.config import Settings
from elex.db import connect
from elex.pipeline.cycle import Pipeline

BASE = "https://civicapi.test/api/v2"
RACES = {87087: "race_87087", 87393: "race_87393", 86922: "race_86922"}


def _search_page(fixtures_dir) -> dict:
    rows = json.loads((fixtures_dir / "civicapi/search_general_p0.json").read_text())["races"]
    gov = json.loads((fixtures_dir / "civicapi/search_20261103_p0.json").read_text())["races"]
    keep = [r for r in rows + gov if r["id"] in RACES]
    return {"count": len(keep), "limit": 1000, "offset": 0, "races": keep}


async def _nosleep(_: float) -> None:
    return None


def _mock_api(fixtures_dir) -> dict[int, respx.Route]:
    respx.get(f"{BASE}/status").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    page = _search_page(fixtures_dir)
    respx.get(f"{BASE}/race/search").mock(return_value=httpx.Response(200, json=page))
    routes = {}
    for rid, name in RACES.items():
        body = json.loads((fixtures_dir / f"civicapi/{name}.json").read_text())
        routes[rid] = respx.get(f"{BASE}/race/{rid}").mock(
            return_value=httpx.Response(200, json=body)
        )
    return routes


@respx.mock
def test_two_cycles_dedupe(tmp_path, fixtures_dir) -> None:
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    settings = Settings(_env_file=None, data_dir=tmp_path)
    client = CivicClient(BASE, jitter_s=0, sleep=_nosleep)
    tracked = tmp_path / "tracked.csv"
    tracked.write_text("race_id,label,tier,baseline_proxy\n87087,GA-Sen,A,\n")
    p = Pipeline(settings, client, clock=lambda: now[0], tracked_csv=tracked, transform=False)

    r1 = asyncio.run(p.run_once())
    assert r1.status == "ok", r1.errors
    assert r1.new_snapshots == 3

    now[0] += timedelta(seconds=61)
    r2 = asyncio.run(p.run_once())
    assert r2.status == "ok"
    assert r2.new_snapshots == 0
    assert r2.requests == 2  # status + tier-A race only; B and C are not due yet

    con = connect(tmp_path, read_only=True)
    tiers = dict(con.execute("select race_id, tier from bronze.race_catalog").fetchall())
    assert tiers == {87087: "A", 87393: "B", 86922: "C"}
    assert con.execute("select count(*) from bronze.race_snapshots").fetchone()[0] == 3
    n_race_logs = con.execute(
        "select count(*) from bronze.ingest_log where endpoint = 'race'"
    ).fetchone()[0]
    assert n_race_logs == 4
    runs = con.execute("select status from ops.pipeline_runs").fetchall()
    assert [r[0] for r in runs] == ["ok", "ok"]
    con.close()


@respx.mock
def test_tier_c_light_then_skip(tmp_path, fixtures_dir) -> None:
    routes = _mock_api(fixtures_dir)
    light = json.loads((fixtures_dir / "civicapi/race_86922.json").read_text())
    light.pop("region_results")
    full_body = routes[86922].return_value

    def by_light(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("light") == "true":
            return httpx.Response(200, json=light)
        return full_body

    routes[86922].mock(side_effect=by_light)

    def full_calls_of(route: respx.Route) -> int:
        return sum("light" not in str(c.request.url) for c in route.calls)

    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
        transform=False,
    )
    asyncio.run(p.run_once())
    full_calls = full_calls_of(routes[86922])
    now[0] += timedelta(seconds=601)
    asyncio.run(p.run_once())
    # unchanged last_updated: only the light call, no new full fetch
    assert full_calls_of(routes[86922]) == full_calls == 1
    con = connect(tmp_path, read_only=True)
    n_light = con.execute(
        "select count(*) from bronze.ingest_log where endpoint = 'race_light'"
    ).fetchone()[0]
    assert n_light == 1
    con.close()


@respx.mock
def test_status_down_records_failed_cycle(tmp_path) -> None:
    respx.get(f"{BASE}/status").mock(return_value=httpx.Response(503))
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path), CivicClient(BASE, jitter_s=0, sleep=_nosleep)
    )
    r = asyncio.run(p.run_once())
    assert r.status == "failed"
    con = connect(tmp_path, read_only=True)
    assert con.execute("select status from ops.pipeline_runs").fetchone()[0] == "failed"
    con.close()


def _slow_api(fixtures_dir, mono: list[float], step_s: float) -> None:
    """Like _mock_api, but every race request advances the client's clock by step_s."""
    _mock_api(fixtures_dir)
    for rid, name in RACES.items():
        body = json.loads((fixtures_dir / f"civicapi/{name}.json").read_text())

        def respond(request, body=body):
            mono[0] += step_s
            return httpx.Response(200, json=body)

        respx.get(f"{BASE}/race/{rid}").mock(side_effect=respond)


@respx.mock
def test_polls_stamped_with_cycle_slot_not_fetch_time(tmp_path, fixtures_dir) -> None:
    mono = [0.0]
    _slow_api(fixtures_dir, mono, step_s=10.0)  # each race takes 10 s
    start = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)
    wall = [start]
    client = CivicClient(BASE, jitter_s=0, sleep=_nosleep, clock=lambda: mono[0], concurrency=1)
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path, search_refresh_s=10**6),
        client,
        clock=lambda: wall[0],
        tracked_csv=tmp_path / "none.csv",
        transform=False,
    )
    asyncio.run(p.run_once())
    assert set(p.last_polled.values()) == {start}  # the slot, although fetches took 30 s
    # next cycle 60 s later: the race fetched last is due again (stamped at the slot)
    wall[0] = start + timedelta(seconds=180)
    r2 = asyncio.run(p.run_once())
    assert r2.requests == 1 + 2  # status + the two 180 s tier-B races


@respx.mock
def test_cycle_budget_defers_without_dropping(tmp_path, fixtures_dir) -> None:
    mono = [0.0]
    _slow_api(fixtures_dir, mono, step_s=30.0)  # each race takes 30 s, budget is 45 s
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    client = CivicClient(BASE, jitter_s=0, sleep=_nosleep, clock=lambda: mono[0], concurrency=1)
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        client,
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
        transform=False,
        cycle_budget_s=45.0,
    )
    r1 = asyncio.run(p.run_once())
    # race 1 starts at t=0, race 2 at t=30 (< 45), race 3 would start at t=60: deferred
    assert (r1.new_snapshots, r1.skipped) == (2, 1)
    deferred = set(RACES) - set(p.last_polled)
    assert len(deferred) == 1
    con = connect(tmp_path, read_only=True)
    n_logged = con.execute(
        "select count(*) from bronze.ingest_log where endpoint='race'"
    ).fetchone()
    con.close()
    assert n_logged == (2,)  # a deferred race is not a request: nothing logged
    now[0] += timedelta(seconds=1)  # next cycle at once: the deferred race is still due
    r2 = asyncio.run(p.run_once())
    assert r2.new_snapshots == 1 and r2.skipped == 0
    assert set(p.last_polled) == set(RACES)


@respx.mock
def test_full_refresh_flag_triggers_rebuild_once(tmp_path, fixtures_dir, monkeypatch) -> None:
    import elex.pipeline.cycle as cycle
    from elex.ingest.backfill import full_refresh_flag
    from elex.pipeline.transform import TransformResult

    calls: list[list[str] | None] = []

    def fake_build(db, target="dev", extra_args=None, **_):
        calls.append(extra_args)
        return TransformResult(True)

    monkeypatch.setattr(cycle, "run_dbt_build", fake_build)
    monkeypatch.setattr(
        cycle,
        "rebuild_in_chunks",
        lambda db, target="dev", **_: fake_build(db, target, ["--full-refresh"]),
    )
    monkeypatch.setattr(cycle, "export", lambda con, data_dir, now: "v-test")
    monkeypatch.setattr(cycle, "current_version", lambda data_dir: "v-test")
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
    )
    asyncio.run(p.run_once())  # new snapshots: an ordinary build
    full_refresh_flag(tmp_path).touch()
    now[0] += timedelta(seconds=1)  # nothing due, no new snapshots, but the flag is set
    asyncio.run(p.run_once())
    now[0] += timedelta(seconds=1)
    asyncio.run(p.run_once())  # flag cleared: no build at all
    assert calls == [None, ["--full-refresh"]]
    assert not full_refresh_flag(tmp_path).exists()


@respx.mock
def test_model_error_marks_partial_but_still_exports(tmp_path, fixtures_dir, monkeypatch) -> None:
    import elex.pipeline.cycle as cycle
    from elex.pipeline.transform import TransformResult

    exported = []
    monkeypatch.setattr(cycle, "run_dbt_build", lambda *a, **k: TransformResult(True))
    monkeypatch.setattr(cycle, "export", lambda con, d, now: exported.append(1) or "v-test")

    def boom(con, **_):
        raise RuntimeError("model blew up")

    monkeypatch.setattr(cycle, "model_run", boom)
    _mock_api(fixtures_dir)
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        tracked_csv=tmp_path / "none.csv",
    )
    r = asyncio.run(p.run_once())
    assert r.status == "partial" and r.model_status == "error"
    assert "model: model blew up" in r.errors
    assert exported == [1]  # counts are still served
    con = connect(tmp_path, read_only=True)
    row = con.execute("select status, model_status, serving_version from ops.pipeline_runs")
    assert row.fetchone() == ("partial", "error", "v-test")
    con.close()


@respx.mock
def test_status_down_but_search_up_still_publishes_totals(tmp_path, fixtures_dir) -> None:
    """civicAPI's /status fails while search answers: the cycle stores race totals."""
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
        transform=False,
    )
    asyncio.run(p.run_once())  # healthy cycle: catalog and first snapshots
    respx.get(f"{BASE}/status").mock(return_value=httpx.Response(502))
    body = json.loads((fixtures_dir / "civicapi/race_86922.json").read_text())
    row = {
        "id": 86922,
        "election_date": "2026-11-03T05:00:00.000Z",
        "type": "House of Representatives",
        "percent_reporting": 5,
        "candidates": [dict(c, votes=100 + i) for i, c in enumerate(body["candidates"])],
    }
    respx.get(f"{BASE}/race/search").mock(
        return_value=httpx.Response(
            200, json={"races": [row], "count": 1, "limit": 1000, "offset": 0}
        )
    )
    now[0] += timedelta(seconds=120)
    r = asyncio.run(p.run_once())
    assert r.status == "partial" and r.new_snapshots == 1
    assert any(e.startswith("status:") for e in r.errors)


@respx.mock
def test_unpublished_data_is_published_while_civicapi_is_down(
    tmp_path, fixtures_dir, monkeypatch
) -> None:
    import elex.pipeline.cycle as cycle
    from elex.pipeline.transform import TransformResult

    builds, exports = [], []
    results = iter([TransformResult(True, errors=1), TransformResult(True)])  # 1st blocked
    monkeypatch.setattr(cycle, "run_dbt_build", lambda *a, **k: builds.append(1) or next(results))
    monkeypatch.setattr(cycle, "export", lambda con, d, now: exports.append(1) or "v-test")
    monkeypatch.setattr(cycle, "model_run", lambda con, **k: __import__("pandas").DataFrame())
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
    )
    asyncio.run(p.run_once())  # new snapshots, export blocked by a DQ error
    assert (len(builds), exports) == (1, [])
    respx.get(f"{BASE}/status").mock(return_value=httpx.Response(502))
    respx.get(f"{BASE}/race/search").mock(return_value=httpx.Response(502))
    now[0] += timedelta(seconds=120)
    r = asyncio.run(p.run_once())  # civicAPI down, but the archive still publishes
    assert r.status == "failed" and exports == [1] and len(builds) == 2
    now[0] += timedelta(seconds=120)
    asyncio.run(p.run_once())  # nothing new, nothing unpublished: no build
    assert len(builds) == 2


@respx.mock
def test_cycle_with_no_successful_fetch_is_not_live(tmp_path, fixtures_dir, monkeypatch) -> None:
    import elex.pipeline.cycle as cycle
    from elex.pipeline.export import read_heartbeat
    from elex.pipeline.transform import TransformResult

    monkeypatch.setattr(cycle, "run_dbt_build", lambda *a, **k: TransformResult(True))
    monkeypatch.setattr(cycle, "export", lambda con, d, now: "v-test")
    monkeypatch.setattr(cycle, "model_run", lambda con, **k: __import__("pandas").DataFrame())
    monkeypatch.setattr(cycle, "current_version", lambda d: "v-test")
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
    )
    asyncio.run(p.run_once())
    first_beat = read_heartbeat(tmp_path)
    assert first_beat is not None
    for rid in RACES:  # civicAPI answers /status but fails every race and search
        respx.get(f"{BASE}/race/{rid}").mock(return_value=httpx.Response(500))
    respx.get(f"{BASE}/race/search").mock(return_value=httpx.Response(502))
    now[0] += timedelta(seconds=700)
    r = asyncio.run(p.run_once())
    assert r.fetched_ok == 0 and r.status == "partial"
    assert "no successful fetches from civicAPI" in r.errors
    assert read_heartbeat(tmp_path) == first_beat  # badge ages instead of staying LIVE


def test_full_refresh_gets_a_longer_dbt_timeout(monkeypatch, tmp_path) -> None:
    from elex.pipeline import transform

    seen = []

    def fake_run(args, env, capture_output, text, timeout):
        seen.append(timeout)
        raise transform.subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(transform.subprocess, "run", fake_run)
    transform.run_dbt_build(tmp_path / "x.duckdb")
    transform.run_dbt_build(tmp_path / "x.duckdb", extra_args=["--full-refresh"])
    assert seen == [300, transform.FULL_REFRESH_TIMEOUT_S]


@respx.mock
def test_failed_full_refresh_falls_back_to_incremental(tmp_path, fixtures_dir, monkeypatch) -> None:
    import elex.pipeline.cycle as cycle
    from elex.ingest.backfill import full_refresh_flag
    from elex.pipeline.transform import TransformResult

    calls: list[list[str] | None] = []

    def fake_build(db, target="dev", extra_args=None, **_):
        calls.append(extra_args)
        if extra_args:  # the full refresh dies (out of memory)
            return TransformResult(False, errors=1, error="Out of Memory")
        return TransformResult(True)

    monkeypatch.setattr(cycle, "run_dbt_build", fake_build)
    monkeypatch.setattr(
        cycle,
        "rebuild_in_chunks",
        lambda db, target="dev", **_: fake_build(db, target, ["--full-refresh"]),
    )
    monkeypatch.setattr(cycle, "export", lambda con, d, now: "v-test")
    monkeypatch.setattr(cycle, "current_version", lambda d: "v-test")
    monkeypatch.setattr(cycle, "model_run", lambda con, **k: __import__("pandas").DataFrame())
    _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
    )
    full_refresh_flag(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    full_refresh_flag(tmp_path).touch()
    r = asyncio.run(p.run_once())
    assert calls == [["--full-refresh"], None]  # refresh failed, incremental ran
    assert r.status == "ok"  # and the cycle published
    assert full_refresh_flag(tmp_path).exists()  # the refresh is still owed
    now[0] += timedelta(minutes=5)
    asyncio.run(p.run_once())
    assert ["--full-refresh"] not in calls[1:]  # no retry within 30 min
    now[0] += timedelta(minutes=30)
    asyncio.run(p.run_once())
    assert calls[-2:] == [["--full-refresh"], None]  # retried after the wait, fell back again


@respx.mock
def test_search_change_makes_tier_c_race_due_for_a_full_poll(tmp_path, fixtures_dir) -> None:
    """House (tier C) county detail only arrives in the full payload. When the search
    refresh sees a race's totals change, the next cycle must fetch it in full even though
    its 600 s interval has not elapsed (the cycle budget starved tier C on election night)."""
    routes = _mock_api(fixtures_dir)
    now = [datetime(2026, 11, 4, 1, 0, tzinfo=UTC)]
    p = Pipeline(
        Settings(_env_file=None, data_dir=tmp_path, search_refresh_s=1),
        CivicClient(BASE, jitter_s=0, sleep=_nosleep),
        clock=lambda: now[0],
        tracked_csv=tmp_path / "none.csv",
        transform=False,
    )
    asyncio.run(p.run_once())  # everything polled once; AZ-06 is tier C
    full_calls = sum("light" not in str(c.request.url) for c in routes[86922].calls)
    # search now reports new totals for AZ-06
    body = json.loads((fixtures_dir / "civicapi/race_86922.json").read_text())
    row = {
        "id": 86922,
        "election_date": "2026-11-03T05:00:00.000Z",
        "type": "House of Representatives",
        "percent_reporting": 12,
        "candidates": [dict(c, votes=1000 + i) for i, c in enumerate(body["candidates"])],
    }
    respx.get(f"{BASE}/race/search").mock(
        return_value=httpx.Response(
            200, json={"races": [row], "count": 1, "limit": 1000, "offset": 0}
        )
    )
    now[0] += timedelta(seconds=61)
    asyncio.run(p.run_once())  # search refresh runs (1 s interval), marks AZ-06 due
    now[0] += timedelta(seconds=61)
    asyncio.run(p.run_once())  # next cycle: full poll of AZ-06 although 600 s have not passed
    assert sum("light" not in str(c.request.url) for c in routes[86922].calls) > full_calls
