"""
Cryptographic first-strike commit-reveal for buy-side negotiation.

Solves the empirical buy-side disadvantage measured in this session: in
alternating-offers SAO, going second caps best-achievable head-to-head
margin at -0.025 (Pareto-frontier-strict). Parameter tuning cannot fix
this. The mechanism does.

How it works:
  1. Buyer declares: "I will pay no more than $R by deadline T."
     Sends commitment_hash = SHA-256(reservation || nonce || salt || metadata).
     Server records and signs with EdDSA, returns signed attestation JWT.
  2. Buyer sends the attestation to the seller (out-of-band: email, chat).
  3. Seller proposes counter-offers. If seller exceeds R, seller knows the
     buyer cannot accept (committed). Seller's options: hit R or walk.
  4. On agreement at R or below: buyer reveals (reservation, nonce, salt).
     Server verifies hash matches, returns binding_offer.
  5. Either party can verify the original attestation against the public
     trust-anchor key — neither can repudiate.

Production extensions (deferred):
  - RFC 3161 trusted-timestamp authority (currently we use server clock).
    Replace `_server_timestamp_token()` with a real TSA call.
  - Public Merkle log of commitments anchored hourly to a transparency log
    so a malicious server cannot back-date commitments. Currently in-process.
  - Per-tenant trust-anchor key rotation. Currently a single ephemeral key
    generated at module load.

Storage: SQLite at the same path as keys.db (a separate `commitments` table).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Optional


# Producer always emits 43-char base64url SHA-256 without padding.
_RESERVATION_HASH_RE = re.compile(r"[A-Za-z0-9_-]{43}")

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption, PublicFormat,
    load_pem_private_key,
)

from gametheory._db import db_conn


_COMMITMENTS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS commitments (
        commitment_id TEXT PRIMARY KEY,
        buyer_id TEXT NOT NULL,
        seller_id TEXT NOT NULL,
        reservation_hash TEXT NOT NULL,
        deadline_unix INTEGER NOT NULL,
        binding_ttl_seconds INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        revealed_at INTEGER,
        revealed_reservation REAL
    )
    """,
)


def _conn():
    return db_conn(_COMMITMENTS_SCHEMA)


# ─── Trust-anchor key ────────────────────────────────────────────────────────
# Single EdDSA keypair per server process. Loaded from FIRST_STRIKE_PRIVATE_PEM
# env var (the production path — JWTs survive restarts and the published public
# key stays stable). Falls back to an ephemeral key generated on first use,
# which is fine for local dev and for testing but means every restart issues
# unverifiable historical attestations.
#
# To generate the env-var value:
#   from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
#   from cryptography.hazmat.primitives.serialization import (
#       Encoding, PrivateFormat, NoEncryption,
#   )
#   k = Ed25519PrivateKey.generate()
#   print(k.private_bytes(
#       Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode())
#
# Then: fly secrets set FIRST_STRIKE_PRIVATE_PEM="$(cat path/to/private.pem)"
#
# Caching the PEM-encoded bytes alongside the key object is intentional: PyJWT
# wants PEM bytes, and the public-key endpoint wants the PEM string — re-
# serializing per request is wasted CPU on the hot path.

_TRUST_ANCHOR_ENV_VAR = "FIRST_STRIKE_PRIVATE_PEM"

_TRUST_ANCHOR_KEY: Optional[Ed25519PrivateKey] = None
_TRUST_ANCHOR_PRIV_PEM: Optional[bytes] = None
_TRUST_ANCHOR_PUB_PEM: Optional[str] = None
_TRUST_ANCHOR_SOURCE: Optional[str] = None  # "env" or "ephemeral"


def _load_or_generate_trust_anchor_key() -> tuple[Ed25519PrivateKey, str]:
    """Load from FIRST_STRIKE_PRIVATE_PEM if set; else generate ephemerally.

    In production (Fly sets FLY_APP_NAME automatically), refuse the
    ephemeral fallback — silently using a fresh per-restart key would
    invalidate every prior JWT and the operator might not notice.
    """
    pem_str = os.environ.get(_TRUST_ANCHOR_ENV_VAR, "").strip()
    if pem_str:
        try:
            key = load_pem_private_key(pem_str.encode(), password=None)
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"{_TRUST_ANCHOR_ENV_VAR} is set but doesn't parse as a PEM "
                f"private key: {e}. Don't fall back to ephemeral — that would "
                f"silently swap the trust anchor and invalidate every attestation "
                f"the operator thought was persistent."
            ) from e
        if not isinstance(key, Ed25519PrivateKey):
            raise RuntimeError(
                f"{_TRUST_ANCHOR_ENV_VAR} parsed as {type(key).__name__}, "
                f"expected Ed25519PrivateKey. Re-generate with PKCS8 + Ed25519."
            )
        return key, "env"
    if os.environ.get("FLY_APP_NAME") or os.environ.get("SNHP_REQUIRE_PERSISTENT_KEY"):
        raise RuntimeError(
            f"{_TRUST_ANCHOR_ENV_VAR} is unset but the process appears to be "
            f"running in a deployed environment (FLY_APP_NAME or "
            f"SNHP_REQUIRE_PERSISTENT_KEY set). Refusing to fall back to an "
            f"ephemeral key — every JWT issued before the next restart would "
            f"become unverifiable. Set FIRST_STRIKE_PRIVATE_PEM via "
            f"`fly secrets set`."
        )
    return Ed25519PrivateKey.generate(), "ephemeral"


def _ensure_trust_anchor() -> None:
    global _TRUST_ANCHOR_KEY, _TRUST_ANCHOR_PRIV_PEM, _TRUST_ANCHOR_PUB_PEM
    global _TRUST_ANCHOR_SOURCE
    if _TRUST_ANCHOR_KEY is not None:
        return
    key, source = _load_or_generate_trust_anchor_key()
    _TRUST_ANCHOR_PRIV_PEM = key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    _TRUST_ANCHOR_PUB_PEM = key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    _TRUST_ANCHOR_KEY = key
    _TRUST_ANCHOR_SOURCE = source


def trust_anchor_source() -> str:
    """Returns 'env' or 'ephemeral' — useful for /health diagnostics."""
    _ensure_trust_anchor()
    return _TRUST_ANCHOR_SOURCE  # type: ignore[return-value]


def trust_anchor_public_key_pem() -> str:
    _ensure_trust_anchor()
    return _TRUST_ANCHOR_PUB_PEM  # type: ignore[return-value]


# JWT issuer + audience + expected `kind`. Issuer pinned per-deployment;
# audience reserved for future cross-app federation. The decoder enforces
# both, so a token issued for one purpose can't be used for another even
# if a future code path adds a second JWT type signed with the same key.
_JWT_ISSUER = "gametheory.dev/first_strike"
_JWT_AUDIENCE = "gametheory.dev/first_strike/v1"
_JWT_KIND = "first_strike_commitment"


def _sign_jwt(payload: dict) -> str:
    _ensure_trust_anchor()
    return jwt.encode(payload, _TRUST_ANCHOR_PRIV_PEM, algorithm="EdDSA")


def verify_attestation(token: str) -> dict:
    """Verify an attestation JWT against the server's public trust anchor.
    Enforces algorithm (EdDSA), expiry (default), audience, issuer, AND
    that `kind` matches the first-strike commitment type."""
    _ensure_trust_anchor()
    decoded = jwt.decode(
        token, _TRUST_ANCHOR_PUB_PEM.encode(),  # type: ignore[union-attr]
        algorithms=["EdDSA"],
        audience=_JWT_AUDIENCE,
        issuer=_JWT_ISSUER,
    )
    if decoded.get("kind") != _JWT_KIND:
        raise jwt.InvalidTokenError(
            f"unexpected JWT kind: {decoded.get('kind')!r}; "
            f"expected {_JWT_KIND!r}"
        )
    return decoded


# ─── Hash commitment ─────────────────────────────────────────────────────────


def commit_hash(reservation: float, nonce: str, salt: str,
                 buyer_id: str, seller_id: str) -> str:
    """
    Hash a buyer's reservation. Caller controls (nonce, salt) so they can
    reveal later. We bind buyer_id and seller_id into the hash so a
    commitment for one negotiation can't be replayed in another.

    Returns base64url-encoded SHA-256 (32 bytes → 43 chars).
    """
    payload = json.dumps({
        "reservation": float(reservation),
        "nonce": str(nonce),
        "salt": str(salt),
        "buyer_id": str(buyer_id),
        "seller_id": str(seller_id),
    }, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ─── Public API ──────────────────────────────────────────────────────────────


_MAX_TTL_SECONDS = 86_400  # 24h cap (DoS guard)
_MAX_DEADLINE_AGE_SECONDS = 7 * 86_400  # at most 7 days in the future


def declare_first_strike(
    *,
    buyer_id: str,
    seller_id: str,
    reservation_hash: str,
    deadline_iso: str,
    binding_ttl_seconds: int,
) -> dict:
    """
    Record a buyer's commitment and return a signed attestation.

    The commitment is BINDING for `binding_ttl_seconds` after creation OR
    until `deadline_iso`, whichever is sooner. After expiry the buyer is
    free to renegotiate without honouring the original reservation.
    """
    if not buyer_id or not seller_id:
        raise ValueError("buyer_id and seller_id are required")
    # SHA-256 base64url-encoded without padding is exactly 43 chars; producer
    # always emits this. Tight check rejects malformed/truncated/encoded values.
    if len(reservation_hash) != 43 or not _RESERVATION_HASH_RE.fullmatch(reservation_hash):
        raise ValueError(
            "reservation_hash must be 43-char base64url-encoded SHA-256 "
            "(charset [A-Za-z0-9_-], no padding)"
        )
    if binding_ttl_seconds < 60 or binding_ttl_seconds > _MAX_TTL_SECONDS:
        raise ValueError(
            f"binding_ttl_seconds must be in [60, {_MAX_TTL_SECONDS}]"
        )
    if len(deadline_iso) > 64:
        raise ValueError("deadline_iso must be at most 64 chars (ISO 8601 datetime)")

    # Only translate trailing 'Z' (UTC suffix). The previous .replace("Z", "+00:00")
    # corrupted any literal 'Z' mid-string (e.g., the parse-error message itself
    # would change semantics). datetime.fromisoformat accepts 'Z' natively in
    # Python 3.11+ but we defensively normalize for cross-version reproducibility.
    iso = deadline_iso[:-1] + "+00:00" if deadline_iso.endswith("Z") else deadline_iso
    try:
        deadline_dt = datetime.fromisoformat(iso)
    except ValueError:
        raise ValueError(
            f"deadline_iso must be ISO 8601 (e.g. 2026-04-29T14:00:00Z), "
            f"got {deadline_iso!r}"
        )
    if deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)

    now_dt = datetime.now(timezone.utc)
    if deadline_dt < now_dt:
        raise ValueError("deadline_iso must be in the future")
    if deadline_dt - now_dt > timedelta(seconds=_MAX_DEADLINE_AGE_SECONDS):
        raise ValueError(
            f"deadline_iso may be at most {_MAX_DEADLINE_AGE_SECONDS // 86400} days out"
        )

    commitment_id = "fs_" + secrets.token_urlsafe(18)
    deadline_unix = int(deadline_dt.timestamp())
    now_unix = int(now_dt.timestamp())

    with _conn() as c:
        c.execute(
            """INSERT INTO commitments
               (commitment_id, buyer_id, seller_id, reservation_hash,
                deadline_unix, binding_ttl_seconds, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (commitment_id, buyer_id, seller_id, reservation_hash,
             deadline_unix, binding_ttl_seconds, now_unix),
        )
        c.commit()

    # Effective expiry is min(deadline, created_at + ttl)
    effective_expiry_unix = min(deadline_unix, now_unix + binding_ttl_seconds)
    attestation_payload = {
        "commitment_id": commitment_id,
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "reservation_hash": reservation_hash,
        "iat": now_unix,
        "exp": effective_expiry_unix,
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
        "kind": _JWT_KIND,
    }
    attestation_jwt = _sign_jwt(attestation_payload)

    return {
        "commitment_id": commitment_id,
        "attestation_jwt": attestation_jwt,
        "expires_at_unix": effective_expiry_unix,
        "expires_at_iso": datetime.fromtimestamp(effective_expiry_unix, tz=timezone.utc).isoformat(),
        "trust_anchor_public_key_pem": trust_anchor_public_key_pem(),
    }


class CommitmentNotFound(LookupError):
    """No commitment with that id exists."""


class CommitmentExpired(RuntimeError):
    """Commitment exists but is past its expiry; reveal is rejected."""


class CommitmentRevealMismatch(ValueError):
    """Provided (reservation, nonce, salt) does not hash to the stored commitment."""


def reveal_first_strike(
    *,
    commitment_id: str,
    reservation: float,
    nonce: str,
    salt: str,
) -> dict:
    """
    Reveal the inputs to a previous commitment. Returns the binding offer if
    the hash matches and the commitment is still active. Idempotent: a
    second reveal of the same commitment returns the same binding offer
    without re-incrementing state.
    """
    with _conn() as c:
        row = c.execute(
            """SELECT buyer_id, seller_id, reservation_hash,
                      deadline_unix, binding_ttl_seconds, created_at,
                      revealed_at, revealed_reservation
               FROM commitments WHERE commitment_id = ?""",
            (commitment_id,),
        ).fetchone()
        if row is None:
            raise CommitmentNotFound(f"unknown commitment_id {commitment_id!r}")

        (buyer_id, seller_id, stored_hash, deadline_unix, ttl,
         created_at, revealed_at, revealed_reservation) = row

        # Idempotent re-reveal
        if revealed_at is not None:
            if abs(float(revealed_reservation) - float(reservation)) > 1e-9:
                raise CommitmentRevealMismatch(
                    "commitment already revealed with a different reservation"
                )
            return {
                "verified": True,
                "binding_offer": float(revealed_reservation),
                "buyer_id": buyer_id,
                "seller_id": seller_id,
                "revealed_at_unix": int(revealed_at),
                "reused": True,
            }

        now_unix = int(time.time())
        effective_expiry = min(deadline_unix, created_at + ttl)
        if now_unix > effective_expiry:
            raise CommitmentExpired(
                f"commitment expired at {effective_expiry} (now={now_unix})"
            )

        recomputed = commit_hash(reservation, nonce, salt, buyer_id, seller_id)
        if recomputed != stored_hash:
            raise CommitmentRevealMismatch(
                "revealed (reservation, nonce, salt) does not match stored commitment hash"
            )

        c.execute(
            """UPDATE commitments
               SET revealed_at = ?, revealed_reservation = ?
               WHERE commitment_id = ?""",
            (now_unix, float(reservation), commitment_id),
        )
        c.commit()

    return {
        "verified": True,
        "binding_offer": float(reservation),
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "revealed_at_unix": now_unix,
        "reused": False,
    }
