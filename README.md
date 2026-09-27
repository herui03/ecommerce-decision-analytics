# E-commerce Decision Analytics — independent case study

[![CI](https://github.com/herui03/ecommerce-decision-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/herui03/ecommerce-decision-analytics/actions/workflows/ci.yml)

An independent e-commerce case study on public data: an offline decision dashboard, a reproducible
dbt + DuckDB pipeline, and two separate studies, one on a Brazilian online marketplace (orders, deliveries,
reviews, payments, seller leads) and one on a randomised online-advertising experiment. The two are never
joined. Every number on the dashboard shows where it came from, what it is divided by, and when the
inputs cannot support it.

**Recruiters and hiring managers: start with the [60-second overview](docs/HR_OVERVIEW.md)** (business problem,
outputs, skills, a 3-minute demo, screenshots, validation and limits).

![Overview of the decision dashboard](docs/screenshots/overview.png)

**Open it:** download [`dashboard/decision-dashboard.html`](dashboard/decision-dashboard.html) and open it in
any browser. It is one self-contained file (about 0.9 MB) with no server, no network access (enforced by its
Content-Security-Policy) and no tracking.

## What is real, what is recomputed, what is synthetic

| | Status in this repository |
|---|---|
| **Marketplace views on the "Historical extracts" source** | Four metric-layer extracts committed by the prior full-data run (2026-07-16). **Not re-executed**: the raw Kaggle files could not be downloaded from the build environment. Every total, rate and ratio is **recomputed** from them with integer cents and integer counts. |
| **Lead-scoring results** | The prior run's committed held-out scores. AUC, PR-AUC and Brier **recompute exactly**; the top-decile hit counts turned out to be tie-dependent and the training labels were not complete at the cut, so the result is shown as a **retrospective backtest**. |
| **Ad experiment** | ITT, CACE and MDE **recomputed** from the arm counts documented by the prior run; one count is inferred as the only integer consistent with a documented rate. The 13.98 M-row file was not re-read. |
| **"Synthetic sample" source** | A deterministic generated dataset (fictional regions `XA`–`XH`, categories `synthetic_cat_*`) that runs through the **real dbt project** from a clean clone with no credentials. It demonstrates the mechanics; it says nothing about the real marketplace or ad experiment. |
| **Full-data re-run of the restored pipeline** | **Not performed.** The five intermediate dbt models were never committed in the original repo; they are reconstructed from the documented contract and validated on synthetic data only. |

The historical claims from the earlier README (28 dbt models; "170 tests", which were in fact 170 passing dbt nodes
including the 28 models; 99,441 orders; 13,979,592 ad-experiment rows)
are the prior run's figures. They are kept in [`docs/data-verification.md`](docs/data-verification.md) as history and
were not re-verified here. Current, re-executed evidence is in [`docs/evidence.md`](docs/evidence.md).

## The questions the dashboard answers

| View | Business question | What makes it trustworthy |
|---|---|---|
| Overview | How did the marketplace perform in the selected months, and which operational signals deserve investigation? | Late rate = late ÷ delivered, summed before dividing (6.79%, not the 5.89% mean of monthly rates); averages that cannot be combined are shown as unavailable |
| Categories | Where is item GMV concentrated, and how large is freight's share of it? | Item grain; an order in two categories counts in both, so category order counts are never summed into a total |
| States | How do customer states compare on GMV, freight burden and delivery? | AOV denominators inferred only when unique; state late rate across months unavailable in the historical extract |
| Payments | Which primary instrument do orders use, and how common are installments? | "Payments on these orders" is the whole order total, not the amount paid with that instrument |
| Lead scoring | Can a score help sales prioritise, and what can honestly be claimed? | Label-maturity audit, look-ahead feature flagged, tie-aware top-k; ranking is not incremental wins |
| Experiment | Did the campaign lift conversions, and what would it need to be worth? | ITT with CI; CACE with its assumptions; significance ≠ importance; hypothetical break-even calculator |
| Definitions & sources | What does each number mean and where does it come from? | Metric dictionary, licences, inference audit, per-month reconciliation, input hashes |
| Decision memo | What should we do next? | Investigations and experiments, not promised gains ([`docs/decision-memo.md`](docs/decision-memo.md)) |

Filters are scoped to the grain that supports them: the month range applies to all four marketplace views, while the
category, state and payment filters apply only to their own view, because no extract has a joint
month × state × category grain.

| Lead scoring | Experiment | Phone width |
|---|---|---|
| ![Lead scoring view](docs/screenshots/lead-scoring.png) | ![Experiment view](docs/screenshots/experiment.png) | ![Overview at 375 px](docs/screenshots/mobile-overview.png) |

## Run it yourself

Tested on **Python 3.11 and 3.12** (Linux) with the pinned `requirements.txt`. Newer interpreters (3.13, 3.14)
are refused with a clear message, because numpy 2.0.2 and scikit-learn 1.6.1 have no wheels for them. On macOS:
`brew install python@3.12` (or `uv python install 3.12`). Viewing the dashboard needs no Python at all.

```bash
git clone https://github.com/herui03/ecommerce-decision-analytics.git
cd ecommerce-decision-analytics

scripts/setup.sh          # .venv with Python 3.12/3.11 + pinned packages (PYTHON=python3.12 to choose)
make sample               # synthetic data -> dbt build (171 nodes: 28 models + 143 data tests) -> extracts -> models -> dashboard (~20 s)
make verify               # committed dashboard and generated docs == a fresh build, byte for byte
make test-fast            # unit, contract, artifact, lead, experiment and engine tests (~10 s)
make test                 # adds the dbt mutation tests and a full pipeline reproduction (~2 min)
make browser              # drives the dashboard in Chromium; writes docs/evidence/browser/
```

`make sample` needs no Kaggle account, no API key and no network. It regenerates `sample/` and the dashboard;
`git status` stays clean because the outputs are deterministic.

**Full-data path (optional, not run here).** Download the three Kaggle datasets into `data/raw/` (see the
source manifest), then `cd dbt && DBT_PROFILES_DIR=$PWD ../.venv/bin/dbt build` (the `dev` target) and
`python/criteo/ab_analysis.py`. The singular tests tagged `full_data` pin the prior run's counts and will show
whether the reconstructed intermediate layer reproduces them.

## How it is built

```
Kaggle CSVs (not committed)      synthetic generator (seeded)
          \                      /
       dbt + DuckDB: 11 staging -> 5 intermediate (reconstructed) -> 12 marts
                        |  generic tests + data-agnostic invariants (+ full_data pins)
          metric extracts (month / month×category / month×state / month×type)
                        |
   python/portfolio: contract (integer cents, per-month reconciliation, bounded inference)
                     leads (as-of windows, point-in-time features, tie-aware top-k)
                     experiment (ITT, CACE, MDE, break-even)
                        |
   dashboard/decision-dashboard.html  (engine.js recomputes every selection in the browser)
```

Stack: SQL, dbt-core 1.10, DuckDB 1.4, Python (pandas, scikit-learn, statsmodels), vanilla JS/SVG, Playwright.

## What was hard, and what was decided

| Plan | What the data said | Decision |
|---|---|---|
| RFM segmentation | 96.88% of customers ordered once (historical), so Frequency is constant | Dropped F and the cohort module ([01](docs/challenge-01-rfm-frequency-collapse.md)) |
| Ad lift on exposed users | Naive exposed vs control reports +2,675.83% against an ITT of +59.45% | ITT for decisions; exposure only as an instrument ([02](docs/challenge-02-exposure-trap.md)) |
| One join across order children | Payments inflate 26% and 1,525 orders vanish (historical measurement) | Pre-aggregate to order grain; assert rows and money ([03](docs/challenge-03-silent-fanout.md)) |
| Chart the full date range | A pilot period and an export tail fake growth and collapse | Explicit 2017-01 to 2018-08 window ([04](docs/challenge-04-phantom-trend.md)) |
| Lead scoring on all leads | Zero 90-day conversions for Jul–Oct 2017 cohorts; cause unknown | Restricted window; labels, features and ties re-examined in 2026-09 ([05](docs/challenge-05-target-measured-the-org.md)) |
| Combine monthly averages | Extracts store per-month means, not their valid counts | Exact combination only with sum + count; otherwise "unavailable" |

## Documents

| Document | For |
|---|---|
| [`docs/HR_OVERVIEW.md`](docs/HR_OVERVIEW.md) | A 60-second overview for recruiters and hiring managers |
| [`docs/decision-memo.md`](docs/decision-memo.md) | The recommendation, with every number generated from the inputs |
| [`docs/metric-dictionary.md`](docs/metric-dictionary.md) | Metric and grain contract: numerators, denominators, how selections combine |
| [`docs/source-manifest.md`](docs/source-manifest.md) | Data sources, licences, what is in the repo |
| [`docs/evidence.md`](docs/evidence.md) | What was executed here, with results; what is historical; what could not run |
| [`docs/defect-log.md`](docs/defect-log.md) | Defects found during this upgrade, with before/after evidence |
| [`docs/demo-3min.md`](docs/demo-3min.md) | A three-minute walkthrough script |
| [`docs/learning-guide-zh.md`](docs/learning-guide-zh.md) | 学习指南（中文）：七个核心概念、亲手复现练习、术语表 |
| [`docs/data-verification.md`](docs/data-verification.md) | The prior run's verification log (historical) |

## Limitations

- No full-data run in this repository; the reconstructed intermediate layer is unverified against the real data.
- The marketplace data has no treatment, cost or margin fields: no causal, A/B or ROI claims are made about it.
- The ad-experiment features are anonymised (`f0`–`f11`) and are never given product or geography meaning.
- The historical state extract lacks delivered/late counts and valid-value counts, so several multi-month
  state and average metrics are unavailable rather than approximated.
- The corrected lead-scoring design trains on about one month of mature labels at the real dates; it has
  been run only on synthetic data.
- The lead-scoring outcome-observation cutoff (wins completely recorded through 2018-08-29) is an assumption.

## Credits and licence

Herui directed the portfolio task. This upgrade retains historical artifacts from the existing repository; their
original personal authorship is not independently verified here. Claude implemented and tested this upgrade
(pipeline restoration, synthetic sample, dashboard, tests and documents); Codex independently reviewed key source,
evidence and displayed screenshots, and several of its findings are recorded in the defect log. The commands that
reproduce each figure are in [`docs/evidence.md`](docs/evidence.md).

Code: MIT ([`LICENSE`](LICENSE)). Data sources: the Brazilian E-Commerce Public Dataset by Olist and the Marketing
Funnel by Olist (CC BY-NC-SA 4.0); the Criteo Uplift Modeling Dataset (Criteo AI Lab; six aggregate counts only).
Olist-derived data in this repository (extracts, lead scores, dashboard payload) is shared under CC BY-NC-SA 4.0,
attribution Olist, non-commercial. See [`docs/source-manifest.md`](docs/source-manifest.md).

Herui Dou, MSc Business Analytics, NTU. [LinkedIn](https://www.linkedin.com/in/heruidou)
