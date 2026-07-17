"""Deterministic time for recorded episodes (SPEC v33: "recorded episodes ...
replayed from real artifacts").

A recorded sim must replay byte-for-byte, so episodes run on a LOGICAL clock,
not wall-clock: a base timestamp plus a monotonic per-tick step. This keeps the
event log, the ledger, and — critically — the workspace git commit hashes
reproducible (commit hashes depend on the author/committer DATE, which we drive
from this clock; see workspace.py). Wall-clock time is never load-bearing in a
replayed artifact.

Contract ambiguity resolved (documented in SPEC.md): timestamps are logical,
not wall-clock, precisely so a published episode regenerates identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Default episode epoch. Arbitrary but fixed so bare runs are deterministic.
DEFAULT_BASE = datetime(2026, 7, 17, 0, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    """Canonical ISO-8601 UTC string for ledger/event persistence."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (trailing 'Z' accepted) to aware UTC."""
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class Clock:
    """Monotonic logical clock. `tick()` advances one step and returns the new
    ISO timestamp; `peek()` reads without advancing. Resumable: seed `count`
    from the number of events already in the log so a resumed episode continues
    the same timeline (runner.py).
    """

    base: datetime = DEFAULT_BASE
    step_seconds: int = 1
    count: int = 0

    def _at(self, n: int) -> datetime:
        return self.base + timedelta(seconds=self.step_seconds * n)

    def peek(self) -> str:
        return iso(self._at(self.count))

    def tick(self) -> str:
        ts = iso(self._at(self.count))
        self.count += 1
        return ts

    def git_date(self) -> str:
        """Current logical instant formatted for GIT_*_DATE (aware ISO). Used to
        make workspace commit hashes deterministic (workspace.py)."""
        return iso(self._at(self.count))
