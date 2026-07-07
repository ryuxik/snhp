"""PAR scoreboard — the retention + virality layer, now on durable storage.

Backed by par/_store.py (SQLite locally, Postgres in prod) instead of in-memory dicts, so
streaks, results, and groups survive restarts and scale across instances. Every figure is a
`SELECT ... GROUP BY` over the tables; the endpoint shapes are unchanged. Scores are recorded
server-side from the close (never trusted from the client), so the board can't be gamed.
"""
from __future__ import annotations

import json
import random
from typing import Optional

from par._store import conn

# pct_of_par buckets for the reveal's "where everyone landed" histogram
_BUCKETS = [(0, 60, "<60"), (60, 70, "60s"), (70, 80, "70s"),
            (80, 90, "80s"), (90, 100, "90s"), (100, None, "par")]


def _day_aggregates(c, day: int, mine: Optional[float] = None) -> dict:
    """One aggregate query over today's results — O(1) rows transferred, not O(N). The
    distribution is six SUM(CASE...) columns; percentile is a COUNT below `mine`."""
    cases = ", ".join(
        ("SUM(CASE WHEN pct_of_par >= %d THEN 1 ELSE 0 END)" % lo) if hi is None else
        ("SUM(CASE WHEN pct_of_par >= %d AND pct_of_par < %d THEN 1 ELSE 0 END)" % (lo, hi))
        for lo, hi, _ in _BUCKETS)
    row = c.execute(
        "SELECT COUNT(*), SUM(CASE WHEN pct_of_par >= 100 THEN 1 ELSE 0 END), "
        "MAX(pct_of_par), " + cases + " FROM results WHERE day=?", (day,)).fetchone()
    played, par_hits, top = int(row[0] or 0), int(row[1] or 0), row[2]
    dist = []
    for i, (lo, hi, label) in enumerate(_BUCKETS):
        here = mine is not None and (mine >= lo if hi is None else lo <= mine < hi)
        dist.append({"label": label, "count": int(row[3 + i] or 0), "you": here})
    beat = 0
    if mine is not None and played > 1:
        beat = c.execute("SELECT COUNT(*) FROM results WHERE day=? AND pct_of_par < ?",
                         (day, mine)).fetchone()[0]
    return {"played": played, "par_hits": par_hits, "top_pct": top,
            "percentile": round(beat / played * 100) if (mine is not None and played > 1) else 100,
            "distribution": dist}


def record(day: int, user_id: str, pct: float, walked: bool, *, side: str = "",
           scenario: str = "", close: Optional[float] = None,
           your_offers: Optional[list] = None, house_offers: Optional[list] = None) -> dict:
    """Record one play (idempotent per (day, user) on the board); advance the streak only on
    the first play of a day; and log the full move sequence to `plays` — the data moat."""
    with conn() as c:
        first = c.execute("SELECT 1 FROM results WHERE day=? AND user_id=?",
                          (day, user_id)).fetchone() is None
        c.execute("INSERT INTO results (day, user_id, pct_of_par, walked) VALUES (?,?,?,?) "
                  "ON CONFLICT (day, user_id) DO UPDATE SET pct_of_par=excluded.pct_of_par, "
                  "walked=excluded.walked", (day, user_id, pct, 1 if walked else 0))
        c.execute("INSERT INTO plays (day, user_id, side, scenario, close, pct_of_par, walked, "
                  "your_offers, house_offers) VALUES (?,?,?,?,?,?,?,?,?)",
                  (day, user_id, side, scenario, close, pct, 1 if walked else 0,
                   json.dumps(your_offers or []), json.dumps(house_offers or [])))
        row = c.execute("SELECT cur, mx, last_day FROM streaks WHERE user_id=?",
                        (user_id,)).fetchone()
        cur, mx, last = row if row else (0, 0, None)
        if first:                                        # streak moves only on the first play of a day
            cur = cur + 1 if last == day - 1 else 1
            mx = max(mx, cur)
            c.execute("INSERT INTO streaks (user_id, cur, mx, last_day) VALUES (?,?,?,?) "
                      "ON CONFLICT (user_id) DO UPDATE SET cur=excluded.cur, mx=excluded.mx, "
                      "last_day=excluded.last_day", (user_id, cur, mx, day))
        agg = _day_aggregates(c, day, pct)
        c.commit()
    return {"streak": cur, "max_streak": mx, **{k: agg[k] for k in
            ("played", "percentile", "par_hits", "distribution")}}


def stats(day: int) -> dict:
    """Anonymous day rollup — powers the landing's live social proof."""
    with conn() as c:
        agg = _day_aggregates(c, day)
    return {k: agg[k] for k in ("played", "par_hits", "top_pct", "distribution")}


def join_group(group_id: str, user_id: str, name: str) -> None:
    """Add a player to a friend group (idempotent). The group_id rides in on the share link."""
    with conn() as c:
        c.execute("INSERT INTO friend_groups (group_id, user_id, name) VALUES (?,?,?) "
                  "ON CONFLICT (group_id, user_id) DO UPDATE SET name=excluded.name",
                  (group_id, user_id, name or user_id))
        c.commit()


def group_board(group_id: str, day: int) -> dict:
    """Today's ranked leaderboard for one friend group; unplayed members last. Display names
    are unique only within a group — duplicates get a short suffix off the hidden user_id."""
    with conn() as c:
        members = c.execute("SELECT user_id, name FROM friend_groups WHERE group_id=?",
                            (group_id,)).fetchall()
        res = {r[0]: r[1] for r in c.execute("SELECT user_id, pct_of_par FROM results WHERE day=?",
                                             (day,)).fetchall()}
    counts: dict = {}
    for _, name in members:
        counts[name] = counts.get(name, 0) + 1
    rows = []
    for uid, name in members:
        disp = name if counts.get(name, 0) < 2 else name + "·" + uid[-2:]
        rows.append({"user": uid, "name": disp, "pct": res.get(uid), "played": uid in res})
    rows.sort(key=lambda x: (x["played"], x["pct"] or 0), reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return {"group": group_id, "members": len(members),
            "played": sum(1 for r in rows if r["played"]), "board": rows}


def seed_demo(day: int, n: int = 240) -> None:
    """DEMO ONLY — a believable spread so /par/stats + the histogram render alive. Idempotent
    per day (skips if already seeded). Delete once real scenarios are seeded."""
    with conn() as c:
        if c.execute("SELECT 1 FROM results WHERE day=? AND user_id=?", (day, "seed0")).fetchone():
            return
        rng = random.Random(1000 + day)
        for i in range(n):
            roll = rng.random()
            pct = 0.0 if roll < 0.06 else min(100.0, round(rng.gauss(78, 11), 1))
            c.execute("INSERT INTO results (day, user_id, pct_of_par, walked) VALUES (?,?,?,?) "
                      "ON CONFLICT (day, user_id) DO NOTHING",
                      (day, f"seed{i}", pct, 1 if pct == 0.0 else 0))
        c.commit()


def seed_group_demo(group_id: str, day: int) -> None:
    """DEMO ONLY — a friend group with named players who already finished, so the leaderboard
    renders alive. Membership seeded once; results seeded per day."""
    friends = [("maya", "Maya", 96.0), ("dev", "Dev", 88.0),
               ("sam", "Sam", 74.0), ("priya", "Priya", 61.0), ("theo", "Theo", None)]
    with conn() as c:
        for uid, name, pct in friends:
            c.execute("INSERT INTO friend_groups (group_id, user_id, name) VALUES (?,?,?) "
                      "ON CONFLICT (group_id, user_id) DO NOTHING", (group_id, uid, name))
            if pct is not None:
                c.execute("INSERT INTO results (day, user_id, pct_of_par, walked) VALUES (?,?,?,0) "
                          "ON CONFLICT (day, user_id) DO NOTHING", (day, uid, pct))
        c.commit()
