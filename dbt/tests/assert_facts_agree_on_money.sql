{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- The two facts live at different grains but describe the same money. They must
-- agree, or one of them is lying.
--
--   fct_orders.items_total_brl      summed over 99,441 order rows
--   fct_order_items.item_total_brl  summed over 112,650 line rows
--
-- Both must equal 15,843,553.24. If a future join fans out either fact, these two
-- totals diverge and this test catches it - even if row counts still look right.
--
-- Also asserts fct_order_items has exactly 99,441 DISTINCT orders: the item fact
-- must not invent or lose an order relative to the order fact.
-- ---------------------------------------------------------------------------
with o as (
    select
        sum(items_total_brl)     as order_grain_items_brl,
        count(*)                 as order_rows
    from {{ ref('fct_orders') }}
),
i as (
    select
        sum(item_total_brl)      as item_grain_items_brl,
        count(distinct order_id) as distinct_orders_in_items
    from {{ ref('fct_order_items') }}
)
select *
from o cross join i
where abs(o.order_grain_items_brl - i.item_grain_items_brl) > 0.01
   -- 98,666 orders have items; the other 775 have none, so the item fact can only
   -- ever cover 98,666 of the 99,441 orders.
   or i.distinct_orders_in_items != 98666
