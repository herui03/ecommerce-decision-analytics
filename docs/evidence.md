# Evidence: what was executed, what is historical, what could not run

Every claim below points at a raw log in `docs/evidence/`. Regenerate the logs with
`scripts/collect_evidence.sh` (about 2.5 minutes). Test counts here are for the current code; they are not
there to impress. Each test exists because it guards a specific failure (see the test docstrings and
`docs/defect-log.md`).

**Which commit these results belong to.**

- **Commit `0577a9353782616ba832f03c8555a24940fe9a46` of the private development repository** (the public
  repository starts from a single reviewed snapshot of it). The dbt, pipeline, determinism, verify, pytest, Node,
  Python 3.12 and interval-coverage logs were produced from this commit's code. That commit added only the
  refreshed logs, so its code equals the code that was run.
- **Later commits** changed documentation, user-facing wording in the dashboard and in the generated
  memo/definitions text, and removed personal application documents. No computation, SQL or data changed.
- **Browser evidence** was regenerated after the wording change: the Chromium record
  (`evidence/browser/browser-run.json`, the full-page captures, `evidence/pytest-browser.txt`) and the README
  screenshots. It tests the dashboard file with SHA-256
  `1c260a0ed002f79a8106f295de1b77600878831019e025d97d2914f15ed63908`, the file committed with them.
- **Regression logs.** The before/after files in `evidence/regressions/` record the code before and after each
  fix, as their names say.
- **CI** (`.github/workflows/ci.yml`) re-runs the suites, including Chromium, on every push; see the Actions tab.

## 1. Executed in this build

Environment ([`environment.txt`](evidence/environment.txt)): Linux x86_64, Python 3.11.15, Node 22.22.2,
dbt-core 1.10.22, dbt-duckdb 1.10.0, DuckDB 1.4.5, numpy 2.0.2, pandas 2.3.3, scikit-learn 1.6.1,
statsmodels 0.14.6, Playwright 1.56.0 with Chromium 141.

| Check | Result | Log |
|---|---|---|
| dbt build on the synthetic sample (restored project, `--exclude tag:full_data`) | **171 successful dbt nodes** = 28 models + 143 data tests (`PASS=171 WARN=0 ERROR=0`); 171 is not a test count. The project defines 150 data tests; the 7 tagged `full_data` pin real-data counts and are excluded on synthetic data | [`dbt-sample-build.log`](evidence/dbt-sample-build.log) |
| Full synthetic pipeline (generator → dbt → extracts → lead designs → experiment → dashboard) | exit 0 | [`pipeline-run.txt`](evidence/pipeline-run.txt) |
| Determinism: two full runs, SHA-256 over every file in `sample/` | identical; committed outputs reproduced (no diff in `sample/`, `dashboard/`, generated docs) | [`determinism.txt`](evidence/determinism.txt) |
| Committed dashboard and generated docs == fresh build | byte-identical (5 files) | [`verify.txt`](evidence/verify.txt) |
| Python 3.12.3: same pipeline, pinned wheels | every sample output and the dashboard byte-identical to 3.11; 108 tests passed | [`python312-validation.txt`](evidence/python312-validation.txt) |
| Python 3.13 | refused with exit 2 and a pointer to the no-install HTML (numpy 2.0.2 has no wheels) | same file |
| Pytest, all non-browser tests | **108 passed** | [`pytest-not-browser.txt`](evidence/pytest-not-browser.txt) |
| of which dbt mutation tests | unmutated build passes; **6 of 6 mutations caught** (INNER JOIN on the spine, shattered item grain, `count(*)` for distinct orders, late flag without delivered status, label without `coalesce`, point-in-time feature seeing the future) | same file |
| of which pipeline reproduction | extracts, experiment JSON, dbt node statuses and raw hashes exact; model scores within 1e-9 | same file |
| Dashboard engine (Node) unit tests | **9 passed** | [`node-engine-tests.txt`](evidence/node-engine-tests.txt) |
| Chromium end-to-end on `dashboard/decision-dashboard.html` | **13 tests, 74 checks passed**; no console errors, no page errors, no network request besides the file | [`pytest-browser.txt`](evidence/pytest-browser.txt), [`browser/browser-run.json`](evidence/browser/browser-run.json) |
| Screenshots from that run | 19 full-page captures (desktop, 375 px, states) + 7 README screenshots | [`evidence/browser/`](evidence/browser/), [`screenshots/`](screenshots/) |
| Interval coverage (300 simulated RCTs, fixed seed) | ITT Wald 95% CI covered the truth 287/300 = 0.957; CACE delta-method 287/300 = 0.957 | [`interval-coverage.txt`](evidence/interval-coverage.txt) |
| Review-driven regressions, before → after | R4 contract 14 failed → 25 passed; R4 follow-ups 11 failed → 14 passed; R4-07 experiment 14 failed → 18 passed; quoted-path clone parser error → clean run | [`regressions/`](evidence/regressions/) |

What the browser run exercises: all 8 views under both data sources; month range, presets and the
reversed-range error; category search with its empty state; state selection, "none selected" and the
unavailable state late rate; the instrument filter keeping the full denominator; the lead model and k
slider; the break-even calculator with invalid and valid input; the table toggle; keyboard navigation of
tabs and charts; no horizontal overflow at 375 px on any view; dark mode. Displayed numbers are compared
with `tests/reference.py`, an independent Decimal implementation that reads the CSVs directly.

## 2. Recomputed here from committed historical inputs

These figures come from files committed by the prior full-data run. This build recomputed them and
checked them against what was documented.

| Figure | Documented | Recomputed here | Where checked |
|---|---|---|---|
| In-window orders / with items | 99,092 / 98,353 (Codex read) | 99,092 / 98,353 | `tests/test_dashboard_artifact.py::test_codex_monthly_figures_reproduce` |
| GMV, goods, freight, payments (cents) | 1,578,620,357 / 1,354,171,278 / 224,449,079 / 1,594,448,057 | identical | same |
| Late / delivered / cancelled | 6,532 / 96,211 / 580 | identical | same |
| Weighted late rate vs mean of monthly rates | 6.7892444731% vs 5.887424% | identical | same |
| AOV | 160.5055623113 BRL | 160.51 (integer cents, half-up) | same |
| GMV across the four extracts, per month | 15,786,203.57 BRL in total | exact per month (199 exact checks, 21 bounded, 0 failed) | `portfolio.contract.reconcile` |
| Lead model AUC / PR-AUC / Brier (LR, GB) | 0.6870 / 0.1849 / 0.0909; 0.6683 / 0.1791 / 0.0919 | identical to 1e-12 from `outputs/lead_scores_test.csv` | `tests/test_leads.py` |
| Top-265 hits | LR 53, GB 51, constant 25 | tie-aware 52.86 [52–54], 50.38 [49–54], 27.95 | same |
| Criteo ITT, CI, relative lift | +0.1152 pp [+0.1085, +0.1219], +59.45% | identical | `tests/test_experiment.py` |
| CACE, compliance, complier control rate | +3.1964 pp, 3.6037%, 2.1820% | identical; Wald vs decomposition gap < 1e-15 | same |
| Naive exposed vs control, z, p, MDE 80/95% | +2675.83%, 28.52, 7.31e-179, 0.0093 / 0.0121 pp | identical (y_exposed = 23,031 inferred as the unique integer matching 5.3784%) | same |

## 3. Historical only (not re-executed)

From `docs/data-verification.md`, the prior run of 2026-07-16: 99,441 source orders, 112,650 order lines,
96,096 customers, 96.88% one-time customers, 170 passing dbt nodes (models and tests together), the fan-out measurements (+26% payments,
1,525 dropped orders), 13,979,592 Criteo rows, the SMDs 0.0069 / 0.8524, and the customer-segment counts.
They are reported as history and were not verified here.

## 4. Could not run here

| Not run | Why | What would run it |
|---|---|---|
| Full-data `dbt build` of the restored project (including the `full_data` pinned tests) | Raw Kaggle files absent; the environment's network policy denied `www.kaggle.com` | Download the three datasets into `data/raw/`, then `cd dbt && dbt build` |
| Corrected lead-scoring design on real data | Same | Same, then `portfolio.leads.run_design` on `mart_lead_features` |
| Re-reading the 13.98 M-row Criteo file | `ailab.criteo.com` and `go.criteo.net` denied | `python/criteo/ab_analysis.py` or `experiment.counts_from_csv` |
| Online re-check of the dataset licences | Same network policy | Visit the links in `docs/source-manifest.md` |
| CI on GitHub | Runs on every push; see the repository's Actions tab | `.github/workflows/ci.yml` |

## 5. Clean-unpack validation

The exact-commit source archive (`git archive`) was unpacked into an empty directory. From there, with a
fresh virtualenv, `make sample`, `make verify` and the test suites were run. The PR description records
the commit, the archive's SHA-256 and the result.
