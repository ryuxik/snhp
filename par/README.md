# PAR

**Out-negotiate a perfect AI. Daily.**

One deal a day, the same for everyone. You haggle against *the House* — the SNHP
equilibrium engine playing flawless. Then the reveal: how close you got to **par**
(the optimal deal) and the dollars you left on the table.

The hook is that par is **real**. The House plays the same recommender that powers
the SNHP A2A-commerce agent; par is the engine's true ceiling, not an LLM's guess.
No vibes-based negotiation game can fake a defensible "perfect deal" — that's the moat.

## Run it

Front end (zero backend — ships with an inline scenario stand-in):

```sh
cd par/web && python3 -m http.server 8100
# open http://localhost:8100
```

Backend (the live daily API):

```sh
pip install fastapi uvicorn          # if needed
uvicorn par.api:app --reload --port 8099
# GET  http://localhost:8099/par/today
```

## Layout

```
par/
  api.py          FastAPI: /par/today, /par/house_move, /par/grade,
                  /par/submit, /par/stats, /par/bundle_move
  scoreboard.py   streak / percentile / distribution (in-memory; swaps for a DB table)
  SPEC.md         daily rotation, the API contract, scoreboard, multi-issue generator
  web/
    index.html    4-screen SPA shell (landing · onboard · play · reveal) + share overlay
    styles.css    dark / off-white / violet palette
    par.js        canyon + value-axis renderers, game flow, scoreboard (inline stand-in)
```

The engine wire lives in [`gametheory/negotiation/par_game.py`](../gametheory/negotiation/par_game.py):
the House move, par, and a `play_out` harness. Run `python -m
gametheory.negotiation.par_game` to watch a patient vs. an eager line play out on the
live engine.

## Design language

- **Shareable = iconic** — the canyon (two off-white masses, black gap = the deal, violet seal on close).
- **Play = feels** — a live canyon: your counter previews the gap closing.
- **Reveal = measures** — a value-axis chart with par as the ceiling and a violet wedge = what you left on the table. *A canyon has no ruler; the reveal needs one.*
- **Multi-issue = trade** — the logroll diagonal (win-marks on a diagonal = one exchange, not three deals).

Palette: dark `#0E0F12`, off-white `#E8E8E3`, violet accent `#A78BFA`. See SPEC.md for
how the front end goes live against the API (three swaps, marked in `par.js`).
