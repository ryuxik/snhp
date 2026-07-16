# THE COMPANY — a live diorama of the swarm engine (v26-R, column Y, phases Y-A/Y-B)

A GROW-Cube-style cutaway building whose rules **are** the swarm engine's
measured mechanisms. It is **not scripted animation**: `index.html` replays
**real, seeded engine runs**, logged tick-by-tick by a pure observer. Flip the
regime toggle and watch the banked science happen — spot bargaining jams the
middle floors, claim stacks unjam them and fire launches, central command idles.

Registered contract: `research/swarm/SPEC.md` → **v26-R (column Y, REVISED)**
(Y-A the event logger, Y-B the renderer) and **Y1 VISUAL DIRECTION** (the GROW
Cube art direction). This directory is the whole deliverable; it is **not linked
from any arena page** (see the last section).

---

## What you're looking at

Three replay logs (`logs/spot.json`, `logs/claims.json`, `logs/director.json`)
are the **same seeded run under three of column X's regimes** (N=240, 2,500
ticks, seed 0). The building is a cutaway with five floors = the field's five
distance bands from the refinery (ground) to the far frontier (top). Little
round workers are the robots; an amber folder is an idea (a mined ore unit) a
worker is carrying; a coral folder + `!` is a **stalled** idea (routing
deadlock, the hold-up); a grey worker is out of budget (stranded). Deliveries
fire a **LAUNCH** off the loading dock; hand-offs pulse a green **✓ stamp**
(claims only); the director's corner office drips **order slips** to workers.

**The money shot — the regime toggle.** Every number on screen is either a live
counter from the loaded log or a banked SPEC verdict (labelled `SPEC verdict`).
At the same turn:

| regime   | ≥2-hop share (live) | shipped (live) | hand-offs (live) | illustrates            |
|----------|--------------------:|---------------:|-----------------:|------------------------|
| Spot     |  ~2.5%              | fewest→mid     | ~hundreds        | P23a / PXc baseline    |
| Claims   |  ~50–57%            | **most**       | ~thousands       | P23a / PXc             |
| Director |  **0.0%**           | **fewest**     | ~none            | PXa / KILL             |

This is the banked P23/X signature, live in the data — not asserted by the UI.

---

## The registered mapping (SPEC v26-R Y-A)

| company skin                    | engine mechanism                                   |
|---------------------------------|----------------------------------------------------|
| idea / project                  | asteroid ore unit                                  |
| research→design→build→ship      | distance bands (floors) far edge → refinery        |
| top floor (research/frontier)   | far band — ore is **mined** at the frontier        |
| middle floors (design/build)    | mid bands — where **hand-offs** happen             |
| ground floor (shipping)         | the refinery — **delivery**                        |
| stalled idea                    | routing **deadlock** (loaded, can't deliver 1-hop) |
| idea folder                     | a parcel (carried ore unit)                        |
| claim-stack stamp (stamp/hop)   | **bills** claim stack — the notarised receipt      |
| a LAUNCH off the dock           | a refined delivery                                 |
| worker budget / rest            | robot **battery / chargers**                        |
| the director's corner office    | the **command** regime (central planner)           |
| order slips arriving late       | plan **reach-latency / staleness** (X machinery)   |
| carriers between stages         | middlemen hand-offs (cargo transfers)              |
| stage workers                   | the ICs (robots)                                   |

Regimes are a **configuration of existing flags**, not new code: `arm=snhp+net`,
`belief_mode`+`gossip` (`r_radio=6`), `lineage` + the deadlock instrument on for
all three; then `spot={}`, `claims={bills:True}`, `director={command:True}` —
exactly `run.py`'s `column == "X"` cells.

---

## Honesty bindings (registered)

- **Every rendered element maps to a logged datum.** A worker's **floor** is its
  real distance band (computed from its logged `(x,y)` and the refineries). Its
  **slot within a floor** is a stable packed layout (by robot id), *not* a
  coordinate — density = the real per-floor count (the pile). No decorative
  agents exist; every dot is a logged robot.
- **Every number is real or banked.** Live counters (shipped, ≥2-hop share,
  stalled-now, hand-offs, budget, order-age) are computed from the loaded log.
  The caption's numbers are **banked SPEC verdicts**, copied verbatim, shown
  under a `SPEC verdict` badge with the exact figures in the hover footnote. The
  page states on-screen that it is a *replay of a real seeded run, time-
  compressed*, with the seed + config.
- **The logger is a pure observer (the FIDELITY KILL).** `company_log.py`
  constructs the World and reads its state after each `arm.tick()`; it never
  touches RNG / physics / Φ / any decision path and adds no mechanism. Running
  with the observer attached is **byte-identical** to running plain — guarded by
  `test_company_observer_bit_identical` and `test_company_observer_differential_oracle`
  in `research/swarm/test_swarm.py`.

---

## The floor / band mapping (as built)

Five floors, cut by the single-hop **loaded reach**
`R = BATTERY_MAX/(1+LOADED_MULT) = 62.5` cells — the same distance the
placement/deadlock code prices. Band edges are `[0.25, 0.55, 0.90, 1.40]·R`:

| floor (top→bottom) | label     | Manhattan band to nearest refinery |
|--------------------|-----------|------------------------------------|
| 4 (roof)           | frontier  | > 87.5 cells (the far edge)         |
| 3                  | research  | 56.25 – 87.5 cells                  |
| 2                  | design    | 34.375 – 56.25 cells                |
| 1                  | build     | 15.625 – 34.375 cells               |
| 0 (ground)         | shipping  | 0 – 15.625 cells (at the refinery)  |

The edges travel in each log's `floor_edges`; the renderer and logger agree.

---

## How to regenerate the logs

```bash
# all three regimes, N=240, seed 0, 2500 ticks (≈7 min; ~0.32 MB each)
python3 research/swarm/company_log.py --regime all

# one regime / smaller / faster
python3 research/swarm/company_log.py --regime claims --n 96 --ticks 1200
```

Logs are **trimmed for size** (each ≈0.32 MB, well under 3 MB — no gzip needed):
robot state is sampled **1 frame every 20 ticks** (`--sample-every`) and stored
as `[x, y, state]` per robot (`state`: 0 empty · 1 loaded · 2 stalled · 3 out-of-
budget); economic counters (delivered, ≥2-hop, hand-offs, deals, deadlock) are
**cumulative per frame**; the `summary` block holds the full-run totals the HUD
shows. Rising-edge stalls/strandings are tallied at full tick resolution.

### Tests

```bash
# engine side (bit-identity + schema + counts): part of the 122-test suite
python3 -m pytest research/swarm/test_swarm.py -q

# renderer side (checked-in logs parse; counters match summaries; contrast real)
python3 arena/web/company/test_company_logs.py
```

---

## Files

- `index.html` — the self-contained 2D-canvas renderer (no CDNs, GROW-Cube style).
- `logs/{spot,claims,director}.json` — the three checked-in replay logs.
- `README.md` — this file.
- generator + engine tests live in `research/swarm/company_log.py` and
  `research/swarm/test_swarm.py`; renderer tests in `test_company_logs.py`.

---

## NOT linked from the arena index (publication is a founder decision)

Per the Y1/Y-A/Y-B registration, this diorama's assets are **local until the
founder publishes**. It is intentionally **not linked** from `index.html`,
`leaderboard.html`, `science.html`, or any other arena page, and must stay that
way unless the founder decides to ship it. To view it locally, serve the
`arena/web` folder over HTTP and open `/company/index.html`
(e.g. `python3 -m http.server` from `arena/web`).
