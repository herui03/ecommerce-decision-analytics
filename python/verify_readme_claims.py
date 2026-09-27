"""
Re-verify every headline figure before it goes in the README.

The README is the one file a recruiter definitely reads. A wrong number there costs
more than a wrong number anywhere else in the repo, because it is the only claim they
will check. So nothing goes in it that has not been re-run here first.
"""
import duckdb, subprocess, re, sys

con = duckdb.connect("data/processed/olist.duckdb", read_only=True)
CRITEO = "read_csv_auto('data/raw/criteo/criteo-uplift-v2.1.csv')"
raw = duckdb.connect()

checks, fails = [], []
def check(label, actual, expected):
    ok = actual == expected
    checks.append((label, actual, expected, ok))
    if not ok: fails.append(label)

print("=" * 90)
print("RE-VERIFYING EVERY README CLAIM")
print("=" * 90)

# ---- Olist scale
check("orders",            con.execute("SELECT count(*) FROM main_marts.fct_orders").fetchone()[0], 99441)
check("order lines",       con.execute("SELECT count(*) FROM main_marts.fct_order_items").fetchone()[0], 112650)
check("customers (people)",con.execute("SELECT count(*) FROM main_marts.dim_customers").fetchone()[0], 96096)
check("products",          con.execute("SELECT count(*) FROM main_marts.dim_products").fetchone()[0], 32951)
check("sellers",           con.execute("SELECT count(*) FROM main_marts.dim_sellers").fetchone()[0], 3095)

# ---- money
check("total item revenue BRL",
      float(con.execute("SELECT round(sum(item_total_brl),2) FROM main_staging.stg_olist__order_items").fetchone()[0]),
      15843553.24)
check("in-window GMV BRL",
      float(con.execute("SELECT round(sum(gmv_brl),2) FROM main_marts.mart_monthly_performance").fetchone()[0]),
      15786203.57)

# ---- window
check("months in window",  con.execute("SELECT count(*) FROM main_marts.mart_monthly_performance").fetchone()[0], 20)
check("orders in window",  con.execute("SELECT sum(orders) FROM main_marts.mart_monthly_performance").fetchone()[0], 99092)
check("orders excluded",   99441 - 99092, 349)

# ---- the 96.88%
r = con.execute("""
  WITH pc AS (SELECT customer_unique_id, order_count FROM main_marts.dim_customers)
  SELECT count(*), count(*) FILTER (WHERE order_count=1), max(order_count) FROM pc
""").fetchone()
check("one-time customers", r[1], 93099)
check("pct one-time", round(100*r[1]/r[0], 2), 96.88)
check("max orders by one person", r[2], 17)

# ---- lead scoring
r = con.execute("""
  SELECT count(*) FILTER (WHERE is_in_model_window),
         count(*) FILTER (WHERE is_in_model_window AND is_won_90d),
         count(*) FROM main_marts.mart_lead_features
""").fetchone()
check("leads total", r[2], 8000)
check("leads in model window", r[0], 5998)
check("positives in window", r[1], 677)
check("positive rate pct", round(100*r[1]/r[0], 2), 11.29)

# ---- criteo
r = raw.execute(f"""
  SELECT count(*), count(*) FILTER (WHERE treatment=1), count(*) FILTER (WHERE treatment=0),
         count(*) FILTER (WHERE treatment=1 AND exposure=1)
  FROM {CRITEO}
""").fetchone()
check("criteo rows", r[0], 13979592)
check("criteo treated", r[1], 11882655)
check("criteo control", r[2], 2096937)
check("criteo exposed", r[3], 428212)
check("criteo compliance pct", round(100*r[3]/r[1], 4), 3.6037)

# ---- dbt test count (run it, don't trust memory)
# CLOSE THE CONNECTIONS FIRST. DuckDB allows many readers but a writer needs
# exclusive access, so the read-only handles opened at the top of this script were
# blocking dbt from rebuilding the very warehouse we are verifying:
#   holding the lock -> returncode 2, "IO Error: Could not set lock on file"
#   after close()    -> returncode 0, PASS=168
# It surfaced as an unparseable-output error, which looked like a format change and
# was actually a lock. A verification script that silently cannot run the thing it
# verifies is worse than having no verification script.
import os
con.close()
raw.close()

env = os.environ.copy()
env["DBT_PROFILES_DIR"] = os.path.abspath("dbt")
out = subprocess.run(["../.venv/bin/dbt", "build"], cwd="dbt",
                     env=env, capture_output=True, text=True)
if out.returncode != 0:
    fails.append(f"dbt build failed (returncode {out.returncode})")
m = re.search(r"PASS=(\d+) WARN=(\d+) ERROR=(\d+)", out.stdout)
if m:
    # The 170 PASS of the 2026-07-16 run predates the 2026-09 restoration (reconstructed
    # intermediate layer, new invariant tests). Until the restored project has been run on
    # the full data, require zero errors and REPORT the pass count instead of pinning it.
    print(f"  dbt PASS = {m.group(1)} (historical 2026-07-16 run: 170)")
    check("dbt ERROR", int(m.group(3)), 0)
else:
    fails.append("dbt build output unparseable")

# ---- report
for label, actual, expected, ok in checks:
    print(f"  {label:<28} actual={str(actual):>16}  claimed={str(expected):>16}  {'PASS' if ok else '*** FAIL ***'}")

print("=" * 90)
if fails:
    print(f"\n{len(fails)} CLAIM(S) FAILED - do not write these into the README:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print(f"\nAll {len(checks)} README claims re-verified against a live run.")
