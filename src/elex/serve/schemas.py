"""Response models for the six read-only endpoints (TypeScript types are generated from them)."""

from pydantic import BaseModel


class Health(BaseModel):
    status: str  # ok (<= 180 s) | delayed (<= 600 s) | offline
    last_ingest_at: str | None
    serving_version: str
    age_seconds: float | None


class Summary(BaseModel):
    office: str
    seats_up: int
    d_total: int
    r_total: int
    o_total: int
    d_called: int
    r_called: int
    o_called: int
    uncalled: int
    majority_line: int | None
    est_pct_counted: float | None
    mean_pct_reporting: float | None


class MapCounty(BaseModel):
    fips: str
    county_name: str | None
    state_po: str | None
    margin_pp: float | None
    pct_reporting: float | None
    total_votes: int
    baseline_margin_pp: float | None = None  # 2024 presidential margin, for "flipped"


class Candidate(BaseModel):
    name: str
    party_code: str
    votes: int
    pct: float


class Projection(BaseModel):
    median: float | None = None
    p10: float | None = None
    p90: float | None = None
    status: str | None = None


class Race(BaseModel):
    race_id: int
    label: str
    office: str
    province: str | None
    district: str | None
    candidates: list[Candidate]
    pct_reporting: float | None
    winner_party: str | None
    margin_pp: float | None
    polls_close: str | None = None  # ISO UTC, from civicAPI
    last_updated: str | None = None  # ISO UTC, civicAPI's last change to the race
    projection: Projection


class HistoryPoint(BaseModel):
    as_of: str
    median: float | None
    p10: float | None
    p90: float | None
    est_pct_counted: float | None


class Recap(BaseModel):
    """County changes over the night as parallel columns (row i = one county update)."""

    t: list[int]  # epoch seconds, ascending
    race_id: list[int]
    fips: list[str]
    d: list[int]
    r: list[int]
    total: list[int]
    pct: list[float | None]


class VotePoint(BaseModel):
    t: str
    name: str
    party_code: str
    votes: int


class Check(BaseModel):
    name: str
    status: str  # pass | warn | fail | error
    detail: str | None


class LatencyPoint(BaseModel):
    t: str
    p50_ms: float | None


class Pipeline(BaseModel):
    last_ingest_at: str | None
    rows_processed: int
    checks: list[Check]
    latency: list[LatencyPoint]
