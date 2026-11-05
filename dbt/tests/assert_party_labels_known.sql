{{ config(severity='warn') }}
-- warn: party labels not in seeds/party_codes.csv (they map to O)
select distinct party_label
from {{ ref('stg_civic__candidate_results') }}
where party_label not in (select party_label from {{ ref('party_codes') }})
