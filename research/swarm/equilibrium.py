"""v4.1 price formation (SPEC.md v4.1): the revenue-maximizing posted tariff
per fleet type, plus the separability probe.

    python research/swarm/equilibrium.py

Each company's tariff is only paid by the OTHER fleet, so demand at a
refinery depends on its own τ alone — pricing separates into two symmetric
monopoly problems (P8d probes this). We sweep symmetric τ, measure mean
per-company tariff revenue, and locate τ* per fleet type and σ.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from swarm.run import run_once

TAU_GRID = [0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.25, 0.35, 0.50]
FLEETS = ["null", "snhp-hz"]
SIGMAS = [0.0, 0.5]
PROBE_TAU1 = 0.50           # separability probe: opponent pinned here


def _star(kw):
    return run_once(**kw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--probe-seeds", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default=os.path.join(_HERE, "results", "equilibrium_v41.json"))
    args = ap.parse_args()

    jobs = []
    for fleet in FLEETS:
        for sigma in SIGMAS:
            for tau in TAU_GRID:
                for seed in range(args.seeds):
                    jobs.append(dict(arm_name=fleet, sigma=sigma, seed=seed,
                                     tau=(tau, tau)))
    # separability probe (null fleet, σ=0.5): own τ swept, opponent pinned
    for tau in TAU_GRID[:8]:
        for seed in range(args.probe_seeds):
            jobs.append(dict(arm_name="null", sigma=0.5, seed=seed,
                             tau=(tau, PROBE_TAU1)))

    with Pool(args.jobs) as pool:
        rows = pool.map(_star, jobs)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=1)
    print(f"{len(rows)} runs → {args.out}\n")

    # ── revenue curves ──────────────────────────────────────────────────
    print(f"{'fleet':<10} {'σ':>5} {'τ':>6} {'revenue/co':>11} {'foreignRef':>11} "
          f"{'delivered':>10} {'dlvMid':>7}")
    print("-" * 66)
    curves = {}
    for fleet in FLEETS:
        for sigma in SIGMAS:
            for tau in TAU_GRID:
                g = [r for r in rows if r["arm"] == fleet and r["sigma"] == sigma
                     and r["tau"] == tau and r["tau1"] == tau]
                if not g:
                    continue
                rev = np.mean([np.mean(r["co_tariffs"]) for r in g])
                fr = np.mean([r["foreign_refined"] for r in g])
                dv = np.mean([r["delivered"] for r in g])
                dm = np.mean([r["delivered_mid"] for r in g])
                curves.setdefault((fleet, sigma), []).append((tau, rev))
                print(f"{fleet:<10} {sigma:>5.2f} {tau:>6.3f} {rev:>11.1f} "
                      f"{fr:>11.1f} {dv:>10.1f} {dm:>7.1f}")

    print("\nτ* (revenue-maximizing posted tariff) per fleet type:")
    for (fleet, sigma), pts in sorted(curves.items()):
        taus, revs = zip(*pts)
        i = int(np.argmax(revs))
        interior = 0 < i < len(taus) - 1
        print(f"  {fleet:<10} σ={sigma:0.2f}  τ*={taus[i]:.3f}  "
              f"revenue={revs[i]:.1f}  "
              f"{'INTERIOR' if interior else 'BOUNDARY'}")

    # ── separability probe ──────────────────────────────────────────────
    print(f"\nseparability probe (null, σ=0.5): R0(τ0) with τ1={PROBE_TAU1} "
          f"vs τ1=τ0 (company-0 revenue only):")
    for tau in TAU_GRID[:8]:
        sym = [r["co_tariffs"][0] for r in rows
               if r["arm"] == "null" and r["sigma"] == 0.5
               and r["tau"] == tau and r["tau1"] == tau and r["seed"] < args.probe_seeds]
        pin = [r["co_tariffs"][0] for r in rows
               if r["arm"] == "null" and r["sigma"] == 0.5
               and r["tau"] == tau and r["tau1"] == PROBE_TAU1]
        if sym and pin:
            print(f"  τ0={tau:0.3f}   R0|sym={np.mean(sym):7.1f}   "
                  f"R0|pinned={np.mean(pin):7.1f}   Δ={np.mean(pin)-np.mean(sym):+6.1f}")


if __name__ == "__main__":
    main()
