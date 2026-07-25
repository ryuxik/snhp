"""Molt Season v9 — closing the gaps left open by v6-v8.

    python3 research/molt/run9.py

1. CONFIRMATORY SEED. v6/v7/v8 were run on 7/11/23/31 and never on the held-out
   101, which v3 and v4 both were. Every headline is re-read there.
2. K39, DONE PROPERLY. The v8 version compared a duel arm against a solo arm --
   two different employer implementations, the exact defect the sixth assertion
   exists to catch. Here the comparison stays inside the duel family, so both
   sides face the same kind of counterparty.
3. LYING, PAST WHERE I STOPPED. K37 tested inflations to 0.3 and found a
   monotone rising gain that never cleared the bar. Continue to 0.5 and 0.7.
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

from molt.v2 import draw_crab2
from molt.v3 import Params3, Season
from run7 import arm_engine, arm_human
from run8 import duel

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)
BAR = 2253

# Every arm declares the employer it faces. Two arms may only be compared when
# these match -- the rule K39 broke in v8.
EMPLOYER = {
    "engine [cut=Y,strict=N]": "works_reply",
    "human  [cut=Y,strict=N]": "works_reply",
    "duel adversarial est": "engine",
    "duel adversarial TRUE": "engine",
    "duel PEER": "engine",
    "duel PEER, lie +0.3": "engine",
    "duel PEER, lie +0.5": "engine",
    "duel PEER, lie +0.7": "engine",
    "duel PEER, Works first": "engine",
}
ARMS = {
    "engine [cut=Y,strict=N]": lambda p, c, s, i, g: arm_engine(p, c, s, i, True, False),
    "human  [cut=Y,strict=N]": lambda p, c, s, i, g: arm_human(p, c, s, g, True, False, ratchet=False),
    "duel adversarial est":    lambda p, c, s, i, g: duel(p, c, s, i, False, False),
    "duel adversarial TRUE":   lambda p, c, s, i, g: duel(p, c, s, i, False, True),
    "duel PEER":               lambda p, c, s, i, g: duel(p, c, s, i, True, True),
    "duel PEER, lie +0.3":     lambda p, c, s, i, g: duel(p, c, s, i, True, True, crab_lie=0.3),
    "duel PEER, lie +0.5":     lambda p, c, s, i, g: duel(p, c, s, i, True, True, crab_lie=0.5),
    "duel PEER, lie +0.7":     lambda p, c, s, i, g: duel(p, c, s, i, True, True, crab_lie=0.7),
    "duel PEER, Works first":  lambda p, c, s, i, g: duel(p, c, s, i, True, True, works_first=True),
}


def run(seeds, seasons=3, nc=40):
    acc = {k: {"u": [], "w": [], "left": []} for k in ARMS}
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
                        acc[k]["u"].append(r["crab"]); acc[k]["w"].append(r["works"])
    return {k: {"utility": float(np.mean(v["u"])), "works": float(np.mean(v["w"])),
                "joint": float(np.mean(v["u"]) + np.mean(v["w"])),
                "left": float(np.mean(v["left"])), "n": len(v["u"])}
            for k, v in acc.items()}


def compare(a, b):
    assert EMPLOYER[a] == EMPLOYER[b], (
        f"refusing to compare {a} against {b}: different employers "
        f"({EMPLOYER[a]} vs {EMPLOYER[b]})")
    return True


def main():
    out = {}
    for tag, seeds in (("main", (7, 11, 23, 31)), ("confirm", (101,))):
        print(f"\n{'='*74}\n{tag.upper()}  seeds={seeds}\n{'='*74}")
        r = run(seeds)
        out[tag] = r
        print(f"{'arm':28s}{'crab utility':>14}{'Works':>12}{'JOINT':>11}{'left%':>7}")
        for k, d in r.items():
            print(f"{k:28s}{d['utility']:>14,.0f}{d['works']:>12,.0f}"
                  f"{d['joint']:>11,.0f}{100*d['left']:>7.1f}")
        compare("duel PEER", "duel adversarial TRUE")
        d36 = r["duel PEER"]["joint"] - r["duel adversarial TRUE"]["joint"]
        print(f"\n  K36 peer - adversarial(TRUE) joint {d36:+,.0f}"
              f"  -> {'FIRES' if d36 < BAR else 'does not fire'}")
        print("  K37 lying, continued past where v8 stopped:")
        for lie in ("+0.3", "+0.5", "+0.7"):
            d = r[f"duel PEER, lie {lie}"]["utility"] - r["duel PEER"]["utility"]
            print(f"      crab inflates its walk-away by {lie}: {d:+9,.0f}"
                  f"  {'CLEARS THE BAR' if d > BAR else 'under the bar'}")
        compare("duel PEER", "duel adversarial est")
        d39a = r["duel PEER"]["utility"] - r["duel adversarial est"]["utility"]
        d39b = r["duel PEER"]["utility"] - r["duel adversarial TRUE"]["utility"]
        print(f"  K39 (redone, same employer) crab in peer vs adversarial-est "
              f"{d39a:+,.0f}; vs adversarial-TRUE {d39b:+,.0f}"
              f"  -> {'FIRES' if d39b < -BAR else 'does not fire'}")
        compare("engine [cut=Y,strict=N]", "human  [cut=Y,strict=N]")
        de = r["engine [cut=Y,strict=N]"]["joint"] - r["human  [cut=Y,strict=N]"]["joint"]
        print(f"  engine - sequential (matched employer) joint {de:+,.0f}")
        try:
            compare("duel PEER", "engine [cut=Y,strict=N]")
            print("  !! the employer guard did not fire when it should have")
        except AssertionError as e:
            print(f"  employer guard works: {e}")
    json.dump(out, open(os.path.join(_HERE, "results_v9.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
