"""State turnout prior k0 = expected 2026 votes / 2024 presidential votes.

The plan derives k0 from MEDSL 2022 House totals, but that file sits behind a Dataverse
guestbook. Instead: k0_s = 2022 total ballots counted (University of Florida Election Lab,
from EAVS / state results) / the state's 2024 presidential votes in ref.county_baseline.
Ballots slightly exceed votes in any one race (undervotes), so k0 runs ~1-3% high; the
model's shrinkage (m = 10) corrects it from fully reported counties during the night.
"""

import logging
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger(__name__)

URL = "https://election.lab.ufl.edu/data-downloads/turnoutdata/Turnout_2022G_v1.2.csv"
FILENAME = "uf_turnout_2022G_v1.2.csv"
DEFAULT_K0 = 1.0  # only for states missing from the UF file


def download(ref_dir: Path) -> Path:
    path = ref_dir / FILENAME
    if not path.exists():
        ref_dir.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        log.info("downloaded %s", path)
    return path


def read_ballots_2022(path: Path) -> pd.DataFrame:
    """state_po, ballots_2022 (the national total row is dropped)."""
    d = pd.read_csv(path, dtype=str)
    d = d[d["STATE_ABV"].notna() & (d["STATE_ABV"].str.len() == 2)]
    ballots = pd.to_numeric(d["TOTAL_BALLOTS_COUNTED"].str.replace(",", ""), errors="coerce")
    return pd.DataFrame({"state_po": d["STATE_ABV"].values, "ballots_2022": ballots.values})


def state_turnout_prior(
    baseline: pd.DataFrame, ballots: pd.DataFrame | None = None
) -> pd.DataFrame:
    pres = (
        baseline.dropna(subset=["state_po"])
        .groupby("state_po", as_index=False)["pres24_total"]
        .sum()
        .rename(columns={"pres24_total": "pres24_votes"})
    )
    if ballots is None:
        ballots = pd.DataFrame(columns=["state_po", "ballots_2022"])
    df = pres.merge(ballots, on="state_po", how="left")
    ratio = df["ballots_2022"].astype(float) / df["pres24_votes"].astype(float)
    ok = ratio.notna() & (ratio > 0)
    df["k0"] = ratio.where(ok, DEFAULT_K0)
    df["source"] = ok.map({True: "uf_ballots_2022/pres24", False: "default_1.0"})
    return (
        df[["state_po", "k0", "source", "ballots_2022", "pres24_votes"]]
        .sort_values("state_po")
        .reset_index(drop=True)
    )
