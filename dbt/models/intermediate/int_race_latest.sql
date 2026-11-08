{{ config(materialized='table') }}
-- Latest stored snapshot per race. A table, not a view: 509 rows, rebuilt in ~10 s.
-- As a view DuckDB inlined it into every consumer (int_region_fips, the projection
-- model's inputs) and built hash tables on all 515k snapshots carrying their raw
-- payloads, which ran the archiver's 4 GB connection out of memory.
-- Pick the snapshot on narrow columns first, then join the full row back. A window
-- straight over `select *` made DuckDB defer the payload ->> '$...' extractions past
-- the window, so the raw JSON payloads of every snapshot (17 GB by 2026-11-07) were
-- buffered and the build ran out of memory, which blocked publishing.
with latest as (
    select snapshot_id
    from {{ ref('stg_civic__race_snapshots') }}
    qualify row_number() over (partition by race_id order by fetched_at desc) = 1
)

select s.*
from {{ ref('stg_civic__race_snapshots') }} as s
join latest using (snapshot_id)
