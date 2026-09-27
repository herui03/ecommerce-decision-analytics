-- ---------------------------------------------------------------------------
-- RECONSTRUCTED 2026-09 - see the note in int_orders__items_agg.sql.
--
-- GRAIN: one row per order_id with at least one payment row (full data: 99,440;
-- one delivered order has no payment record).
--
-- primary_payment_type = the instrument type carrying the most money on the order.
-- Ties (equal value on two types) break on payment_type ascending so the result is
-- deterministic. It is ONE exclusive label per order: payment_total_brl is the whole
-- order's payment, including money paid with other instruments. A mart grouped by
-- primary_payment_type therefore reports "payments on orders whose primary instrument
-- is X", never "amount paid with X".
-- ---------------------------------------------------------------------------
with payments as (
    select * from {{ ref('stg_olist__order_payments') }}
),

by_type as (
    select order_id, payment_type, sum(payment_value_brl) as type_value_brl
    from payments
    group by 1, 2
),

ranked as (
    select
        order_id,
        payment_type,
        row_number() over (
            partition by order_id
            order by type_value_brl desc, payment_type asc      -- deterministic tie-break
        ) as rn
    from by_type
),

totals as (
    select
        order_id,
        sum(payment_value_brl)       as payment_total_brl,
        count(*)                     as payment_count,
        count(distinct payment_type) as distinct_payment_types,
        max(payment_installments)    as max_installments
    from payments
    group by 1
)

select
    t.order_id,
    t.payment_total_brl,
    t.payment_count,
    t.distinct_payment_types,
    t.max_installments,
    r.payment_type as primary_payment_type
from totals t
join ranked r on r.order_id = t.order_id and r.rn = 1
