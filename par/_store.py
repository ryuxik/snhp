"""PAR persistence — SQLite by default, Postgres when DATABASE_URL is set.

Reuses the repo's `gametheory._db.db_conn`, which yields a sqlite3-Connection-shaped object
and translates on the fly for Postgres (`?`->`%s`, `INTEGER`->`BIGINT` in DDL). So the same
SQL runs on both; the offline demo needs zero setup (a local SQLite file), and production
gets durable, shareable state via `fly postgres attach` (see par/DEPLOY.md).

This replaces the in-memory dicts in scoreboard.py / funnel.py — so state survives restarts
and the event log no longer grows unbounded in RAM (it's a table).

DDL is SQLite-compatible (the layer translates to PG): booleans as INTEGER 0/1, JSON as TEXT,
no auto-increment ids (we only count). Upserts use `ON CONFLICT (...) DO UPDATE`, which both
SQLite (3.24+) and Postgres speak natively. Table/column names avoid dialect reserved words
(`friend_groups`, streak cols `cur`/`mx`).
"""
from __future__ import annotations

import os

# Local-dev default: a par-only SQLite file next to this module, so the game's tables don't
# mingle with the toolkit's keys.db. Respected only when neither DATABASE_URL nor an explicit
# GT_KEYS_DB is set; production sets DATABASE_URL and this is a no-op.
if not os.environ.get("DATABASE_URL") and not os.environ.get("GT_KEYS_DB"):
    os.environ["GT_KEYS_DB"] = os.path.join(os.path.dirname(__file__), ".par.db")

from gametheory._db import db_conn  # noqa: E402  (import after the env default above)

PAR_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS results ("
    "  day INTEGER NOT NULL, user_id TEXT NOT NULL,"
    "  pct_of_par REAL NOT NULL, walked INTEGER NOT NULL DEFAULT 0,"
    "  PRIMARY KEY (day, user_id))",
    "CREATE TABLE IF NOT EXISTS streaks ("
    "  user_id TEXT PRIMARY KEY, cur INTEGER NOT NULL DEFAULT 0,"
    "  mx INTEGER NOT NULL DEFAULT 0, last_day INTEGER)",
    "CREATE TABLE IF NOT EXISTS friend_groups ("
    "  group_id TEXT NOT NULL, user_id TEXT NOT NULL, name TEXT NOT NULL,"
    "  PRIMARY KEY (group_id, user_id))",
    "CREATE TABLE IF NOT EXISTS waitlist ("
    "  user_id TEXT PRIMARY KEY, scenario TEXT NOT NULL, contact TEXT)",
    "CREATE TABLE IF NOT EXISTS events ("
    "  user_id TEXT NOT NULL, name TEXT NOT NULL, meta TEXT NOT NULL DEFAULT '{}')",
)


def conn():
    """A db connection with the PAR schema ensured (once per backend). Use as a context
    manager: `with conn() as c: c.execute(...); c.commit()`."""
    return db_conn(PAR_SCHEMA)
