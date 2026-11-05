"""Census Gazetteer counties: names, state postal codes and land area."""

import io
import logging
import zipfile
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger(__name__)

URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2025_Gazetteer/2025_Gaz_counties_national.zip"
)
FILENAME = "2025_Gaz_counties_national.txt"


def download(ref_dir: Path) -> Path:
    path = ref_dir / FILENAME
    if not path.exists():
        ref_dir.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            z.extract(FILENAME, ref_dir)
        log.info("downloaded %s", path)
    return path


def read(path: Path) -> pd.DataFrame:
    """county_fips, state_po, county_name, land_sqmi."""
    d = pd.read_csv(path, sep="|", dtype={"GEOID": str})
    d.columns = [c.strip() for c in d.columns]
    return pd.DataFrame(
        {
            "county_fips": d["GEOID"].str.zfill(5),
            "state_po": d["USPS"],
            "county_name": d["NAME"],
            "land_sqmi": d["ALAND_SQMI"].astype(float),
        }
    )


def state_po_by_fips_prefix(gaz: pd.DataFrame) -> dict[str, str]:
    return dict(zip(gaz["county_fips"].str[:2], gaz["state_po"], strict=False))
