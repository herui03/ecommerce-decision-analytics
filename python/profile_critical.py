import duckdb
con = duckdb.connect()
C = "read_csv_auto('data/raw/olist_customers_dataset.csv')"
O = "read_csv_auto('data/raw/olist_orders_dataset.csv')"

print("="*74); print("A. Repeat purchase: how many orders per real customer (customer_unique_id)?"); print("="*74)
print(con.execute(f"""
WITH per_cust AS (
  SELECT c.customer_unique_id, count(DISTINCT o.order_id) AS orders
  FROM {O} o JOIN {C} c USING (customer_id) GROUP BY 1)
SELECT orders AS orders_per_customer, count(*) AS customers,
       round(100.0*count(*)/sum(count(*)) OVER (),2) AS pct_of_customers
FROM per_cust GROUP BY 1 ORDER BY 1 LIMIT 8
""").df().to_string(index=False))

print()
print(con.execute(f"""
WITH per_cust AS (
  SELECT c.customer_unique_id, count(DISTINCT o.order_id) AS orders
  FROM {O} o JOIN {C} c USING (customer_id) GROUP BY 1)
SELECT count(*) AS unique_customers,
       sum(CASE WHEN orders=1 THEN 1 ELSE 0 END) AS one_time,
       round(100.0*sum(CASE WHEN orders=1 THEN 1 ELSE 0 END)/count(*),2) AS pct_one_time,
       sum(CASE WHEN orders>1 THEN 1 ELSE 0 END) AS repeat_customers
FROM per_cust
""").df().to_string(index=False))

print()
print("="*74); print("B. What is in the marketing funnel? (MQL / closed_deals columns)"); print("="*74)
for t,f in [("marketing_qualified_leads","data/raw/olist_marketing_qualified_leads_dataset.csv"),
            ("closed_deals","data/raw/olist_closed_deals_dataset.csv")]:
    cols = con.execute(f"SELECT * FROM read_csv_auto('{f}') LIMIT 0").df().columns.tolist()
    print(f"\n{t}:\n  {cols}")

print()
print("C. Does closed_deals.seller_id join to sellers?")
print(con.execute("""
SELECT count(*) AS closed_deals,
       count(DISTINCT d.seller_id) AS distinct_sellers,
       sum(CASE WHEN s.seller_id IS NOT NULL THEN 1 ELSE 0 END) AS matched_in_sellers
FROM read_csv_auto('data/raw/olist_closed_deals_dataset.csv') d
LEFT JOIN read_csv_auto('data/raw/olist_sellers_dataset.csv') s USING (seller_id)
""").df().to_string(index=False))
