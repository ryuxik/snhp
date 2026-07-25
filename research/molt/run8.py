"""Molt Season v8 — PREREG AMENDMENT 6. K36..K39: attacks on peer mode.

    python3 research/molt/run8.py

Four arms, one per attack: the honest baseline, a liar, a reversed proposal
order, and the individual-rationality comparison.
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

from molt.arms3 import _pkg_from, crab_batna3, crab_issues3, settle3, works_issues3
from molt.v2 import draw_crab2, prior, update
from molt.v3 import (Package, Params3, Season, crab_value3, discloses3,
                     slot_open, works_npv3, works_signs3)
from molt.world import approval_days, opening_offer, outside_value
from run7 import arm_engine, works_batna_norm, works_reply

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)


def duel(p, c, sea, seed, peer, true_batna, crab_lie=0.0, works_lie=0.0,
         works_first=False):
    """Both sides on the engine.

    crab_lie / works_lie inflate the side's DECLARED walk-away — peer mode trusts
    it, so this is the incentive-compatibility test.
    works_first reverses who proposes.
    """
    from gametheory.negotiation.bundle import negotiate_bundle
    op = opening_offer(p, c)
    spoke = discloses3(p, c, sea)
    bel = update(p, c, prior(p, c), spoke)
    ci, wi = crab_issues3(p, c, sea), works_issues3(p, c, sea)
    cp = {i["name"]: 1.0 for i in ci}
    cost = {i["name"]: abs(min(i["my_utility"])) for i in wi}
    tot = sum(cost.values()) or 1.0
    wp = {k: v / tot for k, v in cost.items()}
    cb_true, wb_true = crab_batna3(p, c, sea), works_batna_norm(p, c, sea)
    # what each side DECLARES (may be a lie); what each side privately holds
    cb_decl = float(np.clip(cb_true + crab_lie, 0.0, 1.0))
    wb_decl = float(np.clip(wb_true + works_lie, 0.0, 1.0))
    tb_c = wb_decl if (peer or true_batna) else p.their_batna_estimate
    tb_w = cb_decl if (peer or true_batna) else p.their_batna_estimate
    top = Package(4, slot_open(p, sea), 2, True, True, 2)
    crab_saw, works_saw, cur = [op.labels()], [top.labels()], op

    def crab_move(r):
        return negotiate_bundle(issues=ci, their_offers=crab_saw, my_priorities=cp,
                                my_batna=cb_decl, their_batna_estimate=tb_c,
                                peer_mode=peer, seed=seed + r,
                                rounds_left=p.max_rounds - r)

    def works_move(r):
        return negotiate_bundle(issues=wi, their_offers=works_saw, my_priorities=wp,
                                my_batna=wb_decl, their_batna_estimate=tb_w,
                                peer_mode=peer, seed=seed + 500 + r,
                                rounds_left=p.max_rounds - r)

    for r in range(p.max_rounds):
        if works_first:
            rw = works_move(r)
            if rw["action"] != "counter":
                break
            cnt = _pkg_from(rw.get("recommended_offer") or {})
            if works_npv3(p, c, sea, bel, cnt) >= works_npv3(p, c, sea, bel, cur):
                cur = cnt
                crab_saw.append(cur.labels())
            if crab_value3(p, c, cur) >= (outside_value(p, c) if c.has_outside else 0):
                break
            rc = crab_move(r)
            if rc["action"] != "counter":
                break
            ask = _pkg_from(rc.get("recommended_offer") or {})
            if works_npv3(p, c, sea, bel, ask) >= works_npv3(p, c, sea, bel, cur):
                cur = ask
                break
            works_saw.append(ask.labels())
        else:
            rc = crab_move(r)
            if rc["action"] != "counter":
                break
            ask = _pkg_from(rc.get("recommended_offer") or {})
            if works_npv3(p, c, sea, bel, ask) >= works_npv3(p, c, sea, bel, cur):
                cur = ask
                break
            works_saw.append(ask.labels())
            rw = works_move(r)
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


ARMS = {
    "adversarial, est BATNA":      lambda p, c, s, i: duel(p, c, s, i, False, False),
    "adversarial, TRUE BATNA":     lambda p, c, s, i: duel(p, c, s, i, False, True),
    "PEER MODE (honest)":          lambda p, c, s, i: duel(p, c, s, i, True, True),
    "PEER, crab lies +0.1":        lambda p, c, s, i: duel(p, c, s, i, True, True, crab_lie=0.1),
    "PEER, crab lies +0.2":        lambda p, c, s, i: duel(p, c, s, i, True, True, crab_lie=0.2),
    "PEER, crab lies +0.3":        lambda p, c, s, i: duel(p, c, s, i, True, True, crab_lie=0.3),
    "PEER, Works lies +0.2":       lambda p, c, s, i: duel(p, c, s, i, True, True, works_lie=0.2),
    "PEER, Works proposes first":  lambda p, c, s, i: duel(p, c, s, i, True, True, works_first=True),
    "adversarial TRUE, W first":   lambda p, c, s, i: duel(p, c, s, i, False, True, works_first=True),
    "crab ALONE (engine vs std)":  lambda p, c, s, i: arm_engine(p, c, s, i, True, False),
}


def main(seeds=(7, 11, 23, 31), seasons=3, nc=40):
    acc = {k: {"u": [], "cash": [], "w": [], "left": []} for k in ARMS}
    for seed in seeds:
        for k, fn in ARMS.items():
            p = Params3(**P)
            rng = np.random.default_rng(seed)
            for _ in range(seasons):
                sea = copy.deepcopy(Season.draw(p, rng, nc))
                for i in range(nc):
                    c = draw_crab2(i, p, rng)
                    r = fn(p, c, sea, seed * 1000 + i)
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
    json.dump(out, open(os.path.join(_HERE, "results_v8.json"), "w"), indent=1)
    print(f"{'arm':32s}{'crab utility':>14}{'Works':>12}{'JOINT':>11}{'left%':>7}")
    for k, d in out.items():
        print(f"{k:32s}{d['utility']:>14,.0f}{d['works']:>12,.0f}{d['joint']:>11,.0f}"
              f"{100*d['left']:>7.1f}")

    BAR = 2253
    adv_t, peer = out["adversarial, TRUE BATNA"], out["PEER MODE (honest)"]
    adv_e = out["adversarial, est BATNA"]
    d36 = peer["joint"] - adv_t["joint"]
    print(f"\nK36 HONEST BASELINE  peer - adversarial(TRUE BATNA) = {d36:+,.0f}"
          f"  -> {'FIRES: the value is BATNA exchange, not peer mode' if d36 < BAR else 'does not fire'}")
    print(f"    (against the rigged baseline it looked like "
          f"{peer['joint']-adv_e['joint']:+,.0f})")
    print("K37 DOES LYING PAY")
    for k in ("PEER, crab lies +0.1", "PEER, crab lies +0.2", "PEER, crab lies +0.3"):
        d = out[k]["utility"] - peer["utility"]
        print(f"    {k:26s} crab {d:+9,.0f}"
              f"  {'PAYS' if d > BAR else 'does not pay'}")
    dw = out["PEER, Works lies +0.2"]["works"] - peer["works"]
    print(f"    {'PEER, Works lies +0.2':26s} Works {dw:+9,.0f}"
          f"  {'PAYS' if dw > BAR else 'does not pay'}")
    liar = max(out[k]["utility"] - peer["utility"]
               for k in ARMS if k.startswith("PEER, crab lies"))
    print(f"    -> {'FIRES: peer mode is not incentive-compatible' if max(liar, dw) > BAR else 'does not fire'}")
    def share(d, base):
        g = d["joint"] - base["joint"]
        return 100 * (d["utility"] - base["utility"]) / g if abs(g) > 1 else float("nan")
    s1 = share(peer, adv_e)
    s2 = share(out["PEER, Works proposes first"], out["adversarial TRUE, W first"])
    print(f"K38 FIRST-MOVER      crab's share of the gain: crab-first {s1:.0f}%, "
          f"Works-first {s2:.0f}%  (moved {abs(s1-s2):.0f}pp)"
          f"  -> {'FIRES: the split is a protocol artifact' if abs(s1-s2) > 20 else 'does not fire'}")
    alone = out["crab ALONE (engine vs std)"]
    d39 = peer["utility"] - alone["utility"]
    print(f"K39 OPT IN?          peer {peer['utility']:,.0f} vs going it alone "
          f"{alone['utility']:,.0f} = {d39:+,.0f}"
          f"  -> {'FIRES: jointly efficient, individually irrational' if d39 < -BAR else 'does not fire'}")


if __name__ == "__main__":
    main()
