-- Grain: one row per (review_id, order_id) - 99,224.
-- WARNING: review_id is NOT unique (814 dupes) and order_id is NOT unique (551 dupes).
-- The natural-looking key is a trap; treat review_id as an attribute.
with source as (select * from {{ source('olist_raw', 'olist_order_reviews_dataset') }}),

renamed as (
    select
        review_id,                                   -- attribute, NOT a key
        order_id,
        cast(review_score as integer) as review_score,
        review_comment_title,
        review_comment_message,
        cast(review_creation_date   as timestamp) as review_created_at,
        cast(review_answer_timestamp as timestamp) as review_answered_at
    from source
)

select * from renamed
