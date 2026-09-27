-- Grain: one row per seller_id (3,095).
with source as (select * from {{ source('olist_raw', 'olist_sellers_dataset') }}),

renamed as (
    select
        seller_id,
        cast(seller_zip_code_prefix as varchar) as seller_zip_prefix,
        seller_city,
        upper(seller_state) as seller_state
    from source
)

select * from renamed
