-- ---------------------------------------------------------------------------
-- RECONSTRUCTED 2026-09 - see the note in int_orders__items_agg.sql.
--
-- GRAIN: one row per zip prefix (full data: 19,015 from 1,000,163 raw points).
-- MEDIAN centroid, as documented: a handful of mis-geocoded points would drag a mean.
-- city/state = the most frequent label among the zip's points, ties broken
-- alphabetically so the model is deterministic.
-- ---------------------------------------------------------------------------
with geo as (
    select * from {{ ref('stg_olist__geolocation') }}
),

centroid as (
    select
        zip_prefix,
        median(latitude)  as latitude,
        median(longitude) as longitude,
        count(*)          as point_count
    from geo
    group by 1
),

label_counts as (
    select zip_prefix, city, state, count(*) as n
    from geo
    group by 1, 2, 3
),

modal_label as (
    select
        zip_prefix, city, state,
        row_number() over (
            partition by zip_prefix
            order by n desc, city asc, state asc
        ) as rn
    from label_counts
)

select
    c.zip_prefix,
    c.latitude,
    c.longitude,
    m.city,
    m.state,
    c.point_count
from centroid c
join modal_label m on m.zip_prefix = c.zip_prefix and m.rn = 1
