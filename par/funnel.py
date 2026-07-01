"""PAR funnel — waitlist + event instrumentation (the growth/analytics layer).

In-memory stand-ins for two production tables:

    waitlist(user_id, scenario, contact, ts)
    events(user_id, name, meta, ts)   -- name in: play, share, cta_view, cta_click, waitlist

Every number `funnel()` returns is a `GROUP BY` in SQL; the shapes stay identical when the
dicts are swapped for a database. The point is to *see* the loop (k-factor, conversion),
not guess: which step leaks, and what the game→product conversion actually is.
"""
from __future__ import annotations

from typing import Optional

# the ordered funnel: play the game -> share it -> see the CTA -> tap it -> join the waitlist
STEPS = ["play", "share", "cta_view", "cta_click", "waitlist"]

_waitlist: dict = {}        # user_id -> {"scenario", "contact"}
_events: list = []          # [{"user", "name", "meta"}]  (ts stamped by the DB in prod)


def join_waitlist(user_id: str, scenario: str, contact: Optional[str] = None) -> int:
    _waitlist[user_id] = {"scenario": scenario, "contact": contact}
    return len(_waitlist)


def record_event(user_id: str, name: str, meta: Optional[dict] = None) -> None:
    _events.append({"user": user_id, "name": name, "meta": meta or {}})


def funnel() -> dict:
    """Unique users reaching each step, plus step-over-step conversion — the whole point
    of instrumenting: find the leak and measure game→product conversion."""
    seen = {step: set() for step in STEPS}
    for e in _events:
        if e["name"] in seen:
            seen[e["name"]].add(e["user"])
    counts = {step: len(seen[step]) for step in STEPS}
    rates = {}
    for i in range(1, len(STEPS)):
        prev, cur = STEPS[i - 1], STEPS[i]
        rates[cur + "/" + prev] = round(counts[cur] / counts[prev] * 100, 1) if counts[prev] else 0.0
    return {"waitlist_size": len(_waitlist), "events": len(_events),
            "counts": counts, "conversion_pct": rates}
