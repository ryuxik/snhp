# Agentic payments — what's real, what we wired, what we deferred

*Research + integration decision for the STORE billing lane. Grounded in
`docs.stripe.com` fetched 2026‑07‑22 via the `stripe-docs` skill. Where a doc
is a preview or a click‑through gate, this says so — no overclaiming.*

The founder's prompt: *"Stripe launched agentic payments this year — investigate
and wire what's real."* This is the honest read.

---

## 1. The verdict, up front

Stripe **does** ship agentic‑payment rails today (2026), and one of them is a
near‑exact fit for our problem — an agent funding its own wallet to pay for our
API without a human clicking a hosted Checkout URL. It is **Machine Payments /
Shared Payment Tokens (SPT)**. But it is a **preview**: the charging parameter
exists only under a preview API version, live use requires accepting a preview
services agreement and a US legal entity, and — critically — the *buyer's* side
must be able to **mint** an SPT, which today means the agent platform holds a
Link/ACP capability most callers don't have yet.

So the split we shipped:

- **Custom top‑up (unconditional, GA rails):** ships now. Kills the 5.4×
  overshoot the gauntlet found (GAUNTLET #2). A $2 credit costs **$2.40** (the
  counter fee is 5% + a fixed 30¢), not $10.80. Pure GA Checkout + our existing
  webhook. No preview anything.
- **Agentic SPT top‑up (preview rails):** implemented as a real, test‑mode‑working
  endpoint (`POST /v1/billing/agentic_topup`) against the **documented** SPT flow,
  hermetically tested (Stripe layer monkeypatched, never networked). It is
  **labeled preview in code and here**, and it is **not live‑ready** until the
  gates in §5 clear. This is "wired, dark" — the code path is genuine and
  exercised; the switch that turns it on in production is Stripe‑side + legal,
  not ours to flip.

An honest "here is the real flow, here is exactly why it can't go live yet, here
is what to watch" is the outcome — we did not fake a GA integration.

---

## 2. What Stripe actually offers (merchant/seller side)

Stripe's agentic surface (`/agentic-commerce`) splits into three roles. We are a
**seller** accepting payment from a **buyer's agent**. Two seller‑side rails
matter to us:

### 2a. Sell through agents — Agentic Commerce Suite (ACS), ACP/UCP
`/agentic-commerce/for-sellers`. You publish a **product catalog feed**
(`/v2/commerce/product_catalog/imports`), a buyer's agent (ChatGPT, Meta, etc.)
runs checkout on the buyer's behalf via the **Agentic Commerce Protocol** (ACP,
the open standard from Stripe + OpenAI + Meta) or **Universal Commerce Protocol**
(UCP), and you fulfill on `checkout.session.completed`. Availability: **US and
Canada**. Activation is **not self‑serve** — from the doc: *"review the agent
terms and enable the agent in the Dashboard. Stripe sends the agent an approval
request that the agent must accept."* So ACS requires (a) Dashboard onboarding at
`/agentic-commerce`, (b) a catalog feed, and (c) a specific AI agent platform to
approve *us* as a seller. **Wrong shape for us:** we don't sell a browsable
product catalog; we sell wallet credit to fund an API. Deferred — see §6.

### 2b. Accept machine payments — MPP / x402 (the right fit)
`/payments/machine`. Verbatim framing: *"let your agents pay for resources
programmatically (for example, for API calls or services) … As an alternative to
setting up an account and getting an API key, your agent can interact with
services on demand and pay per invocation."* That is our exact scenario. Two
protocols:

- **MPP (Machine Payments Protocol, `mpp.dev`):** an HTTP‑402 challenge/response.
  Client requests a paid resource → server returns `402` with a signed challenge
  → client authorizes and retries → server charges and returns the resource + a
  receipt. Payment methods under MPP:
  - **Crypto** (on‑chain deposit addresses; Tempo/Solana/Base USDC). Minimum
    **0.01 USDC**. Available to businesses in all US states **except New York**,
    30+ countries.
  - **Fiat via SPT** (card/wallet). Minimum **0.50 USD**. **US legal entity**
    only. This is the fiat path that fits our USD wallet.
- **x402:** Base network, USDC. Crypto‑only.

### 2c. Shared Payment Tokens (the credential we accept)
`/agentic-commerce/concepts/shared-payment-tokens`. An SPT is a **scoped,
delegated payment credential** the buyer (or the buyer's agent) grants to a
seller: it carries usage limits (currency, `max_amount`, `expires_at`) and the
seller redeems it by creating a PaymentIntent. It settles on **Stripe's normal
payment rails** — the money lands in our Stripe balance, refunds/reporting/payouts
work like any other charge.

**The seller redeem call (this is the whole integration on our side):**

```
# mint a TEST SPT (sandbox; ordinary TEST secret key) — normally the BUYER's side does this
curl https://api.stripe.com/v1/test_helpers/shared_payment/granted_tokens \
  -u "$STRIPE_TEST_SECRET_KEY:" \
  -H "Stripe-Version: 2026-04-22.preview" \
  -d payment_method=pm_card_visa \
  -d "usage_limits[currency]=usd" \
  -d "usage_limits[max_amount]=1000" \
  -d "usage_limits[expires_at]=1798761600"

# redeem it — create + confirm a PaymentIntent carrying the SPT
curl https://api.stripe.com/v1/payment_intents \
  -u "$STRIPE_SECRET_KEY:" \
  -H "Stripe-Version: 2026-04-22.preview" \
  -d amount=1000 \
  -d currency=usd \
  -d "payment_method_data[shared_payment_granted_token]=spt_123" \
  -d confirm=true
```

One extra PaymentIntent parameter — `payment_method_data[shared_payment_granted_token]`
— is the entire seller‑side delta from ordinary card acceptance. On success the
intent reaches `succeeded` synchronously and we credit the wallet.

---

## 3. Is it "ordinary API keys in TEST mode"? Yes — with a preview caveat

- **Keys:** ordinary `sk_test_*` (sandbox) redeems a test SPT minted by the
  `test_helpers/shared_payment/granted_tokens` helper. No partner key, no
  platform credential *we* must hold to test. So the code path is fully
  exercisable with the same monkeypatch discipline as the rest of the suite.
- **The caveat — it's a PREVIEW API version.** The `shared_payment_granted_token`
  parameter is **absent from the GA PaymentIntents reference**; it appears only
  under `Stripe-Version: 2026-04-22.preview`. Confirmed by diffing the API ref:
  the GA `POST /v1/payment_intents` `payment_method_data` block lists dozens of
  methods and does not include it. So this is a versioned preview, not GA.
- **Services terms:** live use requires agreeing to *Stripe Agentic Commerce
  Seller Services (preview)* terms (click‑through, referenced from the SPT doc).
- **Geography / entity:** SPT fiat is **US + Canada**, **US legal entity** for the
  fiat leg. 0.50 USD floor (our 200¢ minimum clears it 4×).

**Decision:** the flow works in test mode with ordinary keys and is
hermetically testable, so per the lane's own rule we **implemented the minimal
endpoint** — but pinned to the preview version behind a named constant, labeled
preview everywhere, and gated for live behind §5. We wired what's real without
pretending the preview is GA.

---

## 4. What we shipped

### 4a. Custom top‑up (GA) — `billing.create_checkout_session`
`create_checkout_session` now accepts **exactly one** of `pack` (unchanged) or
`amount_cents` (custom, min **200**). Custom credits = `amount_cents`, price =
`amount_cents` + the counter fee (`COUNTER_FEE_PCT` = 5%, round‑half‑up, integer‑exact),
fee published as `fee_cents`. The webhook path already credits from
`metadata.credits_cents`, so a custom amount flows through the **same** signed,
deduped, replay‑safe webhook with **no handler change** — we set
`metadata.credits_cents = amount_cents` on the session and the existing crediting
logic does the rest. Pack definitions are **untouched** (and the fee formula
reproduces all three packs exactly at their fixed points — asserted at module
load, so the packs and the published fee can never silently disagree).

Response (custom): `{checkout_url, session_id, pack: "custom", price_cents,
credits_cents, fee_cents, amount_cents}`.

### 4b. Agentic SPT top‑up (preview) — `billing.agentic_topup` + route
`POST /v1/billing/agentic_topup {api_key, amount_cents, payment_token}`:

1. Validate `api_key` (our SNHP key), `amount_cents` (int, ≥ 200), `payment_token`
   (non‑empty `spt_…`).
2. Same fee math as custom top‑up: `price = amount_cents + counter_fee`.
3. `stripe.PaymentIntent.create(amount=price, currency="usd",
   payment_method_data={"shared_payment_granted_token": token}, confirm=True, …)`
   with `stripe_version="2026-04-22.preview"` passed **per request** (no global
   mutation — the GA checkout path is unaffected).
4. On `status == "succeeded"`: dedupe on the returned `payment_intent.id` using
   the **same** `processed_stripe_events` claim‑first / release‑on‑failure
   discipline as the webhook, then `wallet_credit(api_key, amount_cents × 1000,
   "funded")`. A client retry (same `x-request-id` → Stripe idempotency key) +
   the intent‑id dedupe make it replay‑safe: no double‑charge, no double‑credit.
5. Any non‑`succeeded` terminal status → returned with `credited: false` and no
   wallet change. A Stripe error (decline, expired/over‑limit SPT, preview not
   enrolled) → `PaymentDeclinedError` → **402**, never a 500.

Response (credited): `{credited: true, duplicate: false, status, payment_intent_id,
amount_cents, credits_cents, price_cents, fee_cents, new_balance_millicents}`.

**Idempotency note vs the webhook:** the webhook is *signed* by Stripe
(`construct_event`); `agentic_topup` is a direct API call with no inbound
signature — the SPT itself is the credential, validated by Stripe when we redeem
it, and replay‑safety comes from the Stripe idempotency key + our intent‑id
dedupe rather than a signature.

**Deferred within the endpoint (labeled):** async settlement. If an SPT redeem
ever returns `requires_action`/`processing` (e.g. a 3DS step — uncommon for a
delegated token), we do **not** credit inline; completing that would need a
`payment_intent.succeeded` webhook branch. Out of scope for the minimal endpoint;
noted so a later async top‑up isn't a surprise.

---

## 5. What unblocks live SPT (the watch list)

1. **Preview access + services terms.** Accept *Stripe Agentic Commerce Seller
   Services (preview)*; confirm the account is enrolled for the
   `2026-04-22.preview` API version. Until then live redeems 400 on the unknown
   parameter.
2. **Key hygiene before live.** Standard pre-live rotation applies (tracked in
   the private ops checklist); agentic work must not assume a live key exists.
   No live SPT redeem until a fresh restricted key is in `fly secrets`.
3. **US legal entity + geography.** SPT fiat is US/Canada, US legal entity for the
   fiat leg. Confirm the operating entity qualifies.
4. **Buyer‑side SPT issuance.** The decisive external dependency: the *buyer's*
   agent must be able to **mint** an SPT (Link agents / ACP‑integrated platforms
   today). Most API callers can't yet. In test we mint via the test helper; in
   production the credential is the caller's to produce. Watch adoption — this is
   the real gate on whether anyone can actually pay us this way.
5. **Preview version drift.** Parameter names live under a `.preview` version and
   can change. Pin is a named constant (`AGENTIC_PREVIEW_API_VERSION`); re‑verify
   against the SPT doc when bumping.

---

## 6. Explicitly deferred, with reasons

- **ACS / ACP catalog selling (§2a).** Wrong product shape (we sell wallet credit,
  not a browsable catalog) and activation needs a specific agent platform to
  approve us as a seller. Revisit only if we want the negotiation SKUs discoverable
  *inside* a third‑party agent's storefront.
- **Crypto / x402 machine payments.** Real and lower‑floor (0.01 USDC), but pulls
  in stablecoin acceptance, on‑chain settlement, and a NY carve‑out for a wallet
  that is USD‑denominated end to end. Not worth the surface area for a $2 anchor
  today; the SPT fiat path keeps us on Stripe's normal rails and our existing
  balance/webhook loop.
- **MPP HTTP‑402 middleware (`mppx`).** *(Superseded — now IMPLEMENTED, see §8.)*
  The full 402‑challenge framing meters *per API call* and was originally deferred
  as a node‑centric dependency. We have since implemented the MPP **wire protocol**
  natively in Python (no `mppx` runtime dep — `npx mppx` is only a dev‑time
  validator), as a second rail beside the wallet. See §8.

---

## 7. Open questions for the founder

1. **Is live SPT worth pursuing now, or park it dark?** The rail is real but the
   buyer‑side issuance (§5.4) is thin. Shipping it dark (done) costs nothing and
   is ready the day a caller can mint an SPT; chasing preview enrollment + entity
   + key rotation is only worth it if we have a caller who can actually pay.
2. **One published minimum, or two?** We set `agentic_topup`'s floor to the same
   200¢ as custom top‑up for one honest number. Stripe's SPT floor is 50¢ — if a
   caller wants sub‑$2 SPT top‑ups we can drop to 50¢, but then the published
   minimum forks by rail.
3. **Key rotation owner.** The chat‑exposed `sk_test_*` rotation is a hard
   pre‑live gate for *both* GA and preview paths — who holds the Stripe dashboard
   to rotate and re‑set `fly secrets`?

---

## 8. Machine Payments Protocol (MPP) — merchant‑side, fiat SPT rail

*Grounded in `docs.stripe.com/payments/machine/mpp` (fetched 2026‑07‑22 via the
`stripe-docs` skill) + the wire spec at `mpp.dev/protocol/challenges`, cross‑checked
byte‑for‑byte against the `mppx` npm package v0.8.13 — the same library the validator
`npx mppx validate` uses as its client. Implementation: `gametheory/server/mpp.py`
(protocol logic) + `gametheory/server/mpp_routes.py` (HTTP), tests in
`gametheory/tests/test_mpp.py`.*

### 8a. What MPP is (one paragraph, from the docs)
MPP is an HTTP‑402 challenge/response payment protocol for machine‑to‑machine payments
— "let your agents pay for resources programmatically … As an alternative to setting up
an account and getting an API key, your agent can interact with services on demand and
pay per invocation." A client requests a paid resource; the server answers **402 Payment
Required** with a signed `WWW-Authenticate: Payment …` challenge; the client authorizes
payment and retries with an `Authorization: Payment …` credential; the server settles
and returns the resource plus a `Payment-Receipt` header. MPP offers two payment
methods: **crypto** (on‑chain, Tempo/Base USDC) and **fiat via Shared Payment Tokens**
(card/wallet on Stripe's rails). The protocol is HTTP‑level and language‑agnostic — the
docs' `?lang=node` `mppx` examples are a Node SDK convenience; we reproduce the same
wire surface in Python/FastAPI, which is what the validator tests.

### 8b. What we implemented (verbatim shapes)
Two paid resources, both advertised in `/openapi.json` via `x-payment-info` so an MPP
client auto‑discovers them (a SECOND rail beside the prepaid wallet):

- **`POST /v1/mpp/negotiate/turn`** — pure MPP: pay‑per‑call, **no api_key, no wallet**
  (MPP's headline "pay per invocation instead of an API key"). Price **105¢** ($1.00
  service + 5¢ counter fee). On settlement returns the deterministic plain‑terms
  negotiation recommendation + receipt.
- **`POST /v1/mpp/topup`** — MPP‑framed **wallet top‑up**: on SPT settlement we credit
  the caller's wallet via `onboarding.wallet_credit` (settlement FUNDS the wallet — the
  bridge to the prepaid‑wallet primary model). Price **210¢** (200¢ credit + 10¢ fee),
  deduped on the PaymentIntent id like `billing.agentic_topup`.

**402 challenge** (`WWW-Authenticate`, mppx `Challenge.serialize` order):
```
WWW-Authenticate: Payment id="<hmac>", realm="<host>", method="stripe",
  intent="charge", request="<base64url(JCS(json))>",
  description="…$1.00 + $0.35 (5% + $0.30 counter fee) = $1.35", expires="<ISO8601 .fffZ>"
Accept-Payment: stripe
Cache-Control: no-store
Content-Type: application/problem+json
```
Body: `{"type":"https://paymentauth.org/problems/payment-required","title":"Payment
Required","status":402,"detail":"Payment is required.","challengeId":"…", …fee fields}`.
The decoded `request` is `{amount:"105", currency:"usd", methodDetails:{networkId,
paymentMethodTypes:["card","link"]}}` (mppx `stripe/Methods.ts` post‑transform shape).

- **Challenge id = HMAC‑SHA256** over the canonical binding
  `realm|method|intent|base64url(JCS(request))|expires|digest|opaque` (empty string for
  absent slots), base64url no‑pad — so a client that lowers the amount fails
  verification on retry. Signing secret derives from `STRIPE_SECRET_KEY`
  (`HMAC(key,"mpp-challenge-signing")`) per the docs, else `MPP_CHALLENGE_SECRET`, else a
  per‑process ephemeral secret (documented — persistent secret needed once scaled out).
- **Credential** (`Authorization: Payment <base64url({challenge, payload:{spt}})>`) is
  parsed, HMAC‑verified, then the SPT is redeemed. Any malformed credential → **402 with
  a fresh challenge, never a 500** (the retryable‑error contract the validator checks).
- **SPT settlement** (`mpp.settle_spt`, mppx `stripe/server/Charge.ts` shape): a
  PaymentIntent with a **top‑level** `shared_payment_granted_token` +
  `automatic_payment_methods{enabled, allow_redirects:"never"}`, `confirm=true`, pinned
  per‑request to **`Stripe-Version: 2026-02-25.preview`**, `Idempotency-Key`
  `mppx_<challengeId>_<spt>`. Reuses `billing._stripe()` / `_claim_event` — no duplicated
  Stripe plumbing. (NB: this differs from `billing.agentic_topup`, which uses
  `payment_method_data[shared_payment_granted_token]` on `2026-04-22.preview` — that is
  the bespoke pre‑MPP endpoint; this is the MPP‑framed settlement the mppx client
  expects. Both preview; re‑verify on bump.)
- **Receipt** (`Payment-Receipt: <base64url(JSON)>`): `{method:"stripe", reference:"pi_…",
  status:"success", timestamp:"<ISO8601>"}`.

### 8c. Fee treatment (published wherever money moves — 5% + 30¢, visible)
The buyer pays the challenge `amount` = base + the **counter fee (5% + a fixed 30¢)**
computed by the SAME `billing.counter_fee_cents` used for wallet top‑ups (one fee
function, every rail).
The fee is named THREE ways in the 402 frame before the buyer pays: the challenge
`description` string, the problem+json body (`base_cents`/`fee_cents`/`price_cents`/
`counter_fee_pct`), and the discovery `x-payment-info.description`. It is echoed again in
the 200 response body. No hidden markup.

### 8d. Tempo / crypto — DEFERRED (documented, protocol‑level "not supported")
The crypto/Tempo rail stays deferred (stablecoin custody + a NY carve‑out; §6). MPP's own
mechanism for "this rail is unsupported here" is simply to **not advertise a `tempo`
challenge** — the 402 lists only the methods the server accepts, so we emit a single
`stripe` challenge and set `Accept-Payment: stripe`. A crypto‑only client finds no usable
challenge and cannot pay, which is the correct, honest signal. `SUPPORTED_METHODS =
("stripe",)` in `mpp.py` is the single source of that decision; adding Tempo later is
additive (a second `WWW-Authenticate` challenge + on‑chain verification).

### 8e. Validator status (`npx mppx@latest validate`, run locally 2026‑07‑22)
Against the real app on a local port, test‑mode:
- **Default run (Stripe CLI key): 29 passed / 2 failed.** ALL discovery + challenge +
  error‑handling checks pass on BOTH endpoints (document found, valid OpenAPI, 2 paid
  endpoints discovered; 402 w/o creds, `WWW-Authenticate: Payment`, challenge parseable
  `stripe/charge`, id, realm, expires, realm‑matches‑host, amount integer, currency,
  networkId, paymentMethodTypes; malformed credential → 402 not 500 + fresh challenge).
  The **only** 2 failures were `Payment [stripe] — Failed to create SPT: Expired API Key`
  — the validator mints the SPT client‑side using the Stripe **CLI's** `test_mode_api_key`
  (`…uFBk`), which is **expired**. Our settlement code was never reached; this is a
  key/account gate, not an implementation defect.
- **With a valid `sk_test` (via `MPPX_STRIPE_SECRET_KEY`, the `.env` key `…Quve`):
  33 passed / 0 failed / 0 warnings — a clean full pass**, including a REAL SPT mint and
  REAL settlement through Stripe's test layer (server logs show
  `POST /v1/payment_intents → 200` for both endpoints; `Payment [stripe]: successful —
  HTTP 200`). So the merchant implementation is validated end‑to‑end; the default failure
  is purely the stale CLI key.

### 8f. What unblocks live MPP (founder actions)
1. **A valid Stripe test key for the validator's client side.** Refresh the Stripe CLI's
   `test_mode_api_key` (currently expired) or pass a live `MPPX_STRIPE_SECRET_KEY` — this
   alone turns the default 29/2 into 33/0.
2. **Live SPT preview enrollment + a real Business Network profile ID.** For LIVE (not
   test) settlement, accept the *Agentic Commerce Seller Services (preview)* terms and set
   `STRIPE_MPP_NETWORK_ID` to a real `profile_…` id (we emit `profile_test_UNSET`, which
   test mode tolerates but live requires — `mpp/mpp.py:_stripe_request`). US legal entity,
   0.50 USD floor (both our bases clear it).
3. **Key rotation** (same §5.2 gate) before any live mode, and a **persistent**
   `MPP_CHALLENGE_SECRET` once the server runs on more than one instance.
4. **Node present** for the dev‑time validator (`node v22`, `npx 11` confirmed on this
   box). MPP itself adds **no Python runtime deps**.
