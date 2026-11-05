select race_id, fetched_at, candidate_id, candidate_name, party_code, votes
from {{ ref('stg_civic__candidate_results') }}
