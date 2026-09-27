-- Grain: one row per (order_id, order_item_id) - 112,650. NOT one per order.
-- order_id repeats 13,984 times. Any consumer MUST aggregate to order grain first.
with source as (select * from {{ source('olist_raw', 'olist_order_items_dataset') }}),

renamed as (
    select
        order_id,
        cast(order_item_id as integer) as order_item_seq,   -- 1..N within the order
        product_id,
        seller_id,
        cast(shipping_limit_date as timestamp) as shipping_limit_at,
        cast(price         as decimal(12,2)) as item_price_brl,
        cast(freight_value as decimal(12,2)) as item_freight_brl,
        cast(price as decimal(12,2)) + cast(freight_value as decimal(12,2)) as item_total_brl
    from source
)

select * from renamed
