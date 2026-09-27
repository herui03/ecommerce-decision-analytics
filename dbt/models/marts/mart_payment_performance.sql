-- Payment-mix drill-down. GRAIN: one row per (month, primary_payment_type).
-- primary_payment_type = the instrument carrying the most value on that order,
-- resolved in int_orders__payments_agg with a deterministic tie-break.
-- It is ONE exclusive label per order: payment_brl is the WHOLE order's payment total
-- (all instruments on those orders), not the amount paid with this instrument. Orders
-- add across groups because the groups are exclusive; payment_brl adds too, but reads
-- as "payments on orders whose primary instrument is X".
-- The single order with no payment record has a NULL type and is excluded here
-- rather than bucketed as 'unknown' -- it is an anomaly, not a payment method.
with orders as (
    select * from {{ ref('fct_orders') }}
    where is_in_analysis_window
      and primary_payment_type is not null
)

select
    purchase_month,
    strftime(purchase_month, '%Y-%m')                          as month_label,
    primary_payment_type,

    count(*)                                                   as orders,
    sum(payment_total_brl)                                     as payment_brl,
    sum(items_total_brl)                                       as gmv_brl,
    sum(items_total_brl)
        / nullif(count(*) filter (where not has_no_items), 0)  as aov_brl,

    avg(max_installments)                                      as avg_installments,
    count(*) filter (where max_installments > 1)               as installment_orders,
    100.0 * count(*) filter (where max_installments > 1)
        / nullif(count(*), 0)                                  as installment_rate_pct,

    count(*) * 100.0
        / nullif(sum(count(*)) over (partition by purchase_month), 0)
                                                               as pct_of_month_orders,

    -- ADDITIVE COMPONENTS (added 2026-09): AOV's denominator and the installment mean's
    -- valid count, so groups and months can be combined exactly.
    count(*) filter (where not has_no_items)                   as orders_with_items,
    sum(max_installments)                                      as installments_sum,
    count(max_installments)                                    as installments_n

from orders
group by 1, 2, 3
