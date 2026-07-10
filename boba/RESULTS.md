# BOBA P0 results — the vend sim grown into a made-to-order shop

*30 paired days per cell, seed 20260710. Reproduce with
`python3 -m boba.run --grid --days 30 --seed 20260710` (writes
`boba/results.json`; `test_committed_results_stay_reproducible` pins it).*

## Setup, in one paragraph

Calibration constants (menu, toppings, 1.5 drinks/min peak capacity,
40-serving tapioca batches, ~260 cups/day, $330/day rent) come verbatim
from `block/calibration.py`. The static arm posts that menu; drink/topping
"appeal" is **inverted from the menu** so the posted price IS the
profit-optimal all-day price — a competent gut menu, not a strawman. The
world's scarce resource is barista-minutes: one staffer until 14:00, two
until 19:00, a FIFO queue, and 8%/min-of-expected-wait balking. That makes
the 12:00–14:00 lunch rush the only structurally congested window
(`PEAK_HOURS == (12, 13)`): the second staffer arrives exactly one rush too
late, which is the capacity story the pickup-slot logroll monetizes. All
arms face identical arrival/WTP/flexibility streams (paired seeds);
divergence is the treatment.

## Headline: margin Δ/day vs static (paired, 95% CI on 5-day blocks)

Static earns ~$1,515/day margin pre-rent ($1,610 in the shock cells) on
~252 cups; rent is $330/day, reported alongside, never netted.

| cell (shock σ × flexible share) | computed/1 | cart/1 |
|---|---|---|
| σ=0.0, flex=0.15 | +$3.31 [−5.50, 12.12] | **+$308.54** [289.88, 327.20] |
| σ=0.0, flex=0.35 | +$3.31 [−5.50, 12.12] | **+$349.40** [331.94, 366.86] |
| σ=0.4, flex=0.15 | +$3.71 [−6.28, 13.69] | **+$271.69** [213.86, 329.51] |
| σ=0.4, flex=0.35 | +$3.71 [−6.28, 13.69] | **+$310.88** [250.69, 371.07] |

Cart side-metrics (σ=0, flex=0.35 cell): cups 252→504, topping attach
0.86→1.41/cup, peak balks 27.7→21.1/day, pearl waste $7.30→$3.12/day,
~104 deferred pickups/day, consumer surplus +$509/day. Note the queue gets
*hotter*, not cooler: avg peak wait 3.7→4.2 min, because the cart converts
far more volume even while it defers.

## Where the cart edge concentrates (ablations, Δ margin/day vs static)

| variant | flex=0.15 | flex=0.35 |
|---|---|---|
| full cart | +308.5 | +349.4 |
| − pickup slots (`defer_slots=False`) | +143.0 | +143.0 |
| − pearls salvage (`salvage=False`) | +308.5 | +349.4 |
| − looker quotes (`quote_lookers=False`) | +167.4 | +195.5 |
| menu-buyers only, no slots | +62.9 | +62.9 |

1. **Capacity smoothing is the biggest single lever: ~$165–206/day**, and
   it scales with the flexible share as pre-registered. It bundles two
   effects this P0 does not separate: freed lunch-window slots (relief-
   priced logrolls) *and* the balk-free app-pickup channel (a deferred
   order never walks; a now-order faces the same balk roll as a walk-in).
   Without slots, the cart's own extra volume makes peak balking *worse*
   than static (38 vs 28/day).
2. **Personalized sub-list conversion of lookers: ~$140–155/day.** Buyers
   whose WTP sits between ingredient cost and the menu get a Nash-split
   quote and convert (deals/day 222→320). This is perfect price
   discrimination under truthful disclosure — the ceiling, not a field
   forecast (see caveats).
3. **Topping attach + group carts: ~$63/day.** Attach 0.86→1.4/cup at
   quoted prices between cost and list; 3-cup packages concentrate in the
   30% of group buyers (solos keep qty 1 — pinned by test).
4. **Batch clearance: ≈ $0.** Honest surprise, see below.

## Static wins / ties

- **computed/1 ties static everywhere** (CI straddles 0 in all four
  cells): the menu is already the all-day optimum, the run-out shadow only
  ever clamps *at* list, so the computed arm's whole surface is small
  evening/morning discounts that trade margin for +$31/day of consumer
  surplus roughly one-for-one. The vend weak-dominance result replicates
  in its second vertical.
- No cell had static beating cart on margin; cart also dominates on
  consumer surplus (+$470–510/day) — the created surplus is split, as the
  Nash engine promises.

## Honest surprises

- **The pearls-expiry salvage logic is worth ~nothing** (+$0.05/day). The
  markdown surface was pre-registered as a main edge; in fact total pearl
  waste is only ~$7/day at static, and the cart's higher attach drains
  batches before they age — clearance is a side effect of attach, not a
  lever. The c_eff logic is correct, tested, and immaterial at this scale.
- **Deferral does not cool the queue; it makes room for more volume.**
  Peak balks drop 28→21 while average peak wait *rises* — the freed slots
  are immediately resold to converted lookers. The shop trades idle
  barista-minutes for margin; the line stays warm.
- **Demand shocks (σ=0.4) *raise* static margin** ($1,515→$1,610): balking
  is the only capacity cost, so heavy days convert their surplus off-peak
  while light days lose little — the asymmetry favors everyone, and it
  narrows cart's *relative* edge (271 vs 309) because balk-rescue is worth
  less when the queue self-shed less.
- **Cart doubles cup volume (252→504) inside the same physical bar.**
  Feasibility was verified tick-by-tick (≤5 drinks in queue at close, no
  orphaned slots): off-peak utilization at static is ~33%, and personalized
  pricing is what fills it. The margin headline is mostly *volume the menu
  was refusing*, not extraction from existing buyers.

## Caveats (attack these first)

- **Truthful WTP disclosure.** All buyers disclose honestly (vend-P1
  attestation assumed). The looker-conversion component (~45% of the edge)
  is exactly what liars would attack by understating WTP; vend H3 measured
  that leak. P0 numbers are an upper bound.
- **The relief estimate is a forecast, not a settlement.** Deferred-slot
  value = current balk probability × mean drink margin; it is only
  credited in structurally congested hours into slack slots, but it is not
  marked to realized rescues.
- **Menu integrity is not modeled.** No regulars, no reference prices, no
  resentment at the neighbor's cheaper cart (vend's `regulars.py` is the
  template); a real shop cannot show a −49%-off quote to half its walk-ins
  with impunity.
- **`PEAK_HOURS` is a static-regime map.** Under the cart's doubled volume,
  afternoon hours become congestion-prone but earn no relief credit — the
  vend P1 regime-consistency lesson applies and is deliberately deferred.
- **Model = truth for the computed arm** (per-drink lognormal demand is
  the actual process), favorable to it; it still ties.
- Pearls are reserved at order time; deferred pickups are assumed
  balk-free at their slot; no returns/patience; consumer surplus is
  counted only on purchases.

# BOBA P1 (2026-07-10) — the liar battery and menu fairness

*Reproduce: `python3 -m boba.attack --battery --liar-sweep --seed 20260713
--days 30` (and `--seed 7`) writes the P1a artifacts; `python3 -m boba.run
--grid --days 30 --seed 20260710 --arms static,cart,menu,menu-no-defer`
(and `--seed 7`) writes the P1b grid. Full paired outputs are committed at
`boba/attack-battery.json`, `boba/liar-sweep.json`, `boba/menu-fairness.json`.
All CIs are 95% t-intervals on 5-day block means, paired seeds throughout.*

## P1a — the liar battery: honesty is NOT a best response on boba's cart

vend's post-weak-dominance battery found honest disclosure was *already*
the buyers' best response (every genuine misreport lost them money). The
pre-registered question here was whether boba's cart — same Nash-bargaining
skeleton, same event-consistent disagreement point — inherits that
property. **It does not, and the gap is large.**

`strategic_disclosure(consumer, wtp_factor, claim_walk)` scales every
disclosed drink AND topping WTP by `wtp_factor` (boba's analog of vend's
anchor) and, when `claim_walk=True`, prices the buyer's outside-shop
option off their TRUE (unscaled) valuation regardless of the in-store lie
— boba has no separate walk-cost scalar to zero (the 10% coffee-shop
markup is the world's, not the consumer's), so the structurally equivalent
lie is "I don't want much of this menu, but I'd happily pay full price two
doors down," which inflates the buyer's apparent BATNA exactly the way
zero-walk inflates vend's. All buyers deviate the same way each cell
(`liar_share=1.0`); prices are quoted on the disclosed lie but every
buyer's acceptance and realized surplus are settled on their TRUE
preferences (`boba.policies.buyer_disagreement`, `world.bundle_value`) —
a lie can win a quote, never a sale the buyer's real self wouldn't take.

**The full grid, pooled buyer-utility Δ/day vs all-honest cart** (shock=0,
flex=0.35, the flagship P0 cell; 30 paired days, seed 20260713 / seed 7):

| wtp_factor | walk=honest | walk=zero (claim_walk) |
|---|---|---|
| 0.55 | +$797.60 [767, 828] / +$849.71 [817, 883] | +$584.16 [556, 612] / +$604.32 [576, 633] |
| 0.70 | +$556.52 [534, 579] / +$606.18 [578, 635] | **+$1,099.06 [1055, 1143] / +$1,170.65 [1137, 1204]** |
| 0.85 | +$262.93 [248, 278] / +$278.87 [266, 291] | +$975.48 [954, 997] / +$1,036.84 [993, 1081] |
| 1.00 (honest) | $0.00 [0, 0] | — |
| 1.15 | −$203.04 [−222, −184] / −$187.19 [−204, −171] | −$211.80 [−228, −196] / −$201.25 [−214, −188] |
| 1.30 | −$315.79 [−331, −300] / −$314.69 [−331, −299] | −$358.26 [−369, −347] / −$344.45 [−354, −335] |
| 1.50 | −$380.91 [−396, −365] / −$373.11 [−392, −354] | −$441.84 [−456, −428] / −$434.51 [−456, −413] |

Every understating cell (0.55–0.85) is a **large, tight-CI win for liars**
— the reverse of vend's finding. Overstating (>1.0) loses money for
buyers, same qualitative direction as vend (a rich-looking buyer lets the
Nash split extract more from them, and the true-settlement check catches
the rest). The best response is **wtp_factor≈0.7, claim_walk=True**:
+$1,099–1,171/day pooled buyer gain, replicated tight on both seeds; deal
*count* barely moves (9,119 vs 9,584 over 30 days — liars aren't
converting more lookers, they're paying far less for the SAME deals).

**Mechanism, traced by hand** (one consumer, both quotes against the same
state): a genuine buyer whose true sticker surplus is $10.71 (they would
have bought 3 brown-sugar teas at the counter for a light $2.42 discount,
shop margin $11.30) discloses at 0.55× + claim_walk. `best_menu_order` on
the *disclosed* WTP now returns a surplus below the *claimed* outside
option, flipping `cart_nash`'s disagreement branch: the shop's belief of
what it would have earned collapses from **$11.30 to $0.00** — "found
money" mode, meant for genuine lookers, now triggered by someone who was
never going to walk. The quoted price falls from $19.33 to $7.22 for the
identical 3-cup order; their TRUE realized utility is $23.66 against a
true walk-away value of $10.71. The min-gain buffer (max($0.25, 10% of
cart list)) does not catch this — it checks the shop's *believed* gain
over its (already-fooled) disagreement, so a deliberate branch flip clears
it too (in the traced example: $2.42 believed gain vs a $2.18 threshold —
the buffer is calibrated to forecast noise, not an adversary who can move
the disagreement point itself).

**Why vend didn't have this hole.** vend's mechanism has the *same*
branch-flip structure (`st_best >= outside` picks the no-deal event) — but
vend additionally shadow-prices every unit against *expected rest-of-day
list demand*: a quoted unit within that forecast is charged at
`(price − list)` margin regardless of what the disclosed disagreement
says, so a fooled `d_machine=0` still can't clear `gs >= 0` on a
non-excess SKU except at list. That protection comes from vend's
**finite-stock** structure (a can of cola sold now is one fewer sold at
list to the lunch crowd) and has no counterpart in boba's **capacity**
structure — drinks are made on demand, not drawn from a countable stock,
so there is no "unit that would have sold at list later today" to shadow-
price against. Boba's cart inherited vend's disagreement-point *design*
without the inventory-scarcity mechanism that, in vend, incidentally also
defends it. This is a genuine, structural finding, not a bug: verified
against a hand trace above, and `deals_dev` tracks `deals_base` closely
across the whole grid (ruling out "liars are just buying weird bundles").

**At what liar share does the venue's gain erode?** Fixed at the
best-response deviation (wtp_factor=0.7, claim_walk=True), sweeping the
share of buyers (stable identity, keyed on `consumer.uid` via
`substream(seed, "liarid", uid)`, never the policy) who run it, against
the SAME flagship cell (cart_vs_static headline here: +$349.97/day seed
20260713, +$351.10/day seed 7):

| liar share | venue margin Δ/day vs all-honest cart | net vs static (headline − erosion) |
|---|---|---|
| 25% | **−$257.08 [−281, −233]** / −$273.69 [−290, −257] | ≈ +$93 / +$77 (73–78% of the headline gone) |
| 50% | **−$532.04 [−570, −494]** / −$548.45 [−570, −527] | ≈ **−$182 / −$197 (cart now LOSES to static)** |
| 100% | **−$1,080.52 [−1114, −1047]** / −$1,108.50 [−1152, −1065] | ≈ −$731 / −$757 |

Erosion is close to linear in liar share (25%→50%→100% roughly doubles
each step). Interpolating for the crossover: **≈32–34% of buyers running
this one deviation already wipes out the entire pre-registered +$270–350/
day cart headline** — a liar share far below vend's H3 range (25/50/100%),
and one deviation, not a colluding population. Stable liar identity was
checked directly (`test_liar_identity_is_stable_and_policy_independent`):
the roll is `substream(master_seed, "liarid", consumer.uid)`, a pure
function of identity, never of which policy is asking.

**Verdict:** honesty is emphatically **not** a best response on boba's
cart as built. Unlike vend (where attestation became a discount tier,
"something buyers WANT" rather than a defense), boba's cart cannot ship
without verified disclosure — the branch-flip exploit is cheap to run,
requires no coordination, and a quarter of the customer base running it
already erases most of the edge. Fixing this in-mechanism (a boba-native
analog of vend's demand-shadow pricing — e.g., time-of-day capacity
consumed as the scarce resource priced against forecast, not just
`capacity_relief`'s deferred-slot case) is future work, flagged and
pre-registered, not attempted here — this experiment's job was to measure
the gap honestly, not patch the P0 mechanism that the committed
`results.json` headline depends on.

## P1b — menu fairness: how much of the cart's edge survives a public menu

The mitigation for the 45%-discrimination-ceiling caveat (P0's "personalized
sub-list conversion of lookers" component): a broker that publishes a
**small menu of person-INDEPENDENT price boards**, derived only from
`hour_of(tick)` (population WTP statistics — the same `DRINK_APPEAL` /
`TOP_APPEAL` that calibrated the static list), never from any individual's
disclosed willingness. `boba.policies.menu_for_context(hour)` doesn't even
accept a consumer argument; every persona facing the same hour sees the
byte-identical tuple of tiers and self-selects the best one for THEM using
their own true preferences — no disclosure, no negotiation, nothing keyed
on who's asking.

**A flat "same drink, just cheaper" tier collapses immediately** (first
attempt, discarded): with no friction distinguishing a genuine looker from
a buyer who'd have paid list, EVERY buyer prefers the cheaper price
(surplus is monotonic in price for identical goods), so the discount tier
is taken by 100% of buyers, not just the lookers it was priced for —
P0's per-SKU-cannibalization lesson (vend P0 / this doc's static-vs-
computed tie) recurring one level up, at the bundle-menu level. The
shipped design instead pairs each posted markdown
(`world._value_price` — the profit-max price over *only* the sub-list
segment, `argmax_{cost<p<list} (p−cost)·(SF(p)−SF(list))`, the
person-independent analog of the cart's Nash-split looker conversion)
with a REAL screening friction, matching the task's own framing —
**quantity, pickup-time, and topping bundles**:

- `list` — the static board, always available, no friction.
- `topper` — drink at list, TOPPINGS at the value markdown. Self-limiting
  without extra machinery: `best_menu_order` only adds a topping the buyer
  actually values above its price, so a buyer with no topping taste sees
  this tier collapse to identical-to-list. (Partial leak, see below —
  genuine desire for a topping isn't the same screen as price
  sensitivity.)
- `bundle` — drink AND toppings at the value markdown, but ONLY at
  qty≥2 (`_best_order_min_qty`) — a real "2 for" bulk deal. A solo buyer's
  low `qty_decay` makes a 2nd cup worth little regardless of price, so
  this doesn't collapse the way the flat tier did.
- `value-defer30` / `value-defer60` — the value prices plus a balk-free
  pickup slot, offered only in `PEAK_HOURS` (the structurally congested
  hours) — screens on flexibility (`RIGID_DEFER` costs real dollars).

**Headline, flagship cell (shock=0, flex=0.35), 60 paired days, block=5 CI:**

| arm | seed 20260710 | seed 7 |
|---|---|---|
| cart vs static (margin Δ/day) | +$356.65 [345, 369] | +$346.04 [331, 361] |
| **menu vs static (margin Δ/day)** | **+$33.09 [18, 48]** | **+$33.70 [21, 46]** |
| menu-no-defer vs static (margin Δ/day) | −$11.16 [−29, 7] — tie | −$11.97 [−24, 0] — tie |

**≈9.3–9.7% of the cart's margin edge survives** a strictly
person-independent menu (+$33/day of +$346–357/day) — both seeds
significant and tight. Consumer surplus tells the other half of the
story: menu's CS Δ is +$425–435/day, **≈83–87% of cart's own +$502–513/day**
— far more than the margin-survival ratio, because a public menu gives up
Nash-bargaining leverage: whatever value gets created is split more in the
buyer's favor once the shop can't tailor the ask.

**Decomposition — discrimination vs logistics, as pre-registered:**

| lever | cart (P0 ablation, RESULTS.md, flex=0.35) | menu (this cell) | survival |
|---|---:|---:|---:|
| discrimination + attach (`topper`+`bundle`, no slots) | +$143.0/day | −$11.2 to −$12.0/day (statistical tie) | **≈0%, arguably negative** |
| logistics / capacity smoothing (adding slots) | +$206.4/day | +$44.3 to +$45.7/day | **≈21–22%** |

**Pickup-time smoothing is fairness-clean, exactly as pre-registered —
and it is now the ENTIRE surviving edge.** The `topper`/`bundle` tiers
alone are a statistical wash against static (both seeds' CIs straddle or
sit at zero) — none of the cart's $143/day personalized-pricing/attach
component survives a real menu-fairness constraint; the discount posted
to the whole sub-list-eligible population costs about as much on buyers
who'd have converted anyway as it gains from the ones it newly converts.
Every dollar of the menu arm's positive margin comes from the defer
tiers. Logistics itself only partially survives (≈21–22%, not the ~100%
"free lunch" the "fairness-clean" framing might suggest): deferred order
*count* drops from 104/day (cart) to 32.7/day (menu) — a flat, posted
defer discount doesn't size itself to each buyer's actual
relief-value/defer-cost tradeoff the way cart's Nash split does, so fewer
buyers find it worth the wait, and the shop captures less of the freed
capacity's value. Still: a genuine, fairness-clean, positive, replicated
result — the one lever the task predicted would survive is the one that
did.

**A bonus finding, not pre-registered:** the menu arm is *structurally*
immune to the entire P1a liar battery — `menu_pick` never reads a
disclosure at all (`consumer.wtp` only enters when the buyer privately
compares the PUBLIC tiers against their own true preferences), so there is
no channel for the branch-flip exploit above to exist. Menu fairness solves
two problems the task named separately (the 45% discrimination ceiling AND
half of P1a's IC gap) with one mechanism, though at the cost documented
above: it recovers only a tenth of the cart's margin.

**Caveats (attack these first):** the `topper` tier's leak (genuine
topping-wanters get a discount whether or not they were price-sensitive)
is a real, if small, discrimination residual inside a "fairness-clean by
construction" tier — flagged, not hidden, and included in the reported
$143→−$11 number, not backed out of it. Pearls-expiry salvage is
deliberately omitted from the menu arm (P0 found it worth ~$0.05/day,
immaterial, and it is a live-batch signal that would force a
finer-grained cache key than `hour_of(tick)` for no measurable gain).
`_value_price` is a single global optimum per hour, not swept for
robustness the way the cart's price rungs are. The decomposition compares
against cart's *committed* P0 ablation numbers (`RESULTS.md`, seed
20260710, 30 days) rather than a fresh paired re-run at 60 days — a
second-order inconsistency (different day count) noted, not corrected,
since re-deriving that table isn't in scope here and the committed numbers
are themselves reproducible from `results.json`.
