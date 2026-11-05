"""elex command-line interface."""

import logging

import typer

from elex import __version__

app = typer.Typer(no_args_is_help=True, help="Election night pipeline.")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@app.callback()
def main() -> None:
    """Election night pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


def _pipeline():
    from elex.civic.client import CivicClient
    from elex.config import get_settings
    from elex.pipeline.cycle import Pipeline

    s = get_settings()
    return Pipeline(
        s,
        CivicClient(s.civic_base_url, testdata=s.testdata, concurrency=s.concurrency),
        intervals_s={"A": s.tier_a_s, "B": s.tier_b_s, "C": s.tier_c_s},
        max_per_cycle={"C": s.tier_c_max_per_cycle},
        cycle_budget_s=s.cycle_budget_s,
    )


@app.command("init-db")
def init_db_cmd() -> None:
    """Create the bronze/ops schemas and tables (idempotent)."""
    from elex.db import connect, db_path, init_db

    con = connect()
    init_db(con)
    con.close()
    typer.echo(f"initialized {db_path()}")


@app.command()
def sql(
    query: str,
    live: bool = typer.Option(
        False, help="Query the live warehouse file (holds the lock for the whole query)."
    ),
) -> None:
    """Run a query against the warehouse and print the result.

    By default the query runs on a private copy of the warehouse taken in a gap between
    archiver cycles, so a long query can never block the archiver (a 19-minute diagnostic
    once froze publishing). --live reads the real file: newest rows, but the archiver waits.
    """
    from elex.db import connect, query_snapshot

    if live:
        con = connect(read_only=True, retries=30)
        try:
            typer.echo(con.sql(query))
        finally:
            con.close()
        return
    typer.echo(query_snapshot(query))


@app.command()
def discover(list_: bool = typer.Option(False, "--list", help="Print the catalog.")) -> None:
    """Search tonight's races and upsert bronze.race_catalog."""
    import asyncio

    from elex.db import connect, init_db
    from elex.ingest.discover import load_tracked, rows_from_search, search_pages, upsert_catalog

    p = _pipeline()

    async def go() -> list:
        try:
            return await search_pages(p.client, lambda *a, **k: None)
        finally:
            await p.client.aclose()

    rows = rows_from_search(asyncio.run(go()), load_tracked())
    con = connect()
    init_db(con)
    upsert_catalog(con, rows)
    con.close()
    if list_:
        order = {"senate": 0, "governor": 1, "house": 2}
        for r in sorted(rows, key=lambda r: (order[r.office], r.province or "", r.district or "")):
            typer.echo(
                f"{r.race_id}\t{r.office}\t{r.tier}\t{r.province}\t{r.district or ''}\t"
                f"{r.election_name}"
            )
    counts = {o: sum(r.office == o for r in rows) for o in ("senate", "governor", "house")}
    typer.echo(f"{len(rows)} races: {counts}")


@app.command("cycle-once")
def cycle_once() -> None:
    """Run a single pipeline cycle."""
    import asyncio

    p = _pipeline()

    async def go():
        try:
            return await p.run_once()
        finally:
            await p.client.aclose()

    r = asyncio.run(go())
    typer.echo(f"{r.status}: {r.requests} requests, {r.new_snapshots} new snapshots {r.errors}")


@app.command()
def run(interval: int = typer.Option(60, help="Seconds between cycle starts.")) -> None:
    """Poll forever; SIGINT/SIGTERM finish the in-flight cycle, then exit."""
    import asyncio

    from elex.pipeline.cycle import run_forever

    p = _pipeline()

    async def go() -> None:
        try:
            await run_forever(p, interval)
        finally:
            await p.client.aclose()

    asyncio.run(go())


@app.command("load-ref")
def load_ref() -> None:
    """Download reference data and load ref.* tables plus the region crosswalk seed."""
    from elex.config import get_settings
    from elex.db import connect, init_db
    from elex.reference import acs, crosswalk, gazetteer, pres, turnout

    s = get_settings()
    ref_dir = s.data_dir / "reference"
    if not s.census_api_key:
        raise typer.BadParameter("CENSUS_API_KEY is not set (put it in .env)")
    gaz = gazetteer.read(gazetteer.download(ref_dir))
    baseline = pres.county_baseline(pres.download(ref_dir), gazetteer.state_po_by_fips_prefix(gaz))
    features = acs.county_features(acs.read(acs.download(ref_dir, s.census_api_key)), gaz)
    prior = turnout.state_turnout_prior(
        baseline, turnout.read_ballots_2022(turnout.download(ref_dir))
    )
    xwalk = crosswalk.build(gaz)
    crosswalk.write_seed(xwalk)

    # Everything is computed before taking the write lock, so the archiver waits < 1 s.
    con = connect(retries=60)
    try:
        init_db(con)
        con.execute("CREATE SCHEMA IF NOT EXISTS ref")
        for name, df in {
            "county_baseline": baseline,
            "county_features": features,
            "state_turnout_prior": prior,
        }.items():
            con.register("_df", df)
            con.execute(f"CREATE OR REPLACE TABLE ref.{name} AS SELECT * FROM _df")
            con.unregister("_df")
        payloads = crosswalk.archived_payloads(con)
    finally:
        con.close()

    unmatched = crosswalk.unmatched_regions(payloads, xwalk)
    crosswalk.UNMATCHED.parent.mkdir(parents=True, exist_ok=True)
    unmatched.to_csv(crosswalk.UNMATCHED, index=False)
    for y in ("20", "24"):
        n = int(baseline[f"pres{y}_total"].notna().sum())
        typer.echo(f"ref.county_baseline 20{y}: {n} counties")
    typer.echo(f"ref.county_features: {len(features)} counties")
    k0 = prior["k0"]
    typer.echo(
        f"ref.state_turnout_prior: {len(prior)} states, k0 {k0.min():.3f}-{k0.max():.3f} "
        f"(median {k0.median():.3f}; {int((prior['source'] == 'default_1.0').sum())} default)"
    )
    typer.echo(f"region_crosswalk seed: {len(xwalk)} rows")
    typer.echo(f"unmatched archived County regions: {len(unmatched)} -> {crosswalk.UNMATCHED}")


@app.command()
def backfill(
    race_id: list[int] = typer.Option([], help="Races to backfill (default: whole catalog)."),
    concurrency: int = typer.Option(2, help="Parallel races; keep low while the archiver runs."),
) -> None:
    """Fill snapshots we missed from civicAPI race history. Safe while the archiver runs."""
    import asyncio

    from elex.civic.client import CivicClient
    from elex.config import get_settings
    from elex.ingest.backfill import backfill as run_backfill
    from elex.ingest.backfill import summary

    s = get_settings()
    client = CivicClient(s.civic_base_url)

    async def go():
        try:
            return await run_backfill(client, s.data_dir, race_id or None, concurrency)
        finally:
            await client.aclose()

    res = asyncio.run(go())
    typer.echo(summary(res))
    for e in res.errors[:20]:
        typer.echo(f"  error: {e}")
    if res.inserted:
        typer.echo("the archiver's next cycle will rebuild the warehouse (full refresh)")


@app.command()
def project(race_id: int | None = typer.Option(None, help="One race (default: all).")) -> None:
    """Project Senate/Governor races from the warehouse and write model.* tables."""
    from elex.db import connect
    from elex.model.run import run, summarize

    con = connect(retries=120)
    try:
        typer.echo(summarize(run(con, race_id)))
    finally:
        con.close()


@app.command("backtest")
def backtest_cmd() -> None:
    """Simulated-night backtest, grid tuning and gates; freezes config/model.yaml."""
    from elex.config import get_settings
    from elex.model.backtest import run

    r = run(get_settings().data_dir / "reference")
    for name, g in r["gates"].items():
        typer.echo(f"{'PASS' if g['pass'] else 'FAIL'} {name}")
    typer.echo(f"chosen {r['chosen']['kappa']=} {r['chosen']['sigma_nu']=} {r['chosen']['alpha']=}")


@app.command("flow")
def prefect_flow(interval: int = typer.Option(60, help="Seconds between flow runs.")) -> None:
    """Serve the Prefect flow (alternative to `elex run`; never run both)."""
    from elex.flows.prefect_flow import serve

    serve(interval)


@app.command("replay")
def replay_cmd(
    start: str = typer.Option("2026-11-03T22:00:00Z", "--from", help="First step (ISO UTC)."),
    end: str | None = typer.Option(None, "--to", help="Last step (default: now)."),
    every: int = typer.Option(10, help="Minutes between steps."),
    out: str = typer.Option("./data-replay", help="Replay data dir (never the live one)."),
) -> None:
    """Re-run the night from the archive with a simulated clock into a separate data dir."""
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from elex.config import get_settings
    from elex.pipeline.replay import replay

    s = get_settings()
    dst = Path(out).resolve()
    if dst == s.data_dir.resolve():
        raise typer.BadParameter("replay must not write into the live data dir")
    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.now(UTC)

    def tick(t, v):
        typer.echo(f"{t:%Y-%m-%d %H:%M}Z  {v or '-'}")

    steps = replay(s.data_dir, dst, t0, t1, timedelta(minutes=every), on_step=tick)
    typer.echo(f"{len(steps)} steps -> {dst}")


@app.command("export-static")
def export_static_cmd(
    replay_dir: str = typer.Option("./data-replay", help="Output of `elex replay`."),
    out: str = typer.Option("web/public/replay", help="Static files for the replay build."),
) -> None:
    """Write one JSON set per replay step for the VITE_REPLAY=1 dashboard build."""
    import json
    from datetime import datetime
    from pathlib import Path

    from elex.pipeline.export import serving_root
    from elex.pipeline.static_export import clean, export_step, step_key, write_index

    rd = Path(replay_dir)
    steps = json.loads((rd / "replay.json").read_text())
    root = Path(out)
    clean(root)
    tracked = [
        int(r.split(",")[0])
        for r in Path("dbt/seeds/tracked_races.csv").read_text().splitlines()[1:]
        if r.strip()
    ]
    times = []
    for st in steps:
        if not st["version"]:
            continue
        t = datetime.fromisoformat(st["t"])
        (serving_root(rd) / "CURRENT").write_text(st["version"])
        n = export_step(rd, root / step_key(t), tracked)
        times.append(t)
        typer.echo(f"{step_key(t)}: {n} files")
    write_index(root, times)
    typer.echo(f"{len(times)} steps -> {root}")


@app.command("export")
def export_cmd() -> None:
    """Export gold/model tables to a new Parquet serving version and point CURRENT at it."""
    from elex.config import get_settings
    from elex.db import connect
    from elex.pipeline.export import export

    con = connect(retries=60)
    try:
        typer.echo(export(con, get_settings().data_dir))
    finally:
        con.close()


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8000, help="Port."),
) -> None:
    """Serve the read-only API over the CURRENT Parquet version."""
    import uvicorn

    uvicorn.run("elex.serve.api:app", host=host, port=port)


@app.command("fixture-warehouse")
def fixture_warehouse(path: str) -> None:
    """Build a warehouse from tests/fixtures/civicapi (no network), e.g. for make dq."""
    from pathlib import Path

    from elex.ingest.fixture_wh import build

    typer.echo(f"{build(Path(path))} snapshots -> {path}")


@app.command("record-fixtures")
def record_fixtures(
    base: bool = typer.Option(True, help="Record status, dates, search, race 3827."),
    race_id: list[int] = typer.Option([], help="Extra race ids to record (full)."),
    testdata: bool = typer.Option(True, help="Also record each extra race with testdata=true."),
    history_ts: str | None = typer.Option(None, help="Record /race/3827/history/<ts>."),
) -> None:
    """Record real civicAPI responses into tests/fixtures/civicapi/ (max 25 requests)."""
    from pathlib import Path

    from elex.civic.record import Recorder, record_base, record_history_snapshot, record_races
    from elex.config import get_settings

    rec = Recorder(get_settings().civic_base_url, Path("tests/fixtures/civicapi"))
    if base:
        record_base(rec)
    if history_ts:
        record_history_snapshot(rec, 3827, history_ts)
    record_races(rec, race_id, testdata)
    typer.echo(f"{rec.count} requests")
