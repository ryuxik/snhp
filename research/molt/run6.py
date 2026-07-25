"""Molt Season v6 — PREREG AMENDMENT 5. K27..K31.

    python3 research/molt/run6.py

Four changes: the sequential arm can have its ratchet removed (nothing binding
until signed), the engine's offer history is ablated to measure learning,
`peer_mode` is finally exercised, and the `cooperation` dial is run as the
product ships it rather than reimplemented.
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
from negmas.outcomes import make_issue, make_os
from negmas.preferences import MappingUtilityFunction
from negmas.sao import SAOMechanism

from molt.arms2 import WorksSeat, _norm
from molt.arms3 import (OPTS, _pkg_from, crab_issues3, settle3, sitting_crab3,
                        slow_archetype3, works_issues3, crab_batna3)
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (Package, Params3, Season, crab_value3, discloses3,
                     replacement_cost, slot_open, works_best_reply3,
                     works_cost3, works_npv3, works_signs3, works_packages3)
from molt.world import (ISSUES_V3, approval_days, opening_offer, outside_value)

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
ARCH = "Anchoring Bias"
AGENDA6 = ("base", "bonus", "berth", "title", "deepwater", "pto")


def works_batna_norm(p, c, sea):
    top = Package(3, slot_open(p, sea), 2, True, True, 2)
    worst = -works_cost3(p, c, sea, top)
    walk = -replacement_cost(p, c)
    return float(np.clip((walk - worst) / max(-worst, 1.0), 0.0, 1.0))


# ------------------------------------------------------- A5.2: the ratchet off
def _best_with(p, c, sea, bel, issue, label, floor):
    """The Works' best package containing this option, re-optimising everything
    else. This is the claw-back: 'you can have the title, and base goes back'."""
    best, bv = None, -1e30
    for pk in works_packages3(p, sea, Package()):
        if pk.labels()[issue] != label:
            continue
        if crab_value3(p, c, pk) < floor - 1e-9:
            continue
        v = works_npv3(p, c, sea, bel, pk)
        if v > bv:
            best, bv = pk, v
    return best


def slow_reopen(p, c, sea, arch, rng):
    """The sequential arm with NOTHING BINDING until the whole deal is signed."""
    from b2b_opponents import B2B_OPPONENTS
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    floor = max(outside_value(p, c) if c.has_outside else -1e18,
                crab_value3(p, c, op))
    cur = op
    budget, exch, day = p.exchange_budget, 0, 0.0
    from molt.arms3 import _order3
    order = _order3(p, c, sea, "best_first", rng)   # same agenda rule as the
                                                    # ratcheted arm; only the
                                                    # binding-ness differs
    for k, issue in enumerate(order):
        if budget <= 0:
            break
        cands, labels = [], []
        for o in OPTS[issue]:
            pk = _best_with(p, c, sea, bel, issue, o, floor)
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
        lo, hi = min(cu), max(cu)
        uc.reserved_value = 0.0
        steps = max(2, min(budget, math.ceil(p.exchange_budget / len(order))))
        m = SAOMechanism(outcome_space=os_, n_steps=steps)
        m.add(B2B_OPPONENTS[arch](name="crab"), ufun=uc)
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


# ------------------------------------------------- A5.2: learning, and peers
def engine(p, c, sea, seed, truncate=False, peer=False, coop=None):
    """The engine arm. `truncate` shows it only the opening every round (the
    v5 bug, kept as the ablation). `peer`/`coop` finally exercise the product's
    cooperative paths."""
    from gametheory.negotiation.bundle import negotiate_bundle
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    issues = crab_issues3(p, c, sea)
    prio = {i["name"]: 1.0 for i in issues}
    seen = [op.labels()]
    cur = op
    tb = works_batna_norm(p, c, sea) if peer else p.their_batna_estimate
    for r in range(p.max_rounds):
        res = negotiate_bundle(issues=issues,
                               their_offers=([seen[0]] if truncate else seen),
                               my_priorities=prio,
                               my_batna=crab_batna3(p, c, sea),
                               their_batna_estimate=tb,
                               peer_mode=peer, cooperation=coop,
                               seed=seed + r, rounds_left=p.max_rounds - r)
        if res["action"] != "counter":
            break
        ask = _pkg_from(res.get("recommended_offer") or {})
        reply = works_best_reply3(p, c, sea, bel, op, crab_value3(p, c, cur))
        if works_signs3(p, c, sea, bel, ask, cur, reply):
            cur = ask
            break
        if reply is None:
            break
        cur = reply
        seen.append(cur.labels())
    return settle3(p, c, sea, cur, 1.0 + approval_days(p, cur, op), 1,
                   p.max_rounds, spoke)


def duel(p, c, sea, seed, peer=False):
    """Both sides on the engine. peer=True runs the product's cooperative mode
    on BOTH seats with truthfully exchanged BATNAs."""
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
    top = Package(4, slot_open(p, sea), 2, True, True, 2)
    crab_saw, works_saw = [op.labels()], [top.labels()]
    cur = op
    for r in range(p.max_rounds):
        rc = negotiate_bundle(issues=ci, their_offers=crab_saw, my_priorities=cp,
                              my_batna=cb,
                              their_batna_estimate=(wb if peer else p.their_batna_estimate),
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
                              my_batna=wb,
                              their_batna_estimate=(cb if peer else p.their_batna_estimate),
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


ARMS6 = {
    "human_RATCHET":      lambda p, c, s, i, g: slow_archetype3(p, c, s, ARCH, "best_first", g),
    "human_REOPEN":       lambda p, c, s, i, g: slow_reopen(p, c, s, ARCH, g),
    "engine_full_history": lambda p, c, s, i, g: engine(p, c, s, i),
    "engine_TRUNCATED":   lambda p, c, s, i, g: engine(p, c, s, i, truncate=True),
    "coop_0.0":           lambda p, c, s, i, g: engine(p, c, s, i, coop=0.0),
    "coop_0.5":           lambda p, c, s, i, g: engine(p, c, s, i, coop=0.5),
    "coop_1.0":           lambda p, c, s, i, g: engine(p, c, s, i, coop=1.0),
    "both_ADVERSARIAL":   lambda p, c, s, i, g: duel(p, c, s, i, peer=False),
    "both_PEER_MODE":     lambda p, c, s, i, g: duel(p, c, s, i, peer=True),
}


def main(seeds=(7, 11, 23, 31), seasons=3, nc=40):
    acc = {k: {"u": [], "cash": [], "w": [], "left": []} for k in ARMS6}
    for seed in seeds:
        for k, fn in ARMS6.items():
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
               "works": float(np.mean(v["w"])), "left": float(np.mean(v["left"])),
               "joint": float(np.mean(v["u"]) + np.mean(v["w"])), "n": len(v["u"]),
               "se": float(np.std(v["u"], ddof=1) / math.sqrt(len(v["u"])))}
           for k, v in acc.items()}
    json.dump(out, open(os.path.join(_HERE, "results_v6.json"), "w"), indent=1)

    print(f"{'arm':24s}{'crab utility':>14}{'cash':>11}{'Works':>12}{'joint':>11}{'left%':>8}")
    for k, d in out.items():
        print(f"{k:24s}{d['utility']:>14,.0f}{d['cash']:>11,.0f}{d['works']:>12,.0f}"
              f"{d['joint']:>11,.0f}{100*d['left']:>8.1f}")
    BAR = 2253
    hr, ho = out["human_RATCHET"], out["human_REOPEN"]
    ef, et = out["engine_full_history"], out["engine_TRUNCATED"]
    pb, ab = out["both_PEER_MODE"], out["both_ADVERSARIAL"]
    d27 = hr["utility"] - ho["utility"]
    print(f"\nK27 THE RATCHET   human loses {d27:+,.0f} when it cannot bank concessions"
          f"  -> {'FIRES: retract every human-beats-engine line' if d27 > BAR else 'does not fire'}")
    print(f"    with the ratchet gone, human {ho['utility']:,.0f} vs engine "
          f"{ef['utility']:,.0f}  ({ef['utility']-ho['utility']:+,.0f})")
    d28 = ef["utility"] - et["utility"]
    print(f"K28 LEARNING      full history - truncated = {d28:+,.0f}"
          f"  -> {'FIRES: sequential inference buys nothing' if d28 < BAR else 'does not fire'}")
    d29 = pb["joint"] - ab["joint"]
    print(f"K29 PEER MODE     joint {ab['joint']:,.0f} -> {pb['joint']:,.0f} ({d29:+,.0f})"
          f"  -> {'FIRES: peer mode does not deliver' if d29 < BAR else 'does not fire'}")
    sh = pb["works"] / pb["joint"] if pb["joint"] else float("nan")
    print(f"K30 PEER SPLIT    under peer mode the Works takes "
          f"{100*pb['works']/pb['joint'] if pb['joint'] else float('nan'):.0f}% of the joint"
          f"  (crab {pb['utility']:,.0f}, Works {pb['works']:,.0f})")
    d31 = ef["utility"] - ho["utility"]
    print(f"K31 vs THE LIT    packages - sequential (ratchet off) = {d31:+,.0f}"
          f"  -> {'FIRES: contradicts In and Serrano; sim unreliable here' if d31 < 0 else 'does not fire'}")
    print(f"\ncooperation dial: 0.0 {out['coop_0.0']['utility']:,.0f} | "
          f"0.5 {out['coop_0.5']['utility']:,.0f} | 1.0 {out['coop_1.0']['utility']:,.0f}"
          f"   (joint: {out['coop_0.0']['joint']:,.0f} / {out['coop_0.5']['joint']:,.0f} / "
          f"{out['coop_1.0']['joint']:,.0f})")


if __name__ == "__main__":
    main()
