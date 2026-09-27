-- Grain: one row per (order_id, payment_sequential) - 103,886.
-- An order can be split across instruments/instalments; order_id repeats 4,446 times.
-- 99,440 distinct orders here vs 99,441 in orders → exactly one order has no payment
-- row (bfbd0f9bdef84302105ad712db648a6c, status=delivered). Kept, not patched.
with source as (select * from {{ source('olist_raw', 'olist_order_payments_dataset') }}),

renamed as (
    select
        order_id,
        cast(payment_sequential  as integer) as payment_seq,
        payment_type,
        cast(payment_installments as integer)     as payment_installments,
        cast(payment_value        as decimal(12,2)) as payment_value_brl
    from source
)

select * from renamed
