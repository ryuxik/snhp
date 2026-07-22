"""NEXTMOVE paid sessions — $2 per NEGOTIATION, not per move.

The buyer's unit is "win this negotiation", so that's the priced unit:
opening a session charges once and covers every move until the negotiation
closes (cap SESSION_MAX_MOVES, TTL SESSION_TTL_S — resale negotiations
span days). Compute is ~100ms/move, so the cap is abuse-bounding, not
margin protection.

Sessions are DB-backed (same backend as keys/billing: SQLite dev,
Postgres prod), so a deploy mid-negotiation never eats a paid session.

The session fixes the negotiation's identity (category, side, bounds,
seed); the caller supplies the offer history on each move. Advice stays
stateless and deterministic — the session is a payment + identity wrapper,
not hidden state, so every move remains independently auditable via its
context_hash.

Every open/move and the session summary emit an Ed25519-SIGNED receipt (the
notary we already ship, via vend.receipt_signing) — GAUNTLET #4: the anchor
$2 charge used to return NO checkable receipt. Move receipts carry the truthful
compute-provenance (engine_path/rollouts): the paid product refines COUNTER
prices by Monte-Carlo; accept/walk recommendations are closed-form (the MC
layer short-circuits on those, spending 0 rollouts), so ~100ms/move is a
counter-move figure, not a per-move guarantee. The receipt says which ran.
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from core.notary import canon_hash
from gametheory._db import db_conn
from vend.advice import (
    POLICY_ID, Advice, CATEGORIES, advise, advise_bundle, sign_advice_receipt)
from vend.receipt_signing import safe_sign

SESSION_PRICE_CENTS = 200        # $2 per negotiation, all moves included
SESSION_MAX_MOVES = 10
SESSION_TTL_S = 7 * 86400        # resale back-and-forth spans days

_SESS_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS advice_sessions (
        session_id TEXT PRIMARY KEY,
        api_key TEXT NOT NULL,
        category TEXT NOT NULL,
        side TEXT NOT NULL,
        walk_away REAL NOT NULL,
        target REAL NOT NULL,
        seed INTEGER NOT NULL,
        moves_used INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        closed INTEGER NOT NULL DEFAULT 0,
        move_hashes TEXT NOT NULL DEFAULT '[]'
    )
    """,
)


def _conn():
    return db_conn(_SESS_SCHEMA)


class SessionError(ValueError):
    """Unknown/expired/exhausted session or key mismatch — HTTP 4xx."""


def _authorized(session_key: str, caller_key: str) -> bool:
    """Authorize a session call under key ROTATION.

    A raw `session_key == caller_key` compare orphans a paid session the moment
    its key rotates: the rotated-TO (new, live) key could not drive its own paid
    session, while the OLD (now-revoked) key still could — the exact inversion of
    rotate_key's guarantees ("balance carries" + "old key dies at once").

    Fix: resolve the session's stored key to its LIVE rotation descendant and
    require the caller to be presenting exactly that key. onboarding.resolve_live_key
    walks the replaced_by chain to the one key that is present in `keys` AND absent
    from `revoked_keys` (or None on a dead/cyclic/over-long/unknown chain), so:
      - no rotation: resolve_live_key(K) == K, caller must present K.
      - after rotation: the old stored key resolves FORWARD to the new key, so
        the new key drives the session and the old (revoked) key — which no longer
        equals that forward descendant — is rejected at once.
    Because resolve_live_key only ever returns a live, non-revoked key, requiring
    caller_key == that descendant also proves the caller's key is itself live
    (equivalent to `resolve_live_key(caller_key) == resolve_live_key(session_key)`
    AND caller_key live, but with one lookup). A dead chain (None) fails closed."""
    from gametheory.server import onboarding
    live = onboarding.resolve_live_key(session_key)
    return live is not None and live == caller_key


def _append_move_hash(session_id: str, context_hash: str) -> None:
    """Append one move's context_hash to the session's move-hash log. The close
    summary hands these to a principal as the per-move replay anchors; they are
    recorded here rather than recomputed at close because the per-move inputs
    (offer history) are the caller's, not stored. Append-only; the move guard
    upstream serializes moves, so no two writers race a given index."""
    with _conn() as c:
        row = c.execute(
            "SELECT move_hashes FROM advice_sessions WHERE session_id = ?",
            (session_id,)).fetchone()
        if row is None:
            return
        hashes = json.loads(row[0] or "[]")
        hashes.append(context_hash)
        c.execute(
            "UPDATE advice_sessions SET move_hashes = ? WHERE session_id = ?",
            (json.dumps(hashes), session_id))
        c.commit()


def _finalize_move(a: Advice, session_id: str, move_index: int, *,
                   kind: str) -> Advice:
    """Record the move's context_hash and attach a signed move receipt to the
    Advice. Moves are free (the $2 rode the open), so the receipt carries
    price_millicents=0 honestly; its `compute` block is the truthful engine_path
    (mc for a refined counter, closed_form for accept/walk/hold)."""
    _append_move_hash(session_id, a.context_hash)
    receipt = sign_advice_receipt(a, kind=kind, session_id=session_id,
                                  move_index=move_index)
    return replace(a, receipt=receipt)


def open_session_charged(*, api_key: str, category: str, side: str,
                         walk_away: float, target: float,
                         seed: int = 0) -> dict:
    """Charge $2 once; return the session covering the whole negotiation.

    Order: validate -> charge -> insert; insert failure refunds before
    re-raising (same never-silently-charged rule as everywhere else)."""
    if category not in CATEGORIES:
        raise KeyError(f"unknown category {category!r}; "
                       f"valid: {sorted(CATEGORIES)}")
    if side not in ("buy", "sell"):
        raise KeyError(f"side must be 'buy' or 'sell', got {side!r}")
    # Validate the negotiation bounds with the ENGINE's OWN validator BEFORE any
    # charge: an unusable session (target below/above walk_away for the side, a
    # non-positive bound) must be refused uncharged, not sold then 500'd when the
    # first move finally runs the engine. rounds_left is a per-move input, so it
    # is checked at move time, not here. Reused, not reinvented — one source of
    # truth (plain_terms.validate_terms), raising NegotiationInputError → 4xx.
    from gametheory.negotiation.plain_terms import validate_terms
    validate_terms(side=side, walk_away=float(walk_away), target=float(target))
    from gametheory.server import billing, onboarding
    # Charge the ONE wallet (starter bucket applies to the anchor too). The
    # returned split lets an insert failure refund the EXACT buckets it spent.
    split = billing.charge_or_raise(api_key, SESSION_PRICE_CENTS)
    funding = {"starter_millicents": split["starter_spent"],
               "funded_millicents": split["funded_spent"]}
    try:
        sid = "ns_" + secrets.token_urlsafe(18)
        now = int(time.time())
        with _conn() as c:
            c.execute(
                """INSERT INTO advice_sessions
                   (session_id, api_key, category, side, walk_away, target,
                    seed, moves_used, created_at, closed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 0)""",
                (sid, api_key, category, side, float(walk_away),
                 float(target), int(seed), now))
            c.commit()
    except Exception:
        onboarding.wallet_refund(api_key, funding)
        raise
    price_millicents = SESSION_PRICE_CENTS * onboarding.MILLICENTS_PER_CENT
    # Signed OPEN receipt (GAUNTLET #4): the $2 anchor charge now hands back a
    # third-party-checkable receipt — price, the funding split, the post-charge
    # balance, and a context_hash binding the session's economic identity (the
    # only thing a price may depend on), all inside the Ed25519 signature.
    context_hash = canon_hash({
        "policy_id": POLICY_ID, "category": category, "side": side,
        "walk_away": float(walk_away), "target": float(target),
        "seed": int(seed)})
    receipt = safe_sign({
        "kind": "nextmove.session_open",
        "policy_id": POLICY_ID,
        "session_id": sid,
        "category": category,
        "side": side,
        "price_millicents": price_millicents,
        "funding": funding,
        "balance_after": split["balance_after"],
        "context_hash": context_hash,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return {"session_id": sid, "category": category, "side": side,
            "price_cents": SESSION_PRICE_CENTS,
            "price_millicents": price_millicents,
            "max_moves": SESSION_MAX_MOVES,
            "expires_at": now + SESSION_TTL_S,
            "funding": funding, "balance_after": split["balance_after"],
            "context_hash": context_hash, "receipt": receipt}


def session_advise(*, session_id: str, api_key: str,
                   their_offers: list[float],
                   my_offers: Optional[list[float]] = None,
                   rounds_left: Optional[int] = None) -> tuple[Advice, int]:
    """One move inside a paid session. No additional charge. Returns
    (advice, move_index). Raises SessionError on unknown session, key
    mismatch, expiry, exhaustion, or closed session."""
    now = int(time.time())
    with _conn() as c:
        row = c.execute(
            """SELECT api_key, category, side, walk_away, target, seed,
                      moves_used, created_at, closed
               FROM advice_sessions WHERE session_id = ?""",
            (session_id,)).fetchone()
        if row is None or not _authorized(row[0], api_key):
            # key mismatch reported identically to unknown: a session id
            # must not be probeable with someone else's key. _authorized
            # follows key rotation (rotated-to key OK, revoked old key not).
            raise SessionError("unknown session (or key mismatch)")
        _, category, side, walk_away, target, seed, used, created, closed = row
        if closed:
            raise SessionError("session closed")
        if now > created + SESSION_TTL_S:
            raise SessionError("session expired")
        # Enforce the cap BEFORE running the engine so an over-cap call is
        # rejected without consuming a move (and without paying — moves are free).
        if used >= SESSION_MAX_MOVES:
            raise SessionError(
                f"move cap reached ({SESSION_MAX_MOVES}); open a new session")
    # Run the engine FIRST: a failed move (NegotiationInputError/AdviceInvariant
    # Error) must NOT burn a paid move. Only after advise() succeeds do we claim
    # the move index via the guarded compare-and-swap below. Two racing callers
    # may both compute here, but the CAS lets exactly one commit the increment;
    # the loser sees rowcount 0 and retries (no move consumed on either the
    # engine failure or the lost race).
    a = advise(category=category, side=side, walk_away=walk_away,
               target=target, their_offers=their_offers,
               my_offers=my_offers, rounds_left=rounds_left, seed=seed)
    with _conn() as c:
        cur = c.execute(
            """UPDATE advice_sessions SET moves_used = moves_used + 1
               WHERE session_id = ? AND moves_used = ? AND closed = 0""",
            (session_id, used))
        if cur.rowcount != 1:      # concurrent move raced us; caller retries
            raise SessionError("concurrent move in flight; retry")
        c.commit()
    return _finalize_move(a, session_id, used + 1, kind="nextmove.move"), used + 1


def close_session(*, session_id: str, api_key: str) -> bool:
    """Mark a negotiation finished (accept/walk happened). Optional —
    sessions also die by TTL/cap — but closing is good hygiene and good
    telemetry (it timestamps the negotiation's end)."""
    with _conn() as c:
        row = c.execute(
            "SELECT api_key FROM advice_sessions WHERE session_id = ?",
            (session_id,)).fetchone()
        # Rotation-aware auth (matches session_advise): the rotated-to key can
        # close its carried session, the revoked old key cannot. Unknown/mismatch
        # both return False, indistinguishably — a session id can't be probed.
        if row is None or not _authorized(row[0], api_key):
            return False
        cur = c.execute(
            """UPDATE advice_sessions SET closed = 1
               WHERE session_id = ? AND closed = 0""",
            (session_id,))
        c.commit()
        return cur.rowcount == 1


def session_summary_receipt(*, session_id: str, api_key: str) -> dict:
    """A signed session-summary receipt the customer hands their principal
    (GAUNTLET #4: "the customer asked to hand something auditable"). Reports the
    moves count, the total actually charged (one $2 open, moves free), and the
    per-move context_hashes — each of which replays exactly one move. Read-only
    and Ed25519-signed; call after close_session (or any time). Raises
    SessionError on an unknown session or a key mismatch (indistinguishable, so
    a session id can't be probed with someone else's key)."""
    from gametheory.server import onboarding
    with _conn() as c:
        row = c.execute(
            """SELECT api_key, category, side, moves_used, created_at, closed,
                      move_hashes FROM advice_sessions WHERE session_id = ?""",
            (session_id,)).fetchone()
    # Rotation-aware auth (matches session_advise): rotated-to key OK, revoked
    # old key rejected; unknown/mismatch indistinguishable so a session id can't
    # be probed with someone else's key.
    if row is None or not _authorized(row[0], api_key):
        raise SessionError("unknown session (or key mismatch)")
    _, category, side, used, created, closed, move_hashes = row
    hashes = json.loads(move_hashes or "[]")
    summary = {
        "kind": "nextmove.session_summary",
        "policy_id": POLICY_ID,
        "session_id": session_id,
        "category": category,
        "side": side,
        "moves": int(used),
        "total_charged_millicents": (
            SESSION_PRICE_CENTS * onboarding.MILLICENTS_PER_CENT),
        "move_context_hashes": hashes,
        "closed": bool(closed),
        "opened_at": int(created),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return safe_sign(summary)


def session_advise_bundle(*, session_id: str, api_key: str,
                          issues: list[dict],
                          their_offers: Optional[list[dict]] = None,
                          my_priorities: Optional[dict] = None,
                          my_batna: float = 0.40,
                          their_batna_estimate: float = 0.40,
                          cooperation: Optional[float] = None
                          ) -> tuple[Advice, int]:
    """A MULTI-ISSUE move inside a paid session — the logrolling tier.
    Same gating and move accounting as session_advise; the session's
    category and seed apply. No additional charge."""
    now = int(time.time())
    with _conn() as c:
        row = c.execute(
            """SELECT api_key, category, seed, moves_used, created_at, closed
               FROM advice_sessions WHERE session_id = ?""",
            (session_id,)).fetchone()
        if row is None or not _authorized(row[0], api_key):
            # rotation-aware auth: rotated-to key drives it, revoked old key not.
            raise SessionError("unknown session (or key mismatch)")
        _, category, seed, used, created, closed = row
        if closed:
            raise SessionError("session closed")
        if now > created + SESSION_TTL_S:
            raise SessionError("session expired")
        # Cap enforced BEFORE the engine runs — over-cap is rejected uncharged.
        if used >= SESSION_MAX_MOVES:
            raise SessionError(
                f"move cap reached ({SESSION_MAX_MOVES}); open a new session")
    # Engine FIRST, increment only on success (see session_advise): a failed
    # bundle move must not burn a paid move; the CAS below claims the index.
    a = advise_bundle(category=category, issues=issues,
                      their_offers=their_offers, my_priorities=my_priorities,
                      my_batna=my_batna,
                      their_batna_estimate=their_batna_estimate,
                      cooperation=cooperation, seed=seed)
    with _conn() as c:
        cur = c.execute(
            """UPDATE advice_sessions SET moves_used = moves_used + 1
               WHERE session_id = ? AND moves_used = ? AND closed = 0""",
            (session_id, used))
        if cur.rowcount != 1:
            raise SessionError("concurrent move in flight; retry")
        c.commit()
    return _finalize_move(a, session_id, used + 1,
                          kind="nextmove.bundle_move"), used + 1
