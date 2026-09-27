-- ---------------------------------------------------------------------------
-- RECONSTRUCTED 2026-09 - see the note in int_orders__items_agg.sql.
--
-- GRAIN: one row per order_id with at least one review row (full data: 98,673;
-- 768 orders were never reviewed). review_id is NOT a key (814 duplicates), so the
-- source grain is (review_id, order_id) and an order can carry several reviews.
--
-- avg_review_score    = mean over the order's review rows
-- latest_review_score = score of the most recently answered review; ties broken on
--                       creation time, then review_id, so the pick is deterministic.
-- ---------------------------------------------------------------------------
with reviews as (
    select * from {{ ref('stg_olist__order_reviews') }}
),

ranked as (
    select
        order_id,
        review_score,
        row_number() over (
            partition by order_id
            order by review_answered_at desc nulls last,
                     review_created_at  desc nulls last,
                     review_id          desc
        ) as rn
    from reviews
)

select
    order_id,
    count(*)                                   as review_count,
    avg(review_score)                          as avg_review_score,
    max(case when rn = 1 then review_score end) as latest_review_score
from ranked
group by 1
