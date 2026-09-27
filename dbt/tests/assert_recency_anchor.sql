{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- Guards the recency anchor in dim_customers.
--
-- WHY THIS TEST EXISTS IN THIS SHAPE
--   The first version of this test asserted min/max of fct_orders.purchased_at.
--   Mutation testing showed that was useless: swapping dim_customers' anchor to
--   current_date left fct_orders untouched, so the test stayed green while every
--   customer's recency silently became ~2,800 days wrong. The test has to assert
--   the OUTPUT, not the input it was derived from.
--
--   min(days_since_last_order) = 0 is a necessary property of a historic dataset:
--   whoever placed the final order has, by definition, zero days since their last
--   order. Anchoring to current_date makes that impossible.
--
-- Verified 2026-07-16: min 0, max 773, over a window of
-- 2016-09-04 21:15:19 → 2018-10-17 17:30:18.
-- ---------------------------------------------------------------------------
with recency as (
    select
        min(days_since_last_order) as min_days,
        max(days_since_last_order) as max_days
    from {{ ref('dim_customers') }}
),
window_bounds as (
    select
        min(purchased_at) as first_order_at,
        max(purchased_at) as last_order_at
    from {{ ref('fct_orders') }}
)
select *
from recency cross join window_bounds
where min_days       != 0                                    -- anchor drifted off the data
   or max_days       != 773
   or first_order_at != timestamp '2016-09-04 21:15:19'
   or last_order_at  != timestamp '2018-10-17 17:30:18'
