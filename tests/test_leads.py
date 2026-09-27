"""Lead scoring: label boundary and maturity, point-in-time features (leakage),
deterministic ties and permutation invariance, historical recomputation."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from portfolio import leads, paths


def frame(rows):
    return pd.DataFrame(rows, columns=["mql_id", "first_contact_date", "won_date", "lead_origin_channel",
                                       "landing_page_id", "page_lead_volume", "page_lead_volume_prior"])


def test_label_boundary_day_90_in_day_91_out_and_negative_lag():
    c = date(2018, 2, 10)
    df = leads.canonical(frame([
        ["a", c, c + timedelta(days=90), "x", "p", 1, 0],
        ["b", c, c + timedelta(days=91), "x", "p", 1, 0],
        ["c", c, c, "x", "p", 1, 0],
        ["d", c, c - timedelta(days=2), "x", "p", 1, 0],
        ["e", c, None, "x", "p", 1, 0]]))
    far = date(2019, 1, 1)
    assert list(leads.label_as_of(df, far)) == [True, False, True, False, False]
    # as-of censoring: the day-90 win is visible only from day 91 00:00
    assert list(leads.label_as_of(df, c + timedelta(days=90)))[0] is False
    assert list(leads.label_as_of(df, c + timedelta(days=91)))[0] is True


def test_train_end_is_as_of_minus_91_days():
    d = leads.CORRECTED
    assert d.train_end == d.as_of - timedelta(days=91)
    assert leads.label_as_of  # label for a train_end contact matures exactly at as_of
    assert d.train_end + timedelta(days=90) < d.as_of


def test_historical_windows_are_refused_when_maturity_is_enforced():
    bad = leads.LeadDesign("x", date(2018, 1, 1), date(2018, 4, 1), date(2018, 4, 1), date(2018, 5, 31),
                           date(2018, 8, 29))
    probs = bad.problems()
    assert probs and "2018-04-01" in probs[0] and "2018-04-02" in probs[0]
    assert leads.CORRECTED.problems() == []


def test_score_cohort_needs_observable_outcomes():
    d = leads.LeadDesign("x", date(2018, 1, 1), date(2018, 5, 1), date(2018, 5, 1), date(2018, 5, 31),
                         date(2018, 8, 28))
    assert any("observation" in p for p in d.problems())


def _random_leads(n=600, seed=3):
    rng = np.random.default_rng(seed)
    start = date(2018, 1, 1)
    rows = []
    for i in range(n):
        c = start + timedelta(days=int(rng.integers(0, 150)))
        won = c + timedelta(days=int(rng.integers(0, 200))) if rng.random() < 0.2 else None
        rows.append([f"L{i:04d}", c, won, str(rng.choice(["a", "b", "c"])), f"P{int(rng.integers(0, 25))}", 0, 0])
    df = frame(rows)
    df["page_lead_volume"] = leads.full_dataset_page_counts(df).values
    df["page_lead_volume_prior"] = leads.pit_page_counts(leads.canonical(df)).reindex(range(len(df))).values
    return leads.canonical(df)


def test_point_in_time_feature_ignores_every_later_row():
    df = _random_leads()
    cut = date(2018, 3, 15)
    base = leads.pit_page_counts(df)
    # drop, duplicate and relabel everything on/after the cut
    later = df[df.first_contact_date >= cut]
    mutated = pd.concat([df[df.first_contact_date < cut], later.sample(frac=0.5, random_state=1),
                         later.assign(mql_id=later.mql_id + "x", won_date=None)]).reset_index(drop=True)
    after = leads.pit_page_counts(leads.canonical(mutated))
    early = leads.canonical(mutated)
    keep = early.first_contact_date < cut
    before_vals = dict(zip(df.mql_id, base))
    assert all(before_vals[m] == v for m, v in zip(early.mql_id[keep], after[keep]))


def test_legacy_full_dataset_feature_fails_that_invariance():
    """The leakage test has teeth: the legacy count changes when future rows change."""
    df = _random_leads()
    cut = date(2018, 3, 15)
    early_ids = set(df.mql_id[df.first_contact_date < cut])
    trimmed = df[df.first_contact_date < cut].reset_index(drop=True)
    full = dict(zip(df.mql_id, leads.full_dataset_page_counts(df)))
    cut_only = dict(zip(trimmed.mql_id, leads.full_dataset_page_counts(trimmed)))
    assert any(full[m] != cut_only[m] for m in early_ids)


def test_features_do_not_depend_on_labels():
    df = _random_leads()
    shuffled = df.assign(won_date=df.won_date.sample(frac=1, random_state=7).values)
    assert (leads.pit_page_counts(df).values == leads.pit_page_counts(shuffled).values).all()


def test_training_labels_never_use_wins_observed_after_as_of():
    df = _random_leads()
    d = leads.LeadDesign("t", date(2018, 1, 1), date(2018, 4, 15), date(2018, 4, 15), date(2018, 5, 20),
                         date(2018, 8, 30))
    tr = df[(df.first_contact_date >= d.train_start) & (df.first_contact_date <= d.train_end)]
    y = leads.label_as_of(tr, d.as_of)
    assert all(w is None or w < d.as_of or not yy for w, yy in zip(tr.won_date, y))


def test_run_design_is_permutation_invariant_and_deterministic():
    df = _random_leads(900)
    d = leads.LeadDesign("t", date(2018, 1, 1), date(2018, 4, 15), date(2018, 4, 15), date(2018, 5, 30),
                         date(2018, 8, 30))
    a = leads.run_design(df, d)
    b = leads.run_design(df.sample(frac=1, random_state=11).reset_index(drop=True), d)
    assert a["status"] == "ok"
    assert a["results"] == b["results"] and a["scores"] == b["scores"]


def test_ranking_breaks_ties_by_id_not_row_order():
    ids = np.array(["c", "a", "b", "d"])
    s = np.array([0.5, 0.5, 0.9, 0.5])
    assert list(ids[leads.ranked(ids, s)]) == ["b", "a", "c", "d"]
    perm = [3, 2, 1, 0]
    assert list(ids[perm][leads.ranked(ids[perm], s[perm])]) == ["b", "a", "c", "d"]


def test_constant_score_gets_base_rate_expectation():
    y = np.array([1, 0, 0, 1, 0, 0, 0, 0, 0, 0])
    t = leads.top_k(np.array([str(i) for i in range(10)]), y, np.full(10, 0.3), 5)
    assert t["expected_hits"] == pytest.approx(1.0) and t["tie_block"] == 10


def test_historical_scores_recompute_to_committed_metrics():
    r = leads.recompute_historical(paths.HISTORICAL_OUTPUTS / "lead_scores_test.csv",
                                   paths.HISTORICAL_OUTPUTS / "lead_scoring_results.csv")
    assert r["rows"] == 2655 and r["positives"] == 280 and r["mql_id_unique"]
    for m in r["models"]:
        assert m["auc"] == pytest.approx(m["historical_auc"], abs=1e-12)
        assert m["pr_auc"] == pytest.approx(m["historical_pr_auc"], abs=1e-12)
        assert m["brier"] == pytest.approx(m["historical_brier"], abs=1e-12)
        assert m["top_min_hits"] <= m["historical_top_decile_hits"] <= m["top_max_hits"]
    lr, gb = r["models"]
    assert (lr["top_min_hits"], lr["top_max_hits"], lr["top_tie_block"]) == (52, 54, 7)
    assert (gb["top_min_hits"], gb["top_max_hits"], gb["top_tie_block"]) == (49, 54, 47)
    cb = r["constant_baseline"]
    assert cb["historical_hits"] == 25 and cb["tie_aware_expected_hits"] == pytest.approx(265 * 280 / 2655)


def test_audit_of_historical_split_is_date_arithmetic():
    a = leads.audit_historical_split()
    assert a["share_of_training_labels_usable_at_cut"] == 0.0
    assert a["latest_contact_usable_at_cut"] == "2017-12-31"
