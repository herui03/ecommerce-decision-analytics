{{ config(tags=['invariant']) }}
-- The lead label and its point-in-time helpers, row by row:
--   * is_won_90d is exactly "won on day 0..90 after first contact" (inclusive), false
--     otherwise - including never-won leads (NULL won_date) and negative lags;
--   * label_mature_on is first_contact_date + 91 days;
--   * the point-in-time page count can never exceed the full-dataset (legacy) count,
--     and the earliest lead on each page has a prior count of 0.
with f as (select * from {{ ref('mart_lead_features') }}),
first_on_page as (
    select landing_page_id, min(first_contact_date) as first_date
    from f group by 1
)
select f.mql_id, f.is_won_90d, f.days_to_win, f.label_mature_on,
       f.page_lead_volume, f.page_lead_volume_prior
from f
join first_on_page fp using (landing_page_id)
where f.is_won_90d != coalesce(f.days_to_win between 0 and 90, false)
   or f.label_mature_on != f.first_contact_date + 91
   or f.page_lead_volume_prior > f.page_lead_volume - 1
   or (f.first_contact_date = fp.first_date and f.page_lead_volume_prior != 0)
