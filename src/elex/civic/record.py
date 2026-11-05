"""Record real civicAPI responses as test fixtures (Chunk 1). Network use only here."""

import json
import logging
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

MAX_REQUESTS = 25
SEARCH_LIMIT = 1000
ELECTION_DAY = "2026-11-03"


class Recorder:
    def __init__(self, base_url: str, out_dir: Path) -> None:
        self.base_url = base_url.rstrip("/")
        self.out_dir = out_dir
        self.count = 0
        self.client = httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))

    def get(self, path: str, name: str, params: dict | None = None) -> object:
        if self.count >= MAX_REQUESTS:
            raise RuntimeError(f"request budget of {MAX_REQUESTS} exhausted")
        if self.count:
            time.sleep(1.0)
        self.count += 1
        resp = self.client.get(f"{self.base_url}{path}", params=params)
        log.info("%s %s -> %s (%d bytes)", path, params or "", resp.status_code, len(resp.content))
        resp.raise_for_status()
        data = resp.json()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return data


def record_base(rec: Recorder) -> None:
    """Endpoints that do not depend on tonight's race ids."""
    rec.get("/status", "status")
    rec.get("/getElectionDates", "election_dates", {"country": "US"})
    offset, page = 0, 0
    while True:
        params = {
            "country": "US",
            "start_date": ELECTION_DAY,
            "end_date": ELECTION_DAY,
            "limit": SEARCH_LIMIT,
            "offset": offset,
        }
        data = rec.get("/race/search", f"search_20261103_p{page}", params)
        rows = _rows(data)
        if len(rows) < SEARCH_LIMIT:
            break
        offset += SEARCH_LIMIT
        page += 1
    rec.get("/race/3827", "race_3827")
    rec.get("/race/3827", "race_3827_light", {"light": "true"})
    rec.get("/race/3827/history", "history_3827")


def record_races(rec: Recorder, race_ids: list[int], with_testdata: bool) -> None:
    for rid in race_ids:
        rec.get(f"/race/{rid}", f"race_{rid}")
        if with_testdata:
            rec.get(f"/race/{rid}", f"race_{rid}_testdata", {"testdata": "true"})


def record_history_snapshot(rec: Recorder, race_id: int, timestamp: str) -> None:
    rec.get(f"/race/{race_id}/history/{timestamp}", f"history_{race_id}_snapshot")


def _rows(data: object) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return []
