# E-commerce Decision Analytics — overview

An online marketplace needs to see where deliveries run late, where freight eats into order value, whether a lead
score helps sales prioritise, and whether an ad campaign lifted conversions. This project answers those questions
with a single offline HTML dashboard. The dashboard recomputes every KPI for the selected months and shows its
numerator and denominator. When the data cannot support a figure, it says the figure is unavailable. It is an
independent case study on two public datasets, which are analysed separately.

**[Open the dashboard](../dashboard/decision-dashboard.html)** (download and open in any browser) ·
**[README and setup](../README.md)** · **[3-minute demo script](demo-3min.md)**

![Dashboard overview: KPI tiles with numerator ÷ denominator under each value](screenshots/overview.png)

## What it does

- **Eight views:** marketplace overview, categories, customer states, payment methods, lead scoring, ad
  experiment, metric definitions and sources, and a decision memo.
- **Scoped filters:** a month range with presets, plus category, state and payment filters. Each filter
  applies only where the data has that grain.
- **Traceable KPIs:** each KPI tile shows numerator ÷ denominator, and every chart can switch to a table.
- **Break-even calculator:** for the ad campaign, using cost and value figures you enter.
- **Portable:** runs from one file of about 0.9 MB, with no server and no network access. It supports
  keyboard navigation, light and dark themes, and phone-width screens.
- **Reproducible:** a generated sample rebuilds the whole pipeline in about 20 seconds, without accounts or
  credentials.

## Key results (historical public data, recomputed)

- **Late deliveries: 6.79%** of delivered orders (6,532 ÷ 96,211, January 2017 to August 2018). Averaging the
  20 monthly rates would give 5.89%, because it weights a month with 750 delivered orders the same as one
  with 7,289.
- **Ad campaign: +0.115 percentage points** of conversion from assigning users to the campaign (95% CI
  0.108–0.122), about 1.15 extra conversions per 1,000 users. Comparing exposed users with the control group
  gives +2,676%, which reflects selection bias (who ended up exposed) rather than the campaign's effect.
- **Lead ranking (retrospective backtest, AUC 0.687):** the top 10% of held-out leads contained about 52.9
  wins, against about 28 expected from a score with no information. This measures ranking quality, not extra
  sales; a randomised prioritisation test would be needed to measure those.

## Skills and tools

| Area | What the project contains |
|---|---|
| Data modelling | SQL, dbt, DuckDB: 11 staging → 5 intermediate → 12 mart models with declared grain |
| Data quality | 143 data tests on the sample build; checks for fan-out, lost orders and money totals; mutation testing (6 of 6 injected defects caught) |
| Metrics | Weighted rates, integer-cent money, and explicit "unavailable" states when a grain cannot support a figure |
| Experimentation | Intention-to-treat effect with confidence intervals, complier effect with its assumptions, minimum detectable effect, break-even arithmetic |
| ML evaluation | Label maturity, look-ahead leakage, point-in-time features, top-k evaluation with tied scores |
| Front end | Vanilla JavaScript and SVG charts, keyboard access, table alternatives, strict Content-Security-Policy |
| Reproducibility | Deterministic synthetic data, byte-identical rebuilds, CI on Python 3.11 and 3.12, Chromium end-to-end tests |

## 3-minute demo

| Time | Show | Point |
|---|---|---|
| 0:00 | Header and source badges | Two separate public-data studies; each number is labelled historical, recomputed or synthetic |
| 0:20 | Overview tiles | 6.79% = 6,532 ÷ 96,211; rates are summed before dividing; "unavailable" where the data cannot support a figure |
| 1:00 | Month filter, States view | Filters apply only where the data has that grain |
| 1:30 | Lead scoring | Immature labels, a look-ahead feature and tie-dependent hit counts, each identified and corrected |
| 2:10 | Experiment | Effect size and interval rather than the p-value; the break-even calculator |
| 2:45 | Synthetic sample, Decision memo | The pipeline rebuilds in about 20 seconds; recommendations are framed as experiments to run |

Full script: [`docs/demo-3min.md`](demo-3min.md).

| Experiment | Lead scoring | Decision memo |
|---|---|---|
| ![Experiment view](screenshots/experiment.png) | ![Lead scoring view](screenshots/lead-scoring.png) | ![Decision memo view](screenshots/decision-memo.png) |

## Run it

To view the dashboard, download [`dashboard/decision-dashboard.html`](../dashboard/decision-dashboard.html) and
open it; no installation is needed. To rebuild it with Python 3.11 or 3.12:

```bash
git clone https://github.com/herui03/ecommerce-decision-analytics.git
cd ecommerce-decision-analytics
scripts/setup.sh    # virtualenv with pinned packages
make sample         # generated data -> dbt build -> extracts -> models -> dashboard (~20 s)
make verify         # committed dashboard and generated docs match a fresh build
```

More commands and the optional full-data path are in the [README](../README.md#run-it-yourself).

## Data, scope and limits

- **Data in the repository:**
  - Four metric extracts aggregated from the public Olist datasets by an earlier full-data run.
  - 2,655 row-level held-out leads with model scores, identified by the dataset's anonymised lead IDs.
  - Six aggregate counts from the Criteo experiment dataset.
  - A generated synthetic sample. It describes no real business.
- **Provenance:**
  - The historical extracts and lead scores are recomputed from the committed files here; the earlier run
    was not re-executed.
  - The raw public files could not be downloaded in the build environment, so the historical files have not
    been compared row by row with the source datasets.
  - Five intermediate dbt models missing from the original project were reconstructed. They are validated on
    the synthetic sample only.
- **Analysis limits:**
  - The marketplace data has no cost, margin or randomised treatment, so no causal or ROI claims are made
    about it.
  - The lead-scoring result is a retrospective backtest.
  - The corrected lead design has been run only on synthetic data.
- **Validation:**
  - The synthetic dbt build runs 171 nodes (28 models + 143 data tests).
  - Test suites: 108 Python tests, 9 JavaScript tests, and a Chromium run (13 tests, 74 checks).
  - Recomputed totals match reference values exactly, for example 99,092 orders and BRL 15,786,203.57 GMV.
  - Rebuilds are byte-identical.
  - Logs and the defect history are in [`docs/evidence.md`](evidence.md) and
    [`docs/defect-log.md`](defect-log.md).

## Data sources and licences

- **Marketplace data:** the Brazilian E-Commerce Public Dataset by Olist and the Marketing Funnel by Olist,
  both CC BY-NC-SA 4.0 (attribution Olist, non-commercial).
- **Advertising data:** the Criteo Uplift Modeling Dataset (Criteo AI Lab); only six aggregate counts are used.

Details are in [`docs/source-manifest.md`](source-manifest.md). Code is MIT-licensed.

Herui Dou, MSc Business Analytics, NTU. [LinkedIn](https://www.linkedin.com/in/heruidou)
