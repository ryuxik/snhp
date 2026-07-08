# SNHP Evolution Arena

**A live, always-on world where pixel-art AI agents negotiate real deals with the
SNHP engine, earn energy, court mates, bargain over their children's genes, and
evolve — streamed to a browser and rendered as gothic pixel art.**

> Keystone invariant: **nothing in this arena knows how to negotiate except the
> library being showcased.** Every strategic computation is delegated to
> `gametheory.negotiation` / `gametheory.mechanism` / `gametheory.auctions`.

Live: **[arena.snhp.dev](https://arena.snhp.dev)**

## The algorithm — "Coasean Evolution"

Every evolutionary operator is a real market mechanism from the SNHP library:

- **Endogenous selection** — no exogenous fitness. Agents pay a metabolic tax and
  earn energy only from the surplus of closed deals (real `sell_next_offer` /
  `buy_next_offer` / `negotiate_bundle` negotiations). Energy ≤ 0 → death.
- **Mating market = deferred acceptance** — eligible agents are matched by
  `gametheory.mechanism.gale_shapley` over preference lists their evolved genes
  induce. The proposer-optimality asymmetry (Roth) is displayed, not hidden.
- **Logrolled crossover** (the novel operator) — matched parents run a real
  `negotiate_bundle` logroll over the child's gene blocks; each parent's
  per-option utilities come from its credit scorecard, the partner's priorities
  are inferred by the engine's particle filter, and the negotiation **can fail**,
  so "willingness to compromise" is a heritable, selected trait.
- **Eras** — a semi-Markov market regime (symmetric / buyers' / sellers' /
  contract) shifts the reservation distribution; strategy rank changes with it,
  reproducing the leaderboard's market-dependence finding.
- **Staking A/B** — attestation (truthful reservations + true-BATNA exchange)
  only pays when counterparties are also staked; a two-act demo shows staking die
  under random matching and invade under assortative discoverability.

The system is in the lineage of Holland's ECHO and Epstein–Axtell's Sugarscape;
what's new is the variation operator (crossover-as-logrolled-negotiation with
opponent inference and possible impasse). See `arena/world.py`, `courtship.py`,
`credit.py`.

## Layout

```
arena/
  config.py       every ARENA_* knob (env-overridable)
  genome.py       6 crossover blocks; mutation; 8 seed archetypes
  scenarios.py    eras + price/bundle generators (85/15 ZOPA mix)
  executor.py     genome -> engine adapters (the ONLY place we touch the library)
  credit.py       per-block Thompson scorecard
  courtship.py    gale_shapley bipartition + logrolled-crossover state machine
  auction.py      the Grand Auction set piece (optimal_bid)
  species.py      visual clusters + behavioral niches (NumPy leader clustering)
  world.py        the sim loop: energy economy, phases, eras, metrics, hall of fame
  events.py       event schema v1 (+ determinism hash) — see EVENTS.md
  store.py        JSONL event log + per-gen snapshots + highlights index
  broadcaster.py  async fan-out to many viewers
  runner.py       live pacing loop + engine warmup
  api.py          FastAPI: /health, WS /arena/ws, HTTP endpoints, static SPA
  fastforward.py  headless N-generation harness (balance + validation)
  web/            vanilla-JS pixel renderer (no build step)
  clips/          Playwright + ffmpeg clip pipeline (dev-only)
```

## Run it

```bash
pip install -e ".[prod,arena]"
uvicorn arena.api:app --port 8201            # http://localhost:8201

# headless balance / validation
python -m arena.fastforward --gens 160 --report
python -m arena.fastforward --gens 120 --staking     # the two-act network effect
python -m pytest arena/tests/                         # determinism, conservation, ...
```

## What it does — and doesn't — show

Served live at `/arena/stats`. It **does** show: every deal computed by the
shipped engine; the cooperation premium reproduced and measured with this run's
own n; market-dependent strategy rank; mechanism-mediated inheritance; the
staking critical-mass A/B. It **does not** claim agents reach the Nash solution
(offers are subjective Nash points under Bayesian beliefs), that "SNHP wins", or
the lab's +0.186/+12.5% as arena numbers.
