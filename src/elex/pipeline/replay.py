"""Chunk 11: re-run the night from the archive with a simulated clock.

The live archive (ELEX_DATA_DIR) is read-only here. Snapshots are copied into a separate
data dir in order of fetched_at, and at each step the normal transform -> model -> export
runs, producing serving versions as they would have been at that time. Combined with
static_export this yields the replay the dashboard scrubs through.
"""

import json
import logging
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from elex.db import connect, db_path, init_db
from elex.model.run import run as model_run
from elex.pipeline.export import export
from elex.pipeline.transform import rebuild_in_chunks, run_dbt_build

log = logging.getLogger(__name__)

BRONZE_TABLES = ("race_catalog", "race_snapshots", "ingest_log")
REF_TABLES = ("county_baseline", "county_features", "state_turnout_prior")


def snapshot_archive(src: Path, dst: Path, wait_s: int = 300) -> Path:
    """A private copy of the live warehouse to read from. The archiver holds the file lock
    for most of each cycle, so we wait for a gap, then copy the file and its WAL together
    (a copy taken mid-write can be inconsistent)."""
    live = db_path(src)
    copy = dst / "live_copy.duckdb"
    deadline = time.monotonic() + wait_s
    while True:
        try:
            duckdb.connect(str(live), read_only=True).close()  # succeeds only in a gap
            shutil.copy2(live, copy)
            wal = live.with_suffix(".duckdb.wal")
            if wal.exists():
                shutil.copy2(wal, copy.with_suffix(".duckdb.wal"))
            duckdb.connect(str(copy), read_only=True).close()  # replays the WAL, validates
            return copy
        except duckdb.IOException:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


def prepare(src: Path, dst: Path) -> Path:
    """Fresh replay warehouse: catalog + reference data from the live one, no snapshots yet.
    Returns the private copy of the live archive that later steps read from."""
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "warehouse").mkdir(parents=True)
    src_copy = snapshot_archive(src, dst)
    con = connect(dst)
    init_db(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS ref")
    con.execute(f"ATTACH '{src_copy}' AS live (READ_ONLY)")
    con.execute("INSERT INTO bronze.race_catalog SELECT * FROM live.bronze.race_catalog")
    for t in REF_TABLES:
        con.execute(f"CREATE OR REPLACE TABLE ref.{t} AS SELECT * FROM live.ref.{t}")
    con.execute("DETACH live")
    con.close()
    return src_copy


def snapshot_times(src_copy: Path, start: datetime, end: datetime) -> list[datetime]:
    con = duckdb.connect(str(src_copy), read_only=True)
    try:
        rows = con.execute(
            "SELECT DISTINCT fetched_at FROM bronze.race_snapshots "
            "WHERE fetched_at BETWEEN ? AND ? ORDER BY 1",
            [start, end],
        ).fetchall()
    finally:
        con.close()
    return [r[0].astimezone(UTC) for r in rows]


def copy_until(src_copy: Path, dst: Path, upto: datetime) -> int:
    """Copy snapshots (and their ingest_log rows) with fetched_at <= upto not yet in dst."""
    con = connect(dst)
    try:
        con.execute(f"ATTACH '{src_copy}' AS live (READ_ONLY)")
        n = con.execute(
            """INSERT INTO bronze.race_snapshots
               SELECT * FROM live.bronze.race_snapshots s WHERE s.fetched_at <= ?
                 AND NOT EXISTS (SELECT 1 FROM bronze.race_snapshots d
                                 WHERE d.snapshot_id = s.snapshot_id)""",
            [upto],
        ).fetchone()
        con.execute(
            """INSERT INTO bronze.ingest_log
               SELECT * FROM live.bronze.ingest_log l WHERE l.requested_at <= ?
                 AND NOT EXISTS (SELECT 1 FROM bronze.ingest_log d
                                 WHERE d.request_id = l.request_id)""",
            [upto],
        )
        con.execute("DETACH live")
        return int(n[0]) if n else 0
    finally:
        con.close()


def build_and_export(dst: Path, at: datetime, full_refresh: bool = False) -> str | None:
    tr = rebuild_in_chunks(db_path(dst)) if full_refresh else run_dbt_build(db_path(dst))
    if not tr.success or tr.errors:
        failed = [c["name"] for c in tr.checks if c["status"] in ("fail", "error")]
        log.warning("replay %s: dbt errors=%s %s (%s)", at, tr.errors, failed, tr.error)
        return None
    con = connect(dst)
    try:
        model_run(con)
        # every step's version must survive: the static export reads them all afterwards
        return export(con, dst, at, keep=None)
    finally:
        con.close()


def replay(
    src: Path,
    dst: Path,
    start: datetime,
    end: datetime,
    every: timedelta = timedelta(minutes=10),
    on_step: Callable[[datetime, str | None], None] | None = None,
) -> list[tuple[datetime, str | None]]:
    """Walk the archive in `every` steps; at each step build + export the warehouse as it
    stood then. Returns (step time, serving version) pairs."""
    src_copy = prepare(src, dst)
    out: list[tuple[datetime, str | None]] = []
    t = start
    first = True
    while t <= end:
        copied = copy_until(src_copy, dst, t)
        version = build_and_export(dst, t, full_refresh=first) if (copied or first) else None
        if version is None and out:
            version = out[-1][1]  # nothing new: the previous version still stands
        out.append((t, version))
        if on_step:
            on_step(t, version)
        first = False
        t += every
    (dst / "replay.json").write_text(
        json.dumps([{"t": s.isoformat(), "version": v} for s, v in out], indent=1)
    )
    return out
