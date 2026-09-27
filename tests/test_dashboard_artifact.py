"""The committed dashboard: reproducible, offline, and numerically equal to an
independent reference for real selections (JS engine run in Node on the embedded
payload vs tests/reference.py reading the CSVs with Decimal)."""
import json
import re
import shutil
import subprocess
from decimal import Decimal

import pytest

from portfolio import dashboard, paths

import reference as ref

NODE = shutil.which("node")


@pytest.fixture(scope="module")
def built():
    return dashboard.build()


def _h(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_committed_dashboard_equals_a_fresh_build(built):
    html, data = built       # compare digests: a string diff of an 880 KB page is unreadable and slow
    assert _h(paths.DASHBOARD_HTML.read_text(encoding="utf-8")) == _h(html), "run `make dashboard` and commit"
    assert _h(paths.DASHBOARD_DATA.read_text(encoding="utf-8")) == _h(data)


def test_build_is_deterministic():
    assert dashboard.build() == dashboard.build()


def test_page_is_self_contained_and_offline(built):
    html, _ = built
    assert "default-src 'none'" in html                      # CSP forbids every network request
    assert not re.search(r"""(?:src|href)\s*=\s*["'](?:https?:)?//""", html, re.I)
    assert "<link" not in html.lower()
    assert re.search(r"<script[^>]+src=", html) is None
    assert "__DATA_JSON__" not in html and "/*__APP__*/" not in html


def test_embedded_payload_matches_the_inspectable_json(built):
    html, data = built
    m = re.search(r'<script type="application/json" id="dashboard-data">(.*?)</script>', html, re.S)
    embedded = json.loads(m.group(1).replace("<\\/", "</"))
    assert embedded == json.loads(data)


def test_payload_records_input_hashes(built):
    _, data = built
    inputs = json.loads(data)["inputs"]
    assert "tableau/extracts/mart_monthly_performance.csv" in inputs
    assert "outputs/lead_scores_test.csv" in inputs and "historical/criteo_documented_counts.json" in inputs


# --------------------------------------------------------- engine vs reference
def run_engine(queries):
    if not NODE:
        pytest.skip("node not installed")
    p = subprocess.run([NODE, str(paths.ROOT / "tests" / "js" / "run_engine.js"), str(paths.DASHBOARD_DATA)],
                       input=json.dumps(queries), capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def close(a, b, tol=Decimal("1e-9")):
    return abs(Decimal(str(a)) - Decimal(b)) <= tol


RANGES = [("2017-01", "2018-08"), ("2017-01", "2017-12"), ("2018-03", "2018-03"), ("2018-01", "2018-03")]


@pytest.mark.parametrize("source,d", [("historical", paths.HISTORICAL_EXTRACTS), ("synthetic", paths.SAMPLE_EXTRACTS)])
@pytest.mark.parametrize("a,b", RANGES)
def test_overview_matches_reference(source, d, a, b):
    r = run_engine([{"kind": "overview", "source": source, "from": a, "to": b}])[0]
    x = ref.monthly(d, a, b)
    assert r["orders"]["value"] == x["orders"]
    assert r["gmv"]["value"] == x["gmv_c"]
    assert r["orders_with_items"]["value"] == x["owi"]
    assert r["aov"]["value"] == x["aov_c"]
    assert close(r["late_rate"]["value"], x["late_pct"])
    assert close(r["cancel_rate"]["value"], x["cancel_pct"])
    assert close(r["naive_late_mean"]["value"], x["naive_late_pct"])
    assert r["low"]["value"] == x["low"] and close(r["low_rate"]["value"], x["low_pct"])
    single = a == b
    if source == "synthetic" or single:
        assert close(r["review_score"]["value"], x["review_mean"])
        assert close(r["delivery_days"]["value"], x["delivery_days_mean"])
    else:
        assert r["review_score"]["status"] == "unavailable"
        assert r["delivery_days"]["status"] == "unavailable"
    assert r["active_customers"]["status"] == ("ok" if single else "unavailable")


def test_codex_monthly_figures_reproduce():
    r = run_engine([{"kind": "overview", "source": "historical", "from": "2017-01", "to": "2018-08"}])[0]
    assert (r["orders"]["value"], r["orders_with_items"]["value"], r["gmv"]["value"]) == (99092, 98353, 1578620357)
    assert (r["goods"]["value"], r["freight"]["value"], r["payments"]["value"]) == (1354171278, 224449079, 1594448057)
    assert (r["delivered"]["value"], r["late"]["value"], r["canceled"]["value"]) == (96211, 6532, 580)
    assert f'{r["late_rate"]["value"]:.10f}' == "6.7892444731"
    assert f'{r["naive_late_mean"]["value"]:.6f}' == "5.887424"
    assert r["aov"]["value"] == 16051            # BRL 160.51 (160.5055623113 exact)


@pytest.mark.parametrize("source,d", [("historical", paths.HISTORICAL_EXTRACTS), ("synthetic", paths.SAMPLE_EXTRACTS)])
def test_states_match_reference_and_scope(source, d):
    chosen = ["SP", "RJ", "MG"] if source == "historical" else ["XA", "XB"]
    r = run_engine([{"kind": "states", "source": source, "from": "2017-06", "to": "2018-02", "opts": {"states": chosen}}])[0]
    x = ref.states(d, "2017-06", "2018-02", chosen)
    assert {s["state"] for s in r["list"]} == set(chosen)
    for s in r["list"]:
        e = x[s["state"]]
        assert (s["orders"], s["gmv_c"], s["freight_c"]) == (e["orders"], e["gmv_c"], e["freight_c"])
        assert s["orders_with_items"]["value"] == e["owi"] and s["aov"]["value"] == e["aov_c"]
        assert s["aov"]["status"] == ("inferred" if source == "historical" else "ok")
        assert close(s["freight_share"]["value"], e["freight_pct"])
        # historical has no state-level delivered/late counts: multi-month late rate unavailable
        assert (s["late_rate"]["status"] == "unavailable") == (source == "historical")


@pytest.mark.parametrize("source,d", [("historical", paths.HISTORICAL_EXTRACTS), ("synthetic", paths.SAMPLE_EXTRACTS)])
def test_categories_match_reference_search_and_empty(source, d):
    q = [{"kind": "categories", "source": source, "from": "2017-01", "to": "2018-08", "opts": {"top": 1000}},
         {"kind": "categories", "source": source, "from": "2017-01", "to": "2018-08", "opts": {"search": "zzz-no-match"}}]
    full, none = run_engine(q)
    x = ref.categories(d, "2017-01", "2018-08")
    assert full["total_gmv"]["value"] == x["total_gmv_c"]
    for c in full["shown"]:
        e = x["by"][c["category"]]
        assert (c["gmv_c"], c["lines"], c["orders"]) == (e["gmv_c"], e["lines"], e["orders"])
        assert close(c["freight_share"]["value"], e["freight_pct"]) and close(c["share_of_selected_gmv"]["value"], e["share_pct"])
    # category order counts are NOT additive across categories: the pairs exceed orders with items
    owi = ref.monthly(d, "2017-01", "2018-08")["owi"]
    assert full["category_order_pairs"] > owi
    assert none["no_match"] is True and none["shown"] == []


@pytest.mark.parametrize("source,d", [("historical", paths.HISTORICAL_EXTRACTS), ("synthetic", paths.SAMPLE_EXTRACTS)])
def test_payments_share_keeps_full_denominator_and_null_gmv(source, d):
    q = [{"kind": "payments", "source": source, "from": "2017-01", "to": "2018-08", "opts": {"types": ["credit_card"]}}]
    r = run_engine(q)[0]
    x = ref.payments(d, "2017-01", "2018-08")
    assert [p["ptype"] for p in r["list"]] == ["credit_card"]
    assert r["all_orders"]["value"] == x["all_orders"]                  # filter does not shrink it
    assert close(r["list"][0]["share_of_orders"]["value"], x["by"]["credit_card"]["share_pct"])
    assert r["list"][0]["payments_c"] == x["by"]["credit_card"]["payments_c"]
    if source == "historical":
        nd = run_engine([{"kind": "payments", "source": source, "from": "2018-08", "to": "2018-08",
                          "opts": {"types": ["not_defined"]}}])[0]["list"][0]
        assert nd["gmv_c"] is None and nd["aov"]["status"] == "unavailable"


def test_invalid_range_is_an_error_not_numbers():
    r = run_engine([{"kind": "overview", "source": "historical", "from": "2018-05", "to": "2018-02"},
                    {"kind": "states", "source": "historical", "from": "2018-05", "to": "2018-02"}])
    assert all("error" in x for x in r)


def test_lead_topk_in_page_matches_python():
    from portfolio import leads
    rec = leads.recompute_historical(paths.HISTORICAL_OUTPUTS / "lead_scores_test.csv",
                                     paths.HISTORICAL_OUTPUTS / "lead_scoring_results.csv")
    out = run_engine([{"kind": "topk", "source": "historical", "model": "lr", "k": 265},
                      {"kind": "topk", "source": "historical", "model": "gb", "k": 265}])
    for js, py in zip(out, rec["models"]):
        assert js["deterministic"] == py["top_deterministic_hits"]
        assert abs(js["expected"] - py["top_expected_hits"]) < 1e-12
        assert (js["min"], js["max"], js["tie_block"]) == (py["top_min_hits"], py["top_max_hits"], py["top_tie_block"])


def test_generated_docs_are_current():
    from portfolio.pipeline import generated_docs
    for path, text in generated_docs().items():
        assert path.read_text(encoding="utf-8") == text, f"{path.name} is stale: run `make dashboard`"
