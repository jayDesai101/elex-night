-- error: votes >= 0 everywhere
select 'race' as level, race_id, fetched_at, candidate_name, votes
from {{ ref('stg_civic__candidate_results') }}
where votes < 0
union all
select 'region', race_id, fetched_at, candidate_name, votes
from {{ ref('stg_civic__region_results') }}
where votes < 0
