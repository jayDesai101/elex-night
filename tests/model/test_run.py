from functools import partial

import duckdb
import numpy as np
import pytest

from elex.model import run as model_run
from elex.model.run import summarize


@pytest.fixture
def run(tmp_path):
    """run() against a test config, independent of the live kill switch in config/model.yaml."""
    cfg = tmp_path / "model.yaml"
    cfg.write_text("enabled: true\ndraws: 500\n")
    return partial(model_run.run, config=cfg)


@pytest.fixture
def con():
    """A tiny warehouse with the silver/ref shapes run.py reads."""
    c = duckdb.connect()
    for s in ("silver", "ref"):
        c.execute(f"CREATE SCHEMA {s}")
    rng = np.random.default_rng(0)
    rows, base, feats = [], [], []
    for i in range(30):
        fips = f"13{i:03d}"
        T = int(rng.integers(5_000, 50_000))
        b = float(rng.uniform(0.3, 0.7))
        base.append((fips, "GA", int(T * b), int(T * (1 - b)), T))
        feats.append((fips, 3.0 + i / 10, 20 + i, 60_000 + 500 * i, 40 + i / 3))
        V = int(0.7 * T) if i < 15 else 0
        for race in (1, 2):
            rows.append((race, fips, "D", int(V * (b + 0.02)), 100.0 if i < 15 else 0.0))
            rows.append((race, fips, "R", V - int(V * (b + 0.02)), 100.0 if i < 15 else 0.0))
    c.execute(
        "CREATE TABLE silver.int_region_fips AS SELECT col0 race_id, 'senate' office, "
        "col1 county_fips, col2 party_code, col3 votes, col4 region_pct_reporting "
        "FROM (VALUES " + ",".join(map(str, rows)) + ")"
    )
    c.execute(
        "CREATE TABLE silver.int_race_latest AS SELECT * FROM (VALUES "
        "(1, 's1', 'senate', 'GA', 1, TIMESTAMPTZ '2026-11-04 01:00:00+00'), "
        "(2, 's2', 'senate', 'ME', 1, TIMESTAMPTZ '2026-11-04 01:00:00+00')) "
        "t(race_id, snapshot_id, office, province, round, source_last_updated)"
    )
    c.execute(
        "CREATE TABLE silver.stg_civic__candidate_results AS SELECT * FROM (VALUES "
        "('s1','D'),('s1','R'),('s2','D'),('s2','R')) t(snapshot_id, party_code)"
    )
    c.execute(
        "CREATE TABLE ref.county_baseline AS SELECT * FROM (VALUES "
        + ",".join(map(str, base))
        + ") t(county_fips, state_po, pres24_dem, pres24_rep, pres24_total)"
    )
    c.execute(
        "CREATE TABLE ref.county_features AS SELECT * FROM (VALUES "
        + ",".join(map(str, feats))
        + ") t(county_fips, log_density, pct_bachelors_plus, median_hh_income, median_age)"
    )
    c.execute("CREATE TABLE ref.state_turnout_prior AS SELECT 'GA' state_po, 0.7 k0")
    return c


def test_run_writes_latest_and_history_once(con, run) -> None:
    df = run(con)
    by_race = dict(zip(df.race_id, df.status, strict=True))
    assert by_race == {1: "ok", 2: "unsupported"}  # ME: ranked choice
    latest = con.execute(
        "select race_id, status, est_pct_counted from model.projection_latest order by 1"
    ).fetchall()
    assert latest[0][1] == "ok" and 0 < latest[0][2] < 100
    run(con)  # same as_of: latest replaced, no second history row
    assert con.execute("select count(*) from model.projection_history").fetchone()[0] == 1
    assert con.execute("select count(*) from model.projection_latest").fetchone()[0] == 2
    assert "1: ok median" in summarize(df)


def test_race_without_d_and_r_is_unsupported(con, run) -> None:
    con.execute("delete from silver.stg_civic__candidate_results where party_code = 'D'")
    assert run(con, race_id=1).status.tolist() == ["unsupported"]


def test_disabled_writes_nothing(con, tmp_path) -> None:
    cfg = tmp_path / "off.yaml"
    cfg.write_text("enabled: false\n")
    assert model_run.run(con, config=cfg).empty
    assert con.execute("select count(*) from model.projection_latest").fetchone()[0] == 0


def test_projection_hidden_below_min_pct_counted(con, tmp_path) -> None:
    cfg = tmp_path / "strict.yaml"
    cfg.write_text("enabled: true\ndraws: 200\nmin_pct_counted: 99\n")
    df = model_run.run(con, race_id=1, config=cfg)
    assert df.status.tolist() == ["insufficient_data"]
    assert df.proj_margin_median.isna().all()
    assert 0 < df.est_pct_counted.iloc[0] < 99  # still reported, for the vote ring
