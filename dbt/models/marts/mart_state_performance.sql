-- Geography drill-down. GRAIN: one row per (month, customer_state).
-- Built on fct_orders: state is an order-level attribute, so order grain is correct
-- here and category grain would double-count.
with orders as (
    select * from {{ ref('fct_orders') }}
    where is_in_analysis_window
)

select
    purchase_month,
    strftime(purchase_month, '%Y-%m')                          as month_label,
    customer_state,

    count(*)                                                   as orders,
    count(distinct customer_unique_id)                         as customers,
    sum(items_total_brl)                                       as gmv_brl,
    sum(items_freight_brl)                                     as freight_brl,

    sum(items_total_brl)
        / nullif(count(*) filter (where not has_no_items), 0)  as aov_brl,

    -- freight share by state is the headline geography insight in a country this
    -- large: remote states pay materially more to receive the same basket
    100.0 * sum(items_freight_brl)
        / nullif(sum(items_total_brl), 0)                      as freight_share_pct,

    avg(days_purchase_to_delivery) filter (where is_delivered) as avg_delivery_days,
    100.0 * count(*) filter (where is_delivered_late)
        / nullif(count(*) filter (where is_delivered), 0)      as late_delivery_rate_pct,
    avg(avg_review_score)                                      as avg_review_score,

    sum(items_total_brl) * 100.0
        / nullif(sum(sum(items_total_brl)) over (partition by purchase_month), 0)
                                                               as pct_of_month_gmv,

    -- ADDITIVE COMPONENTS (added 2026-09) so rates and means can be combined across
    -- months exactly: rate = sum(numerator) / sum(denominator). Extracts exported
    -- before this change lack them; the dashboard then reports combined late rate and
    -- combined means as unavailable instead of averaging percentages.
    count(*) filter (where not has_no_items)                   as orders_with_items,
    count(*) filter (where is_delivered)                       as delivered_orders,
    count(*) filter (where is_delivered_late)                  as late_orders,
    sum(days_purchase_to_delivery) filter (where is_delivered) as delivery_days_sum,
    count(days_purchase_to_delivery) filter (where is_delivered) as delivery_days_n,
    sum(avg_review_score)                                      as review_score_sum,
    count(avg_review_score)                                    as review_score_n

from orders
group by 1, 2, 3
