{{ config(tags=['invariant']) }}
-- Data-agnostic NTILE check: 5 populated buckets per axis, sizes differing by at most 1.
with r as (select r_score as s, count(*) as n from {{ ref('mart_customer_segments') }} group by 1),
     m as (select m_score as s, count(*) as n from {{ ref('mart_customer_segments') }} group by 1),
     stats as (
        select 'r_score' as axis, count(*) as buckets, max(n) - min(n) as spread from r
        union all
        select 'm_score', count(*), max(n) - min(n) from m
     )
select * from stats where buckets != 5 or spread > 1
