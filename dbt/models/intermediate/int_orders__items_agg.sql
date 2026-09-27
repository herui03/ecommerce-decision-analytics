-- ---------------------------------------------------------------------------
-- RECONSTRUCTED 2026-09 (portfolio upgrade). The five intermediate models were
-- referenced by every mart and documented in docs/data-verification.md and
-- docs/challenge-03-silent-fanout.md, but the .sql files were never committed, so
-- the project could not build from a clean clone. This file re-implements the
-- documented contract; it is validated on the synthetic sample only. Equivalence to
-- the original (uncommitted) SQL on the full Olist data is UNVERIFIED.
--
-- GRAIN: one row per order_id that has at least one item (full data: 98,666, per
-- the historical log; 775 orders have none and are absent here by construction).
-- Aggregating BEFORE the join is the fan-out fix: nothing downstream can multiply.
-- ---------------------------------------------------------------------------
select
    order_id,
    count(*)                   as item_count,
    count(distinct seller_id)  as distinct_sellers,
    count(distinct product_id) as distinct_products,
    sum(item_price_brl)        as items_price_brl,
    sum(item_freight_brl)      as items_freight_brl,
    sum(item_total_brl)        as items_total_brl
from {{ ref('stg_olist__order_items') }}
group by 1
