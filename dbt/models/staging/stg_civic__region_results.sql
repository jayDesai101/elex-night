{{ config(materialized='incremental', incremental_strategy='append') }}
-- Incremental (not a view): region rows are ~100x candidate rows, and every cycle
-- would otherwise re-parse every archived payload. Append-only: dbt runs between
-- cycles, so every new snapshot is later than the max already loaded.
with snaps as (
    select s.snapshot_id, s.race_id, s.fetched_at, s.payload
    from {{ source('bronze', 'race_snapshots') }} as s
    where s.snapshot_id in (select snapshot_id from {{ ref('stg_civic__race_snapshots') }})
    {% if is_incremental() %}
      and s.fetched_at > (select coalesce(max(fetched_at), '1970-01-01'::timestamptz) from {{ this }})
    {% endif %}
    {# A chunked rebuild (transform.rebuild_in_chunks) loads the archive one window at a
       time: a full re-parse in one query does not fit in memory on a night's archive. #}
    {% if var('load_until', none) %}
      and s.fetched_at <= '{{ var("load_until") }}'::timestamptz
    {% endif %}
),

regions as (
    select snaps.snapshot_id, snaps.race_id, snaps.fetched_at, je.key as region_key, je.value as r
    from snaps, json_each(snaps.payload -> '$.region_results') as je
),

flat as (
    select
        snapshot_id,
        race_id,
        fetched_at,
        region_key,
        r ->> '$.name' as region_name,
        r ->> '$.type' as region_type,
        r ->> '$.fips' as region_fips,
        cast(r ->> '$.percent_reporting' as double) as region_pct_reporting,
        unnest(from_json(r -> '$.candidates', '[{"name":"VARCHAR","party":"VARCHAR","votes":"BIGINT"}]')) as c
    from regions
)

select
    flat.snapshot_id,
    flat.race_id,
    flat.fetched_at,
    flat.region_key,
    flat.region_name,
    flat.region_type,
    flat.region_fips,
    flat.region_pct_reporting,
    c.name as candidate_name,
    c.party as party_label,
    coalesce(pc.party_code, 'O') as party_code,
    c.votes
from flat
left join {{ ref('party_codes') }} as pc on pc.party_label = c.party
