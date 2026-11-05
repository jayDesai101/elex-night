"""Backfill snapshots from civicAPI's race history (/race/{id}/history[/{timestamp}]).

Safe to run while the archiver is live: one read connection at the start, all fetching with
no DuckDB lock held, then one short write connection at the end. (The archiver holds the
lock for nearly its whole cycle, so every extra connection means waiting for a gap.)
Backfilled snapshots are older than what stg_civic__region_results has already loaded,
so we leave a FULL_REFRESH flag and the archiver's next cycle rebuilds that incremental
model.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from elex.civic.client import CivicClient, Fetch
from elex.db import connect, init_db
from elex.ingest.archive import canonical_json, raw_path, schema_error, sha256_hex, write_raw

log = logging.getLogger(__name__)

# History timestamps trail the payload's last_updated by ~0.1 s; anything this close to a
# snapshot we already hold is the same state and is not fetched again.
SAME_STATE_WITHIN = timedelta(seconds=5)
FULL_REFRESH_FLAG = "FULL_REFRESH"
# The archiver holds the write lock for a whole cycle (longer on start-up, with discovery);
# a background backfill waits for the gap between cycles.
LOCK_WAIT_S = 300


def full_refresh_flag(data_dir: Path) -> Path:
    return data_dir / "warehouse" / FULL_REFRESH_FLAG


@dataclass
class RaceState:
    hashes: set[str]
    source_ts: list[datetime]


@dataclass
class BackfillResult:
    races: int = 0
    no_history: int = 0
    listed: int = 0
    fetched: int = 0
    inserted: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)


def known_state(data_dir: Path, race_ids: list[int] | None) -> dict[int, RaceState]:
    con = connect(data_dir, read_only=True, retries=LOCK_WAIT_S)
    try:
        where = "" if race_ids is None else f"WHERE race_id IN ({','.join(map(str, race_ids))})"
        races = (
            race_ids
            if race_ids is not None
            else [r[0] for r in con.execute("SELECT race_id FROM bronze.race_catalog").fetchall()]
        )
        state = {rid: RaceState(set(), []) for rid in races}
        for rid, sha, ts in con.execute(
            "SELECT race_id, content_sha256, source_last_updated "
            f"FROM bronze.race_snapshots {where}"
        ).fetchall():
            st = state.setdefault(rid, RaceState(set(), []))
            st.hashes.add(sha)
            if ts is not None:
                st.source_ts.append(ts.astimezone(UTC))
        return state
    finally:
        con.close()


def _already_have(ts: datetime, st: RaceState) -> bool:
    return any(abs(ts - known) <= SAME_STATE_WITHIN for known in st.source_ts)


async def backfill(
    client: CivicClient,
    data_dir: Path,
    race_ids: list[int] | None = None,
    concurrency: int = 2,
) -> BackfillResult:
    state = known_state(data_dir, race_ids)
    res = BackfillResult(races=len(state))
    run_id = uuid.uuid4()
    sem = asyncio.Semaphore(concurrency)
    pending_logs: list[tuple[int, str, Fetch, str | None, bool | None, datetime]] = []
    pending_rows: list[tuple] = []

    async def one(race_id: int) -> None:
        async with sem:
            logs: list[tuple[str, Fetch, str | None, bool | None, datetime]] = []
            listing = await client.get(f"/race/{race_id}/history")
            logs.append(("history", listing, None, None, datetime.now(UTC)))
            if listing.status == 404:
                res.no_history += 1  # no snapshots yet: normal, see api_contract.md
                pending_logs.extend((race_id, *entry) for entry in logs)
                return
            if listing.error or not isinstance(listing.data, dict):
                res.errors.append(f"{race_id}: history list {listing.error}")
                pending_logs.extend((race_id, *entry) for entry in logs)
                return
            st = state[race_id]
            stamps = [_parse_ts(t) for t in listing.data.get("timestamps", [])]
            res.listed += len(stamps)
            rows = []
            for ts in sorted(stamps):
                if _already_have(ts, st):
                    continue
                iso = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
                f = await client.get(f"/race/{race_id}/history/{iso}")
                res.fetched += 1
                data = f.data.get("data") if isinstance(f.data, dict) else None
                if f.error or not isinstance(data, dict):
                    logs.append(("history", f, None, None, datetime.now(UTC)))
                    res.errors.append(f"{race_id}@{iso}: {f.error or 'no data'}")
                    continue
                body = canonical_json(data)
                sha = sha256_hex(body)
                is_new = sha not in st.hashes
                logs.append(("history", f, sha, is_new, datetime.now(UTC)))
                if not is_new:
                    continue
                path = raw_path(data_dir, race_id, ts, sha)
                write_raw(path, body)  # raw first, as in the live archive
                err = schema_error(data)
                if err:
                    res.errors.append(f"{race_id}@{iso}: {err}")
                    continue
                st.hashes.add(sha)
                st.source_ts.append(ts)
                rows.append((race_id, ts, data.get("last_updated"), sha, str(path), body))
            pending_logs.extend((race_id, *entry) for entry in logs)
            pending_rows.extend(rows)

    await asyncio.gather(*(one(rid) for rid in state))
    res.inserted = _write(data_dir, run_id, pending_logs, pending_rows)
    if res.inserted:
        full_refresh_flag(data_dir).touch()
    return res


def _write(data_dir: Path, run_id, logs, rows) -> int:
    """One short write connection for the whole run: request log rows plus new snapshots."""
    con = connect(data_dir, retries=LOCK_WAIT_S)
    inserted = 0
    try:
        init_db(con)
        for race_id, endpoint, f, sha, is_new, at in logs:
            con.execute(
                "INSERT INTO bronze.ingest_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    uuid.uuid4(),
                    run_id,
                    at,
                    endpoint,
                    race_id,
                    f.status,
                    f.latency_ms,
                    f.nbytes,
                    sha,
                    is_new,
                    None if f.status == 404 else f.error,
                ],
            )
        for rid, ts, source_ts, sha, path, body in rows:
            # fetched_at = the history timestamp; ON CONFLICT guards a rerun racing a live poll
            n = con.execute(
                "INSERT INTO bronze.race_snapshots VALUES (?, ?, ?, ?, ?, false, ?, ?) "
                "ON CONFLICT DO NOTHING RETURNING 1",
                [uuid.uuid4(), rid, ts, source_ts, sha, path, body.decode()],
            ).fetchall()
            inserted += len(n)
    finally:
        con.close()
    return inserted


def summary(res: BackfillResult) -> str:
    return json.dumps(
        {k: v for k, v in res.__dict__.items() if k != "errors"} | {"errors": len(res.errors)}
    )
