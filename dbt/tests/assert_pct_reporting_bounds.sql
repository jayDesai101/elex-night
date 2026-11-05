-- error: 0 <= percent_reporting <= 100 at race and region level
select 'race' as level, race_id, fetched_at, percent_reporting as pct
from {{ ref('stg_civic__race_snapshots') }}
where percent_reporting < 0 or percent_reporting > 100
union all
select distinct 'region', race_id, fetched_at, region_pct_reporting
from {{ ref('stg_civic__region_results') }}
where region_pct_reporting < 0 or region_pct_reporting > 100
