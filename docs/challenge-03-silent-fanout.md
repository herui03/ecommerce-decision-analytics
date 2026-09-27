# Challenge 03: The Join That Invented 4.18 Million Reais

## TL;DR

**EN:** Joining `orders` to `order_items`, `order_payments` and `order_reviews` in one
four-way join inflated payment value by 26% (+4,179,056.58 BRL) while simultaneously
dropping 1,525 orders, with no error and no warning. I pre-aggregated each child to
order grain before joining, and locked it down with a row-count assertion and a
cent-level reconciliation test.

---

## What happened

I needed an order-grain fact table: one row per order, carrying basket value, payment
detail, and review score. The obvious SQL is one join:

```sql
FROM orders o
JOIN order_items    i ON i.order_id = o.order_id
JOIN order_payments p ON p.order_id = o.order_id
JOIN order_reviews  r ON r.order_id = o.order_id
```

Before writing it, I had already probed each table's true grain. Only `orders` is one
row per order:

| Table | Rows | Distinct `order_id` | Duplicate rows |
|---|---:|---:|---:|
| orders | 99,441 | 99,441 | 0 |
| order_items | 112,650 | 98,666 | 13,984 |
| order_payments | 103,886 | 99,440 | 4,446 |
| order_reviews | 99,224 | 98,673 | 551 |

So I ran the naive join deliberately, to measure the damage rather than assume it:

| | Correct | Naive four-way join |
|---|---:|---:|
| Rows | 99,441 | **117,329** (1.18×) |
| Distinct orders | 99,441 | **97,916** |
| Item revenue | 15,843,553.24 | **16,490,809.55** (+4%) |
| Payment value | 16,008,872.12 | **20,187,928.70** (+26%) |

It fails in **both directions at once**. It invents **4,179,056.58 BRL** of payment value
that does not exist, and it silently discards **1,525 orders**. The query returns
successfully. Nothing in the output says anything is wrong.

---

## Why it matters

### (a) Technical

**Two distinct bugs wearing one costume.**

*The inflation* is a Cartesian product. An order with 3 items and 2 payment rows produces
3 × 2 = 6 rows, and `sum(payment_value)` counts each payment three times. The multipliers
compound: payment inflates 26% while items inflate only 4%, because the payment
duplication (4,446) multiplies against the item duplication (13,984), not against 1.

*The loss* is the `INNER JOIN`. 775 orders have no items and 768 have no review, so an
inner join drops any order missing a child, 1,525 of them. **The direction is the
tell:** an inner join can only ever shrink the spine, and a fan-out can only ever grow
it. Seeing 117,329 rows over 97,916 distinct orders means both were happening
simultaneously, and they partially masked each other. Had 1,525 fewer orders and a
1.18× fan-out cancelled out more exactly, the row count would have looked *correct*.

**Why no error is possible.** SQL has no concept of "intended grain". `JOIN` on a
non-unique key is legal, ordinary, and usually what you want. The engine cannot know
that `sum(payment_value_brl)` was supposed to mean "money collected" rather than "sum of
this column across whatever rows exist". Grain is a semantic contract that lives entirely
outside the language, so if you don't assert it, nothing does.

### (b) Business / decision

**A 26% GMV overstatement is not an analytics bug, it's a reporting incident.** Payment
value is the number that becomes revenue in a dashboard. Inflated by a quarter and
published, it flows into growth rates, category rankings, campaign ROI, and cost-per-
acquisition, every one of which is a ratio with this number on top. The error doesn't
stay in one chart; it propagates into every decision made downstream of it.

**The number is plausible, which is what makes it lethal.** A bug that returns 10× or a
negative total gets caught by whoever reads the chart. 20.19M against a true 16.01M looks
like a good quarter. There is no smell test that catches it, the only thing that catches
it is an assertion that the total after the join equals the total before it.

**And it's directional in the worst way.** It overstates revenue *and* understates order
count, which means average order value is inflated from both ends at once. AOV is exactly
the metric a marketing stakeholder uses to justify spend.

**Analyst-judgment note:** the naive query is shorter, reads more naturally, and would
have shipped. Nobody reviewing the SQL would flag it, because it looks like every join
anyone writes. This is why grain gets asserted in the pipeline rather than checked in
code review, code review does not catch this class of bug, and the numbers do not look
wrong.

---

## Analogy

You're counting a restaurant's takings. Each table's bill is on one slip, and each slip
is stapled to a copy of every dish ordered and every card used to pay.

If you total the bill amount once per *sheet of paper* instead of once per *bill*, a table
that ordered 3 dishes and split across 2 cards gets its bill counted six times. Your
takings look great.

Meanwhile you've thrown out every bill with no dishes attached, the cancelled tables, 
so you also think you served fewer tables than you did. Revenue up, covers down, spend per
table way up. Every one of those numbers is wrong, all of them are wrong in a flattering
direction, and the arithmetic on every single sheet was correct.

Nobody notices, because 20 million looks like a fine month.

---

## The fix / decision

**1. Aggregate each child to order grain first, in its own model.** `int_orders__items_agg`,
`int_orders__payments_agg`, `int_orders__reviews_agg`, each collapses to exactly one row
per `order_id`, tested `unique`. The fan-out cannot happen if there is nothing to fan out.

**2. `orders` is the spine, and every join is a LEFT JOIN.** The fact table must contain
every order that exists, including the ones missing children. An inner join is a business
decision (*"exclude orders with no items"*) disguised as a technical one, and it was never
a decision anyone made.

**3. Preserve NULLs; never zero-fill.** NULL means "no record exists"; 0.00 means "recorded
as zero". Collapsing them makes a cancelled order indistinguishable from a free one, and
would bury the single delivered-but-unpaid order. Explicit `has_no_items` /
`has_no_payment` / `has_no_review` flags surface the gaps instead of hiding them.

**4. Assert the grain mechanically.** `dbt_utils.equal_rowcount` against
`stg_olist__orders`: the fact must have exactly 99,441 rows, forever.

**5. Assert the money.** A singular test compares totals in the fact against totals at
source grain, tolerance 0.01. Observed difference: **0.00**.

**6. Prove the assertions can fail.** A green test suite proves nothing until it has been
seen red. Both layers were deliberately broken:

| Mutation | Caught by |
|---|---|
| `items_agg` grain shattered (`group by 1, product_id`), compiles fine | 🔴 `unique` **FAIL 3236**, 7 downstream models **SKIPPED** |
| `enriched` `LEFT JOIN` → `INNER JOIN`, grain intact, orders dropped | 🔴 `equal_rowcount` **FAIL 775**, reconciliation **FAIL 1** |

The 775 is exactly the population of no-item orders. The defences catch the right thing,
for the right reason, at the right layer.

**Why this was the right call:** the pipeline now cannot silently produce a wrong GMV. It
can produce a *failing build*, which is the only acceptable alternative.

---

## Evidence

| File | What it proves |
|---|---|
| `python/demo_fanout.py` | The measured damage: 117,329 rows / 97,916 orders / 20,187,928.70 payment |
| `python/probe_grain.py` | The true grain of all 11 tables, established before any model was written |
| `dbt/models/intermediate/int_orders__items_agg.sql` | The fix, aggregate to order grain before joining |
| `dbt/models/intermediate/int_orders__enriched.sql` | Spine + LEFT JOINs + preserved NULLs + data-quality flags |
| `dbt/models/intermediate/_intermediate__models.yml` | `equal_rowcount` assertion against `stg_olist__orders` |
| `dbt/tests/assert_orders_enriched_reconciles.sql` | Cent-level money reconciliation, observed difference 0.00 |
| `docs/data-verification.md` | Full reconciliation (residual 0.00) and mutation-test results |

---

*Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle: `olistbr/brazilian-ecommerce`,
CC-BY-NC-SA-4.0). All figures produced by real runs on 2026-07-16. dbt build at time of
writing: 104 PASS / 0 ERROR.*
