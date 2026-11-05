{# civicAPI region types that are a county or county-equivalent on the map (us-atlas
   counties-10m): County; Parish (LA); Borough (AK); City (VA independent cities, which
   get their FIPS from the name crosswalk). Not included: Town/Township (ME, NH report
   counties too, and towns would double-count), Planning Region (CT, no crosswalk),
   House District / Overseas / State (AK and territory aggregates). #}
{% macro county_types() -%}
('County', 'Parish', 'Borough', 'City')
{%- endmacro %}
