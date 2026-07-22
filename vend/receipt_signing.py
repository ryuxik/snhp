"""vend/receipt_signing.py — sign the STORE's receipts with the notary we ship.

GAUNTLET finding #4: store receipts were UNSIGNED, so "price == wholesale" was
two fields the store wrote about itself — a merchant grading his own homework.
The fix was already in the building: core.notary is the Ed25519 machinery that
signs every field of a discount-only receipt EXCEPT the signature, loads its key
from NOTARY_KEY_PEM (else an ephemeral key whose `key_source` is VISIBLE), and
verifies standalone. This module lifts that exact discipline onto the store's
commodity receipt and the anchor (session/move/close) receipts.

NO crypto is duplicated here: the key, the canonical-bytes convention, the
fingerprint, and the public-key parse all come from core.notary. This module
only decides WHICH bytes are signed (every field except `signature`) and stamps
the honesty fields (`pubkey_fingerprint`, `key_source`) the notary already
insists on. A third party verifies with the published pubkey PEM alone (see
`signing_info()` / the store catalog's `receipts` block) — never the private key.

Canonical bytes == core.notary's `_canon_bytes` (sorted keys, compact
`(",",":")` JSON). The ONLY difference from core.notary's receipt envelope is
the name of the excluded field: there it is `notary_sig`, here it is
`signature` (the store-receipt field name). One convention, two field names.
"""
from __future__ import annotations

import base64

# Reuse core.notary's crypto wholesale — do NOT reimplement Ed25519 / key
# loading / canonical bytes / fingerprinting. core/ imports nothing from vend/,
# so this direction is clean.
from core.notary import (  # noqa: F401  (_canon_bytes/_fingerprint are the shared convention)
    InvalidSignature, _canon_bytes, _fingerprint, _load_pub, load_notary_key,
)

_SIG_FIELD = "signature"


def _signed_bytes(receipt: dict) -> bytes:
    """The canonical bytes actually signed: every receipt field EXCEPT the
    signature itself, in core.notary's sorted-keys/compact-JSON convention.
    Signing and verifying share this one definition — there is no second copy
    of the "drop the signature, canon-encode" rule."""
    return _canon_bytes({k: v for k, v in receipt.items() if k != _SIG_FIELD})


def sign_receipt(receipt: dict) -> dict:
    """Sign a receipt dict with the ambient notary key. Returns a NEW dict with
    three fields added (all three are themselves covered by the signature, since
    the payload is "every field except `signature`"):

      - `pubkey_fingerprint` — the trust pin a verifier matches the key against
      - `key_source`         — "env" | "ephemeral", VISIBLE per the notary's own
                               honesty rule (an ephemeral key signs an
                               unverifiable-after-restart history; the receipt
                               must SAY so, never hide it)
      - `signature`          — base64 Ed25519 over `_signed_bytes(receipt)`

    Deterministic given the same receipt + key. Raises whatever load_notary_key
    raises in a deployed env with no NOTARY_KEY_PEM (by design — an unverifiable
    trust anchor is a hard error, not a silent ephemeral swap); callers that
    must not lose a delivered good use `safe_sign` instead."""
    key = load_notary_key()
    out = dict(receipt)
    out["pubkey_fingerprint"] = key.pubkey_fpr
    out["key_source"] = key.key_source
    # key._private is the same private-key handle core.notary._sign uses; we are
    # reusing the loaded key, not touching the crypto primitives.
    sig = key._private.sign(_signed_bytes(out))
    out[_SIG_FIELD] = base64.b64encode(sig).decode()
    return out


def safe_sign(receipt: dict) -> dict:
    """sign_receipt, but a signing failure NEVER eats a delivered good or a
    charged session: on any exception, return the receipt with signature=None
    plus a `signing_error` so the consumer SEES it is unsigned (never silently).
    In a correctly-configured process — env key in prod, ephemeral in dev/tests
    — this always signs. Used on the settled-fetch and anchor paths, where the
    money has already moved and erroring out would lose the very thing the
    customer paid for."""
    try:
        return sign_receipt(receipt)
    except Exception as e:  # pragma: no cover - only a misconfigured deploy
        return {**receipt, "pubkey_fingerprint": None, "key_source": None,
                "signing_error": type(e).__name__, _SIG_FIELD: None}


def verify_receipt(receipt: dict, *, pubkey_pem: str | None = None) -> bool:
    """The third-party check: recompute the canonical signed bytes and verify
    the Ed25519 signature. Returns a plain bool (True iff the signature is valid
    AND the receipt's `pubkey_fingerprint` matches the verifying key).

    The public key comes from `pubkey_pem` (what an independent auditor pins
    from the catalog's `receipts` block) or, when omitted, the process's ambient
    notary key (the in-process/test check). Never needs the private key."""
    d = dict(receipt)
    sig = d.get(_SIG_FIELD)
    if not sig:
        return False
    pem = pubkey_pem or load_notary_key().pubkey_pem
    # trust pin: the key we verify with must be the one the receipt names.
    if d.get("pubkey_fingerprint") != _fingerprint(pem):
        return False
    try:
        _load_pub(pem).verify(base64.b64decode(sig), _signed_bytes(d))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def signing_info() -> dict:
    """The PUBLIC signature scheme description for the store catalog's `receipts`
    block: what bytes are signed, the notary pubkey PEM + fingerprint +
    key_source, and one sentence on verifying independently. No private material.
    `key_source` is stated so an agent can SEE an ephemeral key when one signed
    (its history dies on restart)."""
    key = load_notary_key()
    return {
        "scheme": "ed25519",
        "encoding": "base64",
        "signed_bytes": (
            "json.dumps({k: v for k, v in receipt.items() if k != 'signature'}, "
            "sort_keys=True, separators=(',', ':')).encode() — every receipt "
            "field EXCEPT `signature` itself"),
        "pubkey_pem": key.pubkey_pem,
        "pubkey_fingerprint": key.pubkey_fpr,
        "key_source": key.key_source,
        "verify": (
            "recompute signed_bytes, base64-decode `signature`, and Ed25519-verify "
            "it against pubkey_pem; confirm pubkey_fingerprint == "
            "'sha256:' + sha256(pubkey_pem.encode()).hexdigest()[:24]. Uses only "
            "the public key — never the private key."),
    }
