-- ---------------------------------------------------------------------------
-- fct_order_items - GRAIN: one row per (order_id, order_item_seq). 112,650.
--
-- USE THIS FOR: revenue by category / product / seller. These are the only
--               grain at which category revenue is additive.
-- DO NOT USE FOR: counting orders. order_id repeats 13,984 times here - counting
--                 rows would report 112,650 "orders" against a true 99,441.
--                 Use count(distinct order_id), or use fct_orders.
--
-- The two facts are deliberately separate rather than one wide table. A single
-- table cannot hold both grains without either duplicating order-level money
-- across items (the fan-out that inflated payments 26% - see challenge-03) or
-- collapsing categories away. Two grains, two facts, one documented rule.
-- ---------------------------------------------------------------------------
with items    as (select * from {{ ref('stg_olist__order_items') }}),
     orders   as (select * from {{ ref('int_orders__enriched') }}),
     products as (select * from {{ ref('dim_products') }})

select
    -- keys
    i.order_id,
    i.order_item_seq,
    i.product_id,
    i.seller_id,
    o.customer_unique_id,

    -- date (inherited from the order - items have no purchase date of their own)
    o.purchased_at,
    cast(o.purchased_at as date)        as purchase_date,
    date_trunc('month', o.purchased_at) as purchase_month,

    -- product
    p.product_category,            -- EN, falling back to PT, then 'unknown'
    p.product_category_en,
    p.has_no_category,             -- 610 products carry no category at all
    p.missing_translation,         -- 13 products in 2 categories absent from the 71-row lookup

    -- geography
    o.customer_state,
    o.order_status,
    (o.order_status = 'delivered') as is_delivered,

    -- money - additive at THIS grain only
    i.item_price_brl,
    i.item_freight_brl,
    i.item_total_brl

from items i
join orders   o on o.order_id   = i.order_id       -- inner is safe: 0 orphan items, verified
left join products p on p.product_id = i.product_id
