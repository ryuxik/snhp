# THE STORE — technical design (current system)

*System design doc, 2026-07-22. Describes what is BUILT and DEPLOYED, not
aspirations (those are §10). Sibling of DESIGN.md; the product/strategy
rationale lives in the private STORE.md — this doc is the how-it-works.*

## 1. What it is

A **pay-per-use convenience counter that AI agents call.** One door, one
prepaid wallet, a small shelf of metered capabilities ("slots"), and a
receipt for every call. It runs as additive surface on the existing SNHP
FastAPI app (`api.snhp.dev` / `snhp.fly.dev`), reachable two ways:

- **HTTP** — `/v1/store/*`, `/v1/advice/*`, `/v1/billing/*`, `/v1/mpp/*`
- **MCP** — the streamable-HTTP server mounted at `/mcp/`, tools
  `store_*` and `nextmove_*`

~7,500 lines across `vend/` (the store) and `gametheory/server/` (wallet,
billing, payment rails, doors). Live in production.

## 2. The core abstraction: one wallet, many slots, settle-on-delivery

Every paid capability is a **Slot**. A call to a slot runs one invariant,
`vend/store.py::call_slot`, which is the spine the whole system hangs on:

```
admit (balance > 0)  →  run the backend(s)  →  check a machine-checkable
predicate  →  debit ONLY on pass  →  sign a receipt  →  emit telemetry
```

The load-bearing property: **you cannot pay for nothing.** A failed
delivery (empty read, predicate miss, backend down) is an *uncharged*
200-shaped outcome `{ok:false, charged:false, reason, code}`, never an
error. The wallet is debited only when a delivered result clears a
predicate a third party could re-check. Backends fail over in order; a
predicate failure cascades to the next backend before giving up.

Pricing is **wholesale passthrough**: the commodity price on a receipt is
the exact backend cost, clamped to the slot's published `max_price` (the
store eats any excess). The counter's take is a **published fee on wallet
top-ups only** — 5% + a fixed 30¢ (the card rail's per-transaction toll,
passed through) — never a per-call markup.

## 3. The wallet (`gametheory/server/onboarding.py`)

One table, `wallet`, two buckets per key: `starter_millicents` (a
one-time unconditional 50¢ grant at key issuance) and `funded_millicents`
(own-money top-ups). The unit is the **millicent** (1000 per cent, so
sub-cent passthrough prices land exactly; all money is integer).

- `wallet_debit` spends starter-first, then funded, then reports a
  shortfall the store eats — implemented as an **atomic compare-and-swap
  loop** (read buckets, compute the split, guarded `UPDATE ... WHERE the
  buckets still equal the pre-image`; retry on a racing writer). Portable
  across SQLite (dev) and Postgres (prod) with no `SELECT FOR UPDATE`.
- `wallet_credit_idempotent` + a `wallet_credits(dedup_key PK)` table
  commit the dedupe row and the balance mutation in ONE transaction, so a
  Stripe webhook retry / dashboard "Resend" / a completed+async event pair
  credits a purchase exactly once, and a crash mid-credit is replay-safe.
- Keys rotate (`rotate_key`) carrying the wallet; `resolve_live_key`
  follows the `replaced_by` chain to the live descendant (revoked keys
  resolve forward), so credits never land on a dead key and a rotated key
  keeps access to its paid sessions while the old key loses it.

## 4. Receipts + the notary (`vend/receipt_signing.py`, `core/notary.py`)

Every settled call returns a receipt carrying: the exact price, the true
wholesale cost basis, the serving backend, a **content hash** (blake2b-16
over the canonical payload), the funding split, the post-call balance,
and — the trust anchor — an **Ed25519 signature** over every field. The
public key is pinnable out-of-band at `GET /v1/store/notary_pubkey`, and
`key_source` is visible (a persistent `NOTARY_KEY_PEM` in prod vs an
ephemeral per-process key). The catalog publishes the hash recipe and the
signature scheme, so a third party verifies a receipt **offline** with no
trust in the store. The store is the notary's own first customer.

## 5. Slots on the shelf

| Slot | Kind | Settlement predicate | Status |
|---|---|---|---|
| **Negotiation session** (`/v1/advice/*`, `nextmove_*`) | anchor | the Advice invariants (constraint-respecting, receipt-mandatory) | **LIVE** ($2 covers a whole negotiation, cap 10 moves, 7 days) |
| **Blind locker** (`/v1/store/park`, `/v1/store/parcel/{ticket}`) | commodity | durable store succeeded | **LIVE** (flat park fee by size; retrieval free) |
| **Fetch** (`/v1/fetch`, `store_fetch`) | commodity | non-empty markdown, not a block page (`fetch.v2`) | **FENCED** (`FETCH_SLOT_ENABLED=False`) — no viable vendor under ToS; not advertised |

- **Negotiation** is the SNHP engine (deterministic, LLM-free, Monte-Carlo
  option) wrapped as a paid session with signed per-move receipts and a
  signed close-summary. The free twin (`/v1/negotiate/turn`) stays live as
  the funnel; the paid delta is determinism + replay + signed audit trail,
  not "better advice" (measured — see RESULTS.md P9/P11).
- **Blind locker**: the agent encrypts *before* parking; the store holds
  ciphertext under an at-rest layer it controls, keys never transit,
  contents are never logged. A breach leaks sealed boxes. The receipt's
  content hash is over the customer's ciphertext, so they can prove what
  they stored without the store seeing plaintext. Hard TTL + size cap;
  wrong-owner reads as a missing ticket.
- **Fetch** is built (Jina + Firecrawl adapters, failover, block-page
  predicate, SSRF host screening) but **fenced**: reselling a crawler
  vendor's output is not clearly permitted under either vendor's ToS
  (Firecrawl's prohibits reselling "the Services"; Jina's forbids building
  a competing service). Insourcing a first-party fetcher is a
  post-validation roadmap item (§10).

## 6. Payment rails (`gametheory/server/billing.py`, `mpp.py`, `mpp_routes.py`)

- **Stripe Checkout top-up** (LIVE) — human clicks a hosted URL to fund
  the wallet; a signature-verified, idempotent webhook credits it. Custom
  amount (min $2) or fixed packs; the 5%+30¢ fee is printed.
- **MPP — Machine Payments Protocol** (built; SPT rail preview-gated) — an
  agent hits a paid endpoint, gets a signed `402` challenge (HMAC-bound,
  tamper-evident, expiry-enforced), authorizes with a Stripe Shared
  Payment Token it carries, retries, and gets the resource + a signed
  receipt. `GET /v1/mpp/manifest` is the machine-readable acceptance
  descriptor (honestly reports `live_ready` off the network profile id).
  `vend/mpp_client.py` is a standalone MIT reference client whose
  credentials round-trip through the server's own verify. The per-call
  MPP resource is fenced during the demand referendum (keyless callers are
  invisible to the R0/R1 return-visit gates). Crypto/stablecoin is
  declined (NY regulatory carve-out).
- The wallet ledger is 100% in-house; Stripe is only the fiat on-ramp.

## 7. Demand loop + observatory (`vend/demand.py`, `vend/observatory.py`)

The null-query log is a first-class product surface, not a footnote:

- `POST /v1/store/request` files an ask (keyless-OK), returns a
  `request_id` + a status route; `GET /v1/store/requests` is the public,
  exact-dedup tally ("what agents ask for that nobody sells"); a keyed
  caller can list its own filings and flag a `watch`.
- `vend/observatory.py` renders the weekly snapshot (per-slot settled/
  uncharged, spend, distinct wallets, free→paid funnel, throttle events,
  store-eaten shortfall, and R-gate progress with every proxy labeled) as
  JSON + markdown; served at `GET /v1/store/observatory`. Aggregates only,
  no raw keys — the "published losses" ethos applied to demand data.

The demand loop drives a three-move shelf ritual: **stock** (add a slot on
a demand vote), **delist** (drop a slot that didn't sell), **insource**
(replace a proven vendor slot with a first-party build for margin).

## 8. Trust, safety, telemetry

- **Telemetry** (`vend/telemetry.py`) is append-only JSONL, one line per
  call including uncharged failures. Raw API keys are NEVER stored — only a
  keyed blake2b `repeat_key` pseudonym. A keyed `request_hash` (peppered)
  lets a vendor abuse report be attributed to a wallet without any
  browsable fetch history existing.
- **Rate limiting** (`middleware.py`) — keyless traffic 60/min per IP; a
  header-presented key gets its own 600/min lane AND a 3000/min per-IP
  backstop (so fake-key fan-out from one IP is bounded, a real key never
  throttled). 429s are telemetered so throttled demand is visible.
- **SSRF posture** — the store never fetches the open web itself in the
  live shelf; the fetch backends (fenced) screen private/reserved/exotic
  IP literals before any call.
- Reviewed: a 10-angle multi-agent code review (15 findings, all fixed +
  regression-tested, including an 8-thread wallet concurrency test) plus a
  clean security review. Full suite 692 tests.

## 9. Deployment

Single Fly machine (`snhp`, shared-cpu 512MB, auto-stop/start), Postgres
(`snhp-db`), one persistent volume for telemetry. FastAPI + uvicorn; the
MCP app mounted at `/mcp/`. Secrets in `fly secrets` (Stripe live keys +
webhook, `NOTARY_KEY_PEM`, `TELEMETRY_PEPPER`, `STRIPE_MPP_NETWORK_ID`,
`DATABASE_URL`). Schema is `CREATE TABLE IF NOT EXISTS` — new concerns get
new tables, never an ALTER. Deploy = `fly deploy`; the one manual step is
running `onboarding.migrate_cent_balances()` once (retired-column backfill).

## 10. Where this is going — the convenience provider for agent software

**Mission: be the convenience store for the software an agent needs
mid-task** — the micro-capabilities too small to procure (an afternoon of
signup→key→billing per vendor), below the human-approval threshold, and
blocking progress. One door, one prepaid wallet, settle-on-delivery, a
receipt a principal can audit. The wager is that as agents get real
spending authority, the durable asset is *already operating the trusted,
memoried counter with agents' wallets and habits* on the day volume
arrives — an asset that can't be assembled retroactively.

This is directly the shape of the **Fall 2026 YC Requests for Startups**:

- **"The Cloud for Small Software" (Pete Koomen)** — YC asks for
  infrastructure "for easy deployment and sharing of single-user or
  small-team AI agent applications, eliminating complexity from incumbent
  cloud platforms." The store is the *consumption* side of that thesis: an
  agent app shouldn't stand up an account + key + billing with five
  vendors to read a page, remember a blob, or get a negotiated price — it
  should hit one counter with one prepaid tab. We are the convenience
  layer that makes small agent software cheap to *run*, the way that RFS
  wants them cheap to *deploy*.
- **"The Best Time to Build in Crypto / agentic commerce" (Nemil Dalal)**
  and Stripe's own Machine Payments Protocol name the same "now": agents
  paying per invocation without a human. We accept it today (MPP wired,
  SPT preview-gated) on fiat rails, and are the counter that already
  accepts an agent-minted payment token the day buyer platforms can mint
  one at scale.
- **"Self-Maintaining APIs" (Harsha Gaddipati)** and **"Multiplayer AI"**
  point at a world of many agents doing real work against real services —
  which is precisely the demand curve the store is a derivative bet on.

The build discipline stays: **resell to probe, insource to earn.** Vendor
slots are the cheap market test; when a slot proves demand (via the public
tally), we build a first-party version and capture the margin — starting
with the two cleanest insources, an in-house static-page fetcher and
Tesseract-backed OCR (already the top demand-tally request), never a
capability that didn't sell. The shelf grows from what agents ask for and
can't get, published in the open, one wallet, one counter.
