"""
Machine Payments Protocol (MPP) — merchant/server side, fiat (SPT) rail.

WHAT MPP IS (docs.stripe.com/payments/machine/mpp, mpp.dev):
  MPP is an HTTP-402 challenge/response payment protocol for machine-to-machine
  payments ("pay per invocation, as an alternative to setting up an account and
  getting an API key"). A client requests a paid resource; the server answers
  `402 Payment Required` with a signed `WWW-Authenticate: Payment ...` challenge;
  the client authorizes payment and retries with an `Authorization: Payment ...`
  credential; the server settles and returns the resource plus a `Payment-Receipt`
  header. MPP supports two payment methods: crypto (on-chain, Tempo/Base USDC) and
  fiat via Shared Payment Tokens (SPT, card/wallet on Stripe's rails).

WHAT THIS MODULE IMPLEMENTS:
  The FIAT / SPT rail only (per vend/AGENTIC_PAYMENTS.md standing decision — the
  crypto/Tempo rail is DEFERRED: stablecoin custody + a NY carve-out; we simply do
  not advertise a `tempo` challenge, which is MPP's own way of saying "this rail is
  not supported here"). The protocol logic here is HTTP-level and language-agnostic;
  the docs' ?lang=node examples translate directly to this Python/FastAPI server.
  The wire shapes below were verified byte-for-byte against the `mppx` npm package
  (v0.8.x) — the same library `npx mppx@latest validate` uses as its client — so a
  real mppx client can parse our challenge and construct a credential we accept.

  Wire-format sources (mppx package, cross-checked with mpp.dev/protocol/challenges):
    - Challenge WWW-Authenticate serialization ...... mppx `src/Challenge.ts` serialize()
    - HMAC-SHA256 challenge-id binding ............... mppx `src/Challenge.ts` idBindingInput()
      slots: realm|method|intent|request|expires|digest|opaque  (empty string if absent)
    - request = base64url(JCS(json)) ................ mppx `src/PaymentRequest.ts` serialize()
    - Credential Authorization parsing .............. mppx `src/Credential.ts` deserialize()
    - Payment-Receipt header ........................ mppx `src/Receipt.ts` serialize()
    - Stripe SPT challenge request shape ............ mppx `src/stripe/Methods.ts`
    - Stripe SPT PaymentIntent settlement ........... mppx `src/stripe/server/Charge.ts`

FEE TREATMENT (published wherever money moves — STORE.md counter fee, same 5%):
  The buyer pays the challenge `amount`, which is base + the 5% counter fee (reusing
  billing.counter_fee_cents — the SAME fee function as the wallet top-ups). The fee
  is printed VISIBLY in the challenge `description` frame and echoed in the response
  body, so the 402 frame itself names the fee before the buyer pays.

COEXISTENCE WITH THE WALLET (MPP is a SECOND rail beside the prepaid wallet):
  Two paid endpoints, both discoverable via `x-payment-info` in /openapi.json:
    - POST /v1/mpp/negotiate/turn  — pure MPP: pay-per-call, NO api_key, NO wallet.
      This is MPP's headline shape ("pay per invocation instead of an API key").
    - POST /v1/mpp/topup           — MPP-framed wallet top-up: on SPT settlement we
      credit the caller's wallet via onboarding.wallet_credit (settlement funds the
      wallet). This is the bridge between MPP and the prepaid-wallet primary model.

NO LLM anywhere in this payment path (house rule). The negotiate resource behind the
per-call door is the deterministic plain-terms engine.

PREVIEW / LIVE GATES (see vend/AGENTIC_PAYMENTS.md §MPP): the SPT settlement rides a
preview Stripe API version and needs (a) SPT-preview enrollment on the account, (b) a
real Stripe Business Network profile ID as `networkId`, (c) a rotated key. Test mode
uses an ordinary sk_test_*; hermetic tests monkeypatch billing._stripe().
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from gametheory.server import billing, onboarding


# ─── Protocol constants (mppx src/Constants.ts) ──────────────────────────────

SCHEME = "Payment"
HDR_WWW_AUTHENTICATE = "WWW-Authenticate"
HDR_AUTHORIZATION = "Authorization"
HDR_PAYMENT_RECEIPT = "Payment-Receipt"
HDR_ACCEPT_PAYMENT = "Accept-Payment"

METHOD_STRIPE = "stripe"
INTENT_CHARGE = "charge"

# The rails we actually accept. Crypto/Tempo is DEFERRED (AGENTIC_PAYMENTS.md); we
# advertise only `stripe`, which is MPP's protocol-level "unsupported rail" answer —
# a client that can only pay crypto finds no usable challenge here.
SUPPORTED_METHODS = (METHOD_STRIPE,)

# RFC 7807 problem type MPP uses for the 402 body (docs.stripe.com/payments/machine/mpp
# "Test manually" — the application/problem+json shape).
PROBLEM_TYPE = "https://paymentauth.org/problems/payment-required"

# Stripe SPT preview API version (mppx src/stripe/internal/constants.ts). Distinct
# from billing.AGENTIC_PREVIEW_API_VERSION (2026-04-22.preview): the bespoke
# agentic_topup endpoint uses payment_method_data[shared_payment_granted_token];
# the MPP/mppx flow uses a TOP-LEVEL shared_payment_granted_token + automatic_
# payment_methods on THIS preview version. Both are preview; re-verify on bump.
STRIPE_SPT_PREVIEW_VERSION = "2026-02-25.preview"

# Challenge lifetime. Short window; the id is HMAC-bound so a tampered/expired
# challenge cannot be replayed with modified terms.
CHALLENGE_TTL_SECONDS = 300

# The two payment methods the challenge advertises to the buyer's agent (fiat SPT).
STRIPE_PAYMENT_METHOD_TYPES = ["card", "link"]

# ── Per-resource pricing. Base is the service list price; price = base + the 5%
# counter fee (billing.counter_fee_cents — one fee function for every rail). Both
# bases clear Stripe's 0.50 USD SPT floor. ──
NEGOTIATE_BASE_CENTS = 100   # $1.00 per pay-per-call negotiation turn (no account)
TOPUP_CREDIT_CENTS = 200     # $2.00 wallet credit, the published anchor (STORE.md)


# ─── base64url + JCS (RFC 8785) — match mppx `ox` Base64/Json.canonicalize ───


def _b64url_encode(data: bytes) -> str:
    """base64url, no padding (mppx uses { url: true, pad: false } everywhere)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode base64url, tolerating missing padding (what mppx/ox emit)."""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _jcs(obj) -> str:
    """RFC 8785 JSON Canonicalization Scheme, matching `ox` Json.canonicalize for the
    value shapes MPP requests use (objects, arrays, and strings — no numbers appear in
    a stripe challenge request, so key-sorted compact JSON IS the canonical form).
    Sorting is by code point (json sort_keys) == RFC 8785's UTF-16 order for our ASCII
    keys; ensure_ascii=False keeps UTF-8 bytes (ASCII-only content is identical)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def serialize_payment_request(request: dict) -> str:
    """PaymentRequest.serialize: base64url(JCS(request)). This exact string is what
    goes in the `request="..."` challenge param AND what the HMAC id binds to."""
    return _b64url_encode(_jcs(request).encode("utf-8"))


def deserialize_payment_request(encoded: str) -> dict:
    """PaymentRequest.deserialize: base64url -> JSON."""
    return json.loads(_b64url_decode(encoded).decode("utf-8"))


# ─── Challenge signing secret ────────────────────────────────────────────────


def _challenge_secret() -> str:
    """The HMAC secret that binds a challenge id to its terms. The docs derive it
    from the Stripe key (HMAC(STRIPE_SECRET_KEY, "mpp-challenge-signing")); we do the
    same when the key is present, else fall back to MPP_CHALLENGE_SECRET, else a
    per-process random secret.

    The secret only needs to be STABLE across a challenge->retry within one server
    lifetime (the validator never sees it), so a per-process secret is correct for
    a single instance; a persistent secret (Stripe key or MPP_CHALLENGE_SECRET) is
    required once the server is horizontally scaled — documented, not silent."""
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if stripe_key:
        return base64.b64encode(
            hmac.new(stripe_key.encode(), b"mpp-challenge-signing", hashlib.sha256).digest()
        ).decode("ascii")
    env_secret = os.environ.get("MPP_CHALLENGE_SECRET", "").strip()
    if env_secret:
        return env_secret
    global _EPHEMERAL_SECRET
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = _b64url_encode(os.urandom(32))
    return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET: Optional[str] = None


# ─── Datetime (ISO 8601, mppx zod.datetime regex requires .fff + Z|±HH:MM) ────


def _iso_now_plus(seconds: int) -> str:
    """ISO 8601 with millisecond precision and a Z suffix — the shape JS
    Date.toISOString() emits and mppx's z.datetime() regex accepts
    (^\\d{4}-..T..:..:..(?:\\.\\d+)?(?:Z|[+-]..:..)$). A wrong format would make
    the validator's Challenge.fromResponseList throw ('Challenge parseable' fail)."""
    t = datetime.now(timezone.utc).timestamp() + seconds
    dt = datetime.fromtimestamp(t, timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ─── Challenge construction + serialization (mppx src/Challenge.ts) ──────────


def compute_challenge_id(*, realm: str, method: str, intent: str, request: dict,
                          expires: str = "", digest: str = "", opaque: str = "",
                          secret: Optional[str] = None) -> str:
    """HMAC-SHA256 over the canonical id-binding input, base64url (no pad). Seven
    fixed positional slots joined by '|' (empty string when a field is absent):
        realm | method | intent | request | expires | digest | opaque
    where the `request` slot is the base64url(JCS(request)) STRING (not raw JSON).
    Because the HMAC covers every field, any tampering with the amount, currency,
    expiry, etc. changes the id and fails verification on the retry."""
    secret = secret if secret is not None else _challenge_secret()
    binding = "|".join([
        realm, method, intent, serialize_payment_request(request),
        expires or "", digest or "", opaque or "",
    ])
    mac = hmac.new(secret.encode(), binding.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(mac)


def build_challenge(*, realm: str, request: dict, description: Optional[str] = None,
                     method: str = METHOD_STRIPE, intent: str = INTENT_CHARGE,
                     ttl_seconds: int = CHALLENGE_TTL_SECONDS) -> dict:
    """Build one signed challenge dict (id HMAC-bound to its terms)."""
    expires = _iso_now_plus(ttl_seconds)
    cid = compute_challenge_id(realm=realm, method=method, intent=intent,
                               request=request, expires=expires)
    ch = {"id": cid, "realm": realm, "method": method, "intent": intent,
          "request": request, "expires": expires}
    if description is not None:
        ch["description"] = description
    return ch


def _auth_param(name: str, value: str) -> str:
    """One quoted auth-param, escaping backslash then double-quote (mppx authParam)."""
    if "\r" in value or "\n" in value:
        raise ValueError("Invalid quoted-string value.")
    return f'{name}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'


def serialize_challenge(ch: dict) -> str:
    """Serialize a challenge to a WWW-Authenticate value (mppx Challenge.serialize
    order: id, realm, method, intent, request, [description], [digest], [expires],
    [opaque]). `request` is emitted as base64url(JCS(request))."""
    parts = [
        _auth_param("id", ch["id"]),
        _auth_param("realm", ch["realm"]),
        _auth_param("method", ch["method"]),
        _auth_param("intent", ch["intent"]),
        _auth_param("request", serialize_payment_request(ch["request"])),
    ]
    if ch.get("description") is not None:
        parts.append(_auth_param("description", ch["description"]))
    if ch.get("digest") is not None:
        parts.append(_auth_param("digest", ch["digest"]))
    if ch.get("expires") is not None:
        parts.append(_auth_param("expires", ch["expires"]))
    if ch.get("opaque") is not None:
        parts.append(_auth_param("opaque", ch["opaque"]))
    return f"{SCHEME} {', '.join(parts)}"


def deserialize_challenge(header: str) -> dict:
    """Parse a `WWW-Authenticate: Payment ...` value into a challenge dict with the
    `request` DECODED to a dict (inverse of serialize_challenge; mirrors mppx
    Challenge.deserialize). Used by a Python MPP client and by tests to echo a
    server-minted challenge back inside a credential."""
    h = header.strip()
    if not h.lower().startswith(SCHEME.lower() + " "):
        raise CredentialError("not a Payment challenge")
    params = _parse_auth_params(h[len(SCHEME):].strip())
    if "request" not in params:
        raise CredentialError("challenge missing request parameter")
    ch = {k: v for k, v in params.items() if k != "request"}
    ch["request"] = deserialize_payment_request(params["request"])
    return ch


def _parse_auth_params(s: str) -> dict:
    """Parse RFC 7235 auth-params (key="value", comma-separated) with backslash
    un-escaping inside quoted strings. Sufficient for the params we emit."""
    out: dict = {}
    i, n = 0, len(s)
    while i < n:
        while i < n and (s[i].isspace() or s[i] == ","):
            i += 1
        start = i
        while i < n and (s[i].isalnum() or s[i] in "_-"):
            i += 1
        key = s[start:i]
        if not key:
            break
        while i < n and s[i].isspace():
            i += 1
        if i >= n or s[i] != "=":
            break
        i += 1
        while i < n and s[i].isspace():
            i += 1
        if i < n and s[i] == '"':
            i += 1
            buf = []
            while i < n:
                c = s[i]
                if c == "\\" and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                buf.append(c)
                i += 1
            out[key] = "".join(buf)
        else:
            start = i
            while i < n and s[i] != ",":
                i += 1
            out[key] = s[start:i].strip()
    return out


def verify_challenge(ch: dict, secret: Optional[str] = None) -> bool:
    """Recompute the HMAC id from the challenge's own fields and constant-time compare
    to the presented id. True iff we minted this challenge and nobody altered its terms.
    `ch['request']` is the DECODED request dict (as carried inside the credential)."""
    expected = compute_challenge_id(
        realm=ch.get("realm", ""), method=ch.get("method", ""),
        intent=ch.get("intent", ""), request=ch.get("request", {}),
        expires=ch.get("expires", "") or "", digest=ch.get("digest", "") or "",
        opaque=ch.get("opaque", "") or "", secret=secret)
    if not hmac.compare_digest(ch.get("id", ""), expected):
        return False
    # Enforce expiry server-side (security-review hardening): the expires
    # field is HMAC-covered, so a stale challenge fails here and the route
    # answers 402 with a fresh one. Settlement idempotency already prevents
    # double-credit on replay; this closes the window on principle, not need.
    expires = ch.get("expires") or ""
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            return False
        if exp <= datetime.now(timezone.utc):
            return False
    return True


# ─── Credential parsing (mppx src/Credential.ts deserialize) ─────────────────


class CredentialError(Exception):
    """Malformed Authorization: Payment credential. The route answers 402 (never
    500) with a fresh challenge — an invalid credential must be retryable."""


def parse_credential(auth_header: str) -> dict:
    """Parse an `Authorization: Payment <base64url>` value into
    {challenge, payload, [source]}, with challenge.request DECODED to a dict.
    Mirrors mppx Credential.deserialize. Raises CredentialError on any malformation."""
    if not auth_header:
        raise CredentialError("missing Authorization header")
    # Tolerate multiple comma-separated schemes; pick the Payment one (mppx
    # extractPaymentScheme). Case-insensitive scheme token.
    payment_part = None
    for scheme in (s.strip() for s in auth_header.split(",")):
        low = scheme.lower()
        if low.startswith(SCHEME.lower() + " ") or low == SCHEME.lower():
            payment_part = scheme
            break
    if payment_part is None:
        raise CredentialError("missing Payment scheme")
    encoded = payment_part[len(SCHEME):].strip()
    if not encoded:
        raise CredentialError("empty Payment credential")
    try:
        raw = _b64url_decode(encoded)
        parsed = json.loads(raw.decode("utf-8"))
        challenge = dict(parsed["challenge"])
        challenge["request"] = deserialize_payment_request(challenge["request"])
        # `opaque` is a base64url string on the wire; leave it as-is (we don't use it).
        payload = parsed.get("payload")
        out = {"challenge": challenge, "payload": payload}
        if parsed.get("source"):
            out["source"] = parsed["source"]
        return out
    except CredentialError:
        raise
    except Exception as e:  # base64/JSON/shape — all "invalid credential" -> 402
        raise CredentialError(f"invalid credential encoding: {e}") from e


def serialize_credential(challenge: dict, payload: dict,
                          source: Optional[str] = None) -> str:
    """Build an `Authorization: Payment <base64url>` value from a challenge (with a
    DECODED request dict) + a payload (mirrors mppx Credential.serialize). The
    challenge's request is re-serialized to base64url(JCS). Used by a Python MPP
    client and by tests to submit a payment credential the server can verify."""
    wire = {
        "challenge": {**{k: v for k, v in challenge.items() if k != "request"},
                      "request": serialize_payment_request(challenge["request"])},
        "payload": payload,
    }
    if source:
        wire["source"] = source
    encoded = _b64url_encode(json.dumps(wire).encode("utf-8"))
    return f"{SCHEME} {encoded}"


# ─── Receipt (mppx src/Receipt.ts serialize) ─────────────────────────────────


def build_receipt(*, method: str, reference: str, extra: Optional[dict] = None) -> dict:
    """A Payment-Receipt: {method, reference, status:'success', timestamp}. `status`
    is always 'success' — failures use 402 + problem+json, never a failure receipt."""
    r = {"method": method, "reference": reference, "status": "success",
         "timestamp": _iso_now_plus(0)}
    if extra:
        r.update(extra)
    return r


def serialize_receipt(receipt: dict) -> str:
    """Payment-Receipt header value: base64url(JSON(receipt)), no padding."""
    return _b64url_encode(json.dumps(receipt).encode("utf-8"))


# ─── SPT settlement (mppx src/stripe/server/Charge.ts) ───────────────────────


def _stripe_request(price_cents: int, currency: str) -> dict:
    """The stripe/charge challenge `request` object (post-transform wire shape,
    mppx src/stripe/Methods.ts): integer smallest-unit amount, ISO currency, and
    methodDetails carrying the Business Network profile id + accepted method types.
    `decimals` is intentionally omitted (mppx's transform strips it from the wire;
    the client defaults display decimals to 2)."""
    return {
        "amount": str(price_cents),          # integer smallest-unit string
        "currency": currency,
        "methodDetails": {
            # The Stripe Business Network profile id (profile_test_… / profile_…).
            # Any non-empty value passes the validator's "Has networkId" check, but a
            # REAL profile is required to mint/settle an SPT — a founder/live gate
            # (docs.stripe.com/payments/machine/mpp "Before you begin"). Sourced from
            # env so live enrollment is a config change, not a code change.
            "networkId": os.environ.get("STRIPE_MPP_NETWORK_ID", "").strip()
                          or "profile_test_UNSET",
            "paymentMethodTypes": STRIPE_PAYMENT_METHOD_TYPES,
        },
    }


def settle_spt(*, spt: str, amount_cents: int, currency: str, challenge_id: str,
               metadata: Optional[dict] = None) -> dict:
    """Redeem a Shared Payment Token by creating + confirming a PaymentIntent, the
    MPP/mppx way (top-level shared_payment_granted_token + automatic_payment_methods,
    pinned to the SPT preview version per-request). Reuses billing._stripe() (key
    loading, lazy import) — no duplicated Stripe plumbing. Returns {id, status}.

    Idempotency-Key mirrors mppx (`mppx_<challengeId>_<spt>`) so a client retry can
    never double-charge the token. Any Stripe rejection (decline, expired/over-limit
    SPT, preview-not-enrolled, unknown profile) becomes billing.PaymentDeclinedError,
    which the route maps to 402 (payment failed) — never a 500.

    NOTE: the param shape differs deliberately from billing.agentic_topup, which uses
    payment_method_data[shared_payment_granted_token] on 2026-04-22.preview. That is
    the bespoke pre-MPP endpoint; THIS is the MPP-framed settlement the mppx client
    (and validator) expects. Both are preview and monkeypatched in tests."""
    stripe = billing._stripe()
    opts = {
        "stripe_version": STRIPE_SPT_PREVIEW_VERSION,
        "idempotency_key": f"mppx_{challenge_id}_{spt}",
    }
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            confirm=True,
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            # The one seller-side delta from ordinary card acceptance — redeem the SPT.
            shared_payment_granted_token=spt,
            metadata=metadata or {},
            **opts,
        )
    except Exception as e:  # stripe.error.* — a redeem failure, never a 500
        raise billing.PaymentDeclinedError(str(e)) from e
    status = getattr(intent, "status", None)
    intent_id = getattr(intent, "id", None)
    if status != "succeeded":
        # requires_action / processing / requires_payment_method: SPTs are delegated,
        # so a step-up is uncommon; we do not deliver the resource on a non-terminal
        # success. Async completion is out of scope (see AGENTIC_PAYMENTS.md).
        raise billing.PaymentDeclinedError(
            f"PaymentIntent not succeeded (status={status})")
    if not intent_id:
        raise billing.PaymentDeclinedError("PaymentIntent succeeded without an id")
    return {"id": intent_id, "status": status}


# ─── Fee framing (billing.counter_fee_cents — one fee for every rail) ────────


def price_with_fee(base_cents: int) -> dict:
    """base -> {base_cents, fee_cents, price_cents}. price = base + the 5% counter
    fee (billing.counter_fee_cents, round-half-up, integer-exact). The buyer pays
    price; the fee is the store's published counter fee, named in the frame."""
    fee = billing.counter_fee_cents(base_cents)
    return {"base_cents": base_cents, "fee_cents": fee, "price_cents": base_cents + fee}


def _fee_description(*, base_cents: int, fee_cents: int, price_cents: int,
                     what: str) -> str:
    """Human-readable fee breakdown for the challenge `description` frame, so the 402
    itself names the counter fee before the buyer authorizes payment."""
    return (f"{what}: ${base_cents / 100:.2f} + ${fee_cents / 100:.2f} "
            f"({billing.COUNTER_FEE_PCT}% counter fee) = ${price_cents / 100:.2f}")


def paid_resource_frame(*, base_cents: int, what: str, currency: str = "usd") -> dict:
    """Everything a route needs to emit a 402 for a fixed-price paid resource:
    the pricing split, the stripe challenge request, and the fee-bearing description."""
    p = price_with_fee(base_cents)
    return {
        **p,
        "currency": currency,
        "request": _stripe_request(p["price_cents"], currency),
        "description": _fee_description(what=what, **p),
    }
