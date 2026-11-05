"""County presidential baselines (2020, 2024).

Source: public GitHub mirror tonmcg/US_County_Level_Election_Results_08-24, used
instead of MEDSL because MEDSL's Dataverse files require a guestbook form (decided
by the user on 2026-11-03; see docs/api_contract.md "Reference sources").
"""

import logging
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger(__name__)

MIRROR = (
    "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/"
    "8cccc82f9235dced94a76d143c59a43f4a6bf979/{year}_US_County_Level_Presidential_Results.csv"
)
YEARS = (2020, 2024)


def download(ref_dir: Path) -> dict[int, Path]:
    ref_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for year in YEARS:
        path = ref_dir / f"pres_{year}.csv"
        if not path.exists():
            resp = httpx.get(MIRROR.format(year=year), timeout=60, follow_redirects=True)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            log.info("downloaded %s", path)
        out[year] = path
    return out


def read_year(path: Path) -> pd.DataFrame:
    """One row per county: fips, name, dem, rep, total (all candidates)."""
    d = pd.read_csv(path, dtype={"county_fips": str})
    d["county_fips"] = d["county_fips"].str.zfill(5)
    d = d.dropna(subset=["votes_dem", "votes_gop", "total_votes"])
    return pd.DataFrame(
        {
            "county_fips": d["county_fips"],
            "county_name": d["county_name"],
            "dem": d["votes_dem"].astype("int64"),
            "rep": d["votes_gop"].astype("int64"),
            "total": d["total_votes"].astype("int64"),
        }
    ).drop_duplicates("county_fips")


def county_baseline(paths: dict[int, Path], state_po: dict[str, str]) -> pd.DataFrame:
    """ref.county_baseline: outer join of 2020 and 2024 on county_fips."""
    y20 = read_year(paths[2020]).add_prefix("pres20_")
    y24 = read_year(paths[2024]).add_prefix("pres24_")
    df = y24.merge(y20, left_on="pres24_county_fips", right_on="pres20_county_fips", how="outer")
    df["county_fips"] = df["pres24_county_fips"].fillna(df["pres20_county_fips"])
    df["county_name"] = df["pres24_county_name"].fillna(df["pres20_county_name"])
    df["state_po"] = df["county_fips"].str[:2].map(state_po)
    cols = ["county_fips", "state_po", "county_name"] + [
        f"pres{y}_{k}" for y in ("20", "24") for k in ("dem", "rep", "total")
    ]
    out = df[cols].sort_values("county_fips").reset_index(drop=True)
    for c in cols[3:]:
        out[c] = out[c].astype("Int64")
    return out
