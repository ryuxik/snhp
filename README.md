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

### Two different numbers — keep them straight

There are two distinct measurements; conflating them is the easy mistake.

**1. Head-to-head competitive margin (the product-relevant number).** In a
SNHP-scaffolded LLM vs a non-SNHP LLM, how much more of the surplus does the SNHP
side capture? On the committed cross-vendor run (`gametheory/server/static/e6_cross_vendor.json`,
Sonnet+SNHP vs Haiku, n=20 paired seeds) the pooled margin is **~+12.5%**
(`mean h3_margin ≈ 0.125`, 29/40 positive signs). This is the number the shipped
tools cite as "~12% better head-to-head." Caveats: n=20, LLM-vs-LLM, single-issue
price, and the opponent is a *general* vanilla prompt — see the strong-baseline
note below.

**2. Joint-welfare lift in self-play (a cooperation metric, NOT the same thing).**
Two-Sonnet B2B contract negotiation, n=20 paired seeds:

| Condition | Joint welfare (frontier ≈ 1.57, estimated) |
|---|---:|
| Vanilla Sonnet (general prompt, no SNHP) | 1.40 |
| Pure SNHP-vs-SNHP (math only) | 1.45 |
| **Sonnet + SNHP MCP tool (both sides)** | **1.59** |
| Haiku + SNHP MCP tool (cross-model) | 1.61 |

Lift from both sides adopting the SNHP tool: **+0.186 joint welfare**, sign test
18/20, **p=0.0004**. (The 1.59/1.61 slightly exceed the 1.57 frontier *estimate* —
the frontier was estimated on a coarse grid, so treat these as "at the frontier,"
not "beyond it.") Cost: $0.025 per matchup at 2026-04 pricing.

### 3. The build-vs-buy test: SNHP vs a STRONG production prompt

Both numbers above are vs a *general* vanilla prompt. The sharper question — "why not
just prompt the LLM well?" — is answered by running SNHP against a strong production
prompt (`snhp/llm_strong_baseline.py`, whose system prompt even includes logrolling
advice). On the 4-issue contract, Haiku+SNHP-tool vs Haiku+strong-prompt, n=12 paired
seeds (`python -m snhp.strong_baseline_headtohead`, result committed at
`gametheory/server/static/strong_baseline_headtohead.json`):

| Metric | Value |
|---|---|
| Utility margin (SNHP − strong baseline) | **+0.077**, 95% CI **[+0.039, +0.115]** (excludes 0) |
| SNHP share of joint surplus | **54%** (CI [52%, 56%]) |
| Sign test | **8/12 positive, 0 negative** |

SNHP beats even a strong production prompt — but by roughly **half** the edge it shows
against a weak one. Caveats: n=12, Haiku (not Sonnet), one contract domain; re-run at
larger n / a stronger model to tighten the CI.

**Network effect**: the cooperation premium requires both sides to be
SNHP-staked. Asymmetric matchups (Sonnet+SNHP vs vanilla Sonnet) lose 0.11
utility vs symmetric scaffolded play. Peer-mode advisor only fires when
counterparty has posted a verifiable SNHP attestation.

Live demo (replay of the actual API trace at seed=42): https://snhp.dev/demo.html

### Tournament rank (honest, per-market)

In the committed round-robin (`leaderboard/results/leaderboard.json`, `n_rounds=20`),
SNHP's rank by average utility depends on the market:

| Market (BATNA) | SNHP rank | Top of field |
|---|---|---|
| Buyer's market (asymmetric) | **#1 of 21** | SNHP 0.508 |
| Seller's market (asymmetric) | **#1 of 21** | SNHP 0.520 |
| Symmetric (neutral) | **5th of 21** | Logroller 0.525, The Closer, Cialdini, Principled, then SNHP 0.512 |

So SNHP is #1 **in the asymmetric markets** and **mid-pack in the symmetric one** —
do not read this as "#1 overall." Its variance is the smallest in the field. At
`n_rounds=100` the symmetric field restabilizes further and Aspiration leads.

This NegMAS agent (`snhp/negmas_agent.py`) is a **research artifact and is NOT the
shipped product recommender** — the product claims below are measured on the
shipped code, not on this tournament.

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
