"""Mutation tests for the restored dbt project: each mutation reintroduces a bug the
project claims to guard against, on a COPY of dbt/, and the data-agnostic tests must
turn it red. A test suite that has never been seen failing proves nothing.

Slow (a dbt build per mutation on the synthetic sample): marked `slow`."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from portfolio import paths, synthetic

pytestmark = pytest.mark.slow

MUTATIONS = {
    "enriched LEFT JOIN items -> INNER JOIN (silently drops item-less orders)": (
        "models/intermediate/int_orders__enriched.sql",
        "left join items     i on i.order_id    = o.order_id",
        "join items     i on i.order_id    = o.order_id",
        ["equal_rowcount_int_orders__enriched", "assert_orders_enriched_reconciles"]),
    "items_agg grain shattered by product (fan-out source)": (
        "models/intermediate/int_orders__items_agg.sql",
        "group by 1", "group by order_id, product_id",
        ["unique_int_orders__items_agg_order_id"]),
    "category orders counted as lines (count(*) for count(distinct))": (
        "models/marts/mart_category_performance.sql",
        "count(distinct order_id)                   as orders,", "count(*)                                   as orders,",
        ["inv_metric_layer_reconciles"]),
    "late rate no longer restricted to delivered orders": (
        "models/intermediate/int_orders__enriched.sql",
        "coalesce(o.order_status = 'delivered'\n             and o.delivery_days_vs_estimate > 0, false)",
        "coalesce(o.delivery_days_vs_estimate > 0, false)",
        ["inv_additive_components"]),
    "lead label loses its coalesce (NULL for never-won leads)": (
        "models/marts/mart_lead_features.sql",
        "        coalesce(\n            date_diff('day', l.first_contact_date, d.won_at::date) between 0 and 90,\n            false\n        ) as is_won_90d,",
        "        date_diff('day', l.first_contact_date, d.won_at::date) between 0 and 90 as is_won_90d,",
        ["not_null_mart_lead_features_is_won_90d"]),
    "point-in-time page count includes same-day and later leads": (
        "models/marts/mart_lead_features.sql",
        "and p.first_contact_date < l.first_contact_date", "and p.first_contact_date <= l.first_contact_date + 30",
        ["inv_lead_label_contract"]),
}


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    d = tmp_path_factory.mktemp("raw")
    synthetic.generate_olist(d)
    return d


def dbt_build(project: Path, raw: Path, db: Path):
    env = dict(os.environ, DBT_PROFILES_DIR=str(project), OLIST_RAW_DIR=str(raw),
               OLIST_DUCKDB_PATH=str(db), DBT_SEND_ANONYMOUS_USAGE_STATS="False")
    dbt = Path(sys.executable).parent / "dbt"
    return subprocess.run([str(dbt), "build", "--target", "sample", "--exclude", "tag:full_data"],
                          cwd=project, env=env, capture_output=True, text=True)


def test_unmutated_project_passes(tmp_path, raw):
    proj = tmp_path / "dbt"
    shutil.copytree(paths.DBT_DIR, proj, ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"))
    r = dbt_build(proj, raw, tmp_path / "w.duckdb")
    assert r.returncode == 0, r.stdout[-3000:]


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_mutation_is_caught(tmp_path, raw, name):
    rel, old, new, expected_failures = MUTATIONS[name]
    proj = tmp_path / "dbt"
    shutil.copytree(paths.DBT_DIR, proj, ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"))
    f = proj / rel
    text = f.read_text()
    assert text.count(old) >= 1, f"mutation anchor not found in {rel}"
    f.write_text(text.replace(old, new))
    r = dbt_build(proj, raw, tmp_path / "w.duckdb")
    assert r.returncode != 0, f"mutation survived: {name}"
    failed = [l for l in r.stdout.splitlines() if " FAIL " in l or " ERROR " in l]
    for t in expected_failures:
        assert any(t in l for l in failed), f"{t} did not fail for mutation '{name}'. Failures:\n" + "\n".join(failed)
