{{ config(tags=['invariant']) }}
-- The additive components added in 2026-09 must agree across marts and with the
-- valid-value counts they claim to be. If any of these fails, a combined mean or rate
-- in the dashboard would be divided by the wrong denominator.
with per_month as (
    -- payment mart + excluded (NULL primary type) population == monthly, EVERY month
    select mm.month_label,
           mm.orders, mm.orders_with_items, mm.gmv_brl, mm.payment_brl,
           coalesce(pp.orders, 0) + mm.orders_no_primary_payment              as p_orders,
           coalesce(pp.owi, 0) + mm.owi_no_primary_payment                    as p_owi,
           coalesce(pp.gmv, 0) + mm.gmv_no_primary_payment_brl                as p_gmv,
           coalesce(pp.pay, 0) + mm.payment_no_primary_payment_brl            as p_pay
    from {{ ref('mart_monthly_performance') }} mm
    left join (select month_label, sum(orders) as orders, sum(orders_with_items) as owi,
                      coalesce(sum(gmv_brl), 0) as gmv, coalesce(sum(payment_brl), 0) as pay
               from {{ ref('mart_payment_performance') }} group by 1) pp using (month_label)
),
payment_scope_breaks as (
    select count(*) as n from per_month
    where p_orders != orders or p_owi != orders_with_items
       or p_gmv != coalesce(gmv_brl, 0) or p_pay != coalesce(payment_brl, 0)
),
m as (
    select sum(orders_with_items) as owi, sum(delivered_orders) as delivered,
           sum(late_orders) as late, sum(delivery_days_n) as dd_n,
           sum(delivery_days_sum) as dd_sum, sum(review_score_n) as rv_n,
           sum(reviewed_orders) as reviewed, sum(items_n) as items_n,
           sum(installments_n) as inst_n, sum(low_score_orders) as low
    from {{ ref('mart_monthly_performance') }}
),
s as (
    select sum(orders_with_items) as owi, sum(delivered_orders) as delivered,
           sum(late_orders) as late, sum(delivery_days_n) as dd_n,
           sum(delivery_days_sum) as dd_sum, sum(review_score_n) as rv_n
    from {{ ref('mart_state_performance') }}
),
p as (
    select sum(orders_with_items) as owi, sum(installments_n) as inst_n, sum(orders) as orders
    from {{ ref('mart_payment_performance') }}
),
f as (
    select count(*) filter (where not has_no_items and primary_payment_type is not null) as owi_with_primary,
           count(*) filter (where primary_payment_type is not null) as orders_with_primary,
           count(*) filter (where is_delivered_late and not is_delivered) as late_not_delivered
    from {{ ref('fct_orders') }} where is_in_analysis_window
)
select 'additive components disagree' as problem, *
from m, s, p, f, payment_scope_breaks b
where b.n != 0
   or s.owi != m.owi or s.delivered != m.delivered or s.late != m.late
   or s.dd_n != m.dd_n or s.dd_sum is distinct from m.dd_sum or s.rv_n != m.rv_n
   or m.rv_n != m.reviewed          -- has_no_review <=> avg_review_score is NULL
   or m.items_n != m.owi            -- has_no_items  <=> item_count is NULL
   or m.dd_n > m.delivered          -- valid delivery durations are a subset of delivered
   or m.late > m.delivered
   or f.late_not_delivered != 0     -- late is defined on delivered orders only
   or p.owi != f.owi_with_primary
   or p.orders != f.orders_with_primary
   or p.inst_n != p.orders          -- every order in the payment mart has a payment row
   or m.low > m.reviewed
