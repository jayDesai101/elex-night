"""Race-level totals for every race from civicAPI search, one request per page.

On election night civicAPI answered single-race requests in ~22 s, so polling 509 races one
by one could not keep up (435 House races ~40 min per pass). One search page (~23 s) returns
every federal race's candidate totals and percent reporting. When a race's totals change,
we archive its latest full payload with candidates and percent_reporting updated from the
search row (county detail keeps coming from the normal race polls). Such snapshots carry
"_source": "search".
"""

import asyncio
import copy
import json
import logging
from datetime import datetime

import duckdb

from elex.civic.client import SEARCH_TIMEOUT_S, CivicClient
from elex.ingest.archive import Archive
from elex.ingest.discover import ELECTION_DAY, PAGE_LIMIT

log = logging.getLogger(__name__)

# General holds Senate + House; Statewide holds Governor (docs/api_contract.md)
SEARCH_TYPES = ("General", "Statewide")


def signature(pct, candidates) -> tuple:
    """What a search row can tell us: percent reporting and each candidate's votes."""
    return (
        round(float(pct or 0), 1),
        tuple(
            sorted((c.get("name"), c.get("party"), int(c.get("votes") or 0)) for c in candidates)
        ),
    )


def is_newer(row_sig: tuple, known_sig: tuple) -> bool:
    """Accept a search row only if it moves the race forward: more votes, or the same votes
    at a higher percent reporting. Search may lag the race endpoint, and taking an older
    row would make counts go backwards; real downward corrections still arrive through the
    normal race polls."""
    row_total = sum(v for *_, v in row_sig[1])
    known_total = sum(v for *_, v in known_sig[1])
    return row_total > known_total or (row_total == known_total and row_sig[0] > known_sig[0])


def merge(payload: dict, row: dict, fetched_at: datetime) -> dict:
    """Latest full payload with race-level totals from a search row."""
    out = copy.deepcopy(payload)
    # Keep every candidate of the race payload (county results reference them all) and
    # update the ones search reports; add any candidate only search knows. Match on
    # candidate_id first: civicAPI sometimes labels the same candidate's party differently
    # in search and race payloads (e.g. "Nonpartisan" vs "Democratic"). Name and party stay
    # as the race payload has them, so county results still join.
    merged = [dict(c) for c in out.get("candidates", [])]
    by_id = {c["candidate_id"]: c for c in merged if c.get("candidate_id") is not None}
    by_key = {(c.get("name"), c.get("party")): c for c in merged}
    for rc in row.get("candidates", []):
        c = by_id.get(rc.get("candidate_id")) or by_key.get((rc.get("name"), rc.get("party")))
        if c is None:
            c = {k: rc[k] for k in ("name", "party", "candidate_id") if k in rc}
            merged.append(c)
        c.update({k: rc[k] for k in ("votes", "percent", "winner") if k in rc})
    out["candidates"] = merged
    out["percent_reporting"] = row.get("percent_reporting", out.get("percent_reporting"))
    # civicAPI's own last_updated is not in search rows: keep the one from the race
    # payload (it is what "updated N min ago" should show) and record our fetch time as
    # the change marker the light poll compares against (archive.latest_source_ts).
    out["_merged_at"] = fetched_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out["_source"] = "search"
    return out


NOT_SEARCH = "AND coalesce(payload->>'$._source', '') <> 'search'"
RECENT_HOURS = 6


def _latest(
    con: duckdb.DuckDBPyConnection, columns: str, race_ids: list[int], where: str = ""
) -> list[tuple]:
    """`columns` (race_id first) of each race's newest snapshot, among those matching `where`.

    The newest snapshot is chosen on narrow columns and only then is its payload read. A
    window over the payloads themselves holds every archived payload in memory (7 GB two
    days after the election): the kernel killed the archiver for it, on every restart."""
    ids = ",".join(map(str, race_ids))
    return con.execute(
        f"""SELECT {columns} FROM bronze.race_snapshots
            WHERE snapshot_id IN (
                SELECT arg_max(snapshot_id, fetched_at) FROM bronze.race_snapshots
                WHERE race_id IN ({ids}) {where} GROUP BY race_id)"""
    ).fetchall()


def _latest_base(con: duckdb.DuckDBPyConnection, columns: str, race_ids: list[int]) -> list[tuple]:
    """Same, among race-endpoint snapshots only (search merges excluded). Telling the two
    apart means parsing payloads, so recent snapshots are tried first and the whole
    archive is read only for the races that have none."""
    recent = (
        "AND fetched_at > (SELECT max(fetched_at) FROM bronze.race_snapshots)"
        f" - INTERVAL {RECENT_HOURS} HOUR"
    )
    rows = _latest(con, columns, race_ids, f"{recent} {NOT_SEARCH}")
    found = {r[0] for r in rows}
    missing = [rid for rid in race_ids if rid not in found]
    if missing:
        rows += _latest(con, columns, missing, NOT_SEARCH)
    return rows


def needs_repair(con: duckdb.DuckDBPyConnection, race_ids: list[int]) -> set[int]:
    """Races whose newest snapshot is a search merge with fewer candidates than the latest
    race-endpoint payload (merges made before candidates were kept). Re-merged until fixed."""
    if not race_ids:
        return set()
    count = "json_array_length(payload->'$.candidates')"
    newest = _latest(con, f"race_id, payload->>'$._source', {count}", race_ids)
    merged = {rid: n for rid, source, n in newest if source == "search" and n is not None}
    if not merged:
        return set()
    base = _latest_base(con, f"race_id, {count}", sorted(merged))
    return {rid for rid, n in base if n is not None and merged[rid] < n}


def latest_signatures(con: duckdb.DuckDBPyConnection, race_ids: list[int]) -> dict[int, tuple]:
    if not race_ids:
        return {}
    rows = _latest(
        con, "race_id, payload->>'$.percent_reporting', payload->'$.candidates'", race_ids
    )
    return {rid: signature(pct, json.loads(cands or "[]")) for rid, pct, cands in rows}


def latest_payloads(con: duckdb.DuckDBPyConnection, race_ids: list[int]) -> dict[int, dict]:
    """Latest payload from the race endpoint itself: merges never build on earlier merges."""
    if not race_ids:
        return {}
    return {rid: json.loads(p) for rid, p in _latest_base(con, "race_id, payload", race_ids)}


async def refresh(
    client: CivicClient,
    con: duckdb.DuckDBPyConnection,
    archive: Archive,
    catalog: set[int],
    log_request,
    clock,
    test_flag: bool,
    remerge: bool = True,
) -> tuple[int, list[int]]:
    """Fetch search pages, archive races whose totals changed.
    Returns (new snapshots, race ids whose totals changed)."""

    async def page(etype: str):
        params = {
            "country": "US",
            "start_date": ELECTION_DAY,
            "end_date": ELECTION_DAY,
            "election_type": etype,
            "limit": PAGE_LIMIT,
            "offset": 0,
        }
        # One attempt, both searches in parallel: the refresh repeats every 90 s, and
        # sequential retries of slow searches kept cycles waiting for minutes.
        return etype, await client.get("/race/search", params, timeout=SEARCH_TIMEOUT_S, attempts=1)

    rows: dict[int, dict] = {}
    for etype, f in await asyncio.gather(*(page(t) for t in SEARCH_TYPES)):
        log_request("search", None, f)
        if f.error or not isinstance(f.data, dict):
            log.warning("search refresh %s failed: %s", etype, f.error)
            continue
        for r in f.data.get("races", []):
            rid = r.get("id")
            if rid in catalog and str(r.get("election_date", "")).startswith(ELECTION_DAY):
                rows[int(rid)] = r
    if not rows:
        return 0, []
    known = latest_signatures(con, list(rows))
    changed = [
        rid
        for rid, r in rows.items()
        if rid in known
        and is_newer(signature(r.get("percent_reporting"), r.get("candidates", [])), known[rid])
    ]
    if remerge:
        changed = sorted(set(changed) | needs_repair(con, list(rows)))
    if not changed:
        return 0, []
    base = latest_payloads(con, changed)
    now = clock()
    new = 0
    for rid in changed:
        if rid not in base:
            continue
        res = archive.persist(rid, merge(base[rid], rows[rid], now), now, test_flag)
        new += res.is_new
    log.info("search refresh: %d races changed, %d new snapshots", len(changed), new)
    return new, changed
