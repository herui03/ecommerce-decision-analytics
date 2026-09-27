"""Real-browser end-to-end check of dashboard/decision-dashboard.html in Chromium.

Exercises every view and filter, compares displayed numbers with the independent
reference (tests/reference.py), checks empty/invalid states, keyboard basics, the table
alternative, narrow-width overflow and console/network silence. Writes evidence:

  docs/evidence/browser/browser-run.json   every check with expected / actual / pass
  docs/evidence/browser/*.jpg              full-page captures of each view
  docs/screenshots/*.png                   the README screenshots

Run: make browser   (or: python -m pytest -m browser -s)
"""
import json
import platform
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest

from portfolio import experiment, paths

import reference as ref

pytestmark = pytest.mark.browser
playwright = pytest.importorskip("playwright.sync_api")

EVID = paths.ROOT / "docs" / "evidence" / "browser"
SHOTS = paths.ROOT / "docs" / "screenshots"
URL = paths.DASHBOARD_HTML.as_uri()
VIEWS = ["overview", "categories", "states", "payments", "leads", "experiment", "definitions", "memo"]


def fmt_int(n):
    return f"{n:,}"


def fmt_cents(c):
    return f"BRL {c // 100:,}.{c % 100:02d}"


def fmt_pct(x, dp=2):
    q = Decimal(1).scaleb(-dp)
    return f"{Decimal(x).quantize(q, ROUND_HALF_UP):,}%"


class Log:
    def __init__(self):
        self.checks = []

    def check(self, name, expected, actual, ok=None):
        passed = (expected == actual) if ok is None else bool(ok)
        self.checks.append({"check": name, "expected": expected, "actual": actual, "pass": passed})
        return passed


@pytest.fixture(scope="module")
def run():
    EVID.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    log = Log()
    events = {"console": [], "pageerror": [], "requests": []}
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
        page = ctx.new_page()
        page.on("console", lambda m: events["console"].append({"type": m.type, "text": m.text}))
        page.on("pageerror", lambda e: events["pageerror"].append(str(e)))
        page.on("request", lambda r: events["requests"].append(r.url))
        page.goto(URL)
        page.wait_for_selector("#panel-overview:not([hidden])")
        yield {"page": page, "ctx": ctx, "browser": browser, "log": log, "events": events,
               "version": browser.version}
        meta = {"url": "dashboard/decision-dashboard.html (file://)", "chromium": browser.version,
                "playwright": __import__("importlib.metadata").metadata.version("playwright"),
                "python": sys.version.split()[0], "platform": platform.platform(),
                "html_sha256": __import__("hashlib").sha256(paths.DASHBOARD_HTML.read_bytes()).hexdigest()}
        out = {"meta": meta, "summary": {"checks": len(log.checks), "passed": sum(c["pass"] for c in log.checks)},
               "checks": log.checks, "console": events["console"], "requests_total": len(events["requests"])}
        (EVID / "browser-run.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
        browser.close()


def tab(page, view):
    page.click(f"#tab-{view}")
    page.wait_for_selector(f"#panel-{view}:not([hidden])")


def text(page, sel):
    return page.locator(sel).first.inner_text()


def shot(page, name, full=True, jpeg=True):
    path = EVID / (name + (".jpg" if jpeg else ".png"))
    page.screenshot(path=str(path), full_page=full, type="jpeg" if jpeg else "png", **({"quality": 70} if jpeg else {}))


def test_01_load_and_every_view_renders(run):
    page, log = run["page"], run["log"]
    assert log.check("CSP forbids network access", True,
                     "default-src 'none'" in page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute("content"))
    for src in ("historical", "synthetic"):
        page.check(f'input[name="source"][value="{src}"]')
        for v in VIEWS:
            tab(page, v)
            ok = page.locator(f"#panel-{v} > *").count() > 0
            assert log.check(f"{src}/{v}: panel renders", True, ok)
            if src == "historical" or v not in ("definitions", "memo"):   # those two are source-independent
                shot(page, f"{src}-{v}")
    page.check('input[name="source"][value="historical"]')
    tab(page, "overview")


def test_02_overview_numbers_and_month_filter(run):
    page, log = run["page"], run["log"]
    full = ref.monthly(paths.HISTORICAL_EXTRACTS, "2017-01", "2018-08")
    a = text(page, '[data-testid="overview-answer"]')
    assert log.check("full window orders shown", True, fmt_int(full["orders"]) + " orders" in a)
    assert log.check("full window GMV shown (integer cents)", True, fmt_cents(full["gmv_c"]) in a)
    assert log.check("weighted late rate tile", fmt_pct(full["late_pct"]), text(page, '[data-metric="late"] .value'))
    callout = text(page, '[data-testid="weighted-callout"]')
    assert log.check("weighted vs naive counterexample shown", True,
                     fmt_pct(full["late_pct"], 4) in callout and fmt_pct(full["naive_late_pct"], 4) in callout)
    page.select_option("#f-from", "2018-01")
    page.select_option("#f-to", "2018-03")
    q = ref.monthly(paths.HISTORICAL_EXTRACTS, "2018-01", "2018-03")
    a2 = text(page, '[data-testid="overview-answer"]')
    assert log.check("month filter changes the numbers", True, a2 != a)
    assert log.check("2018-01..03 orders equal reference", True, fmt_int(q["orders"]) + " orders" in a2)
    assert log.check("2018-01..03 late tile equals reference", fmt_pct(q["late_pct"]), text(page, '[data-metric="late"] .value'))
    assert log.check("2018-01..03 AOV tile equals reference", fmt_cents(q["aov_c"]).replace(" ", ""),
                     "".join(text(page, '[data-metric="aov"] .value').split()))
    assert log.check("multi-month review score is UNAVAILABLE (historical)", True,
                     "Unavailable" in text(page, "#panel-overview table"))
    page.select_option("#f-from", "2018-03")
    page.select_option("#f-to", "2018-03")
    s = ref.monthly(paths.HISTORICAL_EXTRACTS, "2018-03", "2018-03")
    table = text(page, "#panel-overview table")
    exp_rv = f'{Decimal(s["review_mean"]).quantize(Decimal("0.001"), ROUND_HALF_UP)}'
    assert log.check("single month: review score available and equal to extract", True, exp_rv in table)
    assert log.check("single month: active customers available", True,
                     text(page, '[data-metric="active"] .value') != "Unavailable")
    page.select_option("#f-from", "2018-05")
    page.select_option("#f-to", "2018-02")
    alert = page.locator('#panel-overview [role="alert"]')
    assert log.check("reversed range shows an error, not numbers", True,
                     alert.count() == 1 and "after the end month" in alert.inner_text())
    shot(page, "state-invalid-range", full=False)
    page.click("text=Full window")
    assert log.check("preset restores the full window", True,
                     fmt_int(full["orders"]) + " orders" in text(page, '[data-testid="overview-answer"]'))


def test_03_table_alternative_and_keyboard(run):
    page, log = run["page"], run["log"]
    card = page.locator('[data-chart="ov-gmv"]')
    card.locator("button", has_text="Show table").click()
    btn = card.locator("button").first
    assert log.check("table toggle sets aria-pressed", "true", btn.get_attribute("aria-pressed"))
    assert log.check("table alternative has one row per month", 20, card.locator("tbody tr").count())
    btn.click()
    assert log.check("toggle returns to the chart", 1, card.locator("svg").count())
    svg = card.locator("svg")
    svg.focus()
    page.keyboard.press("End")
    tip = card.locator(".tooltip")
    assert log.check("keyboard: End shows the last month's tooltip", True,
                     tip.is_visible() and "2018-08" in tip.inner_text())
    page.focus("#tab-overview")
    page.keyboard.press("ArrowRight")
    assert log.check("keyboard: ArrowRight moves to the next tab", "true",
                     page.get_attribute("#tab-categories", "aria-selected"))
    assert log.check("keyboard: focus follows the selected tab", "tab-categories",
                     page.evaluate("document.activeElement.id"))


def test_04_categories_search_and_empty(run):
    page, log = run["page"], run["log"]
    tab(page, "categories")
    page.fill("#f-search", "furn")
    rows = page.locator("#panel-categories h3 + .table-wrap tbody tr")
    names = [rows.nth(i).locator("th").inner_text() for i in range(rows.count() - 1)]
    assert log.check("search keeps only matching categories", True, names and all("furn" in n for n in names))
    x = ref.categories(paths.HISTORICAL_EXTRACTS, "2017-01", "2018-08")
    top = max((c for c in x["by"] if "furn" in c), key=lambda c: x["by"][c]["gmv_c"])
    assert log.check("largest matching category and GMV equal reference", True,
                     top in text(page, '[data-testid="category-answer"]') and fmt_cents(x["by"][top]["gmv_c"]) in text(page, '[data-testid="category-answer"]'))
    page.fill("#f-search", "zzzz")
    assert log.check("no-match search shows an empty state", 1, page.locator('[data-testid="category-empty"]').count())
    shot(page, "state-empty-category", full=False)
    page.fill("#f-search", "furn")          # leave a category filter set for the scope check


def test_05_states_scope_selection_and_unavailable(run):
    page, log = run["page"], run["log"]
    tab(page, "states")
    all_states = ref.states(paths.HISTORICAL_EXTRACTS, "2017-01", "2018-08")
    total = sum(v["orders"] for v in all_states.values())
    a = text(page, '[data-testid="state-answer"]')
    assert log.check("category search does not leak into the States view", True, fmt_int(total) + " orders" in a)
    assert log.check("multi-month state late rate is UNAVAILABLE (no counts in extract)", 1,
                     page.locator('[data-testid="state-late-unavailable"]').count())
    page.click("#filters button:has-text('None')")
    assert log.check("no state selected shows an empty state", 1, page.locator('[data-testid="state-empty"]').count())
    page.check("#filters input[value='SP']")
    sp = all_states["SP"]
    a = text(page, '[data-testid="state-answer"]')
    assert log.check("SP only: orders and GMV equal reference", True,
                     fmt_int(sp["orders"]) + " orders" in a and fmt_cents(sp["gmv_c"]) in a)
    page.select_option("#f-from", "2018-03")
    page.select_option("#f-to", "2018-03")
    assert log.check("single month: state late-rate chart appears", 1, page.locator('[data-chart="st-late"]').count())
    page.click("#filters button:has-text('All')")
    page.click("text=Full window")


def test_06_payments_filter_keeps_denominator(run):
    page, log = run["page"], run["log"]
    tab(page, "payments")
    x = ref.payments(paths.HISTORICAL_EXTRACTS, "2017-01", "2018-08")
    for t in ("boleto", "debit_card", "not_defined", "voucher"):
        page.uncheck(f"#filters input[value='{t}']")
    rows = page.locator("#panel-payments h3 + .table-wrap tbody tr")
    assert log.check("instrument filter leaves one row", 1, rows.count())
    assert log.check("credit_card share still divides by all instruments", fmt_pct(x["by"]["credit_card"]["share_pct"]),
                     rows.first.locator("td").nth(1).inner_text())
    assert log.check("payments view states what payment_brl means", True,
                     "not the amount paid with that instrument" in text(page, "#panel-payments .callout"))
    page.click("#filters button:has-text('All')")
    nd = page.locator("#panel-payments h3 + .table-wrap tbody tr", has_text="not_defined")
    assert log.check("not_defined: NULL GMV is shown as missing, not BRL 0.00", True,
                     nd.locator("td").nth(3).inner_text() == "—" and "unavailable" in nd.locator("td").nth(4).inner_text())


def test_07_leads_ties_and_slider(run):
    page, log = run["page"], run["log"]
    tab(page, "leads")
    from portfolio import leads
    rec = leads.recompute_historical(paths.HISTORICAL_OUTPUTS / "lead_scores_test.csv",
                                     paths.HISTORICAL_OUTPUTS / "lead_scoring_results.csv")
    lr, gb = rec["models"]
    assert log.check("LR top-265 tie-aware expected hits", f'{lr["top_expected_hits"]:.2f}',
                     text(page, '[data-metric="topk-hits"] .value'))
    assert log.check("maturity callout states usable-from dates", True,
                     "2018-04-02" in text(page, '[data-testid="lead-maturity"]') and "2018-04-01" in text(page, '[data-testid="lead-maturity"]'))
    assert log.check("claim box says ranking is not incremental wins", True,
                     "not incremental wins" in text(page, '[data-testid="topk-claim"]'))
    page.select_option("#f-model", "gb")
    assert log.check("GB top-265 tie-aware expected hits", f'{gb["top_expected_hits"]:.2f}',
                     text(page, '[data-metric="topk-hits"] .value'))
    before = text(page, '[data-metric="topk-hits"] .value')
    page.locator("#f-k").fill("20")
    assert log.check("slider changes k and the hit count", True, text(page, '[data-metric="topk-hits"] .value') != before)
    page.locator("#f-k").fill("10")
    page.select_option("#f-model", "lr")


def test_08_experiment_and_hypothetical_calculator(run):
    page, log = run["page"], run["log"]
    tab(page, "experiment")
    doc = json.loads((paths.HISTORICAL_DIR / "criteo_documented_counts.json").read_text())
    c = doc["counts"]
    a = experiment.analyse(experiment.ArmCounts(c["n_t"], c["y_t"], c["n_c"], c["y_c"], c["n_exposed"],
                                                doc["inferred"]["y_exposed"]["value"]))
    assert log.check("ITT tile equals recomputation", f'+{100 * a["itt"]["diff"]:.4f} pp',
                     text(page, '[data-metric="itt"] .value'))
    def set_input(sel, value):          # the calculator re-renders on every change event
        page.fill(sel, value)
        page.locator(sel).dispatch_event("change")
    set_input("#be-cost", "abc")
    set_input("#be-value", "5")
    assert log.check("invalid cost input shows an error", True,
                     "Cost must be a number" in text(page, '[data-testid="breakeven-out"]'))
    set_input("#be-cost", "2.5")
    net = 1000 * a["itt"]["diff"] * 5 - 2.5
    out = text(page, '[data-testid="breakeven-out"]')
    assert log.check("hypothetical net value per 1,000 assigned", True, f"{net:,.3f}" in out)
    shot(page, "experiment-breakeven", full=False)


def test_09_synthetic_source_exact_means(run):
    page, log = run["page"], run["log"]
    page.check('input[name="source"][value="synthetic"]')
    tab(page, "overview")
    page.click("text=Full window")
    s = ref.monthly(paths.SAMPLE_EXTRACTS, "2017-01", "2018-08")
    assert log.check("synthetic banner is shown", True, "not real data" in text(page, "#source-banner"))
    assert log.check("synthetic orders equal reference", True,
                     fmt_int(s["orders"]) + " orders" in text(page, '[data-testid="overview-answer"]'))
    rv = f'{Decimal(s["review_mean"]).quantize(Decimal("0.001"), ROUND_HALF_UP)}'
    assert log.check("synthetic multi-month review mean = sum / valid count", True,
                     rv in text(page, "#panel-overview table"))
    page.check('input[name="source"][value="historical"]')


def test_10_definitions_and_memo(run):
    page, log = run["page"], run["log"]
    tab(page, "definitions")
    page.fill("#f-defs", "CACE")
    n = page.locator("#panel-definitions table").first.locator("tbody tr").count()
    assert log.check("metric search filters the dictionary", True, 0 < n < 5)
    tab(page, "memo")
    m = text(page, '[data-testid="memo"]')
    full = ref.monthly(paths.HISTORICAL_EXTRACTS, "2017-01", "2018-08")
    assert log.check("memo numbers come from the historical inputs", True,
                     fmt_int(full["orders"]) + " orders" in m and fmt_pct(full["late_pct"]) in m)
    assert log.check("memo frames recommendations as tests", True, "not promised gains" in m)


def test_11_narrow_width_and_dark_mode(run):
    page, log, ctx = run["page"], run["log"], run["ctx"]
    mob = ctx.new_page()
    mob.set_viewport_size({"width": 375, "height": 812})
    mob.goto(URL)
    mob.wait_for_selector("#panel-overview:not([hidden])")
    for v in VIEWS:
        mob.click(f"#tab-{v}")
        mob.wait_for_timeout(120)
        over = mob.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert log.check(f"375px: no horizontal page overflow on {v}", 0, max(0, over))
    mob.click("#tab-overview")
    mob.evaluate("window.scrollTo(0, 0)")
    mob.screenshot(path=str(SHOTS / "mobile-overview.png"), full_page=False)
    mob.screenshot(path=str(EVID / "mobile-overview-full.jpg"), full_page=True, type="jpeg", quality=70)
    mob.click("#tab-leads")
    mob.screenshot(path=str(EVID / "mobile-leads-full.jpg"), full_page=True, type="jpeg", quality=70)
    mob.close()
    page.click("#tab-overview")
    page.click("#theme-toggle")      # auto -> light
    page.click("#theme-toggle")      # light -> dark
    assert log.check("theme toggle applies dark mode", "dark", page.get_attribute("html", "data-theme"))
    page.wait_for_timeout(150)
    page.screenshot(path=str(SHOTS / "overview-dark.png"), full_page=False)
    page.click("#theme-toggle")      # dark -> auto


def test_12_readme_screenshots(run):
    page = run["page"]
    page.check('input[name="source"][value="historical"]')
    for v, name in (("overview", "overview"), ("categories", "categories"), ("leads", "lead-scoring"),
                    ("experiment", "experiment"), ("memo", "decision-memo")):
        tab(page, v)
        page.click("text=Full window") if v in ("overview", "categories") else None
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def test_99_every_check_passed(run):
    log, events = run["log"], run["events"]
    non_file = [u for u in events["requests"] if not u.startswith("file:")]
    errors = [c for c in events["console"] if c["type"] in ("error", "warning")]
    log.check("no console errors or warnings in the whole run", [], errors)
    log.check("no uncaught page errors", [], events["pageerror"])
    log.check("no network request other than the file itself", [], non_file)
    failed = [c for c in log.checks if not c["pass"]]
    assert not failed, json.dumps(failed, indent=1)
