"""Tier scheduling: which races are due this cycle. Pure apart from last_polls()."""

from datetime import datetime, timedelta

import duckdb

DEFAULT_INTERVALS_S = {"A": 60, "B": 180, "C": 600}
TIER_ORDER = {"A": 0, "B": 1, "C": 2}
# `now` is taken once per cycle but each race keeps its own poll time, so a race polled
# d s into a cycle has only (interval - d) elapsed at the next start. Poll up to 25%
# (max 15 s) early rather than skip a whole cycle.
SLACK_FRAC = 0.25
MAX_SLACK_S = 15
# Cap per cycle so the 435 House races never come due as one burst that blocks tier A;
# a synchronized wave drains over ~8 cycles and stays staggered after that.
MAX_PER_CYCLE = {"C": 60}


def due_races(
    tiers: dict[int, str],
    last_polled: dict[int, datetime],
    now: datetime,
    intervals_s: dict[str, int] | None = None,
    max_per_cycle: dict[str, int] | None = None,
) -> list[int]:
    """Races whose time since last poll is at least their tier interval, most overdue first.

    Overdue = elapsed / tier interval; never-polled races count as infinitely overdue and
    ties go tier A first. Capped tiers keep their most overdue races. Order matters: when
    civicAPI is slow the cycle budget runs out partway through the list, and a fixed
    tier-then-race_id order starved tier B and the high ids for hours."""
    intervals = intervals_s or DEFAULT_INTERVALS_S
    caps = MAX_PER_CYCLE if max_per_cycle is None else max_per_cycle

    def overdue(race_id: int, tier: str) -> float:
        last = last_polled.get(race_id)
        return float("inf") if last is None else (now - last).total_seconds() / intervals[tier]

    due: dict[str, list[tuple[float, int]]] = {t: [] for t in TIER_ORDER}
    for race_id, tier in tiers.items():
        last = last_polled.get(race_id)
        slack = min(intervals[tier] * SLACK_FRAC, MAX_SLACK_S)
        if last is None or now - last >= timedelta(seconds=intervals[tier] - slack):
            due[tier].append((overdue(race_id, tier), race_id))
    ranked: list[tuple[float, int, int]] = []
    for tier, races in due.items():
        races.sort(key=lambda x: (-x[0], x[1]))
        if tier in caps:
            races = races[: caps[tier]]
        ranked.extend((-o, TIER_ORDER[tier], r) for o, r in races)
    return [r for *_, r in sorted(ranked)]


def last_polls(con: duckdb.DuckDBPyConnection) -> dict[int, datetime]:
    """Rebuild last-poll times from ingest_log (used at start-up)."""
    rows = con.execute(
        """SELECT race_id, max(requested_at) FROM bronze.ingest_log
           WHERE endpoint IN ('race', 'race_light') AND race_id IS NOT NULL
           GROUP BY race_id"""
    ).fetchall()
    return {r[0]: r[1] for r in rows}
