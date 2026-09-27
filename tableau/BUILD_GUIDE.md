# Tableau Public, Build Guide

Three dashboards, built from five verified extracts. Every step here is one you click;
none of it can be generated for you, because `.twbx` is a binary Tableau writes itself.

**What is already done:** the extracts in `extracts/` are round-trip verified against the
warehouse, row counts, NULL counts, and money to the cent. Their GMV reconciles across
four independent aggregation paths at **15,786,203.57 BRL**.

**The rule this build follows: Tableau performs no arithmetic.** Every ratio, AOV,
cancel rate, late-delivery rate, freight share, share-of-month, is already computed in
SQL, in `dbt/models/marts/`. Tableau plots columns. This is deliberate, and it's worth
being able to say why:

- The metric definition lives in one auditable place, not split between a repo and a
  workbook nobody can diff.
- Two people cannot quietly compute AOV two different ways.
- The BI tool becomes replaceable. Swap Tableau for Power BI or Metabase and the business
  logic doesn't move.

If you find yourself writing a calculated field with a `/` in it, stop, the metric
belongs in dbt.

---

## 1. Setup (~5 min)

1. Download **Tableau Public** (free, native macOS): <https://public.tableau.com/app/discover>
2. Create a Tableau Public account. **Note:** Tableau Public saves to the web and is
   **public by default**, that's what gives you the shareable link for your CV, but it
   also means don't put anything private in it. This dataset is public and licensed
   CC-BY-NC-SA-4.0, so it's fine.
3. Open Tableau Public → **Connect → To a File → Text file** → select
   `tableau/extracts/mart_monthly_performance.csv`

### Check the data types immediately

Tableau infers types on load and it gets `purchase_month` wrong more often than not.
In the data source tab, confirm:

| Field | Must be |
|---|---|
| `purchase_month` | **Date** (not string) |
| `month_label` | String, this is the display label, keep it as text |
| `gmv_brl`, `aov_brl`, all `*_pct` | **Number (decimal)** |
| `orders`, `*_orders`, `customers` | **Number (whole)** |

If a numeric column loaded as string, the CSV had an unexpected value in it, don't
convert it in Tableau, come back and check the extract. That would mean the round-trip
verification missed something and I'd want to know.

---

## Dashboard 1: Business Performance Monitor

**Source:** `mart_monthly_performance.csv` (20 rows)
**Question it answers:** what is happening to the business, and is anything breaking?

### Sheet 1.1: GMV & Orders trend

1. Drag `purchase_month` → Columns. Right-click → **Exact Date** → change to **Month**
   (continuous, green).
2. Drag `gmv_brl` → Rows. Mark type: **Bar**.
3. Drag `orders` → Rows (second axis). Mark type: **Line**.
4. Right-click the second axis → **Dual Axis**. Right-click either axis →
   **Synchronize Axis** → **uncheck** it (they're different units, GMV in BRL, orders as
   a count; forcing a shared scale would make one of them unreadable).
5. Title: `GMV and Order Volume, Jan 2017 to Aug 2018`

**Why bars for GMV and a line for orders:** GMV is a quantity accumulated within each
month, a bar, which is a magnitude you compare across discrete periods. Orders is the
count driving it, and a line reads as a rate of activity over time. Two encodings on one
axis pair says "these are related but not the same thing".

**Say this in an interview:** the axis deliberately starts at zero for GMV. Truncating a
bar-chart axis exaggerates change and is the most common way a dashboard lies without
containing a single wrong number.

### Sheet 1.2: AOV trend

1. `purchase_month` → Columns (Month, continuous).
2. `aov_brl` → Rows. Mark: **Line**.
3. Right-click the axis → Edit Axis → **uncheck Include zero**.
4. Title: `Average Order Value (BRL)`

**Why this axis does NOT start at zero, when 1.1 does:** AOV ranges 147.39 – 173.88. It's
a *ratio*, not a magnitude, nobody compares its area to zero, they read its movement.
Forcing zero would flatten a real 18% swing into a straight line. The rule isn't "always
start at zero"; it's "start at zero for magnitudes you compare by size, and don't for
ratios you read by movement". Be ready to defend which one this is.

### Sheet 1.3: Delivery vs satisfaction

1. `purchase_month` → Columns (Month).
2. `late_delivery_rate_pct` → Rows. Mark: **Line**.
3. `avg_review_score` → Rows (second axis). Mark: **Line**. → **Dual Axis**, do **not**
   synchronize.
4. Colour the two lines distinctly. Title: `Late Deliveries vs Review Score`

**This is the most interesting chart in the project.** The worst late-delivery month
(2018-03, **18.96%**) is the worst-reviewed month (**3.75**). The second-worst late month
(2018-02, 14.14%) is the second-worst reviewed (3.83).

**Be careful how you say this.** Two lines moving together across 20 points is a
*hypothesis*, not a finding. n=20, and both series could be driven by something else, 
volume, seasonality, a category-mix shift. The honest framing: *"these move together and
it's worth testing; here's how I'd test it."* Claiming causation from this chart is
exactly what an interviewer is waiting for you to do.

### Assemble Dashboard 1

- Size: **Automatic** (or Desktop 1366×768 fixed if you want control).
- Layout: 1.1 across the top full width, 1.2 and 1.3 side by side below.
- Add a text object at the bottom, verbatim:
  > Analysis window Jan 2017 – Aug 2018. Excludes 349 of 99,441 orders (0.35%): a
  > 2016 pilot period (one month has zero orders) and a post-2018-08-28 export tail.
  > Charting the raw range shows fake growth from 4 orders/month and a fake collapse
  > back to 4. Source: Olist public dataset (CC-BY-NC-SA-4.0).

**Put that caption on the dashboard, not in a footnote.** It's the single strongest signal
in the whole workbook that you looked at your data. See `docs/challenge-04-phantom-trend.md`.

---

## Dashboard 2: Category & Geography Diagnosis

**Sources:** `mart_category_performance.csv` (1,246 rows), `mart_state_performance.csv` (533)
**Question it answers:** where is the GMV, and where is margin leaking?

> Add these as **separate data sources** (Data → New Data Source). Do **not** join them, 
> they're at different grains (month × category vs month × state) and joining would fan
> out exactly the way `challenge-03` documents. Two sources, two sheets, filters applied
> per sheet.

### Sheet 2.1: GMV by category

1. From `mart_category_performance`: `product_category` → Rows, `gmv_brl` → Columns.
2. Sort descending by `gmv_brl`.
3. Filter → `product_category` → Top 15 by SUM(gmv_brl). (74 categories on one axis is
   unreadable; the tail is a long-tail chart of its own if anyone asks.)
4. Mark: **Bar**. Title: `GMV by Category, full window`

Expect health_beauty (1,435,611), watches_gifts (1,302,074), bed_bath_table (1,241,075) on top.

### Sheet 2.2: Freight share by category

1. `product_category` → Rows, `freight_share_pct` → Columns.
2. **Important:** this column is already a percentage computed in SQL. Set its aggregation
   to **Average**, not Sum. Summing a percentage is meaningless and Tableau will happily
   do it, this is the most common way a "no arithmetic in the dashboard" rule still
   produces a wrong number.
3. Sort descending. Same Top-15 filter.
4. Mark: **Bar**, coloured by `freight_share_pct` (sequential, single hue).

**The insight:** freight share ranges **7.7%** (watches_gifts) to **19.1%**
(furniture_decor). Heavy, bulky goods spend a fifth of their revenue getting there. In a
marketplace, that's a margin story and a pricing question, the categories with the
highest GMV are not the categories with the best economics.

### Sheet 2.3: Map by state

1. From `mart_state_performance`: double-click `customer_state`. Tableau will geocode it, 
   confirm it maps to **Brazil / State**, not somewhere else. Bottom-right will show
   "unknown" if any code failed; expect **0 unknown** across the 27 codes.
2. `gmv_brl` → Colour. `avg_delivery_days` → Size.
3. Add `freight_share_pct` (aggregation: **Average**) to Tooltip.
4. Title: `GMV, Delivery Time and Freight Burden by State`

### Assemble Dashboard 2

- 2.3 (map) on the left, 2.1 and 2.2 stacked on the right.
- Add a **month filter** and apply it to all three: right-click the filter →
  **Apply to Worksheets → All Using This Data Source**, note you'll need to do this once
  per data source, since they're separate.

---

## Dashboard 3: Customer Segments

**Source:** `mart_customer_segments.csv` (96,096 rows, 14.6 MB, largest extract)
**Question it answers:** who are these customers, and is retention even the right lever?

### Sheet 3.1: R/M matrix

1. `r_score` → Columns, `m_score` → Rows. Both must be **Dimensions** (blue), if they're
   green measures, right-click → Convert to Dimension.
2. `customer_unique_id` → Colour, aggregation **Count Distinct**.
3. Mark: **Square**. This is a heatmap of population across the 25 R×M cells.
4. Add `lifetime_payment_brl` (aggregation **Average**) to Tooltip.
5. Title: `Customer Distribution, Recency × Monetary`

**Why there is no F axis, and why this is the point of the dashboard:** 96.88% of these
customers (93,099 of 96,096) ordered exactly once. Frequency is a constant. You cannot
quantile a constant, and every standard RFM implementation will still hand you output,
which is what makes it dangerous. See `docs/challenge-01-rfm-frequency-collapse.md`.

### Sheet 3.2: Segment sizes

1. `rm_segment` → Rows, `customer_unique_id` (Count Distinct) → Columns.
2. Sort descending. Add `lifetime_payment_brl` (Average) to Label.

Expect exactly: **Mid 34,628** (36.03%), **Lapsed low-value 15,871** (16.52%),
**Recent high-value 15,847** (16.49%), **Lapsed high-value 14,931** (15.54%),
**Recent low-value 14,819** (15.42%). Sum = 96,096.

> These counts are reproducible and asserted by `dbt/tests/assert_segments_reproducible.sql`.
> They were not always: NTILE splits tied blocks to keep buckets equal, and with only 632
> distinct recency values across 96,096 customers, it was cutting through ties in physical
> row order, so the counts drifted on every rebuild (Mid went 34,617 → 34,620 → 34,628)
> while the total stayed a correct 96,096 and nothing failed. Both NTILEs now carry a
> deterministic tie-break. If Tableau shows different numbers than the ones above, the
> extract is stale, regenerate it with `python/export_tableau.py`.

### Sheet 3.3: The headline number

1. Drag `customer_unique_id` → Text, aggregation **Count Distinct**.
2. Add `is_repeat_customer` → Columns.
3. Mark: **Text** (a big-number tile).
4. Title: `Repeat Customers: 2,997 of 96,096 (3.12%)`

**Make this tile prominent.** It's the most important number on the dashboard and it's the
one that reframes the question: Olist is a marketplace intermediary, the customer
relationship belongs to the seller, and shoppers arrive by price comparison, not loyalty.
A retention strategy is probably the wrong lever. Acquisition efficiency and basket
economics are the real game.

An interviewer will respect *"the data told me my planned analysis was wrong, so I changed
the analysis"* far more than a Champions/At-Risk deck that quietly means nothing.

---

## Publish

1. **File → Save to Tableau Public As…**, you'll need to be signed in.
2. Name it something a recruiter can parse, without a company name in the title:
   `E-Commerce Performance & Customer Analytics (public marketplace data)`. Keep the dataset
   attribution (Olist, CC BY-NC-SA 4.0) in the description and the source caption.
3. Copy the public URL → into your CV, and into the repo README.
4. In the workbook description, state: analysis window, the 0.35% exclusion, and that all
   metrics are computed in SQL with the dbt repo linked.

**Before you publish, check:** Tableau Public is public. Everything in this workbook is
derived from a CC-BY-NC-SA-4.0 public dataset, so there's nothing sensitive, but form the
habit of asking before you click, because the same button behaves the same way on data
that isn't public.

---

## What to expect when an interviewer opens this

| They'll ask | Your answer lives in |
|---|---|
| "Why does your data start in 2017 when the dataset starts in 2016?" | `docs/challenge-04-phantom-trend.md` |
| "Where's the F in your RFM?" | `docs/challenge-01-rfm-frequency-collapse.md` |
| "How do you know your GMV is right?" | `docs/challenge-03-silent-fanout.md` + four marts reconciling to 15,786,203.57 |
| "Why is the metric logic not in Tableau?" | The rule at the top of this file |
| "Are late deliveries causing bad reviews?" | Sheet 1.3, and the honest answer is "that's a hypothesis, here's how I'd test it" |

---

*Extracts generated by `python/export_tableau.py`, which round-trip verifies every file
against the warehouse and deletes any extract that fails rather than shipping it.
Regenerate with: `.venv/bin/python python/export_tableau.py`*
