"""Project every Senate and Governor race from the warehouse and write model.* tables.

All statewide races are re-projected each run (74 races, well under a second each);
history gets a row only when a race's source last_updated is new.
"""

import logging
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from elex.model.projection import Params, Result, project, standardize

log = logging.getLogger(__name__)

CONFIG = Path("config/model.yaml")
# Ranked-choice (ME, AK) and no clean county crosswalk (AK, CT): counts only.
UNSUPPORTED_STATES = {"AK", "CT", "ME"}
FEATURES = ["log_density", "pct_bachelors_plus", "log_income", "median_age"]

DDL = """
CREATE SCHEMA IF NOT EXISTS model;
CREATE TABLE IF NOT EXISTS model.projection_latest (
  race_id BIGINT PRIMARY KEY, as_of TIMESTAMPTZ, proj_margin_median DOUBLE, p10 DOUBLE,
  p90 DOUBLE, p025 DOUBLE, p975 DOUBLE, est_expected_votes DOUBLE, est_pct_counted DOUBLE,
  n_informative_counties INTEGER, counted_margin DOUBLE, method VARCHAR, status VARCHAR,
  computed_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS model.projection_history AS
  SELECT * FROM model.projection_latest WITH NO DATA;
"""

INPUTS = """
WITH reg AS (
    SELECT race_id, county_fips,
        sum(votes) FILTER (WHERE party_code = 'D') AS d,
        sum(votes) FILTER (WHERE party_code = 'R') AS r,
        sum(votes) AS v,
        max(region_pct_reporting) AS pct
    FROM silver.int_region_fips
    WHERE county_fips IS NOT NULL AND office IN ('senate', 'governor')
    GROUP BY ALL
)
SELECT l.race_id, l.province, l.round, l.source_last_updated AS as_of,
    reg.county_fips, coalesce(reg.d, 0) AS d, coalesce(reg.r, 0) AS r,
    coalesce(reg.v, 0) AS v, coalesce(reg.pct, 0) AS pct,
    b.pres24_dem, b.pres24_rep, b.pres24_total,
    f.log_density, f.pct_bachelors_plus, ln(f.median_hh_income) AS log_income, f.median_age,
    k.k0
FROM silver.int_race_latest AS l
JOIN reg USING (race_id)
JOIN ref.county_baseline AS b ON b.county_fips = reg.county_fips
LEFT JOIN ref.county_features AS f ON f.county_fips = reg.county_fips
LEFT JOIN ref.state_turnout_prior AS k ON k.state_po = l.province
WHERE l.office IN ('senate', 'governor') AND b.pres24_total > 0
"""

PARTIES = """
SELECT l.race_id,
    count(*) FILTER (WHERE c.party_code = 'D') > 0 AS has_d,
    count(*) FILTER (WHERE c.party_code = 'R') > 0 AS has_r
FROM silver.int_race_latest l
JOIN silver.stg_civic__candidate_results c USING (snapshot_id)
WHERE l.office IN ('senate', 'governor')
GROUP BY 1
"""


def load_config(path: Path = CONFIG) -> tuple[bool, Params]:
    raw = yaml.safe_load(path.read_text()) if path.exists() else {}
    enabled = bool(raw.pop("enabled", True))
    known = {f.name for f in fields(Params)}
    return enabled, Params(**{k: v for k, v in raw.items() if k in known})


def _unsupported(as_of) -> dict:
    return {"status": "unsupported", "as_of": as_of}


def project_race(g: pd.DataFrame, p: Params, has_d: bool, has_r: bool) -> dict:
    first = g.iloc[0]
    if first.province in UNSUPPORTED_STATES or (first["round"] or 1) > 1 or not (has_d and has_r):
        out = _unsupported(first.as_of)
        out["counted_margin"] = None
        return out
    b = (g.pres24_dem / (g.pres24_dem + g.pres24_rep)).to_numpy(float)
    Z = standardize(g[FEATURES].to_numpy(float))
    k0 = float(first.k0) if pd.notna(first.k0) else 1.0
    res: Result = project(b, g.pres24_total, g.v, g.d, g.r, g.pct, Z, k0, p)
    if res.status == "ok" and res.est_pct_counted < p.min_pct_counted:
        # Outside the range the backtest validated: keep counts only (ADR-006)
        res = replace(
            res, status="insufficient_data", median=None, p10=None, p90=None, p025=None, p975=None
        )
    out = asdict(res)
    out["proj_margin_median"] = out.pop("median")
    out["n_informative_counties"] = out.pop("n_informative")
    out["as_of"] = first.as_of
    return out


def run(
    con: duckdb.DuckDBPyConnection, race_id: int | None = None, config: Path = CONFIG
) -> pd.DataFrame:
    enabled, p = load_config(config)
    con.execute(DDL)
    if not enabled:
        log.info("model disabled in %s", config)
        return pd.DataFrame()
    inputs = con.execute(INPUTS).df()
    parties = {r[0]: (r[1], r[2]) for r in con.execute(PARTIES).fetchall()}
    if race_id is not None:
        inputs = inputs[inputs.race_id == race_id]
    now = datetime.now(UTC)
    rows = []
    for rid, g in inputs.groupby("race_id"):
        has_d, has_r = parties.get(rid, (False, False))
        out = project_race(g.reset_index(drop=True), p, has_d, has_r)
        rows.append({"race_id": int(rid), "computed_at": now, **out})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    cols = [r[0] for r in con.execute("DESCRIBE model.projection_latest").fetchall()]
    df = df.reindex(columns=cols)
    con.register("_proj", df)
    con.execute("INSERT OR REPLACE INTO model.projection_latest SELECT * FROM _proj")
    con.execute(
        """INSERT INTO model.projection_history SELECT p.* FROM _proj p
           WHERE p.status = 'ok' AND NOT EXISTS (
             SELECT 1 FROM model.projection_history h
             WHERE h.race_id = p.race_id AND h.as_of = p.as_of)"""
    )
    con.unregister("_proj")
    return df


def summarize(df: pd.DataFrame) -> str:
    if df.empty:
        return "no races projected"
    lines = []
    for r in df.itertuples():
        if r.status == "ok":
            lines.append(
                f"{r.race_id}: ok median {r.proj_margin_median:+.1f} "
                f"[p10 {r.p10:+.1f}, p90 {r.p90:+.1f}] counted {r.est_pct_counted:.0f}% "
                f"({r.n_informative_counties} informative, {r.method})"
            )
        else:
            lines.append(f"{r.race_id}: {r.status}")
    return "\n".join(lines)
