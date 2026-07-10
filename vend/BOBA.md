# BOBA — the vend sim grown into a real shop (sketch, v0)

*Sketch 2026-07-10. The strongest pilot vertical yet: app-native ordering
(the cart demo maps 1:1), independent operators with gut pricing (high
miscalibration — where we win), and a genuinely richer negotiation surface
than vending.*

## Why boba specifically

- **Ordering is already a cart on a phone.** The rung-2 design (cart =
  intent, sliders = disclosure, budget = walk-away) is the existing UX of
  every boba app — zero behavior change to introduce a negotiated total.
- **Made-to-order with a capacity constraint.** The scarce resource isn't
  just inventory, it's barista-minutes: ~1–2 drinks/min at peak, a queue,
  and abandonment when the wait is long. This adds the issue vending never
  had: **pickup time.** A buyer flexible on WHEN is worth a discount that
  costs the shop nothing — pure capacity smoothing, pure logroll.
- **Batch perishables on an hours clock.** Tapioca is cooked in batches
  with ~4h of quality life; end-of-batch is the natural markdown surface
  (the vend expiry logic with shelf_life measured in ticks, not days).
- **High-margin add-on issues.** Toppings ($0.50–0.75, ~90% margin) and
  size/sweetness are real bundle dimensions: "add pearls for 30¢ if you
  take the 4:30 pickup" is a three-issue package the engine already speaks.
- **Group orders = the multi-unit case with teeth** (5 drinks, one buyer).

## Realistic parameters (calibration targets, to verify against a real shop)

drinks $5.25–6.75 list; ingredient cost ~$1.10–1.60; toppings 55–75¢ at
~10¢ cost; capacity 1.5 drinks/min (2 staff peak, 1 off-peak); demand:
after-school (15–18h) and lunch spikes, weekend afternoon heavy; tapioca
batches of ~40 servings, 4h life, ~2 batches/day decided by gut; queue
abandonment ~8%/min of expected wait; mobile-order share 40–70%.

## What's new vs vend/ (the build delta)

1. **Capacity + queue in world.py**: service rate per tick, a queue, wait-
   sensitive conversion; profit loses abandoned orders — the shop's shadow
   price of PEAK capacity replaces (adds to) the stock shadow price.
2. **Pickup-time as a bundle issue**: outcomes = (drink, toppings, qty,
   price, pickup_slot). The machine's utility of an off-peak slot = the
   value of the peak barista-minutes it frees (event-consistent: the
   no-deal world is the buyer ordering at peak or walking).
3. **Batch decisions**: how much tapioca to cook and when — the "buy" of
   fashion on a 4-hour clock; markdown = end-of-batch, computed.
4. Arms: static menu (control) / computed menu (posted, GvR-style) /
   **cart-negotiation (a2a with min_gain + event-consistent disagreement,
   verbatim from vend)** / same attestation-tier experiment.
5. Pre-registered: the win concentrates in (a) capacity smoothing at peak
   (pickup-slot logrolls), (b) end-of-batch clearance, (c) topping upsells
   priced into bundles; at a perfectly-priced menu with slack capacity the
   sticker ties (the vend weak-dominance result should replicate).

## The anchor lesson applies here first

The vend anchor experiment (WorldConfig.anchor_peak) showed the ceiling's
PLACEMENT is worth more than the pricing policy under it (+$6.6/day just
from a peak-optimal sticker) and that "surge value without surging" is
capturable: post the peak price, negotiate down everywhere else. Boba menus
are exactly where a high anchor + visible computed discounts ("4:30 pickup:
−80¢") reads as generosity, not gouging.

## Pilot shape

One real shop's POS export (any format; EVA-DTS not needed here) →
calibrate arrivals/WTP/capacity → replay their actual month vs the
computed-menu and cart-negotiation arms → hand the owner a one-pager:
"your month, re-priced: +$X margin, −Y% peak abandonment, customers keep
$Z more." That's the whole sales deck.
