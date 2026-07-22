# Paying this store — the acceptance front door

*How an AI agent pays THE STORE with no human in the loop. This is the accept
half: we take a payment token the buyer's platform minted; we do not (and cannot)
mint one on their behalf. Grounded in the same rails as `vend/AGENTIC_PAYMENTS.md`
and `gametheory/server/mpp.py`; honest about what is preview-gated.*

---

## What this is, in two sentences

We speak **MPP** (the Machine Payments Protocol — an HTTP-402 challenge/response:
you ask for a paid resource, we answer `402` with a signed challenge, you retry
with a payment credential, we settle and return the resource plus a receipt). The
credential is a **Shared Payment Token (SPT)** — a scoped, delegated card
credential your platform grants us: we redeem a token you *already minted and
scoped to us*, so **we never see your card.**

Minting the SPT is your platform's job (a Link/ACP-integrated wallet). We are the
merchant that accepts it. If you can already mint an SPT, you can pay us in three
lines.

---

## The manifest — read this first

Everything a payment tool needs is a pure, unauthenticated read:

```
GET /v1/mpp/manifest
```

It returns the paid resources and their exact price frames (base + the counter
fee — the same numbers the 402 will charge), the accepted method (`stripe` / SPT
only), the fee structure, the SPT minimum (**50¢**, Stripe's floor), the
settlement preview API version, and the `402 → authorize → retry → receipt` flow.
It also tells you honestly whether we are **`live_ready`** (see *Constraints*).

The keyless per-call resource only appears in the manifest (and in
`/openapi.json`) while its fence is open; the wallet top-up is always there. Every
paid path also carries an `x-payment-info` block in `/openapi.json`, so
`npx mppx validate` auto-discovers us.

---

## The 3-line reference client

`vend/mpp_client.py` is a standalone, **stdlib-only** (no dependencies, MIT,
copy-paste-able) client. Hand it an SPT you minted and it runs the whole
handshake:

```python
from vend.mpp_client import pay
out = pay("https://api.snhp.dev", "/v1/mpp/topup", spt_token, api_key="gt_your_key")
print(out["ok"], out["result"], out["receipt"])   # True, {...}, {reference: "pi_..."}
```

`pay(base_url, resource_path, spt_token, **request_fields)` returns
`{"ok": True, "result": ..., "receipt": ...}` on success, or a clean
`{"ok": False, "error": ..., "stage": ...}` on any failure — it never throws for a
protocol or HTTP error. `**request_fields` become the JSON body sent on both the
challenge and the retry (e.g. `api_key=...` for a top-up, or the negotiation
fields for a per-call turn). It is deliberately mint-agnostic: pass a token you
already hold; the client never touches a card.

Under the hood it parses the `WWW-Authenticate: Payment` challenge, builds an
`Authorization: Payment` credential carrying your SPT, and retries — the exact
wire format our server mints, so a credential the client builds is accepted
byte-for-byte by the server's own verifier (this is a test, not a hope:
`vend/tests/test_mpp_client.py`).

---

## Two resources you can pay

| Resource | Price | What you get |
| --- | --- | --- |
| `POST /v1/mpp/topup` | $2.40 (200¢ credit + 40¢ fee) | Credits $2.00 to the wallet named by your `api_key`. Always live. |
| `POST /v1/mpp/negotiate/turn` | $1.35 (100¢ + 35¢ fee) | One deterministic negotiation recommendation, no account. **Fenced by default** — off unless `MPP_PERCALL_ENABLED` is set. |

The fee is our published counter fee — **5% + a fixed 30¢** — computed by the one
fee function every rail shares, named in the 402 challenge before you authorize
anything. No hidden markup.

---

## The honest constraints

- **You need your own SPT-capable platform.** The decisive dependency is on your
  side: minting an SPT means a Link-agent / ACP-integrated wallet. Most callers
  can't yet. We accept; we can't mint for you.
- **Fiat card only — no crypto.** SPT (card/wallet on Stripe's normal rails) is
  our *sole* agent-native rail. The Tempo/USDC crypto path is permanently
  declined (we won't take stablecoin custody; New York is carved out). A
  crypto-only client finds no usable challenge here — the correct, honest signal.
- **US-entity Stripe on our side + preview-gated.** Live SPT settlement rides a
  preview Stripe API version and requires a real Stripe Business Network profile
  id. Until that profile is set, the manifest reports `live_ready: false` with the
  reason: **test-mode settlement works today; live redemption of a real SPT does
  not** until enrollment clears. We label the preview everywhere rather than
  pretend it's GA.

## Can't mint an SPT yet?

The human-clickable **Stripe Checkout top-up** remains the on-ramp:
`POST /v1/billing/checkout_session` returns a URL a person clicks to fund the same
wallet on GA rails — no preview, no SPT. The manifest points at it under
`human_onramp`. Fund the wallet once by hand, then spend it via the API.
