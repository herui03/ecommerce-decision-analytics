-- ---------------------------------------------------------------------------
-- Category drill-down. GRAIN: one row per (month, category).
--
-- BUILT ON fct_order_items, NOT fct_orders. Category revenue is only additive at
-- item grain: 727 orders span more than one category, so attributing a whole
-- order to "its" category would misstate them. See docs/challenge-03.
--
-- Order counts here use count(distinct order_id) -- counting rows would report
-- line items as orders.
-- ---------------------------------------------------------------------------
with items as (
    select i.*
    from {{ ref('fct_order_items') }} i
    join {{ ref('fct_orders') }} o on o.order_id = i.order_id
    where o.is_in_analysis_window
)

select
    purchase_month,
    strftime(purchase_month, '%Y-%m')          as month_label,
    product_category,

    count(*)                                   as order_lines,
    count(distinct order_id)                   as orders,          -- NOT count(*)
    count(distinct customer_unique_id)         as customers,
    count(distinct product_id)                 as products_sold,
    count(distinct seller_id)                  as active_sellers,

    sum(item_total_brl)                        as gmv_brl,
    sum(item_price_brl)                        as goods_brl,
    sum(item_freight_brl)                      as freight_brl,
    avg(item_total_brl)                        as avg_line_value_brl,

    -- freight as a share of category GMV: a margin signal that differs sharply
    -- between heavy/bulky categories and light ones
    100.0 * sum(item_freight_brl)
        / nullif(sum(item_total_brl), 0)       as freight_share_pct,

    -- share of the month's total GMV, computed here so the dashboard doesn't
    sum(item_total_brl) * 100.0
        / nullif(sum(sum(item_total_brl)) over (partition by purchase_month), 0)
                                               as pct_of_month_gmv,

    count(*) filter (where has_no_category)    as lines_missing_category,
    count(*) filter (where missing_translation) as lines_missing_translation

from items
group by 1, 2, 3
