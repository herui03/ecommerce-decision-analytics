{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- The metric layer must not invent or lose money relative to the facts it
-- aggregates. Two independent reconciliations:
--
--  1. mart_monthly_performance GMV  ==  fct_orders GMV (in-window)
--  2. mart_category_performance GMV ==  fct_order_items GMV (in-window)
--
-- These two marts are built on DIFFERENT facts at DIFFERENT grains. If either
-- aggregation ever fans out or filters wrongly, its total diverges from its own
-- source and this fails -- before a wrong GMV reaches a dashboard.
--
-- Also asserts the window itself: exactly 20 months, exactly 99,092 orders.
-- ---------------------------------------------------------------------------
with monthly as (
    select
        count(*)         as months,
        sum(orders)      as orders,
        sum(gmv_brl)     as gmv_brl
    from {{ ref('mart_monthly_performance') }}
),
orders_truth as (
    select
        count(*)              as orders,
        sum(items_total_brl)  as gmv_brl
    from {{ ref('fct_orders') }}
    where is_in_analysis_window
),
category as (
    select
        sum(gmv_brl)     as gmv_brl,
        sum(order_lines) as order_lines,
        sum(orders)      as summed_orders
    from {{ ref('mart_category_performance') }}
),
items_truth as (
    select
        sum(i.item_total_brl) as gmv_brl,
        count(*)              as order_lines
    from {{ ref('fct_order_items') }} i
    join {{ ref('fct_orders') }} o on o.order_id = i.order_id
    where o.is_in_analysis_window
)
select
    m.months, m.orders as monthly_orders, ot.orders as fct_orders_count,
    m.gmv_brl as monthly_gmv, ot.gmv_brl as fct_gmv,
    c.gmv_brl as category_gmv, it.gmv_brl as items_gmv
from monthly m
cross join orders_truth ot
cross join category c
cross join items_truth it
where m.months                             != 20
   or m.orders                             != 99092
   or m.orders                             != ot.orders
   or abs(m.gmv_brl - ot.gmv_brl)          > 0.01
   or abs(c.gmv_brl - it.gmv_brl)          > 0.01
   -- Order-count integrity in the category mart. Added after mutation testing showed
   -- the GMV-only checks above stayed GREEN when count(distinct order_id) was swapped
   -- for count(*) -- i.e. line items silently reported as orders.
   --   line total must match the item fact exactly:            112,279 in-window
   --   summed distinct orders must be STRICTLY FEWER than lines: 99,154 < 112,279
   -- The strict inequality is what catches count(*): it would force the two equal.
   -- (summed_orders exceeds the true 99,092 on purpose -- the 727 multi-category
   --  orders are counted once per category, which is correct for a drill-down.)
   or c.order_lines                        != it.order_lines
   or c.order_lines                        != 112279
   or c.summed_orders                      >= c.order_lines
