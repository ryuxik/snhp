"""
MPP over HTTP — the 402 challenge/response payment surface (see gametheory/server/mpp.py).

Two paid resources:

  POST /v1/mpp/negotiate/turn   Pay-per-call negotiation, NO api_key, NO wallet — MPP's
                                headline "pay per invocation instead of an API key" shape.
                                FENCED by default (MPP_PERCALL_ENABLED, see mpp.py): while
                                fenced it 404s and is ABSENT from discovery, because a
                                keyless per-call caller is invisible to the demand
                                referendum's return-visit gates.
  POST /v1/mpp/topup            MPP-framed wallet top-up: SPT settlement credits the
                                caller's wallet (onboarding.wallet_credit) — the bridge
                                to the prepaid-wallet primary model. ALWAYS live +
                                advertised in /openapi.json via `x-payment-info` so an MPP
                                client (and `npx mppx validate`) auto-discovers it.

Both share one flow (mpp.py): an unpaid request gets a signed 402 `WWW-Authenticate:
Payment` challenge; a request carrying an `Authorization: Payment` SPT credential is
verified + settled, then the resource is returned with a `Payment-Receipt` header. A
malformed credential is answered 402 (never 500) with a fresh challenge, so the client
can retry — exactly what the validator's error-handling phase checks.

No LLM in this path. Routes live under /v1/ so the app's rate-limit + body-size caps
apply automatically.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gametheory.server import mpp, onboarding
from gametheory.negotiation import plain_terms

router = APIRouter(tags=["mpp"])


# Fixed per-resource pricing, resolved once at import (base + the counter fee,
# 5% + a fixed 30¢).
_NEGOTIATE = mpp.price_with_fee(mpp.NEGOTIATE_BASE_CENTS)
_TOPUP = mpp.price_with_fee(mpp.TOPUP_CREDIT_CENTS)


# ─── 402 challenge helpers ────────────────────────────────────────────────────


def _realm(request: Request) -> str:
    """The challenge realm = the request hostname (mppx validator checks realm ==
    server host). Strip any :port — the validator compares against URL.hostname."""
    host = request.headers.get("host", "") or (request.url.hostname or "")
    return host.split(":")[0] or "localhost"


def _challenge_response(request: Request, frame: dict) -> JSONResponse:
    """Build a fresh signed 402 for a fixed-price resource: WWW-Authenticate: Payment
    challenge, application/problem+json body, Cache-Control: no-store, and an
    Accept-Payment header naming the rails we accept (fiat SPT only; crypto deferred)."""
    ch = mpp.build_challenge(realm=_realm(request), request=frame["request"],
                             description=frame["description"])
    body = {
        "type": mpp.PROBLEM_TYPE,
        "title": "Payment Required",
        "status": 402,
        "detail": "Payment is required.",
        "challengeId": ch["id"],
        # Fee named in the body too, not only the WWW-Authenticate description.
        "price_cents": frame["price_cents"],
        "base_cents": frame["base_cents"],
        "fee_cents": frame["fee_cents"],
        "counter_fee_pct": mpp.billing.COUNTER_FEE_PCT,
    }
    return JSONResponse(
        status_code=402,
        content=body,
        media_type="application/problem+json",
        headers={
            mpp.HDR_WWW_AUTHENTICATE: mpp.serialize_challenge(ch),
            mpp.HDR_ACCEPT_PAYMENT: ", ".join(mpp.SUPPORTED_METHODS),
            "Cache-Control": "no-store",
        },
    )


def _verify_and_settle(request: Request, frame: dict, *, kind: str,
                       api_key: Optional[str] = None) -> dict:
    """Given a request that carries an Authorization: Payment credential, verify the
    challenge HMAC, redeem the SPT, and return {receipt_header, reference}. Raises
    mpp.CredentialError (bad credential) or billing.PaymentDeclinedError (settlement
    failed) — the caller converts BOTH to a fresh 402 (never a 500)."""
    cred = mpp.parse_credential(request.headers.get(mpp.HDR_AUTHORIZATION, ""))
    ch = cred["challenge"]
    # 1) Authenticity: we minted this challenge and its terms are unaltered.
    if not mpp.verify_challenge(ch):
        raise mpp.CredentialError("challenge id failed HMAC verification")
    if ch.get("method") != mpp.METHOD_STRIPE:
        raise mpp.CredentialError(f"unsupported payment method {ch.get('method')!r}")
    # 2) Amount/currency come from the VERIFIED challenge, so a client cannot lower
    #    the price. They must match this resource's published price.
    req = ch.get("request", {})
    if str(req.get("amount")) != str(frame["price_cents"]) or req.get("currency") != frame["currency"]:
        raise mpp.CredentialError("challenge terms do not match this resource's price")
    payload = cred.get("payload") or {}
    spt = payload.get("spt") if isinstance(payload, dict) else None
    if not isinstance(spt, str) or not spt:
        raise mpp.CredentialError("credential payload missing spt")
    metadata = {"mpp_kind": kind, "mpp_challenge_id": ch["id"]}
    if api_key:
        metadata["api_key"] = api_key
    pi = mpp.settle_spt(spt=spt, amount_cents=frame["price_cents"],
                        currency=frame["currency"], challenge_id=ch["id"],
                        metadata=metadata)
    receipt = mpp.build_receipt(method=mpp.METHOD_STRIPE, reference=pi["id"])
    return {"receipt_header": mpp.serialize_receipt(receipt), "reference": pi["id"],
            "receipt": receipt}


def _has_payment_credential(request: Request) -> bool:
    auth = request.headers.get(mpp.HDR_AUTHORIZATION, "")
    return mpp.SCHEME.lower() in auth.lower() if auth else False


def _unknown_wallet_response(frame: dict) -> JSONResponse:
    """400 for a topup whose body `api_key` names no wallet — returned BEFORE any
    SPT settlement so an unknown/typo'd key is NEVER charged (charge-before-credit
    fix). A clean 4xx (never a 500); the SPT is untouched, so the caller retries
    with a correct api_key at zero cost."""
    return JSONResponse(
        status_code=400,
        media_type="application/problem+json",
        content={
            "type": mpp.PROBLEM_TYPE_NOT_FOUND,
            "title": "Bad Request",
            "status": 400,
            "detail": ("api_key names no wallet; no payment was taken. Supply a "
                       "valid gt_ api_key in the request body to fund the top-up."),
            "price_cents": frame["price_cents"],
        },
    )


# ─── Resource 1: pay-per-call negotiation (no api_key, no wallet) ─────────────


_NEGOTIATE_XPI = {
    "x-payment-info": {
        "amount": str(_NEGOTIATE["price_cents"]),
        "currency": "usd",
        "method": mpp.METHOD_STRIPE,
        "intent": mpp.INTENT_CHARGE,
        "description": mpp._fee_description(
            what="SNHP negotiation turn (pay-per-call)", **_NEGOTIATE),
    },
    "responses": {
        "200": {"description": "Payment accepted; negotiation recommendation returned "
                               "with a Payment-Receipt header."},
        "402": {"description": "Payment required; a signed WWW-Authenticate: Payment "
                               "challenge is returned."},
    },
    "requestBody": {
        "required": False,
        "content": {"application/json": {"example": {
            "side": "sell", "walk_away": 4000, "target": 6000,
            "counterparty_offers": [4200, 4500], "rounds_left": 6,
        }}},
    },
}


@router.post("/v1/mpp/negotiate/turn", openapi_extra=_NEGOTIATE_XPI)
async def mpp_negotiate_turn(request: Request):
    """MPP pay-per-call negotiation. First (unpaid) call -> 402 with a signed
    challenge for $1.00 + the counter fee (5% + 30¢). Retry with an
    `Authorization: Payment` SPT credential -> the deterministic plain-terms
    recommendation + a receipt. No SNHP api_key and no wallet: this IS MPP's 'pay
    per invocation instead of an API key' model. The free, unmetered version is
    POST /v1/negotiate/turn.

    FENCED by default: while MPP_PERCALL_ENABLED is unset this 404s (keyless
    per-call callers are invisible to the demand referendum's return-visit gates;
    use the wallet + /v1/mpp/topup). See mpp.percall_enabled()."""
    if not mpp.percall_enabled():
        # Fenced: 404 with a problem+json body naming the reason. The path is also
        # stripped from /openapi.json (see http.py's openapi override), so it is
        # absent from every discovery surface while fenced.
        return JSONResponse(
            status_code=404,
            media_type="application/problem+json",
            content={"type": mpp.PROBLEM_TYPE_NOT_FOUND, "title": "Not Found",
                     "status": 404, "detail": mpp.PERCALL_FENCED_REASON},
        )
    frame = {**_NEGOTIATE, "currency": "usd",
             "request": mpp._stripe_request(_NEGOTIATE["price_cents"], "usd"),
             "description": mpp._fee_description(
                 what="SNHP negotiation turn (pay-per-call)", **_NEGOTIATE)}
    if not _has_payment_credential(request):
        return _challenge_response(request, frame)
    try:
        settled = _verify_and_settle(request, frame, kind="mpp_negotiate")
    except mpp.CredentialError:
        return _challenge_response(request, frame)      # bad credential -> retryable 402
    except mpp.billing.PaymentDeclinedError:
        return _challenge_response(request, frame)      # settlement failed -> retryable 402

    # Paid. Run the resource. Inputs are validated AFTER payment (pay-per-call model);
    # a bad body still returns the receipt so the buyer has proof of what they paid for.
    result = await _run_negotiation(request)
    return JSONResponse(
        status_code=200,
        content={"ok": result.get("ok", True), "paid": True,
                 "price_cents": frame["price_cents"], "fee_cents": frame["fee_cents"],
                 "reference": settled["reference"], "receipt": settled["receipt"],
                 **({"result": result["result"]} if result.get("ok") else
                    {"error": result.get("error")})},
        headers={mpp.HDR_PAYMENT_RECEIPT: settled["receipt_header"]},
    )


async def _run_negotiation(request: Request) -> dict:
    """Parse the JSON body and run the deterministic negotiation engine. Returns
    {ok, result|error}. Never raises — a bad body is a reported outcome, not a 500
    (the buyer already paid)."""
    try:
        raw = await request.body()
        body = json.loads(raw) if raw else {}
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        result = plain_terms.negotiate_turn(
            side=body["side"], walk_away=float(body["walk_away"]),
            target=float(body["target"]),
            counterparty_offers=body.get("counterparty_offers"),
            my_previous_offers=body.get("my_previous_offers"),
            rounds_left=int(body.get("rounds_left", 8)),
            item=str(body.get("item", "this")))
        return {"ok": True, "result": result}
    except KeyError as e:
        return {"ok": False, "error": f"missing required field: {e}"}
    except (ValueError, TypeError, plain_terms.NegotiationInputError) as e:
        return {"ok": False, "error": str(e)}


# ─── Resource 2: MPP-framed wallet top-up (settlement funds the wallet) ───────


_TOPUP_XPI = {
    "x-payment-info": {
        "amount": str(_TOPUP["price_cents"]),
        "currency": "usd",
        "method": mpp.METHOD_STRIPE,
        "intent": mpp.INTENT_CHARGE,
        "description": mpp._fee_description(
            what=f"SNHP wallet top-up ({mpp.TOPUP_CREDIT_CENTS}c credit)", **_TOPUP),
    },
    "responses": {
        "200": {"description": "Payment accepted; wallet credited, Payment-Receipt returned."},
        "402": {"description": "Payment required; signed WWW-Authenticate: Payment challenge."},
    },
    "requestBody": {
        "required": True,
        "content": {"application/json": {"example": {"api_key": "gt_your_key_here"}}},
    },
}


@router.post("/v1/mpp/topup", openapi_extra=_TOPUP_XPI)
async def mpp_topup(request: Request):
    """MPP-framed wallet top-up: pay $2.00 + the counter fee (5% + 30¢) = $2.40
    via SPT and we credit $2.00 to the wallet named by `api_key` in the body. This
    is the SECOND rail beside the prepaid wallet — MPP settlement that FUNDS the
    wallet (contrast the per-call resource above, which funds nothing). Same
    counter fee, same settlement plumbing as billing.agentic_topup, but MPP-shaped
    (402 challenge)."""
    frame = {**_TOPUP, "currency": "usd",
             "request": mpp._stripe_request(_TOPUP["price_cents"], "usd"),
             "description": mpp._fee_description(
                 what=f"SNHP wallet top-up ({mpp.TOPUP_CREDIT_CENTS}c credit)", **_TOPUP)}
    if not _has_payment_credential(request):
        return _challenge_response(request, frame)

    # The wallet to credit travels in the body on BOTH requests (client resends it).
    api_key = await _read_api_key(request)

    # CHARGE-BEFORE-CREDIT FIX: settlement (settle_spt, inside _verify_and_settle)
    # TAKES THE CARD. If the api_key names no wallet — a typo/unknown key — that
    # money is charged and can never be credited, with no recovery path. So confirm
    # the wallet EXISTS before ANY settlement: an unknown/missing key is a free 4xx
    # here (never a charge). Scoped to /v1/mpp/topup — the per-call negotiate
    # resource has no wallet, so it never runs this pre-check. Still a 4xx, never a
    # 500, so the MPP wire contract holds.
    if not api_key or onboarding.lookup_key(api_key) is None:
        return _unknown_wallet_response(frame)

    try:
        settled = _verify_and_settle(request, frame, kind="mpp_topup", api_key=api_key)
    except mpp.CredentialError:
        return _challenge_response(request, frame)
    except mpp.billing.PaymentDeclinedError:
        return _challenge_response(request, frame)

    # Paid. Credit the wallet, deduping on the PaymentIntent id (claim-first, the SAME
    # discipline as billing.agentic_topup) so a retried succeeded intent never
    # double-credits.
    credited, duplicate, new_balance, err = _credit_wallet(
        api_key, mpp.TOPUP_CREDIT_CENTS, settled["reference"])
    content = {"paid": True, "credited": credited, "duplicate": duplicate,
               "credits_cents": mpp.TOPUP_CREDIT_CENTS, "price_cents": frame["price_cents"],
               "fee_cents": frame["fee_cents"], "reference": settled["reference"],
               "receipt": settled["receipt"]}
    if credited and new_balance is not None:
        content["new_balance_millicents"] = new_balance
    if err:
        content["error"] = err
    return JSONResponse(status_code=200, content=content,
                        headers={mpp.HDR_PAYMENT_RECEIPT: settled["receipt_header"]})


async def _read_api_key(request: Request) -> Optional[str]:
    try:
        raw = await request.body()
        if not raw:
            return None
        body = json.loads(raw)
        return body.get("api_key") if isinstance(body, dict) else None
    except Exception:
        return None


# ─── Acceptance manifest: machine-readable "how to pay this store" ────────────
#
# GET /v1/mpp/manifest — a PURE READ (no charge, no auth) an agent's payment
# tooling reads to learn how to pay us WITHOUT a human: the paid resources + their
# price frames, the accepted method (stripe / SPT ONLY — no crypto, per the
# stablecoin lock in AGENTIC_PAYMENTS.md), the counter-fee structure (from the
# billing constants, never a hardcoded string), the SPT minimum, the settlement
# preview API version, and the 402 -> authorize-with-SPT -> retry -> receipt flow.
#
# This route is the FIRST PRODUCTION caller of mpp.paid_resource_frame() (it was
# test-only before) — so the price the manifest advertises is computed by the SAME
# function the 402 challenge uses and can never drift from the charged price.
#
# The keyless per-call resource is OMITTED while MPP_PERCALL_ENABLED is off
# (mpp.percall_enabled()), mirroring its absence from /openapi.json. If networkId
# is still the placeholder, live_ready is False WITH the reason, so a caller
# minting a REAL SPT is not misled into thinking we can settle it live yet.


def _resource_descriptor(*, path: str, base_cents: int, what: str) -> dict:
    """One manifest resource entry, built from the SAME mpp.paid_resource_frame the
    402 challenge is built from — the manifest price and the charged price share a
    single source, so they cannot silently disagree."""
    frame = mpp.paid_resource_frame(base_cents=base_cents, what=what)
    return {
        "path": path,
        "method": "POST",
        "what": what,
        "base_cents": frame["base_cents"],
        "fee_cents": frame["fee_cents"],
        "price_cents": frame["price_cents"],
        "currency": frame["currency"],
        "description": frame["description"],
        # The exact stripe/charge `request` object the 402 challenge will carry.
        "challenge_request": frame["request"],
    }


@router.get("/v1/mpp/manifest", tags=["mpp"])
async def mpp_manifest(request: Request):
    """The acceptance manifest: everything an agent's payment tooling needs to pay
    this store over MPP with a Shared Payment Token, WITHOUT a human. Pure read —
    no charge, no auth. Reuses mpp.paid_resource_frame() for every price (so the
    advertised price is the charged price) and mpp.percall_enabled() /
    mpp.live_ready() so the manifest reflects live server state honestly."""
    ready = mpp.live_ready()
    # /v1/mpp/topup is ALWAYS advertised (keyed, countable callers).
    resources = [_resource_descriptor(
        path="/v1/mpp/topup", base_cents=mpp.TOPUP_CREDIT_CENTS,
        what=f"SNHP wallet top-up ({mpp.TOPUP_CREDIT_CENTS}c credit)")]
    # The keyless pay-per-call resource appears ONLY when its fence is open,
    # matching its /openapi.json visibility (mpp.percall_enabled()).
    if mpp.percall_enabled():
        resources.insert(0, _resource_descriptor(
            path="/v1/mpp/negotiate/turn", base_cents=mpp.NEGOTIATE_BASE_CENTS,
            what="SNHP negotiation turn (pay-per-call)"))

    manifest = {
        "protocol": "mpp",
        "protocol_docs": "https://mpp.dev",
        "spec": "https://docs.stripe.com/payments/machine/mpp",
        "realm": _realm(request),
        # We accept exactly one rail: fiat SPT on Stripe. Crypto/Tempo is DECLINED
        # (stablecoin lock, AGENTIC_PAYMENTS.md §5) — a crypto-only caller cannot pay.
        "accepted_method": {
            "method": mpp.METHOD_STRIPE,
            "rail": "fiat",
            "credential": "shared_payment_token",
            "payment_method_types": mpp.STRIPE_PAYMENT_METHOD_TYPES,
            "crypto_accepted": False,
        },
        "accept_payment_header": ", ".join(mpp.SUPPORTED_METHODS),
        # Fee STRUCTURE from the billing constants — never a hardcoded string.
        "fee": {
            "model": "counter_fee",
            "percent": mpp.billing.COUNTER_FEE_PCT,
            "fixed_cents": mpp.billing.COUNTER_FEE_FIXED_CENTS,
            "applies_to": "every resource price = base + counter fee (5% + fixed 30c)",
        },
        "spt_minimum_cents": mpp.SPT_MIN_CENTS,
        "currency": "usd",
        "settlement_api_version": mpp.STRIPE_SPT_PREVIEW_VERSION,
        "api_version_status": "preview",
        "flow": [
            "POST the resource with no credential -> 402 with a signed "
            "WWW-Authenticate: Payment challenge",
            "authorize the challenge with a Shared Payment Token you minted, "
            "scoped to this store",
            "retry with Authorization: Payment <credential carrying the SPT>",
            "receive the resource + a Payment-Receipt header",
        ],
        "resources": resources,
        "discovery": {
            "openapi": "/openapi.json",
            "x_payment_info": ("each paid path carries an x-payment-info block in "
                               "/openapi.json (npx mppx validate reads it)"),
        },
        "reference_client": "vend/mpp_client.py",
        "human_onramp": ("POST /v1/billing/checkout_session — human-clickable Stripe "
                         "Checkout top-up for agents that cannot yet mint an SPT"),
        # The buyer mints the SPT on their platform; we never see their card. We
        # only redeem a token the buyer scoped to us.
        "minting": "buyer-side; the store never sees the card, only redeems a scoped token",
        "live_ready": ready,
        "network_id": mpp.network_id(),
    }
    if not ready:
        manifest["live_ready_reason"] = (
            f"networkId is the placeholder {mpp.NETWORK_ID_PLACEHOLDER!r} — no "
            "Stripe Business Network profile is set. Test-mode settlement works; "
            "live SPT redemption does not until STRIPE_MPP_NETWORK_ID is a real "
            "profile_… id (docs 'Before you begin').")
    return JSONResponse(status_code=200, content=manifest,
                        headers={"Cache-Control": "no-store"})


def _credit_wallet(api_key: Optional[str], credit_cents: int, reference: str):
    """Credit `credit_cents` to the wallet, deduped on the settlement reference.
    Returns (credited, duplicate, new_balance_millicents, error)."""
    if not api_key or onboarding.lookup_key(api_key) is None:
        # Paid but we can't identify a wallet: report it (the receipt is still proof
        # of payment). A real caller supplies a valid api_key on both requests.
        return False, False, None, "unknown or missing api_key; funds not credited to a wallet"
    if not mpp.billing._claim_event(reference, "mpp_topup"):
        return True, True, None, None                    # already credited (retry)
    try:
        new_balance = onboarding.wallet_credit(
            api_key=api_key,
            millicents=credit_cents * onboarding.MILLICENTS_PER_CENT,
            bucket="funded")
    except Exception as e:
        mpp.billing._release_event(reference)
        return False, False, None, str(e)
    return True, False, new_balance, None
