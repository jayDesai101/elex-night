import pytest

from elex.civic.classify import classify_office, normalize_region_name, party_code


@pytest.mark.parametrize(
    ("election_type", "province", "office"),
    [
        ("US Senate", "GA", "senate"),
        ("Governor", "PA", "governor"),
        ("House of Representatives", "AZ", "house"),
        ("US Senate", "US", "other"),
        ("Delegate", "DC", "other"),
        ("Primary", "NJ", "other"),
        ("State Senate", "IA", "other"),
        ("Lieutenant Governor", "IA", "other"),
        (None, None, "other"),
    ],
)
def test_classify_office(election_type, province, office) -> None:
    assert classify_office(election_type, province) == office


@pytest.mark.parametrize(
    ("party", "code"),
    [
        ("Democratic", "D"),
        ("Republican", "R"),
        ("Independent", "I"),
        ("Nonaffiliated", "I"),
        ("Unaffiliated", "I"),
        ("Libertarian", "O"),
        ("Nonpartisan", "O"),
        ("Write-In", "O"),
        (None, "O"),
    ],
)
def test_party_code(party, code) -> None:
    assert party_code(party) == code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Cape May", "CAPE MAY"),
        ("Cape May County", "CAPE MAY"),
        ("St. Louis County", "ST LOUIS"),
        ("Saint Louis", "ST LOUIS"),
        ("St. Louis City", "ST LOUIS CITY"),
        ("Richmond city", "RICHMOND CITY"),
        ("Orleans Parish", "ORLEANS"),
        ("Matanuska-Susitna Borough", "MATANUSKA SUSITNA"),
        ("Bethel Census Area", "BETHEL"),
        ("Anchorage Municipality", "ANCHORAGE"),
        ("  De  Kalb ", "DE KALB"),
        ("O'Brien", "OBRIEN"),
        # New York's duplicate and aggregate regions never match a county
        ("Kings (Active Registered Voters: 448,832)", ""),
        ("All Counties (Active Registered Voters: 12,665,686)", ""),
        ("Kings", "KINGS"),
    ],
)
def test_normalize_region_name(raw: str, expected: str) -> None:
    assert normalize_region_name(raw) == expected
