-- One row per stored snapshot. Office comes from the catalog, never re-derived here.
select
    s.snapshot_id,
    s.race_id,
    s.fetched_at,
    s.source_last_updated,
    s.content_sha256,
    s.test_data,
    c.office,
    c.province,
    c.district,
    s.payload ->> '$.election_name' as election_name,
    cast(s.payload ->> '$.round' as integer) as round,
    cast(s.payload ->> '$.percent_reporting' as double) as percent_reporting,
    cast(s.payload ->> '$.is_disputed' as boolean) as is_disputed,
    cast(s.payload ->> '$.polls_close' as timestamptz) as polls_close,
    -- when search totals were merged in, that is when the race last changed
    greatest(
        s.source_last_updated,
        cast(s.payload ->> '$._merged_at' as timestamptz)
    ) as last_changed
from {{ source('bronze', 'race_snapshots') }} as s
join {{ source('bronze', 'race_catalog') }} as c using (race_id)
{% if not var('include_test_data') %}
where not s.test_data
{% endif %}
