"""
Shared SQLite plumbing for the toolkit. Onboarding (keys) and first-strike
(commitments) share the same file by default; each owns its own table.

Path resolution stays lazy so tests can override `GT_KEYS_DB` at module
import time. Schema DDL runs once per (path, schema) pair, not per
connection — `_conn` previously ran CREATE TABLE on every request.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


def resolve_db_path() -> str:
    return os.environ.get(
        "GT_KEYS_DB",
        os.path.join(os.path.expanduser("~"), ".gametheory", "keys.db"),
    )


_INITIALIZED: set[tuple[str, tuple[str, ...]]] = set()


def _ensure_schema(db_path: str, schema_ddl: tuple[str, ...]) -> None:
    cache_key = (db_path, schema_ddl)
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
def db_conn(schema_ddl: tuple[str, ...]) -> Iterator[sqlite3.Connection]:
    db_path = resolve_db_path()
    _ensure_schema(db_path, schema_ddl)
    c = sqlite3.connect(db_path)
    try:
        yield c
    finally:
        c.close()
