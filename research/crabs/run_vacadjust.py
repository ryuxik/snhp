"""Diagnostic: what the post-hoc `VAC_ADJUST` retune (0.6 -> 3.0) moved.

`market.py`'s DECLARED-BEFORE-RUNNING docstring says `vac_adjust 0.6`; the module
ships 3.0, retuned after observing deflation. RESULTS.md's K20 table reports a
walk-away ratio of 1.08x while the shipped `results_market.json` says 1.474 --
consistent with the table predating the retune. This measures the gap instead of
assuming it, so the record can be corrected with a number rather than a guess.

    python research/crabs/run_vacadjust.py
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

from crabs.run_market import SEEDS, derive_market
from crabs.world import Params, regime_params


def cell(spec):
    from crabs import market
    market.VAC_ADJUST = spec["vac_adjust"]      # module constant, set per proc
    p = regime_params(Params(), "burn")
    mp = market.MarketParams(n_stations=40, units=25, **spec["mp"])
    agg = None
    for s in SEEDS:
        r = market.simulate_market(p, mp, s, drift=0.0)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    d = derive_market(agg)
    return dict(cell=spec["cell"], vac_adjust=spec["vac_adjust"],
                wa_t=d["wa_tenant_renew"], wa_l=d["wa_land_renew"],
                ratio=d["wa_ratio_renew"], zone=d["zone_renew"],
                renew_growth=d["renew_growth"],
                newlet_growth=d["newlet_growth"],
                retention=d["retention"], vacancy=d["vacancy"],
                renew_rent=d["renew_rent"], newlet_rent=d["newlet_rent"])


def main():
    t0 = time.time()
    specs = [dict(cell="baseline", vac_adjust=v, mp=dict())
             for v in (0.6, 1.0, 2.0, 3.0)]
    with Pool(4) as pool:
        cells = pool.map(cell, specs, chunksize=1)
    with open(os.path.join(_HERE, "results_vacadjust.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)
    print(f"\n{'VAC_ADJUST':>11} {'wa_tenant':>10} {'wa_land':>9} "
          f"{'K20 ratio':>10} {'renew_g':>9} {'newlet_g':>9} {'sit rent':>9} "
          f"{'vacancy':>8}")
    for c in cells:
        print(f"{c['vac_adjust']:>11.1f} {c['wa_t']:>10.0f} {c['wa_l']:>9.0f} "
              f"{c['ratio']:>10.3f} {100*c['renew_growth']:>8.2f}% "
              f"{100*c['newlet_growth']:>8.2f}% {c['renew_rent']:>9.1f} "
              f"{100*c['vacancy']:>7.2f}%")
    print("\nRESULTS.md K20 table reports 3062 / 2845 / 1.08; "
          "results_market.json ships 5077 / 3444 / 1.474.")
    print(f"[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
