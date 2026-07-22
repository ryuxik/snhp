"""THE STORE — the BLIND LOCKER (park & retrieve), STORE.md §2c.

A konbini parcel counter for agents: the agent ENCRYPTS before parking, we
store ciphertext ONLY, and we never decrypt, inspect, parse, or log the
contents. Keys never transit the store. A breach of our storage leaks sealed
boxes — twice over (see the at-rest layer below). This is the only custody a
convenience store may sell: 7-Eleven's counter takes parcels BECAUSE it can't
open them (§2c). The admitted limitation is STRUCTURAL, not rhetorical — the cap
is enforced in the architecture, then printed on the receipt.

WHAT CROSSES THE COUNTER
  park(api_key, blob: bytes, ttl_seconds) -> {ticket, expires_at, size_bytes,
       price_millicents, receipt}. `blob` is OPAQUE bytes (the customer's own
       ciphertext). The ticket is the claim token — random, unguessable
       (secrets.token_urlsafe), returned to the caller and NEVER stored raw
       (only its keyed hash is). retrieve(api_key, ticket) -> the exact bytes,
       or a clean not_found / expired outcome.

BLIND BY CONSTRUCTION
  - contents are never logged: telemetry records size + ticket-HASH + a keyed
    repeat_key pseudonym, never the blob, never the raw ticket, never the raw
    key (the same hygiene the telemetry/demand modules keep).
  - hard TTL, enforced on retrieve AND lazily reaped (expired rows are deleted
    opportunistically on every park/retrieve).
  - a documented SIZE CAP (256 KiB); an oversize park is refused UNCHARGED and
    UNSTORED.

TWO LOCKS, WE HOLD ONE (at-rest defense)
  What the customer hands us is ALREADY ciphertext they encrypted (lock #1, key
  never ours). On top of that we wrap a server-side at-rest layer keyed by an
  env secret (LOCKER_AT_REST_KEY) via AES-256-GCM (lock #2, key ours). A raw DB
  dump alone therefore yields our-layer ciphertext of the customer's ciphertext
  — doubly-sealed boxes. If LOCKER_AT_REST_KEY is unset (dev/local) we DEGRADE
  HONESTLY: the customer ciphertext is stored as-is under a visible scheme tag
  and the receipt says at_rest="none" — no fake at-rest layer is claimed. (Per
  the spec's house rule: an admitted limitation must be structural. We never
  substitute XOR-with-HKDF theater for real AEAD.)

SETTLEMENT — settle-on-accept (charge only on durable store)
  Parking is the paid action; retrieval is free (the park covered it, like a
  negotiation session's moves). We charge the ONE wallet via
  onboarding.wallet_debit ONLY after the blob is durably stored — never on a
  failed/oversize park, never on retrieve. The price is a thin published
  commodity fee scaled by a size tier (storage wholesale ~0); the store eats any
  settlement tail past a drained wallet (the never-strand asymmetry, §10 Q2),
  never overcharging.

OWNERSHIP
  A ticket is retrievable only by the SAME api_key (or, once key rotation is
  wired through, its live descendant). We store only a KEYED HASH of the owning
  api_key — never the raw key. Ownership is resolved through
  onboarding.resolve_live_key so the identity keys off the LIVE key, never a
  revoked one. See the ROTATION FOLLOW-UP note on `_owner_key_hash`.

RECEIPT
  A park returns an Ed25519-signed receipt (via receipt_signing.safe_sign) whose
  `content_hash` is the blake2b of the CUSTOMER's blob (their ciphertext) — so
  the customer can prove exactly what they stored WITHOUT us ever seeing
  plaintext. The raw ticket is deliberately NOT in the receipt (it is the secret
  claim token; only its non-secret hash and the content hash are).

House rules honored: no LLM anywhere; integer money (millicents); comments state
the constraints; the `cryptography` dep is the one core.notary already ships.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Callable, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from gametheory._db import db_conn
from vend import telemetry
from vend.receipt_signing import safe_sign

# ─── Published policy constants (all stated in the catalog, §2c) ─────────────

# SIZE CAP: 256 KiB. A sane launch cap for a parcel counter — big enough for a
# serialized plan/context blob, small enough that a DB row stays cheap and abuse
# is bounded. An oversize park is refused UNCHARGED and UNSTORED.
LOCKER_MAX_BYTES = 256 * 1024                 # 262_144

# TTL bounds. A park names its own ttl_seconds; we clamp to [MIN, MAX] and return
# the EFFECTIVE expires_at so the caller sees exactly how long the parcel lives
# (no silent surprise). Default is one day; max a week (cross-session plans span
# days, like the negotiation session's TTL) — long enough to be useful, bounded
# so a blind store is never an unbounded free disk.
LOCKER_TTL_MIN_S = 60
LOCKER_TTL_DEFAULT_S = 86_400                 # 24h
LOCKER_TTL_MAX_S = 7 * 86_400                 # 7 days

# PRICE: a thin published commodity fee scaled by ONE size tier (storage
# wholesale is ~0, so this is a paid SIGNAL — a park proves the agent plans
# across sessions, telemetry gold — not a margin play). Two tiers, both well
# under the fetch slot's 2¢ cap. Integer millicents (1 cent = 1000 millicents).
LOCKER_TIER1_BYTES = 64 * 1024                # 65_536  (<= 64 KiB)
LOCKER_PARK_FEE_TIER1_MILLICENTS = 500        # 0.5¢  small parcels
LOCKER_PARK_FEE_TIER2_MILLICENTS = 1000       # 1.0¢  64 KiB .. 256 KiB
# The published ceiling a single park can cost (the max tier). Documented in the
# catalog exactly as the fetch slot's max_price is.
LOCKER_MAX_PRICE_MILLICENTS = LOCKER_PARK_FEE_TIER2_MILLICENTS

_MILLICENTS_PER_DOLLAR = 100_000              # 1$ = 100c = 100_000 millicents

# At-rest AEAD parameters. The env secret is stretched to a 256-bit AES key via
# HKDF-SHA256 (so any-length secret works and the derived key is domain-separated
# by `info`). A fresh 96-bit nonce per parcel; the ticket_hash is bound as
# associated data so a sealed blob cannot be moved to a different locker row.
_AT_REST_ENV = "LOCKER_AT_REST_KEY"
_HKDF_INFO = b"snhp-locker-at-rest-v1"
_AESGCM_NONCE_BYTES = 12
_SCHEME_PLAINTEXT = b"\x00"   # degraded: no server key set; stored as-is
_SCHEME_AESGCM = b"\x01"      # AES-256-GCM under the env key


# ─── Schema (new table, IF NOT EXISTS only — never ALTER, house rule) ────────
#
# The sealed blob is stored as base64 TEXT rather than a raw BLOB column: the
# repo runs SQLite (dev) AND Postgres (prod), and gametheory._db._translate_sql
# maps INTEGER->BIGINT / ?->%s but does NOT map SQLite `BLOB` to Postgres
# `BYTEA`, so a literal BLOB column would fail the Postgres CREATE. base64 TEXT
# is portable across both backends and the stored value is still opaque sealed
# ciphertext. `ticket_hash` is the PK — we store the ticket's HASH, never the
# raw claim token, so a DB dump reveals no live tickets; lookups hash the
# presented ticket and match on the hash.
_LOCKER_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS locker (
        ticket_hash TEXT PRIMARY KEY,
        owner_key_hash TEXT NOT NULL,      -- keyed hash of the owner key, never raw
        blob TEXT NOT NULL,                -- base64 of the at-rest-sealed ciphertext
        size_bytes INTEGER NOT NULL,       -- the CUSTOMER blob's length (pre-seal)
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_locker_expires ON locker (expires_at)",
)


def _conn():
    return db_conn(_LOCKER_SCHEMA)


# ─── Hashing (keyed for the stored anchors; unkeyed for the customer anchor) ──


def _ticket_hash(ticket: str) -> str:
    """The stored PK for a ticket: a KEYED blake2b of the raw claim token, so a
    raw DB dump cannot be dictionary-checked back to a live ticket without the
    telemetry pepper. Deterministic per deploy (stable pepper), so a presented
    ticket rehashes to the same key. The raw ticket has 256 bits of entropy;
    keying is defense-in-depth on top of that."""
    return hashlib.blake2b(ticket.encode(), digest_size=16, person=b"lockr-tkt",
                           key=telemetry._pepper()).hexdigest()


def _owner_key_hash(api_key: str) -> str:
    """The stored owner identity: a KEYED blake2b of the api_key (same pepper
    discipline as telemetry, distinct `person` so it is not literally the
    telemetry pseudonym). Never the raw key — a breach of the locker table yields
    no credentials.

    ROTATION FOLLOW-UP: the caller resolves the key to its LIVE self via
    onboarding.resolve_live_key before hashing, so ownership never keys off a
    revoked key. But the rotation chain is forward-only (replaced_by -> tip) and
    resolve_live_key jumps to the CURRENT tip, so a ticket parked under key K1
    and retrieved after K1->K2 rotation stores hash(K1) while retrieve resolves
    to hash(K2) — a mismatch. Making tickets survive rotation needs a rotation
    HOOK that re-keys locker rows (owner_key_hash: hash(K1) -> hash(K2)) inside
    onboarding.rotate_key, or a rotation-stable account id. That hook is out of
    this lane (onboarding is mid-edit); documented here and in the report."""
    return hashlib.blake2b(api_key.encode(), digest_size=16, person=b"snhp-lockr",
                           key=telemetry._pepper()).hexdigest()


def _content_hash(blob: bytes) -> str:
    """The receipt's customer-checkable anchor: an UNKEYED blake2b of the
    customer's blob (their ciphertext). Unkeyed on purpose — the customer holds
    the same bytes and must be able to RECOMPUTE this to prove what they stored,
    WITHOUT us ever seeing plaintext and without needing our pepper."""
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


# ─── At-rest seal / unseal (lock #2 — the key we hold) ───────────────────────


def _at_rest_key() -> Optional[bytes]:
    """The 256-bit AES key derived from LOCKER_AT_REST_KEY, or None when the
    env secret is unset (dev/local) — in which case we DEGRADE HONESTLY rather
    than fake an at-rest layer. Read fresh each call (locker ops are infrequent;
    HKDF is cheap) so a test/deploy that sets the env mid-process is honored."""
    secret = os.environ.get(_AT_REST_ENV, "").strip()
    if not secret:
        return None
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=_HKDF_INFO).derive(secret.encode())


def _seal(blob: bytes, ticket_hash: str) -> tuple[bytes, str]:
    """Wrap the customer ciphertext in our at-rest layer. Returns (stored_bytes,
    at_rest_scheme). A one-byte scheme tag prefixes the stored bytes so retrieve
    knows how to unseal:
      \\x01 nonce||AESGCM(ct)  — AES-256-GCM under the env key (ticket_hash AAD)
      \\x00 blob               — degraded (no env key): customer ciphertext as-is
    """
    key = _at_rest_key()
    if key is None:
        # Honest degrade: no server-side layer. The stored bytes are still the
        # customer's OWN ciphertext (lock #1); we simply don't add lock #2.
        return _SCHEME_PLAINTEXT + blob, "none"
    nonce = os.urandom(_AESGCM_NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, blob, ticket_hash.encode())
    return _SCHEME_AESGCM + nonce + ct, "aes-256-gcm"


def _unseal(stored: bytes, ticket_hash: str) -> bytes:
    """Reverse _seal. Raises LockerError if a row sealed under the env key can no
    longer be opened (env key rotated away/absent) — an honest failure, never a
    silent wrong-plaintext."""
    scheme, body = stored[:1], stored[1:]
    if scheme == _SCHEME_PLAINTEXT:
        return body
    if scheme == _SCHEME_AESGCM:
        key = _at_rest_key()
        if key is None:
            raise LockerError("at_rest_key_unavailable")
        nonce, ct = body[:_AESGCM_NONCE_BYTES], body[_AESGCM_NONCE_BYTES:]
        return AESGCM(key).decrypt(nonce, ct, ticket_hash.encode())
    raise LockerError("unknown_at_rest_scheme")


class LockerError(Exception):
    """An at-rest unseal could not be completed (missing/rotated env key or an
    unknown scheme tag). Surfaced as a clean retrieve outcome, never a 500."""


# ─── Telemetry sink (contents NEVER logged) ──────────────────────────────────


def _default_sink(**fields) -> None:
    """Default sink: one append-only JSONL line via the telemetry module's own
    writer (shared lock + path). Records size + ticket_hash + repeat_key only —
    NEVER the blob, NEVER the raw ticket, NEVER the raw key."""
    telemetry._append({"kind": "locker", "ts": time.time(), **fields})


_TELEMETRY_SINK: Callable[..., None] = _default_sink


def set_telemetry_sink(sink: Callable[..., None]) -> None:
    """Swap the telemetry sink (tests capture lines to assert no blob leaks)."""
    global _TELEMETRY_SINK
    _TELEMETRY_SINK = sink


def _emit(**fields) -> None:
    try:
        _TELEMETRY_SINK(**fields)
    except Exception:
        # Telemetry must never break the counter — the parcel was already
        # stored/returned on its own terms before we log it.
        pass


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _exact_usd(millicents: int) -> str:
    """Exact dollar string for a millicent amount — five decimals, no rounding
    (the store's exact-display rule; a millicent is $0.00001)."""
    m = int(millicents)
    return f"${m // _MILLICENTS_PER_DOLLAR}.{m % _MILLICENTS_PER_DOLLAR:05d}"


def _price_for(size_bytes: int) -> int:
    """The published park fee for a parcel of this size (integer millicents)."""
    if size_bytes <= LOCKER_TIER1_BYTES:
        return LOCKER_PARK_FEE_TIER1_MILLICENTS
    return LOCKER_PARK_FEE_TIER2_MILLICENTS


def _clamp_ttl(ttl_seconds: Optional[int]) -> int:
    """Clamp a requested TTL to [MIN, MAX]; None -> the default. The caller learns
    the effective value from the returned expires_at, so clamping is never
    silent."""
    if ttl_seconds is None:
        return LOCKER_TTL_DEFAULT_S
    ttl = int(ttl_seconds)
    if ttl < LOCKER_TTL_MIN_S:
        return LOCKER_TTL_MIN_S
    if ttl > LOCKER_TTL_MAX_S:
        return LOCKER_TTL_MAX_S
    return ttl


def _reap_expired(c, now: int) -> None:
    """Lazily delete expired rows — a hard TTL is enforced on read AND swept
    here so a parcel that outlived its ttl leaves no bytes at rest. Bounded,
    cheap, indexed on expires_at."""
    c.execute("DELETE FROM locker WHERE expires_at <= ?", (now,))
    c.commit()


# ─── park (the paid action — settle-on-accept) ───────────────────────────────


def park(api_key: str, blob: bytes, ttl_seconds: Optional[int] = None,
         *, now: Optional[int] = None, door: str = "lib") -> dict:
    """Store one OPAQUE ciphertext blob and hand back a claim ticket + a signed
    receipt. Charges the park fee ONCE, only after the blob is durably stored
    (settle-on-accept). `now` is injectable for deterministic tests.

    Failure envelopes (all UNCHARGED and UNSTORED) mirror the store's style
    {ok:false, charged:false, code, reason}:
      empty_blob / too_large       — the blob is 0 bytes / over the size cap
      unknown_key                  — the key resolves to no live key
      insufficient_balance         — the wallet holds 0 millicents

    On success: {ok:true, ticket, ticket_hash, size_bytes, expires_at,
    price_millicents, receipt}. The raw `ticket` is the caller's secret claim
    token — keep it; it is never stored raw and never appears in the receipt.
    """
    from gametheory.server import onboarding

    now = int(time.time()) if now is None else int(now)

    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("blob must be bytes (the customer's own ciphertext)")
    blob = bytes(blob)
    size_bytes = len(blob)

    # Cap checks FIRST — nothing stored, nothing charged.
    if size_bytes == 0:
        _emit(op="park", door=door, repeat_key=_rk(api_key), ticket_hash=None,
              size_bytes=0, ok=False, charged=False, price_millicents=0,
              reason="empty_blob")
        return _fail("empty_blob", "a parcel must carry at least one byte")
    if size_bytes > LOCKER_MAX_BYTES:
        _emit(op="park", door=door, repeat_key=_rk(api_key), ticket_hash=None,
              size_bytes=size_bytes, ok=False, charged=False, price_millicents=0,
              reason="too_large")
        return _fail("too_large",
                     f"parcel is {size_bytes} bytes; the cap is "
                     f"{LOCKER_MAX_BYTES} ({LOCKER_MAX_BYTES // 1024} KiB)")

    # Resolve the owner to its LIVE key so ownership never keys off a revoked
    # key (and so the debit below targets a real wallet).
    owner = onboarding.resolve_live_key(api_key)
    if owner is None:
        _emit(op="park", door=door, repeat_key=_rk(api_key), ticket_hash=None,
              size_bytes=size_bytes, ok=False, charged=False, price_millicents=0,
              reason="unknown_key")
        return _fail("unknown_key", "no live key for this credential")

    # Admission: the wallet must hold SOME money. The store eats any settlement
    # tail past the balance (never-strand, §10 Q2); only a truly empty wallet is
    # refused — and nothing is stored for a wallet that cannot pay.
    if onboarding.wallet_available(owner)["total_millicents"] <= 0:
        _emit(op="park", door=door, repeat_key=_rk(owner), ticket_hash=None,
              size_bytes=size_bytes, ok=False, charged=False, price_millicents=0,
              reason="insufficient_balance")
        return _fail("insufficient_balance",
                     "wallet is empty; top up before parking",
                     needed_millicents=1)

    ttl = _clamp_ttl(ttl_seconds)
    expires_at = now + ttl
    price = _price_for(size_bytes)

    # Mint the claim token, store only its hash. The at-rest seal binds the
    # ticket_hash as AAD, so a sealed blob is cryptographically tied to its row.
    ticket = secrets.token_urlsafe(32)         # 256 bits of entropy
    ticket_hash = _ticket_hash(ticket)
    owner_hash = _owner_key_hash(owner)
    stored_bytes, at_rest = _seal(blob, ticket_hash)
    stored_b64 = base64.b64encode(stored_bytes).decode()

    # DURABLE STORE, then (and only then) charge — settle-on-accept.
    with _conn() as c:
        _reap_expired(c, now)
        c.execute(
            """INSERT INTO locker (ticket_hash, owner_key_hash, blob,
                                   size_bytes, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticket_hash, owner_hash, stored_b64, size_bytes, now, expires_at))
        c.commit()

    try:
        debit = onboarding.wallet_debit(owner, price)
    except Exception:
        # A store-without-charge would be the store's loss, but cleaner to undo:
        # the parcel is unwound and the caller gets an uncharged error rather
        # than a stored-but-unbilled parcel. (owner is live, so this is a race,
        # not the common path.)
        with _conn() as c:
            c.execute("DELETE FROM locker WHERE ticket_hash = ?", (ticket_hash,))
            c.commit()
        _emit(op="park", door=door, repeat_key=_rk(owner),
              ticket_hash=ticket_hash, size_bytes=size_bytes, ok=False,
              charged=False, price_millicents=0, reason="charge_failed")
        return _fail("charge_failed", "could not settle the park; nothing stored")

    funding = {"starter_millicents": debit["starter_spent"],
               "funded_millicents": debit["funded_spent"]}
    # content_hash is over the CUSTOMER's blob (their ciphertext) — the anchor
    # they can recompute to prove what they stored, without us seeing plaintext.
    content_hash = _content_hash(blob)
    receipt = safe_sign({
        "kind": "locker.park",
        "slot_id": "locker",
        "content_hash": content_hash,      # blake2b-128 of the customer blob
        "ticket_hash": ticket_hash,        # non-secret row id (NOT the raw ticket)
        "size_bytes": size_bytes,
        "at_rest": at_rest,                # "aes-256-gcm" | "none" (honest)
        "price_millicents": price,
        "price_usd": _exact_usd(price),
        "wallet_delta_millicents": debit["starter_spent"] + debit["funded_spent"],
        "absorbed_tail_millicents": debit["shortfall_millicents"],
        "funding": funding,
        "balance_after": debit["balance_after"],
        "created_at": now,
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "ts": time.time(),
    })
    _emit(op="park", door=door, repeat_key=_rk(owner), ticket_hash=ticket_hash,
          size_bytes=size_bytes, ok=True, charged=True, price_millicents=price,
          reason=None)
    return {"ok": True, "ticket": ticket, "ticket_hash": ticket_hash,
            "size_bytes": size_bytes, "expires_at": expires_at,
            "price_millicents": price, "receipt": receipt}


# ─── retrieve (free — the park covered it) ───────────────────────────────────


def retrieve(api_key: str, ticket: str, *, now: Optional[int] = None,
             door: str = "lib") -> dict:
    """Return the exact bytes parked under `ticket`, or a clean outcome. FREE —
    retrieval is never charged (the park settled it). `now` is injectable for
    deterministic TTL tests.

    Outcomes:
      {ok:true, blob: bytes, size_bytes, expires_at}
      {ok:false, code:"not_found"}            — unknown ticket OR wrong owner
                                                 (indistinguishable, so a ticket
                                                 cannot be probed with another
                                                 key)
      {ok:false, code:"expired"}              — the parcel outlived its TTL
      {ok:false, code:"at_rest_key_unavailable"} — sealed under a server key that
                                                 is no longer present (honest)
    """
    from gametheory.server import onboarding

    now = int(time.time()) if now is None else int(now)
    owner = onboarding.resolve_live_key(api_key)
    ticket_hash = _ticket_hash(ticket)

    with _conn() as c:
        row = c.execute(
            """SELECT owner_key_hash, blob, size_bytes, expires_at
               FROM locker WHERE ticket_hash = ?""", (ticket_hash,)).fetchone()
        if row is None:
            _reap_expired(c, now)
            _emit(op="retrieve", door=door, repeat_key=_rk(api_key),
                  ticket_hash=ticket_hash, size_bytes=None, ok=False,
                  charged=False, price_millicents=0, reason="not_found")
            return _fail("not_found", "no parcel for this ticket")

        owner_hash, stored_b64, size_bytes, expires_at = row
        # Ownership check — a non-owner (or an unknown key -> owner None) is told
        # not_found, exactly as if the ticket didn't exist, so existence never
        # leaks. Compared BEFORE expiry so a non-owner learns nothing either way.
        expected = _owner_key_hash(owner) if owner is not None else None
        if expected is None or owner_hash != expected:
            _emit(op="retrieve", door=door, repeat_key=_rk(api_key),
                  ticket_hash=ticket_hash, size_bytes=None, ok=False,
                  charged=False, price_millicents=0, reason="not_found")
            return _fail("not_found", "no parcel for this ticket")

        if int(expires_at) <= now:
            # Hard TTL enforced on read: expired -> gone. Reap it now.
            c.execute("DELETE FROM locker WHERE ticket_hash = ?", (ticket_hash,))
            c.commit()
            _emit(op="retrieve", door=door, repeat_key=_rk(owner),
                  ticket_hash=ticket_hash, size_bytes=None, ok=False,
                  charged=False, price_millicents=0, reason="expired")
            return _fail("expired", "the parcel's TTL has passed")

    stored_bytes = base64.b64decode(stored_b64)
    try:
        blob = _unseal(stored_bytes, ticket_hash)
    except LockerError as e:
        _emit(op="retrieve", door=door, repeat_key=_rk(owner),
              ticket_hash=ticket_hash, size_bytes=None, ok=False, charged=False,
              price_millicents=0, reason=str(e))
        return _fail(str(e), "the at-rest layer could not open this parcel")

    _emit(op="retrieve", door=door, repeat_key=_rk(owner),
          ticket_hash=ticket_hash, size_bytes=int(size_bytes), ok=True,
          charged=False, price_millicents=0, reason=None)
    return {"ok": True, "blob": blob, "size_bytes": int(size_bytes),
            "expires_at": int(expires_at)}


# ─── Door-ready wrappers (bytes cross HTTP/MCP as base64) ─────────────────────


def park_b64(api_key: str, blob_b64: str, ttl_seconds: Optional[int] = None,
             *, door: str = "http") -> dict:
    """Door-facing park: accepts the blob as base64 (JSON/MCP can't carry raw
    bytes). Decodes, parks, and returns the same envelope park() returns (no raw
    bytes in a park result). A malformed base64 body is a clean client error."""
    try:
        blob = base64.b64decode(blob_b64, validate=True)
    except Exception:
        return _fail("bad_encoding", "blob_b64 is not valid base64")
    return park(api_key, blob, ttl_seconds, door=door)


def retrieve_b64(api_key: str, ticket: str, *, door: str = "http") -> dict:
    """Door-facing retrieve: on success returns the parcel as base64 under
    `blob_b64` (never raw bytes over the wire); failure envelopes pass through."""
    out = retrieve(api_key, ticket, door=door)
    if out.get("ok"):
        blob = out.pop("blob")
        out["blob_b64"] = base64.b64encode(blob).decode()
    return out


# ─── Catalog entry (the counter's shelf card — honest, checkable language) ────


def catalog_entry() -> dict:
    """The public locker shelf card for the store catalog. States the TTL, size
    cap, and price, and the blind-custody guarantee in checkable terms (§2c: the
    limitation is load-bearing, so it goes on the receipt). Merged into the
    store catalog by the door/orchestrator — this module never edits store.py."""
    return {
        "id": "locker",
        "title": "Blind locker — park & retrieve ciphertext across sessions",
        "tier": "commodity",
        "unit": "millicents",
        "price": {
            "model": "flat park fee by size tier; retrieval is free",
            "tiers": [
                {"max_bytes": LOCKER_TIER1_BYTES,
                 "park_millicents": LOCKER_PARK_FEE_TIER1_MILLICENTS,
                 "park_usd": _exact_usd(LOCKER_PARK_FEE_TIER1_MILLICENTS)},
                {"max_bytes": LOCKER_MAX_BYTES,
                 "park_millicents": LOCKER_PARK_FEE_TIER2_MILLICENTS,
                 "park_usd": _exact_usd(LOCKER_PARK_FEE_TIER2_MILLICENTS)},
            ],
            "max_price_millicents": LOCKER_MAX_PRICE_MILLICENTS,
            "settlement": ("settle-on-accept: charged once, only after the blob "
                           "is durably stored; never on a failed/oversize park, "
                           "never on retrieve"),
        },
        "ttl": {
            "min_seconds": LOCKER_TTL_MIN_S,
            "default_seconds": LOCKER_TTL_DEFAULT_S,
            "max_seconds": LOCKER_TTL_MAX_S,
            "note": "hard TTL, enforced on retrieve and lazily reaped; a "
                    "requested ttl is clamped to [min, max] and the effective "
                    "expires_at is returned",
        },
        "size_cap_bytes": LOCKER_MAX_BYTES,
        "request_doc": ("park: {api_key, blob_b64: base64(your ciphertext), "
                        "ttl_seconds?} -> {ticket, expires_at, size_bytes, "
                        "receipt}; retrieve: {api_key, ticket} -> {blob_b64}"),
        "privacy": (
            "BLIND by construction: you encrypt BEFORE parking, we store "
            "ciphertext only and never decrypt, inspect, parse, or log it; your "
            "keys never transit the store; contents are never logged (we record "
            "size + a hashed ticket + a keyed pseudonym only); hard TTL; the "
            "ticket is stored as a hash, so a DB dump reveals no live tickets. "
            "AT-REST: we add a second AES-256-GCM layer keyed by a server secret "
            "(LOCKER_AT_REST_KEY), so a raw DB dump alone yields DOUBLY-sealed "
            "boxes; where that secret is unset the receipt says at_rest='none' "
            "rather than claim a layer we don't have."),
        "receipt": (
            "each park returns an Ed25519-signed receipt whose content_hash is "
            "blake2b-128 of YOUR blob (your ciphertext), so you can prove exactly "
            "what you stored without us ever seeing plaintext; verify it the same "
            "way as any store receipt (see the catalog's `receipts` block)."),
    }


# ─── small internals ─────────────────────────────────────────────────────────


def _rk(api_key: Optional[str]) -> Optional[str]:
    """The keyed telemetry pseudonym (never the raw key), or None if keyless."""
    return telemetry._repeat_key(api_key) if api_key else None


def _fail(code: str, reason: str, **extra) -> dict:
    """The normalized uncharged failure envelope, matching the store's shape."""
    return {"ok": False, "charged": False, "code": code, "reason": reason,
            "error": code, **extra}
