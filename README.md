# SNHP

The Synthetic Negotiation Handshake Protocol — and a 4-tier game-theory
toolkit for AI agents built around it.

## What's here

```
snhp/                  Algorithm + NegMAS agent + B2B tournament harness
gametheory/            Productization layer (FastAPI, MCP, Tier 1/2/3 endpoints)
gametheory/agents/     Aspiration detector + variant zoo
gametheory/evals/      Tournament + Optuna tuning + PBT scaffolds
gametheory/server/     HTTP + MCP entry points
gametheory/tests/      pytest suite (55 tests passing)
SNHP_Whitepaper/       Protocol description + 3 component PRDs
```

## Quick start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the test suite
python -m pytest gametheory/tests/

# Boot the FastAPI server locally (catalog at http://127.0.0.1:8000/v1/catalog)
uvicorn gametheory.server.http:app --reload

# Boot the MCP server (stdio)
gametheory-mcp
```

## Empirical anchor

SNHP ranks **#1 of 21** by average utility in a NegMAS round-robin tournament
at `n_rounds=20` (the standard horizon). At `n_rounds=100` the field
restabilizes and Aspiration takes #1 — SNHP slips to #4, but its variance
is the smallest of any agent in the field. The honest claim is "lowest
worst-case loss," not "always wins."

When two SNHP agents play each other, both walk away with ~0.62 utility
(reservation 0.40). That's the marketplace network-effect property.

See `gametheory/evals/README.md` for the eval/tuning runbook.

## Tiers

- **Tier 1 — Negotiation**: sell-side + buy-side recommenders, anchor-attack
  detection, cryptographic first-strike commit-reveal, LLM-drafted reply
  emails (paid).
- **Tier 2 — Auctions**: Vickrey / first-price BNE / English ascending,
  Myerson optimal reserve, format recommendation, MC simulation.
- **Tier 3 — Mechanism design**: Gale-Shapley, asymmetric Myerson optimal
  auction, Gallego-van Ryzin posted-price.

Tier 4 (coalition games) deferred until a paying buyer asks for it.
