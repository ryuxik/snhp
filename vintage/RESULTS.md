# VINTAGE results — offer/1 and hazard/1 vs sticker/1

*One-of-one LES vintage store, 60 paired days per cell, 8 independent
replicate stores per cell, seed 20260710. Reproduce:
`python3 -m vintage.run --grid --days 60 --reps 8 --seed 20260710 --out vintage/results.json`.
Replicates are independent stores (fresh sourcing, browsers, learner state),
so CIs are plain paired t over rep-level totals (block=1).*

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
