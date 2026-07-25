"""AMENDMENT 10, second half — derive `vacancy` and re-run the K20 crossing.

`Params.vacancy` (1.2 loss / 1.8 gain) is classified CIRCULAR: SPEC §5 sets it
from "39.7% of 2026 listings carried a concession", which is the model's own
V1/V5/V6 target. It sits in K20's DENOMINATOR next to `turn_cost` and
`RELET_RISK_ON`, so the shipped ratio is fitted-over-fitted.

`market.py` already runs a real matching process, and time-to-let is an OUTPUT
of it. This feeds that output back into `vacancy`, the same move A8 made for
`move_med`, and reports the K20 ratio on the full cross:

    MOVE_PHYSICAL sweep  x  {vacancy fitted, derived, upstream}  x  RELET_RISK_ON

THREE vacancy states, because the derived one is not clean on its own:

  fitted    1.2 / 1.8 per regime          CIRCULAR (the concession statistic)
  derived   realised vacant-months per completed let, from the matching loop.
            ENDOGENOUS, but contaminated: RESULTS Phase 5 §5's unfixed
            deflation defect inflates vacancy durations, so this is an UPPER
            BOUND, not a replacement.
  upstream  BASE_LET_MONTHS = 1.15, already declared in market.py from "30-41
            day commonly cited let times". UPSTREAM of the phenomenon and
            independent of the concession statistic -- the only one of the
            three that satisfies DESIGN-PRINCIPLES C.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crabs.run_amend10 import BAND_HI, BAND_LO, SEARCH_PART, SWEEP, crossing
from crabs.run_market import SEEDS, derive_market
from crabs.world import Params, regime_params

FIT_SEEDS = SEEDS[:10]          # the fixed point needs fewer stations than the
                                # reported cells; declared, not tuned


def _one(p, mp_kw, seeds, drift=0.0):
    from crabs import market
    agg = None
    for s in seeds:
        r = market.simulate_market(p, market.MarketParams(
            n_stations=40, units=25, **mp_kw), s, drift=drift)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    return agg


def realised_let_months(agg) -> float:
    """Months a habitat sits vacant per completed let -- an OUTPUT of the
    matching process, not a constant."""
    return agg["vacant_months"] / max(agg["n_newlet_signed"], 1.0)


def fixed_point(n_iter: int = 4):
    """`vacancy` enters the renewal walk-away, which moves the offer, which
    moves who leaves, which moves the pool, which moves time-to-let. So the
    derivation has feedback and has to be iterated rather than read off once."""
    p = regime_params(Params(), "burn")
    hist = []
    for _ in range(n_iter):
        v = realised_let_months(_one(p, dict(), FIT_SEEDS))
        hist.append(v)
        p = replace(p, vacancy=v)          # AFTER regime_params -- REGIMES
                                           # overrides `vacancy`, so setting it
                                           # on the pre-regime Params is a no-op
    return hist


def cell(spec):
    from crabs import market
    market.RELET_RISK_ON = spec["relet"]
    base = Params(**{**Params().__dict__,
                     "move_med": spec["move_med"], "move_sigma": 0.21})
    p = regime_params(base, "burn")
    if spec["vacancy"] is not None:
        p = replace(p, vacancy=spec["vacancy"])
    agg = _one(p, dict(), SEEDS)
    d = derive_market(agg)
    return dict(move_physical=spec["move_physical"], relet=spec["relet"],
                vac_mode=spec["vac_mode"], vacancy=spec["vacancy"],
                ratio=d["wa_ratio_renew"], wa_t=d["wa_tenant_renew"],
                wa_l=d["wa_land_renew"],
                let_months=realised_let_months(agg))


def main():
    t0 = time.time()
    print("[fixed point] deriving `vacancy` from realised time-to-let ...",
          flush=True)
    hist = fixed_point()
    derived = hist[-1]
    print("  iterations: " + " -> ".join(f"{v:.3f}" for v in hist))
    print(f"  converged   : {derived:.3f} months")
    print(f"  fitted      : 1.5 (burn) / 1.2 (loss) / 1.8 (gain)  [CIRCULAR]")
    print(f"  upstream    : 1.15  [BASE_LET_MONTHS, 30-41 day let times]")

    from crabs.market import BASE_LET_MONTHS
    modes = (("fitted", None), ("derived", derived),
             ("upstream", BASE_LET_MONTHS))
    specs = [dict(move_physical=m, move_med=SEARCH_PART + m, relet=rl,
                  vac_mode=nm, vacancy=v)
             for m in SWEEP for rl in (True, False) for nm, v in modes]
    with Pool(8) as pool:
        cells = pool.map(cell, specs, chunksize=1)

    with open(os.path.join(_HERE, "results_amend10_vacancy.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 fixed_point=hist, derived_vacancy=derived,
                                 band=[BAND_LO, BAND_HI],
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    print(f"\nK20 ratio = wa_tenant / wa_landlord, neutral drift\n")
    hdr = f"{'MOVE_PHY':>9} {'$':>6}"
    for nm, _ in modes:
        for rl in (True, False):
            hdr += f" {nm[:4]}/{'RR' if rl else 'no'}".rjust(12)
    print(hdr + "   band?")
    for m in SWEEP:
        row = f"{m:>9.2f} {m*2000:>6.0f}"
        for nm, _ in modes:
            for rl in (True, False):
                c = next(x for x in cells if x["move_physical"] == m
                         and x["relet"] is rl and x["vac_mode"] == nm)
                row += f"{c['ratio']:>12.3f}"
        print(row + ("  <-- IN BAND" if BAND_LO <= m <= BAND_HI else ""))

    print("\ncrossing of ratio = 1.0, by combination:")
    fires = []
    for nm, v in modes:
        for rl in (True, False):
            rows = [c for c in cells if c["relet"] is rl
                    and c["vac_mode"] == nm]
            x = crossing(rows)
            inside = (x == x) and BAND_LO <= x <= BAND_HI
            fires.append(inside)
            vs = "regime" if v is None else f"{v:.2f}"
            print(f"  vacancy={nm:<8} ({vs:>6})  RELET_RISK_ON={str(rl):<5} -> "
                  + (f"MOVE_PHYSICAL {x:.3f} (${x*2000:.0f})" if x == x
                     else "never crosses")
                  + f"   {'INSIDE BAND' if inside else 'outside'}")
    print(f"\nK30 on the full cross (fires if ANY combination crosses inside "
          f"[{BAND_LO}, {BAND_HI}]): "
          f"{'FIRES' if any(fires) else 'does NOT fire'}  "
          f"({sum(fires)}/{len(fires)} combinations land inside)")
    print(f"\n[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
