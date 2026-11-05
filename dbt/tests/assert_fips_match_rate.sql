-- error: >= 99% of County regions in statewide races map to a FIPS (AK, CT allow-listed)
with r as (
    select province, county_fips
    from {{ ref('int_region_fips') }}
    where office in ('senate', 'governor') and province not in ('AK', 'CT')
)
select count(*) as regions, count(county_fips) as matched
from r
having count(*) > 0 and count(county_fips) < 0.99 * count(*)
