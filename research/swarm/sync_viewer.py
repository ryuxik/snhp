#!/usr/bin/env python3
"""Generate arena/web/swarm.html from research/swarm/viewer.html.

The deployed viewer is the research viewer plus exactly two site patches
(badge link, default demo traces). Hand-syncing 540-line twins is how the
public page drifts from the committed sim (review C1) — this script is the
only sanctioned way to update the arena copy:

    python research/swarm/sync_viewer.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "viewer.html")
DST = os.path.normpath(os.path.join(HERE, "..", "..", "arena", "web", "swarm.html"))

PATCHES = [
    # (research line, arena line) — each must match exactly once
    ('<div id="badge">replay of a real committed simulation · reproducible from the repo</div>',
     '<div id="badge"><a href="/leaderboard.html">arena.snhp.dev</a> · replay of a real committed simulation · reproducible from the repo</div>'),
    ('  let urls=[p.get("trace"),p.get("trace2")].filter(Boolean);',
     '  let urls=[p.get("trace"),p.get("trace2")].filter(Boolean);\n'
     '  if(!urls.length) urls=["swarm-traces/trace_v5_snhp-hz_s0.5_seed3.jsonl","swarm-traces/trace_v5_auction_seed3.jsonl"];'),
]


def main() -> None:
    html = open(SRC).read()
    for old, new in PATCHES:
        n = html.count(old)
        if n != 1:
            sys.exit(f"sync_viewer: patch anchor matched {n}x (want 1): {old[:60]}…")
        html = html.replace(old, new)
    open(DST, "w").write(html)
    print(f"wrote {DST} ({len(html)} bytes, {len(PATCHES)} site patches)")


if __name__ == "__main__":
    main()
