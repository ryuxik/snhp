"""
AP2 settlement — turn an SNHP-negotiated agreement into signed payment mandates.

Closes the #4 gap (no settlement of the negotiated deal). Maps SNHP's outputs
onto Google's Agent Payments Protocol (AP2), whose mandates are signed W3C
Verifiable Credentials carried between parties:

  - Intent Mandate  — the buyer's scope/constraint (their reservation / max
    price). Mirrors SNHP's first-strike commitment.
  - Cart Mandate    — the final agreed SKU/price/total, the non-repudiable
    record of the deal SNHP's bargaining produced.

We emit each as a VC-JWT (a standard W3C VC representation) signed by a dedicated
settlement-notary key — DISTINCT from the operator-registry trust anchor (see
TRUST_MODEL.md) — whose public half is published at /v1/keys/settlement_notary,
so any AP2-aware party can verify the mandate offline before moving money on its
own rails (Mastercard/PayPal/Coinbase). SNHP supplies the bargaining brain; AP2
supplies the payment rails — we don't build escrow.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import jwt

from gametheory.crypto.first_strike import (
    settlement_notary_private_pem, settlement_notary_public_key_pem,
)

_ISS = "gametheory.dev/ap2"
_AUD = "gametheory.dev/ap2/v1"

CART_MANDATE_KIND = "AP2CartMandate"
INTENT_MANDATE_KIND = "AP2IntentMandate"


def _now_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _vc_jwt(vc_type: str, subject: dict, ttl_seconds: int | None) -> dict:
    """`ttl_seconds=None` issues a NON-EXPIRING credential — required for a Cart
    Mandate, which is a permanent non-repudiable settlement record (an `exp` would
    make a past deal unverifiable after the TTL)."""
    now = int(time.time())
    vc = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://ap2-protocol.org/contexts/v1",
        ],
        "type": ["VerifiableCredential", vc_type],
        "issuer": _ISS,
        "issuanceDate": _now_iso(now),
        "credentialSubject": subject,
    }
    claims = {"iss": _ISS, "aud": _AUD, "iat": now, "kind": vc_type, "vc": vc}
    if ttl_seconds is not None:
        claims["exp"] = now + int(ttl_seconds)
    token = jwt.encode(claims, settlement_notary_private_pem(), algorithm="EdDSA")
    return {"mandate_jwt": token, "mandate": vc,
            "expires_at_iso": _now_iso(claims["exp"]) if "exp" in claims else None}


def emit_intent_mandate(*, negotiation_id: str, buyer_operator: str,
                        max_price: float, currency: str = "USD",
                        item: str | None = None, ttl_seconds: int = 86_400) -> dict:
    """The buyer's pre-commitment: 'I will pay at most max_price for item.'"""
    return _vc_jwt("AP2IntentMandate", {
        "negotiation_id": negotiation_id,
        "buyer_operator": buyer_operator,
        "constraint": {"max_price": float(max_price), "currency": currency,
                       "item": item},
    }, ttl_seconds)


def emit_cart_mandate(*, session_id: str, negotiation_id: str,
                      seller_operator: str, buyer_operator: str,
                      agreed_price: float, currency: str = "USD",
                      item: str | None = None, terms: dict | None = None,
                      ttl_seconds: int | None = None) -> dict:
    """The final agreed deal — the non-repudiable settlement record. Permanent by
    default (ttl_seconds=None) so the deal stays verifiable indefinitely."""
    return _vc_jwt("AP2CartMandate", {
        "session_id": session_id,
        "negotiation_id": negotiation_id,
        "seller_operator": seller_operator,
        "buyer_operator": buyer_operator,
        "cart": {"agreed_price": float(agreed_price), "currency": currency,
                 "item": item, "terms": terms or {}},
    }, ttl_seconds)


def verify_mandate(mandate_jwt: str, expected_kind: str | None = None) -> dict:
    """Verify a mandate VC-JWT against the settlement-notary public key (NOT the
    registry trust anchor — they are separate keys). If `expected_kind` is given
    (CART_MANDATE_KIND / INTENT_MANDATE_KIND), enforce it — otherwise an Intent
    Mandate would verify where a Cart Mandate is required (and vice versa).
    Returns the decoded VC."""
    decoded = jwt.decode(
        mandate_jwt, settlement_notary_public_key_pem().encode(),
        algorithms=["EdDSA"], audience=_AUD, issuer=_ISS,
    )
    if expected_kind is not None and decoded.get("kind") != expected_kind:
        raise jwt.InvalidTokenError(
            f"mandate kind {decoded.get('kind')!r} != expected {expected_kind!r}")
    return decoded["vc"]
