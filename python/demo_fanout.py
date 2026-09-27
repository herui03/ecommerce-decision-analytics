import duckdb
con = duckdb.connect('data/processed/olist.duckdb', read_only=True)
S = "main_staging"

print("="*80)
print("Ground truth: each table totalled at its own grain")
print("="*80)
truth = con.execute(f"""
SELECT
  (SELECT count(*) FROM {S}.stg_olist__orders)                       AS orders,
  (SELECT round(sum(item_total_brl),2) FROM {S}.stg_olist__order_items)   AS true_item_revenue,
  (SELECT round(sum(payment_value_brl),2) FROM {S}.stg_olist__order_payments) AS true_payment_value
""").df()
print(truth.to_string(index=False))
t = truth.iloc[0]

print()
print("="*80)
print("Naive approach: orders joined straight to items + payments + reviews (all four tables)")
print("="*80)
naive = con.execute(f"""
SELECT
  count(*)                             AS row_count,
  count(DISTINCT o.order_id)           AS distinct_orders,
  round(sum(i.item_total_brl),2)       AS item_revenue,
  round(sum(p.payment_value_brl),2)    AS payment_value
FROM {S}.stg_olist__orders o
JOIN {S}.stg_olist__order_items    i ON i.order_id = o.order_id
JOIN {S}.stg_olist__order_payments p ON p.order_id = o.order_id
JOIN {S}.stg_olist__order_reviews  r ON r.order_id = o.order_id
""").df()
print(naive.to_string(index=False))
n = naive.iloc[0]

print()
print("="*80)
print("Damage assessment")
print("="*80)
print(f"  rows:            99,441 -> {n.row_count:,}          inflated {n.row_count/99441:.2f}x")
print(f"  item revenue:    {t.true_item_revenue:>15,.2f} -> {n.item_revenue:>15,.2f}   overstated {n.item_revenue/t.true_item_revenue:.2f}x  (+{n.item_revenue-t.true_item_revenue:,.2f})")
print(f"  payment value:   {t.true_payment_value:>15,.2f} -> {n.payment_value:>15,.2f}   overstated {n.payment_value/t.true_payment_value:.2f}x  (+{n.payment_value-t.true_payment_value:,.2f})")
print()
print("  Note: the query above raised no error and no warning.")
print("    It quietly returns an inflated GMV that would go straight onto a dashboard.")
