"""Metric/grain contract for the four Olist metric-layer extracts.

This module turns an extract CSV into rows the dashboard can aggregate WITHOUT
changing any definition in dbt/models/marts/*.sql:

* Money is parsed with Decimal and stored as integer cents. It is never a float until
  it is formatted for display.
* Counts stay integers. Rates and means are re-derived at display time from summed
  numerators and denominators - never averaged across rows.
* A column the SQL computes as a per-cell mean over a VALID-VALUE count (delivery
  days, review score, items per order, installments) cannot be combined across cells
  unless the extract also carries that valid count and the matching sum. Older
  extracts do not, so combined values are UNAVAILABLE for them.
* Two denominators that the historical extracts do not store are recovered only by a
  bounded inference (see `infer_unique_integer`): accepted only when EXACTLY ONE
  integer in the feasible range reproduces the exported ratio within its exported
  precision. Otherwise the cell is UNAVAILABLE and that status propagates into every
  total that includes it.

Grain summary (from the SQL, see docs/metric-dictionary.md for the full contract):
  monthly  - month                       (fct_orders, analysis window)
  category - month x product_category    (fct_order_items, item grain)
  state    - month x customer_state      (fct_orders)
  payment  - month x primary_payment_type(fct_orders; one exclusive label per order)
The four grains are separate: no extract supports a joint month x state x category
filter, so the dashboard scopes each filter to the view whose grain carries it.
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from math import ceil, floor
from pathlib import Path


class ExtractError(ValueError):
    """An extract is missing, empty, or violates its declared schema."""


# --------------------------------------------------------------------------- money
def to_cents(text: str | None) -> int | None:
    """'1234.56' -> 123456. Empty -> None (NULL is not zero). Rejects sub-cent values,
    non-numbers and floats-in-disguise such as '1e3'."""
    if text is None or text == "":
        return None
    try:
        d = Decimal(text)
    except InvalidOperation as exc:
        raise ExtractError(f"not a decimal money value: {text!r}") from exc
    if not d.is_finite() or "e" in text.lower():
        raise ExtractError(f"not a plain decimal money value: {text!r}")
    c = d * 100
    if c != c.to_integral_value():
        raise ExtractError(f"money value has sub-cent precision: {text!r}")
    return int(c)


def _finite_decimal(text: str, what: str) -> Decimal:
    try:
        d = Decimal(text)
    except InvalidOperation as exc:
        raise ExtractError(f"not a {what}: {text!r}") from exc
    if not d.is_finite():                       # NaN, sNaN, Infinity, -Infinity
        raise ExtractError(f"non-finite {what}: {text!r}")
    return d


def to_int(text: str | None) -> int | None:
    if text is None or text == "":
        return None
    d = _finite_decimal(text, "integer count")
    if d != d.to_integral_value() or d < 0:
        raise ExtractError(f"count must be a non-negative integer: {text!r}")
    return int(d)


def to_float(text: str | None) -> float | None:
    if text is None or text == "":
        return None
    v = float(_finite_decimal(text, "number"))
    if not math.isfinite(v):                    # e.g. '1e999' is a finite Decimal but no double
        raise ExtractError(f"number out of double range: {text!r}")
    return v


def req(conv, row: dict, col: str, ctx: str):
    """A REQUIRED field: NULL/empty is a contract violation, reported with context."""
    try:
        v = conv(row[col])
    except ExtractError as exc:
        raise ExtractError(f"{ctx}: column {col}: {exc}") from None
    if v is None:
        raise ExtractError(f"{ctx}: required column {col} is empty")
    return v


def opt(conv, row: dict, col: str, ctx: str):
    """An OPTIONAL field: empty is a true NULL (kept as None), bad text is still an error."""
    try:
        return conv(row[col])
    except ExtractError as exc:
        raise ExtractError(f"{ctx}: column {col}: {exc}") from None


# ------------------------------------------------------------------ bounded inference
@dataclass(frozen=True)
class Inference:
    value: int | None
    status: str            # "inferred" | "unavailable"
    reason: str
    candidates: int        # number of feasible integers found (0, 1, or >1)


def exported_tolerance(text: str) -> Fraction:
    """Half a unit in the last printed decimal place (taken from the Decimal exponent,
    so '11.1093' and '1e-05' are both handled), plus 8 double-precision ulps of the value
    for the single rounded division that produced it. Deliberately tight: a broad
    isclose would admit several denominators and hide the ambiguity."""
    d = _finite_decimal(text.strip(), "ratio")
    exp = d.as_tuple().exponent
    half_unit = Fraction(1, 2) * (Fraction(10) ** exp)
    return half_unit + abs(Fraction(d)) * Fraction(8, 2 ** 53)


def infer_unique_integer(ratio_text: str | None, numerator: Fraction | None,
                         scale: Fraction, lo: int, hi: int, what: str) -> Inference:
    """Find integers n in [lo, hi] with |scale * numerator / n - ratio| <= tol, where
    the ratio column was produced by SQL as scale*numerator/n (n > 0; n = 0 would have
    made the ratio NULL via nullif). Accept only a UNIQUE feasible n.

    Used for:
      AOV        = gmv / orders_with_items        -> n = orders_with_items in [1, orders]
      low-score% = 100 * k / reviewed             -> solved for k by the caller variant
    """
    if ratio_text is None or ratio_text == "":
        return Inference(None, "unavailable",
                         f"{what}: ratio is NULL - a zero denominator and a NULL numerator "
                         "are indistinguishable", 0)
    if numerator is None:
        return Inference(None, "unavailable", f"{what}: numerator is NULL", 0)
    r = Fraction(_finite_decimal(ratio_text, "ratio"))      # bad text -> ExtractError
    tol = exported_tolerance(ratio_text)
    lo = max(lo, 1)
    if hi < lo:
        return Inference(None, "unavailable", f"{what}: empty feasible range", 0)
    target = scale * numerator
    if target == 0:
        # every n >= 1 gives ratio 0: identified only if the range holds one integer
        if r == 0 or abs(r) <= tol:
            n = hi - lo + 1
            if n == 1:
                return Inference(lo, "inferred", f"{what}: zero numerator, single feasible value", 1)
            return Inference(None, "unavailable",
                             f"{what}: zero numerator - any of {n} denominators fits", n)
        return Inference(None, "unavailable", f"{what}: zero numerator but non-zero ratio", 0)
    rmin, rmax = r - tol, r + tol
    if rmax <= 0:
        return Inference(None, "unavailable", f"{what}: ratio has wrong sign", 0)
    # target / n in [rmin, rmax]  <=>  n in [target / rmax, target / rmin]
    n_lo = ceil(target / rmax)
    n_hi = floor(target / rmin) if rmin > 0 else hi
    n_lo, n_hi = max(n_lo, lo), min(n_hi, hi)
    count = max(0, n_hi - n_lo + 1)
    if count == 1:
        return Inference(n_lo, "inferred", f"{what}: unique integer reproduces exported ratio", 1)
    if count == 0:
        return Inference(None, "unavailable",
                         f"{what}: no integer in [{lo}, {hi}] reproduces the exported ratio "
                         "(inconsistent or tampered row)", 0)
    return Inference(None, "unavailable",
                     f"{what}: {count} integers reproduce the exported ratio at its precision", count)


def infer_aov_denominator(gmv_text: str | None, aov_text: str | None, orders: int) -> Inference:
    """orders_with_items from gmv_brl and aov_brl = gmv / nullif(orders_with_items, 0)."""
    if gmv_text in (None, ""):
        return Inference(None, "unavailable",
                         "orders_with_items: GMV is NULL (no item value recorded), so the "
                         "denominator is not identified", 0)
    return infer_unique_integer(aov_text, Fraction(_finite_decimal(gmv_text, "GMV")), Fraction(1),
                                1, orders, "orders_with_items")


def infer_rate_numerator(rate_text: str | None, denominator: int, what: str) -> Inference:
    """k from rate = 100 * k / denominator, k in [0, denominator]. Solved directly:
    k in [(rate - tol) * d / 100, (rate + tol) * d / 100]."""
    if rate_text in (None, ""):
        return Inference(None, "unavailable", f"{what}: rate is NULL", 0)
    if denominator <= 0:
        return Inference(None, "unavailable", f"{what}: denominator is zero", 0)
    r = Fraction(_finite_decimal(rate_text, "rate"))        # bad text -> ExtractError
    tol = exported_tolerance(rate_text)
    k_lo = max(0, ceil((r - tol) * denominator / 100))
    k_hi = min(denominator, floor((r + tol) * denominator / 100))
    count = max(0, k_hi - k_lo + 1)
    if count == 1:
        return Inference(k_lo, "inferred", f"{what}: unique integer reproduces exported rate", 1)
    if count == 0:
        return Inference(None, "unavailable", f"{what}: no integer reproduces the exported rate", 0)
    return Inference(None, "unavailable", f"{what}: {count} integers reproduce the exported rate", count)


# ------------------------------------------------------------------------ schemas
MONTHLY_REQUIRED = ["purchase_month", "month_label", "orders", "active_customers", "gmv_brl",
                    "goods_brl", "freight_brl", "payment_brl", "orders_with_items", "aov_brl",
                    "canceled_orders", "cancel_rate_pct", "delivered_orders", "late_orders",
                    "late_delivery_rate_pct", "avg_delivery_days", "reviewed_orders",
                    "avg_review_score", "low_score_rate_pct", "avg_items_per_order",
                    "avg_installments"]
CATEGORY_REQUIRED = ["purchase_month", "month_label", "product_category", "order_lines", "orders",
                     "customers", "products_sold", "active_sellers", "gmv_brl", "goods_brl",
                     "freight_brl", "avg_line_value_brl", "freight_share_pct", "pct_of_month_gmv",
                     "lines_missing_category", "lines_missing_translation"]
STATE_REQUIRED = ["purchase_month", "month_label", "customer_state", "orders", "customers",
                  "gmv_brl", "freight_brl", "aov_brl", "freight_share_pct", "avg_delivery_days",
                  "late_delivery_rate_pct", "avg_review_score", "pct_of_month_gmv"]
PAYMENT_REQUIRED = ["purchase_month", "month_label", "primary_payment_type", "orders", "payment_brl",
                    "gmv_brl", "aov_brl", "avg_installments", "installment_orders",
                    "installment_rate_pct", "pct_of_month_orders"]
# Additive components written by the 2026-09 marts (optional: older extracts lack them).
MONTHLY_COMPONENTS = ["low_score_orders", "delivery_days_sum", "delivery_days_n",
                      "delivered_missing_delivery_date", "review_score_sum", "review_score_n",
                      "items_sold", "items_n", "installments_sum", "installments_n",
                      "orders_no_primary_payment", "owi_no_primary_payment",
                      "gmv_no_primary_payment_brl", "payment_no_primary_payment_brl"]
STATE_COMPONENTS = ["orders_with_items", "delivered_orders", "late_orders", "delivery_days_sum",
                    "delivery_days_n", "review_score_sum", "review_score_n"]
PAYMENT_COMPONENTS = ["orders_with_items", "installments_sum", "installments_n"]

FILES = {
    "monthly": "mart_monthly_performance.csv",
    "category": "mart_category_performance.csv",
    "state": "mart_state_performance.csv",
    "payment": "mart_payment_performance.csv",
}


def read_csv(path: Path, required: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise ExtractError(f"missing extract: {path}")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = list(reader)
    if not header:
        raise ExtractError(f"empty extract (no header): {path.name}")
    dupes = sorted({c for c in header if header.count(c) > 1})
    if dupes:
        raise ExtractError(f"{path.name}: duplicate column names {dupes} "
                           "(a dict reader would silently keep only the last one)")
    missing = [c for c in required if c not in header]
    if missing:
        raise ExtractError(f"{path.name}: missing required columns {missing}")
    if not rows:
        raise ExtractError(f"{path.name}: header only, zero data rows")
    for i, r in enumerate(rows, start=2):
        if None in r or any(v is None for v in r.values()):
            raise ExtractError(f"{path.name}: line {i} has the wrong number of fields")
    return header, rows


_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_PURCHASE_MONTH = re.compile(r"^(\d{4}-(?:0[1-9]|1[0-2]))-01(?:[ T]00:00:00(?:\.0+)?)?$")


def _month(row: dict, name: str) -> str:
    """Canonical YYYY-MM label that agrees with purchase_month (the first day of that
    month). A non-canonical label such as '2017-1' would sort after '2017-10'; a label
    that disagrees with purchase_month means the row was edited or mis-exported."""
    label, pm = row.get("month_label") or "", row.get("purchase_month") or ""
    if not _MONTH.match(label):
        raise ExtractError(f"{name}: month_label {label!r} is not canonical YYYY-MM")
    m = _PURCHASE_MONTH.match(pm)
    if not m:
        raise ExtractError(f"{name}: purchase_month {pm!r} is not the first day of a month")
    if m.group(1) != label:
        raise ExtractError(f"{name}: month_label {label!r} disagrees with purchase_month {pm!r}")
    return label


def _check_unique(rows: list[dict], keys: tuple[str, ...], name: str) -> None:
    seen = set()
    for r in rows:
        k = tuple(r[x] for x in keys)
        if k in seen:
            raise ExtractError(f"{name}: duplicate grain key {k} - grain {keys} violated")
        seen.add(k)


@dataclass
class Extracts:
    source: str                      # "historical" | "synthetic"
    monthly: list[dict] = field(default_factory=list)
    category: list[dict] = field(default_factory=list)
    state: list[dict] = field(default_factory=list)
    payment: list[dict] = field(default_factory=list)
    components: dict[str, bool] = field(default_factory=dict)
    inference_log: list[dict] = field(default_factory=list)
    reconciliation: list[dict] = field(default_factory=list)


def _ctx(fn, ctx: str, col: str):
    """Run an inference and attach file/row/column context to any contract violation."""
    try:
        return fn()
    except ExtractError as exc:
        raise ExtractError(f"{ctx}: column {col}: {exc}") from None


def _log(out: Extracts, extract: str, key: str, fld: str, inf: Inference) -> None:
    out.inference_log.append({"extract": extract, "key": key, "field": fld, "status": inf.status,
                              "value": inf.value, "candidates": inf.candidates, "reason": inf.reason})


def load_extracts(directory: Path, source: str) -> Extracts:
    """Load, type-check and reconcile the four extracts. Raises ExtractError with the
    file, row key and column on any contract violation."""
    out = Extracts(source=source)

    # ---- monthly ------------------------------------------------------------------
    hdr, rows = read_csv(directory / FILES["monthly"], MONTHLY_REQUIRED)
    has_comp = all(c in hdr for c in MONTHLY_COMPONENTS)
    out.components["monthly"] = has_comp
    for r in rows:
        m = _month(r, "monthly")
        ctx = f"monthly {m}"
        row = {
            "month": m,
            "orders": req(to_int, r, "orders", ctx),
            "active_customers": req(to_int, r, "active_customers", ctx),
            "gmv_c": opt(to_cents, r, "gmv_brl", ctx),
            "goods_c": opt(to_cents, r, "goods_brl", ctx),
            "freight_c": opt(to_cents, r, "freight_brl", ctx),
            "payment_c": opt(to_cents, r, "payment_brl", ctx),
            "orders_with_items": req(to_int, r, "orders_with_items", ctx),
            "canceled": req(to_int, r, "canceled_orders", ctx),
            "delivered": req(to_int, r, "delivered_orders", ctx),
            "late": req(to_int, r, "late_orders", ctx),
            "reviewed": req(to_int, r, "reviewed_orders", ctx),
            # original-grain means: valid for this single month only
            "avg_delivery_days": opt(to_float, r, "avg_delivery_days", ctx),
            "avg_review_score": opt(to_float, r, "avg_review_score", ctx),
            "avg_items_per_order": opt(to_float, r, "avg_items_per_order", ctx),
            "avg_installments": opt(to_float, r, "avg_installments", ctx),
            "late_rate_pct_exported": opt(to_float, r, "late_delivery_rate_pct", ctx),
        }
        opt(to_float, r, "aov_brl", ctx)
        opt(to_float, r, "cancel_rate_pct", ctx)
        if row["orders"] == 0:
            raise ExtractError(f"{ctx}: orders must be positive (a month row exists only if it has orders)")
        if row["late"] > row["delivered"] or row["delivered"] > row["orders"] \
                or row["canceled"] > row["orders"] or row["orders_with_items"] > row["orders"] \
                or row["reviewed"] > row["orders"] or row["active_customers"] > row["orders"]:
            raise ExtractError(f"{ctx}: a count exceeds its denominator")
        if None not in (row["gmv_c"], row["goods_c"], row["freight_c"]) \
                and row["goods_c"] + row["freight_c"] != row["gmv_c"]:
            raise ExtractError(f"{ctx}: goods + freight != GMV")
        if has_comp:
            row["low_score"] = req(to_int, r, "low_score_orders", ctx)
            row["low_score_status"] = "observed"
            for c in MONTHLY_COMPONENTS[1:]:
                if c == "review_score_sum":
                    row[c] = opt(to_float, r, c, ctx)
                elif c.endswith("_brl"):
                    row[c.replace("_brl", "_c")] = req(to_cents, r, c, ctx)
                elif c in ("delivery_days_sum", "items_sold", "installments_sum"):
                    row[c] = opt(to_int, r, c, ctx)      # sum over zero valid rows is NULL
                else:
                    row[c] = req(to_int, r, c, ctx)
        else:
            inf = _ctx(lambda: infer_rate_numerator(r["low_score_rate_pct"], row["reviewed"],
                                                    "low_score_orders"), ctx, "low_score_rate_pct")
            row["low_score"] = inf.value
            row["low_score_status"] = inf.status
            _log(out, "monthly", m, "low_score_orders", inf)
        out.monthly.append(row)
    _check_unique(out.monthly, ("month",), "monthly")
    out.monthly.sort(key=lambda r: r["month"])
    months = [r["month"] for r in out.monthly]
    _check_contiguous(months)

    # ---- category -----------------------------------------------------------------
    hdr, rows = read_csv(directory / FILES["category"], CATEGORY_REQUIRED)
    for r in rows:
        m = _month(r, "category")
        ctx = f"category {m}/{r['product_category']}"
        row = {
            "month": m,
            "category": r["product_category"],
            "lines": req(to_int, r, "order_lines", ctx),
            "orders": req(to_int, r, "orders", ctx),          # distinct within the cell
            "customers": req(to_int, r, "customers", ctx),    # distinct within the cell
            "products": req(to_int, r, "products_sold", ctx),
            "sellers": req(to_int, r, "active_sellers", ctx),
            "gmv_c": req(to_cents, r, "gmv_brl", ctx),        # item rows always carry a price
            "goods_c": req(to_cents, r, "goods_brl", ctx),
            "freight_c": req(to_cents, r, "freight_brl", ctx),
            "lines_missing_category": req(to_int, r, "lines_missing_category", ctx),
            "lines_missing_translation": req(to_int, r, "lines_missing_translation", ctx),
        }
        for c in ("avg_line_value_brl", "freight_share_pct", "pct_of_month_gmv"):
            opt(to_float, r, c, ctx)
        if not row["category"]:
            raise ExtractError(f"{ctx}: product_category must not be empty ('unknown' is the NULL bucket)")
        if not 1 <= row["orders"] <= row["lines"]:
            raise ExtractError(f"{ctx}: need 1 <= distinct orders <= lines")
        if row["goods_c"] + row["freight_c"] != row["gmv_c"]:
            raise ExtractError(f"{ctx}: goods + freight != GMV")
        out.category.append(row)
    _check_unique(out.category, ("month", "category"), "category")
    out.category.sort(key=lambda r: (r["month"], r["category"]))

    # ---- state ----------------------------------------------------------------------
    hdr, rows = read_csv(directory / FILES["state"], STATE_REQUIRED)
    has_comp = all(c in hdr for c in STATE_COMPONENTS)
    out.components["state"] = has_comp
    for r in rows:
        m = _month(r, "state")
        ctx = f"state {m}/{r['customer_state']}"
        row = {
            "month": m,
            "state": r["customer_state"],
            "orders": req(to_int, r, "orders", ctx),
            "customers": req(to_int, r, "customers", ctx),
            "gmv_c": opt(to_cents, r, "gmv_brl", ctx),
            "freight_c": opt(to_cents, r, "freight_brl", ctx),
            "avg_delivery_days": opt(to_float, r, "avg_delivery_days", ctx),
            "late_rate_pct": opt(to_float, r, "late_delivery_rate_pct", ctx),
            "avg_review_score": opt(to_float, r, "avg_review_score", ctx),
        }
        for c in ("aov_brl", "freight_share_pct", "pct_of_month_gmv"):
            opt(to_float, r, c, ctx)
        if not row["state"]:
            raise ExtractError(f"{ctx}: customer_state must not be empty")
        if has_comp:
            row["orders_with_items"] = req(to_int, r, "orders_with_items", ctx)
            row["owi_status"] = "observed"
            for c in STATE_COMPONENTS[1:]:
                if c == "review_score_sum":
                    row[c] = opt(to_float, r, c, ctx)
                elif c == "delivery_days_sum":
                    row[c] = opt(to_int, r, c, ctx)
                else:
                    row[c] = req(to_int, r, c, ctx)
        else:
            inf = _ctx(lambda: infer_aov_denominator(r["gmv_brl"], r["aov_brl"], row["orders"]),
                       ctx, "aov_brl")
            row["orders_with_items"] = inf.value
            row["owi_status"] = inf.status
            _log(out, "state", f"{m}/{row['state']}", "orders_with_items", inf)
        out.state.append(row)
    _check_unique(out.state, ("month", "state"), "state")
    out.state.sort(key=lambda r: (r["month"], r["state"]))

    # ---- payment ----------------------------------------------------------------------
    hdr, rows = read_csv(directory / FILES["payment"], PAYMENT_REQUIRED)
    has_comp = all(c in hdr for c in PAYMENT_COMPONENTS)
    out.components["payment"] = has_comp
    for r in rows:
        m = _month(r, "payment")
        ctx = f"payment {m}/{r['primary_payment_type']}"
        row = {
            "month": m,
            "ptype": r["primary_payment_type"],
            "orders": req(to_int, r, "orders", ctx),
            "payment_c": opt(to_cents, r, "payment_brl", ctx),
            "gmv_c": opt(to_cents, r, "gmv_brl", ctx),
            "installment_orders": req(to_int, r, "installment_orders", ctx),
            "avg_installments": opt(to_float, r, "avg_installments", ctx),
        }
        for c in ("aov_brl", "installment_rate_pct", "pct_of_month_orders"):
            opt(to_float, r, c, ctx)
        if not row["ptype"]:
            raise ExtractError(f"{ctx}: NULL primary_payment_type rows must be excluded by the mart")
        if row["installment_orders"] > row["orders"]:
            raise ExtractError(f"{ctx}: installment orders exceed orders")
        if has_comp:
            row["orders_with_items"] = req(to_int, r, "orders_with_items", ctx)
            row["owi_status"] = "observed"
            row["installments_sum"] = opt(to_int, r, "installments_sum", ctx)
            row["installments_n"] = req(to_int, r, "installments_n", ctx)
        else:
            inf = _ctx(lambda: infer_aov_denominator(r["gmv_brl"], r["aov_brl"], row["orders"]),
                       ctx, "aov_brl")
            row["orders_with_items"] = inf.value
            row["owi_status"] = inf.status
            _log(out, "payment", f"{m}/{row['ptype']}", "orders_with_items", inf)
        out.payment.append(row)
    _check_unique(out.payment, ("month", "ptype"), "payment")
    out.payment.sort(key=lambda r: (r["month"], r["ptype"]))

    for name in ("category", "state", "payment"):
        extra = sorted({r["month"] for r in getattr(out, name)} - set(months))
        if extra:
            raise ExtractError(f"{name}: months {extra} are outside the monthly extract's window")
    out.reconciliation = reconcile(out)
    bad = [c for c in out.reconciliation if c["result"] == "fail"]
    if bad:
        raise ExtractError("cross-extract reconciliation failed: "
                           + "; ".join(f"{c['check']} [{c['month']}]: {c['detail']}" for c in bad[:4]))
    return out


def _check_unique(rows: list[dict], keys: tuple[str, ...], name: str) -> None:
    seen = set()
    for r in rows:
        k = tuple(r[x] for x in keys)
        if k in seen:
            raise ExtractError(f"{name}: duplicate grain key {k} - grain {keys} violated")
        seen.add(k)


def _check_contiguous(months: list[str]) -> None:
    def idx(m):
        y, mm = map(int, m.split("-"))
        return y * 12 + mm - 1
    for a, b in zip(months, months[1:]):
        if idx(b) - idx(a) != 1:
            raise ExtractError(f"monthly extract has a gap between {a} and {b}")


def reconcile(x: Extracts) -> list[dict]:
    """Per-MONTH checks that tie the separately-grained extracts to the monthly extract.
    Each check is scoped to what its grain can support:

      state    - exclusive per order (one customer state per order): orders, GMV, freight
                 and orders_with_items must EQUAL the month.
      category - item grain: GMV, goods and freight must EQUAL the month; distinct orders
                 are NOT exclusive across categories, so they are only bounded:
                 orders_with_items <= sum over categories <= order lines.
      payment  - excludes orders with a NULL primary type (no payment record). With the
                 2026-09 excluded-population columns the month reconciles EXACTLY
                 (payment mart + excluded == month). Without them the check is exact only
                 in months where no order is excluded, and otherwise BOUNDED - the gap
                 is reported as unattributed, never filled with invented payments.

    result: "pass" | "fail" | "bounded" (a weaker check that passed) |
            "unsupported" (the extract cannot support the check)."""
    checks: list[dict] = []

    def add(name, month, result, detail):
        checks.append({"check": name, "month": month, "result": result, "detail": detail})

    def eq(name, month, a, b):
        add(name, month, "pass" if a == b else "fail", f"{a} vs {b}")

    def s(rows, f):
        return sum(r[f] or 0 for r in rows)

    by = {name: {} for name in ("category", "state", "payment")}
    for name in by:
        for r in getattr(x, name):
            by[name].setdefault(r["month"], []).append(r)
    comp = x.components.get("monthly", False)

    for mr in x.monthly:
        m = mr["month"]
        gmv, freight = mr["gmv_c"] or 0, mr["freight_c"] or 0
        # ---- category
        c = by["category"].get(m, [])
        eq("category GMV == month GMV (cents)", m, s(c, "gmv_c"), gmv)
        eq("category goods == month goods (cents)", m, s(c, "goods_c"), mr["goods_c"] or 0)
        eq("category freight == month freight (cents)", m, s(c, "freight_c"), freight)
        so, sl = s(c, "orders"), s(c, "lines")
        add("orders_with_items <= category distinct orders summed <= lines", m,
            "bounded" if mr["orders_with_items"] <= so <= sl else "fail",
            f"{mr['orders_with_items']} <= {so} <= {sl} (multi-category orders count once per category)")
        # ---- state
        st = by["state"].get(m, [])
        eq("state orders == month orders", m, s(st, "orders"), mr["orders"])
        eq("state GMV == month GMV (cents)", m, s(st, "gmv_c"), gmv)
        eq("state freight == month freight (cents)", m, s(st, "freight_c"), freight)
        known = [r for r in st if r["owi_status"] in ("observed", "inferred")]
        unknown = [r for r in st if r not in known]
        if not unknown:
            eq("state orders_with_items == month", m, s(known, "orders_with_items"), mr["orders_with_items"])
        else:
            lo, hi = s(known, "orders_with_items"), s(known, "orders_with_items") + s(unknown, "orders")
            add("state orders_with_items bounded by month", m,
                "bounded" if lo <= mr["orders_with_items"] <= hi else "fail",
                f"{lo} <= {mr['orders_with_items']} <= {hi}")
        # ---- payment
        p = by["payment"].get(m, [])
        p_orders, p_gmv, p_pay = s(p, "orders"), s(p, "gmv_c"), s(p, "payment_c")
        pk = [r for r in p if r["owi_status"] in ("observed", "inferred")]
        pu = [r for r in p if r not in pk]
        if comp:
            eq("payment orders + excluded == month orders", m,
               p_orders + mr["orders_no_primary_payment"], mr["orders"])
            eq("payment GMV + excluded GMV == month GMV (cents)", m,
               p_gmv + mr["gmv_no_primary_payment_c"], gmv)
            eq("payment payments + excluded == month payments (cents)", m,
               p_pay + mr["payment_no_primary_payment_c"], mr["payment_c"] or 0)
            eq("payment orders_with_items + excluded == month", m,
               s(p, "orders_with_items") + mr["owi_no_primary_payment"], mr["orders_with_items"])
            continue
        excluded = mr["orders"] - p_orders
        if excluded < 0:
            add("payment orders <= month orders", m, "fail", f"{p_orders} > {mr['orders']}")
            continue
        if excluded == 0:
            eq("payment GMV == month GMV (no order excluded this month)", m, p_gmv, gmv)
            eq("payment payments == month payments (no order excluded)", m, p_pay, mr["payment_c"] or 0)
            if not pu:
                eq("payment inferred orders_with_items == month (no order excluded)", m,
                   s(pk, "orders_with_items"), mr["orders_with_items"])
            else:
                lo = s(pk, "orders_with_items")
                hi = lo + s(pu, "orders")
                add("payment inferred orders_with_items bounded by month", m,
                    "bounded" if lo <= mr["orders_with_items"] <= hi else "fail",
                    f"{lo} <= {mr['orders_with_items']} <= {hi}; {len(pu)} cell(s) not identified")
        else:
            add("payment GMV <= month GMV (excluded population not in this extract)", m,
                "bounded" if p_gmv <= gmv else "fail",
                f"{p_gmv} <= {gmv}; {excluded} order(s) with no primary type, gap unattributed")
            add("payment orders_with_items vs month", m, "unsupported",
                f"{excluded} excluded order(s) of unknown basket status")
    return checks
