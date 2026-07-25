"""Molt Season v7 — the SYMMETRIC harness, and the BATNA guess as a treatment.

    python3 research/molt/run7.py

v6 compared two arms whose employers played by different rules. Two asymmetries,
both mine, both favouring the sequential arm:

  ACTION SET  `works_packages3` iterates range(base_pkg.base, 4), so an employer
              handed the opening offer can never cut base to fund a title. The
              reopen arm was handed Package() and could; the engine arm was
              handed the opening and could not.
  REPLY RULE  `works_best_reply3` seeds its search at the opening's NPV and
              returns None when nothing beats doing nothing. The reopen arm's
              per-option argmax had no such requirement.

Here ONE reply function serves both arms, and both asymmetries become explicit
2x2 treatments so their contributions can be separated instead of conflated.

Also: `their_batna_estimate` was a bare 0.45 in world.py with no justification,
never swept in a registered run, while the engine ships 0.40. It is a treatment
here.
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE)),
           os.path.join(os.path.dirname(os.path.dirname(_HERE)), "snhp"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
from negmas.outcomes import make_issue, make_os
from negmas.preferences import MappingUtilityFunction
from negmas.sao import SAOMechanism

from molt.arms2 import WorksSeat, _norm
from molt.arms3 import (OPTS, _order3, _pkg_from, crab_batna3, crab_issues3,
                        settle3, works_issues3)
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (Package, Params3, Season, crab_value3, discloses3,
                     replacement_cost, slot_open, works_cost3, works_npv3,
                     works_packages3, works_signs3)
from molt.world import approval_days, opening_offer, outside_value

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
ARCH = "Anchoring Bias"


def works_batna_norm(p, c, sea):
    top = Package(3, slot_open(p, sea), 2, True, True, 2)
    worst = -works_cost3(p, c, sea, top)
    return float(np.clip((-replacement_cost(p, c) - worst) / max(-worst, 1.0), 0, 1))


# ---------------------------------------------------------- the shared employer
def works_reply(p, c, sea, bel, op, floor_value, may_cut, strict, only=None):
    """THE employer. One function, used by every arm.

    may_cut : may it cut base below the standing offer to fund something else?
    strict  : must its counter beat simply holding the opening?
    only    : (issue, label) restricts the search, for the per-issue arm.
    """
    floor_pkg = Package() if may_cut else op
    best, bv = None, (works_npv3(p, c, sea, bel, op) if strict else -1e30)
    for pk in works_packages3(p, sea, floor_pkg):
        if only is not None and pk.labels()[only[0]] != only[1]:
            continue
        if crab_value3(p, c, pk) <= floor_value + 1e-9:
            continue
        v = works_npv3(p, c, sea, bel, pk)
        if v > bv:
            best, bv = pk, v
    return best


def arm_engine(p, c, sea, seed, may_cut, strict, batna=None):
    from gametheory.negotiation.bundle import negotiate_bundle
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    issues = crab_issues3(p, c, sea)
    prio = {i["name"]: 1.0 for i in issues}
    tb = works_batna_norm(p, c, sea) if batna == "true" else \
        (batna if batna is not None else p.their_batna_estimate)
    seen, cur = [op.labels()], op
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues, their_offers=seen,
                               my_priorities=prio, my_batna=crab_batna3(p, c, sea),
                               their_batna_estimate=tb, seed=seed + r,
                               rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        ask = _pkg_from(res.get("recommended_offer") or {})
        rep = works_reply(p, c, sea, bel, op, crab_value3(p, c, cur), may_cut, strict)
        if works_signs3(p, c, sea, bel, ask, cur, rep):
            cur = ask
            break
        if rep is None:
            break
        cur = rep
        seen.append(cur.labels())
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


def arm_human(p, c, sea, rng, may_cut, strict, ratchet):
    """Sequential, one issue per meeting, driven by a real archetype. `ratchet`
    keeps concessions banked (the v4 behaviour); without it nothing binds until
    the whole deal is signed."""
    from b2b_opponents import B2B_OPPONENTS
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    cur = op
    floor0 = crab_value3(p, c, op) if ratchet else \
        max(outside_value(p, c) if c.has_outside else -1e18, crab_value3(p, c, op))
    budget, exch, day = p.exchange_budget, 0, 0.0
    order = _order3(p, c, sea, "best_first", rng)
    for k, issue in enumerate(order):
        if budget <= 0:
            break
        floor = crab_value3(p, c, cur) if ratchet else floor0
        cands, labels = [], []
        for o in OPTS[issue]:
            pk = works_reply(p, c, sea, bel, op, floor - 1e-6, may_cut, strict,
                             only=(issue, o))
            if pk is not None:
                cands.append(pk)
                labels.append(o)
        if len(cands) < 2:
            continue
        os_ = make_os([make_issue(labels, name=issue)])
        outs = list(os_.enumerate_or_sample())
        cu = _norm([crab_value3(p, c, pk) for pk in cands])
        wu = _norm([works_npv3(p, c, sea, bel, pk) for pk in cands])
        uc = MappingUtilityFunction(dict(zip(outs, cu)), outcome_space=os_)
        uw = MappingUtilityFunction(dict(zip(outs, wu)), outcome_space=os_)
        uc.reserved_value = 0.0
        steps = max(2, min(budget, math.ceil(p.exchange_budget / len(order))))
        m = SAOMechanism(outcome_space=os_, n_steps=steps)
        m.add(B2B_OPPONENTS[ARCH](name="crab"), ufun=uc)
        m.add(WorksSeat(name="works", util=dict(zip(outs, wu)),
                        thresh=p.counter_thresh * 4.0), ufun=uw)
        m.run()
        used = max(1, int(m.current_step))
        exch += used
        budget -= used
        day += float(sum(c.delays[(k * 3 + j) % len(c.delays)]
                         for j in range(min(used, 3))))
        if m.agreement is not None:
            nxt = cands[outs.index(tuple(m.agreement))]
            if works_npv3(p, c, sea, bel, nxt) >= works_npv3(p, c, sea, bel, cur):
                cur = nxt
    if p.clock:
        day += float(np.exp(np.log(p.meeting_med)
                            + p.meeting_sig * (c.u_exo - 0.5) * 2))
    day += approval_days(p, cur, op)
    return settle3(p, c, sea, cur, max(day, 1.0), 1, exch, spoke)


def duel(p, c, sea, seed, peer, true_batna):
    from gametheory.negotiation.bundle import negotiate_bundle
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    ci, wi = crab_issues3(p, c, sea), works_issues3(p, c, sea)
    cp = {i["name"]: 1.0 for i in ci}
    cost = {i["name"]: abs(min(i["my_utility"])) for i in wi}
    tot = sum(cost.values()) or 1.0
    wp = {k: v / tot for k, v in cost.items()}
    cb, wb = crab_batna3(p, c, sea), works_batna_norm(p, c, sea)
    tb_c = wb if (peer or true_batna) else p.their_batna_estimate
    tb_w = cb if (peer or true_batna) else p.their_batna_estimate
    top = Package(4, slot_open(p, sea), 2, True, True, 2)
    crab_saw, works_saw, cur = [op.labels()], [top.labels()], op
    for r in range(p.max_rounds):
        rc = negotiate_bundle(issues=ci, their_offers=crab_saw, my_priorities=cp,
                              my_batna=cb, their_batna_estimate=tb_c,
                              peer_mode=peer, seed=seed + r,
                              rounds_left=p.max_rounds - r)
        if rc["action"] != "counter":
            break
        ask = _pkg_from(rc.get("recommended_offer") or {})
        if works_npv3(p, c, sea, bel, ask) >= works_npv3(p, c, sea, bel, cur):
            cur = ask
            break
        works_saw.append(ask.labels())
        rw = negotiate_bundle(issues=wi, their_offers=works_saw, my_priorities=wp,
                              my_batna=wb, their_batna_estimate=tb_w,
                              peer_mode=peer, seed=seed + 500 + r,
                              rounds_left=p.max_rounds - r)
        if rw["action"] != "counter":
            break
        cnt = _pkg_from(rw.get("recommended_offer") or {})
        if works_npv3(p, c, sea, bel, cnt) < works_npv3(p, c, sea, bel, cur):
            break
        cur = cnt
        crab_saw.append(cur.labels())
        if crab_value3(p, c, cur) >= (outside_value(p, c) if c.has_outside else 0):
            break
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


ARMS = {}
for mc in (False, True):
    for st in (True, False):
        tag = f"cut={'Y' if mc else 'N'},strict={'Y' if st else 'N'}"
        ARMS[f"engine [{tag}]"] = (lambda mc, st: (
            lambda p, c, s, i, g: arm_engine(p, c, s, i, mc, st)))(mc, st)
        ARMS[f"human  [{tag}]"] = (lambda mc, st: (
            lambda p, c, s, i, g: arm_human(p, c, s, g, mc, st, ratchet=False)))(mc, st)
ARMS["human RATCHET [cut=Y,strict=N]"] = \
    lambda p, c, s, i, g: arm_human(p, c, s, g, True, False, ratchet=True)
for b in (0.20, 0.40, 0.45, 0.60, 0.80, "true"):
    ARMS[f"engine batna={b}"] = (lambda b: (
        lambda p, c, s, i, g: arm_engine(p, c, s, i, True, False, batna=b)))(b)
ARMS["duel adversarial est"] = lambda p, c, s, i, g: duel(p, c, s, i, False, False)
ARMS["duel adversarial TRUE"] = lambda p, c, s, i, g: duel(p, c, s, i, False, True)
ARMS["duel PEER MODE"] = lambda p, c, s, i, g: duel(p, c, s, i, True, True)


def main(seeds=(7, 11, 23, 31), seasons=3, nc=40):
    acc = {k: {"u": [], "cash": [], "w": [], "left": []} for k in ARMS}
    for seed in seeds:
        for k, fn in ARMS.items():
            p = Params3(**P)
            rng = np.random.default_rng(seed)
            g = np.random.default_rng(seed + 99)
            for _ in range(seasons):
                sea = copy.deepcopy(Season.draw(p, rng, nc))
                for i in range(nc):
                    c = draw_crab2(i, p, rng)
                    r = fn(p, c, sea, seed * 1000 + i, g)
                    if r["pkg"].title and not r["left"]:
                        sea.slots_left -= 1
                    acc[k]["left"].append(1.0 if r["left"] else 0.0)
                    if not r["left"]:
                        acc[k]["u"].append(r["crab"]); acc[k]["cash"].append(r["cash"])
                        acc[k]["w"].append(r["works"])
    out = {k: {"utility": float(np.mean(v["u"])), "cash": float(np.mean(v["cash"])),
               "works": float(np.mean(v["w"])),
               "joint": float(np.mean(v["u"]) + np.mean(v["w"])),
               "left": float(np.mean(v["left"])), "n": len(v["u"])}
           for k, v in acc.items()}
    json.dump(out, open(os.path.join(_HERE, "results_v7.json"), "w"), indent=1)
    print(f"{'arm':34s}{'crab utility':>13}{'cash':>10}{'Works':>11}{'JOINT':>10}{'left%':>7}")
    for k, d in out.items():
        print(f"{k:34s}{d['utility']:>13,.0f}{d['cash']:>10,.0f}{d['works']:>11,.0f}"
              f"{d['joint']:>10,.0f}{100*d['left']:>7.1f}")
    return out


if __name__ == "__main__":
    main()
