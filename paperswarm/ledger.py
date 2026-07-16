"""Append-only, hash-chained receipt ledger (SPEC.md: "Every event is a
receipt ... hash-chained ledger from day one").

JSONL. Each record carries prev_hash + sha256(self) so any edit breaks the
chain. A null `sig` field is reserved for notary signing when core/notary N1
lands (SPEC: "upgraded to notary-signed"). The dashboard shows NOTHING that is
not derivable from this chain.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from . import config
from .timeutil import iso, now_utc

GENESIS_PREV = "0" * 64

# Event types (the receipt taxonomy).
EV_BID_COMMIT = "bid_commit"   # max bid committed >=60s before close
EV_FILL = "fill"               # auction resolved: won@hammer+inc | lost
EV_MARK = "mark"               # inventory mark-to-realized
EV_SPEND = "spend"             # metered API/LLM compute charged to P&L
EV_NOTE = "note"               # freeform audit note (e.g. cold-start refusal)


def _canonical(obj: dict) -> str:
    """Deterministic JSON for hashing (sorted keys, compact, ASCII-safe)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(seq: int, ts: str, ev_type: str, data: dict,
                 prev_hash: str, sig) -> str:
    """sha256 over the canonical record body (everything but `hash`)."""
    body = _canonical({
        "seq": seq, "ts": ts, "type": ev_type,
        "data": data, "prev_hash": prev_hash, "sig": sig,
    })
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    ts: str
    type: str
    data: dict
    prev_hash: str
    sig: object
    hash: str

    def to_json(self) -> str:
        return json.dumps({
            "seq": self.seq, "ts": self.ts, "type": self.type,
            "data": self.data, "prev_hash": self.prev_hash,
            "sig": self.sig, "hash": self.hash,
        }, sort_keys=True, separators=(",", ":"))


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path or config.LEDGER_PATH)
        if str(self.path) != os.devnull:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- reads -------------------------------------------------------------
    def records(self) -> Iterator[Record]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                yield Record(
                    seq=d["seq"], ts=d["ts"], type=d["type"], data=d["data"],
                    prev_hash=d["prev_hash"], sig=d.get("sig"), hash=d["hash"],
                )

    def all(self) -> list[Record]:
        return list(self.records())

    def last(self) -> Record | None:
        last = None
        for rec in self.records():
            last = rec
        return last

    def head_hash(self) -> str:
        last = self.last()
        return last.hash if last else GENESIS_PREV

    def next_seq(self) -> int:
        last = self.last()
        return (last.seq + 1) if last else 0

    # -- writes ------------------------------------------------------------
    def append(self, ev_type: str, data: dict, *, sig=None, ts: str | None = None) -> Record:
        """Append a receipt, chaining onto the current head. sig defaults null.

        Reserving sig=None keeps the schema notary-ready (SPEC).
        """
        seq = self.next_seq()
        prev_hash = self.head_hash()
        ts = ts or iso(now_utc())
        h = compute_hash(seq, ts, ev_type, data, prev_hash, sig)
        rec = Record(seq, ts, ev_type, data, prev_hash, sig, h)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(rec.to_json() + "\n")
        return rec

    # typed convenience wrappers (the receipt taxonomy) ---------------------
    def bid_commit(self, data: dict, ts: str | None = None) -> Record:
        return self.append(EV_BID_COMMIT, data, ts=ts)

    def fill(self, data: dict, ts: str | None = None) -> Record:
        return self.append(EV_FILL, data, ts=ts)

    def mark(self, data: dict, ts: str | None = None) -> Record:
        return self.append(EV_MARK, data, ts=ts)

    def spend(self, data: dict, ts: str | None = None) -> Record:
        return self.append(EV_SPEND, data, ts=ts)

    def note(self, data: dict, ts: str | None = None) -> Record:
        return self.append(EV_NOTE, data, ts=ts)


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    length: int
    error_seq: int | None = None
    error: str | None = None


def verify_chain(path=None) -> ChainResult:
    """Recompute the whole chain (SPEC: verify_chain() + CLI hook).

    Fails on: broken prev_hash linkage, a recomputed hash that differs from the
    stored hash (content tamper), or a non-contiguous seq. First failure wins.
    """
    ledger = Ledger(path)
    prev = GENESIS_PREV
    expected_seq = 0
    n = 0
    for rec in ledger.records():
        n += 1
        if rec.seq != expected_seq:
            return ChainResult(False, n, rec.seq,
                               f"seq gap: expected {expected_seq}, got {rec.seq}")
        if rec.prev_hash != prev:
            return ChainResult(False, n, rec.seq,
                               "prev_hash mismatch (chain broken)")
        recomputed = compute_hash(rec.seq, rec.ts, rec.type, rec.data,
                                  rec.prev_hash, rec.sig)
        if recomputed != rec.hash:
            return ChainResult(False, n, rec.seq,
                               "hash mismatch (content tampered)")
        prev = rec.hash
        expected_seq += 1
    return ChainResult(True, n)
