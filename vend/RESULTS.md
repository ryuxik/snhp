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

## Task #68B (2026-07-10) — the HARDER IC battery: sup-over-types, the adaptive liar, and the MDE that hid the leak

The committed liar sweep and attack battery above report a **population mean**
over an all-liar arm. A referee (MIT theory) objected — correctly — that a mean
*washes profitable liars out*: a lie that pays only on the rare excess day, or
only for a high-outside-option type, is diluted by the many days/types on which
the same uniform lie forfeits the buyer's board disagreement. Task #68B builds
the instrument the mean cannot substitute for (`vend/battery.py`; artifact
`vend/battery.json`; 6 seeds × 180 measured days after a 30-day learner burn-in,
realistic calibrated cell, **attestation OFF**, discount-only ON, finite stock).

**The unilateral deviation probe.** The world is held HONEST and the learner
converged; at each buyer's decision node we compute — against the *identical*
state — the honest quote and each counterfactual-lie quote, and the buyer's
TRUE-preference realized welfare under each. The deviation gain
`lie_true − honest_true` holds all other buyers and the state fixed: the exact
best-response object, with zero state contamination (an all-liar arm cannot
isolate it — there the state moves too). Deviations: uniform WTP-scaling, the
**state-conditioned adaptive** liar (understate only where visible stock is high
— concentrate the exploit on excess days), an **oracle-excess** adaptive
(understate exactly the shadow-excess SKUs — the strongest possible attacker),
**per-SKU** favorite-only and perishables-only, and the free-outside-option
claim — each with the cond-(d) walk channel ON and OFF so the WTP and
outside-option channels never hide behind each other.

**Result — the pooled mean HID a real, small, buffered leak (the sup-over-types
finds it):**

| deviation (WTP channel, walk OFF) | pooled mean $/day | **SUP over types** (excess stratum) | sig? |
|---|---|---|---|
| uniform WTP 0.55× | −0.15 [−0.25, −0.05] | **+0.17 [0.09, 0.25]** | **yes** |
| adaptive WTP (visible stock ≥1.2·par) | −0.11 | −0.01 [−0.05, 0.03] | no |
| adaptive WTP (oracle-excess) | −0.29 | **+0.15 [0.07, 0.23]** | **yes** |
| per-SKU favorite-only | −0.22 | −0.00 | no |
| perishables-only | −0.46 | −0.08 | no |
| **free-walk only (cond d)** | **+0.49 [0.40, 0.59]** | +0.49 (all strata) | **yes** |

Replicated in the high-excess stress cell (glut 0.4): the excess-stratum WTP sup
holds at +0.15 (uniform) / +0.20 (oracle). **Answers to the three questions the
mean could not:**

1. **Does honesty survive the adaptive + per-SKU liar at finite stock?** On the
   WTP channel, *the visible-stock adaptive and per-SKU-favorite deviations do
   NOT beat the plain uniform lie* — their sup is non-significant (≤0). Only an
   **oracle** who sees the true shadow-excess set matches the uniform lie
   (+0.15). So the decisive untested deviation **concentrates but does not
   enlarge** the leak. Honesty is NOT strictly a best response — but the leak is
   the same small residual whether uniform or adaptively targeted.
2. **The sup-over-types worst-case number.** +\$0.15–0.20/day for the
   excess × high-outside type on the WTP channel (~1–2% of the ~\$9/day CS);
   +\$0.49/day for the free-outside-option (cond-d) channel. The **pooled mean is
   negative** (−0.15) — it genuinely hid the profitable type. This matches the
   §3/THEOREM-IC (a′) prediction exactly: a bounded excess-unit leak survives on
   the high-rent SKUs (ℓ−c > 2β: sandwich, cola, candy) and is absent on the
   low-rent ones (water, ℓ−c < 2β).
3. **The MDE (why the committed sweep read a clean tie).** The committed liar
   sweep (30 days, 1 seed → 6 blocks, sd_block ≈ 0.87) has an 80%-power
   two-sided **MDE of \$1.25/day** — it *structurally could not detect* a
   \$0.15–0.30 exploit; a tie was the only possible reading. The battery
   (216 pooled blocks, sd_block ≈ 0.58) has **MDE \$0.11/day** on the excess
   stratum, which is why the +0.17 leak becomes visible. The refinement is a
   matter of *power*, and the proof (THEOREM-IC §4.3) says where to point it.

**Warm vs cold learner (the "run to convergence" ask) — a NULL.** The all-liar
population arm measured on a cold learner (days 0–60) and a learner converged on
the liar population (days 40–100) are statistically identical (free-walk arm:
cold +0.22 vs warm +0.22; WTP-only arms ≈0 in both). A learner adapted to liars
opens no leak the cold learner's over-forecast hid — the leak is structural, not
a learner transient.

**The refinement to the Proposition.** THEOREM-IC.md proves the corrected
single-unit characterization: the four §3 conditions are necessary-not-
sufficient; strict emergent IC additionally requires **(a′) ℓ − c ≤ 2β** (the
list-minus-shadow-cost rent at most twice the min-gain buffer). Where it holds
(scarce units always; low-rent excess units) honesty is a *strict* best
response; where it fails (high-rent/perishable excess units) a *bounded* leak
≤ ℓ−c−β survives, ≈+\$0.15–0.20/day at the sup — closed by a larger buffer or
WTP attestation, not by outside-option attestation alone. This is the "5th
condition" the referee's counterexample pointed at, now proven and measured.

Reproduce:

```
python3 -m vend.battery --probe --warm --seeds 20260713,7,20260710,101,42,2026 \
    --burn 30 --measure 180 --out vend/battery.json
```

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

(Updated 2026-07-10 for the review-fix batch — the MATERIAL fix here is the
strong posted arm's synthetic-panel OUTSIDE option, which was machine-stock-
masked and only over in-stock SKUs; it now ranges over the WHOLE catalog at
full QTY_CAP with NO machine-stock cap, exactly like the real consumer's
outside option at run.py:163. Net effect on the posted arm's *aggregate*
profit is tiny [seed A 912.9→911.9 isolated, ≈−$0.01/day: it prices a hair
more competitively where SKUs sell out, but the 12-rung discretization and
the discount-only-from-a-calibrated-ceiling structure bound the change]; the
a2a arm gained a bit more from the OTHER fixes [disagreement stock-cap +
escalator ceiling], so the a2a−posted headline nudged from −$0.05 to
+$0.12/+$0.04 — still a TIE both seeds. The CS edge shrank modestly but stays
significant everywhere. Numbers below are post-fix.)

| pairing | seed 20260713 profit Δ/day | seed 7 profit Δ/day | CS Δ/day (A / 7) |
|---|---|---|---|
| posted − static | **+$0.63** [0.27, 0.99] | +$0.32 [0.03, 0.60] | +1.06 / +0.68 |
| a2a − static | **+$0.75** [0.43, 1.07] | +$0.35 [0.03, 0.68] | +1.87 / +1.33 |
| **a2a − posted** (the test) | **+$0.12** [−0.19, 0.44] | **+$0.04** [−0.23, 0.30] | **+0.81** [0.28,1.35] / **+0.66** [0.21,1.11] |

(The a2a−posted profit CI includes zero on BOTH seeds — still a tie, the sign
merely flipped from the committed −$0.05. Was: a2a−posted −$0.05/−$0.05 profit,
CS +0.88/+0.90. The tie survives; the CS win survives, at a slightly smaller
margin on seed 7.)

### Robustness — hot "smart-store P90" profile, 90 days
| pairing | seed 20260713 | seed 7 |
|---|---|---|
| posted − static | **+$3.70** [2.70, 4.70] | **+$2.60** [2.15, 3.05] |
| a2a − static | +$2.55 [1.44, 3.66] | +$2.30 [1.58, 3.02] |
| **a2a − posted** | **−$1.15** [−2.14, −0.16] | **−$0.30** [−0.83, 0.22] |
| a2a − posted, CS | +$4.12 [2.87, 5.38] | +$5.49 [3.97, 7.00] |

(Was: posted−static +3.55/+2.59, a2a−static +2.45/+2.44, a2a−posted
−1.09/−0.15, CS +4.96/+5.44. The hot-seed-A story is UNCHANGED: the posted
board still significantly out-earns nego [a2a−posted −$1.15, CI excludes zero],
exactly as pre-fix. a2a still wins CS on all four seed×profile points.)

### The verdict (honest, both directions)

1. **The strong posted arm CLOSES the profit gap — the disclosure-beats-
   inference claim does NOT survive as a SELLER-PROFIT claim.** On the
   realistic cell the a2a−posted profit CI includes zero on both seeds
   (+$0.12/+$0.04/day — a tie); at the hot profile the posted board even
   significantly *out-earns* nego on seed A (posted beats static by +$3.70 vs
   nego's +$2.55; a2a−posted −$1.15 [−2.14, −0.16]). The entire "+$0.60/+$2.45
   nego-beats-the-sticker" profit edge that earlier sections leaned on is
   reproduced — sometimes exceeded — by a posted price that merely models
   cross-SKU substitution and optimizes the board jointly. **This is the
   pre-registered outcome that weakens the claim, and we report it.** It
   also *completes P0's diagnosis*: gvr lost because of per-SKU
   independence; the same posted-dynamic idea made choice-aware and jointly
   optimized wins — the bug was the modeling, not the medium.

2. **What HARDENS instead: consumer surplus / total welfare.** On CS the a2a
   arm beats the strong posted arm on all four seed×profile points and every
   CI excludes zero (+$0.81/+$0.66 calibrated, +$4.12/+$5.49 hot).
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
profit (a2a−posted +$0.12/+$0.04/day, CI includes zero both seeds — see the
section above); the engine's durable edge is CONSUMER SURPLUS, not seller profit. A merchant pays
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

(Updated 2026-07-10 for the review-fix batch; posted baseline + a2a dynamics
both moved. The SHAPE is unchanged — tie at w=0.5, monotone-up seller profit,
CS>0 throughout, IC breaks before w=1.0, attested-realized peak-then-collapse —
but the honest region is TIGHTER: the WTP-understatement lie now becomes the
buyer's significant best response one grid-point earlier, at w=0.70 [was 0.80],
so the peak/collapse moves to w=0.60 and the deliverable shrinks from +$0.61 to
+$0.35/day.)

| w | SELLER Δ (a2a−posted) | CONSUMER-SURPLUS Δ (a2a−posted) | WTP-understatement lie gain | attested REALIZED seller Δ |
|---|---|---|---|---|
| 0.50 | +0.08 [−0.12, 0.28] | **+0.73** [0.40, 1.07] | −0.14 [−0.50, 0.22] | +0.08  (banked) |
| **0.60** | **+0.35 [0.13, 0.57]** | **+0.99** [0.59, 1.38] | +0.21 [−0.28, 0.70] | **+0.35  (banked — PEAK)** |
| 0.70 | +0.66 [0.41, 0.91] | +0.97 [0.57, 1.37] | **+0.37 [0.02, 0.72]** | −0.98  (COLLAPSED) |
| 0.80 | +0.95 [0.70, 1.21] | +0.66 [0.24, 1.08] | +0.79 [0.37, 1.21] | −0.86  (COLLAPSED) |
| 0.90 | +1.24 [0.97, 1.50] | +0.52 [0.06, 0.98] | +0.92 [0.47, 1.38] | −0.80  (COLLAPSED) |
| 0.95 | +1.30 [1.02, 1.58] | +0.46 [−0.00, 0.92] | +1.03 [0.59, 1.47] | −0.82  (COLLAPSED) |
| 1.00 | +1.37 [1.11, 1.63] | +0.45 [0.01, 0.89] | +0.93 [0.52, 1.35] | −0.68  (COLLAPSED) |

*SELLER Δ* is the HONEST (attested, truthtelling) a2a arm's profit over posted.
*attested REALIZED seller Δ* is what the seller actually banks once the engine
attests the OUTSIDE OPTION (blocking the w-robust free-walk leak, which is what
attestation prices out) but WTP disclosure is only as good as the incentive to
tell the truth: below the WTP-IC break buyers stay honest and the seller banks
the honest number; at/after it buyers understate and the seller gets the
understatement-arm profit. Bold CI = excludes zero. (Against the plain STATIC
sticker the tilt looks even stronger — seller Δ +$0.55→+$1.84/day, CS Δ
+$1.60→+$1.32/day — but posted is the honest, referee-hardened baseline.)

### The three break-points

1. **CS crosses zero: NEVER (in [0.5, 1.0]).** The a2a−posted consumer-surplus
   advantage falls with w (+$0.73 → +$0.45/day) but stays strictly positive
   even at full seller-take (w=1.0). The tilt cannot turn the engine into a
   pure-extraction tool RELATIVE TO THE POSTED BOARD: the disagreement discipline
   floors every buyer at their outside option, and negotiation still grows the
   pie (more deals recruited, better substitution, bigger baskets), so buyers
   stay net-ahead of the discounted posted board. "Both benefit" survives the
   whole dial. (CS even peaks at w=0.6, +$0.99 — the extra recruited deals
   outrun the per-deal buyer-share erosion early.)
2. **IC break (WTP disclosure): w ≈ 0.7.** At w=0.5 the pure WTP-understatement
   attack LOSES the buyer money (−$0.14/day, CI includes zero — the "H3 inverted"
   result holds: understating denies you deals the buffer would have cleared).
   As the mechanism favors the seller, the incentive to claw surplus back by
   understating grows monotonically (−0.14 → +0.93) and becomes the buyer's
   significant best response (CI lower bound > 0) at **w=0.7** [was w=0.8 pre-fix;
   the review-fix batch tightened it one grid-point earlier]. The seller-favoring
   mechanism destroys the WTP disclosure it runs on. (A SEPARATE, w-robust leak
   — claiming a free outside option — pays a little at every w, +$0.58→+$1.19;
   it is not created by the tilt and is exactly what outside-option attestation
   prices out, so it is excluded from the WTP-IC break and handled by the
   attestation tier.)
3. **Profit peak: w = 1.0 on paper, w = 0.6 in reality.** The HONEST-arm profit
   rises monotonically and saturates at w=1.0 (+$1.37/day) — but that number is
   a MIRAGE if buyers can lie. The ATTESTED REALIZED profit peaks at **w = 0.6
   (+$0.35/day [0.13, 0.57])** and then COLLAPSES to −$0.98/day at w=0.7 the
   instant WTP-understatement becomes the buyer's best response. The predicted
   peak-then-collapse is exactly here. (If the outside-option leak is ALSO
   unattested, realized seller profit is negative at every w, −$0.7…−$1.0/day —
   strategic buyers neutralize the tilt entirely from the start; attestation is
   not optional garnish, it is what makes any of the tilt collectible.)

### THE DELIVERABLE — max defensible seller-profit gain

Honest region = {CS ≥ 0 (all of [0.5,1.0]) AND WTP-disclosure IC intact
(w < 0.7) AND CS ≥ half the symmetric level ($0.36, satisfied through w=0.6)}.

> **Max defensible seller-profit gain: +$0.35/day [0.13, 0.57] at w = 0.60**,
> vs the strong posted board — a real, CI-excludes-zero seller gain (an ~+3%
> lift on the ~$10.9/day realized profit), delivered WHILE consumers stay
> +$0.99/day [0.59, 1.38] ahead and WTP disclosure stays incentive-compatible.

That is the growth-sharing region — what a merchant pays for, banked as seller
profit, without becoming RealPage: it never prices below a buyer's outside
option, it leaves the buyer strictly better off than the best posted board, and
it does not corrupt the disclosure it runs on. Push past w≈0.7 and all three
guarantees fail together — the paper profit keeps rising but buyers begin to
lie, and the REALIZED profit collapses below the symmetric tie. **The
monetization mechanism is a BOUNDED tilt (w≈0.6), gated by attestation** (which
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
| **×1.0** | surge (to ceiling) | +6.97 [6.91, 7.04] | +6.89 | +0.54 | 8 / 4 | 120 / 120 | −0.09 |
| **×1.0** | **engine** | **+8.24** [8.01, 8.47] | **+8.24** | **+1.15** [0.51, 1.80] | 11 / 5 | 119 / 120 | 0.00 |
| **×1.25** | surge (to ceiling) | +32.92 [31.7, 34.2] | **+29.76** [29.0, 30.5] | **−12.15** [−13.3, −11.0] | 51 / 44 | 118 / 118 | −3.16 |
| **×1.25** | **engine** | +41.11 [38.4, 43.8] | **+36.68** [34.5, 38.9] | **−15.39** [−16.5, −14.3] | 70 / 73 | **104 / 112** | −4.42 |

Head-to-head (engine − surge, paired, pooled): at ×1.0 **net +$1.36/day [1.11,
1.60]**, CS **+$0.61**; at ×1.25 net +$6.92 [5.17, 8.67], CS **−$3.25**.

(Updated 2026-07-10 for the review-fix batch. The mild ×1.0 both-win and the
×1.25 refutation are UNCHANGED. The one visible mechanism shift is at the ×1.25
engine: the new REGULAR acceptance gate — a regular is never routed into a quote
worse for them than the sticker board — cuts a few regular deals routed into
harvest quotes, so the engine hurts consumers slightly LESS [CS −15.93→−15.39]
while still churning MORE than the surge [143 vs 95] and retaining fewer.)

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
   At ×1.25 the engine churns **143** (70+73) vs the surge's **95** (51+44) and
   retains **fewer** regulars (104/112 vs 118/118). The reason is mechanical and
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
   capture), not retention.** engine−surge net is +$1.36/day (×1.0) / +$6.92/day
   (×1.25), CIs clear, driven by the churn-off *captured*-value edge (+$1.27 /
   +$8.18) — individual price discrimination extracts more per transaction. At
   ×1.25 the engine's fairness cost (−$4.42/day) is WORSE than the surge's
   (−$3.16), and it hurts consumers MORE (CS −$15.39 vs −$12.15): in the harvest
   zone the engine is the *harsher* extractor, not the fairer one (the review-fix
   regular gate narrowed but did not close the gap).

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
   *anchor / price level*, not the frame (churn 5→143, fairness cost $0→−$4.42/day,
   CS +$1.15→−$15.39/day as the anchor climbs 1.0→1.25), for surge and engine
   alike. Delete it (the Musk critique) and the model predicts the ×1.25 harvest is
   free and painless — contradicting the empirical Wendy's/Coke backlash the whole
   apparatus is calibrated to. And the ENGINE-REF diagnostic locates the ONE
   fairness-free lever: individual discounts BELOW the reference (never above) —
   which capture **+$0.00** here (churn-off −$0.10, zero churn) because the clean
   world's all-day sticker is already profit-optimal, so the only extra value at a
   captive machine is captive HARVEST, which costs fairness in ANY frame. Where the
   sticker is genuinely MIS-SET (the realistic-miscalibration cells) that same
   below-reference lever is worth +$0.35–2.55/day at CS-positive (referee #48's
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

## Review-fix batch (2026-07-10) — six correctness fixes; artifacts regenerated

A code review flagged six issues; all six are fixed and every affected artifact
(`results.json`, `grid.json`, `tilt.json`, `surge.json`) was regenerated
deterministically. The sections above carry the post-fix numbers with inline
"Updated 2026-07-10" notes. Summary:

1. **(MATERIAL, §2) StrongPostedPolicy synthetic-panel OUTSIDE option**
   (`policies.py::_panel_outside`). It reused the machine-stock feasibility
   mask and only ranged over in-stock SKUs; the real consumer's outside option
   (`run.py:163`, `consumer.best_bundle(outside_prices)`) ranges over the WHOLE
   catalog at full QTY_CAP with NO machine-stock cap (the bodega carries its own
   stock). Fixed to match run.py exactly, so the "strongest posted baseline" is
   actually strongest. **Headline impact:** on the realistic calibrated cell the
   a2a−posted profit Δ moved −$0.05 → **+$0.12 (seed A) / +$0.04 (seed 7)** — CI
   includes zero on both seeds, i.e. **still a TIE** (sign flipped, not the
   conclusion). a2a **still wins consumer surplus** on all four seed×profile
   points (calibrated +$0.81/+$0.66, hot +$4.12/+$5.49; every CI excludes zero),
   at a slightly smaller margin than the committed +$0.88/+$0.90. Note: fix 1's
   *isolated* effect on posted profit is tiny (≈−$0.01/day — 12-rung
   discretization + a discount-only-from-a-calibrated-ceiling bound it); most of
   the a2a−posted shift is the a2a arm gaining from fixes 4 & 6. **The §2
   conclusion (posted ties/wins profit; disclosure's durable edge is CS) HOLDS.**
2. **Regular acceptance gate** (`run.py`, intent path). Regulars accepted any
   quote with `raw+fair−fric>0`, never comparing against the sticker board /
   bodega, while transients enforce `≥ max(s_out, s_board)`. Regulars now get the
   same guarantee (evaluated on their own utility basis incl. transaction
   utility) — a regular can't be routed into a deal worse than the board they can
   always access. **Impact:** at the surge ×1.25 engine cell, a few fewer harvest
   quotes fire (reg_deals ↓) and consumers are hurt slightly less (CS
   −15.93→−15.39).
3. **Return-defer roll re-pairing** (`run.py:223`). Seeded on positional `k`,
   which diverges across paired arms; now seeds on `consumer.uid` (the liar_roll
   pattern), so the return decision is stable per person and policy-independent.
4. **nash_quote disagreement stock-cap** (`scenario.py`). The board-disagreement
   loop iterated `1..QTY_CAP` with no stock cap while `enumerate_outcomes` /
   `best_bundle` cap at `min(QTY_CAP, stock)`; a stock-constrained buyer got d_b
   from an unbuyable unit (spurious no-deal). Now stock-capped (the comment
   already claimed it).
5. **_pooled_ci per-seed blocking** (`run.py`). Concatenated both seeds then
   blocked, letting a block straddle the seed boundary for non-multiple day
   counts. Now blocks WITHIN each seed and pools the block-means (byte-identical
   for the committed 90-day, multiple-of-5 runs; correct for any day count).
6. **DemandLearner censored-escalation ceiling** (`policies.py`). `max(old,obs)
   *1.2` compounded 1.2^n unbounded over consecutive sellout days; now ceilinged
   at `censor_cap_mult × observed` (3×), documented. Small a2a/posted dynamics
   shift where slow SKUs sell out.

Tests: one per fix (`test_nash_disagreement_is_stock_capped`,
`test_regular_gate_rejects_worse_than_board`, `test_censored_escalation_is_capped`,
`test_pooled_ci_blocks_within_seed_never_across`,
`test_strong_posted_panel_outside_option_matches_run_py`), plus the
`test_fairness_harvest_regression` pin re-baselined (reg_deals 1307→1325,
day90 108→107, churn 75→76). Full suite: 64 passing.

## 90-day re-run of the two pure-engine control cells (2026-07-10) — horizon-honesty fix

The paper's headline standard is 90-day (or multi-seed); two PURE-ENGINE cells
were still cited at 30-day single-seed and flagged in review. Both re-run at 90
days, same seed (20260713) and args, deterministic. **The LLM contrast
(`vend/h4-llm.json`) is left at 30 days on purpose — it burns a paid LLM.** The
committed artifacts (`vend/results.json`, `vend/liar-sweep.json`) are now 90-day;
the whitepaper §5a/§5c prose is updated from these numbers.

**§5a — perfect-calibration control** (`vend/results.json`; stationary, hot
smart-store-P90 traffic, static/gvr/a2a/posted, block-5 CIs):

| metric | committed 30-day | **90-day** |
|---|---|---|
| a2a − static profit Δ/day | −$0.05 [−0.74, 0.65] | **−$0.05 [−0.25, 0.16]** |
| a2a − static CS Δ/day | +$1.79 [0.20, 3.38] | **+$0.97 [0.43, 1.51]** |
| gvr − static profit Δ/day | −$1.92 [−2.75, −1.08] | **−$2.20 [−2.60, −1.80]** |
| (posted − static profit Δ/day, 90d) | — | +$0.26 [0.10, 0.42] |
| (posted − static CS Δ/day, 90d) | — | +$0.48 [0.17, 0.78] |

**§5c — finite-stock liar sweep** (`vend/liar-sweep.json`; same perfect-cal
stationary world, a2a vs a2a-liars25/50/100, liar identity keyed on `uid`):

| liar share | committed 30-day CS Δ/day | **90-day CS Δ/day** | 90-day profit Δ/day |
|---|---|---|---|
| 25% | −$0.31 [−0.79, 0.18] | **−$0.10 [−0.23, 0.03]** | +$0.03 [−0.18, 0.23] |
| 50% | −$0.61 [−1.58, 0.36] | **−$0.15 [−0.46, 0.17]** | +$0.10 [−0.08, 0.27] |
| 100% | −$0.62 [−1.53, 0.30] | **−$0.30 [−0.59, −0.02]** | −$0.11 [−0.27, 0.06] |

**Verdict guards — all four HOLD at 90 days:** (a) a2a−static profit stays a
statistical tie (CI includes 0; a *large significant* win over the perfectly-
calibrated sticker would be a Riley–Zeckhauser bug — it isn't); (b) consumer
surplus stays a positive win (CI excludes 0); (c) gvr−static stays a loss (CI
excludes 0); (d) no liar cohort significantly *gains* — every CS delta is
non-positive and every profit delta CI includes 0. The tighter 90-day window
*sharpens* §5c: at 100% liars the CS delta is now marginally-significantly
NEGATIVE (liars end up slightly worse than honest disclosure), strengthening
the no-exploit result rather than weakening it.

**Reproduction note (Appendix A command bug).** The committed Appendix A / §5c
line reads `python3 -m vend.scenario --liar-sweep --days N …`, but `vend.scenario`
has no `__main__`/CLI — that invocation is a **silent no-op** and never wrote the
artifact. The liar sweep is actually produced by the same `vend.run` harness with
the registered liar arms:
`python3 -m vend.run --days 90 --seed 20260713 --arms a2a,a2a-liars25,a2a-liars50,a2a-liars100 --out vend/liar-sweep.json`
(matches the "Reproduce" line above and the committed artifact config byte-for-byte
at 30 days). §5a control:
`python3 -m vend.run --days 90 --seed 20260713 --arms static,gvr,a2a,posted --out vend/results.json`.
`results.json` reproducibility is pinned by
`test_default_config_reproduces_committed_artifact` (reads the horizon from the
artifact, so 90-day reproduces cleanly). Full vend suite: 70 passing.

## P4 (pre-registered 2026-07-21; Phase-A listing date: ______) — NEXTMOVE demand referendum

Listing 3 categories (resale, supply, retail-discount) at **$2 per
negotiation session** (all moves of one negotiation, cap 10, 7-day TTL)
via the MCP door only (`nextmove_open`/`nextmove_advise`; no human door —
humans send their agents), prepaid Stripe credit packs, deterministic
400k-rollout advice with commit-auditable context_hash. The generic
engine (`gt_negotiate_turn`) stays free on the same server — P4 measures
willingness to pay for the TUNED + AUDITABLE session specifically, with
the free substitute one tool away and honestly labeled. Sixty days from public announcement,
preceded by a ~1-week quiet soak (registry listing live, no publicity)
for production burn-in. Organic traffic during the soak is reported as
a descriptive note in the launch post, not a hypothesis — the clean
organic-discovery experiment is reproducible any time with a fresh
unannounced endpoint, so no measurement is being burned by announcing.

Per-category gates (set before listing, published before the first
sale): d1 total paid sessions ≥ 30; d2 distinct repeat_keys ≥ 10;
d3 buyers with ≥2 sessions ≥ 3; d4 refund rate ≤ 2%. Pricing may move
between pre-registered week-long posted-price epochs ($1/$2/$5 ladder,
schedule published in advance); gates are evaluated on sessions, with
per-epoch conversion reported alongside.

Hypotheses: D1 — at $2, ≥1 category clears all gates in 60 days.
D2 — repeat purchase exists somewhere (d3 > 0 in any category).
D3 — ≥1 unlisted category out-requests a listed one via the
null-query log (`nextmove_request`).

Kill rule: all categories miss d1+d2 → machine goes to maintenance
(standing telemetry only) and build-hours reallocate; the negative
result is the deliverable and publishes here like every other P.

Results publish either way, gate by gate, in this file.

**SUPERSEDED before Phase A (2026-07-21).** Never listed; the clock never
started. The store referendum (P6) replaces these single-SKU gates — see
vend/STORE.md §6. Kept as the record of the single-product framing.

## P5 (2026-07-21) — NEXTMOVE-as-product: the panel verdict, and the pivot

Panel critique of NEXTMOVE as a standalone product: a lone $2 negotiation
SKU competes with its own free tier and reaches the wrong buyer;
population uninterpretable, retail-repeat gate unpassable. Verdict
absorbed rather than transcribed: the useful finding (wrong unit — a
product, not a position) became vend/STORE.md; the two-seat refinement +
founder amendments that followed are recorded in STORE.md §10. This entry
marks the pivot point: NEXTMOVE demoted from product to anchor tenant.

## P6 (pre-registered 2026-07-21; clock start date: ______) — THE STORE referendum

**PROPOSED numbers below await founder confirmation before listing; the
block is binding once the clock-start date is filled in.**

The question: **do agents come back to the counter?** Shelf at clock
start: fetch/extract (passthrough + settlement-on-delivery) alongside the
negotiation anchor SKUs ($2 session, unchanged) — two unrelated snacks,
one wallet. Commodity pricing is wholesale passthrough (exact cost basis
on every receipt); the store's take is a published ~5% counter fee on
top-ups; settlement debits only when the slot's machine-checkable
predicate passes — non-delivery is never charged.

**The clock:** the 60-day window starts at the first distribution event —
the MCP door listed/default in ≥1 third-party tool config or registry
with observed traffic — NOT at deploy. Quiet production soak before that
is burn-in, reported descriptively, per P4's convention.

**The starter credit:** every new key gets a one-time 50¢ starter credit,
unconditional, no card. Starter-credit usage is excluded from every gate;
all gates below are measured on SELF-FUNDED wallets (wallets that topped
up with their own money) only.

Gates, evaluated at day 60 from clock start:

| Gate | Meaning | Threshold (PROPOSED) |
|---|---|---|
| R0 conversion | wallets that used starter credit AND subsequently self-funded | ≥ 10 |
| R1 return | self-funded wallets purchasing across ≥2 distinct sessions ≥24h apart | ≥ 5 |
| R2 breadth | self-funded wallets buying from ≥2 different slots | observational — reported, never kill-relevant; ≥5 arms the STORE.md §9 marketplace trigger |
| R3 demand pull | distinct unstocked capabilities with a commodity backend surfaced via catalog.request, each by ≥2 distinct repeat_keys | ≥ 3 |

Deliberately low — this measures whether the return-visit habit EXISTS,
not whether it's a business. R1 is the load-bearing gate (tourist-proof).

**Delist rule (the shelf exhales):** any commodity slot with < 10 paid
calls from < 2 distinct self-funded wallets over a rolling 4 weeks is
delisted at the weekly restock ritual; its slot goes to the top
catalog.request write-in with a commodity backend. A slot's first 4 weeks
are exempt (stocking grace).

**Published-losses carry-over:** alongside the gates we report settled-call
rate, predicate-failure rate (uncharged non-deliveries), and cumulative
settlement shortfall eaten by the store — the store's losses publish like
everything else.

Kill rule: R0 AND R1 both miss at day 60 → the store goes to maintenance
(standing telemetry only, shelf frozen), build-hours reallocate to the
notary roadmap; the negative result is the deliverable and publishes here
like every other P.

Results publish either way, gate by gate, in this file.

## P7 (pre-registered 2026-07-22) — the engine's accept-collapse: is the recommender leaving surplus on the table?

**This block was written BEFORE any engine source was touched.** The
pre-registration (hypothesis, probes, metrics, kill conditions, and the
one fix that ships iff H1 confirms) is fixed below; the RESULTS subsection
at the bottom is filled after the battery runs, either way.

**The observed anomaly.** For the seller node `side=sell, walk_away=170,
target=210, counterparty_offers=[150,165,175], my_previous_offers=[215,195],
rounds_left≈3`, the shipped engine returns **accept $175** — it takes the
buyer's standing $175 rather than countering. The buyer has been climbing
(150→165→175) with three rounds still on the clock. Accepting the floor of
a rising offer, with time left, looks like surplus left on the table.

**H1 (the bug hypothesis).** The accept is EV-dominated: the engine's own
rollout machinery values *holding and countering* strictly above accepting,
and the accept is produced not by a value comparison but by a saturated
concession schedule. Two mechanism claims, cited to source:
 - `plain_terms.py:164` — accept fires iff `their_util_raw >= recommended_util`
   (a pure threshold against the engine's OWN next counter; there is no EV
   comparison; `expected_settlement` is display-only, overwritten at
   `plain_terms.py:177-178`).
 - `sell.py:119-120` computes `rounds_used = len(my_offer_history) +
   len(opponent_offer_history)` (CUMULATIVE, both sides) and
   `time_fraction = rounds_used / deadline_rounds`, but `plain_terms.py:138`
   passes `deadline_rounds = rounds_left` (REMAINING). cumulative ≥ remaining
   ⇒ `time_fraction` clamps to 1.0 ⇒ aspiration collapses to the floor ⇒ the
   next-counter utility collapses to the schelling buffer ⇒ almost any
   standing offer clears the accept threshold. Buy-side is symmetric
   (`buy.py:208-209`; `plain_terms.py:143`). Rationale prints "round 5/3".

**Battery (permanent artifact, `gametheory/tests/test_accept_battery.py`).**
seed=0 everywhere, no LLM anywhere. Six probes:
 - P1 — the reported node, rounds_left ∈ {2,3,5,8}.
 - P2 — trajectory controls at rounds_left=3, final offer ≈$175 held fixed:
   climbing [150,165,175], barely-moving [174,174,175], flat [165,165,165],
   steep [150,170,178].
 - P3 — history controls at rounds_left=3, same cp:
   mine ∈ {[], [215], [215,195], [215,205,195]}.
 - P4 — buy-side mirror: WA210/T170, seller descending, deep history,
   rounds_left=3.
 - P5 — deadline scaling: fixed history, rounds_left 2..12, record
   accept-threshold($).
 - P6 — out-of-model control arm: full engine plays to termination against
   {rollout-conceder, boulware, mirror, random, anomalous-below-floor}
   opponents; realized seller surplus, shipped policy vs a
   hold-to-rollout-optimal-counter policy.

**Metrics.**
 - PRIMARY EV_gap = V_rollout(best counter) − V(recommended), with a 95% CI,
   using the engine's OWN rollouts (`_conceder_payoffs`, 400k, seed=0).
 - SECONDARY realized-surplus delta (P6): hold-to-counter − shipped.
 - TERTIARY monotonicity: d(accept-threshold $)/d(rounds_left) ≥ 0, and
   threshold(flat) ≥ threshold(climbing).

**H1 CONFIRMED** iff EV_gap > 2·CI in ≥4/6 probes AND hold-to-counter beats
shipped by >1 SE vs the conceder AND mirror families AND the tertiary
monotonicity is violated. **H1 KILLED** iff EV_gap ≤ 2·CI in ≥4/6 probes OR
shipped ≥ hold-to-counter (within 1 SE) across ALL families. If KILLED: NO
fix is applied, the vindication is recorded here, and that is a fully
successful outcome.

**The fix that ships iff H1 confirms (and ONLY this).** At the adapter
boundary in `plain_terms.py` (both the sell call at :136-139 and the buy
call at :141-144), the concession schedule must see the TOTAL horizon, not
the remaining count: pass `deadline_rounds = len(counterparty_offers) +
len(my_previous_offers) + rounds_left`. Equivalently, the internal
`time_fraction = rounds_used / (rounds_used + rounds_left)` no longer
saturates. NOTHING else changes: not `_VALIDATED_KNOB`, not any tuned
`_config` parameter, not the conceder/schelling branch (`sell.py:171-179`),
not the MC accept short-circuit (`mc_search.py:179-180`). Corrective
counterfactual prediction to verify post-fix: rounds_left=3 → counter ≈ $196.9.

Flagged-but-out-of-scope (recorded here, not fixed under this block; each
becomes a follow-up only if the POST-fix battery still shows the pathology):
 - conceder/schelling branch trajectory-perversity (a *conceding* buyer
   routed to the schelling floor can be accepted LOWER than a flat one);
 - `mc_search.py:179-180` accept short-circuit — MC never runs on accept
   nodes, so a receipt can present an EV-dominated accept as "optimal" (a
   receipts-honesty fix for the display already shipped in a parallel lane).

Results publish either way, gate by gate, below.

### P7 RESULTS (2026-07-22) — H1 CONFIRMED pre-fix, fix applied, bug resolved post-fix

Battery: `gametheory/tests/test_accept_battery.py` (seed=0, 400k rollouts, no LLM;
runnable as `python -m gametheory.tests.test_accept_battery`). Pre/post transcripts
archived in the engine_fix scratchpad.

**Gate-by-gate verdict on the CURRENT (pre-fix) engine — all three legs fire:**

| Gate | Rule | Pre-fix result | Fires? |
|---|---|---|---|
| PRIMARY (EV_gap) | EV_gap > 2·CI in ≥4/6 probes | P1,P2,P3,P4 all EV-dominated (4/4 EV-probes); reported node EV_gap **0.155** vs 2·CI **0.001** (~135×) | ✅ |
| SECONDARY (P6) | hold-to-counter beats shipped >1 SE vs conceder AND mirror | conceder **+8.94 ± 1.31** SE, mirror **+12.79 ± 1.67** SE, random +12.32 ± 1.03 (boulware/below-floor tie, correct) | ✅ |
| TERTIARY (P5) | accept-threshold saturation / monotonicity violated | threshold **flat at $172** across rounds_left ∈ {2,3,4,5} (schedule saturated) | ✅ |

⇒ **H1 CONFIRMED.** The accept-$175 is not a value judgment — it is a saturated
concession schedule. 12/13 probe-nodes were EV-dominated; the invariance across
P3 (my-own-offer history [] → [215,205,195], all accept $175, identical EV_gap
0.155) proves the mechanism is `rounds_used/deadline_rounds` saturation, not the
buyer's trajectory.

**The fix (exactly the pre-registered one, nothing else).** `plain_terms.py`
adapter boundary: the `deadline_rounds` handed to `sell_next_offer` /
`buy_next_offer` changed from `rounds_left` (remaining) to
`total_horizon = len(counterparty_offers) + len(my_previous_offers) + rounds_left`,
so the engine's `time_fraction = rounds_used / (rounds_used + rounds_left)` no
longer saturates. Untouched, as pre-committed: `_VALIDATED_KNOB`, every `_config`
parameter, the conceder/schelling branch, and the MC accept short-circuit. A
convention comment was pinned at `dispute_copilot.py:coach_round` (audited:
it already passes a fixed TOTAL — round derived from history — so it was never
affected; comment prevents a future regression). `dispute_sim.py` and `_sim.py`
likewise already pass totals. plain_terms was the sole mis-passer.

**Post-fix battery — the conjunction is now FALSE (bug resolved):**

| Probe | Pre-fix | Post-fix |
|---|---|---|
| Reported node (rl=3) | **accept $175**, EV_gap 0.155 | **counter $196.91**, EV_gap 0.002 |
| P1 rl=2 / rl=5 / rl=8 | accept $175 / accept $175 / counter $196.91 | counter $192.63 / $201.15 / $203.58 |
| P2 climbing / steep / flat | accept $175 / accept $178 / counter $190.32 | counter $196.91 / $196.91 / $196.91 |
| P3 (all 4 histories) | accept $175 (all) | counter $195–$201 (all) |
| P4 buy-mirror | accept $205 | counter $183.79 |
| P5 threshold (rl 2→12) | **$172,172,172,172**,185,…,203 (saturated) | **$192.63,196.91,199.50,201.15**,…,204.70 (strictly rising) |
| P6 ensemble Δ (hold−shipped) | conceder +8.94, mirror +12.79, random +12.32 | conceder **+1.02**, mirror **+1.19**, random **+0.50** |

Post-fix verdict: 2/4 EV-probes fire, P5 saturation **False**, ⇒ **H1 no longer
confirmed** = success. No probe node accepts anymore.

**$196.9 prediction check:** predicted counter ≈ $196.9 at rounds_left=3;
observed **$196.91**. Independently reproduced by the orchestrator's read-only
seed=0 replay against the in-flight fixed tree: **$196.91**. ✔

**Honest residual (not the bug, not actionable).** Post-fix a few nodes still
show small positive EV_gaps under the *conceder rollout belief* (≤0.024; one
short-horizon rl=2 node at 0.085) — the engine now counters marginally FIRMER
than the myopic conceder-optimum. This is the KNOWN, validated closed-form-vs-MC
null (MC ties, does not beat, the closed form in realized play: MC−closed =
−0.002, `mc_search.py` docstring). The realized-surplus arm (P6, the better
ground truth) confirms the fix captured the surplus for the shipped policy — the
hold-to-counter advantage collapsed by ~90% on every ZOPA family. The residual
is firmness, the opposite failure mode from accept-collapse; it is not closed and
is not meant to be by this fix.

**Engine tests + goldens.** Full `gametheory/tests/` = **348 pass** (346 non-slow
+ 2 slow battery), **0 broken** by the fix. No engine test asserted a now-changed
specific recommendation, so no expectation edits were needed. **No byte-exact
golden broke** — no `gametheory/tests` fixture compares live engine output to a
pinned negotiation trace; the static demo traces under `server/static/` are
generated by server-lane `http.py` and are not asserted against the engine here,
and `gametheory/evals/*.json` are tuning artifacts, not goldens. Nothing to
re-pin.

**Vend tests likely to shift (orchestrator's lane — NOT touched here).** All are
resale/single-issue paths that route through `negotiate_turn`; the fix raises
mid-ZOPA counters (holds firmer) and eliminates the early accept:
- `vend/tests/test_advice.py` — `_RESALE` (sell WA170/T210, their=[150,165],
  mine=[215], rl=4). Only asserts determinism + conditional bounds (no pinned
  move/price) ⇒ should still PASS, but the receipt's counter OFFER value rises.
- `vend/tests/test_receipt_signing.py` — `test_move_receipt_counter_is_mc`
  (below-floor ⇒ counter) and `test_move_receipt_accept_is_closed_form`
  (above-target ⇒ accept) sit at the robust extremes ⇒ moves unchanged, PASS;
  but a refined counter PRICE inside any pinned receipt shifts.
- Any vend fixture byte-pinning a mid-ZOPA resale counter price will shift upward.

**Flagged follow-ups (evidence status; deliberately NOT fixed under this block):**
1. **Conceder/schelling-branch trajectory-perversity** (`sell.py:171-179`,
   `buy.py:238-245`). PRE-FIX proof: at the reported node a *conceding* (climbing)
   buyer routed to the schelling floor ($172) while a *flat* buyer got the
   Rubinstein floor ($190.32) — the conceding buyer was accepted LOWER. POST-FIX
   it is MASKED (aspiration $196.91 now dominates both floors, so P2 climbing =
   flat = steep = $196.91); the branch still routes conceders to the lower floor
   and will RESURFACE once aspiration < Rubinstein floor (late rounds / low-knob).
   The battery's P2 nodes are permanent and will catch it if it does.
2. **MC accept short-circuit** (`mc_search.py:179-180`). MC runs zero rollouts on
   accept nodes, so a receipt can present an EV-dominated accept as "optimal."
   PRE-FIX this compounded the bug (the $175 accept shipped 0 rollouts while the
   engine's own rollouts valued countering at 0.28). POST-FIX the accept-collapse
   no longer manufactures such accepts here (they are counters now, which DO get
   MC-refined), but the structural honesty gap persists for any genuine future
   accept. A receipts-honesty fix for the display already shipped in a parallel
   lane; the search short-circuit itself is left as flagged.

## P8 (pre-registered 2026-07-22) — the conceder/schelling branch: value-positive, or strictly dominated?

**This block was written BEFORE any engine source was touched.** Follow-up A
to P7 (P7 flagged #1). The hypotheses, probes, metrics, kill conditions, and
the one fix that ships iff H1 confirms are fixed below; the RESULTS subsection
is filled after the battery runs, either way.

**The branch under test.** `sell.py:175-178` (buy.py:242-245 mirrors it, with
a HARDCODED `0.05` where sell reads `get_param("opp_concession_threshold")`):

```
opp_concession = opponent_offer_history[-1] - opponent_offer_history[0]   # utility
if opp_concession > 0.05:                     # opponent is visibly conceding
    recommended = max(aspiration, schelling_floor)   # DOWNGRADE to the schelling floor
else:
    recommended = max(aspiration, rubinstein_floor)  # hold at the SPE floor
```

With the adapter's `my_reservation=0` (plain_terms.py:147), `schelling_floor =
0 + min(0.05, 0.5·1) = 0.05` (sell.py:114-116) while `rubinstein_floor =
surplus·freelancer_share` (sell.py:168) ≈ 0.48-0.51 at the P7 frame. So a
visibly-conceding opponent is routed to `max(aspiration, 0.05)` = **aspiration**
(aspiration ≫ 0.05), whereas a stonewaller is routed to `max(aspiration,
rubinstein_floor)`. The two branches DIFFER iff `aspiration < rubinstein_floor`
(otherwise `max()` masks the floor). Pre-P7 this was proven perverse (a climbing
buyer accepted at $172 while a flat buyer was countered at $190). Post-P7-fix it
is MASKED at the P7 probe nodes (aspiration $196.91 dominates both floors) and
RESURFACES wherever aspiration decays below the Rubinstein floor.

**Where the branch binds post-fix (verified empirically, seed=0, knob=1.0,
frame WA170/T210).** `aspiration = 0.89·(1 − time_fraction³)` (sell.py:123),
`time_fraction = rounds_used/(rounds_used+rounds_left)` (post-P7-fix). Binding =
late rounds with deep histories = the ENDGAME of any multi-round negotiation:
 - `cp=[155,170,185,193], mine=[215,205,198], rounds_left=2` → aspiration
   **0.471 < rubinstein 0.508** → binds; band = [$188.8, $190.3].
 - one offer deeper (`cp=5, mine=4`) → aspiration **0.403 < 0.508** → band widens.
 - at the r=7 endgame of a horizon-8 rollout → aspiration ≈ **0.285 ≪ 0.508** →
   band ≈ [$181, $190] (the divergence GROWS as aspiration decays).
 - at rounds_left ≥ 3 with short histories the branch is masked (aspiration
   dominates) — exactly the P7 probe nodes, which the fix must leave unchanged.

**H1 (dominated).** The conceder→schelling downgrade is strictly dominated:
routing everyone to `max(aspiration, rubinstein_floor)` (arm B) yields ≥ realized
surplus per opportunity than the shipped branch (arm A) everywhere the branch
binds, and buys no deal-rate that pays for its surplus cost.

**H0 (deal-existence, the steelman).** The branch buys deal-existence near the
deadline: against a conceder, the lower floor closes deals that a Rubinstein
floor loses to timeout/withdrawal, and that deal-rate gain pays for the lower
surplus-per-deal. Surplus-per-deal is not the only metric.

**Battery (extends `gametheory/tests/test_accept_battery.py`; seed=0; no LLM).**
 - ARMS, applied by monkeypatching `sell.get_param("opp_concession_threshold")`
   in the harness only (production untouched during the eval): **A** = shipped
   (threshold 0.05); **B** = always-Rubinstein (threshold→+∞ ⇒ the `else` branch
   for all opponents = the proposed fix); **C** = always-schelling (threshold→−∞,
   symmetry control). Faithfulness: arm-A passthrough reproduces the unpatched
   recommender byte-for-byte (verified in-harness on conceder and flat nodes).
 - BINDINGNESS PROBE: sweep (rounds_left, history depth) on both sell and buy;
   record aspiration vs rubinstein_floor and the arm-A/arm-B recommended-util
   gap. Confirms the regime the arms are measured in is actually binding.
 - REALIZED-SURPLUS ARM: the P7 out-of-model willingness ensemble
   {rollout-conceder (t^0.5), boulware (t³), mirror (t), random, anomalous-
   below-floor (m<WA)} played to termination under the SHIPPED accept-on-
   threshold policy (negotiate_turn verbatim), under each arm, over a grid
   (m, b0, horizon). TWO termination models, because the P7 buzzer (grab the
   buyer's last standing offer if > WA) makes deal-existence STRUCTURALLY
   impossible to lose on a ZOPA family (deal rate ≡ 100%), which would rig H1:
     · STANDING (P7 buzzer): isolates the surplus effect; deal-rate not at risk.
     · WITHDRAWING (buzzer ⇒ no deal): the H0 steelman — holding firm to the
       Rubinstein counter at the buzzer can now TIME OUT to no-deal, so arm A's
       earlier accept can save a deal arm B loses. The m-grid is widened into the
       sensitive band {188,189,190,191,196,204} so the deal-existence tradeoff is
       actually exercised (a Rubinstein counter ≈ $190 straddles it).
 - EV-PROBE (engine's own conceder rollouts, `_conceder_payoffs`, 400k, seed=0):
   at binding nodes, V(arm-B rec) − V(arm-A rec) — does the engine's OWN belief
   value holding to the Rubinstein floor over the schelling downgrade?

**Metrics (per family × termination model × arm).**
 - PRIMARY: realized surplus per opportunity = mean over the grid of
   (deal_price − WA), counting no-deal as 0, with SE across grid points; the
   arm contrast is the paired B−A (identical buyer trajectories).
 - SECONDARY: deal rate (fraction of grid points that close).
 - TERTIARY: surplus per closed deal.

**Deal-rate-loss bound (pre-declared): 10 percentage points absolute.**
Justification: the shipped product already reveals a firmness-over-deal-rate
preference (plain_terms.py:36-37, `_VALIDATED_KNOB=1.0`: "walks away from
below-floor counterparties rather than capitulating — the correct call"). Below
10pp the surplus win is effectively free and the branch is pure dead-weight;
above 10pp the branch is genuinely purchasing deals that the surplus metric does
not fully price (relationship / optionality), and H0's defense stands.

**Kill conditions (declared numerically BEFORE running).**
 - H1 CONFIRMED iff, in the binding regime: arm B beats arm A on the PRIMARY by
   > 2·SE on the conceder AND mirror families under BOTH termination models,
   AND arm B's deal-rate loss vs arm A is < 10pp on those families.
 - H1 KILLED iff EITHER arm A ≥ arm B within 1·SE on the PRIMARY on any
   binding-regime family (the branch is not costing surplus), OR arm B's
   deal-rate loss vs arm A exceeds 10pp on the conceder or mirror family (the
   branch genuinely buys deal-existence). If KILLED: NO fix is applied; the
   branch's deal-existence defense is recorded here and the P7 trajectory-
   perversity is reclassified as the price of deal-existence, published honestly.

**The fix that ships iff H1 confirms (and ONLY this).** Remove the conceder
downgrade: replace the `opp_concession` branch at `sell.py:171-179` and
`buy.py:238-245` with `recommended = max(aspiration, rubinstein_floor)` for ALL
opponents (symmetric; identical to arm B). NOTHING else changes: not
`_VALIDATED_KNOB`, not any `_config` parameter, not the P7 adapter fix, not the
MC accept short-circuit. Because aspiration dominates the Rubinstein floor at
every P7 probe/P5 node, the fix leaves the entire P7 post-fix battery
byte-identical (verified: the branch only diverges where aspiration <
rubinstein_floor, which no P7 node reaches) — so P7 must not regress. Post-fix:
re-run the FULL P7+P8 battery and extend `test_accept_battery.py` with permanent
P8 nodes (fast subset + `-m slow` full).

Results publish either way, gate by gate, below.

### P8 RESULTS (2026-07-22) — H1 KILLED: the branch is a deal-existence HEDGE, not dead-weight; NO fix shipped

Battery: the P8 section of `gametheory/tests/test_accept_battery.py` (seed=0, no
LLM; arms applied by an in-harness monkeypatch of
`sell.get_param('opp_concession_threshold')` — production untouched during the
eval). Transcripts archived in the `conceder_eval` scratchpad.

**Where the branch binds post-fix (verified).** The conceder route diverges from
the non-conceder route only where `aspiration < rubinstein_floor` — the endgame
of a long negotiation. Sell frame WA170/T210, climbing conceder, rounds_left=2:
| history | aspiration | rubinstein_floor | binds? | band |
|---|---|---|---|---|
| cp=2, mine=1 | 0.698 | 0.508 | no (masked) | — |
| cp=3, mine=2 | 0.566 | 0.508 | no (masked) | — |
| **cp=4, mine=3** | **0.471** | **0.508** | **yes** | [$188.8, $190.3] |
| **cp=5, mine=4** | **0.403** | **0.508** | **yes** | [$186.1, $190.3] |
At the r=7 endgame of a horizon-8 rollout aspiration decays to ≈0.285, so the
band widens to ≈[$181,$190] — the divergence GROWS as the deadline nears. Buy-side
is the same code, but its second-mover-corrected Rubinstein floor is lower (≈0.29
vs 0.51 sell), so buy binds only at an even deeper endgame and the overshoot it
risks is smaller; the perversity is symmetric in FORM, milder in buy-side MAGNITUDE.

**Gate-by-gate verdict.** Realized surplus per opportunity ($ over WA), paired
arms A=shipped / B=always-Rubinstein (the fix H1 would have shipped) / C=always-
schelling, over a grid m∈{188,189,190,191,196,204}×b0∈{150,158}×horizon∈{6,8,10}
(random ×3 seeds). Two termination models bracket reality — the P6 buzzer makes
deal-existence impossible to lose on a ZOPA family, so it alone would rig H1:

| gate | rule | result | fires? |
|---|---|---|---|
| PRIMARY, STANDING (buyer stands pat at buzzer) | B beats A on $/opp by >2·SE | conceder **+2.10 ± 0.25**, mirror **+3.37 ± 0.29**, boulware +5.76, random +2.46; deal rate tied at 100% | ✅ B>A |
| PRIMARY, WITHDRAWING (buzzer ⇒ no deal — the H0 steelman) | B beats A on $/opp by >2·SE | conceder **−7.40 ± 1.46**, mirror **−6.13 ± 1.51**, random −6.52, boulware −2.72 | ❌ **A ≫ B** |
| SECONDARY, WITHDRAWING | B's deal-rate loss vs A < 10pp bound | conceder & mirror & random **50pp**, boulware 44pp — all ≫ 10pp | ❌ **kill** |
| TERTIARY (surplus per closed deal) | — | B closes HIGHER when it closes: conceder A18.2/B21.6, mirror A16.5/B20.7 | (genuine deal-rate↔$/deal trade) |
| CONTROL (anomalous below-floor, m<WA) | no arm closes | 0 surplus, 0 deal rate on A, B, C | ✅ clean |

**⇒ H1 KILLED.** The pre-registered kill fired under the mandated steelman: with a
withdrawing counterparty, always-Rubinstein (arm B) is ≤ shipped (arm A) on the
primary on every ZOPA family, AND its deal-rate loss (44–50pp) blows through the
10pp bound. H1 ("strictly dominated") is decisively rejected; H0 (deal-existence)
is upheld. Per the pre-registration, **no fix is applied** — `sell.py:171-179` and
`buy.py:238-245` are UNTOUCHED, so the entire P7 post-fix battery is byte-identical
(re-run green: `test_full_battery_h1_no_longer_confirmed`, `test_p6_*` both pass).

**Mechanism (why the branch earns its keep).** Arm B holds every counter at the
Rubinstein floor (≈$190.3 at the endgame). That floor is an ESTIMATE built from
`opp_rv_estimate = clip(0.40 − 0.20·weight, .1, .6)` (sell.py:159-162); when the
buyer's true max `m` lands below it, arm B counters above the ZOPA and — against a
buyer who won't stand pat — TIMES OUT to no-deal. The diagnostic is crisp and NOT
a horizon artifact: arm B closes iff **m ≥ $191** (uniformly at horizons 4–12);
for m∈{186,188,189,190} it never closes. Where both close (m clears the floor) B
banks +$1.47/deal; where only A closes (m below the floor) A banks ~$15.6 and B
banks **$0**. So the branch is a deal-existence HEDGE against Rubinstein-floor
overshoot, with a real PREMIUM: under a stand-pat buyer it concedes $2–6/opp it
did not need to. Its value = P(counterparty walks near the deadline) ×
P(our SPE floor overshoots their true max); the eval prices both regimes but does
not pin those probabilities.

**The engine's own belief agrees with H1 — and that is the point.** The EV-probe
(engine's `_conceder_payoffs`, 400k, seed=0) values arm B's higher counter over
arm A's at both binding nodes (V_B−V_A = +0.008 and +0.058, both > CI). But that
rollout belief structurally excludes withdrawal (opponent max ~ Uniform[u_lo,1] ≥
every revealed offer). So the branch is dominated INSIDE the model and vindicated
only by the out-of-model deal-existence risk the model omits — the mirror image of
P7, where hold-to-counter beat shipped out-of-model with NO compensating benefit.

**P7 flag #1 reclassified.** The trajectory-perversity (a climbing buyer accepted
LOWER than a stonewaller) is not a bug to remove — it is the visible face of the
deal-existence hedge: routing a conceder to the lower floor is what closes the
deal when our Rubinstein estimate overshoots and the counterparty won't wait. It
stays, now with a permanent regression guard (`test_p8_*`) so a future
"simplification" to always-Rubinstein can't silently regress deal-existence.

**Left flagged (NOT fixed — new hypothesis, out of this lane).** The branch's
TRIGGER is `opp_concession > 0.05` (conceding ⇒ hedge). But the deal-existence
rationale is about the opponent's RESERVATION being below our estimate, which is
orthogonal to whether they are visibly conceding — arguably a stonewaller (whose
max we know less about) needs the hedge more. This eval only tested conceders (the
P6 families all climb), so it establishes the hedge is value-positive FOR
conceders; whether the concession trigger is the RIGHT selector for it is a
separate, untested question (a P9 candidate), not a defect this block condemns.

**Engine tests.** Full `gametheory/tests/` non-slow = **349 pass** (346 prior +
3 new P8 fast guards), 3 slow deselected; `test_accept_battery.py -m slow` = **3
pass** (2 P7 regression + 1 P8 verdict). No production source edited; no golden
touched; vend tests not run (out of lane).

## P9 (pre-registered 2026-07-22) — should the PAID MC layer VERIFY accepts, not short-circuit them?

**This block was written BEFORE any engine source was touched.** The hypotheses,
probes, metrics, the margin ladder, the kill conditions, and the one change that
ships iff H1 confirms are fixed below; the RESULTS subsection is filled after the
battery runs, either way.

**The gap under test.** `mc_search.py:179-180` short-circuits: when the closed
form recommends anything other than `counter`, `negotiate_turn_mc` returns
immediately and ZERO rollouts run. So on an ACCEPT node the paid MC layer spends
nothing and can never catch a premature capitulation — "the $2 session can stop a
bad accept; the free tool can't" is, today, an empty claim on accept nodes. P7
fixed the accept-COLLAPSE (saturated schedule ⇒ accept a rising floor); its
residual note flagged that a few post-fix nodes still show tiny in-model EV_gaps
(≤0.024; one short-horizon rl=2 node at 0.085). This block asks whether a paid
MC accept-VERIFICATION — run rollouts on accept nodes and OVERRIDE accept→counter
when countering dominates beyond a pre-declared margin — recovers realized
surplus the short-circuit leaves on the table, honestly and without lighting a
deal-existence fire.

**CARRY-FORWARD FROM P8 (mandatory framing).** An accept→counter override is a
deal-existence gamble of exactly the P8 shape: the offer on the table is CERTAIN,
a counter risks WITHDRAWAL. P8 proved this structure cuts both ways — the
in-model-dominant always-Rubinstein "fix" was KILLED because a withdrawing buyer
punished it by ~50pp of deals. Therefore (a) the eval runs BOTH P8 termination
models — STANDING (opponent stands pat; the buzzer grabs their last standing
offer if > WA) and WITHDRAWING (a rejected final offer vanishes ⇒ no deal); and
(b) the override rule is CONSERVATIVE BY CONSTRUCTION: it overrides only when the
rollout EV of the best counter exceeds the CERTAIN accept-now EV by more than a
pre-declared margin M that prices withdrawal risk. M is pre-registered below and
is NOT tuned after seeing results.

**The override rule (evaluated; ships iff H1 confirms).** On an accept node with a
compute budget:
 - `V_accept_now` = the CERTAIN utility of taking their standing offer now
   (`their_util_raw`, at t=0, undiscounted) — identical to the P7 battery's
   accept-value convention (`ev_probe`, test_accept_battery.py:132).
 - `V_best_counter` = max over the single-issue rollout grid of `_conceder_payoffs`
   discounted EV (the engine's OWN belief), at the fixed deterministic
   `compute_samples` budget (seed=0), with its 95% CI.
 - OVERRIDE accept→counter (at the rollout-best price) iff
   `V_best_counter − V_accept_now > M` AND the gap clears its 95% CI (noise alone
   can't trigger it). Otherwise the accept STANDS. The result carries a `compute`
   block (`samples`, `override` true/false, `margin`) so the receipt honesty lane
   shows REAL rollout numbers on accept nodes instead of a short-circuit.
 - Free path unchanged: compute budget 0 ⇒ closed-form accept stands, byte-for-byte.

**Margin ladder (pre-declared; anchored to P7 landmarks, NOT to results).** All
three are utility-frame [0,1] thresholds tied to empirical P7 magnitudes:
 - **M_aggressive = 0.05** — just above the post-P7 honest-residual firmness band
   (≤0.024 typical, 0.085 rl=2 outlier). Overrides whenever the in-model counter
   beats accept by more than residual-firmness noise. Least conservative — the
   "does verification ever help" probe.
 - **M_moderate = 0.10** — the battery's gross-EV-domination flag
   (`test_full_battery_h1_no_longer_confirmed` uses EV_gap ≥ 0.10). Overrides only
   at gaps as large as the pre-fix bug's lower fringe.
 - **M_conservative = 0.15** — the bottom of the pre-fix accept-collapse range
   (0.15–0.28). Overrides ONLY when the in-model surplus of holding is as large as
   the original accept-collapse bug; maximally conservative, prices heavy
   withdrawal risk.

**Selection rule (pre-declared).** SHIPPED M = the SMALLEST M in {0.05,0.10,0.15}
that satisfies ALL gates under BOTH termination models (smaller M = more overrides
= more paid-tier value-add, so among SAFE margins we prefer the one that does the
most work; safety is the hard gate). If no M satisfies the gates, H1 is KILLED and
nothing ships.

**Probes (permanent, extend `test_accept_battery.py`; seed=0; no LLM).**
 - ACCEPT-REGIME nodes — the point of this eval: nodes where the post-P7 closed
   form GENUINELY accepts (their standing offer at/above the engine's accept
   threshold), at varied horizons incl. the rl=2 short-horizon regime where the
   P7 residual was largest — marginal accepts (just above threshold) and generous
   accepts (well above). Each asserted to actually `accept` (an eval of
   accept-verification that never visits genuine accept nodes proves nothing).
 - The P7/P8 node families, unchanged, as the regression backdrop.
 - REALIZED-SURPLUS ARM — the P7/P8 out-of-model willingness ensemble
   {conceder t^0.5, boulware t³, mirror t, random, anomalous-below-floor m<WA}
   played to termination under two seller ARMS: **short_circuit** (shipped: accept
   on the engine's threshold) vs **verify** (accept-verification at margin M), over
   a grid whose buyer max WTP m spans ABOVE the post-P7 accept thresholds so
   climbing offers cross into the accept regime (coverage requirement, verified
   in-harness that accept opportunities occur). BOTH termination models.

**Metrics (per family × termination model × arm).**
 - PRIMARY: realized surplus per opportunity = mean over the grid of
   (deal_price − WA), no-deal = 0, paired arms (identical buyer trajectories), SE.
 - SECONDARY: deal rate (fraction of grid points that close).
 - TERTIARY: override frequency (fraction of accept opportunities the verify arm
   overrode) + override-was-right rate (of the overrides, the fraction whose
   verify-arm realized surplus BEAT what accepting would have banked).

**Deal-rate-loss bound (pre-declared): 10 percentage points absolute**, the SAME
bound P8 used, for the same reason: the shipped product already reveals a
firmness-over-deal-rate preference (`plain_terms.py:36-37`, `_VALIDATED_KNOB=1.0`),
so below 10pp a deal-rate cost is priced by that preference; above it, the override
is destroying deal-existence value the surplus metric can't fully capture. (A paid
capitulation-stopper arguably warrants a TIGHTER bound; 10pp is the established
precedent and is NOT tightened post-hoc to force a verdict.)

**H1 (verification pays).** For at least one pre-registered M, a conservative
accept-verification improves realized surplus per opportunity vs the shipped
short-circuit on the out-of-model ensemble, under BOTH termination models, without
violating the 10pp deal-rate bound. **H0 (verification adds nothing).** Post-P7
accepts are already EV-consistent: on genuine accept nodes the engine's own
rollout belief does not value the best counter above the certain accept, so the
override never fires (surplus tie under both models); or it fires only to take a
withdrawal-risk-shaped loss (surplus down / deal-rate loss > bound under
WITHDRAWING).

**Kill conditions (numeric, declared BEFORE running), evaluated per M:**
 - G-UPSIDE (STANDING): verify surplus/opp > short_circuit surplus/opp by > 1·SE
   on conceder OR mirror. [If this fails for every M — no upside exists — H0.]
 - G-NO-DOWNSIDE (WITHDRAWING, surplus): verify surplus/opp ≥ short_circuit
   surplus/opp − 1·SE on conceder AND mirror. [If it fails — H0: withdrawal loss.]
 - G-DEAL (WITHDRAWING, deal rate): short_circuit deal_rate − verify deal_rate <
   0.10 on conceder AND mirror AND boulware AND random. [If it fails — H0.]
 - G-CONTROL: anomalous-below-floor (m<WA) closes 0 deals on both arms (no
   spurious deal creation), both models.
 H1 CONFIRMED at M iff G-UPSIDE ∧ G-NO-DOWNSIDE ∧ G-DEAL ∧ G-CONTROL all hold at
 M; shipped M = smallest confirming M. H1 KILLED iff no M confirms.

**The change that ships iff H1 confirms (and ONLY this).** In `mc_search.py`,
replace the unconditional short-circuit at :179-180 with: budget 0 ⇒ closed form
stands (unchanged); accept node + budget ⇒ run the override rule above at the
shipped M and return the (possibly overridden) turn with an honest `compute` block
(`samples`, `override`, `margin`); counter node ⇒ the existing anytime search;
walk / negotiate_directly ⇒ closed form. NOTHING else changes: not
`_VALIDATED_KNOB`, not `_config`, not the P7 adapter fix, not the P8 conceder
branch. If H1 KILLS: `mc_search.py:179-180` is REVERTED byte-for-byte to the
shipped short-circuit, the implementation is preserved in the p9_mc_accept
scratchpad for the record, and this block states plainly that the paid tier's
accept-node value-add remains zero-rollouts honesty only. Either way,
`test_accept_battery.py` gains permanent P9 guards (fast + slow) and the full
P7+P8 suites must stay green.

Results publish either way, gate by gate, below.

### P9 RESULTS (2026-07-22) — H1 KILLED: the override NEVER fires; verification is a no-op; REVERTED

Battery: the P9 section of `gametheory/tests/test_accept_battery.py` (seed=0,
deterministic `compute_samples`, no LLM). The verification was implemented in
`mc_search.py` and RUN against the real code path (`_accept_override` /
`_verify_accept`), then reverted; the implemented file is archived at
`scratchpad/p9_mc_accept/mc_search_WITH_P9_verification.py` and the run transcript
at `scratchpad/p9_mc_accept/battery_transcript.txt`.

**The decisive finding — structural, not marginal.** On EVERY genuine post-P7
accept node the engine's OWN conceder-rollout belief values the best counter
*below* the certain accept-now EV. `V_best_counter − V_accept_now` is NEGATIVE
everywhere, so the override never fires at any margin — not even the most
aggressive 0.05:

| accept node (sell WA170/T210) | their offer | V_accept | V_best_counter | gap | override @{.05,.10,.15} |
|---|---|---|---|---|---|
| rl=2 marginal (just above thr $195.05) | $195.55 | 0.639 | 0.588 | **−0.051** | False/False/False |
| rl=2 generous | $206.00 | 0.900 | 0.828 | **−0.072** | False/False/False |
| rl=3 marginal (thr $198.96) | $199.46 | 0.737 | 0.664 | **−0.073** | False/False/False |
| rl=3 generous | $208.00 | 0.950 | 0.762 | **−0.188** | False/False/False |
| rl=5 marginal (thr $202.48) | $202.98 | 0.825 | 0.648 | **−0.177** | False/False/False |
| rl=8 marginal (thr $204.28) | $204.78 | 0.870 | 0.557 | **−0.313** | False/False/False |

WHY (mechanism): the closed form accepts precisely when their standing offer
meets/beats our next counter (`plain_terms.py:174`), so the offer we could bank is
already at/above what we'd ask. The rollout belief cannot value holding above that
because (i) it discounts every future close (`_DELTA=0.92`), and (ii) it gates the
opponent's FIRST-round acceptance at `c(0)=C0=0.5` (`_conceder_payoffs`,
mc_search.py:118-130) and has NO "grab their standing offer now" action — so a
certain, undiscounted accept of an at-or-above-ask offer strictly dominates any
discounted counter IN-MODEL. The verification is therefore CONSERVATIVE by
construction to the point of never acting: it prices the deal-existence risk P8
measured so heavily that the engine's own belief already refuses the gamble.

**Gate-by-gate verdict (realized arms: short_circuit vs verify, both termination
models, out-of-model ensemble; surplus/opp in $ over WA, paired):**

| gate | rule | result | fires? |
|---|---|---|---|
| G-UPSIDE (STANDING) | verify surplus/opp > short_circuit by >1·SE on conceder OR mirror | Δ = **+0.000** on ALL families (conceder/boulware/mirror/random), both models — override never fired | ❌ **no upside** |
| G-NO-DOWNSIDE (WITHDRAWING, surplus) | verify ≥ short_circuit − 1·SE on conceder AND mirror | Δ = **0.000** (holds trivially — nothing changed) | ✅ (moot) |
| G-DEAL (WITHDRAWING, deal rate) | short_circuit − verify deal-rate < 10pp | Δ = **0pp** on every family | ✅ (moot) |
| G-CONTROL (below-floor m<WA) | 0 deals both arms | 0 surplus, 0 deal rate, both models | ✅ clean |
| override frequency | — | **0 / 57 accept opportunities** at M∈{.05,.10,.15}, both models | — |
| override-was-right rate | — | undefined (no overrides) | — |

Coverage confirmed: the realized ensemble visited real accept nodes (conceder 9,
boulware 8, mirror 9, random 31 accept opportunities; below-floor 0) — the eval
did NOT skip the accept regime.

**⇒ H1 KILLED (H0 confirmed).** G-UPSIDE fails at every pre-registered margin: the
override never fires, so the verify arm equals the shipped short-circuit
byte-for-byte on realized surplus AND deal rate under BOTH termination models. The
two-model bracket (STANDING/WITHDRAWING) that killed the P8 fix has nothing to
punish OR reward here, because no deal-existence gamble is ever taken. This is the
cleanest possible null: post-P7 the accept regime holds no premature capitulations
for MC to catch — the P7 adapter fix already turned the genuine "hold" nodes into
counters (which the MC layer DOES refine), leaving behind only accepts that the
engine's own rollouts agree are correct.

**No fix ships.** `mc_search.py:179-180` is REVERTED byte-for-byte to the shipped
short-circuit (only a docstring note pointing here was added, behavior identical;
verified: an accept node with a compute budget again returns 0 rollouts / no
`compute` block, a counter node still MC-refines). The implemented verification is
preserved in the scratchpad for the record.

**What this means for the paid-vs-free differentiator.** The claim "the $2 session
can stop a premature capitulation; the free tool can't" is FALSE on accept nodes:
there is nothing to stop — the paid tier's accept-node value-add remains
zero-rollouts honesty only (the receipt truthfully says the accept is closed-form,
0 rollouts, per the parallel receipt-honesty fix). A weaker "verification-as-proof"
differentiator (spend the rollouts anyway and PROVE `override=false`) is technically
available but was NOT validated here as surplus-positive and, by the pre-registered
rule, is not shipped. The paid tier's real, measured edge stays where P-series
found it: MC-refinement of COUNTER prices (the +9% multi-issue timing lever), not
accept-node overrides.

**P8's flagged P9-candidate, addressed in passing.** P8 left open whether the
concession trigger is the right selector for its deal-existence hedge; that is a
distinct question about the conceder BRANCH and is untouched here. This P9 answered
a different flagged item (the `mc_search.py:179-180` accept short-circuit, P7 flag
#2): the short-circuit is not a latent honesty gap that verification would close —
it is the correct behavior, because verification would be inert.

**Engine tests.** Full `gametheory/tests/` non-slow = **350 pass** (349 prior + 1
new P9 fast guard `test_p9_genuine_accept_node_is_ev_consistent_fast`), 4 slow
deselected; `test_accept_battery.py -m slow` = **4 pass** (2 P7 + 1 P8 + 1 new P9
`test_p9_accept_verification_is_a_noop`). The P7 short-circuit-contract test
(`test_mc_search.py::test_accept_branch_is_untouched_by_compute`) still passes
post-revert. No production behavior changed; no golden touched; vend tests not run
(out of lane).

## P10 (pre-registered 2026-07-22) — the BUNDLE tier: an accept-floor leak, a determinism leak, and a time-blind endgame

**This block was written BEFORE any bundle source was touched.** The three
defects, the exact fix for each, and the bidirectional numeric gates that
decide whether each fix ships are fixed below; the RESULTS subsection is filled
after the battery runs, either way. A completed read-only audit (36k instances)
already VINDICATED the skyline Pareto filter and Bayesian-Nash selection
(`snhp/nash_solver.py`, zero divergence vs first-principles brute force across 9
adversarial instance kinds) — that code is NOT touched. This block is only the
multi-issue *decision + plumbing* around that verified core.

**Scope note (concurrent-lane honesty).** The single-issue accept/schedule work
(P7), the conceder branch (P8), and the paid MC accept short-circuit (P9) are
DONE and out of this lane. P10 is the multi-issue analog surface:
`gametheory/negotiation/bundle.py`, `snhp/bayesian_agent.py` (additive only),
`vend/advice.py::advise_bundle`, and the two bundle server seams
(`server/mcp_server.py::gt_negotiate_bundle`, `server/a2a_routes.py` bundle
endpoint). `mc_search.py` (P9's lane) is untouched.

### The three defects (verified pre-fix; each cite-checked)

**Defect 1 — accept BELOW my walk-away (BUG, bounded ≤ 0.02).**
`bundle.py:345` fires `accept` iff `u_latest >= rec_u_self - 0.02`. The COUNTER
utility `rec_u_self` is guarded above `my_batna` (the walk check at
`bundle.py:312`), but the accept threshold subtracts 0.02 from it, so a standing
offer worth up to 0.02 BELOW the user's stated BATNA is accepted. Compounding it,
`bundle.py:361` reports the COUNTER's utility (`rec_u_self`) on an accept, so
`vend/advice.py:334-337`'s `AdviceInvariantError` ("package utility below your
BATNA") is fed the wrong quantity and can NEVER fire on the leak it is meant to
catch. Repro (audit t2 test B, instance-gen seed=0, per-trial `np.random.seed(t)`
to pin the particle cloud): **222 / 40000** trials accept an offer strictly below
`my_batna`; minimal at `np.random.seed(118)` — `u_latest=0.666402`,
`my_batna=0.671402` (offer 0.005 below floor), engine returns `accept`, reports
`my_utility=0.675` (the counter's, not the accepted 0.666).

**Defect 2 — paid-path non-determinism (BUG).** `bayesian_agent.py:13` draws the
cold-start particle cloud from the UNSEEDED global `np.random.rand`;
`bayesian_agent.py:17` the warm-start cloud from unseeded `np.random.normal`.
`negotiate_bundle` builds the filter at `bundle.py:185-188` with no rng. So when
`their_offers` is non-empty (the inference path runs), the inferred priorities —
and therefore the selected package — are a function of global RNG state. The paid
`advise_bundle(..., seed=0)` param (`vend/advice.py:302-370`) is captured ONLY in
the `context_hash` and is a NO-OP on compute; `gt_negotiate_bundle`
(`server/mcp_server.py:145`) and the a2a bundle endpoint (`a2a_routes.py:286`)
seed nothing either. (The FREE advisor `gametheory/negotiation/mcp_server.py:41-46`
`_seed_from_args` DOES seed the global RNG right before the call, so that one path
is already deterministic and is NOT in this lane.) Repro: **30 identical
`negotiate_bundle` calls with `their_offers` non-empty → 2 distinct packages**,
inferred-priority spread up to 0.06/issue, `my_utility ∈ {0.5, 0.533}`. The
`advise_bundle` docstring's "Deterministic by construction … no theater possible"
is, on the inference path, currently FALSE.

**Defect 3 — time-blindness (DESIGN-GAP, not a bug in existing behavior).**
`negotiate_bundle` (`bundle.py:244-253`) takes no `rounds_left`. A standing offer
with clear positive surplus over BATNA is countered identically at round 1 and
the final round — where countering means walking away from a certain deal.
Concrete probe (seed=0): issues `price` [lo/mid/hi] my `[1,.6,0]` their `[0,.5,1]`,
`term` [1yr/2yr/3yr] my `[0,.5,1]` their `[1,.4,0]`, `sla` [basic/gold] my `[0,1]`
their `[1,0]`; standing offer `{price:hi, term:2yr, sla:gold}` → `u_latest=0.500`;
`my_batna=0.400` (surplus **+0.100**). Pre-fix engine returns `counter`
(`rec_u_self=0.667`), correct at rounds 1..k-1, a self-inflicted no-deal at the
buzzer.

### The three fixes (each ships only if its gate passes)

**Fix 1 (Defect 1).** Guard the accept branch: `accept` iff
`u_latest >= max(rec_u_self - 0.02, my_batna)` — i.e. add `u_latest >= my_batna`.
On an accept, the response describes the ACCEPTED standing package
(`recommended_offer`, `my_utility`, `their_expected_utility` all reflect their
latest offer), so `my_utility` is the number that actually clears the floor and
the `AdviceInvariantError` guards the right quantity. Nothing else in the
selection math changes.

**Fix 2 (Defect 2) — structural, not a global-seed shotgun.**
`BayesianParticleFilter.__init__` gains an optional `rng` (a `numpy.random.
Generator`); `rng=None` (default) preserves the EXACT current global-RNG draws
byte-for-byte, so the ~14 other constructors (`sell.py`, `buy.py`, `sdk.py`,
`benchmark.py`, `research/*`) are unaffected. `negotiate_bundle` /`_build_model`
gain an optional `seed`; when set, they build `np.random.default_rng(seed)` and
thread it to the filter. `advise_bundle`'s existing `seed` becomes REAL (threaded
through; `context_hash` meaning unchanged). `gt_negotiate_bundle` and the a2a
bundle endpoint derive a deterministic seed from their inputs (the same
input-derived determinism the free advisor gets from `_seed_from_args`, but via
the structural `seed=` param — no global mutation) and pass it on the closed-form
path. The `advise_bundle` docstring claim becomes true, now earned. NOTE for the
record (NOT fixed here — P9-adjacent): `mc_search.py`'s separate bundle rollout
cloud (`negotiate_bundle_mc`, reached from `gt_negotiate_bundle` only when
`compute_ms>0`) is also unseeded; left to the mc_search lane.

**Fix 3 (Defect 3) — additive + gated.** `negotiate_bundle` (and the callers that
already hold rounds context: `gt_negotiate_bundle`, the a2a endpoint) gain an
optional `rounds_left` (default `None` = exactly current behavior everywhere).
When `rounds_left <= 1` AND a standing counterparty offer clears `my_batna`
(`u_latest >= my_batna`), accept it — the certain positive-surplus endgame. Never
accepts below floor. Ships ONLY if G3 passes.

### Gates (bidirectional, declared numerically BEFORE running; seed=0)

**G1 — accept-floor (Fix 1).** Over N=40000 seeded random instances (audit t2
generator: instance-gen `default_rng(0)`, per-trial `np.random.seed(t)`), with
`rounds_left` unset:
 - `count(action=="accept" AND u_latest < my_batna - 1e-9) == 0`  (leak closed), AND
 - `count(action=="counter" AND u_latest >= max(rec_u_self - 0.02, my_batna) + 1e-9) == 0`
   (NO dominating in-floor offer is rejected — the fix must not OVERCORRECT into
   refusing offers it should take).
 Both directions must hold. Fix 1 ships iff G1 passes; the pre-fix run is recorded
 showing the first clause FAILS (222 leaks) to prove the gate has teeth.

**G2 — determinism (Fix 2).** 100 repeated identical `advise_bundle` calls with
`their_offers` non-empty and `seed=0` collapse to exactly **1** distinct tuple of
`(recommended_offer, inferred_their_priorities, my_utility, their_expected_utility,
context_hash)`. Pre-fix (same harness, the no-op seed) yields ≥ 2. Also asserted:
two DIFFERENT seeds may differ (the seed is real, not ignored), and `seed=None`
on `negotiate_bundle` reproduces the legacy global-RNG path (additivity check).

**G3 — time-blindness (Fix 3), with a byte-identity guard and a surplus sanity
arm.** Fix 3 ships ONLY if ALL three hold:
 - (a) BYTE-IDENTITY: with `rounds_left=None` OR `rounds_left>=2`, output is
   byte-identical to the pre-fix engine across the full G1 instance set AND the
   probe (the fix touches nothing off the final round).
 - (b) THE FLIP: at `rounds_left=1` the pre-registered probe flips `counter →
   accept` with `my_utility==0.500` (the standing offer's true utility), and
   ACROSS the G1 set no instance with `u_latest < my_batna` flips to accept at
   `rounds_left=1` (the endgame never accepts a loss).
 - (c) SURPLUS/DEAL-RATE SANITY (both directions, reusing the audit harness):
   over the G1 instances at `rounds_left=1`, the endgame rule must (i) ADD accepts
   ONLY on offers with `u_latest >= my_batna` — `count(new-accept AND u_latest <
   my_batna) == 0` (no over-acceptance / no manufactured losing deal), AND (ii)
   leave NO in-floor final-round standing offer as a no-deal — `count(u_latest >=
   my_batna AND rounds_left==1 AND action != "accept") == 0` (no under-serving).
   Mean reported `my_utility` on the added accepts is reported for the record.

If G3(a) fails, Fix 3 does NOT ship (it would be perturbing non-endgame play). If
G3(b)/(c) fail in the over-acceptance direction, Fix 3 does NOT ship. Both
directions are pinned above so the endgame rule cannot silently over- or
under-accept.

### Fixed-if-KILLED disposition
Each fix is independent. A gate that fails means THAT fix is reverted byte-for-byte
and the vindication (or the reason the change was unsafe) is recorded here; the
other fixes are unaffected. The skyline/Nash core stays untouched regardless.

**Permanent battery:** `gametheory/tests/test_bundle_battery.py` — fast: a
skyline-vs-brute subset (from audit t1), a G1 accept-floor sample, a G2
determinism check (small n), a full-pipeline label-swap symmetry sample, the G3
probe + byte-identity spot; slow (`-m slow`): the full 36k skyline-vs-brute and
40k G1/G3 versions. `test_accept_battery.py` (P7-P9 lane) is NOT modified.

House rules honored: seed=0 in every check; file:line citations above; no LLM; no
new deps; the two corrected docstring claims are quoted before/after in RESULTS.

Results publish either way, gate by gate, below.

### P10 RESULTS (2026-07-22) — all three gates PASS; all three fixes ship

Gate harness `p10_gates.py` (seed=0, no LLM) + the permanent battery
`gametheory/tests/test_bundle_battery.py`. The audit's skyline/Nash core stayed
untouched and its guard is folded into the battery.

**Gate-by-gate verdict — all three PASS, both directions:**

| Gate | Rule (declared before running) | Pre-fix | Post-fix | Verdict |
|---|---|---|---|---|
| G1a (leak) | count(accept ∧ u_latest < my_batna), t2-B config, N=40k | **222** | **0** | ✅ closed |
| G1b clause1 | count(accept ∧ u_latest < my_batna), mixed-batna sweep N=40k | — | **0** | ✅ |
| G1b clause2 | count(counter ∧ u_latest ≥ max(rec−0.02, my_batna)), N=40k | — | **0** | ✅ no over-correction |
| G2 | distinct (pkg, priorities, utils, ctx_hash) over 100 identical advise_bundle(seed=0) | ≥2 (30-call→**2**) | **1** | ✅ deterministic |
| G2 (seed real) | seed=0 vs seed=1 may differ | — | differ | ✅ not ignored |
| G2 (additivity) | rng=None reproduces legacy global np.random.rand draw byte-for-byte | — | **True** | ✅ |
| G3(a) | rounds_left=None ≡ rounds_left=5 across N=40k (Fix 3 inert off final round) | — | **0** mismatches | ✅ |
| G3(b) | probe flips counter→accept ONLY at rounds_left≤1, my_utility==0.500 | counter@all | counter@{None,9,5,2}; **accept@1, u=0.500** | ✅ |
| G3(c-i) | count(endgame below-floor accept), N=40k | — | **0** | ✅ no over-accept |
| G3(c-ii) | count(in-floor final-round offer left un-accepted), N=40k | — | **0** | ✅ no under-serve |

⇒ **G1 ∧ G2 ∧ G3 all PASS.** All three fixes ship. The endgame rule ADDED 18415
accepts across the G3 sweep (mean accepted `my_utility` = **0.4991**, every one
≥ its instance's `my_batna` — no manufactured losing deal). The audit's
skyline-vs-brute vindication reproduced clean in the battery (0 divergences at
40 and 4000 instances/kind).

**Fixes applied (exactly the pre-registered three, nothing else).**
 - **Fix 1 — accept-floor** (`bundle.py:406`): accept now requires
   `u_latest >= my_batna AND u_latest >= rec_u_self − 0.02`; on an accept the
   response describes the ACCEPTED standing package (`recommended_offer`,
   `my_utility=reported_u_self`, `their_expected_utility`), so `my_utility`
   (`bundle.py:410`) is the number that clears the floor.
 - **Fix 2 — structural determinism.** `bayesian_agent.py:4` gains `rng=None`
   (`:25` `rng.random(...)`, `:29` `draw.normal(...)`); `rng=None` = legacy global
   draw byte-for-byte (verified). `bundle.py:146` `_build_model(rng=...)`,
   `bundle.py:255/318` `negotiate_bundle(seed=...)` builds a LOCAL
   `default_rng(seed)`. `advice.py:339` threads the real seed;
   `mcp_server.py:146/224` and `a2a_routes.py:290/318-319` derive an input-hash
   seed and pass it STRUCTURALLY (no global mutation). `session_advise_bundle`
   already forwards the session seed, so the paid session path is now deterministic
   with no edit to `vend/session.py`.
 - **Fix 3 — gated final-round endgame** (`bundle.py:344`): `rounds_left`
   (`bundle.py:256`, `advice.py`, `mcp_server.py`, `a2a_routes.py`, all optional,
   default None). When `rounds_left ≤ 1` and a standing offer clears `my_batna`,
   accept it; dominates the walk branch. None/≥2 leaves every path byte-identical
   (G3(a) = 0). `mc_search.py`'s separate bundle rollout cloud is left unseeded on
   purpose (P9-adjacent) and flagged in-code at `mcp_server.py` and here.

**Invariant now fires (proof).** Pre-fix, an accept reported the COUNTER's utility
(`rec_u_self`, guarded above BATNA), so `vend/advice.py:334-337`'s
`AdviceInvariantError` saw a value that could never be below floor and never
fired. Post-fix, an accept reports the accepted offer's utility. Feeding
`advise_bundle` a synthetic accept with `my_utility = my_batna − 0.05` now raises:
`AdviceInvariantError: package utility 0.45 below your BATNA 0.5`. A REAL post-fix
accept (`my_utility=1.0 ≥ batna 0.40`) leaves it silent. Guard:
`test_advice_invariant_fires_on_below_floor_accept`.

**Determinism proof.** 100 identical `advise_bundle(seed=0)` calls with non-empty
`their_offers` → **1** distinct `(package, inferred_priorities, utilities,
context_hash)`; pre-fix, 30 identical calls gave **2** packages
(`my_utility ∈ {0.5, 0.533}`, priority spread up to 0.06/issue). Seed is real
(seed 0 vs 1 differ); `rng=None` reproduces the legacy global draw exactly.

**Time-blindness disposition.** The pre-registered probe (standing offer
`{price:hi, term:2yr, sla:gold}`, `u_latest=0.500`, `my_batna=0.400`, surplus
+0.100) is countered at `rounds_left ∈ {None,9,5,2}` (`my_utility=0.667`) and, at
`rounds_left=1`, flips to **accept** at its true `my_utility=0.500`. The fix
touches nothing off the last round (G3(a) byte-identity, 0/40k) and never accepts
below floor (G3(c-i), 0/40k).

**The two corrected docstring claims (before → after).**
 1. `advise_bundle` (`vend/advice.py`): BEFORE — "Deterministic by construction:
    the closed-form bundle engine is a pure function — no rollouts needed, no
    theater possible" (FALSE on the inference path: the particle cloud was
    unseeded global RNG). AFTER — "…a pure function **and the priority-inference
    particle cloud is now drawn from a seeded RNG (the `seed` below is threaded
    into the engine, not just the receipt)** — same context + seed => byte-identical
    advice, no theater possible." Now earned (G2).
 2. `advise_bundle` / `session_advise_bundle` (`mcp_server.py`): "the recommended
    package must clear YOUR stated BATNA, enforced here, not promised" /
    "guaranteed to clear YOUR stated BATNA (enforced, not promised)". TEXT
    UNCHANGED but was FALSE pre-fix (accepts up to 0.02 below floor); Fix 1 makes
    it TRUE (G1a: 222→0). The claim is now honored by the engine, not just asserted.

**Battery + test counts.** New `gametheory/tests/test_bundle_battery.py`: 9 fast
(skyline-vs-brute subset, G1 both clauses, G2 determinism + seed-real + additivity,
G3 probe flip + never-below-floor + inert/sanity, symmetry, invariant-fires) +
4 slow (36k skyline-vs-brute, 40k G1, 40k G3, 5k symmetry). `test_accept_battery.py`
NOT modified. Full `python -m pytest gametheory/tests/ vend/tests/ -q -m "not slow"`
= **542 pass, 8 deselected** (baseline 532 + 9 new P10 fast + 1 concurrent P9 fast
guard); slow P10 battery = **4 pass**. No golden touched; no commit.

**Out-of-lane observations (NOT touched).** (1) `mc_search.py`'s
`negotiate_bundle_mc` bundle rollout cloud is separately unseeded — reachable from
`gt_negotiate_bundle` only when `compute_ms>0`; left to the mc_search/P9 lane,
noted in-code. (2) The concurrent P9 worker appended a P9 RESULTS block and a P11
worker a P11 pre-registration to this file; both are outside this lane and were
not modified. No failures observed outside this lane.

## P11 (pre-registered 2026-07-22) — compute-moat RE-VALIDATION: does MC's counter-price refinement pay on the FIXED engine?

**This block was written BEFORE any measurement was taken.** The claim under
re-test, why it is suspect, the paired design, the deterministic budgets, the n
rule, the per-family breakdown, and the pre-declared bidirectional decision rule
are fixed below; the RESULTS subsection is filled after the harness runs, in
whichever direction it lands. This is a RE-MEASUREMENT of a PUBLISHED null on the
corrected engine — direction unknown, published either way.

**The published claim under re-test.** `mc_search.py`'s module docstring and team
memory both record: *"MC − closed form = −0.002, 95% CI [−0.043, +0.038], 98%
ties → no realized edge; compute tier ships OFF BY DEFAULT and EXPERIMENTAL."*
That number is what put the paid compute tier off by default.

**Why the number is SUSPECT (biased toward the null).** It was measured by
`gametheory/negotiation/mc_validation.py` on the **PRE-P7 engine**. Pre-P7,
`plain_terms.py` passed `deadline_rounds = rounds_left` (remaining) into a
schedule that computes `time_fraction = rounds_used/deadline_rounds` with
`rounds_used` CUMULATIVE across both sides, so cumulative ≥ remaining ⇒
`time_fraction` clamped to 1.0 ⇒ the concession schedule SATURATED ⇒ the engine
accepted a rising counterparty's floor with rounds still on the clock (the P7
accept-collapse, CONFIRMED and fixed above). In `mc_validation.py`'s realized
play BOTH arms route their decision through this same collapsing closed form
(the MC arm only *refines the counter price* on nodes where the closed form
counters; on accept/walk it short-circuits, `mc_search.py:189`). So pre-fix, both
arms capitulated early and identically, and MC's action window — the counter
nodes where its rollout can move the price — was CRUSHED. The blast-radius audit
classified this harness AFFECTED-material: a null measured where the mechanism
can barely act is biased TOWARD "no edge." **The P7 fix has landed**
(`plain_terms.py:144`, `total_horizon = len(cp)+len(mine)+rounds_left`; the
engine now counters through the mid-game instead of collapsing), so MC's
counter-refinement window is open for the first time in this harness.

**What P11 measures, and what it does NOT.** P9 already established (KILLED, H0
confirmed) that MC is STRUCTURALLY INERT on ACCEPT nodes post-P7: on every
genuine accept node the engine's own rollout belief values the best counter
BELOW the certain accept, so an accept-verification override never fires. P11
therefore measures the ONLY channel where MC can still add realized value — its
refinement of the COUNTER price on counter nodes — now that the P7 fix has opened
that window. Delta = realized discounted seller surplus (MC arm) − (closed-form
arm), paired.

**The paired design (preserved from `mc_validation.py`, de-circularised).**
Seller frame WALK=100 / TARGET=200, ROUNDS=8, realized-surplus discount
DELTA=0.95. A population of conceder buyers whose HIDDEN parameters are drawn
OUTSIDE the rollout's assumed model (`mc_search.py` belief fixes `_C0=0.50`,
`_E_OPP=2.5`): reservation `b ~ U(115,200)`, concession exponent `e ~ U(1.3,4.0)`,
initial-concession fraction `c0 ~ U(0.30,0.60)`; `willingness(t,b,e,c0)` rises
from `c0·b` toward `b` by the deadline. SAME (b,e,c0) draws face BOTH arms
(paired). seed=0 for the population draw AND for every MC call.

**Deterministic budgets (the one harness change: wall-clock → sample count).** The
original harness used `compute_ms ∈ {50,200}` — a WALL-CLOCK budget whose realized
sample count depends on machine speed (non-deterministic across runs/machines).
P11 converts the harness to the deterministic `compute_samples` path added for
bit-identical paid advice (`mc_search.py:196-198`; `anytime_search` runs a fixed
sample budget with `deadline_s=inf`). Sample counts are pinned from the shipped
provenance calibration `719k rollouts / 200ms` (`vend/NEXTMOVE.md:191`) ⇒ ≈3.6k
samples/ms on the author's machine ⇒ **50ms ≈ 180k, 200ms ≈ 720k**; the shipped
paid default is **400k** (`vend/advice.py:33 _DEFAULT_COMPUTE_SAMPLES`). Three
tiers are run:
 - **180k** samples — the low bracket (≈ the original 50ms budget);
 - **400k** samples — the SHIPPED paid default, the **PRIMARY** decision tier;
 - **720k** samples — the high bracket (≈ the original 200ms budget).
(All three are named round numbers derived from the NEXTMOVE provenance; they are
NOT tuned to any result.)

**n rule (pre-declared, BEFORE running).** n = 600 paired negotiations per tier
(≥ the original n=400 floor; larger for tighter CIs, runtime-permitting at the
measured ~28 min for all three tiers). n is FIXED at 600 for this run and is never
reduced below 400; it is not adjusted after seeing any delta.

**Per-family breakdown (pre-declared).** The rollout belief holds the opponent's
concession exponent FIXED at `_E_OPP=2.5` (`mc_search.py:46`), so realized MC
value should track how far the true `e` deviates from that belief. Report the
paired delta + 95% CI + tie-rate stratified into three families by hidden `e`:
 - **FAST** conceder: `e ∈ [1.3,2.0)` (concedes earlier than belief);
 - **MATCHED**: `e ∈ [2.0,3.0)` (near belief 2.5);
 - **SLOW / Boulware**: `e ∈ [3.0,4.0]` (concedes later than belief).
Aggregate and per-family tie-rate both reported (tie = |d| ≤ 1e-6, the harness's
existing win/tie/lose convention).

**The pre-declared decision rule (bidirectional; applied to the aggregate paired
delta `d = surplus_MC − surplus_closed`, 95% CI = mean(d) ± 1.96·SE, at the
PRIMARY 400k tier; the 180k/720k brackets are reported alongside and any
disagreement across tiers is itself recorded as the finding):**
 - **CI EXCLUDES 0 in favour of MC** (mean−1.96·SE > 0) ⇒ the off-by-default
   **NULL FLIPS**: MC's counter-refinement has realized value on the fixed engine.
   The compute tier's ship posture gets RE-DECIDED by the founder.
 - **CI INCLUDES 0** ⇒ the **NULL is RE-CONFIRMED on the fixed engine** and now
   becomes TRUSTWORTHY (the original was biased toward it; a re-confirmation with
   the window open is real). Off-by-default stands.
 - **CI EXCLUDES 0 BELOW** (mean+1.96·SE < 0) ⇒ MC is **significantly NEGATIVE**:
   the rollout belief mis-models post-fix play (it counters too firm / at the
   wrong price for the realized population). Recorded as such.

**The one docstring touch (post-results only).** Per the P11 lane rule, the SOLE
permitted edit to `mc_search.py` is its module-docstring stale-number line: if the
null flips or the number changes materially it is updated to the new measurement
with a P11 citation; if re-confirmed it is updated to cite P11's re-confirmation
on the FIXED engine. No `mc_search.py` behavior changes. No production source is
edited by this block. `mc_validation.py` is converted to the deterministic path
(this block's only code change) and re-run; the P7/P8/P9 batteries are untouched.

House rules honored: seed=0 everywhere; deterministic `compute_samples` budgets
only (no wall-clock, no LLM); file:line citations above; no commit.

Results publish either way, gate by gate, below.

### P11 RESULTS (2026-07-22) — VERDICT: the published null does NOT reproduce; MC is significantly NEGATIVE on the fixed engine (third branch fired)

Harness: `gametheory/negotiation/mc_validation.py`, converted to the deterministic
`compute_samples` path (seed=0, n=600 paired negotiations per tier, out-of-model
conceder population `b~U(115,200)`, `e~U(1.3,4.0)`, `c0~U(0.30,0.60)`). Fully
reproducible: `python -m gametheory.negotiation.mc_validation`. Artifact +
transcript archived at `scratchpad/p11_compute_moat/p11_results.json` and
`run.log`. Determinism verified (identical output across repeat runs).

**The aggregate re-measurement — MC is realized-NEGATIVE at every budget, and more
compute does not help** (discounted seller surplus $/negotiation, paired, n=600):

| budget (samples) | ≈ old ms | closed $/neg | MC $/neg | **MC − closed** | 95% CI | rel % | deal rate C→MC | win/tie/lose | verdict |
|---|---|---:|---:|---:|---|---:|---|---|---|
| 180k | ≈50ms | 30.738 | 29.924 | **−0.814** | [−1.214, −0.414] | −2.65% | 75.7%→71.5% | 12.7 / 74.5 / 12.8 | MC NEGATIVE |
| **400k (SHIPPED, primary)** | ≈110ms | 30.738 | 29.916 | **−0.822** | **[−1.222, −0.422]** | −2.67% | 75.7%→71.5% | 12.3 / 74.7 / 13.0 | **MC NEGATIVE** |
| 720k | ≈200ms | 30.738 | 29.918 | **−0.820** | [−1.220, −0.420] | −2.67% | 75.7%→71.5% | 12.5 / 74.3 / 13.2 | MC NEGATIVE |

(Closed-form surplus is byte-identical across tiers — it spends no compute — a
clean sanity check on the paired design.)

**Gate-by-gate against the pre-declared decision rule (evaluated at the PRIMARY
400k tier; the brackets corroborate):**

| branch (pre-registered) | condition | 400k result | fires? |
|---|---|---|---|
| NULL FLIPS (MC edge) | CI excludes 0 ABOVE (lo > 0) | lo = **−1.222** < 0 | ❌ no |
| NULL RE-CONFIRMED | CI includes 0 | CI = [−1.222, −0.422] excludes 0 | ❌ no |
| **MC NEGATIVE** | CI excludes 0 BELOW (hi < 0) | hi = **−0.422** < 0 | ✅ **YES** |

⇒ **The third branch fires: MC is significantly NEGATIVE.** The CI excludes 0
below at ALL THREE budgets, and the three brackets are statistically
indistinguishable from one another (−0.814 / −0.822 / −0.820) — the harm does not
shrink with more rollouts, so it is **belief mis-specification, not Monte-Carlo
sampling noise.**

**Old vs new — the number moved materially, and its SIGN flipped:**

| | engine | budget | n | MC − closed | 95% CI | tie rate |
|---|---|---|---|---|---|---|
| PUBLISHED (stale) | PRE-P7 (accept-collapse) | wall-clock 50/200ms | 400 | −0.002 | [−0.043, +0.038] | 98% |
| **P11 (this block)** | **P7-FIXED** | **deterministic 400k** | **600** | **−0.822** | **[−1.222, −0.422]** | **74.7%** |

**Per-family breakdown (by the buyer's HIDDEN concession exponent e; the rollout
belief fixes `_E_OPP=2.5`, `mc_search.py:46`), at the SHIPPED 400k tier:**

| family | e range | n | MC − closed | 95% CI | tie rate | significant? |
|---|---|---:|---:|---|---:|---|
| FAST | [1.3, 2.0) | 155 | −0.682 | [−1.522, +0.159] | 72.9% | no (CI spans 0; small n, high variance) |
| **MATCHED** | [2.0, 3.0) | 220 | **−1.102** | [−1.848, −0.357] | 72.7% | **yes, negative** |
| SLOW / Boulware | [3.0, 4.0] | 225 | −0.645 | [−1.166, −0.124] | 77.8% | yes, negative |

Note the pre-registered hypothesis (MC value tracks deviation of true `e` from the
belief) is REFUTED: the MATCHED family — where the belief's concession exponent is
CORRECT — is the MOST harmed (−1.102). The harm is therefore NOT "belief wrong
about the concession speed"; it is the rollout's structural over-firmness (the
`_DELTA=0.92` discount + the `Uniform[u_lo,1]` reservation model + the Boulware
continuation, `_conceder_payoffs`, mc_search.py:114-141), which bites hardest
exactly where the closed-form counter was already near the realized optimum and
any refinement can only push it off.

**Mechanism (why the pre-fix null was an artifact, and what the fix exposed).**
Pre-P7 the accept-collapse made BOTH arms capitulate early and identically — MC
almost never reached a counter node it could act on (98% ties = the action window
was crushed, exactly the AFFECTED-material bias the pre-registration named). The
P7 total-horizon fix (`plain_terms.py:144`) opens that window: MC now moves the
price on ~25% of negotiations (tie 98%→75%). When it acts, it applies the P7-
documented "honest firmness residual" — its conceder rollout values holding firmer
than the realized out-of-model population rewards — so it counters at prices that
push more buyers into timeout: **MC deal rate 71.5% vs closed 75.7% (−4.2pp)**.
The lost deals (surplus counted as 0) plus the firmer-but-fewer closes net
**−$0.82/negotiation (−2.67%)**. Win-frequency (12.3%) and lose-frequency (13.0%)
are nearly balanced, but the losses are larger in magnitude and the deal-rate
leak is the dominant driver. This is the realized-play face of P7's residual note
("the residual is firmness, the opposite failure mode from accept-collapse") — now
quantified: acting on it COSTS surplus.

**What the founder should re-decide.** Off-by-default is no longer a "harmless tie
kept for optionality" (the old null's rationale) — it is now a **REQUIREMENT with
the current belief**. Shipping single-issue `compute_ms`/`compute_samples` refinement
ON, as built, would cost ≈2.67% of realized seller surplus and ≈4pp of deals
against an out-of-model population. The paid tier's real edge is NOT single-issue
counter-refinement (P11) and NOT accept verification (P9, inert); it remains the
separate multi-issue timing lever (the +9% bundle claim, out of this lane) plus
zero-rollout receipt honesty. The `mc_validation.py` harness now has TEETH — it
detects harm the pre-fix engine masked — so any future belief improvement (e.g. a
reservation-aware or discount-corrected rollout) can be gated against a real,
signed bar before the tier is ever promoted.

**Docstring updated (the ONE permitted `mc_search.py` touch).** The stale
"−0.002, 98% ties, no realized edge" line in `mc_search.py`'s module docstring is
replaced with the P11 measurement (−0.82 / −2.67% / CI excludes 0 below, fixed
engine, deterministic, n=600) and a note that off-by-default is now required. No
`mc_search.py` behavior changed; no other production source edited.

**Engine tests.** Full `gametheory/tests/` non-slow = **377 pass, 0 fail**, 8 slow
deselected (350 was the P9 baseline; the surplus over it is the concurrent P10
lane's growing bundle-battery fast guards — a moving target while P10 runs, all
green when observed). No test imports `mc_validation.py`, so the harness conversion
touches no assertion; the `mc_search.py` edit is docstring-only (verified: module
still imports, no behavior change). No golden touched; vend tests not run (out of
lane).

