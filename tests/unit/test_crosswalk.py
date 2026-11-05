import json

from elex.civic.classify import normalize_region_name
from elex.reference import crosswalk, gazetteer

REF = "tests/fixtures/reference"
CIVIC = "tests/fixtures/civicapi"


def _xwalk(tmp_path, overrides: str = "province,region_name_norm,county_fips\n"):
    ov = tmp_path / "overrides.csv"
    ov.write_text(overrides)
    return crosswalk.build(gazetteer.read(f"{REF}/gaz_counties_nj_ia_va.txt"), ov)


def test_all_nj_regions_in_race_3827_map(tmp_path) -> None:
    race = json.loads(open(f"{CIVIC}/race_3827.json").read())
    known = crosswalk.lookup(_xwalk(tmp_path))
    regions = race["region_results"].values()
    fips = {known.get(("NJ", normalize_region_name(r["name"]))) for r in regions}
    assert len(race["region_results"]) == 21
    assert None not in fips and len(fips) == 21
    assert crosswalk.unmatched_regions([race], _xwalk(tmp_path)).empty


def test_virginia_city_vs_county(tmp_path) -> None:
    known = crosswalk.lookup(_xwalk(tmp_path))
    assert known[("VA", "RICHMOND CITY")] == "51760"
    assert known[("VA", "RICHMOND")] == "51159"


def test_override_wins(tmp_path) -> None:
    xw = _xwalk(tmp_path, "province,region_name_norm,county_fips\nIA,Pottawattamie Co,19155\n")
    row = xw[(xw.province == "IA") & (xw.region_name_norm == "POTTAWATTAMIE CO")]
    assert row["county_fips"].tolist() == ["19155"]
    assert row["match_method"].tolist() == ["override"]


def test_unmatched_reports_unknown_and_conflicting(tmp_path) -> None:
    payload = {
        "province": "IA",
        "region_results": {
            "polk": {"name": "Polk", "type": "County", "fips": "19153"},
            "nowhere": {"name": "Nowhere", "type": "County"},
            "story": {"name": "Story", "type": "County", "fips": "19001"},
            "ames": {"name": "Ames", "type": "Town"},
        },
    }
    un = crosswalk.unmatched_regions([payload], _xwalk(tmp_path))
    assert sorted(un["region_key"]) == ["nowhere", "story"]
