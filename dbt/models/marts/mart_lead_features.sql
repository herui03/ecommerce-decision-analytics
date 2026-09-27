-- ---------------------------------------------------------------------------
-- mart_lead_features - GRAIN: one row per marketing-qualified lead. 8,000.
--
-- TARGET: is_won_90d - won within 90 days of first contact. NOT is_won_ever.
--
-- WHY A FIXED HORIZON
--   "Ever won" gives every lead a different observation window: a 2017-07 lead had
--   ~500 days to convert, a 2018-05 lead had 167. Comparing them measures how long
--   we watched, not how good the lead was. A 90-day horizon gives every lead an
--   identical window.
--
-- OBSERVATION CUTOFF IS AN ASSUMPTION, NOT A FACT (corrected 2026-09)
--   The earlier comment here claimed "zero right-censoring" because the last lead
--   (2018-05-31) + 90d = 2018-08-29 is before the latest recorded win (2018-11-14).
--   The latest POSITIVE event date does not prove that every NEGATIVE lead was
--   followed up for its full 90 days: the source does not document an outcome-
--   observation cutoff. Treat "wins are completely recorded through at least
--   2018-08-29" as an explicit analysis assumption (python/portfolio/leads.py
--   declares it as outcome_observed_through), not as something this data proves.
--
-- LABEL MATURITY (added 2026-09)
--   Convention: an as-of date means 00:00 on that date (information strictly before it
--   is known). The outcome window for a lead contacted on day c is c .. c+90 inclusive,
--   so it ENDS on c+90 and the label is usable from c+91 00:00 = label_mature_on.
--   A model "deployed" at as-of date T may only train on leads with label_mature_on <= T.
--   The historical model trained on Jan-Mar 2018 leads and was evaluated on Apr-May 2018
--   with a cut at 2018-04-01 00:00. The earliest training window (2018-01-01 contact)
--   ends 2018-04-01 and is usable from 2018-04-02; the latest (2018-03-31) ends
--   2018-06-29. NONE of its training labels was complete at the cut, so it is a
--   RETROSPECTIVE cohort backtest, not a prospective/deployable evaluation.
--
-- WHY THE HISTORICAL MODEL WINDOW STARTS 2018-01 (cause corrected 2026-09)
--   The 90-day conversion rate by lead month (historical log, prior full-data run):
--     2017-07: 0.00%   2017-08: 0.00%   2017-09: 0.00%   2017-10: 0.00%
--     2017-11: 1.80%   2017-12: 3.00%
--     2018-01: 11.31%  2018-02: 12.45%  2018-03: 11.93%  2018-04: 12.65%  2018-05: 8.37%
--   1,353 leads from Jul-Oct 2017 have ZERO recorded 90-day conversions and the first
--   recorded win is in 2017-12. That is an observed regime break. Its CAUSE IS UNKNOWN:
--   an earlier version of this comment asserted "there was no sales operation", which
--   the data cannot establish. Candidate explanations to investigate include sales
--   capacity/process not yet in place, closed deals only being recorded from late 2017,
--   or a CRM/pipeline change. Whatever the cause, a model trained across the break would
--   learn the date boundary rather than lead quality, which is why the window is
--   restricted - a modelling decision, not an organisational finding.
--   Historical model window: first_contact_date >= 2018-01-01 (no explicit end bound;
--   the data ends 2018-05-31). The corrected pipeline declares train, score and
--   observation windows explicitly instead.
--
-- KNOWN DATA CONTRADICTION: mql_id b91cf8812365f50ff4bda4bcd6206b05 has won_at
-- 2018-03-06 and first_contact_date 2018-03-08 -- won two days BEFORE first contact.
-- Kept and flagged, not silently patched. Its days_to_win is negative and therefore
-- excluded from the 0..90 target window by construction.
--
-- THE HARD RULE HERE: only information available AT THE MOMENT THE LEAD ARRIVES.
--
--   closed_deals carries business_segment, lead_type, lead_behaviour_profile,
--   declared_monthly_revenue_brl, declared_catalog_size. Every one of them looks
--   like a strong feature and every one of them is 100% target leakage: they exist
--   ONLY on the 842 rows that converted, because a salesperson records them AFTER
--   the deal closes. The other 7,158 leads don't have NULLs in those fields - they
--   have no row at all.
--
--   Train on them and the model learns "leads with a business_segment convert",
--   scores a near-perfect AUC, and is worthless on a live lead. A lead-scoring
--   model exists to rank leads BEFORE anyone has spoken to them, so the feature set
--   is whatever the form captured: a date, a channel, a landing page. That's it.
--
-- WHAT IS DELIBERATELY *NOT* HERE:
--   - No target encoding of landing_page_id. 247 of the 495 pages have exactly one
--     lead; target-encoding them would memorise the label. Any encoding that touches
--     the target must be fitted inside the CV fold, not here.
--   - page_lead_volume below is a FREQUENCY encoding - it counts leads per page and
--     never touches is_won, so it is not LABEL leakage. It is, however, computed over
--     the FULL dataset, including leads that arrive after the lead being scored and
--     leads in the test period: temporal (look-ahead) leakage. Kept unchanged ONLY so
--     the historical run stays reproducible; it is marked LEGACY.
--   - page_lead_volume_prior (added 2026-09) is the point-in-time replacement: the
--     number of leads on the same landing page with a STRICTLY EARLIER contact date.
--     Same-day leads are excluded because the source has no intra-day timestamp.
--     tests/test_leads.py asserts it is invariant to any change in later-dated rows.
-- ---------------------------------------------------------------------------

with leads as (
    select * from {{ ref('stg_olist__marketing_qualified_leads') }}
),

deals as (
    select * from {{ ref('stg_olist__closed_deals') }}
),

-- LEGACY: frequency of each landing page over ALL leads, past and future. Label-free
-- but look-ahead: see header. Kept only to reproduce the historical run.
page_volume as (
    select
        landing_page_id,
        count(*) as page_lead_volume
    from leads
    group by 1
),

-- Point-in-time: leads on the same page with a strictly earlier contact date.
page_volume_prior as (
    select
        l.mql_id,
        count(p.mql_id) as page_lead_volume_prior
    from leads l
    left join leads p
      on p.landing_page_id = l.landing_page_id
     and p.first_contact_date < l.first_contact_date
    group by 1
),

campaign_start as (
    select min(first_contact_date) as first_lead_date from leads
),

final as (
    select
        l.mql_id,

        -- ---- target -------------------------------------------------------
        -- The modelling target. BETWEEN 0 AND 90 also excludes the one negative-lag
        -- record, which is correct: a deal that closed before contact cannot be an
        -- outcome of that contact.
        -- coalesce is REQUIRED, not defensive noise. For the 7,158 leads that never
        -- converted, won_at is NULL, and `NULL between 0 and 90` evaluates to NULL --
        -- not false. Without the coalesce the target is NULL for every negative case,
        -- and a model trained on the non-nulls would see 100% positives and score a
        -- perfect AUC. dbt's not_null test caught this: FAIL 7158.
        coalesce(
            date_diff('day', l.first_contact_date, d.won_at::date) between 0 and 90,
            false
        ) as is_won_90d,

        -- Kept for comparison/reporting only. NEVER train on this -- the observation
        -- window differs per lead. 842 positives (10.53%) vs 677 (11.29%) in-window.
        (d.mql_id is not null) as is_won_ever,
        date_diff('day', l.first_contact_date, d.won_at::date) as days_to_win,
        d.won_at::date as won_date,

        -- First as-of date at which the 90-day label is complete (info strictly before
        -- this date covers contact day + 90). Train only on label_mature_on <= as-of.
        cast(l.first_contact_date + interval 91 day as date) as label_mature_on,

        -- ---- modelling scope ----------------------------------------------
        -- HISTORICAL window flag, lower bound only. The corrected pipeline
        -- (python/portfolio/leads.py) declares train / score / observation windows
        -- explicitly and does not rely on this open-ended flag.
        (l.first_contact_date >= date '2018-01-01') as is_in_model_window,

        -- ---- raw, available at lead time ----------------------------------
        l.first_contact_date,

        -- 60 leads have no channel recorded. Bucketed explicitly rather than
        -- dropped: "not recorded" is itself a state of the world, and this group
        -- converts at 23.33% - the highest of any channel - so dropping it would
        -- discard the strongest segment in the data.
        coalesce(l.lead_origin_channel, 'not_recorded') as lead_origin_channel,

        l.landing_page_id,
        p.page_lead_volume,                 -- LEGACY, look-ahead; do not use for new models
        pp.page_lead_volume_prior,          -- point-in-time replacement

        -- ---- derived from the contact date --------------------------------
        date_part('month',   l.first_contact_date)            as contact_month,
        date_part('year',    l.first_contact_date)            as contact_year,
        date_part('dayofweek', l.first_contact_date)          as contact_dow,   -- 0=Sun
        (date_part('dayofweek', l.first_contact_date) in (0, 6)) as is_weekend_contact,
        date_diff('day', c.first_lead_date, l.first_contact_date) as days_since_campaign_start

    from leads l
    left join deals d       on d.mql_id = l.mql_id
    left join page_volume p on p.landing_page_id = l.landing_page_id
    left join page_volume_prior pp on pp.mql_id = l.mql_id
    cross join campaign_start c
)

select * from final
