"""Re-run the whole synthetic pipeline and compare with the committed sample outputs.

Exact: the synthetic raw inputs (SHA-256), dbt node statuses, the four extracts (bytes)
and the experiment JSON. Model outputs (lead designs and scores) are compared with an
absolute tolerance of 1e-9: they are byte-identical across repeated runs in the tested
environment, but BLAS/OpenMP builds on other platforms may differ in the last digits.
The committed files are restored afterwards, so the working tree is left unchanged."""
import csv
import json
import math
import shutil
import subprocess
import sys

import pytest

from portfolio import paths

pytestmark = pytest.mark.slow
TOL = 1e-9


def _num_equal(a, b, path="$"):
    if isinstance(a, dict):
        assert set(a) == set(b), path
        for k in a:
            _num_equal(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _num_equal(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=0, abs_tol=TOL), f"{path}: {a} vs {b}"
    else:
        assert a == b, f"{path}: {a!r} vs {b!r}"


def test_pipeline_reproduces_committed_sample(tmp_path):
    backup = tmp_path / "backup"
    keep = [paths.SAMPLE_OUT, paths.DASHBOARD_HTML, paths.DASHBOARD_DATA,
            paths.ROOT / "docs" / "metric-dictionary.md", paths.ROOT / "docs" / "source-manifest.md"]
    for p in keep:
        dst = backup / p.relative_to(paths.ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if p.is_dir() else shutil.copy2)(p, dst)
    try:
        r = subprocess.run([sys.executable, "-m", "portfolio.pipeline", "sample"], cwd=paths.ROOT,
                           env={**__import__("os").environ, "PYTHONPATH": str(paths.ROOT / "python")},
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        old = backup / "sample"
        new_m = json.loads((paths.SAMPLE_OUT / "manifest.json").read_text())
        old_m = json.loads((old / "manifest.json").read_text())
        assert new_m["raw_inputs"] == old_m["raw_inputs"]
        assert new_m["dbt"] == old_m["dbt"]
        assert (paths.SAMPLE_OUT / "dbt_nodes.json").read_text() == (old / "dbt_nodes.json").read_text()
        for f in sorted((old / "extracts").glob("*.csv")):
            assert (paths.SAMPLE_EXTRACTS / f.name).read_bytes() == f.read_bytes(), f.name
        assert (paths.SAMPLE_OUT / "experiment" / "criteo_synthetic.json").read_text() == \
            (old / "experiment" / "criteo_synthetic.json").read_text()
        _num_equal(json.loads((paths.SAMPLE_OUT / "lead_scoring" / "designs.json").read_text()),
                   json.loads((old / "lead_scoring" / "designs.json").read_text()))
        read = lambda p: list(csv.DictReader(open(p, newline="")))
        a = read(paths.SAMPLE_OUT / "lead_scoring" / "scores_corrected_design.csv")
        b = read(old / "lead_scoring" / "scores_corrected_design.csv")
        assert [x["mql_id"] for x in a] == [x["mql_id"] for x in b]
        for x, y in zip(a, b):
            for k in ("score_lr", "score_gb"):
                assert math.isclose(float(x[k]), float(y[k]), rel_tol=0, abs_tol=TOL)
    finally:
        for p in keep:
            src = backup / p.relative_to(paths.ROOT)
            if p.is_dir():
                shutil.rmtree(p)
                shutil.copytree(src, p)
            else:
                shutil.copy2(src, p)
