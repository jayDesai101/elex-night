"""One pipeline cycle: steps 1-9 (docs/PLAN.md "Pipeline cycle").

The DuckDB connection is opened per cycle and closed after, so `elex sql` can read
between cycles and dbt can take the file in step 6.
"""

import asyncio
import logging
import signal
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from elex.civic.client import DEADLINE, CivicClient, Fetch
from elex.config import Settings
from elex.db import connect, db_path, init_db
from elex.ingest import search_refresh
from elex.ingest.archive import Archive
from elex.ingest.backfill import full_refresh_flag
from elex.ingest.discover import (
    catalog_tiers,
    load_tracked,
    rows_from_search,
    search_pages,
    upsert_catalog,
)
from elex.ingest.poller import DEFAULT_INTERVALS_S, due_races, last_polls
from elex.model.run import run as model_run
from elex.pipeline.export import current_version, export, write_heartbeat
from elex.pipeline.static_export import append_live_step
from elex.pipeline.transform import (
    TransformResult,
    rebuild_in_chunks,
    record_checks,
    run_dbt_build,
)

log = logging.getLogger(__name__)

DISCOVERY_EVERY = timedelta(minutes=30)
FULL_REFRESH_RETRY = timedelta(minutes=30)


def model_status(df) -> str:
    """'disabled' when the kill switch is off, else e.g. 'ok:3 insufficient_data:40'."""
    if df.empty:
        return "disabled"
    return " ".join(f"{k}:{v}" for k, v in sorted(df.status.value_counts().items()))


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class CycleResult:
    cycle_id: uuid.UUID
    status: str
    requests: int = 0
    new_snapshots: int = 0
    skipped: int = 0
    model_status: str | None = None
    fetched_ok: int = 0  # race/search responses that succeeded this cycle
    errors: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        client: CivicClient,
        *,
        clock: Callable[[], datetime] = utcnow,
        intervals_s: dict[str, int] | None = None,
        tracked_csv: Path | None = None,
        transform: bool = True,
        max_per_cycle: dict[str, int] | None = None,
        dbt_target: str = "dev",
        cycle_budget_s: float = 45.0,
        model: bool = True,
        model_config: Path | None = None,
        replay_steps: bool = True,
    ) -> None:
        self.settings = settings
        self.client = client
        self.clock = clock
        self.intervals_s = intervals_s or DEFAULT_INTERVALS_S
        self.tracked_csv = tracked_csv
        self.transform = transform
        self.max_per_cycle = max_per_cycle
        self.dbt_target = dbt_target
        self.cycle_budget_s = cycle_budget_s
        self.model = model
        self.model_config = model_config  # None = config/model.yaml (the live kill switch)
        self.replay_steps = replay_steps  # write a replay step every 10 min after a publish
        self.last_discovery: datetime | None = None
        self.last_search: datetime | None = None
        self._unpublished = False  # stored snapshots not yet exported (e.g. export blocked)
        self._refresh_failed_at: datetime | None = None  # last failed full refresh
        self.last_polled: dict[int, datetime] | None = None
        self._con: duckdb.DuckDBPyConnection | None = None
        self._cycle_id: uuid.UUID | None = None
        self._requests = 0

    # -- logging -----------------------------------------------------------------
    def _log_request(
        self,
        endpoint: str,
        race_id: int | None,
        f: Fetch,
        sha: str | None = None,
        is_new: bool | None = None,
        error: str | None = None,
    ) -> None:
        self._requests += 1
        assert self._con is not None
        self._con.execute(
            "INSERT INTO bronze.ingest_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                uuid.uuid4(),
                self._cycle_id,
                self.clock(),
                endpoint,
                race_id,
                f.status,
                f.latency_ms,
                f.nbytes,
                sha,
                is_new,
                error or f.error,
            ],
        )

    # -- the cycle ---------------------------------------------------------------
    async def run_once(self) -> CycleResult:
        self._cycle_id = uuid.uuid4()
        self._requests = 0
        started = self.clock()
        result = CycleResult(self._cycle_id, "ok")
        con = connect(self.settings.data_dir, retries=30)
        self._con = con
        try:
            await self._ingest(con, result)
        finally:
            result.requests = self._requests
            con.close()
            self._con = None

        # 6. transform: when ingestion stored something new, or nothing has been served yet.
        # Ingestion is already committed, so a dbt failure marks the cycle partial and
        # never loses data.
        tr: TransformResult | None = None
        # A backfill leaves a flag: its snapshots are older than what the incremental
        # region model has loaded, so that model must be rebuilt from scratch once.
        refresh_flag = full_refresh_flag(self.settings.data_dir)
        # A failed full refresh (e.g. out of memory) must not hold publishing hostage: fall
        # back to the incremental build and retry the refresh every 30 minutes.
        full_refresh = refresh_flag.exists() and (
            self._refresh_failed_at is None
            or self.clock() - self._refresh_failed_at >= FULL_REFRESH_RETRY
        )
        if result.new_snapshots > 0:
            self._unpublished = True
        # Build even when this cycle's fetching failed: archived but unpublished data does
        # not need civicAPI to be published.
        need_build = (
            self._unpublished
            or full_refresh
            or (result.status != "failed" and current_version(self.settings.data_dir) is None)
        )
        if self.transform and need_build:
            try:
                if full_refresh:
                    tr = rebuild_in_chunks(db_path(self.settings.data_dir), target=self.dbt_target)
                else:
                    tr = run_dbt_build(db_path(self.settings.data_dir), target=self.dbt_target)
                if full_refresh:
                    if tr.success:
                        refresh_flag.unlink(missing_ok=True)
                        self._refresh_failed_at = None
                    else:
                        self._refresh_failed_at = self.clock()
                        log.warning(
                            "full refresh failed (%s); retrying in %s", tr.error, FULL_REFRESH_RETRY
                        )
                        # publish what the incremental build can give meanwhile
                        tr = run_dbt_build(db_path(self.settings.data_dir), target=self.dbt_target)
            except Exception as exc:  # dbt must never stop polling
                log.exception("dbt build crashed")
                tr = TransformResult(False, errors=1, error=f"dbt crashed: {exc}")
            if tr.errors or not tr.success:
                result.status = "partial"
                result.errors.append(tr.error or f"dq errors: {tr.errors}")

        # 8. export (an error-severity DQ failure blocks it: the dashboard keeps the last
        # good version) and 9. record
        con = connect(self.settings.data_dir, retries=30)
        version: str | None = None
        try:
            if tr is not None:
                record_checks(con, result.cycle_id, tr)
                if tr.success and tr.errors == 0:
                    # 7. model (config/model.yaml enabled: false = counts only); a model
                    # error marks the cycle partial but still exports the counts
                    if self.model:
                        try:
                            kw = {"config": self.model_config} if self.model_config else {}
                            result.model_status = model_status(model_run(con, **kw))
                        except Exception as exc:
                            log.exception("model failed")
                            result.model_status = "error"
                            result.status = "partial"
                            result.errors.append(f"model: {exc}")
                    try:
                        version = export(con, self.settings.data_dir, self.clock())
                        self._unpublished = False
                        if self.replay_steps:
                            try:
                                append_live_step(
                                    self.settings.data_dir, self.clock(), self._tracked_ids()
                                )
                            except Exception:  # the replay is a bonus, never a blocker
                                log.exception("replay step failed")
                    except Exception as exc:  # export must never stop polling
                        log.exception("export failed")
                        result.status = "partial"
                        result.errors.append(f"export: {exc}")
            self._record_run(con, started, result, tr, version)
            # The heartbeat says "published data is current": only when nothing new needed
            # publishing, or this cycle published. A blocked export must show as stale, and so
            # must a cycle in which civicAPI answered nothing.
            if (
                result.requests
                and result.status != "failed"
                and result.fetched_ok > 0
                and (version is not None or result.new_snapshots == 0)
            ):
                write_heartbeat(self.settings.data_dir, self.clock())
        finally:
            con.close()
        return result

    async def _ingest(self, con: duckdb.DuckDBPyConnection, result: CycleResult) -> None:
        """Steps 1-5. Sets result.status to failed when the API or catalog is unusable."""
        init_db(con)
        if self.last_polled is None:
            self.last_polled = last_polls(con)

        # 1. health
        f = await self.client.get("/status")
        self._log_request("status", None, f)
        if f.error or not isinstance(f.data, dict) or f.data.get("status") != "ok":
            result.errors.append(f"status:{f.error or f.data}")
            # civicAPI's health check failed, but its search sometimes still answers: try
            # the one-request race totals before giving up on the cycle.
            tiers = catalog_tiers(con)
            if tiers:
                before = result.new_snapshots
                self.last_search = self.clock()
                await self._search_refresh(
                    con, Archive(con, self.settings.data_dir), set(tiers), result
                )
                if result.new_snapshots > before:
                    result.status = "partial"
                    return
            result.status = "failed"
            return

        # 2. discovery. With a catalog already stored, start-up skips it (the race list is
        # stable on the night; a slow or failing search must not stall the first cycle).
        now = self.clock()
        if self.last_discovery is None and catalog_tiers(con):
            self.last_discovery = now
        if self.last_discovery is None or now - self.last_discovery >= DISCOVERY_EVERY:
            try:
                tracked = load_tracked(self.tracked_csv) if self.tracked_csv else load_tracked()
                pages = await search_pages(self.client, self._log_request)
                n = upsert_catalog(con, rows_from_search(pages, tracked))
                self.last_discovery = now
                log.info("discovery: %d races in catalog", n)
            except RuntimeError as exc:
                result.errors.append(str(exc))
                log.warning("discovery failed: %s", exc)
        tiers = catalog_tiers(con)
        if not tiers:
            result.status = "failed"
            result.errors.append("empty catalog")
            return

        # 3-5. due list, fetch, persist. Every race polled this cycle is stamped with the
        # cycle's slot time, not its own fetch time, so a race fetched late in a cycle is
        # still due at the next cycle start: the cadence follows the cycle clock and cannot
        # drift. Races not started before the cycle budget runs out stay due (unstamped).
        archive = Archive(con, self.settings.data_dir)
        slot = self.clock()
        deadline = self.client.clock() + self.cycle_budget_s
        due = due_races(tiers, self.last_polled, slot, self.intervals_s, self.max_per_cycle)
        tasks = [self._poll_race(rid, tiers[rid], archive, result, slot, deadline) for rid in due]
        refresh_every = timedelta(seconds=self.settings.search_refresh_s)
        if self.last_search is None or slot - self.last_search >= refresh_every:
            self.last_search = slot
            tasks.append(self._search_refresh(con, archive, set(tiers), result))
        await asyncio.gather(*tasks)
        if due and result.fetched_ok == 0:
            # Every race request and search failed: nothing here is fresh
            result.errors.append("no successful fetches from civicAPI")
        if result.skipped:
            log.warning(
                "cycle budget %.0f s reached: %d races deferred",
                self.cycle_budget_s,
                result.skipped,
            )
        if result.errors:
            result.status = "partial"

    async def _search_refresh(
        self, con: duckdb.DuckDBPyConnection, archive: Archive, catalog: set[int], res: CycleResult
    ) -> None:
        """Race-level totals for every race in a couple of requests (search_refresh.py)."""

        def log_and_count(endpoint, race_id, f, *a, **k):
            if f.error is None:
                res.fetched_ok += 1
            self._log_request(endpoint, race_id, f, *a, **k)

        try:
            new, changed = await search_refresh.refresh(
                self.client,
                con,
                archive,
                catalog,
                log_and_count,
                self.clock,
                self.client.testdata,
            )
            res.new_snapshots += new
            # A changed total means the county detail (only in the full payload) is
            # stale too. Make those races due now, so the next cycle fetches them in
            # full ahead of their tier interval; on election night the cycle budget
            # starved tier C for two hours exactly when counting began.
            if self.last_polled is not None:
                for rid in changed:
                    self.last_polled.pop(rid, None)
        except Exception as exc:  # never let the refresh stop the race polls
            log.exception("search refresh failed")
            res.errors.append(f"search refresh: {exc}")

    async def _poll_race(
        self,
        race_id: int,
        tier: str,
        archive: Archive,
        res: CycleResult,
        slot: datetime,
        deadline: float,
    ) -> None:
        assert self.last_polled is not None
        path = f"/race/{race_id}"
        if tier == "C" and race_id in archive.latest_sha and not self.client.testdata:
            light = await self.client.get(path, {"light": "true"}, deadline=deadline)
            if light.error == DEADLINE:
                res.skipped += 1
                return
            self.last_polled[race_id] = slot
            self._log_request("race_light", race_id, light)
            if light.error or not isinstance(light.data, dict):
                return
            res.fetched_ok += 1
            known = archive.latest_source_ts.get(race_id)
            ts = light.data.get("last_updated")
            if known is not None and ts and datetime.fromisoformat(ts) == known:
                return
        f = await self.client.get(path, deadline=deadline)
        if f.error == DEADLINE:
            res.skipped += 1
            return
        fetched_at = self.clock()
        self.last_polled[race_id] = slot
        if f.error or not isinstance(f.data, dict):
            self._log_request("race", race_id, f)
            return
        res.fetched_ok += 1
        p = archive.persist(race_id, f.data, fetched_at, self.client.testdata)
        self._log_request("race", race_id, f, p.sha, p.is_new, p.error)
        if p.is_new:
            res.new_snapshots += 1

    def _tracked_ids(self) -> list[int]:
        path = self.tracked_csv or load_tracked.__defaults__[0]
        return list(load_tracked(path))

    def _record_run(
        self,
        con: duckdb.DuckDBPyConnection,
        started: datetime,
        r: CycleResult,
        tr: TransformResult | None = None,
        version: str | None = None,
    ) -> None:
        con.execute(
            "INSERT INTO ops.pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                r.cycle_id,
                started,
                self.clock(),
                r.status,
                r.requests,
                r.new_snapshots,
                tr.errors if tr else None,
                tr.warnings if tr else None,
                r.model_status,
                version,
                "; ".join(r.errors)[:2000] or None,
            ],
        )
        log.info(
            "cycle %s: %s, %d requests, %d new snapshots",
            r.status,
            r.cycle_id,
            r.requests,
            r.new_snapshots,
        )


async def run_forever(pipeline: Pipeline, interval_s: int) -> None:
    """Loop until SIGINT/SIGTERM; the in-flight cycle always finishes its writes."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    failures = 0
    while not stop.is_set():
        t0 = loop.time()
        try:
            res = await pipeline.run_once()
            failures = failures + 1 if res.status == "failed" else 0
        except Exception:
            log.exception("cycle crashed")
            failures += 1
        if failures:
            # 60 s, then 120 s at most: on election night a long backoff idles the
            # archiver for minutes after civicAPI recovers
            wait = min(60 * 2 ** (failures - 1), 120)
        else:
            # next cycle starts interval_s after this one started; after an overrun it starts
            # at once, and because polls are stamped with the slot time it has work to do
            wait = max(0.0, interval_s - (loop.time() - t0))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
        except TimeoutError:
            pass
    log.info("stopped cleanly")
