"""Single source of truth for metric definitions, provenance badges and the data-source
manifest. The dashboard embeds these lists and docs/metric-dictionary.md and
docs/source-manifest.md are generated from them (`python -m portfolio.pipeline docs`),
so the page and the documents cannot drift apart. A test checks the docs are current."""

BADGES = [
    {"id": "historical", "label": "HISTORICAL", "icon": "◷",
     "meaning": "Committed output of the prior full-data run (2026-07-16). Not re-executed in this build."},
    {"id": "recomputed", "label": "RECOMPUTED", "icon": "↻",
     "meaning": "Computed in this build (or in your browser) from committed historical inputs."},
    {"id": "synthetic", "label": "SYNTHETIC", "icon": "◇",
     "meaning": "From the deterministic generated sample. Demonstrates mechanics; says nothing about the real marketplace or ad experiment."},
    {"id": "inferred", "label": "INFERRED", "icon": "≈",
     "meaning": "An integer not stored in the extract, recovered only because exactly one value reproduces "
                "an exported ratio at its printed precision. Never an estimate."},
    {"id": "unavailable", "label": "UNAVAILABLE", "icon": "∅",
     "meaning": "The inputs cannot support this number for the current selection. Shown as such, never estimated."},
    {"id": "hypothetical", "label": "HYPOTHETICAL", "icon": "?",
     "meaning": "Depends on assumptions you type in (cost, value). Neither dataset contains costs or margins."},
    {"id": "retrospective", "label": "RETROSPECTIVE", "icon": "↺",
     "meaning": "Evaluated after the fact on a cohort split whose training labels were not available at the cut; "
                "not a deployable, prospective result."},
]

# grain: where the number is defined. combine: how the dashboard aggregates a selection.
METRICS = [
    # ---------------------------------------------------------------- Olist, order grain
    {"id": "orders", "name": "Orders", "views": "Overview, States, Payments",
     "definition": "Orders purchased in the month (analysis window 2017-01 to 2018-08).",
     "formula": "count(*) over fct_orders", "numerator": "orders", "denominator": "-",
     "grain": "month (and month x state, month x primary payment type)",
     "combine": "Sum across months. Sum across states (one customer state per order). Sum across primary "
                "payment types (one exclusive primary type per order; orders with no payment record are "
                "excluded from the payment extract)."},
    {"id": "gmv", "name": "GMV (item value incl. freight)", "views": "all marketplace views",
     "definition": "Sum of item price + item freight over order lines, in BRL. Orders with no items "
                   "contribute nothing (NULL, not zero). Not the same as payments.",
     "formula": "sum(price + freight_value), integer cents", "numerator": "cents", "denominator": "-",
     "grain": "every extract", "combine": "Sum of integer cents; exact in every view."},
    {"id": "payments", "name": "Payments", "views": "Overview, Payments",
     "definition": "Sum of payment_value over all payment rows of the orders in scope. In the Payments view "
                   "it is the WHOLE payment total of orders whose primary instrument is X - including money "
                   "paid with other instruments - not the amount paid with X.",
     "formula": "sum(payment_total_brl)", "numerator": "cents", "denominator": "-",
     "grain": "month; month x primary payment type", "combine": "Sum of integer cents."},
    {"id": "aov", "name": "Average order value (AOV)", "views": "Overview, States, Payments",
     "definition": "GMV divided by orders that have at least one item.",
     "formula": "sum(GMV) / sum(orders_with_items)", "numerator": "GMV cents",
     "denominator": "orders with >= 1 item (not all orders)",
     "grain": "any selection",
     "combine": "Re-derived from summed numerator and denominator. Historical state/payment extracts do not "
                "store orders_with_items: it is INFERRED per cell only when a unique integer reproduces the "
                "exported AOV; any unidentified cell makes the selection's AOV UNAVAILABLE."},
    {"id": "cancel_rate", "name": "Cancellation rate", "views": "Overview",
     "definition": "Cancelled orders as a share of all orders.",
     "formula": "canceled / orders", "numerator": "orders with status 'canceled'",
     "denominator": "all orders", "grain": "month", "combine": "Sum numerator and denominator, then divide."},
    {"id": "late_rate", "name": "Late-delivery rate (weighted)", "views": "Overview, States",
     "definition": "Delivered orders whose delivery calendar day is after the estimated calendar day, as a "
                   "share of delivered orders. Delivered on the estimated day counts as on time. A "
                   "delivered-status order without a delivery timestamp stays in the denominator and is "
                   "never counted late.",
     "formula": "late / delivered", "numerator": "late delivered orders",
     "denominator": "orders with status 'delivered'", "grain": "month; month x state (synthetic only)",
     "combine": "Sum late and delivered, then divide. Historical state extract has no delivered/late "
                "counts: a multi-cell state late rate is UNAVAILABLE rather than an average of percentages."},
    {"id": "naive_late_mean", "name": "Mean of monthly late rates (counterexample)", "views": "Overview",
     "definition": "Unweighted average of the monthly rates. Shown ONLY to demonstrate why it is wrong: it "
                   "gives an 800-order month the same weight as a 7,500-order month.",
     "formula": "mean_m(late_m / delivered_m)", "numerator": "-", "denominator": "-",
     "grain": "month", "combine": "Not a metric. Never used for decisions."},
    {"id": "low_review_rate", "name": "Low-review rate", "views": "Overview",
     "definition": "Reviewed orders whose latest review score is 1 or 2, as a share of reviewed orders.",
     "formula": "low_score_orders / reviewed_orders", "numerator": "latest review score <= 2",
     "denominator": "orders with >= 1 review",
     "grain": "month", "combine": "Sum then divide. Historical numerator is INFERRED per month (unique integer "
                                  "reproducing the exported rate); all 20 months were identified."},
    {"id": "review_score", "name": "Average review score", "views": "Overview, States",
     "definition": "Mean, over reviewed orders, of each order's mean review score (1-5).",
     "formula": "sum(order mean score) / count(reviewed orders)", "numerator": "sum of order means",
     "denominator": "orders with a non-NULL mean score (valid-value count)", "grain": "month; month x state",
     "combine": "Exact only with the valid-value count and sum (synthetic extracts). Historical extracts: "
                "single cell only; a multi-cell value is UNAVAILABLE."},
    {"id": "delivery_days", "name": "Average delivery days", "views": "Overview, States",
     "definition": "Mean calendar days from purchase to customer delivery, over delivered orders that have a "
                   "delivery timestamp.",
     "formula": "sum(days) / count(non-NULL days) among delivered", "numerator": "sum of days",
     "denominator": "delivered orders WITH a delivery timestamp - not all delivered orders",
     "grain": "month; month x state", "combine": "As average review score."},
    {"id": "items_per_order", "name": "Items per order", "views": "Overview",
     "definition": "Mean number of order lines per order that has items.",
     "formula": "sum(item_count) / count(item_count)", "numerator": "order lines",
     "denominator": "orders with items (valid-value count)", "grain": "month",
     "combine": "As average review score."},
    {"id": "installments", "name": "Average installments", "views": "Overview, Payments",
     "definition": "Mean of each order's maximum installment count, over orders with a payment record.",
     "formula": "sum(max_installments) / count(max_installments)", "numerator": "sum of installments",
     "denominator": "orders with a payment record (valid-value count)", "grain": "month; month x type",
     "combine": "As average review score."},
    {"id": "installment_rate", "name": "Installment rate", "views": "Payments",
     "definition": "Orders paid in more than one installment, as a share of orders in the group.",
     "formula": "installment_orders / orders", "numerator": "orders with max_installments > 1",
     "denominator": "orders in the primary-type group", "grain": "month x primary type",
     "combine": "Sum then divide."},
    {"id": "share_of_orders", "name": "Share of orders by primary instrument", "views": "Payments",
     "definition": "Orders whose primary instrument (the one carrying the most money on the order) is X, as a "
                   "share of all orders with a primary instrument in the selected months. The payment-type "
                   "filter does not change the denominator.",
     "formula": "orders_X / orders_all_types", "numerator": "orders with primary type X",
     "denominator": "orders with any primary type (excludes orders with no payment record)",
     "grain": "month x primary type", "combine": "Sum then divide."},
    {"id": "active_customers", "name": "Active customers", "views": "Overview, States (single cell)",
     "definition": "Distinct people (customer_unique_id) with an order in the cell.",
     "formula": "count(distinct customer_unique_id)", "numerator": "-", "denominator": "-",
     "grain": "month; month x state; month x category",
     "combine": "NOT additive: a person active in two months would be counted twice. Shown for a single "
                "cell only; the sum of monthly values is labelled customer-months."},
    # --------------------------------------------------------------- Olist, item grain
    {"id": "freight_share", "name": "Freight share of GMV", "views": "Overview, Categories, States",
     "definition": "Freight value as a share of item GMV. A price-composition measure - NOT margin, cost to "
                   "the marketplace, or a saving.",
     "formula": "sum(freight) / sum(GMV)", "numerator": "freight cents", "denominator": "GMV cents",
     "grain": "any selection", "combine": "Sum then divide."},
    {"id": "category_orders", "name": "Orders containing the category", "views": "Categories",
     "definition": "Distinct orders with at least one line in the category.",
     "formula": "count(distinct order_id) per month x category", "numerator": "-", "denominator": "-",
     "grain": "month x category",
     "combine": "For ONE category, adds across months (an order belongs to one month). NOT additive across "
                "categories: an order spanning two categories is counted in both. The all-category sum is "
                "labelled category-order pairs."},
    {"id": "avg_line_value", "name": "Average line value", "views": "Categories",
     "definition": "GMV per order line in the category.", "formula": "sum(GMV) / sum(order lines)",
     "numerator": "GMV cents", "denominator": "order lines", "grain": "month x category",
     "combine": "Sum then divide."},
    {"id": "share_of_selected_gmv", "name": "Share of selected GMV", "views": "Categories",
     "definition": "Category GMV as a share of GMV across all categories in the selected months (the search "
                   "box does not change the denominator).",
     "formula": "GMV_category / GMV_all_categories", "numerator": "category GMV cents",
     "denominator": "all-category GMV cents in the selected months", "grain": "any selection",
     "combine": "Sum then divide."},
    # ------------------------------------------------------------------- lead scoring
    {"id": "is_won_90d", "name": "Label: won within 90 days", "views": "Lead scoring",
     "definition": "A closed deal dated 0 to 90 days (inclusive) after first contact. Never-won leads and "
                   "negative lags are negatives.",
     "formula": "0 <= won_date - first_contact_date <= 90", "numerator": "-", "denominator": "-",
     "grain": "lead", "combine": "Counts sum."},
    {"id": "label_maturity", "name": "Label maturity / as-of", "views": "Lead scoring",
     "definition": "A lead's 90-day label is complete on first_contact + 91 days. A model deployed at as-of "
                   "date T may train only on leads contacted on or before T - 91 days (purge gap 91 days).",
     "formula": "train_end = as_of - 91 days", "numerator": "-", "denominator": "-", "grain": "design",
     "combine": "-"},
    {"id": "page_volume_prior", "name": "Point-in-time landing-page volume", "views": "Lead scoring",
     "definition": "Leads on the same landing page with a strictly earlier contact date. Replaces the legacy "
                   "full-dataset count, which included future leads.",
     "formula": "count(earlier leads on page)", "numerator": "-", "denominator": "-", "grain": "lead",
     "combine": "-"},
    {"id": "top_k_hits", "name": "Top-k hits (tie-aware)", "views": "Lead scoring",
     "definition": "Positives among the k highest-scored leads of a held-out cohort. Deterministic order: "
                   "score descending, then lead id. Where the k-th score is tied, the expected value over all "
                   "orderings of the tied block is shown with its min-max range. Retrospective ranking "
                   "quality - NOT incremental wins.",
     "formula": "hits above cut + positives in tied block x slots left / block size",
     "numerator": "positives", "denominator": "k", "grain": "score cohort", "combine": "-"},
    {"id": "auc", "name": "ROC AUC / PR-AUC / Brier", "views": "Lead scoring",
     "definition": "Ranking (AUC, average precision) and calibration (Brier: mean squared error of the "
                   "predicted probability) on the held-out cohort.",
     "formula": "sklearn roc_auc_score / average_precision_score / brier_score_loss",
     "numerator": "-", "denominator": "-", "grain": "score cohort", "combine": "-"},
    # --------------------------------------------------------------------- experiment
    {"id": "itt", "name": "ITT effect (intention to treat)", "views": "Experiment",
     "definition": "Conversion rate of users ASSIGNED to treatment minus that of users assigned to control. "
                   "Identified by randomisation alone; the effect of the decision a marketer can take.",
     "formula": "y_t/n_t - y_c/n_c, Wald 95% CI", "numerator": "conversions", "denominator": "assigned users",
     "grain": "experiment arm", "combine": "-"},
    {"id": "relative_lift", "name": "Relative lift", "views": "Experiment",
     "definition": "ITT as a share of the control rate, with a delta-method (log ratio) 95% CI.",
     "formula": "p_t/p_c - 1", "numerator": "-", "denominator": "-", "grain": "experiment arm", "combine": "-"},
    {"id": "cace", "name": "CACE (effect on compliers)", "views": "Experiment",
     "definition": "ITT divided by the exposure rate in the treated arm. Needs the exclusion restriction and "
                   "describes only compliers (users who would be exposed) - a small, systematically different "
                   "group. Not 'the true effect'.",
     "formula": "ITT / P(exposed | treated), delta-method 95% CI", "numerator": "ITT",
     "denominator": "compliance", "grain": "experiment", "combine": "-"},
    {"id": "naive", "name": "Exposed vs control (naive)", "views": "Experiment",
     "definition": "Conversion of exposed users vs control. NOT an effect estimate: exposure is selected by "
                   "user behaviour after assignment.",
     "formula": "y_exposed/n_exposed - y_c/n_c", "numerator": "-", "denominator": "-",
     "grain": "experiment", "combine": "-"},
    {"id": "mde", "name": "Minimum detectable effect", "views": "Experiment",
     "definition": "Smallest absolute difference the design detects with the stated power at alpha 0.05. "
                   "Statistical significance is not practical importance.",
     "formula": "Cohen's h inversion (as the prior run)", "numerator": "-", "denominator": "-",
     "grain": "design", "combine": "-"},
    {"id": "breakeven", "name": "Break-even value per incremental conversion", "views": "Experiment",
     "definition": "HYPOTHETICAL. Cost per 1,000 assigned users (or per 1,000 exposed users x compliance) "
                   "divided by incremental conversions per 1,000 assigned users. The datasets contain no "
                   "cost or margin.",
     "formula": "cost_per_1000_assigned / (1000 x ITT)", "numerator": "your cost input",
     "denominator": "incremental conversions per 1,000", "grain": "experiment", "combine": "-"},
]

SOURCES = [
    {"id": "olist", "name": "Brazilian E-Commerce Public Dataset by Olist",
     "publisher": "Olist (via Kaggle: olistbr/brazilian-ecommerce)",
     "url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
     "license": "CC BY-NC-SA 4.0 (as recorded by the prior run; not re-checked online from this environment)",
     "rows_documented": "99,441 orders (prior run, 2026-07-16)",
     "in_repo": "Derived aggregates only: tableau/extracts/*.csv (month-level metric extracts) and the "
                "dashboard's embedded copy of them. Raw files are not committed.",
     "obligations": "Attribution to Olist; non-commercial use; derived data shared under the same licence; "
                    "indicate changes (aggregation, recomputation)."},
    {"id": "olist_funnel", "name": "Marketing Funnel by Olist",
     "publisher": "Olist (via Kaggle: olistbr/marketing-funnel-olist)",
     "url": "https://www.kaggle.com/datasets/olistbr/marketing-funnel-olist",
     "license": "CC BY-NC-SA 4.0 (as recorded by the prior run; not re-checked online from this environment)",
     "rows_documented": "8,000 leads, 842 closed deals (prior run)",
     "in_repo": "Derived row-level outputs: outputs/lead_scores_test.csv (2,655 held-out leads: id, date, "
                "channel, label, model scores) and outputs/lead_scoring_results.csv; the dashboard embeds the "
                "scores and labels (no ids).",
     "obligations": "As above (BY-NC-SA). The derived lead-level file carries the source's hashed lead ids."},
    {"id": "criteo", "name": "Criteo Uplift Modeling Dataset v2.1",
     "publisher": "Criteo AI Lab (the prior run used the Kaggle mirror arashnic/uplift-modeling)",
     "url": "https://www.kaggle.com/datasets/arashnic/uplift-modeling",
     "license": "Recorded by the prior run as CC0-1.0 (Kaggle mirror listing). The original publisher's terms "
                "could not be checked from this environment (network policy) - verify before any reuse.",
     "rows_documented": "13,979,592 rows (prior run)",
     "in_repo": "Six aggregate counts transcribed from the verification log "
                "(historical/criteo_documented_counts.json); one inferred. No rows.",
     "obligations": "Cite Criteo AI Lab; follow the publisher's terms."},
    {"id": "synthetic", "name": "Synthetic sample (this repository)",
     "publisher": "Generated by python/portfolio/synthetic.py, seed 20260926",
     "url": "-", "license": "MIT, with the code (no third-party data)",
     "rows_documented": "12,443 orders, 4,980 leads, 240,000 RCT rows (see sample/manifest.json)",
     "in_repo": "Aggregated outputs in sample/; raw CSVs regenerate into data/sample/ (gitignored).",
     "obligations": "None. Must never be presented as real data."},
]


def metric_dictionary_markdown() -> str:
    lines = ["# Metric dictionary and grain contract", "",
             "_Generated from `python/portfolio/definitions.py` by `python -m portfolio.pipeline docs`. "
             "Do not edit by hand; the dashboard embeds the same list._", "",
             "## Provenance badges", "", "| Badge | Meaning |", "|---|---|"]
    for b in BADGES:
        lines.append(f"| {b['icon']} {b['label']} | {b['meaning']} |")
    lines += ["", "## Grain of each extract", "",
              "| Extract | Grain | Built on | Joint filters it supports |", "|---|---|---|---|",
              "| monthly | month | fct_orders (order grain), analysis window | month |",
              "| category | month x product category | fct_order_items (item grain) | month, category |",
              "| state | month x customer state | fct_orders | month, state |",
              "| payment | month x primary payment type | fct_orders, orders with a payment record | month, type |",
              "", "No extract has a joint month x state x category grain, so the dashboard never "
              "filters one view by another view's dimension. Each filter shows the views it applies to.",
              "", "## Metrics", ""]
    for m in METRICS:
        lines += [f"### {m['name']} (`{m['id']}`)", "",
                  f"- **Views:** {m['views']}",
                  f"- **Definition:** {m['definition']}",
                  f"- **Formula:** `{m['formula']}`",
                  f"- **Numerator / denominator:** {m['numerator']} / {m['denominator']}",
                  f"- **Grain:** {m['grain']}",
                  f"- **Combining a selection:** {m['combine']}", ""]
    return "\n".join(lines).rstrip() + "\n"


def source_manifest_markdown() -> str:
    lines = ["# Source and licence manifest", "",
             "_Generated from `python/portfolio/definitions.py`. The dashboard shows the same table._", "",
             "Olist and Criteo are separate studies. They are never joined: Olist has no treatment, cost or "
             "margin fields, and Criteo's features are anonymised (`f0`-`f11`) with no product or geography "
             "meaning.", ""]
    for s in SOURCES:
        lines += [f"## {s['name']}", "",
                  f"- **Publisher:** {s['publisher']}",
                  f"- **Link:** {s['url']}",
                  f"- **Licence:** {s['license']}",
                  f"- **Size (documented):** {s['rows_documented']}",
                  f"- **What is in this repository:** {s['in_repo']}",
                  f"- **Obligations:** {s['obligations']}", ""]
    lines += ["## Download status in this build", "",
              "The build environment's network policy denied `www.kaggle.com`, `ailab.criteo.com` and "
              "`go.criteo.net`, so no raw file was downloaded and no full-data result was re-executed. "
              "To run the full-data path locally, download the three Kaggle datasets into `data/raw/` "
              "(see README) and run the original `dbt build` plus `python/criteo/ab_analysis.py`.", ""]
    return "\n".join(lines)
