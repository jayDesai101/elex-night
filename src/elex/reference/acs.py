"""ACS 5-year county demographics (vintage 2024; all variables confirmed to exist)."""

import logging
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

VINTAGE = 2024
BASE = f"https://api.census.gov/data/{VINTAGE}/acs/acs5"
VARS = {
    "B01003_001E": "pop_total",
    "B19013_001E": "median_hh_income",
    "B01002_001E": "median_age",
    "B15003_001E": "edu_total",
    "B15003_022E": "edu_ba",
    "B15003_023E": "edu_ma",
    "B15003_024E": "edu_prof",
    "B15003_025E": "edu_phd",
}


def download(ref_dir: Path, api_key: str) -> Path:
    path = ref_dir / f"acs5_{VINTAGE}_county.csv"
    if path.exists():
        return path
    for var in VARS:
        r = httpx.get(f"{BASE}/variables/{var}.json", timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"ACS {VINTAGE} variable {var} not found ({r.status_code})")
    params = {"get": "NAME," + ",".join(VARS), "for": "county:*", "key": api_key}
    r = httpx.get(BASE, params=params, timeout=120)
    r.raise_for_status()
    rows = r.json()
    ref_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows[1:], columns=rows[0]).to_csv(path, index=False)
    log.info("downloaded %s (%d counties)", path, len(rows) - 1)
    return path


def read(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"state": str, "county": str})
    d["county_fips"] = d["state"].str.zfill(2) + d["county"].str.zfill(3)
    d = d.rename(columns=VARS)
    for c in VARS.values():
        d[c] = pd.to_numeric(d[c], errors="coerce")
        d.loc[d[c] < 0, c] = np.nan  # Census sentinels such as -666666666
    return d


def county_features(acs: pd.DataFrame, gaz: pd.DataFrame) -> pd.DataFrame:
    """ref.county_features."""
    edu = acs[["edu_ba", "edu_ma", "edu_prof", "edu_phd"]].sum(axis=1, min_count=4)
    acs = acs.assign(pct_bachelors_plus=100 * edu / acs["edu_total"].replace(0, np.nan))
    df = acs.merge(gaz[["county_fips", "land_sqmi"]], on="county_fips", how="left")
    density = df["pop_total"] / df["land_sqmi"].where(df["land_sqmi"] > 0)
    df["log_density"] = np.log(density.where(density > 0))
    cols = [
        "county_fips",
        "pop_total",
        "median_hh_income",
        "pct_bachelors_plus",
        "median_age",
        "land_sqmi",
        "log_density",
    ]
    return df[cols].sort_values("county_fips").reset_index(drop=True)
