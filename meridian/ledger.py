"""Append-only, hash-chained event ledger (SPEC "Hash-chained event ledger";
Deliverable "every event is hash-chain receipted").

Self-contained on purpose: this demo ships as customer-visible sample code, so
it does NOT import the paperswarm ledger even though it follows the same
pattern.  The one deliberate difference: the timestamp is the simulation TICK
(a logical clock), never wall time, so `same seed -> identical ledger hash`
holds (determinism test).  Each record carries prev_hash + sha256(body); any
edit or reorder breaks the chain and verify_chain() localizes the first break.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterator, Optional

GENESIS_PREV = "0" * 64

# Event taxonomy (the MPX receipt types).
EV_RFQ = "rfq"
EV_QUOTE = "quote"
EV_COUNTER = "counter"
EV_ACCEPT = "accept"
EV_SETTLE = "settle"        # optimistic payment on accept
EV_DELIVER = "deliver"      # goods arrive (may be late/short)
EV_RATE = "rate"
EV_FAIL = "fail"            # negotiation ended with no trade
EV_NOTE = "note"


def _canonical(obj: dict) -> str:
    """Deterministic JSON for hashing (sorted keys, compact, ASCII)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(seq: int, tick: int, ev_type: str, data: dict,
                 prev_hash: str) -> str:
    body = _canonical({
        "seq": seq, "tick": tick, "type": ev_type,
        "data": data, "prev_hash": prev_hash,
    })
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    tick: int
    type: str
    data: dict
    prev_hash: str
    hash: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "tick": self.tick, "type": self.type,
                "data": self.data, "prev_hash": self.prev_hash, "hash": self.hash}


class Ledger:
    """In-memory hash-chained ledger. `records` is the append-only log."""

    def __init__(self) -> None:
        self.records: list[Record] = []

    def head_hash(self) -> str:
        return self.records[-1].hash if self.records else GENESIS_PREV

    def append(self, ev_type: str, tick: int, data: dict) -> Record:
        seq = len(self.records)
        prev = self.head_hash()
        # Round floats so hashing is stable across platforms (SPEC determinism).
        data = _round_floats(data)
        h = compute_hash(seq, tick, ev_type, data, prev)
        rec = Record(seq, tick, ev_type, data, prev, h)
        self.records.append(rec)
        return rec

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def of_type(self, ev_type: str) -> list[Record]:
        return [r for r in self.records if r.type == ev_type]

    def to_jsonl(self) -> str:
        return "\n".join(_canonical(r.to_dict()) for r in self.records)


def _round_floats(obj, ndigits: int = 6):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    length: int
    error_seq: Optional[int] = None
    error: Optional[str] = None


def verify_chain(ledger: Ledger) -> ChainResult:
    """Recompute the whole chain; first failure wins. Detects reordering (seq
    gap), broken linkage (prev_hash), and content tamper (hash mismatch)."""
    prev = GENESIS_PREV
    expected_seq = 0
    for rec in ledger.records:
        if rec.seq != expected_seq:
            return ChainResult(False, len(ledger), rec.seq,
                               f"seq gap: expected {expected_seq}, got {rec.seq}")
        if rec.prev_hash != prev:
            return ChainResult(False, len(ledger), rec.seq,
                               "prev_hash mismatch (chain broken)")
        recomputed = compute_hash(rec.seq, rec.tick, rec.type, rec.data,
                                  rec.prev_hash)
        if recomputed != rec.hash:
            return ChainResult(False, len(ledger), rec.seq,
                               "hash mismatch (content tampered)")
        prev = rec.hash
        expected_seq += 1
    return ChainResult(True, len(ledger))
