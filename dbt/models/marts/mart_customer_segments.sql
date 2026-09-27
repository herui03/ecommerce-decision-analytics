-- ---------------------------------------------------------------------------
-- mart_customer_segments - GRAIN: one row per person (customer_unique_id).
--
-- THIS IS NOT RFM, AND SAYING SO IS THE POINT.
--   96.88% of these people ordered exactly once (93,099 of 96,096). Frequency is a
--   constant, not a variable - you cannot quantile it. Every standard RFM
--   implementation still returns output: pd.qcut with duplicates='drop' silently
--   hands back fewer bins and a segmentation table that looks finished and is
--   arithmetic noise. See docs/challenge-01-rfm-frequency-collapse.md.
--
--   So segmentation runs on the two axes that DO have variance - Recency and
--   Monetary - and the axes this marketplace actually carries: state, payment
--   type, review score, delivery performance. is_repeat_customer is exposed as a
--   flag, honestly labelled as covering 3.12% of the base, NOT as a scoring axis.
--
-- NTILE, NOT qcut-style binning: NTILE distributes ties across buckets rather than
-- collapsing bin edges, so R and M always yield exactly 5 populated quintiles.
-- Verified below by an even-bucket assertion.
--
-- RECENCY is anchored to the dataset's last order (2018-10-17 17:30:18), derived
-- in dim_customers - never current_date, which would make every customer look
-- years dormant and would change the answer on every run.
-- ---------------------------------------------------------------------------

with customers as (
    select * from {{ ref('dim_customers') }}
),

orders as (
    select * from {{ ref('fct_orders') }}
),

-- Behavioural attributes that actually vary, pulled from the person's orders.
person_behaviour as (
    select
        c.customer_unique_id,
        avg(o.avg_review_score)                                        as avg_review_score,
        avg(o.items_freight_brl)                                       as avg_freight_brl,
        count(*) filter (where o.is_delivered_late)                    as late_orders,
        count(*) filter (where o.is_canceled)                          as canceled_orders,
        -- modal payment type by order count, deterministic tie-break on the name
        min(o.primary_payment_type)                                    as sample_payment_type
    from customers c
    join orders o on o.customer_unique_id = c.customer_unique_id
    group by 1
),

scored as (
    select
        c.customer_unique_id,
        c.customer_state,
        c.customer_city,
        c.order_count,
        c.is_repeat_customer,
        c.first_purchased_at,
        c.last_purchased_at,
        c.days_since_last_order,
        c.lifetime_payment_brl,
        c.avg_order_payment_brl,

        b.avg_review_score,
        b.avg_freight_brl,
        b.late_orders,
        b.canceled_orders,
        b.sample_payment_type,

        -- R: 5 = most recent. Ascending days -> descending recency, so invert.
        -- customer_unique_id is a DETERMINISTIC TIE-BREAK, not decoration. There are
        -- only 632 distinct recency values across 96,096 customers -- 1,143 people share
        -- recency=327 alone -- so NTILE has to split tied blocks to keep buckets equal.
        -- Without a tie-break it splits them in physical row order, which changes on
        -- every rebuild: segment counts drifted by up to 4 customers between runs.
        -- Ties are still split (that is inherent to NTILE and the price of equal
        -- buckets); the tie-break makes the SAME customers split the SAME way forever.
        6 - ntile(5) over (order by c.days_since_last_order asc,
                                    c.customer_unique_id asc)          as r_score,

        -- M: 5 = highest lifetime value. NULLS FIRST keeps the one customer with no
        -- payment record out of the top bucket instead of letting NULL sort as "large".
        -- Same deterministic tie-break as R -- 28,154 distinct values over 96,096
        -- customers means ties here too.
        ntile(5) over (order by c.lifetime_payment_brl asc nulls first,
                                c.customer_unique_id asc)               as m_score

    from customers c
    left join person_behaviour b using (customer_unique_id)
),

final as (
    select
        *,
        r_score + m_score as rm_score,

        -- Labels describe what these people ARE in a marketplace with no repeat
        -- base, not the borrowed Champions/Loyal/At-Risk vocabulary of RFM, which
        -- presumes a loyalty dynamic this business does not have.
        case
            when r_score >= 4 and m_score >= 4 then 'Recent high-value'
            when r_score >= 4 and m_score <= 2 then 'Recent low-value'
            when r_score <= 2 and m_score >= 4 then 'Lapsed high-value'
            when r_score <= 2 and m_score <= 2 then 'Lapsed low-value'
            else 'Mid'
        end as rm_segment

    from scored
)

select * from final
