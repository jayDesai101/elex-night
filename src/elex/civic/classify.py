"""Pure classification helpers. Rules are documented in docs/api_contract.md."""

import re

_OFFICES = {
    "US Senate": "senate",
    "Governor": "governor",
    "House of Representatives": "house",
}
_PARTIES = {
    "Democratic": "D",
    "Republican": "R",
    "Independent": "I",
    "Nonaffiliated": "I",
    "Unaffiliated": "I",
}
_NOT_A_COUNTY = re.compile(r"registered voters|^\s*all counties\b", re.I)
_SUFFIXES = ("CENSUS AREA", "MUNICIPALITY", "BOROUGH", "COUNTY", "PARISH")


def classify_office(election_type: str | None, province: str | None = None) -> str:
    """Office from the race `election_type` (or search-row `type`): senate|house|governor|other."""
    if province == "US":
        return "other"
    return _OFFICES.get((election_type or "").strip(), "other")


def party_code(party: str | None) -> str:
    """civicAPI party label -> D, R, I or O."""
    return _PARTIES.get((party or "").strip(), "O")


def normalize_region_name(name: str) -> str:
    """Uppercase, strip punctuation, collapse spaces, drop a trailing county-type word.

    CITY is kept on purpose: Virginia's independent cities differ from same-name counties.
    """
    # civicAPI (New York) sends each county twice, the second as
    # "Kings (Active Registered Voters: 448,832)", plus "All Counties (...)" aggregates;
    # neither is a county and both must never join the crosswalk.
    if _NOT_A_COUNTY.search(name):
        return ""
    s = name.upper().replace("-", " ")
    s = re.sub(r"[^A-Z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suffix in _SUFFIXES:
        if s.endswith(" " + suffix):
            s = s[: -len(suffix) - 1].rstrip()
            break
    s = re.sub(r"^SAINT ", "ST ", s)
    s = s.replace(" SAINT ", " ST ")
    return s
