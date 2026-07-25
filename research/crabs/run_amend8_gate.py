"""AMENDMENT 8 §A8.4 items 4 and 5 — K20, K26 and GATE 3 on derived costs.

One knob against run_market.py's own cells: the switching-cost distribution is
either DRAWN (the calibrated move_med = 3.6) or DERIVED (whatever A8's search
process produces). Geometry, seeds and every other parameter unchanged.
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crabs.market import MarketParams, simulate_market
from crabs.run_market import SEEDS, derive_market
from crabs.world import Params, regime_params

DRAWN = (3.60, 0.70)        # SPEC §4, "calibrated to observed elasticity"
DERIVED = (1.48, 0.21)      # A8: median and fitted sigma of the search process


def cell(spec):
    base = Params(**{**Params().__dict__, "move_med": spec["med"],
                     "move_sigma": spec["sig"]})
    p = regime_params(base, "burn")
    mp = MarketParams(n_stations=40, units=25, **spec["mp"])
    agg = None
    for s in SEEDS:
        r = simulate_market(p, mp, s)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    out = dict(cell=spec["cell"], med=spec["med"], sig=spec["sig"])
    out["derived"] = derive_market(agg)
    out["raw"] = {k: agg[k] for k in ("n_renewal", "n_renewal_signed",
                                      "n_newlet_signed", "sitting_rent_sum",
                                      "sitting_rent_n")}
    return out


def specs():
    out = []
    for med, sig, tag in ((DRAWN[0], DRAWN[1], "drawn"),
                          (DERIVED[0], DERIVED[1], "derived")):
        for nm, mpk in (("baseline", dict()),
                        ("supply_shock", dict(completions_frac=0.30)),
                        ("a6a_secured", dict(secured_share=0.5))):
            out.append(dict(cell=f"{nm}[{tag}]", med=med, sig=sig, mp=mpk))
    return out


def main():
    t0 = time.time()
    with Pool(6) as pool:
        cells = pool.map(cell, specs(), chunksize=1)
    with open(os.path.join(_HERE, "results_amend8_gate.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 drawn=DRAWN, derived=DERIVED,
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    print(f"\n{'cell':22} {'renew_g':>9} {'newlet_g':>9} {'wa_ratio':>9} "
          f"{'reten':>8} {'sit_rent':>9} {'newlet_rent':>11}")
    for c in cells:
        d = c["derived"]
        print(f"{c['cell']:22} {100*d['renew_growth']:>8.3f}% "
              f"{100*d['newlet_growth']:>8.3f}% {d['wa_ratio_renew']:>9.3f} "
              f"{100*d['retention']:>7.2f}% {d['renew_rent']:>9.1f} "
              f"{d['newlet_rent']:>11.1f}")

    print("\n--- K20 (fires if tenant walk-away > landlord walk-away) ---")
    for c in cells:
        if not c["cell"].startswith("baseline"):
            continue
        r = c["derived"]["wa_ratio_renew"]
        print(f"  move_med={c['med']:.2f}: ratio {r:.3f} -> "
              f"{'FIRES (tenant weaker)' if r > 1 else 'DOES NOT FIRE (LANDLORD weaker)'}")

    print("\n--- GATE 3 ---")
    for c in cells:
        d = c["derived"]
        if c["cell"].startswith("supply_shock"):
            v8 = d["newlet_rent"] < d["renew_rent"]
            v9 = d["newlet_growth"] < 0 < d["renew_growth"]
            print(f"  {c['cell']}: V8 {'PASS' if v8 else 'FAIL'} "
                  f"(new-let {d['newlet_rent']:.1f} vs sitting "
                  f"{d['renew_rent']:.1f});  V9 {'PASS' if v9 else 'FAIL'} "
                  f"(new-let {100*d['newlet_growth']:+.3f}%, renewal "
                  f"{100*d['renew_growth']:+.3f}%)")
    print("\n--- K26 (secured vs unsecured, signal channel OFF) ---")
    for c in cells:
        if not c["cell"].startswith("a6a_secured"):
            continue
        d = c["derived"]
        print(f"  move_med={c['med']:.2f}: secured offer {d['secured_offer']:.4f} "
              f"vs unsecured {d['unsecured_offer']:.4f}  "
              f"(gap {100*(d['unsecured_offer']-d['secured_offer']):+.3f}% of market)")
    print(f"\n[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
