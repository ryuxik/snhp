# VINTAGE results — offer/1 and hazard/1 vs sticker/1

*One-of-one LES vintage store, 60 paired days per cell, 8 independent
replicate stores per cell, seed 20260710. Reproduce:
`python3 -m vintage.run --grid --days 60 --reps 8 --seed 20260710 --out vintage/results.json`.
Replicates are independent stores (fresh sourcing, browsers, learner state),
so CIs are plain paired t over rep-level totals (block=1).*

*NOTE (2026-07-10): `results.json` is now v2 — same seeds, five arms — after
the post-registration fixes recorded in the clearly-marked section at the
bottom of this file. The v1 tables below are preserved as the record; their
sticker/1 and hazard/1 rows reproduce exactly in v2, and their offer/1 rows
describe the PRE-fix offer/1.*

## Pre-registration (written before the first grid run)

**World.** Items are one-of-one: ~6/day sourced at $8–40 (log-uniform),
TRUE market value (appeal) = cost x 3.2 x lognormal(0, 0.40) — the sourcing
lottery. The tag is the owner's noisy guess of appeal: tag = appeal x
lognormal(0, sigma_tag), sigma_tag in {0.3, 0.6} — the miscalibration IS the
business. ~40 browsers/day; each connects with ~8% of the rack; a connecting
browser's WTP ~ lognormal(appeal, 0.25). Browsers see tags, never appeal.
Sold is gone; unsold ages at $0.06/item-day holding.

**Arms.**
* `sticker/1` — the cultural control: tag price, take it or leave it,
  −20% gut markdown every 30 unsold days.
* `offer/1` — make-an-offer: a connecting browser offers WTP x shading
  (grid {0.75, 0.9}, per-browser ±0.08); the engine accepts/counters against
  an event-consistent disagreement value: the value of WAITING for a future
  connecting browser, from a censoring-aware hazard learned off its own
  sales history (per-item appeal posterior + learned connection rate).
  One counter round; browsers accept a counter ≤ WTP x 1.0, and 25% walk
  out on being countered at all (haggle friction). Buffer: the engine's
  believed gain must clear max($2, 8% of tag).
* `hazard/1` — ablation for H-V3: the SAME learned per-item hazard computes
  weekly markdowns (PV-maximizing posted price, never raised, never above
  tag); no offers.

**Headline metric.** Net margin per 60-day store = revenue − COGS of sold −
holding cost, paired rep-level t CIs (n=8). Ending inventory (units, cost,
true appeal) reported alongside — a margin win that strips the rack is not
a win.

**H-V1.** offer/1's edge over sticker/1 comes overwhelmingly from
UNDER-tagged items (tag ≤ appeal/1.2) — capturing upside the sticker gave
away — more than from moving over-tagged (tag ≥ 1.2 x appeal) stale stock.
*Measured:* per-rep gross-margin Δ (offer − sticker) by item class (classes
are identical across arms — paired items). *Supported iff* mean
Δmargin_under > mean Δmargin_over, the under class contributes > 50% of the
total positive Δ, and the paired (under − over) CI excludes 0 in ≥ 3 of 4
cells. *A-priori design note, recorded for honesty:* the tag is a ceiling —
offers are capped at the ask and the engine cannot counter above its own
tag (discount-only, house invariant) — so the mechanism has NO channel to
recapture under-tag upside. We pre-register the folk claim anyway and expect
the data to arbitrate.

**H-V2.** The offer flow reduces median days-to-sale materially.
*Measured:* median days-to-sale over the fair-exposure cohort (items sourced
≥ 30 days before the horizon), unsold items CENSORED and counted (an arm
must not look fast by selling only its easy pieces). *Supported iff* the
cohort median falls ≥ 25% vs sticker/1 in ≥ 3 of 4 cells; secondary,
selection-proof read: mean paired Δ days over items sold in BOTH arms,
CI < 0.

**H-V3.** The engine's learned per-item hazard beats the fixed 30-day
markdown calendar even WITHOUT offers. *Measured:* hazard/1 − sticker/1 net
margin, rep-level CI. *Supported iff* the CI excludes 0 (positive) in both
sigma_tag = 0.6 cells (where miscalibration bites; hazard/1 and sticker/1
are shading-independent by construction, so the two shading columns
replicate them).

*(Everything below this line was written after the grid run.)*

---

## Headline: net margin Δ per 60-day store (arm − sticker/1)

| cell (σ_tag / shading) | sticker net | offer net | offer Δ | offer Δ CI95 | hazard net | hazard Δ | hazard Δ CI95 |
|---|---:|---:|---:|---|---:|---:|---|
| 0.3 / 0.75 | 17,281 | 16,979 | **−302** | [−524, −80] | 17,418 | +136 | [−47, +319] |
| 0.3 / 0.90 | 17,281 | 17,388 | +106 | [−48, +261] | 17,418 | +136 | [−47, +319] |
| 0.6 / 0.75 | 13,506 | 14,482 | **+976** | [+299, +1654] | 14,735 | **+1,229** | [+456, +2,002] |
| 0.6 / 0.90 | 13,506 | 14,876 | **+1,370** | [+697, +2,043] | 14,735 | **+1,229** | [+456, +2,002] |

(hazard/1 and sticker/1 never see an offer, so their rows replicate across
shading columns by construction.) Net margin = revenue − COGS of sold −
holding. Both engines also end with roughly HALF the sticker's leftover
rack at σ_tag = 0.6 (35–37 items vs 54.5) and lower holding cost.

## The mechanism (σ_tag = 0.6, shading 0.9 cell, per store)

offer/1 sells 317 units: 238 at the tag, 35 as accepted offers, 45 as
accepted counters — the negotiation channel is ~25% of units and carries
essentially ALL of the edge. Browsers lob 1,761 offers; the engine's floor
(waiting value + buffer) bounces 1,265 of the counters and 416 browsers
huff out mid-haggle. The margin decomposition (Δ vs sticker, paired items):

| class | n items | offer Δ margin | hazard Δ margin |
|---|---:|---:|---:|
| under-tagged | 134 | −0.3 | 0.0 |
| fair | 82 | −21 | 0.0 |
| over-tagged | 137 | **+1,358** | **+1,200** |

## Hypothesis verdicts

**H-V1 — REFUTED, decisively.** The edge comes from OVER-tagged stale
stock, not under-tagged upside; the pre-registered support criterion fails
in 4/4 cells and `under_minus_over` excludes zero the WRONG way in both
σ_tag = 0.6 cells (−1,027 [−1,702, −351] and −1,359 [−2,033, −684]). The
a-priori design note held: the tag is a ceiling. An under-tagged piece
sells at the ask within hours in EVERY arm — the upside was gone the moment
the tag was printed, and a discount-only offer flow has no channel to claw
it back (the under-class Δ is in fact a tiny NEGATIVE: occasionally the
engine accepts a shaded offer on a fresh gem the sticker would have sold at
tag the same week). Recovering under-tag value needs a mechanism that can
go ABOVE the tag — an auction or best-offer-over-ask — not this one.

**H-V2 — NOT SUPPORTED as pre-registered; the real effect is a tail
effect.** The primary criterion (cohort median days-to-sale down ≥ 25%)
fails trivially: the median is 0.0–0.2 days in every arm and cell — at 3.2
connecting browsers per item-day, the median piece sells the day it hits
the rack, and a median cannot fall 25% from zero. The selection-proof
secondary DOES hold everywhere: among items sold in both arms, offer/1 is
faster by 0.37 days (σ_tag = 0.3) and 0.85–0.91 days (σ_tag = 0.6), CIs
entirely below zero; share sold within 14 days rises 83.5% → 90%, and the
60-day leftover rack shrinks 54.5 → ~36 items. Velocity improves where it
matters (the stale tail) and nowhere else — which is not what "reduces
median days-to-sale materially" claimed.

**H-V3 — SUPPORTED, per the pre-registered criterion.** Computed markdowns
off the learned per-item hazard beat the 30-day gut calendar by +1,229
[+456, +2,002] in both σ_tag = 0.6 cells. At σ_tag = 0.3 the point estimate
is positive but the CI covers zero (+136 [−47, +319]) — when the gut is
mostly right there is little for the learner to fix, exactly as it should
be.

## Honest surprises

1. **The offer culture can COST money.** At good tagging + deep shading
   (0.3/0.75) offer/1 LOSES −302 [−524, −80]: ~244 countered browsers per
   store huff out (a quarter of them would have paid more than the
   counter), fair-tagged pieces leak haggled discounts (fair Δ −143 in that
   cell), and there isn't enough dead stock to win it back. A make-an-offer
   store is a bet that your own tags are wrong; if they aren't, the culture
   is pure friction.
2. **The ablation nearly matches the headline mechanism.** hazard/1
   (repricing only, no negotiation) captures most of the recoverable value
   and BEATS offer/1 at deep shading (+1,229 vs +976). offer/1 out-earns it
   only when browsers shade lightly (0.9) — the negotiation channel's
   premium over plain repricing is mostly the buyers' generosity, not the
   engine's cleverness. (Rhymes with the arena finding: the mechanism's
   edge keeps turning out to be smaller than the folk story once the
   control is competent.)
3. **The liquidation lens cuts the win down honestly.** Credit leftover
   inventory at COST and the σ_tag = 0.6 wins stand (offer +587/+1,003,
   hazard +901, CIs ≥ 0). Credit it at FULL true market value — pretend the
   rack is instantly liquid — and every edge collapses to noise (offer +53
   [−235, +341] at 0.6/0.9) or goes significantly negative at σ_tag = 0.3
   (offer −322, hazard −196). A large share of both engines' margin edge is
   converting illiquid rack into cash sooner. That is a real win only
   because holding is costly and appeal is not instantly realizable — which
   is the premise of the world, but say it plainly.

## Caveats (attack here)

* **Demand-rich world.** 40 browsers x 8% connection = 3.2 connecting
  browsers per item-day; fairly-tagged pieces sell same-day and the rack's
  steady state is adversely selected residue. All effects live in that
  residue. A slower store (fewer connections) would shift more weight onto
  the engines' patience math — untested here.
* **The sticker's patience is strong by construction:** with a lognormal
  WTP tail and ~200 connectors over 60 days, someone eventually overpays
  for over-tagged stock. The σ_tag = 0.3 results hinge on holding cost
  ($0.06/item-day) and the 0.998/day discount; cheaper patience would
  favor sticker/1 further.
* **Offers are capped at the ask** (nobody bids above a posted tag), so
  the under-tag leak is unfixable by design in every arm tested.
* **The engine knows** σ_wtp, mean traffic, and the huff rate; it LEARNS
  the connection rate, per-item appeal posteriors, and its own realized
  price fraction, censoring-aware. It never sees appeal, WTP, or the true
  shading center (belief: uniform [0.75, 0.95] vs truth 0.75/0.9 ± 0.08).
* **Survival-only belief updates:** the engine ignores the offer stream as
  demand evidence (a rejected $80 counter on a $200 tag is information it
  throws away). This handicaps both engine arms equally.
* **offer/1 never marks asks down** — stale stock moves only via offers. A
  combined arm (offers + computed markdowns) is the obvious P1 and would
  likely dominate; it was not pre-registered and was not run.
* One purchase per browser per visit; no returns, no bidding wars between
  browsers beyond first-come-first-served within a day.
* offer/1's waiting value assumes future settlement at f̂ x ask (EWMA of
  its own realized fractions) — a fixed-point approximation, not a solved
  dynamic program; same fixed-price-resolve heuristic as fashion's
  markdown/1 in the hazard arm's solve.

---

# POST-REGISTRATION FIXES (2026-07-10) — everything below was pre-registered in paper/CRITICAL-ANALYSIS.md §4 BEFORE implementation; results written after the v2 grid run

Two fixes, two pre-registered predictions, same seeds (20260710), same
60-day x 8-rep grid. sticker/1 and hazard/1 rows reproduce v1 exactly
(verified key-for-key across all four cells) — the world and their code
paths are untouched.

**FIX A — `retag/1`, bidirectional retagging (§4b).** Discount-only is a
category error for one-of-one goods: the ceiling exists to protect
reference prices, and one-of-one items have none. `retag/1` is hazard/1's
PV machinery with the shackle removed — the weekly per-item re-solve moves
the POSTED, VISIBLE price UP as well as DOWN, toward the posterior-optimal
posted price, bounded by the item's own appeal posterior support (floor
0.35 x tag unchanged, ceiling the top of the posterior grid). Cadence: the
first solve happens at ADMISSION, then at most weekly per item.
*Interpretation disclosed:* the registration said "updated at most weekly
per item"; an admission-day first solve satisfies that, and waiting a week
would have protected nothing — the median piece sells the day it hits the
rack, so a delayed retag cannot touch the under-tag upside the fix exists
to recover. `retag+offer/1` adds the offer flow on top; the offer ceiling
is the CURRENT tag (offers cap at the posted price, counters live under
it). *Prediction:* recovers a large share of the under-tagged upside H-V1
showed unrecoverable.

**FIX B — shading-aware counters in `offer/1` (§4a).** The old engine
believed shading ~ U[0.75, 0.95] by fiat, knew the huff rate, and could
only accept or counter — so it countered into huffs it could not
anticipate. The fixed engine LEARNS from its own history, censoring-aware:
an accepted counter at c on offer x reveals shading ≤ x/c (WTP ≥ c), a
non-huff reject reveals shading > x/c, and a huff reveals NOTHING about
shading (huffing is price-blind — the update skips it rather than mistake
pride for poverty) while updating the learned huff rate. It also learns
F̂, the browser's continuation value to the store (realized fallback
margin over the fallback piece's own waiting value when a non-huff
negotiation dies; huffed continuations are censored, and the reject-branch
mean stands in exactly because the huff roll is independent of price and
WTP). Counters are charged the huff externality ĥ x F̂, and a DECLINE
action exists: no number handed over, no huff risked, the browser shops
the board — but never buys the declined target that visit (a decline is
not a free conversion at ask). The accept floor (waiting value + buffer)
is unchanged and still tested. *Prediction:* the −$302 cell (σ_tag 0.3 /
shading 0.75) improves to ≥ 0 — the engine learns to mostly accept or
decline rather than counter into huffs — and the winning cells keep most
of their edge.

## The v2 grid: net margin Δ per 60-day store (arm − sticker/1)

| cell (σ_tag / shading) | sticker net | offer Δ (fixed) | hazard Δ | retag Δ | retag+offer Δ |
|---|---:|---|---|---|---|
| 0.3 / 0.75 | 17,281 | +40 [−167, +246] | +136 [−47, +319] | **+4,380** [+3,908, +4,853] | **+4,358** [+3,895, +4,822] |
| 0.3 / 0.90 | 17,281 | +1 [−164, +165] | +136 [−47, +319] | **+4,380** [+3,908, +4,853] | **+4,673** [+4,355, +4,992] |
| 0.6 / 0.75 | 13,506 | **+1,411** [+687, +2,135] | **+1,229** [+456, +2,002] | **+3,677** [+3,278, +4,076] | **+3,912** [+3,395, +4,430] |
| 0.6 / 0.90 | 13,506 | **+1,679** [+1,001, +2,357] | **+1,229** [+456, +2,002] | **+3,677** [+3,278, +4,076] | **+4,329** [+3,792, +4,865] |

(sticker/1, hazard/1, and retag/1 never see an offer, so their rows
replicate across shading columns by construction.) The retag arms' wins
survive both liquidation lenses from the v1 honesty check — at σ_tag 0.3
retag/1 ends with MORE rack value than sticker (ending appeal 2,491 vs
980), so crediting leftovers at cost (+4,794) or at full appeal (+5,892)
only widens the edge; at σ_tag 0.6 the lenses give +3,734 / +3,885.

## FIX A verdict: SUPPORTED — with the decomposition read honestly

Under/over decomposition for retag/1 (Δ gross margin vs sticker/1 by item
class, paired items; the pre-registered report):

| class | σ_tag 0.3: retag Δ | σ_tag 0.6: retag Δ |
|---|---|---|
| under-tagged | **+2,031** [+1,831, +2,231] | **+2,011** [+1,751, +2,271] |
| fair | **+3,073** [+2,852, +3,293] | **+1,485** [+1,296, +1,674] |
| over-tagged | **−662** [−995, −328] | +213 [−319, +745] |
| under − over | **+2,693** [+2,243, +3,142] | **+1,798** [+1,040, +2,557] |

The under-tag upside H-V1 measured as unrecoverable — Σ(appeal − tag) over
under-tagged sourcing, per store — is $2,076 at σ_tag 0.3 and $3,950 at
σ_tag 0.6. retag/1's under-class Δ recovers **~98% of it at σ_tag 0.3 and
~51% at σ_tag 0.6**: "a large share," as predicted, with CIs nowhere near
zero. The prediction is supported.

Two honest qualifications, both visible only because the decomposition was
pre-registered as the report:

1. **The biggest slice of retag/1's total edge at σ_tag 0.3 is the FAIR
   class (+3,073), not the under class.** The bidirectional solve does not
   merely repair the gut's per-piece mistakes — it reprices the entire
   board to the PV optimum, and in this demand-rich world (3.2 connecting
   browsers per item-day, lognormal WTP tails, cheap patience) that
   optimum sits well ABOVE a correct tag. The headline Δ therefore
   overstates the "fix the tagging errors" story; the v1 caveat
   ("demand-rich world", "the sticker's patience is strong by
   construction") now has a dollar figure attached. In a slower store the
   fair-class slice would shrink; the under-class recovery is the part the
   category-error argument actually predicts.
2. **retag/1 is WORSE than hazard/1 on over-tagged stock at σ_tag 0.3
   (−662 vs +132).** A fresh over-tagged piece gets retagged further UP
   (the prior centers on the owner's tag), and the weekly evidence takes
   weeks to walk it back down — bidirectional retagging trades markdown
   speed for upside capture. The combined arm repairs this: retag+offer/1
   turns the over class positive in every cell (+338 to +1,213) because
   the offer flow moves stale stock UNDER the high board, and it
   dominates or matches retag/1 in 3 of 4 cells.

**Fairness exposure: none introduced.** Retags are posted and visible,
identical for every browser, set at admission or weekly — never mid-
negotiation, never per-person; no transaction ever exceeds the CURRENT
posted tag (offers cap at it, counters live under it, both enforced in the
runner and tested). The invariant's scope becomes the first-class finding
pre-registered in §4: discount-only is per-category — it binds where
reference prices exist and protects nothing where they don't.

## FIX B verdict: SUPPORTED — both clauses, one wrinkle

The −$302 cell (σ_tag 0.3 / shading 0.75), before → after:

| metric (per store) | offer/1 v1 | offer/1 fixed |
|---|---:|---:|
| net Δ vs sticker | **−302** [−524, −80] | **+40** [−167, +246] |
| counters made | 1,032 | 448 |
| declines | — | 626 |
| huffs (browsers lost) | 244 | 104 |
| counter→rejects | 609 | 170 |
| units sold | 346.0 | 345.4 |

The pre-registered behavioral claim — "the engine should learn to mostly
accept or decline rather than counter into huffs" — is literally what
happens: counters fall 2.3–8.5x across the cells (1,833 → 326 at
0.6/0.75), declines absorb the flow, and huffs fall 2.3–8.7x. The cell improves to a
positive point estimate whose CI now includes zero instead of sitting
significantly negative: ≥ 0 as predicted (as a point estimate; the CI does
not exclude zero, so read it as "the loss is gone," not "a win appeared").
The winning cells did better than keep their edge: +976 → **+1,411**
[+687, +2,135] and +1,370 → **+1,679** [+1,001, +2,357] — learned shading
places counters where they stick, and the huff externality ĥ x F̂ stops
the engine gambling browsers it can't convert.

The wrinkle, stated plainly: the OTHER σ_tag 0.3 cell (shading 0.9) fell
from +106 [−48, +261] to +1 [−164, +165]. It was a null cell before and
remains one, but the point estimate dropped: where huffs were affordable
(light shading, decent tags), the learned caution also declines some
counters that would have paid. The fix buys insurance against the −$302
disaster at the price of a few points of upside in the benign cell —
which is the correct trade, and also a real cost.

## v2 mechanics and tests

* Engine: `ShadingLearner` (censoring-aware shading-center posterior, Beta
  huff rate, learned F̂) + a three-action `decide_offer`
  (accept/counter/decline) in `vintage/engine.py`; `solve_price_free` (the
  bidirectional re-solve, posterior-bounded) alongside the untouched
  discount-only `solve_price`.
* Arms: `retag/1` and `retag+offer/1` in `vintage/policies.py`; offer
  arms observe every counter outcome and every non-huff dead negotiation's
  continuation via runner hooks in `vintage/run.py`.
* New/updated tests (`vintage/tests/test_vintage.py`, 24 pass): retag
  bounded by the posterior in BOTH directions; retag cadence at most
  weekly per item; shading learner updates from huffs (rate up, shading
  posterior untouched — the censoring rule); counter-aggression monotone
  in learned huff risk (counter → decline flip, no un-flip; accept above
  the floor); decline carries no huff and never converts the target;
  accept-floor invariant under any learner state; one-of-one conservation
  and above-original-tag sales bounded by the posterior ceiling for the
  retag arms.
* `results.json` v2 adds a `decomp` block per cell (under/fair/over Δ
  margin vs sticker for every arm) and a `declines` count; all v1 keys for
  sticker/hazard are byte-identical.

---

# v3 RECALIBRATION (2026-07-10) — CALIBRATION-TARGETS.md §2, priority #5

*Everything above this line is the v1/v2 record, preserved as-is. This
section recalibrates the WORLD (not the v2 fixes) to two pieces of
published evidence and re-runs the full pre-registered grid. It answers
one question head-on: does FIX A's retag result survive realistic
time-on-shelf?*

**What changed.** Two parameters, both in `vintage/calibration.py`, both
cited:

1. **`CONNECT_PROB`: 0.08 → 0.0015** (~53x down). The old world sold a
   fairly-tagged item to ~half its connecting browsers THE SAME DAY (3.2
   connections/item-day; median days-to-sale ≈ 0) — flatly contradicted by
   ThredUp's FY2025 10-K (~50% of resale listings sell within 30 days).
   Fit empirically against sticker/1's 30-day fair-exposure cohort share
   (the same cohort `median_dts`/`share_sold_14d` already used).
2. **`P_HUFF` / `HUFF_BELIEF`: 0.25 → 0.58.** Backus et al. (QJE 2020, 88M
   eBay Best Offer listings) measure buyer decline-after-counter at 58%;
   CALIBRATION-TARGETS.md §2 flagged the old 0.25 as "too low." Both moved
   together so the engine's prior keeps "happening to equal the truth"
   before data dominates it — the v2 design pattern, unchanged.

**What did NOT change:** `TRAFFIC_MEAN` (real LES foot traffic), `SIGMA_WTP`
(the "market is right on average" WTP spread), `SOURCING_RATE`,
`MARKUP_MU`, `DAILY_DISCOUNT`, `HOLDING_COST`, `RHO_PRIOR_MEAN`, the
`GRID_SIGMA_TAG`/`GRID_SHADING` experimental sweep points, and none of the
v2 FIX A/B machinery (`ShadingLearner`, `solve_price_free`, the
accept/counter/decline engine). One robustness diagnostic below
(not part of the calibration) checks what happens if `RHO_PRIOR_MEAN` is
ALSO corrected — it is not the story.

A real bug surfaced by the recalibration: `core.paired_ci` NaN'd on an
empty diff list (sales are now genuinely rare enough that "sold in both
arms" cohorts can be empty over short windows). Fixed to return
`{"mean": None, "ci95": None, "n": 0}`; tested
(`test_v3_paired_ci_handles_empty_diffs`).

## Calibration: sim vs. evidence

**(a) Time-on-shelf (sticker/1, the passive/no-negotiation baseline —
the closest analog to ThredUp's algorithmic-markdown consignment model).**
Official 60-day grid, 8 reps, seed 20260710:

| metric | target (evidence) | sim, σ_tag=0.3 | sim, σ_tag=0.6 |
|---|---|---:|---:|
| 30-day cohort sell-through | ~50% (ThredUp FY2025 10-K) | **54.1%** | **48.7%** |
| median days-to-sale (fair-exposure cohort) | "weeks–months" (was ≈0) | **26.2 d** | **32.9 d** |
| share sold within 14 days | — (diagnostic) | 33.0% | 31.1% |

Both σ_tag cells land inside the pre-registered [0.40, 0.60] test band
(`test_v3_thirty_day_sellthrough_matches_thredup`); the 60-day arm table
can't directly see the 90-day tail (no item has had 90 days), so a
**separate 150-day, 4-rep validation run** (not part of the pre-registered
grid) checks it: share unsold at day 90 is **7.8%** (σ=0.3) and **20.4%**
(σ=0.6) — a real tail past 90 days, consistent with evidence (c)'s 30–90
day consignment window (many real listings get pulled/returned around
there). Day-120 unsold share: 2.3% / 12.0%.

**(b) Offer mechanics (offer/1, Backus et al. QJE 2020).** Same grid,
`first_offer_ratio`/`thread_deal_rate`/etc. are new derived fields in
`aggregate()` (offer-amount and response-outcome counters that already
existed, plus a new `offer_ratio_sum`/`ask_at_sale` instrumentation pair
in `run.py`):

| metric | target | σ0.3/sh0.75 | σ0.3/sh0.9 | σ0.6/sh0.75 | σ0.6/sh0.9 | **grid mean** |
|---|---:|---:|---:|---:|---:|---:|
| first-offer ratio | **60.8%** | 63.9% | 70.2% | 52.9% | 57.5% | **61.1%** |
| response: accept | 32% | 39.1% | 49.2% | 26.0% | 31.2% | 36.4% |
| response: counter | 28% | 52.8% | 40.6% | 52.5% | 58.2% | 51.0% |
| response: decline | 40% | 8.1% | 10.2% | 21.5% | 10.6% | 12.6% |
| post-counter decline (huff) | **58%** | 57.5% | 60.0% | 60.4% | 59.5% | **59.4%** |
| thread deal rate | ~45% | 50.3% | 53.2% | 33.5% | 33.8% | 42.7% |
| price-to-list, bargained | 73% | 79.6% | 82.1% | 78.4% | 79.9% | 80.0% |
| price-to-list, unbargained | 83% | 100%* | 100%* | 100%* | 100%* | 100%* |

Read honestly, metric by metric:

* **First-offer ratio: excellent match (61.1% vs 60.8%), unforced.** The
  shading GRID stayed at the task-specified {0.75, 0.9} — those are
  experimental treatment points, not free calibration knobs — yet the
  *observed* ratio lands well below the shading center in every cell
  (e.g. 63.9% at shading=0.75, not 75%). Why: `offer = min(ask, shading x
  WTP)`; whenever shading x WTP already clears the ask the browser just
  buys at ask (an auto "ask" sale, never entering the offer log) — so the
  offer population left over is SELECTED for the cases where the shaded
  bid falls short, which drags the empirical ratio down toward Backus's
  figure as a byproduct of the sparse-connection recalibration, not a
  deliberate fit. Test: `test_v3_first_offer_ratio_near_ebay_evidence`.
* **Post-counter decline: excellent match (59.4% vs 58%), by
  construction** — `P_HUFF` fires independently of the engine's strategy,
  so this is close to a direct readout of the parameter. Test:
  `test_v3_post_counter_decline_near_ebay_evidence`.
* **Thread deal rate: good match in σ=0.3 (50–53% vs ~45%), weaker in
  σ=0.6 (34%).** Noisier tags mean more items are badly over-tagged, whose
  huge gap between ask and true value the engine's floor won't close even
  with a counter — more threads simply die.
* **Price-to-list, bargained: directionally right, ~7–9 points rich
  (80% vs 73%).** The engine's accept floor (`v_wait + buffer`) puts a
  hard lower bound on how much it discounts that Backus's real sellers
  don't have to respect as strictly.
* **Response mix: the one real miss — decline undershoots badly (13%
  grid mean vs 40%).** Not a tuning failure so much as a STRUCTURAL
  consequence of the SAME recalibration that fixed (a): declining only
  pays when the browser has a real fallback item to shop toward (the
  engine's `decide_offer` math shows counter beats decline whenever the
  learned fallback value F̂ is near zero — see `test_counter_aggression_
  monotone_in_learned_huff_risk`'s v3-updated fixture). At CONNECT_PROB
  =0.0015, a browser connecting with the store's rack rarely connects
  with a SECOND item the same visit (mean connections/visit ≈0.2–0.4), so
  there is usually nowhere to decline TO. Backus's eBay is a marketplace
  of millions of parallel listings; a one-of-one rack of ~150–200 items
  is not. Decline share is highest exactly where it should be (21.5% at
  σ=0.6/sh=0.75, the noisiest-tag cell, where fallback alternatives are
  most likely to have real value) — the mechanism is directionally
  correct, just structurally capped well below Backus's population by the
  one-of-one setting. Accept, correspondingly, runs a bit high (36% vs
  32%) — it absorbs the traffic decline "should" have taken.
* **Price-to-list, unbargained: 100% for offer/1 — a structural
  invariant, not a miscalibration.** offer/1 never marks the ASK down (the
  offer flow IS its only discount channel); an "unbargained" (ask-channel)
  sale is BY DEFINITION a purchase at the posted price, so this ratio is
  always exactly 1.00 for this arm, full stop. The meaningful read is on
  arms whose ask MOVES: **hazard/1's unbargained ratio is 85.3%/84.3%
  (σ=0.3/0.6) and retag/1's is 85.0%/82.6%** — both within a couple points
  of Backus's 83%, because their weekly repricing (see below) genuinely
  discounts stock that eventually sells at ask. sticker/1's own
  unbargained ratio (96.4%/96.9%) is high because its markdown only bites
  after 30 unsold days, and ~50% of the cohort sells before that.

## The re-run arm table (v3 world): net margin Δ per 60-day store (arm − sticker/1)

8 reps, seed 20260710, block=1 paired t-CIs — same protocol as v1/v2.
**Dollar levels are NOT comparable to the v1/v2 tables above** — this
world is ~53x less liquid by design; sticker/1's own net margin fell from
17,281/13,506 to **6,845 (σ=0.3) / 4,509 (σ=0.6)**.

| cell (σ_tag / shading) | sticker net | offer Δ | hazard Δ | retag Δ | retag+offer Δ |
|---|---:|---|---|---|---|
| 0.3 / 0.75 | 6,845 | −34 [−184, +117] | −161 [−359, +38] | **−317** [−584, −51] | **−654** [−836, −471] |
| 0.3 / 0.90 | 6,845 | **+1,467** [+1,088, +1,846] | −161 [−359, +38] | **−317** [−584, −51] | **+725** [+438, +1,012] |
| 0.6 / 0.75 | 4,509 | +259 [−26, +545] | −54 [−211, +104] | **−268** [−477, −60] | −329 [−661, +4] |
| 0.6 / 0.90 | 4,509 | **+1,479** [+1,123, +1,835] | −54 [−211, +104] | **−268** [−477, −60] | **+762** [+431, +1,094] |

(hazard/1 and retag/1 never see an offer, so their rows replicate across
shading columns by construction, as before.) Every arm still ends with
LESS inventory (both cost and appeal basis) than sticker/1 in every cell —
no arm wins by merely refusing to sell, including retag/1 despite its
losses (it moves MORE units than sticker — 195.9 vs 178.9 at σ=0.3 — at a
lower average realized price, which is the whole story below).

## THE KEY FINDING: computed markdowns flip sign under realistic time-on-shelf

**retag/1 is significantly WORSE than sticker/1 in every cell** (CI
excludes zero, negative, in all four) — the complete reversal of v2's
headline (+3,677 to +4,380, CI nowhere near zero). **hazard/1 goes from a
significant winner in v2 (+1,229 at σ=0.6) to a null-to-negative arm in
v3** (point estimates −54 to −161, CIs include zero). Both arms share the
same PV-repricing machinery (`solve_price`/`solve_price_free` in
`vintage/engine.py`); both flip. This is the direct answer to the
pre-registered key question.

**Mechanism, isolated with a diagnostic (not part of the calibration, run
against the ALREADY-recalibrated world):** a single fresh, correctly-
tagged item, retagged weekly, with `RHO_PRIOR_MEAN` pinned at the store's
own CORRECT converged rate (ruling out "the prior hasn't learned yet" as
the explanation):

| week | 0 (admission) | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|
| retag price / original tag | 1.05 | 0.98 | 0.91 | 0.84 | 0.77 | 0.70 | 0.63 |

Even with the RIGHT demand belief, a correctly-tagged item that simply
hasn't sold yet — the NORMAL outcome now that a fair item's true daily
hazard is ~2–3%, not ~90% — gets marked down almost as fast as sticker's
crude 30-day ritual (which reaches 80% at day 30, roughly where retag/1
is by week 4) and considerably FURTHER by day 56 (63% vs sticker's flat
80%). Zeroing `HOLDING_COST` slows but does not stop the decline (still
77% by week 8) — **`DAILY_DISCOUNT` alone is enough**: the PV-maximizing
solve assumes the chosen price is held FOREVER (the documented
"fixed-price-resolve heuristic"), so it discounts the value of holding
out for a future high-WTP buyer over an expected wait that is now WEEKS
long, not under a day. The v2 world's `DAILY_DISCOUNT`/`HOLDING_COST`
levels were never miscalibrated in isolation — they were tuned (implicitly,
by never being stress-tested) against a hazard ~50x faster than the one
CALIBRATION-TARGETS.md's evidence says is real. **Not selling for a few
weeks is now the EXPECTED outcome for a perfectly fairly-tagged item, but
the repricing objective still reads it as evidence of overpricing and
cuts — a computed markdown is only as patient as the model of the future
it's handed, and this one was handed a demand-rich future.**

The under/fair/over decomposition makes the reversal concrete — same
report FIX A pre-registered, now run against the recalibrated world:

| class | σ_tag 0.3: retag Δ (v3) | σ_tag 0.3: retag Δ (v2) | σ_tag 0.6: retag Δ (v3) | σ_tag 0.6: retag Δ (v2) |
|---|---:|---:|---:|---:|
| under-tagged | **−208** [−250, −165] | +2,031 [+1,831, +2,231] | **−402** [−461, −344] | +2,011 [+1,751, +2,271] |
| fair | **−311** [−470, −151] | +3,073 [+2,852, +3,293] | −86 [−187, +15] | +1,485 [+1,296, +1,674] |
| over | +174 [−13, +361] | −662 [−995, −328] | +200 [−9, +409] | +213 [−319, +745] |
| under − over | **−382** [−579, −184] | +2,693 [+2,243, +3,142] | **−602** [−803, −402] | +1,798 [+1,040, +2,557] |

**The under-tagged class Δ inverted sign** — from v2's headline "recovers
~98%/~51% of the unrecoverable under-tag upside" to a significant LOSS in
v3. The reason is exactly the mechanism above: v1/2's world sold an
under-tagged item to a WTP-clearing browser within hours regardless of
arm (near-instant connections), so retag/1's admission-day markup had all
the time in the world to land before anyone showed up, and it worked. In
the recalibrated world, an under-tagged item can sit for WEEKS before its
first connection — plenty of time for the SAME weekly re-solve that used
to mark it up to instead grind it back down as quiet (uninformative, at
this hazard) survival evidence accumulates, converting engineered upside
into an engineered giveaway, sometimes selling it for LESS than the
already-too-low original tag would have fetched had the store simply left
it alone. The over-tagged class is now a small, non-significant positive
in both cells (v2 had it significantly negative at σ=0.3) — retag/1's
board-wide markdown pressure, which used to be too weak to fix stale
over-tagged stock fast enough, now more closely matches what stale stock
actually needs; it just does the same thing to everything else too.

## Verdict: retag/1's dominance does NOT survive realistic time-on-shelf

**REVERSED, not just weakened.** FIX A's under-tag recovery — the
headline result of the previous section — was a genuine artifact of a
world where median days-to-sale was ≈0. At ThredUp's real pace, the same
mechanism, unchanged, loses money relative to doing nothing (the sticker
ritual) in all four grid cells, three of them at CI-excludes-zero
significance. **retag+offer/1 survives only where offer/1's shading-driven
upside is large enough to outrun retag's drag** (significantly positive
at shading=0.9 in both σ_tag cells, significantly negative at
shading=0.75/σ=0.3, null at shading=0.75/σ=0.6) — it is not a robust
combined-arm win, it is retag/1's loss partially or fully offset by
offer/1's gain depending on the cell.

## offer/1 vs. retag+offer/1: price discrimination survives; broadcast discounting doesn't

Both engines share the SAME waiting-value machinery (`Beliefs.
continuation`, the identical `_pv` closed form retag's markdown solve
uses) — so offer/1's accept floor is JUST AS "impatient" as retag/1's
posted price. Yet offer/1 alone is never significantly negative anywhere
in the v3 grid (worst cell: −34 [−184, +117], a null, not a loss) while
retag/1 is significantly negative everywhere. The difference is not the
belief, it's the BLAST RADIUS of acting on it:

* **retag/1 broadcasts its discount** — cutting the posted price hands a
  markdown to EVERY future browser who sees the item, including the ones
  who would have paid full ask anyway. An impatient waiting-value estimate
  is therefore a tax on the whole future customer base.
* **offer/1 price-discriminates** — a low waiting value only makes the
  engine more willing to accept a LOWBALL from the specific browser
  standing in front of it RIGHT NOW, who has already revealed they will
  not pay ask. The same mis-calibrated impatience only ever costs the
  store the marginal difference on a sale that was, by construction, not
  going to happen at the posted price anyway.

This is a general, not vintage-specific, point: **a repricing objective's
calibration errors are amplified when the action is a broadcast price
change and dampened when the action is a private, per-counterparty
decision.** It also reframes the v2 "H-V3 supported" result: hazard/1's
v2 win wasn't evidence that computed markdowns beat a fixed calendar in
general — it was evidence they beat it in a demand-rich world where the
model's implicit patience assumptions happened to be roughly right.

## Does offer/1's learned counter-caution work better at 58% huff?

**Yes, on the metric that matters most: no cell loses money.** At the old
25%-huff calibration (v1, pre-FIX-B), the −$302 disaster cell existed
specifically because the engine countered into huffs it couldn't
anticipate. At 58% huff — a MUCH harsher regime — the FIX-B engine (learned
shading/huff/fallback, unchanged from v2) still produces zero
significantly-negative offer/1 cells in the recalibrated grid: the worst
outcome is a tight null (−34 [−184, +117]), not a loss. The learned model
is doing its job: `decline_after_counter_rate` tracks the true 58%
almost exactly (59.4% grid mean) rather than the engine systematically
over- or under-countering into it, and `response_counter_rate` (51% grid
mean) sits well below what a naive fixed-shading engine with no huff
model would attempt. The one place the higher huff rate visibly costs
money is the SIZE of the win at generous shading — offer/1's shading=0.9
gains (+1,467/+1,479) are large but come with wider, noisier CIs than a
lower-huff regime would produce, because a larger share of each cell's
negotiation attempts now end in a walkout rather than a resolved price.
The counter-caution mechanism (learned shading/huff/fallback, FIX B) is
unchanged from v2 and was already stress-tested at a MUCH harsher huff
level here than it was designed against — it holds.

## Honest surprises (v3)

1. **Absolute dollars aren't the story anymore — the recalibration is a
   ~53x demand cut, not a fine-tune.** Every headline number in this
   section is far smaller than v1/v2's; anyone quoting a dollar figure
   from this file must say which world it's from.
2. **`RHO_PRIOR_MEAN` mismatch (0.05 prior vs. 0.0015 true) is NOT the
   driver of retag's reversal.** A diagnostic that pins the engine's
   belief at the TRUE rate from day one still shows retag/1 within ~$50
   of the mismatched-prior result (net_margin 5,805 vs 5,760 in one
   single-seed probe) — nowhere near closing the ~$650 gap to sticker/1
   in that cell. The store-level rho estimator also converges to within
   1% of the true value by day 60 on its own (verified), so "the learner
   hasn't caught up" is not the mechanism either. The impatience lives in
   `DAILY_DISCOUNT`/`HOLDING_COST` meeting a hazard that dropped ~53x
   while they didn't move at all — see the mechanism section above.
3. **offer/1's shading sensitivity got MUCH bigger, not just carried
   over.** v2's shading swing was small and sometimes even the WRONG
   direction (+106→+1 in one σ=0.3 cell). v3's swing is large and
   monotonically positive in every cell (+1,500 and +1,220 respectively
   going 0.75→0.90). With so few connections overall, each one is a much
   larger share of the store's total business, so how the engine converts
   it (which shading governs directly) moves the whole store's economics
   far more than it did in the demand-rich world where a lost browser was
   quickly replaced by the next one.
4. **No arm strips the rack to win.** Every treatment arm — including the
   now-losing retag/1 — ends with less ending inventory (cost and appeal
   basis) than sticker/1 in every cell. retag/1's loss is a genuine
   value-destruction story (it sells MORE units for LESS total profit),
   not a "sold fewer, kept nicer inventory" story.

## Files changed / test count (v3)

* `vintage/calibration.py` — `CONNECT_PROB` 0.08→0.0015, `P_HUFF`/
  `HUFF_BELIEF` 0.25→0.58, both cited inline.
* `vintage/core.py` — `paired_ci` returns `{"mean": None, "ci95": None,
  "n": 0}` on an empty diff list instead of NaN'ing.
* `vintage/run.py` — `VINTAGE_VERSION` 2→3; new `ask_at_sale` ledger
  field and `offer_ratio_sum` day-metric; `aggregate()` gains
  `share_sold_30d`, `first_offer_ratio`, `thread_deal_rate`,
  `decline_after_counter_rate`, `response_{accept,counter,decline}_rate`,
  `price_to_list_{bargained,unbargained}`; `run_experiment`'s per-rep
  averaging made None-safe for all of the above (mirrors the pre-existing
  `share_sold_14d` pattern); config notes updated.
* `vintage/tests/test_vintage.py` — `test_counter_aggression_monotone_
  in_learned_huff_risk` re-fixtured for the new HUFF_BELIEF prior (the
  qualitative finding it tests — counter aggression falls monotonically
  in learned huff risk — is unchanged; the specific offer/ask/waiting-value
  numbers that trigger it needed updating since a realistic 58% prior
  changes where the accept/counter/decline boundaries sit). Four new
  tests: 30-day sell-through in [0.40, 0.60] under sticker/1, first-offer
  ratio in [0.45, 0.80], post-counter decline in [0.45, 0.70], and
  `paired_ci`'s empty-list fix. **28 tests total, all pass** (24 v2 +
  4 v3; runtime ~12.5s).
* `vintage/results.json` — regenerated at v3 (`vintage_version: 3`), same
  seed (20260710), same 5-arm x 4-cell grid, 8 reps; NOT comparable
  key-for-key to v1/v2 (the world itself changed, not just the arms).
* `paper/CALIBRATION-TARGETS.md` — untouched (source of the targets,
  not a target of this task).
