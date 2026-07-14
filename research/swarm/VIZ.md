# Swarm benchmark visualization — spec

*Answers two needs: (1) intuition/debugging — SEE the economy run; (2) the
public money-shot — this is the "grid of crab robots doing something
impressive" image, and the X strategy atom is image+number.*

## v0: trace replay viewer (built — `viewer.html`)

**Pipeline:** sim → JSONL trace → self-contained HTML replay. No server-side
anything; the viewer is one file, works from `file://`, a static host, or a
claude.ai Artifact (no external deps, CSP-safe).

### Data contract (`trace.py` writes it)

One JSON object per line:

| line | fields | notes |
|---|---|---|
| `header` | grid, sources, sink, charger, arm, sigma, seed, total_stock, robots[{id,cap,eff,sector}] | static per run |
| `tick` | t, r=[[x,y,battery,load,stranded]…], stock, delivered, charged | robot order = header order |
| `xfer` | t, kind=energy\|cargo\|sector, src, dst, amt | physical exchanges, ALL arms |
| `deal` | t, a, b, q, e, s, sa, sb, capture | SNHP bargaining metadata |

`world.event_log` is populated by the physics methods themselves, so rule
firings (trophallaxis), auction handoffs, and bargained trades all emit the
same `xfer` events — the viewer never guesses what an arm did.

### Visual language

- **Grid:** dark field, faint lattice. Sites: sources = amber squares with
  remaining stock count, sink = green square with delivered count, charger =
  cyan square (queue visible as clustered robots).
- **Robots:** circles, radius ∝ capacity; fill = battery (green→amber→red);
  load shown as white pips; sector = thin outline color (two hues);
  stranded = desaturated + grey ✕.
- **Exchanges:** animated arcs between the two robots, fading over ~20 ticks —
  energy cyan, cargo amber, sector-swap violet dashed. SNHP deals get a
  caption at the arc midpoint with the barter terms, e.g. `1▣ ⇄ 4⚡ +swap`.
  This caption IS the thesis in one image: a scalar bid can't say that.
- **HUD per panel:** arm, σ, seed, tick, delivered/total, strandings, deals.

### Compare mode (the killer shot)

Two traces side-by-side on a shared clock — same seed, same world, auction
left, SNHP right. The finish-line frame (delivered counts diverging, stranded
robots grey on one side) is money-shot (a). Load via drag-drop of 1–2 `.jsonl`
files or `?trace=…&trace2=…` URL params when served over HTTP.

### Controls

Play/pause (space), speed (1/4/16/64 ticks per frame), scrub bar, ←/→ step.

## Money shots (X atom: image + one number)

1. **Side-by-side finish line** — same world, two economies; caption is the
   completion delta (v2.1 demo pair, σ=0.5 seed 0: snhp+net finishes all 120
   at tick 1370 vs auction's 1938 — 29% faster with 63 bargains vs 420 rule
   firings).
2. **Rescue trade close-up** — stranded grey robot, cyan+amber arc pair
   incoming, caption `2▣ ⇄ 8⚡`; one number: surplus both sides.
3. **Ablation staircase** (static chart, dataviz skill): 0.33 → 0.68 → 0.73
   efficiency as issues stack; caption "the win is the coupling."

## v1 (only if the result survives expert review): arena integration

- Mount as an Evolution Arena page (`arena/web/swarm.html`), same replay
  theater pattern as the existing sim — traces are already the right shape
  for a WebSocket live mode later.
- 3D "crab robots" pass reuses the duel3d.js lessons (r128 postprocessing,
  bloom threshold 0.9, RGBA-gray toon ramps). Explicitly NOT v0.
- WebM export for clips (MediaRecorder on the canvas) — feeds `arena/clips/`.

## Non-goals for v0

No live sim in the browser (replay only), no 3D, no mobile layout, no
pheromone-field rendering (rules arm has no field to show).
