-- Latest stored snapshot per race.
select *
from {{ ref('stg_civic__race_snapshots') }}
qualify row_number() over (partition by race_id order by fetched_at desc) = 1
