{# SQL mirror of elex.civic.classify.normalize_region_name (keep the two in sync). #}
{% macro normalize_region_name(col) -%}
case when regexp_matches({{ col }}, 'registered voters|^\s*all counties\b', 'i') then ''
else
regexp_replace(
  regexp_replace(
    regexp_replace(
      trim(regexp_replace(regexp_replace(replace(upper({{ col }}), '-', ' '), '[^A-Z0-9 ]', '', 'g'), '\s+', ' ', 'g')),
      ' (CENSUS AREA|MUNICIPALITY|BOROUGH|COUNTY|PARISH)$', ''),
    '^SAINT ', 'ST '),
  ' SAINT ', ' ST ', 'g')
end
{%- endmacro %}
