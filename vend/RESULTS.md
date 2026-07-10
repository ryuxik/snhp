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

> **CORRECTED 2026-07-10 (reproducibility gate #55 — the headline drifted and this is the honest fix).**
> The numbers first published here ($33/day harvest, pool 120/120 fully
> intact) were measured on a since-fixed learner and **no longer reproduce
> on current HEAD**. The corrected table is below; the two rows are kept
> side by side because the *direction* of the correction matters — the
> harvest got BIGGER but the "fully intact pool" claim did NOT survive.
> Full drift forensics are in the boxed note that follows the table.

| arm | late profit $/d | churned | active pool at day 90 | reg deals |
|---|---:|---:|---:|---:|
| static ×1.25 | 142.1 | 81 | 102 and falling | 1,145 |
| **a2a ×1.25 — CORRECTED (current HEAD)** | **143.1** | **75** | **108/120** | **1,307** |
| ~~a2a ×1.25 — as first published (pre-fix learner)~~ | ~~133.9~~ | ~~60~~ | ~~120/120~~ | ~~1,463~~ |
| static mixture (the old world) | 100.5 | 0 | 120 | 2,100 |

(seed 2, 90 days, `WorldConfig(regulars=120, anchor_peak=True,
anchor_mult=1.25)`, default 0.75/15% buffer. The original table's "1,852"
reg-deals figure does not reproduce even at the commit it was written
against — that commit yields 1,463; the $33 / 120-120 / churn-60 headline
figures do reproduce there exactly.)

**The corrected safe-harvest answer: ≈ +$42.6/day** (143.1 − 100.5) over
the old sticker world — HIGHER than the $33 first published — **but the
customer base is NOT fully intact: 108/120 active, churn 75.** This
matches the Fairness parameter sweep's own λ=2.0/carryover=0.80 diagnostic
cell (1,307 reg deals, 108 active, churn 75, ≈$41/day; the ~$1 gap to
$42.6 is late-window bookkeeping). The honest reading is worse for the v2
thesis than the original: under the corrected mechanism the a2a arm now
protects only *marginally* better than the raw ×1.25 board (108 vs 102
active, churn 75 vs 81, late profit 143.1 vs 142.1 — it harvests almost as
aggressively as the fairness-blind sticker). Quote protection still fires
more widely than the raw board (1,307 vs 1,145 reg deals) and good deals
still heal dissatisfaction, but **"quote protection keeps the pool fully
intact" is no longer supported** — it keeps ~6 more of 120 regulars than
raw harvesting does, not all of them.

### Drift forensics — WHICH commit moved it, WHY, and which number is right

Bisected `4abecf8..HEAD` over the fairness/learner machinery (worktree
checkout + a paired re-run of the diagnostic metrics at each commit). The
harvest is $33.4 / 1,463 / 120-active / 60-churn at Fairness v2's own base
commit (4abecf8), unchanged through the Attack-battery (36b5e20) and
Whitepaper (13e39a5, which added `quote_friction`/`quotes_seen` but with a
0.0 default they are behavior-neutral here) commits, and **flips to $42.6 /
1,307 / 108-active / 75-churn at commit `3a8fc4d` ("BLOCK B0 + the
censoring discovery")** — a *block*-focused commit that also edited
`vend/policies.py` + `vend/run.py`. The traffic recalibration (7ccccb6)
left it untouched, exactly as the sweep note suspected ("unrelated to the
recalibration"): 7ccccb6 reproduces 3a8fc4d's number, and the fairness
experiment runs at `traffic_scale=1.0`, which skips every recalibration
knob.

**Mechanism (causally isolated).** 3a8fc4d made `DemandLearner.end_day`
censoring-aware: on a sellout day a SKU's demand estimate now escalates to
`max(old, obs)·1.2` instead of the plain EWMA (a genuine, correct fix — a
sellout truncates observed sales below true demand, and the old rule read
that truncation as *weak* demand). The A2A shadow price consumes exactly
this estimate (`daily_fn=self.learner.daily`): a higher demand forecast
means less stock reads as "excess," so fewer/smaller protective
discount-quotes fire to regulars (reg deals 1,463→1,307), more regulars
face the raw ×1.25 board, churn rises (60→75), retention falls (120→108),
and realized margin/harvest rises (133.9→143.1). Proof it is *this* change
and nothing else: monkeypatching current HEAD to ignore the `censored` set
(i.e. restore the pre-3a8fc4d plain-EWMA rule) reverts the experiment
exactly to 133.9 / 1,463 / 120 / 60.

**Which number is correct: the NEW one (~$42/day).** The censoring-aware
learner is the intended, more-defensible mechanism — it fixed a real
adverse-selection bug (validated on the block twin-run and the vend win
cell, which rose to +$2.45 in the same commit). The original $33 headline
was produced by the buggy pre-fix learner that over-discounted because it
misread sellout truncation as slack demand. So $33 is stale and $42.6 is
the value the intended mechanism produces. The correction is not free
publicity, though: it *raises the harvest dollar figure while weakening the
"safe" adjective* — the same conservatism that fixed the forecast also
fires fewer protective quotes, so the "pool fully intact / quote protection
works" story of the original v2 must be downgraded to "quote protection
helps at the margin (108 vs 102 of 120) but does not shield the franchise
the way first claimed." Reproduce:
`scratchpad/repro_fairness.py` logic = `run_experiment(["static","a2a"], 90,
2, WorldConfig(regulars=120, anchor_peak=True, anchor_mult=1.25))`, compare
a2a late-window (days 60–89) profit against the static-mixture run.

Buffer frontier (documented, not hidden; these were the pre-fix figures and
the *relative* ordering is unaffected by the censoring fix): $1 flat →
perfect-cal tie (−$0.72) but regulars unprotected; 0.25/10% → strongest
protection, −$5.43 control leak; **default 0.75/15% → control −$1.98
[−2.70, −1.25]** — a ~2% concession at a knife-edge world that doesn't
exist in the field, buying whatever marginal franchise protection the
mechanism can offer wherever anchors are aggressive.

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

**Drift flag — NOW RESOLVED (see the corrected Fairness v2 section above,
gate #55):** the grid's own λ=2.0/carryover=0.80 cell ($41.38/day harvest,
108/120 active, churn 75, reg_deals 1307) does NOT reproduce the numbers
this file's "Fairness v2" section originally headlined ($33/day harvest,
120/120 "full" retention). Bisected to commit **`3a8fc4d` ("BLOCK B0 + the
censoring discovery")**, which made `DemandLearner.end_day` censoring-aware
(sellout days escalate the demand estimate instead of EWMA-ing it down).
That raises the A2A arm's forecast, shrinks perceived "excess" stock, and
fires fewer protective discount-quotes to regulars — hence more churn and a
higher realized harvest. The recalibration (7ccccb6) is confirmed
INNOCENT: it reproduces 3a8fc4d's number and the fairness run skips every
recalibration knob (`traffic_scale=1.0`). **The corrected (post-fix) number
is the right one** — the censoring fix repaired a real adverse-selection
bug — so this sweep's $40.61–41.67/day band is measured against the CORRECT
mechanism, and the original $33 was the stale/buggy figure. Reproduce:
`vend/tests/test_vend.py`'s fairness-knob tests pin the plumbing, and
`test_fairness_harvest_regression` now pins the harvest headline itself
against drift; the sweep is a direct script over `WorldConfig(regulars=120,
anchor_peak=True, anchor_mult=1.25, loss_aversion=λ, ref_alpha_paid=1-carryover)`.

## H4 (2026-07-10) — an LLM handed the machine (Project Vend, in sim)

Pre-registered gate: give a frontier model the machine's pricing seat and see
what it leaves on the table versus the engine. Arm `llm/1` = the machine
priced turn-by-turn by **claude-haiku-4-5** (intent mode, strict no-deal
protocol, format failures count against it); paired against `static/1` and
`a2a/1` (the SNHP engine) on the **same seeded population**. Realistic-cell
config (--sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow --glut 0.15),
seed 20260713. **Profile caveat: this run predates the traffic recalibration —
it is on the smart-store-P90 (hot) profile at 30 days, not the calibrated
7–8 vends/day at 90.** The absolute deltas are therefore the hot-profile
figures; the qualitative result is what carries.

| arm vs static | profit Δ/day | CI95 | consumer surplus Δ/day |
|---|---:|---|---:|
| a2a (SNHP engine) | **+$2.42** | [1.67, 3.18] | **+$9.46** |
| llm (haiku machine) | +$0.87 | [0.28, 1.46] | **+$0.00** |

**The finding: an LLM alone beats the sticker by under a dollar a day and
passes nothing to the customer.** The haiku machine negotiated 53 deals
(machine gain $26) vs the engine's 115 deals ($153) — it shaves a little
price for itself but does not find the joint-surplus-growing trades, so
consumer surplus moves $0.00. The engine grows the pie for *both* sides
(+$2.42 seller / +$9.46 buyer); the LLM-alone barely moves it and only for
the seller. This is the Project Vend lesson in miniature and it matches the
gauntlet's solo-vs-advised story exactly: the model alone is weak, the model
*advised by the engine* is strong (advised-haiku ≈ advised-opus on the
leaderboard). **Headline rerun still owed: calibrated traffic (7–8 vends/day)
at 90 days** — expected to shrink absolute deltas per the recalibration, with
the LLM's zero-consumer-surplus signature the durable qualitative result.
Artifact: `vend/h4-llm.json` (non-deterministic — API-priced; not a
byte-reproducibility target).

## The strongest posted baseline (2026-07-10) — referee item #48 / CRITICAL-ANALYSIS §2: **the disclosure claim weakens honestly on profit, hardens on welfare**

Pre-registered gate: "disclosure beats inference" is only earned if
inference gets its BEST shot. Every posted/computed arm so far was weak —
`gvr` prices each SKU independently against a uniform per-SKU demand share
(P0's diagnosis: it can't see cross-SKU cannibalization, and it LOST to
static, −$1.71/−$2.07/day at the hot profile). So we built the posted arm
that fixes exactly that and ran it against nego at the realistic cell.

**`posted` (`vend/policies.py::StrongPostedPolicy`) — a choice-model-aware,
JOINTLY-optimized board:** (a) it models each buyer as choosing the
best-surplus bundle across the WHOLE board plus the bodega outside option
(the same discrete choice `world.best_bundle` makes the simulated consumer
make), via a seeded synthetic panel drawn from the operator's own lognormal
WTP belief — so lowering one SKU's price steals demand from its substitutes;
(b) it optimizes the entire price vector jointly by coordinate ascent over
the panel's expected profit, warm-started at the calibrated list board;
(c) it uses the SAME demand information the a2a arm has — the operator's
`wtp_mu_est` (what set the sticker) for the crowd belief, and the IDENTICAL
`expected_list_demand(mult_hat, share, daily)` call the a2a arm makes for
the scarcity shadow value. It sees the crowd; it just never sees the
individual buyer's wallet — and that missing signal is exactly the
disclosure value this experiment isolates. (Deterministic; result invariant
to panel size 200/400/800; discount-only and floored at opportunity cost,
type-enforced like every arm.)

### Realistic cell — calibrated traffic, 90 days, block-5 CIs
`--sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow --glut 0.15 --calibrated-traffic`

| pairing | seed 20260713 profit Δ/day | seed 7 profit Δ/day | CS Δ/day (A / 7) |
|---|---|---|---|
| posted − static | **+$0.65** [0.33, 0.98] | +$0.29 [−0.04, 0.61] | +1.02 / +0.64 |
| a2a − static | **+$0.60** [0.23, 0.97] | +$0.24 [−0.11, 0.59] | +1.90 / +1.55 |
| **a2a − posted** (the test) | **−$0.05** [−0.39, 0.29] | **−$0.05** [−0.31, 0.22] | **+0.88** [0.44,1.31] / **+0.90** [0.36,1.45] |

(The a2a−static row reproduces the committed recalibration table
[+$0.60/+$0.24] to the cent — the harness is faithful; adding the posted
arm did not perturb the paired streams, as it must not.)

### Robustness — hot "smart-store P90" profile, 90 days
| pairing | seed 20260713 | seed 7 |
|---|---|---|
| posted − static | **+$3.55** [2.55, 4.54] | **+$2.59** [2.13, 3.05] |
| a2a − static | +$2.45 [1.51, 3.40] | +$2.44 [1.87, 3.01] |
| **a2a − posted** | **−$1.09** [−2.04, −0.14] | **−$0.15** [−0.65, 0.35] |
| a2a − posted, CS | +$4.96 [3.45, 6.47] | +$5.44 [4.00, 6.88] |

### The verdict (honest, both directions)

1. **The strong posted arm CLOSES the profit gap — the disclosure-beats-
   inference claim does NOT survive as a SELLER-PROFIT claim.** On the
   realistic cell the a2a−posted profit CI includes zero on both seeds
   (−$0.05/day); at the hot profile the posted board even significantly
   *out-earns* nego on seed A (posted beats static by +$3.55 vs nego's
   +$2.45; a2a−posted −$1.09 [−2.04, −0.14]). The entire "+$0.60/+$2.45
   nego-beats-the-sticker" profit edge that earlier sections leaned on is
   reproduced — sometimes exceeded — by a posted price that merely models
   cross-SKU substitution and optimizes the board jointly. **This is the
   pre-registered outcome that weakens the claim, and we report it.** It
   also *completes P0's diagnosis*: gvr lost because of per-SKU
   independence; the same posted-dynamic idea made choice-aware and jointly
   optimized wins — the bug was the modeling, not the medium.

2. **What HARDENS instead: consumer surplus / total welfare.** On CS the a2a
   arm beats the strong posted arm on all four seed×profile points and every
   CI excludes zero (+$0.88/+$0.90 calibrated, +$4.96/+$5.44 hot).
   Negotiation grows the pie for BUYERS in a way a single posted price
   structurally cannot: it price-discriminates in the buyer's favor
   per-transaction (bigger baskets, each buyer's own best substitution,
   marginal-customer recruitment against a zero counterfactual), delivering
   more welfare at equal-or-lower seller profit — a Pareto improvement over
   the posted board. **The realized value of disclosure at a vending machine
   is a consumer-surplus edge, not a seller-profit edge.** That is a weaker
   and more defensible claim than the one we started with, and it is the one
   the evidence supports.

3. **Note the information asymmetry cuts the RIGHT way.** The posted arm has
   strictly LESS information than nego per transaction — it knows only the
   operator's crowd belief `wtp_mu_est`, while nego sees each buyer's actual
   disclosed WTP and walk cost. It ties nego on profit anyway. So the tie is
   not bought with an information advantage; it hardens the finding — even
   knowing strictly less, a choice-aware posted board matches nego's profit.

### The parking asymmetry does NOT reproduce here (and why)

The robustness finding to check: at parking, nego carrying the SAME wrong
forecast beat posted because a bad quote is DECLINED while a bad posted
price silently bleeds. Here both arms carry the same non-converging learner
(this file's calibrated-traffic section documents per-SKU demand errors of
−88%…+342% at day 90), yet posted TIES/BEATS nego on profit — the asymmetry
is absent. The structural reason: the vend posted arm is **discount-only
from a profit-CALIBRATED list ceiling**, so its downside is bounded by the
strong static optimum — a "bad" posted price reverts *toward* the
already-good sticker; it cannot bleed *below* static the way a mispriced
parking meter can. The "bad posted price bleeds" channel that made nego win
at parking is shut whenever the posted baseline is a discount-from-a-good-
ceiling, so nego's decline-a-bad-quote advantage buys it nothing on profit
in this venue. (Where it still pays: consumer surplus, per finding #2.)

Reproduce: `python3 -m vend.run --days 90 --seed 20260713 --arms
static,posted,a2a --sigma-cal 0.3 --sigma-rate 0.6 --sigma-wtp 0.3 --dow
--glut 0.15 --calibrated-traffic` (and `--seed 7`), then read the a2a−posted
paired block CI. `posted` = `StrongPostedPolicy`; the a2a−posted pairing is
computed off the per-day series (the runner pairs every arm against arm[0]).

## Split-tilt frontier (2026-07-10) — Task #65: "who pays us, and how far can we tilt before it breaks"

**The business question.** The strong posted board TIES the engine on seller
profit (a2a−posted −$0.05/day, CI includes zero — see the section above); the
engine's durable edge is CONSUMER SURPLUS, not seller profit. A merchant pays
for SELLER profit. `scenario.nash_quote` split the created surplus SYMMETRICALLY
(Nash product `gs·gb`, no seller knob). So we added one: a seller bargaining
weight **w ∈ [0.5, 1.0]** that generalizes the split to the ASYMMETRIC Nash
solution — the chosen outcome maximizes `gs**w · gb**(1−w)`, where gs, gb are
the seller/buyer gains ABOVE their disagreement points. w=0.5 = the symmetric
split (default; **byte-identical** to the committed artifact — special-cased to
the exact `gs·gb` and pinned by test); w=1.0 = seller takes ALL surplus above
the buyer's floor. The tilt only reallocates surplus ABOVE the disagreement —
feasibility still requires gs≥0 AND gb≥0, and the outcome space is still
discount-only (floor…list) — so it **never** prices below the buyer's outside
option or above the sticker (type-/test-enforced). It is the monetization knob:
how much of the jointly-created pie the merchant keeps.

**The sweep.** Realistic calibrated cell (`--sigma-cal 0.3 --sigma-rate 0.6
--sigma-wtp 0.3 --dow --glut 0.15 --calibrated-traffic`), 90 days, both seeds
(20260713, 7), pooled block-5 CIs. Baselines run once; the a2a arm re-run at
each w; the liar battery (disclosed-WTP scale {0.55, 0.75, 1.0, 1.25, 1.5} ×
free-outside-claim {no, yes}, every buyer deviating) re-run at each w to find
the buyer's best-response gain-from-lying. `python3 -m vend.run --tilt`
(→ `vend/tilt.json`).

### The frontier (a2a arm vs the strong posted board, $/day, pooled both seeds)

| w | SELLER Δ (a2a−posted) | CONSUMER-SURPLUS Δ (a2a−posted) | WTP-understatement lie gain | attested REALIZED seller Δ |
|---|---|---|---|---|
| 0.50 | −0.05 [−0.26, 0.16] | **+0.89** [0.56, 1.22] | −0.16 [−0.59, 0.26] | −0.05  (banked) |
| 0.60 | +0.24 [0.03, 0.44] | +1.14 [0.77, 1.50] | +0.12 [−0.37, 0.61] | +0.24  (banked) |
| **0.70** | **+0.61 [0.37, 0.85]** | **+1.04** [0.67, 1.41] | +0.39 [−0.02, 0.79] | **+0.61  (banked — PEAK)** |
| 0.80 | +0.89 [0.65, 1.12] | +0.79 [0.38, 1.20] | **+0.69 [0.21, 1.17]** | −0.78  (COLLAPSED) |
| 0.90 | +1.19 [0.93, 1.46] | +0.68 [0.27, 1.09] | +0.73 [0.28, 1.17] | −0.74  (COLLAPSED) |
| 0.95 | +1.26 [0.98, 1.53] | +0.53 [0.12, 0.94] | +0.90 [0.46, 1.34] | −0.74  (COLLAPSED) |
| 1.00 | +1.27 [1.04, 1.50] | +0.52 [0.19, 0.84] | +0.80 [0.41, 1.18] | −0.63  (COLLAPSED) |

*SELLER Δ* is the HONEST (attested, truthtelling) a2a arm's profit over posted.
*attested REALIZED seller Δ* is what the seller actually banks once the engine
attests the OUTSIDE OPTION (blocking the w-robust free-walk leak, which is what
attestation prices out) but WTP disclosure is only as good as the incentive to
tell the truth: below the WTP-IC break buyers stay honest and the seller banks
the honest number; at/after it buyers understate and the seller gets the
understatement-arm profit. Bold CI = excludes zero. (Against the plain STATIC
sticker the tilt looks even stronger — seller Δ +$0.42→+$1.74/day, CS Δ
+$1.35→+$1.97/day — but posted is the honest, referee-hardened baseline.)

### The three break-points

1. **CS crosses zero: NEVER (in [0.5, 1.0]).** The a2a−posted consumer-surplus
   advantage falls with w (+$0.89 → +$0.52/day) but stays strictly positive
   even at full seller-take (w=1.0). The tilt cannot turn the engine into a
   pure-extraction tool RELATIVE TO THE POSTED BOARD: the disagreement discipline
   floors every buyer at their outside option, and negotiation still grows the
   pie (more deals recruited — 73→146 negotiated/day — better substitution,
   bigger baskets), so buyers stay net-ahead of the discounted posted board.
   "Both benefit" survives the whole dial. (CS even peaks at w=0.6, +$1.14 —
   the extra recruited deals outrun the per-deal buyer-share erosion early.)
2. **IC break (WTP disclosure): w ≈ 0.8.** At w=0.5 the pure WTP-understatement
   attack LOSES the buyer money (−$0.16/day, CI includes zero — the "H3 inverted"
   result holds: understating denies you deals the buffer would have cleared).
   As the mechanism favors the seller, the incentive to claw surplus back by
   understating grows monotonically (−0.16 → +0.90) and becomes the buyer's
   significant best response (CI lower bound > 0) at **w=0.8**. The seller-favoring
   mechanism destroys the WTP disclosure it runs on. (A SEPARATE, w-robust leak
   — claiming a free outside option — pays a little at every w, +$0.49→+$1.16;
   it is not created by the tilt and is exactly what outside-option attestation
   prices out, so it is excluded from the WTP-IC break and handled by the
   attestation tier.)
3. **Profit peak: w = 1.0 on paper, w = 0.7 in reality.** The HONEST-arm profit
   rises monotonically and saturates at w=1.0 (+$1.27/day) — but that number is
   a MIRAGE if buyers can lie. The ATTESTED REALIZED profit peaks at **w = 0.7
   (+$0.61/day [0.37, 0.85])** and then COLLAPSES to −$0.78/day at w=0.8 the
   instant WTP-understatement becomes the buyer's best response. The predicted
   peak-then-collapse is exactly here. (If the outside-option leak is ALSO
   unattested, realized seller profit is negative at every w, −$0.6…−$0.9/day —
   strategic buyers neutralize the tilt entirely from the start; attestation is
   not optional garnish, it is what makes any of the tilt collectible.)

### THE DELIVERABLE — max defensible seller-profit gain

Honest region = {CS ≥ 0 (all of [0.5,1.0]) AND WTP-disclosure IC intact
(w < 0.8) AND CS ≥ half the symmetric level ($0.45, satisfied through w=0.7)}.

> **Max defensible seller-profit gain: +$0.61/day [0.37, 0.85] at w = 0.70**,
> vs the strong posted board — a real, CI-excludes-zero seller gain (an ~+6%
> lift on the ~$10.5/day realized profit), delivered WHILE consumers stay
> +$1.04/day [0.67, 1.41] ahead and WTP disclosure stays incentive-compatible.

That is the growth-sharing region — what a merchant pays for, banked as seller
profit, without becoming RealPage: it never prices below a buyer's outside
option, it leaves the buyer strictly better off than the best posted board, and
it does not corrupt the disclosure it runs on. Push past w≈0.8 and all three
guarantees fail together — the paper profit keeps rising but buyers begin to
lie, and the REALIZED profit collapses below the symmetric tie. **The
monetization mechanism is a BOUNDED tilt (w≈0.7), gated by attestation** (which
banks the honest number by pricing out the outside-option leak). Pre-registered
prediction — "a small tilt buys real seller profit while CS>0 and IC holds; a
large tilt collapses disclosure and the profit evaporates as buyers lie" —
**confirmed on all three axes.**

Reproduce: `python3 -m vend.run --tilt --days 90` (writes `vend/tilt.json` with
the full per-w frontier, per-deviation liar battery, and break-points). Tests:
`vend/tests/test_vend.py::test_seller_weight_*`, `::test_run_tilt_is_deterministic`,
`::test_tilt_frontier_artifact_shows_the_predicted_shape`.

## Surge value without surging (2026-07-10) — Task #66: **the strong thesis is PARTIALLY REFUTED, and the refutation is the finding**

**The pre-registered thesis.** Single-price categories (bodega / vending / boba /
fashion) forfeit time-of-day + heterogeneity value because a VISIBLE posted surge
on everyday goods is a fairness violation (Coca-Cola's 1999 hot-day vending PR
disaster; Wendy's 2024 dynamic-pricing backlash; Kahneman-Knetsch-Thaler dual
entitlement). The CLAIM under test: SNHP captures that same value INVISIBLY as an
individual discount-from-a-peak-anchor, so the fairness churn that makes the
visible surge *net-negative* does NOT fire for the engine — "surge value without
surging," and therefore the fairness apparatus is the economic engine (not
deletable transitional scaffolding — the rebuttal to the "delete fairness"
critique).

**The design.** Three arms + one diagnostic, same seeded 120-regular franchise,
paired seeds (20260713, 7), 90 days, clean stationary world (the Fairness-v2
regime the churn machinery was validated in — no calibration/shock noise to muddy
the churn signal), block-5 pooled CIs. Everyday reference = the all-day
profit-optimal single price (what regulars remember, what STATIC posts).
- **STATIC** — the single all-day sticker these categories run (board == reference
  ⇒ no above-reference event, ≈0 churn).
- **POSTED-SURGE** (`PostedSurgePolicy`) — a VISIBLE peak-surcharge board: the
  everyday price off-peak, ABOVE the reference at peak (a bar / parking / happy-hour
  surge). `surge_to_ceiling` sets how far the peak surcharge reaches (mild
  profit-max vs the aggressive anchor ceiling).
- **ENGINE** (`a2a`, `anchor_peak`) — invisible individual discount-from-a-PEAK-
  anchor: the ceiling IS the peak anchor, quotes discount from it. The hypothesis:
  "no above-reference event."
- **ENGINE-REF** (diagnostic: `a2a` on the all-day catalog) — the fairness-SAFE
  engine whose sticker == the everyday reference, so it NEVER posts above the
  reference; it captures value only as discounts BELOW it.

Captured value is isolated from the churn cost with a **churn-OFF counterfactual**
(`WorldConfig.churn_rate=0`, pool held full): churn-off gross-margin Δ vs static =
pricing capture before any permanent exit; churn-ON profit Δ = capture net of
churn; their difference is the fairness (churn) cost.

### The 3-arm table (pooled both seeds, block-5 CIs, $/day vs STATIC)

| anchor | arm | captured (churn-off) | NET profit (churn-on) | consumer surplus | churn (s7013/s7) | day-90 active | fairness cost/day |
|---|---|---|---|---|---|---|---|
| — | static | +0.00 | +0.00 | +0.00 | 0 / 0 | 120 / 120 | 0.00 |
| — | **engine-ref** (never > ref) | **−0.10** [−0.25, 0.04] | −0.10 | +0.01 | **0 / 0** | **120 / 120** | 0.00 |
| **×1.0** | surge (mild, profit-max) | +2.83 [2.73, 2.93] | +2.77 | −0.05 | 5 / 2 | 120 / 120 | −0.07 |
| **×1.0** | surge (to ceiling) | +6.98 [6.91, 7.04] | +6.89 | +0.54 | 8 / 4 | 120 / 120 | −0.09 |
| **×1.0** | **engine** | **+8.24** [8.01, 8.47] | **+8.24** | **+1.15** [0.51, 1.79] | 11 / 5 | 119 / 120 | 0.00 |
| **×1.25** | surge (to ceiling) | +32.88 [31.7, 34.1] | **+29.75** [29.1, 30.4] | **−12.16** [−13.4, −11.0] | 48 / 47 | 118 / 118 | −3.14 |
| **×1.25** | **engine** | +40.89 [38.3, 43.5] | **+36.69** [34.5, 38.9] | **−15.93** [−16.9, −15.0] | 72 / 71 | **102 / 114** | −4.20 |

Head-to-head (engine − surge, paired, pooled): at ×1.0 **net +$1.36/day [1.11,
1.60]**, CS **+$0.61**; at ×1.25 net +$6.94 [5.17, 8.71], CS **−$3.76**.

### The verdict — honest, both directions

1. **The visible surge does NOT go net-negative from churn — the strong premise
   FAILS.** At every anchor the posted surge is net-POSITIVE (+$2.77 → +$29.75/day
   vs static, CIs clear). Even the aggressive ×1.25 harvest surge, which churns 95
   regulars, nets +$29.75/day: the captive harvest SURVIVES the churn because the
   survivors pay more and the 0.7/day exogenous replenishment holds the pool at
   118/120. There is no self-destructing surge here. The pre-registered "fairness
   churn makes the visible surge net-negative in these categories" is **not
   supported by the model.**

2. **The peak-anchor engine does NOT escape the surge's churn — it churns MORE.**
   At ×1.25 the engine churns **143** (72+71) vs the surge's **95** (48+47) and
   retains **fewer** regulars (102/114 vs 118/118). The reason is mechanical and
   fatal to the "no above-reference event" premise: the engine's *fallback board*
   IS the flat peak ceiling ($2.56 cola vs the $1.95 reference), so a no-quote
   regular faces an above-reference price **all day**, while the surge is above
   reference only at **peak** (off-peak == the everyday reference, fairness-neutral).
   **Consumers react to the reference-price VIOLATION (the level), not to
   posted-vs-negotiated VISIBILITY.** An aggressive discount-from-a-high-anchor is
   a reference violation just like a visible surge — worse, because it is
   all-day. Unit-tested: a surge board above ref×1.10 accrues dissatisfaction,
   but a discount quote *below* the reference is a gain-with-glow that *heals* it
   (`test_surge_board_fires_fairness_churn_but_discount_quote_does_not`) — so the
   engine's aggregate churn is its FALLBACK board, not its discounts.

3. **The engine still NETS MORE than the surge — but via VALUE (heterogeneity
   capture), not retention.** engine−surge net is +$1.36/day (×1.0) / +$6.94/day
   (×1.25), CIs clear, driven by the churn-off *captured*-value edge (+$1.27 /
   +$8.01) — individual price discrimination extracts more per transaction. At
   ×1.25 the engine's fairness cost (−$4.20/day) is WORSE than the surge's
   (−$3.14), and it hurts consumers MORE (CS −$15.93 vs −$12.16): in the harvest
   zone the engine is the *harsher* extractor, not the fairer one.

4. **What SURVIVES — the modest-anchor both-win is real.** At the mild peak-optimum
   anchor (×1.0) the engine captures modestly MORE value than the posted surge
   (+$8.24 vs +$6.89 net) at BETTER consumer surplus (+$1.15 vs +$0.54) with the
   whole franchise retained (119-120/120, churn negligible for both). engine−surge
   +$1.36/day [1.11, 1.60] AND CS +$0.61 — a genuine both-sides-win over the visible
   surge, on the within-hour heterogeneity the surge structurally cannot touch
   (referee #48). This is the deployable "who pays us": the merchant pays because,
   at a defensible anchor, the engine out-earns the visible time-of-day board AND
   leaves customers better off.

5. **"Fairness is the economic engine" — SUPPORTED in the load-bearing sense, and
   that still rebuts "delete fairness."** The fairness apparatus is the BINDING
   economic constraint on BOTH arms: churn, fairness cost, and CS all track the
   *anchor / price level*, not the frame (churn 5→143, fairness cost $0→−$4.20/day,
   CS +$1.15→−$15.93/day as the anchor climbs 1.0→1.25), for surge and engine
   alike. Delete it (the Musk critique) and the model predicts the ×1.25 harvest is
   free and painless — contradicting the empirical Wendy's/Coke backlash the whole
   apparatus is calibrated to. And the ENGINE-REF diagnostic locates the ONE
   fairness-free lever: individual discounts BELOW the reference (never above) —
   which capture **+$0.00** here (churn-off −$0.10, zero churn) because the clean
   world's all-day sticker is already profit-optimal, so the only extra value at a
   captive machine is captive HARVEST, which costs fairness in ANY frame. Where the
   sticker is genuinely MIS-SET (the realistic-miscalibration cells) that same
   below-reference lever is worth +$0.60–2.45/day at CS-positive (referee #48's
   result) — the fair value SNHP actually captures.

**Sharpened, defensible claim (what the evidence supports):** the value a
single-price *captive* machine forfeits is, in a calibrated world, captive-harvest
value; capturing it costs fairness churn visibly OR invisibly — there is no free
"surge without surging." SNHP's fairness-free edge is EFFICIENCY capture
(below-reference discrimination that recruits marginal buyers and redistributes to
them), which is CS-positive and churn-free, and it is real where the sticker is
mispriced. The fairness apparatus is the economic engine because it is what taxes
the harvest identically in every frame and channels the fair value into discounts —
the very line that keeps SNHP from being RealPage. The strong "posted surge
self-destructs, engine dodges it via invisibility" claim is **refuted**; the modest-
anchor both-win and the non-deletability of fairness **stand.**

Reproduce: `python3 -m vend.run --surge --days 90` (writes `vend/surge.json` — the
full two-anchor frontier, both surge intensities, the engine-ref diagnostic, and
the churn-on/off decomposition). Tests: `vend/tests/test_vend.py::test_surge_*`,
`::test_worldconfig_churn_rate_matches_regulars_module`,
`::test_regular_pool_honors_churn_rate`, `::test_posted_surge_is_a_visible_above_reference_board`,
`::test_run_surge_is_deterministic`.
