-- Called = civicAPI winner flags only. Totals = called + holdovers (seats not up).
with up as (
    select office, count(*) as seats_up
    from {{ source('bronze', 'race_catalog') }}
    group by office
),

called as (
    select
        office,
        count(*) filter (where winner_party = 'D') as d_called,
        count(*) filter (where winner_party = 'R') as r_called,
        count(*) filter (where winner_party in ('I', 'O')) as o_called
    from {{ ref('fct_race_latest') }}
    group by office
),

hold as (
    select
        office,
        cast(sum(seats_not_up) filter (where party_code = 'D') as bigint) as d_hold,
        cast(sum(seats_not_up) filter (where party_code = 'R') as bigint) as r_hold,
        cast(sum(seats_not_up) filter (where party_code in ('I', 'O')) as bigint) as o_hold
    from {{ ref('holdovers') }}
    group by office
)

select
    up.office,
    up.seats_up,
    coalesce(called.d_called, 0) as d_called,
    coalesce(called.r_called, 0) as r_called,
    coalesce(called.o_called, 0) as o_called,
    coalesce(hold.d_hold, 0) as d_not_up,
    coalesce(hold.r_hold, 0) as r_not_up,
    coalesce(hold.o_hold, 0) as o_not_up,
    coalesce(called.d_called, 0) + coalesce(hold.d_hold, 0) as d_total,
    coalesce(called.r_called, 0) + coalesce(hold.r_hold, 0) as r_total,
    coalesce(called.o_called, 0) + coalesce(hold.o_hold, 0) as o_total,
    up.seats_up
    - coalesce(called.d_called, 0) - coalesce(called.r_called, 0) - coalesce(called.o_called, 0)
        as uncalled,
    case up.office when 'senate' then 51 when 'house' then 218 end as majority_line
from up
left join called using (office)
left join hold using (office)
