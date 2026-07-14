"""Dump a replayable JSONL trace of one run for the viewer (see VIZ.md).

    python research/swarm/trace.py --arm snhp-hz --sigma 0.5 --seed 0 --tau 0.15

Schema (one JSON object per line):
  {"type":"header", grid, sources, refineries:[{pos,owner}], charger, arm,
   sigma, seed, tau, total_stock, robots:[{id,cap,eff,sector,company}]}
  {"type":"tick", t, r:[[x,y,battery,load,stranded],...], stock:[s1,s2],
   delivered, co:[d0,d1]}
  {"type":"xfer", t, kind, src, dst, amt}
  {"type":"deal", t, a, b, q, e, s, border, sa, sb, capture}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from swarm import world as W
from swarm.arms import make_arm
from swarm.world import TOTAL_STOCK, World


def write_trace(arm_name: str, sigma: float, seed: int, ticks: int,
                out_path: str, tau: float = 0.0, preset: str = "v4",
                noise: float = 0.0,
                issues=("cargo", "energy", "sector")) -> dict:
    hazard = arm_name.endswith("-hz")
    base = arm_name[:-3] if hazard else arm_name
    w = World(sigma=sigma, seed=seed, hazard_phi=hazard, preset=preset,
              tau=(tau, tau), internalize_tariffs=(base == "team"))
    arm = make_arm(base, w, issues=issues, noise=noise)
    n_events = n_deals = 0
    with open(out_path, "w") as f:
        f.write(json.dumps(dict(
            type="header", grid=W.GRID, sources=w.sources,
            refineries=[dict(pos=list(p), owner=o)
                        for p, o in zip(w.refineries, w.ref_owner)],
            chargers=[dict(pos=list(p_), owner=o)
                      for p_, o in zip(w.chargers, w.charger_owner)],
            arm=arm_name, sigma=sigma, seed=seed,
            tau=tau, noise=noise, total_stock=w.total_stock,
            robots=[dict(id=r.rid, cap=r.cap, eff=round(r.eff, 3),
                         sector=r.sector, company=r.company)
                    for r in w.robots])) + "\n")
        for _ in range(ticks):
            arm.tick()
            f.write(json.dumps(dict(
                type="tick", t=w.tick,
                r=[[r.pos[0], r.pos[1], round(r.battery, 1), r.load,
                    int(r.stranded)] for r in w.robots],
                stock=list(w.stock), delivered=w.delivered,
                co=[sum(r.delivered for r in w.robots if r.company == c)
                    for c in (0, 1)])) + "\n")
            while n_events < len(w.event_log):
                f.write(json.dumps(dict(type="xfer", **w.event_log[n_events])) + "\n")
                n_events += 1
            while n_deals < len(w.deal_log):
                d = w.deal_log[n_deals]
                f.write(json.dumps(dict(
                    type="deal", t=d["tick"], a=d["a"], b=d["b"], q=d["q"],
                    e=d["e"], s=d["s"], border=d.get("border", 0),
                    sa=round(d["sa"], 2), sb=round(d["sb"], 2),
                    capture=round(d["capture"], 3))) + "\n")
                n_deals += 1
            if w.delivered >= w.total_stock:
                break
    return dict(arm=arm_name, sigma=sigma, seed=seed, tau=tau, ticks=w.tick,
                delivered=w.delivered, deals=len(w.deal_log),
                xfers=len(w.event_log), path=out_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="snhp-hz")
    ap.add_argument("--sigma", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tau", type=float, default=0.0)
    ap.add_argument("--preset", default="v4")
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--ticks", type=int, default=2500)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(
        _HERE, "results",
        f"trace_{args.arm}_s{args.sigma:g}_t{args.tau:g}_seed{args.seed}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print(json.dumps(write_trace(args.arm, args.sigma, args.seed, args.ticks,
                                 out, tau=args.tau, preset=args.preset,
                                 noise=args.noise), indent=1))


if __name__ == "__main__":
    main()
