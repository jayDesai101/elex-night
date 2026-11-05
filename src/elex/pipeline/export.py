"""Cycle step 8: gold and model tables -> a versioned Parquet snapshot + atomic CURRENT pointer.

The API reads only these files, never the warehouse, so DuckDB's one-writer rule cannot
bite and a failure after the archive never takes the dashboard down (ADR-002).
"""

import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)

GOLD_TABLES = (
    "fct_race_latest",
    "fct_county_latest",
    "fct_county_timeseries",
    "fct_race_timeseries",
    "fct_chamber_summary",
    "fct_pipeline_health",
)
MODEL_TABLES = ("projection_latest", "projection_history")
KEEP_VERSIONS = 20
LATENCY_CYCLES = 60

LATENCY_SQL = """
SELECT r.started_at AS t, median(l.latency_ms) AS p50_ms
FROM ops.pipeline_runs r JOIN bronze.ingest_log l USING (cycle_id)
WHERE l.error IS NULL
GROUP BY r.cycle_id, r.started_at
ORDER BY r.started_at DESC
LIMIT {n}
"""
DQ_SQL = """
SELECT name, status, failures, detail, checked_at FROM ops.dq_results
QUALIFY row_number() OVER (PARTITION BY name ORDER BY checked_at DESC) = 1
"""


def serving_root(data_dir: Path) -> Path:
    return data_dir / "serving"


def write_heartbeat(data_dir: Path, at: datetime) -> None:
    """Last time the archiver polled, written every cycle (exports happen only on change)."""
    root = serving_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "HEARTBEAT.tmp"
    tmp.write_text(at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    os.replace(tmp, root / "HEARTBEAT")


def read_heartbeat(data_dir: Path) -> datetime | None:
    try:
        raw = (serving_root(data_dir) / "HEARTBEAT").read_text().strip()
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (FileNotFoundError, ValueError):
        return None


def current_version(data_dir: Path) -> str | None:
    """The version CURRENT points at, or None if there is none (or it is dangling)."""
    pointer = serving_root(data_dir) / "CURRENT"
    try:
        version = pointer.read_text().strip()
    except FileNotFoundError:
        return None
    return version if version and (serving_root(data_dir) / version).is_dir() else None


def _exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(
        con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()[0]
    )


def _copy(con: duckdb.DuckDBPyConnection, query: str, path: Path) -> None:
    con.execute(f"COPY ({query}) TO '{path}' (FORMAT parquet)")


def export(
    con: duckdb.DuckDBPyConnection,
    data_dir: Path,
    now: datetime | None = None,
    keep: int | None = KEEP_VERSIONS,
) -> str:
    """Write a new version and swap CURRENT to it. Returns the version name."""
    now = now or datetime.now(UTC)
    root = serving_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    base = "v" + now.strftime("%Y%m%dT%H%M%SZ")
    version, n = base, 0
    while (root / version).exists():
        n += 1
        version = f"{base}-{n}"
    tmp = root / f"{version}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        for table in GOLD_TABLES:  # a missing gold table means dbt has not built: an error
            _copy(con, f"SELECT * FROM gold.{table}", tmp / f"{table}.parquet")
        for table in MODEL_TABLES:  # the model is optional until Chunk 8 and can be disabled
            if _exists(con, "model", table):
                _copy(con, f"SELECT * FROM model.{table}", tmp / f"{table}.parquet")
        _copy(con, LATENCY_SQL.format(n=LATENCY_CYCLES), tmp / "latency.parquet")
        if _exists(con, "ops", "dq_results"):
            _copy(con, DQ_SQL, tmp / "dq_checks.parquet")
        os.replace(tmp, root / version)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    pointer_tmp = root / "CURRENT.tmp"
    pointer_tmp.write_text(version)
    os.replace(pointer_tmp, root / "CURRENT")
    if keep is not None:
        _prune(root, keep)
    log.info("exported %s", version)
    return version


def _prune(root: Path, keep: int = KEEP_VERSIONS) -> None:
    versions = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name.startswith("v"))
    for stale in [v for v in versions if v.endswith(".tmp")]:
        shutil.rmtree(root / stale, ignore_errors=True)
    finished = [v for v in versions if not v.endswith(".tmp")]
    for old in finished[:-keep]:
        shutil.rmtree(root / old, ignore_errors=True)
