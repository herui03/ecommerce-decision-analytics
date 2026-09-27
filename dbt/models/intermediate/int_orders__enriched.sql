-- ---------------------------------------------------------------------------
-- RECONSTRUCTED 2026-09 - see the note in int_orders__items_agg.sql.
--
-- GRAIN: one row per order = stg_olist__orders exactly (full data: 99,441).
-- The orders table is the spine and EVERY join is a LEFT JOIN onto it. Each child was
-- pre-aggregated to order grain first, so these joins cannot fan out, and no order is
-- dropped for missing a child (775 no-item, 1 no-payment, 768 no-review orders on the
-- full data, per the historical log).
--
-- NULLs are preserved, never zero-filled: NULL = "no record exists", 0.00 = "recorded
-- as zero". The has_no_* flags make each gap countable.
--
-- DELIVERY DEFINITIONS (explicit because the dashboard divides by them):
--   is_delivered_late = order_status = 'delivered' AND the delivery CALENDAR day is
--                       after the estimated CALENDAR day (delivery_days_vs_estimate > 0).
--                       Delivered on the estimated day = on time.
--                       A delivered-status order with no delivery timestamp cannot be
--                       evaluated; it stays in the delivered denominator (historical
--                       contract: late / delivered) and is never counted late. The
--                       count of such orders is exposed in the monthly mart so the
--                       possible understatement is visible, not hidden.
--   days_purchase_to_delivery = calendar-day difference; NULL when not delivered.
-- ---------------------------------------------------------------------------
with orders    as (select * from {{ ref('stg_olist__orders') }}),
     customers as (select * from {{ ref('stg_olist__customers') }}),
     items     as (select * from {{ ref('int_orders__items_agg') }}),
     payments  as (select * from {{ ref('int_orders__payments_agg') }}),
     reviews   as (select * from {{ ref('int_orders__reviews_agg') }})

select
    -- keys
    o.order_id,
    o.customer_id,
    c.customer_unique_id,

    -- customer address on THIS order (a person can hold several addresses)
    c.customer_zip_prefix,
    c.customer_city,
    c.customer_state,

    -- status and timestamps
    o.order_status,
    o.purchased_at,
    o.approved_at,
    o.handed_to_carrier_at,
    o.delivered_at,
    o.estimated_delivery_at,

    -- basket (NULL when the order has no items)
    i.item_count,
    i.distinct_sellers,
    i.distinct_products,
    i.items_price_brl,
    i.items_freight_brl,
    i.items_total_brl,

    -- payment (NULL when the order has no payment record)
    p.payment_total_brl,
    p.payment_count,
    p.distinct_payment_types,
    p.max_installments,
    p.primary_payment_type,

    -- satisfaction (NULL when unreviewed)
    r.review_count,
    r.avg_review_score,
    r.latest_review_score,

    -- fulfilment
    date_diff('day', o.purchased_at, o.delivered_at)                 as days_purchase_to_delivery,
    o.delivery_days_vs_estimate,
    coalesce(o.order_status = 'delivered'
             and o.delivery_days_vs_estimate > 0, false)             as is_delivered_late,

    -- data-quality flags, carried not hidden
    (i.order_id is null) as has_no_items,
    (p.order_id is null) as has_no_payment,
    (r.order_id is null) as has_no_review

from orders o
left join customers c on c.customer_id = o.customer_id
left join items     i on i.order_id    = o.order_id
left join payments  p on p.order_id    = o.order_id
left join reviews   r on r.order_id    = o.order_id
