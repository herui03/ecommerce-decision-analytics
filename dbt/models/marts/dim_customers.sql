-- Grain: one row per PERSON (customer_unique_id). 96,096 rows.
-- NOT per customer_id - that is per-order and would give 99,441 rows and a fake
-- 100% one-time rate. See docs/challenge-01-rfm-frequency-collapse.md.
--
-- ADDRESS: a person can hold more than one. Verified: 250 people have multiple zip
-- prefixes and 39 span multiple states (max 3 of each). The address is therefore
-- taken from their MOST RECENT order, with a deterministic tie-break on customer_id
-- so the model is reproducible - without it, two orders at the same timestamp would
-- return an arbitrary winner per run.
--
-- NO FREQUENCY SEGMENTATION: 96.88% of these people ordered exactly once, so
-- Frequency is a constant and cannot be quantiled. order_count is exposed as a fact,
-- not as a segmentation axis.
with customers as (select * from {{ ref('stg_olist__customers') }}),
     orders    as (select * from {{ ref('int_orders__enriched') }}),

-- Recency anchor = the dataset's own last order, computed, never hardcoded.
-- Verified 2026-07-16: 2018-10-17 17:30:18 (min is 2016-09-04 21:15:19).
-- Deriving it means the model cannot drift out of sync with the data, and
-- tests/assert_recency_anchor.sql fails loudly if that date ever moves.
anchor as (
    select max(purchased_at) as as_of_at from orders
),

person_orders as (
    select
        c.customer_unique_id,
        o.order_id,
        o.purchased_at,
        o.payment_total_brl,
        c.customer_id,
        c.customer_state,
        c.customer_city,
        c.customer_zip_prefix,
        row_number() over (
            partition by c.customer_unique_id
            order by o.purchased_at desc, c.customer_id asc   -- deterministic tie-break
        ) as rn_latest
    from customers c
    join orders o on o.customer_id = c.customer_id
),

latest_address as (
    select
        customer_unique_id,
        customer_state as customer_state,
        customer_city  as customer_city,
        customer_zip_prefix as customer_zip_prefix
    from person_orders
    where rn_latest = 1
),

behaviour as (
    select
        customer_unique_id,
        count(distinct order_id)         as order_count,
        min(purchased_at)                as first_purchased_at,
        max(purchased_at)                as last_purchased_at,
        -- payment_total_brl is NULL for the single unpaid order; sum ignores NULLs,
        -- so this is "money we have a record of", not "money we assume".
        sum(payment_total_brl)           as lifetime_payment_brl,
        avg(payment_total_brl)           as avg_order_payment_brl
    from person_orders
    group by 1
)

select
    b.customer_unique_id,
    a.customer_state,
    a.customer_city,
    a.customer_zip_prefix,
    b.order_count,
    (b.order_count > 1) as is_repeat_customer,     -- true for 2,997 of 96,096 (3.12%)
    b.first_purchased_at,
    b.last_purchased_at,
    b.lifetime_payment_brl,
    b.avg_order_payment_brl,
    -- Recency is measured against the dataset's last order, NOT current_date.
    -- The data ends 2018-10-17; using current_date would make every customer look
    -- years dormant and would silently change the value on every single run.
    date_diff('day', b.last_purchased_at, x.as_of_at) as days_since_last_order
from behaviour b
left join latest_address a using (customer_unique_id)
cross join anchor x
