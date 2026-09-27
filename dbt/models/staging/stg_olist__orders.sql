-- Grain: one row per order_id (verified unique, 99,441).
-- Light cleaning only: rename, cast, no filtering. Orders with no items/payments are
-- KEPT here on purpose - dropping them is a business decision, not a staging one.
with source as (select * from {{ source('olist_raw', 'olist_orders_dataset') }}),

renamed as (
    select
        order_id,
        customer_id,                                    -- per-order key, NOT a person
        order_status,
        cast(order_purchase_timestamp as timestamp) as purchased_at,
        cast(order_approved_at        as timestamp) as approved_at,
        cast(order_delivered_carrier_date  as timestamp) as handed_to_carrier_at,
        cast(order_delivered_customer_date as timestamp) as delivered_at,
        cast(order_estimated_delivery_date as timestamp) as estimated_delivery_at,

        -- delivery performance: negative = early, positive = late.
        -- date_diff on days, not a raw timestamp subtraction, so partial days don't
        -- silently round in different directions across the two columns.
        date_diff('day',
                  cast(order_estimated_delivery_date as timestamp),
                  cast(order_delivered_customer_date as timestamp)
        ) as delivery_days_vs_estimate
    from source
)

select * from renamed
