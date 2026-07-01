"""PAR funnel — waitlist + event instrumentation, on durable storage.

Backed by par/_store.py (SQLite locally, Postgres in prod). The event log is a table now, not
an in-memory list — so it survives restarts and doesn't grow unbounded in RAM. `funnel()` is
a `SELECT name, COUNT(DISTINCT user_id) ... GROUP BY name`; the shape is unchanged.
"""
from __future__ import annotations

import json
from typing import Optional

from par._store import conn

# the ordered funnel: play -> share -> see the CTA -> tap it -> join the waitlist
STEPS = ["play", "share", "cta_view", "cta_click", "waitlist"]


def join_waitlist(user_id: str, scenario: str, contact: Optional[str] = None) -> int:
    with conn() as c:
        c.execute("INSERT INTO waitlist (user_id, scenario, contact) VALUES (?,?,?) "
                  "ON CONFLICT (user_id) DO UPDATE SET scenario=excluded.scenario, "
                  "contact=excluded.contact", (user_id, scenario, contact))
        n = c.execute("SELECT count(*) FROM waitlist").fetchone()[0]
        c.commit()
    return n


def record_event(user_id: str, name: str, meta: Optional[dict] = None) -> None:
    with conn() as c:
        c.execute("INSERT INTO events (user_id, name, meta) VALUES (?,?,?)",
                  (user_id, name, json.dumps(meta or {})))
        c.commit()


def funnel() -> dict:
    """Unique users reaching each step + step-over-step conversion — find the leak, measure
    game->product conversion."""
    with conn() as c:
        rows = c.execute("SELECT name, COUNT(DISTINCT user_id) FROM events GROUP BY name").fetchall()
        total_events = c.execute("SELECT count(*) FROM events").fetchone()[0]
        waitlist_size = c.execute("SELECT count(*) FROM waitlist").fetchone()[0]
    by_step = {name: n for name, n in rows}
    counts = {step: by_step.get(step, 0) for step in STEPS}
    rates = {}
    for i in range(1, len(STEPS)):
        prev, cur = STEPS[i - 1], STEPS[i]
        rates[cur + "/" + prev] = round(counts[cur] / counts[prev] * 100, 1) if counts[prev] else 0.0
    return {"waitlist_size": waitlist_size, "events": total_events,
            "counts": counts, "conversion_pct": rates}
