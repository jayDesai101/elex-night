-- County-equivalent regions (see macro county_types) of each race's latest snapshot, with
-- FIPS from the API or, when the
-- API leaves it null (odd casing such as "Mcleod"), from the name crosswalk.
select
    r.race_id,
    l.office,
    l.province,
    l.fetched_at,
    r.region_key,
    r.region_name,
    r.region_pct_reporting,
    coalesce(r.region_fips, xw.county_fips) as county_fips,
    case
        when r.region_fips is not null then 'api'
        when xw.county_fips is not null then 'crosswalk_' || xw.match_method
    end as fips_source,
    r.candidate_name,
    r.party_label,
    r.party_code,
    r.votes
from {{ ref('stg_civic__region_results') }} as r
join {{ ref('int_race_latest') }} as l using (snapshot_id)
left join {{ ref('region_crosswalk') }} as xw
    on xw.province = l.province
    and xw.region_name_norm = {{ normalize_region_name('r.region_name') }}
where r.region_type in {{ county_types() }}
