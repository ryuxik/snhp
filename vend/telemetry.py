"""NEXTMOVE telemetry — append-only JSONL, raw now, science offline.

One line per paid advice, one per catalog request. No behavioral
classification at write time (derivable later from raw records — freeze
any classifier before the first *read*, not the first session).

Hygiene rules (NEXTMOVE.md §5/§7):
  - api_key is never stored raw — only a keyed hash (repeat-measurement
    without credential-in-log risk).
  - free-text requests are size-capped at ingestion and stored as data;
    nothing downstream may render them raw or treat them as instructions.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

_LOCK = threading.Lock()
_MAX_REQUEST_CHARS = 2_000


def _path() -> str:
    return os.environ.get("NEXTMOVE_TELEMETRY_PATH",
                          os.path.join(os.getcwd(), "nextmove_telemetry.jsonl"))


def _repeat_key(api_key: str) -> str:
    """Stable pseudonym for repeat measurement; never the key itself."""
    return hashlib.blake2b(api_key.encode(), digest_size=8,
                           person=b"nextmove").hexdigest()


def _append(record: dict) -> None:
    line = json.dumps(record, sort_keys=True, separators=(",", ":"))
    with _LOCK:
        with open(_path(), "a") as f:
            f.write(line + "\n")


def log_session_open(*, api_key: str, door: str, category: str,
                     side: str, stake: float, price_cents: int,
                     session_id: str) -> None:
    """A paid negotiation session opened. `stake` = |target - walk_away|,
    the value-scaled-pricing analysis field (see NEXTMOVE.md §6)."""
    _append({
        "kind": "session_open", "ts": time.time(), "door": door,
        "repeat_key": _repeat_key(api_key), "session_id": session_id,
        "category": category, "side": side, "stake": stake,
        "price_cents": price_cents,
    })


def log_advice(*, advice, api_key: str, door: str,
               price_cents: int, session_id: str | None = None,
               move_index: int | None = None) -> None:
    """One advice, both doors. `advice` is a vend.advice.Advice."""
    _append({
        "kind": "advice",
        "session_id": session_id,
        "move_index": move_index,
        "ts": time.time(),
        "door": door,                       # "http" | "mcp"
        "repeat_key": _repeat_key(api_key),
        "category": advice.category,
        "side": advice.side,
        "move": advice.move,
        "offer": advice.offer,
        "context_hash": advice.context_hash,
        "policy_id": advice.policy_id,
        "seed": advice.seed,
        "price_cents": price_cents,
        "compute": advice.engine.get("compute", {}),
    })


def log_slot_call(*, api_key: str | None, door: str, slot_id, backend_id,
                  ok: bool, settled: bool, price_millicents: int,
                  wholesale_millicents: int, wholesale_estimated: bool,
                  funding, shortfall_millicents: int, predicate, reason,
                  content_hash) -> None:
    """One line per store slot call — INCLUDING uncharged failures, since a
    non-delivery is itself telemetry (the null-query log's paid twin). The
    settlement engine hands `api_key` RAW; it is stored ONLY as the keyed
    blake2b repeat_key, never as the key itself. Payload contents are never
    logged — only content_hash, the receipt's checkable anchor."""
    _append({
        "kind": "slot_call",
        "ts": time.time(),
        "door": door,                          # "http" | "mcp"
        "repeat_key": _repeat_key(api_key) if api_key else None,
        "slot_id": slot_id,
        "backend_id": backend_id,
        "ok": ok,
        "settled": settled,
        "price_millicents": price_millicents,
        "wholesale_millicents": wholesale_millicents,
        "wholesale_estimated": wholesale_estimated,
        "funding": funding,
        "shortfall_millicents": shortfall_millicents,
        "predicate": predicate,
        "reason": reason,
        "content_hash": content_hash,
    })


def log_throttle(*, scope: str, had_key: bool, path: str,
                 api_key: str | None = None) -> None:
    """One line per 429 (rate-limit reject). Rate-limited requests never reach
    slot telemetry, so throttled demand is otherwise invisible to the R-gate
    instruments (GAUNTLET.md #3) — this makes it countable. `had_key` records
    whether a key credential was PRESENTED (true even for a bogus token); when
    one was, repeat_key carries the keyed blake2b hash for repeat-measurement,
    NEVER the raw key. `scope` is the bucket that fired (e.g. math_per_ip,
    math_per_key, issue_key_per_ip). Cheap, append-only, no PII."""
    _append({
        "kind": "throttle",
        "ts": time.time(),
        "scope": scope,
        "had_key": had_key,
        "path": path,
        "repeat_key": _repeat_key(api_key) if api_key else None,
    })


def log_free_taste(api_key: str | None, door: str) -> None:
    """The free negotiate/turn taste — the TOP of the free->paid funnel. Keyed
    free usage must be measurable (free->paid conversion for the observatory),
    so we log one line per free call. `api_key` is stored ONLY as the keyed
    repeat_key (or None for anonymous free use), never raw. `door` is
    "http" | "mcp". Cheap, append-only, no PII."""
    _append({
        "kind": "free_taste",
        "ts": time.time(),
        "door": door,
        "repeat_key": _repeat_key(api_key) if api_key else None,
    })


def log_request(*, text: str, door: str,
                api_key: str | None = None) -> dict:
    """catalog.request intake — the null-query log. Returns the stored
    record (truncation visible to the caller)."""
    raw = str(text)
    record = {
        "kind": "catalog_request",
        "ts": time.time(),
        "door": door,
        "repeat_key": _repeat_key(api_key) if api_key else None,
        "request": raw[:_MAX_REQUEST_CHARS],
        "truncated": len(raw) > _MAX_REQUEST_CHARS,
    }
    _append(record)
    return record
