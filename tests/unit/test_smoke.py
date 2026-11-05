from typer.testing import CliRunner

from elex import __version__
from elex.cli import app
from elex.config import Settings


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_settings_defaults(monkeypatch) -> None:
    for k in ("ELEX_TESTDATA", "ELEX_INTERVAL_S", "ELEX_INCLUDE_TEST_DATA"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.interval_s == 60
    assert s.testdata is False
    assert s.civic_base_url == "https://civicapi.org/api/v2"


def test_tier_intervals_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ELEX_TIER_A_S", "90")
    monkeypatch.setenv("ELEX_TIER_C_MAX_PER_CYCLE", "40")
    s = Settings(_env_file=None)
    assert (s.tier_a_s, s.tier_b_s, s.tier_c_max_per_cycle) == (90, 180, 40)


def test_sql_runs_on_a_private_copy(tmp_path, monkeypatch) -> None:
    """elex sql must not hold the live warehouse: it queries a copy and deletes it."""
    import duckdb

    from elex.db import connect, init_db, query_snapshot

    con = connect(tmp_path)
    init_db(con)
    con.execute(
        "INSERT INTO bronze.race_catalog VALUES (1,'x','t','s','GA',NULL,'senate','A',now())"
    )
    con.close()
    before = {p for p in __import__("pathlib").Path("/tmp").glob("elex-wh-*")}
    out = query_snapshot("select count(*) as n from bronze.race_catalog", tmp_path)
    assert "1" in out
    # the live file is free right after: a writer can open it immediately
    w = duckdb.connect(str(tmp_path / "warehouse" / "elex.duckdb"))
    w.close()
    after = {p for p in __import__("pathlib").Path("/tmp").glob("elex-wh-*")}
    assert after - before == set()  # the copy was removed
