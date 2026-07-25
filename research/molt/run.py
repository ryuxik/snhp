"""Molt Season — the harness.

    python research/molt/run.py            # main seeds + zero-clock + sweeps
    python research/molt/run.py --quick    # one seed, one season (smoke test)
    python research/molt/run.py --confirm  # the held-out seed, after freeze

Every arm sees the SAME crabs, drawn from the same seeded stream, with the same
taste shocks and the same meeting-delay draws (common random numbers), so arm
differences are paired and not sampling noise.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.arms import ARMS
from molt.world import Params, draw_crab

N_CRABS = 40
N_SEASONS = 12
MAIN_SEEDS = (7, 11, 23, 31)
CONFIRM_SEED = 101

FIELDS = ("crab", "works", "days", "meetings", "cash_paid", "concession",
          "mgr", "distraction", "replacement")


def run_cell(p: Params, seeds, n_crabs=N_CRABS, n_seasons=N_SEASONS):
    """Returns {arm: {field: np.array over crab-seasons}} — per-unit, so that
    paired differences between arms are available downstream."""
    out = {a: {f: [] for f in FIELDS} for a in ARMS}
    for a in ARMS:
        out[a]["agreed"] = []
        out[a]["left"] = []
        out[a]["walked"] = []
        out[a]["base_pct"] = []
        out[a]["title"] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for season in range(n_seasons):
            for i in range(n_crabs):
                c = draw_crab(i, p, rng)
                nseed = int(seed) * 100_000 + season * 100 + i
                for name, fn in ARMS.items():
                    r = fn(p, c, nseed)
                    for f in FIELDS:
                        out[name][f].append(r[f])
                    out[name]["agreed"].append(1.0 if r["agreed"] else 0.0)
                    out[name]["left"].append(1.0 if r["left"] else 0.0)
                    out[name]["walked"].append(1.0 if r["walked"] else 0.0)
                    from molt.world import BASE_PCT
                    out[name]["base_pct"].append(BASE_PCT[r["pkg"].base]
                                                 if r["agreed"] and not r["left"]
                                                 else 0.0)
                    out[name]["title"].append(1.0 if (r["pkg"].title and r["agreed"]
                                                      and not r["left"]) else 0.0)
    return {a: {f: np.asarray(v, dtype=float) for f, v in d.items()}
            for a, d in out.items()}


def summarise(cell: dict) -> dict:
    res = {}
    for a, d in cell.items():
        res[a] = {f: float(np.mean(v)) for f, v in d.items()}
        res[a]["joint"] = res[a]["crab"] + res[a]["works"]
        res[a]["n"] = int(len(d["crab"]))
    return res


def paired(cell: dict, a: str, b: str) -> dict:
    """a minus b, per crab-season, with a paired standard error."""
    out = {}
    for f in ("crab", "works", "days", "meetings", "cash_paid", "concession",
              "agreed", "left", "mgr", "distraction", "replacement"):
        d = cell[a][f] - cell[b][f]
        out[f] = float(np.mean(d))
        out[f + "_se"] = float(np.std(d, ddof=1) / math.sqrt(len(d)))
    dj = (cell[a]["crab"] + cell[a]["works"]) - (cell[b]["crab"] + cell[b]["works"])
    out["joint"] = float(np.mean(dj))
    out["joint_se"] = float(np.std(dj, ddof=1) / math.sqrt(len(dj)))
    return out


def mean_salary(seeds, p, n_crabs=N_CRABS, n_seasons=N_SEASONS) -> float:
    sal = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for _ in range(n_seasons):
            for i in range(n_crabs):
                sal.append(draw_crab(i, p, rng).salary)
    return float(np.mean(sal))


def cell_report(cell: dict) -> dict:
    pairs = {}
    for a in ARMS:
        if a != "A_sign":
            pairs[f"{a}-A_sign"] = paired(cell, a, "A_sign")
    for a in ("C_slow_engine", "D_sitting_crab", "E_sitting_works",
              "F_sitting_both"):
        pairs[f"{a}-B_slow"] = paired(cell, a, "B_slow")
    pairs["D_sitting_crab-C_slow_engine"] = paired(cell, "D_sitting_crab",
                                                   "C_slow_engine")
    return {"means": summarise(cell), "paired": pairs,
            "both_stay": both_stay(cell)}


def both_stay(cell: dict) -> dict:
    """The selection-free decomposition: restrict to crab-seasons the Works
    RETAINS under both B and D, so 'the Works paid more' is not just a different
    mix of crabs. (The rent study's K11 was pure selection; this is the guard.)"""
    keep = (cell["B_slow"]["left"] == 0.0) & (cell["D_sitting_crab"]["left"] == 0.0)
    out = {"n": int(keep.sum())}
    if not keep.any():
        return out
    for a in ("A_sign", "B_slow", "C_slow_engine", "D_sitting_crab",
              "E_sitting_works", "F_sitting_both"):
        out[a] = {f: float(np.mean(cell[a][f][keep]))
                  for f in ("crab", "concession", "cash_paid", "base_pct",
                            "title", "days", "mgr", "distraction")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.quick:
        seeds, ns, nc = (7,), 1, 20
        tag = "quick"
    elif args.confirm:
        seeds, ns, nc = (CONFIRM_SEED,), N_SEASONS, N_CRABS
        tag = "confirm"
    else:
        seeds, ns, nc = MAIN_SEEDS, N_SEASONS, N_CRABS
        tag = "main"

    t0 = time.time()
    report = {"tag": tag, "seeds": list(seeds), "n_crabs": nc,
              "n_seasons": ns, "mean_salary": mean_salary(seeds, Params(), nc, ns)}

    print(f"[{tag}] clock ON ...", flush=True)
    on = run_cell(Params(clock=True), seeds, nc, ns)
    report["clock_on"] = cell_report(on)

    print(f"[{tag}] clock OFF (zero-clock condition, PREREG §0) ...", flush=True)
    off = run_cell(Params(clock=False), seeds, nc, ns)
    report["clock_off"] = cell_report(off)

    if tag == "main":
        sweeps = {}
        grid = [("rho_mult", (0.5, 1.0, 1.5)),
                ("peer_spill", (0.0, 0.15, 0.30, 0.60)),
                ("dirichlet", (0.8, 1.4, 4.0)),
                ("distraction", (0.0, 0.04, 0.08, 0.16)),
                ("meet_delay_med", (4.5, 9.0, 18.0)),
                ("hazard_day", (0.0045, 0.009, 0.018)),
                ("counter_thresh", (0.0, 0.005, 0.02))]
        for key, vals in grid:
            for v in vals:
                print(f"[sweep] {key}={v} ...", flush=True)
                p = Params(**{key: v})
                cell = run_cell(p, (7,), nc, ns)
                sweeps[f"{key}={v}"] = cell_report(cell)
        report["sweeps"] = sweeps

        # EXPLORATORY, added after K6 fired. Two-way identification of where the
        # gains from trade come from: differences in relative price BETWEEN THE
        # SIDES, or differences BETWEEN CRABS. Clock off, so the time channel
        # cannot contaminate it.
        ident = {}
        for flat in (False, True):
            for alpha in (1.4, 4.0):
                key = f"flat={flat},alpha={alpha}"
                print(f"[ident] {key} ...", flush=True)
                p = Params(clock=False, flat_prices=flat, dirichlet=alpha)
                ident[key] = cell_report(run_cell(p, (7,), nc, ns))
        report["identification"] = ident

    out = args.out or os.path.join(_HERE, f"results_{tag}.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=1)
    print(f"wrote {out} in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
