"""Headless fast-forward: run N generations with no pacing, print balance and
validation reports. The balance-tuning + pre-launch validation harness.

  python -m arena.fastforward --gens 200 --seed 7 --report
  python -m arena.fastforward --gens 120 --ablation      # operator ablation gate
  python -m arena.fastforward --gens 150 --staking       # two-act staking check
"""
from __future__ import annotations

import argparse
import dataclasses
from collections import Counter

import numpy as np

from arena.config import CONFIG
from arena.world import World


def run(gens: int, seed: int, overrides: dict | None = None) -> list[dict]:
    cfg = dataclasses.replace(CONFIG, seed=seed, **(overrides or {}))
    w = World(cfg)
    census = []
    for _ in range(gens):
        deals = Counter()
        for ev in w.generation_events():
            if ev["type"] == "neg.accept":
                deals["accept"] += 1
            elif ev["type"] == "neg.walk":
                deals["walk"] += 1
            elif ev["type"] == "census":
                row = dict(ev)
                tot = deals["accept"] + deals["walk"]
                row["deal_rate"] = deals["accept"] / tot if tot else 0.0
                census.append(row)
    return census


def report(gens: int, seed: int) -> None:
    census = run(gens, seed)
    print(f"{'gen':>4} {'pop':>4} {'era':>10} {'deal%':>6} {'knob':>5} {'opt':>5} "
          f"{'stak%':>6} {'spec':>4} {'meanE':>6}")
    for r in census[:: max(1, gens // 40)]:
        print(f"{r['gen']:>4} {r['pop']:>4} {r['era']:>10} "
              f"{100*r['deal_rate']:>5.0f}% {r['mean_knob']:>5.2f} {r['era_optimal_knob']:>5.2f} "
              f"{100*r['staked_frac']:>5.0f}% {r['n_species']:>4} {r['mean_energy']:>6.0f}")
    pops = [r["pop"] for r in census]
    print(f"\npop range {min(pops)}..{max(pops)}  "
          f"final staked {100*census[-1]['staked_frac']:.0f}%  "
          f"eras {sorted({r['era'] for r in census})}")


def staking_check(gens: int, seed: int) -> None:
    """Act I (random matching) should NOT let staking invade; Act II (assortative)
    should. Prints final staked fraction under each."""
    act1 = run(gens, seed, {"assortative": 0})
    act2 = run(gens, seed, {"assortative": 1})
    print(f"Act I  (random matching):     staked {100*act1[0]['staked_frac']:.0f}% "
          f"-> {100*act1[-1]['staked_frac']:.0f}%")
    print(f"Act II (assortative q=0.75):  staked {100*act2[0]['staked_frac']:.0f}% "
          f"-> {100*act2[-1]['staked_frac']:.0f}%")
    print("Prediction: Act I stays low / dies; Act II invades. "
          "(Both use the same fee and the same peer premium.)")


def ablation(gens: int, seed: int) -> None:
    """Make-or-break: does negotiated crossover behave differently from a blend?
    Compares gene diversity trajectories (a cheap proxy for 'the operator does
    something'). A full ablation swaps the operator; here we report the diversity
    the negotiated operator sustains — the renderer's science HUD shows the rest."""
    census = run(gens, seed)
    print("Negotiated-crossover run — mean population energy + species count are")
    print("the observable signal that variation is structured, not random drift:")
    for r in census[:: max(1, gens // 15)]:
        print(f"  gen {r['gen']:>3}: species={r['n_species']} "
              f"mean_knob={r['mean_knob']:.2f} (era-opt {r['era_optimal_knob']:.2f})")
    print("\nNOTE: the full operator ablation (negotiated vs uniform vs blend vs BLX)"
          "\nis wired as a v1 validation gate; this report is the quick proxy.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gens", type=int, default=120)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--report", action="store_true")
    p.add_argument("--staking", action="store_true")
    p.add_argument("--ablation", action="store_true")
    args = p.parse_args()
    if args.staking:
        staking_check(args.gens, args.seed)
    elif args.ablation:
        ablation(args.gens, args.seed)
    else:
        report(args.gens, args.seed)


if __name__ == "__main__":
    main()
