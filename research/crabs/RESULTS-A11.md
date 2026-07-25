# RESULTS — AMENDMENT 11

*2026-07-25. Filed in its own file: `RESULTS.md` and `PREREG.md` are held open by
another worker. The pre-registration is `PREREG-A11.md`, complete before
`run_amend11.py` existed; §A11.5 is a dated correction appended before the first
measurement.*

Reproduce:

```
python3 research/crabs/run_amend11.py j1      # Phase 1 under sourced p_exo
python3 research/crabs/run_amend11.py j1m     # market: GATE 3 V10, K21
python3 research/crabs/run_amend11.py j1a7    # A7's "either fact, not both"
python3 research/crabs/run_amend11.py j1k18   # arm K turnover (K18)
python3 research/crabs/run_amend11.py j2      # arm F: the counter rate
python3 research/crabs/analyze_amend11.py
```

Source pinned for the market runs, because `market.py` was being edited by
another worker while these ran: `market.py`
sha256 `0bd645a5a2b2998e86f179abcad4f821ceb53b3e5e0ab0a6cebb548ae7409cc9`.
The `F` (fitted) market row below is **bit-identical** to the `baseline` cell of
the shipped `results_market.json`, so the before/after is measured against the
code as it stands, not against a stale snapshot.

---

## 0. The four headlines

1. **K31 FIRED.** With `p_exo` sourced from the Census instead of fitted to the
   turnover target, modelled retention is **83.6% / 81.0%** against a 52–62%
   band. The model needs a non-rent move hazard **3.6–3.9× larger** than the
   largest one the Census supports.
2. **A second "either fact, not both", and this time only one of the two facts
   is fitted.** The shipped parameter implies **90.4%** of moves are non-rent;
   CPS says **61.2%**. The model can match observed *retention* or observed
   *reason-for-move composition*, never both — and the composition was never
   fitted to anything, so this is not the artefact A7's version was.
3. **K32 FIRED, and the parameter it is about cannot be identified at all.**
   `courage_med` and `belief0` are **one knob under two names** — only their
   ratio ρ enters — and ρ moves the counter rate across essentially its whole
   range (0.03% → 100%). At the sourced ρ the counter rate is **99.96%**. To
   reproduce the observed 39%, sending one email must cost **~27–55 hours** of
   the tenant's own wage.
4. **A solved-policy cache defect was found and fixed** in `run.py`, `run2.py`,
   `run3.py` and `run_engine.py`. It would have silently poisoned every number
   in Job 1. Nothing already published is affected; the fix is
   behaviour-preserving for every shipped spec.

---

## 1. JOB 1 — the sourcing

### 1.1 The primary source

> **U.S. Census Bureau, *Geographic Mobility: 2023*** — the 1-year table package
> from the **2023 Current Population Survey Annual Social and Economic
> Supplement (CPS ASEC)**, released **10 December 2024**. It is the most recent
> published year; the 2024 and 2025 packages do not exist at the time of writing
> (both URLs 404).
>
> Landing page:
> `https://www.census.gov/data/tables/2023/demo/geographic-mobility/cps-2023.html`
>
> - **Table 13** — *Reason for Move in the Past Year (Both Collapsed and Specific
>   Categories), by Sex, Age, Race and Hispanic Origin, Relationship to
>   Householder, Educational Attainment, Marital Status, Nativity, Tenure,
>   Poverty Status, and Type of Move: 2023*
>   `https://www2.census.gov/programs-surveys/demo/tables/geographic-mobility/2023/cps-2023/mig_13_2023_1yr.xlsx`
> - **Table 1** — *General Mobility in the Past Year, by … Tenure … : 2023*
>   `https://www2.census.gov/programs-surveys/demo/tables/geographic-mobility/2023/cps-2023/mig_01_2023_1yr.xlsx`
>
> Both `.xlsx` files were downloaded from `www2.census.gov` and parsed directly;
> no secondary source was used for any figure below.

**ACS cannot supply this.** The ACS publishes mobility and tenure but does not
ask *reason for move*; that question exists only on the CPS ASEC (added 1998).
Everything here is CPS.

### 1.2 The figures used

**Table 13, row "In a renter-occupied housing unit" (thousands):**

| category | count | share of renter moves |
|---|---|---|
| **Total movers** | **16,337** | 100.00% |
| Family-related | 3,496 | 21.40% |
| Employment-related | 3,845 | 23.54% |
| Housing-related | 6,330 | 38.75% |
| Other | 2,665 | 16.31% |

**Housing-related, in specific categories:**

| specific reason | count | share |
|---|---|---|
| Wanted newer/better/larger house or apartment | 2,207 | 13.51% |
| **Cheaper housing** | **1,793** | **10.98%** |
| Other housing reason | 1,065 | 6.52% |
| Wanted better neighborhood / less crime | 967 | 5.92% |
| Wanted to own home, not rent | 149 | 0.91% |
| Foreclosure / eviction | 149 | 0.91% |

**Table 1, same row:** total 101,024 · nonmovers 84,687 · movers 16,337
→ **renter mover rate = 16.1714 % / yr**.

Two mappings, both registered in §A11.2.4 before running:

| mapping | non-rent share | sourced flat `p_exo` |
|---|---|---|
| **M1 — non-housing** (family + employment + other) | **0.612475** | **0.099046** ← primary |
| M2 — non-price (everything except "cheaper housing") | 0.890249 | 0.143966 |

### 1.3 The functional form the data does *not* support

**CPS publishes reason for move by nine characteristics and not one of them is
length of residence.** There is no published tenure gradient to source
`0.18·exp(−(j−1)/3)` from, and `p_exo_tau` was already classified INVENTED
("decay constant, no stated source"). Per §A11.2.3, fixed before running: **the
form the data supports is a constant.** The decay is not deleted — it is demoted
to an INVENTED shape and ablated as variants S1d/S2d, which rescale the shipped
shape so its mean over j=1..8 equals the sourced flat value.

### 1.4 What the shipped parameter was actually asserting

`0.42 / 0.47 = 0.894`: evaluated at first renewal against its own cited turnover
figure, `p_exo_floor + p_exo_extra` claims **89% of first-year renter moves are
not about rent.** Measured rather than inferred, the model under the fitted
parameter puts **90.4%** (loss) / **86.6%** (gain) of its leavers in the
exogenous channel. **CPS says 61.2%.**

The fitted value coincides with mapping **M2** — the reading under which only
"cheaper housing" counts as rent-driven. Per §A11.2.4 this is **not** claimed as
a validation of the shipped parameter, and the reason is stated there: it would
mean the fit silently adopted M2's mapping *and* the apartment-sector turnover
level together, and only the mapping half of that has any source.

---

## 2. K31 — VERDICT: **FIRED**, in both regimes

*Fires if S1 retention lands outside 52–62% (observed ~57.3%). Registered
specification, Phase 1 arm A, 39% price askers, 60 stations, seeds 1000–1059.*

| regime | fitted `p_exo` | **sourced S1** | band | verdict |
|---|---|---|---|---|
| loss | 0.6013 ± 0.0050 | **0.8359 ± 0.0034** | 0.52–0.62 | **FIRES** |
| gain | 0.5693 ± 0.0052 | **0.8099 ± 0.0040** | 0.52–0.62 | **FIRES** |

Every variant, registered specification:

| variant | `p_exo(1)` | `p_exo(8)` | regime | retention | turnover | exo/leavers | success | tenure ratio (V3) | push |
|---|---|---|---|---|---|---|---|---|---|
| **F** fitted | 0.4200 | 0.2575 | loss | 0.6013 | 0.3987 | 0.9036 | 0.0004 | n/a | +10.73% |
| **F** fitted | 0.4200 | 0.2575 | gain | 0.5693 | 0.4307 | 0.8659 | 0.0017 | 0.466 | −1.19% |
| **S1** CPS M1 | 0.0990 | 0.0990 | loss | **0.8359** | 0.1641 | 0.6196 | 0.0407 | n/a | +10.04% |
| **S1** CPS M1 | 0.0990 | 0.0990 | gain | **0.8099** | 0.1901 | 0.5537 | 0.0663 | **1.415** | −3.12% |
| S2 CPS M2 | 0.1440 | 0.1440 | loss | 0.8008 | 0.1992 | 0.7201 | 0.0059 | n/a | +10.20% |
| S2 CPS M2 | 0.1440 | 0.1440 | gain | 0.7648 | 0.2352 | 0.6422 | 0.0557 | 1.457 | −2.65% |
| S1d shape | 0.1325 | 0.0812 | loss | 0.8374 | 0.1626 | 0.6335 | 0.0310 | n/a | +9.98% |
| S1d shape | 0.1325 | 0.0812 | gain | 0.8107 | 0.1893 | 0.5716 | 0.0824 | 0.703 | −3.19% |
| S2d shape | 0.1926 | 0.1181 | loss | 0.7926 | 0.2074 | 0.7352 | 0.0316 | n/a | +10.16% |
| S2d shape | 0.1926 | 0.1181 | gain | 0.7622 | 0.2378 | 0.6650 | 0.0681 | 0.548 | −2.76% |

*(V3's loss-regime cell is `nan` in both the fitted and the sourced run: under
the registered specification the loss-regime station concedes to almost nobody,
so the under-2y denominator is empty. That is a pre-existing property of the
registered spec, not something A11 introduced.)*

**The shape is not the story.** S1 vs S1d differ only in whether the sourced mean
is delivered flat or with the shipped decay: retention 0.8359 vs 0.8374 (loss),
0.8099 vs 0.8107 (gain). **The level does essentially all of the work; the
INVENTED decay contributes under 0.2pp of retention.** The one place the shape
*does* matter is V3 — see §5.

### 2.1 How far off the level is

Interpolating the flat-`p_exo` sweep (11 points, 0.03 → 0.42):

| target | loss | gain |
|---|---|---|
| `p_exo` reproducing observed retention 57.3% | **0.3907** | **0.3565** |
| ratio to the CPS-sourced 0.0990 | **3.94×** | **3.60×** |
| the model's exo share of leavers at that `p_exo` | 0.908 | 0.843 |

### 2.2 The composition test — the finding this amendment exists to have found

Because `p_exo` now carries a *sourced composition* as well as a level, the
model's own reason-for-move mix becomes a checkable free output. It is
instrumented in `world.new_recorder` (`left_exo`, `left_endo`,
`left_endo_only`), added for A11.

| | non-rent share of moves | modelled retention |
|---|---|---|
| **CPS 2023, renters** | **0.6125** | — |
| model at the CPS-sourced `p_exo` (S1) | 0.6196 / 0.5537 | 0.836 / 0.810 |
| model at the fitted `p_exo` (F) | 0.9036 / 0.8659 | 0.601 / 0.569 |
| model at the `p_exo` that reproduces observed retention | 0.908 / 0.843 | 0.573 |
| **S3 — `p_exo` chosen so the mix matches CPS** | 0.6125 by construction | **0.838 / 0.782** |

**S3 is the sharpest cell in Job 1.** It throws away the CPS mobility *level*
entirely — the part with the population-mismatch caveat — and imposes only the
CPS *composition*, leaving turnover completely free. It needs `p_exo` = 0.0969
(loss) / 0.1267 (gain), and retention lands at **83.8% / 78.2%**: still far
outside K31's band. **So K31 fires on the level-free variant too, and the
population mismatch is not the explanation.**

Stated plainly: **the model cannot simultaneously reproduce apartment-sector
retention and the Census reason-for-move composition.** One of those two facts
was fitted and the other was not, so unlike A7's version of this sentence, this
one is not a tension between two things we installed.

### 2.3 The endogenous channel is too big by the same test

The instrumentation also prices the *rent-driven* half against the only Census
category that corresponds to it. CPS: "cheaper housing" moves are
10.98% × 16.17% = **1.78%/yr**.

| variant | regime | modelled rent-driven leave hazard |
|---|---|---|
| F fitted | loss / gain | 5.9% / 9.2% |
| S1 sourced | loss / gain | 7.0% / 9.4% |
| S2 sourced | loss / gain | 6.8% / 9.8% |

**3.3–5.5× the CPS figure, in every variant.** Both halves of turnover are too
large against Census, which is why fitting one of them to an apartment-sector
aggregate could look like it worked.

One honest coincidence, reported because it is interesting and not because it
rescues anything: under S1 in the **loss** regime, total modelled turnover is
**16.41%** against the CPS all-renter mover rate of **16.17%**. In the gain
regime it is 19.01% and the agreement breaks. So the sourced model reproduces
*all-renter mobility* in one regime while missing *apartment turnover* by 2.6×.
The two published "observed" facts are 2.6× apart, and the study fitted to the
second while describing the fit as validation.

---

## 3. JOB 3 — what `p_exo` broke downstream

### 3.1 GATE 1 V2 — retention

`FREE-OUTPUTS.md` §2: V2 is *"the only criterion the study ever passed on the
first attempt, and it is an identity."* With the non-rent half sourced it stops
being an identity and **fails**: 0.836 / 0.810 against a 0.45–0.65 bar. It is
still not a clean test — `move_med` remains CALIBRATED to the rent-driven half,
so V2 is now **half-free**, not free.

### 3.2 GATE 3 V10 — market-side retention

*Bar: endogenous market retention within 5pp of Phase 1's.*

| variant | market retention | Phase 1 (gain) | gap | verdict |
|---|---|---|---|---|
| F fitted | 0.6462 | 0.5693 | 7.7pp | FAIL |
| S1 sourced | 0.9007 | 0.8099 | 9.1pp | FAIL |
| S2 sourced | 0.8562 | 0.7648 | 9.1pp | FAIL |

V10 fails either way and fails slightly worse when sourced. **Note for the
`RESULTS.md` owner:** the `F` row is bit-identical to the current shipped
`results_market.json` baseline, and RESULTS.md currently reports V10 as
*"FAIL by 0.3pp"*. Against today's `market.py` the gap is 7.7pp. That number is
stale independently of A11.

### 3.3 K21 — "for some tenants the right advice is move". **The verdict inverts.**

`market.py:541` sets `stay = 1.0 / p_exo(p, j)`, and the whole net-move-gain
table is the tenant's moving cost amortised over that. Sourcing `p_exo` takes
the expected remaining stay from ~2.5 years to ~10 years, so the amortised cost
collapses.

| | raw annual rent saving | net of amortised move cost | share for whom moving wins |
|---|---|---|---|
| **F** fitted | +$1,068 | **−$722** | **17.4%** |
| **S1** sourced | +$1,568 | **+$860** | **95.2%** |
| S2 sourced | +$1,376 | +$462 | 83.2% |

Quartiles by moving cost (net gain / share for whom moving wins):

| variant | q0 cheapest | q1 | q2 | q3 dearest |
|---|---|---|---|---|
| **F** fitted | +$46 / 50.3% | −$112 / 32.1% | −$273 / 27.7% | −$1,022 / 9.7% |
| **S1** sourced | +$655 / 100% | +$691 / 100% | +$830 / 100% | +$901 / 92.7% |

**Everything about K21 changes.** The sign of the net gain flips, the share for
whom moving wins goes from one in six to nineteen in twenty, and the monotone
quartile gradient — the "genuine product consequence" RESULTS.md reports —
**disappears entirely** (it even reverses: the dearest quartile gains most,
because the rent gap it faces is larger). Registered in §A11.2.8 before the run:
*the flip is a property of `p_exo` and must be reported as such, not as a finding
about tenants.* K21 still does not fire on its own bar (raw saving ≥ $480
would fire it — and on today's `market.py` the raw saving is $1,068, which
**does** clear the bar in every variant, fitted included; that is a separate
pre-existing discrepancy with RESULTS.md's +$372, not an A11 result).

The audit already said K21's quartiles are a readout of `move_med`. Add: **its
sign is a readout of `p_exo`.**

### 3.4 K18 — "mutual engines destroy value". Verdict holds, stated reason does not

*Fires only if T/L has BOTH higher turnover than N/N AND lower joint surplus.*

| variant | regime | turnover N/N → T/L | joint N/N → T/L | verdict |
|---|---|---|---|---|
| F fitted | loss | 0.3961 → 0.3891 (**falls**) | 22,248 → 23,747 (rises) | does not fire |
| F fitted | gain | 0.4281 → 0.4152 (**falls**) | 14,450 → 15,843 (rises) | does not fire |
| **S1** sourced | loss | 0.1625 → **0.1684 (RISES)** | 27,026 → 27,555 (rises) | does not fire |
| **S1** sourced | gain | 0.1872 → 0.1862 (falls by 0.10pp) | 18,097 → 19,015 (rises) | does not fire |

The fitted rows reproduce RESULTS.md exactly (0.396 → 0.389, 0.428 → 0.415).
**K18's verdict survives, because it needs both conditions and joint surplus
rises throughout. Its stated mechanism — "turnover falls" — does not:** with
`p_exo` sourced the direction flips in the loss regime and shrinks by 13× in the
gain regime. The sentence in RESULTS.md should be cut back to the joint-surplus
half, which is the half that is robust.

### 3.5 A7's "you can have either observed fact, not both". **Dissolved.**

The audit's suspicion was that A7's trade-off is between two *fitted* facts and
so may not be a real tension. It is not.

| variant | cap | regime | mean push | retention |
|---|---|---|---|---|
| F fitted | capped 0.12 | loss | **+10.73%** | **0.6013** |
| F fitted | free 2.00 | loss | **+13.81%** | **0.5613** |
| **S1** sourced | capped 0.12 | loss | +10.04% | 0.8359 |
| **S1** sourced | free 2.00 | loss | **+11.35%** | 0.7968 |
| S2 sourced | capped 0.12 | loss | +10.20% | 0.8008 |
| S2 sourced | free 2.00 | loss | +11.77% | 0.7582 |

The fitted rows reproduce A7 to four decimals (+10.73% / 60.1%; +13.81% / 56.1%).
Two things follow:

1. **The either/or is gone.** A7's sentence was "capped gets you the observed
   push but the wrong retention; free gets you the observed retention but the
   wrong push." With `p_exo` sourced, **no cap reaches observed retention at
   all** — both configurations sit 23–24pp above it. There is no trade-off
   between the two observed facts, only a failure on one of them. **The tension
   was an artefact of the fitted parameter**, exactly as the audit suspected.
2. **A7's headline number moves a lot, in our favour, which is why it gets said
   carefully.** A7 reported that elasticity alone gives +13.81% against an
   observed +10.7% — *"elasticity generates ~3/4 of the restraint the world
   shows; something else supplies the rest."* Under sourced `p_exo` the free
   station chooses **+11.35%**, overshooting by 0.65pp instead of 3.1pp. The
   "something else" largely disappears. **This may not be claimed as a result**:
   the free push is still a readout of `move_med`, which is CALIBRATED to
   observed elasticity (`FREE-OUTPUTS.md` row 4), and A8 is the outstanding fix
   for that. What can be said is narrower and still worth saying: *A7's estimate
   of how much restraint elasticity fails to explain was itself a function of a
   circular parameter, and it is not robust.*

### 3.6 Free observables that moved (reported, not claimed)

| observable | free? | F fitted (gain) | S1 sourced (gain) |
|---|---|---|---|
| **V3 tenure ratio** (bar ≥1.5×) | FREE (row 10) | 0.466 | **1.415** — still fails, but only just |
| V4 zero-increase share (bar 0.10–0.30) | FREE (row 14) | 0.586 | 0.801 — fails worse |
| V1 counter success (bar 0.15–0.30) | FITTED (row 1) | 0.129 | 0.188 *(exploratory spec)* |
| deadweight $/habitat-year | FITTED (row 18) | 6,034 | 2,511 |
| tenant surplus $/crab-year | free, `ask_frac`-scoped | −4,972 | −3,793 |

**V3's improvement is the shape, not the level, and that is the one place the
ablation earns its keep.** S1 (flat) gives 1.415; S1d (same mean, shipped decay)
gives 0.703; the fitted decay gives 0.466. So the near-pass comes from removing
the INVENTED tenure decay, which is a *modelling* change with a *data* argument
behind it (CPS does not publish reason for move by length of residence), not
from the sourced level. Reported as such rather than as V3 nearly passing.

V1 lands inside its band in one cell (exploratory / gain / S1: 0.188 against
0.15–0.30). **This may not be reported as V1 passing.** V1 is FITTED through
`vacancy`, `face_premium` and `renewal_cap` — `FREE-OUTPUTS.md` row 1 — and a
fitted gate that passes is precisely where the damage happens.

---

## 4. JOB 2 — the counter rate

### 4.1 The brief was wrong, and the code says so: it is ONE knob

`world._set_endogenous_askers` asks iff
`belief × ask_scale × ask_frac × 12q > courage`, so a crab asks iff
`z < ln(belief0 · K / courage_med)/σ`. **Only the ratio ρ = belief0/courage_med
enters.** Both parameters were swept, from both ends, and they trace one curve:

| ρ | swept via `courage_med` | swept via `belief0` |
|---|---|---|
| 1.389 | 0.6166 | 0.6192 |
| 2.775 | 0.8510 | 0.8515 |

*(loss regime; the gain regime gives 0.7275 vs 0.7305 and 0.9121 vs 0.9122.)*

The whole of their separate identification is that ≤0.3pp gap, and it comes only
from the belief update — askers move toward the realised success rate, so where
`belief0` starts relative to it matters a little. Never-askers never update, so
for them the ratio is the entire model.

**The study carried one degree of freedom under two names, and fitted both names
to the same observed fact.** `FREE-OUTPUTS.md`'s "compounding case" for the
counter rate — *"`courage_med` fits the cost of asking to land on 39%; `belief0`
fits the perceived odds of winning to land on the 61% complement. Two ends of
one split"* — is exactly right about the intent and understates the damage: they
are not two ends of one split, they are one number written twice.

### 4.2 K32 — VERDICT: **FIRED**, in both regimes

*Fires if the counter rate at the sourced ratio ρ\* = 0.50/0.018029 = 27.73 lands
outside 29–49%. Arm F, institutional, broadcast off, exploratory spec.*

| regime | shipped ρ = 0.556 | **sourced ρ\* = 27.73** | band | verdict |
|---|---|---|---|---|
| loss | 0.2341 | **0.9996 ± 0.0002** | 0.29–0.49 | **FIRES** |
| gain | 0.3274 | **0.9998 ± 0.0001** | 0.29–0.49 | **FIRES** |

Robust to the INVENTED dispersion: at ρ\*, `courage_sigma` ∈ {0.4, 0.8, 1.2}
gives 1.0000 / 0.9996 / 0.9930 (loss).

**The coordinator's prediction is confirmed in the direction it was made.** With
the cost of asking sourced from the only upstream anchor there is — one hour of
the ACS renter wage already used in `demographics.py` and `searchcost.py` — the
model says essentially every tenant counters, and it cannot reproduce the
observed 39%. **It is not tuned back.**

### 4.3 But the sharper result is that ρ is not identified at all

The counter rate spans **0.0003 to 1.0000** as ρ runs from 0.056 to 111. Every
value the observed number could have taken is reachable. So:

- **"The counter rate is a free output" is true and nearly empty.** Nothing is
  fitted to it any more, and the model places no constraint on it whatever.
- **K32 is not a test of the model.** It is a test of whether the sourced ratio
  happens to land on the observed value, and it does not.
- **Arm F never measured the courage problem.** It restated an input, through a
  parameter that was chosen to make it come out right.

The interpretable form of the identified set — what the model needs to be true
about the world in order to explain why 61% of renters never ask:

| regime | ρ consistent with 29–49% | ρ hitting 39% exactly | `courage_med` at an uninformative prior | **in hours of the ACS renter wage** |
|---|---|---|---|---|
| loss | 0.645 – 1.036 | 0.822 | $965 – $1,550 (at 39%: $1,217) | **26.8 – 43.0 h** (at 39%: **33.7 h**) |
| gain | 0.501 – 0.812 | 0.645 | $1,231 – $1,995 (at 39%: $1,549) | **34.1 – 55.3 h** (at 39%: **43.0 h**) |

**For this model to explain the 61% who never ask, sending one email to your
landlord has to cost between about three and seven working days of your own
time.** That is the size of the thing the model is missing. It is not a cost;
whatever keeps renters from asking — fear of retaliation, fear of non-renewal,
conflict aversion, not knowing it is allowed — is not priced by anything in
this apparatus, and the shipped `courage_med = 0.18` was a residual absorbing
all of it under a label that says "time".

Elasticity, for anyone tempted to treat ρ as nearly-identified: above ρ = 1 the
curve is flat — **+8.4pp (loss) / +4.5pp (gain) of counter rate per doubling of
ρ.** A 50× error in ρ moves the counter rate from 33% to 91%. Weakly identified
in both directions.

**The shipped ρ is not privileged and neither is the sourced one.** The model
cannot choose between them. What separates them is that the shipped value's
only justification was the number it reproduces.

---

## 5. JOB 3 — what the counter-rate ratio broke downstream

### 5.1 Phase 2 §7 arm F, shipped ratio vs sourced ratio

`counter` is the counter rate; `total`/`askers`/`non` are $/crab-year.

| ρ | type | regime | bcast | counter | belief | ask scale | success | total | askers | non-askers |
|---|---|---|---|---|---|---|---|---|---|---|
| shipped | institutional | loss | off | 0.2371 | 0.099 | 1.000 | 0.0587 | −5,863 | −5,678 | −5,921 |
| shipped | institutional | loss | **on** | 0.2068 | 0.098 | 0.752 | 0.0963 | −5,860 | −5,640 | −5,917 |
| shipped | institutional | gain | off | 0.3237 | 0.108 | 1.000 | 0.2108 | −4,900 | −4,796 | −4,950 |
| shipped | institutional | gain | **on** | 0.4672 | 0.168 | 0.732 | 0.3187 | −4,868 | −4,728 | −4,990 |
| shipped | inst-adaptive | gain | off | 0.3253 | 0.109 | 1.000 | 0.2259 | −4,905 | −4,789 | −4,961 |
| shipped | inst-adaptive | gain | **on** | 0.4986 | 0.183 | 0.735 | 0.3963 | −4,857 | −4,697 | −5,017 |
| **sourced** | institutional | loss | off | 0.9997 | 0.398 | 1.000 | 0.0607 | −5,821 | −5,823 | −3,474 |
| **sourced** | institutional | loss | **on** | 0.9973 | 0.341 | 0.728 | 0.0956 | −5,803 | −5,806 | −4,763 |
| **sourced** | institutional | gain | off | 0.9998 | 0.428 | 1.000 | 0.2024 | −4,819 | −4,818 | −5,879 |
| **sourced** | institutional | gain | **on** | 0.9999 | 0.412 | 0.732 | 0.3090 | −4,788 | −4,788 | −5,578 |
| **sourced** | inst-adaptive | gain | off | 1.0000 | 0.546 | 1.000 | 0.8013 | −4,358 | −4,357 | −5,794 |
| **sourced** | inst-adaptive | gain | **on** | 1.0000 | 0.575 | 0.851 | 0.8013 | −4,645 | −4,644 | −5,794 |

The shipped rows reproduce RESULTS.md Phase 2 §7 (ask share 0.234 / 0.322 →
0.461 for the institution; belief ~0.10; `ask_scale` 1.00 → 0.73).

**The structural change: at an honest cost of asking, adoption is saturated, so
the grapevine's adoption channel closes.** RESULTS.md lists three things
broadcast does, and the first — *"it raises adoption only where asking actually
works"* — has nothing left to raise (0.9998 → 0.9999). What remains is the
third: **it shrinks the ask** (`ask_scale` 1.000 → 0.73–0.85). Publishing base
rates now does one thing only: it teaches tenants to ask for less.

### 5.2 K7 — the live-page claim. **The direction flips, and the kill fires.**

*Fires if under BROADCAST + ADAPTIVE INSTITUTIONAL total crab surplus is lower
than under no-broadcast by ≥ $240. The page states the DIRECTION only, which
`FREE-OUTPUTS.md` row 16 classifies as FREE.*

| ρ | regime | broadcast off | on | harm | verdict |
|---|---|---|---|---|---|
| shipped | loss | −5,863 | −5,860 | **−$4 ± 63** (helped) | does not fire |
| shipped | gain | −4,905 | −4,857 | **−$48 ± 51** (helped) | does not fire |
| **sourced** | loss | −5,593 | −5,702 | **+$109 ± 62** (harmed) | does not fire (1.8σ) |
| **sourced** | gain | −4,358 | −4,645 | **+$287 ± 47** (harmed) | **FIRES** |

The shipped rows reproduce RESULTS.md's −$5 / −$55. **At the sourced ratio the
sign reverses in both regimes and clears the pre-registered bar in the gain
regime at 6.1σ.**

Per PREREG-A11 §A11.3.5, registered before the run: **this goes to the page, not
into a footnote.** The honest statement is not "the product is harmful" — it is:

> K7's published direction is conditional on a parameter the model cannot
> identify, and it reverses at the only value of that parameter anyone has
> sourced. What we can say is that broadcast helps *only through adoption*. Where
> adoption is already high, its remaining effect is to teach tenants to ask for
> less, and that is a transfer to the landlord.

**The bug hunt, because this is the more interesting story** (DESIGN-PRINCIPLES
E: six of seven artefacts ran that way). The whole chain is checkable in the
recorder and every link holds:

| sourced / adaptive / gain | broadcast off | on |
|---|---|---|
| counter rate | 1.0000 | 1.0000 — **adoption channel closed** |
| success rate | 0.8013 | 0.8013 — **unchanged, so it is not "fewer concessions"** |
| `ask_scale` | 1.000 | **0.851** — the only channel left |
| retention | 0.5758 | **0.5600** — smaller concessions retain fewer tenants |
| tenant surplus | −4,358 | −4,645 (**−$287**) |
| station cash | 18,874 | 18,974 (**+$100**) |

$100 of the $287 is a transfer to the landlord; the remaining $187 is the extra
moving cost of the 1.6pp who now leave. So broadcast is not merely
redistributive here — it **destroys** value, by teaching tenants to ask for less
than would have retained them. The loss regime runs the same way
(retention 0.6036 → 0.6008, harm +$109).

**Caveat, stated rather than buried:** the *magnitude* is a readout of
`learn_rate` (INVENTED, 0.40) and the `ask_scale_lo/hi` clamps (INVENTED). The
*direction* is not, and the direction is what the page prints.

**One knob, checked:** Job 2 holds `p_exo` at the shipped fitted value
throughout. Nothing in §4 or §5 crosses Job 1's treatment with Job 2's; the only
thing that moves between the "shipped" and "sourced" rows is ρ.

### 5.3 K8 — "broadcast only helps the loud". **Becomes unmeasurable.**

*Fires if under broadcast, non-asker surplus falls while asker surplus rises.*

| ρ | type | regime | Δ askers | Δ non-askers | fires |
|---|---|---|---|---|---|
| shipped | institutional | loss | +$38 | +$4 ± 68 | no |
| shipped | mom | loss | +$366 | −$83 ± 171 | **yes** |
| shipped | institutional | gain | +$68 | −$40 ± 55 | **yes** |
| shipped | mom | gain | −$133 | +$61 ± 75 | no |
| shipped | inst-adaptive | loss | +$29 | +$5 ± 68 | no |
| shipped | **inst-adaptive** | **gain** | **+$92** | **−$56 ± 56** | **yes** |
| **sourced** | institutional | loss | +$17 | −$1,289 ± **1,262** | yes (1.0σ) |
| **sourced** | institutional | gain | +$31 | +$300 ± **1,700** | no |
| **sourced** | mom | loss | −$15 | −$309 ± **5,334** | no |
| **sourced** | mom | gain | −$9 | +$1,980 ± **2,413** | no |
| **sourced** | inst-adaptive | loss | −$110 | −$83 ± **1,414** | no |
| **sourced** | inst-adaptive | gain | −$287 | +$0 ± **2,500** | no |

Look at the standard errors, not the point estimates. **At the sourced ratio the
counter rate is 99.97%, so the non-asker group is essentially empty and its
surplus is noise** — the SE goes from ±56 to ±2,500, a 45× increase, on the same
number of stations.

**K8 is not refuted. It is rendered undecidable.** The claim *"the quiet
subsidise the loud, and we are the reason"* is a claim about a population whose
existence is the fitted parameter. Once the cost of asking is sourced, there are
no quiet tenants left to subsidise anyone. RESULTS.md sends K8 to `snhp.dev/rent`
per AMENDMENT 1; it should not go there in that form. **What survives is K3,
which is measured at an *assigned* asker share and so does not depend on ρ at
all.** That is the version of the externality the page can support.

---

## 6. Plain list — what changed sign, what changed size, what held

**Changed SIGN:**

| claim | fitted | sourced |
|---|---|---|
| **K7** broadcast's effect on total crab surplus (**live page**) | helps (−$5 / −$48) | **harms (+$109 / +$287); FIRES in gain** |
| **K21** net gain from moving | **−$722**, 17.4% of tenants | **+$860**, 95.2% of tenants |
| **K21** quartile gradient | monotone, cheapest-quartile only | gone; every quartile positive, order reversed |
| **K18** turnover in T/L vs N/N | falls (−0.70pp loss) | **rises (+0.59pp loss)** |
| A7's "either observed fact, not both" | a live trade-off | **dissolved — neither cap reaches observed retention** |

**Changed SIZE materially (same sign):**

| claim | fitted | sourced |
|---|---|---|
| V2 retention | 0.601 / 0.569 (PASS) | **0.836 / 0.810 (FAIL) — K31 FIRED** |
| V3 tenure ratio | 0.466 | 1.415 — but the gain is the *shape*, not the level (S1d: 0.703) |
| V4 zero-increase share | 0.586 | 0.801 (fails worse) |
| A7 free-cap push | +13.81% (3.1pp over observed) | +11.35% (0.65pp over observed) |
| deadweight $/habitat-yr | 6,034 | 2,511 |
| counter rate (arm F) | 0.234 / 0.327 | **0.9996 / 0.9998 — K32 FIRED** |

**HELD:**

- **K18's verdict** (does not fire) — joint surplus rises under mutual engines in
  every variant. Only its stated reason moved.
- **K21's verdict** (does not fire on its own $480 raw-saving bar under the
  fitted parameter as RESULTS.md reports it) — though on today's `market.py` the
  raw saving is $1,068 in every variant, which clears the bar. That is a
  pre-existing discrepancy with RESULTS.md, not an A11 result.
- **V10** fails in every variant (7.7pp fitted, 9.1pp sourced).
- **The Phase 2 arm F table's qualitative shape at the shipped ratio** — every
  shipped row reproduces RESULTS.md.
- **K3** — measured at an assigned asker share, so it does not move with ρ.

---

## 7. `PARAM_SOURCES` and the register

**No `Params` default was changed** (PREREG-A11 §A11.1): the defaults are what
every published run used, and three workers are running against them. So the
four entries keep their CIRCULAR class — the shipped number is still justified by
the number it reproduces — and each now carries what A11 found:

| entry | change |
|---|---|
| `p_exo_floor` | CIRCULAR retained; points at `P_EXO_CPS_NONHOUSING` and records that the fitted value implies 90.4% non-rent moves against the Census's 61.2% |
| `p_exo_extra` | CIRCULAR retained; records that the CPS publishes no reason-for-move-by-duration, so the decay has **no source at all**, and that it is worth <0.2pp of retention |
| `courage_med` | CIRCULAR retained; both entries now carry the shared `AND_ONE_KNOB` note |
| `belief0` | CIRCULAR retained; same note |

**New, classified, and enforced by the coverage test** (`world.py` module scope):

| constant | class | value |
|---|---|---|
| `CPS_RENTER_MOVER_RATE` | UPSTREAM | 0.161714 |
| `CPS_NONHOUSING_SHARE` | UPSTREAM | 0.612475 |
| `CPS_NONPRICE_SHARE` | UPSTREAM | 0.890249 |
| `P_EXO_CPS_NONHOUSING` | DERIVED | 0.099046 |
| `P_EXO_CPS_NONPRICE` | DERIVED | 0.143966 |
| `COURAGE_WAGE_HOURLY` | UPSTREAM | $36.06/h |
| `COURAGE_MED_1H` | INVENTED (ANCHORED wage, INVENTED hours) | 0.018029 months |

**`FREE-OUTPUTS.md` rows that A11 changes** (for its owner; not edited here):

- **Row 2, retention.** No longer an identity — it is now fitted through
  `move_med` alone. Half-free, and it **fails** once the other half is sourced.
  A8 is the outstanding fix for the remaining half.
- **Row 3, counter rate.** Not "fitted twice" — fitted **once, under two names**.
  And once un-fitted it is free but unidentified: the model admits any value.
- **New row candidate: reason-for-move composition.** Free, sourced, and the
  model misses it by 29pp at the fitted parameter and cannot hit it and
  retention together at any parameter.

---

## 8. Defects found on the way

1. **The solved-policy cache key** (reported by the triage worker, confirmed and
   fixed here). `run._station` keyed on
   `(regime, share, adaptive, face_premium, p_substitute, p_continue)`;
   `run2._get`, `run3._dp` and `run_engine._station` on similarly partial
   tuples. `StationDP._leave_table` reads `p_exo(p, j)` **directly**, so any
   `p_exo` sweep through those runners would have returned the policy solved for
   the fitted value. Confirmed: `p_exo_floor`, `move_med`, `renewal_cap`,
   `turn_cost`, `vacancy` and `nu` all collided under the old key.
   - Fixed in all four, keyed on the whole frozen `Params` plus an exact
     fingerprint of the switching-cost prior (which is as much an input to the
     solve as `Params` is, and was a process-level global).
   - Regression test `test_station_cache_key_covers_every_parameter_the_solve_depends_on`
     is **total** — changing *any* field of `Params` must change the key —
     because a list of known-relevant fields is the thing that went stale. Plus
     `test_sweeping_p_exo_actually_resolves_the_station_policy` end to end.
   - **Nothing published is affected.** `phase1_specs` holds `base` fixed,
     `sens_specs` sweeps only keyed parameters, `phase2_specs` varies only
     `units`. The fix can only split entries that should have been separate.
   - `run_amend11.py` keeps its own cache anyway, and rebuilds the pilot prior
     per variant — the prior is measured off a simulation, so it is a function
     of `p_exo` too.
2. **`RESULTS.md`'s Phase 5 numbers are stale against today's `market.py`**
   (for its owner). The shipped `results_market.json` baseline now gives
   K21 raw +$1,068 / net −$722 / 17.4% and quartiles +46/−112/−273/−1,022,
   against RESULTS.md's +$372 / −$706 / 2.3% and −137/−342/−663/−1,380; and
   V10's gap is 7.7pp against RESULTS.md's "FAIL by 0.3pp". Independent of A11 —
   my fitted row is bit-identical to that file.
3. **`market.py`'s baseline vacancy is 0.0000** in the current shipped
   `results_market.json` and in every A11 market cell, while the supply-shock
   cell gives 2.14%. Flagged, not investigated: `market.py` is fenced.

## 9. What A11 does not establish

- **It does not rescue anything.** Every gate that failed still fails, and V2 now
  fails too.
- **Retention is still half-fitted.** `move_med` remains CALIBRATED to the
  rent-driven half of turnover. A8 is the other half of this job.
- **The CPS mobility level is measured on all renters, person-weighted, with
  tenure recorded at the destination** — so S1/S2 understate exit from a rental,
  and the model's target segment is more mobile than all renters. Declared in
  §A11.2.5 before the run. **S3 exists precisely to test whether that is the
  explanation, and it is not:** discarding the level and imposing only the
  composition still lands retention at 78–84%.
- **It cannot say what the missing 27–55 hours are.** It can only say the model
  has no name for them, and that calling them `courage_med = 0.18` was a way of
  not noticing.
