"""
Programmatic API key issuance + credit balance.

Self-serve key issuance, idempotent on agent_id within 24h. Math endpoints
are free; LLM-cost endpoints (currently `draft_message`) deduct from a
balance that's topped up via Stripe Checkout (see gametheory.server.billing).

Schema:
  keys
    api_key                 TEXT  PRIMARY KEY
    agent_id                TEXT  NOT NULL
    contact_email           TEXT  NOT NULL
    intended_use_summary    TEXT  NOT NULL
    tier                    TEXT  NOT NULL    -- always "standard" now
    rate_limit_per_minute   BIGINT NOT NULL
    created_at              BIGINT NOT NULL   -- unix seconds
    balance_usd_cents       BIGINT NOT NULL DEFAULT 0   -- credit balance

Storage: SQLite (default ~/.gametheory/keys.db) or Postgres if DATABASE_URL.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from gametheory._db import db_conn


_RATE_LIMIT_PER_MIN = 600     # uniform now; the free/metered split is gone
_KEY_PREFIX = "gt_"


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
        balance_usd_cents INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_id ON keys(agent_id, created_at)",
)
# NOTE: this schema is `IF NOT EXISTS`-only. Adding a column to an existing
# DB requires a manual `ALTER TABLE keys ADD COLUMN ... DEFAULT ...` migration
# (run before deploying the code that reads the column). The Stripe billing
# rollout added `balance_usd_cents`; production DBs created before that need:
#   ALTER TABLE keys ADD COLUMN balance_usd_cents BIGINT NOT NULL DEFAULT 0;


def _conn():
    return db_conn(_KEYS_SCHEMA)


def issue_key(*, agent_id: str, contact_email: str,
              intended_use_summary: str) -> dict:
    """
    Issue a new API key, idempotent on agent_id within 24h.
    Math endpoints are immediately callable; LLM endpoints require credits.
    """
    if not agent_id or len(agent_id) < 3 or len(agent_id) > 128:
        raise ValueError("agent_id must be 3-128 chars")
    if "@" not in contact_email:
        raise ValueError("contact_email must be an email")
    if not 8 <= len(intended_use_summary) <= 1024:
        raise ValueError("intended_use_summary must be 8-1024 chars")

    now = int(time.time())
    cutoff = now - 86400

    with _conn() as c:
        row = c.execute(
            """SELECT api_key, tier, rate_limit_per_minute, created_at,
                      balance_usd_cents
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
                "balance_usd_cents": row[4],
                "reused": True,
            }

        key = _KEY_PREFIX + secrets.token_urlsafe(24)
        c.execute(
            """INSERT INTO keys (api_key, agent_id, contact_email,
                                  intended_use_summary, tier,
                                  rate_limit_per_minute, created_at,
                                  balance_usd_cents)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, agent_id, contact_email, intended_use_summary,
             "standard", _RATE_LIMIT_PER_MIN, now, 0),
        )
        c.commit()
        return {
            "api_key": key,
            "tier": "standard",
            "rate_limit_per_minute": _RATE_LIMIT_PER_MIN,
            "created_at": now,
            "balance_usd_cents": 0,
            "reused": False,
        }


def lookup_key(api_key: str) -> Optional[dict]:
    """Look up a key. Returns None if not found."""
    if not api_key.startswith(_KEY_PREFIX):
        return None
    with _conn() as c:
        row = c.execute(
            """SELECT agent_id, tier, rate_limit_per_minute, created_at,
                      balance_usd_cents
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
            "balance_usd_cents": row[4],
        }


def credit_balance(*, api_key: str, cents: int) -> int:
    """
    Add `cents` to the key's balance. Idempotency is the caller's job
    (Stripe webhook does this via processed-events dedupe). Returns the
    new balance.
    """
    if cents <= 0:
        raise ValueError("cents must be positive")
    with _conn() as c:
        c.execute(
            "UPDATE keys SET balance_usd_cents = balance_usd_cents + ? WHERE api_key = ?",
            (cents, api_key),
        )
        c.commit()
        row = c.execute(
            "SELECT balance_usd_cents FROM keys WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        return int(row[0])


def deduct_balance(*, api_key: str, cents: int) -> bool:
    """
    Atomically deduct `cents` from the key's balance, but only if it
    has enough. Returns True on success, False if insufficient balance
    (or unknown key). Single-statement guarded UPDATE — atomic on both
    SQLite and Postgres.
    """
    if cents <= 0:
        raise ValueError("cents must be positive")
    with _conn() as c:
        cur = c.execute(
            """UPDATE keys
               SET balance_usd_cents = balance_usd_cents - ?
               WHERE api_key = ? AND balance_usd_cents >= ?""",
            (cents, api_key, cents),
        )
        # Both sqlite3.Cursor and psycopg2 cursor expose .rowcount; it
        # reflects the number of rows the UPDATE actually changed (0 if
        # the guard predicate failed or the key doesn't exist).
        affected = cur.rowcount
        c.commit()
        return affected == 1
