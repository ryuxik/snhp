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

### Headline (2026-04-30): adding the SNHP MCP tool to Claude lifts cooperation by +13%

We tested whether scaffolding Claude Sonnet 4.6 with the SNHP MCP advisor
actually improves negotiation outcomes. Two-Sonnet B2B contract negotiation,
n=20 paired seeds on the rich-frontier harness:

| Condition | Joint welfare | % of Pareto frontier (1.57) |
|---|---:|---:|
| Vanilla Sonnet (production prompt, no SNHP) | 1.40 | 89% |
| Pure SNHP-vs-SNHP (math only) | 1.45 | 92% |
| **Sonnet + SNHP MCP tool** | **1.59** | **101%** |
| Haiku + SNHP MCP tool (cross-model) | 1.61 | 102% |

Lift from adding SNHP tool: **+0.186 joint welfare**, sign test 18/20,
**p=0.0004**. Cross-model parity confirmed (Haiku works as well as Sonnet).
Cost: $0.025 per matchup at 2026-04 Anthropic pricing.

**Network effect**: the cooperation premium requires both sides to be
SNHP-staked. Asymmetric matchups (Sonnet+SNHP vs vanilla Sonnet) lose 0.11
utility vs symmetric scaffolded play. Peer-mode advisor only fires when
counterparty has posted a verifiable SNHP attestation.

Live demo (replay of the actual API trace at seed=42): https://snhp.dev/demo.html

### Tournament rank

SNHP ranks **#1 of 21** by average utility in a NegMAS round-robin tournament
at `n_rounds=20` (the standard horizon). At `n_rounds=100` the field
restabilizes and Aspiration takes #1 — SNHP slips to #4, but its variance
is the smallest of any agent in the field.

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
