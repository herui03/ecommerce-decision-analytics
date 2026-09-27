# Challenge 05: A Regime Break in the Target (Cause Unknown)

_Original title: "The Target Was Measuring the Sales Team, Not the Lead"._

> **Correction (2026-09 upgrade, raised in independent review).** This write-up originally
> stated as fact that the 2017 leads failed because "no sales team existed yet", that the
> 90-day window had "zero censoring", and that the top decile meant "53 wins instead of 28".
> None of those three is established by the data:
> - **Cause of the regime break: unknown.** The data shows zero 90-day conversions for the
>   Jul–Oct 2017 cohorts and a first recorded win in 2017-12. Missing sales capacity is one
>   hypothesis; late start of deal recording or a CRM/pipeline change are others.
> - **Observation cutoff: an assumption.** The latest recorded win (2018-11-14) does not prove
>   every non-converted lead was followed for 90 days; the source documents no cutoff.
> - **53 vs 28 is retrospective ranking, not incremental wins.** It is also tie-dependent
>   (52–54 across tie-breaks), and the historical split trained on labels that were not yet
>   complete at its 2018-04-01 cut.
>
> The observed rates below are unchanged. Sentences that assert the organisational cause are
> kept as the record of the original reasoning and marked *(hypothesis)*. The corrected
> pipeline is in `python/portfolio/leads.py`; see `docs/defect-log.md`.

## TL;DR

**EN:** 1,353 leads from Jul–Oct 2017 converted at exactly 0.00% within 90 days, because
no deal of any kind closed until December 2017. The label wasn't measuring lead quality, it
was, on this hypothesis, measuring whether a sales team existed yet *(hypothesis; cause unknown)*. I restricted the model window to 2018-01
onwards (5,998 leads, 11.29% positive) and switched the target to a fixed 90-day horizon so
every lead has an identical observation window.

---

## What happened

The task: score marketing-qualified leads so sales calls the promising ones first.
8,000 leads, 842 converted, a 10.53% positive rate, a workable balance. Straightforward.

Then I looked at the conversion rate by lead month, using a fixed 90-day horizon so every
lead is compared on equal terms:

| Lead month | Leads | Won ≤90d | Rate |
|---|---:|---:|---:|
| 2017-07 | 239 | **0** | **0.00%** |
| 2017-08 | 386 | **0** | **0.00%** |
| 2017-09 | 312 | **0** | **0.00%** |
| 2017-10 | 416 | **0** | **0.00%** |
| 2017-11 | 445 | 8 | 1.80% |
| 2017-12 | 200 | 6 | 3.00% |
| 2018-01 | 1,141 | 129 | **11.31%** |
| 2018-02 | 1,028 | 128 | 12.45% |
| 2018-03 | 1,174 | 140 | 11.93% |
| 2018-04 | 1,352 | 171 | 12.65% |
| 2018-05 | 1,303 | 109 | 8.37% |

**Zero.** Not a low rate, 1,353 leads over four months, not one of which converted inside
90 days. No lead source on earth is that bad.

So I looked at when deals actually closed:

```
2017-12     3
2018-01    73  ################
2018-02   113  ##########################
2018-03   147  ##################################
2018-04   207  ################################################
2018-05   122  ############################
2018-06    57  #############
...
```

**The first deal of any kind closed in December 2017, six months after leads started
arriving.** And the 2017 leads that did eventually convert waited an average of **398 days**
(the 2017-07 cohort). They weren't rejected. They sat in a queue until somebody was hired
to call them.

*(Hypothesis, original wording:)* the label was never describing the lead. It was describing whether a sales operation
existed on the day the lead arrived.

---

## Why it matters

### (a) Technical

**The target is non-stationary, and the strongest feature would encode that.**
`days_since_campaign_start` is available at prediction time, it passes every leakage check
you can write. It would also dominate the model, and what it encodes is *"was this lead
before or after the sales team got hired?"* That's a real, true, perfectly predictive fact
about 2017 and it has zero applicability to a lead arriving tomorrow, when the sales team
already exists for every row. The model would be right on the test set and useless in
production. **Leakage detection doesn't catch this, the feature genuinely is knowable in
advance. Only knowing what the business did catches it.**

**Random cross-validation would have hidden it entirely.** A random split smears a 0%
regime and a 12% regime into every fold. Both train and test get some of each, the model
learns the date boundary, and CV reports a score that no future deployment could achieve.
The split has to be temporal because the data-generating process changed.

**Two separate mechanisms, easy to confuse.** *Right-censoring* is "we stopped watching", 
a 2018-05 lead had 167 days of observation, a 2017-07 lead had ~500. That's real and the
fixed 90-day horizon fixes it. *The regime break* is "nobody was working the queue", a
completely different problem that no horizon fixes. I could only tell them apart by
checking `won_at`: under the 90-day horizon the 2017 cohorts stay at 0.00%, which rules out
censoring *as the sole cause* and leaves an organisational or recording explanation *(which one is unknown)*.

**And the rich features were pure leakage.** `closed_deals` carries `business_segment`,
`lead_type`, `declared_monthly_revenue_brl`, `declared_catalog_size`, everything you'd
want. All of it is entered by a salesperson *after* the deal closes. The 7,158 unconverted
leads don't have NULLs in those columns; they have no row at all. Train on them and you get
a near-perfect AUC from a model that cannot score a lead that hasn't converted yet.

### (b) Business / decision

**Trained on the raw data, the model tells sales to ignore leads for being old.** It would
learn that 2017 leads never convert and rank them at the bottom, and the reason they never
converted is that the model's own employer never called them. It would then justify not
calling them. The prophecy closes the loop, the data confirms the model was right, and
nobody ever finds out those leads were fine.

**This is what a "biased model" actually looks like in practice**, not a demographic
protected attribute, but a label produced by the company's own past behaviour and then fed
back as ground truth. The 2017 leads are labelled negative because of an internal staffing
decision, and a model trained on that label operationalises the staffing gap as a
permanent judgement about lead quality.

**And the honest finding is worth more than the model.** "1,353 leads went completely
unworked for four months" is a real operational finding a sales director would want. It's
not a modelling problem to route around, it's the most valuable thing in the dataset,
and it only shows up if you look at the target before you fit anything to it.

**Analyst-judgment note:** including 2017 would have made every metric look better. More
data (8,000 vs 5,998), a stronger feature (`days_since_campaign_start`), higher AUC. The
model would have been more impressive and less true. Cutting 25% of the rows to remove a
regime that no longer exists is the whole job.

---

## Analogy

You're asked to predict which job applicants are worth interviewing, and you train on who
got hired.

You don't know that for the first four months of the data, the company had no recruiter.
Every application from that period is labelled "not hired", not because those people were
weak, but because nobody opened the inbox.

Your model learns that applications submitted in spring are worthless. It's *right* about
the data. And if the company deploys it, it will filter out every spring applicant forever,
and every year the data will confirm the model was correct.

The applications weren't bad. The inbox was closed. That fact is invisible in the label,
and no amount of cross-validation will reveal it, you have to go and ask what the company
was doing that spring.

---

## The fix / decision

**1. Fixed 90-day target horizon.** `is_won_90d`, not `is_won_ever`. Every lead gets an
identical observation window. Last lead 2018-05-31 + 90d = 2018-08-29; last recorded win
2018-11-14 → consistent with complete follow-up, *which is an assumption, not a verified fact*. (Time-to-win:
median 14 days, p75 55, p90 162, 90 days captures the great majority.)

**2. Model window 2018-01 → 2018-05.** 5,998 leads, 677 positives, **11.29%**. Out of
window: 2,002 leads, **0.70%**. The contrast is the justification.

**3. Dropped every time feature.** No `contact_month`, no `contact_year`, no
`days_since_campaign_start`. Day-of-week survives, because it recurs in both train and test
and doesn't encode a regime.

**4. Dropped every `closed_deals` feature.** The entire feature space is what the form
captured: a channel, a landing page, a date.

**5. Temporal split.** Train 2018-01→03 (n=3,343, 11.88% positive), test 2018-04→05
(n=2,655, 10.55%). The base rate shifts between them, that's the honest situation, and
exactly what a random split would have papered over.

**6. Kept everything in the mart, flagged.** `mart_lead_features` holds all 8,000 rows with
`is_in_model_window` and both targets. The window is a modelling decision, and it's visible
and reversible rather than baked in by a deleted row.

**7. `not_null` caught a bug this created.** Writing the target as
`date_diff(...) between 0 and 90` returns **NULL**, not false, for the 7,158 leads with a
NULL `won_at`, SQL three-valued logic. dbt failed with exactly 7158. Without that test I'd
have trained on positives only and scored a perfect AUC. Fixed with `coalesce(..., false)`.

**Why this was the right call:** the alternative is a model that recommends ignoring leads
because the company previously ignored them.

---

## Evidence

| File | What it proves |
|---|---|
| `dbt/models/marts/mart_lead_features.sql` | 90-day target, window flag, leakage exclusions, with the reasoning in the header |
| `python/train_lead_scoring.py` | Temporal split, baselines, the design notes an interviewer would attack |
| `docs/data-verification.md` → "Lead scoring" | The 0.00% table, deal-close distribution, full results |
| `outputs/lead_scoring_results.csv` | AUC / PR-AUC / Brier / lift for all four models |
| `outputs/lead_scores_test.csv` | 2,655 scored held-out leads |

---

*Data: Marketing Funnel by Olist (Kaggle: `olistbr/marketing-funnel-olist`,
CC-BY-NC-SA-4.0). All figures from real runs on 2026-07-16.*
