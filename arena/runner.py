"""The live pacing loop. Drains World.generation_events() and publishes to the
broadcaster, sleeping between choreography beats so the event stream spaces out
in real wall-clock time (the renderer's jitter buffer keys off `t`). Warms up
numba/the engine before the server reports healthy.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from arena.config import CONFIG, ArenaConfig
from arena.world import World
from arena.broadcaster import Broadcaster
from arena.store import EventStore

# Pacing is TICK-driven: each sim tick is one round advanced across all live
# negotiations, so we sleep once per tick (a choreography beat) rather than once
# per event. Within a tick, the ~dozen concurrent duels each emit one offer;
# the renderer's jitter buffer spaces them. Bookkeeping events (census, births)
# don't advance the tick and stream fast. A few event types get an extra dwell
# so big moments land.
_TICK_SLEEP = 0.9          # seconds per round (choreography beat)
_EXTRA = {"era.change": 0.8, "gen.end": 0.6, "auction.hammer": 0.6,
          "agent.birth": 0.15, "agent.death": 0.15, "court.accept": 0.2}


def _now_ms() -> int:
    return int(time.time() * 1000)


class ArenaRunner:
    def __init__(self, cfg: ArenaConfig = CONFIG, run_id: str = "live",
                 persist: bool = True, speed: float = 1.0):
        self.cfg = cfg
        self.world = World(cfg, clock_ms=_now_ms)
        self.bcast = Broadcaster()
        self.store = EventStore(cfg.data_dir, run_id) if persist else None
        self.speed = speed
        self.paused = False
        self._task: Optional[asyncio.Task] = None
        self._warm = False
        snap = self.world.snapshot()
        self.bcast.set_snapshot(snap)
        # the ONLY object HTTP endpoints read — swapped atomically each generation
        self.public = {"snapshot": snap, "census": None, "species": [], "leaderboard": []}

    def warmup(self) -> None:
        """Trigger numba JIT + a full generation off-broadcast so the first live
        beats aren't stalled by compilation."""
        if self._warm:
            return
        w = World(self.cfg)  # throwaway; compiles the engine paths
        for _ in w.generation_events():
            pass
        self._warm = True

    async def run(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            if self.paused:
                await asyncio.sleep(0.2)
                continue
            # Produce one generation's events in a thread (engine is CPU-bound),
            # then pace their emission on the event loop. The World is ONLY read
            # while the executor thread is idle (before the next _next_generation),
            # so HTTP endpoints must read self.public (an immutable snapshot swapped
            # atomically here), never the live world — avoids a dict-mutation race.
            events = await loop.run_in_executor(None, self._next_generation)
            last_tick = events[0]["tick"] if events else 0
            census = species = leaderboard = None
            for ev in events:
                self.bcast.publish(ev)
                if self.store is not None:
                    self.store.write(ev)
                t = ev["type"]
                if t == "census":
                    census = ev
                elif t == "species.update":
                    species = ev.get("species")
                elif t == "leaderboard":
                    leaderboard = ev.get("top")
                sleep = 0.0
                if ev["tick"] > last_tick:
                    sleep += _TICK_SLEEP
                    last_tick = ev["tick"]
                sleep += _EXTRA.get(ev["type"], 0.0)
                sleep /= max(self.speed, 0.01)
                if sleep > 0:
                    await asyncio.sleep(sleep)
            # Build the read-state from the (now-idle) world, then publish it as
            # one atomic reference the endpoints can read without locking.
            snap = self.world.snapshot()
            self.bcast.set_snapshot(snap)
            self.public = {"snapshot": snap, "census": census,
                           "species": species or [], "leaderboard": leaderboard or []}
            if self.store is not None:
                # persist off the event loop — json.dump + fsync are blocking syscalls
                await loop.run_in_executor(None, self._persist, self.world.gen, snap)

    def _persist(self, gen: int, snap: dict) -> None:
        self.store.write_snapshot(gen, snap)
        self.store.flush()

    def _next_generation(self) -> list[dict]:
        return list(self.world.generation_events())

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self.store is not None:
            self.store.flush()
            self.store.close()
