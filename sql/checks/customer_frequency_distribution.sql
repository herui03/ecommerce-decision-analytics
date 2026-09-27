-- ---------------------------------------------------------------------------
-- customer_frequency_distribution.sql
--
-- PURPOSE
--   Establish whether the Olist customer base has enough repeat-purchase
--   behaviour to support (a) the Frequency axis of an RFM segmentation and
--   (b) a cohort-retention curve.
--
-- WHY THE JOIN KEY IS THE WHOLE POINT
--   Olist mints a NEW customer_id for every order. Grouping on customer_id
--   therefore reports 1 order per "customer" by construction -- a fake 100%
--   one-time rate that looks like a finding and is an artifact.
--   customer_unique_id is the stable person-level key. Using it is what makes
--   the 3.12% repeat population visible at all.
--
-- WHY COUNT(DISTINCT order_id) AND NOT COUNT(*)
--   orders is already one row per order, so COUNT(*) would agree here. DISTINCT
--   is defensive: it keeps this check correct if the model is ever pointed at a
--   joined/exploded source (e.g. order_items) where one order spans many rows.
--
-- RUN
--   duckdb -c ".read sql/checks/customer_frequency_distribution.sql"
--   (or via python/profile_critical.py)
-- ---------------------------------------------------------------------------

WITH orders_per_customer AS (
    SELECT
        c.customer_unique_id,                      -- person-level key, NOT customer_id
        COUNT(DISTINCT o.order_id) AS order_count
    FROM read_csv_auto('data/raw/olist_orders_dataset.csv')    AS o
    JOIN read_csv_auto('data/raw/olist_customers_dataset.csv') AS c
      ON o.customer_id = c.customer_id
    GROUP BY 1
)

-- Distribution: how many customers sit at each frequency value?
-- If one value holds the overwhelming majority, Frequency is a constant and
-- quantile binning on it is meaningless (qcut will silently drop bins).
SELECT
    order_count                                                  AS orders_per_customer,
    COUNT(*)                                                     AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)           AS pct_of_customers
FROM orders_per_customer
GROUP BY 1
ORDER BY 1;
