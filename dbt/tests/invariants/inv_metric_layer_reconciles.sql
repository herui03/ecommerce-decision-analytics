{{ config(tags=['invariant']) }}
-- Data-agnostic reconciliation of the metric layer (the full-data version pins
-- 20 months / 99,092 orders / 112,279 lines). Every mart must land on the same
-- in-window item GMV as fct_orders, exactly (DECIMAL arithmetic, no tolerance).
with truth as (
    select count(*)                                   as orders,
           sum(items_total_brl)                       as gmv,
           count(*) filter (where primary_payment_type is null) as orders_no_primary,
           sum(items_total_brl) filter (where primary_payment_type is null) as gmv_no_primary,
           count(*) filter (where not has_no_items)   as orders_with_items,
           count(distinct purchase_month)             as months,
           date_diff('month', min(purchase_month), max(purchase_month)) + 1 as month_span
    from {{ ref('fct_orders') }}
    where is_in_analysis_window
),
lines_truth as (
    select count(*) as lines
    from {{ ref('fct_order_items') }} i
    join {{ ref('fct_orders') }} o on o.order_id = i.order_id
    where o.is_in_analysis_window
),
m as (select count(*) as months, sum(orders) as orders, sum(gmv_brl) as gmv,
             sum(orders_with_items) as owi from {{ ref('mart_monthly_performance') }}),
c as (select sum(gmv_brl) as gmv, sum(order_lines) as lines, sum(orders) as summed_orders
      from {{ ref('mart_category_performance') }}),
s as (select sum(gmv_brl) as gmv, sum(orders) as orders from {{ ref('mart_state_performance') }}),
p as (select coalesce(sum(gmv_brl), 0) as gmv, sum(orders) as orders from {{ ref('mart_payment_performance') }})
select 'reconciliation failed' as problem, *
from truth t, lines_truth lt, m, c, s, p
where m.months != t.months
   or t.months != t.month_span                       -- a gap month would be invisible in a group by
   or m.orders != t.orders
   or m.gmv is distinct from t.gmv
   or m.owi != t.orders_with_items
   or c.gmv is distinct from t.gmv
   or s.gmv is distinct from t.gmv
   or s.orders != t.orders
   or p.gmv != coalesce(t.gmv, 0) - coalesce(t.gmv_no_primary, 0)
   or p.orders != t.orders - t.orders_no_primary
   or c.lines != lt.lines
   -- distinct orders summed over categories: at least every order with items once,
   -- never more than one per line (count(*) swapped in would make it equal lines
   -- only when no order has two lines - the sample guarantees multi-line orders).
   or c.summed_orders < t.orders_with_items
   or c.summed_orders >= c.lines
