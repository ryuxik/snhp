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
