"""TRIAGE (f) -- the crab flu: "the station held face rent and ate vacancy while
concessions tripled; face rent is sticky BECAUSE it capitalises."

    python research/crabs/triage_shock.py

The stated mechanism is capitalisation, i.e. `face_premium` (INVENTED; SPEC §6
says cap-rate arithmetic implies far more than the 1.0 it ships with, so this
sweeps UP as well as down). DESIGN-PRINCIPLES C.2 requires the mechanism to be
ABLATED, not asserted: at `face_premium = 0` a dollar of face rent is worth
exactly its cash, so if the station still holds face rent and eats the vacancy
there, capitalisation is not what does it.

Also swept:
  size_scaled_face   the other parameter the claim was said to rest on
  renewal_cap        CIRCULAR (AMENDMENT 7); A7 asserts the flu result is
                     unaffected because the cap binds increases. Checked.
  move_med           CALIBRATED, and A8 derives 1.48 rather than 3.60.

Everything else -- geometry, seeds, the shock array -- is run2.py's, unchanged.
"""
from __future__ import annotations

import argparse
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

from crabs import run as R
from crabs import run2 as R2
from crabs.landlords import INSTITUTIONAL
from crabs.world import Params

UNITS = 200
PRE = (1, 2)                    # years before the collapse
DURING = (4, 5, 6, 7, 8, 9)     # inside it (drift -10% over years 3..10)
POST = (12, 13)

SWEEP = (
    [("face_premium", v) for v in (0.0, 0.5, 1.0, 2.0, 4.0)]
    + [("size_scaled_face", v) for v in (False, True)]
    + [("renewal_cap", v) for v in (0.12, 2.00)]
    + [("move_med", v) for v in (1.48, 3.60)]
    + [("kappa_crab", v) for v in (0.8, 1.6, 3.2)]
)


def specs():
    base0 = Params(**R.EXPLORATORY)
    out = []
    for name, val in SWEEP:
        b = Params(**{**base0.__dict__, name: val})
        out.append(dict(params=dict(b.__dict__), type=INSTITUTIONAL,
                        regime="burn", arm="D", share=0.39, strategy="ranked",
                        adaptive=False, shock="flu", sweep=name, sweep_val=val))
    return out


def _mean(series, years, key):
    v = [series[y][key] for y in years if y < len(series)]
    v = [x for x in v if np.isfinite(x)]
    return float(np.mean(v)) if v else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=6)
    a = ap.parse_args()
    t0 = time.time()
    sp = specs()
    print(f"[run] flu: {len(sp)} cells", flush=True)
    # one prior per move_med, because the quadrature nodes depend on it
    priors = {}
    for mm in sorted({s["params"]["move_med"] for s in sp}):
        priors[mm] = R.pilot_prior(Params(**{**R.EXPLORATORY, "move_med": mm}))
    cells = []
    for mm, prior in priors.items():
        sub = [s for s in sp if s["params"]["move_med"] == mm]
        with Pool(a.procs, initializer=R2._init, initargs=(prior,)) as pool:
            cells.extend(pool.map(R2.run_cell, sub, chunksize=1))

    rows = []
    for c in cells:
        s = c["series"]
        r = dict(sweep=c["sweep"], val=c["sweep_val"])
        for lbl, yrs in (("pre", PRE), ("during", DURING), ("post", POST)):
            r[f"rmkt_{lbl}"] = _mean(s, yrs, "rent_ratio")
            r[f"succ_{lbl}"] = _mean(s, yrs, "success_rate")
            r[f"ret_{lbl}"] = _mean(s, yrs, "retention")
            r[f"vac_{lbl}"] = _mean(s, yrs, "vacancy_months") / UNITS
            r[f"mkt_{lbl}"] = _mean(s, yrs, "market")
        r["rmkt_delta"] = r["rmkt_during"] - r["rmkt_pre"]
        r["succ_mult"] = (r["succ_during"] / r["succ_pre"]
                          if r["succ_pre"] > 1e-9 else float("nan"))
        r["vac_mult"] = (r["vac_during"] / r["vac_pre"]
                         if r["vac_pre"] > 1e-9 else float("nan"))
        r["mkt_fall"] = r["mkt_during"] / r["mkt_pre"] - 1.0
        rows.append(r)

    out = os.path.join(_HERE, "results_triage_flu.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(units=UNITS, pre=PRE, during=DURING,
                                 runtime_s=round(time.time() - t0, 1)),
                       rows=rows, cells=cells), f)

    print("\nCRAB FLU -- does the station hold FACE RENT and eat the vacancy?\n")
    hdr = (f"{'sweep':18}{'val':>7}{'mkt fall':>10}{'r/mkt pre':>11}"
           f"{'during':>9}{'delta':>8}{'succ pre':>10}{'during':>9}{'x':>6}"
           f"{'vac pre':>9}{'during':>8}{'ret pre':>9}{'during':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['sweep']:18}{str(r['val']):>7}{r['mkt_fall']*100:>9.1f}%"
              f"{r['rmkt_pre']:>11.4f}{r['rmkt_during']:>9.4f}"
              f"{r['rmkt_delta']*100:>7.2f}p{r['succ_pre']:>10.3f}"
              f"{r['succ_during']:>9.3f}{r['succ_mult']:>6.2f}"
              f"{r['vac_pre']:>9.3f}{r['vac_during']:>8.3f}"
              f"{r['ret_pre']:>9.3f}{r['ret_during']:>8.3f}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
