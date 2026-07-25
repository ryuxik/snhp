# AMENDMENT 11 — un-fit `p_exo_*`, `courage_med` and `belief0`

*Written 2026-07-25, **before any A11 run**. Filed in its own file because
`PREREG.md` is held open by another worker. Kills K31 and K32 are fixed here,
stated on OUTPUTS, and bidirectional: each says what a non-firing means as well
as what a firing means.*

`PREREG.md` is the parent document; nothing here supersedes it. Results go to
`RESULTS-A11.md` (`RESULTS.md` is likewise held open).

---

## A11.0 Why these three, and why together

`principles.py:PARAM_SOURCES` currently lists nine CIRCULAR constants. Three of
them are the two loops `FREE-OUTPUTS.md` §1 calls out as *compounding* — pairs
of parameters fitted to two halves of one observed fact, which is the shape
Principle G rule 1 exists to catch:

| loop | parameters | the one fact both halves come from |
|---|---|---|
| retention | `p_exo_floor` + `p_exo_extra` (with `move_med`) | NAA turnover ~47% / RealPage retention ~54–57% |
| the counter rate | `courage_med` + `belief0` | Avail/Urban 2022: 39% counter, 61% never ask |

`PREREG.md` §2's own grounding table prints *"Annual turnover (calibration
target) ~47%"* and *"Retention (calibration target) ~54–57%"* — the words
"calibration target" are in the table — and then §3 makes retention **V2**. V2
is therefore an identity, and it is **the only gate criterion this study has
ever passed on the first attempt.** `FREE-OUTPUTS.md` §2 states this and
`principles.py` pins it in a test. A fitted gate that *passes* is where the
damage happens.

The counter-rate loop is the same shape one level down. `world.py:122` says it
in terms: *"Set so that at the pessimistic prior belief the endogenous counter
rate lands near the observed 39%."* `belief0`'s first-pass audit note already
read *"an output not a source."* The counter rate is the phenomenon **arm F
exists to measure.**

Both loops are removed here. Neither is "fixed" — a parameter cannot be fixed by
a better number if the honest answer is that we do not have one. The test is
whether the observable survives being let go.

## A11.1 What is NOT being attempted

Per A6.3's stopping rule and A8.0's reading of it: this is a **defect fix**,
the same class as A7 (`renewal_cap`) and A8 (`move_med`). It is **not** an
attempt to pass any gate. Per DESIGN-PRINCIPLES E, **if a gate passes under
un-fitted parameters that is a suspicious result requiring a bug hunt before it
is believed, not a vindication.** Both kills below are written so that the
convenient outcome is the one that triggers the hunt.

No `Params` default is changed. The shipped defaults are what every published
run in `RESULTS.md` used, and three other workers are running against them right
now; changing them would silently invalidate work in flight and make the
before/after tables unreproducible. A11's sourced values are declared as named
module constants in `world.py` and passed as explicit overrides, exactly as
AMENDMENT 9 passed its `move_med` crossing.

---

## A11.2 JOB 1 — `p_exo_floor = 0.24`, `p_exo_extra = 0.18`

### A11.2.1 The defect

```python
def p_exo(p, j):
    """...NAA's ~47% annual turnover is mostly not about rent."""
    return p.p_exo_floor + p.p_exo_extra * np.exp(-(j - 1.0) / p.p_exo_tau)
```

`0.24 + 0.18·exp(−(j−1)/3)` runs from **0.42** at first renewal to **0.257** at
j=8, mean **0.3139** over j=1..8. Its cited source, NAA turnover ~47%, is V2's
calibration target. Read alone that looks like data. Read against the register it
is the non-rent half of the number the gate measures, with `move_med` fitted to
the rent-driven half.

An arithmetic check on how much of the target was imported: **0.42 / 0.47 =
0.894.** The shipped parameter, evaluated at first renewal against the cited
turnover figure, asserts that **89% of first-year renter moves are not about
rent.** That claim was never sourced. It falls out of the fit.

### A11.2.2 The source, and why it is upstream

Non-rent moves are genuinely exogenous to the model, so they cannot be derived
from inside it. They must come from data that is not a validation target.

**Primary source, verified by direct download from census.gov:**

> U.S. Census Bureau, *Geographic Mobility: 2023* (1-year table package from the
> **2023 Current Population Survey Annual Social and Economic Supplement**),
> released 10 December 2024.
>
> - **Table 13** — *Reason for Move in the Past Year (Both Collapsed and Specific
>   Categories), by … Tenure … : 2023*
>   `https://www2.census.gov/programs-surveys/demo/tables/geographic-mobility/2023/cps-2023/mig_13_2023_1yr.xlsx`
> - **Table 1** — *General Mobility in the Past Year, by … Tenure … : 2023*
>   `https://www2.census.gov/programs-surveys/demo/tables/geographic-mobility/2023/cps-2023/mig_01_2023_1yr.xlsx`
>
> Landing page: `https://www.census.gov/data/tables/2023/demo/geographic-mobility/cps-2023.html`
> 2023 is the most recent published year; the 2024 and 2025 packages do not exist
> at the time of writing.

**ACS is not usable for this.** The ACS collects mobility and tenure but does
**not** ask reason for move; only the CPS ASEC does (question added 1998).
Reason for move is therefore CPS-only, and everything below is CPS.

**Table 13, row "In a renter-occupied housing unit" (numbers in thousands):**

| collapsed category | count | share |
|---|---|---|
| Total movers | 16,337 | 100.00% |
| Family-related | 3,496 | 21.40% |
| Employment-related | 3,845 | 23.54% |
| Housing-related | 6,330 | 38.75% |
| Other | 2,665 | 16.31% |

Housing-related, in specific categories:

| specific reason | count | share of all renter moves |
|---|---|---|
| Wanted newer/better/larger house or apartment | 2,207 | 13.51% |
| **Cheaper housing** | **1,793** | **10.98%** |
| Other housing reason | 1,065 | 6.52% |
| Wanted better neighborhood / less crime | 967 | 5.92% |
| Wanted to own home, not rent | 149 | 0.91% |
| Foreclosure / eviction | 149 | 0.91% |

**Table 1, same row:** total 101,024; nonmovers 84,687; movers 16,337 →
**renter mover rate = 16.1714%/yr.**

This is upstream of everything the model predicts. It is a different survey
(CPS ASEC), a different producer (Census), a different unit of analysis
(persons, all renters) and a different quantity (composition of moves) from the
NAA/RealPage unit-level apartment turnover the model is asked to reproduce.
Nothing in the model was ever set by reference to it.

### A11.2.3 The functional form the data supports — it is NOT the shipped one

**CPS publishes reason for move by sex, age, race, relationship, education,
marital status, nativity, tenure, poverty status and type of move. It does not
publish it by length of residence.** There is no published tenure-duration
gradient in reason-for-move to source `0.18·exp(−(j−1)/3)` from, and
`p_exo_tau = 3.0` is already classified INVENTED ("decay constant, no stated
source").

Registered consequence, fixed here rather than after seeing any output: **the
form the data supports is a constant.** The sourced specification sets
`p_exo_extra = 0` and puts the whole hazard in `p_exo_floor`. The decay is not
deleted from the study — it is demoted to an INVENTED shape and ablated (§A11.2.5
variants S1d/S2d), per Principle C rule 2.

### A11.2.4 Two mappings, both declared now

The Census categories do not map onto "rent-driven" without a modelling choice,
so both defensible choices are registered in advance and both are reported.

- **M1 — non-housing (the literal reading).** Non-rent = family + employment +
  other. Share = 10,006/16,337 = **0.612475**. This treats *every* housing-related
  reason as potentially a response to the rent, which is the choice that leaves
  the model's endogenous channel the most work to do.
- **M2 — non-price (the model's own reading).** The model's endogenous exit is a
  logit on `gain_base − switching cost`: a price response to the rent offered
  against market. The Census category that is a price response is **"Cheaper
  housing"**. Non-rent = 1 − 1,793/16,337 = **0.890249**. Under M2, wanting a
  bigger apartment, a better neighbourhood, or to buy a home are exogenous —
  which is what `world.p_exo`'s own docstring already says ("job, household,
  **home purchase**").

**M1 is the registered primary**, because it is the reading the task names and
the conservative one. M2 is a registered secondary and is reported beside it.

**Stated in advance so it cannot be claimed as a discovery:** M2 × the cited NAA
figure gives 0.890 × 0.47 = 0.418, and the shipped `p_exo(1)` is 0.42. If that
turns out to line up it is *not* a validation of the shipped parameter. It means
the fit silently adopted M2's mapping and the apartment-sector turnover level at
the same time, and only the mapping half of that has any source.

### A11.2.5 The sourced values, fixed before running

`p_exo` is a **hazard** (probability per tenancy-year), so it needs a level as
well as a composition: `p_exo = (renter mover rate) × (non-rent share)`.

| variant | form | `p_exo_floor` | `p_exo_extra` | basis |
|---|---|---|---|---|
| **F** (baseline) | decay | 0.24 | 0.18 | the shipped fitted value |
| **S1** *(primary)* | **flat** | **0.099046** | **0.0** | 0.161714 × 0.612475 (CPS, M1) |
| **S2** | flat | 0.143966 | 0.0 | 0.161714 × 0.890249 (CPS, M2) |
| S1d | decay | 0.075738 | 0.056803 | S1's mean, shipped shape (shape ablation) |
| S2d | decay | 0.110087 | 0.082565 | S2's mean, shipped shape |
| S3 | flat | solved | 0.0 | **composition-anchored**: see below |

S1d/S2d rescale the shipped shape by a constant so its **unweighted mean over
j=1..8 (0.313859)** equals the sourced flat value. Level and shape then move
separately, and any difference between S1 and S1d is the INVENTED decay's
contribution and nothing else.

**S3, the composition-anchored variant.** S1/S2 import the CPS mobility *level*,
which is measured on all renters and not on the professionally-managed apartment
segment the model's targets come from. S3 drops the level entirely and uses only
the Census *composition*: choose flat `p_exo` such that the model's own share of
leavers whose exogenous draw fired equals M1's 0.612475, leaving the turnover
level completely free. It is a fixed point in the model's endogenous rate, not a
fit to any target, and it is reported as a secondary.

**Declared limitation, before the numbers exist.** The CPS rate is
person-weighted, all-renter, and tenure is recorded at the **destination**, so a
renter who moved into a home they bought is counted in the owner row, not the
renter row (the renter row's "wanted to own home, not rent" is 149k against the
owner row's 1,594k). S1/S2 therefore **understate** the hazard of exit from a
rental, and the model's target segment is more mobile than all renters. This is
declared now so that a low modelled turnover is read as what it is — a
population mismatch we can name — rather than discovered afterwards as an
excuse.

### A11.2.6 What becomes free

With `p_exo_*` sourced, `FREE-OUTPUTS.md` row 2 changes. `move_med` remains
CALIBRATED, so the **rent-driven** half of turnover is still fitted; the
**non-rent** half is not. Retention is therefore no longer an identity. It is a
half-free observable, and V2 becomes a partial test for the first time. Reported
as *partly free*, not as free — Principle G rule 1 is not repealed by fixing one
of two parameters, and A8 (`move_med` from search) is the other half.

### A11.2.7 K31 — the sourced hazard does not reproduce observed retention

**K31 FIRES if**, under variant S1, modelled retention lands **outside
52–62%** (observed ~57.3%, the midpoint of RealPage's 54–57% band and NAA's
implied 53%). Measured on Phase 1 arm A (39% price askers), registered
specification, main seeds, both regimes reported and the kill evaluated on each.

- ***If it fires:*** published as a negative. It means the non-rent move rate we
  can source from the Census cannot carry the turnover the model was tuned to
  reproduce, and the 0.24/0.18 pair was importing the validation target's level
  under the description of a hazard. V2's historical PASS is then not merely an
  identity but a **wrong** one, and every retention number in `RESULTS.md`
  becomes a readout of a parameter with no source. This is the outcome I expect;
  saying so in advance is the point of writing it down.
- ***If it does NOT fire:*** it is the convenient outcome and gets the
  DESIGN-PRINCIPLES E bug hunt **before** it is believed — specifically: (a) is
  the sourced value actually reaching the station's DP, or is a cached policy
  built on the old one? (b) does the endogenous channel absorb the change
  because `move_med` was calibrated against the old `p_exo`, making the pair
  jointly, not separately, identified? (c) is retention being measured over
  renewals only, so term-locked crabs are excluded from the denominator? Only
  after all three come back clean may a non-firing be reported as V2 surviving.

**Non-firing is not a pass for V2 either way.** `move_med` is still fitted to the
other half. The most a non-firing can license is "retention survives sourcing one
of its two fitted inputs."

### A11.2.8 Downstream, all reported before/after

Every result the audit traced to `p_exo_*`, re-run under F and S1 (and S2 where
it is cheap):

1. **GATE 1 V2** — retention 0.45–0.65. Re-run.
2. **GATE 3 V10** — market-side endogenous retention within 5pp of Phase 1's.
   `market.simulate_market` takes `Params`, so the sourced hazard flows in
   unmodified. Both sides move; report both and the gap.
3. **K21** — `market.py:541` sets `stay = 1/p_exo(p, j)`, and the −$706 net
   move-gain figure and its quartile table are the tenant's moving cost
   amortised over that. A smaller hazard means a longer expected stay and a
   smaller annual amortisation, so K21 is **mechanically** sensitive to this
   parameter. Report the net gain, the share for whom moving wins, and all four
   quartiles, before and after. **Registered in advance: K21's bar is $480 of
   raw annual saving; if the verdict flips, the flip is a property of `p_exo`
   and must be reported as such, not as a finding about tenants.**
4. **K18** ("mutual engines destroy value — did not fire; turnover falls").
   Re-run and report whether the turnover direction survives.
5. **A7's "you can have either observed fact, not both"** — capped push +10.73%
   with retention 60.1%, free push +13.81% with retention 56.1%. The audit's
   objection is that this is a tension between two *fitted* facts and so may not
   be a real tension. Re-run the free-cap/capped pair under S1 and report
   whether the trade-off survives when only one of the two is fitted.

## A11.3 JOB 2 — `courage_med = 0.18`, `belief0 = 0.10`

### A11.3.1 The defect

Arm F's ask rule (`world._set_endogenous_askers`):

```
worth = belief × ask_scale × ask_frac × 12 × max(q, 0.1)      # ≈ belief × 1.45 months
ask if worth > courage                                        # courage ~ lognormal(med, 0.8)
```

At `belief0 = 0.10` and `courage_med = 0.18`, `P(courage < 0.145)` = **0.394**.
The observed number is 0.39. Two parameters, one observation, and the counter
rate is what arm F measures.

### A11.3.2 `courage_med` — what is upstream, and what is not

The only cost of sending the message that has an upstream anchor is the sender's
**time**. That anchor already exists in this repo and predates A11:
`demographics.INCOME_MEDIAN = $75,000` (ANCHORED, ACS renter median for the
market-rate segment), which `searchcost.TIME_COST` already converts at
**$36.06/hour** full-time-equivalent (its own comment: *"$75,000 → ~$36/h"*).

**Registered value: `courage_med = 0.018029` months = $36.06 = one hour** — read
the renewal notice, look up two comparable listings, write the email. The wage is
ANCHORED and upstream of rent-setting; the *one hour* is INVENTED, exactly the
label `TIME_COST` already carries ("ANCHORED wage, INVENTED hours. Swept."), and
it is swept.

**Stated before running:** the shipped 0.18 months is $360, which at this same
wage is **9.98 hours** to send one email. That is not a cost, it is a fitted
residual wearing a cost's name. Everything above the time cost is a psychological
premium — fear of retaliation, conflict aversion, fear of non-renewal — for which
**no published dollar value exists**. That premium is therefore INVENTED, and per
Principle C rule 1 the honest handling is to sweep it across its full plausible
range rather than fix it at the value that reproduces 39%:

`courage_med ∈ {0.0045, 0.0090, 0.0180, 0.0361, 0.0721, 0.1803, 0.36, 0.72, 1.44}`
(15 min, 30 min, **1 h**, 2 h, 4 h, 10 h = the shipped value, 20 h, 40 h, 80 h).

`courage_sigma = 0.80` stays INVENTED and is swept over {0.4, 0.8, 1.2}, because
the counter rate depends on the dispersion as well as the median.

### A11.3.3 `belief0` — the prior, chosen and justified before running

**Registered primary: `belief0 = 0.50`, the uninformative prior.** A tenant who
has never asked has no basis for any particular number; the mean of a
Beta(1,1) prior over an unknown success probability is 0.5. It is a stated
modelling convention with no published counterpart, so it is **INVENTED**, and it
is swept: `belief0 ∈ {0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.95}`.

**Registered secondary: the model-consistent prior**, a fixed point in which
`belief0` equals the success rate the model itself generates (iterate
`belief0 ← realised success rate` to convergence or 6 iterations). Reported, and
reported with its defect: the realised success rate is `FREE-OUTPUTS.md` row 1,
which is **FITTED** through `vacancy`, `face_premium` and `renewal_cap`. So the
fixed point inherits `vacancy`'s circularity and cannot be the primary. This is
why the uninformative prior is primary despite being less clever.

`belief0` is load-bearing beyond the first year: without broadcast, a crab that
never asks never updates, so the prior is the permanent belief of every
non-asker. That is precisely why fitting it to the 61% who never ask was
circular.

### A11.3.4 K32 — the free counter rate

**K32 FIRES if**, with `courage_med = 0.018029` and `belief0 = 0.50` and no
other change, the endogenous counter rate in arm F lands **outside 29–49%**
(observed 39% ± 10pp). Measured on arm F, institutional, broadcast **off** (the
control), both regimes, exploratory specification (arm F is only run there;
under the registered spec the institution concedes to nobody).

- ***If it fires:*** **do not tune it back.** Published as the headline of Job 2:
  *once we stop assuming the cost of asking, this model predicts most tenants
  would counter, and it cannot explain why 61% of renters never do.* Arm F's
  counter rate then joins the readouts, and the article may not use the model to
  explain the courage problem — only to say the courage problem is not explained
  by the economics of asking. Additionally report the `courage_med` that *would*
  reproduce 39% at the uninformative prior, in hours of the ACS wage, as the size
  of the thing the model is missing.
- ***If it does NOT fire:*** the convenient outcome, and per Principle E it gets
  the harder look. Hunt specifically for: (a) is `courage_med` actually being
  applied, or is `new_crab` drawing courage from a stale `Params`? (b) is the
  counter rate being suppressed by the `locked > 0` skip in
  `_set_endogenous_askers`, so that the denominator is renewals but the numerator
  is unlocked renewals? (c) does `ask_scale` collapse and drag `worth` down, so
  that the rate is set by the learning rule rather than by the prior? Only if all
  three come back clean may a non-firing be reported.

### A11.3.5 Downstream, all reported before/after

1. **Phase 2 §7 arm F** — the whole table: ask share, mean belief, ask scale,
   success, surplus, askers, non-askers, station cash, for all six
   type × broadcast cells plus F-adaptive.
2. **K7 — "our product is net-harmful at scale."** Re-run under un-fitted
   `courage_med` and `belief0`, both regimes, broadcast off vs on, adaptive
   institutional. **K7's DIRECTION is printed on a live user-facing page**
   (`snhp.dev/rent`). `FREE-OUTPUTS.md` row 16 classifies the externality as
   FREE, so the direction is claimable in principle — but "free" is not "robust",
   and the direction is verified here rather than assumed. Registered in advance:
   **if the sign of the broadcast effect on total crab surplus flips under any
   un-fitted variant, that goes to the page**, not into a footnote, per PREREG §7.
3. **K8 — "broadcast only helps the loud."** The +$138 / −$67 magnitudes are
   fitted through `belief0`; the direction is what fired. Re-run all eight cells
   and report which still fire.

---

## A11.4 Discipline

- This file is complete before the first A11 run. Nothing in it is edited after
  a result exists; corrections are appended with a date.
- Every kill above is stated on an **output**, has a numeric bar fixed here, and
  says what a non-firing means.
- Both convenient outcomes (K31 not firing, K32 not firing) carry a named,
  enumerated bug hunt that must be run and reported before the result is
  believed. DESIGN-PRINCIPLES E: six of this study's seven artefacts ran toward
  the more interesting story.
- No `Params` default changes. Sourced values are named constants in `world.py`
  with `PARAM_SOURCES` entries, passed as explicit overrides.
- Before/after tables for every downstream result named in §A11.2.8 and
  §A11.3.5, whether or not the number moved.
- `python3 -m pytest research/crabs/test_crabs.py -q` stays green (119 tests at
  the time of writing).

---

## A11.5 CORRECTION, appended 2026-07-25, before the first A11 measurement

*Two items came back from the triage worker after §A11.0–A11.4 were written and
before any A11 result existed. Both are appended here rather than edited in,
per §A11.4. The only A11 code that had run at this point was the shipped
baseline and the probe reported in §A11.5.1, which is a property of the source
and not a measurement.*

### A11.5.1 `courage_med` and `belief0` are ONE knob, labelled twice

§A11.3 treats them as two parameters to source separately. **That is wrong, and
the code says so.** `world._set_endogenous_askers` is

```
worth  = belief × ask_scale × ask_frac × 12 × max(q, 0.1)
ask if   worth > courage,      courage = courage_med · exp(σ·z)
```

so a crab asks iff `z < ln(belief0 · K / courage_med) / σ`. Only the **ratio**
`ρ = belief0 / courage_med` enters. Scaling both by the same factor is a no-op.

Verified before restating the kill, on arm F / institutional / gain /
exploratory / 20 seeds, holding `ρ = 0.5556` and moving both ends over a 20×
range:

| `belief0` | `courage_med` | counter rate |
|---|---|---|
| 0.025 | 0.045 | 0.3314 |
| 0.05 | 0.09 | 0.3282 |
| 0.10 | 0.18 | **0.3282** (the shipped pair) |
| 0.20 | 0.36 | 0.3280 |
| 0.50 | 0.90 | 0.3248 |

Two parameters, one degree of freedom. The residual spread (0.3248–0.3314, 2%
relative) is the whole of their separate identification, and it comes only from
the belief update: askers move toward the realised success rate, so how far
`belief0` starts from it matters a little. Never-askers never update, so for
them the ratio is the entire model.

**Consequence for what is registered.** The sourcing exercise stands — both ends
are still sourced, and it is the sourcing that fixes the ratio — but it produces
**one** number, not two:

> **ρ\* = 0.50 / 0.018029 = 27.73**, the uninformative prior over one hour of the
> ACS renter wage.

The shipped pair is ρ = 0.10/0.18 = **0.5556**, i.e. **50× smaller**. Both
sweeps in §A11.3.2/§A11.3.3 are kept and run, because their *purpose* changes: a
sweep of either parameter alone is now understood to be a sweep of ρ, and
running both confirms they trace the same curve.

### A11.5.2 K32, restated on the ratio — and what it can and cannot test

**K32 (amended) FIRES if the counter rate at the sourced ratio ρ\* = 27.73
lands outside 29–49%.** Same arm, same cells, same bars as §A11.3.4; the two
bug-hunt clauses there stand unchanged, with one added: (d) confirm the
counter rate is a function of ρ alone before reading any single-parameter sweep
as a result.

**And a limitation that has to be registered rather than discovered.** The
triage worker reports the pair spans counter rates from ~0.9% to ~96% across
their joint range. If that holds, **ρ is not identified by this model**: every
counter rate between ~0 and ~1 is reachable, so "the counter rate is a free
output" is a very weak statement about it. It is free in the Principle G sense —
nothing is now fitted to it — and simultaneously uninformative, because the
model places no constraint on it at all.

That makes K32 **not a test of the model**. It is a test of whether the *sourced*
ratio happens to land on the observed value, and nothing more. Registered
consequences:

- **Report the identified set**, not just the point: the range of ρ for which
  the counter rate falls in 29–49%, and its translation into interpretable
  units — *hours of the ACS renter wage, at an uninformative prior*. That number
  is the size of the thing the model is missing, and it is the deliverable of
  Job 2 whichever way K32 goes.
- **Report the elasticity**: how many pp of counter rate one doubling of ρ buys.
  If a 50× error in ρ moves the counter rate only from 33% to 90%, the parameter
  is weakly identified in the *other* direction too, and that is worth saying.
- **If the whole 29–49% band is reachable and so is everything else, say that
  the parameter cannot be identified from this model**, and treat that as the
  finding — it is cleaner than either verdict on K32, and it retires the idea
  that arm F ever measured the courage problem rather than restating an input.

### A11.5.3 The solved-policy cache defect, and what it invalidates here

`run._station` keyed its cache on `(regime, share, adaptive, face_premium,
p_substitute, p_continue)` and `run2._get` on a similarly partial tuple. Every
other parameter `StationDP` reads was absent, and `StationDP._leave_table` reads
`p_exo(p, j)` **directly** — so a `p_exo` sweep through either runner would have
returned a policy solved for the shipped 0.24/0.18 and reported it as the swept
cell's. **This lands squarely on Job 1.**

Confirmed against the old key: `p_exo_floor`, `move_med`, `renewal_cap`,
`turn_cost`, `vacancy` and `nu` all collide.

- **Fixed in place** in `run.py` and `run2.py`, keyed on the whole frozen
  `Params` plus an exact fingerprint of the switching-cost prior — which is as
  much an input to the solve as `Params` is and was a process-level global.
- **Regression test** `test_station_cache_key_covers_every_parameter_the_solve_depends_on`
  is total rather than a list of known-relevant fields, because a list is the
  thing that went stale: changing **any** field of `Params` must change the key.
  Plus an end-to-end test on `p_exo_floor` specifically.
- **Nothing already published is affected.** `phase1_specs` holds `base` fixed
  and `sens_specs` sweeps only the three parameters that were in the key, which
  is why the defect survived; `phase2_specs` varies only `units`, which was
  keyed. The fix can only split cache entries that should have been separate, so
  every shipped cell is bit-identical.
- **No A11 number was produced before the fix**, so nothing here is re-run —
  and the A11 runner keeps its own cache built per variant regardless.
