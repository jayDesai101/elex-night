-- One row. DQ check statuses are written by the pipeline to ops.dq_results after each
-- dbt build (a model cannot see the tests that run after it). History backfill requests
-- are excluded so a backfill cannot make a stalled archiver look fresh.
with log as (
    select * from {{ source('bronze', 'ingest_log') }}
    where endpoint <> 'history'
)

select
    (select max(requested_at) from log) as last_ingest_at,
    (select count(*) from {{ ref('stg_civic__region_results') }}) as rows_processed,
    (select count(*) from {{ source('bronze', 'race_snapshots') }}) as snapshots_total,
    (select median(latency_ms) from log
        where requested_at > now() - interval 60 minute and error is null) as p50_latency_ms_last_60,
    (select count(*) from log
        where requested_at > now() - interval 60 minute and error is not null) as errors_last_60,
    case
        when (select max(requested_at) from log) >= now() - interval 3 minute then 'pass'
        when (select max(requested_at) from log) >= now() - interval 10 minute then 'warn'
        else 'error'
    end as freshness_status,
    now() as built_at
