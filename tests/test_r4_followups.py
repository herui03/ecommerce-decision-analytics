"""Review round 4 follow-ups: R4-05b (contextual validation of inference inputs and
float overflow) and R4-06 (file paths inside DuckDB SQL literals).

Imports of helpers are inside the tests so the pre-fix module produces per-test
failures instead of a collection error (evidence in docs/evidence/regressions/)."""
import csv
import shutil
from pathlib import Path

import pytest

from portfolio import paths
from portfolio.contract import FILES, ExtractError


def _rewrite(path: Path, col: str, value: str, row: int = 1):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    rows[row][rows[0].index(col)] = value
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


# ------------------------------------------------------------------ R4-05b
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "abc", "sNaN"])
def test_r4_05b_bad_low_score_rate_is_contextual(hist_copy, bad):
    from portfolio.contract import load_extracts
    _rewrite(hist_copy / FILES["monthly"], "low_score_rate_pct", bad)
    with pytest.raises(ExtractError, match="low_score_rate_pct"):
        load_extracts(hist_copy, "historical")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "not-a-number"])
def test_r4_05b_bad_aov_is_contextual(hist_copy, bad):
    from portfolio.contract import load_extracts
    _rewrite(hist_copy / FILES["state"], "aov_brl", bad)
    with pytest.raises(ExtractError, match="aov_brl"):
        load_extracts(hist_copy, "historical")


def test_r4_05b_float_overflow_is_rejected():
    from portfolio.contract import to_float
    with pytest.raises(ExtractError):
        to_float("1e999")
    with pytest.raises(ExtractError):
        to_float("-1e999")


def test_r4_05b_mean_overflow_in_extract_is_contextual(hist_copy):
    from portfolio.contract import load_extracts
    _rewrite(hist_copy / FILES["monthly"], "avg_review_score", "1e999")
    with pytest.raises(ExtractError, match="avg_review_score"):
        load_extracts(hist_copy, "historical")


def test_tolerance_uses_decimal_exponent_for_scientific_notation():
    from fractions import Fraction
    from portfolio.contract import exported_tolerance
    # '1e-05' is printed to the 1e-05 place: half-unit = 5e-06 (plus a few ulps)
    tol = exported_tolerance("1e-05")
    assert Fraction(5, 10 ** 6) <= tol < Fraction(6, 10 ** 6)


# ------------------------------------------------------------------ R4-06
def test_r4_06_sql_literal_escapes_single_quotes():
    from portfolio.paths import sql_literal
    assert sql_literal(Path("/tmp/Herui's portfolio/x.csv")) == "'/tmp/Herui''s portfolio/x.csv'"


def test_r4_06_counts_from_csv_in_quoted_directory(tmp_path):
    from portfolio.experiment import counts_from_csv
    d = tmp_path / "Herui's portfolio"
    d.mkdir()
    f = d / "rct.csv"
    rows = [["treatment", "conversion", "visit", "exposure"]]
    rows += [[1, 1, 1, 1]] * 3 + [[1, 0, 0, 0]] * 5 + [[0, 1, 1, 0]] * 1 + [[0, 0, 0, 0]] * 3
    with open(f, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    c = counts_from_csv(f)
    assert (c.n_t, c.y_t, c.n_c, c.y_c, c.n_exposed, c.y_exposed) == (8, 3, 4, 1, 3, 3)


def test_r4_06_export_extracts_to_quoted_directory(tmp_path):
    """Build a tiny warehouse from the committed SAMPLE extracts, export it into a
    directory whose name contains a space and an apostrophe, and load the result."""
    import duckdb
    from portfolio.contract import load_extracts
    from portfolio.paths import sql_literal
    from portfolio.pipeline import export_extracts
    root = tmp_path / "Herui's portfolio"
    root.mkdir()
    db = root / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA main_marts")
    for name, f in FILES.items():
        con.execute(f"CREATE TABLE main_marts.{f[:-4]} AS SELECT * FROM read_csv_auto({sql_literal(paths.SAMPLE_EXTRACTS / f)})")
    con.close()
    out = root / "extracts out"
    report = export_extracts(db, out)
    assert all(r["round_trip"] for r in report)
    x = load_extracts(out, "synthetic")
    assert len(x.monthly) == 20
