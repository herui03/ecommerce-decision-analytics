"""
Export the metric layer to Tableau-ready CSVs, then ROUND-TRIP VERIFY.

Exporting is trivial; proving the export didn't silently corrupt anything is the
point. Every extract is re-read from disk and compared against the warehouse on
row count, NULL count, and money to the cent. An extract that fails is deleted
rather than shipped -- a wrong CSV in Tableau is indistinguishable from a wrong
dashboard, and by then you are debugging the wrong layer.
"""
import duckdb, os, sys

DB  = "data/processed/olist.duckdb"
OUT = "tableau/extracts"
os.makedirs(OUT, exist_ok=True)
con = duckdb.connect(DB, read_only=True)

# (model, money column to reconcile or None)
EXTRACTS = [
    ("mart_monthly_performance",  "gmv_brl"),
    ("mart_category_performance", "gmv_brl"),
    ("mart_state_performance",    "gmv_brl"),
    ("mart_payment_performance",  "gmv_brl"),
    ("mart_customer_segments",    "lifetime_payment_brl"),
]

print("=" * 84)
print(f"{'extract':<30} {'rows':>8} {'nulls':>7} {'money (warehouse)':>20} {'round-trip':>12}")
print("=" * 84)

failures = []
for model, money_col in EXTRACTS:
    src = f"main_marts.{model}"
    path = f"{OUT}/{model}.csv"

    # --- warehouse truth -------------------------------------------------
    rows_w  = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]
    money_w = con.execute(f"SELECT round(sum({money_col}), 2) FROM {src}").fetchone()[0]
    nulls_w = con.execute(f"SELECT count(*) - count({money_col}) FROM {src}").fetchone()[0]

    # --- export ----------------------------------------------------------
    # NULLs are written as empty strings, which is what Tableau expects for a
    # numeric measure -- writing the literal 'NULL' would force the column to
    # string and silently break every aggregate on it.
    # DuckDB's COPY TO always emits UTF-8; ENCODING is a read-side option only.
    con.execute(f"""
        COPY (SELECT * FROM {src})
        TO '{path}' (FORMAT CSV, HEADER, DELIMITER ',')
    """)

    # --- round-trip: read the FILE back, not the warehouse ----------------
    rt = f"read_csv_auto('{path}')"
    rows_r  = con.execute(f"SELECT count(*) FROM {rt}").fetchone()[0]
    money_r = con.execute(f"SELECT round(sum({money_col}), 2) FROM {rt}").fetchone()[0]
    nulls_r = con.execute(f"SELECT count(*) - count({money_col}) FROM {rt}").fetchone()[0]

    ok_rows  = rows_w  == rows_r
    ok_money = (money_w is None and money_r is None) or (
        money_w is not None and money_r is not None and abs(float(money_w) - float(money_r)) <= 0.01
    )
    ok_nulls = nulls_w == nulls_r
    ok = ok_rows and ok_money and ok_nulls

    verdict = "PASS" if ok else "*** FAIL ***"
    money_s = f"{float(money_w):,.2f}" if money_w is not None else "-"
    print(f"{model:<30} {rows_w:>8,} {nulls_w:>7,} {money_s:>20} {verdict:>12}")

    if not ok:
        failures.append((model, rows_w, rows_r, money_w, money_r, nulls_w, nulls_r))
        os.remove(path)          # never ship an extract that failed verification

print("=" * 84)
if failures:
    print("\nROUND-TRIP FAILURES (extract deleted, not shipped):")
    for f in failures:
        print(f"  {f[0]}: rows {f[1]}->{f[2]}  money {f[3]}->{f[4]}  nulls {f[5]}->{f[6]}")
    sys.exit(1)

print(f"\nAll {len(EXTRACTS)} extracts verified: file on disk == warehouse, to the cent.")
for model, _ in EXTRACTS:
    p = f"{OUT}/{model}.csv"
    print(f"  {os.path.getsize(p)/1024:>8.1f} KB  {p}")
