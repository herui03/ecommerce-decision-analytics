{{ config(tags=['invariant']) }}
-- Data-agnostic recency anchor: whoever placed the dataset's final order has zero days
-- since their last order. Anchoring to current_date makes that impossible.
select min(days_since_last_order) as min_days
from {{ ref('dim_customers') }}
having min(days_since_last_order) != 0
