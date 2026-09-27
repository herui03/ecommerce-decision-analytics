-- ---------------------------------------------------------------------------
-- fct_orders - GRAIN: one row per order. 99,441.
--
-- USE THIS FOR: order counts, AOV, delivery performance, payment mix, customer
--               geography, cancellation rate.
-- DO NOT USE FOR: anything by product category or seller.
--
-- WHY NOT CATEGORY
--   An order can span more than one category - verified: 712 orders span 2 and 15
--   span 3. Only 97.86% are single-category, which is exactly the trap: the number
--   is high enough that stamping "the" category onto the order looks harmless, and
--   it would misattribute 727 orders' revenue. Category revenue lives in
--   fct_order_items, at item grain, where it is actually additive.
-- ---------------------------------------------------------------------------
with orders as (select * from {{ ref('int_orders__enriched') }}),
     geo    as (select * from {{ ref('dim_geography') }})

select
    -- keys
    o.order_id,
    o.customer_unique_id,

    -- date spine helpers
    o.purchased_at,
    cast(o.purchased_at as date)          as purchase_date,
    date_trunc('month', o.purchased_at)   as purchase_month,

    -- geography
    o.customer_state,
    o.customer_city,
    g.latitude  as customer_latitude,
    g.longitude as customer_longitude,
    (g.zip_prefix is null) as customer_zip_not_geocoded,   -- 278 of 99,441 (0.28%)

    -- status
    o.order_status,
    (o.order_status = 'delivered') as is_delivered,
    (o.order_status = 'canceled')  as is_canceled,

    -- basket (NULL when no items - 775 orders)
    o.item_count,
    o.distinct_sellers,
    o.items_price_brl,
    o.items_freight_brl,
    o.items_total_brl,

    -- payment (NULL for the 1 unpaid order)
    o.payment_total_brl,
    o.payment_count,
    o.max_installments,
    o.primary_payment_type,

    -- fulfilment
    o.delivered_at,
    o.days_purchase_to_delivery,
    o.delivery_days_vs_estimate,
    o.is_delivered_late,

    -- satisfaction (NULL when unreviewed - 768 orders)
    o.avg_review_score,
    o.latest_review_score,

    -- Analysis window. The fact keeps ALL 99,441 orders; this flag lets the metric
    -- layer exclude the 349 (0.35%) that are export artifacts rather than business:
    -- 329 from the 2016 pilot (incl. a month with zero orders) and 20 from the
    -- 2018-09/10 tail where the daily count had already collapsed to 1-4.
    -- See dbt_project.yml vars and docs/challenge-04-*.md.
    (o.purchased_at >= timestamp '{{ var("analysis_window_start") }}'
     and o.purchased_at < timestamp '{{ var("analysis_window_end") }}') as is_in_analysis_window,

    -- data-quality flags, carried not hidden
    o.has_no_items,
    o.has_no_payment,
    o.has_no_review

from orders o
left join geo g on g.zip_prefix = o.customer_zip_prefix
