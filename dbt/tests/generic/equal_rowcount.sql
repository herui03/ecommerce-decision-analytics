-- Local replacement for dbt_utils.equal_rowcount (same semantics: fails with one row
-- when the two relations have different row counts). Vendored so `dbt build` needs no
-- network access for `dbt deps`; the package hub is unreachable in offline/sandboxed
-- environments and a clean clone must still build.
{% test equal_rowcount(model, compare_model) %}
with a as (select count(*) as n from {{ model }}),
     b as (select count(*) as n from {{ compare_model }})
select a.n as model_rows, b.n as compare_rows, a.n - b.n as diff
from a cross join b
where a.n != b.n
{% endtest %}
