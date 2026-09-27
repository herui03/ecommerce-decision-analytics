-- Grain: one row per product. 32,951 rows - ALL of them.
--
-- WHY LEFT JOIN AND COALESCE, NOT INNER JOIN
--   The PT→EN lookup has 71 rows but the product table carries 73 distinct PT
--   categories. Two are missing from the lookup entirely:
--     portateis_cozinha_e_preparadores_de_alimentos (10 products)
--     pc_gamer                                       (3 products)
--   A further 610 products have a NULL category.
--   An INNER JOIN here would silently drop 623 products and every order line that
--   references them - revenue would quietly go missing from category reporting with
--   no error. LEFT JOIN keeps all 32,951; coalesce falls back to the PT name so the
--   category is still usable; the flag makes the gap visible instead of invisible.
with products as (select * from {{ ref('stg_olist__products') }}),
     lookup   as (select * from {{ ref('stg_olist__product_categories') }})

select
    p.product_id,
    p.product_category_pt,
    l.product_category_en,

    -- Reporting label: EN where we have it, PT where we don't, explicit bucket for NULL.
    coalesce(l.product_category_en, p.product_category_pt, 'unknown') as product_category,

    (p.product_category_pt is null)                                    as has_no_category,
    (p.product_category_pt is not null and l.product_category_en is null) as missing_translation,

    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm * p.product_height_cm * p.product_width_cm     as product_volume_cm3
from products p
left join lookup l on l.product_category_pt = p.product_category_pt
