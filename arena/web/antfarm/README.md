# The Ant Farm — Y1 pipeline-replay renderer

A GROW-Cube–style, cutaway-isometric replay of **this repository's own research
history**: the pipeline that produced the swarm program in `research/swarm/`.
Contracts get registered, builders spawn into isolated worktrees, merges ride a
test gate, verdicts are filed, re-scopes are re-filed — and the company grows one
floor at a time. **The method is the demo.**

This is the pre-registered **Y1** artifact from `research/swarm/SPEC.md`
(§ *v26 (column Y)* and § *Y1 VISUAL DIRECTION*). Art style is GROW Cube
(the EYEZMAZE web game) — **style only, all assets original** (no copied
sprites/characters): chunky isometric cutaway diorama, soft pastels on warm
cream, clean dark outlines, flat two-tone shading, discrete pop / level-up.

## Files

| file | what it is |
|---|---|
| `generate_events.py` | parses `git log` of this repo + `research/swarm/SPEC.md` structure, classifies real events, emits `events.json`. Idempotent. |
| `events.json` | the checked-in, generated replay script (ordered real events). |
| `index.html` | the renderer. Self-contained: inline JS/CSS, 2D canvas, **no external CDNs, fonts, scripts, or images**. Reads `./events.json`. |
| `test_antfarm.py` | guards on the generator (idempotency, schema, census, ordering). |
| `README.md` | this file. |

## Honesty bindings (the whole point)

Everything on screen maps to a **real commit**. Nothing is invented.

- **Hover anything** — a floor, a verdict plaque, an archive folder, the
  registry, the utility gear, or a panel-row cell — and you get the real
  **commit hash + subject + timestamp**.
- The turn counter reads **`TURN n`** and shows the event's **real ISO
  timestamp**; a persistent header states **`replay: time-compressed`** — turns
  are commits, not minutes.
- Every event in `events.json` is derived from the repo. No fabricated activity,
  no decorative agents, no invented timestamps. If a field can't be derived from
  the repo, it is omitted rather than guessed.
- The column **`Y`** shows only as a dashed **REGISTERED** blueprint ghost with
  no level-up — because Y1 (this artifact) is registered-but-not-yet-verdicted.
  That, too, is honest.

### Room → organ mapping

| room / element | pipeline organ | driven by event type |
|---|---|---|
| **Registry** (lobby front desk, contract scrolls) | contracts posted | `REGISTRATION` |
| **Builder workshops** (one floor per column; a round worker hammers on the active build) | worktree builders | `BUILDRUN` |
| **Test gate** (a cart rides the spine up on a merge, carrying the passing test count) | test-gated merge | `BUILDRUN` where `is_merge` |
| **Ledger vault** (right cutaway wall, verdict plaques) | verdicts filed | `VERDICT` |
| **Archive** (left cutaway wall, re-filed folders) | corrections / re-scopes | `CORRECTION` |
| **Utility** (basement gear) | perf / infra | `PERF` |

A column **levels up** (GROW-style `LV.n` badge) once it has **both** a merged
`BUILDRUN` **and** a filed `VERDICT`. The bottom **panel row** shows one cell per
column **in the order the pipeline actually ran them** (build-time order, not
registration order — the capability columns ran U → V → Q → X, out of their
registered P-number order, and the panel shows exactly that).

## Regenerating `events.json`

The replay regenerates from git history at any time:

```sh
cd arena/web/antfarm
python3 generate_events.py          # rewrites events.json from live git state
python3 generate_events.py --check  # non-zero exit if the checked-in file is stale
python3 test_antfarm.py             # or: python3 -m pytest test_antfarm.py
```

The generator walks all commits reachable from `HEAD`, keeps those in the swarm
pipeline (touching `research/swarm/`, plus merge commits whose build parent does),
classifies each (`REGISTRATION` / `BUILDRUN` / `VERDICT` / `CORRECTION` / `PERF`),
and derives the column each event belongs to from the commit corpus itself
(`vN`↔column co-occurrence, the capability ladder `columns Q-W (P24-P30)`, and the
scale-program header). Test counts are the real `def test_` count in
`research/swarm/test_swarm.py` at each build commit (they climb 15 → 112).

## Running it

The renderer reads `./events.json` via `fetch`, so serve the folder over HTTP:

```sh
cd arena/web/antfarm
python3 -m http.server 8000
# open http://localhost:8000/
```

Opening `index.html` directly from `file://` may be blocked by the browser's
`fetch` policy; in that case the page shows an on-page banner with these
instructions instead of failing silently. Controls: **play/pause** (or spacebar),
speed **1× / 4× / 16×**, and a **scrub** slider (← / → step by one turn). Click a
panel cell to jump to that column's build.

## Publication

This page is **intentionally unlinked** from the arena index and every other
arena page — no navigation points at it. Whether to publish the ant farm (and its
assets) is a **founder decision**; nothing here links it into the live site.
