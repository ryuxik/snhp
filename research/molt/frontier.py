"""Where on the Pareto frontier does each arm land?

EXPLORATORY, post-hoc, run after v4 in response to the question: "doesn't that
just mean the engine bargains over a different utility function — aren't we
landing on a different point of the frontier, or playing a different game?"

The first half is checkable in code and the answer is no: `slow_archetype3`
scores the crab with `crab_value3` (arms3.py:168) and `crab_issues3` hands
`negotiate_bundle` the same `crab_value3` (arms3.py:73). Identical objective.

So this measures the second half. For every crab-season, enumerate the package
space, compute (crab utility, Works NPV) for each, find the Pareto frontier, and
locate both arms' agreed packages on it.

    python3 research/molt/frontier.py
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE)),
           os.path.join(os.path.dirname(os.path.dirname(_HERE)), "snhp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.arms3 import sitting_crab3, slow_archetype3
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (Params3, Season, crab_cash3, crab_value3, discloses3,
                     works_npv3, works_packages3)
from molt.world import opening_offer

ARCH = "Anchoring Bias"          # the strongest slow opponent in v4


def pareto(pts):
    return {i for i, (u, w) in enumerate(pts)
            if not any((u2 >= u and w2 >= w and (u2 > u or w2 > w))
                       for u2, w2 in pts)}


def main(seeds=(7, 11, 23), seasons=3, n_crabs=40):
    p = Params3(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
                disclose_tau=0.0322)
    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        r3 = np.random.default_rng(seed + 99)
        for _ in range(seasons):
            sea0 = Season.draw(p, rng, n_crabs)
            seaE, seaA = copy.deepcopy(sea0), copy.deepcopy(sea0)
            for i in range(n_crabs):
                c = draw_crab2(i, p, rng)
                e = sitting_crab3(p, c, seaE, i)
                a = slow_archetype3(p, c, seaA, ARCH, "best_first", r3)
                for r, sea in ((e, seaE), (a, seaA)):
                    if r["pkg"].title and not r["left"]:
                        sea.slots_left -= 1
                if e["left"] or a["left"]:
                    continue
                bel = update(p, c, prior(p, c), discloses3(p, c, sea0))
                pkgs = works_packages3(p, sea0, opening_offer(p, c))
                pts = [(crab_value3(p, c, pk), works_npv3(p, c, sea0, bel, pk))
                       for pk in pkgs]
                fr = pareto(pts)
                best_joint = max(u + w for u, w in pts)
                out = {}
                for name, r in (("engine", e), ("archetype", a)):
                    u = crab_value3(p, c, r["pkg"])
                    w = works_npv3(p, c, sea0, bel, r["pkg"])
                    on = any(abs(pts[j][0] - u) < 1e-6 and abs(pts[j][1] - w) < 1e-6
                             for j in fr)
                    out[name] = dict(u=u, w=w, on=on, gap=best_joint - (u + w),
                                     cash=crab_cash3(p, c, r["pkg"]))
                rows.append(out)

    print(f"n = {len(rows)} crab-seasons in which both arms retained the crab\n")
    print(f"{'':12s}{'crab utility':>14}{'crab cash':>12}{'Works NPV':>12}"
          f"{'on frontier':>13}")
    for name in ("archetype", "engine"):
        v = [r[name] for r in rows]
        print(f"{name:12s}{np.mean([x['u'] for x in v]):>14,.0f}"
              f"{np.mean([x['cash'] for x in v]):>12,.0f}"
              f"{np.mean([x['w'] for x in v]):>12,.0f}"
              f"{100*np.mean([x['on'] for x in v]):>12.0f}%")
    du = np.mean([r["engine"]["u"] - r["archetype"]["u"] for r in rows])
    dc = np.mean([r["engine"]["cash"] - r["archetype"]["cash"] for r in rows])
    dw = np.mean([r["engine"]["w"] - r["archetype"]["w"] for r in rows])
    se = np.std([r["engine"]["u"] - r["archetype"]["u"] for r in rows],
                ddof=1) / np.sqrt(len(rows))
    print(f"\nengine - archetype:  utility {du:+,.0f} +/-{se:,.0f}   "
          f"cash {dc:+,.0f}   Works {dw:+,.0f}   joint {du+dw:+,.0f}")
    if abs(du + dw) > 1:
        print(f"of the joint gain the engine finds, the employer takes "
              f"{100*dw/(du+dw):.0f}%")
    print(f"both arms Pareto-efficient in the same crab-season: "
          f"{100*np.mean([r['engine']['on'] and r['archetype']['on'] for r in rows]):.0f}%")


if __name__ == "__main__":
    main()
