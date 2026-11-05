"""Read-only API over the CURRENT Parquet version (never the live warehouse)."""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from elex.config import get_settings
from elex.pipeline.export import current_version, read_heartbeat, serving_root
from elex.serve import schemas as s

OFFICES = {"senate", "house", "governor"}
CACHE_CONTROL = "max-age=15"
ISO = "strftime(({col} AT TIME ZONE 'UTC'), '%Y-%m-%dT%H:%M:%SZ')"
FRESHNESS_STATUS = {"pass": "pass", "warn": "warn", "error": "error"}

OfficeQuery = Annotated[str | None, Query(pattern="^(senate|house|governor)$")]


def iso(col: str) -> str:
    return ISO.format(col=col)


def rows(cur: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict]:
    cur.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


class NoData(Exception):
    pass


class Store:
    """One in-memory DuckDB per serving version; reloaded only when CURRENT changes."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._lock = threading.Lock()
        self._version: str | None = None
        self._con: duckdb.DuckDBPyConnection | None = None
        self._tables: set[str] = set()

    def open(self) -> tuple[duckdb.DuckDBPyConnection, str]:
        version = current_version(self.data_dir)
        if version is None:
            raise NoData
        with self._lock:
            if version != self._version:
                con = duckdb.connect()
                con.execute("SET TimeZone='UTC'")
                tables = set()
                for f in sorted((serving_root(self.data_dir) / version).glob("*.parquet")):
                    con.execute(f"CREATE TABLE {f.stem} AS SELECT * FROM read_parquet('{f}')")
                    tables.add(f.stem)
                self._con, self._version, self._tables = con, version, tables
            assert self._con is not None
            return self._con.cursor(), self._version

    def has(self, table: str) -> bool:
        return table in self._tables


def _matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    return any(t.strip().removeprefix("W/") == etag for t in header.split(","))


def create_app(data_dir: Path | None = None, web_dist: Path | None = None) -> FastAPI:
    store = Store(data_dir or get_settings().data_dir)
    app = FastAPI(title="elex-night API", version="0.1.0")

    @app.middleware("http")
    async def etag_and_cache(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        version = current_version(store.data_dir)
        if version is None:
            return JSONResponse({"detail": "no data yet"}, status_code=503)
        headers = {"ETag": f'"{version}"', "Cache-Control": CACHE_CONTROL}
        if _matches(request.headers.get("if-none-match"), headers["ETag"]):
            return Response(status_code=304, headers=headers)
        response = await call_next(request)
        response.headers.update(headers)
        return response

    # added last = outermost, so even the 503 and 304 responses carry CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET"],
        expose_headers=["ETag"],
    )

    @app.exception_handler(NoData)
    async def no_data(_: Request, __: NoData) -> JSONResponse:
        return JSONResponse({"detail": "no data yet"}, status_code=503)

    @app.get("/api/health", response_model=s.Health)
    def health() -> s.Health:
        cur, version = store.open()
        row = rows(
            cur,
            "SELECT last_ingest_at, epoch(now()) - epoch(last_ingest_at) AS age "
            "FROM fct_pipeline_health",
        )[0]
        # Exports happen only when results change; the heartbeat shows polling continues.
        last, age = row["last_ingest_at"], row["age"]
        beat = read_heartbeat(store.data_dir)
        if beat is not None and (last is None or beat > last):
            last, age = beat, (datetime.now(UTC) - beat).total_seconds()
        row = {"last_ingest_at": last.strftime("%Y-%m-%dT%H:%M:%SZ") if last else None}
        status = "offline" if age is None or age > 600 else "ok" if age <= 180 else "delayed"
        return s.Health(
            status=status,
            last_ingest_at=row["last_ingest_at"],
            serving_version=version,
            age_seconds=age,
        )

    @app.get("/api/summary", response_model=list[s.Summary])
    def summary(office: OfficeQuery = None) -> list[s.Summary]:
        cur, _ = store.open()
        counted: dict[str, float | None] = {}
        if store.has("projection_latest"):
            for r in rows(
                cur,
                "SELECT l.office, sum(p.est_pct_counted * p.est_expected_votes) "
                "/ nullif(sum(p.est_expected_votes), 0) AS pct "
                "FROM projection_latest p JOIN fct_race_latest l USING (race_id) "
                "WHERE p.status = 'ok' GROUP BY l.office",
            ):
                counted[r["office"]] = r["pct"]
        reporting = {
            r["office"]: r["pct"]
            for r in rows(
                cur, "SELECT office, avg(pct_reporting) AS pct FROM fct_race_latest GROUP BY office"
            )
        }
        out = rows(
            cur,
            "SELECT * FROM fct_chamber_summary WHERE (? IS NULL OR office = ?) ORDER BY office",
            [office, office],
        )
        return [
            s.Summary(
                **{
                    k: r[k]
                    for k in (
                        "office seats_up d_total r_total o_total d_called r_called "
                        "o_called uncalled majority_line"
                    ).split()
                },
                est_pct_counted=counted.get(r["office"]),
                mean_pct_reporting=reporting.get(r["office"]),
            )
            for r in out
        ]

    @app.get("/api/map", response_model=list[s.MapCounty])
    def county_map(office: OfficeQuery = "senate") -> list[s.MapCounty]:
        cur, _ = store.open()
        return [
            s.MapCounty(**r)
            for r in rows(
                cur,
                "SELECT county_fips AS fips, county_name, state_po, margin_pp, pct_reporting, "
                "coalesce(total_votes, 0) AS total_votes, baseline_margin_pp "
                "FROM fct_county_latest WHERE office = ? ORDER BY county_fips",
                [office],
            )
        ]

    @app.get("/api/recap", response_model=s.Recap)
    def recap(office: OfficeQuery = "senate") -> s.Recap:
        """Every county update of the night, for replaying the map from the first result."""
        cur, _ = store.open()
        cols: dict[str, list] = {k: [] for k in ("t", "race_id", "fips", "d", "r", "total", "pct")}
        if not store.has("fct_county_timeseries"):
            return s.Recap(**cols)
        cur.execute(
            "SELECT cast(epoch(fetched_at) AS bigint), race_id, county_fips, d_votes, r_votes, "
            "total_votes, pct_reporting FROM fct_county_timeseries WHERE office = ? "
            "ORDER BY fetched_at, race_id, county_fips",
            [office],
        )
        for row in cur.fetchall():
            for k, v in zip(cols, row, strict=True):
                cols[k].append(v)
        return s.Recap(**cols)

    @app.get("/api/races", response_model=list[s.Race])
    def races(office: OfficeQuery = None, tracked: bool = False) -> list[s.Race]:
        cur, _ = store.open()
        races_ = rows(
            cur,
            "SELECT race_id, label, office, province, district, pct_reporting, winner_party, "
            f"margin_pp, {iso('polls_close')} AS polls_close, "
            f"{iso('last_updated')} AS last_updated FROM fct_race_latest "
            "WHERE (? IS NULL OR office = ?) AND (NOT ? OR is_tracked) ORDER BY label",
            [office, office, tracked],
        )
        by_race: dict[int, list[dict]] = {}
        for r in rows(
            cur,
            "SELECT t.race_id, t.candidate_name AS name, t.party_code, "
            "coalesce(t.votes, 0) AS votes FROM fct_race_timeseries t "
            "JOIN fct_race_latest l ON l.race_id = t.race_id AND l.fetched_at = t.fetched_at "
            "WHERE (? IS NULL OR l.office = ?) AND (NOT ? OR l.is_tracked) "
            "ORDER BY t.votes DESC NULLS LAST, t.candidate_name",
            [office, office, tracked],
        ):
            by_race.setdefault(r["race_id"], []).append(r)
        proj: dict[int, s.Projection] = {}
        if store.has("projection_latest"):
            for r in rows(
                cur, "SELECT race_id, proj_margin_median, p10, p90, status FROM projection_latest"
            ):
                proj[r["race_id"]] = s.Projection(
                    median=r["proj_margin_median"], p10=r["p10"], p90=r["p90"], status=r["status"]
                )
        out = []
        for r in races_:
            cands = by_race.get(r["race_id"], [])
            total = sum(c["votes"] for c in cands)
            out.append(
                s.Race(
                    **r,
                    candidates=[
                        s.Candidate(
                            name=c["name"],
                            party_code=c["party_code"],
                            votes=c["votes"],
                            pct=100.0 * c["votes"] / total if total else 0.0,
                        )
                        for c in cands
                    ],
                    projection=proj.get(r["race_id"], s.Projection()),
                )
            )
        return out

    @app.get("/api/races/{race_id}/history", response_model=list[s.HistoryPoint])
    def race_history(race_id: int) -> list[s.HistoryPoint]:
        cur, _ = store.open()
        if not store.has("projection_history"):
            return []
        return [
            s.HistoryPoint(**r)
            for r in rows(
                cur,
                f"SELECT {iso('as_of')} AS as_of, proj_margin_median AS median, p10, p90, "
                "est_pct_counted FROM projection_history WHERE race_id = ? ORDER BY as_of",
                [race_id],
            )
        ]

    @app.get("/api/races/{race_id}/votes", response_model=list[s.VotePoint])
    def race_votes(race_id: int) -> list[s.VotePoint]:
        """Every archived snapshot's candidate totals (vote count over the night)."""
        cur, _ = store.open()
        return [
            s.VotePoint(**r)
            for r in rows(
                cur,
                f"SELECT {iso('fetched_at')} AS t, candidate_name AS name, party_code, "
                "coalesce(votes, 0) AS votes FROM fct_race_timeseries "
                "WHERE race_id = ? AND fetched_at >= TIMESTAMPTZ '2026-11-03 12:00:00+00' "
                "ORDER BY fetched_at, votes DESC",
                [race_id],
            )
        ]

    @app.get("/api/pipeline", response_model=s.Pipeline)
    def pipeline() -> s.Pipeline:
        cur, _ = store.open()
        h = rows(
            cur,
            f"SELECT {iso('last_ingest_at')} AS last_ingest_at, rows_processed, "
            "freshness_status FROM fct_pipeline_health",
        )[0]
        checks = [
            s.Check(name=r["name"], status=r["status"], detail=r["detail"])
            for r in (
                rows(cur, "SELECT name, status, detail FROM dq_checks ORDER BY name")
                if store.has("dq_checks")
                else []
            )
        ]
        checks.append(
            s.Check(
                name="source_freshness",
                status=FRESHNESS_STATUS[h["freshness_status"]],
                detail="last request to civicAPI (warn after 3 min, error after 10)",
            )
        )
        latency = [
            s.LatencyPoint(**r)
            for r in rows(cur, f"SELECT {iso('t')} AS t, p50_ms FROM latency ORDER BY latency.t")
        ]
        return s.Pipeline(
            last_ingest_at=h["last_ingest_at"],
            rows_processed=h["rows_processed"],
            checks=checks,
            latency=latency,
        )

    # Replay steps written by the archiver (static_export.append_live_step): the dashboard
    # scrubs through them and hands over to the live API at the last step.
    replay_dir = store.data_dir / "serving" / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/replay", StaticFiles(directory=replay_dir), name="replay")

    # Production: the built dashboard (web/dist) at /, so UI and API share one origin.
    # Mounted last so every /api route above takes precedence.
    dist = web_dist or get_settings().web_dist
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
