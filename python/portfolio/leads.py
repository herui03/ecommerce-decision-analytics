"""Corrected lead-scoring path: explicit windows, label maturity, point-in-time
features and deterministic, tie-aware evaluation.

Three problems in the historical run (python/train_lead_scoring.py, results in
outputs/) are handled separately here, because they are different mistakes:

1. LABEL AVAILABILITY. is_won_90d for a lead contacted on day c is complete only after
   day c+90. The historical run trained on Jan-Mar 2018 cohorts and evaluated on
   Apr-May with a cut at 2018-04-01, but every one of its training labels matured AFTER
   that cut (a 2018-01-01 lead matures on 2018-04-02; March leads in late June). That is
   a retrospective cohort backtest, not an evaluation a model deployed on 2018-04-01
   could have produced. (Convention: as_of is 00:00 on its date; a 90-day window for a
   contact on day c covers c..c+90 inclusive, so the label is usable from c+91 00:00.) Here a design declares `as_of`, and training is restricted to
   leads whose label matured strictly before it (purge gap = horizon + 1 day).

2. FEATURE LOOK-AHEAD. page_lead_volume counted leads over the whole dataset, including
   later leads. The point-in-time feature counts only strictly earlier-dated leads.

3. TIES. np.argsort(-score) breaks ties by input row order, and the SQL load ordered by
   first_contact_date only. Here rows are canonicalised by (first_contact_date, mql_id)
   before fitting; exports sort by (score desc, mql_id asc); and top-k metrics report
   the tied block at the cut-off plus the tie-aware expected hit count, so a constant
   score is no longer credited with an arbitrary 9.43% hit rate.

What is NOT claimed: a top-k hit rate is retrospective ranking quality on a held-out
cohort. It is not incremental wins - whether calling top-ranked leads first creates
extra conversions needs a randomised prioritisation test.

Outcome observation: the source documents no outcome-observation cutoff. A design
therefore carries `outcome_observed_through` as an explicit ASSUMPTION ("wins are
completely recorded through this date") and refuses to evaluate a score cohort whose
90-day windows extend past it.
"""
from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message=".*encountered in matmul.*")
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

RNG = 42
HORIZON_DAYS = 90


# ------------------------------------------------------------------------- windows
@dataclass(frozen=True)
class LeadDesign:
    name: str
    train_start: date
    as_of: date                       # information strictly BEFORE this date is known
    score_start: date
    score_end: date
    outcome_observed_through: date    # ASSUMPTION: wins fully recorded through this date
    feature_set: str = "point_in_time"   # or "legacy_full_dataset"
    horizon_days: int = HORIZON_DAYS
    enforce_label_maturity: bool = True  # False only to reproduce the historical design

    @property
    def train_end(self) -> date:
        """Last contact date whose label is complete before as_of: c + horizon < as_of."""
        return self.as_of - timedelta(days=self.horizon_days + 1)

    def problems(self) -> list[str]:
        p = []
        if self.feature_set not in ("point_in_time", "legacy_full_dataset"):
            p.append(f"unknown feature_set {self.feature_set!r}")
        if self.enforce_label_maturity and self.train_end < self.train_start:
            p.append(f"no training label is complete at as-of {self.as_of} 00:00: the {self.horizon_days}-day "
                     f"outcome window of the earliest training contact ({self.train_start}) ends "
                     f"{self.train_start + timedelta(days=self.horizon_days)} and is usable only from "
                     f"{self.train_start + timedelta(days=self.horizon_days + 1)} 00:00")
        if self.score_start < self.as_of:
            p.append("score cohort starts before as_of (scoring the past as if it were new)")
        if self.score_end < self.score_start:
            p.append("score cohort window is empty")
        need = self.score_end + timedelta(days=self.horizon_days)
        if need > self.outcome_observed_through:
            p.append(f"score cohort outcomes need observation through {need}, beyond the "
                     f"assumed outcome_observed_through {self.outcome_observed_through}")
        return p

    def describe(self) -> dict:
        d = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in asdict(self).items()}
        d["train_end"] = self.train_end.isoformat() if self.enforce_label_maturity else None
        d["purge_gap_days"] = self.horizon_days + 1 if self.enforce_label_maturity else 0
        d["problems"] = self.problems()
        return d


# The corrected design used for the synthetic run AND declared (not run) for full data.
CORRECTED = LeadDesign(
    name="corrected: as-of 2018-05-01, point-in-time features",
    train_start=date(2018, 1, 1), as_of=date(2018, 5, 1),
    score_start=date(2018, 5, 1), score_end=date(2018, 5, 31),
    outcome_observed_through=date(2018, 8, 29),
)
CORRECTED_LEGACY_FEATURE = LeadDesign(
    name="same windows, LEGACY full-dataset page count (look-ahead)",
    train_start=CORRECTED.train_start, as_of=CORRECTED.as_of,
    score_start=CORRECTED.score_start, score_end=CORRECTED.score_end,
    outcome_observed_through=CORRECTED.outcome_observed_through,
    feature_set="legacy_full_dataset",
)
# The historical calendar split, reproduced only to show why it is retrospective.
HISTORICAL_SPLIT = LeadDesign(
    name="historical calendar split (retrospective; labels immature at the cut)",
    train_start=date(2018, 1, 1), as_of=date(2018, 4, 1),
    score_start=date(2018, 4, 1), score_end=date(2018, 5, 31),
    outcome_observed_through=date(2018, 8, 29),
    feature_set="legacy_full_dataset", enforce_label_maturity=False,
)
HISTORICAL_TRAIN_END = date(2018, 3, 31)


def audit_historical_split() -> dict:
    """Pure date arithmetic on the historical design - needs no raw data.

    Convention: as_of is the START of a day (00:00); a label counts a win on contact day
    c through c + 90 inclusive. A 2018-01-01 lead's outcome window therefore ends on
    2018-04-01 and its label is usable from 2018-04-02 00:00 - one day after the
    2018-04-01 cut. A 2018-03-31 lead's window ends 2018-06-29 (usable 2018-06-30)."""
    w_first = HISTORICAL_SPLIT.train_start + timedelta(days=HORIZON_DAYS)
    w_last = HISTORICAL_TRAIN_END + timedelta(days=HORIZON_DAYS)
    return {
        "train_cohort": ["2018-01-01", "2018-03-31"],
        "cut": HISTORICAL_SPLIT.as_of.isoformat(),
        "test_cohort": ["2018-04-01", "2018-05-31"],
        "outcome_windows_end_between": [w_first.isoformat(), w_last.isoformat()],
        "labels_usable_from_between": [(w_first + timedelta(days=1)).isoformat(),
                                       (w_last + timedelta(days=1)).isoformat()],
        "share_of_training_labels_usable_at_cut": 0.0,
        "latest_contact_usable_at_cut": (HISTORICAL_SPLIT.as_of - timedelta(days=HORIZON_DAYS + 1)).isoformat(),
        "historical_training_leads_documented": 3343,
        "verdict": ("Every training lead's 90-day outcome window ended on or after 2018-04-01 "
                    f"(the earliest, for a 2018-01-01 contact, ends 2018-04-01 and is usable from "
                    f"2018-04-02 00:00), so none of the training labels was complete at the "
                    "2018-04-01 00:00 cut. The Apr-May test is a retrospective cohort backtest. A model "
                    "deployed at the cut could only have trained on contacts up to 2017-12-31, i.e. "
                    "none from the 2018 model window."),
    }


# ----------------------------------------------------------------------- features
def canonical(df: pd.DataFrame) -> pd.DataFrame:
    """One deterministic row order regardless of how the input arrived."""
    out = df.copy()
    out["first_contact_date"] = pd.to_datetime(out["first_contact_date"]).dt.date
    out["won_date"] = pd.to_datetime(out["won_date"]).dt.date
    out["won_date"] = out["won_date"].where(out["won_date"].notna(), None)
    return out.sort_values(["first_contact_date", "mql_id"], kind="mergesort").reset_index(drop=True)


def pit_page_counts(df: pd.DataFrame) -> pd.Series:
    """Leads on the same landing page with a STRICTLY earlier contact date. Uses only
    the page id and the date of other rows - no label, and nothing dated on/after the
    lead itself. Independent re-implementation of mart_lead_features.page_lead_volume_prior."""
    d = df[["mql_id", "landing_page_id", "first_contact_date"]].copy()
    per_day = d.groupby(["landing_page_id", "first_contact_date"]).size().rename("n").reset_index()
    per_day = per_day.sort_values(["landing_page_id", "first_contact_date"])
    per_day["prior"] = per_day.groupby("landing_page_id")["n"].cumsum() - per_day["n"]
    m = d.merge(per_day[["landing_page_id", "first_contact_date", "prior"]],
                on=["landing_page_id", "first_contact_date"], how="left")
    return pd.Series(m["prior"].astype(int).values, index=df.index, name="page_lead_volume_prior")


def full_dataset_page_counts(df: pd.DataFrame) -> pd.Series:
    """LEGACY feature: count over the whole frame, future rows included."""
    return df.groupby("landing_page_id")["mql_id"].transform("count").rename("page_lead_volume")


def label_as_of(df: pd.DataFrame, as_of: date, horizon: int = HORIZON_DAYS) -> pd.Series:
    """Won within [0, horizon] days of contact AND the win is dated strictly before
    as_of (i.e. it had been observed by then). NULL won_date -> False."""
    lag = [(w - c).days if w is not None else None
           for w, c in zip(df["won_date"], df["first_contact_date"])]
    return pd.Series([bool(l is not None and 0 <= l <= horizon and w < as_of)
                      for l, w in zip(lag, df["won_date"])], index=df.index)


CAT = ["lead_origin_channel"]
NUM = ["log_page_volume", "contact_dow", "is_weekend_contact"]


def _design_matrix(d: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    col = "page_lead_volume_prior" if feature_set == "point_in_time" else "page_lead_volume"
    X = pd.DataFrame({
        "lead_origin_channel": d["lead_origin_channel"].fillna("not_recorded").astype(str),
        "log_page_volume": np.log1p(d[col].astype(float)),
        "contact_dow": pd.to_datetime(d["first_contact_date"]).dt.dayofweek.astype(float),
    })
    X["is_weekend_contact"] = (X["contact_dow"] >= 5).astype(float)
    return X


# ------------------------------------------------------------------------ metrics
def ranked(ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """Indices ordered by score DESC, then id ASC - explicit, deterministic tie-break."""
    id_rank = np.unique(np.asarray(ids).astype(str), return_inverse=True)[1]
    return np.lexsort((id_rank, -np.asarray(scores, dtype=float)))


def top_k(ids: np.ndarray, y: np.ndarray, scores: np.ndarray, k: int) -> dict:
    """Top-k hits with the tie structure at the cut-off made explicit.

    deterministic_hits: hits among the first k after sorting by (score desc, id asc)
    expected_hits:      average over all tie-breaks = hits strictly above the cut-off
                        score + (slots left) x (positive share of the tied block)
    min_hits/max_hits:  the range any tie-break could produce
    """
    n = len(scores)
    if n == 0 or k <= 0:
        return {"k": k, "n": n, "deterministic_hits": None, "expected_hits": None,
                "min_hits": None, "max_hits": None, "tie_block": None, "tie_block_positives": None}
    k = min(k, n)
    order = ranked(ids, scores)
    det = int(y[order[:k]].sum())
    cut = scores[order[k - 1]]
    above = scores > cut
    block = scores == cut
    n_above, n_block = int(above.sum()), int(block.sum())
    pos_above, pos_block = int(y[above].sum()), int(y[block].sum())
    slots = k - n_above
    expected = pos_above + pos_block * slots / n_block
    return {"k": k, "n": n, "deterministic_hits": det, "expected_hits": float(expected),
            "min_hits": pos_above + max(0, slots - (n_block - pos_block)),
            "max_hits": pos_above + min(pos_block, slots),
            "tie_block": n_block, "tie_block_positives": pos_block, "strictly_above": n_above}


def evaluate(ids, y, scores, k_share: float = 0.10) -> dict:
    y = np.asarray(y, dtype=int)
    scores = np.asarray(scores, dtype=float)
    ids = np.asarray(ids)
    single_class = len(np.unique(y)) < 2
    k = max(1, int(len(y) * k_share))
    t = top_k(ids, y, scores, k)
    prevalence = float(y.mean()) if len(y) else None
    return {
        "n": int(len(y)), "positives": int(y.sum()), "prevalence": prevalence,
        "auc": None if single_class else float(roc_auc_score(y, scores)),
        "pr_auc": None if single_class else float(average_precision_score(y, scores)),
        "brier": float(brier_score_loss(y, scores)) if len(y) else None,
        "distinct_scores": int(len(np.unique(scores))),
        **{f"top_{kk}": vv for kk, vv in t.items()},
        "random_expected_hits": None if prevalence is None else prevalence * t["k"],
    }


# ------------------------------------------------------------------------ pipeline
def run_design(leads: pd.DataFrame, design: LeadDesign) -> dict:
    """Fit on the design's training cohort and score its score cohort."""
    problems = design.problems()
    if problems:
        return {"design": design.describe(), "status": "invalid", "problems": problems,
                "results": [], "scores": []}
    df = canonical(leads)
    c = df["first_contact_date"]
    train_last = design.train_end if design.enforce_label_maturity else HISTORICAL_TRAIN_END
    tr = df[(c >= design.train_start) & (c <= train_last)].copy()
    te = df[(c >= design.score_start) & (c <= design.score_end)].copy()
    if design.enforce_label_maturity:
        y_tr = label_as_of(tr, design.as_of, design.horizon_days)
    else:   # historical reproduction: full 90-day labels, observed after the cut
        y_tr = label_as_of(tr, design.outcome_observed_through + timedelta(days=1), design.horizon_days)
    y_te = label_as_of(te, design.outcome_observed_through + timedelta(days=1), design.horizon_days)
    immature = int((pd.to_datetime(tr["first_contact_date"]) + pd.Timedelta(days=design.horizon_days + 1)
                    > pd.Timestamp(design.as_of)).sum())
    info = {"design": design.describe(), "status": "ok", "problems": [],
            "train_n": int(len(tr)), "train_positives": int(y_tr.sum()),
            "train_labels_immature_at_as_of": immature,
            "score_n": int(len(te)), "score_positives": int(y_te.sum())}
    if len(tr) == 0 or y_tr.nunique() < 2 or len(te) == 0:
        info["status"] = "invalid"
        info["problems"] = ["training cohort has fewer than two label classes or cohorts are empty"]
        info["results"], info["scores"] = [], []
        return info

    X_tr, X_te = _design_matrix(tr, design.feature_set), _design_matrix(te, design.feature_set)
    ytr, yte = y_tr.astype(int).values, y_te.astype(int).values
    ids = te["mql_id"].values
    def pre():   # a fresh, dense transformer per model: fitted on the training cohort only
        return ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False), CAT),
            ("num", StandardScaler(), NUM),
        ])
    models = {}
    models["baseline: base rate (constant)"] = np.full(len(te), ytr.mean())
    ch = pd.Series(ytr, index=X_tr.index).groupby(X_tr["lead_origin_channel"]).mean()
    models["baseline: channel rate (train only)"] = X_te["lead_origin_channel"].map(ch).fillna(ytr.mean()).values
    lr = Pipeline([("pre", pre()), ("clf", LogisticRegression(max_iter=2000, random_state=RNG))])
    lr.fit(X_tr, ytr)
    models["logistic regression"] = lr.predict_proba(X_te)[:, 1]
    gb = Pipeline([("pre", pre()), ("clf", HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, max_depth=4, random_state=RNG))])
    gb.fit(X_tr, ytr)
    models["gradient boosting"] = gb.predict_proba(X_te)[:, 1]

    results = []
    for name, s in models.items():
        results.append({"model": name, **evaluate(ids, yte, s)})
    info["results"] = results
    lr_scores = models["logistic regression"]
    order = ranked(ids, lr_scores)
    info["scores"] = [{"mql_id": str(ids[i]), "first_contact_date": te["first_contact_date"].iloc[i].isoformat(),
                       "lead_origin_channel": X_te["lead_origin_channel"].iloc[i],
                       "is_won_90d": int(yte[i]), "score_lr": float(lr_scores[i]),
                       "score_gb": float(models["gradient boosting"][i])} for i in order]
    return info


def check_pit_column(leads: pd.DataFrame) -> int:
    """Rows where the dbt column disagrees with the independent Python computation."""
    df = canonical(leads)
    return int((pit_page_counts(df).values != df["page_lead_volume_prior"].astype(int).values).sum())


# --------------------------------------------------------- historical recomputation
def recompute_historical(scores_csv, results_csv) -> dict:
    """Recompute what the committed held-out scores CAN support: AUC, PR-AUC, Brier and
    tie-aware top-decile for LR and GB. The channel-rate baseline cannot be recomputed
    (its train-period channel rates were not saved)."""
    # round_trip: pandas' default float parser is not correctly rounded (it returns a different
    # double for 2,190 of the 2,655 committed LR scores), which would make these recomputations
    # disagree with the exact values the dashboard embeds, and can vary between builds of pandas.
    s = pd.read_csv(scores_csv, float_precision="round_trip")
    r = pd.read_csv(results_csv, float_precision="round_trip")
    ids, y = s["mql_id"].values, s["is_won_90d"].astype(int).values
    out = {"rows": int(len(s)), "positives": int(y.sum()), "prevalence": float(y.mean()),
           "mql_id_unique": bool(s["mql_id"].is_unique), "models": []}
    for col, name in (("score_lr", "logistic regression"), ("score_gb", "gradient boosting")):
        ev = evaluate(ids, y, s[col].values)
        # Ties broken by the committed file's row order (a STABLE sort). The historical code used
        # np.argsort's default unstable sort, whose tie order depends on the CPU's SIMD kernel:
        # CI observed 52 vs 53 (LR) and 51 vs 52 (GB) between two machines, so that number is
        # deliberately not stored here.
        n = ev["top_k"]
        file_order_hits = int(y[np.argsort(-s[col].values, kind="stable")[:n]].sum())
        hist = r[r["model"] == name].iloc[0]
        out["models"].append({"model": name, **ev,
                              "historical_auc": float(hist["auc"]), "historical_pr_auc": float(hist["pr_auc"]),
                              "historical_brier": float(hist["brier"]),
                              "historical_top_decile_hits": int(round(hist["top_decile_rate"] * hist["n_called"])),
                              "stable_file_order_tiebreak_hits": file_order_hits})
    # constant baseline: every score tied -> expected hits = k x prevalence
    base = r[r["model"] == "baseline: base rate"].iloc[0]
    k = int(base["n_called"])
    const = top_k(ids, y, np.full(len(y), 0.5), k)
    out["constant_baseline"] = {
        "min_hits": const["min_hits"], "max_hits": const["max_hits"],
        "historical_top_decile_rate": float(base["top_decile_rate"]),
        "historical_hits": int(round(base["top_decile_rate"] * k)),
        "tie_aware_expected_hits": float(y.mean() * k),
        "tie_aware_rate": float(y.mean()),
        "note": "all 2,655 scores tie; the historical 9.43% was whichever 265 rows argsort put first",
    }
    chan = r[r["model"] == "baseline: channel rate"].iloc[0]
    out["channel_baseline"] = {"historical_top_decile_rate": float(chan["top_decile_rate"]),
                               "status": "unavailable",
                               "note": "train-period channel rates were not saved; its top-decile "
                                       "figure is tie-sensitive (at most one distinct score per "
                                       "channel) and cannot be re-derived"}
    return out
