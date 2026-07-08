"""Async fan-out: one sim, many viewers, same arena. Keeps a ring buffer of
recent events so a reconnecting client can resync from a seq without a full
snapshot; slow clients get drop-oldest rather than back-pressuring the sim.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Optional


class Broadcaster:
    def __init__(self, ring_size: int = 20000, client_queue_max: int = 4000):
        self._clients: set[asyncio.Queue] = set()
        self._ring: deque = deque(maxlen=ring_size)
        self._client_queue_max = client_queue_max
        self.last_snapshot: Optional[dict] = None

    def set_snapshot(self, snap: dict) -> None:
        self.last_snapshot = snap

    def publish(self, ev: dict) -> None:
        self._ring.append(ev)
        for q in list(self._clients):
            if q.qsize() >= self._client_queue_max:
                try:
                    q.get_nowait()  # drop oldest for a slow client
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(ev)

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._client_queue_max)
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    def replay_since(self, since_seq: int) -> list[dict]:
        """Events in the ring buffer with seq > since_seq (for resync)."""
        return [e for e in self._ring if e.get("seq", 0) > since_seq]

    @property
    def n_clients(self) -> int:
        return len(self._clients)
