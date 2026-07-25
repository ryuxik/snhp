"""AMENDMENT 10 — where does the renewal asymmetry change sign, and is that
crossing inside the range a careful person could defend?

    python research/crabs/run_amend10.py

K30 is fixed in PREREG AMENDMENT 10 §A10.4, written before this file ran.
The declared band for MOVE_PHYSICAL, [0.35, 1.65] months, is fixed in §A10.2
from published sources without reference to any ratio.
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

import numpy as np

from crabs.run_market import SEEDS, derive_market
from crabs.world import Params, regime_params

# A8's derivation: everything in the derived median that is NOT the physical
# move. spell overhead 0.25 + one engaged listing 0.08 + one month of search
# 0.15. So move_med = SEARCH_PART + MOVE_PHYSICAL.
SEARCH_PART = 0.48
SWEEP = (0.0, 0.35, 0.5, 0.7, 1.0, 1.25, 1.65, 2.0, 2.5, 3.1)
BAND_LO, BAND_HI = 0.35, 1.65          # PREREG A10.2, declared from sources
CENTRAL_LO, CENTRAL_HI = 0.70, 1.00
CALIBRATED_MOVE_MED = 3.60             # what the shipped model uses
REGIMES = ((0.0, "neutral"), (+0.09, "loss-like"), (-0.06, "gain-like"))


def cell(spec):
    from crabs import market
    market.RELET_RISK_ON = spec["relet"]
    base = Params(**{**Params().__dict__,
                     "move_med": spec["move_med"], "move_sigma": 0.21})
    p = regime_params(base, "burn")
    mp = market.MarketParams(n_stations=40, units=25)
    agg = None
    for s in SEEDS:
        r = market.simulate_market(p, mp, s, drift=spec["drift"])
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    d = derive_market(agg)
    return dict(move_physical=spec["move_physical"], move_med=spec["move_med"],
                relet=spec["relet"], drift=spec["drift"],
                regime=spec["regime"], ratio=d["wa_ratio_renew"],
                wa_t=d["wa_tenant_renew"], wa_l=d["wa_land_renew"],
                renew_growth=d["renew_growth"], retention=d["retention"])


def specs():
    out = []
    for mpx in SWEEP:
        for relet in (True, False):
            for drift, rg in REGIMES:
                out.append(dict(move_physical=mpx,
                                move_med=SEARCH_PART + mpx, relet=relet,
                                drift=drift, regime=rg))
    return out


def crossing(rows) -> float:
    """MOVE_PHYSICAL at which the ratio crosses 1.0, by linear interpolation.
    NaN if it never crosses inside the swept range."""
    rows = sorted(rows, key=lambda r: r["move_physical"])
    for a, b in zip(rows, rows[1:]):
        if (a["ratio"] - 1.0) * (b["ratio"] - 1.0) <= 0.0 and a["ratio"] != b["ratio"]:
            t = (1.0 - a["ratio"]) / (b["ratio"] - a["ratio"])
            return a["move_physical"] + t * (b["move_physical"]
                                             - a["move_physical"])
    return float("nan")


def main():
    t0 = time.time()
    with Pool(8) as pool:
        cells = pool.map(cell, specs(), chunksize=1)
    with open(os.path.join(_HERE, "results_amend10.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 band=[BAND_LO, BAND_HI],
                                 sweep=list(SWEEP), search_part=SEARCH_PART,
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    print("\nAMENDMENT 10 -- wa_tenant / wa_landlord in the RENEWAL channel")
    print(f"declared band for MOVE_PHYSICAL: [{BAND_LO}, {BAND_HI}] months "
          f"(${BAND_LO*2000:.0f}-${BAND_HI*2000:.0f}); "
          f"central [{CENTRAL_LO}, {CENTRAL_HI}]\n")
    for relet in (True, False):
        print(f"--- RELET_RISK_ON = {relet} "
              f"{'(as shipped, never ablated)' if relet else '(ABLATION)'} ---")
        print(f"{'MOVE_PHY':>9} {'$':>6} {'move_med':>9} " +
              " ".join(f"{rg:>11}" for _, rg in REGIMES) + "   band?")
        for mpx in SWEEP:
            rs = [next(c for c in cells if c["move_physical"] == mpx
                       and c["relet"] == relet and c["regime"] == rg)
                  for _, rg in REGIMES]
            mark = "  <-- IN BAND" if BAND_LO <= mpx <= BAND_HI else ""
            print(f"{mpx:>9.2f} {mpx*2000:>6.0f} {SEARCH_PART+mpx:>9.2f} " +
                  " ".join(f"{c['ratio']:>11.3f}" for c in rs) + mark)
        for _, rg in REGIMES:
            rows = [c for c in cells if c["relet"] == relet and c["regime"] == rg]
            x = crossing(rows)
            inside = BAND_LO <= x <= BAND_HI if x == x else False
            print(f"    crossing ({rg}): MOVE_PHYSICAL = "
                  + (f"{x:.3f} (${x*2000:.0f})" if x == x else "never")
                  + f"  -> {'INSIDE the band' if inside else 'outside the band'}")
        print()

    fires = False
    for relet in (True, False):
        for _, rg in REGIMES:
            rows = [c for c in cells if c["relet"] == relet and c["regime"] == rg]
            x = crossing(rows)
            if x == x and BAND_LO <= x <= BAND_HI:
                fires = True
    print("K30 (fires if the crossing falls INSIDE the declared band in either "
          f"RELET_RISK_ON state): {'FIRES' if fires else 'does NOT fire'}")

    # the bug hunt A10.4 demands if it fires: is the crossing a trivial
    # restatement of two levels, i.e. wa_land ~ constant while wa_t is linear?
    print("\n--- A10.4 bug hunt: is the crossing just two levels crossing? ---")
    for relet in (True, False):
        rows = sorted([c for c in cells if c["relet"] == relet
                       and c["regime"] == "neutral"],
                      key=lambda r: r["move_physical"])
        wl = np.array([r["wa_l"] for r in rows])
        wt = np.array([r["wa_t"] for r in rows])
        print(f"  RELET_RISK_ON={relet}: wa_land {wl.min():.0f}-{wl.max():.0f} "
              f"(spread {100*(wl.max()-wl.min())/wl.mean():.1f}% of mean), "
              f"wa_tenant {wt.min():.0f}-{wt.max():.0f}")
    print(f"\n[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
