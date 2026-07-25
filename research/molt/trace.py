"""Record one crab's molt season, both ways, for the demo to play back.

    python research/molt/trace.py

Writes arena/web/molt/trace-<slug>.json and science-data.json. Nothing on the
demo page is written by hand: every number it shows comes out of this file,
which comes out of the same `arms.py` the experiment runs.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_RESEARCH)
for _p in (_RESEARCH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

import molt.arms as A
from molt.world import (BASE_PCT, ISSUES, Package, Params,
                        crab_value, draw_crab, opening_offer, outside_value,
                        p_leave, works_cost, works_npv)

OUT = os.path.join(_ROOT, "arena", "web", "molt")

NAMES = ["Pincer Okonkwo", "Vell Tidewright", "Sar Molting-Ash", "Krill Vantablack",
         "Bex Carapace", "Nix Shorewall", "Ori Saltrender", "Juno Clawgrave",
         "Hess Barnacle", "Mira Undertow", "Tobi Reefsong", "Ada Kelpline"]


def crab_card(p, c, name):
    m = A.weight_mult(c)
    return {
        "name": name,
        "spec": c.spec.name,
        "salary": round(c.salary),
        "tenure": c.tenure,
        "perf": round(100 * c.perf),
        "weights": {k: round(float(w), 3) for k, w in zip(ISSUES, c.w)},
        "cares_most": max(ISSUES, key=lambda k: m[k]),
        "has_outside": c.has_outside,
        "outside_premium": round(100 * c.omega, 1) if c.has_outside else None,
        "outside_value": round(outside_value(p, c)) if c.has_outside else None,
        "offer_expires_day": round(c.d_exp, 1) if c.has_outside else None,
        "replacement_cost": round(p.spec_rho(c.spec) * c.salary),
        "opening": opening_offer(p, c).labels(),
        "issue_values": {k: round(v) for k, v in issue_values(p, c).items()},
        "issue_costs": {k: round(v) for k, v in issue_costs(p, c).items()},
    }


def issue_values(p, c):
    z = Package()
    return {"base": crab_value(p, c, Package(base=1)) - crab_value(p, c, z),
            "title": crab_value(p, c, Package(title=True)) - crab_value(p, c, z),
            "bonus": crab_value(p, c, Package(bonus=1)) - crab_value(p, c, z),
            "berth": crab_value(p, c, Package(berth=True)) - crab_value(p, c, z),
            "deepwater": crab_value(p, c, Package(deep=True)) - crab_value(p, c, z)}


def issue_costs(p, c):
    z = Package()
    return {"base": works_cost(p, c, Package(base=1)) - works_cost(p, c, z),
            "title": works_cost(p, c, Package(title=True)) - works_cost(p, c, z),
            "bonus": works_cost(p, c, Package(bonus=1)) - works_cost(p, c, z),
            "berth": works_cost(p, c, Package(berth=True)) - works_cost(p, c, z),
            "deepwater": works_cost(p, c, Package(deep=True)) - works_cost(p, c, z)}


def score(p, c, r):
    return {"crab": round(r["crab"]), "works": round(r["works"]),
            "joint": round(r["crab"] + r["works"]),
            "days": round(r["days"], 1), "meetings": int(r["meetings"]),
            "left": bool(r["left"]), "walked": bool(r["walked"]),
            "expired": bool(r["expired"]), "pkg": r["pkg"].labels(),
            "concession": round(r["concession"]), "mgr": round(r["mgr"]),
            "distraction": round(r["distraction"]),
            "replacement": round(r["replacement"]),
            "p_leave": round(p_leave(p, c, r["pkg"], r["expired"]), 3)}


def record(p, c, seed, name):
    slow_trace, fast_trace = [], []
    slow = A.arm_slow(p, c, engine_asks=False, trace=slow_trace)
    fast = A.arm_sitting_crab(p, c, seed, trace=fast_trace)
    sign = A.arm_sign(p, c)
    both = A.arm_sitting_both(p, c, seed)
    return {
        "crab": crab_card(p, c, name),
        "sign": {"score": score(p, c, sign)},
        "slow": {"steps": slow_trace, "score": score(p, c, slow),
                 "agenda": list(A.AGENDA)},
        "fast": {"steps": fast_trace, "score": score(p, c, fast)},
        "both": {"score": score(p, c, both)},
    }


def pick(p, seeds=range(200), want=("walkout", "settled", "works_wins")):
    """Find one vivid crab per story. Selection is on the SETUP (an outside
    offer, a crab who wants something other than cash), never on the size of the
    result — and the chosen seeds are printed so anyone can re-derive them."""
    found = {}
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for i in range(40):
            c = draw_crab(i, p, rng)
            if not c.has_outside:
                continue
            m = A.weight_mult(c)
            slow = A.arm_slow(p, c)
            fast = A.arm_sitting_crab(p, c, seed * 100 + i)
            tag = None
            if slow["walked"] and not fast["left"] and m["title"] > 1.6:
                tag = "walkout"
            elif (not slow["left"] and not fast["left"]
                  and slow["concession"] > fast["concession"] * 1.4
                  and fast["pkg"].title and m["title"] > 1.5):
                tag = "settled"
            elif slow["left"] and not fast["left"] and c.spec.rho >= 1.1:
                tag = "works_wins"
            if tag and tag not in found:
                found[tag] = (seed, i, c)
            if len(found) == len(want):
                return found
    return found


def main():
    os.makedirs(OUT, exist_ok=True)
    p = Params()
    found = pick(p)
    index = []
    for n, (tag, (seed, i, c)) in enumerate(sorted(found.items())):
        name = NAMES[(seed + i) % len(NAMES)]
        rec = record(p, c, seed * 100 + i, name)
        rec["provenance"] = {"seed": seed, "crab_index": i, "tag": tag,
                             "params": "molt.world.Params() defaults",
                             "generated_by": "research/molt/trace.py"}
        slug = tag
        path = os.path.join(OUT, f"trace-{slug}.json")
        with open(path, "w") as fh:
            json.dump(rec, fh, indent=1)
        index.append({"slug": slug, "name": name, "spec": c.spec.name,
                      "seed": seed, "crab_index": i})
        print(f"wrote {path}  ({name}, {c.spec.name}, seed {seed} #{i})")

    # the population panel: straight out of the committed experiment
    res = json.load(open(os.path.join(_HERE, "results_main.json")))
    on = res["clock_on"]
    sci = {
        "n": on["means"]["A_sign"]["n"],
        "seeds": res["seeds"],
        "mean_salary": round(res["mean_salary"]),
        "arms": {a: {k: round(v, 4) if k in ("left", "agreed", "base_pct",
                                             "title", "meetings", "days")
                     else round(v)
                     for k, v in m.items()}
                 for a, m in on["means"].items()},
        "paired": {k: {kk: round(vv) for kk, vv in v.items()}
                   for k, v in on["paired"].items()},
        "both_stay": on["both_stay"],
        "zero_clock": {"D-B": {k: round(v) for k, v in
                               res["clock_off"]["paired"]["D_sitting_crab-B_slow"].items()}},
        "identification": {k: round(v["paired"]["D_sitting_crab-C_slow_engine"]["joint"])
                           for k, v in res["identification"].items()},
        "index": index,
    }
    # the rebuild (PREREG AMENDMENT 1). The demo must not keep showing v1
    # numbers that v2 retracted, so the supersession travels with the data.
    try:
        v2 = json.load(open(os.path.join(_HERE, "results_v2_main.json")))
        ver, unv = v2["verifiable"], v2["unverifiable"]

        def champ(reg):
            mm = reg["clock_on"]["means"]
            bf = [a for a in mm if a.endswith("|best_first")]
            return max(bf, key=lambda a: mm[a]["joint"])

        cv, cu = champ(ver), champ(unv)
        sci["v2"] = {
            "bar": round(0.02 * v2["mean_salary"]),
            "n_archetypes": len(v2["archetypes"]),
            "clock_on": round(ver["clock_on"]["paired"][f"D_sitting_crab-{cv}"]["joint"]),
            "clock_off_verifiable": round(ver["clock_off"]["paired"][f"D_sitting_crab-{cv}"]["joint"]),
            "clock_off_verifiable_crab": round(ver["clock_off"]["paired"][f"D_sitting_crab-{cv}"]["crab"]),
            "clock_off_unverifiable": round(unv["clock_off"]["paired"][f"D_sitting_crab-{cu}"]["joint"]),
            "clock_off_unverifiable_crab": round(unv["clock_off"]["paired"][f"D_sitting_crab-{cu}"]["crab"]),
            "disclose_crab": round(ver["clock_on"]["paired"]["K10_disclose-K10_silent"]["crab"]),
            "disclose_works": round(ver["clock_on"]["paired"]["K10_disclose-K10_silent"]["works"]),
            "letter_regime_crab": round(ver["clock_on"]["means"]["D_sitting_crab"]["crab"]
                                        - unv["clock_on"]["means"]["D_sitting_crab"]["crab"]),
            "letter_regime_works": round(ver["clock_on"]["means"]["D_sitting_crab"]["works"]
                                         - unv["clock_on"]["means"]["D_sitting_crab"]["works"]),
            "archetype_ratio": round(
                max(ver["clock_on"]["paired"][f"D_sitting_crab-{a}"]["joint"]
                    for a in ver["clock_on"]["means"] if a.endswith("|best_first"))
                / min(ver["clock_on"]["paired"][f"D_sitting_crab-{a}"]["joint"]
                      for a in ver["clock_on"]["means"] if a.endswith("|best_first")), 2),
            "ordering_max": 650,
            "split_works": round(100 * ver["clock_on"]["paired"][f"D_sitting_crab-{cv}"]["works"]
                                 / ver["clock_on"]["paired"][f"D_sitting_crab-{cv}"]["joint"], 1),
        }
    except FileNotFoundError:
        pass
    with open(os.path.join(OUT, "science-data.json"), "w") as fh:
        json.dump(sci, fh, indent=1)
    print(f"wrote {os.path.join(OUT, 'science-data.json')}")


if __name__ == "__main__":
    main()
