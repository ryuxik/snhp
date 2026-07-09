"""Evolve the arena champion and export it as a gauntlet candidate.

The evolution arena's remaining job in the leaderboard era: its selection loop
breeds a negotiation POLICY (tactic family + the evolvable bundle_tactic genes),
and this module exports the current champion so it can hold a leaderboard seat
next to the frontier models — "what N generations of evolution found."

Selection is the arena's own fitness (lifetime earnings), NOT the gauntlet
metric — the champion never sees the frozen gauntlet scenarios before it is
scored on them, same as every other candidate.

Usage:
    python -m arena.gauntlet.champion --gens 100 --seeds 1,2,3
    python -m arena.gauntlet.run --candidate champion: --scenarios 20 \\
        --out arena/web/leaderboard.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import time

CHAMPION_PATH = pathlib.Path(__file__).with_name("champion.json")


def evolve_champion(gens: int, seeds: tuple[int, ...]) -> dict:
    from arena.config import CONFIG
    from arena.world import World

    best = None  # (earnings, genome, seed)
    for sd in seeds:
        w = World(dataclasses.replace(CONFIG, seed=sd))
        for _ in range(gens):
            list(w.generation_events())
        top = max(w.agents.values(), key=lambda a: a.total_earned)
        if best is None or top.total_earned > best[0]:
            best = (float(top.total_earned), top.genome, sd)
    earnings, g, sd = best
    return {
        "genome": dataclasses.asdict(g),
        "provenance": {"gens": gens, "seed": sd, "seeds_tried": list(seeds),
                       "lifetime_earnings": round(earnings, 2),
                       "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }


def load_champion(path: pathlib.Path = CHAMPION_PATH):
    """champion.json → (Genome, provenance dict)."""
    from arena.genome import Genome
    data = json.loads(path.read_text())
    raw = dict(data["genome"])
    for k, v in raw.items():           # JSON lists → the dataclass's tuples
        if isinstance(v, list):
            raw[k] = tuple(v)
    return Genome(**raw), data.get("provenance", {})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gens", type=int, default=100)
    p.add_argument("--seeds", default="1,2,3")
    p.add_argument("--out", default=str(CHAMPION_PATH))
    args = p.parse_args(argv)
    seeds = tuple(int(s) for s in args.seeds.split(","))
    t0 = time.time()
    data = evolve_champion(args.gens, seeds)
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(data, indent=1))
    g, prov = data["genome"], data["provenance"]
    print(f"evolved {args.gens} gens x {len(seeds)} seeds in {time.time() - t0:.0f}s")
    print(f"champion: {g['tactic_family']}, staked={g['staked']}, "
          f"bundle_tactic={[round(x, 2) for x in g['bundle_tactic']]}, "
          f"earnings={prov['lifetime_earnings']} (seed {prov['seed']})")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
