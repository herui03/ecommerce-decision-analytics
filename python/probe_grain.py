import duckdb
con = duckdb.connect()
R = lambda f: f"read_csv_auto('data/raw/{f}')"

def probe(label, csv, keys):
    """keys: list of candidate key column-tuples to test for uniqueness"""
    n = con.execute(f"SELECT count(*) FROM {R(csv)}").fetchone()[0]
    print(f"\n{label}  (rows = {n:,})")
    for k in keys:
        cols = ", ".join(k)
        d = con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {cols} FROM {R(csv)})").fetchone()[0]
        verdict = "UNIQUE  <- grain" if d == n else f"not unique ({n-d:,} dupes)"
        print(f"    ({cols:<38}) distinct={d:>9,}   {verdict}")

print("="*88)
print("GRAIN PROBE - what is the true unique key of each table?")
print("="*88)
probe("orders",        "olist_orders_dataset.csv",        [("order_id",), ("customer_id",)])
probe("order_items",   "olist_order_items_dataset.csv",   [("order_id",), ("order_id","order_item_id")])
probe("order_payments","olist_order_payments_dataset.csv",[("order_id",), ("order_id","payment_sequential")])
probe("order_reviews", "olist_order_reviews_dataset.csv", [("review_id",), ("order_id",), ("review_id","order_id")])
probe("customers",     "olist_customers_dataset.csv",     [("customer_id",), ("customer_unique_id",)])
probe("products",      "olist_products_dataset.csv",      [("product_id",)])
probe("sellers",       "olist_sellers_dataset.csv",       [("seller_id",)])
probe("mql",           "olist_marketing_qualified_leads_dataset.csv", [("mql_id",)])
probe("closed_deals",  "olist_closed_deals_dataset.csv",  [("mql_id",), ("seller_id",)])
probe("category_xlat", "product_category_name_translation.csv", [("product_category_name",)])
probe("geolocation",   "olist_geolocation_dataset.csv",   [("geolocation_zip_code_prefix",)])
