import duckdb
con = duckdb.connect()
R = lambda f: f"read_csv_auto('data/raw/{f}')"
ok = lambda c: "PASS" if c else "*** FAIL ***"

print("="*78)
print("AUDIT A - re-run every figure I have claimed")
print("="*78)
claims = []

n = con.execute(f"SELECT count(*) FROM {R('olist_orders_dataset.csv')}").fetchone()[0]
claims.append(("orders = 99,441", n, 99441))
n = con.execute(f"SELECT count(*) FROM {R('olist_order_items_dataset.csv')}").fetchone()[0]
claims.append(("order_items = 112,650", n, 112650))
n = con.execute(f"SELECT count(*) FROM {R('olist_customers_dataset.csv')}").fetchone()[0]
claims.append(("customers = 99,441", n, 99441))
n = con.execute(f"SELECT count(*) FROM {R('olist_geolocation_dataset.csv')}").fetchone()[0]
claims.append(("geolocation = 1,000,163", n, 1000163))
n = con.execute(f"SELECT count(*) FROM {R('olist_marketing_qualified_leads_dataset.csv')}").fetchone()[0]
claims.append(("MQL = 8,000", n, 8000))
n = con.execute(f"SELECT count(*) FROM {R('olist_closed_deals_dataset.csv')}").fetchone()[0]
claims.append(("closed_deals = 842", n, 842))

for label, got, exp in claims:
    print(f"  {label:<34} got={got:>10,}   {ok(got==exp)}")

# frequency distribution must sum to unique customers
d = con.execute(f"""
WITH pc AS (SELECT c.customer_unique_id, count(DISTINCT o.order_id) n
            FROM {R('olist_orders_dataset.csv')} o
            JOIN {R('olist_customers_dataset.csv')} c USING (customer_id) GROUP BY 1)
SELECT count(*) uniq, count(*) FILTER (WHERE n=1) one, count(*) FILTER (WHERE n>1) rep, max(n) mx FROM pc
""").fetchone()
uniq, one, rep, mx = d
print(f"\n  unique_customers = 96,096           got={uniq:>10,}   {ok(uniq==96096)}")
print(f"  one_time = 93,099                  got={one:>10,}   {ok(one==93099)}")
print(f"  repeat = 2,997                     got={rep:>10,}   {ok(rep==2997)}")
print(f"  max_orders = 17                    got={mx:>10,}   {ok(mx==17)}")
print(f"  one+repeat == unique               {one:,}+{rep:,}={one+rep:,}   {ok(one+rep==uniq)}")
print(f"  pct_one_time = 96.88%              got={100*one/uniq:>9.2f}%   {ok(round(100*one/uniq,2)==96.88)}")
print(f"  pct_repeat = 3.12%                 got={100*rep/uniq:>9.2f}%   {ok(round(100*rep/uniq,2)==3.12)}")

print()
print("="*78)
print("AUDIT B - unverified claim 1: does Olist have any campaign cost field?")
print("="*78)
import glob, os
cost_hits = []
for f in sorted(glob.glob("data/raw/*.csv")):
    cols = con.execute(f"SELECT * FROM read_csv_auto('{f}') LIMIT 0").df().columns.tolist()
    t = os.path.basename(f)
    hits = [c for c in cols if any(k in c.lower() for k in
            ("cost","spend","budget","campaign","offer","discount","promo","coupon","treatment","control","ab_","variant"))]
    if hits: cost_hits.append((t, hits))
    print(f"  {t:<52} {len(cols):>2} cols")
print(f"\n  tables with cost/campaign/offer/treatment columns: {cost_hits if cost_hits else 'NONE -- claim holds'}")

print()
print("="*78)
print("AUDIT C - unverified claim 2: do MQL and closed_deals actually join?")
print("="*78)
j = con.execute(f"""
SELECT
  (SELECT count(*) FROM {R('olist_marketing_qualified_leads_dataset.csv')})                     AS mql_rows,
  (SELECT count(DISTINCT mql_id) FROM {R('olist_marketing_qualified_leads_dataset.csv')})       AS mql_distinct,
  (SELECT count(*) FROM {R('olist_closed_deals_dataset.csv')})                                  AS deal_rows,
  (SELECT count(DISTINCT mql_id) FROM {R('olist_closed_deals_dataset.csv')})                    AS deal_distinct,
  (SELECT count(*) FROM {R('olist_closed_deals_dataset.csv')} d
     WHERE EXISTS (SELECT 1 FROM {R('olist_marketing_qualified_leads_dataset.csv')} m
                   WHERE m.mql_id = d.mql_id))                                                  AS deals_matched_to_mql
""").df()
print(j.to_string(index=False))
m = j.iloc[0]
print(f"\n  -> closed deals that join back to an MQL: {m.deals_matched_to_mql:,} / {m.deal_rows:,}   {ok(m.deals_matched_to_mql==m.deal_rows)}")
print(f"  -> true conversion rate = {m.deal_distinct}/{m.mql_distinct} = {100*m.deal_distinct/m.mql_distinct:.2f}%")
print(f"  -> mql_id unique in MQL table?  {ok(m.mql_rows==m.mql_distinct)}")
print(f"  -> mql_id unique in deals table? {ok(m.deal_rows==m.deal_distinct)}")
