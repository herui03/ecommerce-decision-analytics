{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- Singular test: the 96.88% one-time-customer figure is quoted in the README,
-- in challenge-01, and in the interview script. Lock it down.
--
-- Also asserts the independent cross-check: the number of duplicate
-- customer_unique_id rows (3,345) must equal sum(orders-1) over repeat
-- customers. Two different derivations of the same fact - if they ever
-- disagree, the frequency story is broken.
-- ---------------------------------------------------------------------------

with per_customer as (
    select c.customer_unique_id, count(distinct o.order_id) as order_count
    from {{ ref('stg_olist__orders') }} o
    join {{ ref('stg_olist__customers') }} c using (customer_id)
    group by 1
),

headline as (
    select
        count(*)                                                            as unique_customers,
        count(*) filter (where order_count = 1)                             as one_time,
        count(*) filter (where order_count > 1)                             as repeat_customers,
        max(order_count)                                                    as max_orders,
        round(100.0 * count(*) filter (where order_count = 1) / count(*), 2) as pct_one_time,
        sum(order_count - 1)                                                as excess_rows
    from per_customer
)

select * from headline
where unique_customers  != 96096
   or one_time          != 93099
   or repeat_customers  != 2997
   or max_orders        != 17
   or pct_one_time      != 96.88
   or excess_rows       != 3345          -- cross-check vs customers table duplication
