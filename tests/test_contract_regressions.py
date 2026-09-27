"""Regressions for Codex review round 4 (R4-03, R4-04, R4-05) on
python/portfolio/contract.py. Each test builds a small or mutated COPY of the
extracts and runs the real loader path (load_extracts), not a re-implementation.

Old-fails / fixed-passes evidence: docs/evidence/regressions/R4-contract-*.txt
"""
import csv
from pathlib import Path

import pytest

from portfolio.contract import ExtractError, FILES, load_extracts, to_cents, to_float, to_int


def _rewrite(path: Path, fn):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    rows = fn(rows)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerows(rows)


def _write(path: Path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def minimal_single_line_dataset(d: Path) -> Path:
    """One month, two orders, each with exactly ONE line in its own category.
    Summed distinct orders over categories == order lines == 2. This is valid."""
    d.mkdir(parents=True, exist_ok=True)
    _write(d / FILES["monthly"],
           ["purchase_month", "month_label", "orders", "active_customers", "gmv_brl", "goods_brl",
            "freight_brl", "payment_brl", "orders_with_items", "aov_brl", "canceled_orders",
            "cancel_rate_pct", "delivered_orders", "late_orders", "late_delivery_rate_pct",
            "avg_delivery_days", "reviewed_orders", "avg_review_score", "low_score_rate_pct",
            "avg_items_per_order", "avg_installments"],
           [["2017-01-01", "2017-01", "2", "2", "30.00", "25.00", "5.00", "30.00", "2", "15.0",
             "0", "0.0", "2", "1", "50.0", "10.0", "2", "4.0", "0.0", "1.0", "1.0"]])
    _write(d / FILES["category"],
           ["purchase_month", "month_label", "product_category", "order_lines", "orders", "customers",
            "products_sold", "active_sellers", "gmv_brl", "goods_brl", "freight_brl",
            "avg_line_value_brl", "freight_share_pct", "pct_of_month_gmv", "lines_missing_category",
            "lines_missing_translation"],
           [["2017-01-01", "2017-01", "cat_a", "1", "1", "1", "1", "1", "10.00", "8.00", "2.00",
             "10.0", "20.0", "33.3", "0", "0"],
            ["2017-01-01", "2017-01", "cat_b", "1", "1", "1", "1", "1", "20.00", "17.00", "3.00",
             "20.0", "15.0", "66.7", "0", "0"]])
    _write(d / FILES["state"],
           ["purchase_month", "month_label", "customer_state", "orders", "customers", "gmv_brl",
            "freight_brl", "aov_brl", "freight_share_pct", "avg_delivery_days",
            "late_delivery_rate_pct", "avg_review_score", "pct_of_month_gmv"],
           [["2017-01-01", "2017-01", "XA", "2", "2", "30.00", "5.00", "15.0", "16.6", "10.0", "50.0",
             "4.0", "100.0"]])
    _write(d / FILES["payment"],
           ["purchase_month", "month_label", "primary_payment_type", "orders", "payment_brl",
            "gmv_brl", "aov_brl", "avg_installments", "installment_orders", "installment_rate_pct",
            "pct_of_month_orders"],
           [["2017-01-01", "2017-01", "boleto", "2", "30.00", "30.00", "15.0", "1.0", "0", "0.0",
             "100.0"]])
    return d


# ------------------------------------------------------------------ R4-03
def test_r4_03_single_line_orders_are_valid(tmp_path):
    x = load_extracts(minimal_single_line_dataset(tmp_path / "x"), "synthetic")
    assert sum(r["orders"] for r in x.category) == sum(r["lines"] for r in x.category) == 2


# ------------------------------------------------------------------ R4-04
def test_r4_04_swapped_category_months_are_rejected(hist_copy):
    def swap(rows):
        h = rows[0]
        im, il = h.index("purchase_month"), h.index("month_label")
        for r in rows[1:]:
            if r[il] == "2017-01":
                r[il], r[im] = "2017-02", "2017-02-01"
            elif r[il] == "2017-02":
                r[il], r[im] = "2017-01", "2017-01-01"
        return rows
    _rewrite(hist_copy / FILES["category"], swap)
    with pytest.raises(ExtractError, match="2017-0[12]"):
        load_extracts(hist_copy, "historical")


def test_r4_04_swapped_state_months_are_rejected(hist_copy):
    def swap(rows):
        h = rows[0]
        im, il = h.index("purchase_month"), h.index("month_label")
        for r in rows[1:]:
            if r[il] == "2018-03":
                r[il], r[im] = "2018-04", "2018-04-01"
            elif r[il] == "2018-04":
                r[il], r[im] = "2018-03", "2018-03-01"
        return rows
    _rewrite(hist_copy / FILES["state"], swap)
    with pytest.raises(ExtractError):
        load_extracts(hist_copy, "historical")


@pytest.mark.parametrize("label,pm", [("2017-1", "2017-01-01"), ("2017-13", "2017-13-01"),
                                      ("2017-01", "2017-02-01"), ("17-01", "2017-01-01")])
def test_r4_04_non_canonical_or_inconsistent_month_is_rejected(hist_copy, label, pm):
    def bad(rows):
        h = rows[0]
        im, il = h.index("purchase_month"), h.index("month_label")
        rows[1][il], rows[1][im] = label, pm
        return rows
    _rewrite(hist_copy / FILES["payment"], bad)
    with pytest.raises(ExtractError):
        load_extracts(hist_copy, "historical")


# ------------------------------------------------------------------ R4-05
@pytest.mark.parametrize("text", ["NaN", "nan", "Infinity", "-inf", "sNaN"])
def test_r4_05_to_float_rejects_nonfinite(text):
    with pytest.raises(ExtractError):
        to_float(text)


@pytest.mark.parametrize("text", ["Infinity", "NaN", "1.5", "-3", "abc"])
def test_r4_05_to_int_rejects_bad_counts_with_extract_error(text):
    with pytest.raises(ExtractError):
        to_int(text)


def test_r4_05_to_cents_rejects_nonfinite():
    for t in ("NaN", "Infinity", "1e3", "0.001"):
        with pytest.raises(ExtractError):
            to_cents(t)


def test_r4_05_missing_required_count_is_a_contextual_error(hist_copy):
    def blank(rows):
        rows[1][rows[0].index("late_orders")] = ""
        return rows
    _rewrite(hist_copy / FILES["monthly"], blank)
    with pytest.raises(ExtractError, match="late_orders"):
        load_extracts(hist_copy, "historical")


def test_r4_05_nonfinite_mean_is_rejected(hist_copy):
    def nan(rows):
        rows[1][rows[0].index("avg_review_score")] = "NaN"
        return rows
    _rewrite(hist_copy / FILES["state"], nan)
    with pytest.raises(ExtractError):
        load_extracts(hist_copy, "historical")


def test_r4_05_duplicate_header_is_rejected(hist_copy):
    def dup(rows):
        h = rows[0]
        i = h.index("avg_installments")
        h[i] = "orders"               # DictReader would silently let the 2nd 'orders' win
        return rows
    _rewrite(hist_copy / FILES["payment"], dup)
    with pytest.raises(ExtractError, match="duplicate"):
        load_extracts(hist_copy, "historical")


def test_optional_true_nulls_remain_valid(hist_copy):
    """The committed payment extract has a genuine NULL GMV/AOV row (2018-08 not_defined).
    It must load, and its inferred denominator must be UNAVAILABLE, not dropped."""
    x = load_extracts(hist_copy, "historical")
    row = [r for r in x.payment if r["month"] == "2018-08" and r["ptype"] == "not_defined"][0]
    assert row["gmv_c"] is None and row["orders_with_items"] is None
    assert row["owi_status"] == "unavailable"


# ------------------------------------------------ payment scope (R4-04 follow-up)
def _unpaid_month(d: Path, with_components: bool, payment_gmv: str = "30.00") -> Path:
    """Month with 3 orders: 2 paid (primary boleto), 1 item-bearing order with NO payment
    record (10.00 of item value). The payment mart legitimately excludes the unpaid order."""
    minimal_single_line_dataset(d)
    mon = d / FILES["monthly"]
    def fix(rows):
        h, r = rows[0], rows[1]
        vals = {"orders": "3", "active_customers": "3", "gmv_brl": "40.00", "goods_brl": "33.00",
                "freight_brl": "7.00", "orders_with_items": "3", "delivered_orders": "3",
                "reviewed_orders": "3"}
        for k, v in vals.items():
            r[h.index(k)] = v
        if with_components:
            comp = {"low_score_orders": "0", "delivery_days_sum": "30", "delivery_days_n": "3",
                    "delivered_missing_delivery_date": "0", "review_score_sum": "12.0",
                    "review_score_n": "3", "items_sold": "3", "items_n": "3",
                    "installments_sum": "2", "installments_n": "2",
                    "orders_no_primary_payment": "1", "owi_no_primary_payment": "1",
                    "gmv_no_primary_payment_brl": "10.00", "payment_no_primary_payment_brl": "0"}
            h.extend(comp)
            r.extend(comp.values())
        return rows
    _rewrite(mon, fix)
    def cat(rows):   # add the unpaid order's line as a third category
        rows.append(["2017-01-01", "2017-01", "cat_c", "1", "1", "1", "1", "1", "10.00", "8.00",
                     "2.00", "10.0", "20.0", "25.0", "0", "0"])
        return rows
    _rewrite(d / FILES["category"], cat)
    def st(rows):
        h, r = rows[0], rows[1]
        for k, v in {"orders": "3", "customers": "3", "gmv_brl": "40.00", "freight_brl": "7.00",
                     "aov_brl": "13.333333333333334"}.items():
            r[h.index(k)] = v
        return rows
    _rewrite(d / FILES["state"], st)
    def pay(rows):
        rows[1][rows[0].index("gmv_brl")] = payment_gmv
        if with_components:
            rows[0].extend(["orders_with_items", "installments_sum", "installments_n"])
            rows[1].extend(["2", "2", "2"])
        return rows
    _rewrite(d / FILES["payment"], pay)
    return d


def test_unpaid_item_order_reconciles_exactly_with_components(tmp_path):
    x = load_extracts(_unpaid_month(tmp_path / "x", with_components=True), "synthetic")
    pay = [c for c in x.reconciliation if c["check"].startswith("payment")]
    assert pay and all(c["result"] == "pass" for c in pay)


def test_unpaid_item_order_is_bounded_not_rejected_without_components(tmp_path):
    x = load_extracts(_unpaid_month(tmp_path / "x", with_components=False), "historical")
    res = {c["check"]: c["result"] for c in x.reconciliation if c["check"].startswith("payment")}
    assert res["payment GMV <= month GMV (excluded population not in this extract)"] == "bounded"
    assert res["payment orders_with_items vs month"] == "unsupported"


def test_payment_gmv_above_month_is_rejected(tmp_path):
    d = _unpaid_month(tmp_path / "x", with_components=False, payment_gmv="45.00")
    with pytest.raises(ExtractError, match="payment GMV"):
        load_extracts(d, "historical")
