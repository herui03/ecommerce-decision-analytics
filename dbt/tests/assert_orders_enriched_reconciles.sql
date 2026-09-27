-- ---------------------------------------------------------------------------
-- Money must survive the aggregation. To the cent.
--
-- The fan-out bug does not announce itself - it produces a plausible, slightly
-- larger number. The only way to catch it is to assert that the total in the
-- order-grain fact equals the total at the original source grain.
--
-- Verified 2026-07-16:
--   items_total_brl   sums to 15,843,553.24  at BOTH item grain and order grain
--   payment_total_brl sums to 16,008,872.12  at BOTH payment grain and order grain
--
-- Tolerance is 0.01 to absorb decimal(12,2) summation order, not to paper over
-- a real gap: the observed difference is exactly 0.00.
-- ---------------------------------------------------------------------------

with fact as (
    select
        count(*)                as fact_rows,
        sum(items_total_brl)    as fact_items_brl,
        sum(payment_total_brl)  as fact_payment_brl
    from {{ ref('int_orders__enriched') }}
),

source_truth as (
    select
        (select count(*)              from {{ ref('stg_olist__orders') }})         as source_orders,
        (select sum(item_total_brl)   from {{ ref('stg_olist__order_items') }})    as source_items_brl,
        (select sum(payment_value_brl) from {{ ref('stg_olist__order_payments') }}) as source_payment_brl
)

select
    f.fact_rows,
    s.source_orders,
    f.fact_items_brl,
    s.source_items_brl,
    f.fact_payment_brl,
    s.source_payment_brl
from fact f
cross join source_truth s
where f.fact_rows                             != s.source_orders
   or abs(f.fact_items_brl   - s.source_items_brl)   > 0.01
   or abs(f.fact_payment_brl - s.source_payment_brl) > 0.01
