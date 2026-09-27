-- ---------------------------------------------------------------------------
-- Headline business-performance trend. GRAIN: one row per month. 20 rows.
--
-- Analysis window only (2017-01 → 2018-08). Charting the raw range would show
-- growth from 4 orders to 7,544 and then a collapse to 4 - both ends are export
-- artifacts, not the business. See docs/challenge-04-*.md.
--
-- EVERY RATIO IS COMPUTED HERE, NOT IN THE DASHBOARD. Tableau does no arithmetic:
-- it plots columns. That keeps the metric definition in one auditable place and
-- means the BI tool is replaceable without redefining the business.
--
-- DENOMINATORS ARE EXPLICIT AND DIFFERENT ON PURPOSE:
--   AOV        ÷ orders WITH items      (775 orders have none; dividing by all
--                                        orders would understate AOV)
--   cancel     ÷ ALL orders             (that is what a cancellation rate means)
--   late rate  ÷ DELIVERED orders       (an undelivered order cannot be late yet)
--   review     ÷ REVIEWED orders        (768 orders were never reviewed; scoring
--                                        them as 0 would invent dissatisfaction)
-- ---------------------------------------------------------------------------
with orders as (
    select * from {{ ref('fct_orders') }}
    where is_in_analysis_window
)

select
    purchase_month,
    strftime(purchase_month, '%Y-%m')                          as month_label,

    -- volume
    count(*)                                                   as orders,
    count(distinct customer_unique_id)                         as active_customers,

    -- value (NULLs excluded by sum/avg automatically -- never zero-filled)
    sum(items_total_brl)                                       as gmv_brl,
    sum(items_price_brl)                                       as goods_brl,
    sum(items_freight_brl)                                     as freight_brl,
    sum(payment_total_brl)                                     as payment_brl,

    -- AOV over orders that actually have a basket
    count(*) filter (where not has_no_items)                   as orders_with_items,
    sum(items_total_brl)
        / nullif(count(*) filter (where not has_no_items), 0)  as aov_brl,

    -- cancellation, over ALL orders
    count(*) filter (where is_canceled)                        as canceled_orders,
    100.0 * count(*) filter (where is_canceled)
        / nullif(count(*), 0)                                  as cancel_rate_pct,

    -- fulfilment, over DELIVERED orders only
    count(*) filter (where is_delivered)                       as delivered_orders,
    count(*) filter (where is_delivered_late)                  as late_orders,
    100.0 * count(*) filter (where is_delivered_late)
        / nullif(count(*) filter (where is_delivered), 0)      as late_delivery_rate_pct,
    avg(days_purchase_to_delivery) filter (where is_delivered) as avg_delivery_days,

    -- satisfaction, over REVIEWED orders only
    count(*) filter (where not has_no_review)                  as reviewed_orders,
    avg(avg_review_score)                                      as avg_review_score,
    100.0 * count(*) filter (where latest_review_score <= 2)
        / nullif(count(*) filter (where not has_no_review), 0) as low_score_rate_pct,

    -- basket shape
    avg(item_count)                                            as avg_items_per_order,
    avg(max_installments)                                      as avg_installments,

    -- ADDITIVE COMPONENTS (added 2026-09). Every mean above is a mean over the rows
    -- where its input is non-NULL, so its true denominator is a VALID-VALUE count, not
    -- orders / delivered / reviewed. A dashboard that combines months must re-derive
    -- each mean as sum(numerator) / sum(valid count) - never a mean of monthly means and
    -- never a mean weighted by a count it did not divide by. These columns make that
    -- exact. Extracts exported before this change do not carry them, so combined means
    -- are reported as unavailable for those extracts.
    count(*) filter (where latest_review_score <= 2)           as low_score_orders,
    sum(days_purchase_to_delivery) filter (where is_delivered) as delivery_days_sum,
    count(days_purchase_to_delivery) filter (where is_delivered) as delivery_days_n,
    count(*) filter (where is_delivered and delivered_at is null) as delivered_missing_delivery_date,
    sum(avg_review_score)                                      as review_score_sum,
    count(avg_review_score)                                    as review_score_n,
    sum(item_count)                                            as items_sold,
    count(item_count)                                          as items_n,
    sum(max_installments)                                      as installments_sum,
    count(max_installments)                                    as installments_n,

    -- EXCLUDED-FROM-PAYMENT-MART components (added 2026-09). mart_payment_performance
    -- drops orders whose primary_payment_type is NULL (no payment record). These
    -- columns account for exactly that population, so the payment view reconciles to
    -- this month per month: payment mart + these = monthly totals. The coalesce is
    -- the value of an EMPTY sum (no such orders -> 0), not a zero-fill of a NULL order.
    count(*) filter (where primary_payment_type is null)       as orders_no_primary_payment,
    count(*) filter (where primary_payment_type is null
                       and not has_no_items)                   as owi_no_primary_payment,
    coalesce(sum(items_total_brl)
             filter (where primary_payment_type is null), 0)   as gmv_no_primary_payment_brl,
    coalesce(sum(payment_total_brl)
             filter (where primary_payment_type is null), 0)   as payment_no_primary_payment_brl

from orders
group by 1
