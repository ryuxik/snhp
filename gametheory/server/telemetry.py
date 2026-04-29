"""
Opt-in telemetry for the SNHP data moat.

V1 design (per privacy-engineering review):

  Crypto:
    - HMAC-SHA-256(pepper, api_key || iso_week) → 128-bit truncated hash.
      Per-WEEK rotation eliminates cross-time linkability while still
      supporting recommendation→outcome joins (capped at the same week).
    - The pepper is a Fly secret; never leaves the box. Without it, hashes
      are not reversible AND not joinable to any external corpus.

  Schema:
    - Quantize all numeric features at ingest to a 0.02 grid (50 buckets
      across [0,1]). Sheds 2+ orders of magnitude of fingerprint entropy
      vs raw float64 while losing <1% of prior-calibration signal.
    - Cap stored list fields at 16 elements (separate from the 128-cap
      on the request — we accept up to 128 for math, store at most 16).
    - Strip free-text `rationale` from recommendations. Keep posteriors
      only when they're already summary stats (verified per-endpoint).
    - Drop `outcome_at_hour` entirely (gives no calibration signal,
      adds re-id risk via deal-announcement matching).

  Consent:
    - Account-level via `keys.telemetry_consent` (set at /v1/keys issuance).
    - Per-call `share_outcome=True` is a downgrade-only refinement —
      ignored if account consent is False.
    - Allowlisted `vertical` enum (no free text — covert-channel risk).

  Failure modes:
    - If `TELEMETRY_PEPPER` isn't set, `share_outcome=True` requests RAISE
      (refuse to silently no-op, which would be a privacy lie).

  Deferred to read-side launch (gold-plating today):
    - Differential privacy at release (epsilon ≈ 1.0 per vertical, k=10 floor)
    - Pepper rotation infrastructure
    - Audit log of delete/export
    - VACUUM after delete (SQLite tombstone reclaim)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Optional

from gametheory._db import db_conn


_PEPPER_ENV_VAR = "TELEMETRY_PEPPER"
_HASH_BYTES = 16
_HOUR_SECONDS = 3600
_QUANTIZE_GRID = 0.02
_MAX_LIST_LEN = 16


_TELEMETRY_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS telemetry_recommendations (
        recommendation_id   TEXT PRIMARY KEY,
        agent_week_hash     TEXT NOT NULL,
        vertical            TEXT NOT NULL,
        endpoint            TEXT NOT NULL,
        request_features    TEXT NOT NULL,
        recommendation      TEXT NOT NULL,
        created_at_hour     INTEGER NOT NULL,
        outcome_reported    INTEGER NOT NULL DEFAULT 0,
        outcome_deal_closed INTEGER,
        outcome_my_utility  REAL,
        outcome_opp_utility REAL
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_telemetry_agent_week_hash
        ON telemetry_recommendations(agent_week_hash)""",
    """CREATE INDEX IF NOT EXISTS idx_telemetry_vertical_endpoint
        ON telemetry_recommendations(vertical, endpoint, created_at_hour)""",
)


def _conn():
    return db_conn(_TELEMETRY_SCHEMA)


# ─── Cryptographic pepper + week-bounded hashing ────────────────────────────


def _pepper() -> bytes:
    val = os.environ.get(_PEPPER_ENV_VAR, "").strip()
    if not val:
        raise RuntimeError(
            f"{_PEPPER_ENV_VAR} not set. Telemetry refuses to operate without "
            f"the pepper (silent no-op would be a privacy lie). Set via "
            f"`fly secrets set {_PEPPER_ENV_VAR}=$(python -c \"import secrets; "
            f"print(secrets.token_urlsafe(32))\")`."
        )
    return val.encode()


def _iso_week(now_seconds: float | None = None) -> str:
    """ISO 8601 year-week tag (e.g. '2026-W18'). Wraps cleanly across
    year boundaries (uses ISO calendar, not Gregorian)."""
    dt = datetime.fromtimestamp(now_seconds if now_seconds is not None
                                  else time.time(), tz=timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def hash_api_key(api_key: str, week: str | None = None) -> str:
    """Per-week non-reversible non-joinable agent identifier.

    `HMAC(pepper, api_key || week)` truncated to 128 bits, base64url. The
    week argument defaults to the current ISO week so two records from
    the same agent in the same week are joinable (recommendation→outcome)
    but records across weeks are NOT joinable, which prevents long-horizon
    behavioral fingerprinting of any single customer.
    """
    week = week or _iso_week()
    msg = (api_key + "||" + week).encode()
    digest = hmac.new(_pepper(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:_HASH_BYTES]).rstrip(b"=").decode()


def _hour_bucket(t: float) -> int:
    return int(t // _HOUR_SECONDS) * _HOUR_SECONDS


# ─── Quantization (anti-fingerprinting) ─────────────────────────────────────


def _quantize(value: Any) -> Any:
    """Recursively quantize floats to a 0.02 grid and cap lists at 16
    elements. Strings, ints, bools, None pass through.

    The cap matters even when callers already cap at request-validation
    time — defense in depth, and it lets us tighten the storage cap below
    the request cap without breaking the API.
    """
    if isinstance(value, float):
        return round(value / _QUANTIZE_GRID) * _QUANTIZE_GRID
    if isinstance(value, list):
        return [_quantize(v) for v in value[:_MAX_LIST_LEN]]
    if isinstance(value, dict):
        return {k: _quantize(v) for k, v in value.items()}
    return value


# Recommendation fields that MUST be stripped before storage. `rationale`
# is a free-text string from the math layer that often embeds raw input
# values verbatim, defeating quantization. The negotiation endpoints'
# `posterior` field already contains only summary stats (verified) so it's
# safe to keep, but quantize the numeric values inside.
_RECOMMENDATION_DROP_FIELDS = {"rationale"}


def _strip_recommendation(rec: dict) -> dict:
    return {k: _quantize(v) for k, v in rec.items()
            if k not in _RECOMMENDATION_DROP_FIELDS}


# ─── Public API ─────────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """Whether telemetry can operate (pepper present). Doesn't reveal the
    pepper itself — only its presence."""
    return bool(os.environ.get(_PEPPER_ENV_VAR, "").strip())


def record_recommendation(
    *,
    api_key: str,
    endpoint: str,
    vertical: str,
    request_features: dict,
    recommendation: dict,
) -> Optional[str]:
    """
    Persist an anonymized recommendation record. Returns the
    `recommendation_id` for outcome reporting later, or None if the
    account didn't grant consent (per-call share_outcome alone is
    insufficient — account-level consent is required).

    Caller is responsible for the per-call `share_outcome=True` check;
    this function additionally enforces the account-level gate via a
    single guarded INSERT — one round-trip, and no TOCTOU window between
    consent check and write.
    """
    agent_week_hash = hash_api_key(api_key)
    rec_id = "rec_" + secrets.token_urlsafe(16)
    now = _hour_bucket(time.time())
    quantized_features = _quantize(request_features)
    stripped_rec = _strip_recommendation(recommendation)
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO telemetry_recommendations
               (recommendation_id, agent_week_hash, vertical, endpoint,
                request_features, recommendation, created_at_hour)
               SELECT ?, ?, ?, ?, ?, ?, ?
               WHERE EXISTS (
                 SELECT 1 FROM keys
                 WHERE api_key = ? AND telemetry_consent = 1
               )""",
            (
                rec_id, agent_week_hash, vertical, endpoint,
                json.dumps(quantized_features, sort_keys=True, separators=(",", ":")),
                json.dumps(stripped_rec, sort_keys=True, separators=(",", ":")),
                now,
                api_key,
            ),
        )
        c.commit()
        return rec_id if cur.rowcount == 1 else None


def report_outcome(
    *,
    api_key: str,
    recommendation_id: str,
    deal_closed: bool,
    my_utility: Optional[float] = None,
    opponent_utility: Optional[float] = None,
) -> bool:
    """
    Attach an outcome to a recommendation. The recommendation MUST have
    been recorded in the same ISO week as this call — agent_week_hash
    only matches within the week, which caps outcome-reporting at ~7 days
    (acceptable: customer's deals close on hours-to-days timescale, not
    weeks).

    Returns True on success; False if the recommendation doesn't exist,
    doesn't belong to this agent (cross-agent forge attempt), is in a
    different week (too late to report), or has already been reported
    (idempotent re-report = no-op).

    Outcome utilities are quantized at write time (same 0.02 grid as
    inputs).
    """
    expected_hash = hash_api_key(api_key)
    with _conn() as c:
        cur = c.execute(
            """UPDATE telemetry_recommendations
               SET outcome_reported    = 1,
                   outcome_deal_closed = ?,
                   outcome_my_utility  = ?,
                   outcome_opp_utility = ?
               WHERE recommendation_id = ?
                 AND agent_week_hash   = ?
                 AND outcome_reported  = 0""",
            (
                1 if deal_closed else 0,
                _quantize(float(my_utility)) if my_utility is not None else None,
                _quantize(float(opponent_utility)) if opponent_utility is not None else None,
                recommendation_id, expected_hash,
            ),
        )
        c.commit()
        return cur.rowcount == 1


_RETENTION_WEEKS = 78  # ≈18 months — privacy-notice retention window


def _retention_week_hashes(api_key: str) -> list[str]:
    """Every week-hash for this key within the retention window. Used by
    GDPR delete + export so the same sweep covers any row this key could
    have written during retention."""
    now = time.time()
    return [hash_api_key(api_key, _iso_week(now - i * 7 * 86400))
            for i in range(_RETENTION_WEEKS)]


def delete_agent_records(api_key: str) -> int:
    """GDPR Article 17. Returns the row count deleted.

    Note: SQLite doesn't zero pages on DELETE; for forensic-grade deletion
    run `VACUUM` (deferred — documented in the privacy notice as
    "deletion within 24h, full storage reclaim within 30 days").
    """
    week_hashes = _retention_week_hashes(api_key)
    placeholders = ",".join("?" for _ in week_hashes)
    with _conn() as c:
        cur = c.execute(
            f"DELETE FROM telemetry_recommendations "
            f"WHERE agent_week_hash IN ({placeholders})",
            tuple(week_hashes),
        )
        c.commit()
        return cur.rowcount


def export_agent_records(api_key: str) -> list[dict]:
    """GDPR Article 15."""
    week_hashes = _retention_week_hashes(api_key)
    placeholders = ",".join("?" for _ in week_hashes)
    with _conn() as c:
        rows = c.execute(
            f"""SELECT recommendation_id, vertical, endpoint, request_features,
                       recommendation, created_at_hour, outcome_reported,
                       outcome_deal_closed, outcome_my_utility, outcome_opp_utility
                FROM telemetry_recommendations
                WHERE agent_week_hash IN ({placeholders})
                ORDER BY created_at_hour""",
            tuple(week_hashes),
        ).fetchall()
    return [
        {
            "recommendation_id": r[0],
            "vertical": r[1],
            "endpoint": r[2],
            "request_features": json.loads(r[3]),
            "recommendation": json.loads(r[4]),
            "created_at_hour": r[5],
            "outcome": (
                {
                    "deal_closed": bool(r[7]) if r[7] is not None else None,
                    "my_utility": r[8],
                    "opponent_utility": r[9],
                } if r[6] else None
            ),
        }
        for r in rows
    ]
