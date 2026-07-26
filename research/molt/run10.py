"""Molt Season v10 — PREREG AMENDMENT 7. A manager stands between the firm and
the crab, and negotiates on their own incentives.

    python3 research/molt/run10.py

Every negotiating decision is made on the MANAGER's payoff; everything reported is
the FIRM's. The gap is the mechanism.
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

from molt.arms2 import WorksSeat, _norm
from molt.arms3 import OPTS, _order3, settle3, arm_sign3
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (BASE_PCT, BONUS_MO, PVF, Package, Params3, Season,
                     crab_cash3, crab_value3, discloses3, p_leave_belief3,
                     replacement_cost, works_cost3, works_npv3, works_packages3)
from molt.world import approval_days, opening_offer, outside_value

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
ARCH = "Anchoring Bias"
TOL, K = 0.01, 3


def comp_spend(p, c, sea, pk):
    """The part of a package that lands on the manager's comp budget: the base
    raise, the bonus, and the raise attached to a promotion. Perks come out of
    accrual/coverage/capacity/band, which the manager is not judged on."""
    S, lam = c.salary, sea.lam
    v = lam["comp"] * (S * BASE_PCT[pk.base] * PVF * (1.0 + p.peer_spill)
                       + S / 12.0 * BONUS_MO[pk.bonus])
    if pk.title and p.promo_raise is not None:
        v += lam["comp"] * S * p.promo_raise * PVF
    return v


def manager_npv(p, c, sea, bel, pk, alpha, beta):
    """What the manager is optimising. The firm's version is `works_npv3`."""
    from molt.v3 import feasible
    if not feasible(p, sea, pk):
        return -1e18
    pl = p_leave_belief3(p, c, bel, pk)
    cost = works_cost3(p, c, sea, pk) + beta * comp_spend(p, c, sea, pk)
    return -(1.0 - pl) * cost - alpha * pl * replacement_cost(p, c)


def mgr_reply(p, c, sea, bel, op, floor, alpha, beta, only=None):
    best, bv = None, -1e30
    for pk in works_packages3(p, sea, Package()):
        if only is not None and pk.labels()[only[0]] != only[1]:
            continue
        if crab_value3(p, c, pk) <= floor + 1e-9:
            continue
        v = manager_npv(p, c, sea, bel, pk, alpha, beta)
        if v > bv:
            best, bv = pk, v
    return best


def arm_menu(p, c, sea, alpha, beta):
    """The manager picks its preferred package, then offers everything it would
    equally sign. The crab chooses."""
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    star = mgr_reply(p, c, sea, bel, op, crab_value3(p, c, op), alpha, beta)
    if star is None:
        return arm_sign3(p, c, sea)
    w = manager_npv(p, c, sea, bel, star, alpha, beta)
    band = [pk for pk in works_packages3(p, sea, op)
            if manager_npv(p, c, sea, bel, pk, alpha, beta) >= w - TOL * c.salary
            and crab_value3(p, c, pk) >= crab_value3(p, c, op)]
    if not band:
        band = [star]
    short = sorted(band, key=lambda pk: -crab_value3(p, c, pk))[:K]
    best = max(short, key=lambda pk: crab_value3(p, c, pk))
    return settle3(p, c, sea, best, 1.0 + approval_days(p, best, op), 1, 1, spoke)


def arm_haggle(p, c, sea, rng, alpha, beta):
    """Six weeks of email, with the manager deciding on its own payoff."""
    from b2b_opponents import B2B_OPPONENTS
    from negmas.outcomes import make_issue, make_os
    from negmas.preferences import MappingUtilityFunction
    from negmas.sao import SAOMechanism
    import math
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    cur = op
    floor = max(outside_value(p, c) if c.has_outside else -1e18,
                crab_value3(p, c, op))
    budget, day = p.exchange_budget, 0.0
    order = _order3(p, c, sea, "best_first", rng)
    for k, issue in enumerate(order):
        if budget <= 0:
            break
        cands, labels = [], []
        for o in OPTS[issue]:
            pk = mgr_reply(p, c, sea, bel, op, floor - 1e-6, alpha, beta,
                           only=(issue, o))
            if pk is not None:
                cands.append(pk); labels.append(o)
        if len(cands) < 2:
            continue
        os_ = make_os([make_issue(labels, name=issue)])
        outs = list(os_.enumerate_or_sample())
        cu = _norm([crab_value3(p, c, pk) for pk in cands])
        wu = _norm([manager_npv(p, c, sea, bel, pk, alpha, beta) for pk in cands])
        uc = MappingUtilityFunction(dict(zip(outs, cu)), outcome_space=os_)
        uw = MappingUtilityFunction(dict(zip(outs, wu)), outcome_space=os_)
        uc.reserved_value = 0.0
        steps = max(2, min(budget, math.ceil(p.exchange_budget / len(order))))
        m = SAOMechanism(outcome_space=os_, n_steps=steps)
        m.add(B2B_OPPONENTS[ARCH](name="crab"), ufun=uc)
        m.add(WorksSeat(name="mgr", util=dict(zip(outs, wu)),
                        thresh=p.counter_thresh * 4.0), ufun=uw)
        m.run()
        used = max(1, int(m.current_step))
        budget -= used
        day += float(sum(c.delays[(k * 3 + j) % len(c.delays)]
                         for j in range(min(used, 3))))
        if m.agreement is not None:
            nxt = cands[outs.index(tuple(m.agreement))]
            if manager_npv(p, c, sea, bel, nxt, alpha, beta) >= \
               manager_npv(p, c, sea, bel, cur, alpha, beta):
                cur = nxt
    if p.clock:
        day += float(np.exp(np.log(p.meeting_med)
                            + p.meeting_sig * (c.u_exo - 0.5) * 2))
    day += approval_days(p, cur, op)
    return settle3(p, c, sea, cur, max(day, 1.0), 1, p.exchange_budget, spoke)


def cell(alpha, beta, seeds=(7, 11, 23, 31, 101), seasons=2, nc=40):
    p = Params3(**P)
    out = {k: {"u": [], "cash": [], "w": [], "left": [], "comp": []}
           for k in ("menu", "haggle", "sign")}
    for seed in seeds:
        rng = np.random.default_rng(seed); g = np.random.default_rng(seed + 99)
        for _ in range(seasons):
            s1 = Season.draw(p, rng, nc)
            sm, sh, ss = copy.deepcopy(s1), copy.deepcopy(s1), copy.deepcopy(s1)
            for i in range(nc):
                c = draw_crab2(i, p, rng)
                rows = {"menu": arm_menu(p, c, sm, alpha, beta),
                        "haggle": arm_haggle(p, c, sh, g, alpha, beta),
                        "sign": arm_sign3(p, c, ss)}
                for k, (r, s) in zip(rows, ((rows["menu"], sm), (rows["haggle"], sh),
                                            (rows["sign"], ss))):
                    if r["pkg"].title and not r["left"]:
                        s.slots_left -= 1
                    out[k]["left"].append(1.0 if r["left"] else 0.0)
                    if not r["left"]:
                        out[k]["u"].append(r["crab"]); out[k]["cash"].append(r["cash"])
                        out[k]["w"].append(r["works"])
                        out[k]["comp"].append(comp_spend(p, c, s1, r["pkg"]))
    return {k: {"u": float(np.mean(v["u"])), "cash": float(np.mean(v["cash"])),
                "w": float(np.mean(v["w"])), "comp": float(np.mean(v["comp"])),
                "left": float(np.mean(v["left"])),
                "joint": float(np.mean(v["u"]) + np.mean(v["w"]))}
            for k, v in out.items()}


def main():
    BAR = 2253
    res = {}
    print(f"{'manager':28s}{'arm':9s}{'you get':>10}{'firm':>11}{'joint':>10}"
          f"{'comp spend':>12}{'collapse':>10}")
    for alpha, beta, lab in ((1.0, 0.0, "aligned (alpha=1.0)"),
                             (0.5, 0.0, "half-aligned"),
                             (0.2, 0.0, "misaligned (alpha=0.2)"),
                             (0.2, 0.3, "misaligned + budget squeeze")):
        r = cell(alpha, beta)
        res[lab] = r
        for arm in ("sign", "haggle", "menu"):
            d = r[arm]
            print(f"{lab if arm=='sign' else '':28s}{arm:9s}{d['u']:>10,.0f}"
                  f"{d['w']:>11,.0f}{d['joint']:>10,.0f}{d['comp']:>12,.0f}"
                  f"{100*d['left']:>9.1f}%")
        print()
    json.dump(res, open(os.path.join(_HERE, "results_v10.json"), "w"), indent=1)

    A = res["aligned (alpha=1.0)"]; M = res["misaligned + budget squeeze"]
    d40 = M["menu"]["u"] - M["haggle"]["u"]
    print(f"K40 does the manager block the menu?  menu - haggle, misaligned = {d40:+,.0f}"
          f"  -> {'FIRES: the manager is the blocker' if d40 < BAR else 'does not fire'}")
    df = A["menu"]["w"] - M["menu"]["w"]; dc = A["menu"]["u"] - M["menu"]["u"]
    print(f"K41 who pays for misalignment?  firm {-df:+,.0f}, employee {-dc:+,.0f}"
          f"  -> {'the FIRM pays more' if df > dc else 'the EMPLOYEE pays more'}")
    d42 = M["menu"]["comp"] - M["haggle"]["comp"]
    print(f"K42 is the menu manager-aligned?  comp-budget spend menu vs haggle = {d42:+,.0f}"
          f"  -> {'FIRES: menu costs the manager MORE comp budget' if d42 > 0 else 'does not fire: the menu is cheaper on comp budget'}")
    print(f"K43 ordering under misalignment: menu {M['menu']['u']:,.0f} > "
          f"haggle {M['haggle']['u']:,.0f} > sign {M['sign']['u']:,.0f}"
          f"  -> {'holds' if M['menu']['u'] > M['haggle']['u'] > M['sign']['u'] else 'REVERSED'}")


if __name__ == "__main__":
    main()
