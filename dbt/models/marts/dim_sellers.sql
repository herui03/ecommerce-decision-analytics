-- Grain: one row per seller. 3,095 rows.
with sellers as (select * from {{ ref('stg_olist__sellers') }}),
     geo     as (select * from {{ ref('int_geolocation__zip_centroid') }})

select
    s.seller_id,
    s.seller_state,
    s.seller_city,
    s.seller_zip_prefix,
    g.latitude  as seller_latitude,
    g.longitude as seller_longitude,
    (g.zip_prefix is null) as seller_zip_not_geocoded
from sellers s
left join geo g on g.zip_prefix = s.seller_zip_prefix
