"""Repository paths, resolved from this file so every entry point works from any cwd."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DBT_DIR = ROOT / "dbt"
HISTORICAL_EXTRACTS = ROOT / "tableau" / "extracts"
HISTORICAL_OUTPUTS = ROOT / "outputs"
HISTORICAL_DIR = ROOT / "historical"

SAMPLE_WORK = ROOT / "data" / "sample"          # gitignored: raw synthetic CSVs + duckdb
SAMPLE_RAW = SAMPLE_WORK / "raw"
SAMPLE_CRITEO = SAMPLE_WORK / "criteo" / "criteo-uplift-synthetic.csv"
SAMPLE_DUCKDB = SAMPLE_WORK / "olist_sample.duckdb"

SAMPLE_OUT = ROOT / "sample"                      # committed: aggregated synthetic outputs
SAMPLE_EXTRACTS = SAMPLE_OUT / "extracts"

DASHBOARD_SRC = ROOT / "dashboard" / "src"
DASHBOARD_HTML = ROOT / "dashboard" / "decision-dashboard.html"
DASHBOARD_DATA = ROOT / "dashboard" / "dashboard-data.json"


def sql_literal(path) -> str:
    """A filesystem path as a DuckDB string literal. Single quotes are doubled, so a
    clone at e.g. "~/Herui's portfolio" cannot break (or inject into) the SQL."""
    return "'" + str(path).replace("'", "''") + "'"
