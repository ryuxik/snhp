"""Tier 2 — pondering sessions: spend the COUNTERPARTY's think-time on rollouts.

The richer idle window in a negotiation isn't your own turn — it's the seconds
*after* you send an offer, while the other agent deliberates. A chess engine
"ponders" on the opponent's clock; this does the same.

  open_session(...)            -> session_id (holds the running history + belief)
  propose(session_id)          -> your move NOW, and in the background it speculates
                                  over the counter-offers the belief expects and
                                  pre-solves your reply to each (on their clock)
  respond(session_id, offer)   -> if they did roughly what we expected, the deeply
                                  -searched reply is already cached -> instant;
                                  otherwise a fresh (warm) search

Speculation runs in a ThreadPoolExecutor — the rollouts are numpy/numba and release
the GIL, so background threads genuinely use idle cores. Each speculation job gets a
SNAPSHOT of the history, so it never races the live session state.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from gametheory.negotiation.mc_search import negotiate_turn_mc

_N_ANTICIPATED = 6          # how many counter-offers we speculate over
_N_BUCKETS = 12             # price discretization for cache hits
_DEFAULT_COMPUTE_MS = 200

# one shared pool for all sessions; rollouts release the GIL so threads use cores
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="snhp-ponder")
_SESSIONS: dict[str, "PonderingSession"] = {}
_LOCK = threading.Lock()


def _bucket(price: float, lo: float, step: float) -> int:
    return round((price - lo) / step) if step > 0 else 0


class PonderingSession:
    def __init__(self, *, side, walk_away, target, rounds_left, item="this",
                 compute_ms=_DEFAULT_COMPUTE_MS):
        self.side = side
        self.walk_away = float(walk_away)
        self.target = float(target)
        self.rounds_left = int(rounds_left)
        self.item = item
        self.compute_ms = int(compute_ms)
        self.counterparty_offers: list[float] = []
        self.my_offers: list[float] = []
        self._lo = min(walk_away, target)
        self._step = max(abs(target - walk_away) / _N_BUCKETS, 1e-9)
        self._cache: dict[int, Future] = {}
        self._lock = threading.Lock()

    # ── moves ────────────────────────────────────────────────────────────────
    def propose(self, compute_ms: Optional[int] = None) -> dict:
        ms = self.compute_ms if compute_ms is None else int(compute_ms)
        res = negotiate_turn_mc(
            side=self.side, walk_away=self.walk_away, target=self.target,
            counterparty_offers=list(self.counterparty_offers),
            my_previous_offers=list(self.my_offers),
            rounds_left=self.rounds_left, item=self.item, compute_ms=ms)
        if res.get("action") == "counter":
            self.my_offers.append(res["recommended_price"])
            self._spawn_speculation(res["recommended_price"], ms)
        res["_pondered"] = False
        return res

    def respond(self, their_offer: float, compute_ms: Optional[int] = None) -> dict:
        their_offer = float(their_offer)
        ms = self.compute_ms if compute_ms is None else int(compute_ms)
        # cache hit? (their counter landed in a bucket we already searched)
        b = _bucket(their_offer, self._lo, self._step)
        with self._lock:
            fut = self._cache.get(b)
            self._cache.clear()
        if fut is not None and fut.done() and fut.exception() is None:
            self.counterparty_offers.append(their_offer)
            self.rounds_left = max(self.rounds_left - 1, 1)
            res = dict(fut.result())
            res["_pondered"] = True
            if res.get("action") == "counter":
                self.my_offers.append(res["recommended_price"])
                self._spawn_speculation(res["recommended_price"], ms)
            return res
        # miss: fresh (warm) search
        self.counterparty_offers.append(their_offer)
        self.rounds_left = max(self.rounds_left - 1, 1)
        res = negotiate_turn_mc(
            side=self.side, walk_away=self.walk_away, target=self.target,
            counterparty_offers=list(self.counterparty_offers),
            my_previous_offers=list(self.my_offers),
            rounds_left=self.rounds_left, item=self.item, compute_ms=ms)
        res["_pondered"] = False
        if res.get("action") == "counter":
            self.my_offers.append(res["recommended_price"])
            self._spawn_speculation(res["recommended_price"], ms)
        return res

    # ── background speculation ────────────────────────────────────────────────
    def _anticipated_counters(self, my_price: float):
        """The counter-offers the other side is likely to make next. They concede
        toward our price, so sample between their last position and ours."""
        their_last = self.counterparty_offers[-1] if self.counterparty_offers else None
        if self.side == "sell":              # buyer counters upward, below our ask
            lo = their_last if their_last is not None else self.walk_away
            hi = my_price
        else:                                # seller counters downward, above our bid
            lo = my_price
            hi = their_last if their_last is not None else self.walk_away
        if hi <= lo:
            return []
        return [lo + (hi - lo) * (i + 1) / (_N_ANTICIPATED + 1) for i in range(_N_ANTICIPATED)]

    def _spawn_speculation(self, my_price: float, compute_ms: int):
        hist_cp = list(self.counterparty_offers)
        hist_me = list(self.my_offers)
        rounds = max(self.rounds_left - 1, 1)
        new_cache: dict[int, Future] = {}
        for q in self._anticipated_counters(my_price):
            b = _bucket(q, self._lo, self._step)
            if b in new_cache:
                continue
            new_cache[b] = _EXECUTOR.submit(
                negotiate_turn_mc, side=self.side, walk_away=self.walk_away,
                target=self.target, counterparty_offers=hist_cp + [q],
                my_previous_offers=hist_me, rounds_left=rounds, item=self.item,
                compute_ms=compute_ms)
        with self._lock:
            self._cache = new_cache


# ── registry (used by the MCP tools) ──────────────────────────────────────────
def open_session(*, side, walk_away, target, rounds_left=8, item="this",
                 compute_ms=_DEFAULT_COMPUTE_MS) -> str:
    sid = uuid.uuid4().hex[:12]
    with _LOCK:
        _SESSIONS[sid] = PonderingSession(
            side=side, walk_away=walk_away, target=target, rounds_left=rounds_left,
            item=item, compute_ms=compute_ms)
    return sid


def get_session(sid: str) -> PonderingSession:
    with _LOCK:
        s = _SESSIONS.get(sid)
    if s is None:
        raise KeyError(f"unknown or closed session {sid!r}")
    return s


def close_session(sid: str) -> bool:
    with _LOCK:
        s = _SESSIONS.pop(sid, None)
    if s is not None:
        with s._lock:
            for fut in s._cache.values():
                fut.cancel()
        return True
    return False
