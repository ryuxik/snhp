"""
Database plumbing — SQLite by default, Postgres when DATABASE_URL is set.

Onboarding (keys) and first-strike (commitments) share the same backend;
each owns its own table. Schema DDL runs once per (backend, schema) pair.

Backend selection:
  - DATABASE_URL=postgres://... or postgresql://... → Postgres (psycopg2)
  - else → SQLite at GT_KEYS_DB (default ~/.gametheory/keys.db)

The module exposes a single `db_conn(schema_ddl)` context manager whose
yielded object behaves like a sqlite3.Connection for the small subset of
calls our handlers use (`.execute(sql, params).fetchone()` and `.commit()`).
The Postgres path translates `?` placeholders to `%s` on the fly.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator


def _database_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        return url
    return None


def resolve_db_path() -> str:
    return os.environ.get(
        "GT_KEYS_DB",
        os.path.join(os.path.expanduser("~"), ".gametheory", "keys.db"),
    )


_INITIALIZED: set[tuple[str, tuple[str, ...]]] = set()


# ─── SQLite path (default) ──────────────────────────────────────────────────


def _ensure_sqlite_schema(db_path: str, schema_ddl: tuple[str, ...]) -> None:
    cache_key = ("sqlite:" + db_path, schema_ddl)
    if cache_key in _INITIALIZED:
        return
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    c = sqlite3.connect(db_path)
    try:
        for stmt in schema_ddl:
            c.execute(stmt)
        c.commit()
    finally:
        c.close()
    _INITIALIZED.add(cache_key)


@contextmanager
def _sqlite_conn(schema_ddl: tuple[str, ...]) -> Iterator[sqlite3.Connection]:
    db_path = resolve_db_path()
    _ensure_sqlite_schema(db_path, schema_ddl)
    c = sqlite3.connect(db_path)
    try:
        yield c
    finally:
        c.close()


# ─── Postgres path ──────────────────────────────────────────────────────────


def _translate_sql(sql: str) -> str:
    """Translate SQLite SQL to Postgres dialect on the fly.

    Translations applied:
      `?` → `%s`           — parameter placeholder convention.
      `INSERT OR IGNORE`   → `INSERT ... ON CONFLICT DO NOTHING`
                              (only on INSERT statements; appended at end).
      `INTEGER` → `BIGINT` (only on CREATE statements; SQLite INTEGER is
                            variable-width but Postgres INTEGER is 32-bit,
                            overflowing at year 2038 for unix timestamps).

    The DDL-only narrowing for INTEGER prevents accidental rewrites of
    runtime queries that happen to contain the word "INTEGER" (e.g.,
    `CAST(x AS INTEGER)`).
    """
    out = sql.replace("?", "%s")
    head = out.lstrip().upper()[:20]
    if head.startswith("CREATE "):
        out = out.replace("INTEGER", "BIGINT")
    if head.startswith("INSERT ") and "INSERT OR IGNORE" in out.upper():
        # SQLite uses INSERT OR IGNORE; Postgres uses ON CONFLICT DO NOTHING.
        # Strip the modifier and append the conflict clause. Assumes a
        # PRIMARY KEY constraint provides the conflict target.
        out = out.replace("INSERT OR IGNORE", "INSERT", 1)
        out = out.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return out


class _PgConn:
    """Thin sqlite3.Connection-shaped wrapper around psycopg2.

    Implements only the surface our handlers actually use:
      .execute(sql, params=()) → cursor (fetchone/fetchall both work)
      .commit()
      .close()
    """

    def __init__(self, dsn: str):
        import psycopg2  # imported lazily so SQLite users don't need it
        self._conn = psycopg2.connect(dsn)

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        cur = self._conn.cursor()
        cur.execute(_translate_sql(sql), params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _ensure_pg_schema(dsn: str, schema_ddl: tuple[str, ...]) -> None:
    cache_key = ("pg:" + dsn, schema_ddl)
    if cache_key in _INITIALIZED:
        return
    c = _PgConn(dsn)
    try:
        for stmt in schema_ddl:
            c.execute(stmt)
        c.commit()
    finally:
        c.close()
    _INITIALIZED.add(cache_key)


@contextmanager
def _pg_conn(schema_ddl: tuple[str, ...]) -> Iterator[_PgConn]:
    dsn = _database_url()
    assert dsn is not None  # caller checked
    _ensure_pg_schema(dsn, schema_ddl)
    c = _PgConn(dsn)
    try:
        yield c
    finally:
        c.close()


# ─── Public API ─────────────────────────────────────────────────────────────


@contextmanager
def db_conn(schema_ddl: tuple[str, ...]) -> Iterator[Any]:
    if _database_url() is not None:
        with _pg_conn(schema_ddl) as c:
            yield c
    else:
        with _sqlite_conn(schema_ddl) as c:
            yield c
