with l as (
    select * from {{ ref('int_race_latest') }}
),

-- Only the latest snapshot per race is needed here. Aggregating every archived
-- snapshot parsed the whole payload history each cycle and ran DuckDB out of
-- memory once the archive passed ~3.5 GB (2026-11-07), which blocked publishing.
c as (
    select
        snapshot_id,
        cast(sum(votes) filter (where party_code = 'D') as bigint) as d_votes,
        cast(sum(votes) filter (where party_code = 'R') as bigint) as r_votes,
        cast(sum(votes) as bigint) as total_votes,
        -- civicAPI's own winner flag; we never make calls (ADR-003)
        max(party_code) filter (where winner) as winner_party
    from {{ ref('stg_civic__candidate_results') }}
    where snapshot_id in (select snapshot_id from l)
    group by snapshot_id
)

select
    l.race_id,
    coalesce(t.label, l.election_name) as label,
    l.election_name,
    l.office,
    l.province,
    l.district,
    t.race_id is not null as is_tracked,
    l.percent_reporting as pct_reporting,
    coalesce(c.d_votes, 0) as d_votes,
    coalesce(c.r_votes, 0) as r_votes,
    coalesce(c.total_votes, 0) as total_votes,
    case
        when coalesce(c.d_votes, 0) + coalesce(c.r_votes, 0) > 0
            then 100.0 * (c.d_votes - c.r_votes) / (c.d_votes + c.r_votes)
    end as margin_pp,
    c.winner_party,
    l.round,
    l.is_disputed,
    l.test_data,
    coalesce(l.last_changed, l.source_last_updated) as last_updated,
    l.polls_close,
    l.fetched_at
from l
left join c using (snapshot_id)
left join {{ ref('tracked_races') }} as t on t.race_id = l.race_id
