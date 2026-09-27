{{ config(tags=['invariant']) }}
-- Data-agnostic version of assert_facts_agree_on_money: no hard-coded counts, so it
-- runs on the synthetic sample AND the full data. The two facts live at different
-- grains but must carry the same item money, and the item fact must cover exactly the
-- orders that the order fact says have items.
with o as (
    select sum(items_total_brl) as items_brl,
           count(*) filter (where not has_no_items) as orders_with_items
    from {{ ref('fct_orders') }}
),
i as (
    select sum(item_total_brl) as items_brl,
           count(distinct order_id) as distinct_orders
    from {{ ref('fct_order_items') }}
)
select *
from o cross join i
where o.items_brl is distinct from i.items_brl
   or o.orders_with_items != i.distinct_orders
