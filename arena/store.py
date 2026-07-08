"""Event-sourced persistence: JSONL segments + per-generation snapshots on the
Fly volume. Single writer, append-only — replay is a file read, so v1 needs no
Postgres. Also indexes highlights (with seq ranges) for the clip pipeline.
"""
from __future__ import annotations

import json
import os
from typing import Iterable, Optional

from arena.events import dumps, _json_default


class EventStore:
    def __init__(self, data_dir: str, run_id: str):
        self.run_dir = os.path.join(data_dir, run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        self._seg: Optional[object] = None
        self._seg_gen = -1
        self._highlights_path = os.path.join(self.run_dir, "highlights.jsonl")

    def _segment(self, gen: int):
        if self._seg_gen != gen or self._seg is None:
            if self._seg is not None:
                self._seg.close()
            path = os.path.join(self.run_dir, f"events-{gen:06d}.jsonl")
            self._seg = open(path, "a", buffering=1)
            self._seg_gen = gen
        return self._seg

    def write(self, ev: dict) -> None:
        f = self._segment(int(ev.get("gen", 0)))
        f.write(dumps(ev) + "\n")
        if ev.get("type") == "highlight":
            with open(self._highlights_path, "a") as h:
                h.write(dumps(ev) + "\n")

    def write_snapshot(self, gen: int, snapshot: dict) -> None:
        path = os.path.join(self.run_dir, f"snap-{gen:06d}.json")
        with open(path, "w") as f:
            json.dump(snapshot, f, default=_json_default)  # numpy-safe, like dumps()

    def flush(self) -> None:
        if self._seg is not None:
            self._seg.flush()
            os.fsync(self._seg.fileno())

    def close(self) -> None:
        if self._seg is not None:
            self._seg.close()
            self._seg = None

    # ── replay ──
    def read_gen(self, gen: int) -> Iterable[dict]:
        path = os.path.join(self.run_dir, f"events-{gen:06d}.jsonl")
        if not os.path.exists(path):
            return
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def read_highlights(self) -> list[dict]:
        if not os.path.exists(self._highlights_path):
            return []
        out = []
        with open(self._highlights_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
