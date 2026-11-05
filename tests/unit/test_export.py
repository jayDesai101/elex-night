from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from elex.pipeline.export import GOLD_TABLES, KEEP_VERSIONS, current_version, export, serving_root


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("SET TimeZone='UTC'")
    for schema in ("gold", "ops", "bronze"):
        c.execute(f"CREATE SCHEMA {schema}")
    for t in GOLD_TABLES:
        c.execute(f"CREATE TABLE gold.{t} AS SELECT 1 AS a")
    c.execute("CREATE TABLE ops.pipeline_runs (cycle_id UUID, started_at TIMESTAMPTZ)")
    c.execute("CREATE TABLE bronze.ingest_log (cycle_id UUID, latency_ms INTEGER, error VARCHAR)")
    c.execute("INSERT INTO ops.pipeline_runs VALUES (uuid(), now())")
    c.execute("INSERT INTO bronze.ingest_log SELECT cycle_id, 100, NULL FROM ops.pipeline_runs")
    return c


T0 = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)


def test_export_writes_version_and_points_current(con, tmp_path) -> None:
    v = export(con, tmp_path, T0)
    assert v == "v20261104T010000Z"
    assert current_version(tmp_path) == v
    files = {p.name for p in (serving_root(tmp_path) / v).iterdir()}
    assert {f"{t}.parquet" for t in GOLD_TABLES} | {"latency.parquet"} <= files
    # model and dq tables are absent: skipped, not errors
    assert "projection_latest.parquet" not in files and "dq_checks.parquet" not in files
    assert not (serving_root(tmp_path) / "CURRENT.tmp").exists()


def test_model_and_dq_tables_exported_when_present(con, tmp_path) -> None:
    con.execute("CREATE SCHEMA model")
    con.execute("CREATE TABLE model.projection_latest AS SELECT 1 AS race_id")
    con.execute("CREATE TABLE model.projection_history AS SELECT 1 AS race_id")
    con.execute(
        "CREATE TABLE ops.dq_results (name VARCHAR, status VARCHAR, failures INTEGER, "
        "detail VARCHAR, checked_at TIMESTAMPTZ)"
    )
    con.execute("INSERT INTO ops.dq_results VALUES ('t', 'pass', 0, NULL, now() - INTERVAL 1 DAY)")
    con.execute("INSERT INTO ops.dq_results VALUES ('t', 'warn', 3, 'x', now())")
    v = export(con, tmp_path, T0)
    d = serving_root(tmp_path) / v
    assert (d / "projection_latest.parquet").exists()
    latest = duckdb.sql(f"select status from read_parquet('{d}/dq_checks.parquet')").fetchall()
    assert latest == [("warn",)]  # newest result per check only


def test_missing_gold_table_is_an_error_and_leaves_current_alone(con, tmp_path) -> None:
    good = export(con, tmp_path, T0)
    con.execute("DROP TABLE gold.fct_race_latest")
    with pytest.raises(duckdb.Error):
        export(con, tmp_path, T0 + timedelta(minutes=1))
    assert current_version(tmp_path) == good
    assert [p.name for p in serving_root(tmp_path).iterdir() if p.name.endswith(".tmp")] == []


def test_prunes_to_newest_20_and_keeps_current_valid(con, tmp_path) -> None:
    last = ""
    for i in range(KEEP_VERSIONS + 5):
        last = export(con, tmp_path, T0 + timedelta(seconds=i))
    versions = sorted(p.name for p in serving_root(tmp_path).iterdir() if p.is_dir())
    assert len(versions) == KEEP_VERSIONS
    assert versions[-1] == last == current_version(tmp_path)


def test_same_second_gets_distinct_version(con, tmp_path) -> None:
    a, b = export(con, tmp_path, T0), export(con, tmp_path, T0)
    assert a != b and current_version(tmp_path) == b


def test_current_version_none_when_missing_or_dangling(tmp_path) -> None:
    assert current_version(tmp_path) is None
    root = serving_root(tmp_path)
    root.mkdir(parents=True)
    (root / "CURRENT").write_text("v-gone")
    assert current_version(tmp_path) is None


def test_heartbeat_roundtrip(tmp_path) -> None:
    from elex.pipeline.export import read_heartbeat, write_heartbeat

    assert read_heartbeat(tmp_path) is None
    write_heartbeat(tmp_path, T0)
    assert read_heartbeat(tmp_path) == T0


def test_keep_none_prunes_nothing(con, tmp_path) -> None:
    for i in range(KEEP_VERSIONS + 5):
        export(con, tmp_path, T0 + timedelta(seconds=i), keep=None)
    versions = [p for p in serving_root(tmp_path).iterdir() if p.is_dir()]
    assert len(versions) == KEEP_VERSIONS + 5
