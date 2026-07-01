# PAR

**Out-negotiate a perfect AI. Daily.**

One deal a day, the same for everyone. You haggle against *the House* — the SNHP
equilibrium engine playing flawless. Then the reveal: how close you got to **par**
(the optimal deal) and the dollars you left on the table.

The hook is that par is **real**. The House plays the same recommender that powers
the SNHP A2A-commerce agent; par is the engine's true ceiling, not an LLM's guess.
No vibes-based negotiation game can fake a defensible "perfect deal" — that's the moat.

## Run it

The whole game, live (uvicorn serves the SPA **and** the API same-origin, so the front
end's `fetch()` calls need no CORS):

```sh
pip install fastapi uvicorn          # if needed
uvicorn par.api:app --reload --port 8099
# open http://localhost:8099            (a sell day: the salary talk)
# open http://localhost:8099/?s=buy     (a buy day: the used car)
# open http://localhost:8099/?g=demo    (join a friend group — the seeded leaderboard)
```

Front end only (zero backend — the SPA falls back to an inline stand-in for the House,
the distribution, and the friends board):

```sh
cd par/web && python3 -m http.server 8100     # open http://localhost:8100
```

**Identity, no accounts:** a persistent device `user_id` (localStorage) is the key; the
name you pick is just a label, unique only within a group (dupes get a server suffix,
`Alex·a1`). Scores are recomputed server-side from your close, so the board can't be
gamed. See SPEC.md §4.

## Layout

```
par/
  api.py          FastAPI: today, house_move, grade, submit, stats, group(/join),
                  bundle_move, waitlist, event, funnel, advise, /health — + serves the SPA
  scoreboard.py   streak / percentile / distribution / friend groups (in-memory; -> DB)
  funnel.py       waitlist + funnel events (play→share→cta→waitlist); measures conversion
  SPEC.md         daily rotation, API contract, scoreboard, identity, multi-issue generator
  Dockerfile      par.game image (build context = repo root)
  fly.toml        Fly app config (par.game, HTTPS, health check)
  schema.sql      Postgres DDL — the swap target for the in-memory stores
  DEPLOY.md       how to ship it + the in-memory → Postgres swap
  web/
    index.html    SPA shell (landing · onboard · play · reveal) + share/agent overlays
    styles.css    dark / off-white / violet palette
    par.js        canyon + value-axis renderers, live play, scoreboard, conversion CTA
```

`POST /par/advise` is the agent MVP: the same SNHP equilibrium the game runs, now advising
a **real** negotiation (give it your side, walk-away, target, and the offers so far → it
returns the move + rationale). It's the conversion the game's "the agent beat you by $X"
has been earning. See [DEPLOY.md](DEPLOY.md) to ship the game to par.game.

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
