"""Chunk 11: export the night as static JSON, one folder per time step, for the replay build.

The dashboard in replay mode (VITE_REPLAY=1) reads web/public/replay/<step>/<endpoint>.json
instead of the live API, so it can be hosted anywhere with no server. Each step's files are
produced by the same FastAPI handlers the live site uses, run against a serving version
built from the archive as it stood at that time.
"""

import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from elex.serve.api import create_app

log = logging.getLogger(__name__)

# Requests the UI makes; query strings become file-name suffixes (lib/replay.ts replayPath)
STATIC_REQUESTS = [
    "/api/health",
    "/api/summary",
    "/api/map?office=senate",
    "/api/map?office=house",
    "/api/map?office=governor",
    "/api/races",
    "/api/races?office=senate&tracked=true",
    "/api/races?office=house&tracked=true",
    "/api/races?office=governor&tracked=true",
    "/api/races?office=senate&tracked=false",
    "/api/races?office=house&tracked=false",
    "/api/races?office=governor&tracked=false",
    "/api/pipeline",
]


def file_name(api_path: str) -> str:
    path, _, qs = api_path.partition("?")
    name = path.removeprefix("/api/").replace("/", "_")
    if not qs:
        return f"{name}.json"
    parts = sorted(p.split("=", 1) for p in qs.split("&"))
    return f"{name}__{'_'.join(f'{k}-{v}' for k, v in parts)}.json"


def step_key(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def export_step(data_dir: Path, out_dir: Path, race_ids: list[int]) -> int:
    """Write every static request for the serving version currently in data_dir."""
    client = TestClient(create_app(data_dir, web_dist=Path("/nonexistent")))
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for req in STATIC_REQUESTS + [
        f"/api/races/{rid}/{kind}" for rid in race_ids for kind in ("history", "votes")
    ]:
        r = client.get(req)
        if r.status_code != 200:
            log.warning("%s -> %s", req, r.status_code)
            continue
        (out_dir / file_name(req)).write_bytes(r.content)
        n += 1
    return n


def steps_between(start: datetime, end: datetime, every: timedelta) -> list[datetime]:
    out, t = [], start
    while t <= end:
        out.append(t)
        t += every
    return out


def write_index(root: Path, steps: list[datetime]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(
        json.dumps(
            {
                "steps": [s.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") for s in steps],
                "keys": [step_key(s) for s in steps],
            }
        )
    )


def clean(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


REPLAY_STEP = timedelta(minutes=10)


def replay_root(data_dir: Path) -> Path:
    return data_dir / "serving" / "replay"


def read_index(root: Path) -> dict:
    try:
        return json.loads((root / "index.json").read_text())
    except (FileNotFoundError, ValueError):
        return {"steps": [], "keys": []}


def append_live_step(data_dir: Path, now: datetime, race_ids: list[int]) -> str | None:
    """Called after each publish: if REPLAY_STEP has passed since the last step, export the
    current serving version as a new replay step and extend index.json. The dashboard's
    replay mode reads these files from the same server as the live API, so the replay
    always ends at 'now' and hands over to live."""
    root = replay_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    idx = read_index(root)
    if idx["steps"]:
        last = datetime.fromisoformat(idx["steps"][-1].replace("Z", "+00:00"))
        if now - last < REPLAY_STEP:
            return None
    key = step_key(now)
    export_step(data_dir, root / key, race_ids)
    idx["steps"].append(now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    idx["keys"].append(key)
    tmp = root / "index.json.tmp"
    tmp.write_text(json.dumps(idx))
    tmp.replace(root / "index.json")
    return key
