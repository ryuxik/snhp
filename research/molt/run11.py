"""Molt Season v11 — PREREG AMENDMENT 8. K44..K47.

    python3 research/molt/run11.py

The first cross-season link in the study: the same crab, two molt seasons. If a
menu reveals the employer's slack, that knowledge has to cost the employer
somewhere, and next year is where.
"""
from __future__ import annotations

import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE)),
           os.path.join(os.path.dirname(os.path.dirname(_HERE)), "snhp"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.arms3 import arm_sign3, settle3
from molt.v2 import Belief, draw_crab2, prior, update
from molt.v3 import (Package, Params3, Season, crab_value3, discloses3,
                     p_leave_true3, replacement_cost, works_npv3,
                     works_packages3)
from molt.world import approval_days, opening_offer

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
TOL, K = 0.01, 3
BAR = 2253


def offer(p, c, sea, floor_value, as_menu):
    """One season's offer. Returns (settled row, the top of the band the crab
    was shown — which is what leaks if it saw a menu)."""
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    pool = [pk for pk in works_packages3(p, sea, op)
            if crab_value3(p, c, pk) >= floor_value - 1e-9]
    if not pool:
        r = arm_sign3(p, c, sea)
        return r, crab_value3(p, c, r["pkg"])
    star = max(pool, key=lambda pk: works_npv3(p, c, sea, bel, pk))
    w = works_npv3(p, c, sea, bel, star)
    band = [pk for pk in pool
            if works_npv3(p, c, sea, bel, pk) >= w - TOL * c.salary]
    if as_menu:
        short = sorted(band, key=lambda pk: -crab_value3(p, c, pk))[:K]
        chosen = max(short, key=lambda pk: crab_value3(p, c, pk))
        # what the crab now knows the employer will sign
        leak = max(crab_value3(p, c, pk) for pk in short)
    else:
        chosen = star
        leak = crab_value3(p, c, star)
    row = settle3(p, c, sea, chosen, 1.0 + approval_days(p, chosen, op), 1, 1, spoke)
    return row, leak


def two_seasons(p, seeds, as_menu, leak_on, precedent=0.0, nc=40):
    """Same crab, two molt seasons. With `leak_on`, what the crab saw last year
    becomes the floor it starts from this year."""
    firm, emp, coll = [], [], []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        crabs = [draw_crab2(i, p, rng) for i in range(nc)]
        s1 = Season.draw(p, rng, nc)
        s2 = Season.draw(p, rng, nc)
        sa, sb = copy.deepcopy(s1), copy.deepcopy(s2)
        rng2 = np.random.default_rng(seed + 4242)
        for c in crabs:
            r1, leak = offer(p, c, sa, crab_value3(p, c, opening_offer(p, c)), as_menu)
            if r1["pkg"].title and not r1["left"]:
                sa.slots_left -= 1
            # next year: a new outside offer, and possibly a memory
            c2 = copy.deepcopy(c)
            c2.has_outside = bool(rng2.random() < min(0.95, c.spec.p_out * (0.55 + 0.9 * c.perf)))
            c2.omega = float(max(-0.02, rng2.normal(0.12 + p.omega_q_load * c.quality, 0.06)))
            c2.u_taste = float(rng2.random())
            saw_band = leak_on and (as_menu or rng2.random() < precedent)
            floor2 = leak if saw_band else crab_value3(p, c2, opening_offer(p, c2))
            r2, _ = offer(p, c2, sb, floor2, as_menu)
            if r2["pkg"].title and not r2["left"]:
                sb.slots_left -= 1
            firm.append(r1["works"] + r2["works"])
            emp.append((r1["crab"] if not r1["left"] else 0)
                       + (r2["crab"] if not r2["left"] else 0))
            coll.append((r1["left"] + r2["left"]) / 2.0)
    return (float(np.mean(firm)), float(np.mean(emp)), float(np.mean(coll)))


def belief_vs_truth(p, seeds, nc=40):
    """K47. The employer decides on a belief; the world resolves on the truth.
    Does knowing the truth actually make the firm better off?"""
    out = {"belief": [], "truth": []}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for _ in range(2):
            sea = copy.deepcopy(Season.draw(p, rng, nc))
            for i in range(nc):
                c = draw_crab2(i, p, rng)
                op = opening_offer(p, c)
                spoke = discloses3(p, c, sea)
                b_est = update(p, c, prior(p, c), spoke)
                grid = np.array([c.omega])
                b_true = Belief(1.0 if c.has_outside else 0.0, grid, np.ones(1))
                for tag, bel in (("belief", b_est), ("truth", b_true)):
                    pool = works_packages3(p, sea, op)
                    star = max(pool, key=lambda pk: works_npv3(p, c, sea, bel, pk))
                    r = settle3(p, c, sea, star,
                                1.0 + approval_days(p, star, op), 1, 1, spoke)
                    out[tag].append(r["works"])
    return {k: float(np.mean(v)) for k, v in out.items()}


def main():
    p = Params3(**P)
    seeds = (7, 11, 23, 31, 101)
    print(f"{'employer policy':34s}{'firm (2 seasons)':>19}{'employee':>12}{'collapse':>11}")
    rows = {}
    for lab, menu, leak, prec in (
            ("single package, no leak", False, False, 0.0),
            ("MENU, no leak (the v7 world)", True, False, 0.0),
            ("MENU, band leaks to next year", True, True, 0.0),
            ("single, but precedent 50%", False, True, 0.5),
            ("MENU, band leaks + precedent 50%", True, True, 0.5)):
        f, e, cl = two_seasons(p, seeds, menu, leak, prec)
        rows[lab] = (f, e, cl)
        print(f"{lab:34s}{f:>19,.0f}{e:>12,.0f}{100*cl:>10.1f}%")

    base = rows["single package, no leak"][0]
    leaky = rows["MENU, band leaks to next year"][0]
    d44 = leaky - base
    print(f"\nK44 DOES THE BAND EXPLAIN IT?  employer, menu-with-leak vs single = {d44:+,.0f}")
    print(f"    -> {'FIRES: revealing the band costs the employer more than the menu saves' if d44 < -BAR else 'does not fire'}")

    prec_cost = rows["MENU, band leaks + precedent 50%"][0] - leaky
    print(f"K45 DOES PRECEDENT EXPLAIN IT?  adding 50% precedent costs the employer {prec_cost:+,.0f}")
    print(f"    -> {'FIRES' if prec_cost < -BAR else 'does not fire'}")

    if d44 >= -BAR and prec_cost >= -BAR:
        print("K46 NO MODELLED REASON: neither band secrecy nor precedent explains it. "
              "-> FIRES. The article must say the puzzle is unexplained.")
    else:
        print("K46 -> does not fire; a mechanism was found.")

    bt = belief_vs_truth(p, seeds)
    d47 = bt["truth"] - bt["belief"]
    print(f"\nK47 THE BELIEF ANOMALY  firm payoff: deciding on a belief {bt['belief']:,.0f} "
          f"vs on the truth {bt['truth']:,.0f} = {d47:+,.0f}")
    print(f"    -> {'FIRES: knowing the truth makes the firm WORSE off; the belief model is mis-specified' if d47 < 0 else 'does not fire: information helps the firm, as it should'}")
    json.dump({"two_season": rows, "belief_vs_truth": bt},
              open(os.path.join(_HERE, "results_v11.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
