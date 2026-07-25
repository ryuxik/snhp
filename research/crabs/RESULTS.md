# RESULTS — Station Rents (research/crabs)

Simulation of station-habitat rent renewal, pre-registered in `PREREG.md` and
implemented per `SPEC.md`. Code version `crabs-1.0`.

Reproduce:

```
python3 research/crabs/run.py     --phase 1                                 # registered spec
python3 research/crabs/run.py     --phase 1 --seeds heldout
python3 research/crabs/run.py     --phase 1 --spec exploratory
python3 research/crabs/run.py     --phase 1 --spec exploratory --seeds heldout
python3 research/crabs/run.py     --phase 1 --sens                          # + --spec exploratory
python3 research/crabs/analyze.py --file results_phase1_registered.json     # any of the above
python3 -m pytest research/crabs/test_crabs.py -q                           # 69 tests, ~33s
```

Seeds, fixed in code before running: pilot `9000–9019`, main `1000–1059`,
held-out `7000–7059`. 60 stations x 50 habitats x 4 measured years =
**240 station-years / 12,000 habitat-years per cell** (PREREG requires ≥200
station-years). Crab surplus is dollars per occupied crab-year, measured
against paying market rent with no move. All "% of annual rent" thresholds use
the fixed $24,000 anchor, so K1's bar is $480 and K3/K4's is $240.

---

> **POINTER, added 2026-07-25 (PREREG AMENDMENT 3).** Everything in Phase 1 and
> Phase 2 below is reported verbatim and unrevised. Two structural defects were
> later found by inspection: (a) **K1 fired against our own reimplementation of
> ranked asks, not against the SNHP engine** — `negotiate_bundle` is never called
> anywhere in Phase 1/2 — so K1's verdict was SUSPENDED and re-run; see
> "PHASE 4". (b) The market-rent path is exogenous and stations do not compete,
> so it is a set of bilateral negotiations rather than a swarm; GATE 3 was
> registered to test that and **has not been run** (see "What is not done").
> One Phase-2 claim is also corrected in Phase 4 §4: we wrote that a large
> station's grapevine "lifts beliefs more" than a small one; size in fact governs
> the grapevine's *precision*, not its mean.

# PHASE 1

## 1. Validation gate — reported first, as PREREG §7 requires

### 1a. The registered specification

| | LOSS-TO-LEASE | GAIN-TO-LEASE | target | verdict |
|---|---|---|---|---|
| **V1** counter success | **0.000** | **0.003** | 0.15–0.30 | **FAIL** |
| **V2** retention | 0.599 | 0.575 | 0.45–0.65 | PASS |
| **V3** tenure ratio | **n/a** (0 successes) | **1.46** | ≥ 1.50x | **FAIL** |

Held-out seeds (7000–7059) give the same verdict: V1 0.001 / 0.001, V2 0.599 /
0.577, V3 undefined in both regimes for want of any successes.

**GATE: FAIL.** V2 passes everywhere. V1 fails by two orders of magnitude — the
station concedes essentially never. V3 is undefined in the loss regime because
there are no successes at all to compare, and in the gain regime it misses the
1.5x bar on a base of 0.3% vs 0.4%.

Supporting numbers (arm A, the empirical 39% mix, main seeds):

| | loss | gain |
|---|---|---|
| counter rate | 0.389 | 0.390 |
| success, <2y / 2y+ | 0.000 / 0.001 | 0.003 / 0.004 |
| price-concession success | 0.000 | 0.000 |
| mean offer push | +10.7% | −1.2% |
| rent of record / market | 1.055 | 1.120 |
| station's predicted leave rate | 0.402 | 0.424 |
| realised leave rate | 0.401 | 0.425 |
| cash ledger gap | $0.0000 | $0.0000 |

The station's departure model is well calibrated (predicted 0.402 vs realised
0.401), so the failure is not a miscalibrated station. The regime variable works
as intended: the loss regime puts sitting rents 5.5% above market and the
station pushes +10.7% at 59.9% retention (2022 actual: +10.7% pushes, 57.3%
retention); the gain regime puts them 12% above market with the station holding
roughly flat.

**Per PREREG §3, every counterfactual is void.** The arm and kill numbers in §2
and §3 are diagnostic only.

### 1b. Why it failed — the diagnosis

Distance from indifference at the station's concession decision, in months of
market rent. Positive means grant; the figure is the best instrument the crab
would accept:

```
        LOSS                                    GAIN
   r     j=1     j=3     j=5     j=8       j=1     j=3     j=5     j=8
0.95  -0.093  -0.142  -0.187  -0.237    -0.075  -0.128  -0.176  -0.229
1.05  -0.030  -0.021  -0.045  -0.041    -0.033  -0.030  -0.024  -0.021
1.15  -0.035  -0.030  -0.022  -0.018    -0.039  -0.041  -0.037  -0.035
1.30  +0.043  -0.012  -0.005  -0.040    -0.053  -0.061  -0.061  -0.021
```

Every cell but one is a hair below zero — within about $100 of indifference, and
almost always on the refusing side. This is structural, and the reason is an
economic result rather than a bug:

**At its own NPV optimum the station is, by construction, indifferent at the
margin between rent and turnover.** A concession is a discrete step off that
optimum, so it is second-order bad unless the instrument delivers crab value
more cheaply than headline rent does. It does — but only by a little, and the
"little" is smaller than the step size. Because the decision is a single
deterministic threshold evaluated on a tightly clustered state, the outcome is
not a *rate*; it is all-or-nothing. That is why V1 is 0.0% rather than 22%.

### 1c. One respecification, relabelled EXPLORATORY, gate re-run on held-out seeds

PREREG §3 permits exactly one move here: change the specification, relabel the
run exploratory, re-run the gate on held-out seeds. We did that once and
stopped. The change adds **unit-level dispersion in turn exposure**, which is
economically real and was simply missing: make-ready cost ranges from a
touch-up to a full renovation (`sigma_turn = 0.5`), days-vacant swings with
expiry month and unit desirability (`sigma_vac = 0.4`), and an eight-year
habitat costs ~32% more to make ready than a one-year habitat
(`turn_tenure_slope = 0.25`). Both dispersions are mean-one, so the average turn
cost is unchanged (asserted by a test). The manager making the concession call
can see this habitat's own exposure; the revenue-management system still prices
the opening offer off pooled data — which is the article's own picture of an
algorithmic offer with discretionary concessions.

It deliberately does **not** add the mechanism under test — a counter as an
elasticity signal. Adding that would make the experiment circular.

| | LOSS held-out | GAIN held-out | LOSS main | GAIN main | target | verdict |
|---|---|---|---|---|---|---|
| **V1** counter success | 0.045 | 0.134 | 0.039 | 0.126 | 0.15–0.30 | **FAIL** |
| **V2** retention | 0.601 | 0.582 | 0.601 | 0.580 | 0.45–0.65 | PASS |
| **V3** tenure ratio | 10.85 | **0.836** | 24.34 | **0.754** | ≥ 1.50x | **FAIL** |

**GATE: FAIL again**, and with the same shape on held-out and main seeds, so it
is not a seed artefact. V1 moved from 0.0%/0.3% to 3.9%/13.4% — the right
direction and much closer, but still outside the band. We stopped here rather
than continue respecifying, because each further iteration is p-hacking against
a gate whose whole purpose is to be un-hackable.

The failure now has a sharper and more interesting shape:

- In the **loss** regime, concessions are rare (3.9%) but the tenure effect is
  enormous (24x — 6.4% success at 2y+ against 0.3% under 2y).
- In the **gain** regime, concessions are common (12.6%) and the tenure effect
  is absent or slightly reversed (0.75x — 14.7% at <2y against 11.1% at 2y+).

The Avail data these targets come from was measured in 2022 — a loss regime —
and reports **both** a 22% success rate **and** a ~1.8x tenure effect. Our model
cannot produce both at once in the same regime. It produces one or the other, in
opposite regimes.

### 1d. The parameter that decides everything, and why it cannot be set

`FACE_RENT_PREMIUM` (SPEC §6) is how much a dollar of face rent is worth to the
operator above its cash value — the capitalisation channel that makes
concessions cheaper than rate cuts. Sweeping it (exploratory spec, gain regime):

| face premium | C − B (gain) | C − B (loss) | counter success, arm C (gain) |
|---|---|---|---|
| 0.0 | **−$19** | +$11 | 0.012 |
| 0.5 | **−$15** | −$12 | 0.023 |
| 1.0 | +$58 | +$27 | 0.202 |
| 2.0 | +$610 | +$377 | 0.965 |
| 4.0 | +$1,168 | +$814 | 1.000 |

This is the most useful number in Phase 1. **No value of the face-rent premium
reproduces the observed counter-success rate and makes the ranked-ask advice
worth ≥2% of annual rent at the same time.** Where the success rate is plausible
(premium 1.0, giving 20.2%), the ranked-ask edge is $58/year. Where the
ranked-ask edge clears the $480 bar (premium ≥2.0), the station concedes to
96–100% of counterers, which is nothing like the world. And at ≤0.5 the ordering
**inverts**: a headline rent cut becomes the *cheaper* instrument for the station
and asking easiest-first is actively wrong.

The other two flagged parameters behave as SPEC predicted and neither rescues
K1: patience `p_continue` 0.3/0.6/0.9 gives C−B of +$70/+$58/+$44, and
substitution `p_substitute` 0.0/0.35/0.7/1.0 gives +$100/+$58/+$33/+$16 — at
`p_substitute = 1.0`, where the station always volunteers a cheaper instrument
when it refuses a rate cut, the ranked ladder is worth $16/year, i.e. nothing.

## 2. Arm results (diagnostic — the gate failed)

Registered spec, main seeds. Crab surplus, $/crab-year:

| arm | regime | surplus | askers | non-askers | station cash | retention | r/mkt | success |
|---|---|---|---|---|---|---|---|---|
| A mix 39% price | loss | −5919 | −5780 | −6007 | 28512 | 0.599 | 1.055 | 0.000 |
| B all price | loss | −5919 | −5919 | — | 28512 | 0.599 | 1.055 | 0.001 |
| C all ranked | loss | −5918 | −5918 | — | 28512 | 0.599 | 1.055 | 0.001 |
| D share 1.00 | loss | −5918 | −5918 | — | 28512 | 0.599 | 1.055 | 0.001 |
| E adapt 0.75 | loss | −5763 | −5640 | **−6143** | 28426 | 0.603 | 1.060 | 0.280 |
| E adapt 1.00 | loss | −5469 | −5469 | — | 28168 | 0.605 | 1.072 | 0.321 |
| A mix 39% price | gain | −4945 | −4968 | −4930 | 19743 | 0.575 | 1.120 | 0.003 |
| B all price | gain | −4943 | −4943 | — | 19743 | 0.575 | 1.119 | 0.003 |
| C all ranked | gain | −4942 | −4942 | — | 19742 | 0.575 | 1.119 | 0.005 |
| D share 1.00 | gain | −4942 | −4942 | — | 19742 | 0.575 | 1.119 | 0.005 |
| E adapt 0.75 | gain | −4576 | −4418 | **−5058** | 19490 | 0.585 | 1.134 | 1.000 |
| E adapt 1.00 | gain | −4182 | −4182 | — | 19024 | 0.579 | 1.188 | 1.000 |

Exploratory spec, main seeds (concessions now happen, so the arms separate):

| arm | regime | surplus | askers | non-askers | station cash | retention | r/mkt | success |
|---|---|---|---|---|---|---|---|---|
| A mix 39% price | loss | −5877 | −5716 | −5979 | 28150 | 0.601 | 1.054 | 0.039 |
| B all price | loss | −5859 | −5859 | — | 28140 | 0.602 | 1.054 | 0.039 |
| C all ranked | loss | −5832 | −5832 | — | 28123 | 0.602 | 1.054 | 0.062 |
| D share 1.00 | loss | −5832 | −5832 | — | 28123 | 0.602 | 1.054 | 0.062 |
| E adapt 0.75 | loss | −5746 | −5622 | **−6129** | 28061 | 0.603 | 1.060 | 0.266 |
| E adapt 1.00 | loss | −5447 | −5447 | — | 27825 | 0.607 | 1.073 | 0.323 |
| A mix 39% price | gain | −4878 | −4859 | −4891 | 19465 | 0.580 | 1.117 | 0.126 |
| B all price | gain | −4839 | −4839 | — | 19453 | 0.582 | 1.117 | 0.131 |
| C all ranked | gain | −4781 | −4781 | — | 19428 | 0.584 | 1.118 | 0.202 |
| D share 1.00 | gain | −4781 | −4781 | — | 19428 | 0.584 | 1.118 | 0.202 |
| E adapt 0.75 | gain | −4596 | −4448 | **−5046** | 19208 | 0.581 | 1.133 | 0.875 |
| E adapt 1.00 | gain | −4164 | −4164 | — | 18740 | 0.580 | 1.187 | 1.000 |

Market rent averaged $2,523/month in the loss regime and $1,729 in the gain
regime, identical across arms by construction (it is exogenous and shared under
common random numbers), so surplus **levels** are not comparable between
regimes — only differences within a regime are.

## 3. Kill conditions

Reported for both specifications. **Under both, the gate failed, so these are
diagnostic, not findings** — and under the exploratory spec with the extra
caveat that the specification is post-hoc.

### K1 — the ranked-ask advice is decoration. **FIRED** (both specs)

Fires if C does not beat B by ≥$480/crab-year in the gain regime.

- registered: C − B (paired) = **+$2 ± 1**
- exploratory: C − B (paired) = **+$58 ± 2** (loss regime +$27)

Both are an order of magnitude below the $480 bar. FIRED. And §1d shows the bar
is only cleared at face-rent premiums that simultaneously destroy V1.

### K2 — negotiation value is transitional, not structural. **DID NOT FIRE**

Fires if the per-asker value of asking in E declines monotonically to ≤25% of
its arm-D value as asker share → 100%. It does the **opposite** (exploratory
spec; the registered spec has the same shape with noisier levels):

| share | VOA in D (gain) | VOA in E (gain) | E/D | | VOA in D (loss) | VOA in E (loss) | E/D |
|---|---|---|---|---|---|---|---|
| 0.10 | +$220 | +$220 | 1.00 | | +$260 | +$260 | 1.00 |
| 0.25 | +$162 | +$165 | 1.02 | | +$261 | +$261 | 1.00 |
| 0.50 | +$110 | +$137 | 1.24 | | +$128 | +$139 | 1.08 |
| 0.75 | +$84 | +$456 | 5.46 | | +$101 | +$267 | 2.64 |
| 1.00 | +$123 | +$740 | 6.01 | | +$57 | +$442 | 7.72 |

Monotone decline: false. Ratio at share 1.0: 6.01 (gain) and 7.72 (loss), not
≤0.25. **DID NOT FIRE.**

This needs explaining, because "the adaptive landlord makes askers *better* off"
is surprising and my first assumption was a bug. It is not. The adaptive station
raises the **rent of record** (r/mkt 1.118 → 1.187 in the gain regime) and hands
back **cash** (success 1.000). It prefers that trade because face rent carries
the capitalisation premium and cash concessions do not. The crab is indifferent
to face rent and cares only about cash, so it gains. This is a gains-from-trade
result driven entirely by `FACE_RENT_PREMIUM = 1.0`; at premium 0 the adaptive
station has no reason to make the swap and the effect disappears. It is an
artefact of the one parameter we could not pin down and should not be reported
as a finding.

The literal reading of PREREG's wording — per-asker surplus *levels* — is
degenerate, because levels are dominated by the common `12·M` term (E −$4,164 vs
D −$4,781 at share 1.0, a ratio of 0.87 that says nothing about negotiation).
SPEC §10 fixed the value-of-asking form before running; both are reported.

### K3 — the tool has a negative externality. **FIRED in 3 of 4 spec x seed-set combinations**

Fires if non-asker surplus in arm E at high asker share is worse than at share 0
by ≥$240. Share 1.00 has no non-askers by construction, so 0.75 is the highest
evaluable share. This kill sits **right on its bar**, so all four combinations
are reported rather than one:

| spec | seeds | loss regime | gain regime | verdict |
|---|---|---|---|---|
| registered | main | +$230 ± 119 | +$147 ± 73 | did not fire |
| registered | held-out | **+$428 ± 121** | **+$299 ± 64** | FIRED (both) |
| exploratory | main | **+$245 ± 119** | +$180 ± 71 | FIRED (loss) |
| exploratory | held-out | **+$406 ± 119** | **+$318 ± 63** | FIRED (both) |

(positive = non-askers made worse off; bar $240)

**All eight estimates are positive.** The *sign* is unambiguous: non-askers are
always made worse off when three-quarters of their neighbours counter. The
pooled mean is **+$282, or 1.2% of annual rent**, against a 1% bar — which is
why the verdict flips between seed sets. Honest summary: **the externality is
real and consistently present, and its magnitude is right at the threshold we
pre-registered as material.**

The mechanism is exactly the one PREREG §0 anticipated, and it is visible in the
arm table: the station cannot tell askers from non-askers when it sets the
opening offer (asserted by a test), so when three-quarters of crabs counter it
raises the offer on everyone — r/mkt goes 1.118 → 1.133 in the gain regime — and
gives it back only to those who ask. Non-askers eat the increase and get
nothing.

This is the one Phase 1 kill whose direction survives every specification and
seed set, and it is the one that is bad for us.

### K4 — the regime argument is wrong. **FIRED**

Fires unless C's advantage over A is larger in the gain regime than in the loss
regime by ≥$240 (SPEC §10 fixed this threshold before running).

- registered: C − A gain = +$4 ± 2; loss = +$1 ± 0; difference **+$3**
- exploratory: C − A gain = +$98 ± 4; loss = +$45 ± 4; difference **+$53**

**FIRED in both.** The advantage *is* larger in the gain regime under the
exploratory spec — more than twice as large — but the absolute gap is $53, well
under the $240 bar. The regime argument has the right sign and an economically
uninteresting magnitude.

## 4. Phase 1 summary

| | registered | exploratory |
|---|---|---|
| Validation gate | **FAIL** (V1, V3) | **FAIL** (V1, V3) |
| K1 ranked-ask is decoration | **FIRED** ($2 vs $480) | **FIRED** ($58 vs $480) |
| K2 value is transitional | DID NOT FIRE (ratio 6.0, not ≤0.25) | DID NOT FIRE |
| K3 negative externality | **FIRED** on held-out seeds | **FIRED** (3 of 4 combinations) |
| K4 regime argument wrong | **FIRED** ($3 vs $240) | **FIRED** ($53 vs $240) |

### What the adaptive station did to the value of countering

Not what we expected, and the honest answer is "it depends entirely on one
unpinned parameter." The adaptive station did pre-inflate its opening offer
exactly as PREREG predicted — at asker share 1.0 it raised the rent of record
from 1.118x market to 1.187x market in the gain regime, and it is smart enough
to do this only because it knows the asker share (asserted by a test; at share 0
arms D and E are bit-identical). But it did **not** destroy the value of
countering. It increased it, because with `FACE_RENT_PREMIUM = 1.0` it prefers a
high face rent plus cash concessions to a lower face rent, and the crab only
values cash. Set the premium to 0 and that channel closes.

What it unambiguously did do is **push the cost onto people who don't ask**:
non-askers at 75% adoption lost $147–$428/year depending on regime and seed set.
The adaptive station is not a threat to the tool's users. It is a threat to
everyone else.

### What we tuned, and why

1. **`FACE_RENT_PREMIUM = 1.0`** was declared in SPEC §6 before running, with a
   stated rationale and a pre-declared sweep. Not tuned — but §1d shows the whole
   ranked-ask claim rests on it and that no value of it fits the data.
2. **Three bugs fixed during construction, before accepting any gate result.**
   All three were identified from structural symptoms, not from gate levels:
   - The value iteration **diverged** in the loss regime: `δ·(1+g) = 0.935 ×
     1.09 = 1.019 > 1`. A perpetual +9% at 7% discounting makes a habitat worth
     infinity. It produced a term-extension NPV of +1370 months and a spurious
     53% success rate. Fixed by having the station use near-term market growth
     for transitions and long-run growth (3%) for terminal value, which is what
     underwriters do. There is now an assertion that the DP cannot diverge.
   - `renewal_floor = 0.20` made the value function **non-monotone in the rent of
     record** (at high r the station was forced to over-ask and lose the crab).
     An arbitrary constraint producing an artefact; removed. How far to cut is
     the DP's decision.
   - The adaptive station anticipated granting concessions **the crab would
     refuse** (a term lock in a falling market) and mis-set its opening offer
     downward as a result. It may now only anticipate packages with positive crab
     value.
3. **The exploratory respecification** (§1c) is post-hoc and labelled as such
   throughout. It was adopted on the strength of the all-or-nothing diagnosis in
   §1b, its gate was re-run on held-out seeds, and it failed too.
4. **V2 was partly calibrated in, not predicted** — declared in SPEC §8 before
   running. The crab switching-cost distribution was set so the model reproduces
   the two observed elasticity facts, and retention is one of them. V1 and V3 are
   genuine out-of-sample predictions, and they are what failed.
5. **Nothing else.** No station parameter was set by reference to V1 or V3, and
   no parameter changed after any kill-condition number was seen.

### The honest headline finding

**The pre-registered mechanism cannot reproduce the one number we have about
renewal bargaining, and the article's ranked-ask claim is not supported.**

An NPV-optimal landlord facing a counter that carries no information concedes
essentially never (0.0%), and even with realistic dispersion in turn costs it
concedes 3.9–13.4% against an observed 22%. Meanwhile the ranked-ask advantage
is $58/crab-year — a quarter of a percent of annual rent, against a $480 bar.

The most likely missing ingredient is the one we deliberately left out, and it
is the one the article itself names: **countering is only worth something if
countering is a signal.** In our model askers are drawn at random, so a counter
tells the station nothing, and a station already at its optimum has no reason to
move. In the world, people who counter are presumably disproportionately the
people who would leave — which is exactly why it works, and exactly why it would
stop working if everyone did it. That is not a rescue; it is a sharper statement
of the K2/K3 worry, and it points at an uncomfortable prediction: the tool's
value would come from selection, and a tool that succeeds destroys its own
selection.

Three things we can say with the gate failed:

1. **K3 fired and should be published.** A landlord that cannot tell askers from
   non-askers ex ante raises the offer on everyone. At 75% adoption non-askers
   lose about 1.2% of annual rent, positive in all eight estimates, straddling
   the bar we called material.
2. **K1 fired and the ranked-ask section should be downgraded to a hypothesis**,
   per PREREG's own stated consequence. The article's stronger framing — that a
   rent cut "resets the comparable for the entire building" — is not needed by
   the mechanism and is not modelled; the mechanism that does the work is
   unit-level persistence plus capitalisation of face rent, and it is not large
   enough.
3. **K4 fired.** The regime argument has the right sign (the gain-regime
   advantage is ~2x the loss-regime one) and a magnitude of $53/year. Keep the
   idea, drop the emphasis.

### What this cannot establish

Restated from PREREG §6 because a gate failure makes it more important, not
less: this is a model, the station's policy is our invention, and a failure here
is an argument about mechanism, not a measurement. It says our mechanism is
insufficient to explain the data. It does not say countering doesn't work.

## 5. Test suite

60 tests, `python3 -m pytest research/crabs/test_crabs.py -q` (~28s). They cover
determinism (same seed → identical dict; no dependence on the global numpy RNG;
regime-independent burn-in), cash conservation (`station_cash = crab_cash +
arrival_cash − turn_cost` to 1e-6 in every regime, for every landlord type, and
under both shocks), the asker/non-asker partition, policy invariants (offer
respects the renewal cap, is monotone in the rent of record, softens when
turnover is dearer; the value function is monotone; leave probability is
monotone and never below the exogenous floor), the instrument cost ordering that
K1 depends on (a rent cut must cost the station strictly more per dollar
delivered than free weeks, at every state), that a one-time concession does not
move the rent of record while a rent cut does, that the station never grants a
negative-NPV package, and the structural properties the kills rest on — that the
station cannot observe asker status, that arms D and E are bit-identical at share
0, and that the adaptive station really does pre-inflate.

Phase 2 adds 18 of those: per-type determinism and cash conservation, that a
no-increase mom-and-pop never raises rent and no mom-and-pop ever prices a
sitting crab above market, that its grant rate is ~10% at short tenure and rises
with tenure, that MEDIUM's offer is bounded and comp-aware and that it refuses
headline rate cuts, that arm F never reads the nominal asker share (two runs with
shares 0.0 and 1.0 give the same endogenous share), that the endogenous share
moves with belief, that broadcast raises beliefs where asking works and *lowers*
the asker share where it does not, that a 200-habitat grapevine lifts beliefs
more than a 4-habitat one, that the shock arrays have the declared shape and the
flu really drives market rent below 60% of its no-shock path, that wealthy crabs
tolerate more above-market rent, and that cash still conserves under both shocks.

---

# PHASE 2 (PREREG AMENDMENT 1)

Reproduce:

```
python3 research/crabs/run2.py     --spec exploratory
python3 research/crabs/analyze2.py
python3 research/crabs/run2.py     --spec exploratory --shocks
python3 research/crabs/analyze2.py --shocks
```

Phase 1 was written up before this was run. **Everything in Phase 2 inherits
Phase 1's gate failure**: it is mechanism, not measurement. Phase 2 is run on
the exploratory specification, because under the registered one the
institutional station concedes to nobody and there is nothing for landlord type
or a grapevine to be about — a fact that is itself reported below, since it
turns out to be the cleanest test in the section.

Geometry, chosen so every cell clears ≥200 station-years while station **size**
keeps its real value (size is what makes arm F's grapevine informative):

| type | habitats | stations | station-years | habitat-years |
|---|---|---|---|---|
| INSTITUTIONAL | 200 | 60 | 240 | 48,000 |
| MEDIUM | 40 | 120 | 480 | 19,200 |
| MOM-AND-POP | 5 | 500 | 2,000 | 10,000 |

**The MEDIUM policy is our invention with no empirical anchor.** It is marked
on every line it appears on, and it turns out to drive the K5/K6 result, so the
caveat is load-bearing rather than decorative.

## 6. Landlord types

Arm D, 39% ranked askers. *Gain from countering* = asker surplus minus
non-asker surplus in the **same** cell, so composition is random and the
difference is causal. $/crab-year.

**LOSS-TO-LEASE**

| type | gain from countering | success | retention | mean push | r/mkt | surplus | station cash |
|---|---|---|---|---|---|---|---|
| INSTITUTIONAL (200 hab, full RM) | **+$117 ± 61** | 0.061 | 0.603 | +10.7% | 1.053 | −5809 | 28103 |
| MEDIUM (40 hab) ***INVENTED*** | **+$1979 ± 125** | 0.996 | 0.630 | +8.3% | 1.014 | −4268 | 26939 |
| MOM-AND-POP (5 hab) | **−$338 ± 224** | 0.135 | 0.652 | +2.1% | 0.918 | −2692 | 25741 |

**GAIN-TO-LEASE**

| type | gain from countering | success | retention | mean push | r/mkt | surplus | station cash |
|---|---|---|---|---|---|---|---|
| INSTITUTIONAL | **+$100 ± 42** | 0.201 | 0.581 | −1.3% | 1.118 | −4885 | 19449 |
| MEDIUM ***INVENTED*** | **+$1359 ± 64** | 0.998 | 0.577 | −0.6% | 1.131 | −4532 | 19085 |
| MOM-AND-POP | **+$8 ± 98** | 0.138 | 0.511 | +0.0% | 1.119 | −5185 | 18801 |

### K5 — landlord type is not actionable. **DID NOT FIRE**

Fires if gain from countering differs by <$240 across the three types.
Spread = **$2,317** (loss) and **$1,340** (gain), both far above the bar.

**But the spread is created almost entirely by MEDIUM, which we invented.**
Excluding it and comparing only the two empirically anchored types:

| | INSTITUTIONAL | MOM-AND-POP | spread | verdict on grounded types |
|---|---|---|---|---|
| loss | +$117 ± 61 | −$338 ± 224 | $456 | would not fire |
| gain | +$100 ± 42 | +$8 ± 98 | $92 | **would fire** |

So K5's survival is half-grounded at best. On grounded types the gain-regime
spread is $92 — inside the noise and inside the bar. And MEDIUM's dominance is
an artefact we can name precisely: its invented concession budget is
0.5 × (turn cost + vacancy) ≈ 1.65 months, while the standard ask is ≈1.4
months, so it grants essentially every request (success 0.996). We built a
landlord that always says yes. That is not a finding about regional operators;
it is a finding about our own rule, and the honest conclusion is that
**the MEDIUM tier should not be used for anything until it has an anchor.**

### K6 — the tool is worth least where we aimed it. **DID NOT FIRE**

Fires if gain from countering is highest against MOM-AND-POP. Ordering in both
regimes: **MEDIUM > INSTITUTIONAL > MOM-AND-POP**. Mom-and-pop is last in both.

**The pre-registered paradox survives, on the grounded types.** Mom-and-pops
are unambiguously the best landlord to *have* — they push +2.1% against the
institution's +10.7% in the loss regime, they let sitting rents fall to 0.918
of market, and their tenants' surplus is more than twice as good
(−$2,692 vs −$5,809). They are also the worst to *negotiate* with: countering
buys $8 ± 98 in the gain regime and −$338 ± 224 in the loss regime, i.e.
nothing, or possibly slightly less than nothing.

Two caveats on that negative number, because it looks like a bug and is not
quite one. First, it is 1.5 SE from zero on 500 stations of 5 habitats each,
so the honest read is "indistinguishable from zero," not "harmful." Second,
there **is** a real mechanism by which a concession can lower measured surplus:
crabs decide using reference-dependent, `κ_c`-weighted utility, while surplus
is measured in plain one-year cash. A one-time payment can retain a crab that
would have been better off in cash terms leaving. That wedge is a modelling
choice (SPEC §4), not an accounting error, and it is worth knowing it exists
before anyone reads a small negative number as evidence of harm.

**What this would mean for scoping, if the gate had passed:** aiming v1 at
large multifamily is aimed at the right segment among grounded types — the
institution concedes ~2x–3x more often than the mom-and-pop and countering is
worth ~$100–120/year against it versus ~$0. The counterintuitive half of the
thesis holds: the tool is worth most against the most sophisticated
counterparty, because sophistication is what makes a counter answerable at all.
The gate did not pass, so this is a mechanism claim.

## 7. Arm F — BROADCAST

The asker share is **endogenous**: a crab asks when
`belief × ask_scale × 0.11 × 12q` exceeds its own cost of sending the message
(`courage`, lognormal, median $360 — the article's courage problem). Broadcast
changes beliefs; it never sets the share. The control is the same machinery
with broadcast off, so crabs learn only from their own outcome. Asserted by
tests: arm F ignores the nominal `share` entirely, and the endogenous share
moves with the prior belief.

| cell | bcast | ask share | belief | ask scale | success | surplus | askers | non-askers | station cash |
|---|---|---|---|---|---|---|---|---|---|
| loss / F / institutional | off | 0.234 | 0.099 | 1.00 | 0.068 | −5816 | −5660 | −5864 | 28104 |
| loss / F / institutional | **on** | 0.214 | 0.102 | 0.75 | 0.112 | −5812 | −5621 | −5864 | 28102 |
| loss / F / medium *INV* | off | 0.324 | 0.181 | 1.00 | 0.996 | −4380 | −3103 | −4990 | 27048 |
| loss / F / medium *INV* | **on** | **0.780** | 0.459 | 0.92 | 0.998 | −3615 | −3281 | −4798 | 26332 |
| loss / F / mom | off | 0.225 | 0.103 | 1.00 | 0.140 | −2706 | −3452 | −2491 | 25755 |
| loss / F / mom | **on** | 0.248 | 0.110 | 0.94 | 0.149 | −2707 | −3122 | −2570 | 25756 |
| loss / F-adaptive / inst | off | 0.234 | 0.099 | 1.00 | 0.070 | −5817 | −5661 | −5865 | 28104 |
| loss / F-adaptive / inst | **on** | 0.218 | 0.104 | 0.75 | 0.116 | −5812 | −5635 | −5861 | 28102 |
| gain / F / institutional | off | 0.322 | 0.108 | 1.00 | 0.207 | −4891 | −4844 | −4914 | 19453 |
| gain / F / institutional | **on** | **0.461** | 0.165 | 0.73 | 0.310 | −4863 | −4769 | −4942 | 19440 |
| gain / F / medium *INV* | off | 0.417 | 0.195 | 1.00 | 0.998 | −4508 | −3674 | −5104 | 19068 |
| gain / F / medium *INV* | **on** | **0.817** | 0.453 | 0.93 | 0.999 | −3996 | −3708 | −5274 | 18828 |
| gain / F / mom | off | 0.322 | 0.099 | 1.00 | 0.114 | −5196 | −5129 | −5228 | 18798 |
| gain / F / mom | **on** | 0.313 | 0.105 | 0.95 | 0.122 | −5199 | −5314 | −5146 | 18804 |
| gain / F-adaptive / inst | off | 0.325 | 0.110 | 1.00 | 0.236 | −4898 | −4834 | −4929 | 19451 |
| gain / F-adaptive / inst | **on** | **0.506** | 0.188 | 0.73 | 0.445 | −4843 | −4698 | −4991 | 19421 |

Three structural things the grapevine does, all emergent:

1. **It raises adoption only where asking actually works.** Against the
   always-yes MEDIUM it drives the asker share from 0.42 to 0.82; against the
   institution in the gain regime 0.33 → 0.51; against the mom-and-pop, which
   says no 86% of the time, it does essentially nothing (0.32 → 0.31).
2. **It carries bad news too.** Under the *registered* specification, where the
   institution concedes to nobody, broadcast *lowers* the asker share (0.29 →
   0.20) and leaves surplus bit-identical, because a truthful grapevine teaches
   people to stop wasting the ask. This is asserted by a test and it is the
   cleanest evidence we have that the mechanism is not rigged in our favour.
3. **It shrinks the ask.** `ask_scale` falls from 1.00 to 0.73–0.75 against the
   institution: crabs learn what actually cleared, which is smaller than the
   textbook 11%-of-annual-rent ask. Broadcast makes people ask more often and
   ask for less.

### K7 — our product is net-harmful at scale. **DID NOT FIRE**

Fires if under BROADCAST + ADAPTIVE INSTITUTIONAL total crab surplus is lower
than under no-broadcast by ≥$240.

| regime | surplus, broadcast off | broadcast on | harm from broadcast | bar |
|---|---|---|---|---|
| loss | −$5,817 | −$5,812 | **−$5 ± 1** | $240 |
| gain | −$4,898 | −$4,843 | **−$55 ± 4** | $240 |

Broadcast **helped** total crab surplus, by $5 and $55/crab-year — small,
statistically clean, and the wrong sign for the kill. Station cash fell
($19,451 → $19,421). The adaptive station did raise its opening offer as
adoption rose, but not enough to claw back more than it conceded.

So on this model's terms, **the product succeeding does not make its users
collectively worse off.** Two honest qualifications. The effect is tiny — 0.2%
of annual rent, which is nearer "no effect" than "benefit". And it rests on the
same `FACE_RENT_PREMIUM = 1.0` swap identified in Phase 1 §K2: the adaptive
station prefers a higher rent of record plus cash concessions, and crabs only
value cash. At premium 0 that channel closes, and we cannot pin the premium.

### K8 — broadcast only helps the loud. **FIRED**

Fires if under broadcast, non-asker surplus falls while asker surplus rises.

| cell | askers | non-askers | fires |
|---|---|---|---|
| loss / F / institutional | **+$81** | **−$2 ± 12** | yes |
| loss / F / mom | **+$181** | **−$80 ± 47** | yes |
| gain / F / institutional | **+$78** | **−$33 ± 12** | yes |
| **gain / F-adaptive / institutional** | **+$138** | **−$67 ± 15** | **yes** |
| loss / F / medium *INV* | −$128 | +$170 ± 94 | no |
| loss / F-adaptive / institutional | +$70 | +$0 ± 12 | no |
| gain / F / medium *INV* | −$19 | −$178 ± 65 | no |
| gain / F / mom | −$202 | +$113 ± 25 | no |

**FIRED**, in four of eight cells, including the one that matters most —
broadcast plus an adaptive institutional landlord in the gain regime, where
askers gain $138/crab-year and non-askers lose $67 ± 15.

This is K3's externality with a mechanism we actually control, and it is the
result Phase 2 exists to have found. The chain is entirely legible: publishing
base rates raises adoption (0.325 → 0.506); the landlord cannot see who reads
our page, so it raises the opening offer on everyone; askers recover more than
the increase and non-askers eat it. **The quiet subsidise the loud, and we are
the reason.** Per AMENDMENT 1 this belongs on snhp.dev/rent, not in a footnote.

Note the sign flip against MOM-AND-POP in the gain regime (askers −$202,
non-askers +$113): with a landlord that neither raises nor concedes there is
nothing to redistribute and the numbers are noise around zero.

## 8. Phase 2 summary

| kill | verdict | deciding numbers |
|---|---|---|
| K5 landlord type not actionable | **DID NOT FIRE** | spread $2,317 / $1,340 vs $240 bar — **but $92 in the gain regime on grounded types only, which would fire** |
| K6 worth least where we aimed it | **DID NOT FIRE** | MEDIUM > INSTITUTIONAL > MOM in both regimes; mom last |
| K7 net-harmful at scale | **DID NOT FIRE** | broadcast changed total surplus by −$5 / −$55 (i.e. helped), bar $240 |
| K8 broadcast only helps the loud | **FIRED** | gain/F-adaptive: askers +$138, non-askers −$67 ± 15 |

---

# EXPLORATORY — SHOCKS

**No kill conditions. Not evidence.** AMENDMENT 1 §A1.3: these exist for
mechanism intuition and for an article's narrative. No product decision may
rest on them, and if they are ever promoted to evidence that is a failure.

The station does **not** foresee either shock — its policy is solved on a
neutral forecast, so it is surprised, as an operator would be. Surplus is shown
as a percentage of that year's annual market rent as well as in dollars,
because market rent itself moves by 3x across the migration and dollar surplus
is not comparable across years.

## CRAB FLU — demand collapses for eight periods (years 3–10)

INSTITUTIONAL, 200 habitats:

| yr | market | r/mkt | retention | success | vac/hab | incumbent %AR |
|---|---|---|---|---|---|---|
| 2 | 2000 | 1.104 | 0.575 | 0.238 | 0.63 | −10.1 |
| 3 | 1815 | 1.128 | 0.583 | **0.720** | **1.23** | −11.1 |
| 6 | 1344 | 1.132 | 0.583 | 0.724 | 1.23 | −11.5 |
| 10 | 902 | 1.133 | 0.585 | 0.696 | 1.23 | −11.7 |
| 13 | 956 | 1.097 | 0.588 | 0.390 | 0.80 | −9.0 |

**The station holds the rent and eats the vacancy.** Market rent falls 55% and
the rent of record barely moves relative to it (1.104 → 1.133 and flat);
vacancy per habitat doubles; retention does not move at all. What triples is
**concessions**: the success rate on a counter goes 0.24 → 0.72 and stays
there for the whole collapse, then falls back to 0.39 on recovery.

So the answer to the pre-registered question is: tenant leverage in a demand
collapse is real but it arrives as *concessions, not as a lower rent of record*
— which is exactly the shape of the 2026 evidence (39.7% of listings carrying a
move-in deal while renewal rents stayed positive). It also means a tenant who
asks "will you lower my rent?" during a bust is asking the one question the
model says the landlord will refuse, while the thing it will say yes to costs it
the same cash and preserves its rent roll.

The other two types behave very differently, and it inverts the "best landlord
to have" ordering:

| type | retention before flu | during flu | vac/hab before → during |
|---|---|---|---|
| INSTITUTIONAL | 0.575 | 0.583 (flat) | 0.63 → 1.23 |
| MEDIUM *INVENTED* | 0.596 | 0.478–0.502 | 0.61 → 1.28 |
| MOM-AND-POP | 0.609 | **0.411–0.434** | 0.60 → 1.70 |

The mom-and-pop, best landlord to have in normal times, is the worst in a
collapse: it does not cut, does not concede, and its tenants leave — retention
falls by a third and its vacancy per habitat nearly triples. The institution's
revenue management is what keeps its tenants through the bust.

## THE AI CRAB MIGRATION — high-budget arrivals years 2–7, half depart year 8

INSTITUTIONAL:

| yr | market | r/mkt | retention | vac/hab | incumbent %AR | migrant %AR |
|---|---|---|---|---|---|---|
| 1 | 2004 | 1.104 | 0.579 | 0.63 | −10.0 | — |
| 4 | 2540 | 1.055 | 0.614 | 0.55 | −7.4 | −4.0 |
| 7 | 3234 | **1.052** | **0.640** | 0.51 | −8.4 | −4.4 |
| **8** | 2785 | **1.136** | **0.365** | **0.91** | **−15.7** | **−12.7** |
| 9 | 2793 | 1.101 | 0.581 | 0.62 | −8.5 | −11.8 |
| 13 | 2787 | 1.104 | 0.588 | 0.62 | −9.7 | −13.3 |

MOM-AND-POP, same shock:

| yr | market | r/mkt | retention | incumbent %AR | migrant %AR |
|---|---|---|---|---|---|
| 1 | 2006 | 1.033 | 0.607 | −4.0 | — |
| 7 | 3237 | **0.854** | 0.652 | **+12.8** | +11.5 |
| **8** | 2785 | 0.916 | **0.370** | +4.6 | **−6.2** |
| 13 | 2795 | 1.010 | 0.642 | −0.8 | −1.3 |

Three mechanisms worth the article:

1. **The boom is good for incumbents and the mechanism is the renewal cap.**
   Market rent rises 62% over six years; the institution can only push 12% a
   year, so its incumbents fall *behind* market (r/mkt 1.104 → 1.052) and
   retention rises to 0.640 — they cling to a below-market rent. Against a
   mom-and-pop, which pushes 3% and never above market, incumbents go to 0.854
   of market and their surplus turns positive (+12.8% of annual rent). The
   tenant who wins the boom is the one whose landlord is slowest.
2. **Gain-to-lease inverts in a single year on the way out.** At the exodus,
   r/mkt jumps 1.052 → 1.136 for the institution and 0.854 → 0.916 for the
   mom-and-pop, retention halves (0.640 → 0.365), vacancy per habitat rises
   79%, and incumbent surplus has its worst year of the whole run (−15.7% of
   annual rent). The rent of record is sticky on the way down, so the comp the
   newcomers set is left behind as a bill for the people who stayed.
3. **The migrants take the worst of it, and keep taking it.** They signed at
   the peak, so their surplus goes to −12.7% at the exodus and stays worse than
   the incumbents' for the rest of the run (−13.3% vs −9.7% at year 13). Buying
   at the top of a comp is a durable mistake in this model, not a transient one.

The mom-and-pop tenant's arc is the cleanest story in the whole simulation:
+12.8% of annual rent at the peak of the boom, and −0.8% five years later. They
got rich because their landlord wasn't paying attention, and gave all of it back
when the market normalised.

---

# PHASE 4 — the real engine (AMENDMENT 3) and the engine matrix (AMENDMENT 4)

Reproduce:

```
python3 research/crabs/run_engine.py
python3 research/crabs/analyze_engine.py
python3 -m pytest research/crabs/test_crabs.py -q          # 69 tests, ~33s
```

Same seeds (`1000–1059`), 50 habitats, both regimes, all crabs counter. Phase 1's
station is unchanged; what changes is who negotiates and how.

## 1. Grounding of the agent utilities (A3.2), labelled

| quantity | label |
|---|---|
| income | **ANCHORED** level (ACS renter median, market-rate segment) / **INVENTED** dispersion (σ_log = 0.55) |
| cost burden | **DERIVED** from rent/income > 0.30 |
| marginal utility of rent | **DERIVED**: CRRA(η=1.5) over residual income — a cost-burdened tenant is more rent-sensitive without being told to be |
| household size | **ANCHORED** (approx), ACS renter shares |
| job flexibility | **INVENTED**, Beta(2,3) |
| moving cost | **INVENTED** functional form, **ANCHORED** scale (median $7,199, matching Phase 1's elasticity-calibrated $7,200) |
| priority weights | **INVENTED**, Dirichlet(2.5, 1.0, 1.2, 0.8) — and unavoidably so: nobody has published tenant priority weights across rent/term/credit/fees. This is the same evidence gap the article is about. |
| station costs | **ANCHORED** NAA/IREM/BOMA |
| station priorities | **DERIVED** from the station's own NPV, never drawn |

Checks that the logrolling surface actually exists: **17.7% of tenants weight
term above rent**; 54.7% are cost-burdened at the anchor rent (published ~50%).
Had the first number been ~0, logrolling could not help and K13 would have
deserved to fire on the population rather than the engine.

## 2. The K1 re-run against the real engine — reported first, per A3.5

The crab's side is now `gametheory.negotiation.bundle.negotiate_bundle`
(multi-issue) or `.plain_terms.negotiate_turn` (rent only). The engine receives
the tenant's own utilities and Dirichlet priorities, and only the *direction* of
the station's preferences — **the station's relative priorities are inferred by
the engine from its offers, which is the product, and is not bypassed** (asserted
by a test).

$/habitat-year, main seeds:

| negotiator | regime | tenant cash | welfare | joint cash | joint+welfare | turnover | success | issues/grant |
|---|---|---|---|---|---|---|---|---|
| ladder (Phase 1) | loss | −5783 | 0 | 22283 | 22283 | 0.395 | 0.051 | 1 |
| engine, rent only | loss | −5840 | 0 | 22249 | 22249 | 0.396 | 0.129 | 1 |
| **engine, bundle** | loss | **−4896** | 33 | **23045** | 23077 | 0.382 | 0.166 | **2.04** |
| ladder (Phase 1) | gain | −4829 | 0 | 14520 | 14520 | 0.424 | 0.199 | 1 |
| engine, rent only | gain | −4946 | 1 | 14443 | 14444 | 0.429 | 0.082 | 1 |
| **engine, bundle** | gain | **−3969** | 552 | **15645** | 16197 | 0.413 | 0.716 | **3.42** |

### K13 — logrolling does nothing here. **DID NOT FIRE**

Bar: multi-issue must beat single-issue rent bargaining by ≥$480/crab-year.

| regime | metric | bundle − single |
|---|---|---|
| loss | tenant **cash** (pre-registered unit) | **+$944 ± 43** |
| loss | tenant cash + welfare | +$977 ± 46 |
| gain | tenant **cash** | **+$977 ± 39** |
| gain | tenant cash + welfare | +$1,528 ± 43 |

Roughly **2× the bar**, on the pre-registered cash metric, in both regimes.

### K14 — the engine is worse than the hand-rolled ladder. **DID NOT FIRE**

engine − ladder = **+$887 ± 41** (loss), **+$860 ± 38** (gain). The engine beats
our reimplementation decisively.

### K1's suspended verdict

**K1 fired in Phase 1 against a reimplementation and does NOT fire against the
real engine.** C − B was +$58 with the hand-rolled ladder; the equivalent
multi-issue-versus-single-issue gap with `negotiate_bundle` is +$944/+$977,
against a $480 bar. Phase 1's K1 verdict stands as reported for what it tested —
our own ladder — and is **superseded as a test of the product**.

### The bug hunt, because this result favours us

Three confounds, each tested and each cleared:

1. **Protocol parity.** The engine initially got three unconditional rounds while
   the ladder faced the station's patience roll each round. Applying the same
   patience to the engine changed the gap from +$930/+$900 to **+$887/+$860** —
   it was not the driver. The fix is in the code, not just in this note.
2. **Is it one trade?** Removing the 24-month term issue entirely *increases* the
   engine's advantage (+$965/+$958), so the term lock is not the story — it was
   slightly reducing the gain.
3. **Was the ladder crippled by "a grant ends the negotiation"?** Letting the
   ladder keep asking after a yes adds **+$0 (loss) / +$23 (gain)**. Not the
   driver either.

What is left, and what I believe the mechanism is: the ladder asks for fixed
sizes of one instrument at a time, and the engine searches the whole
4×2×4×2 bundle space for a package that clears *both* sides' thresholds. Its
success rate is 0.166/0.716 against the ladder's 0.051/0.199. **The engine wins by
finding deals that exist, not by extracting harder.**

### The caveat that matters most

**The engine arm does not pass Phase 1's validation gate either — it fails in the
opposite direction.** Observed counter success is ~22%. Phase 1 undershot
(0.0–13%); the engine arm in the gain regime **overshoots at 71.6%**. Only the
loss-regime figure (16.6%) lands inside the pre-registered 15–30% band, and that
is a different quantity from V1 (all crabs counter here, on bundles, not 39% on
price), so it is suggestive rather than a gate pass. Phase 1's gate failure is
not repaired by Amendment 3; it is relocated.

## 3. Arm K — the engine matrix. Joint surplus first, per A4.3

Rent is a **pure transfer** between the pair, so it cancels in the joint total.
Joint surplus can move only through **deadweight** (turn cost + vacancy + moving
cost, destroyed rather than moved) and through the **preference-intensity
premium**. Both are reported because they can disagree. This is what makes K17 a
sharp test rather than a rhetorical one: an engine that merely shifts cash cannot
move joint surplus at all.

**LOSS-TO-LEASE** ($/habitat-year)

| cell | joint cash | joint+welfare | deadweight | turnover | welfare | success |
|---|---|---|---|---|---|---|
| N/N (neither) | 22249 | 22248 | 8024 | 0.396 | −0 | 0.004 |
| T/N (tenant has it) | 22479 | 22537 | 7794 | 0.392 | 58 | 0.038 |
| **N/L (landlord has it)** | **23625** | 23747 | **6648** | 0.389 | 122 | 0.743 |
| T/L (both) | 23621 | 23747 | 6652 | 0.389 | 126 | 0.743 |

**GAIN-TO-LEASE**

| cell | joint cash | joint+welfare | deadweight | turnover | welfare | success |
|---|---|---|---|---|---|---|
| N/N | 14451 | 14450 | 6299 | 0.428 | −1 | 0.024 |
| T/N | 14569 | 14748 | 6181 | 0.432 | 179 | 0.106 |
| **N/L** | **15454** | 15841 | **5296** | 0.415 | 386 | 0.793 |
| T/L | 15453 | 15843 | 5297 | 0.415 | 390 | 0.793 |

Paired against N/N:

| cell | joint cash (loss) | joint cash (gain) |
|---|---|---|
| T/N | +$230 ± 29 | +$117 ± 30 |
| **N/L** | **+$1,376 ± 71** | **+$1,003 ± 56** |
| T/L | +$1,372 ± 71 | +$1,001 ± 57 |

**The split** (reported second, per A4.3), $/habitat-year:

| regime | cell | tenant | landlord |
|---|---|---|---|
| loss | N/N | −5838 | 17317 |
| loss | T/N | −5540 | 17697 |
| loss | **N/L** | **−4003** | **19959** |
| loss | T/L | −4003 | 19952 |
| gain | N/N | −4937 | 11831 |
| gain | T/N | −4701 | 12119 |
| gain | **N/L** | **−3591** | **13812** |
| gain | T/L | −3589 | 13814 |

### K16 — we arm the stronger side more than the weaker. **FIRED**

| regime | landlord gain in N/L | tenant gain in T/N | ratio |
|---|---|---|---|
| loss | **+$2,642 ± 121** | +$298 ± 26 | **8.9×** |
| gain | **+$1,981 ± 88** | +$236 ± 22 | **8.4×** |

**FIRED, decisively, in both regimes.** Putting SNHP in the landlord's hands is
worth about **nine times** more to the landlord than putting it in the tenant's
hands is worth to the tenant. Per A4.3 this goes in the article **and** on
snhp.dev/rent.

Two things that make it worse rather than better for us. First, **the tenant is
also better off in N/L** (−4003 vs −5838 in the loss regime): the landlord-held
engine is Pareto-improving, so we cannot dismiss it as extraction — it is real
value creation of which the landlord captures ~90%. Second, **T/L ≈ N/L to within
$4**: once the landlord has the engine, the tenant having it too adds nothing
measurable. The landlord's opening bundle has already taken the surplus.

**How this kill was nearly missed, which is the part I want on the record.** My
first implementation let the SNHP landlord only *reply* to asks. Because the
heuristic tenant's asks are almost never granted, the landlord's engine had
nothing to do, N/L came out bit-identical to N/N, and **K16 read "DID NOT FIRE"
with a landlord gain of +$3.** That was a defect in my Arm K code, not a finding.
Allowing the landlord to *open* with a bundle — which is what a landlord holding
a negotiation engine would obviously do, and which Phase 1's arm E had already
shown to be profitable (raise the rent of record, hand back cash, because face
rent is capitalised and cash is not) — moved the landlord's gain from +$3 to
+$2,642 and fired the kill. There is now a test asserting the landlord can open
above its plain optimum.

### K17 — it is an arms race, not value creation. **DID NOT FIRE**

T/L − N/N on joint cash: **+$1,372 ± 71** (loss), **+$1,001 ± 57** (gain) —
about 4–6% of annual rent, far outside noise. Mechanically this is deadweight
reduction: total deadweight falls from $8,024 to $6,652 per habitat-year in the
loss regime and from $6,299 to $5,297 in the gain regime. Real value, not a
transfer.

### K18 — mutual engines destroy value. **DID NOT FIRE**

Turnover *falls* in T/L (0.396 → 0.389 loss; 0.428 → 0.415 gain) and joint
surplus rises. Requires both to go the wrong way; neither does.

### The pre-registered SURVIVES condition

**Joint surplus in T/L materially exceeds N/N**, so on A4.2's own terms this is
the best available outcome: the engine finds Pareto improvements both sides
missed. But it survives *alongside* K16 firing, and the two together give a
single honest sentence: **SNHP creates real joint value in rent renewal, and if
the landlord holds it the landlord captures about 90% of that value.** A4.2
anticipated that the survive case would mean rewriting the article around joint
gains; the K16 result means the rewrite also has to say who the gains go to.

## 3b. Phase 1's numbers under the Phase-4 code

Amendments 2–4 added uniform slots to the common-random-number stream (22 → 29
draws per habitat-year, for the demographic and belief machinery). That shifts
every random draw, so **re-running Phase 1 today no longer reproduces the exact
figures printed above** — same distributions and same seeds, a different
realisation. The figures in Phase 1 stand as reported at that code state, and the
verdicts were re-checked under the current layout:

| | Phase 1 as reported | re-checked under Phase-4 layout |
|---|---|---|
| Gate | **FAIL** (V1 0.000/0.003, V3 n/a/1.46) | **FAIL** (V1 0.000/0.002, V3 n/a/0.47) |
| K1 | FIRED (C−B +$2) | FIRED (C−B +$0) |
| K2 | DID NOT FIRE | DID NOT FIRE |
| K3 | FIRED on held-out seeds | FIRED (+$263 loss, +$352 gain) |
| K4 | FIRED (difference +$3) | FIRED (difference −$4) |

Every verdict is unchanged, and K3's two new estimates sit inside the range of
the eight already pooled in §3 — consistent with "the sign is robust, the
magnitude sits on the bar".

## 4. A Phase-2 claim I got wrong

Phase 2 §7 states that a 200-habitat grapevine "lifts beliefs more" than a
4-habitat one. That is wrong as stated. Station size governs the *precision* of
the grapevine, not its mean: with a landlord whose concession rate is the same
regardless of size, both large and small stations converge on the same believed
success rate given enough station-years. Re-running under Phase 4's random-number
layout gives lifts of 0.3500 (200 habitats) versus 0.3495 (4 habitats) — a tie.
The test now asserts the weak inequality and says why. The Phase 2 text is left
verbatim per the amendments' discipline; this is the correction.

## 5. What is NOT done, and what that costs

**GATE 3 (AMENDMENT 3 §A3.3) has not been run.** The market is still an imposed
`market_path`: stations do not post asking rents, do not compete for a search
pool, and leaving crabs vanish rather than re-match. So:

- **V8 / V9 / V10 are unevaluated, and K15 is undecided.** We cannot say whether a
  supply shock produces gain-to-lease endogenously, nor whether the MAA sign
  pattern (negative new-let growth beside positive renewal growth) emerges from
  primitives.
- The honest consequence is the one A3.3 already wrote down: **the article's
  central empirical claim rests entirely on the REIT filings, with no mechanism of
  our own.** Phase 1's regime variable is imposed, exactly as the landlord
  behaviour in Phase 2 was imposed, and that criticism stands unanswered.

**AMENDMENT 2's arms G–J and GATE 2 have not been run either.** The substrate is
built and tested — `emergent.py` derives every landlord difference from portfolio
size (risk aversion ∝ 1/U from CRRA over total income, comp noise ∝ 1/√U,
non-pecuniary value and cost-of-raising ∝ 1/(1+U/10), turn-cost scale economy,
size-scaled face-rent capitalisation, agent wedge), the arm-G blanket-policy and
exception-queue machinery is in `world.py`, the ask-mode machinery for arms H/I is
in place, and `SPEC-A2.md` fixes every primitive value before any run. What is
missing is the runs and the verdicts. **K9–K12 are undecided.** One prediction is
already on record in SPEC-A2 §A2-2 and should be checked when it is run: a
first-order calculation says the risk-aversion channel is too weak to carry the
hypothesised chain, so the "risk aversion + bad comps ⇒ small pushes" story will
probably rest on the non-pecuniary primitives instead.

I sequenced K1's re-run and Arm K first because they were named the highest-value
items. That was the right call, but it means two registered gates are open and
four kills undecided, and no conclusion here should be read as though they had
passed.
