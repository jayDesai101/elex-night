"""Region -> county FIPS crosswalk.

2026 civicAPI County regions carry `fips` directly; this name crosswalk covers payloads
without it (e.g. race 3827) and is checked against archived regions.
"""

import csv
import json
from pathlib import Path

import duckdb
import pandas as pd

from elex.civic.classify import normalize_region_name

SEED = Path("dbt/seeds/region_crosswalk.csv")
OVERRIDES = Path("dbt/seeds/region_overrides.csv")
UNMATCHED = Path("reports/unmatched_regions.csv")
COLUMNS = ["province", "region_name_norm", "county_fips", "match_method"]


def build(gaz: pd.DataFrame, overrides_path: Path = OVERRIDES) -> pd.DataFrame:
    """Gazetteer names (normalized) plus manual overrides; overrides win."""
    df = pd.DataFrame(
        {
            "province": gaz["state_po"],
            "region_name_norm": gaz["county_name"].map(normalize_region_name),
            "county_fips": gaz["county_fips"],
            "match_method": "normalized",
        }
    )
    # A name that maps to two FIPS in one state is ambiguous: drop it, needs an override
    df = df[~df.duplicated(["province", "region_name_norm"], keep=False)]
    if overrides_path.exists():
        ov = pd.read_csv(overrides_path, dtype=str)
        if len(ov):
            ov = ov.assign(
                region_name_norm=ov["region_name_norm"].map(normalize_region_name),
                match_method="override",
            )[COLUMNS]
            keys = set(zip(ov["province"], ov["region_name_norm"], strict=False))
            keep = [
                (p, n) not in keys
                for p, n in zip(df["province"], df["region_name_norm"], strict=False)
            ]
            df = pd.concat([df[keep], ov], ignore_index=True)
    return df.sort_values(["province", "region_name_norm"]).reset_index(drop=True)[COLUMNS]


def lookup(xwalk: pd.DataFrame) -> dict[tuple[str, str], str]:
    return {
        (p, n): f
        for p, n, f in zip(
            xwalk["province"], xwalk["region_name_norm"], xwalk["county_fips"], strict=False
        )
    }


def unmatched_regions(payloads: list[dict], xwalk: pd.DataFrame) -> pd.DataFrame:
    """County regions whose name does not resolve (and that carry no usable fips)."""
    known = lookup(xwalk)
    rows = []
    for p in payloads:
        prov = p.get("province")
        for slug, reg in (p.get("region_results") or {}).items():
            if reg.get("type") != "County":
                continue
            norm = normalize_region_name(reg.get("name", ""))
            hit = known.get((prov, norm))
            if hit is None or (reg.get("fips") and reg["fips"] != hit):
                rows.append(
                    {
                        "province": prov,
                        "region_key": slug,
                        "region_name": reg.get("name"),
                        "region_name_norm": norm,
                        "api_fips": reg.get("fips"),
                        "crosswalk_fips": hit,
                    }
                )
    return pd.DataFrame(
        rows,
        columns=[
            "province",
            "region_key",
            "region_name",
            "region_name_norm",
            "api_fips",
            "crosswalk_fips",
        ],
    ).drop_duplicates()


def archived_payloads(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Latest snapshot per statewide race from the archive."""
    rows = con.execute(
        """SELECT s.payload FROM bronze.race_snapshots s
           JOIN bronze.race_catalog c USING (race_id)
           WHERE c.office IN ('senate', 'governor') AND NOT s.test_data
           QUALIFY row_number() OVER (PARTITION BY s.race_id ORDER BY s.fetched_at DESC) = 1"""
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def write_seed(df: pd.DataFrame, path: Path = SEED) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
