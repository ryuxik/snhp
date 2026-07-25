"""Molt Season v3 harness — PREREG AMENDMENT 2.

    python research/molt/run3.py            # main seeds, both credibility regimes
    python research/molt/run3.py --quick
    python research/molt/run3.py --confirm

Every arm reports CASH beside utility (A2.4). The perk-rate sweep runs on seed 7
and reports the break-even multiplier as a headline number (K16).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT, os.path.join(_ROOT, "snhp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.arms3 import (REPORTED_ARCHETYPES, arm_sign3, sitting_crab3,
                        sitting_works3, slow_archetype3)
from molt.v2 import draw_crab2
from molt.v3 import Params3, Season, solve_tau3

N_CRABS = 40
N_SEASONS = 12
MAIN_SEEDS = (7, 11, 23, 31)
CONFIRM_SEED = 101
PERK_RATES = (0.5, 0.75, 1.0, 1.25, 1.5)

FIELDS = ("crab", "cash", "works", "days", "exchanges", "concession", "mgr",
          "distraction", "replacement", "match")
FLAGS = ("agreed", "left", "walked", "disclosed", "granted_title",
         "granted_berth", "granted_deep", "granted_pto")


def all_archetypes():
    from b2b_opponents import B2B_OPPONENTS
    return sorted(B2B_OPPONENTS)


def arm_names():
    n = ["A_sign", "D_sitting_crab", "E_sitting_works", "E_biased",
         "K10_disclose", "K10_silent"]
    n += [f"B|{a}|best_first" for a in all_archetypes()]
    n += [f"B|{a}|{o}" for a in REPORTED_ARCHETYPES
          for o in ("money_first", "random")]
    return n


def run_one(args):
    seed, cred, tau, nc, ns, rate = args
    p_on = Params3(credibility=cred, disclose_tau=tau, clock=True, perk_rate=rate)
    p_off = Params3(credibility=cred, disclose_tau=tau, clock=False, perk_rate=rate)
    names = arm_names()
    on = {a: {f: [] for f in FIELDS + FLAGS} for a in names}
    off = {a: {f: [] for f in FIELDS + FLAGS} for a in names}
    rng = np.random.default_rng(seed)
    ordrng = np.random.default_rng(seed + 500_000)
    for season in range(ns):
        sea = Season.draw(p_on, rng)
        for i in range(nc):
            c = draw_crab2(i, p_on, rng)
            s = int(seed) * 100_000 + season * 100 + i
            rows = {
                "A_sign": arm_sign3(p_on, c, sea),
                "D_sitting_crab": sitting_crab3(p_on, c, sea, s),
                "E_sitting_works": sitting_works3(p_on, c, sea, s),
                "E_biased": sitting_works3(p_on, c, sea, s, biased=True),
                "K10_disclose": sitting_crab3(p_on, c, sea, s, force_disclose=True),
                "K10_silent": sitting_crab3(p_on, c, sea, s, force_disclose=False),
            }
            for a in all_archetypes():
                rows[f"B|{a}|best_first"] = slow_archetype3(
                    p_on, c, sea, a, "best_first", ordrng)
            for a in REPORTED_ARCHETYPES:
                for o in ("money_first", "random"):
                    rows[f"B|{a}|{o}"] = slow_archetype3(p_on, c, sea, a, o, ordrng)
            for name, r in rows.items():
                _push(on[name], r)
                _push(off[name], _resettle(p_off, c, sea, r))
    return {"on": _arr(on), "off": _arr(off)}


def _resettle(p_off, c, sea, row):
    from molt.arms3 import settle3
    return settle3(p_off, c, sea, row["pkg"], 1.0, row["meetings"],
                   row["exchanges"], row["disclosed"])


def _push(d, r):
    for f in FIELDS:
        d[f].append(r[f])
    for f in FLAGS:
        d[f].append(1.0 if r[f] else 0.0)


def _arr(d):
    return {a: {f: np.asarray(v, float) for f, v in x.items()}
            for a, x in d.items()}


def merge(cells):
    out = {}
    for cond in ("on", "off"):
        acc = {}
        for cell in cells:
            for a, d in cell[cond].items():
                acc.setdefault(a, {f: [] for f in d})
                for f, v in d.items():
                    acc[a][f].append(v)
        out[cond] = {a: {f: np.concatenate(v) for f, v in d.items()}
                     for a, d in acc.items()}
    return out


def paired(cell, a, b):
    o = {}
    for f in ("crab", "cash", "works", "days", "concession", "left", "agreed"):
        d = cell[a][f] - cell[b][f]
        o[f] = float(np.mean(d))
        o[f + "_se"] = float(np.std(d, ddof=1) / math.sqrt(len(d)))
    dj = (cell[a]["crab"] + cell[a]["works"]) - (cell[b]["crab"] + cell[b]["works"])
    o["joint"] = float(np.mean(dj))
    o["joint_se"] = float(np.std(dj, ddof=1) / math.sqrt(len(dj)))
    return o


def means(cell):
    out = {}
    for a, d in cell.items():
        out[a] = {f: float(np.mean(v)) for f, v in d.items()}
        out[a]["joint"] = out[a]["crab"] + out[a]["works"]
        out[a]["n"] = int(len(d["crab"]))
    return out


def report(cell):
    m = means(cell)
    pr = {f"{a}-A_sign": paired(cell, a, "A_sign") for a in cell if a != "A_sign"}
    for a in [x for x in cell if x.startswith("B|")]:
        pr[f"D_sitting_crab-{a}"] = paired(cell, "D_sitting_crab", a)
    pr["K10_disclose-K10_silent"] = paired(cell, "K10_disclose", "K10_silent")
    pr["E_biased-E_sitting_works"] = paired(cell, "E_biased", "E_sitting_works")
    bs = {}
    for arch in REPORTED_ARCHETYPES:
        a = f"B|{arch}|best_first"
        if a not in cell:
            continue
        k = (cell["D_sitting_crab"]["left"] == 0.0) & (cell[a]["left"] == 0.0)
        if k.sum() < 10:
            continue
        bs[arch] = {"n": int(k.sum())}
        for nm, lab in ((("D_sitting_crab"), "sitting"), (a, "slow"),
                        ("A_sign", "sign")):
            bs[arch][lab] = {f: float(np.mean(cell[nm][f][k]))
                             for f in ("crab", "cash", "concession", "days",
                                       "granted_title", "granted_pto",
                                       "granted_berth", "granted_deep")}
    return {"means": m, "paired": pr, "both_stay": bs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.quick:
        seeds, ns, nc, tag = (7,), 1, 20, "quick"
    elif args.confirm:
        seeds, ns, nc, tag = (CONFIRM_SEED,), N_SEASONS, N_CRABS, "confirm"
    else:
        seeds, ns, nc, tag = MAIN_SEEDS, N_SEASONS, N_CRABS, "main"

    out = {"tag": tag, "seeds": list(seeds), "n_crabs": nc, "n_seasons": ns,
           "archetypes": all_archetypes(),
           "reported_archetypes": list(REPORTED_ARCHETYPES)}
    sal = []
    rng = np.random.default_rng(seeds[0])
    for _ in range(ns):
        for i in range(nc):
            sal.append(draw_crab2(i, Params3(), rng).salary)
    out["mean_salary"] = float(np.mean(sal))

    for cred in ("verifiable", "unverifiable"):
        tau = solve_tau3(Params3(credibility=cred))
        out[f"tau_{cred}"] = tau
        print(f"[{tag}/{cred}] tau={tau:.4f} ...", flush=True)
        jobs = [(s, cred, tau, nc, ns, 1.0) for s in seeds]
        with Pool(min(len(jobs), 4)) as pool:
            cells = pool.map(run_one, jobs)
        merged = merge(cells)
        out[cred] = {"clock_on": report(merged["on"]),
                     "clock_off": report(merged["off"])}

    if tag == "main":
        # K16: the break-even on the exchange rate, as a headline
        sweep = {}
        for rate in PERK_RATES:
            print(f"[perk_rate {rate}] ...", flush=True)
            cells = [run_one((7, "verifiable", out["tau_verifiable"], nc, ns, rate))]
            merged = merge(cells)
            sweep[str(rate)] = {"clock_on": report(merged["on"]),
                                "clock_off": report(merged["off"])}
        out["perk_sweep"] = sweep

    path = args.out or os.path.join(_HERE, f"results_v3_{tag}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
