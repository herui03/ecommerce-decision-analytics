-- Grain: one row per PT category name (71).
with source as (select * from {{ source('olist_raw', 'product_category_name_translation') }})

select
    product_category_name         as product_category_pt,
    product_category_name_english as product_category_en
from source
