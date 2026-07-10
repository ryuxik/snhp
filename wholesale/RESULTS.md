# WHOLESALE TIER (B5) — pre-registration and results

*2026-07-10. The B2B side of the block (DESIGN §4b): three wholesalers
(beverage, produce/deli, dry-goods) x four venues (bodega, boba, vending
operator, bakery-deli) negotiate weekly stocking, with and without SNHP.
Pure math, paired weeks, seeded. Rerun:*

```
python3 -m wholesale.run --weeks 26 --seeds 8 --grid --out wholesale/results.json
python3 -m pytest wholesale/tests -q
```

## Pre-registered predictions (written BEFORE the first run)

Hypotheses fixed from block/DESIGN.md §4b before any simulation was
executed. Metrics: realized weekly surplus, paired by (seed, week) —
identical demand forecasts and realizations across arms by construction —
CIs over 8 seed-level means (t, n=8). Arms: `ratecard` (posted rate card +
published volume breaks, FCFS delivery — the industry control), `nego`
(Nash per relationship-week over the full bundle: price x window x
quantity x terms x spoilage-sharing, wholesaler coordinating across the
block), `nego-indep` (coordination ablation), and one `nego-no-<issue>`
arm per issue (the issue frozen at its rate-card default).

- **H-W1 (window/route-density is the biggest lever).** Freezing the
  delivery-window issue costs more realized JOINT surplus than freezing
  the price issue: `joint(nego) − joint(nego-no-window)` >
  `joint(nego) − joint(nego-no-price)`, at every grid cell. Reasoning
  pre-committed: price rungs mostly TRANSFER surplus (they create none),
  while window choice moves real resources — receiving labor, slot shadow
  values, and the $45-stop-vs-$8-drop route-density margin. This is the
  boba pickup-slot result one tier up.
- **H-W2 (both sides beat the rate card).** vs `ratecard`, the nego arm's
  realized surplus rises on BOTH sides of the market in aggregate:
  venue-side Δ > 0 (landed cost + window fit + financing + spoilage
  terms) AND wholesaler-side Δ > 0 (route density + slot values +
  retention of would-be cash-and-carry defectors). Secondary (weaker)
  prediction: every per-venue row and every per-wholesaler row is ≥ 0.
- **H-W3 (route density is a CROSS-VENUE effect).** The wholesaler's gain
  depends on coordinating across the block: wholesaler-side surplus
  (nego) − (nego-indep) > 0, and shared windows per week are higher under
  coordination. Quantification pre-committed: coordination accounts for a
  material share (> 20%) of the wholesaler-side Δ vs rate card at the
  headline cell (noise 0.15, flexibility 0.7).

Secondary expectations (directional, lower confidence): the window lever
grows as venue flexibility falls (higher receiving-labor stakes); the
spoilage-sharing lever grows with demand noise (more overage risk to
share); the terms lever concentrates on cash-tight venues (bodega,
bakery).

Buffer honesty: negotiated deals require the wholesaler's believed gain to
clear max($5, 3% of order list value) over its event-consistent
disagreement (the rate-card sale it already had, or a freed slot when the
venue's cash-and-carry alternative wins) — the vend/scenario.py rule, one
tier up. When negotiation fails, the disagreement EVENT executes (the
venue still buys at the posted rate card or runs to Jetro), so the nego
arms are never worse than the control by construction on the venue side;
the wholesaler side CAN lose (that is what H-W2 tests).

## Results (26 paired weeks x 8 seeds, grid run of 2026-07-10)

*Committed artifact: `wholesale/results.json` (8 arms x 4 grid cells,
runtime 7.4s on one core). 18 tests, ~1s. Headline cell: demand noise
0.15, flexibility 0.7. All dollars are realized $/block-week; CIs are 95%
t-intervals over 8 seed-level means.*

### Headline: Δ vs the rate card, both sides of the market

| VENUE-SIDE | nego                    | nego-indep             |
|------------|-------------------------|------------------------|
| bodega     | +1.73 [0.91, 2.54]      | +1.73 [0.91, 2.54]     |
| boba       | +77.26 [71.98, 82.54]   | +11.40 [10.65, 12.15]  |
| vending    | +63.73 [60.21, 67.25]   | +3.84 [3.46, 4.22]     |
| bakery     | +4.47 [2.80, 6.14]      | +14.27 [13.09, 15.45]  |
| **TOTAL**  | **+147.19 [142.4, 152.0]** | +31.23 [29.55, 32.91] |

| WHOLESALER-SIDE | nego                 | nego-indep             |
|-----------------|----------------------|------------------------|
| beverage        | +74.59 [74.27, 74.92]| +11.74 [11.44, 12.05]  |
| produce/deli    | +49.00 [42.48, 55.51]| +0.00 [0.0, 0.0]       |
| dry-goods       | +59.05 [57.80, 60.31]| +15.21 [12.68, 17.74]  |
| **TOTAL**       | **+182.64 [175.7, 189.6]** | +26.95 [24.66, 29.25] |

Levels for scale: wholesaler-side surplus 794.61 -> 977.26 (**+23%**);
block joint +329.83/wk (+3.7%). The truck is where the money is: stops/wk
9.0 -> 3.07, AM stops 6.0 -> 2.94, realized route cost $555 -> $263/wk
(−53%). Only 51% of relationship-weeks actually negotiate — the rest fall
back to the posted card because the wholesaler's 3%-of-order buffer
exceeds the available non-density gains (mostly the big bodega/bakery
lines). SNHP negotiates where it creates surplus and posts otherwise.

### Hypothesis verdicts

- **H-W1 — SUPPORTED, at every grid cell.** Joint $/wk lost when the
  issue is frozen at its rate-card default (headline cell): **window
  +320.97 [317.1, 324.8]** > price +80.64 [75.4, 85.9] > qty +27.54 ≈
  terms +27.34 > spoilage −0.29 [−3.3, 2.7]. The window/route-density
  logroll is 4x the price lever. Same ordering at all four cells
  (window/price: 321/81, 130/118, 127/98, 307/57).
- **H-W2 — SUPPORTED.** Both sides gain vs the rate card at every cell;
  every per-venue and per-wholesaler row ≥ 0 (secondary prediction holds,
  but weakly: at flexibility 0.3 the bodega and bakery rows are exactly
  $0 — they never negotiate, see the buffer note above). The wholesaler's
  gain decomposes as route density + slot release + net-30 terms + extra
  perishable volume; NOT retention — see surprise 3.
- **H-W3 — SUPPORTED, stronger than pre-registered.** Coordination value
  (nego − nego-indep, wholesaler side) = **+155.69 [146.7, 164.7]** —
  **85% of the wholesaler's total gain** (pre-registered threshold: >20%;
  other cells: 90–97%). Blind negotiation keeps only +26.95 of +182.64.
  One pre-registered sub-metric FAILED: shared-windows/wk is 3.0 in ALL
  arms — a saturated, non-discriminating count (FCFS already co-locates
  bodega+bakery coincidentally; coordination shows up as FEWER STOPS,
  9.0 -> 3.07, not more shared windows). The stop count and route cost
  carry the effect; the shared-window count was the wrong statistic.

### Surprise 1: price rungs are the grease, not the prize

Price is a pure transfer (it creates no joint surplus directly), yet
freezing it costs +80.64/wk of JOINT surplus — second-largest lever. In
`nego-no-price` the wholesaler side actually RISES (+1008 vs +977; no
discounts given) while the venue side collapses and the route stays
fragmented (4.43 stops vs 3.07): without the price instrument the Nash
point cannot compensate venues for taking wholesaler-dense windows, so
consolidations that need side-payments die. Discount-only price rungs are
what make the window logroll *clearable*.

### Surprise 2: the window lever needs slack — it SHRINKS when venues are rigid

Pre-registered secondary expectation was the opposite. At flexibility 0.3
the window lever falls from ~320 to ~128 $/wk (and negotiation coverage
drops 51% -> 34%): with only 3 zero-cost windows per venue there is often
NO mutually-cheap window to consolidate into, so the density logroll is
infeasible rather than merely valuable. Flexibility is the raw material
of the logroll — a pitch-relevant fact (the ask to venues is literally
"name more windows you can live with").

### Surprise 3: the cash-and-carry threat never fires, so "retention" is $0

Jetro (0.93 x base, $95 haul+time, COD, no breaks) wins the disagreement
in 0 of 9,984 relationship-weeks in EVERY arm — at these order sizes the
7% price edge never covers the trip. The event-consistent disagreement is
therefore always "the rate-card sale the wholesaler already had", which
is exactly what disciplines the engine into discounting only out of newly
created surplus. But it also means H-W2's predicted retention channel
contributed nothing; the wholesaler's entire gain is operational (route
density + slots + terms + volume). The Jetro bound still matters
structurally — it caps what the wholesaler could ever extract — it just
never binds in this calibration.

### Also honest

- Spoilage-sharing has no measurable joint lever (CI spans 0 at 3 of 4
  cells; +2.59 at noise 0.35/flex 0.3). In expectation it is ~a transfer;
  its newsvendor quantity effect is second-order at these margins. The
  pre-registered "grows with noise" direction is right but the magnitude
  is noise-level.
- Terms lever concentrates at high flexibility (+27 vs +5) mostly because
  more deals clear there at all; per-deal it is worth ~1–2% of invoice
  (the r_venue − r_wholesaler carry spread on net-30).
- Processing order matters at the margin: the first venue on the route
  sheet (bodega) can never capture a density credit — no stop exists yet
  when it negotiates — which is why its nego and nego-indep rows are
  identical. A second negotiation pass (or simultaneous solve) is the
  obvious B5.1 upgrade.
- `nego-indep` produce/deli row is exactly $0 everywhere: without the
  density credit, the wholesaler's share of terms/window gains on
  perishables never clears the 3%-of-order buffer. Coordination is not
  just most of the gain — for the perishable line it is ALL of it.

### Shortcuts taken (all documented in-code)

- One composite "case" per (wholesaler, venue) line; venue retail value
  per case is an attribution multiple of the rate-card base, not a SKU
  P&L. Weeks are independent newsvendor problems: durable overage carries
  over as salvage at 0.85 x base (no explicit inventory state).
- Jetro trips are priced per relationship-week (no consolidation of one
  trip across categories) — conservative AGAINST the rate-card arm's
  outside option, and it still never fires.
- Venue cash constraints enter only through per-venue financing rates
  (1.0–2.5%/mo around the DESIGN 4b ~1.5% center); no hard working-capital
  cap.
- FCFS control grants venue requests in fixed route-sheet order; a real
  dispatcher may route-optimize somewhat (the control could be ~$50–100/wk
  less bad than modeled; the coordination effect would shrink accordingly
  but the stop arithmetic — 12 venue-lines cannot beat 3 clustered stops
  without cross-venue visibility — survives).
