"""Race discovery: filtered searches -> bronze.race_catalog with office and tier.

Unfiltered search returns 23k+ mostly local races, so we search by election_type
(`General` holds Senate/House, `Statewide` holds Governor; see docs/api_contract.md)
and filter election_date client-side because the date filter is not strict.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from elex.civic.classify import classify_office
from elex.civic.client import SEARCH_TIMEOUT_S, CivicClient

log = logging.getLogger(__name__)

ELECTION_DAY = "2026-11-03"
SEARCH_TYPES = ("General", "Statewide")
PAGE_LIMIT = 1000
MAX_PAGES = 10
TRACKED_CSV = Path("dbt/seeds/tracked_races.csv")


@dataclass
class CatalogRow:
    race_id: int
    election_name: str | None
    election_type: str | None
    election_scope: str | None
    province: str | None
    district: str | None
    office: str
    tier: str


def load_tracked(path: Path = TRACKED_CSV) -> dict[int, str]:
    if not path.exists():
        return {}
    with path.open(newline="") as fh:
        return {int(r["race_id"]): (r.get("tier") or "A") for r in csv.DictReader(fh)}


def rows_from_search(pages: list[dict], tracked: dict[int, str]) -> list[CatalogRow]:
    out: dict[int, CatalogRow] = {}
    for page in pages:
        for r in page.get("races", []):
            if not str(r.get("election_date", "")).startswith(ELECTION_DAY):
                continue
            office = classify_office(r.get("type"), r.get("province"))
            if office == "other":
                continue
            rid = int(r["id"])
            tier = tracked.get(rid) or ("C" if office == "house" else "B")
            out[rid] = CatalogRow(
                rid,
                r.get("election_name"),
                r.get("type"),
                r.get("election_type"),
                r.get("province"),
                r.get("district"),
                office,
                tier,
            )
    return list(out.values())


async def search_pages(client: CivicClient, log_request) -> list[dict]:
    pages: list[dict] = []
    for etype in SEARCH_TYPES:
        for n in range(MAX_PAGES):
            params = {
                "country": "US",
                "start_date": ELECTION_DAY,
                "end_date": ELECTION_DAY,
                "election_type": etype,
                "limit": PAGE_LIMIT,
                "offset": n * PAGE_LIMIT,
            }
            f = await client.get("/race/search", params, timeout=SEARCH_TIMEOUT_S)
            log_request("search", None, f)
            if f.error or not isinstance(f.data, dict):
                raise RuntimeError(f"search {etype} page {n} failed: {f.error}")
            pages.append(f.data)
            races = f.data.get("races", [])
            tonight = [r for r in races if str(r.get("election_date", "")).startswith(ELECTION_DAY)]
            if len(races) < PAGE_LIMIT or not tonight:
                break
    return pages


def upsert_catalog(con: duckdb.DuckDBPyConnection, rows: list[CatalogRow]) -> int:
    now = datetime.now(UTC)
    for r in rows:
        con.execute(
            """INSERT INTO bronze.race_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (race_id) DO UPDATE SET
                 election_name = excluded.election_name, election_type = excluded.election_type,
                 election_scope = excluded.election_scope, province = excluded.province,
                 district = excluded.district, office = excluded.office, tier = excluded.tier""",
            [
                r.race_id,
                r.election_name,
                r.election_type,
                r.election_scope,
                r.province,
                r.district,
                r.office,
                r.tier,
                now,
            ],
        )
    return len(rows)


def catalog_tiers(con: duckdb.DuckDBPyConnection) -> dict[int, str]:
    return dict(con.execute("SELECT race_id, tier FROM bronze.race_catalog").fetchall())
