# THE BLOCK — a pixel-art NYC block where every price is negotiated

*Design v1, 2026-07-10. The flagship demo: one NYC block — bodega, boba
shop, fashion boutique, vending machine — with people walking in and out,
a commerce timelapse where every number on screen traces to a committed,
seeded simulation, and a running ledger of how SNHP helped everyone.*

## 0. The shot

A pixel-art street elevation (the arena's Castlevania-NES language, daylight
palette): four storefronts, walkers with personas (office worker, student,
tourist, local) flowing through a day/night cycle. People enter shops;
deals happen as small receipt popups ("2× sandwich −$2.10 · expires
tonight"). A timelapse dial runs days in seconds. Two HUD counters climb:
**"shoppers kept $X"** and **"merchants earned +$Y vs the sticker world"**
— both backed by a paired counterfactual sim (identical customer streams,
sticker-world vs SNHP-world), not vibes. Click any deal → the 3D duel
theater replays the actual negotiation (existing machinery).

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

## 5. Honesty gates

Every on-screen number traces to a seeded artifact (committed JSON, rerun
command in the info panel). The counters are paired differences with CIs
available on hover. Fairness caveat carried from the sticker experiment:
consumer models don't yet punish reference-price violations; anchors in the
block use the computed-discount design (high anchor, visible discounts)
pending the pre-registered fairness experiment.
