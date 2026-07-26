"""Back-test the salary tool against the simulation it was derived from.

    python3 research/molt/backtest_tool.py

The tool makes three claims to a person. Each is checked here against the world
that produced it, on crabs the tool has never seen:

  V1  its VERDICT ranks people correctly. Someone told "strong" should
      actually do better than someone told "weak".
  V2  its headline number, the cost of replacing you, tracks the thing it is
      supposed to proxy: how much the employer will actually concede.
  V3  its top ROUTE is the one that pays. When it says "show the letter",
      showing the letter should be worth more than not showing it.

A tool whose advice does not survive its own simulation has no business being
shown to anyone, whatever the evidence module says.
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE)),
           os.path.join(os.path.dirname(os.path.dirname(_HERE)), "snhp"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from molt.v2 import draw_crab2
from molt.v3 import Params3, Season, crab_value3, works_cost3
from run7 import arm_engine
from vend.situations import salary_negotiation as TOOL

#: The simulation's specialisations, mapped onto the role families a person
#: would pick from in the tool. Nothing else about the crab is shown to it.
ROLE_MAP = {"HULL-WELDER": "frontline", "BRINE-CHEMIST": "professional",
            "NAV-PILOT": "scarce", "CARGO-BROKER": "revenue",
            "SHELL-SMITH": "leadership"}

P = dict(promo_raise=0.12, promo_market_lift=0.05, slot_frac=0.12,
         disclose_tau=0.0322)


def tool_view(c) -> dict:
    """Only what a person could type. The tool never sees the crab's internals."""
    return dict(
        salary=float(c.salary),
        role_family=ROLE_MAP.get(c.spec.name, "professional"),
        has_outside_offer=bool(c.has_outside),
        offer_is_provable=bool(c.has_outside),   # they'd show it if they had it
        offer_premium_pct=int(round(100 * c.omega)) if c.has_outside else 0,
        months_in_role=int(c.tenure * 12),
        cycle_open=True,
    )


def main(seeds=(7, 11, 23, 31, 101), seasons=2, nc=40):
    p = Params3(**P)
    rows = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        for _ in range(seasons):
            sea = copy.deepcopy(Season.draw(p, rng, nc))
            for i in range(nc):
                c = draw_crab2(i, p, rng)
                r = arm_engine(p, c, sea, seed * 1000 + i, True, False)
                if r["pkg"].title and not r["left"]:
                    sea.slots_left -= 1
                if r["left"]:
                    continue
                v = tool_view(c)
                out = TOOL.assess(v)
                rows.append(dict(
                    verdict=out.verdict,
                    headline_low=out.context["replacement_cost_low_usd"],
                    top_route=out.routes[0].key,
                    provable=v["offer_is_provable"],
                    # what actually happened in the world
                    realised=r["crab"],
                    conceded=works_cost3(p, c, sea, r["pkg"]),
                    salary=c.salary,
                ))
    n = len(rows)
    print(f"n = {n} crab-seasons the tool has never seen\n")

    # ---- V1: does the verdict rank people correctly?
    print("V1  does the verdict rank people correctly?")
    order = {"weak": 0, "moderate": 1, "strong": 2}
    by = {k: [r["realised"] / r["salary"] for r in rows if r["verdict"] == k]
          for k in order}
    for k in ("weak", "moderate", "strong"):
        v = by[k]
        if v:
            print(f"    {k:9s} n={len(v):5d}   realised {np.mean(v):6.1%} of salary")
    seq = [np.mean(by[k]) for k in ("weak", "moderate", "strong") if by[k]]
    v1 = all(a < b for a, b in zip(seq, seq[1:]))
    print(f"    -> {'PASS, monotone' if v1 else 'FAIL, the ranking does not hold'}\n")

    # ---- V2: does the headline number track what they actually concede?
    print("V2  does 'what replacing you costs' track what they concede?")
    x = np.array([r["headline_low"] for r in rows])
    y = np.array([r["conceded"] for r in rows])
    rho = float(np.corrcoef(np.argsort(np.argsort(x)), np.argsort(np.argsort(y)))[0, 1])
    print(f"    rank correlation = {rho:+.3f}")
    v2 = rho > 0.30
    print(f"    -> {'PASS' if v2 else 'FAIL, the headline does not proxy the thing it claims to'}\n")

    # ---- V3: is the top route the one that pays?
    print("V3  when it says 'show the letter', is showing it worth more?")
    shown = [r["realised"] / r["salary"] for r in rows if r["top_route"] == "show_the_letter"]
    other = [r["realised"] / r["salary"] for r in rows if r["top_route"] != "show_the_letter"]
    print(f"    told to show it   n={len(shown):5d}   realised {np.mean(shown):6.1%} of salary")
    print(f"    told anything else n={len(other):4d}   realised {np.mean(other):6.1%} of salary")
    v3 = np.mean(shown) > np.mean(other)
    print(f"    -> {'PASS' if v3 else 'FAIL'}\n")

    ok = v1 and v2 and v3
    print("=" * 66)
    print(f"BACK-TEST: {'PASS. The advice survives its own simulation.' if ok else 'FAIL. Do not ship this.'}")
    print("=" * 66)
    print("\nWhat this does NOT establish: that the simulation resembles a real")
    print("labour market. It establishes only that the tool is a faithful")
    print("summary of the model it came from. Those are different claims and")
    print("only the second one is tested here.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
