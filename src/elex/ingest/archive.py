"""Persist race payloads: raw .json.gz first, then a deduped bronze snapshot row."""

import gzip
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from pydantic import ValidationError

from elex.civic.models import CivicRace

log = logging.getLogger(__name__)


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_path(data_dir: Path, race_id: int, fetched_at: datetime, sha: str) -> Path:
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    return data_dir / "raw" / "civicapi" / "race" / str(race_id) / f"{stamp}_{sha[:12]}.json.gz"


def write_raw(path: Path, data: bytes) -> None:
    """Atomic gzip write: temp file in the same dir, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def schema_error(payload: Any) -> str | None:
    try:
        CivicRace.model_validate(payload)
    except ValidationError as exc:
        loc = exc.errors()[0]["loc"]
        return "schema:" + ".".join(str(p) for p in loc)
    return None


@dataclass
class PersistResult:
    sha: str
    is_new: bool
    error: str | None


class Archive:
    """Tracks the latest hash per race so dedupe needs no query per fetch."""

    def __init__(self, con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
        self.con = con
        self.data_dir = data_dir
        rows = con.execute(
            """SELECT race_id, content_sha256,
                      greatest(source_last_updated,
                               cast(payload->>'$._merged_at' as timestamptz)) AS source_ts
               FROM bronze.race_snapshots
               QUALIFY row_number() OVER (PARTITION BY race_id ORDER BY fetched_at DESC) = 1"""
        ).fetchall()
        self.latest_sha: dict[int, str] = {r[0]: r[1] for r in rows}
        self.latest_source_ts: dict[int, datetime | None] = {r[0]: r[2] for r in rows}

    def persist(
        self, race_id: int, payload: Any, fetched_at: datetime, test_flag: bool
    ) -> PersistResult:
        body = canonical_json(payload)
        sha = sha256_hex(body)
        if self.latest_sha.get(race_id) == sha:
            return PersistResult(sha, False, None)
        path = raw_path(self.data_dir, race_id, fetched_at, sha)
        write_raw(path, body)
        err = schema_error(payload)
        if err:
            log.warning("race %s %s (raw kept at %s)", race_id, err, path)
            return PersistResult(sha, False, err)
        source_ts = payload.get("last_updated")
        self.con.execute(
            """INSERT INTO bronze.race_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                uuid.uuid4(),
                race_id,
                fetched_at,
                source_ts,
                sha,
                # Only our own setting decides: civicAPI's test_data flag is wrong in both
                # directions (false on its ?testdata=true responses; true on all 18 real
                # Pennsylvania races on election night, which blanked the PA map).
                bool(test_flag),
                str(path),
                body.decode(),
            ],
        )
        self.latest_sha[race_id] = sha
        race = CivicRace.model_validate(payload)
        merged_at = payload.get("_merged_at")
        self.latest_source_ts[race_id] = (
            max(race.last_updated, datetime.fromisoformat(merged_at.replace("Z", "+00:00")))
            if merged_at
            else race.last_updated
        )
        return PersistResult(sha, True, None)
