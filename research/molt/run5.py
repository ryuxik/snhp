"""Molt Season v5 — PREREG AMENDMENT 4, arms G and H, on INFERRED costs.

    python3 research/molt/run5.py

Arm G (selfish selection) gets nothing the shipped engine does not already
compute: `negotiate_bundle` runs, its particle filter infers the counterparty's
priorities from their offers, and the selection is made against THAT inference
and the tool's own `their_batna_estimate`. The employer's true cost function is
never read.

Arm H (the menu) perturbs the engine's model of the crab's own utility by
lognormal noise and asks whether handing the crab a short menu, chosen under the
noisy model, beats handing it one package — with the crab picking by its TRUE
preferences. The menu's value should be the estimation error it routes around,
so it must grow with the noise (K25, bidirectional).
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE)),
           os.path.join(os.path.dirname(os.path.dirname(_HERE)), "snhp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.arms3 import (OPTS, _pkg_from, crab_issues3, settle3, sitting_crab3,
                        slow_archetype3)
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (Package, Params3, Season, crab_cash3, crab_value3,
                     discloses3, works_npv3, works_packages3)
from molt.world import approval_days, opening_offer

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
ARCH = "Anchoring Bias"
SIGMAS = (0.0, 0.25, 0.50)
MENU_K = 3


def _norm01(a):
    a = np.asarray(a, float)
    lo, hi = a.min(), a.max()
    return np.full_like(a, 0.5) if hi - lo < 1e-12 else (a - lo) / (hi - lo)


def inferred_their_utility(issues, inferred, pool):
    """Rebuild the counterparty's utility for every package from ONLY what the
    engine reports: its inferred per-issue priorities, and the direction vectors
    the caller supplied. The true cost function is never touched."""
    per = {}
    for iss in issues:
        per[iss["name"]] = dict(zip(iss["options"], _norm01(iss["their_utility"])))
    w = {k: float(v) for k, v in (inferred or {}).items()}
    tot = sum(w.values()) or 1.0
    out = []
    for pk in pool:
        lab = pk.labels()
        s = 0.0
        for name, table in per.items():
            s += (w.get(name, 1.0 / max(len(per), 1)) / tot) * table.get(lab[name], 0.0)
        out.append(s)
    return np.asarray(out)


def engine_inference(p, c, sea, seed):
    """One engine call: its recommended package and its inferred read of the
    counterparty. Everything downstream uses only these."""
    from gametheory.negotiation.bundle import negotiate_bundle
    op = opening_offer(p, c)
    issues = crab_issues3(p, c, sea)
    prio = {i["name"]: 1.0 for i in issues}
    res = negotiate_bundle(issues=issues, their_offers=[op.labels()],
                           my_priorities=prio, my_batna=0.4,
                           their_batna_estimate=p.their_batna_estimate,
                           seed=seed, rounds_left=p.max_rounds)
    return res, issues, op


def arm_G(p, c, sea, seed):
    """SELFISH SELECTION on inferred costs — and the employer really decides.

    The first version of this arm selected a package and handed it straight to
    settle3, so the Works never got to refuse. That produced +$45k of fantasy.
    Here the crab proposes its selfish pick, the Works accepts or counters with
    the same rule it uses in every other arm, and a refused crab must lower its
    sights."""
    from molt.v3 import works_best_reply3, works_signs3
    res, issues, op = engine_inference(p, c, sea, seed)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    pool = works_packages3(p, sea, op)
    est = inferred_their_utility(issues, res.get("inferred_their_priorities"), pool)
    thresh = p.their_batna_estimate
    cur = op
    for _ in range(p.max_rounds):
        ok = [pk for pk, e in zip(pool, est)
              if e >= thresh and crab_value3(p, c, pk) > crab_value3(p, c, cur)]
        if not ok:
            break
        ask = max(ok, key=lambda pk: crab_value3(p, c, pk))
        reply = works_best_reply3(p, c, sea, bel, op, crab_value3(p, c, cur))
        if works_signs3(p, c, sea, bel, ask, cur, reply):
            cur = ask
            break
        if reply is None:
            break
        cur = reply                       # the Works' counter stands
        thresh = min(0.95, thresh + 0.15)  # refused: ask for less next time
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


def arm_H(p, c, sea, seed, sigma, rng, menu=True, tol=0.01):
    """The menu, presented by the EMPLOYER, under preference noise.

    Acceptance is not assumed away: the menu is drawn from packages inside a
    `tol` band of the employer's own settled payoff, so every item on it is one
    the Works would sign. Noise enters only through the employer's model of what
    the crab wants. menu=False is the single-package control -- the employer
    guesses; menu=True lets the crab point."""
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    base = sitting_crab3(p, c, sea, seed)          # the shipped engine's deal
    op = opening_offer(p, c)
    w_ref = works_npv3(p, c, sea, bel, base["pkg"])
    band = [pk for pk in works_packages3(p, sea, op)
            if works_npv3(p, c, sea, bel, pk) >= w_ref - tol * c.salary]
    if not band:
        return base
    noise = rng.lognormal(0.0, sigma, size=len(band)) if sigma > 0 \
        else np.ones(len(band))
    noisy = np.array([crab_value3(p, c, pk) for pk in band]) * noise
    short = [band[i] for i in np.argsort(-noisy)[:(MENU_K if menu else 1)]]
    best = max(short, key=lambda pk: crab_value3(p, c, pk))   # crab's TRUE pick
    return settle3(p, c, sea, best, 1.0 + approval_days(p, best, op), 1,
                   p.max_rounds, spoke)


def main(seeds=(7, 11, 23, 31), seasons=4, nc=40):
    out = {}
    acc = {k: {"u": [], "cash": [], "w": [], "left": []}
           for k in ("base_engine", "arm_G", "archetype")}
    for s in SIGMAS:
        acc[f"H_single_{s}"] = {"u": [], "cash": [], "w": [], "left": []}
        acc[f"H_menu_{s}"] = {"u": [], "cash": [], "w": [], "left": []}

    for seed in seeds:
        for key in list(acc):
            p = Params3(**P)
            rng = np.random.default_rng(seed)
            r3 = np.random.default_rng(seed + 99)
            nz = np.random.default_rng(seed + 777)
            for _ in range(seasons):
                sea0 = Season.draw(p, rng, nc)
                sea = copy.deepcopy(sea0)
                for i in range(nc):
                    c = draw_crab2(i, p, rng)
                    sd = seed * 1000 + i
                    if key == "base_engine":
                        r = sitting_crab3(p, c, sea, sd)
                    elif key == "arm_G":
                        r = arm_G(p, c, sea, sd)
                    elif key == "archetype":
                        r = slow_archetype3(p, c, sea, ARCH, "best_first", r3)
                    else:
                        kind, sig = key.split("_")[1], float(key.split("_")[2])
                        r = arm_H(p, c, sea, sd, sig, nz, menu=(kind == "menu"))
                    if r["pkg"].title and not r["left"]:
                        sea.slots_left -= 1
                    acc[key]["left"].append(1.0 if r["left"] else 0.0)
                    if not r["left"]:
                        acc[key]["u"].append(r["crab"])
                        acc[key]["cash"].append(r["cash"])
                        acc[key]["w"].append(r["works"])

    for k, v in acc.items():
        out[k] = {"utility": float(np.mean(v["u"])), "cash": float(np.mean(v["cash"])),
                  "works": float(np.mean(v["w"])), "left": float(np.mean(v["left"])),
                  "n": len(v["u"]),
                  "se": float(np.std(v["u"], ddof=1) / math.sqrt(len(v["u"])))}
    with open(os.path.join(_HERE, "results_v5.json"), "w") as fh:
        json.dump(out, fh, indent=1)

    b, g, a = out["base_engine"], out["arm_G"], out["archetype"]
    print(f"{'arm':26s}{'crab utility':>14}{'crab cash':>12}{'Works':>12}{'joint':>12}{'left%':>8}")
    for k, lab in (("archetype", "human archetype"),
                   ("base_engine", "engine (Nash, shipped)"),
                   ("arm_G", "arm G: selfish, INFERRED")):
        d = out[k]
        print(f"{lab:26s}{d['utility']:>14,.0f}{d['cash']:>12,.0f}{d['works']:>12,.0f}"
              f"{d['utility']+d['works']:>12,.0f}{100*d['left']:>8.1f}")
    BAR = 2253
    print(f"\nK23 selection is the defect: G - base = {g['utility']-b['utility']:+,.0f}"
          f"  -> {'FIRES (diagnosis wrong)' if g['utility']-b['utility'] < BAR else 'does not fire'}")
    print(f"K24 does the fix beat a person: G - human = {g['utility']-a['utility']:+,.0f}"
          f"  -> {'FIRES (still loses)' if g['utility'] < a['utility'] else 'does not fire'}")
    dj = (g['utility']+g['works']) - (b['utility']+b['works'])
    print(f"K26 what selfish costs: joint {dj:+,.0f}, Works {g['works']-b['works']:+,.0f}"
          f"  -> {'FIRES (extraction, not efficiency)' if dj < 0 else 'does not fire'}")
    print(f"\n{'preference noise':>18}{'single':>12}{'menu of 3':>12}{'menu edge':>12}")
    for s in SIGMAS:
        si, me = out[f"H_single_{s}"], out[f"H_menu_{s}"]
        print(f"{s:>18.2f}{si['utility']:>12,.0f}{me['utility']:>12,.0f}"
              f"{me['utility']-si['utility']:>+12,.0f}")
    e0 = out["H_menu_0.0"]["utility"] - out["H_single_0.0"]["utility"]
    e5 = out["H_menu_0.5"]["utility"] - out["H_single_0.5"]["utility"]
    print(f"\nK25 menu value is the noise: edge at sigma=0 {e0:+,.0f}, at sigma=.5 {e5:+,.0f}")
    print(f"    -> {'FIRES (menu worthless)' if e5 < BAR else 'does not fire'}"
          f"; {'ALSO FIRES (edge at zero noise)' if e0 > BAR else 'edge at zero noise is small, as required'}")


if __name__ == "__main__":
    main()
