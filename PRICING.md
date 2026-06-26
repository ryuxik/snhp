# Pricing & service posture

Honest, value-based, agent-native. The principle: **the deterministic math is free
(it costs ~nothing to serve and drives adoption); we charge for the LLM work that
costs real money and for the verified-settlement moat where the value actually is.**

These are the current posture and illustrative rates, not a locked rate card — Tier 2
in particular is priced with the first settlement customer.

## Tiers

| Tier | What | Price | Why |
|---|---|---|---|
| **0 — Core math** | `negotiate_turn`, `negotiate_bundle`, all `auction.*` and `mechanism.*` tools | **Free**, no key | Pure CPU, COGS ≈ $0.000005/call. This is the adoption wedge — the whole agent-facing surface. |
| **1 — LLM extras** | Natural-language drafting / dispute coaching (`/v1/dispute/*`) — anything that calls an LLM under the hood | **Off by default**; usage-based when enabled | These are the *only* endpoints that cost real API money. See "Abuse resistance" — they're opt-in, hard-capped, and meant to be key-gated (caller pays) in production. Optional anyway: an agent can draft with its own LLM provider. |
| **2 — Verified commerce (the moat)** | A2A verified peering + AP2 settlement (`/v1/a2a/*`) | **0.1–0.5% of settled value**, or a flat operator seat | This is where the value is: a verified, settleable deal. On a $10k deal SNHP's edge captures ~$160 of value; a 0.1–0.5% fee is $10–50. Priced per the first settlement partner. |

Value sanity check (so we never price off cost): SNHP's measured edge captures roughly
**$16 / $160 / $1,600** of value on a **$1k / $10k / $100k** deal. Every Tier-1 and
Tier-2 rate above is a small fraction of that.

## Abuse resistance (can't be milked for cheap LLMs)

The thing people fear — "someone uses my endpoint as a cheap LLM proxy or burns my
API budget" — is structurally contained:

1. **The entire product is LLM-free.** `negotiate_turn`, `negotiate_bundle`, every
   `auction.*` and `mechanism.*` tool is pure math (no model call). There is *nothing*
   to proxy. The free tier cannot be exploited for LLM access, by construction.
2. **The only LLM-touching endpoints are the 3 `/v1/dispute/*` drafting/coaching
   routes, and they are OFF by default** (`SNHP_ENABLE_DISPUTE_LLM` must be set). A
   fresh or public deploy exposes **zero** LLM surface.
3. **When enabled, spend is hard-bounded**, not best-effort: a daily USD cap
   (`SNHP_DAILY_LLM_USD`, default $5) that *persists* across restarts — so even a
   distributed botnet can't cost more than the cap per day — plus a per-IP hourly
   limit (`SNHP_LLM_PER_IP_HOURLY`, default 40). Past the cap, calls 429.
4. **They emit structured dispute outputs, not raw completions** — useless as a
   general-purpose LLM proxy even within the cap.
5. **Production posture: key-gate them** so the *caller* pays (the `billing.py`
   credit-pack rails already exist) — then operator exposure is zero, not just capped.

Net: the worst case on a misconfigured deploy is "$5/day of dispute-coaching JSON,"
and the default is "no LLM exposure at all."

## Service level (honest posture)

**Best-effort. No uptime SLA today.** The hosted service runs on a single deployment;
publishing a "99.9%" we can't fail over to would be dishonest. What we offer instead:

- **Free core, no key required** — try it with zero commitment.
- **Self-hostable** — the math endpoints are deterministic; run your own instance and
  you depend on no one. (This is the real answer to the single-author bus factor.)
- **A persistent-key requirement is enforced in prod** so attestations/mandates don't
  silently break across restarts (see `gametheory/crypto/first_strike.py`).

For reference, the standard SLA tiers a customer might ask for:

| Tier | Downtime budget/month |
|---|---|
| 99% | ~7.2 hours |
| 99.9% (typical B2B headline) | ~43 minutes |
| 99.99% (Stripe-tier) | ~4.3 minutes |

We move to a real **99.9%-with-credits** commitment only once the service is on
redundant infrastructure — not before. Until then: best-effort + self-host.

## What's deliberately NOT priced yet

No SDK is sold or needed — agents integrate via **MCP** and the **OpenAPI** spec
(`/openapi.json`), so a bespoke client library would be redundant. Tier-2 settlement
fees are not metered until a real settlement customer exists; building billing for a
moat with no users would be premature.
