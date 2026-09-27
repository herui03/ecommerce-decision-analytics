"""Shared fixtures. Every test that mutates an extract works on a COPY in tmp_path;
committed files are never modified by the suite."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))      # tests/reference.py for sub-folders

import pytest

from portfolio import paths
from portfolio.contract import FILES


@pytest.fixture
def hist_copy(tmp_path) -> Path:
    d = tmp_path / "extracts"
    d.mkdir()
    for f in FILES.values():
        shutil.copy(paths.HISTORICAL_EXTRACTS / f, d / f)
    return d
