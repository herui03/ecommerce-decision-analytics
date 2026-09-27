"""
Lead scoring - will an MQL convert within 90 days?

HISTORICAL SCRIPT, KEPT AS RUN (it produced outputs/lead_scoring_results.csv and
outputs/lead_scores_test.csv on 2026-07-16). Known issues found in the 2026-09 review,
fixed in the corrected pipeline (python/portfolio/leads.py), not here:
  * the Jan-Mar training labels were not complete at the 2018-04-01 cut (retrospective
    backtest, not a deployable evaluation);
  * page_lead_volume counts future and test-period leads (look-ahead);
  * ORDER BY first_contact_date has no id tie-break and np.argsort(-score) breaks ties by
    row order, so the top-decile hit counts depend on row order;
  * the 2017 regime break is described below as "the sales team did not exist yet": that
    is a hypothesis, the cause is unknown.

DESIGN DECISIONS, ALL OF WHICH AN INTERVIEWER SHOULD BE ABLE TO ATTACK:

1. TEMPORAL SPLIT, NOT RANDOM CV.
   Leads arrive over time. A random split lets the model see April when predicting
   January. That isn't a small optimism -- the conversion regime shifts materially
   month to month, so random CV would report a score this model could never achieve
   in production, where you only ever have the past.
     train = 2018-01 .. 2018-03   test = 2018-04 .. 2018-05

2. NO TIME FEATURES.
   contact_month, contact_year and days_since_campaign_start are all available at
   prediction time, and all excluded. In the 2017 data they encode the regime break
   (hypothesised at the time as "the sales team did not exist yet"; cause unknown) -- worthless for
   scoring a live lead. Under a temporal split they are worse than useless: train
   and test occupy disjoint months, so any month feature is pure noise on test.
   Day-of-week survives because it recurs in both.

3. NO closed_deals FEATURES.
   business_segment, lead_type, declared_monthly_revenue_brl et al. exist only on
   the 842 converted rows -- a salesperson enters them AFTER the win. Training on
   them yields a near-perfect AUC and a model that cannot score a new lead.

4. PR-AUC AND DECILE LIFT OVER ACCURACY.
   At an 11.29% base rate, predicting "nobody converts" scores 88.71% accuracy.
   Accuracy is not a metric here, it's a trap. The sales team's actual question is
   "if I can only call 10% of these, which 10%?" -- that is decile lift.

5. NO class_weight="balanced" -- AND THAT IS A DELIBERATE REVERSAL.
   It was in the first version, added reflexively because the classes are imbalanced.
   Measured, it was strictly worse:
       balanced : AUC 0.6851   Brier 0.2234   mean predicted p = 0.4617
       default  : AUC 0.6870   Brier 0.0909   mean predicted p = 0.1148
       (true test positive rate = 0.1055)
   It bought nothing on ranking -- AUC was marginally WORSE -- and destroyed
   calibration: it tells a salesperson a lead has a 46% chance when the truth is 11%.
   Imbalance is not automatically a problem to fix. Here the task is ranking, the
   base rate is 11% not 0.1%, and reweighting only shifts the intercept. Brier score
   is what exposed it; AUC alone would have hidden it completely.
"""

import warnings, duckdb, numpy as np, pandas as pd

# numpy 2.0 on macOS/Accelerate BLAS emits "divide by zero encountered in matmul"
# from sklearn's linear loss. Verified cosmetic, not a correctness problem: the
# fitted coefficients are all finite (|max| = 1.34) and every predicted probability
# is finite and inside [0, 1]. matmul does not divide -- this is numpy attributing a
# warning to the wrong op. Suppressed with the reason recorded rather than silenced
# blind.
warnings.filterwarnings("ignore", message=".*encountered in matmul.*")
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

RNG = 42
DB = "data/processed/olist.duckdb"

# ---------------------------------------------------------------- load
con = pd.read_sql if False else None
df = duckdb.connect(DB, read_only=True).execute("""
    SELECT mql_id, first_contact_date, is_won_90d,
           lead_origin_channel, landing_page_id, page_lead_volume,
           contact_dow, is_weekend_contact
    FROM main_marts.mart_lead_features
    WHERE is_in_model_window
    ORDER BY first_contact_date
""").df()

print("=" * 78)
print("DATA")
print("=" * 78)
print(f"  leads           {len(df):,}")
print(f"  positives       {df.is_won_90d.sum():,}  ({100*df.is_won_90d.mean():.2f}%)")
print(f"  window          {df.first_contact_date.min()} -> {df.first_contact_date.max()}")

# ---------------------------------------------------------------- split
CUT = pd.Timestamp("2018-04-01")   # first_contact_date arrives as datetime64, not date
train = df[df.first_contact_date < CUT].copy()
test  = df[df.first_contact_date >= CUT].copy()

print()
print("=" * 78)
print("TEMPORAL SPLIT")
print("=" * 78)
for name, d in [("train (Jan-Mar)", train), ("test  (Apr-May)", test)]:
    print(f"  {name}   n={len(d):>5,}   positives={int(d.is_won_90d.sum()):>4}  ({100*d.is_won_90d.mean():.2f}%)")

# The base rates differ between train and test. That is the honest situation and the
# reason a random split flatters: it would smear these two regimes together.
print(f"\n  base-rate shift train -> test: {100*train.is_won_90d.mean():.2f}% -> {100*test.is_won_90d.mean():.2f}%")

CAT = ["lead_origin_channel"]
NUM = ["page_lead_volume", "contact_dow"]
BOOL = ["is_weekend_contact"]

def prep(d):
    X = d[CAT + NUM + BOOL].copy()
    X["is_weekend_contact"] = X["is_weekend_contact"].astype(int)
    return X

X_train, y_train = prep(train), train.is_won_90d.astype(int).values
X_test,  y_test  = prep(test),  test.is_won_90d.astype(int).values

pre = ColumnTransformer([
    ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), CAT),
    ("num", StandardScaler(), NUM + BOOL),
])

# ---------------------------------------------------------------- metrics
def decile_lift(y_true, y_score, k=0.10):
    """If sales can only call the top k of leads, how many more wins than calling at random?"""
    n = max(1, int(len(y_score) * k))
    idx = np.argsort(-y_score)[:n]
    rate_top = y_true[idx].mean()
    rate_all = y_true.mean()
    return rate_top, rate_all, (rate_top / rate_all if rate_all > 0 else np.nan), n

def report(name, y_true, p):
    auc  = roc_auc_score(y_true, p)
    ap   = average_precision_score(y_true, p)
    bs   = brier_score_loss(y_true, p)
    top, base, lift, n = decile_lift(y_true, p)
    print(f"  {name:<22} AUC={auc:.4f}  PR-AUC={ap:.4f}  Brier={bs:.4f}   "
          f"top-10% hit={100*top:5.2f}% vs base {100*base:5.2f}%  lift={lift:.2f}x  (n={n})")
    return dict(model=name, auc=auc, pr_auc=ap, brier=bs, top_decile_rate=top,
                base_rate=base, lift=lift, n_called=n)

print()
print("=" * 78)
print("RESULTS  (test = Apr-May 2018, never seen in training)")
print("=" * 78)

rows = []

# --- baseline 1: predict the base rate for everyone. The floor any model must clear.
p_const = np.full(len(y_test), y_train.mean())
rows.append(report("baseline: base rate", y_test, p_const))

# --- baseline 2: channel conversion rate learned on train only.
#     A pivot table, not a model. If the ML cannot beat this, ship the pivot table.
ch = train.groupby("lead_origin_channel").is_won_90d.mean()
p_chan = test.lead_origin_channel.map(ch).fillna(y_train.mean()).values
rows.append(report("baseline: channel rate", y_test, p_chan))

# --- model 1: logistic regression
lr = Pipeline([("pre", pre),
               # No class_weight: see design note 5. It cost calibration and
               # returned nothing on ranking.
               ("clf", LogisticRegression(max_iter=2000, random_state=RNG))])
lr.fit(X_train, y_train)
rows.append(report("logistic regression", y_test, lr.predict_proba(X_test)[:, 1]))

# --- model 2: gradient boosting
gb = Pipeline([("pre", pre),
               ("clf", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                      max_depth=4, random_state=RNG))])
gb.fit(X_train, y_train)
rows.append(report("gradient boosting", y_test, gb.predict_proba(X_test)[:, 1]))

# ---------------------------------------------------------------- coefficients
print()
print("=" * 78)
print("LOGISTIC COEFFICIENTS  (log-odds; positive = more likely to convert)")
print("=" * 78)
names = lr.named_steps["pre"].get_feature_names_out()
coefs = lr.named_steps["clf"].coef_[0]
for n, c in sorted(zip(names, coefs), key=lambda t: -abs(t[1])):
    print(f"  {n:<45} {c:+.4f}")

# ---------------------------------------------------------------- save
out = pd.DataFrame(rows)
out.to_csv("outputs/lead_scoring_results.csv", index=False)
print(f"\nSaved -> outputs/lead_scoring_results.csv")

scored = test[["mql_id", "first_contact_date", "lead_origin_channel"]].copy()
scored["is_won_90d"] = y_test
scored["score_lr"] = lr.predict_proba(X_test)[:, 1]
scored["score_gb"] = gb.predict_proba(X_test)[:, 1]
scored.sort_values("score_gb", ascending=False).to_csv("outputs/lead_scores_test.csv", index=False)
print(f"Saved -> outputs/lead_scores_test.csv  ({len(scored):,} scored test leads)")
