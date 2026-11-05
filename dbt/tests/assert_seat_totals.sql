-- error: Senate seats sum to 100, House to 435 (called + not up + uncalled).
-- Needs the full live catalog, so it is skipped on the fixture (test) target, whose
-- catalog holds only a handful of races.
select office, d_total + r_total + o_total + uncalled as seats
from {{ ref('fct_chamber_summary') }}
where {{ 'false' if target.name == 'test' else 'true' }}
  and ((office = 'senate' and d_total + r_total + o_total + uncalled <> 100)
    or (office = 'house' and d_total + r_total + o_total + uncalled <> 435))
