import math

import pandas as pd
import pytest

from elex.reference import acs, gazetteer, pres, turnout

REF = "tests/fixtures/reference"


@pytest.fixture(scope="module")
def gaz() -> pd.DataFrame:
    return gazetteer.read(f"{REF}/gaz_counties_nj_ia_va.txt")


@pytest.fixture(scope="module")
def baseline(gaz) -> pd.DataFrame:
    paths = {
        2020: f"{REF}/pres_2020_nj_ia_va.csv",
        2024: f"{REF}/pres_2024_nj_ia_va.csv",
    }
    return pres.county_baseline(paths, gazetteer.state_po_by_fips_prefix(gaz))


def test_baseline_counts_and_keys(baseline) -> None:
    counts = baseline.groupby("state_po").size().to_dict()
    assert counts == {"IA": 99, "NJ": 21, "VA": 133}
    assert baseline["county_fips"].str.len().eq(5).all()
    assert baseline["county_fips"].is_unique


def test_baseline_values(baseline) -> None:
    cape_may = baseline.set_index("county_fips").loc["34009"]
    assert cape_may["state_po"] == "NJ"
    assert cape_may["pres24_dem"] + cape_may["pres24_rep"] <= cape_may["pres24_total"]
    assert (baseline["pres20_dem"] > 0).all()


def test_virginia_cities_are_separate_counties(baseline) -> None:
    va = baseline[baseline["state_po"] == "VA"].set_index("county_fips")
    # Richmond city (51760) and Richmond County (51159) are different places
    assert {"51760", "51159"} <= set(va.index)


def test_acs_features(gaz) -> None:
    feats = acs.county_features(acs.read(f"{REF}/acs5_2024_nj_ia_va.csv"), gaz)
    assert len(feats) == 253
    row = feats.set_index("county_fips").loc["34009"]
    assert 0 < row["pct_bachelors_plus"] < 100
    assert math.isclose(row["log_density"], math.log(row["pop_total"] / row["land_sqmi"]))


def test_acs_negative_sentinels_become_null(tmp_path) -> None:
    src = pd.read_csv(f"{REF}/acs5_2024_nj_ia_va.csv", dtype={"state": str, "county": str})
    src.loc[0, "B19013_001E"] = -666666666
    p = tmp_path / "acs.csv"
    src.to_csv(p, index=False)
    assert pd.isna(acs.read(p).loc[0, "median_hh_income"])


def test_turnout_prior_from_2022_ballots(baseline) -> None:
    ballots = turnout.read_ballots_2022(f"{REF}/uf_turnout_2022G_nj_ia_va.csv")
    assert set(ballots["state_po"]) == {"IA", "NJ", "VA"}  # national total row dropped
    prior = turnout.state_turnout_prior(baseline, ballots).set_index("state_po")
    nj = prior.loc["NJ"]
    assert nj["k0"] == pytest.approx(nj["ballots_2022"] / nj["pres24_votes"])
    assert nj["pres24_votes"] == baseline.loc[baseline.state_po == "NJ", "pres24_total"].sum()
    assert (prior["source"] == "uf_ballots_2022/pres24").all()
    assert prior["k0"].between(0.4, 1.0).all()  # a midterm draws fewer voters


def test_turnout_prior_missing_state_defaults(baseline) -> None:
    ballots = turnout.read_ballots_2022(f"{REF}/uf_turnout_2022G_nj_ia_va.csv")
    prior = turnout.state_turnout_prior(baseline, ballots[ballots.state_po != "VA"])
    va = prior.set_index("state_po").loc["VA"]
    assert va["k0"] == 1.0 and va["source"] == "default_1.0"
