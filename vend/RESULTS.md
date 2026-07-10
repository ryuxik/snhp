# VEND results log

## P0 (2026-07-09) — pre-registered H1: **FAILED**, and the failure is the finding

**H1 said:** a machine running engine-computed posted prices out-earns the
same machine at static prices. **It doesn't.** Against a *competent* static
baseline (profit-optimal all-day single price per SKU), per-SKU resolving
GvR — profit objective, bid-price scarcity guard, salvage floors, hourly
crowd discrimination — **loses money**, replicated on two seeds:

| paired, 30 days | seed 20260713 | seed 7 |
|---|---|---|
| profit Δ/day (gvr − static) | **−$1.71** [−2.50, −0.93] | **−$2.07** [−2.77, −1.36] |
| consumer surplus Δ/day | +$2.41 | +$2.41 |
| units Δ/day | +2.4 | +2.0 |

Margin per unit: static $1.377 → gvr $1.308. Revenue ~flat. Spoilage $0 in
both arms (well-tuned par stocks never let the perishable lever fire).

**Mechanism (diagnosed, not assumed):** cross-SKU cannibalization plus
surplus transfer. Per-SKU pricing treats each slot's demand as separable;
in reality (and in the sim) consumers choose the best surplus across the
whole board, so an off-peak discount on chips mostly diverts buyers who
would have paid list for cola, and gives cheaper chips to buyers who would
have paid list for chips. Per-hour, per-SKU profit-max is pointwise optimal
*only if hours and SKUs are separable* — they aren't, and the diversion
externality eats the gains. The extra consumer surplus is real but it is
bought with the merchant's margin, not created.

Note the two objective-level corrections made along the way (both arms,
baseline kept strong): revenue-max → profit-max everywhere; expiring-tonight
stock prices against salvage as its opportunity cost, durable stock against
unit cost (nightly top-to-par restock ⇒ carry value = replacement cost).

**Why this sharpens the thesis instead of sinking it:** posted dynamic
pricing fails here precisely because it prices SKUs independently against an
anonymous crowd. A negotiation prices one person's *entire choice problem* —
their substitution options, their quantity curve, their outside option —
which internalizes exactly the externality that sank GvR. That is now the
sharpened, pre-registered **H2 for P1**: the A2A arm must beat *both* static
and gvr on profit while keeping consumer surplus at or above static. If it
can't, the honest conclusion is that a well-priced sticker beats invisible
negotiation at a vending machine, and we publish that.

**Caveats for readers who want to attack this (please do):** the operator
here is unrealistically competent (profit-optimal list prices, well-tuned
pars, true demand model — the last is *favorable* to the dynamic arm and it
still lost); demand has no day-level shocks, so there is nothing for an
adaptive policy to react to. Real-world dynamic-pricing value often lives in
exactly those miscalibrations. A demand-shock arm (static can't react;
learning policies can) is a candidate P4 extension.

Reproduce: `python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr`

## P1 (2026-07-09) — brokered A2A: H2 not yet, H3 emphatically yes

The A2A arm quotes the Nash bargaining point over the enumerated outcome
space (item × quantity × price ladder), on verified disclosures from both
sides, with the machine's disagreement point = its sticker counterfactual
for THIS buyer. Built in three acts, each diagnosed from the paired runs:

**Act 1 — naive bilateral Nash loses catastrophically** (profit −$22.9/day,
CS −$44.5): early bargain-hunters drained stock in multi-unit bundles at
near-cost; the lunch crowd hit empty slots (stockouts +68%, walk-outs 2×).
The per-deal guarantee `u_machine ≥ d_machine` says nothing about the
*future* buyer the deal starves.

**Act 2 — shadow pricing fixes the drain, not the gap** (profit −$11.0/day,
CS −$12.1): each quoted unit now carries its opportunity cost — units within
expected rest-of-day list demand are worth list margin to keep, only excess
is cheap to move. Stockouts drop *below* static. The remaining gap is the
most instructive bug of the day: `neg_machine_gain` (the machine's believed
surplus vs. its counterfactuals) totals **+$548** while realized profit is
**−$329**. The demand forecast behind the shadow price assumes a static
world; in the A2A world later buyers also negotiate, so the "someone will
buy this at list later" counterfactual partially never happens. The
mechanism invalidates the model that prices it — the Lucas critique, in a
vending machine.

**H3 — the attestation moat, quantified (clean, monotone, tight CIs):**
holding the mechanism fixed and letting a share of buyer agents run the
anchoring attack (understate WTP, claim a free outside option):

| liar share | machine profit Δ/day vs all-honest | CS Δ/day |
|---|---|---|
| 25% | **−$4.14** [−5.09, −3.20] | +$7.26 |
| 50% | **−$9.26** [−10.68, −7.83] | +$16.75 |
| 100% | **−$21.55** [−23.11, −19.99] | +$40.75 |

Every dollar the machine loses lands in the liars' pockets. A merchant
adopting brokered negotiation without verified disclosure bleeds
monotonically in the share of adversarial agents — attestation is not a
compliance feature, it is the difference between a mechanism and a coupon
exploit. (`vend/liar-sweep.json`; the discount surface liars attack is
excess/expiring stock — shadow pricing holds scarce stock at list for
honest and liar alike.)

**The emerging meta-result (pre-registering P1.5):** against a
perfectly-calibrated sticker in a stationary world, there is almost no
surplus for ANY dynamic mechanism to find — we built the static baseline at
the profit ceiling by construction, and every dynamic arm has now paid for
information it didn't have. The honest next experiment asks *when does
negotiation pay*: introduce (a) day-level demand shocks, (b) miscalibrated
list prices (±20%), (c) oversupplied pars — the conditions real retail
lives in. Pre-registered expectation: static degrades with miscalibration
while A2A (which observes each buyer directly) does not; if that's wrong,
we say so.

Reproduce: `python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr,a2a`
and `--arms a2a,a2a-liars25,a2a-liars50,a2a-liars100`.

## P1.5 (2026-07-09) — negotiation pays exactly where the real world lives

P0/P1 gave the sticker an omniscient operator in a stationary world. P1.5
restores real retail's information structure — day-level demand shocks, an
office-tower calendar under one all-week sticker, glut deliveries, and the
big one: the sticker is optimized against a NOISY operator estimate of
demand (σ_cal), which is also what the dynamic arms believe (they adapt via
a Gamma–Poisson crowd posterior and shares learned from their own sales;
nobody secretly knows the truth). Pre-registered grid, 30 paired days per
cell (`vend/grid.json`):

| σ_cal \ σ_shock | 0 | 0.3 | 0.6 |
|---|---|---|---|
| **0 (omniscient)** | a2a −6.05 | −4.08 | −1.65 |
| **0.15** | −3.19 | −1.53 | −0.30 *(all straddle 0)* |
| **0.30 (realistic)** | **+3.80** [1.3, 6.3] | **+4.48** [1.4, 7.6] | **+5.85** [2.5, 9.2] |

(a2a profit Δ/day vs static; control cell with all knobs off replicates
P0/P1: −12.17.)

**The three findings:**
1. **Monotone in operator ignorance, exactly as pre-registered.** With a
   perfectly-calibrated sticker, static stays unbeatable. At a realistic
   ±30% demand-estimate error, brokered negotiation wins **+$3.80–5.85/day
   per machine** (CIs exclude zero), and the edge GROWS with demand
   volatility. Replicated on an independent seed (+$4.05 [1.1, 7.0]).
2. **Both sides win — only in the A2A arm.** Consumer surplus is positive
   in every winning cell (+$0.94 to +$2.00/day; +$4.45 on the replication
   seed). Dynamic posted pricing (gvr) ekes out ~$1/day; **negotiation's
   edge over posted-dynamic is 4–5×**, because disclosure beats inference:
   the posted arm learns the crowd slowly from foot traffic, while the
   negotiation sees each buyer's actual willingness directly, so the
   miscalibrated sticker stops mattering for negotiated deals.
3. **The mechanism sentence:** a sticker is a bet on a demand curve;
   negotiation is what wins when that bet is wrong — and outside
   simulations, it is always somewhat wrong.

Caveats, honestly: the discount-only clamp means stickers set too LOW are
unrecoverable by every arm (the win comes from the too-high SKUs); σ_cal =
0.30 as "realistic" is an assumption reviewers should attack (markdown-
optimization vendors claim retail price-setting errors at least this
large); WTP shocks remain unobserved by all arms alike.

Reproduce: `python3 -m vend.run --grid --days 30 --seed 20260713 --arms static,gvr,a2a`

## Post-review corrections (2026-07-10) — the numbers above are SUPERSEDED

A 10-angle adversarial code review found three rigor bugs in the sim, all
biased in the A2A arm's favor, plus an anti-conservative statistics choice.
Fixed, and every artifact regenerated:

1. **Irrational acceptance**: consumers compared negotiated deals only
   against the bodega, never against the machine's own sticker board — they
   could accept deals worse than walking two feet to the stickers. Now
   acceptance requires beating BOTH alternatives ("never worse UX than
   static" is enforced, not assumed).
2. **Unstable liar identity**: the anchoring roll re-randomized per
   encounter and was policy-coupled through the return queue. Liars are now
   stable people (keyed on consumer identity, paired across arms).
3. **Divergent sticker counterfactual**: the machine's disagreement point
   was computed with different stock-capping than the buyer's actual board
   behavior, and ignored the buyer's stated intent constraints. One shared
   chooser now backs both, and the counterfactual respects the intent.
4. **CI honesty**: daily paired diffs are autocorrelated (learner state,
   lots carry over); intervals now use 5-day block means.

**Corrected results.** Control cell (omniscient sticker): a2a −$9.38/day —
static still wins where the operator knows everything. The grid stays
monotone in miscalibration; at σ_cal=0.3 the 30-day point estimates are
+$2.07/+$2.41/+$2.66/day (block CIs straddle zero at n=6 blocks — 30 days
is underpowered under honest intervals). The **90-day confirmatory runs**
settle it:

| cal 0.3 / shock 0.6, 90 days | profit Δ/day vs static | CS Δ/day |
|---|---|---|
| seed 20260713 | **+$4.29** [2.68, 5.90] | +$7.43 |
| seed 7 | **+$3.31** [1.82, 4.79] | +$8.19 |

Both sides win, both seeds, intervals exclude zero under block CIs, with
rational consumers. **H2 holds — and the corrected result is more
defensible than the inflated one it replaces.** H3 likewise re-confirmed
with stable liar identities: −$6.24 / −$11.42 / −$22.89 per day at
25/50/100% liars (all significant), buyers pocketing the difference.

Reproduce the confirmatory: `python3 -m vend.run --days 90 --seed 20260713
--arms static,a2a --sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow
--glut 0.15 --out /tmp/confirm90.json` (and --seed 7).

## The weak-dominance upgrade (2026-07-10) — CURRENT results

Challenged on "a well-priced sticker shouldn't be unbeatable," we found the
mechanism (not the economics) was leaving money down, and made three
upgrades:

1. **Event-consistent disagreement.** The no-deal world is ONE event: the
   buyer's best alternative (board purchase or bodega), and both sides'
   threat points come from it. A buyer who'd walk outside gives the machine
   a ZERO counterfactual — recruiting marginal customers with deep quantity
   deals is found money — while a board buyer must be offered something
   genuinely better than the board, or the engine honestly says "no deal,
   buy the sticker."
2. **Regime-consistent forecasting.** Displacement demand now comes from
   the learner's EWMA of realized units/day in the arm's OWN world
   (dow-normalized), not a static-world formula — closing P1's
   self-invalidating-forecast gap.
3. **A don't-negotiate-for-pennies buffer** (min_gain = $1.00): believed
   machine gain must clear a buffer, so forecast noise can't leak margin on
   near-zero-gain deals. Swept in-sample on the control cell; validated
   out-of-sample on the untouched seed-7 realistic cell.

**Current numbers (supersede the corrections section above):**

| cell | a2a profit Δ/day vs static | CS Δ/day |
|---|---|---|
| control (omniscient sticker) | **−$0.72** [−1.43, −0.00] — statistical tie | +$2.11 |
| cal0.3 grid row (30d) | +$2.47 / +$2.49 / +$2.34 | +$5–7 |
| cal0.3/shock0.6, 90d, seed A | **+$2.30** [1.09, 3.52] | +$10.41 |
| cal0.3/shock0.6, 90d, seed 7 | **+$1.95** [1.06, 2.83] | +$8.29 |

**Weak dominance:** statistically indistinguishable from a PERFECT sticker
in its own fortress; significantly better wherever the operator's
calibration or the world is imperfect; consumers better off everywhere.

**H3 inverted — the anchoring attack no longer pays.** Under the upgraded
mechanism the liar sweep flattens to zero for the machine (Δ +$0.26–0.48/day,
CIs spanning 0) and liars do slightly WORSE than honest disclosure
themselves (CS Δ −$0.27 to −$1.77): understating your wants mostly denies
you deals the buffer would otherwise have cleared. Approximate
incentive-compatibility emerged from the disagreement structure + buffer.
This repositions attestation from defense to **discount tier** —
pre-registered next experiment: verified agents get a lower buffer
(min_gain $0.25 vs $1.00), prediction: attested buyers capture measurably
more surplus at no machine cost, making verification something buyers WANT.
