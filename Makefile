# All targets run from a clean clone with no credentials and no network access
# (except `make setup`, which installs pinned packages from PyPI).
PY := .venv/bin/python
export PYTHONPATH := python

.PHONY: setup sample dashboard verify test test-fast browser clean

setup:            ## create .venv (Python 3.11/3.12) and install pinned requirements
	scripts/setup.sh

sample:           ## synthetic data -> dbt build -> extracts -> lead scoring -> experiment -> dashboard
	$(PY) -m portfolio.pipeline sample

dashboard:        ## rebuild dashboard/decision-dashboard.html (and generated docs) from committed inputs only
	$(PY) -m portfolio.pipeline dashboard
	$(PY) -m portfolio.pipeline docs

verify:           ## committed dashboard and generated docs == fresh build (byte for byte)
	$(PY) -m portfolio.pipeline verify

test-fast:        ## unit + contract + artifact tests (no dbt build, no browser)
	$(PY) -m pytest -m "not slow and not browser"
	node --test tests/js/engine.test.mjs

test:             ## everything except the browser run (includes dbt mutation tests, ~2 min)
	$(PY) -m pytest -m "not browser"
	node --test tests/js/engine.test.mjs

browser:          ## drive the real dashboard in Chromium; writes docs/evidence/browser/
	$(PY) -m pytest -m browser -s

clean:
	rm -rf data/sample dbt/target dbt/logs .pytest_cache
