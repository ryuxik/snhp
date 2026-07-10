# FASHION — the season is a negotiation (sketch, v0)

*Sketch 2026-07-09. Builds on vend/DESIGN.md; reuses the same core. Status:
design only — build after VEND P2/P3 ship and the leaderboard week clears.*

## 1. The problem, in the industry's own terms

Fashion retail runs the **markdown cliff**: MSRP → 30% → 50% → 70% clearance
on a calendar. It is a negotiation the retailer loses on purpose: one absurd
opening offer, months of silence, then capitulation on a published schedule
that customers learned decades ago — which is why the rational customer
waits, and why nobody pays full price. J.C. Penney tried to exit the game
unilaterally in 2012 (everyday fair pricing, no games) and nearly died: you
cannot quit a game your counterparty is still playing. The pitch is never
"end discounts" — it is "play the season strategically."

Enterprise markdown optimization (Oracle, Blue Yonder) exists at six-figure
contracts for big chains. The wedge is everyone else: **markdown-as-an-API**,
$49/month Shopify-app economics, powered by the same engine on the
leaderboard.

## 2. Mapping onto the VEND machinery (what's reused)

| vend concept | fashion instance |
|---|---|
| SKU | style × size (the size dimension is load-bearing — see §3) |
| day / tick | week / day; season = 12–16 weeks, then salvage |
| nightly restock | NONE — one buy at week 0 (this is the whole game) |
| salvage | outlet/jobber recovery (~15–25% of cost) |
| list price | MSRP (the ceiling; discount-only clamp unchanged) |
| day shocks | weather/trend shocks; miscalibration = the buy itself |
| DemandLearner | weekly sell-through posterior per style×size |
| patience knob | STRATEGIC WAITING is now a first-class consumer type |

Because there is no restock, the shadow price of a unit is its option value
over the remaining season — the finite-horizon GvR case the engine's
`posted_price` module was built for. The vend code's "carry value = restock
cost" simplification is exactly what changes.

## 3. Size risk — fashion's natural commitment device

The reason not to wait for 70% off is that your size will be gone. That is
a *credible, structural* anti-waiting force — no artificial urgency needed.
The engine should **price it explicitly**: per style×size, the posted price
carries a stockout-hazard term, and the honest UX shows the trade ("price
falls as the season goes; 3 left in your size — lock it or gamble"). A
strategic-waiting consumer facing correct size-risk pricing is indifferent
at the engine's price — that is the equilibrium the cliff never finds.

Modeling: consumer types (loyal-now / strategic-waiter / clearance-only)
with a waiting-cost distribution; waiters re-arrive weekly, observe price
path + size availability, exercise optimal stopping. THE experiment: the
cliff trains waiting (waiter share grows across simulated seasons under
cliff pricing); the engine's smooth size-risk-priced path does not.

## 4. The three arms (mirrors vend exactly)

1. **cliff/1** (control): MSRP weeks 0–7, −30% weeks 8–10, −50% weeks
   11–13, −70% clearance — the industry default, honestly implemented.
2. **markdown/1**: finite-horizon posted-price resolve per style×size,
   weekly (sell-through posterior + size-level scarcity + salvage floor).
3. **offer/1 (A2A)**: engine-backed **"make an offer"** on the product page
   — the buyer names a price; the machine-side engine accepts/counters from
   inventory state + season clock, honored via price link. This is
   `nash_quote` with the sticker counterfactual as the disagreement point,
   verbatim — and where reservation-price DATA accumulates (the moat: after
   one season of offers, the retailer owns a demand curve nobody else has).

## 5. Pre-registered expectations

- H-F1: markdown/1 beats cliff/1 on season gross margin at realistic buy
  miscalibration (the buy is the sticker-error analog; σ on ordered depth
  and on WTP estimate), primarily via fewer units hitting −70%.
- H-F2: offer/1 ≥ markdown/1 with consumer surplus ≥ cliff, gains
  concentrated in (a) broken-size endgames and (b) strategic-waiter
  conversion at week 6–9 (they reveal reservations the posted path can't
  see). Same disclosure-beats-inference mechanism P1.5 proved.
- H-F3: under cliff pricing, waiter share grows season-over-season; under
  engine pricing it stabilizes (the "training your customers" claim, made
  falsifiable).
- Anti-claims we accept if found: if the cliff's simplicity wins at low
  miscalibration, we publish it — the omniscient-buyer row of the vend grid
  says it might.

## 6. Guardrails (unchanged, they matter more here)

Discount-only off MSRP; context-based (size/stock/week), never
person-based; offer counters keyed to inventory state, not the individual;
receipt shows why ("week 9, 2 left in M, season ends in 4"). Fashion is
where surveillance-pricing optics are deadliest — the transparent size-risk
trade IS the marketing.

## 7. Build shape (when scheduled)

`fashion/` mirroring `vend/`: season world (one buy, no restock, size
grids, waiter types) ≈ 1 day; arms (cliff + markdown reuse
posted_price/learner; offer/1 reuses nash_quote) ≈ 1 day; experiment grid
(buy-error × waiter-share) + writeup ≈ 1 day. Demo: same theater — YOUR
AGENT vs THE BOUTIQUE over PRICE × SIZE-RISK × TIMING; the make-an-offer
widget is the first Shopify-shaped surface.

## 8. GTM note

The pilot conversation writes itself for any boutique sitting on last
season's buy: "connect your Shopify, we replace your markdown calendar, you
pay us out of the margin we save." The vend grid is the evidence; the offer
widget is the hook; the season data moat is the retention.
