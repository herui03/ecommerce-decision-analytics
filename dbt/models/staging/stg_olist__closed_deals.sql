-- Grain: one row per mql_id (842). seller_id is ALSO unique -> clean 1:1.
-- These 842 are the positive class for lead scoring: 842/8,000 = 10.53%.
with source as (select * from {{ source('olist_raw', 'olist_closed_deals_dataset') }})

select
    mql_id,
    seller_id,
    sdr_id,
    sr_id,
    cast(won_date as timestamp) as won_at,
    business_segment,
    lead_type,
    lead_behaviour_profile,
    has_company,
    has_gtin,
    average_stock,
    business_type,
    cast(declared_product_catalog_size as double) as declared_catalog_size,
    cast(declared_monthly_revenue      as double) as declared_monthly_revenue_brl
from source
