{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- NTILE must produce 5 near-even buckets on both axes (19,219 x 4 + 19,220 = 96,096).
-- A bucket count outside 19,219..19,220 means the partitioning changed.
with r as (select r_score as s, count(*) as n from {{ ref('mart_customer_segments') }} group by 1),
     m as (select m_score as s, count(*) as n from {{ ref('mart_customer_segments') }} group by 1)
select 'r_score' as axis, s, n from r where n not between 19219 and 19220
union all
select 'm_score', s, n from m where n not between 19219 and 19220
