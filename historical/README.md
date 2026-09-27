# Historical inputs (prior full-data run, 2026-07-16)

These files are **outputs of a prior run on the real data**. They are committed so the
dashboard can show real-data results without redistributing the raw datasets. They were
**not re-executed** in this repository: the raw Kaggle (Olist) and Criteo files are not in the
repository and the build environment could not download them.

| Input | What it is | How the dashboard uses it |
|---|---|---|
| `tableau/extracts/mart_{monthly,category,state,payment}_performance.csv` | Metric-layer extracts from the prior dbt run (round-trip verified at export) | Loaded through `portfolio.contract`; all totals and ratios are recomputed from integer cents and integer counts |
| `outputs/lead_scores_test.csv`, `outputs/lead_scoring_results.csv` | Held-out lead scores and metrics from the prior lead-scoring run | Metrics recomputed from the scores; labelled RETROSPECTIVE (training labels were not mature at the 2018-04-01 cut; look-ahead page feature) |
| `historical/criteo_documented_counts.json` | Arm counts transcribed from `docs/data-verification.md` | ITT/CACE/MDE recomputed from the counts; one count inferred as the unique integer matching a documented rate |

`mart_customer_segments.csv` was intentionally not committed (15 MB, regenerable only with
the raw data) and is not used.
