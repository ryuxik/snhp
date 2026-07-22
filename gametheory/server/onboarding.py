"""
Programmatic API key issuance + the store wallet.

Self-serve key issuance, idempotent on agent_id within 24h. Every key carries
ONE wallet (the `wallet` table): a starter bucket (the 50¢ grant) and a funded
bucket (own-money top-ups via Stripe). One unit — millicents — spends across
every slot, anchor and commodity alike (STORE.md §2d, §6).

Schema:
  keys
    api_key                 TEXT  PRIMARY KEY
    agent_id                TEXT  NOT NULL
    contact_email           TEXT  NOT NULL
    intended_use_summary    TEXT  NOT NULL
    tier                    TEXT  NOT NULL    -- always "standard" now
    rate_limit_per_minute   BIGINT NOT NULL
    created_at              BIGINT NOT NULL   -- unix seconds
    balance_usd_cents       BIGINT NOT NULL DEFAULT 0   -- DEAD/deprecated: the
                                                         -- `wallet` table is the
                                                         -- single money source;
                                                         -- never read/written.
    telemetry_consent       INTEGER NOT NULL DEFAULT 0  -- opt-in to data moat
                                                         -- (set at issuance,
                                                         -- immutable after)
  wallet
    api_key                 TEXT  PRIMARY KEY
    funded_millicents       INTEGER NOT NULL DEFAULT 0  -- own-money top-ups
    starter_millicents      INTEGER NOT NULL DEFAULT 0  -- the 50¢ grant
    starter_granted_at      INTEGER                     -- NULL until granted

Storage: SQLite (default ~/.gametheory/keys.db) or Postgres if DATABASE_URL.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from gametheory._db import db_conn


_RATE_LIMIT_PER_MIN = 600     # uniform now; the free/metered split is gone
_KEY_PREFIX = "gt_"

# The store's ONE wallet coin (STORE.md §2d, §6). A single unit spends across
# every slot — the anchor $2 session and the commodity fetch slot both settle
# here, so the starter credit is spendable on all of them. 1 cent == 1000
# millicents. ("millicent" is the honest name — a thousandth of a cent; the
# earlier label implied a millionth and would mislead a naive agent by 1000×.)
MILLICENTS_PER_CENT = 1000
# One-time starter credit into the starter bucket, UNCONDITIONAL by
# construction (STORE.md §6: pre-committed so it can never become a scarcity
# lever). 50¢ per §6, which also bounds per-key Sybil cost at exactly this
# number.
STARTER_GRANT_MILLICENTS = 50_000


_KEYS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS keys (
        api_key TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        intended_use_summary TEXT NOT NULL,
        tier TEXT NOT NULL,
        rate_limit_per_minute INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        balance_usd_cents INTEGER NOT NULL DEFAULT 0,
        telemetry_consent INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_id ON keys(agent_id, created_at)",
    # Rotation/revocation lives in its own table so the `keys` schema never
    # needs an ALTER TABLE migration (see NOTE below). A key is dead iff it
    # has a row here; replaced_by lets in-flight Stripe credits follow the
    # chain to the live key.
    """
    CREATE TABLE IF NOT EXISTS revoked_keys (
        api_key TEXT PRIMARY KEY,
        revoked_at INTEGER NOT NULL,
        replaced_by TEXT NOT NULL
    )
    """,
    # The wallet lives in its OWN table (same house rule as revoked_keys: never
    # ALTER `keys`). ONE wallet, two buckets so a gate can exclude
    # starter-funded usage without a join: the starter grant and the own-money
    # top-ups are spent in that order (see wallet_debit). There is no third
    # cent source any more — this table is the whole money supply.
    """
    CREATE TABLE IF NOT EXISTS wallet (
        api_key TEXT PRIMARY KEY,
        funded_millicents INTEGER NOT NULL DEFAULT 0,
        starter_millicents INTEGER NOT NULL DEFAULT 0,
        starter_granted_at INTEGER          -- NULL until the one-time grant
    )
    """,
)
# NOTE: this schema is `IF NOT EXISTS`-only. Adding a column to a DB created
# before the column was in the schema requires a manual
# `ALTER TABLE keys ADD COLUMN ... DEFAULT ...` run before deploying the code
# that reads the column.


def _conn():
    return db_conn(_KEYS_SCHEMA)


def _wallet_summary(starter: int, funded: int) -> dict:
    return {"starter_millicents": int(starter),
            "funded_millicents": int(funded),
            "total_millicents": int(starter) + int(funded)}


def issue_key(*, agent_id: str, contact_email: str,
              intended_use_summary: str,
              telemetry_consent: bool = False) -> dict:
    """
    Issue a new API key, idempotent on agent_id within 24h. The 50¢ starter
    credit is granted immediately (unconditional, §6) and the response carries
    the wallet summary so a caller never has to guess what it holds.

    `telemetry_consent` is set at issuance and immutable afterwards.
    Revocation is via /v1/telemetry/delete (which removes existing rows)
    plus refraining from passing share_outcome=True on subsequent calls;
    the consent flag itself doesn't change because doing so would create
    races between consent state and in-flight writes.
    """
    if not agent_id or len(agent_id) < 3 or len(agent_id) > 128:
        raise ValueError("agent_id must be 3-128 chars")
    if "@" not in contact_email:
        raise ValueError("contact_email must be an email")
    if not 8 <= len(intended_use_summary) <= 1024:
        raise ValueError("intended_use_summary must be 8-1024 chars")

    now = int(time.time())
    cutoff = now - 86400
    consent_int = 1 if telemetry_consent else 0

    with _conn() as c:
        row = c.execute(
            """SELECT api_key, tier, rate_limit_per_minute, created_at,
                      telemetry_consent
               FROM keys WHERE agent_id = ? AND created_at >= ?
               ORDER BY created_at DESC LIMIT 1""",
            (agent_id, cutoff),
        ).fetchone()
        if row is not None:
            existing = row[0]
            reused = {
                "api_key": existing,
                "tier": row[1],
                "rate_limit_per_minute": row[2],
                "created_at": row[3],
                "telemetry_consent": bool(row[4]),
                "reused": True,
            }
        else:
            key = _KEY_PREFIX + secrets.token_urlsafe(24)
            # balance_usd_cents is omitted (DEAD column, DEFAULT 0).
            c.execute(
                """INSERT INTO keys (api_key, agent_id, contact_email,
                                      intended_use_summary, tier,
                                      rate_limit_per_minute, created_at,
                                      telemetry_consent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, agent_id, contact_email, intended_use_summary,
                 "standard", _RATE_LIMIT_PER_MIN, now, consent_int),
            )
            c.commit()
            reused = {
                "api_key": key,
                "tier": "standard",
                "rate_limit_per_minute": _RATE_LIMIT_PER_MIN,
                "created_at": now,
                "telemetry_consent": bool(consent_int),
                "reused": False,
            }

    # Grant the starter credit at issuance (idempotent — a reused key already
    # has it) and attach the wallet summary either way.
    wallet_grant_starter(reused["api_key"])
    reused["wallet"] = wallet_available(reused["api_key"])
    return reused


def lookup_key(api_key: str) -> Optional[dict]:
    """Look up a key. Returns None if not found OR revoked — a rotated key
    is indistinguishable from a nonexistent one to every caller. The wallet
    is queried separately (wallet_available); balance is not carried here."""
    if not api_key.startswith(_KEY_PREFIX):
        return None
    with _conn() as c:
        if c.execute("SELECT 1 FROM revoked_keys WHERE api_key = ?",
                     (api_key,)).fetchone() is not None:
            return None
        row = c.execute(
            """SELECT agent_id, tier, rate_limit_per_minute, created_at,
                      telemetry_consent
               FROM keys WHERE api_key = ?""",
            (api_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "agent_id": row[0],
            "tier": row[1],
            "rate_limit_per_minute": row[2],
            "created_at": row[3],
            "telemetry_consent": bool(row[4]),
        }


# ─── The wallet (the store's one settlement coin — STORE.md §2d, §6) ──────────


def wallet_grant_starter(api_key: str) -> bool:
    """One-time 50¢ starter credit into the starter bucket.

    Idempotent per key: True on the grant, False if already granted or if
    the key is unknown/revoked. The grant is UNCONDITIONAL — it must never
    acquire a precondition (STORE.md §6: pre-committed so it can't become a
    scarcity lever). Atomic on both backends: the guarded UPDATE
    (starter_granted_at IS NULL) is the idempotency point, so two concurrent
    first-calls grant exactly once.
    """
    now = int(time.time())
    with _conn() as c:
        if c.execute("SELECT 1 FROM revoked_keys WHERE api_key = ?",
                     (api_key,)).fetchone() is not None:
            return False
        if c.execute("SELECT 1 FROM keys WHERE api_key = ?",
                     (api_key,)).fetchone() is None:
            return False
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)",
                  (api_key,))
        cur = c.execute(
            """UPDATE wallet
               SET starter_millicents = starter_millicents + ?,
                   starter_granted_at = ?
               WHERE api_key = ? AND starter_granted_at IS NULL""",
            (STARTER_GRANT_MILLICENTS, now, api_key))
        granted = cur.rowcount == 1
        c.commit()
        return granted


def wallet_available(api_key: str) -> dict:
    """Spendable millicents by bucket: {starter_millicents, funded_millicents,
    total_millicents}. An unknown or revoked key reads as all zeros — an empty
    wallet, never an error; the admission check turns that into
    insufficient_balance."""
    with _conn() as c:
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
        starter = int(row[0]) if row else 0
        funded = int(row[1]) if row else 0
    return _wallet_summary(starter, funded)


def wallet_debit(api_key: str, millicents: int) -> dict:
    """Debit `millicents`, starter bucket first, then funded bucket.

    Returns {starter_spent, funded_spent, shortfall_millicents, balance_after:
    {starter_millicents, funded_millicents, total_millicents}}. shortfall > 0
    means the wallet ran dry AFTER the good was already delivered (a settlement
    race): the store eats it, the agent is NEVER charged more than it had, and
    nothing is raised. Raises ValueError ONLY for an unknown key.
    """
    if millicents < 0:
        raise ValueError("millicents must be non-negative")
    with _conn() as c:
        if c.execute("SELECT 1 FROM keys WHERE api_key = ?",
                     (api_key,)).fetchone() is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)",
                  (api_key,))
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
        starter = int(row[0])
        funded = int(row[1])

        need = int(millicents)
        starter_spent = min(need, starter)
        need -= starter_spent
        funded_spent = min(need, funded)
        need -= funded_spent
        shortfall = need                      # > 0 only on a settlement race

        starter_new = starter - starter_spent
        funded_new = funded - funded_spent
        c.execute(
            """UPDATE wallet
               SET starter_millicents = ?, funded_millicents = ?
               WHERE api_key = ?""",
            (starter_new, funded_new, api_key))
        c.commit()
    return {
        "starter_spent": starter_spent,
        "funded_spent": funded_spent,
        "shortfall_millicents": shortfall,
        "balance_after": _wallet_summary(starter_new, funded_new),
    }


def wallet_credit(api_key: str, millicents: int, bucket: str = "funded") -> int:
    """Add `millicents` to a bucket (default funded — Stripe top-ups, refunds).
    Returns the new TOTAL spendable millicents.

    Idempotency is the caller's job (the Stripe webhook dedupes events). A
    checkout can complete AFTER the customer rotated the key it started with,
    so credits follow the replaced_by chain to the live descendant (bounded
    walk) — money must never land on a dead key.
    """
    if millicents <= 0:
        raise ValueError("millicents must be positive")
    if bucket not in ("funded", "starter"):
        raise ValueError(f"unknown bucket {bucket!r}")
    col = "funded_millicents" if bucket == "funded" else "starter_millicents"
    with _conn() as c:
        for _ in range(16):
            row = c.execute(
                "SELECT replaced_by FROM revoked_keys WHERE api_key = ?",
                (api_key,)).fetchone()
            if row is None:
                break
            api_key = row[0]
        if c.execute("SELECT 1 FROM keys WHERE api_key = ?",
                     (api_key,)).fetchone() is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)",
                  (api_key,))
        c.execute(
            f"UPDATE wallet SET {col} = {col} + ? WHERE api_key = ?",
            (millicents, api_key))
        c.commit()
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
    return int(row[0]) + int(row[1])


def wallet_refund(api_key: str, split: dict) -> dict:
    """Return a prior debit to the exact buckets it came from.

    `split` is the funding split a wallet_debit recorded:
    {"starter_millicents": int, "funded_millicents": int}. Reverses it
    bucket-accurately (the Advice/session refund-on-failure path) so a starter
    dollar refunded stays a starter dollar and never silently converts to
    own-money. Follows the revoked-key chain like wallet_credit. Returns
    balance_after {starter_millicents, funded_millicents, total_millicents}.
    """
    starter_back = int(split.get("starter_millicents", 0) or 0)
    funded_back = int(split.get("funded_millicents", 0) or 0)
    if starter_back < 0 or funded_back < 0:
        raise ValueError("refund amounts must be non-negative")
    with _conn() as c:
        for _ in range(16):
            row = c.execute(
                "SELECT replaced_by FROM revoked_keys WHERE api_key = ?",
                (api_key,)).fetchone()
            if row is None:
                break
            api_key = row[0]
        if c.execute("SELECT 1 FROM keys WHERE api_key = ?",
                     (api_key,)).fetchone() is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)",
                  (api_key,))
        c.execute(
            """UPDATE wallet
               SET starter_millicents = starter_millicents + ?,
                   funded_millicents = funded_millicents + ?
               WHERE api_key = ?""",
            (starter_back, funded_back, api_key))
        c.commit()
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
    return _wallet_summary(int(row[0]), int(row[1]))


def rotate_key(api_key: str) -> Optional[dict]:
    """Self-service rotation: mint a replacement, carry the wallet, kill the
    old key immediately. Returns the new key record (with `wallet` and
    `replaces`) or None if the key is unknown or already revoked. The old key
    stops working the moment this returns — there is no grace period, because
    the caller proving possession of the key IS the authorization, and a
    compromised key must die at once."""
    if not api_key.startswith(_KEY_PREFIX):
        return None
    now = int(time.time())
    with _conn() as c:
        if c.execute("SELECT 1 FROM revoked_keys WHERE api_key = ?",
                     (api_key,)).fetchone() is not None:
            return None
        row = c.execute(
            """SELECT agent_id, contact_email, intended_use_summary, tier,
                      rate_limit_per_minute, telemetry_consent
               FROM keys WHERE api_key = ?""", (api_key,)).fetchone()
        if row is None:
            return None
        new_key = _KEY_PREFIX + secrets.token_urlsafe(24)
        # balance_usd_cents omitted (DEAD column, DEFAULT 0).
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at,
                                  telemetry_consent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_key, row[0], row[1], row[2], row[3], row[4], now, row[5]))
        # Carry the wallet buckets AND starter_granted_at to the new key, then
        # zero the old row. starter_granted_at must travel so a rotation can
        # never mint a second starter grant; the buckets travel because they
        # are prepaid value. No old wallet row means starter was never granted
        # — nothing to carry, and the new key stays grant-eligible.
        mrow = c.execute(
            """SELECT funded_millicents, starter_millicents, starter_granted_at
               FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
        if mrow is not None:
            funded, starter = int(mrow[0]), int(mrow[1])
            c.execute(
                """INSERT INTO wallet (api_key, funded_millicents,
                                       starter_millicents, starter_granted_at)
                   VALUES (?, ?, ?, ?)""",
                (new_key, funded, starter, mrow[2]))
            c.execute(
                """UPDATE wallet
                   SET funded_millicents = 0, starter_millicents = 0
                   WHERE api_key = ?""", (api_key,))
        else:
            funded, starter = 0, 0
        c.execute("""INSERT INTO revoked_keys (api_key, revoked_at,
                                                replaced_by)
                     VALUES (?, ?, ?)""", (api_key, now, new_key))
        c.commit()
        return {
            "api_key": new_key, "tier": row[3],
            "rate_limit_per_minute": row[4], "created_at": now,
            "wallet": _wallet_summary(starter, funded),
            "telemetry_consent": bool(row[5]), "replaces": api_key,
        }


def admin_rotate_by_identity(*, agent_id: str, contact_email: str
                             ) -> Optional[dict]:
    """FOUNDER-ONLY recovery for 'I lost my key entirely' — NOT exposed
    over HTTP (no email verification infra exists, so ownership proof is
    a human judgment made off-channel). Finds the newest live key whose
    agent_id AND contact_email both match, rotates it, and returns the
    new record for the founder to deliver to the verified owner.

    Run: python3 -c "from gametheory.server.onboarding import \
         admin_rotate_by_identity as r; print(r(agent_id='...', \
         contact_email='...'))"
    """
    with _conn() as c:
        row = c.execute(
            """SELECT k.api_key FROM keys k
               LEFT JOIN revoked_keys r ON r.api_key = k.api_key
               WHERE k.agent_id = ? AND k.contact_email = ?
                 AND r.api_key IS NULL
               ORDER BY k.created_at DESC LIMIT 1""",
            (agent_id, contact_email)).fetchone()
    if row is None:
        return None
    return rotate_key(row[0])
