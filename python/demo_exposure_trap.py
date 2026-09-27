"""
The exposure trap, measured rather than asserted.

Criteo randomised `treatment` (85/15). But only 3.6% of the treated arm was actually
`exposed` to an ad. Exposure is NOT randomised -- it depends on whether the user
happened to browse. Analysing on exposure breaks the randomisation and produces a
large, significant, confident, WRONG answer.

This script computes both and puts the numbers side by side.
"""
import duckdb
con = duckdb.connect()
F = "read_csv_auto('data/raw/criteo/criteo-uplift-v2.1.csv')"

print("=" * 84)
print("SETUP")
print("=" * 84)
print(con.execute(f"""
  SELECT count(*) AS rows,
         count(*) FILTER (WHERE treatment=1) AS treated,
         count(*) FILTER (WHERE treatment=0) AS control,
         count(*) FILTER (WHERE exposure=1)  AS exposed,
         round(100.0*count(*) FILTER (WHERE exposure=1 AND treatment=1)
               / nullif(count(*) FILTER (WHERE treatment=1),0), 4) AS pct_treated_exposed,
         count(*) FILTER (WHERE exposure=1 AND treatment=0) AS exposed_in_control
  FROM {F}
""").df().to_string(index=False))

print()
print("=" * 84)
print("A. THE CORRECT ANALYSIS - intention-to-treat, on the randomised assignment")
print("=" * 84)
itt = con.execute(f"""
  SELECT
    avg(CASE WHEN treatment=1 THEN conversion END) AS t_rate,
    avg(CASE WHEN treatment=0 THEN conversion END) AS c_rate,
    count(*) FILTER (WHERE treatment=1) AS n_t,
    count(*) FILTER (WHERE treatment=0) AS n_c
  FROM {F}
""").fetchone()
t, c, nt, nc = float(itt[0]), float(itt[1]), itt[2], itt[3]
print(f"  treated   conversion = {100*t:.4f}%   (n = {nt:,})")
print(f"  control   conversion = {100*c:.4f}%   (n = {nc:,})")
print(f"  ITT effect: {100*(t-c):+.4f} pp absolute   |   {100*(t/c-1):+.2f}% relative")

print()
print("=" * 84)
print("B. THE TRAP - comparing the EXPOSED against the control")
print("=" * 84)
naive = con.execute(f"""
  SELECT
    avg(CASE WHEN exposure=1 THEN conversion END)              AS e_rate,
    avg(CASE WHEN treatment=0 THEN conversion END)             AS c_rate,
    count(*) FILTER (WHERE exposure=1)                         AS n_e
  FROM {F}
""").fetchone()
e, c2, ne = float(naive[0]), float(naive[1]), naive[2]
print(f"  exposed   conversion = {100*e:.4f}%   (n = {ne:,})")
print(f"  control   conversion = {100*c2:.4f}%   (n = {nc:,})")
print(f"  'effect':   {100*(e-c2):+.4f} pp absolute   |   {100*(e/c2-1):+.2f}% relative")

print()
print("=" * 84)
print("C. DAMAGE")
print("=" * 84)
print(f"  correct (ITT) relative lift : {100*(t/c-1):+8.2f}%")
print(f"  trap    (exposed) lift      : {100*(e/c2-1):+8.2f}%")
print(f"  overstatement               : {(e/c2-1)/(t/c-1):8.2f}x")

print()
print("  Why the trap is not a small bias: the treated arm that was NEVER exposed")
print("  still converts. If exposure were irrelevant those people would look like control.")
unexposed = con.execute(f"""
  SELECT avg(conversion) FROM {F} WHERE treatment=1 AND exposure=0
""").fetchone()[0]
print(f"    treated but NOT exposed conversion = {100*float(unexposed):.4f}%")
print(f"    control                 conversion = {100*c:.4f}%")
print(f"    difference = {100*(float(unexposed)-c):+.4f} pp")
print("    -> If this is ~0, non-exposure means 'no dose'. If it is NOT ~0, then who")
print("       gets exposed is confounded with who converts, and the trap is worse.")
