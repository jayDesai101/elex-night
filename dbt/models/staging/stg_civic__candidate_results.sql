with snaps as (
    select s.snapshot_id, s.race_id, s.fetched_at, s.payload
    from {{ source('bronze', 'race_snapshots') }} as s
    where s.snapshot_id in (select snapshot_id from {{ ref('stg_civic__race_snapshots') }})
),

cands as (
    select
        snapshot_id,
        race_id,
        fetched_at,
        unnest(from_json(
            payload -> '$.candidates',
            '[{"name":"VARCHAR","candidate_id":"BIGINT","party":"VARCHAR","votes":"BIGINT","percent":"DOUBLE","winner":"BOOLEAN","incumbent":"BOOLEAN"}]'
        )) as c
    from snaps
)

select
    cands.snapshot_id,
    cands.race_id,
    cands.fetched_at,
    c.candidate_id,
    c.name as candidate_name,
    c.party as party_label,
    coalesce(pc.party_code, 'O') as party_code,
    c.votes,
    c.percent as pct,
    coalesce(c.winner, false) as winner,
    c.incumbent
from cands
left join {{ ref('party_codes') }} as pc on pc.party_label = c.party
-- civicAPI's earliest history snapshots (weeks before the election, every candidate at 0
-- votes) list candidates without a candidate_id; nothing downstream can key them.
where c.candidate_id is not null
