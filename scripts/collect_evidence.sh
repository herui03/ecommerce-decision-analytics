#!/usr/bin/env bash
# Re-run every executable check and store its raw output under docs/evidence/.
# docs/evidence.md summarises these files. Run from the repository root after `scripts/setup.sh`.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
export PYTHONPATH=python
E=docs/evidence
mkdir -p "$E"

{
  echo "# environment"
  uname -srm
  $PY --version
  node --version
  $PY -m pip list 2>/dev/null | grep -Ei '^(dbt-core|dbt-duckdb|duckdb|numpy|pandas|scikit-learn|statsmodels|playwright|pytest) '
} > "$E/environment.txt"

echo "== synthetic pipeline, run 1 and run 2 (determinism)"
$PY -m portfolio.pipeline sample > "$E/pipeline-run.txt" 2>&1
cp data/sample/dbt_build.log "$E/dbt-sample-build.log"
h1=$(find sample -type f | sort | xargs sha256sum | sha256sum)
$PY -m portfolio.pipeline sample > /dev/null 2>&1
h2=$(find sample -type f | sort | xargs sha256sum | sha256sum)
{
  echo "# two full \`make sample\` runs, SHA-256 over every file in sample/"
  echo "run 1: $h1"
  echo "run 2: $h2"
  [ "$h1" = "$h2" ] && echo "result: identical" || echo "result: DIFFERENT"
  echo
  echo "# git status after the runs (empty = committed outputs reproduced exactly)"
  git status --short -- sample dashboard docs/metric-dictionary.md docs/source-manifest.md docs/decision-memo.md
} > "$E/determinism.txt"

echo "== verify"
$PY -m portfolio.pipeline verify > "$E/verify.txt" 2>&1

echo "== node engine tests"
node --test tests/js/engine.test.mjs > "$E/node-engine-tests.txt" 2>&1

echo "== pytest (everything except the browser run)"
$PY -m pytest -m "not browser" -p no:cacheprovider -rA -q > "$E/pytest-not-browser.txt" 2>&1 || true
tail -3 "$E/pytest-not-browser.txt"

echo "== pytest browser (Chromium)"
$PY -m pytest -m browser -p no:cacheprovider -rA -q > "$E/pytest-browser.txt" 2>&1 || true
tail -3 "$E/pytest-browser.txt"

echo "== interval coverage (reported numbers for tests/test_experiment.py)"
$PY - > "$E/interval-coverage.txt" <<'PYEOF'
import numpy as np
from portfolio import experiment
rng = np.random.default_rng(20260926)
reps, n_t, n_c, pi, p0, tau = 300, 40000, 10000, 0.08, 0.02, 0.05
ci = cc = 0
for _ in range(reps):
    d1 = rng.random(n_t) < pi
    y = rng.random(n_t) < p0 + tau * d1
    yc = int((rng.random(n_c) < p0).sum())
    a = experiment.analyse(experiment.ArmCounts(n_t, int(y.sum()), n_c, yc, int(d1.sum()), int((y & d1).sum())))
    lo, hi = a["itt"]["ci"]; ci += lo <= tau * pi <= hi
    clo, chi = a["cace"]["ci"]; cc += clo <= tau <= chi
print("# same simulation as tests/test_experiment.py::test_interval_coverage_is_close_to_nominal")
print(f"replications: {reps}; true ITT {tau*pi}; true CACE {tau}")
print(f"ITT 95% Wald interval coverage: {ci}/{reps} = {ci/reps:.3f}")
print(f"CACE 95% delta-method interval coverage: {cc}/{reps} = {cc/reps:.3f}")
PYEOF
cat "$E/interval-coverage.txt"
