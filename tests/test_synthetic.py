"""Synthetic generator: deterministic bytes and the planted edge cases exist."""
import csv
from collections import Counter

from portfolio import synthetic


def test_generation_is_byte_identical(tmp_path):
    a = synthetic.generate_olist(tmp_path / "a")
    b = synthetic.generate_olist(tmp_path / "b")
    assert a.files == b.files
    for name in a.files:
        assert synthetic.sha256(tmp_path / "a" / name) == synthetic.sha256(tmp_path / "b" / name)


def test_edge_cases_are_planted(tmp_path):
    synthetic.generate_olist(tmp_path)
    rd = lambda n: list(csv.DictReader(open(tmp_path / n, newline="")))
    orders, items, pays = rd("olist_orders_dataset.csv"), rd("olist_order_items_dataset.csv"), rd("olist_order_payments_dataset.csv")
    with_items = {r["order_id"] for r in items}
    paid = {r["order_id"] for r in pays}
    assert any(o["order_id"] not in with_items for o in orders)                    # item-less orders
    unpaid = [o for o in orders if o["order_id"] not in paid]
    assert len(unpaid) == 2 and all(o["order_status"] == "delivered" for o in unpaid)
    months = Counter(o["order_purchase_timestamp"][:7] for o in orders)
    assert "2016-11" not in months and months["2018-10"] > 0                        # pilot gap, tail
    assert all(o["order_status"] == "canceled" for o in orders if o["order_purchase_timestamp"][:7] == "2018-10")
    per_order = Counter(r["order_id"] for r in items)
    assert max(per_order.values()) >= 3
    assert any(r["payment_type"] == "not_defined" for r in pays)
    assert any(o["order_status"] == "canceled" and o["order_delivered_customer_date"] for o in orders)
    assert any(o["order_status"] == "delivered" and not o["order_delivered_customer_date"] for o in orders)
    split = Counter(r["order_id"] for r in pays)
    assert any(v >= 2 for v in split.values())
    reviews = rd("olist_order_reviews_dataset.csv")
    assert any(v >= 2 for v in Counter(r["order_id"] for r in reviews).values())
    assert any(v >= 2 for v in Counter(r["review_id"] for r in reviews).values())
    leads = rd("olist_marketing_qualified_leads_dataset.csv")
    assert any(r["origin"] == "" for r in leads)
    customers = rd("olist_customers_dataset.csv")
    assert any(v >= 2 for v in Counter(r["customer_unique_id"] for r in customers).values())
    assert all(r["customer_state"].startswith("X") for r in customers)              # fictional regions


def test_criteo_truth_is_reported(tmp_path):
    t = synthetic.generate_criteo(tmp_path / "c.csv", n=5000)
    assert t["rows"] == 5000 and 0 < t["true_itt_pp"] < t["true_cace_pp"]
