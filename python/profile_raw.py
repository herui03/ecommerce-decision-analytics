import duckdb, glob, os
con = duckdb.connect()
print("="*74)
print("TABLE ROW COUNTS")
print("="*74)
for f in sorted(glob.glob("data/raw/*.csv")):
    name = os.path.basename(f).replace("olist_","").replace("_dataset.csv","").replace(".csv","")
    n = con.execute(f"SELECT count(*) FROM read_csv_auto('{f}')").fetchone()[0]
    print(f"{name:<38} {n:>10,}")

print()
print("="*74)
print("ORDERS: date range, status mix")
print("="*74)
print(con.execute("""
  SELECT min(order_purchase_timestamp)::DATE AS first_order,
         max(order_purchase_timestamp)::DATE AS last_order,
         count(*) AS orders
  FROM read_csv_auto('data/raw/olist_orders_dataset.csv')
""").df().to_string(index=False))
print()
print(con.execute("""
  SELECT order_status, count(*) AS n,
         round(100.0*count(*)/sum(count(*)) OVER (),2) AS pct
  FROM read_csv_auto('data/raw/olist_orders_dataset.csv')
  GROUP BY 1 ORDER BY 2 DESC
""").df().to_string(index=False))
