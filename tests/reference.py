"""Independent reference aggregation for tests.

Deliberately does NOT import portfolio.contract or the JS engine: it reads the extract
CSVs with csv + Decimal and computes each selection from first principles, so a bug in
either production path cannot also hide in the reference."""
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def rows(path: Path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def cents(s):
    return None if s == "" else int(Decimal(s) * 100)


def months_between(all_months, a, b):
    return [m for m in all_months if a <= m <= b]


def monthly(d: Path, a: str, b: str) -> dict:
    rs = [r for r in rows(d / "mart_monthly_performance.csv") if a <= r["month_label"] <= b]
    S = lambda k: sum(int(r[k]) for r in rs)
    C = lambda k: sum(cents(r[k]) or 0 for r in rs)
    out = {"months": len(rs), "orders": S("orders"), "owi": S("orders_with_items"), "gmv_c": C("gmv_brl"),
           "freight_c": C("freight_brl"), "late": S("late_orders"), "delivered": S("delivered_orders"),
           "canceled": S("canceled_orders"), "reviewed": S("reviewed_orders")}
    out["late_pct"] = Decimal(out["late"]) * 100 / Decimal(out["delivered"])
    out["cancel_pct"] = Decimal(out["canceled"]) * 100 / Decimal(out["orders"])
    out["aov_c"] = int((Decimal(out["gmv_c"]) / out["owi"]).quantize(Decimal(1), ROUND_HALF_UP))
    out["naive_late_pct"] = sum(Decimal(r["late_orders"]) * 100 / Decimal(r["delivered_orders"]) for r in rs) / len(rs)
    if "low_score_orders" in rs[0]:
        out["low"] = S("low_score_orders")
        out["review_mean"] = sum(Decimal(r["review_score_sum"]) for r in rs) / S("review_score_n")
        out["delivery_days_mean"] = Decimal(S("delivery_days_sum")) / S("delivery_days_n")
    else:
        # historical: the exported rate x reviewed must round to one integer per month
        low = 0
        for r in rs:
            k = Decimal(r["low_score_rate_pct"]) * int(r["reviewed_orders"]) / 100
            assert abs(k - k.to_integral_value()) < Decimal("1e-6")
            low += int(k.to_integral_value())
        out["low"] = low
        if len(rs) == 1:
            out["review_mean"] = Decimal(rs[0]["avg_review_score"])
            out["delivery_days_mean"] = Decimal(rs[0]["avg_delivery_days"])
    out["low_pct"] = Decimal(out["low"]) * 100 / Decimal(out["reviewed"])
    return out


def states(d: Path, a: str, b: str, chosen=None) -> dict:
    rs = [r for r in rows(d / "mart_state_performance.csv") if a <= r["month_label"] <= b
          and (chosen is None or r["customer_state"] in chosen)]
    by = {}
    for r in rs:
        by.setdefault(r["customer_state"], []).append(r)
    out = {}
    for st, g in by.items():
        gmv = sum(cents(r["gmv_brl"]) or 0 for r in g)
        fr = sum(cents(r["freight_brl"]) or 0 for r in g)
        if "orders_with_items" in g[0]:
            owi = sum(int(r["orders_with_items"]) for r in g)
        else:   # AOV = gmv / owi  ->  owi = gmv / aov, must be an exact-looking integer
            owi = 0
            for r in g:
                q = Decimal(r["gmv_brl"]) / Decimal(r["aov_brl"])
                assert abs(q - q.to_integral_value()) < Decimal("1e-6")
                owi += int(q.to_integral_value())
        out[st] = {"orders": sum(int(r["orders"]) for r in g), "gmv_c": gmv, "freight_c": fr, "owi": owi,
                   "aov_c": int((Decimal(gmv) / owi).quantize(Decimal(1), ROUND_HALF_UP)) if owi else None,
                   "freight_pct": Decimal(fr) * 100 / Decimal(gmv)}
    return out


def categories(d: Path, a: str, b: str) -> dict:
    rs = [r for r in rows(d / "mart_category_performance.csv") if a <= r["month_label"] <= b]
    total = sum(cents(r["gmv_brl"]) for r in rs)
    by = {}
    for r in rs:
        by.setdefault(r["product_category"], []).append(r)
    out = {}
    for c, g in by.items():
        gmv = sum(cents(r["gmv_brl"]) for r in g)
        out[c] = {"gmv_c": gmv, "lines": sum(int(r["order_lines"]) for r in g),
                  "orders": sum(int(r["orders"]) for r in g),
                  "freight_pct": Decimal(sum(cents(r["freight_brl"]) for r in g)) * 100 / Decimal(gmv),
                  "share_pct": Decimal(gmv) * 100 / Decimal(total)}
    return {"total_gmv_c": total, "by": out}


def payments(d: Path, a: str, b: str) -> dict:
    rs = [r for r in rows(d / "mart_payment_performance.csv") if a <= r["month_label"] <= b]
    total = sum(int(r["orders"]) for r in rs)
    by = {}
    for r in rs:
        by.setdefault(r["primary_payment_type"], []).append(r)
    return {"all_orders": total, "by": {k: {
        "orders": sum(int(r["orders"]) for r in g),
        "share_pct": Decimal(sum(int(r["orders"]) for r in g)) * 100 / Decimal(total),
        "payments_c": sum(cents(r["payment_brl"]) or 0 for r in g),
        "installment_pct": Decimal(sum(int(r["installment_orders"]) for r in g)) * 100 / Decimal(sum(int(r["orders"]) for r in g)),
        "gmv_all_null": all(r["gmv_brl"] == "" for r in g)} for k, g in by.items()}}
