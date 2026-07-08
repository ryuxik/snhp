"""Event schema v1 — the wire format between sim and renderer.

Every event is a JSON dict with a common envelope stamped by the world:
  {"v":1, "seq":<monotonic int>, "tick":int, "gen":int, "t":<epoch ms>, "type":str, ...}

`t` (wall clock) is EXCLUDED from the determinism hash — the same seed produces
an identical event log up to `t`. The renderer treats unknown `type`s as no-ops,
so new event types are backward-compatible.

The authoritative human doc is arena/EVENTS.md; this module is the machine copy.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

EVENT_V = 1

# Canonical set (documentation + a light validation aid). Not enforced on emit —
# the renderer's forward-compat rule is "unknown type => no-op".
EVENT_TYPES = frozenset({
    "world.snapshot",
    "agent.spawn", "agent.birth", "agent.critical", "agent.death",
    "neg.start", "neg.offer", "neg.accept", "neg.walk",
    "court.start", "court.offer", "court.accept", "court.impasse",
    "mating.round",
    "auction.start", "auction.bid", "auction.hammer",
    "energy.tick",
    "era.change", "dynasty.critical",
    "species.update", "census", "gen.end", "leaderboard",
    "bloom",
    "highlight", "immigration",
})

# Fields never part of the deterministic content of an event.
_NONDET_FIELDS = ("t",)


def strip_nondeterministic(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if k not in _NONDET_FIELDS}


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(o: Any):
    # numpy scalars / arrays sometimes sneak in; coerce to plain python
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    raise TypeError(f"not JSON-serializable: {type(o)}")


def hash_events(events: Iterable[dict]) -> str:
    """SHA256 over the canonical JSON of every event, minus non-deterministic
    fields. Two runs with the same seed must produce the same hash."""
    h = hashlib.sha256()
    for ev in events:
        h.update(_canonical(strip_nondeterministic(ev)).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def dumps(ev: dict) -> str:
    """Serialize one event to a compact JSON line (for JSONL storage / WS)."""
    return json.dumps(ev, separators=(",", ":"), default=_json_default)
