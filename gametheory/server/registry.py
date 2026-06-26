"""
Operator registry — the identity layer for SNHP agent-to-agent commerce.

An operator registers a stable identity bound to an Ed25519 public key and
receives a trust-anchor-SIGNED operator attestation (a JWT). Counterparties
verify it OFFLINE against the server's published trust-anchor public key — the
TLS-CA model: the registry issues, peers verify without calling back.

Verification levels (sybil resistance):
  - "self"   — anyone can self-register an operator_id. Cheap, unverified.
  - "domain" — proves CONTROL of a domain via a DNS-TXT challenge (RFC-8555
    style). The operator_id IS the domain; sybil now costs a domain + DNS
    control per identity. Carried as a `verification_level` claim so a cautious
    peer can require domain-verified counterparties.

Persisted via the shared DB so identities, levels, and revocations survive
restarts and span workers.
"""
from __future__ import annotations

import base64
import hashlib
import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import jwt

from gametheory._db import db_conn
from gametheory.crypto.first_strike import (
    trust_anchor_private_pem, trust_anchor_public_key_pem,
)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover
    _SSL_CTX = None

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS operators (
        operator_id        TEXT PRIMARY KEY,
        public_key_b64     TEXT NOT NULL,
        display_name       TEXT,
        created_at         INTEGER NOT NULL,
        revoked_at         INTEGER,
        verification_level TEXT NOT NULL DEFAULT 'self'
    )
    """,
)

_ISS = "gametheory.dev/registry"
_AUD = "gametheory.dev/registry/v1"
_KIND = "operator_attestation"
_DEFAULT_TTL_SECONDS = 365 * 24 * 3600

LEVELS = {"self": 0, "domain": 1}
CHALLENGE_PREFIX = "_snhp-challenge."

_migrated = False


class OperatorError(ValueError):
    """Bad registration / verification input."""


def _ensure_migrated() -> None:
    """Best-effort add of verification_level to DBs created before it existed.
    Idempotent: the duplicate-column error on already-migrated DBs is ignored."""
    global _migrated
    if _migrated:
        return
    try:
        with db_conn(_SCHEMA) as c:
            c.execute("ALTER TABLE operators ADD COLUMN verification_level "
                      "TEXT NOT NULL DEFAULT 'self'")
            c.commit()
    except Exception:  # noqa: BLE001  (column already exists)
        pass
    _migrated = True


def _validate_pubkey(public_key_b64: str) -> bytes:
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
    except Exception as e:  # noqa: BLE001
        raise OperatorError(f"public_key_b64 is not valid base64: {e}") from e
    if len(raw) != 32:
        raise OperatorError(
            f"public_key_b64 must decode to a 32-byte Ed25519 key, got {len(raw)}"
        )
    return raw


def register_operator(operator_id: str, public_key_b64: str,
                      display_name: str | None = None,
                      ttl_seconds: int = _DEFAULT_TTL_SECONDS,
                      verification_level: str = "self",
                      allow_rotation: bool = False) -> dict:
    """Register an operator identity and issue a signed attestation.

    Security rules (the open /v1/registry/register_operator endpoint is
    unauthenticated, so re-registration must not be a takeover primitive):
      - A REVOKED operator cannot be re-registered (revocation is sticky;
        un-revoke is an explicit admin action, not a side effect of register).
      - Re-registering an existing operator with a DIFFERENT key is a key
        rotation and is refused unless `allow_rotation=True` (only the
        domain-verified path sets it, because DNS control authorizes rotation).
      - Re-registration NEVER downgrades the stored verification_level.
    """
    _ensure_migrated()
    operator_id = (operator_id or "").strip()
    if not operator_id or len(operator_id) > 256:
        raise OperatorError("operator_id must be non-empty and <= 256 chars")
    if verification_level not in LEVELS:
        raise OperatorError(f"verification_level must be one of {sorted(LEVELS)}")
    _validate_pubkey(public_key_b64)

    now = int(time.time())
    with db_conn(_SCHEMA) as c:
        row = c.execute(
            "SELECT public_key_b64, revoked_at, verification_level "
            "FROM operators WHERE operator_id = ?",
            (operator_id,),
        ).fetchone()
        if row is None:
            stored_level = verification_level
            c.execute(
                """INSERT INTO operators
                   (operator_id, public_key_b64, display_name, created_at,
                    verification_level)
                   VALUES (?, ?, ?, ?, ?)""",
                (operator_id, public_key_b64, display_name, now, stored_level),
            )
        else:
            stored_key, revoked_at, existing_level = row
            if revoked_at is not None:
                raise OperatorError(
                    "operator_id is revoked and cannot be re-registered")
            if stored_key != public_key_b64 and not allow_rotation:
                raise OperatorError(
                    "operator_id already registered with a different key; key "
                    "rotation requires domain re-verification (proof of control)")
            # never downgrade the verification level on re-registration
            stored_level = (existing_level
                            if LEVELS[existing_level] >= LEVELS[verification_level]
                            else verification_level)
            c.execute(
                """UPDATE operators
                   SET public_key_b64 = ?, display_name = ?, verification_level = ?
                   WHERE operator_id = ?""",   # revoked_at deliberately untouched
                (public_key_b64, display_name, stored_level, operator_id),
            )
        c.commit()

    exp = now + int(ttl_seconds)
    token = jwt.encode(
        {
            "iss": _ISS, "aud": _AUD, "kind": _KIND,
            "operator_id": operator_id, "pubkey_b64": public_key_b64,
            "verification_level": stored_level, "iat": now, "exp": exp,
        },
        trust_anchor_private_pem(), algorithm="EdDSA",
    )
    return {
        "operator_id": operator_id,
        "verification_level": stored_level,
        "operator_attestation_jwt": token,
        "expires_at_unix": exp,
        "expires_at_iso": datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(),
        "trust_anchor_public_key_pem": trust_anchor_public_key_pem(),
    }


def verify_operator_attestation(token: str) -> dict:
    """Verify an operator attestation JWT against the trust anchor. Offline.
    Returns {operator_id, public_key_b64, verification_level}."""
    decoded = jwt.decode(
        token, trust_anchor_public_key_pem().encode(),
        algorithms=["EdDSA"], audience=_AUD, issuer=_ISS,
    )
    if decoded.get("kind") != _KIND:
        raise jwt.InvalidTokenError(
            f"unexpected JWT kind {decoded.get('kind')!r}; expected {_KIND!r}"
        )
    return {
        "operator_id": decoded["operator_id"],
        "public_key_b64": decoded["pubkey_b64"],
        "verification_level": decoded.get("verification_level", "self"),
    }


# ─── Domain-control proof (DNS-TXT challenge, stateless) ─────────────────────

def _challenge_token(domain: str, public_key_b64: str) -> str:
    """Deterministic token binding (domain, pubkey) to this deployment. Stateless
    — no challenge table — and stable until the key rotates. Secret is derived
    from the trust-anchor private key so only this server can mint valid tokens."""
    secret = hashlib.sha256(trust_anchor_private_pem()).digest()
    digest = hashlib.sha256(
        secret + b"|" + domain.encode() + b"|" + public_key_b64.encode()
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def request_domain_challenge(domain: str, public_key_b64: str) -> dict:
    """Return the DNS-TXT record the operator must publish to prove control of
    `domain` for this public key."""
    domain = (domain or "").strip().lower()
    if not domain or "." not in domain or "/" in domain or " " in domain:
        raise OperatorError("domain must be a bare hostname, e.g. acme.example")
    _validate_pubkey(public_key_b64)
    token = _challenge_token(domain, public_key_b64)
    return {
        "domain": domain,
        "record_name": CHALLENGE_PREFIX + domain,
        "record_type": "TXT",
        "record_value": f"snhp-verify={token}",
        "instructions": (
            f"Publish a TXT record at {CHALLENGE_PREFIX + domain} with value "
            f"snhp-verify={token}, then call verify_domain. The token is bound "
            f"to this public key — a different key needs a different record."
        ),
    }


def _resolve_txt_doh(name: str) -> list[str]:
    """Resolve TXT records via DNS-over-HTTPS (no extra dependency). Overridable
    as registry._RESOLVE_TXT in tests."""
    url = "https://dns.google/resolve?name=" + urllib.parse.quote(name) + "&type=TXT"
    req = urllib.request.Request(url, headers={"User-Agent": "snhp-registry"})
    with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as r:
        data = json.loads(r.read().decode())
    out = []
    for ans in data.get("Answer", []) or []:
        if ans.get("type") == 16:  # TXT
            # DoH may return a multi-string TXT record as space-separated quoted
            # chunks ("a" "b"); strip the outer quotes and join the chunks so a
            # chunked record still matches the expected single value.
            val = str(ans.get("data", "")).strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            out.append(val.replace('" "', ''))
    return out


_RESOLVE_TXT = _resolve_txt_doh


def verify_domain_and_register(domain: str, public_key_b64: str,
                               display_name: str | None = None) -> dict:
    """Verify the DNS-TXT challenge and register the domain as a domain-verified
    operator (operator_id == domain). Raises OperatorError if the record is
    missing or wrong."""
    domain = (domain or "").strip().lower()
    if not domain or "." not in domain:
        raise OperatorError("domain must be a bare hostname, e.g. acme.example")
    _validate_pubkey(public_key_b64)
    expected = f"snhp-verify={_challenge_token(domain, public_key_b64)}"
    try:
        records = _RESOLVE_TXT(CHALLENGE_PREFIX + domain)
    except Exception as e:  # noqa: BLE001
        raise OperatorError(f"DNS lookup failed for {CHALLENGE_PREFIX + domain}: {e}") from e
    if expected not in records:
        raise OperatorError(
            f"required TXT record not found at {CHALLENGE_PREFIX + domain}. "
            f"Publish 'snhp-verify=...' from request_domain_challenge first."
        )
    # DNS control was just proven, so authorize key rotation for this domain.
    return register_operator(domain, public_key_b64, display_name,
                             verification_level="domain", allow_rotation=True)


# ─── Lookups / revocation ────────────────────────────────────────────────────

def get_operator(operator_id: str) -> dict | None:
    _ensure_migrated()
    with db_conn(_SCHEMA) as c:
        row = c.execute(
            """SELECT operator_id, public_key_b64, display_name, created_at,
                      revoked_at, verification_level
               FROM operators WHERE operator_id = ?""",
            (operator_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "operator_id": row[0], "public_key_b64": row[1], "display_name": row[2],
        "created_at": row[3], "revoked_at": row[4], "verification_level": row[5],
    }


def is_revoked(operator_id: str) -> bool:
    op = get_operator(operator_id)
    return op is None or op["revoked_at"] is not None


def revoke_operator(operator_id: str) -> bool:
    _ensure_migrated()
    with db_conn(_SCHEMA) as c:
        cur = c.execute(
            "UPDATE operators SET revoked_at = ? WHERE operator_id = ? AND revoked_at IS NULL",
            (int(time.time()), operator_id),
        )
        c.commit()
        return getattr(cur, "rowcount", 0) != 0
