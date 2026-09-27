# Challenge 04: The Growth Story That Wasn't There

## TL;DR

**EN:** Charted naively, Olist shows explosive growth from 4 orders a month to 7,544 and
then a total collapse back to 4. Neither end is real, 2016 is a pilot (with one month
missing entirely) and the data is simply cut off after 2018-08-28. I set an explicit
analysis window of 2017-01 → 2018-08, keeping 99,092 of 99,441 orders (99.65%) and
discarding 349 (0.35%) that are export artifacts rather than business.

---

## What happened

The first deliverable was a monthly business-performance trend, the chart everyone opens
first. The obvious query is `group by date_trunc('month', purchased_at)`. Before plotting
it, I looked at the monthly distribution:

| Month | Orders |
|---|---:|
| 2016-09 | 4 |
| 2016-10 | 324 |
| **2016-11** | **, (no row at all)** |
| 2016-12 | 1 |
| 2017-01 | 800 |
| … | ramping |
| 2017-11 | 7,544 |
| … | plateau ~6,000–7,300 |
| 2018-08 | 6,512 |
| 2018-09 | **16** |
| 2018-10 | **4** |

Two separate problems, and a third hiding inside one of them.

**2016 is not a business.** Four orders, then 324, then a month that does not exist in the
source at all, I confirmed 2016-11 returns exactly 0 rows, so it's a genuine hole rather
than an aggregation artifact, then a single order in December.

**The end is a cut, not a decline.** Daily counts locate it precisely:

```
2018-08-25   69
2018-08-26   73
2018-08-27   67
2018-08-28   44
2018-08-29   14   <- the cut
2018-08-30    4
2018-08-31    1
2018-09-03    4      then 1-4 orders on scattered,
2018-09-06    3      non-consecutive days through
...                  to 2018-10-17
```

A business does not go from 67 orders a day to 1 and then dribble out single orders on
random days for seven weeks. That is an export cutoff with stragglers whose
`purchase_date` happens to fall later.

**And 2018-10's GMV came back NULL.** All four October orders are `canceled` with no item
records, they carry payments (80.38, 197.55, 222.03, 89.71 BRL) but no basket. The NULL
is correct behaviour, and it vindicated an earlier decision not to zero-fill: "no item
record exists" is genuinely different from "the basket was worth zero".

---

## Why it matters

### (a) Technical

**The chart renders perfectly.** There is no error, no gap warning, no null. `date_trunc`
plus `group by` is correct SQL over correct data. Every point on the line is a true count
of rows that genuinely exist. The output is arithmetically flawless and semantically
worthless at both ends.

**The missing month is worse than a wrong number.** 2016-11 has no row, so `group by`
simply omits it and the line connects October to December as though they were adjacent.
A chart cannot show you a month that isn't in the result set, the gap is invisible by
construction. This is the one that a date spine exists to catch: without a conforming
date dimension, absence and zero are indistinguishable in a `group by`.

**Boundary months are structurally, not randomly, wrong.** Any time-series cut at an
arbitrary timestamp has a partial period at each end. It's not noise you can average out
it's a systematic undercount whose size depends entirely on where the knife fell. Here
2018-08 survives because the cut landed on the 29th (~2.6% of the month lost); had it
landed on the 5th, August would have looked like a catastrophe too.

### (b) Business / decision

**This is the single most common way a portfolio project embarrasses its author.** A
hiring manager who has seen this dataset before, and Olist has 577,164 downloads, knows
the tail is fake. A dashboard opening with a cliff says one of two things: the analyst
didn't look at their data, or they looked and shipped it anyway. Both are
disqualifying, and neither requires the interviewer to check any of your SQL.

**The false story is directionally seductive.** "1,800× growth then collapse" is a
*narrative*. It invites explanation, market entry, competitor, seasonality, a crisis, 
and every one of those explanations would be fabricated. The moment you write a
"so-what" under that chart, you are inventing business history from a file-export
boundary.

**Growth rates are the metric this destroys.** MoM growth is a ratio with the previous
month on the denominator. From 4 to 324 is +8,000%. From 6,512 to 16 is −99.75%. Any
average, trendline, or forecast fitted across the raw range inherits both. And unlike an
absolute number, nobody eyeballs a growth rate for plausibility, that's what they built
it to tell them.

**The honest move is to state the window, not to quietly trim it.** Dropping 0.35% of
rows silently would be indistinguishable from cherry-picking. Declared in the README with
the exclusion counted and the reason given, it is exactly what an analyst is paid to do:
decide what data can answer the question, and say so out loud.

**Analyst-judgment note:** the raw chart is more impressive. It has a growth story, a
dramatic peak, and a crisis. The honest chart is a plateau. Choosing the plateau is the
job.

---

## Analogy

You're handed a shop's till receipts and asked how business is going.

The first three are from the soft-launch week when only the owner's friends came, and
one week's worth is missing from the box entirely. The last handful are from the morning
someone started boxing up the receipts, plus a few stragglers that drifted in while the
box sat by the door.

Plot takings per week across everything in the box and you'll report a shop that exploded
out of nowhere and then died last month. The shop is fine. You measured the box.

The receipts aren't lying. They're just not all *from the period you think you're
measuring*, and the ones at the edges are from the packing, not the trading.

---

## The fix / decision

**1. Set an explicit window: 2017-01 → 2018-08.** Twenty consecutive months, verified no
gaps, thinnest month 800 orders, a real ramp, not a pilot.

**2. Quantify and publish the cost.**

| | Orders |
|---|---:|
| In window | 99,092 (**99.65%**) |
| Excluded, 2016 pilot | 329 |
| Excluded, 2018 tail | 20 |
| Total excluded | **349 (0.35%)** |

Sacrificing 0.35% of rows to remove 100% of the phantom trend is not a close call.

**3. The window lives in `dbt_project.yml` vars, not scattered in WHERE clauses.** One
definition, one place to change it, and the reasoning sits in a comment beside it.

**4. The fact keeps everything; the metric layer filters.** `fct_orders` retains all
99,441 orders and carries an `is_in_analysis_window` boolean. The spine records what
happened, filtering is a reporting decision and belongs in the reporting layer. Anyone
who wants the pilot data can have it; they just have to ask for it explicitly.

**5. Assert the window.** `assert_metric_layer_reconciles` requires exactly 20 months and
exactly 99,092 orders, and reconciles the metric layer's GMV against both facts. Mutation
test: removing the window filter turns it red immediately.

**Why this was the right call:** the alternative is a chart that invites a fabricated
explanation. There is no version of this where the raw range is defensible, only versions
where nobody has looked yet.

---

## Evidence

| File | What it proves |
|---|---|
| `dbt/dbt_project.yml` → `vars` | The window, defined once, with the full reasoning beside it |
| `dbt/models/marts/fct_orders.sql` | `is_in_analysis_window` flag, fact keeps all 99,441 rows |
| `dbt/models/marts/mart_monthly_performance.sql` | The 20-month trend, window applied, all ratios in SQL |
| `dbt/tests/assert_metric_layer_reconciles.sql` | Asserts exactly 20 months / 99,092 orders, and GMV against both facts |
| `docs/data-verification.md` → "The analysis window" | Monthly and daily distributions, exclusion counts, mutation results |

---

*Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle: `olistbr/brazilian-ecommerce`,
CC-BY-NC-SA-4.0). All figures from real runs on 2026-07-16. dbt build at time of writing:
158 PASS / 0 ERROR.*
