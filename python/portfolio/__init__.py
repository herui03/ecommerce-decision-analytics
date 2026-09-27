"""Portfolio pipeline: synthetic sample, metric contract, corrected lead scoring,
experiment statistics and the offline decision dashboard.

Every output this package writes carries a provenance label:

  HISTORICAL  - committed output of a prior full-data run (2026-07-16); not re-executed.
  RECOMPUTED  - computed in this build from committed historical inputs.
  SYNTHETIC   - produced from the deterministic synthetic sample. Not real data.
  HYPOTHETICAL- depends on user-entered assumptions (e.g. costs) absent from any dataset.
  UNAVAILABLE - the inputs cannot support the number; shown as such, never estimated.
"""
