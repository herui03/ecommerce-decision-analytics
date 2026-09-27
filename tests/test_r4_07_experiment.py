"""Review round 4, item 7: experiment.py edge cases. Imports inside tests so the
pre-fix module reports per-test failures (docs/evidence/regressions/R4-07-*.txt)."""
import csv
import json
import math

import pytest


def test_r4_07_invalid_counts_give_one_controlled_result():
    from portfolio.experiment import ArmCounts, analyse
    res = analyse(ArmCounts(0, 0, 10, 1, 0, 0))          # empty treated arm
    assert res["status"] == "invalid" and res["problems"]
    json.dumps(res, allow_nan=False)


@pytest.mark.parametrize("counts", [
    (100, 90, 100, 10, 90, 0),     # 90 unexposed treated conversions among 10 unexposed users
    (100, 10, 100, 5, 20, 30),     # more exposed conversions than exposed users
    (100, 10, 100, 5, 20, 15),     # more exposed conversions than all treated conversions
    (100, 10, -1, 0, 0, 0),        # negative arm size
    (100.5, 10, 100, 5, 0, 0),     # non-integer count
    (True, 0, 100, 5, 0, 0),       # bool is not a count
])
def test_r4_07_infeasible_cells_are_rejected(counts):
    from portfolio.experiment import ArmCounts
    assert ArmCounts(*counts).validate(), f"{counts} should be infeasible"


def test_r4_07_all_zero_outcomes_are_explicit_not_nan():
    from portfolio.experiment import ArmCounts, analyse
    res = analyse(ArmCounts(1000, 0, 500, 0, 40, 0))
    s = json.dumps(res, allow_nan=False)                  # raises on NaN / Infinity
    assert "NaN" not in s
    itt = res["itt"]
    assert itt["ci"] is None and itt["ci_status"] == "unavailable"
    assert any("boundary" in w for w in itt["warnings"])


def test_r4_07_boundary_rate_does_not_report_degenerate_interval():
    from portfolio.experiment import ArmCounts, itt
    r = itt(ArmCounts(200, 0, 200, 3, 0, 0))              # treated rate exactly 0
    assert r["ci_status"] == "unavailable" and r["ci"] is None


def test_r4_07_small_counts_carry_an_approximation_warning():
    from portfolio.experiment import ArmCounts, itt
    r = itt(ArmCounts(300, 4, 300, 2, 0, 0))
    assert any("normal approximation" in w for w in r["warnings"])


def test_r4_07_generic_assumptions_carry_no_measured_numbers():
    from portfolio.experiment import ASSUMPTIONS
    text = json.dumps(ASSUMPTIONS)
    assert "0.0069" not in text and "0.85" not in text and "SMD 0." not in text


def test_r4_07_synthetic_run_has_its_own_measured_balance(tmp_path):
    from portfolio.experiment import balance_from_csv
    f = tmp_path / "rct.csv"
    rows = [["f0", "treatment", "conversion", "visit", "exposure"]]
    rows += [[v, 1, 0, 0, 1] for v in (1.0, 1.4)]
    rows += [[v, 1, 0, 0, 0] for v in (0.0, 0.2, 0.1, 0.3, -0.1, 0.05)]
    rows += [[v, 0, 0, 0, 0] for v in (0.5, 0.6, 0.4, 0.55)]
    with open(f, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    b = balance_from_csv(f, "f0")
    assert math.isfinite(b["smd_treatment"]) and math.isfinite(b["smd_exposure_within_treated"])
    assert b["smd_exposure_within_treated"] > b["smd_treatment"] > 0
    assert "synthetic" in b["provenance"]


def test_r4_07_balance_is_undefined_without_variance(tmp_path):
    from portfolio.experiment import balance_from_csv
    f = tmp_path / "flat.csv"
    rows = [["f0", "treatment", "conversion", "visit", "exposure"]]
    rows += [[1.0, 1, 0, 0, 1]] * 2 + [[0.0, 1, 0, 0, 0]] * 6 + [[0.5, 0, 0, 0, 0]] * 4
    with open(f, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    assert balance_from_csv(f, "f0")["smd_exposure_within_treated"] is None


@pytest.mark.parametrize("bad_row", [["", 0, 0, 0], [2, 0, 0, 0], [1, 3, 0, 0], [1, 0, 0, None]])
def test_r4_07_counts_from_csv_rejects_null_or_nonbinary(tmp_path, bad_row):
    from portfolio.experiment import counts_from_csv
    f = tmp_path / "rct.csv"
    rows = [["treatment", "conversion", "visit", "exposure"], [1, 0, 0, 0], [0, 1, 1, 0], [1, 1, 1, 1]]
    rows.append(["" if v is None else v for v in bad_row])
    with open(f, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    with pytest.raises(ValueError):
        counts_from_csv(f)


def test_r4_07_audit_states_window_end_and_usable_date_precisely():
    from portfolio.leads import audit_historical_split
    a = audit_historical_split()
    assert a["outcome_windows_end_between"] == ["2018-04-01", "2018-06-29"]
    assert a["labels_usable_from_between"] == ["2018-04-02", "2018-06-30"]
