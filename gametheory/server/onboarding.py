"""
Programmatic API key issuance. Free tier is self-serve and idempotent on
agent_id within 24h. Metered upgrade requires a Stripe pm_* identifier.

Storage: SQLite at the path resolved by gametheory._db (default
~/.gametheory/keys.db). Rate limits are advertised here but enforced
elsewhere (best-effort in-process today; Redis when there's a second pod).
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from gametheory._db import db_conn


_FREE_TIER_RATE = 60        # requests per minute
_METERED_TIER_RATE = 600    # requests per minute
_FREE_PREFIX = "gt_test_"
_METERED_PREFIX = "gt_live_"


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
        stripe_payment_method_id TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_id ON keys(agent_id, created_at)",
)


def _conn():
    return db_conn(_KEYS_SCHEMA)


def issue_key(*, agent_id: str, contact_email: str,
              intended_use_summary: str) -> dict:
    """
    Issue a free-tier API key. Idempotent on agent_id within 24h: returns
    the existing key if one was issued recently.
    """
    if not agent_id or len(agent_id) < 3 or len(agent_id) > 128:
        raise ValueError("agent_id must be 3-128 chars")
    if "@" not in contact_email:
        raise ValueError("contact_email must be an email")
    if not 8 <= len(intended_use_summary) <= 1024:
        raise ValueError("intended_use_summary must be 8-1024 chars")

    now = int(time.time())
    cutoff = now - 86400  # 24h

    with _conn() as c:
        # Idempotency: if this agent has an active key issued <24h ago, return it.
        row = c.execute(
            """SELECT api_key, tier, rate_limit_per_minute, created_at
               FROM keys WHERE agent_id = ? AND created_at >= ?
               ORDER BY created_at DESC LIMIT 1""",
            (agent_id, cutoff),
        ).fetchone()
        if row is not None:
            return {
                "api_key": row[0],
                "tier": row[1],
                "rate_limit_per_minute": row[2],
                "created_at": row[3],
                "reused": True,
            }

        # Issue a new key. 24 bytes of entropy → 32-char base64.
        key = _FREE_PREFIX + secrets.token_urlsafe(24)
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key, agent_id, contact_email, intended_use_summary,
             "free_only", _FREE_TIER_RATE, now),
        )
        c.commit()
        return {
            "api_key": key,
            "tier": "free_only",
            "rate_limit_per_minute": _FREE_TIER_RATE,
            "created_at": now,
            "reused": False,
        }


def lookup_key(api_key: str) -> Optional[dict]:
    """Look up a key. Returns None if not found / not active."""
    if not (api_key.startswith(_FREE_PREFIX) or api_key.startswith(_METERED_PREFIX)):
        return None
    with _conn() as c:
        row = c.execute(
            """SELECT agent_id, tier, rate_limit_per_minute, created_at,
                      stripe_payment_method_id
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
            "stripe_payment_method_id": row[4],
        }


def upgrade_key(*, api_key: str, stripe_payment_method_id: str) -> dict:
    """
    Upgrade a free-tier key to metered (paid endpoints unlocked).

    The Stripe payment-method ID is recorded but not yet confirmed against
    Stripe — that wiring lives behind a separate billing service. Callers
    pass `pm_*`, get a `gt_live_*` key.
    """
    existing = lookup_key(api_key)
    if existing is None:
        raise ValueError(f"unknown api_key {api_key!r}")
    if not stripe_payment_method_id or not stripe_payment_method_id.startswith("pm_"):
        raise ValueError("stripe_payment_method_id must be a Stripe pm_* identifier")

    # Mint a new metered key bound to the same agent_id.
    new_key = _METERED_PREFIX + secrets.token_urlsafe(24)
    now = int(time.time())
    with _conn() as c:
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at,
                                  stripe_payment_method_id)
               SELECT ?, agent_id, contact_email, intended_use_summary,
                      'metered', ?, ?, ?
               FROM keys WHERE api_key = ?""",
            (new_key, _METERED_TIER_RATE, now, stripe_payment_method_id, api_key),
        )
        c.commit()
    return {
        "api_key": new_key,
        "tier": "metered",
        "rate_limit_per_minute": _METERED_TIER_RATE,
        "created_at": now,
        "stripe_payment_method_id": stripe_payment_method_id,
    }
