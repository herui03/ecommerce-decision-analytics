-- Grain: one row per zip prefix. 19,015 rows.
-- Pass-through of the intermediate centroid; exists so marts consumers never reach
-- past the mart layer into intermediate.
select
    zip_prefix,
    latitude,
    longitude,
    city,
    state,
    point_count as source_point_count
from {{ ref('int_geolocation__zip_centroid') }}
