# Three-minute demo script

For a screen-share or a recorded walkthrough. Open `dashboard/decision-dashboard.html` before you start;
nothing else needs to be running. Times are cumulative.

## 0:00 — What this is (20 s)

> "This is one offline HTML file, an independent case study on public data. It covers two separate
> datasets: orders from a Brazilian online marketplace and a randomised online-ad test. They are never
> joined, because the marketplace data has no treatment or cost data and the experiment's features are
> anonymised. The yellow banner matters: these marketplace numbers come from extracts of an earlier
> full-data run that were already in the repository. This page recomputes every total from those
> extracts; it does not re-run the pipeline."

Point at the **HISTORICAL** and **RECOMPUTED** badges. Dataset publishers and licences are on the
**Definitions & sources** tab.

## 0:20 — Overview: one number done right (40 s)

- Read the tiles: 99,092 orders, BRL 15,786,203.57 GMV, late-delivery rate **6.79%**.
- Point at the sub-line "6,532 late ÷ 96,211 delivered" and at the callout below it.

> "If you average the twenty monthly late rates you get 5.89%. That gives an 800-order month the same
> weight as a 7,500-order month. The page always sums numerators and denominators first."

- Hover the late-delivery line, or press **Show table**: every chart has a real table alternative.
- Point at "Active customers: Unavailable":

> "Distinct customers can't be added across months, so the page says unavailable instead of inventing
> a number."

## 1:00 — Filters are scoped to what the data supports (30 s)

- Set **From 2018-01, To 2018-03**. The numbers change.
- Open **States**. The late rate by state reads **Unavailable**:

> "The historical state extract stores only a percentage per state-month, not the counts behind it.
> Averaging those percentages across months would be wrong, so it is refused. Switch to one month and
> the per-state value appears."

- Mention the scope note: the category, state and payment filters never cross views, because no extract
  has a joint grain.

## 1:30 — Lead scoring: where the original analysis was wrong (40 s)

Open **Lead scoring** and read the three callouts in order:

1. "The training labels weren't complete at the cut. A lead contacted on 1 January has an outcome window
   ending 1 April, and the test started 1 April. So this is a retrospective backtest."
2. "One feature counted future leads on the same landing page."
3. "The famous 53-out-of-265 depended on row order: with ties the honest answer is 52.86, anywhere from
   52 to 54."

> "And even 53 isn't '53 extra wins'. It's ranking quality on leads that were worked anyway. To claim
> extra wins you need a randomised prioritisation test."

## 2:10 — Experiment: effect, not significance (35 s)

Open **Experiment**.

> "Assigning users to the campaign raised conversion by 0.115 percentage points, 95% CI 0.108 to 0.122,
> about 1.15 extra conversions per thousand users. The p-value is around 10^-178, but at 14 million users
> that only says 'not exactly zero'. The naive exposed-vs-control number, +2,676%, is selection, not an
> effect."

Type a cost of `2.5` and a value of `5` in the **hypothetical** calculator:

> "Neither dataset has costs, so this is arithmetic on assumptions you supply."

## 2:45 — Close (15 s)

Switch the data source to **Synthetic sample**:

> "This is generated data that runs through the real dbt project from a clean clone in about twenty
> seconds, with no credentials. Here the averages combine exactly, because the synthetic extracts carry
> the counts. The memo tab turns all of this into four experiments to run, not gains I've already proven."

---

**If asked "what did you do vs the AI?":** Herui directed the portfolio task. This upgrade retains historical artifacts from the existing repository; their original personal authorship is not independently verified here. Claude implemented and tested this upgrade; Codex independently reviewed key source, evidence and displayed screenshots.
Before a live demo, reproduce the numbers you plan to mention (commands in `docs/evidence.md`), so that
every number you mention is one you have produced yourself.
