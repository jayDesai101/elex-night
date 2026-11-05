{{ config(severity='warn') }}
-- warn: votes never decrease per race x candidate (real counts do get corrected down)
with t as (
    select
        race_id, candidate_id, candidate_name, fetched_at, votes,
        lag(votes) over (partition by race_id, candidate_id order by fetched_at) as prev_votes
    from {{ ref('fct_race_timeseries') }}
)
select *, round(100.0 * (prev_votes - votes) / nullif(prev_votes, 0), 2) as drop_pct
from t
where votes < prev_votes
