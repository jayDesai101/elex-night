-- Office x county. House districts split counties, so House rows sum every district's
-- share of the county. baseline_margin_pp = 2024 presidential two-party margin, so the map
-- can mark counties that flipped.
with c as (
select
    f.office,
    f.county_fips,
    any_value(f.province) as state_po,
    any_value(f.region_name) as county_name,
    cast(sum(f.votes) filter (where f.party_code = 'D') as bigint) as d_votes,
    cast(sum(f.votes) filter (where f.party_code = 'R') as bigint) as r_votes,
    cast(sum(f.votes) as bigint) as total_votes,
    avg(f.region_pct_reporting) as pct_reporting,
    case
        when coalesce(sum(f.votes) filter (where f.party_code in ('D', 'R')), 0) > 0
            then 100.0
            * (coalesce(sum(f.votes) filter (where f.party_code = 'D'), 0)
                - coalesce(sum(f.votes) filter (where f.party_code = 'R'), 0))
            / sum(f.votes) filter (where f.party_code in ('D', 'R'))
    end as margin_pp,
    max(f.fetched_at) as fetched_at
from {{ ref('int_region_fips') }} as f
where f.county_fips is not null
group by f.office, f.county_fips
)

select
    c.*,
    case
        when b.pres24_dem + b.pres24_rep > 0
            then 100.0 * (b.pres24_dem - b.pres24_rep) / (b.pres24_dem + b.pres24_rep)
    end as baseline_margin_pp
from c
left join {{ source('ref', 'county_baseline') }} as b using (county_fips)
