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

**Attack battery ("IC against one deviation isn't IC"):** best-response
search over disclosed-WTP scaling {0.55…1.5} × outside-option claims, every
buyer deviating, paired 30 days. Honest disclosure is at the buyers' best
response: every genuine misreport LOSES them money (−$0.11 to −$1.76/day
pooled across all buyers); the lone positive point estimate (truthful WTP +
free-walk claim, +$0.50/day pooled ≈ half a cent per visit) is noise-level,
costs the machine, and is precisely what the attestation discount tier
prices out. Remaining for the formal write-up: per-deviation CIs across
seeds, adaptive (state-dependent) deviations, colluding buyers.

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

## The sticker question (2026-07-10) — "Uber has no sticker; why do we?"

Asked whether the sticker is necessary at all, we made the ceiling a dial
(`anchor_peak`, `anchor_mult`) and made the competitor price independently
of our board (`Listing.bodega_price` from TRUE demand — previously the
bodega copied our list, a modeling shortcut this experiment exposed).
Perfect-calibration, stationary world, 30 paired days:

| ceiling placement | static profit | a2a profit | a2a negotiated |
|---|---:|---:|---:|
| mixture-optimal sticker | $2,864 | $2,842 | 40 |
| peak-anchored | $3,037 | $3,020 | 48 |
| **×1.25 (the TRUE static optimum)** | **$3,511** | **$3,554** | 226 |
| ×1.5 (ceiling ~never binds = no sticker) | $1,690 | $2,953 | 712 |

**Findings, honestly:**
1. Our "profit-optimal" stickers were never optimal — the single-price
   optimizer prices the demand curve and ignores the machine's local
   monopoly power (competitor price + walk cost). The true optimum sits
   ~25% above the peak anchor and earns +$21/day more. Every "omniscient
   operator" claim above inherits this asterisk.
2. **At the true optimal anchor, quote-assisted pricing beats/ties the
   best sticker even at perfect calibration**: +$1.44/day [−2.16, 5.03]
   seed A, **+$2.56/day [1.23, 3.89] seed 7**, with consumer surplus
   +$10–11/day in both — because the high anchor prices the captive
   sticker lane while quotes recover everyone the anchor would lose.
3. A fully sticker-less machine (ceiling never binds) holds 84% of peak
   profit on 712 quotes — the sticker's real job is a ZERO-FRICTION
   DEFAULT LANE, not consumer protection; the remaining gap is quote
   friction (our $1 buffer, tuned for a world with a good sticker), not
   economics. Uber's answer to the same problem is the binding upfront
   quote.
4. The unpriced risk: our consumers carry no reference-price/fairness
   memory — the ×1.25 "optimum" harvests captivity that real humans
   punish (the Wendy's zone) and regulators watch. Pre-registered:
   a reference-price/churn response in the consumer model, to measure how
   much of the +$21/day anchor value is safely harvestable, and whether
   visible computed DISCOUNTS from a high anchor (our design) escape the
   fairness penalty that visible increases trigger (the dual-entitlement
   literature says yes).

## Fairness v1 — reference prices, churn, and the harvest (PRELIMINARY)

Built (`vend/regulars.py` + WorldConfig.regulars): a persistent pool of
repeat customers with per-SKU reference prices (EWMA of paid, weaker for
observed), loss-averse transaction utility (2.0× above reference, 0.5×
below, +0.15/dollar deal-framing glow on visible discounts), sticker-shock
on visits, dissatisfaction → permanent churn. 120 regulars, 90 days, seed 2:

| anchor | arm | early $/d | late $/d | churned | reg deals |
|---|---|---:|---:|---:|---:|
| mixture | static | 100.5 | 100.5 | 0/120 | 2,512 |
| mixture | a2a | 99.5 | 99.5 | 2/120 | 2,468 |
| ×1.25 | static | 128.0 | 140.4 | **56/120** | 1,007 |
| ×1.25 | a2a | 126.7 | 135.4 | **57/120** | 1,142 |

**Preliminary findings, honestly:**
1. In-model, the high anchor harvest SURVIVES churning half the regular
   pool — but via survivor bias (churn removes the price-sensitive;
   remaining whales pay more) plus a transient cushion (walk-ins have no
   fairness memory) and NO pool replenishment (churned customers are never
   replaced, so 90 days understates terminal damage). Static's "rising"
   late profit is a melting ice cube presented as growth.
2. The quote-protection hypothesis UNDER-DELIVERS as built: quotes fire on
   only ~23% of regular visits, so most regulars face the raw ×1.25 board
   and shock anyway. Three specific mechanisms identified, pre-registered
   for v2: (a) below-reference payments should RELIEVE dissatisfaction
   (transaction utility is symmetric; currently only pain accrues);
   (b) quote-salience — in the scan-first UX the customer sees THEIR price,
   not the board, so sticker-shock should key on the quote when one fires
   (this is rung 2's entire design, now measurable); (c) the $1 flat
   noise buffer is a 50% margin floor on a $2 item — it must scale with
   transaction size (e.g. max($0.25, 10% of list×qty)).
3. Fairness-aware agent disclosure (cap disclosed willingness at reference
   tolerance) is implemented for regulars and necessary but not sufficient
   — it raised regular deals 1,007→1,142 without moving churn.

VERDICT SO FAR: do not ship the ×1.25 anchor on fairness-blind numbers;
the safe-harvest number awaits v2's three fixes plus pool replenishment.
Reproduce: WorldConfig(regulars=120, anchor_peak=True, anchor_mult=1.25).

## Fairness v2 — the safe harvest, measured

The three pre-registered fixes are in: symmetric dissatisfaction relief
(good deals heal), quote-salience (a fired quote is the salient price —
the scan-first UX as fairness technology), and a size-scaled buffer
(floor $0.75 + 15% of bundle list; the flat $1 was gating quotes off
exactly the small-basket regulars the anchor shocks). Plus exogenous pool
replenishment (0.7 joins/day, market references) so churn has a real
price. 120 regulars, 90 days, ×1.25 anchor:

| arm | late profit $/d | churned | active pool at day 90 | reg deals |
|---|---:|---:|---:|---:|
| static ×1.25 | 142.1 | 81 | 102 and falling | 1,145 |
| **a2a ×1.25** | **133.5–133.9** | 49–60 | **120/120 — full** | 1,852 |
| static mixture (the old world) | 100.5 | 0 | 120 | 2,100 |

**The safe-harvest answer: ≈ +$33/day over the old sticker world with the
customer base fully intact.** Fairness-blind static harvests ~$8/day more
on this horizon but burns the franchise (net churn despite replenishment,
survivor-bias whales, fairness-immune transients cushioning the optics) —
on any longer horizon or any customer-lifetime accounting, the negotiated
harvest dominates. Quote protection works through exactly the hypothesized
channel: quotes fire widely (1,852 vs 1,145 regular deals), the paid price
stays near reference, good deals heal dissatisfaction.

Buffer frontier (documented, not hidden): $1 flat → perfect-cal tie
(−$0.72) but regulars unprotected; 0.25/10% → full protection, −$5.43
control leak; **default 0.75/15% → control −$1.98 [−2.70, −1.25] AND full
protection with the harvest intact** — a ~2% concession at a knife-edge
world that doesn't exist in the field, buying the customer base wherever
anchors are aggressive.

## Calibrated traffic (2026-07-10) — priority #1: the machine was ~10x too hot

paper/CALIBRATION-TARGETS.md's worst violation: arrival→purchase conversion
sat near 100% (nobody just browses), landing the STATIC arm at ~74
vends/day against the real US-average machine's **7-8 vends/day** (~$15.8
avg-machine revenue/day; SOTI 2025 + Cantaloupe Micropayment Trends 2025).
Fixed as an arrival-thinning knob, `WorldConfig.traffic_scale` — arithmetic-
ally identical to a price-independent conversion gate (most passers-by never
engage the machine at all, which is where the ~100%-conversion violation
actually lived): `CALIBRATED_TRAFFIC_SCALE = 0.14` (vend/world.py) lands
STATIC at **7.4–7.8 units/day** ("vends" = individual dispenses; a qty>1
sale is one deal, several vends) on both committed seeds, in the realistic
miscalibration cell. **traffic_scale=1.0 (the original profile) is kept and
RELABELED "smart-store P90"** — defensible only as a top-decile fresh-food
Smart Store machine, never as the average, and used below purely as the
pre-recalibration baseline for the proportional-shrink check.

Par stocks now scale with realized velocity (`PAR_COVER_DAYS=2.0`, floor 1
unit) — a competent operator sizes stock to what the machine actually
sells; freezing smart-store-P90 pars at 0.14× traffic would drown the
experiment in perishable spoilage no real operator accepts. The learner's
cold-start structural demand fallback (`expected_list_demand` in
scenario.py, used only before a SKU has any realized-sales history) is now
also `traffic_scale`-aware — otherwise an unsold SKU at 7-8 vends/day would
read a smart-store-P90-sized demand estimate, see zero "excess" stock, and
refuse to discount until it happened to sell once. `GvrPolicy`'s scarcity
solve got the same fix (not exercised by the run below, which is
static/a2a only, but left half-fixed otherwise).

### Per-machine deltas, calibrated traffic, realistic cell

`python3 -m vend.run --days 90 --seed {20260713,7} --arms static,a2a
--sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow --glut 0.15
--calibrated-traffic`

| seed | static units/day | a2a profit Δ/day (block=5 CI) | CS Δ/day |
|---|---:|---|---:|
| 20260713 | 7.70 | **+$0.60** [0.23, 0.97] | +1.90 |
| 7 | 7.38 | +$0.24 [−0.11, 0.59] | +1.55 |

**Honest reading:** seed 20260713's single-machine CI still clears zero;
**seed 7's does not** — [−0.11, 0.59] straddles it. At real single-machine
traffic, 90 days of ~7.4 vends/day is thin enough that one machine's paired
CI can look like a coin flip even though (see the route framing below) the
underlying effect is real and positive. This is the honest CI-touches-zero
result the recalibration was pre-registered to risk, and it happened.

Same cell at the current smart-store-P90 profile (traffic_scale=1.0), the
pre-recalibration baseline, reproduced against CURRENT HEAD (not the commit
this file's "weak-dominance" section above was written against — that
section's $2.30/$1.95 no longer reproduce exactly on this codebase, a
pre-existing drift unrelated to this recalibration, confirmed via `git
stash` A/B and not investigated further here):

| seed | a2a profit Δ/day (smart-store P90) |
|---|---|
| 20260713 | +$2.45 [1.51, 3.40] |
| 7 | +$2.44 [1.87, 3.01] |

### Does the delta shrink proportionally to traffic? Sub-proportionally

Traffic itself was thinned ~7.1× (1/0.14). A 25-independent-seed-machine
sweep (same cell, different customer-stream seed per "machine",
`base_seed + i*1009`) averages out single-machine noise:

| base seed | per-machine profit Δ/day (mean, sd, n=25) | % of static profit/day |
|---|---|---:|
| 20260713 | +$0.519 (sd 0.480), 24/25 machines positive | 5.99% |
| 7 | +$0.531 (sd 0.623), 21/25 machines positive | 5.67% |

vs. smart-store-P90's +$2.45/+$2.44 (≈4.6% of its own, much larger, static
profit base). The **dollar** edge shrank ~4.6–4.7×, sub-proportional to the
~7.1× traffic cut — and the **relative** edge (% of static profit) is
essentially preserved, slightly larger if anything. Read honestly: the
mechanism's per-vend edge holds up about as well in percentage terms at
realistic traffic as at the hot profile; it is the ABSOLUTE dollar number
that shrinks with the machine, exactly as paper/CALIBRATION-TARGETS.md
predicted.

### Route framing (what an operator running a fleet actually sees)

The 25-machine sweep above is a real (not hand-waved) route: summing the
daily a2a−static profit diff ACROSS the 25 independently-seeded machines
per day, then running the same `paired_ci(block=5)` on that SUMMED daily
series gives an honestly-computed route-level CI (no manufactured
independence assumption — these are 25 fully independent customer
streams):

| base seed | route (N=25) profit Δ/day | CI95 |
|---|---:|---|
| 20260713 | **+$12.97** | [11.02, 14.91] |
| 7 | **+$13.27** | [11.29, 15.25] |

Both route-level CIs clear zero comfortably even though one of the two
*single-machine* CIs above did not — exactly the CLT story: a single
machine's 90-day sample is noisy at 7-8 vends/day, a 25-machine route
averages it out. Projecting further (mean scales linearly with fleet size;
CI half-width scales √(M/25) under cross-machine independence — the same
approximation, not separately simulated at these sizes):

| machines | seed 20260713 | seed 7 |
|---:|---|---|
| 50 | +$26/day [23, 29] | +$27/day [24, 29] |
| 100 | +$52/day [48, 56] | +$53/day [49, 57] |
| 200 | +$104/day [98, 109] | +$106/day [101, 112] |

**Commercial story moves to the route, exactly as pre-registered**: a
50-200-machine operator earns a robust, statistically unambiguous
$26-106/day from the mechanism at real traffic, even though any ONE of
their machines' 90-day report could plausibly show a CI touching zero.

### Critical Q: does the censoring-aware learner converge at 7-8 vends/day? — NO, not within 90 days

Instrumented the A2A arm's `DemandLearner` (seed 20260713, the calibrated
cell) at checkpoints, and compared its day-90 per-SKU `daily()` estimate
against a 2000-day ground truth (a `StaticPolicy` run wearing the same
`DemandLearner` purely as an OBSERVER — static's board never reads it, so
this is an unbiased-by-mechanism per-SKU realized-demand estimate under the
identical catalog/traffic, on an independent customer-stream seed):

| SKU | true daily (2000-day) | A2A day-90 estimate | error |
|---|---:|---:|---:|
| cola | 0.895 | 3.953 | +342% |
| diet-cola | 1.764 | 4.965 | +181% |
| water | 8.294 | 7.953 | −4% |
| chips | 2.184 | 2.965 | +36% |
| candy | ≈0.000 | 0.605 | (true demand ≈0 — % error degenerate) |
| energy | 5.184 | 2.965 | −43% |
| sandwich | 3.456 | 3.872 | +12% |
| fruit-cup | 16.775 | 1.976 | **−88%** |

The estimate does not settle, either: `candy`'s own trajectory across
checkpoints is 0.98 → 2.96 → 17.64 → 0.14 → 0.04 → 1.57 → 0.61, day 10
through day 90 — it is still swinging by an order of magnitude at the END
of the 90-day run, not converging toward anything. **Verdict: no, the
learner does not meaningfully converge in this regime.** At ~7.5 total
vends/day spread over 8 SKUs, most SKUs see under one sale per day; the EWMA
smoother (`share_ewma=0.3`, an effective memory of a few days) was tuned
and validated at the smart-store-P90 profile (~74/day, ample per-SKU counts)
and simply cannot average out Poisson noise this sparse in a short window.
The machine-level `mult_hat` (today's-crowd posterior) fares somewhat
better — `prior_strength=8` anchors it — but at calibrated traffic that
prior is now comparable in size to a whole day's arrivals (5-8), so the
posterior is heavily prior-shrunk and correspondingly LESS responsive to
genuine day-to-day demand shocks than the same posterior was at the hot
profile (observed range across checkpoints: 0.696–1.334, day 10 → day 90,
consistent with real σ_shock=0.6 noise but likely still an under-reaction).

**Why the route-level result survives this anyway:** the A2A mechanism's
`min_gain`/`min_gain_frac` don't-negotiate-for-pennies buffer and
event-consistent disagreement design mean a badly-mis-estimated `excess`
mostly costs FOUND deals (a discount that should have cleared the buffer
doesn't), not BAD deals (the buffer keeps a noisy-but-inflated demand
estimate from leaking real margin) — so the mechanism degrades gracefully
toward static's own behavior on the SKUs its learner can't see clearly, and
the aggregate/route-level edge above is real. But per-SKU, per-machine
tactical claims about A2A's WHERE-it-wins story (the "excess vs. list-bound
stock" targeting P1.5/P1 sections describe) should not be trusted at
real single-machine traffic — that precision was validated at ~74
vends/day and does not transfer down.

## Fairness parameter sweep (2026-07-10) — priority #3: harvestability holds across the evidence bands

paper/CALIBRATION-TARGETS.md §5 flags the fairness model's two literature-
sourced parameters as the single most attackable consumer-model choice:
`loss_aversion` (λ, `vend/regulars.py`'s `LOSS_AVERSION=2.0` — meta-analytic
mean 1.955 [1.82, 2.10], price-specific λ=1.66, Hardie–Johnson–Fader 1993)
and reference-price `carryover` (`1 - REF_ALPHA_PAID`, currently 0.80 —
published band 0.47–0.65, Briesch et al. 1997 Table 6; HJF temporal 0.847).
Both are now `WorldConfig` fields (`loss_aversion`, `ref_alpha_paid`),
threaded through `RegularPool` to every spawned `Regular` (including
exogenous-replenishment joins), so the Fairness v2 experiment
(`WorldConfig(regulars=120, anchor_peak=True, anchor_mult=1.25)`, 90 days,
seed 2) is now sweepable without touching the module defaults committed
artifacts rely on.

Swept λ ∈ {1.66, 1.95, 2.00} × carryover ∈ {0.50, 0.65, 0.80, 0.85} — the
2.0/0.80 cell is the current default, included as the reference point, not
a new number:

| harvest $/day (a2a ×1.25 late profit − static-mixture "old world" late profit) | range across all 12 cells |
|---|---|
| **min** | $40.61 (λ=1.66, carryover=0.85) |
| **max** | $41.67 (λ=2.00, carryover=0.50) |
| current default (λ=2.0, carryover=0.80) | $41.38 |

**Harvestability holds across the full pre-registered evidence band — no
corner kills it.** The spread is $1.06/day, ≈2.6% relative, across every
combination of the published λ and carryover ranges: the safe-harvest
result is not sensitive to either parameter within the literature's own
uncertainty. Pool retention likewise stays in a narrow band across the
grid: 102–116 of 120 regulars active at day 90 (85–97%), churn 67–86 events
over 90 days, regardless of the exact λ/carryover point.

**Honest flag, unrelated to this sweep:** the grid's own λ=2.0/carryover=0.80
cell ($41.38/day harvest, 108/120 active, churn 75, reg_deals 1307) does
NOT reproduce the numbers this file's "Fairness v2" section headlined
above ($33/day harvest, 120/120 — "full" retention, reg_deals 1852).
Confirmed via `git stash` A/B on the identical config/seed that this is
pre-existing drift in the current HEAD codebase, present with or without
any change made for this task — something else changed the regulars
mechanism's behavior between when that section was written and now. Not
investigated or fixed here (out of scope for priority #3); flagged so the
sweep's baseline is read against CURRENT code, not that section's snapshot.
Reproduce: `vend/tests/test_vend.py`'s fairness-knob tests pin the plumbing;
the sweep itself is a direct script over `WorldConfig(regulars=120,
anchor_peak=True, anchor_mult=1.25, loss_aversion=λ, ref_alpha_paid=1-carryover)`.
