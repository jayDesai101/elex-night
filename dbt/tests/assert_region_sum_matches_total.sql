{{ config(severity='warn') }}
-- warn: sum of County regions vs race votes within max(0.5%, 50) per candidate,
-- latest snapshot, races that report County regions
with reg as (
    select snapshot_id, candidate_name, party_label, sum(votes) as region_votes
    from {{ ref('stg_civic__region_results') }}
    where region_type = 'County'
      and snapshot_id in (select snapshot_id from {{ ref('int_race_latest') }})
    group by all
)
select c.race_id, c.candidate_name, c.votes, reg.region_votes
from reg
join {{ ref('stg_civic__candidate_results') }} as c
    on c.snapshot_id = reg.snapshot_id
    and c.candidate_name = reg.candidate_name
    and c.party_label is not distinct from reg.party_label
where abs(c.votes - reg.region_votes) > greatest(0.005 * c.votes, 50)
