# Metric dictionary and grain contract

_Generated from `python/portfolio/definitions.py` by `python -m portfolio.pipeline docs`. Do not edit by hand; the dashboard embeds the same list._

## Provenance badges

| Badge | Meaning |
|---|---|
| ◷ HISTORICAL | Committed output of the prior full-data run (2026-07-16). Not re-executed in this build. |
| ↻ RECOMPUTED | Computed in this build (or in your browser) from committed historical inputs. |
| ◇ SYNTHETIC | From the deterministic generated sample. Demonstrates mechanics; says nothing about the real marketplace or ad experiment. |
| ≈ INFERRED | An integer not stored in the extract, recovered only because exactly one value reproduces an exported ratio at its printed precision. Never an estimate. |
| ∅ UNAVAILABLE | The inputs cannot support this number for the current selection. Shown as such, never estimated. |
| ? HYPOTHETICAL | Depends on assumptions you type in (cost, value). Neither dataset contains costs or margins. |
| ↺ RETROSPECTIVE | Evaluated after the fact on a cohort split whose training labels were not available at the cut; not a deployable, prospective result. |

## Grain of each extract

| Extract | Grain | Built on | Joint filters it supports |
|---|---|---|---|
| monthly | month | fct_orders (order grain), analysis window | month |
| category | month x product category | fct_order_items (item grain) | month, category |
| state | month x customer state | fct_orders | month, state |
| payment | month x primary payment type | fct_orders, orders with a payment record | month, type |

No extract has a joint month x state x category grain, so the dashboard never filters one view by another view's dimension. Each filter shows the views it applies to.

## Metrics

### Orders (`orders`)

- **Views:** Overview, States, Payments
- **Definition:** Orders purchased in the month (analysis window 2017-01 to 2018-08).
- **Formula:** `count(*) over fct_orders`
- **Numerator / denominator:** orders / -
- **Grain:** month (and month x state, month x primary payment type)
- **Combining a selection:** Sum across months. Sum across states (one customer state per order). Sum across primary payment types (one exclusive primary type per order; orders with no payment record are excluded from the payment extract).

### GMV (item value incl. freight) (`gmv`)

- **Views:** all marketplace views
- **Definition:** Sum of item price + item freight over order lines, in BRL. Orders with no items contribute nothing (NULL, not zero). Not the same as payments.
- **Formula:** `sum(price + freight_value), integer cents`
- **Numerator / denominator:** cents / -
- **Grain:** every extract
- **Combining a selection:** Sum of integer cents; exact in every view.

### Payments (`payments`)

- **Views:** Overview, Payments
- **Definition:** Sum of payment_value over all payment rows of the orders in scope. In the Payments view it is the WHOLE payment total of orders whose primary instrument is X - including money paid with other instruments - not the amount paid with X.
- **Formula:** `sum(payment_total_brl)`
- **Numerator / denominator:** cents / -
- **Grain:** month; month x primary payment type
- **Combining a selection:** Sum of integer cents.

### Average order value (AOV) (`aov`)

- **Views:** Overview, States, Payments
- **Definition:** GMV divided by orders that have at least one item.
- **Formula:** `sum(GMV) / sum(orders_with_items)`
- **Numerator / denominator:** GMV cents / orders with >= 1 item (not all orders)
- **Grain:** any selection
- **Combining a selection:** Re-derived from summed numerator and denominator. Historical state/payment extracts do not store orders_with_items: it is INFERRED per cell only when a unique integer reproduces the exported AOV; any unidentified cell makes the selection's AOV UNAVAILABLE.

### Cancellation rate (`cancel_rate`)

- **Views:** Overview
- **Definition:** Cancelled orders as a share of all orders.
- **Formula:** `canceled / orders`
- **Numerator / denominator:** orders with status 'canceled' / all orders
- **Grain:** month
- **Combining a selection:** Sum numerator and denominator, then divide.

### Late-delivery rate (weighted) (`late_rate`)

- **Views:** Overview, States
- **Definition:** Delivered orders whose delivery calendar day is after the estimated calendar day, as a share of delivered orders. Delivered on the estimated day counts as on time. A delivered-status order without a delivery timestamp stays in the denominator and is never counted late.
- **Formula:** `late / delivered`
- **Numerator / denominator:** late delivered orders / orders with status 'delivered'
- **Grain:** month; month x state (synthetic only)
- **Combining a selection:** Sum late and delivered, then divide. Historical state extract has no delivered/late counts: a multi-cell state late rate is UNAVAILABLE rather than an average of percentages.

### Mean of monthly late rates (counterexample) (`naive_late_mean`)

- **Views:** Overview
- **Definition:** Unweighted average of the monthly rates. Shown ONLY to demonstrate why it is wrong: it gives an 800-order month the same weight as a 7,500-order month.
- **Formula:** `mean_m(late_m / delivered_m)`
- **Numerator / denominator:** - / -
- **Grain:** month
- **Combining a selection:** Not a metric. Never used for decisions.

### Low-review rate (`low_review_rate`)

- **Views:** Overview
- **Definition:** Reviewed orders whose latest review score is 1 or 2, as a share of reviewed orders.
- **Formula:** `low_score_orders / reviewed_orders`
- **Numerator / denominator:** latest review score <= 2 / orders with >= 1 review
- **Grain:** month
- **Combining a selection:** Sum then divide. Historical numerator is INFERRED per month (unique integer reproducing the exported rate); all 20 months were identified.

### Average review score (`review_score`)

- **Views:** Overview, States
- **Definition:** Mean, over reviewed orders, of each order's mean review score (1-5).
- **Formula:** `sum(order mean score) / count(reviewed orders)`
- **Numerator / denominator:** sum of order means / orders with a non-NULL mean score (valid-value count)
- **Grain:** month; month x state
- **Combining a selection:** Exact only with the valid-value count and sum (synthetic extracts). Historical extracts: single cell only; a multi-cell value is UNAVAILABLE.

### Average delivery days (`delivery_days`)

- **Views:** Overview, States
- **Definition:** Mean calendar days from purchase to customer delivery, over delivered orders that have a delivery timestamp.
- **Formula:** `sum(days) / count(non-NULL days) among delivered`
- **Numerator / denominator:** sum of days / delivered orders WITH a delivery timestamp - not all delivered orders
- **Grain:** month; month x state
- **Combining a selection:** As average review score.

### Items per order (`items_per_order`)

- **Views:** Overview
- **Definition:** Mean number of order lines per order that has items.
- **Formula:** `sum(item_count) / count(item_count)`
- **Numerator / denominator:** order lines / orders with items (valid-value count)
- **Grain:** month
- **Combining a selection:** As average review score.

### Average installments (`installments`)

- **Views:** Overview, Payments
- **Definition:** Mean of each order's maximum installment count, over orders with a payment record.
- **Formula:** `sum(max_installments) / count(max_installments)`
- **Numerator / denominator:** sum of installments / orders with a payment record (valid-value count)
- **Grain:** month; month x type
- **Combining a selection:** As average review score.

### Installment rate (`installment_rate`)

- **Views:** Payments
- **Definition:** Orders paid in more than one installment, as a share of orders in the group.
- **Formula:** `installment_orders / orders`
- **Numerator / denominator:** orders with max_installments > 1 / orders in the primary-type group
- **Grain:** month x primary type
- **Combining a selection:** Sum then divide.

### Share of orders by primary instrument (`share_of_orders`)

- **Views:** Payments
- **Definition:** Orders whose primary instrument (the one carrying the most money on the order) is X, as a share of all orders with a primary instrument in the selected months. The payment-type filter does not change the denominator.
- **Formula:** `orders_X / orders_all_types`
- **Numerator / denominator:** orders with primary type X / orders with any primary type (excludes orders with no payment record)
- **Grain:** month x primary type
- **Combining a selection:** Sum then divide.

### Active customers (`active_customers`)

- **Views:** Overview, States (single cell)
- **Definition:** Distinct people (customer_unique_id) with an order in the cell.
- **Formula:** `count(distinct customer_unique_id)`
- **Numerator / denominator:** - / -
- **Grain:** month; month x state; month x category
- **Combining a selection:** NOT additive: a person active in two months would be counted twice. Shown for a single cell only; the sum of monthly values is labelled customer-months.

### Freight share of GMV (`freight_share`)

- **Views:** Overview, Categories, States
- **Definition:** Freight value as a share of item GMV. A price-composition measure - NOT margin, cost to the marketplace, or a saving.
- **Formula:** `sum(freight) / sum(GMV)`
- **Numerator / denominator:** freight cents / GMV cents
- **Grain:** any selection
- **Combining a selection:** Sum then divide.

### Orders containing the category (`category_orders`)

- **Views:** Categories
- **Definition:** Distinct orders with at least one line in the category.
- **Formula:** `count(distinct order_id) per month x category`
- **Numerator / denominator:** - / -
- **Grain:** month x category
- **Combining a selection:** For ONE category, adds across months (an order belongs to one month). NOT additive across categories: an order spanning two categories is counted in both. The all-category sum is labelled category-order pairs.

### Average line value (`avg_line_value`)

- **Views:** Categories
- **Definition:** GMV per order line in the category.
- **Formula:** `sum(GMV) / sum(order lines)`
- **Numerator / denominator:** GMV cents / order lines
- **Grain:** month x category
- **Combining a selection:** Sum then divide.

### Share of selected GMV (`share_of_selected_gmv`)

- **Views:** Categories
- **Definition:** Category GMV as a share of GMV across all categories in the selected months (the search box does not change the denominator).
- **Formula:** `GMV_category / GMV_all_categories`
- **Numerator / denominator:** category GMV cents / all-category GMV cents in the selected months
- **Grain:** any selection
- **Combining a selection:** Sum then divide.

### Label: won within 90 days (`is_won_90d`)

- **Views:** Lead scoring
- **Definition:** A closed deal dated 0 to 90 days (inclusive) after first contact. Never-won leads and negative lags are negatives.
- **Formula:** `0 <= won_date - first_contact_date <= 90`
- **Numerator / denominator:** - / -
- **Grain:** lead
- **Combining a selection:** Counts sum.

### Label maturity / as-of (`label_maturity`)

- **Views:** Lead scoring
- **Definition:** A lead's 90-day label is complete on first_contact + 91 days. A model deployed at as-of date T may train only on leads contacted on or before T - 91 days (purge gap 91 days).
- **Formula:** `train_end = as_of - 91 days`
- **Numerator / denominator:** - / -
- **Grain:** design
- **Combining a selection:** -

### Point-in-time landing-page volume (`page_volume_prior`)

- **Views:** Lead scoring
- **Definition:** Leads on the same landing page with a strictly earlier contact date. Replaces the legacy full-dataset count, which included future leads.
- **Formula:** `count(earlier leads on page)`
- **Numerator / denominator:** - / -
- **Grain:** lead
- **Combining a selection:** -

### Top-k hits (tie-aware) (`top_k_hits`)

- **Views:** Lead scoring
- **Definition:** Positives among the k highest-scored leads of a held-out cohort. Deterministic order: score descending, then lead id. Where the k-th score is tied, the expected value over all orderings of the tied block is shown with its min-max range. Retrospective ranking quality - NOT incremental wins.
- **Formula:** `hits above cut + positives in tied block x slots left / block size`
- **Numerator / denominator:** positives / k
- **Grain:** score cohort
- **Combining a selection:** -

### ROC AUC / PR-AUC / Brier (`auc`)

- **Views:** Lead scoring
- **Definition:** Ranking (AUC, average precision) and calibration (Brier: mean squared error of the predicted probability) on the held-out cohort.
- **Formula:** `sklearn roc_auc_score / average_precision_score / brier_score_loss`
- **Numerator / denominator:** - / -
- **Grain:** score cohort
- **Combining a selection:** -

### ITT effect (intention to treat) (`itt`)

- **Views:** Experiment
- **Definition:** Conversion rate of users ASSIGNED to treatment minus that of users assigned to control. Identified by randomisation alone; the effect of the decision a marketer can take.
- **Formula:** `y_t/n_t - y_c/n_c, Wald 95% CI`
- **Numerator / denominator:** conversions / assigned users
- **Grain:** experiment arm
- **Combining a selection:** -

### Relative lift (`relative_lift`)

- **Views:** Experiment
- **Definition:** ITT as a share of the control rate, with a delta-method (log ratio) 95% CI.
- **Formula:** `p_t/p_c - 1`
- **Numerator / denominator:** - / -
- **Grain:** experiment arm
- **Combining a selection:** -

### CACE (effect on compliers) (`cace`)

- **Views:** Experiment
- **Definition:** ITT divided by the exposure rate in the treated arm. Needs the exclusion restriction and describes only compliers (users who would be exposed) - a small, systematically different group. Not 'the true effect'.
- **Formula:** `ITT / P(exposed | treated), delta-method 95% CI`
- **Numerator / denominator:** ITT / compliance
- **Grain:** experiment
- **Combining a selection:** -

### Exposed vs control (naive) (`naive`)

- **Views:** Experiment
- **Definition:** Conversion of exposed users vs control. NOT an effect estimate: exposure is selected by user behaviour after assignment.
- **Formula:** `y_exposed/n_exposed - y_c/n_c`
- **Numerator / denominator:** - / -
- **Grain:** experiment
- **Combining a selection:** -

### Minimum detectable effect (`mde`)

- **Views:** Experiment
- **Definition:** Smallest absolute difference the design detects with the stated power at alpha 0.05. Statistical significance is not practical importance.
- **Formula:** `Cohen's h inversion (as the prior run)`
- **Numerator / denominator:** - / -
- **Grain:** design
- **Combining a selection:** -

### Break-even value per incremental conversion (`breakeven`)

- **Views:** Experiment
- **Definition:** HYPOTHETICAL. Cost per 1,000 assigned users (or per 1,000 exposed users x compliance) divided by incremental conversions per 1,000 assigned users. The datasets contain no cost or margin.
- **Formula:** `cost_per_1000_assigned / (1000 x ITT)`
- **Numerator / denominator:** your cost input / incremental conversions per 1,000
- **Grain:** experiment
- **Combining a selection:** -
