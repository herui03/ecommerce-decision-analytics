-- Grain: NONE. 1,000,163 rows, 19,015 distinct zip prefixes (~53 rows each).
-- Deliberately left at raw grain: staging stays 1:1 with the source. Collapsing to a
-- centroid is a modelling decision and lives in int_geolocation__zip_centroid.
-- Do NOT join this model directly to customers or sellers - it multiplies rows ~53x.
with source as (select * from {{ source('olist_raw', 'olist_geolocation_dataset') }})

select
    cast(geolocation_zip_code_prefix as varchar) as zip_prefix,
    cast(geolocation_lat as double) as latitude,
    cast(geolocation_lng as double) as longitude,
    geolocation_city  as city,
    upper(geolocation_state) as state
from source
