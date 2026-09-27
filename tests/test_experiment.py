"""Experiment statistics: the documented historical figures reproduce from the
documented counts; the interval code has close to nominal coverage."""
import json
import math

import numpy as np
import pytest

from portfolio import experiment, paths
from portfolio.contract import infer_rate_numerator


@pytest.fixture(scope="module")
def hist():
    doc = json.loads((paths.HISTORICAL_DIR / "criteo_documented_counts.json").read_text())
    c = doc["counts"]
    return doc, experiment.ArmCounts(c["n_t"], c["y_t"], c["n_c"], c["y_c"], c["n_exposed"],
                                     doc["inferred"]["y_exposed"]["value"])


def test_exposed_conversions_are_uniquely_identified(hist):
    doc, c = hist
    inf = infer_rate_numerator(doc["inferred"]["y_exposed"]["documented_rate_pct"], c.n_exposed, "y")
    assert inf.status == "inferred" and inf.value == c.y_exposed == 23031


def test_documented_historical_results_reproduce(hist):
    doc, c = hist
    d = doc["documented_results"]
    a = experiment.analyse(c)
    assert round(100 * a["itt"]["diff"], 4) == d["itt_pp"]
    assert [round(100 * x, 4) for x in a["itt"]["ci"]] == d["itt_ci_pp"]
    assert round(100 * a["itt"]["relative_lift"], 2) == d["itt_relative_pct"]
    assert round(100 * a["cace"]["compliance"], 4) == d["compliance_pct"]
    assert round(100 * a["cace"]["cace"], 4) == d["cace_pp"]
    assert round(100 * a["cace"]["implied_complier_control_rate"], 4) == d["complier_control_rate_pct"]
    assert round(100 * a["cace"]["complier_relative_lift"], 2) == d["complier_relative_pct"]
    assert round(100 * a["naive"]["relative"], 2) == d["naive_relative_pct"]
    assert round(100 * a["cace"]["never_taker_rate"], 4) == d["never_taker_rate_pct"]
    assert round(100 * a["cohen_h_mde80"], 4) == d["mde80_pp"]
    assert round(100 * a["cohen_h_mde95"], 4) == d["mde95_pp"]
    assert round(a["itt"]["z"], 2) == d["z"]
    assert f'{10 ** (a["itt"]["log10_p_value"] + 179):.2f}' == "7.31"      # 7.31e-179
    assert a["cace"]["wald_vs_decomposition_gap"] < 1e-15


def test_interval_coverage_is_close_to_nominal():
    """300 simulated RCTs with a known effect (fixed seed): the Wald ITT interval and the
    delta-method CACE interval should cover the truth about 95% of the time."""
    rng = np.random.default_rng(20260926)
    cover_itt = cover_cace = 0
    reps, n_t, n_c, pi, p0, tau = 300, 40000, 10000, 0.08, 0.02, 0.05
    for _ in range(reps):
        d1 = rng.random(n_t) < pi
        y_t_arr = rng.random(n_t) < p0 + tau * d1
        y_c = int((rng.random(n_c) < p0 + 0 * 0).sum())
        c = experiment.ArmCounts(n_t, int(y_t_arr.sum()), n_c, y_c, int(d1.sum()), int((y_t_arr & d1).sum()))
        a = experiment.analyse(c)
        lo, hi = a["itt"]["ci"]
        cover_itt += lo <= tau * pi <= hi
        clo, chi = a["cace"]["ci"]
        cover_cace += clo <= tau <= chi
    assert 0.91 <= cover_itt / reps <= 0.98
    assert 0.90 <= cover_cace / reps <= 0.98


def test_synthetic_run_interval_covers_the_built_in_truth():
    res = json.loads((paths.SAMPLE_OUT / "experiment" / "criteo_synthetic.json").read_text())
    lo, hi = res["itt"]["ci"]
    assert lo <= res["truth"]["true_itt_pp"] / 100 <= hi
    clo, chi = res["cace"]["ci"]
    assert clo <= res["truth"]["true_cace_pp"] / 100 <= chi
    assert "synthetic" in res["diagnostics"]["provenance"]
    # the planted exposure trap: naive relative lift far above the ITT relative lift
    assert res["naive"]["relative"] > 5 * res["itt"]["relative_lift"]
