# Block scene event schema — `block.week.v1`

The twin-blocks street scene (`block/web/`) renders from **one JSON file**,
`canned-week.json`. Today that file is a hand-authored canned preview; the
live wiring (B4) replaces it with `block/runner.py` output on the **same
schema**, so this document is the sim ↔ renderer contract.

Design north stars: `block/DESIGN.md` §0 (the twin-blocks shot), §4d (art
direction), §5 (honesty gates). Honesty rule carried from the sim: **every
on-screen number lives in this JSON, never in the renderer.** The renderer
does arithmetic (mature-delta × day-weight, cumulative sums) but authors no
magnitudes.

The scene runs **7 timelapse days** (`meta.days`), each ≈ `meta.day_seconds`
real seconds. Each timelapse-day sweeps a full clock from `day_start_hour`
(pre-dawn) through dawn / midday / night, so the dawn delivery ballet, the
midday crowd, and the neon-lit night all show every day. The two blocks
(`sticker`, `snhp`) run the **same seeded population**; they start identical
(day 0) and diverge — that divergence IS the fairness-v2 result made visible.

---

## Top-level shape

```
{
  "schema": "block.week.v1",
  "meta":     { ... },     // clock, worlds, HUD labels, honesty badge
  "venues":   [ ... ],     // the 10-storefront roster (order = street order)
  "regulars": [ ... ],     // named recurring characters + their churn schedule
  "ledger":   { ... },     // the paired counters' source numbers
  "crowd":    { ... },     // ambient density, intraday curve, receipt pool
  "mood":     { ... },     // sticker-block desaturation by day
  "decay":    { ... },     // per-venue sticker spoilage/clearance by day
  "weather":  [ ... ],     // per-day weather (demand shocks made visible)
  "beats":    [ ... ]      // the scripted, visible per-event stream
}
```

## `meta`

| field | meaning |
|---|---|
| `day_seconds` | real seconds per timelapse-day at 1× dial (default 6) |
| `days` | number of timelapse days (7) |
| `day_start_hour` | clock hour each timelapse-day begins at (5.0 = pre-dawn) |
| `worlds` | `["sticker","snhp"]` — the two blocks, always paired |
| `badge` | the visible "canned preview" banner text (honesty gate) |
| `provenance` | where the numbers come from / why they are conservative |
| `hud_labels` | `{shopper, merchant}` — the two flip-clock counter labels |

## `venues[]`

The street roster, **rendered left→right in `slot` order**. Each future sim
in the repo is a storefront (DESIGN §4b-2 composition guarantee).

```
{ "id": "boba", "slot": 2, "label": "BOBA", "kind": "boba" }
```

`kind` selects the storefront art + signature micro-animation in
`venues.js`. Live wiring must keep `id` stable (it keys `ledger`, `decay`,
`crowd.receipt_pool`).

## `regulars[]`

Named recurring characters with **persistent, distinct silhouettes** so a
viewer can follow one person across the week and literally watch them stop
coming (DESIGN §4d). Same person renders on both blocks (mirrored) until they
churn off the sticker block.

```
{ "id": "maria", "name": "Maria", "persona": "local", "home": "bodega",
  "look": { "skin, hair, top, bottom, prop, hat, big? },
  "churn": { "sticker_lastday": 3, "reason": "anchor hike at the bodega" } }
```

- `look` drives the sprite: `prop` ∈ tote/coffee/backpack/satchel/cane/shopbag/none;
  `hat` ∈ scarf/phones/beanie/cap/none; `big` widens the body.
- `churn.sticker_lastday` — after this day the character no longer appears on
  the **sticker** block (they keep coming on the SNHP block all week). The
  `churn` beat (below) is the on-screen moment they walk up and leave.

## `ledger` — the counters' honest source

The two HUD counters ("shoppers kept $X", "merchants earned +$Y") are paired
differences (snhp − sticker), same variance-reduction design as every
vend/fashion experiment (DESIGN §2).

```
"ledger": {
  "day_weight": [0.03, 0.28, ... 1.00],          // per-day, index = day
  "per_venue_mature": { "boba": { "merchant": 24, "shopper": 40 }, ... },
  "block_mature": { "merchant": 118, "shopper": 188 }
}
```

- **Day `d`'s whole contribution** for a venue = `mature × day_weight[d]`.
  `day_weight[0] ≈ 0` enforces the "blocks start identical" gate.
- HUD value at time `t` (fractional days) =
  `Σ_{d<⌊t⌋} block_mature·day_weight[d]  +  frac·block_mature·day_weight[⌊t⌋]`.
  So the counters climb smoothly with the dial and land on the week total.
- `per_venue_mature[*].src` cites the published result (or names the
  candidate venue) each number traces to — the honesty gate.

**Live wiring:** `block/runner.py` already emits per-`(world, venue, day)`
deltas via `block/ledger.py` (`day_delta`, `block_day_delta`,
`paired_deltas`). Emit `per_venue_mature` from the realized daily deltas and a
`day_weight` ramp (or emit the raw 7×10 grid — the renderer only needs
per-venue-per-day `merchant`/`shopper` deltas; the mature×weight form is a
compression for the canned file).

## `crowd`

```
"crowd": {
  "seed": 20260710,
  "ambient_concurrent": { "sticker": [15,15,14,12,...], "snhp": [15,15,16,17,...] },
  "hour_weight": [24 multipliers, index = clock hour 0-23],
  "receipt_rate_per_hour_snhp": 5.0,
  "receipt_pool": { "boba": [ ["pickup 4:15 −$1.35", 1.35], ... ], ... }
}
```

- `ambient_concurrent[world][day]` — how many **anonymous** walkers populate
  the block. Sticker thins day over day; SNHP holds. Named regulars are drawn
  in addition to these. The renderer places ambient walkers deterministically
  from `seed` (so screenshots are reproducible).
- `hour_weight[hour]` — intraday multiplier (rush peaks, dead nights) applied
  to the concurrent count.
- `receipt_pool[venue]` — `[label, shopper_saved]` templates. On the SNHP
  block the renderer pops these as confetti tickets at
  `receipt_rate_per_hour_snhp`. Labels are flair; the authoritative counter is
  `ledger` (receipts never drive the total, so they can't drift it).

## `mood.gray`

```
"mood": { "gray": { "sticker": [0,0.06,0.14,...0.58], "snhp": [0,0,0,...] } }
```

Sticker-block desaturation 0→1 by day — the block grays as regulars churn
(divergence-as-drama). Applied as a `saturation`+`multiply` wash over the
whole sticker panel. **Day 0 = 0 on both blocks: identical.**

## `decay.sticker[venue]`

Per-venue sticker decay 0→1 by day, driving the venue's own decline art:
spoilage bins fill (bodega, bakery, boba), flower buckets fade to gray,
fashion clearance racks deepen, neon dims, gates stick. SNHP venues stay at 0.

## `weather[]`

Per-day, index = day: `clear | rain | overcast`. A demand shock made visible
— rain thins both blocks, darkens the sky, adds umbrellas + puddles.

## `beats[]` — the scripted per-event stream

The ordered stream of **visible narrative moments**. This is the shape live
wiring emits per event (the ambient crowd + receipt confetti are generated
from `crowd`, so `beats` carries only the things a viewer actually notices).

Common envelope: `{ day, hour, world, type, ... }`.

| type | fields | renders as |
|---|---|---|
| `truck` | `venue, supplier, negotiated, shared_with?` | dawn delivery. `negotiated` ⇒ handshake sprite; else clipboard. `shared_with` ⇒ one truck serves two adjacent bays (SNHP route density, DESIGN §4d dawn ballet). |
| `churn` | `regular, venue, reason` | the named regular walks to the venue, pauses, and leaves — after `day` they stop appearing on the sticker block. The emotional beat of depopulation. |
| `spoil` | `venue, kind:"bin"` | a spoilage bin appears/fills behind the sticker venue. |
| `clearance` | `venue, pct` | a `−pct%` clearance rack appears on the sticker fashion/vintage front. |
| `receipt` | `venue, label, shopper_saved, merchant_gain, regular?` | a confetti ticket pops (SNHP). (In the canned file most receipts are generated from `crowd.receipt_pool`; a `beats` receipt is a scripted, character-attached one.) |

### Mapping to the existing sim event log

`block/ledger.py` already logs `arrival`, `venue_entered`, `deal`, `no_sale`.
The scene stream is a thin projection of those:

| ledger event | scene beat |
|---|---|
| `arrival {world,day,tick,uid,persona}` | ambient `walk` (or a named regular if `uid` is one) — the renderer generates these from `crowd`, but live wiring can also emit them explicitly |
| `venue_entered` | walker turns into the venue door |
| `deal {..., spend, surplus, negotiated}` | on SNHP, a `receipt` (label from sku+discount, `shopper_saved` = surplus gain, `merchant_gain` = margin delta) |
| `no_sale {reason: balk/lost/stockout}` | a `churn` beat if the walker is a tracked regular; else the walker leaves without entering |
| (new, dawn layer B5) | `truck` — the wholesale tier's shared delivery window |

**What live wiring will need from `block/runner.py`:**

1. **Clock projection** — the runner's 10-minute block ticks mapped to
   `(day, hour)`. The scene wants a wall-clock hour per event, not tick index.
2. **The paired delta grid** — per-`(venue, day)` `merchant` (margin Δ) and
   `shopper` (consumer-surplus Δ) from `ledger.day_delta`, shaped into
   `ledger.per_venue_mature` (+ a `day_weight` ramp) or a raw 7×10 grid.
3. **Regular identity + churn** — a stable `uid → regular` map, and the day a
   tracked regular's sticker-world attendance goes to zero (readable from the
   `no_sale`/attendance record). The canned file hard-codes `sticker_lastday`.
4. **Per-venue decay signal** — spoilage units / clearance depth / balk rate
   per `(venue, day)` on the sticker world → `decay.sticker` 0-1.
5. **The dawn/truck layer** — the B5 wholesale tier's delivery windows
   (`venue, supplier, negotiated, shared_with`); until B5 ships, `truck` beats
   are illustrative of route-density logrolling.
6. **Weather / demand-shock flags** per day → `weather[]`.

Anything the renderer doesn't recognize is a no-op (forward-compatible, same
rule as `arena/EVENTS.md`).
