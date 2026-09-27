-- Local replacement for dbt_utils.unique_combination_of_columns. Returns one row per
-- duplicated key combination, so the failure count is the number of duplicated GROUPS
-- (the same measure dbt_utils reports - e.g. 9,803 for order_items keyed on order_id
-- alone, see docs/data-verification.md correction #6).
{% test unique_combination_of_columns(model, combination_of_columns) %}
select {{ combination_of_columns | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ combination_of_columns | join(', ') }}
having count(*) > 1
{% endtest %}
