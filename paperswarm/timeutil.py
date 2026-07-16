"""Time helpers. Everything internal is timezone-aware UTC so ledger
timestamps and comp windows compare unambiguously (honesty depends on the
60s bid-cutoff clock being exact — SPEC BUY rule)."""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (trailing 'Z' accepted) to aware UTC."""
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    """Canonical ISO string (UTC, +00:00) for ledger/store persistence."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def epoch(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()
