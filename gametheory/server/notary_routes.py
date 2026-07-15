"""The notary key + standalone verifier over HTTP — the public half of the
SNHP notary (core/notary.py).

Two endpoints, both free and stateless:

  GET  /v1/notary/key      → {pubkey_pem, pubkey_fpr, key_source, algo}. The
                             signer's PUBLIC key. `key_source` is "env"
                             (persistent) or "ephemeral" (regenerated this
                             process — a verifier must be able to SEE that).
  POST /v1/notary/verify   → a receipt JSON (or a list / a {"receipts":[...]}
                             wrapper) → per-receipt verdicts + the prev_hash
                             chain verdict. Uses the STANDALONE verifier — no
                             signing key is needed to verify, and a client can
                             reproduce every check locally with only GET
                             /v1/notary/key.

The `/v1/offer/quote` receipt (the "attestation" block on that response) is
signed by the SAME key GET /v1/notary/key returns, so a client can fetch the
key once and verify every quote attestation offline.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response

from core.notary import load_notary_key, verify_chain

router = APIRouter(prefix="/v1/notary", tags=["notary"])

_MAX_RECEIPTS = 1000        # DoS guard on the (public, unauthenticated) verifier


@router.get(
    "/key",
    summary="The notary's public signing key (verify quote attestations offline)",
    description=(
        "Returns the Ed25519 PUBLIC key that signs SNHP notary receipts — the "
        "`attestation` block on /v1/offer/quote and any receipt POSTed to "
        "/v1/notary/verify. `key_source` is 'env' (a persistent key set via "
        "NOTARY_KEY_PEM — signatures survive restarts) or 'ephemeral' (a fresh "
        "per-process key — historical signatures become unverifiable across a "
        "restart). The private key never leaves the server."),
)
def notary_key(response: Response):
    response.headers["X-GT-Cost-USD"] = "0"
    return load_notary_key().key_info()


@router.post(
    "/verify",
    summary="Verify notary receipts standalone (signature + discount-only + chain)",
    description=(
        "Body: a single receipt JSON, a JSON array of receipts, or "
        "{\"receipts\": [...]}. Each receipt is verified STANDALONE — the "
        "canonical signature (against the embedded pubkey, or this server's "
        "notary key), the discount-only invariant (p ≤ ℓ) re-checked, and "
        "a_prime_ok re-derived from the receipt's own ℓ/c_eff/β — plus the "
        "prev_hash chain across the sequence. No signing key is needed; the "
        "same checks run client-side with only GET /v1/notary/key."),
)
async def notary_verify(request: Request, response: Response):
    response.headers["X-GT-Cost-USD"] = "0"
    # site 1: parse the request body ourselves so a pathologically deep body
    # returns a friendly 422 (not a 500) instead of an uncaught RecursionError.
    try:
        body = await request.json()
    except RecursionError:
        raise HTTPException(status_code=422,
                            detail="receipt too large/deep to parse")
    except ValueError:
        raise HTTPException(status_code=422, detail="malformed JSON body")
    pubkey_pem: Optional[str] = None
    if isinstance(body, dict) and "receipts" in body and isinstance(
            body["receipts"], list):
        receipts = body["receipts"]
        pubkey_pem = body.get("pubkey_pem")
    elif isinstance(body, dict):
        receipts = [body]
    elif isinstance(body, list):
        receipts = body
    else:
        raise HTTPException(status_code=422,
                            detail="send a receipt object, a list, or "
                                   "{\"receipts\": [...]}")
    if not receipts:
        raise HTTPException(status_code=422, detail="no receipts to verify")
    if len(receipts) > _MAX_RECEIPTS:
        raise HTTPException(status_code=422,
                            detail=f"at most {_MAX_RECEIPTS} receipts per call")
    if not all(isinstance(r, dict) for r in receipts):
        raise HTTPException(status_code=422,
                            detail="each receipt must be a JSON object")
    # site 2: a deeply-nested receipt can overflow the canonical encoder — same
    # friendly 422 rather than a 500.
    try:
        return verify_chain(receipts, pubkey_pem=pubkey_pem)
    except RecursionError:
        raise HTTPException(status_code=422,
                            detail="receipt too large/deep to verify")
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(status_code=422,
                            detail=f"malformed receipt: {type(e).__name__}: {e}")
