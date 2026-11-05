-- error: no test-data snapshots in gold unless var include_test_data
select race_id, fetched_at
from {{ ref('fct_race_latest') }}
where test_data and not {{ var('include_test_data') }}
