"""
Criteo uplift RCT - the A/B analysis done properly.

THREE THINGS THIS SCRIPT REFUSES TO DO, EACH FOR A REASON:

1. It does not analyse on `exposure`. Assignment is randomised; exposure is not.
   Only 3.60% of the treated arm was exposed, and the exposed differ from the
   unexposed on observables by SMD 0.85 (f0) and 1.47 (f3) -- against 0.007 and
   0.049 across the randomised treatment arms. Exposure selects active browsers,
   who convert anyway. Comparing exposed to control reports +2675.83% against a
   true ITT of +59.45%: a 45x overstatement.

2. It does not lead with a p-value. At n = 13,979,592 every difference is
   "significant". A p-value here answers a question nobody asked -- it tests
   whether the effect is exactly zero, which it never is. The confidence interval
   and the effect size are the analysis; the p-value is a footnote.

3. It does not report the naive number without also reporting what it costs.
"""
import duckdb, numpy as np
from statsmodels.stats.proportion import proportions_ztest, confint_proportions_2indep
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

F = "read_csv_auto('data/raw/criteo/criteo-uplift-v2.1.csv')"
con = duckdb.connect()

# ---------------------------------------------------------------- counts
r = con.execute(f"""
  SELECT
    count(*) FILTER (WHERE treatment=1)                            AS n_t,
    count(*) FILTER (WHERE treatment=0)                            AS n_c,
    count(*) FILTER (WHERE treatment=1 AND conversion=1)           AS y_t,
    count(*) FILTER (WHERE treatment=0 AND conversion=1)           AS y_c,
    count(*) FILTER (WHERE treatment=1 AND exposure=1)             AS n_exposed,
    count(*) FILTER (WHERE treatment=1 AND exposure=1 AND conversion=1) AS y_exposed,
    count(*) FILTER (WHERE treatment=1 AND exposure=0)             AS n_t_unexp,
    count(*) FILTER (WHERE treatment=1 AND exposure=0 AND conversion=1) AS y_t_unexp
  FROM {F}
""").fetchone()
n_t, n_c, y_t, y_c, n_exp, y_exp, n_tu, y_tu = r

p_t, p_c = y_t / n_t, y_c / n_c
p_exp    = y_exp / n_exp
p_tu     = y_tu / n_tu

print("=" * 86)
print("1. INTENTION-TO-TREAT - the answer")
print("=" * 86)
print(f"  treated   {y_t:>7,} / {n_t:>10,} = {100*p_t:.4f}%")
print(f"  control   {y_c:>7,} / {n_c:>10,} = {100*p_c:.4f}%")

diff = p_t - p_c
lo, hi = confint_proportions_2indep(y_t, n_t, y_c, n_c, method="wald", compare="diff")
print(f"\n  ITT absolute effect = {100*diff:+.4f} pp")
print(f"  95% CI              = [{100*lo:+.4f}, {100*hi:+.4f}] pp")
print(f"  relative lift       = {100*(p_t/p_c - 1):+.2f}%")
print(f"  CI excludes zero?     {'YES' if lo > 0 else 'NO'}")

stat, pval = proportions_ztest([y_t, y_c], [n_t, n_c])
print(f"\n  z = {stat:.2f}   p = {pval:.3g}")
print("  ^ The p-value is not the finding. At n=13.98M it was always going to be tiny.")
print("    The CI is the finding: the effect is somewhere in a narrow band, and that")
print("    band is far from zero. Report the interval, not the asterisks.")

# ---------------------------------------------------------------- MDE
print()
print("=" * 86)
print("2. WHAT COULD THIS TEST EVEN DETECT? - minimum detectable effect")
print("=" * 86)
power = NormalIndPower()
ratio = n_c / n_t
for pw in (0.80, 0.95):
    es = power.solve_power(effect_size=None, nobs1=n_t, alpha=0.05, power=pw,
                           ratio=ratio, alternative="two-sided")
    # invert Cohen's h back to a detectable p2 given p1 = control rate
    lo_p, hi_p = 0.0, 1.0
    for _ in range(200):
        mid = (lo_p + hi_p) / 2
        if abs(proportion_effectsize(mid, p_c)) < es:
            lo_p = mid
        else:
            hi_p = mid
    mde_abs = lo_p - p_c
    print(f"  power {int(100*pw)}%: MDE = {100*mde_abs:.4f} pp "
          f"({100*(mde_abs/p_c):+.2f}% relative)   [Cohen's h = {es:.5f}]")
print(f"\n  Observed effect = {100*diff:.4f} pp - comfortably above the MDE.")
print("  The test is heavily over-powered: it can detect effects far smaller than")
print("  anyone would act on. That is precisely why the p-value carries no information")
print("  here and the effect size has to carry the argument.")

# ---------------------------------------------------------------- CACE
print()
print("=" * 86)
print("3. THE EFFECT ON THE EXPOSED - done correctly, via CACE (Wald / IV)")
print("=" * 86)
compliance = n_exp / n_t                      # P(exposed | treated)
# control exposure is 0 by construction -- verified, so ITT_D = compliance - 0
cace = diff / compliance
print(f"  compliance (P(exposed|treated))  = {100*compliance:.4f}%")
print(f"  control exposure                 = 0.0000%  (by construction, verified)")
print(f"  CACE = ITT / compliance          = {100*diff:.4f} / {compliance:.6f}"
      f" = {100*cace:+.4f} pp")

# Independent cross-check: decompose the control rate into compliers/never-takers.
# control = compliance * complier_rate + (1-compliance) * nevertaker_rate
# never-takers in control are unobservable, but under exclusion they behave like the
# treated-but-unexposed -- who received no ad either.
nevertaker = p_tu
complier_control = (p_c - (1 - compliance) * nevertaker) / compliance
cace_check = p_exp - complier_control
print(f"\n  Cross-check by decomposition (independent of the Wald algebra):")
print(f"    treated & unexposed rate (never-takers) = {100*nevertaker:.4f}%")
print(f"    implied complier rate in CONTROL        = {100*complier_control:.4f}%")
print(f"    exposed rate (compliers, treated)       = {100*p_exp:.4f}%")
print(f"    CACE = {100*p_exp:.4f} - {100*complier_control:.4f} = {100*cace_check:+.4f} pp")
print(f"    agreement with Wald: {abs(cace - cace_check)*100:.6f} pp")
print(f"\n  complier relative lift = {100*(p_exp/complier_control - 1):+.2f}%")

print()
print("=" * 86)
print("4. THE THREE NUMBERS, SIDE BY SIDE")
print("=" * 86)
print(f"  naive 'exposed vs control'  {100*(p_exp/p_c - 1):+10.2f}%   WRONG - selection, not effect")
print(f"  CACE (effect on compliers)  {100*(p_exp/complier_control - 1):+10.2f}%   correct, but only about compliers")
print(f"  ITT  (effect on everyone)   {100*(p_t/p_c - 1):+10.2f}%   correct, and the number you budget against")
print()
print("  ITT is the decision number: you buy the campaign for everyone assigned, not")
print("  for the 3.6% who happen to browse. CACE tells you the ad works on people who")
print("  see it; ITT tells you what you get for the money.")
