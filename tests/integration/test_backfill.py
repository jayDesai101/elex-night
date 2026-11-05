"""History backfill: fetch what we lack, dedupe against all stored states, flag a refresh."""

import asyncio
import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from elex.civic.client import CivicClient
from elex.db import connect, init_db
from elex.ingest.archive import Archive
from elex.ingest.backfill import backfill, full_refresh_flag
from elex.ingest.discover import CatalogRow, upsert_catalog

BASE = "https://civicapi.test/api/v2"
CIVIC = Path("tests/fixtures/civicapi")
GUAM, GA = 160886, 87087


async def _nosleep(_: float) -> None:
    return None


def _load(name: str) -> dict:
    return json.loads((CIVIC / f"{name}.json").read_text())


def _setup(tmp_path: Path) -> None:
    con = connect(tmp_path)
    init_db(con)
    upsert_catalog(
        con,
        [
            CatalogRow(GUAM, "Guam Governor", "Governor", "Statewide", "GU", None, "governor", "B"),
            CatalogRow(GA, "Georgia US Senate", "US Senate", "General", "GA", None, "senate", "A"),
        ],
    )
    con.close()


def _mock(hist: dict, snaps: dict[str, dict]) -> dict[str, respx.Route]:
    respx.get(f"{BASE}/race/{GA}/history").mock(
        return_value=httpx.Response(404, json={"error": "no history found for this race!"})
    )
    respx.get(f"{BASE}/race/{GUAM}/history").mock(return_value=httpx.Response(200, json=hist))
    routes = {}
    for ts, body in snaps.items():
        routes[ts] = respx.get(f"{BASE}/race/{GUAM}/history/{ts}").mock(
            return_value=httpx.Response(200, json=body)
        )
    return routes


def _history():
    hist = _load("history_160886")
    new_ts, old_ts = hist["timestamps"]  # newest first
    latest = _load("history_160886_snapshot")
    assert latest["timestamp"] == new_ts
    older = copy.deepcopy(latest)
    older["timestamp"] = old_ts
    older["data"]["last_updated"] = old_ts
    for c in older["data"]["candidates"]:
        c["votes"] //= 2
    return hist, {new_ts: latest, old_ts: older}


def _run(tmp_path: Path):
    client = CivicClient(BASE, jitter_s=0, sleep=_nosleep)
    return asyncio.run(backfill(client, tmp_path))


@respx.mock
def test_backfill_inserts_missing_states_and_flags_refresh(tmp_path) -> None:
    _setup(tmp_path)
    hist, snaps = _history()
    _mock(hist, snaps)
    res = _run(tmp_path)
    assert (res.races, res.no_history, res.listed, res.fetched, res.inserted) == (2, 1, 2, 2, 2)
    assert res.errors == []
    con = connect(tmp_path, read_only=True)
    got = con.execute(
        "select fetched_at, test_data from bronze.race_snapshots where race_id = ? "
        "order by fetched_at",
        [GUAM],
    ).fetchall()
    logs = con.execute(
        "select count(*), count(error) from bronze.ingest_log where endpoint = 'history'"
    ).fetchone()
    con.close()
    stamps = sorted(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in snaps)
    assert [g[0].astimezone(UTC) for g in got] == stamps  # fetched_at = history timestamp
    assert all(g[1] is False for g in got)
    assert logs == (4, 0)  # 2 listings (one a normal 404, not an error) + 2 snapshots
    assert full_refresh_flag(tmp_path).exists()


@respx.mock
def test_rerun_fetches_nothing(tmp_path) -> None:
    _setup(tmp_path)
    hist, snaps = _history()
    routes = _mock(hist, snaps)
    _run(tmp_path)
    full_refresh_flag(tmp_path).unlink()
    before = {ts: r.call_count for ts, r in routes.items()}
    res = _run(tmp_path)
    assert (res.fetched, res.inserted) == (0, 0)
    assert {ts: r.call_count for ts, r in routes.items()} == before
    assert not full_refresh_flag(tmp_path).exists()


@respx.mock
def test_skips_state_the_live_archiver_already_has(tmp_path) -> None:
    _setup(tmp_path)
    hist, snaps = _history()
    routes = _mock(hist, snaps)
    new_ts = hist["timestamps"][0]
    live = snaps[new_ts]["data"]  # the live poll saw the newest state (last_updated ~0.1 s off)
    con = connect(tmp_path)
    Archive(con, tmp_path).persist(GUAM, live, datetime(2026, 11, 3, 16, 21, tzinfo=UTC), False)
    con.close()
    res = _run(tmp_path)
    assert routes[new_ts].call_count == 0  # within 5 s of a stored state: not fetched
    assert res.inserted == 1  # only the older state was missing
    con = connect(tmp_path, read_only=True)
    n = con.execute("select count(*) from bronze.race_snapshots").fetchone()[0]
    con.close()
    assert n == 2


@respx.mock
def test_same_content_under_new_timestamp_is_not_duplicated(tmp_path) -> None:
    _setup(tmp_path)
    hist, snaps = _history()
    old_ts = hist["timestamps"][1]
    snaps[old_ts] = snaps[hist["timestamps"][0]]  # identical payload at both timestamps
    _mock(hist, snaps)
    res = _run(tmp_path)
    assert (res.fetched, res.inserted) == (2, 1)
