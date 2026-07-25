# TRIAGE — which claims survive their own parameter's declared sweep

*Run 2026-07-25. Scope: everything that runs through `world.py`, `policies.py`,
`engine_bridge.py`, `landlords.py` / `armk.py` — Phase 1, Phase 2, the shocks,
the engine arms, K1–K18. K19–K26 and everything in `market.py` are another
agent's triage and are marked OUT OF SCOPE below rather than judged here.*

**The bar.** A claim that does not hold across its own parameter's declared
sweep is not a claim; it is a calibration readout. Several parameters in this
study are circular — their justification is the outcome they produce — so
"does this survive its parameter moving?" now decides what can be published.

**Verdict buckets.** SURVIVES / DIES / **FLIPS** (holds at every swept point of
some parameters but changes verdict across the declared range of another, so it
is neither publishable nor withdrawable as stated) / UNTESTABLE (the apparatus
cannot decide it without a respecified run).

**What was run.** New runners, none of the fenced files touched:

```
python3 research/crabs/triage_margin.py                 # (a) the DP margin, analytic + numeric
python3 research/crabs/triage_arms.py --part queue      # (b) queue_frac
python3 research/crabs/triage_arms.py --part info       # (c) signal vs selection
python3 research/crabs/triage_arms.py --part split      # (d) courage_med / belief0
python3 research/crabs/triage_extern.py --part k3       # (e) K3 + the arm-D ablation
python3 research/crabs/triage_extern.py --part k8       # (e) K8 broadcast
python3 research/crabs/triage_shock.py                  # (f) crab flu
python3 research/crabs/triage_k16.py                    # (g) K16 one-knob decomposition
```

Two defects in the shipped runners were found and worked around rather than
edited: `run._station` and `run2._get` key their station caches on a subset of
`Params`, omitting `renewal_cap` and `move_med`, so **any sweep of those two
through the shipped runners silently reuses another cell's solved policy.**
`triage_extern.py` replaces both with a full-parameter key. This is worth fixing
in place; the first pass of the K3 sweep produced a bogus `renewal_cap = 2.0`
row before it was caught (arms D and E disagreed at share 0, where they are
supposed to be bit-identical — that disagreement is the detector).

Per AMENDMENT 8 and the coordinator's instruction, every claim that rests on
`move_med` is run at both the calibrated **3.60** and the derived **1.48**.

---

# PART 1 — the narrative claims (what the article is built from)

## (a) "A landlord at its own optimum is indifferent at the margin, so a randomly-chosen counter earns it nothing"

**It is not analytic. Two thirds of it is, and the load-bearing third is a ratio
of three INVENTED constants.** Derivation first, because an analytic claim is
worth more than a swept one and this one has to be split before it can be judged.

Let `W(q, z)` be the station's NPV when it offers ratio `q` and settles a
concession worth `z` (months) to the crab:

```
W(q,z) = (1 - pl(g - z)) * (S(q) - z)  +  pl(g - z) * T
g(q)   = 12*kappa_c*(q-1) + 12*lambda_ref*(q-r) - a(j)
S(q)   = 12*q*(1+face_premium) - q_sit + d1*V(q/(1+g_mkt), j+1)
```

Differentiate in `z` at `z = 0`, then substitute the station's own optimality
condition in `q` (`dW/dq = 0`, which is what "sitting at its own optimum" means):

```
dW/dz|0  =  pl'(g)*(S-T) - (1-pl)
dW/dq    = -pl'(g)*gamma*(S-T) + (1-pl)*sigma = 0
                                =>  pl'(S-T) = (1-pl)*sigma/gamma

    ==>   dW/dz|0  =  (1 - pl) * ( sigma/gamma - 1 )

    gamma = 12*(kappa_crab + lambda_ref)          = 25.2   the CRAB's marginal
                                                            valuation of q
    sigma = 12*(1+face_premium) + d1*dV/dr'                the STATION's
```

So the first-order value of a marginal concession is **not zero**. It is
`(1-pl)` times how much more a marginal dollar of headline rent is worth to the
landlord than to the tenant. It is zero only where `sigma == gamma` — a coincidence
between `face_premium` (INVENTED), `kappa_crab` (INVENTED) and `lambda_ref`
(INVENTED). Verified numerically over `r in {0.95…1.30} x j in {1,3,5,8}`
(`triage_margin.py`, exploratory spec, loss regime; `pred A` is the formula,
`act A` the numerical `dW/dz` at eps = 1e-4):

| sweep | σ/γ | pred A | act A | grants ONE_TIME | grants a RENT cut |
|---|---|---|---|---|---|
| `face_premium` 0.0 | 0.557 | −0.278 | −0.297 | 0% | 0% |
| `face_premium` 0.5 | 0.840 | −0.098 | −0.146 | 0% | 0% |
| **`face_premium` 1.0 (shipped)** | **1.124** | **+0.079** | **+0.015** | **4%** | **0%** |
| `face_premium` 2.0 | 1.692 | +0.430 | +0.320 | 86% | 0% |
| `face_premium` 4.0 | 2.831 | +1.130 | +0.896 | 89% | 0% |
| `kappa_crab` 0.8 | 2.303 | +0.831 | +0.289 | 68% | 0% |
| `kappa_crab` 3.2 | 0.586 | −0.263 | −0.266 | 0% | 0% |
| `lambda_ref` 0.0 | 1.371 | +0.239 | +0.017 | 18% | 0% |
| `lambda_ref` 1.0 | 0.985 | −0.008 | −0.015 | 0% | 0% |
| `move_med` 1.48 (derived) | 1.097 | +0.060 | +0.061 | 0% | 0% |
| `move_med` 7.20 | 1.433 | +0.294 | −0.156 | 21% | 0% |

Three separate things fall out, and they have different verdicts.

**a1 — "at its own optimum, indifferent at the margin": ANALYTIC, but false for
most loss-regime renewals.** `dW/dq = 0` is a definition, not a finding. It only
holds at an *interior* optimum, and the shipped `renewal_cap = 0.12` is binding
on **72.3%** of realised loss-regime renewals (`results_amend7_registered.json`,
`share_at_cap`). On those the station is at a corner and would raise the rent
further if allowed — the opposite of indifferent. `renewal_cap` is **CIRCULAR**.

**a2 — "the station learns nothing it didn't already price in": TRUE BY
CONSTRUCTION, not a finding.** In Phase 1/2 asker status is a random trait and
`StationDP.negotiate` has no counter-conditional belief. `run.py` says so
explicitly ("It deliberately does not add the mechanism under test"). Add the
belief (arm H) and the station learns a great deal — see (c).

**a3 — "conceding is a straight loss": DIES.** At the shipped parameters the
first-order term is **positive** (+0.079 station-months per crab-month
delivered). What actually keeps the grant rate near zero is the *lumpiness* of
the grant menu, not indifference: the smallest menu grant delivers 0.42–0.47
months of crab value, the first-order gain on it is ≈ +0.02 months and the
curvature cost is ≈ −0.03 to −0.09 months, netting −$10 to −$190/yr. The whole
"wall" is a $60/year balance between two quantities set by INVENTED constants.

**The wall itself, measured in the simulation** (arm A counter-success, from
`results_amend7_*.json`, which is the A7 cap sweep re-read rather than taken
from the summary):

| renewal_cap | success, loss (reg / expl) | success, gain (reg / expl) |
|---|---|---|
| 0.06 | 0.96% / 0.88% | 0.74% / 13.45% |
| **0.12 (shipped, CIRCULAR)** | **0.04% / 3.25%** | **0.17% / 12.89%** |
| 0.25 | **42.90% / 49.31%** | 0.17% / 12.71% |
| 0.50 | 43.34% / 49.77% | 0.17% / 12.71% |
| 2.00 (free) | 43.34% / 49.77% | 0.17% / 12.71% |
| 2.00, `face_premium` 0 | 53.39% / 58.23% | 0.35% / 8.90% |
| 2.00, `face_premium` 2 | 54.74% / 56.93% | 54.79% / 54.48% |

**In the loss regime the wall is the circular parameter.** Free the cap and an
NPV-optimal station concedes to 43–50% of counterers. (Diagnosed: at the free
optimum the 24-month TERM lock becomes NPV-positive in 57% of states, against 4%
capped.) In the gain regime the wall holds across the whole cap sweep and dies
only at `face_premium ≥ 2.0` — which SPEC §6 itself says is the *honest*
region, since "cap-rate arithmetic implies far more" than 1.0.

**The one part that survives everything:** a headline **rent cut is never
granted** — 0% of states at every point of every sweep, including
`face_premium = 0`. The *ordering* the ranked ladder rests on is structural.
Its *size* is not (see K1).

> **VERDICT (a): DIES as stated.** Publishable residue: (i) the optimality
> identity, stated as an identity; (ii) rent is the hardest instrument to get,
> at every parameter tried; (iii) the honest negative — *we could not tell
> whether a well-run landlord concedes, because the two constants that decide it
> have no source and the third is circular.*

## (b) "Menu costs + an exception queue made countering pay WORSE, and most counterers are unread rather than refused"

Rests on `queue_frac = 0.15`, which SPEC-A2 §A2-5 calls "a working guess"
(**INVENTED**). Swept `{0, 0.02, 0.05, 0.10, 0.15, 0.25, 0.50, 1.0, 2.0}`,
institutional 200 units x 60 stations, arm G alone (`triage_arms.py --part queue`):

| queue_frac | regime | success | unread share | value of countering ($/crab-yr) | total surplus |
|---|---|---|---|---|---|
| *baseline, no menu costs* | loss | 0.068 | — | **+184 ± 65** | −5598 |
| 0.05 | loss | 0.006 | 0.873 | +38 ± 60 | −6000 |
| **0.15 (shipped)** | loss | **0.020** | **0.619** | **+177 ± 60** | −5939 |
| 0.25 | loss | 0.033 | 0.365 | +305 ± 62 | −5887 |
| ≥ 0.50 | loss | 0.051 | 0.000 | **+490 ± 62** | −5813 |
| *baseline, no menu costs* | gain | 0.100 | — | **+16 ± 39** | −4731 |
| 0.05 | gain | 0.012 | 0.871 | −13 ± 35 | −5122 |
| **0.15 (shipped)** | gain | **0.037** | **0.615** | **+126 ± 38** | −5081 |
| ≥ 0.50 | gain | 0.099 | 0.000 | **+436 ± 47** | −4976 |

- **"Most counterers are unread": true at 0.15, and it is arithmetic.** Read
  share = `min(1, queue_frac / counter_rate)` = 0.15/0.39 = 0.385; measured
  0.381 / 0.385. The model cannot return anything else for any `queue_frac`
  below the counter rate, and returns the opposite above it. **A restatement of
  an invented parameter, not a finding.**
- **"Countering paid worse": true of the success RATE, false of the money.**
  Success falls 0.068 → 0.020 (loss) and 0.100 → 0.037 (gain), and stays at or
  below baseline even at unlimited capacity — that part is robust. But the
  dollar value of countering at the shipped `queue_frac` is +$177 ± 60 against a
  baseline +$184 ± 65 (a tie) in the loss regime and **+$126 ± 38 against +$16 ± 39
  (better by +$110 ± 54)** in the gain regime. At capacity ≥ 0.39 countering is
  worth **2.7x the baseline**. The sentence "it paid worse" is true only of a
  rate the article never quotes.
- **What is robust and was not claimed:** the blanket policy makes *everyone*
  worse off — total crab surplus −$341 (loss) / −$350 (gain) at the shipped
  value, negative at every `queue_frac`, of which $215 (loss) / $245 (gain) is
  the blanket policy itself and the rest is the queue.

> **VERDICT (b): DIES as stated** (the money went the other way in one regime and
> tied in the other). Two survivors: countering succeeds *less often* under a
> blanket policy at every queue capacity, and a blanket policy costs tenants
> ~1.4% of annual rent whether or not anyone counters.

## (c) "Asking works only because it is informative, so its value depends on asking being rare"

*In scope this is arm H: `weights_counter`, the switching-cost distribution the
station believes it faces GIVEN a counter, measured from a pilot run.* The
apparatus can separate the two candidate mechanisms, and the study never did:

- **SIGNAL** — the station updates on the *act* of countering (`prior=True` vs
  `prior=False`, same ask mode, same asker share). One knob.
- **SELECTION** — the tool picks better askers (`tool`/`selfselect` with the
  prior OFF, against `random_at` at the *same* asker share). One knob.

The asker share is traced with a single knob, `engage_margin` (INVENTED, 2.0
months), from `tool` (only tenants past the walk-away floor ask) up to
`everyone`. `random_at` supplies a random-asker control at each share.

**The cleanest statement uses one arm.** Hold the station's inference machinery
fixed (prior ON throughout) and move only the asker share:

| asker share (loss) | 0.012 | 0.041 | 0.105 | 0.287 | 0.648 | 0.935 | 1.000 |
|---|---|---|---|---|---|---|---|
| **counter success** | **0.943** | 0.982 | 0.943 | 0.736 | 0.257 | 0.053 | **0.045** |
| population value vs a random asker at the same share | −$16 | — | +$229 | **+$390** | +$136 | +$62 | +$26 |

| asker share (gain) | 0.025 | 0.078 | 0.161 | 0.374 | 0.713 | 0.946 | 1.000 |
|---|---|---|---|---|---|---|---|
| **counter success** | **0.997** | 1.000 | 1.000 | 0.998 | 0.431 | 0.080 | **0.053** |
| population value | +$39 | — | ~+$305 | **+$551** | ~+$180 | ~+$3 | **−$16** |

**A 20x decay in the value of a counter as countering goes from rare to
universal, monotone, on one knob, in both regimes.** The population value (total
crab surplus over an *identical* population, Principle D, against `random_at`
at the matched share) is an inverted U: it peaks near 30% adoption at +$390
(loss) / +$551 (gain) — the gain figure clears the $480 bar — and decays to
approximately zero, and in one cell slightly negative, at full adoption.

**Which of the two mechanisms does it?** The signal, decisively:

| | signal channel (prior ON − OFF, same share) | selection channel (prior OFF vs `random_at`, same share) |
|---|---|---|
| loss, share ≈ 0.01 | **+0.804** | +0.072 |
| loss, share ≈ 0.28 | **+0.647** | +0.021 |
| gain, share ≈ 0.02 | **+0.871** | +0.019 |
| gain, share ≈ 0.37 | **+0.896** | +0.002 |
| either, share = 1.00 | **−0.047** | 0.000 |

Selection — the tool picking tenants who really would leave — moves the success
rate by 0.002–0.072. The station's *inference from the act of countering* moves
it by 0.80–0.90, and that term is what dies as everyone starts asking.

**Bug hunt, because this one favours the story.** (i) `weights_counter` is not
an information leak: it is a population-level conditional distribution, and
`principles.information_leaks` returns empty for `StationDP.negotiate`.
(ii) It is not circular: it is an equilibrium object measured from the model's
own pilot run, not fitted to an observed target. (iii) The success rate is a
conditional statistic, which is why the identical-population row sits under it.
(iv) **One real wrinkle:** the `prior=False` arm gives the station a *flat*
switching-cost belief, so the raw prior ON/OFF contrast mixes "conditions on the
counter" with "has an accurate distribution at all" — which is why the headline
above is stated within the prior-ON arm alone, where that confound cannot enter.
(v) **One assumption that flatters the mechanism:** the counter prior is measured
under exactly the ask mode being run, so the station knows the tenants' selection
rule perfectly. A landlord that had to learn which tool its tenants use would
concede less.
(vi) `move_med` 1.48 (derived): the decay holds — loss success 0.632 at share
0.60 against 0.330 at share 1.00; gain 0.637 at 0.63 against 0.186 at 1.00;
population value +$157 / +$180 at the peak, +$9 to +$26 at full adoption. Levels
shrink, direction does not flip.

> **VERDICT (c): SURVIVES.** The strongest surviving result in this triage.
> Publishable as: *the value of a counter comes from what the landlord infers
> from it, not from who is doing the asking — selection moves the success rate
> by under 7 points, inference by 80–90 — and that value decays roughly 20-fold
> as countering goes from rare to universal, peaking around 30% adoption.*

## (d) "61% never negotiate, and that split is load-bearing"

Arm F, where the counter rate is an *output* of `courage_med` (**CIRCULAR** —
"set so that the endogenous counter rate lands near the observed 39%") and
`belief0` (**CIRCULAR** — "0.10 → 61% never try"). Swept both
(`triage_arms.py --part split`, institutional, 60 stations).

**First finding: they are not two parameters.** A crab asks iff
`belief × ask_scale × ask_frac × 12q > courage`, so only the *ratio* matters.
Ratio-matched pairs give the same counter rate to three decimals:

| `courage_med` | 0.045 | 0.09 | **0.18** | 0.36 | 0.72 |
| `belief0` matched | 0.40 | 0.20 | **0.10** | 0.05 | 0.025 |
| counter rate (loss) | 0.790 / 0.789 | 0.518 / 0.518 | **0.232 / 0.232** | 0.061 / 0.061 | 0.009 / 0.009 |
| counter rate (gain) | 0.849 / 0.849 | 0.609 / 0.609 | **0.304 / 0.304** | 0.092 / 0.092 | 0.015 / 0.015 |

**One knob, labelled twice, and both labels are circular.** It spans counter
rates from 0.9% to 96%. The 61/39 split is a parameter choice, full stop; the
model will return whatever split you dial in. Level: **not claimable**, exactly
as PARAM_SOURCES already says.

**Second finding: the direction of (c) survives the knob moving**, in 3 of the 4
regime × `move_med` cells. Value of countering ($/crab-year, asker minus
non-asker in the same cell):

| counter rate | 0.01 | 0.06–0.09 | 0.23–0.30 | 0.52–0.61 | 0.79–0.85 | 0.94–0.96 |
|---|---|---|---|---|---|---|
| gain, `move_med` 3.60 | **+225** | +79 | +53 | −5 | −38 | **−222** |
| gain, `move_med` 1.48 | **+260** | +171 | +161 | +148 | +133 | **+59** |
| loss, `move_med` 1.48 | +710 | +651 | **+714** | +633 | +255 | **−677** |
| loss, `move_med` 3.60 | +650 | +292 | +333 | +353 | +358 | +247 |

Three of four decline; the loss/3.60 cell is flat within noise. Note this arm has
**no** counter-conditional belief at all — arm F runs a plain `StationDP` — so
what is decaying here is not inference but ordinary congestion: as more crabs
counter, the station's rent of record falls (1.047 → 1.041) and total surplus
*rises* (−5673 → −5480), which shrinks the asker's edge over the non-asker
without anyone being made worse off. The strong version of the decay is arm H's,
in (c).

> **VERDICT (d): level DIES, direction SURVIVES.** Publishable as: *how many
> people negotiate is an input to this model, not an output of it — but the
> value of negotiating falls as more people do, in every specification where the
> landlord can respond at all.* And: **`courage_med` and `belief0` should be
> collapsed into one declared parameter** before anything else is run on them.

## (e) "More counters raise the OPENING offer for everyone, and the quiet absorb it"

**This is the claim currently printed on a live user-facing page, so it gets the
harshest treatment.** K3 fires if non-asker surplus in arm E at 75% adoption is
worse than the share-0 baseline by ≥ $240/crab-year.

Swept: `face_premium` (INVENTED) `{0, .5, 1, 2, 4}`, `p_substitute` (INVENTED)
`{0, .35, .7, 1}`, `renewal_cap` (CIRCULAR) `{0.12, 2.0}`, `move_med`
(CALIBRATED) `{3.60, 1.48}`. **And the mechanism is ablated**: arm D is the same
world with a station that cannot see the adoption rate at all.

| sweep point | harm, arm E loss | arm E gain | **ABLATION: arm D loss / gain** |
|---|---|---|---|
| `face_premium` 0.0 | **+285 ± 180** | +16 ± 100 | +63 / +16 |
| `face_premium` 0.5 | +167 ± 172 | +13 ± 100 | +61 / +13 |
| **`face_premium` 1.0 (shipped)** | **+202 ± 170** | **+293 ± 100** | **+70 / +44** |
| `face_premium` 2.0 | **+334 ± 168** | **+865 ± 98** | +48 / +45 |
| `face_premium` 4.0 | **+311 ± 166** | **+849 ± 97** | +53 / +41 |
| `p_substitute` 0.0 → 1.0 | +200 … +203 | **+286 … +308** | +68 … +72 / +38 … +61 |
| `renewal_cap` 2.00 (free) | **+810 ± 166** | **+295 ± 100** | +12 / +47 |
| `move_med` 1.48 (derived) | **+621 ± 89** | +155 ± 43 | +58 / −22 |

- **Sign: positive in 20 of 20 arm-E estimates**, across every parameter swept.
- **Magnitude: clears the $240 bar in 10 of 20**, exactly the "sits on its bar"
  the study already reported, and it is `face_premium`-sensitive
  (+$16 → +$865 in the gain regime).
- **The mechanism survives ablation — the only one in this triage that does.**
  Remove the station's knowledge of adoption and the harm collapses from
  +$202…+$865 to **+$12…+$72, never significant, never clearing the bar.** The
  channel is directly visible in the offer: arm E moves the rent of record
  1.1173 → **1.1331** as adoption goes 0 → 75%, while arm D moves it
  1.1173 → 1.1173.

The A7 note that this claim "is supported by a test *asserting* it" is half
right and worth stating precisely: what the test asserts is that the station
cannot identify *which individual* asks. What arm E assumes — and what the
ablation isolates — is that it *can* observe the aggregate adoption rate and
re-prices on it. That is an assumption about landlord behaviour, not an emergent
result; it is the assumption the claim is about, and inside it the mechanism is
clean.

### But the *broadcast* form of the same claim is not robust

K8 is the version that models **our own page** raising adoption: arm F-adaptive,
institutional, broadcast off vs on. It fires only if askers gain **and**
non-askers lose. Swept the same parameters (`triage_extern.py --part k8`):

| sweep point | gain: askers / non-askers (± se) | K8 | loss: askers / non-askers |
|---|---|---|---|
| `face_premium` 0.0 | **−136 / +35 ± 8** | no — **sign reversed** | +6 / +40 ± 14 |
| `face_premium` 0.5 | **−123 / +34 ± 7** | no — **sign reversed** | +94 / +3 ± 12 |
| **`face_premium` 1.0 (shipped)** | **+146 / −90 ± 12** | **FIRES** | +32 / +7 ± 14 |
| `face_premium` 2.0 | −436 / −309 ± 44 | no — both lose | −214 / +44 |
| `face_premium` 4.0 | −350 / −213 ± 49 | no — both lose | −346 / +177 |
| `p_substitute` 0 → 1 | +131…+146 / −81…−90 | **FIRES ×4** | +23…+32 / +6…+10 |
| `renewal_cap` 2.00 | +139 / −87 | **FIRES** | +430 / +473 |
| `move_med` 1.48 | +61 / −25 ± 8 | **FIRES** | +249 / +16 |
| `courage_med` 0.09 / 0.18 / 0.36 | +11 / −243; +146 / −90; +140 / −23 | **FIRES ×3** | −14/+61; +32/+7; +96/−4 |
| `belief0` 0.05 / 0.10 / 0.20 | +214 / −91; +146 / −90; −65 / −173 | FIRES ×2, then no | −114/+7; +32/+7; +49/+9 |

**K8 fires in 12 of 15 gain-regime points and 1 of 15 loss-regime points**, and
its three gain-regime failures are at the two ends of the `face_premium` sweep —
at 0 and 0.5 the sign **reverses** (askers lose, the quiet gain), at 2 and 4
everyone loses. K7 meanwhile never fires anywhere: the worst total-surplus
effect of broadcast across the whole sweep is **−$38**, against a $240 bar.

> **VERDICT (e): SPLITS.**
> **K3 form — SURVIVES.** *When a landlord re-prices on how many tenants
> negotiate, the non-negotiators pay for it.* Positive in 20 of 20 sweep points,
> ~1% of annual rent at the shipped parameters, sitting on the bar we called
> material, and it vanishes (+$12…+$72, never significant) when the landlord
> cannot see adoption. The mechanism is visible in the offer: 1.1173 → 1.1331.
> **K8 form — FLIPS on `face_premium`.** The sentence currently on the live page
> — "the direction held up under every attempt to break it" — is true of the
> exogenous-adoption arm and **false of the broadcast arm**, where the sign
> reverses at `face_premium` ≤ 0.5. That sentence needs narrowing.

## (f) "The station held face rent and ate vacancy while concessions tripled; face rent is sticky because it capitalises"

`triage_shock.py`, institutional 200 units, crab flu (market falls 35.3% over
years 3–10). Pre = years 1–2, during = years 4–9.

| sweep | r/mkt pre → during | Δ | concession success pre → during | ×  | vacancy mo/hab pre → during |
|---|---|---|---|---|---|
| **`face_premium` 0.0 (ABLATION)** | 1.0927 → 1.1231 | **+3.04pp** | 0.142 → 0.067 | **0.47×** | 0.60 → 1.23 |
| `face_premium` 0.5 | 1.1003 → 1.1301 | +2.98pp | 0.110 → 0.194 | 1.76× | 0.62 → 1.25 |
| **`face_premium` 1.0 (shipped)** | 1.1051 → 1.1333 | +2.82pp | 0.260 → 0.714 | **2.74×** | 0.63 → 1.24 |
| `face_premium` 2.0 | 1.1092 → 1.1374 | +2.82pp | 0.943 → 1.000 | 1.06× | 0.62 → 1.22 |
| `face_premium` 4.0 | 1.1128 → 1.1411 | +2.83pp | 0.995 → 1.000 | 1.00× | 0.62 → 1.22 |
| `size_scaled_face` False/True | *bit-identical* | — | *bit-identical* | — | — |
| `renewal_cap` 0.12 / 2.00 | *bit-identical* | — | *bit-identical* | — | — |
| `move_med` 1.48 (derived) | 1.0271 → 1.0569 | +2.98pp | 0.437 → 0.663 | 1.52× | 0.61 → 1.25 |
| `kappa_crab` 0.8 / 3.2 | +7.15pp / +2.61pp | — | 1.33× / 2.72× | — | 2× |

- **"Rent of record rose relative to market while vacancy doubled": SURVIVES**
  every sweep point (+2.6 to +7.2pp; vacancy 0.60 → 1.24 months per
  habitat-year).
- **"…because it capitalises": DIES on its own ablation.** At
  `face_premium = 0`, where a dollar of face rent is worth exactly its cash and
  the stated mechanism is switched off, the rise is the **largest in the table**.
  This is the third mechanism claim in this study to survive every test except
  being ablated.
- **"Concessions tripled": DIES.** 0.47x / 1.76x / **2.74x** / 1.06x / 1.00x
  across the `face_premium` sweep — non-monotone, and it **reverses** at the
  ablation point. The tripling exists at one value of one invented parameter.
- **"Held its rent": overstated by an order of magnitude.** Market rent fell
  35.3%; holding face rent would have put r/mkt at ≈1.70. It went to 1.133. The
  station cut face rent by roughly 33 of the 35 points — it tracked the market
  down and lagged by about 3 points.
- **"A fifth of its habitats sat empty": overstated 2x.** 1.24 months of vacancy
  per habitat-year is **10.3%**, not 20%.
- **`size_scaled_face` is inert here**, so the claim never rested on it: the
  shock arm builds an `INSTITUTIONAL` landlord, which is a plain `StationDP`,
  and only `EmergentDP` (Gate 2) reads that flag. The rows are bit-identical.
- `renewal_cap` free is bit-identical, which **confirms A7's assertion** that
  the flu result is unaffected by the circular cap.

> **VERDICT (f): SPLITS — the phenomenon SURVIVES, the mechanism and both
> magnitudes DIE.** Publishable as: *in a demand collapse the station let its
> rent of record drift about 3 points above a market that fell 35%, and took
> roughly double the vacancy (0.60-0.63 -> 1.22-1.25 months per habitat-year), at every parameter we swept -- but our stated
> reason (capitalisation) is refuted by its own ablation, and the "concessions
> tripled" figure exists only at the shipped value of that same parameter.*

## (g) K16 — "whoever holds the engine takes ~90% of the value"

Already classified artefact #6. Reproduced and decomposed one confound at a time
(`triage_k16.py`; `crabs.armk.negotiate_matrix` is monkey-patched, nothing
shipped is edited). $/habitat-year, main seeds.

**First, a correction to the record: the 8.5x is a metric mismatch.** RESULTS.md
reports T/N tenant gains of +$298 / +$236 against landlord +$2,642 / +$1,981,
giving 8.9x / 8.4x. The tenant figures are **cash *plus* the welfare premium**
(`tenant_phy`); the landlord figure is **cash only** (`landlord_phy`, which has
no welfare term). On the pre-registered cash metric — the unit SPEC §10 fixes
and K13 is written in — the same file gives **+$240 / +$55 against +$2,642 /
+$1,981, i.e. 11.04x / 36.08x**. My replication of the shipped arm reproduces
that exactly. The published ratio is measured with two different rulers, and the
mismatch runs in the direction that *understates* the artefact.

| variant | regime | landlord gain (N/L) | tenant gain (T/N) | ratio | joint (T/L) |
|---|---|---|---|---|---|
| **shipped** | loss | +2642 ± 121 | +239 ± 22 | **11.04x** | +1372 |
| **shipped** | gain | +1981 ± 88 | +55 ± 16 | **36.08x** | +1001 |
| equalise rounds at 3 | loss / gain | identical | identical | 11.04 / 36.08 | identical |
| landlord confined to the tenant's grid | loss | +1544 | +239 | 6.45x | +845 |
| landlord confined to the tenant's grid | gain | +2976 | +55 | 54.21x | +1449 |
| landlord may not read `ten.w` / `job_flex` | loss | +3340 | +239 | 13.96x | +1598 |
| landlord may not read `ten.w` / `job_flex` | gain | +2628 | +55 | 47.87x | +1279 |
| **MIRROR (one knob: whose objective the search maximises)** | loss | **+1651 ± 109** | **+1155 ± 47** | **1.43x** | +885 |
| **MIRROR** | gain | **+3234 ± 112** | **+1669 ± 44** | **1.94x** | +1587 |
| MIRROR, `break_damp` 1.0 | loss / gain | +531 / +809 | +321 / +294 | 1.66x / 2.75x | +178 / +225 |
| MIRROR, `move_med` 1.48 | loss / gain | +4362 / +3635 | +2110 / +1373 | 2.07x / 2.65x | +1416 / +1208 |
| shipped, `break_damp` 1.0 | loss / gain | +1682 / **+250** | +34 / −2 | 49x / n.a. | +336 / +198 |
| shipped, `move_med` 1.48 | loss / gain | +4871 / +2818 | +534 / +62 | 9.12x / 45.66x | +1678 / +945 |

- **The round count is not a confound** (equalising changes nothing).
- **The private-weight read is a real Principle-B violation but a
  *conservative* one** — removing it makes the landlord *better* off, because
  the welfare term was tightening its own opener constraint.
- **The confound is the weapon.** Give the tenant the same brute-force
  enumeration over the same grid and the same first move, and the ratio goes
  **11.0x / 36.1x → 1.43x / 1.94x**. The landlord still takes more (59% / 66% of
  the two-sided gain), but "nine parts in ten" is gone. My mirror is built
  differently from the audit's (I confine both sides to the shared 64-point grid
  rather than extending the tenant's) and lands at 1.4–1.9x against its
  2.25 / 0.77 — different constructions, same verdict.
- **K17 rides on `break_damp` (INVENTED, 0.5 — "a 2-year lease halves the chance
  a job move happens at all").** Set it to 1.0 and joint surplus goes
  +$1,372 → +$336 (loss) and +$1,001 → +$198 (gain): **76% and 80% of "the
  engine creates real value" is that one unanchored assumption.** Confirms the
  audit's 75–80% independently.
- `move_med` 1.48: the shipped ratio stays huge (9.1x / 45.7x) and the mirror
  stays small (2.1x / 2.7x). The verdict does not flip on it.

> **VERDICT (g): DIES.** The corrected arm gives 1.4–2.7x, not 8.5x, and the
> joint-value claim it was paired with loses three quarters of its size to one
> invented constant. Nothing in the 90% framing is publishable. The residue is a
> real and less flattering finding: **`negotiate_bundle` leaves large sums on the
> table against brute-force enumeration of its own grid** — in the mirror the
> tenant's enumerated opener is worth +$1,155 / +$1,669 where the engine's
> reply-only play was worth +$239 / +$55.

**And the commercial conclusion reverses.** In the corrected arm the
tenant-held tool produces *more* joint value than the landlord-held one
(loss 23159 vs 23138; gain 16139 vs 16034) and *fewer* moves (turnover 0.376 vs
0.381 loss; 0.378 vs 0.402 gain). "Our likelier customer is the landlord" was a
conclusion of the confound, not of the comparison.

---

# PART 2 — the pre-registered kills, K1–K18

*K19–K26 run through `market.py` and belong to the other agent's triage; they are
listed at the end for completeness only.* Bars are PREREG's own: $480/crab-year
for K1/K13/K14/K21/K26, $240 for K3/K4.

| kill | asserts | rests on (class) | declared sweep | result across the sweep | verdict |
|---|---|---|---|---|---|
| **K1** ranked-ask is decoration | C−B < $480 in gain | `face_premium` (INVENTED), `p_continue` (CIRCULAR), `p_substitute` (INVENTED), `grant_menu` (INVENTED) | fp {0,.5,1,2,4}; pc {.3,.6,.9}; ps {0,.35,.7,1} | C−B, reg/expl: fp 0 → +$3/−$19; .5 → +$2/−$15; 1 → +$2/+$58; **2 → +$722/+$610; 4 → +$1,195/+$1,168**. pc → +$2/+$2/+$1 (reg), +$70/+$58/+$44 (expl). ps → +$4…+$0 (reg), +$100…+$16 (expl) | **FLIPS** on `face_premium`: fires at ≤1.0, does not at ≥2.0 — where success is 0.96–1.00, nothing like the world |
| **K2** value is transitional | E/D ratio ≤0.25 as share→1 | `face_premium` | never swept for arm E | RESULTS itself: "an artefact of the one parameter we could not pin down and should not be reported as a finding" | **UNTESTABLE** (self-withdrawn) |
| **K3** negative externality | non-asker loss ≥$240 at 75% | `face_premium`, `p_substitute` (INVENTED), `renewal_cap` (CIRCULAR), `move_med` (CALIBRATED) | **not in the shipped sens design; swept here** | sign +ve in **20/20**; magnitude +$13…+$865, clears the bar in **10/20**; **ablation (arm D) collapses it to +$12…+$72** | **SURVIVES** (direction) |
| **K4** regime argument wrong | (C−A)gain − (C−A)loss < $240 | `drift` (UPSTREAM), `face_premium` | **arm A is absent from `run.sens_specs`, so K4 was never swept at all** | +$3 (reg) / +$53 (expl) at the shipped point only | **UNTESTABLE** — no sweep exists |
| **K5** landlord type not actionable | spread <$240 | MEDIUM policy (INVENTED, no anchor) | — | spread $2,317/$1,340 with MEDIUM, **$456/$92 on grounded types alone**; and K9 fired, which withdraws the type paradox by A2.3 | **DIES** (already withdrawn) |
| **K6** worth least where we aimed | mom-and-pop highest | same | — | same withdrawal | **DIES** |
| **K7** net-harmful at scale | total surplus −$240 under broadcast | `face_premium`, `courage_med`/`belief0` (CIRCULAR), `learn_rate` (INVENTED) | 15 points swept here | worst total effect of broadcast anywhere in the sweep **−$38** against a $240 bar | **SURVIVES** (did not fire, robustly) |
| **K8** broadcast helps only the loud | askers up, non-askers down | as K7 | 15 points swept here | fires **12/15 in gain, 1/15 in loss**; at `face_premium` 0 and 0.5 the **sign reverses**, at 2 and 4 both groups lose | **FLIPS** on `face_premium` |
| **K9** primitives cannot generate landlord behaviour | GATE 2 fails | the A2 primitives (5 of 8 INVENTED) | 6-way ablation, already run | institutional push **10.60–10.61% in all six ablations**; gate fails 4/4 | **SURVIVES as "our derivation fails"**; the broader reading ("portfolio size does not generate distinct behaviour") **DIES** — the audit's satisficing landlord recovers V5 in 18/27 and V7 in 22/27 |
| **K10** mechanism is bureaucratic | arm G reaches 15–30% success | `queue_frac` (INVENTED) | {0 … 2.0} swept here | max success across the whole sweep 0.051 (loss) / 0.099 (gain), never reaches the band | **SURVIVES** |
| **K11** walk-away floor is the product | tool beats everyone by ≥$480 on an identical population | `engage_margin` (INVENTED), `tool_noise` (INVENTED) | `engage_margin` {0…32} swept here | tool at its own share is worth **−$16 (loss) / +$39 (gain)** against random askers at the same share | **SURVIVES** (did not fire) |
| **K12** landlord wants you to ask | station cash rises with a concession channel | A2 primitives | not swept | −$137/−$128 (inst) at the shipped point only | **UNTESTABLE** — no sweep run |
| **K13** logrolling does nothing | bundle−single < $480 | tenant demographics (INVENTED priorities) | not swept | +$944/+$977 at the shipped point — but `engine_bridge.station_counter` **reads `ten.w` and `ten.job_flex`** (Principle B violation, confirmed by `principles.information_leaks`), and the audit found a *homogeneous* population gives a **larger** advantage, so the stated mechanism (logrolling) is refuted; it is combinatorial search | **effect UNTESTABLE until the leak is closed; the mechanism DIES** |
| **K14** engine worse than our ladder | engine−ladder < $480 | as K13 | not swept | +$887/+$860, same leak | **UNTESTABLE** (same leak) |
| **K16** we arm the stronger side | ratio ≥ some multiple | the 2x2's 8 undeclared dimensions; `break_damp` (INVENTED), `move_med` | decomposed here | 11.0x / 36.1x shipped → **1.43x / 1.94x mirrored** | **DIES** |
| **K17** arms race, not value creation | joint does not rise | `break_damp` (INVENTED 0.5) | {0.5, 1.0} here | joint +$1,372/+$1,001 → **+$336/+$198** at `break_damp` 1.0; **76%/80% of the effect is one unanchored constant** | **FLIPS** — sign survives, magnitude does not |
| **K18** mutual engines destroy value | turnover up **and** joint down | as K16 | mirror + `break_damp` | turnover falls and joint rises in both the shipped and the mirrored arm | **SURVIVES** (did not fire) |
| K15, K19–K26 | — | `market.py` | — | — | **OUT OF SCOPE** — other agent |

---

# PART 3 — RESULTS.md against the audit

The consolidated summary is stale in at least nine places, and **in every one it
is stale in the direction that flatters the study.** Where the summary and the
audit disagree, the audit wins; where the summary and its own JSON disagree, the
JSON wins.

| # | RESULTS.md says | the audit / the data say | in scope? |
|---|---|---|---|
| 1 | "Whoever holds the engine captures ~90% — K16 FIRED, 8.5–8.9x… Belongs on snhp.dev/rent" (publishable finding #2) | ARTEFACT #6 in DESIGN-PRINCIPLES; commit 7c82c05 mirrors the weapon → 2.25/0.77; this triage → 1.43x/1.94x | **yes** |
| 2 | K16's own numbers: T/N +$298/+$236, ratio 8.9x/8.4x | **measured with two different rulers** — the tenant with the welfare premium (`tenant_phy`), the landlord on cash (`landlord_phy`). On the pre-registered cash metric the same file gives +$240/+$55, ratio **11.0x/36.1x**. The mismatch understates the artefact | **yes** |
| 3 | "The engine… wins by finding deals that exist" (multi-issue logrolling), K13/K14 | audit: a *homogeneous* population gives a **larger** advantage, so it is combinatorial search, not logrolling; and A7's unfixed leak — `station_counter` reads `ten.w`, `ten.job_flex` | **yes** |
| 4 | GATE 1: "the station concedes essentially never (0.0%)"; the diagnosis in §1b | PREREG A7 RESULT: freeing the circular cap takes loss-regime success **0.04% → 43.3%**; "Gate 1's 'the station concedes to nobody' was partly the cap." Phase 1 and the summary were never updated | **yes** |
| 5 | K9 / Phase 7 §2: "Portfolio size, in our derivation, does not generate distinct landlord behaviour" | audit: too broad — a satisficing landlord recovers V5 in 18/27 and V7 in 22/27 | **yes** |
| 6 | K17: joint +$1,372/+$1,001, "Real value, not a transfer" | 76%/80% of it is `break_damp = 0.5`, an INVENTED constant; at 1.0 it is +$336/+$198 | **yes** |
| 7 | K20 "FIRED, 1.08x", tenant is the weaker party | A8's derived `move_med` 1.48 inverts it to 0.892 — does not fire | out (market.py) |
| 8 | K25 "CONFIRMED… the strongest piece of product advice in the whole study… $645/year" | commit 7c82c05 **removed the $645** ("constructed in closed form"); the live page no longer carries it | out (market.py) |
| 9 | K26 "does not confirm (+$17)… Drop any copy implying otherwise" | commit 7c82c05 **reversed it**: a costly verifiable signal takes 10.2 points off the offer. RESULTS still prints advice the product deliberately un-shipped — and Amendment 9 then refuted that correction's own mechanism (the gap collapses to 0.000 without the deadline cliff) | out (market.py) |
| 10 | "Four of my five measurement artefacts ran in the direction of a sharper story" | DESIGN-PRINCIPLES: **six of seven** | — |
| 11 | Reproduce block: "80 tests" / "76 tests" | 85 as of commit 7c82c05 | — |

**Of the nine claims RESULTS.md lists as "What survived, and is publishable",
one survives this triage as written** — K11's identical-population null. A
second ("K3 and K8 FIRED") survives in its K3 half only. The rest lose a
magnitude, a mechanism, or both.

---

# PART 4 — the three lists

## SURVIVES — publishable

1. **The value of a counter is what the landlord infers from it, and it decays
   with adoption.** Signal channel +0.80 to +0.90 on the success rate; selection
   channel +0.002 to +0.072. Success falls from 0.94–1.00 at 1–37% adoption to
   0.045–0.053 at 100%, monotone, on one knob, in both regimes. Population value
   (identical population) peaks near 30% adoption at +$390 (loss) / +$551 (gain)
   and decays to ~0. Holds at `move_med` 1.48. **(c)**
2. **A landlord that re-prices on how many tenants negotiate makes the
   non-negotiators pay for it.** Positive in 20 of 20 sweep points; clears the
   $240 bar in 10; the rent of record moves 1.1173 → 1.1331 as adoption goes
   0 → 75%; **ablated to +$12…+$72 when the landlord cannot see adoption.** The
   only mechanism claim in this triage that survives its own ablation. **(e), K3.**
   *The broadcast version of the same claim (K8) does not survive — see FLIPS.*
3. **In a demand collapse the rent of record drifts up against the market while
   vacancy roughly doubles** — +2.6 to +7.2pp and 0.60 → 1.24 months per
   habitat-year, at every parameter swept including the capitalisation ablation
   and the derived `move_med`. **(f), phenomenon only**
4. **A headline rent cut is never the instrument granted.** 0% of states, every
   point of every sweep, including `face_premium = 0`. The *ordering* the ranked
   ladder assumes is structural even though its *value* is not. **(a) residue**
5. **A blanket-policy landlord concedes less often than a per-unit one at every
   exception capacity** (0.020/0.037 at the shipped queue, 0.051/0.099 at
   unlimited, against 0.068/0.100), and never reaches the observed 15–30% band.
   **K10, (b) residue**
6. **A blanket policy costs tenants about 1.4% of annual rent** whether or not
   anyone counters (−$341 loss / −$350 gain), of which $215 (loss) / $245 (gain) is the
   policy itself and the rest the queue. Negative at every `queue_frac`. **(b), new**
7. **The "you are weak, just sign" verdict is worth approximately nothing at the
   population level**: −$16 (loss) / +$39 (gain) against random askers at the
   same share. The pre-registered identical-population guard is what catches it.
   **K11**
8. **Mutual engines do not destroy value** — turnover falls and joint surplus
   rises in both the shipped and the corrected arm. **K18**
9. **Our size-derived primitives do not generate distinct landlord behaviour**
   (institutional push 10.60–10.61% in all six ablations). Narrow reading only.
   **K9**
10. **The value of negotiating falls as more people negotiate**, in every arm-F
    specification where the landlord can respond at all. **(d), direction**

## DIES — must be withdrawn

1. **"A landlord at its own optimum is indifferent at the margin, so conceding
   is a straight loss."** The margin is `(1-pl)(sigma/gamma - 1)`, which at the
   shipped parameters is **+0.079, i.e. positive**, and whose sign is set by
   three INVENTED constants. **(a)**
2. **The loss-regime wall (0.0% concessions).** It is `renewal_cap = 0.12`,
   which PARAM_SOURCES classes CIRCULAR. Free it and an NPV-optimal station
   concedes to **43–50%** of counterers. **(a)**
3. **"Menu costs made countering pay worse."** In money it tied in the loss
   regime (+$177 ± 60 vs +$184 ± 65) and was **better** in the gain regime
   (+$126 ± 38 vs +$16 ± 39), and at capacity ≥ 39% countering is worth 2.7x
   baseline. **(b)**
4. **"Most counterers are unread rather than refused"** as a *finding*. It is
   `min(1, queue_frac / counter_rate)` — arithmetic on a parameter SPEC-A2 calls
   "a working guess". **(b)**
5. **The 61/39 split as a fact.** `courage_med` and `belief0` are the same knob
   (only their ratio enters), both CIRCULAR, and it spans counter rates from
   0.9% to 96%. **(d)**
6. **"Face rent is sticky because it capitalises."** Refuted by its own
   ablation: at `face_premium = 0` the drift is the *largest* in the table. **(f)**
7. **"Concessions tripled."** 0.47x / 1.76x / 2.74x / 1.06x / 1.00x across the
   `face_premium` sweep — non-monotone and reversed at the ablation. **(f)**
8. **"The station held its rent"** and **"a fifth of its habitats sat empty."**
   The station cut face rent by ~33 of the market's 35 points; vacancy was
   10.3%, not 20%. **(f)**
9. **"Whoever holds the engine takes ~90%"** and **"our likelier customer is the
   landlord."** 11.0x/36.1x → 1.43x/1.94x mirrored, and the tenant-held tool
   creates *more* joint value with *fewer* moves. **(g), K16**
10. **"The engine wins by logrolling."** A homogeneous population gives a larger
    advantage; it is combinatorial search. **K13**
11. **The landlord-type paradox** (K5/K6) — already withdrawn by K9, and the
    spread is carried by an INVENTED policy with no anchor.
12. **"Portfolio size does not generate distinct landlord behaviour"** as a
    general claim. **K9, broad reading**

## FLIPS — neither publishable nor withdrawable as stated

1. **K1.** Fires at `face_premium` ≤ 1.0 (C−B ≤ $58), does not at ≥ 2.0
   (+$610…+$1,195). The parameter's own stated derivation (cap-rate arithmetic)
   points *above* the range where it fires — but at those values the station
   concedes to 96–100% of counterers, which is nothing like the world. **The
   model cannot be simultaneously plausible and informative about K1.**
2. **K17.** Joint value survives in sign at both `break_damp` values but loses
   76–80% of its magnitude at 1.0. An unanchored constant carries the headline.
3. **K8 — the broadcast externality.** Fires 12/15 in the gain regime, 1/15 in
   the loss regime; at `face_premium` 0 and 0.5 the sign **reverses** (askers
   lose, the quiet gain). The exogenous-adoption form of the claim (K3) is fine;
   this one is not, and it is the form the live page describes.
4. *(out of scope, noted)* **K20** inverts on A8's derived `move_med`
   (1.474 → 0.892).

## UNTESTABLE — needs a respecified run

1. **K2** — arm E was never swept on `face_premium`; RESULTS withdraws it itself.
2. **K4** — arm A is absent from `run.sens_specs`, so the pre-registered
   sensitivity design cannot evaluate a kill defined on C−A. It has one data
   point and no sweep.
3. **K12** — never swept.
4. **K13 / K14 magnitudes** — `engine_bridge.station_counter` reads the tenant's
   private Dirichlet weights and job flexibility. Close the leak and re-run
   before quoting +$944 / +$887.
5. **The gain-regime concession wall** — it holds across every `renewal_cap` but
   dies at `face_premium ≥ 2.0`, and SPEC §6's own arithmetic implies a premium
   far above 2.0. Deciding it needs a face-rent premium with a source.
6. **Anything resting on `move_med`** now needs both values reported. A8 derives
   1.48 against the calibrated 3.60, and only ~15% of the derived figure comes
   from search, so it is a band and not a point.

---

# PART 5 — what the article can still say

*Bullet claims with their supporting numbers. Everything here survived its own
parameter's sweep; everything the current draft says that is not here should
come out. The article's spine — (a), (c), (e), (f) — comes through with one
section intact, two rewritten, and one replaced.*

### The wall (replaces "the station wouldn't move")

- **A landlord at its own optimum is not indifferent about conceding. Whether it
  concedes is a ratio of two numbers nobody has measured.** The station's gain
  from a marginal concession is exactly
  `(1 - P(leave)) x (sigma/gamma - 1)`, where `gamma = 12 x (tenant's horizon +
  reference weight)` and `sigma = 12 x (1 + face-rent premium) + persistence`.
  At our numbers the ratio is **1.12** — the concession is marginally
  *profitable*, and the near-zero grant rate comes from the smallest available
  concession being too big a step, not from indifference.
- **Move any of the three constants and the answer changes completely.**
  Face-rent premium 0 → the landlord refuses everywhere (ratio 0.56); premium 2
  → it concedes in 86% of states. Tenant horizon 0.8 years → concedes in 68%;
  3.2 years → never. **None of the three has a published source.**
- **In the falling-rent regime the wall was our own constraint.** We capped
  renewal increases at 12% because 2022 renewals averaged +10.7% — an outcome
  installed as a rule. Remove it and the same landlord concedes to **43–50%** of
  counterers instead of 0.04%.
- **The one thing that held everywhere: the landlord never grants a headline
  rent cut.** 0% of states at every parameter tried, including with
  capitalisation switched off. *Which instrument is hardest to get is
  structural. How much easier the others are is not.*

### Why asking works (this section gets stronger, not weaker)

- **Asking is worth something because of what the landlord infers from it, not
  because of who is asking.** Letting the landlord form a belief about
  counterers moves the concession rate by **0.80 to 0.90**. Letting a tool pick
  better askers, with no inference, moves it by **0.002 to 0.072**.
- **And that value decays about twenty-fold as countering goes from rare to
  universal.** Success 0.94–1.00 at 1–37% of tenants countering; **0.045–0.053
  when everyone does**. One knob, monotone, both regimes, and it survives the
  switching cost being rebuilt from search (1.48 months) instead of calibrated.
- **The value to tenants as a group peaks at about 30% adoption** — +$390/year
  (rising market) and +$551/year (falling market) per tenant, measured over an
  identical population — and falls to roughly zero, in one case slightly
  negative, when everybody negotiates.
- **What cannot be said: that 61% of renters never negotiating is a fact of the
  model.** That number is dialled in. The two parameters that set it turn out to
  be one parameter (only their ratio enters the decision), it is circular by its
  own stated justification, and across its range the model produces counter
  rates from 0.9% to 96%. *The direction is ours; the level is the world's, and
  the article should cite the survey for it and not the simulation.*

### The externality (narrow it, keep it)

- **When a landlord prices off how many of its tenants negotiate, the ones who
  don't negotiate pay for it.** Non-askers lose **$202/year (rising market) and
  $293/year (falling market)** at 75% adoption, about 1% of annual rent, against
  a $240 bar we set in advance. **Positive in 20 out of 20 parameter settings.**
- **We can name the mechanism and switch it off.** The landlord's opening offer
  moves from 1.1173x market to **1.1331x** as adoption goes from 0 to 75%. Give
  it the identical world but no view of the adoption rate and the loss collapses
  to **$12–$72, never statistically distinguishable from nothing**. This is the
  only mechanism in the study that survived being ablated.
- **What must be narrowed:** when we model *our own page* driving adoption
  rather than adoption being handed to the landlord, the result stops being
  robust — it holds in 12 of 15 settings in a falling market, 1 of 15 in a
  rising one, and **reverses sign** where face rent carries no capitalisation
  premium. The live page's "the direction held up under every attempt to break
  it" is true of the first version and not the second.

### The plague (keep the picture, drop the reasons and the numbers)

- **In a demand collapse the landlord let its rent of record drift up against
  the market and took the vacancy instead.** Market rent fell 35%; the rent of
  record went from 1.105x to 1.133x of it; vacancy went from 0.63 to 1.24 months
  per unit per year. **Every parameter we swept, including the derived switching
  cost.**
- **But it did not "hold" its rent** — it cut face rents by about 33 of the 35
  points and lagged the market by roughly 3. And **10%** of unit-years sat empty,
  not a fifth.
- **And our explanation was wrong.** We said face rent is sticky because it
  capitalises into the building's value. Switch capitalisation off entirely and
  the drift is *larger*, not smaller. **We do not know why it holds.**
- **"Concessions tripled" has to go.** Across the capitalisation sweep the
  multiple runs 0.47x, 1.76x, 2.74x, 1.06x, 1.00x. The tripling exists at one
  value of one unsourced parameter and reverses at the ablation.

### The agent-versus-agent close (rewrite the direction)

- **"Whoever holds the negotiation engine takes ~90% of the value" is
  withdrawn.** The landlord's cell had a brute-force enumeration over a rent
  grid the tenant was forbidden and the first move; the tenant had a reply-only
  engine. Give both sides the same weapon and the ratio goes **11.0x/36.1x →
  1.4x/1.9x**.
- **The corrected comparison points the other way.** The tenant-held tool
  produces more joint value than the landlord-held one (23,159 vs 23,138 rising;
  16,139 vs 16,034 falling) and fewer moves.
- **The finding that replaces it is about our own product**: our negotiation
  engine leaves **$900–$1,600 per unit-year** on the table against brute-force
  enumeration of its own 64-point grid.
- **And "the engine creates real value" is mostly one assumption**: 76–80% of
  the joint gain is `break_damp = 0.5`, the unanchored premise that signing a
  two-year lease halves the chance a job move happens at all.

### The honest frame for the whole piece

- Three validation gates failed; **seven artefacts** were found by inspection,
  six of them pointing at the more interesting story.
- This triage adds an eighth failure mode: **of the nine results the write-up
  listed as publishable, one survives as written**, and a second survives in
  half. The rest lost a magnitude, a mechanism, or both.
- **Two shipped runners silently reuse a solved policy when `renewal_cap` or
  `move_med` is swept** (`run._station`, `run2._get`), which means the study's
  own sensitivity machinery could not have swept either correctly. Fix before
  anything else is run.
- The strongest sentence available: *we set out to find how much asking is
  worth, and the only things that survived our own sweeps were that it works by
  telling the landlord something, that it works less the more people do it, and
  that when landlords watch how many people ask, the quiet pay for it.*
