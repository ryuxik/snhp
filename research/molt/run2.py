"""Molt Season v2 harness — PREREG AMENDMENT 1.

    python research/molt/run2.py            # main seeds, both credibility regimes
    python research/molt/run2.py --quick
    python research/molt/run2.py --confirm

Compute decision, disclosed rather than silent (A1.4 said "all 19 run"): all 19
archetypes are run at `best_first`, the ordering the SNHP claim must beat. The
six REPORTED archetypes are additionally run at `money_first` and `random`. That
is 31 slow arms per crab-season instead of 57, and it costs nothing that any kill
depends on — K9 needs the six at three orderings, K12 needs all nineteen at one.

The zero-clock condition re-scores the SAME negotiations rather than re-running
them: turning the clock off changes what the calendar costs, never what was
agreed. The v1 test suite pins that invariant and `tests/test_v2.py` re-pins it.
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

from molt.arms2 import (REPORTED_ARCHETYPES, arm_sign, resettle, sitting_crab,
                        sitting_works, slow_archetype)
from molt.v2 import Params2, draw_crab2, solve_tau

N_CRABS = 40
N_SEASONS = 12
MAIN_SEEDS = (7, 11, 23, 31)
CONFIRM_SEED = 101
ORDERINGS = ("money_first", "random", "best_first")

FIELDS = ("crab", "works", "days", "meetings", "exchanges", "cash_paid",
          "concession", "mgr", "distraction", "replacement")
FLAGS = ("agreed", "left", "walked", "disclosed")


def all_archetypes():
    from b2b_opponents import B2B_OPPONENTS
    return sorted(B2B_OPPONENTS)


def arm_names():
    names = ["A_sign", "D_sitting_crab", "E_sitting_works",
             "K10_disclose", "K10_silent"]
    for a in all_archetypes():
        names.append(f"B|{a}|best_first")
    for a in REPORTED_ARCHETYPES:
        for o in ("money_first", "random"):
            names.append(f"B|{a}|{o}")
    return names


def run_one(args):
    """One (seed, credibility) cell. Returns per-crab-season arrays for both
    clock conditions."""
    seed, cred, tau, n_crabs, n_seasons = args
    p_on = Params2(credibility=cred, disclose_tau=tau, clock=True)
    p_off = Params2(credibility=cred, disclose_tau=tau, clock=False)
    names = arm_names()
    on = {a: {f: [] for f in FIELDS + FLAGS + ("match",)} for a in names}
    off = {a: {f: [] for f in FIELDS + FLAGS + ("match",)} for a in names}

    rng = np.random.default_rng(seed)
    ordrng = np.random.default_rng(seed + 500_000)
    for season in range(n_seasons):
        for i in range(n_crabs):
            c = draw_crab2(i, p_on, rng)
            nseed = int(seed) * 100_000 + season * 100 + i
            rows = {
                "A_sign": arm_sign(p_on, c),
                "D_sitting_crab": sitting_crab(p_on, c, nseed),
                "E_sitting_works": sitting_works(p_on, c, nseed),
                "K10_disclose": sitting_crab(p_on, c, nseed, force_disclose=True),
                "K10_silent": sitting_crab(p_on, c, nseed, force_disclose=False),
            }
            for a in all_archetypes():
                rows[f"B|{a}|best_first"] = slow_archetype(
                    p_on, c, a, "best_first", ordrng)
            for a in REPORTED_ARCHETYPES:
                for o in ("money_first", "random"):
                    rows[f"B|{a}|{o}"] = slow_archetype(p_on, c, a, o, ordrng)
            for name, r in rows.items():
                _push(on[name], r, c)
                _push(off[name], resettle(p_off, c, r), c)
    return {"on": _arr(on), "off": _arr(off)}


def _push(d, r, c):
    for f in FIELDS:
        d[f].append(r[f])
    for f in FLAGS:
        d[f].append(1.0 if r[f] else 0.0)
    d["match"].append(c.match)


def _arr(d):
    return {a: {f: np.asarray(v, float) for f, v in x.items()}
            for a, x in d.items()}


def merge(cells):
    out = {}
    for cond in ("on", "off"):
        acc = {}
        for cell in cells:
            for a, d in cell[cond].items():
                if a not in acc:
                    acc[a] = {f: [] for f in d}
                for f, v in d.items():
                    acc[a][f].append(v)
        out[cond] = {a: {f: np.concatenate(v) for f, v in d.items()}
                     for a, d in acc.items()}
    return out


def paired(cell, a, b):
    o = {}
    for f in ("crab", "works", "days", "concession", "left", "agreed",
              "cash_paid", "exchanges"):
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
    names = [a for a in cell if a != "A_sign"]
    pr = {f"{a}-A_sign": paired(cell, a, "A_sign") for a in names}
    # every slow arm against the engine arm — the comparison the kills read
    for a in [x for x in cell if x.startswith("B|")]:
        pr[f"D_sitting_crab-{a}"] = paired(cell, "D_sitting_crab", a)
    pr["K10_disclose-K10_silent"] = paired(cell, "K10_disclose", "K10_silent")
    # K11: does the private match value move what the Works pays?
    keep = cell["D_sitting_crab"]["left"] == 0.0
    mt, cn = cell["D_sitting_crab"]["match"][keep], \
        cell["D_sitting_crab"]["concession"][keep]
    k11 = float(np.corrcoef(_rank(mt), _rank(cn))[0, 1]) if keep.sum() > 10 else 0.0
    # K11 diagnostic: does the match matter only among crabs with no visible
    # outside offer? Reported alongside the headline correlation.
    no_off = keep & (cell["D_sitting_crab"]["disclosed"] == 0.0)
    k11b = float(np.corrcoef(_rank(cell["D_sitting_crab"]["match"][no_off]),
                             _rank(cell["D_sitting_crab"]["concession"][no_off]))[0, 1]) \
        if no_off.sum() > 10 else 0.0
    # the selection-free decomposition: crab-seasons retained under BOTH the
    # engine arm and each reported slow arm
    bs = {}
    for arch in REPORTED_ARCHETYPES:
        a = f"B|{arch}|best_first"
        if a not in cell:
            continue
        k = (cell["D_sitting_crab"]["left"] == 0.0) & (cell[a]["left"] == 0.0)
        if k.sum() < 10:
            continue
        bs[arch] = {"n": int(k.sum())}
        for nm in ("D_sitting_crab", a, "A_sign"):
            bs[arch][nm if nm != a else "slow"] = {
                f: float(np.mean(cell[nm][f][k]))
                for f in ("crab", "concession", "cash_paid", "days")}
    return {"means": m, "paired": pr, "k11_rank_corr": k11,
            "k11_n": int(keep.sum()), "k11_no_offer_corr": k11b,
            "k11_no_offer_n": int(no_off.sum()), "both_stay": bs}


def _rank(a):
    o = np.argsort(np.argsort(a))
    return o.astype(float)


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

    for cred in ("verifiable", "unverifiable"):
        tau = solve_tau(Params2(credibility=cred))
        out[f"tau_{cred}"] = tau
        print(f"[{tag}/{cred}] tau={tau:.4f}; running {len(seeds)} seeds ...",
              flush=True)
        jobs = [(s, cred, tau, nc, ns) for s in seeds]
        with Pool(min(len(jobs), 4)) as pool:
            cells = pool.map(run_one, jobs)
        merged = merge(cells)
        out[cred] = {"clock_on": report(merged["on"]),
                     "clock_off": report(merged["off"])}
        sal = []
        rng = np.random.default_rng(seeds[0])
        for _ in range(ns):
            for i in range(nc):
                sal.append(draw_crab2(i, Params2(), rng).salary)
        out["mean_salary"] = float(np.mean(sal))

    path = args.out or os.path.join(_HERE, f"results_v2_{tag}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
