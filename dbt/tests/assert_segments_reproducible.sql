{{ config(tags=['full_data']) }}
-- TAG full_data: this test hard-codes counts from the prior full-data run (2026-07-16).
-- It runs only against the real Kaggle CSVs; the synthetic sample excludes it
-- (`--exclude tag:full_data`) and runs the data-agnostic tests in tests/invariants/.
-- ---------------------------------------------------------------------------
-- The R/M segmentation must be REPRODUCIBLE across rebuilds.
--
-- WHY THIS TEST EXISTS
--   NTILE splits tied blocks to keep buckets equal. There are only 632 distinct
--   recency values across 96,096 customers -- 1,143 people share recency=327 --
--   so ties are everywhere and NTILE must cut through them. Without a deterministic
--   tie-break it cuts in PHYSICAL ROW ORDER, which changes on every rebuild.
--   Observed drift before the fix: Mid 34,617 -> 34,620 -> 34,628 across runs, with
--   the total always a correct 96,096. Nothing failed. The segmentation was simply
--   a different answer each time, and a customer could change segment because the
--   table got rebuilt.
--
--   Both NTILEs now carry `, customer_unique_id asc` as a tie-break. These counts
--   are the fixed point, verified by two consecutive --full-refresh builds.
--
-- Ties are still split -- that is inherent to NTILE and the price of equal buckets.
-- What is guaranteed is that the SAME customers split the SAME way every time.
-- ---------------------------------------------------------------------------
with actual as (
    select rm_segment, count(*) as n
    from {{ ref('mart_customer_segments') }}
    group by 1
),

expected (rm_segment, n) as (
    values
        ('Mid',               34628),
        ('Lapsed low-value',  15871),
        ('Recent high-value', 15847),
        ('Lapsed high-value', 14931),
        ('Recent low-value',  14819)
)

select
    e.rm_segment,
    e.n as expected_n,
    a.n as actual_n,
    a.n - e.n as drift
from expected e
full outer join actual a using (rm_segment)
where a.n is distinct from e.n

-- Quintile buckets must also stay even: NTILE guarantees it, and if this ever fails
-- the window function itself has changed behaviour under us.
