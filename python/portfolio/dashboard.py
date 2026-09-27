"""Build the self-contained offline dashboard.

Inputs (all committed, so the page rebuilds from a clean clone without dbt or data):
  tableau/extracts/*.csv                  HISTORICAL metric extracts (prior full-data run)
  outputs/lead_scores_test.csv, outputs/lead_scoring_results.csv   HISTORICAL lead run
  historical/criteo_documented_counts.json                         HISTORICAL counts
  sample/**                               SYNTHETIC outputs of `make sample`
  dashboard/src/{template.html,styles.css,engine.js,app.js}

Output: dashboard/decision-dashboard.html (one file: CSS, JS and data inlined, no
network requests) and dashboard/dashboard-data.json (the same payload, for inspection).
The build is deterministic: no timestamps, sorted keys, fixed float repr.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import definitions, experiment, leads, paths
from .contract import load_extracts
from .synthetic import sha256


def _rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(paths.ROOT))


def _olist_block(x, source: str) -> dict:
    summary: dict[str, dict[str, int]] = {}
    for e in x.inference_log:
        k = f"{e['extract']}.{e['field']}"
        summary.setdefault(k, {"inferred": 0, "unavailable": 0})
        summary[k][e["status"]] += 1
    results: dict[str, int] = {}
    for c in x.reconciliation:
        results[c["result"]] = results.get(c["result"], 0) + 1
    return {
        "source": source,
        "components": x.components,
        "months": [r["month"] for r in x.monthly],
        "monthly": x.monthly, "category": x.category, "state": x.state, "payment": x.payment,
        "inference": {"summary": summary,
                      "not_identified": [e for e in x.inference_log if e["status"] != "inferred"]},
        "reconciliation": {"counts": results,
                           "non_exact": [c for c in x.reconciliation if c["result"] != "pass"]},
    }


def _ranked(ids, scores, labels) -> dict:
    """Pre-sort by (score desc, id asc) so ties are contiguous and ordered by id; the ids
    themselves are not embedded."""
    import numpy as np
    order = leads.ranked(np.asarray(ids), np.asarray(scores, dtype=float))
    return {"scores": [float(scores[i]) for i in order], "labels": [int(labels[i]) for i in order]}


def _leads_historical() -> dict:
    sc = paths.HISTORICAL_OUTPUTS / "lead_scores_test.csv"
    rs = paths.HISTORICAL_OUTPUTS / "lead_scoring_results.csv"
    with open(sc, newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [r["mql_id"] for r in rows]
    y = [int(r["is_won_90d"]) for r in rows]
    with open(rs, newline="") as fh:
        committed = [{k: (v if k == "model" else float(v)) for k, v in r.items()} for r in csv.DictReader(fh)]
    return {
        "committed_results": committed,
        "recomputed": leads.recompute_historical(sc, rs),
        "audit": leads.audit_historical_split(),
        "ranked": {"lr": _ranked(ids, [float(r["score_lr"]) for r in rows], y),
                   "gb": _ranked(ids, [float(r["score_gb"]) for r in rows], y)},
        "cohort": ["2018-04-01", "2018-05-31"],
    }


def _leads_synthetic() -> dict:
    d = json.loads((paths.SAMPLE_OUT / "lead_scoring" / "designs.json").read_text())
    with open(paths.SAMPLE_OUT / "lead_scoring" / "scores_corrected_design.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [r["mql_id"] for r in rows]
    y = [int(r["is_won_90d"]) for r in rows]
    d["ranked"] = {"lr": _ranked(ids, [float(r["score_lr"]) for r in rows], y),
                   "gb": _ranked(ids, [float(r["score_gb"]) for r in rows], y)}
    d["declared_full_data_design"] = leads.CORRECTED.describe()
    return d


def _experiment_historical() -> dict:
    doc = json.loads((paths.HISTORICAL_DIR / "criteo_documented_counts.json").read_text())
    c = doc["counts"]
    counts = experiment.ArmCounts(c["n_t"], c["y_t"], c["n_c"], c["y_c"], c["n_exposed"],
                                  doc["inferred"]["y_exposed"]["value"])
    dz = doc["documented_results"]
    diag = {"covariate": "f0", "smd_treatment": dz["smd_treatment_f0"],
            "smd_exposure_within_treated": dz["smd_exposure_f0"],
            "provenance": "documented by the prior full-data run (docs/data-verification.md); not re-measured"}
    res = experiment.analyse(counts, diagnostics=diag)
    return {"provenance": doc["label"], "source_document": doc["source_document"],
            "inferred": doc["inferred"], "documented": doc["documented_results"], **res}


def _experiment_synthetic() -> dict:
    return json.loads((paths.SAMPLE_OUT / "experiment" / "criteo_synthetic.json").read_text())


def input_files() -> list[Path]:
    files = [paths.HISTORICAL_EXTRACTS / f for f in sorted(p.name for p in paths.HISTORICAL_EXTRACTS.glob("*.csv"))]
    files += [paths.HISTORICAL_OUTPUTS / "lead_scores_test.csv", paths.HISTORICAL_OUTPUTS / "lead_scoring_results.csv",
              paths.HISTORICAL_DIR / "criteo_documented_counts.json"]
    files += sorted(p for p in paths.SAMPLE_OUT.rglob("*") if p.is_file())
    files += [paths.DASHBOARD_SRC / n for n in ("template.html", "styles.css", "engine.js", "app.js")]
    return files


def payload() -> dict:
    hist = load_extracts(paths.HISTORICAL_EXTRACTS, "historical")
    syn = load_extracts(paths.SAMPLE_EXTRACTS, "synthetic")
    manifest = json.loads((paths.SAMPLE_OUT / "manifest.json").read_text())
    return {
        "schema": 1,
        "inputs": {_rel(p): sha256(p) for p in input_files()},
        "olist": {"historical": _olist_block(hist, "historical"),
                  "synthetic": _olist_block(syn, "synthetic")},
        "leads": {"historical": _leads_historical(), "synthetic": _leads_synthetic()},
        "experiment": {"historical": _experiment_historical(), "synthetic": _experiment_synthetic()},
        "sample_manifest": {"seed": manifest["seed"], "dbt": manifest["dbt"],
                            "raw_rows": {k: v["rows"] for k, v in manifest["raw_inputs"].items()}},
        "badges": definitions.BADGES,
        "metrics": definitions.METRICS,
        "sources": definitions.SOURCES,
    }


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def build() -> tuple[str, str]:
    data = payload()
    src = paths.DASHBOARD_SRC
    html = (src / "template.html").read_text(encoding="utf-8")
    embedded = _json(data).replace("</", "<\\/")          # cannot close the <script> element
    for token, text in (("/*__STYLES__*/", (src / "styles.css").read_text(encoding="utf-8")),
                        ("/*__ENGINE__*/", (src / "engine.js").read_text(encoding="utf-8")),
                        ("/*__APP__*/", (src / "app.js").read_text(encoding="utf-8")),
                        ("__DATA_JSON__", embedded)):
        if html.count(token) != 1:
            raise ValueError(f"template must contain {token} exactly once")
        html = html.replace(token, text)
    pretty = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    return html, pretty
