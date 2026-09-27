# E-commerce Decision Analytics — 60-second overview

An **independent case study on public data**. No employer or client is involved, and no company is
represented. The deliverable is a decision dashboard that a manager can open offline, backed by a pipeline
and tests that anyone can re-run.

![Dashboard overview: KPI tiles with numerator ÷ denominator under each value](screenshots/overview.png)

## The business problem

An online marketplace wants to know four things:

- How did we perform, and where are deliveries late?
- Where does freight eat into order value?
- Could a lead score help the sales team prioritise?
- Did an advertising campaign actually lift conversions?

Producing the charts is the easy part. The hard part is answering without misleading numbers: rates averaged
the wrong way, joins that double-count money, and "lift" measured on self-selected users.

## What you can open

| Output | What it is |
|---|---|
| [`dashboard/decision-dashboard.html`](../dashboard/decision-dashboard.html) | One offline HTML file (about 0.9 MB, no server, no network). It has 8 views, filters, chart ↔ table toggles, light and dark themes, and works at phone width. |
| [`docs/decision-memo.md`](decision-memo.md) | A one-page recommendation: three investigations and one budgeting rule, framed as tests to run rather than promised gains. |
| [`docs/metric-dictionary.md`](metric-dictionary.md) | Every metric with its numerator, denominator, grain and how a selection combines. |
| `make sample` | Rebuilds everything from generated data in about 20 s, with no accounts or credentials. |
| [`docs/evidence.md`](evidence.md) | What was executed, with raw logs; what is historical; what could not run. |

## Headline findings (historical data, recomputed)

- **Late deliveries: 6.79%** of delivered orders (6,532 ÷ 96,211). Averaging the monthly rates would report
  5.89%, because it gives small months the same weight as large ones.
- **Advertising: +0.115 percentage points** of conversion from assigning users to the campaign (95% CI
  0.108–0.122), about 1.15 extra conversions per 1,000 users. Comparing exposed users with the control group
  gives +2,676%, which is selection bias, not the campaign's effect.
- **Lead ranking.** This is a retrospective backtest (AUC 0.687); it is not a deployable estimate.
  - The top 10% of held-out leads contained about 52.9 wins, against about 28 for a score with no information.
  - That is ranking quality, not extra sales. Measuring extra sales needs a randomised prioritisation test.

## Skills and stack

| Area | What the project contains |
|---|---|
| Data modelling | SQL, dbt, DuckDB: 11 staging → 5 intermediate → 12 mart models with declared grain |
| Data quality | 143 data tests on the sample build; checks that catch fan-out, lost orders and money leaks; mutation testing (6 of 6 injected bugs caught) |
| Metrics | Weighted rates; integer-cent money; values reported as unavailable when the grain cannot support them |
| Experimentation | Intention-to-treat with confidence intervals, complier effect with its assumptions, minimum detectable effect, break-even arithmetic |
| ML evaluation | Label maturity, look-ahead leakage, point-in-time features, tie-aware top-k evaluation |
| Front end | Vanilla JavaScript and SVG charts, keyboard access, table alternatives, strict Content-Security-Policy |
| Reproducibility | Deterministic synthetic data, byte-identical rebuilds, CI on Python 3.11 and 3.12, Chromium end-to-end tests |

## 3-minute demo

| Time | Show | Point to make |
|---|---|---|
| 0:00 | Header, yellow banner, badges | Two separate studies on public data; every number says whether it is historical, recomputed or synthetic |
| 0:20 | Overview tiles | 6.79% = 6,532 ÷ 96,211. Rates are summed before dividing. "Unavailable" is shown instead of an invented number |
| 1:00 | Month filter, States view | Filters apply only where the data has that grain |
| 1:30 | Lead scoring | Immature labels, a look-ahead feature and a tie-dependent hit count, each found and corrected |
| 2:10 | Experiment | The effect size and its interval, not the p-value; a hypothetical break-even calculator |
| 2:45 | Synthetic sample, Decision memo | The whole pipeline re-runs in 20 s; recommendations are experiments to run |

The full script is in [`docs/demo-3min.md`](demo-3min.md).

| Experiment | Lead scoring | Decision memo |
|---|---|---|
| ![Experiment view](screenshots/experiment.png) | ![Lead scoring view](screenshots/lead-scoring.png) | ![Decision memo view](screenshots/decision-memo.png) |

## How it was validated

- **Figures the independent review supplied reproduce exactly** from the committed data: 99,092 orders and
  BRL 15,786,203.57 GMV, among others.
- **Test suites:**
  - Synthetic dbt build: 171 successful nodes (28 models + 143 data tests).
  - 108 Python tests.
  - 9 JavaScript engine tests.
  - A Chromium run that clicks through every view and compares the numbers shown with an independent
    reference implementation.
- **Reproducibility:** two full rebuilds are byte-identical, and Python 3.12 reproduces the Python 3.11
  outputs byte for byte. CI re-runs the suites on every push.
- **Defect log:** [`docs/defect-log.md`](defect-log.md) lists every defect found, including those in the
  original analysis, each with before and after evidence.

## Limitations

- The historical figures come from extracts of an earlier full-data run already in the repository. They were
  recomputed here but **not re-executed**, because the raw public files could not be downloaded in the build
  environment.
- Five intermediate models were missing from the original repository. They were reconstructed and validated
  on synthetic data only.
- There is no cost, margin or randomised treatment in the marketplace data, so no causal or ROI claims are
  made about it.
- The synthetic sample demonstrates the mechanics only; it describes no real business.

## Who did what

Herui directed the portfolio task. This upgrade retains historical artifacts from the existing repository;
their original personal authorship is not independently verified here. Claude implemented and tested this
upgrade; Codex independently reviewed key source, evidence and displayed screenshots.

## Data and licences

- **Marketplace data:** the Brazilian E-Commerce Public Dataset by Olist and the Marketing Funnel by Olist,
  both CC BY-NC-SA 4.0 (attribution Olist, non-commercial).
- **Advertising data:** the Criteo Uplift Modeling Dataset (Criteo AI Lab); only six aggregate counts are used.

Details are in [`docs/source-manifest.md`](source-manifest.md). Code is MIT-licensed.

Herui Dou, MSc Business Analytics, NTU. [LinkedIn](https://www.linkedin.com/in/heruidou)
