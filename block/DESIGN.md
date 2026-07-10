# THE BLOCK — a pixel-art NYC block where every price is negotiated

*Design v1, 2026-07-10. The flagship demo: one NYC block — bodega, boba
shop, fashion boutique, vending machine — with people walking in and out,
a commerce timelapse where every number on screen traces to a committed,
seeded simulation, and a running ledger of how SNHP helped everyone.*

## 0. The shot — TWIN BLOCKS

Two pixel-art street elevations, stacked or side by side: **THE STICKER
BLOCK** and **THE SNHP BLOCK** — the same four storefronts, and the SAME
people (paired seeds render as mirrored walkers entering both worlds).
They start identical and DIVERGE over the timelapse, and the divergence is
the fairness-v2 result made visible: on the sticker block under an
aggressive anchor, regulars stop coming back (the street visibly thins —
churn as depopulation), spoilage bins fill behind the bodega, the boutique
drowns in −70% clearance racks at season end, the boba queue balks at peak;
on the SNHP block the same people keep coming, receipts pop ("2× sandwich
−$2.10 · expires tonight"), pickup-time deals smooth the boba rush, and
the two HUD counters climb between the blocks: **"shoppers kept $X"** and
**"merchants earned +$Y"** — honest paired differences, because both
worlds run the identical seeded population. A timelapse dial runs days in
seconds; the community-level trajectories (active regulars, waste, queue
health) chart underneath. Click any deal → the 3D duel theater replays the
actual negotiation (existing machinery).

## 1. Why this is the demo

- It renders the thesis: invisible negotiation, everywhere money changes
  hands, both sides better off — visible as a living street.
- Every venue is an already-built sim: vend/ (machine), fashion/ (boutique),
  vend/BOBA.md (shop, next build), and the bodega — which today's sticker
  experiment proved is the load-bearing outside option — becomes a real
  venue instead of a formula, closing the block's economy.
- The pixel pipeline exists: arena/ runner → broadcaster → WebSocket →
  Canvas2D. The block is a new scene on the same rails, not a new engine.

## 2. Architecture

```
block/
  calibration.py   NYC prices/costs/traffic/rents — ONE source of truth
  population.py    the shared walkers: personas, schedules, WTP draws,
                   cross-venue substitution (the bodega IS the machine's
                   outside option, endogenously)
  venues/          adapters wrapping each sim's world+policy on the block
                   clock (vending verbatim; boba per BOBA.md; fashion runs
                   its weekly tick inside the block's 10-min ticks; bodega
                   = posted-price venue with its own inventory)
  ledger.py        the paired counterfactual: same seeded population runs
                   sticker-world and snhp-world; per-venue and per-consumer
                   deltas accumulate into the HUD counters
  runner.py        block clock, event stream (walk/enter/deal/receipt)
  web/             the street scene (reuse arena sprite/renderer modules)
```

Paired honesty rule: the timelapse renders the SNHP world; the counters are
differences against the sticker world running silently on the same seeds —
the same variance-reduction design as every vend/fashion experiment.

## 3. NYC calibration

All numbers live in block/calibration.py (committed, cited in-app via an
"where do these numbers come from?" panel). Rents included deliberately:
NYC margins are thin, so "+$X/day" reads honestly against fixed costs —
the pitch becomes "the engine pays N% of your rent."

## 4. Build phases

- **B0** calibration.py + population.py + vending↔bodega on the shared
  population with the paired ledger (the two-venue block proves the
  composition; the machine's outside option becomes the actual bodega).
- **B1** boba venue: capacity + queue + pickup-time-as-issue (the BOBA.md
  build, landing directly on the block).
- **B2** fashion venue: multi-timescale (weekly season inside daily block),
  the offer arm with waiter threat points.
- **B3** the street scene: sprites, storefronts, receipts, day/night,
  timelapse dial, HUD counters; deploy at /block (arena app).
- **B4** the block becomes the landing page: the leaderboard proves the
  engine, the block shows the world it builds.

## 4b. B5 — the wholesale tier (both sides of the business)

The venues' unit costs stop being constants and become NEGOTIATED inputs:
wholesalers (beverage distributor, produce/deli supplier, tea/tapioca
importer, apparel jobber) sell to the venues, with and without SNHP, in
both worlds. This is the natural home of the June A2A stack — registry,
verified peering, AP2 settlement — because B2B is where attestation is
already culturally required (businesses do KYC), relationships repeat, and
deals are genuinely multi-issue: price × delivery window × case size ×
payment terms × spoilage-sharing. Pre-registered predictions: (1) the
biggest B2B lever is DELIVERY-WINDOW logrolling against the wholesaler's
route-density capacity — the boba pickup-slot result one tier up; (2)
procurement and retail pricing are COUPLED (fashion P1 already showed a
buy planned to the cliff calendar poisons the season): joint
negotiated-procurement + negotiated-retail beats either alone; (3) the
flywheel — SNHP retail volume → better wholesale terms → lower costs →
better retail prices — compounds across tiers and the twin worlds show
margin stacking. The wholesaler's truck is a shared constraint across
venues, making it the block's first cross-venue coordination problem.

## 4b-2. Composition guarantee

Every standalone sim in this repo IS a future storefront: the venue-adapter
pattern (B0/B1/B2) wraps each package's world+policies onto the block clock
with the shared population, and the wholesale tier becomes the block's dawn
layer (trucks, windows, route density). Target roster for the full street:
vending machine, bodega, boba, fashion boutique, bakery, flower shop,
barbershop, parking lot, happy-hour bar, vintage store — each running
sticker-world vs snhp-world — plus wholesalers and (later) the courier as
infrastructure actors. A sim is not "done" until it has a storefront.

## 4d. Art direction — high quality AND playful (binding, not aspirational)

The bar is the arena's proven pixel language (Castlevania-NES heritage,
the Adam Ho design pass) applied warmly. Direction:

- **Regulars are recognizable characters.** Named sprites with persistent
  looks — you can literally watch Maria stop visiting the sticker block
  after the anchor hike. Churn becomes a story you follow, not a counter.
- **Every venue gets a signature micro-animation**: spinning barber pole,
  blinking neon boba cup, croissant steam, flower buckets whose colors
  fade with freshness, the parking gate arm, the bar's happy-hour glow,
  browsing hands at the vintage rack, fashion window displays that change
  with the season.
- **The dawn ballet**: wholesale trucks at 6am — a handshake sprite over
  negotiated deliveries, a clipboard over rate-card ones; two venues
  sharing one truck window on the SNHP block (route density, visible).
- **Street life**: pigeons, a bodega cat, dog walkers, rain days (demand
  shocks made visible as weather), day/night palette shifts.
- **Deals feel good**: receipts pop as tiny confetti tickets; the HUD
  counters are a flip-clock scoreboard; the timelapse dial is a chunky
  jukebox knob.
- **The divergence is the drama**: the sticker block slowly grays and
  thins as regulars churn; the SNHP block keeps its crowd. Emotional
  storytelling through crowd density, backed cell-by-cell by the ledger.
- **Everything clickable**: follow any walker; click any deal → the 3D
  duel theater replays the actual negotiation (shipped machinery).
- **Make-or-break gate** (the duel3d discipline): B3's first milestone is
  a canned-data street frame that a stranger finds charming and legible
  at BOTH 1280px and 375px before any live wiring happens.

## 4c. Venue candidates beyond the first four (each tests a NEW mechanism)

- **Bakery** — the friction-free wedge: end-of-day markdown culture already
  exists ("day-old shelf"); batch economics like boba. First to add.
- **Barbershop / nail salon** — pure appointment capacity, zero inventory:
  slot pricing + no-show risk; the boba scheduling result isolated.
- **Parking lot** — pure yield management, duration × start-time bundles,
  extreme real-world miscalibration; hilariously legible on a pixel street.
- **Bar happy hour** — the anchor-optics wedge: happy hour IS computed
  discounting by hour; we formalize an accepted ritual ("happy hour, but
  optimal") — the cultural cover for computed pricing.
- **Vintage/second-hand store** — one-of-one items: make-an-offer native
  (the fashion offer arm's true home; reservation-price data moat).
- **Flower shop** — extreme perishability + event demand spikes: fashion ×
  vending hybrid stress test.
- **Courier** (infrastructure actor) — delivery capacity shared across ALL
  venues: the block's second cross-venue coordination market.
- **Named non-fit:** pharmacy/regulated goods — price floors/ceilings and
  fairness sensitivities make computed pricing wrong there; excluding it
  deliberately is part of the honesty posture.

## 5. Honesty gates

Every on-screen number traces to a seeded artifact (committed JSON, rerun
command in the info panel). The counters are paired differences with CIs
available on hover. Fairness caveat carried from the sticker experiment:
consumer models don't yet punish reference-price violations; anchors in the
block use the computed-discount design (high anchor, visible discounts)
pending the pre-registered fairness experiment.
