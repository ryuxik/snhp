"""
Verified bilateral peering + negotiation sessions.

Closes the #1 gap: in the shipped server `peer_mode` was an UNVERIFIED boolean
the caller passed, so the cooperation premium (the moat) could be claimed by
anyone and could not be established between two real agents. Here `peer_mode` is
DERIVED server-side from a real, spoof-resistant, transport-agnostic handshake:

  - Each party presents a peer proof = (its registry-issued operator attestation
    JWT) + (an Ed25519 signature over a binding tied to this negotiation_id).
  - The server verifies the operator attestation against the trust anchor (CA
    model), checks the operator isn't revoked, and verifies the per-negotiation
    signature against the attested public key.
  - Cooperation is a NETWORK good: peer_mode = both sides verified. A spoofer who
    can't be verified gets the adversarial outcome — the premium can't be stolen.

A session object (persisted) gives both agents a shared, server-authoritative
peer_mode that `next_offer` reads — so the negotiation can't be unilaterally
upgraded to cooperative by a lying client.
"""
from __future__ import annotations

import base64
import secrets
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from gametheory._db import db_conn
from gametheory.server.registry import (
    verify_operator_attestation, is_revoked, LEVELS,
)

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS peer_sessions (
        session_id       TEXT PRIMARY KEY,
        negotiation_id   TEXT NOT NULL,
        seller_operator  TEXT,
        buyer_operator   TEXT,
        peer_mode        INTEGER NOT NULL,
        created_at       INTEGER NOT NULL
    )
    """,
)


# Roles a proof can be bound to. A proof signed for one role can't be replayed
# as the other (the v1 binding omitted role, allowing cross-role replay).
ROLES = ("seller", "buyer")
_MAX_PROOF_TTL_SECONDS = 3600   # reject proofs that claim an absurdly distant expiry


def _binding(negotiation_id: str, operator_id: str, role: str,
             expires_at: int) -> bytes:
    """What each party signs — binds the proof to THIS negotiation, operator,
    ROLE, and an expiry, so a captured proof can't be replayed into another
    negotiation, into the other role, or after it expires."""
    return (f"snhp-peer-proof|v2|{negotiation_id}|{operator_id}|{role}|{expires_at}"
            .encode("utf-8"))


def build_peer_proof(*, operator_attestation_jwt: str, operator_id: str,
                     negotiation_id: str, role: str, private_key_bytes: bytes,
                     ttl_seconds: int = 300) -> dict:
    """Client/SDK helper: produce a role-bound, time-limited proof. The server
    never sees the private key."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    expires_at = int(time.time()) + int(ttl_seconds)
    sig = Ed25519PrivateKey.from_private_bytes(private_key_bytes).sign(
        _binding(negotiation_id, operator_id, role, expires_at)
    )
    return {
        "operator_attestation_jwt": operator_attestation_jwt,
        "sig_b64": base64.b64encode(sig).decode(),
        "role": role,
        "expires_at": expires_at,
    }


def verify_peer_proof(proof: dict, negotiation_id: str, expected_role: str,
                      require_level: str = "self") -> tuple[bool, str | None, str]:
    """Server-side verification. Returns (ok, operator_id, reason). The proof
    must be for `expected_role`, unexpired, and at >= require_level."""
    # Fail CLOSED on an unrecognized require_level: LEVELS.get(...) would otherwise
    # default an unknown/typo'd value to 0 (the weakest gate), silently accepting
    # self-verified peers when the caller asked for 'domain'.
    if require_level not in LEVELS:
        return False, None, (
            f"unknown require_level {require_level!r}; expected one of {sorted(LEVELS)}")
    if not isinstance(proof, dict):
        return False, None, "proof must be an object"
    token = proof.get("operator_attestation_jwt")
    sig_b64 = proof.get("sig_b64")
    role = proof.get("role")
    if not token or not sig_b64:
        return False, None, "proof missing operator_attestation_jwt or sig_b64"
    if role != expected_role:
        return False, None, f"proof role {role!r} != expected {expected_role!r}"
    try:
        expires_at = int(proof.get("expires_at"))
    except (TypeError, ValueError):
        return False, None, "proof missing/invalid expires_at"
    now = int(time.time())
    if now > expires_at:
        return False, None, "proof expired"
    if expires_at > now + _MAX_PROOF_TTL_SECONDS:
        return False, None, "proof expiry too far in the future"
    try:
        claims = verify_operator_attestation(token)
    except Exception as e:  # noqa: BLE001  (any JWT failure → unverified)
        return False, None, f"invalid operator attestation: {e}"
    operator_id = claims["operator_id"]
    if LEVELS.get(claims.get("verification_level", "self"), 0) < LEVELS.get(require_level, 0):
        return False, operator_id, (
            f"verification level {claims.get('verification_level')!r} below "
            f"required {require_level!r}")
    if is_revoked(operator_id):
        return False, operator_id, "operator revoked or unknown"
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(claims["public_key_b64"])
        )
        pub.verify(base64.b64decode(sig_b64),
                   _binding(negotiation_id, operator_id, role, expires_at))
    except (InvalidSignature, ValueError):
        return False, operator_id, "per-negotiation signature invalid"
    return True, operator_id, "verified"


def open_session(*, negotiation_id: str, seller_proof: dict,
                 buyer_proof: dict, require_level: str = "self") -> dict:
    """Verify both parties and persist a session with a server-authoritative
    peer_mode. peer_mode is True ONLY if both sides verify (at >= require_level),
    for their respective roles, AND are DISTINCT operators (no self-dealing —
    otherwise one party could farm the cooperation premium against itself)."""
    s_ok, s_op, s_reason = verify_peer_proof(seller_proof, negotiation_id, "seller", require_level)
    b_ok, b_op, b_reason = verify_peer_proof(buyer_proof, negotiation_id, "buyer", require_level)
    self_deal = bool(s_ok and b_ok and s_op is not None and s_op == b_op)
    peer_mode = bool(s_ok and b_ok and not self_deal)
    note = ("self-dealing not permitted: seller and buyer are the same operator"
            if self_deal else None)

    session_id = "sess_" + secrets.token_urlsafe(18)
    with db_conn(_SCHEMA) as c:
        c.execute(
            """INSERT INTO peer_sessions
               (session_id, negotiation_id, seller_operator, buyer_operator,
                peer_mode, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, negotiation_id, s_op, b_op, int(peer_mode), int(time.time())),
        )
        c.commit()
    return {
        "session_id": session_id,
        "negotiation_id": negotiation_id,
        "peer_mode": peer_mode,
        "self_deal": self_deal,
        "note": note,
        "seller": {"verified": s_ok, "operator_id": s_op, "reason": s_reason},
        "buyer": {"verified": b_ok, "operator_id": b_op, "reason": b_reason},
    }


def get_session(session_id: str) -> dict | None:
    with db_conn(_SCHEMA) as c:
        row = c.execute(
            """SELECT session_id, negotiation_id, seller_operator, buyer_operator,
                      peer_mode FROM peer_sessions WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0], "negotiation_id": row[1],
        "seller_operator": row[2], "buyer_operator": row[3],
        "peer_mode": bool(row[4]),
    }
