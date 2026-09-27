-- Headline one-liner for the README / dashboard: the 96.88% figure.
WITH orders_per_customer AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_count
    FROM read_csv_auto('data/raw/olist_orders_dataset.csv')    AS o
    JOIN read_csv_auto('data/raw/olist_customers_dataset.csv') AS c
      ON o.customer_id = c.customer_id
    GROUP BY 1
)
SELECT
    COUNT(*)                                                          AS unique_customers,
    COUNT(*) FILTER (WHERE order_count = 1)                           AS one_time_customers,
    ROUND(100.0 * COUNT(*) FILTER (WHERE order_count = 1) / COUNT(*), 2) AS pct_one_time,
    COUNT(*) FILTER (WHERE order_count > 1)                           AS repeat_customers,
    MAX(order_count)                                                  AS max_orders_by_one_customer
FROM orders_per_customer;
