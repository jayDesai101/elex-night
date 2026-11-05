"""DuckDB connection and the bronze/ops DDL (created here, never by dbt)."""

import os
import time
from pathlib import Path

import duckdb

from elex.config import get_settings

DDL = """
CREATE SCHEMA IF NOT EXISTS bronze; CREATE SCHEMA IF NOT EXISTS ops;
CREATE TABLE IF NOT EXISTS bronze.ingest_log (
  request_id UUID PRIMARY KEY, cycle_id UUID NOT NULL,
  requested_at TIMESTAMPTZ NOT NULL,
  endpoint VARCHAR NOT NULL,
  race_id BIGINT, http_status INTEGER, latency_ms INTEGER, bytes INTEGER,
  content_sha256 VARCHAR, is_new_content BOOLEAN, error VARCHAR);
CREATE TABLE IF NOT EXISTS bronze.race_catalog (
  race_id BIGINT PRIMARY KEY, election_name VARCHAR, election_type VARCHAR,
  election_scope VARCHAR, province VARCHAR, district VARCHAR,
  office VARCHAR NOT NULL,
  tier VARCHAR NOT NULL,
  discovered_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS bronze.race_snapshots (
  snapshot_id UUID PRIMARY KEY, race_id BIGINT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL, source_last_updated TIMESTAMPTZ,
  content_sha256 VARCHAR NOT NULL, test_data BOOLEAN NOT NULL,
  raw_path VARCHAR NOT NULL, payload JSON NOT NULL,
  UNIQUE (race_id, fetched_at));
CREATE SCHEMA IF NOT EXISTS ref;
-- Placeholder so gold models can join it before `elex load-ref` replaces it.
CREATE TABLE IF NOT EXISTS ref.county_baseline (
  county_fips VARCHAR, state_po VARCHAR, county_name VARCHAR,
  pres20_dem BIGINT, pres20_rep BIGINT, pres20_total BIGINT,
  pres24_dem BIGINT, pres24_rep BIGINT, pres24_total BIGINT);
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
  cycle_id UUID PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
  status VARCHAR,
  requests INTEGER, new_snapshots INTEGER, dq_errors INTEGER, dq_warnings INTEGER,
  model_status VARCHAR, serving_version VARCHAR, error VARCHAR);
"""


# DuckDB assumes it may use 80% of RAM. This host has less than that free next to its
# other containers, and past it the kernel kills the archiver. With a cap DuckDB spills to
# disk instead (dbt has its own cap in dbt/profiles.yml).
MEMORY_LIMIT = os.environ.get("ELEX_DUCKDB_PY_MEMORY", "4GB")


def db_path(data_dir: Path | None = None) -> Path:
    return (data_dir or get_settings().data_dir) / "warehouse" / "elex.duckdb"


def connect(
    data_dir: Path | None = None, read_only: bool = False, retries: int = 0
) -> duckdb.DuckDBPyConnection:
    """Open the warehouse. The archiver holds the write lock only during a cycle, so
    read-only callers (elex sql) retry briefly instead of failing on a lock."""
    path = db_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            con = duckdb.connect(str(path), read_only=read_only)
            con.execute("SET TimeZone='UTC'")
            con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
            return con
        except duckdb.IOException:
            if attempt == retries:
                raise
            time.sleep(1.0)
    raise AssertionError("unreachable")


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)


def snapshot_copy(data_dir: Path | None = None, wait_s: int = 120) -> Path:
    """Copy the warehouse (with its WAL) into a temp dir during a gap between archiver
    cycles. The copy is private: querying it holds no lock on the live file."""
    import shutil
    import tempfile

    live = db_path(data_dir)
    tmp = Path(tempfile.mkdtemp(prefix="elex-wh-"))
    copy = tmp / live.name
    deadline = time.monotonic() + wait_s
    while True:
        try:
            duckdb.connect(str(live), read_only=True).close()  # only succeeds in a gap
            shutil.copy2(live, copy)
            wal = live.with_suffix(".duckdb.wal")
            if wal.exists():
                shutil.copy2(wal, copy.with_suffix(".duckdb.wal"))
            duckdb.connect(str(copy), read_only=True).close()  # replays the WAL, validates
            return copy
        except duckdb.IOException:
            if time.monotonic() > deadline:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            time.sleep(1)


def query_snapshot(query: str, data_dir: Path | None = None) -> str:
    """Run a read-only query on a private copy of the warehouse and remove the copy."""
    import shutil

    copy = snapshot_copy(data_dir)
    try:
        con = duckdb.connect(str(copy), read_only=True)
        try:
            con.execute("SET TimeZone='UTC'")
            return str(con.sql(query))
        finally:
            con.close()
    finally:
        shutil.rmtree(copy.parent, ignore_errors=True)
