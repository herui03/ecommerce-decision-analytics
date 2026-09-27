# Data Verification Log

> **Status (2026-09 portfolio upgrade).** This log records the prior full-data run of
> 2026-07-16. Its counts (e.g. 170 PASS, 99,441 orders) are **historical and were not re-executed**
> on the upgrade branch: the raw Kaggle/Criteo files could not be downloaded there. The five
> intermediate dbt models this log describes were never committed; they have been
> reconstructed and validated on synthetic data only. Current, re-executed evidence is in
> [`docs/evidence.md`](evidence.md); corrections found in the upgrade are appended to the
> corrections log below (#17 onwards) and detailed in [`docs/defect-log.md`](defect-log.md).

Every figure quoted in this repo's README, docs, dashboard, or interview material must
appear here first, with the script that reproduces it. If a number isn't in this file,
it hasn't been verified and must not be stated.

**Last full audit:** 2026-07-16
**Current build: 170 PASS / 0 WARN / 0 ERROR / 170 TOTAL**, 28 models (11 staging,
5 intermediate, 12 marts).

**Reproduce everything:**
```bash
cd dbt && DBT_PROFILES_DIR=$PWD ../.venv/bin/dbt build     # 170 PASS
.venv/bin/python python/audit_stage1.py                    # Stage-1 figures
.venv/bin/python python/probe_grain.py                     # true grain of all 11 tables
.venv/bin/python python/demo_fanout.py                     # the fan-out damage
.venv/bin/python python/demo_exposure_trap.py              # the exposure trap
.venv/bin/python python/criteo/ab_analysis.py              # ITT, CACE, MDE
.venv/bin/python python/train_lead_scoring.py              # lead scoring
.venv/bin/python python/export_tableau.py                  # extracts + round-trip check
.venv/bin/python python/verify_readme_claims.py            # 24 README claims
```

> Build counts quoted in the per-stage sections below (79, 104, 158) are historical, 
> they are the totals at the time each layer was built, kept so the sequence is legible.
> **170 is the current figure.**

---

## Source 1: Olist Brazilian E-Commerce

Kaggle `olistbr/brazilian-ecommerce` + `olistbr/marketing-funnel-olist` · CC-BY-NC-SA-4.0

### Table row counts, 6/6 verified

| Table | Rows |
|---|---:|
| orders | 99,441 |
| order_items | 112,650 |
| customers | 99,441 |
| geolocation | 1,000,163 |
| marketing_qualified_leads | 8,000 |
| closed_deals | 842 |

Order window: **2016-09-04 → 2018-10-17**. Order status: **97.02% delivered**.

### Customer frequency, the RFM blocker

Grouped on `customer_unique_id` (person-level key), **not** `customer_id`.

| Orders per customer | Customers | % |
|---:|---:|---:|
| 1 | 93,099 | 96.88% |
| 2 | 2,745 | 2.86% |
| 3 | 203 | 0.21% |
| 4 | 30 | 0.03% |
| 5 | 8 | 0.01% |
| 6 | 6 | 0.01% |
| 7 | 3 | 0.00% |
| 9 | 1 | 0.00% |
| 17 | 1 | 0.00% |

**96,096 unique customers · 93,099 one-time (96.88%) · 2,997 repeat (3.12%) · max 17 orders.**

Integrity checks passed: `93,099 + 2,997 = 96,096`; distribution sums to 96,096.

**Wrong-key counterfactual (proves the key matters):** grouping on `customer_id` returns
**99,441 customers, 100.00% one-time, max 1 order**, a fake result identical in shape to
a real one.

→ See `docs/challenge-01-rfm-frequency-collapse.md`

### Campaign / cost fields, verified absent

All **11 tables**, all columns scanned for `cost / spend / budget / campaign / offer /
discount / promo / coupon / treatment / control / variant`: **zero hits**.

→ Olist cannot support A/B testing, campaign-cost forecasting, or offer-response
modelling. Those modules move to Source 2.

### Marketing funnel, verified joinable

| Check | Result |
|---|---|
| MQL rows / distinct `mql_id` | 8,000 / 8,000 (unique) |
| closed_deals rows / distinct `mql_id` | 842 / 842 (unique) |
| Deals joining back to MQL | **842 / 842** (no orphans) |
| **Lead → won conversion rate** | **842 / 8,000 = 10.53%** |
| closed_deals `seller_id` → sellers | **380 / 842 (45.13%)** matched |

The funnel is **B2B seller recruitment**, not consumer marketing. Supports lead scoring
(10.53% positive class, workable balance). The 462 won sellers with no matching seller
record is an open data-quality question, not yet explained.

---

## Source 2: Criteo Uplift v2.1

Kaggle `arashnic/uplift-modeling` · CC0-1.0 · 3.1 GB uncompressed CSV

**Rows: 13,979,592.** Columns (16): `f0`–`f11`, `treatment`, `conversion`, `visit`, `exposure`.

### Randomised assignment

| Arm | Rows | % |
|---|---:|---:|
| control (`treatment=0`) | 2,096,937 | 15.0% |
| treated (`treatment=1`) | 11,882,655 | 85.0% |

Deliberately imbalanced (85/15), not 50/50.

### Outcomes, real run, no modelling

| | control | treated | absolute lift | relative lift |
|---|---:|---:|---:|---:|
| visit | 3.8201% | 4.8543% | +1.0342 pp | +27.07% |
| conversion | 0.1938% | 0.3089% | +0.1152 pp | +59.45% |
| exposure | 0.0000% | 3.6037% | n/a | n/a |

No significance testing applied yet, these are descriptive only.

### Covariate balance, randomisation holds

| treatment | f0 | f1 | f2 | f3 | f4 | f5 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 19.6517 | 10.0679 | 8.4482 | 4.2328 | 10.3365 | 4.0393 |
| 1 | 19.6148 | 10.0703 | 8.4463 | 4.1694 | 10.3392 | 4.0266 |

Means are near-identical across arms, consistent with valid randomisation. (Formal
standardised-mean-difference test still to run.)

### ⚠️ Open design decision, `treatment` vs `exposure`

Only **3.6037%** of the treated arm was actually exposed; control exposure is **0.0000%**
by construction. This is **non-compliance**: assignment is random, exposure is not.

- Analysing on `exposure` **breaks randomisation**, exposure is endogenous (it depends on
  the user's own browsing) and will yield a large, significant, and **wrong** lift.
- Correct default: **ITT (intention-to-treat)** on `treatment`, accepting dilution.
- For the effect on the exposed, `exposure` must be used as an instrument (CACE / LATE),
  not as a grouping variable.

Decision to be recorded in challenge doc 02 when the A/B module is built.

---

## Grain, probed, not assumed

`python/probe_grain.py`, 2026-07-16. Three tables have a column that looks like a
primary key and is not one.

| Table | True grain | Trap |
|---|---|---|
| orders | `order_id` | `customer_id` is also unique, it is per-order, not per-person |
| **order_items** | `(order_id, order_item_seq)` | `order_id` **not** unique |
| **order_payments** | `(order_id, payment_seq)` | `order_id` **not** unique |
| **order_reviews** | `(review_id, order_id)` | **`review_id` itself has 814 duplicates** |
| customers | `customer_id` | `customer_unique_id` has 3,345 dupes, that IS the repeat population |
| products / sellers / mql | `product_id` / `seller_id` / `mql_id` | clean |
| closed_deals | `mql_id` (and `seller_id`, both unique, 1:1) | clean |
| geolocation | **none** | 1,000,163 rows / 19,015 zips, no key at all |

### order_items, two different "duplicate" measures, do not conflate

| Measure | Value |
|---|---:|
| Total rows | 112,650 |
| Distinct `order_id` | 98,666 |
| Excess rows beyond distinct order_id | **13,984** |
| Orders carrying >1 item | **9,803** |
| Mean items per order | 1.14 |
| Max items in one order | 21 |

`dbt_utils.unique_combination_of_columns` reports the **9,803** figure (duplicated
groups), not 13,984. Both are correct; they measure different things.

### Referential integrity, anti-joins, not subtraction

| Check | Result |
|---|---:|
| Orders with no `order_items` | 775 |
| Orders with no `order_payments` | 1 |
| Orders with no `order_reviews` | 768 |
| Reverse orphans (child `order_id` absent from orders) | **0** in all three |

**The 775 orders with no items are 99.0% explained by status:**

| order_status | n |
|---|---:|
| unavailable | 603 |
| canceled | 164 |
| created | 5 |
| invoiced | 2 |
| shipped | 1 |

767 of 775 are `unavailable` or `canceled`, orders that never materialised. Only 8 are
genuinely anomalous.

**The 1 order with no payment is a real anomaly:** `bfbd0f9bdef84302105ad712db648a6c`,
status = **delivered**. A delivered order with no payment record. Kept in staging, not
patched, the handling decision belongs in the mart layer.

---

## dbt layer, build status

`cd dbt && DBT_PROFILES_DIR=$PWD ../.venv/bin/dbt build`

**79 PASS / 0 WARN / 0 ERROR / 79 TOTAL.**

11 staging models, grain declared per the probe above, plus two singular tests that make
this document executable:

- `dbt/tests/assert_staging_rowcounts.sql`, all 11 row counts must match this file
- `dbt/tests/assert_customer_frequency_headline.sql`, the 96.88% headline, plus the
  independent cross-check that `sum(orders-1) = 3,345` matches the customers-table
  duplication

### Mutation testing, proof the tests can actually fail

A green suite proves nothing unless a wrong number turns it red. Each assertion was
deliberately broken and the failure observed:

| Mutation | Result |
|---|---|
| orders expected 99,441 → 99,442 (**off by one row**) | 🔴 FAIL 1 |
| 96.88% → 96.89% (**off by 0.01 pp**) | 🔴 FAIL 1 |
| order_items grain misdeclared as `[order_id]` | 🔴 FAIL 9803 |
| all restored | 🟢 79/79 PASS |

---

## Money, reconciled to the cent

Source-grain truth (`python/demo_fanout.py`):

| Measure | BRL |
|---|---:|
| Total item value (`order_items`) | 15,843,553.24 |
| Total payment value (`order_payments`) | 16,008,872.12 |
| **Gap** | **165,318.88** |

The gap is fully explained, residual **0.00**:

| Component | BRL |
|---|---:|
| + Payments on the 775 orders that have no items | 162,591.95 |
| + Net per-order difference across the 98,665 orders having both | 2,870.39 |
| − Item value of the 1 order with no payment | −143.46 |
| **= Reconciled** | **165,318.88** |
| **Residual** | **0.00** |

**Order coverage is exhaustive:** 98,665 (both) + 775 (payment only) + 1 (items only)
= **99,441** = every order.

Per-order agreement is high: of the 98,665 orders with both, **98,089 (99.42%) match to
the cent**; 264 paid more, 39 paid less.

Payment mix:

| payment_type | rows | BRL |
|---|---:|---:|
| credit_card | 76,795 | 12,542,084.19 |
| boleto | 19,784 | 2,869,361.27 |
| voucher | 5,775 | 379,436.87 |
| debit_card | 1,529 | 217,989.79 |
| not_defined | 3 | 0.00 |

---

## The fan-out, measured, not assumed

Joining `orders` directly to `order_items` + `order_payments` + `order_reviews`
(`python/demo_fanout.py`). **This query raises no error and emits no warning.**

| | Correct | Naive 4-way join | Damage |
|---|---:|---:|---|
| Rows | 99,441 | 117,329 | 1.18× |
| **Distinct orders** | 99,441 | **97,916** | **1,525 silently dropped** |
| Item revenue | 15,843,553.24 | 16,490,809.55 | +4% (+647,256.31) |
| **Payment value** | 16,008,872.12 | **20,187,928.70** | **+26% (+4,179,056.58)** |

It overstates money and understates orders *at the same time*. Payment inflates 26% while
items inflate only 4%, because the payment duplication (4,446) multiplies against the item
duplication (13,984).

→ See `docs/challenge-03-silent-fanout.md`

---

## Intermediate layer

Each child is pre-aggregated to order grain in its own model, then LEFT JOINed onto the
`orders` spine.

| Model | Rows | Note |
|---|---:|---|
| `int_orders__items_agg` | 98,666 | 775 orders have no items |
| `int_orders__payments_agg` | 99,440 | 1 order has no payment |
| `int_orders__reviews_agg` | 98,673 | 768 orders unreviewed |
| `int_geolocation__zip_centroid` | 19,015 | from 1,000,163 raw points; **median** centroid |
| **`int_orders__enriched`** | **99,441** | order grain, = `stg_olist__orders` exactly |

`int_orders__enriched` verified totals: items **15,843,553.24**, payments **16,008,872.12**, 
identical to source grain. Flags carried: 775 `has_no_items`, 1 `has_no_payment`, 768
`has_no_review`. NULLs preserved, never zero-filled: NULL = "no record exists", 0.00 =
"recorded as zero", and conflating them would make a canceled order look free.

**Build: 104 PASS / 0 WARN / 0 ERROR / 104 TOTAL.**

### Mutation testing, both defence layers proven

| Mutation | Result |
|---|---|
| `items_agg`: `group by 1` → `group by 1, product_id` (compiles fine, grain silently shatters) | 🔴 `unique_int_orders__items_agg_order_id` **FAIL 3236**, 7 downstream models **SKIPPED**, bad data never reached the fact |
| `enriched`: `LEFT JOIN items` → `INNER JOIN` (grain intact, orders silently dropped) | 🔴 `equal_rowcount` **FAIL 775** (exactly the no-item orders) + `assert_orders_enriched_reconciles` **FAIL 1** |
| all restored | 🟢 104/104 PASS |

---

## Marts layer

| Model | Rows | Grain |
|---|---:|---|
| `dim_customers` | **96,096** | one **person** (`customer_unique_id`), not 99,441 |
| `dim_products` | 32,951 | one product, **all** of them |
| `dim_sellers` | 3,095 | one seller |
| `dim_geography` | 19,015 | one zip prefix |
| `fct_orders` | **99,441** | one order |
| `fct_order_items` | **112,650** | one order line |

**Build: 135 PASS / 0 WARN / 0 ERROR / 135 TOTAL.**

### Two facts, two grains, the rule

| Question | Fact | Why not the other |
|---|---|---|
| Order counts, AOV, delivery, payment mix, cancellation | `fct_orders` | `fct_order_items` repeats `order_id` 13,984 times, counting rows reports 112,650 "orders" |
| Revenue by category / product / seller | `fct_order_items` | **727 orders span multiple categories** (712 span 2, 15 span 3), order grain cannot attribute them |

Only 97.86% of orders are single-category, which is the trap: high enough that stamping
"the" category onto an order looks harmless, and it would misattribute 727 orders.

**Cross-fact money agreement (asserted, `dbt/tests/assert_facts_agree_on_money.sql`):**
both facts sum `items_total_brl` to **15,843,553.24**, difference **0.00**, despite living
at different grains. `fct_order_items` covers **98,666** distinct orders (99,441 − 775
with no items).

### The category lookup gap, quantified

The PT→EN lookup has **71** rows; the product table carries **73** distinct PT categories.

| | Products |
|---|---:|
| Translated cleanly | 32,328 |
| No category at all (NULL) | 610 |
| Category exists but absent from the lookup | 13 |
| **Total** | **32,951** |

Missing from the lookup: `portateis_cozinha_e_preparadores_de_alimentos` (10 products),
`pc_gamer` (3).

**An `INNER JOIN` here would silently drop 623 products, taking 1,627 order lines
across 1,473 orders and 213,662.90 BRL of revenue out of category reporting.**
Hence LEFT JOIN + coalesce to `'unknown'` + explicit `has_no_category` /
`missing_translation` flags.

### Other verified mart facts

- **278 of 99,441 customer zips (0.28%)** have no geolocation match → LEFT JOIN, flagged
  as `customer_zip_not_geocoded`.
- **A person can hold multiple addresses:** 250 people span multiple zip prefixes, 39 span
  multiple states (max 3 of each). `dim_customers` takes the most recent order's address
  with a deterministic tie-break.
- **Recency:** min 0, max 773, mean 288.1 days, anchored to the dataset's last order
  (2018-10-17 17:30:18), derived not hardcoded.

### Mutation testing, and a real gap it found

| Mutation | Result |
|---|---|
| `dim_products`: `LEFT JOIN` → `INNER JOIN` | 🔴 `equal_rowcount` **FAIL 623**, exactly 610 + 13 |
| `fct_order_items`: drop freight from `item_total_brl` | 🔴 `assert_facts_agree_on_money` **FAIL 1** |
| `dim_customers`: recency anchor → `current_date` | ⚠️ **PASSED, test suite gap.** Fixed, see below |
| recency anchor → `current_date`, retested after fix | 🔴 `assert_recency_anchor` **FAIL 1** |
| all restored | 🟢 135/135 PASS |

---

## Metric layer

**Build: 158 PASS / 0 WARN / 0 ERROR / 158 TOTAL.** 27 models across 3 layers.

| Model | Grain | Built on |
|---|---|---|
| `mart_monthly_performance` | month (20 rows) | `fct_orders` |
| `mart_category_performance` | month × category | **`fct_order_items`**, category is only additive at item grain |
| `mart_state_performance` | month × state | `fct_orders` |
| `mart_payment_performance` | month × payment type | `fct_orders` |
| `mart_customer_segments` | person (96,096) | `dim_customers` + `fct_orders` |

Every ratio is computed in SQL. The dashboard performs no arithmetic, it plots columns.

### The analysis window, the raw range tells a false story

| Period | Orders | Reality |
|---|---:|---|
| 2016-09 | 4 | pilot |
| 2016-10 | 324 | pilot |
| **2016-11** | **0** | **month absent from the source entirely** |
| 2016-12 | 1 | pilot |
| 2017-01 … 2018-08 | 800 → 7,544 | the actual business |
| 2018-09 | 16 | export tail |
| 2018-10 | 4 | export tail |

Daily counts show precisely where the export was cut: **69 / 73 / 67 / 44 through
2018-08-28, then 14 → 4 → 1**, and never recovering. September and October are scattered
single orders on non-consecutive days.

Plotting the raw range would show growth from 4 orders to 7,544 and then a collapse to 4.
**Both ends are the dataset, not the market.**

**Window adopted: 2017-01 → 2018-08 (exclusive of 2018-09).**

| | Orders |
|---|---:|
| In window | **99,092 (99.65%)** |
| Excluded, 2016 pilot | 329 |
| Excluded, 2018 tail | 20 |
| **Total excluded** | **349 (0.35%)** |

20 consecutive months, **no gaps verified**. Thinnest in-window month: 2017-01 at 800
orders. The window lives in `dbt_project.yml` vars; `fct_orders` keeps all 99,441 rows
and carries an `is_in_analysis_window` flag, the spine records what happened, the metric
layer filters.

→ See `docs/challenge-04-phantom-trend.md`

### 2018-10's NULL GMV, NULL semantics working, not a bug

All 4 orders in 2018-10 are `canceled` with `has_no_items = true`, so `items_total_brl` is
NULL for every one and `sum()` returns NULL. They do carry payments (80.38, 197.55,
222.03, 89.71). This vindicates the no-zero-fill decision: "no item record exists" is not
"the basket was worth 0".

### Verified metric-layer output (in-window)

| | Value |
|---|---|
| Months | 20 |
| Orders | 99,092 |
| GMV range | 137,188 (2017-01) → 1,179,144 (2017-11) BRL |
| AOV range | 147.39 – 173.88 BRL |
| Cancel rate | 0.19% – 1.29% |
| Late-delivery rate | 1.16% – **18.96%** (2018-03) |
| Avg review score | **3.75** (2018-03) – 4.28 (2018-06) |

The worst late-delivery month (2018-03, 18.96%) is also the worst-reviewed month (3.75),
and the second-worst (2018-02, 14.14%) is the second-worst reviewed (3.83), a
relationship worth testing rather than asserting.

### R/M segments, reproducible only after a tie-break was added

| Segment | Customers | % | Avg LTV (BRL) | Avg recency (days) |
|---|---:|---:|---:|---:|
| Mid | **34,628** | 36.03% | 135.78 | 279 |
| Lapsed low-value | **15,871** | 16.52% | 55.86 | 447 |
| Recent high-value | **15,847** | 16.49% | 310.05 | 141 |
| Lapsed high-value | **14,931** | 15.54% | 314.38 | 445 |
| Recent low-value | **14,819** | 15.42% | 54.89 | 139 |
| **Total** | **96,096** | 100% | | |

NTILE yields exactly even quintiles on both axes (19,219 × 4 + 19,220 = 96,096).

**These counts were not stable until a tie-break was added.** There are only **632 distinct
recency values** across 96,096 customers, **1,143 people share `recency = 327` alone**, 
and 28,154 distinct monetary values. NTILE must cut through tied blocks to keep buckets
equal, and without a deterministic tie-break it cut in **physical row order**, which changes
on every rebuild.

Observed drift: **Mid went 34,617 → 34,620 → 34,628 across runs.** The total was always a
correct 96,096, every test passed, and nothing warned. A customer could change segment
because the table was rebuilt.

Both NTILEs now carry `, customer_unique_id asc`. Verified by two consecutive
`--full-refresh` builds producing identical counts, and locked by
`dbt/tests/assert_segments_reproducible.sql` + `dbt/tests/assert_ntile_buckets_even.sql`.
Mutation test, tie-break removed: 🔴 **FAIL 4**.

Ties are still split; that is inherent to NTILE and the price of equal buckets. What is
guaranteed is that the *same* customers split the *same* way every time.

Top categories by in-window GMV: health_beauty 1,435,611; watches_gifts 1,302,074;
bed_bath_table 1,241,075. Freight share ranges 7.7% (watches_gifts) to 19.1%
(furniture_decor).

### Mutation testing, and a second suite gap it found

| Mutation | Result |
|---|---|
| `mart_monthly_performance`: window filter removed | 🔴 `assert_metric_layer_reconciles` **FAIL 1** + `not_null_gmv_brl` **FAIL 1** (the 2018-10 NULL) |
| `mart_category_performance`: `count(distinct order_id)` → `count(*)`, line items reported as orders | ⚠️ **PASSED, suite gap.** GMV reconciled; order counts were never asserted |
| same mutation, after adding order-count assertions | 🔴 `assert_metric_layer_reconciles` **FAIL 1** |
| all restored | 🟢 158/158 PASS |

The fix uses a strict inequality: in-window `sum(order_lines)` must equal **112,279** and
`sum(orders)` must be **strictly fewer** (99,154). `count(*)` forces them equal, which the
inequality catches. Note 99,154 exceeds the true 99,092 by design, the 727
multi-category orders count once per category, which is correct for a drill-down.

---

## Tableau extracts, round-trip verified

`python/export_tableau.py`. Each extract is written, then **re-read from disk** and
compared against the warehouse on row count, NULL count, and money to the cent. An
extract that fails verification is **deleted, not shipped**, a corrupt CSV in Tableau is
indistinguishable from a wrong dashboard, and by then you're debugging the wrong layer.

| Extract | Rows | NULLs | Money (BRL) | Size | Round-trip |
|---|---:|---:|---:|---:|---|
| `mart_monthly_performance` | 20 | 0 | 15,786,203.57 | 5.0 KB | ✅ |
| `mart_category_performance` | 1,246 | 0 | 15,786,203.57 | 156.7 KB | ✅ |
| `mart_state_performance` | 533 | 0 | 15,786,203.57 | 73.6 KB | ✅ |
| `mart_payment_performance` | 81 | 1 | 15,786,203.57 | 8.9 KB | ✅ |
| `mart_customer_segments` | 96,096 | 1 | 16,008,872.12 | 14.6 MB | ✅ |

### Four aggregation paths, one number

| Source | In-window GMV | Diff |
|---|---:|---:|
| `fct_orders` (baseline) | 15,786,203.57 | n/a |
| `mart_monthly_performance` | 15,786,203.57 | +0.00 |
| `mart_category_performance` | 15,786,203.57 | +0.00 |
| `mart_state_performance` | 15,786,203.57 | +0.00 |
| `mart_payment_performance` | 15,786,203.57 | +0.00 |

`mart_category_performance` is aggregated up from **item grain** and still lands on the
same total as three order-grain marts. That cross-grain agreement is the strongest single
piece of evidence that the model is coherent.

### Two anomalies checked rather than assumed

**The payment mart excludes the one order with no payment type, so why does its GMV match?**
Because `bfbd0f9bdef84302105ad712db648a6c` was purchased **2016-09-15**, putting it in the
excluded pilot period (`is_in_analysis_window = false`). Two independent decisions, drop
the pilot, drop orders with no payment type, happen to land on the same order. Verified,
not assumed.

**The payment mart's 1 NULL GMV:** 2018-08, `primary_payment_type = 'not_defined'`,
2 orders, payment 0.00, no items → NULL GMV. Consistent with the raw source, where
`not_defined` has 3 rows totalling 0.00 BRL. A real quirk, not a bug.

### CSV export hazards, checked before exporting

| Hazard | Result |
|---|---|
| Accented Portuguese characters | **0**, Olist city names are already ASCII-normalised |
| Commas/quotes inside city or category names | **0** |
| NULLs needing careful handling | 1 (`lifetime_payment_brl`) + 716 (`avg_review_score`) in segments; 1 in payment mart |

NULLs are written as empty strings, not the literal `NULL`, writing text would coerce the
whole column to string in Tableau and silently break every aggregate on it.

### Dimension counts (quoted in the build guide)

- **27** distinct state codes.
- **74** distinct categories = **71** translated EN + **2** untranslated PT
  (`portateis_cozinha_e_preparadores_de_alimentos`, `pc_gamer`) + **1** `unknown` bucket
  (where the 610 NULL-category products land via `coalesce`). Same 74 in `dim_products`.

---

## Lead scoring

**Question:** will a marketing-qualified lead convert within 90 days?
**Model window:** 2018-01 → 2018-05. **5,998 leads, 677 positives (11.29%).**

### Why the target is `is_won_90d` and not `is_won_ever`

Time-to-win, over the 842 won deals: min **−2**, median **14**, mean **48.4**, p75 **54.75**,
p90 **161.9**, max **427** days.

"Ever won" gives each lead a different observation window (a 2017-07 lead had ~500 days;
a 2018-05 lead had 167), so it measures how long we watched, not lead quality. A fixed
90-day horizon equalises it. Last lead **2018-05-31** + 90d = **2018-08-29**; last recorded
win **2018-11-14** → consistent with every lead being fully observed. *(Corrected 2026-09: the latest positive date does not prove complete follow-up of negatives; treat the observation cutoff as an assumption.)*

### Why the window starts 2018-01: a regime break in the target (cause unknown)

90-day conversion by lead month:

| Month | Leads | Won ≤90d | Rate |
|---|---:|---:|---:|
| 2017-07 | 239 | **0** | **0.00%** |
| 2017-08 | 386 | **0** | **0.00%** |
| 2017-09 | 312 | **0** | **0.00%** |
| 2017-10 | 416 | **0** | **0.00%** |
| 2017-11 | 445 | 8 | 1.80% |
| 2017-12 | 200 | 6 | 3.00% |
| 2018-01 | 1,141 | 129 | 11.31% |
| 2018-02 | 1,028 | 128 | 12.45% |
| 2018-03 | 1,174 | 140 | 11.93% |
| 2018-04 | 1,352 | 171 | 12.65% |
| 2018-05 | 1,303 | 109 | 8.37% |

**1,353 leads from Jul–Oct 2017 produced exactly zero 90-day conversions.** Not a low rate, 
zero. The first deal of any kind closed **2017-12**, six months after leads began arriving,
and deals then cluster 2018-01→2018-05 (73, 113, 147, 207, 122). The 2017 leads that did
eventually convert waited an average of **398 days** (2017-07 cohort).

*(Corrected 2026-09: the next sentence is a hypothesis, not a finding.)* There was no sales operation to work them. The 2017 target measures the company's org
history, not lead quality. In-window vs out-of-window 90-day rate: **11.29% vs 0.70%**.

→ See `docs/challenge-05-target-measured-the-org.md`

### Features, only what exists at lead-arrival time

Available: `first_contact_date`, `landing_page_id` (**495** distinct, **247** with exactly
one lead), `lead_origin_channel` (**10** distinct + 60 nulls). That is the entire feature
space.

**Excluded as 100% target leakage:** every rich field on `closed_deals`
(`business_segment` 33 distinct, `lead_type` 8, `lead_behaviour_profile` 9,
`declared_monthly_revenue_brl` 27, `declared_catalog_size` 33). They exist only on the 842
converted rows, the other 7,158 leads have no row at all, not a NULL.

**Excluded as non-generalising:** `contact_month`, `contact_year`,
`days_since_campaign_start`. Under a temporal split train and test occupy disjoint months.

Channel conversion (full data, ever-won): not_recorded 23.33%, unknown 16.29%, paid_search
12.30%, organic_search 11.80%, direct_traffic 11.22%, referral 8.45%, social 5.56%,
display 5.08%, other_publicities 4.62%, email 3.04%, other 2.67%. A ~5× spread, real signal.

### Results, temporal split, test never seen

train 2018-01→03 (n=3,343, 11.88% positive) · test 2018-04→05 (n=2,655, 10.55% positive)

| Model | AUC | PR-AUC | Brier | Top-10% hit | Lift |
|---|---:|---:|---:|---:|---:|
| baseline: base rate | 0.5000 | 0.1055 | 0.0945 | 9.43% | 0.89× |
| **baseline: channel rate (a GROUP BY)** | 0.6177 | 0.1458 | 0.0927 | **19.62%** | **1.86×** |
| **logistic regression** | **0.6870** | **0.1849** | **0.0909** | **20.00%** | **1.90×** |
| gradient boosting | 0.6683 | 0.1791 | 0.0919 | 19.25% | 1.82× |

**The honest headline: the ML model barely beats a pivot table.** A channel-rate `GROUP BY`
delivers 1.86× decile lift against logistic regression's 1.90×, 98% of the value from a
single aggregate. LR wins clearly on *ranking* (AUC 0.687 vs 0.618, PR-AUC 0.185 vs 0.146)
and gives calibrated probabilities, but at the actual decision point the pivot table is
nearly as good.

**Gradient boosting is worse than logistic regression** (AUC 0.6683 vs 0.6870). With 3
features and 3,343 training rows there is nothing for it to find.

**Business translation:** calling the top decile (265 leads) yields a **20.00%** hit rate
vs **10.55%** calling at random, roughly **53 wins instead of 28 from the same 265 calls**. *(Corrected 2026-09: this is retrospective ranking on a held-out cohort, not incremental wins; the 53 depends on tie order (52–54 possible, tie-aware 52.86); and the training labels were not complete at the 2018-04-01 cut, so this is a retrospective backtest.)*

### `class_weight="balanced"`, added reflexively, measured, removed

| | AUC | Brier | Mean predicted p |
|---|---:|---:|---:|
| `balanced` | 0.6851 | **0.2234** | **0.4617** |
| default | **0.6870** | **0.0909** | **0.1148** |
| *(true test rate)* | | | *0.1055* |

It bought nothing on ranking, AUC was marginally **worse**, and destroyed calibration,
telling a salesperson a lead has a 46% chance when the truth is 11%. **Brier is what
exposed it; AUC alone would have hidden it entirely.** Imbalance at an 11% base rate on a
ranking task is not a problem needing a fix.

### The matmul warnings, verified cosmetic

numpy 2.0 on macOS/Accelerate emits `divide by zero encountered in matmul` from sklearn's
linear loss. Verified harmless before suppressing: all coefficients finite (|max| 1.34),
all predicted probabilities finite and within [0, 1]. `matmul` performs no division, 
numpy is attributing the warning to the wrong operation.

---

## Criteo A/B analysis

**13,979,592 rows.** treated 11,882,655 (85.0%) · control 2,096,937 (15.0%).

### Randomisation holds at `treatment`, breaks at `exposure`

Standardised mean differences (SMD; < 0.1 conventionally = balanced):

| Split | f0 | f3 | SMD(f0) | SMD(f3) |
|---|---|---|---:|---:|
| **treatment** (randomised) | 19.6517 vs 19.6148 | 4.2328 vs 4.1694 | **0.0069** ✅ | **0.0488** ✅ |
| **exposure** (within treated) | 19.754 vs **15.890** | 4.2735 vs **1.3858** | **0.8524** ❌ | **1.4688** ❌ |

**SMD differs by 124×.** Only **3.6037%** of the treated arm was exposed (428,212 of
11,882,655); control exposure is **0.0000%** by construction. The exposed are a
systematically different population, f3 means differ threefold.

### The three numbers

| Analysis | Relative lift | Verdict |
|---|---:|---|
| naive: exposed (5.3784%) vs control (0.1938%) | **+2675.83%** | ❌ selection, not causation, **45.01× overstated** |
| CACE: effect on compliers | **+146.49%** | ✅ correct, but describes only the 3.6% |
| **ITT: effect on everyone assigned** | **+59.45%** | ✅ **the number to budget against** |

**ITT:** treated 36,711/11,882,655 = **0.3089%**; control 4,063/2,096,937 = **0.1938%**.
Absolute effect **+0.1152 pp**, 95% CI **[+0.1085, +0.1219] pp**.

**The smoking gun:** treated-but-unexposed convert at **0.1194%** vs control **0.1938%**, 
*lower*. If exposure were random within the treated arm they would match. They don't,
because exposure selects active browsers, who convert anyway.

### CACE, two independent derivations agreeing to 6 dp

| Method | CACE |
|---|---:|
| Wald / IV: ITT ÷ compliance = 0.1152 ÷ 0.036037 | **+3.1964 pp** |
| Decomposition: exposed (5.3784%) − implied complier rate in control (2.1820%) | **+3.1964 pp** |
| **Disagreement** | **0.000000 pp** |

The decomposition recovers the complier rate in control from the never-taker rate
(= treated-and-unexposed, 0.1194%) and the compliance share, using no part of the Wald
algebra. That the two agree exactly is strong evidence both are right.

### The p-value is uninformative here, measured, not asserted

`z = 28.52`, `p = 7.31e-179`.

| Power | MDE (absolute) | MDE (relative) |
|---|---:|---:|
| 80% | **0.0093 pp** | +4.82% |
| 95% | 0.0121 pp | +6.22% |

The observed effect (0.1152 pp) is **12× the 80%-power MDE**. The test is so over-powered
it would flag effects far below anything anyone would act on. The CI and the effect size
carry the argument; the p-value is a footnote.

→ See `docs/challenge-02-exposure-trap.md`

---

## Corrections log

Errors found by audit and fixed. Kept visible on purpose, the point of the log is that
it catches things.

| # | Claim I made | Reality | How it was caught |
|---|---|---|---|
| 1 | Max frequency = **9** orders | **17** | Asserted from a `LIMIT 8` result without pulling the full distribution. Caught when a headline query returned `max=17`. |
| 2 | Criteo = **25,000,000** rows | **13,979,592** | Stated from memory; conflated v1 (~25M) with v2.1. Caught on first real `count(*)`. |
| 3 | "Olist has no cost fields" | Correct, but **had only checked 2 of 11 tables** when first asserted | Re-verified across all 11 tables; conclusion held. |
| 4 | Row-count assertion written as `dbt_utils.expression_is_true: count(*) = 99441` | **Binder error**, that test evaluates row-by-row inside a `WHERE`, so an aggregate is illegal | First `dbt build`. Rewritten as a singular test. |
| 5 | Staging as views (the dbt convention) | **Made the warehouse non-portable.** The CSV path in `external_location` is relative to the dbt working directory and gets baked into the view, so `olist.duckdb` only worked when queried from `dbt/`, it broke for Tableau, notebooks, and anyone cloning the repo | Querying the warehouse from a different directory. Staging changed to `table`; verified by querying successfully from `/tmp`. |
| 6 | Treated 13,984 and 9,803 as the same "duplicate" figure | Different measures: 13,984 = excess rows beyond distinct `order_id`; 9,803 = orders carrying >1 item. `dbt_utils` reports the latter | Mutation test 3 returned 9,803 where 13,984 was expected. Both now defined explicitly above. |

| 7 | `assert_recency_anchor` asserted `min`/`max` of `fct_orders.purchased_at` | **The test was useless.** It guarded the *input* the anchor was derived from, not the *output*. Swapping `dim_customers`' anchor to `current_date` left `fct_orders` untouched, so the suite stayed green while every customer's recency went ~2,800 days wrong | Mutation test 2, the mutation passed when it should have failed. Rewritten to assert `min(days_since_last_order) = 0`, a necessary property of a historic dataset. Re-mutated: now **FAIL 1**. |
| 8 | Hardcoded `timestamp '2018-10-17 17:30:18'` as the recency anchor | Value happened to be **correct**, but was written from memory before being checked, and hardcoding is fragile regardless | Verified after the fact; it passed by luck. Replaced with a derived `max(purchased_at)`. |
| 9 | Mutation procedure restored the `.sql` but never rebuilt | **State leaked between mutations.** Mutation 3 showed `FAIL 1627` that belonged to mutation 1's stale `dim_products` still sitting in the warehouse | Unexplained failure count during mutation 3. Procedure now forces a full rebuild after every restore. (The leak did usefully quantify the damage: those 623 products carry 1,627 order lines / 213,662.90 BRL.) |

| 10 | `assert_metric_layer_reconciles` checked GMV only | **Order counts were unguarded.** Swapping `count(distinct order_id)` for `count(*)` in the category mart, reporting line items as orders, left the suite green | Mutation test on the metric layer. Added a strict-inequality assertion (`sum(orders) < sum(order_lines)`, 99,154 < 112,279). Re-mutated: now **FAIL 1**. |

| 11 | Target written as `date_diff(...) between 0 and 90` | **NULL for every negative case.** `won_at` is NULL for the 7,158 leads that never converted, and `NULL between 0 and 90` evaluates to **NULL, not false**, SQL three-valued logic. A model trained on the non-nulls would have seen 100% positives and scored a perfect AUC | dbt's `not_null` test: **FAIL 7158**, exactly the never-converted population. Wrapped in `coalesce(..., false)`. |
| 12 | `class_weight="balanced"` on the logistic regression | Added reflexively for imbalance. Strictly worse: AUC 0.6851 vs 0.6870 (marginally **worse**) and Brier 0.2234 vs 0.0909, mean predicted probability 0.4617 against a true rate of 0.1055 | Comparing Brier scores. AUC alone would never have shown it. Removed. |
| 13 | `brew install --cask tableau-public 2>&1 \| tail -25` reported exit code 0 | **The pipe masked the failure.** A pipeline returns the exit code of the LAST command, `tail` always succeeds. brew's real exit code was **1**: the `.pkg` needs `sudo` and a password prompt | `brew list --cask` showed tableau absent despite "success". Re-ran without the pipe. `set -o pipefail` is the general fix. |

| 14 | Both `NTILE(5)` calls in `mart_customer_segments` had no tie-break | **The segmentation was not reproducible.** Only 632 distinct recency values across 96,096 customers means NTILE must cut through tied blocks; without a tie-break it cut in physical row order. Segment counts drifted across rebuilds (Mid 34,617 → 34,620 → 34,628) while the total stayed a correct 96,096 and every test passed. A customer could change segment because the table got rebuilt | Cross-checking the numbers quoted in `tableau/BUILD_GUIDE.md` against a live run, 4 of 5 segment counts had moved. Deterministic tie-break added to both axes; two consecutive `--full-refresh` builds now identical; locked by a test. Mutation (tie-break removed): **FAIL 4**. |
| 15 | `verify_readme_claims.py` held a DuckDB read-only connection, then shelled out to `dbt build` | **The verification script blocked the thing it was verifying.** DuckDB allows many readers but a writer needs exclusive access: holding the lock → returncode 2, `IO Error: Could not set lock on file`; after `close()` → returncode 0, PASS=168. It surfaced as "output unparseable", which looked like a format change and was a lock | Debugging why a regex that matched by hand failed in the script. Connections are now closed before the subprocess runs, and a non-zero returncode is treated as a failure instead of being swallowed. |
| 16 | README referenced `requirements.txt` | **The file did not exist.** Anyone following the README would fail on step one | Verifying every path referenced in the README actually resolves. Generated from the live venv with pinned versions; `pip install --dry-run` confirmed resolvable. |

| 17 | The dbt project built from a clean clone | **Five intermediate models were never committed**; every mart referenced them, so `dbt build` could not succeed | 2026-09 upgrade review of the file list. Reconstructed from this log's contract; validated on synthetic data only. |
| 18 | Lead model evaluated "on unseen Apr–May leads" | **Training labels were not complete at the 2018-04-01 cut** (windows ended 2018-04-01 … 2018-06-29) | Independent review (Codex). Now a retrospective backtest; corrected as-of design in `portfolio.leads`. |
| 19 | `page_lead_volume` "not leakage" | **Look-ahead**: counted future and test-period leads | Review; replaced by a point-in-time count with invariance tests. |
| 20 | Top-decile hits 53 / 51 / 25 | **Tie-dependent** (LR 52–54, GB 49–54, constant baseline expected 27.95) | Recomputed from `outputs/lead_scores_test.csv`. |
| 21 | "No sales operation", "zero right-censoring" | **Unsupported inferences** | Review; restated as hypothesis / assumption. |

See [`docs/defect-log.md`](defect-log.md) for the full list with evidence.

**Rules adopted:**

1. Never state a max, total, or rate derived from a truncated result. Never state a
   figure from memory. Run it or don't say it.
2. A passing test proves nothing until it has been seen to fail. Mutate every assertion
   once and observe the red.
3. Derive orphan and gap counts from anti-joins, not from subtracting two counts.
4. The warehouse must be queryable from outside the build directory, or it isn't real.
5. **Assert the output, not the input it came from.** A test on an upstream value does
   not guard a downstream calculation, mutation testing is what exposes the difference.
6. **Never hardcode a value that can be derived**, even when the hardcoded value is right.
7. **Rebuild after restoring a mutation.** Reverting the file does not revert the warehouse.
8. **Every window function that can hit a tie needs a deterministic tie-break.** `NTILE`,
   `ROW_NUMBER`, `FIRST_VALUE`, without one, the answer depends on physical row order and
   silently changes on rebuild. Test it by building twice and diffing.
9. **A verification script must not hold a lock on what it verifies**, and must treat a
   non-zero exit code as a failure rather than parsing for success.
10. **Every path a doc references must resolve.** Check it mechanically, not by memory.
