"""Build a small warehouse from recorded civicAPI fixtures (for make dq and tests).

No network: every race_*.json fixture is archived as one snapshot, and *_testdata
fixtures as test-data snapshots one minute later, so staging must filter them out.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from elex.civic.classify import classify_office
from elex.db import init_db
from elex.ingest.archive import Archive
from elex.ingest.discover import CatalogRow, upsert_catalog

FIXTURES = Path("tests/fixtures/civicapi")
T0 = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)


def build(db_file: Path, fixtures: Path = FIXTURES) -> int:
    import duckdb

    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()
    con = duckdb.connect(str(db_file))
    con.execute("SET TimeZone='UTC'")
    init_db(con)
    files = sorted(p for p in fixtures.glob("race_*.json") if not p.stem.endswith("_light"))
    rows, n = [], 0
    archive = Archive(con, db_file.parent / "fixture_raw")
    for path in files:
        payload = json.loads(path.read_text())
        race_id = int(path.stem.split("_")[1])
        is_test = path.stem.endswith("_testdata")
        if not is_test:
            office = classify_office(payload["election_type"], payload["province"])
            tier = "C" if office == "house" else "B"
            rows.append(
                CatalogRow(
                    race_id,
                    payload["election_name"],
                    payload["election_type"],
                    payload.get("election_scope"),
                    payload["province"],
                    payload.get("district"),
                    office,
                    tier,
                )
            )
        fetched = T0 + timedelta(minutes=1 if is_test else 0)
        res = archive.persist(race_id, payload, fetched, test_flag=is_test)
        n += res.is_new
        con.execute(
            "INSERT INTO bronze.ingest_log VALUES (?, ?, ?, 'race', ?, 200, 100, 0, ?, ?, NULL)",
            [uuid.uuid4(), uuid.UUID(int=0), fetched, race_id, res.sha, res.is_new],
        )
    upsert_catalog(con, rows)
    con.close()
    return n
