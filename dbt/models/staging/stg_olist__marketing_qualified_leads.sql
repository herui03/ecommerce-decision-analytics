-- Grain: one row per mql_id (8,000). B2B SELLER-acquisition funnel, not consumer marketing.
with source as (select * from {{ source('olist_raw', 'olist_marketing_qualified_leads_dataset') }})

select
    mql_id,
    cast(first_contact_date as date) as first_contact_date,
    cast(landing_page_id as varchar) as landing_page_id,
    origin as lead_origin_channel
from source
