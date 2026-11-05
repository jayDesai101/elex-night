-- error: every region candidate matches a race candidate on (name, party), checked on
-- each race's latest snapshot
with latest as (select snapshot_id from {{ ref('int_race_latest') }})
select distinct r.race_id, r.fetched_at, r.region_key, r.candidate_name, r.party_label
from {{ ref('stg_civic__region_results') }} as r
join latest using (snapshot_id)
left join {{ ref('stg_civic__candidate_results') }} as c
    on c.snapshot_id = r.snapshot_id
    and c.candidate_name = r.candidate_name
    and c.party_label is not distinct from r.party_label
where c.snapshot_id is null
