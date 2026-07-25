"""AMENDMENT 9 — run the costly-verifiable-signal arm, and ablate its mechanism.

    python research/crabs/run_amend9.py

Cells come from `run_market.amendment9_specs`, so the arm lives in the ordinary
runner rather than in a private harness. Adds A9.3's `move_med` crossing, which
run_market.py cannot express because `move_med` is a `Params` field.

Kills K28 / K29 are fixed in PREREG AMENDMENT 9 §A9.4, written before this file.
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
from crabs.run_market import SEEDS, amendment9_specs, derive_market
from crabs.world import Params, regime_params

BASE = dict(n_stations=40, units=25)
K28_BAR = 0.02       # proved-vs-unproved offer gap, as a share of market rent
K29_BAR = 0.40       # noshape gap as a share of the with-shape gap
MOVE_MEDS = ((3.60, 0.70, "calibrated"), (1.48, 0.21, "A8-derived"))


def cell(spec):
    base = Params(**{**Params().__dict__, "move_med": spec["med"],
                     "move_sigma": spec["sig"]})
    p = regime_params(base, "burn")
    mp = MarketParams(**spec["mp"])
    agg = None
    for s in SEEDS:
        r = simulate_market(p, mp, s, drift=spec.get("drift", 0.0))
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    d = derive_market(agg)
    return dict(cell=spec["cell"], med=spec["med"], tag=spec["tag"],
                shape=spec["mp"].get("deadline_shape", True),
                signal=spec["mp"].get("signal_enabled", False),
                cost=spec["mp"].get("signal_cost", 0.0),
                secured_offer=d["secured_offer"],
                unsecured_offer=d["unsecured_offer"],
                secured_surp=d["secured_surp"],
                unsecured_surp=d["unsecured_surp"],
                renew_growth=d["renew_growth"], retention=d["retention"],
                secured_n=agg["secured_n"], unsecured_n=agg["unsecured_n"])


def specs():
    out = []
    for med, sig, tag in MOVE_MEDS:
        # the K26 baseline the signal arm is one knob away from
        out.append(dict(cell="a6a_secured", med=med, sig=sig, tag=tag,
                        drift=0.0, mp=dict(BASE, deadline_shape=True,
                                           secured_share=0.5)))
        for s in amendment9_specs(BASE):
            out.append(dict(cell=s["cell"], med=med, sig=sig, tag=tag,
                            drift=s["drift"], mp=s["mp"]))
    return out


def main():
    t0 = time.time()
    sp = specs()
    with Pool(8) as pool:
        cells = pool.map(cell, sp, chunksize=1)
    with open(os.path.join(_HERE, "results_amend9.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 k28_bar=K28_BAR, k29_bar=K29_BAR,
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    def gap(c):
        return c["unsecured_offer"] - c["secured_offer"]

    for med, sig, tag in MOVE_MEDS:
        rows = [c for c in cells if c["tag"] == tag]
        print(f"\n=== move_med = {med:.2f} ({tag}) ===")
        print(f"{'cell':24} {'signal':>7} {'cliff':>6} {'proved q':>9} "
              f"{'unproved q':>11} {'gap':>8} {'prov surp':>10} "
              f"{'unprov surp':>12}")
        for c in rows:
            print(f"{c['cell']:24} {str(c['signal']):>7} "
                  f"{str(c['shape']):>6} {c['secured_offer']:>9.4f} "
                  f"{c['unsecured_offer']:>11.4f} {100*gap(c):>7.3f}% "
                  f"{c['secured_surp']:>10.0f} {c['unsecured_surp']:>12.0f}")

        on = [c for c in rows if c["signal"] and c["shape"]]
        off = [c for c in rows if c["signal"] and not c["shape"]]
        best = max((abs(gap(c)) for c in on), default=0.0)
        print(f"\n  K28 (fires if EVERY gap < {100*K28_BAR:.0f}% of market): "
              f"largest gap {100*best:.3f}% -> "
              f"{'FIRES' if best < K28_BAR else 'does NOT fire'}")
        for c_on, c_off in zip(on, off):
            g_on, g_off = abs(gap(c_on)), abs(gap(c_off))
            ratio = g_off / g_on if g_on > 1e-12 else float("nan")
            print(f"  K29 @ cost {c_on['cost']:.2f}: with cliff "
                  f"{100*g_on:.3f}%, without {100*g_off:.3f}%  ->  "
                  f"ratio {ratio:.3f} "
                  f"{'FIRES (it is the clock)' if ratio < K29_BAR else 'does NOT fire'}")
    print(f"\n[{time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
