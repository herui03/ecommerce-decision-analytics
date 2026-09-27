# Challenge 02: The Column That Turned a 59% Lift Into 2,676%

## TL;DR

**EN:** Criteo randomised `treatment`, but only 3.60% of the treated arm was actually
`exposed` to an ad, and exposure isn't random, it depends on whether the user browsed.
Analysing on exposure reports a +2675.83% lift against a true ITT of +59.45%: a 45×
overstatement, with a p-value of 7e-179 attached to it. I proved exposure was endogenous
by covariate balance (SMD 0.85 vs 0.007), reported ITT as the decision number, and used
exposure only as an instrument.

---

## What happened

The Criteo uplift dataset is a real randomised controlled trial: 13,979,592 rows, with
`treatment` (85% / 15%), `conversion`, and, invitingly, `exposure`.

`exposure` looks like the better variable. `treatment` only means "we were willing to show
this person an ad". `exposure` means "they actually saw it". Surely you want the effect of
seeing the ad?

The numbers agree, enthusiastically:

| | Conversion | n |
|---|---:|---:|
| exposed | **5.3784%** | 428,212 |
| control | 0.1938% | 2,096,937 |

**+5.1847 pp. +2675.83%.** The ad works 27× over. Ship it.

Except only **3.6037%** of the treated arm was ever exposed, and nothing randomised who.
Assignment was random; exposure is whatever the user's own browsing produced.

So I checked the balance, the same check that validates any RCT, just applied at both
levels:

| Split | f0 | f3 | SMD(f0) | SMD(f3) |
|---|---|---|---:|---:|
| **treatment** (randomised) | 19.6517 vs 19.6148 | 4.2328 vs 4.1694 | **0.0069** | **0.0488** |
| **exposure** (within treated) | 19.754 vs **15.890** | 4.2735 vs **1.3858** | **0.8524** | **1.4688** |

Randomisation is textbook-clean at `treatment`, SMDs of 0.007 and 0.049, well under the
0.1 convention. At `exposure` it is annihilated: **SMD 124× larger**, and f3's mean differs
*threefold*. The exposed aren't the treated-who-saw-an-ad. They're a different population.

And the tell that settles it:

```
treated but NOT exposed   0.1194%
control                   0.1938%
```

The unexposed treated convert *below* control. If exposure were as-good-as-random within
the treated arm, they'd match. They don't, because the people who never got exposed are
the people who barely browse, and those people rarely convert regardless.

The exposed group's 5.38% is mostly a story about who they are, not what we did to them.

---

## Why it matters

### (a) Technical

**Randomisation is a property of a *variable*, not of a dataset.** "This is an RCT" is not
a licence to condition on anything in it. `treatment` was assigned by a coin flip;
`exposure` was assigned by the user's behaviour, which is exactly the kind of thing that
also drives conversion. Conditioning on a post-treatment variable throws away the one
thing the experiment bought you. The dataset is still an RCT, you just stopped using it
as one.

**This is collider/selection bias, and it survives every check that isn't the right one.**
Sample size doesn't help, it makes the wrong number more precise. The covariates don't
warn you, unless you look. The p-value certainly doesn't: the trap's estimate comes with
overwhelming significance, because it is a real, large, reproducible difference between two
groups. It just isn't an effect.

**The exclusion restriction is subtler than it looks, and the arithmetic proves it.** My
first instinct was that treated-unexposed converting *below* control violated exclusion.
It doesn't. Control contains ~3.6% of people who *would* have been exposed, the compliers,
who convert well. Treated-unexposed excludes them by construction. So the comparison is
never-takers against a compliers/never-takers mix, and the inequality is exactly what
exclusion predicts. Decomposing it recovers a complier rate in control of **2.1820%**, and
`5.3784 − 2.1820 = 3.1964 pp`, which matches the Wald estimator `0.1152 / 0.036037 =
3.1964 pp` **to six decimal places**, from completely independent algebra. Two derivations
agreeing that exactly is the strongest evidence available that the model of the world is
right.

**Second trap, same dataset: n = 13,979,592 makes p-values meaningless.** `p = 7.31e-179`.
At 80% power this test detects **0.0093 pp**, the observed effect is **12× that**. A test
this over-powered will return "significant" for effects nobody would ever act on, so
significance carries no information about whether to act. The 95% CI, `[+0.1085, +0.1219]
pp`, is the actual finding: narrow, and far from zero.

### (b) Business / decision

**+2676% versus +59% isn't a rounding error, it's a different investment decision.** At 27×
return you spend everything you have. At 1.6× you compare it against your other channels
and you might well not. Both numbers are computed from the same real experiment; only one
of them is the campaign's effect.

**The wrong number is the one that gets shipped, because it's the one that looks like a
win.** Nobody in a review challenges a result that says the thing they funded works
spectacularly. The check that catches it, covariate balance on a post-treatment variable, 
is not in anyone's standard deck.

**ITT is the number you budget against, and this is the part people get wrong even after
they avoid the trap.** CACE (+146.49%) is a correct estimate: the ad genuinely more than
doubles conversion among people who see it. But you cannot buy "people who will see it".
You buy the campaign for everyone in the assigned population, and 96.4% of them never see
the ad. ITT (+59.45%) is what your money purchases. CACE tells you the creative works; ITT
tells you whether the media buy does.

**And low compliance is itself the finding.** 3.6% exposure means the money is going
somewhere other than eyeballs. That's a delivery problem worth more attention than another
decimal place on the lift, and it's invisible if you analyse on the exposed, because then
non-exposure has been quietly defined out of the analysis.

**Analyst-judgment note:** the exposure analysis is easier, more intuitive to explain, and
produces a triumphant result. Every incentive points at it.

---

## Analogy

You run a trial for a free gym membership. You randomly hand out vouchers, then measure
fitness a year later.

Only 3.6% of voucher recipients ever walk into the gym. You compare *those people* against
everyone who got no voucher, and conclude the membership made people 27× fitter.

But the people who used the voucher are the people who were going to work out anyway. The
voucher didn't make them fit; being the kind of person who redeems a gym voucher and shows
up is what made them fit. You've measured the redeemers, not the redemption.

The honest question isn't "how fit are the people who went?" It's "how much fitter is a
neighbourhood where we handed out vouchers than one where we didn't?" That's a much smaller
number. It's also the only one that tells you whether to print more vouchers.

And note the second finding hiding in plain sight: 96.4% of your vouchers went in the bin.

---

## The fix / decision

**1. ITT is the headline. Always, and on `treatment`.** Treated 0.3089% vs control 0.1938%
= **+0.1152 pp**, 95% CI **[+0.1085, +0.1219]**, **+59.45%** relative. Dilution by
non-compliance is not a flaw to correct, it's the reality of what a media buy delivers.

**2. `exposure` is an instrument, never a grouping variable.** CACE = ITT ÷ compliance =
0.1152 ÷ 0.036037 = **+3.1964 pp**, a **+146.49%** relative lift among compliers. Reported
alongside ITT, explicitly labelled as being about 3.6% of the population.

**3. Cross-check the CACE by a second, independent route.** The decomposition
(never-taker rate → implied complier rate in control → difference) agrees with Wald to
**0.000000 pp**. One derivation is a claim; two independent derivations agreeing is
evidence.

**4. Prove the endogeneity rather than asserting it.** Balance is checked at both levels.
SMD 0.0069 at `treatment`, 0.8524 at `exposure`, 124×. That table is the argument; without
it, "exposure is endogenous" is just something I read in a textbook.

**5. Lead with the CI, demote the p-value, and state the MDE.** At 80% power this test
detects 0.0093 pp. Saying so up front pre-empts the reviewer who wants to read `p < 0.001`
as though it means the effect is large.

**Why this was the right call:** the trap doesn't produce a *suspicious* number. It produces
a spectacular, highly significant, reproducible number that is 45× too big. Nothing catches
it except deciding, before you look, which variable was randomised.

---

## Evidence

| File | What it proves |
|---|---|
| `python/demo_exposure_trap.py` | The measured damage: +2675.83% vs +59.45%, 45.01× |
| `python/criteo/ab_analysis.py` | ITT + CI, MDE at 80/95% power, CACE via Wald **and** decomposition |
| `docs/data-verification.md` → "Criteo A/B analysis" | Balance table (SMD 0.0069 vs 0.8524), all figures |

---

*Data: Criteo Uplift Modeling dataset v2.1 (Kaggle: `arashnic/uplift-modeling`, CC0-1.0),
13,979,592 rows. All figures from real runs on 2026-07-16.*
