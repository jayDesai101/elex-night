"""Optional Prefect runner: one flow run per pipeline cycle, served every 60 s.

The cycle is a single task (steps 1-9 in Pipeline.run_once) because its steps hand the
DuckDB file back and forth (released before dbt, reopened after); splitting them into
tasks would duplicate that logic. Prefect adds run history, retries visibility and a UI.
Use instead of `elex run`, never alongside it (both would poll civicAPI).
"""

import asyncio

from prefect import flow, get_run_logger, task

from elex.civic.client import CivicClient
from elex.config import get_settings
from elex.pipeline.cycle import Pipeline
from elex.pipeline.export import current_version


@task(name="pipeline-cycle")
def run_cycle() -> dict:
    s = get_settings()
    client = CivicClient(s.civic_base_url, testdata=s.testdata, concurrency=s.concurrency)
    pipeline = Pipeline(
        s,
        client,
        intervals_s={"A": s.tier_a_s, "B": s.tier_b_s, "C": s.tier_c_s},
        max_per_cycle={"C": s.tier_c_max_per_cycle},
        cycle_budget_s=s.cycle_budget_s,
    )

    async def go():
        try:
            return await pipeline.run_once()
        finally:
            await client.aclose()

    r = asyncio.run(go())
    return {
        "status": r.status,
        "requests": r.requests,
        "new_snapshots": r.new_snapshots,
        "deferred": r.skipped,
        "model": r.model_status,
        "errors": r.errors,
    }


@task(name="serving-version")
def serving_version() -> str | None:
    return current_version(get_settings().data_dir)


@flow(name="elex-cycle")
def elex_cycle() -> dict:
    log = get_run_logger()
    result = run_cycle()
    result["serving_version"] = serving_version()
    log.info("cycle %s", result)
    if result["status"] == "failed":
        raise RuntimeError(f"cycle failed: {result['errors']}")
    return result


def serve(interval_s: int = 60) -> None:
    elex_cycle.serve(name="elex-night", interval=interval_s)
