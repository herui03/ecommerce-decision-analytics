-- Grain: one row per product_id (32,951). Category joined to EN in the mart layer.
with source as (select * from {{ source('olist_raw', 'olist_products_dataset') }}),

renamed as (
    select
        product_id,
        product_category_name as product_category_pt,
        cast(product_name_lenght        as integer) as product_name_length,
        cast(product_description_lenght as integer) as product_description_length,
        cast(product_photos_qty         as integer) as product_photos_qty,
        cast(product_weight_g           as integer) as product_weight_g,
        cast(product_length_cm          as integer) as product_length_cm,
        cast(product_height_cm          as integer) as product_height_cm,
        cast(product_width_cm           as integer) as product_width_cm
    from source
)

select * from renamed
