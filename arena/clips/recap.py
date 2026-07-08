"""Nightly recap reel — stitch the day's flagged highlights into one chaptered
clip, chaptered by era. This is where the multi-hour macro-stories (the staking
two-act, dynasty arcs) become legible, and it's the appointment-viewing / best-X-post
unit. Dev-only deps (playwright + ffmpeg), same as capture.py.

Usage:
    python arena/clips/recap.py --url http://localhost:8201 [--limit 8]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

from arena.clips.capture import capture, OUT, _ffmpeg, _ensure_out  # reuse


def fetch_highlights(url: str) -> list[dict]:
    with urllib.request.urlopen(url.rstrip("/") + "/arena/highlights", timeout=10) as r:
        return json.load(r).get("highlights", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8201")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--seconds", type=float, default=6.0)
    a = ap.parse_args()
    _ensure_out()

    highs = fetch_highlights(a.url)
    if not highs:
        sys.exit("no highlights yet — let the arena run for a while first")
    # Prefer the most narratively loaded kinds, newest first.
    rank = {"record_surplus": 3, "dynasty_founder_death": 3, "dynasty_founded": 2,
            "era_flip": 2, "grand_auction": 2}
    highs.sort(key=lambda h: (rank.get(h.get("kind"), 1), h.get("seq", 0)), reverse=True)
    chosen = highs[: a.limit]

    clips = []
    for i, h in enumerate(chosen):
        gen = h.get("gen", 0)
        name = f"recap_{i:02d}_g{gen}"
        capture(a.url, a.seconds, replay=gen, fps=30, name=name)
        clips.append(os.path.join(OUT, name + ".mp4"))

    # concat
    listfile = os.path.join(OUT, "recap_list.txt")
    with open(listfile, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    reel = os.path.join(OUT, "recap.mp4")
    _ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", reel])
    print(f"wrote {reel}  ({len(clips)} chapters)")


if __name__ == "__main__":
    main()
