"""PAR scoreboard — the retention + virality layer, now on durable storage.

Backed by par/_store.py (SQLite locally, Postgres in prod) instead of in-memory dicts, so
streaks, results, and groups survive restarts and scale across instances. Every figure is a
`SELECT ... GROUP BY` over the tables; the endpoint shapes are unchanged. Scores are recorded
server-side from the close (never trusted from the client), so the board can't be gamed.
"""
from __future__ import annotations

import random
from typing import Optional

from par._store import conn

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
    play of a day. Returns the streak + how the player placed against everyone today."""
    with conn() as c:
        first = c.execute("SELECT 1 FROM results WHERE day=? AND user_id=?",
                          (day, user_id)).fetchone() is None
        c.execute("INSERT INTO results (day, user_id, pct_of_par, walked) VALUES (?,?,?,?) "
                  "ON CONFLICT (day, user_id) DO UPDATE SET pct_of_par=excluded.pct_of_par, "
                  "walked=excluded.walked", (day, user_id, pct, 1 if walked else 0))
        row = c.execute("SELECT cur, mx, last_day FROM streaks WHERE user_id=?",
                        (user_id,)).fetchone()
        cur, mx, last = row if row else (0, 0, None)
        if first:                                        # streak moves only on the first play of a day
            cur = cur + 1 if last == day - 1 else 1
            mx = max(mx, cur)
            c.execute("INSERT INTO streaks (user_id, cur, mx, last_day) VALUES (?,?,?,?) "
                      "ON CONFLICT (user_id) DO UPDATE SET cur=excluded.cur, mx=excluded.mx, "
                      "last_day=excluded.last_day", (user_id, cur, mx, day))
        pcts = [r[0] for r in c.execute("SELECT pct_of_par FROM results WHERE day=?",
                                        (day,)).fetchall()]
        c.commit()
    played = len(pcts)
    beat = sum(1 for p in pcts if p < pct)
    return {
        "streak": cur, "max_streak": mx, "played": played,
        "percentile": round(beat / played * 100) if played > 1 else 100,
        "par_hits": sum(1 for p in pcts if p >= 100),
        "distribution": _bucketize(pcts, pct),
    }


def stats(day: int) -> dict:
    """Anonymous day rollup — powers the landing's live social proof."""
    with conn() as c:
        pcts = [r[0] for r in c.execute("SELECT pct_of_par FROM results WHERE day=?",
                                        (day,)).fetchall()]
    return {"played": len(pcts), "par_hits": sum(1 for p in pcts if p >= 100),
            "top_pct": max(pcts) if pcts else None, "distribution": _bucketize(pcts)}


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
