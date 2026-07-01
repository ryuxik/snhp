"""PAR scoreboard — the retention + virality layer.

An in-memory stand-in for what production stores in two tables:

    results(day, user_id, pct_of_par, walked, ts)   -- one row per play
    streaks(user_id, current, max, last_day)         -- the daily-habit state

Every aggregation here (percentile, distribution, par-hit count) is a `GROUP BY` in
SQL; the API shape stays identical when the dict is swapped for a database. Scores are
recomputed server-side from the close (never trusted from the client), so the board
can't be gamed by POSTing a fake percentage.
"""
from __future__ import annotations

from collections import defaultdict
import random
from typing import Optional

# day -> {user_id: {"pct": float, "walked": bool}}  (one entry per user per day → idempotent)
_results: "defaultdict[int, dict]" = defaultdict(dict)
# user_id -> {"current": int, "max": int, "last_day": int|None}
_streaks: dict = {}

# pct_of_par buckets for the reveal's "where everyone landed" histogram
_BUCKETS = [(0, 60, "<60"), (60, 70, "60s"), (70, 80, "70s"),
            (80, 90, "80s"), (90, 100, "90s"), (100, None, "par")]


def _bucketize(pcts: list[float], mine: Optional[float] = None) -> list[dict]:
    out = []
    for lo, hi, label in _BUCKETS:
        n = sum(1 for p in pcts if (p >= lo if hi is None else lo <= p < hi))
        here = mine is not None and (mine >= lo if hi is None else lo <= mine < hi)
        out.append({"label": label, "count": n, "you": here})
    return out


def record(day: int, user_id: str, pct: float, walked: bool) -> dict:
    """Record one play (idempotent per (day, user)); advance the streak only on the first
    play of a day. Returns the player's streak plus how they placed against everyone who
    has played today."""
    today = _results[day]
    first_play_today = user_id not in today
    today[user_id] = {"pct": pct, "walked": walked}

    st = _streaks.setdefault(user_id, {"current": 0, "max": 0, "last_day": None})
    if first_play_today:
        st["current"] = st["current"] + 1 if st["last_day"] == day - 1 else 1
        st["last_day"] = day
        st["max"] = max(st["max"], st["current"])

    pcts = [r["pct"] for r in today.values()]
    played = len(pcts)
    beat = sum(1 for p in pcts if p < pct)
    return {
        "streak": st["current"],
        "max_streak": st["max"],
        "played": played,
        "percentile": round(beat / played * 100) if played > 1 else 100,
        "par_hits": sum(1 for p in pcts if p >= 100),
        "distribution": _bucketize(pcts, pct),
    }


def stats(day: int) -> dict:
    """Anonymous day rollup — powers the landing's live social proof (no user needed)."""
    pcts = [r["pct"] for r in _results[day].values()]
    return {
        "played": len(pcts),
        "par_hits": sum(1 for p in pcts if p >= 100),
        "top_pct": max(pcts) if pcts else None,
        "distribution": _bucketize(pcts),
    }


def seed_demo(day: int, n: int = 240) -> None:
    """DEMO ONLY — populate a day with a believable spread so the stats and the reveal
    histogram aren't empty when running offline. Delete once the results table is real."""
    if _results[day]:
        return
    rng = random.Random(1000 + day)
    for i in range(n):
        roll = rng.random()
        # ~6% walk (0%); the rest cluster 68–88% of par; a handful nail par
        pct = 0.0 if roll < 0.06 else min(100.0, round(rng.gauss(78, 11), 1))
        _results[day][f"seed{i}"] = {"pct": pct, "walked": pct == 0.0}
