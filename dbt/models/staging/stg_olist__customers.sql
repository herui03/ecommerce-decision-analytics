-- Grain: one row per customer_id (99,441) = one row per ORDER, not per person.
-- customer_unique_id resolves to 96,096 real people; 96.88% of them ordered exactly once.
with source as (select * from {{ source('olist_raw', 'olist_customers_dataset') }}),

renamed as (
    select
        customer_id,           -- per-order key
        customer_unique_id,    -- person-level key  <- use this for anything customer-level
        cast(customer_zip_code_prefix as varchar) as customer_zip_prefix,
        customer_city,
        upper(customer_state) as customer_state
    from source
)

select * from renamed
