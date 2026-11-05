"""Pydantic models for civicAPI race payloads (fields per docs/api_contract.md)."""

from pydantic import AwareDatetime, BaseModel, ConfigDict


class CivicCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    party: str | None = None
    candidate_id: int | None = None
    incumbent: bool | None = None
    major_candidate: bool | None = None
    winner: bool | None = None
    color: str | None = None
    votes: int
    percent: float | None = None


class CivicRegion(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    fips: str | None = None
    fill: str | None = None
    percent_reporting: float | None = None
    candidates: list[CivicCandidate]


class CivicRace(BaseModel):
    model_config = ConfigDict(extra="allow")

    election_name: str
    election_type: str
    election_scope: str | None = None
    election_date: AwareDatetime
    country: str
    province: str
    district: str | None = None
    municipality: str | None = None
    polls_open: AwareDatetime | None = None
    polls_close: AwareDatetime | None = None
    is_disputed: bool | None = None
    has_map: bool | None = None
    registered_voters: int | None = None
    percent_reporting: float
    test_data: bool
    last_updated: AwareDatetime
    round: int | None = None
    candidates: list[CivicCandidate]
    region_results: dict[str, CivicRegion] = {}
