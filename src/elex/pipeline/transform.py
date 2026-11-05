"""Cycle step 6: `dbt build`; DQ check results go to ops.dq_results.

dbt runs in a subprocess, not in-process via dbtRunner: dbt-duckdb keeps its connection
to the file open after invoke() returns, and a second connection with different settings
then fails, so the cycle could not reopen the warehouse. A subprocess always releases it.
The caller must still close its own connection before calling run_dbt_build.
"""

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)

DBT_DIR = Path("dbt")
FULL_REFRESH_TIMEOUT_S = 1800
DQ_DDL = """
CREATE TABLE IF NOT EXISTS ops.dq_results (
  checked_at TIMESTAMPTZ NOT NULL, cycle_id UUID, name VARCHAR NOT NULL,
  status VARCHAR NOT NULL, failures INTEGER, detail VARCHAR)
"""


@dataclass
class TransformResult:
    success: bool
    errors: int = 0
    warnings: int = 0
    checks: list[dict] = field(default_factory=list)
    error: str | None = None


def run_dbt_build(
    db_path: Path,
    target: str = "dev",
    project_dir: Path = DBT_DIR,
    extra_args: list[str] | None = None,
    timeout_s: int | None = None,
) -> TransformResult:
    """Run dbt build against db_path. Errors = failed error-severity tests or model errors.

    A full refresh re-parses every archived region row (minutes on a night's archive), so it
    gets a longer timeout than the incremental build that runs every cycle."""
    if timeout_s is None:
        timeout_s = FULL_REFRESH_TIMEOUT_S if "--full-refresh" in (extra_args or []) else 300
    target_path = db_path.resolve().parent / f"dbt_target_{target}"
    dbt_bin = Path(sys.executable).parent / "dbt"
    args = [
        str(dbt_bin),
        "build",
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(project_dir),
        "--target",
        target,
        "--target-path",
        str(target_path),
        "--quiet",
        *(extra_args or []),
    ]
    env_key = "ELEX_DUCKDB_PATH" if target == "dev" else "ELEX_DUCKDB_TEST_PATH"
    env = {**os.environ, env_key: str(db_path.resolve())}
    started = time.time()
    try:
        proc = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return TransformResult(False, errors=1, error=f"dbt timed out after {timeout_s} s")
    results_file = target_path / "run_results.json"
    if not results_file.exists() or results_file.stat().st_mtime < started:
        tail = (proc.stdout + proc.stderr)[-500:]
        return TransformResult(False, errors=1, error=f"dbt exit {proc.returncode}: {tail}")
    out = TransformResult(success=proc.returncode == 0)
    for r in json.loads(results_file.read_text())["results"]:
        uid, status = r["unique_id"], r["status"]
        name = uid.split(".")[2]
        if uid.startswith("test."):
            out.checks.append(
                {
                    "name": name,
                    "status": status,
                    "failures": r.get("failures"),
                    "detail": (r.get("message") or "")[:500] or None,
                }
            )
            if status in ("fail", "error"):
                out.errors += 1
            elif status == "warn":
                out.warnings += 1
        elif status == "error":
            out.errors += 1
            out.error = f"{name}: {(r.get('message') or '')[:300]}"
    if not out.success and out.errors == 0:
        out.errors = 1
        out.error = f"dbt exit {proc.returncode}: {(proc.stdout + proc.stderr)[-300:]}"
    return out


CHUNK_SNAPSHOTS = 1500  # a peak election-night hour; ~200 MB of JSON, well inside 4 GB


def rebuild_in_chunks(
    db_path: Path,
    target: str = "dev",
    project_dir: Path = DBT_DIR,
    chunk_snapshots: int = CHUNK_SNAPSHOTS,
) -> TransformResult:
    """Rebuild the incremental region model from the whole archive without a single giant
    query: truncate it, then run the normal incremental build repeatedly with `load_until`
    advancing over the archive `chunk_snapshots` snapshots at a time (boundaries come from
    the archive's own timestamps, so sparse weeks before the election cost nothing). The
    final unbounded build runs everything else, marts and tests, as a normal build would."""
    import duckdb

    con = duckdb.connect(str(db_path))
    try:
        bounds = [
            r[0]
            for r in con.execute(
                """WITH t AS (SELECT fetched_at, row_number() OVER (ORDER BY fetched_at) AS n
                              FROM bronze.race_snapshots)
                   SELECT max(fetched_at) FROM t GROUP BY (n - 1) // ? ORDER BY 1""",
                [chunk_snapshots],
            ).fetchall()
        ]
        con.execute("DROP TABLE IF EXISTS silver.stg_civic__region_results")
    finally:
        con.close()
    last: TransformResult | None = None
    for bound in bounds[:-1]:  # the last window is covered by the final unbounded build
        last = run_dbt_build(
            db_path,
            target,
            project_dir,
            # the model only: its tests (e.g. regions add up to race totals) cannot pass on
            # a partial table; the final unbounded build runs them
            extra_args=[
                "--select",
                "stg_civic__region_results",
                "--exclude-resource-type",
                "test",
                "--vars",
                f"{{load_until: '{bound.isoformat()}'}}",
            ],
        )
        if not last.success or last.errors:
            last.error = f"chunk to {bound:%Y-%m-%d %H:%M}: {last.error}"
            return last
    return run_dbt_build(db_path, target, project_dir)


def record_checks(con: duckdb.DuckDBPyConnection, cycle_id, result: TransformResult) -> None:
    con.execute(DQ_DDL)
    now = datetime.now(UTC)
    for c in result.checks:
        con.execute(
            "INSERT INTO ops.dq_results VALUES (?, ?, ?, ?, ?, ?)",
            [now, cycle_id, c["name"], c["status"], c["failures"], c["detail"]],
        )
