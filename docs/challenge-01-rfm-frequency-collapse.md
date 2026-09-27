# Challenge 01: The RFM Segmentation That Had No "F"

## TL;DR

**EN:** I planned a standard RFM segmentation on the Olist dataset, then profiled the data first and found that 96.88% of customers (93,099 of 96,096) had placed exactly one order, collapsing the Frequency dimension to a constant and making textbook RFM meaningless. I dropped the cohort-retention module entirely and rebuilt segmentation on dimensions the data could actually support.

---

## What happened

The project plan called for two customer-behaviour modules on the Olist Brazilian E-Commerce dataset (99,441 orders, 2016-09-04 → 2018-10-17):

1. **RFM segmentation**, score customers on Recency, Frequency, Monetary and bucket them.
2. **Cohort retention**, track how monthly acquisition cohorts repurchase over time.

Before writing either, I profiled the customer table. Olist issues a new `customer_id` per order, so the real person is `customer_unique_id`, joining on the wrong key would have silently reported a 0% repeat rate and I'd never have known the difference. Grouping correctly gave:

| Orders per customer | Customers | % of customers |
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

**96,096 unique customers · 93,099 one-time (96.88%) · 2,997 repeat (3.12%).**

The maximum frequency in the entire dataset is 17 orders, a single customer. The next highest is 9, also a single customer; there is no customer with 8, or with 10–16.

Both planned modules were dead on arrival, for the same underlying reason.

---

## Why it matters

### (a) Technical

**Frequency is a constant, not a variable.** RFM works by ranking customers into quantiles on each of three axes. When 96.88% of the population shares one value, you cannot cut F into quintiles, the quantile boundaries all land on 1. Every standard implementation still *returns output*: `pd.qcut` either throws on duplicate bin edges or, with `duplicates='drop'`, silently returns fewer bins than requested. You get a segmentation table that looks complete and is arithmetic noise. **The failure is silent, which is what makes it dangerous.**

Cohort retention fails for the same reason from the other direction: with a 3.12% repeat rate, every cohort's month-2 retention rounds to near-zero. The curve is flat at the floor. There is no signal to plot, only the visual impression of one.

**The key-choice trap:** had I grouped by `customer_id` instead of `customer_unique_id`, I'd have measured a 100% one-time rate (99,441 orders / 99,441 customer_ids) and concluded the same thing for entirely the wrong reason. Getting the right answer via the wrong key is not getting the right answer.

### (b) Business / decision

This is a **model-validity** failure, and its business cost is that it is invisible downstream. A segmentation deck showing "Champions / Loyal / At-Risk / Hibernating" buckets is exactly what a marketing stakeholder expects to see. They would not ask whether F had variance, they'd ask which segment to target. Budget then gets allocated against buckets that are, in substance, a Recency-and-Monetary sort wearing an RFM label.

The reason for the flat frequency is structural, not a data defect: **Olist is a marketplace intermediary**, not a retailer. The customer relationship belongs to the seller, and shoppers arrive through price comparison rather than brand loyalty. A retention strategy premised on repeat purchase is the wrong strategy for this business model, and the data says so before any model is built.

The defensible move is to report the constraint as the finding. "96.88% of customers never return" *is* the insight. It reframes the question from *"how do we segment for retention?"* to *"is retention even the right lever for a marketplace, or is acquisition efficiency and basket value the real game?"*, which is a materially better question to bring to a stakeholder.

**Analyst-judgment note:** running the RFM anyway and shipping the deck would have been faster, would have looked more impressive, and no one would have caught it. That is precisely why profiling before modelling is not optional.

---

## Analogy

It's like being asked to rank a class by exam attempts when the exam is offered once and 97% of students sat it exactly once. You can still produce a leaderboard, sort by attempts, break ties by score. It will render, it will look authoritative, and every position on it will actually be driven by the tiebreaker. The column you claimed to rank on contributed nothing.

The right answer isn't a better sorting algorithm. It's telling whoever asked: *"almost nobody re-sits this exam, that's the finding, and it changes what you should be asking."*

---

## The fix / decision

**1. Killed the cohort-retention module outright.** Not deferred, not degraded, removed, with the reason documented in the README. A 3.12% repeat rate cannot support a retention curve, and shipping a flat-line chart to imply analysis is worse than shipping nothing.

**2. Rebuilt segmentation on axes with real variance.** Frequency is out. Segmentation runs on Recency and Monetary, plus dimensions Olist genuinely carries: product category, customer state, payment type and instalment count, review score, and delivery performance vs. estimate. These have distribution; F does not.

**3. Kept the profiling result as a headline finding**, with the exact numbers, in the README and the dashboard, rather than burying an inconvenient constraint.

**4. Moved the causal/experimental work to a dataset that can carry it.** Olist has no offers, no treatment/control assignment and no campaign cost fields, so A/B testing and uplift modelling cannot be honestly done on it. Those modules move to the Criteo Uplift dataset (a real randomised controlled trial). Two datasets, two questions, stated plainly, rather than one dataset stretched to cover work it cannot support.

**Why this was the right call:** the alternative was a segmentation that produces plausible output from a degenerate input. The whole point of a monitoring or segmentation asset is that someone acts on it. An analysis that silently fails is worse than one that loudly refuses.

---

## Evidence

| File | What it proves |
|---|---|
| `python/profile_critical.py` | The query that produced the 96.88% / 93,099 / 96,096 figures |
| `python/profile_raw.py` | Table row counts, order date range, order-status mix |
| `sql/checks/customer_frequency_distribution.sql` | Standalone reproducible version of the frequency check |
| `README.md` → "Known constraints" | Where the dropped cohort module and the 96.88% finding are disclosed |
| `README.md` → "Limitations" | Data-quality caveats for the Olist source (the earlier `docs/assumptions_and_limitations.md` was never committed) |

---

*Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle: `olistbr/brazilian-ecommerce`, CC-BY-NC-SA-4.0). All figures produced by a real run against the raw CSVs on 2026-07-16.*
