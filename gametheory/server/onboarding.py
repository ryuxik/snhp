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

# Rotation chain: follow replaced_by at most this many hops before giving up.
# A credit that would land past the cap (or on a still-revoked/cyclic chain)
# is REFUSED, never dropped onto a dead key (money must never land on a
# revoked key — see resolve_live_key). A 16-hop cap tolerates any realistic
# rotation history while bounding a malformed/cyclic chain.
_CHAIN_MAX_HOPS = 16

# wallet_debit settles with an optimistic compare-and-swap (read → compute →
# guarded write; retry if the row moved under us). This bounds the retry loop.
# It is effectively unbounded for real traffic: a miss only happens when a
# concurrent debit/credit committed between our read and our write, and writes
# to one wallet serialize, so N contenders resolve in ~N passes. Exhausting it
# means pathological sustained contention on a single key — an operational
# fault (RuntimeError), never a normal business outcome.
_DEBIT_CAS_ATTEMPTS = 10_000


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
    # Per-purchase credit dedupe for settlement webhooks / SPT redeems. The
    # PRIMARY KEY is the STABLE per-purchase id (a Stripe checkout *session* id
    # or PaymentIntent id) — NOT the event id — so a dashboard "Resend" (new
    # event id) or a completed + async_payment_succeeded pair credits the
    # purchase exactly once. It lives in the SAME schema as `wallet` on purpose:
    # wallet_credit_idempotent writes this row AND the wallet delta in ONE
    # transaction on ONE connection, so the credit and its "already applied"
    # marker are atomic (a crash before commit moves nothing; after commit every
    # retry is a no-op). CREATE ... IF NOT EXISTS, so it self-creates on an
    # existing DB — no manual migration (a new TABLE, not a new column).
    """
    CREATE TABLE IF NOT EXISTS wallet_credits (
        dedup_key TEXT PRIMARY KEY,
        api_key TEXT NOT NULL,
        millicents INTEGER NOT NULL,
        bucket TEXT NOT NULL,
        applied_at INTEGER NOT NULL
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


def _resolve_live_key(c, api_key: str) -> Optional[str]:
    """Walk the replaced_by rotation chain from `api_key` to the LIVE
    descendant, using an already-open connection `c`. "Live" == present in
    `keys` AND absent from `revoked_keys`. Returns that key, or None if the
    chain dead-ends (a hop with no `keys` row), cycles, or exceeds
    _CHAIN_MAX_HOPS while still on a revoked key, or `api_key` is unknown.

    Money must NEVER land on a revoked key: a revoked key keeps its `keys` row
    (revocation lives in `revoked_keys`), so an existence check on `keys` alone
    would happily credit a dead key at the end of an exhausted walk. This
    resolves to the live descendant instead, or refuses.
    """
    seen: set[str] = set()
    cur = api_key
    for _ in range(_CHAIN_MAX_HOPS + 1):
        if cur in seen:                       # cycle → refuse
            return None
        seen.add(cur)
        rev = c.execute(
            "SELECT replaced_by FROM revoked_keys WHERE api_key = ?",
            (cur,)).fetchone()
        if rev is None:
            # `cur` is not revoked; it is live iff it exists in `keys`.
            exists = c.execute(
                "SELECT 1 FROM keys WHERE api_key = ?", (cur,)).fetchone()
            return cur if exists is not None else None
        cur = rev[0]
    # Walked _CHAIN_MAX_HOPS revoked keys and never reached a live one.
    return None


def resolve_live_key(api_key: str) -> Optional[str]:
    """Public: follow the replaced_by rotation chain to the LIVE descendant
    (present in `keys`, absent from `revoked_keys`), or None if the chain is
    dead/cyclic/over-long or the key is unknown. In-flight money (wallet
    credit/refund) and callers holding a possibly-rotated key route through
    this so a credit can never land on a revoked key."""
    with _conn() as c:
        return _resolve_live_key(c, api_key)


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
        c.commit()
        # Optimistic compare-and-swap. The old code did SELECT → compute in
        # Python → absolute-value UPDATE, so two concurrent debits (or a debit
        # racing a credit) both read the same balance and the second's absolute
        # write clobbered the first — a lost update that silently discarded a
        # settled charge. Here the UPDATE is GUARDED on the exact values we
        # read (WHERE ... starter=? AND funded=?): the DB applies it atomically
        # and only if the row still holds our pre-image. A racing writer moves
        # the row, the guard matches zero rows, and we re-read and retry. This
        # is portable (no MAX/GREATEST, no backend-specific SELECT ... FOR
        # UPDATE / BEGIN IMMEDIATE) and keeps the returned split EXACT: the
        # split we return is the one whose pre-image the winning UPDATE guarded
        # on, so a bucket-accurate refund can never reverse cents this debit
        # did not actually take.
        for _ in range(_DEBIT_CAS_ATTEMPTS):
            row = c.execute(
                """SELECT starter_millicents, funded_millicents
                   FROM wallet WHERE api_key = ?""", (api_key,)).fetchone()
            starter = int(row[0])
            funded = int(row[1])

            need = int(millicents)
            starter_spent = min(need, starter)   # starter bucket drains first
            need -= starter_spent
            funded_spent = min(need, funded)      # funded covers the remainder
            need -= funded_spent
            shortfall = need                      # > 0 only on a settlement race

            starter_new = starter - starter_spent
            funded_new = funded - funded_spent
            cur = c.execute(
                """UPDATE wallet
                   SET starter_millicents = ?, funded_millicents = ?
                   WHERE api_key = ?
                     AND starter_millicents = ?
                     AND funded_millicents = ?""",
                (starter_new, funded_new, api_key, starter, funded))
            matched = cur.rowcount == 1
            c.commit()
            if matched:
                return {
                    "starter_spent": starter_spent,
                    "funded_spent": funded_spent,
                    "shortfall_millicents": shortfall,
                    "balance_after": _wallet_summary(starter_new, funded_new),
                }
            # Lost the CAS: a concurrent write moved the buckets between our
            # read and our guarded write. Re-read and retry.
    raise RuntimeError(
        f"wallet_debit could not settle {api_key!r} after "
        f"{_DEBIT_CAS_ATTEMPTS} attempts under sustained concurrent contention")


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
        # Follow the rotation chain to the LIVE descendant. None means the chain
        # is dead/cyclic/over-long or the key is unknown — refuse rather than
        # drop money on a revoked key (the old bounded walk credited whatever
        # key it landed on, including a still-revoked one at the hop cap).
        live = _resolve_live_key(c, api_key)
        if live is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)", (live,))
        c.execute(
            f"UPDATE wallet SET {col} = {col} + ? WHERE api_key = ?",
            (millicents, live))
        c.commit()
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (live,)).fetchone()
    return int(row[0]) + int(row[1])


def _apply_wallet_delta(c, col: str, millicents: int, api_key: str) -> None:
    """Add `millicents` to bucket column `col` for `api_key` on the open
    connection `c` (no commit here — the caller commits). Factored out as the
    single wallet-mutation point so wallet_credit_idempotent can bind it into
    the same transaction as its dedupe-row claim (and so that mutation can be
    fault-injected in a test to prove the claim rolls back with it)."""
    c.execute(f"UPDATE wallet SET {col} = {col} + ? WHERE api_key = ?",
              (int(millicents), api_key))


def wallet_credit_idempotent(api_key: str, millicents: int, *,
                             dedup_key: str, bucket: str = "funded") -> dict:
    """Crash-safe, replay-safe wallet credit — the settlement path for Stripe
    webhooks and SPT redeems. Credits `millicents` to `bucket` EXACTLY ONCE per
    `dedup_key`.

    `dedup_key` is the STABLE per-purchase id (a Stripe checkout *session* id or
    a PaymentIntent id), NOT the Stripe event id, so a dashboard "Resend" (new
    event id) or a completed + async_payment_succeeded pair for one purchase
    credits the wallet once, not once per event.

    Atomicity: the dedupe-row INSERT and the wallet UPDATE run on ONE connection
    and commit together, so the credit and its "already applied" marker are
    inseparable. A crash before the commit leaves NOTHING (Stripe's at-least-once
    retry re-credits cleanly); after the commit the dedupe row makes every retry
    a no-op. This replaces the old claim-event → credit → release-on-failure
    dance, whose two separate transactions stranded a paid-but-uncredited event
    permanently if the process died in the window between them.

    Follows the replaced_by rotation chain to the live descendant like
    wallet_credit; raises ValueError if the key resolves to no live key.
    Returns {total_millicents, duplicate}. Public function names other modules
    import are unchanged; this is additive.
    """
    if millicents <= 0:
        raise ValueError("millicents must be positive")
    if bucket not in ("funded", "starter"):
        raise ValueError(f"unknown bucket {bucket!r}")
    if not dedup_key:
        raise ValueError("dedup_key is required")
    col = "funded_millicents" if bucket == "funded" else "starter_millicents"
    now = int(time.time())
    with _conn() as c:
        live = _resolve_live_key(c, api_key)
        if live is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        # Claim the dedupe key IN THE SAME TRANSACTION as the wallet mutation.
        # INSERT OR IGNORE is the atomic sync point: two concurrent deliveries
        # of the same purchase race here and exactly one wins the insert.
        cur = c.execute(
            """INSERT OR IGNORE INTO wallet_credits
               (dedup_key, api_key, millicents, bucket, applied_at)
               VALUES (?, ?, ?, ?, ?)""",
            (dedup_key, live, int(millicents), bucket, now))
        if cur.rowcount == 0:
            # Already applied (a committed prior credit) — idempotent no-op.
            row = c.execute(
                """SELECT starter_millicents, funded_millicents
                   FROM wallet WHERE api_key = ?""", (live,)).fetchone()
            total = (int(row[0]) + int(row[1])) if row else 0
            c.commit()
            return {"total_millicents": total, "duplicate": True}
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)", (live,))
        _apply_wallet_delta(c, col, millicents, live)
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (live,)).fetchone()
        # ONE commit finalizes the dedupe claim AND the credit together.
        c.commit()
        return {"total_millicents": int(row[0]) + int(row[1]),
                "duplicate": False}


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
        # Follow the rotation chain to the LIVE descendant (never refund onto a
        # revoked key — same rule as wallet_credit). None → refuse.
        live = _resolve_live_key(c, api_key)
        if live is None:
            raise ValueError(f"unknown api_key {api_key!r}")
        c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)", (live,))
        c.execute(
            """UPDATE wallet
               SET starter_millicents = starter_millicents + ?,
                   funded_millicents = funded_millicents + ?
               WHERE api_key = ?""",
            (starter_back, funded_back, live))
        c.commit()
        row = c.execute(
            """SELECT starter_millicents, funded_millicents
               FROM wallet WHERE api_key = ?""", (live,)).fetchone()
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


def migrate_cent_balances() -> dict:
    """ONE-TIME, IDEMPOTENT backfill of the retired `keys.balance_usd_cents`
    column into the wallet's funded bucket. The cent column was deprecated when
    the `wallet` table became the single money source, but any pre-change key
    still carrying a nonzero cent balance would otherwise have that money
    stranded. This moves it: for every key with balance_usd_cents > 0, credit
    funded_millicents += balance_usd_cents * MILLICENTS_PER_CENT and zero the
    cent column.

    NOT auto-run at import — invoke once at the deploy step:
        python3 -c "from gametheory.server.onboarding import \
             migrate_cent_balances as m; print(m())"

    Safe to run repeatedly: the zero-cents UPDATE is GUARDED on the exact cent
    value and shares ONE transaction with the wallet credit, so (a) a second run
    finds nothing to move, (b) two concurrent runs each move a balance once (the
    guard makes the loser's update match zero rows), and (c) a crash before the
    per-key commit moves nothing (rerun-safe — no half-migrated money).

    NOTE (ops): in prod the only nonzero balance is the founder's own test key
    `nextmove-prod-verify` (test-mode $10), so this is correctness hygiene, not
    a real-money-critical migration — but ship it so no balance is ever
    stranded. Returns {migrated, millicents_moved, entries}.
    """
    migrated: list[dict] = []
    with _conn() as c:
        rows = c.execute(
            "SELECT api_key, balance_usd_cents FROM keys "
            "WHERE balance_usd_cents > 0").fetchall()
        for api_key, cents in rows:
            cents = int(cents)
            if cents <= 0:                    # defensive; the WHERE already filters
                continue
            c.execute("INSERT OR IGNORE INTO wallet (api_key) VALUES (?)",
                      (api_key,))
            # Zero the cent column FIRST, guarded on its exact value: only the
            # run that flips it non-zero → 0 proceeds to credit. Both statements
            # commit together, so the move is all-or-nothing per key.
            cur = c.execute(
                """UPDATE keys SET balance_usd_cents = 0
                   WHERE api_key = ? AND balance_usd_cents = ?""",
                (api_key, cents))
            if cur.rowcount == 1:
                c.execute(
                    """UPDATE wallet
                       SET funded_millicents = funded_millicents + ?
                       WHERE api_key = ?""",
                    (cents * MILLICENTS_PER_CENT, api_key))
                migrated.append({
                    "api_key": api_key, "cents": cents,
                    "millicents": cents * MILLICENTS_PER_CENT})
            c.commit()
    return {
        "migrated": len(migrated),
        "millicents_moved": sum(m["millicents"] for m in migrated),
        "entries": migrated,
    }
