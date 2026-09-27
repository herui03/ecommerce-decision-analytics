{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- Singular test: staging row counts must match the figures audited on
-- 2026-07-16 and published in docs/data-verification.md.
--
-- WHY THIS EXISTS
--   Every number in the README, the dashboard, and the interview material is
--   derived from these counts. If a source CSV is ever swapped, re-downloaded,
--   or silently truncated, those numbers become lies and nothing else would
--   catch it. This turns the verification log into an executable contract.
--
-- WHY A SINGULAR TEST AND NOT dbt_utils.expression_is_true
--   expression_is_true evaluates row-by-row inside a WHERE clause, so an
--   aggregate like count(*) is a binder error. Row-count assertions are
--   aggregate assertions and need their own query.
--
-- A dbt test FAILS if it returns rows. Every count that matches is filtered
-- out, so a clean run returns zero rows.
-- ---------------------------------------------------------------------------

with actual as (
    select 'stg_olist__orders'                      as model, count(*) as n from {{ ref('stg_olist__orders') }}
    union all select 'stg_olist__order_items',                count(*)      from {{ ref('stg_olist__order_items') }}
    union all select 'stg_olist__order_payments',             count(*)      from {{ ref('stg_olist__order_payments') }}
    union all select 'stg_olist__order_reviews',              count(*)      from {{ ref('stg_olist__order_reviews') }}
    union all select 'stg_olist__customers',                  count(*)      from {{ ref('stg_olist__customers') }}
    union all select 'stg_olist__products',                   count(*)      from {{ ref('stg_olist__products') }}
    union all select 'stg_olist__sellers',                    count(*)      from {{ ref('stg_olist__sellers') }}
    union all select 'stg_olist__geolocation',                count(*)      from {{ ref('stg_olist__geolocation') }}
    union all select 'stg_olist__product_categories',         count(*)      from {{ ref('stg_olist__product_categories') }}
    union all select 'stg_olist__marketing_qualified_leads',  count(*)      from {{ ref('stg_olist__marketing_qualified_leads') }}
    union all select 'stg_olist__closed_deals',               count(*)      from {{ ref('stg_olist__closed_deals') }}
),

expected (model, n) as (
    values
        ('stg_olist__orders',                       99441),
        ('stg_olist__order_items',                 112650),
        ('stg_olist__order_payments',              103886),
        ('stg_olist__order_reviews',                99224),
        ('stg_olist__customers',                    99441),
        ('stg_olist__products',                     32951),
        ('stg_olist__sellers',                       3095),
        ('stg_olist__geolocation',                1000163),
        ('stg_olist__product_categories',              71),
        ('stg_olist__marketing_qualified_leads',     8000),
        ('stg_olist__closed_deals',                   842)
)

select
    e.model,
    e.n as expected_rows,
    a.n as actual_rows,
    a.n - e.n as drift
from expected e
join actual a using (model)
where a.n != e.n
