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
