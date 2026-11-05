"""Race totals from search: changed races get a merged snapshot, unchanged ones do not."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from elex.civic.client import CivicClient
from elex.db import connect, init_db
from elex.ingest import search_refresh
from elex.ingest.archive import Archive

BASE = "https://civicapi.test/api/v2"
CIVIC = Path("tests/fixtures/civicapi")
AZ06 = 86922
T0 = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)


async def _nosleep(_: float) -> None:
    return None


def _row(payload: dict, votes: list[int], pct: float) -> dict:
    cands = [
        {**{k: c[k] for k in ("name", "party", "percent", "winner")}, "votes": v}
        for c, v in zip(payload["candidates"], votes, strict=False)
    ]
    return {
        "id": AZ06,
        "election_date": "2026-11-03T05:00:00.000Z",
        "type": "House of Representatives",
        "percent_reporting": pct,
        "candidates": cands,
    }


def _run(tmp_path, row):
    return _run_full(tmp_path, row)[0]


def _run_full(tmp_path, row) -> tuple[int, list[int]]:
    respx.get(f"{BASE}/race/search").mock(
        return_value=httpx.Response(
            200, json={"races": [row], "count": 1, "limit": 1000, "offset": 0}
        )
    )
    con = connect(tmp_path)
    try:
        client = CivicClient(BASE, jitter_s=0, sleep=_nosleep)
        return asyncio.run(
            search_refresh.refresh(
                client, con, Archive(con, tmp_path), {AZ06}, lambda *a, **k: None, lambda: T0, False
            )
        )
    finally:
        con.close()


@respx.mock
def test_changed_totals_create_a_merged_snapshot(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    Archive(con, tmp_path).persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    con.close()
    votes = [1000 + 10 * i for i in range(len(base["candidates"]))]
    assert _run(tmp_path, _row(base, votes, 12.0)) == 1
    con = connect(tmp_path, read_only=True)
    latest = json.loads(
        con.execute(
            "select payload from bronze.race_snapshots order by fetched_at desc limit 1"
        ).fetchone()[0]
    )
    con.close()
    assert [c["votes"] for c in latest["candidates"]] == votes
    assert latest["percent_reporting"] == 12.0 and latest["_source"] == "search"
    assert latest["region_results"] == base["region_results"]  # county detail kept
    assert all("candidate_id" in c for c in latest["candidates"])  # ids preserved by name+party


@respx.mock
def test_unchanged_totals_store_nothing(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    Archive(con, tmp_path).persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    con.close()
    same = _row(base, [c["votes"] for c in base["candidates"]], base["percent_reporting"])
    assert _run(tmp_path, same) == 0


def test_merge_keeps_unknown_fields_and_marks_source() -> None:
    base = {
        "candidates": [
            {"name": "A", "party": "Democratic", "candidate_id": 1, "votes": 0, "color": "#00f"}
        ],
        "percent_reporting": 0,
        "region_results": {"x": 1},
    }
    out = search_refresh.merge(
        base,
        {
            "percent_reporting": 5,
            "candidates": [{"name": "A", "party": "Democratic", "votes": 7, "percent": 100.0}],
        },
        T0,
    )
    assert out["candidates"][0] == {
        "name": "A",
        "party": "Democratic",
        "candidate_id": 1,
        "votes": 7,
        "color": "#00f",
        "percent": 100.0,
    }
    assert out["region_results"] == {"x": 1} and base["candidates"][0]["votes"] == 0
    assert out["_merged_at"] == "2026-11-04T01:00:00.000Z"
    assert "last_updated" not in out  # civicAPI's own timestamp is kept as-is


@respx.mock
def test_older_search_totals_are_ignored(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922_testdata.json").read_text())  # real vote counts
    con = connect(tmp_path)
    init_db(con)
    Archive(con, tmp_path).persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    con.close()
    lagging = _row(base, [max(0, c["votes"] - 500) for c in base["candidates"]], 1.0)
    assert _run(tmp_path, lagging) == 0  # never roll counts back


def test_merge_keeps_candidates_search_omits() -> None:
    base = {
        "candidates": [
            {"name": "A", "party": "Democratic", "votes": 1},
            {"name": "Write-in", "party": "Nonpartisan", "votes": 0},
        ]
    }
    out = search_refresh.merge(
        base,
        {
            "percent_reporting": 5,
            "candidates": [
                {"name": "A", "party": "Democratic", "votes": 9},
                {"name": "B", "party": "Republican", "votes": 4},
            ],
        },
        T0,
    )
    assert [(c["name"], c["votes"]) for c in out["candidates"]] == [
        ("A", 9),
        ("Write-in", 0),
        ("B", 4),
    ]


@respx.mock
def test_remerge_repairs_and_merges_onto_race_payload(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    arch = Archive(con, tmp_path)
    arch.persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    bad = dict(base, candidates=base["candidates"][:1], _source="search")  # an old bad merge
    arch.persist(AZ06, bad, datetime(2026, 11, 4, 0, 30, tzinfo=UTC), False)
    con.close()
    votes = [c["votes"] for c in bad["candidates"]]
    row = _row(base, votes, base["percent_reporting"])
    row["candidates"] = row["candidates"][:1]  # same totals as the bad snapshot
    respx.get(f"{BASE}/race/search").mock(
        return_value=httpx.Response(
            200, json={"races": [row], "count": 1, "limit": 1000, "offset": 0}
        )
    )
    con = connect(tmp_path)
    client = CivicClient(BASE, jitter_s=0, sleep=_nosleep)
    n, _ = asyncio.run(
        search_refresh.refresh(
            client,
            con,
            Archive(con, tmp_path),
            {AZ06},
            lambda *a, **k: None,
            lambda: T0,
            False,
            remerge=True,
        )
    )
    latest = json.loads(
        con.execute(
            "select payload from bronze.race_snapshots order by fetched_at desc limit 1"
        ).fetchone()[0]
    )
    con.close()
    assert n == 1
    assert len(latest["candidates"]) == len(base["candidates"])  # repaired: all candidates back


@respx.mock
def test_repaired_race_is_not_remerged_again(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    arch = Archive(con, tmp_path)
    arch.persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    good = search_refresh.merge(base, _row(base, [c["votes"] for c in base["candidates"]], 0), T0)
    arch.persist(AZ06, good, datetime(2026, 11, 4, 0, 30, tzinfo=UTC), False)
    assert search_refresh.needs_repair(con, [AZ06]) == set()
    con.close()


def test_merge_matches_candidate_id_across_party_labels() -> None:
    """civicAPI labelled Ben Ray Lujan 'Nonpartisan' in the race payload and 'Democratic' in
    search; matching on name+party duplicated him under the same candidate_id."""
    base = {
        "candidates": [
            {"name": "Ben Ray Lujan", "party": "Nonpartisan", "candidate_id": 220790, "votes": 10}
        ]
    }
    out = search_refresh.merge(
        base,
        {
            "percent_reporting": 40,
            "candidates": [
                {
                    "name": "Ben Ray Lujan",
                    "party": "Democratic",
                    "candidate_id": 220790,
                    "votes": 99,
                }
            ],
        },
        T0,
    )
    assert out["candidates"] == [
        {"name": "Ben Ray Lujan", "party": "Nonpartisan", "candidate_id": 220790, "votes": 99}
    ]


@respx.mock
def test_changed_totals_report_their_race_ids(tmp_path) -> None:
    base = json.loads((CIVIC / "race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    Archive(con, tmp_path).persist(AZ06, base, datetime(2026, 11, 4, 0, 0, tzinfo=UTC), False)
    con.close()
    votes = [500 + i for i in range(len(base["candidates"]))]
    n, changed = _run_full(tmp_path, _row(base, votes, 9.0))
    assert (n, changed) == (1, [AZ06])


def test_base_payload_older_than_the_recent_window_is_still_found(tmp_path) -> None:
    """The newest race-endpoint payload is looked for among recent snapshots first; a race
    with none there still gets its older one, never a search merge."""
    base = json.loads((CIVIC / "race_86922.json").read_text())
    merged = dict(base, percent_reporting=50.0, _source="search")
    con = connect(tmp_path)
    init_db(con)
    arch = Archive(con, tmp_path)
    arch.persist(AZ06, base, datetime(2026, 11, 3, 12, 0, tzinfo=UTC), False)
    arch.persist(AZ06, merged, T0, False)  # 13 h later: outside the recent window
    found = search_refresh.latest_payloads(con, [AZ06])[AZ06]
    newest_cands = search_refresh.latest_signatures(con, [AZ06])[AZ06]
    con.close()
    assert "_source" not in found and found["percent_reporting"] == base["percent_reporting"]
    assert newest_cands == search_refresh.signature(50.0, base["candidates"])


def test_connect_caps_duckdb_memory(tmp_path) -> None:
    """Uncapped, DuckDB takes 80% of RAM and the kernel kills the archiver instead."""
    import duckdb

    con = connect(tmp_path)
    capped = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    con.close()
    assert (
        capped != duckdb.connect().execute("SELECT current_setting('memory_limit')").fetchone()[0]
    )
