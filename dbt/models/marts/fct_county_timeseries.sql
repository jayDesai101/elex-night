-- County results of every archived snapshot, for the recap replay. One row per race x
-- county x snapshot where the county's numbers changed: search-sourced snapshots carry the
-- previous full payload's regions, so they repeat old values and drop out here.
with snap as (
    select
        r.race_id,
        l.office,
        r.fetched_at,
        coalesce(r.region_fips, xw.county_fips) as county_fips,
        cast(sum(r.votes) filter (where r.party_code = 'D') as bigint) as d_votes,
        cast(sum(r.votes) filter (where r.party_code = 'R') as bigint) as r_votes,
        cast(sum(r.votes) as bigint) as total_votes,
        avg(r.region_pct_reporting) as pct_reporting
    from {{ ref('stg_civic__region_results') }} as r
    join {{ ref('int_race_latest') }} as l using (race_id)
    left join {{ ref('region_crosswalk') }} as xw
        on xw.province = l.province
        and xw.region_name_norm = {{ normalize_region_name('r.region_name') }}
    where r.region_type in {{ county_types() }}
    group by r.race_id, l.office, r.fetched_at, 4
),

changed as (
    select
        *,
        lag(d_votes) over w as prev_d,
        lag(r_votes) over w as prev_r,
        lag(total_votes) over w as prev_total,
        lag(pct_reporting) over w as prev_pct
    from snap
    where county_fips is not null and office in ('senate', 'house', 'governor')
    window w as (partition by race_id, county_fips order by fetched_at)
)

select
    office,
    race_id,
    county_fips,
    fetched_at,
    coalesce(d_votes, 0) as d_votes,
    coalesce(r_votes, 0) as r_votes,
    coalesce(total_votes, 0) as total_votes,
    pct_reporting
from changed
where prev_total is null
    or d_votes is distinct from prev_d
    or r_votes is distinct from prev_r
    or total_votes is distinct from prev_total
    or pct_reporting is distinct from prev_pct
