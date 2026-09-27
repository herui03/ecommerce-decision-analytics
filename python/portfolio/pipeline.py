"""Command-line entry point.

    python -m portfolio.pipeline sample      # synthetic data -> dbt -> extracts -> models -> dashboard
    python -m portfolio.pipeline dashboard   # rebuild the HTML from committed inputs only
    python -m portfolio.pipeline verify      # rebuild in memory, compare with committed files

Run from the repository root with PYTHONPATH=python (the Makefile does this).
Nothing here needs network access or credentials. The full-data path (real Kaggle CSVs
in data/raw) is the original dbt build and is documented, not run, by this command.
"""
from __future__ import annotations

import os
import sys

SUPPORTED = ((3, 11), (3, 12))


def check_python() -> None:
    v = sys.version_info[:2]
    if v not in SUPPORTED:
        ok = ", ".join(f"{a}.{b}" for a, b in SUPPORTED)
        sys.stderr.write(
            f"\nThis pipeline is tested on Python {ok}; you are running {v[0]}.{v[1]}.\n"
            "The pinned numpy 2.0.2 / scikit-learn 1.6.1 have no wheels for newer Pythons, so\n"
            "pip would try (and usually fail) to build them from source.\n\n"
            "  * To just LOOK at the work: open dashboard/decision-dashboard.html in a browser.\n"
            "    It is self-contained and needs no Python at all.\n"
            "  * To run the pipeline: install Python 3.12 (e.g. `brew install python@3.12` or\n"
            "    `uv python install 3.12`) and run scripts/setup.sh.\n\n")
        sys.exit(2)


check_python()
# Single-threaded numerics. Tested claim: repeated runs are byte-identical in the tested
# environment (Linux x86_64, Python 3.11, pinned requirements). Across OS/CPU/BLAS builds
# the DuckDB extracts are expected to match exactly, but model scores can differ in the
# last floating-point digits; tests/test_determinism.py compares those with a tolerance.
for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

from . import paths  # noqa: E402

EXPORTS = {
    "mart_monthly_performance": "purchase_month",
    "mart_category_performance": "purchase_month, product_category",
    "mart_state_performance": "purchase_month, customer_state",
    "mart_payment_performance": "purchase_month, primary_payment_type",
}


def _rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(paths.ROOT))


def run_dbt(log_path: Path) -> dict:
    env = dict(os.environ)
    env.update({
        "DBT_PROFILES_DIR": str(paths.DBT_DIR),
        "OLIST_RAW_DIR": "../data/sample/raw",
        "OLIST_DUCKDB_PATH": "../data/sample/olist_sample.duckdb",
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "False",
    })
    if paths.SAMPLE_DUCKDB.exists():
        paths.SAMPLE_DUCKDB.unlink()          # full rebuild every time: no stale state
    dbt = Path(sys.executable).parent / "dbt"
    cmd = [str(dbt), "build", "--target", "sample", "--exclude", "tag:full_data"]
    proc = subprocess.run(cmd, cwd=paths.DBT_DIR, env=env, capture_output=True, text=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise SystemExit(f"dbt build failed (exit {proc.returncode}); see {log_path}\n{tail}")
    rr = json.loads((paths.DBT_DIR / "target" / "run_results.json").read_text())
    nodes = sorted((r["unique_id"], r["status"]) for r in rr["results"])
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for uid, status in nodes:
        by_status[status] = by_status.get(status, 0) + 1
        kind = "model" if uid.startswith("model.") else "test"
        by_type[kind] = by_type.get(kind, 0) + 1
    return {"command": " ".join(cmd[1:]), "exit_code": proc.returncode,
            "by_status": by_status, "by_type": by_type,
            "nodes": [{"id": u, "status": s} for u, s in nodes]}


def export_extracts(db_path: Path, out: Path) -> list[dict]:
    """Same COPY + round-trip idea as python/export_tableau.py. Paths go into SQL only
    through paths.sql_literal (quotes escaped), so any clone directory name works."""
    import duckdb
    from .contract import load_extracts, to_cents
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    report = []
    for model, order in EXPORTS.items():
        path = out / f"{model}.csv"
        con.execute(f"COPY (SELECT * FROM main_marts.{model} ORDER BY {order}) "
                    f"TO {paths.sql_literal(path)} (FORMAT CSV, HEADER, DELIMITER ',')")
        rows_w = con.execute(f"SELECT count(*) FROM main_marts.{model}").fetchone()[0]
        # exact for DECIMAL columns; round() also makes it exact if a column arrives as DOUBLE
        cents_w = con.execute(f"SELECT CAST(round(coalesce(sum(gmv_brl), 0) * 100) AS BIGINT) "
                              f"FROM main_marts.{model}").fetchone()[0]
        with open(path, newline="") as fh:
            rows_f = list(csv.DictReader(fh))
        cents_f = sum(to_cents(r["gmv_brl"]) or 0 for r in rows_f)
        ok = rows_w == len(rows_f) and int(cents_w) == cents_f
        report.append({"extract": model, "rows": rows_w, "gmv_cents": cents_f, "round_trip": ok})
        if not ok:
            path.unlink()
            raise SystemExit(f"round-trip verification failed for {model}; extract deleted")
    con.close()
    x = load_extracts(out, "synthetic")      # full contract + per-month reconciliation
    fails = [c for c in x.reconciliation if c["result"] == "fail"]
    assert not fails, fails
    return report


def run_leads() -> dict:
    import duckdb
    from . import leads
    con = duckdb.connect(str(paths.SAMPLE_DUCKDB), read_only=True)
    df = con.execute("""
        SELECT mql_id, first_contact_date, won_date, lead_origin_channel, landing_page_id,
               page_lead_volume, page_lead_volume_prior
        FROM main_marts.mart_lead_features""").df()
    con.close()
    mismatches = leads.check_pit_column(df)
    if mismatches:
        raise SystemExit(f"page_lead_volume_prior disagrees with the Python recomputation on {mismatches} rows")
    designs = [leads.run_design(df, d) for d in (leads.CORRECTED, leads.CORRECTED_LEGACY_FEATURE,
                                                  leads.HISTORICAL_SPLIT)]
    invalid_demo = leads.LeadDesign(
        name="historical windows WITH label maturity enforced",
        train_start=leads.HISTORICAL_SPLIT.train_start, as_of=leads.HISTORICAL_SPLIT.as_of,
        score_start=leads.HISTORICAL_SPLIT.score_start, score_end=leads.HISTORICAL_SPLIT.score_end,
        outcome_observed_through=leads.HISTORICAL_SPLIT.outcome_observed_through)
    designs.append(leads.run_design(df, invalid_demo))
    d = paths.SAMPLE_OUT / "lead_scoring"
    d.mkdir(parents=True, exist_ok=True)
    scores = designs[0].pop("scores")
    for x in designs[1:]:
        x.pop("scores", None)
    with open(d / "scores_corrected_design.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(scores[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(scores)
    summary = {"label": "SYNTHETIC", "leads": int(len(df)), "pit_feature_mismatches": mismatches,
               "designs": designs, "historical_split_audit": leads.audit_historical_split()}
    (d / "designs.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str,
                                               allow_nan=False) + "\n")
    return summary


def run_experiment(truth: dict) -> dict:
    from . import experiment
    c = experiment.counts_from_csv(paths.SAMPLE_CRITEO)
    diag = experiment.balance_from_csv(paths.SAMPLE_CRITEO, "f0")
    res = {"label": "SYNTHETIC", "truth": truth, **experiment.analyse(c, diagnostics=diag)}
    d = paths.SAMPLE_OUT / "experiment"
    d.mkdir(parents=True, exist_ok=True)
    (d / "criteo_synthetic.json").write_text(json.dumps(res, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return res


def cmd_sample(_args) -> None:
    from . import synthetic
    from .synthetic import sha256
    print("1/6 generating deterministic synthetic sample ...")
    manifest = synthetic.generate_all(paths.SAMPLE_WORK)
    print("2/6 dbt build (target=sample, excluding tag:full_data) ...")
    dbt = run_dbt(paths.SAMPLE_WORK / "dbt_build.log")
    print(f"    {dbt['by_type']} {dbt['by_status']}")
    print("3/6 exporting + round-trip verifying sample extracts ...")
    ex = export_extracts(paths.SAMPLE_DUCKDB, paths.SAMPLE_EXTRACTS)
    print("4/6 lead scoring (corrected windows, point-in-time features) ...")
    leads_summary = run_leads()
    print("5/6 experiment statistics on the synthetic RCT ...")
    truth = {k: v for k, v in manifest["criteo"].items() if k not in ("file", "sha256")}
    run_experiment(truth)
    out = {
        "label": "SYNTHETIC - generated by python/portfolio/synthetic.py, not real data",
        "seed": manifest["seed"],
        "raw_inputs": manifest["files"],
        "criteo_input": {k: manifest["criteo"][k] for k in ("file", "sha256", "rows")},
        "dbt": {k: dbt[k] for k in ("command", "exit_code", "by_status", "by_type")},
        "extracts": ex,
    }
    (paths.SAMPLE_OUT / "dbt_nodes.json").write_text(json.dumps(dbt["nodes"], indent=1) + "\n")
    outputs = sorted(p for p in paths.SAMPLE_OUT.rglob("*") if p.is_file() and p.name != "manifest.json")
    out["outputs"] = {_rel(p): sha256(p) for p in outputs}
    (paths.SAMPLE_OUT / "manifest.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"    leads: {leads_summary['leads']} rows, designs: "
          + ", ".join(f"{x['design']['name'][:30]}={x['status']}" for x in leads_summary["designs"]))
    if getattr(_args, "skip_dashboard", False):
        print("6/6 dashboard build skipped (--skip-dashboard)")
        return
    print("6/6 building the dashboard and generated docs ...")
    cmd_dashboard(_args)
    cmd_docs(_args)


def cmd_dashboard(_args) -> None:
    from . import dashboard
    html, data = dashboard.build()
    paths.DASHBOARD_HTML.parent.mkdir(parents=True, exist_ok=True)
    paths.DASHBOARD_HTML.write_text(html, encoding="utf-8")
    paths.DASHBOARD_DATA.write_text(data, encoding="utf-8")
    kb = len(html.encode()) / 1024
    print(f"    wrote {_rel(paths.DASHBOARD_HTML)} ({kb:,.0f} KB) and {_rel(paths.DASHBOARD_DATA)}")


def generated_docs() -> dict:
    from . import definitions, memo
    docs = paths.ROOT / "docs"
    return {docs / "metric-dictionary.md": definitions.metric_dictionary_markdown(),
            docs / "source-manifest.md": definitions.source_manifest_markdown(),
            docs / "decision-memo.md": memo.markdown()}


def cmd_docs(_args) -> None:
    for path, text in generated_docs().items():
        path.write_text(text, encoding="utf-8")
        print(f"    wrote {_rel(path)}")


def _json_diff(a, b, path="$") -> list[str]:
    """Paths where two JSON documents differ, with both values (for a readable verify)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _json_diff(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _json_diff(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [f"{path}: committed={json.dumps(a)[:80]} fresh={json.dumps(b)[:80]}"]


def cmd_verify(_args) -> None:
    from . import dashboard
    html, data = dashboard.build()
    ok = True
    for path, fresh in [(paths.DASHBOARD_HTML, html), (paths.DASHBOARD_DATA, data)] + list(generated_docs().items()):
        same = path.exists() and path.read_text(encoding="utf-8") == fresh
        print(f"  {_rel(path)}: {'identical to a fresh build' if same else 'DIFFERS from a fresh build'}")
        ok &= same
        if not same and path == paths.DASHBOARD_DATA and path.exists():
            for line in _json_diff(json.loads(path.read_text(encoding="utf-8")), json.loads(fresh))[:25]:
                print("      " + line)
    sys.exit(0 if ok else 1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m portfolio.pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("sample", help="run the full synthetic pipeline and rebuild the dashboard")
    sp.add_argument("--skip-dashboard", action="store_true", help="stop after the model outputs")
    sub.add_parser("dashboard", help="rebuild the dashboard from committed inputs")
    sub.add_parser("verify", help="check committed dashboard files equal a fresh build")
    sub.add_parser("docs", help="regenerate the metric dictionary, source manifest and decision memo")
    args = ap.parse_args(argv)
    {"sample": cmd_sample, "dashboard": cmd_dashboard, "verify": cmd_verify, "docs": cmd_docs}[args.cmd](args)


if __name__ == "__main__":
    main()
