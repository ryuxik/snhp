# B0 RESULTS — first twin-run numbers (two-venue block)

*2026-07-10. Committed artifact: `block/results.json` — rerun with*

```
python3 -m block.runner --days 30 --seed 20260710 --regulars 25 --out block/results.json
python3 -m pytest block/tests -q          # 20 tests, ~5s (incl. 30-day twin)
```

*30-day twin (sticker world vs SNHP world, identical seeded population),
σ_cal = 0.15, honest anchor (×1.0), 25 regulars. Runtime 2.4s on one core
(budget: 60s).*

## Headline (per day, paired, 5-day-block CIs)

| venue   | sticker margin | snhp margin | Δ margin           | Δ CS    |
|---------|---------------:|------------:|--------------------|--------:|
| vending |        $135.54 |     $130.80 | **−4.74** [−7.5, −2.0] | +11.58 |
| bodega  |      $2,992.00 |   $2,983.21 | **−8.79** [−10.9, −6.7] | −6.36 |

HUD over 30 days: **shoppers kept +$156.72 · merchants earned −$405.99.**
Margins are net of calibration rents (bodega $400/day; the machine has no
rent line in calibration — flagged as a pilot-data target).

## What actually happened

- **The block composes.** The bodega really is the machine's outside
  option now: 534.8 bodega tx/day (target 550), ~70 arrivals/day headed to
  the machine, and in the sticker world 459 of the machine's 1,024 street
  sales were bodega-home walkers it poached — endogenously, not by the
  ×1.15 formula.
- **The one clean SNHP win is sticker-error recovery.** The noised
  operator overpriced cola-20oz at $3.65 (true optimum $3.00; the bodega
  posts $3.25). Sticker world: 6.1 of 12 cola/day sell. SNHP world: quotes
  averaging −$1.65 off list recover cola to 11.9/day. That is the machine's
  entire units gain (+5.8/day).
- **Everything else is a leak.** Every OTHER SKU sells out daily in BOTH
  worlds — the calibration makes the machine oversubscribed (par 64 units
  vs ~70 home arrivals plus 550 potential defectors). A discount on a
  sellout SKU is a dollar-for-dollar transfer to the shopper. Yet the
  engine kept issuing ~5–6 street quotes/day at steady state (−$4.28/day
  margin after the day-5 warmup, so it is NOT a warmup artifact).

## Surprise 1: forecast-noise adverse selection

The vend shadow-price guard prices displacement off `expected_list_demand`,
whose level after day 1 is the learner's EWMA of REALIZED units — which on
a sellout machine is capacity-censored (it learns "12/day" when true
list demand is higher), and whose intraday shape is still vend's
office-tower curve. The Nash search fires **exactly when that forecast
over-estimates excess** — a winner's curse against the machine's own
forecast error. vend's min_gain buffer (0.75/0.15) was calibrated to a
~$2/day control leak in the 65-arrival office lobby; on the oversubscribed
block it passes −$4.7/day (−$14.4/day with a PERFECT sticker, σ_cal = 0,
where there is nothing to recover and every quote is displacement).
**B1 fix candidate:** a sellout-aware demand floor (stockout time observed
→ demand ≥ stock/remaining_frac), or simply a stricter buffer when
stock-to-go < forecast demand.

## Surprise 2: at the honest sticker, block-total surplus falls

Default world: shoppers +$5.2/day net, merchants −$13.5/day → total
−$8.3/day. Negotiation on capacity-constrained stock mostly REALLOCATES
scarce units toward earlier/lower-WTP buyers and burns real cross-venue
walk costs (CS is booked net of walks). Both worlds sell ~the same units;
SNHP just sells them cheaper and to different people. The composition
lesson: **negotiation creates surplus where the sticker is wrong or the
stock is excess; where a strong sticker meets excess demand it only moves
money.** Consistent with the arena honest-read.

## Surprise 3: the anchor probe replicates fairness-v2 on the block

At anchor ×1.5 (probe): the sticker machine HARVESTS within the 30-day
window (margin $168.79/day, up from $147 honest — captive walkers pay up
on the 5 goods the bodega doesn't carry), but churns 11 of 25 regulars.
The SNHP machine ties it on margin (Δ −3.23, CI spans 0) while consumers
keep +$35.06/day, the bodega loses −$27.85/day (quotes claw its defectors
back), and churn drops to 4. Shoppers kept +$702.80 over 30 days. The
churn bleed is the anchor's real cost and 30 days barely shows it —
fairness gating remains the point.

## Calibration honesty

Realized vs target: 631.5 arrivals/day (620 street by construction +
regular visits ride on top — documented approximation), bodega 534.8
tx/day vs 550 (conversion is endogenous), vending sees its 70. Funnel
fraction derived, not tuned: 620/4200 = 14.8% of walkers shop.

## Shortcuts taken (all documented in-code)

- Bodega is a non-adopter in B0: calibration prices in BOTH worlds; no
  deli-waste model; deep stock (300/item) restocked daily.
- Bodega-only goods get WTP μ = posted price × 1.08 (calibration publishes
  prices, not WTPs; the 1.08 matches the vending μ/price ratios).
- Non-overlap `Listing.bodega_price` = ×1.15 off the TRUE-μ optimal
  sticker (anchor-independent, vend's convention) — NOT off the anchored
  list, so the anchor probe can't inflate the engine's believed outside.
- No day-of-week, day shocks, or same-day return queue (B0).
- Street shoppers carry no reference-price fairness (only regulars do) —
  carried caveat from DESIGN §5.
- Regulars' off-machine bodega purchases move money, not reference prices
  (vend's psychology stays machine-scoped in B0).
