"""AMENDMENT 3 §A3.1 (K1 re-run, K13, K14) and AMENDMENT 4 (arm K, K16-K18).

    python research/crabs/run_engine.py
    python research/crabs/analyze_engine.py

Sequenced per A3.5/A4.3: the K1 re-run against the REAL engine is reported before
K13, and arm K reports joint surplus before the split.
"""
from __future__ import annotations

import argparse, json, os, sys, time
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from crabs.policies import StationDP
from crabs.run import (EXPLORATORY, MAIN_SEEDS, derive, pilot_prior,
                       station_key, _d)
from crabs.world import (ASK_RANKED, Params, new_recorder, regime_params,
                         simulate_station)

UNITS = 50
_CACHE: dict = {}


def _station(base, regime, nodes, w):
    # DEFECT FIXED 2026-07-25 (AMENDMENT 11). The key was
    # `(regime, units, negotiator)` and omitted every parameter the DP reads --
    # `StationDP._leave_table` reads `p_exo(p, j)` directly -- so a sweep of any
    # of them silently reused another cell's solved policy. See
    # `run.station_key`. Behaviour-preserving for the shipped `specs()`, which
    # varies only `negotiator` and the two engine selectors.
    p = regime_params(base, regime)
    key = station_key(p, nodes, w, 0.0, False)
    if key not in _CACHE:
        _CACHE[key] = StationDP(p, nodes, w)
    return _CACHE[key]


def run_cell(spec):
    base = Params(**spec["params"])
    nodes, w = _CACHE["prior"]
    regime = spec["regime"]
    p_burn, p_meas = regime_params(base, "burn"), regime_params(base, regime)
    stb = _station(base, "burn", nodes, w)
    stm = _station(base, regime, nodes, w)
    agg = new_recorder()
    per = {k: [] for k in ("joint_phy", "joint_cash_phy", "tenant_phy",
                           "tenant_cash_phy", "landlord_phy", "turnover",
                           "success", "welfare_phy")}
    for seed in MAIN_SEEDS:
        rec = simulate_station(p_burn, p_meas, seed, regime, stb, stm,
                               spec["share"], ASK_RANKED)
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        d = derive(rec)
        for k in per:
            per[k].append(d[k] if k != "success" else d["success_rate"])
    out = {k: v for k, v in spec.items() if k != "params"}
    out["agg"] = agg
    out["derived"] = derive(agg)
    out["per_station"] = per
    return out


def specs():
    out = []
    for regime in ("loss", "gain"):
        for neg in ("ladder", "engine_single", "engine_bundle"):
            b = Params(**{**EXPLORATORY, "units": UNITS, "negotiator": neg})
            out.append(dict(cell=f"K1:{neg}", regime=regime, share=1.0,
                            negotiator=neg, tenant_engine=(neg != "ladder"),
                            landlord_engine=False, params=dict(b.__dict__)))
        for te, le, nm in ((False, False, "N/N"), (True, False, "T/N"),
                           (False, True, "N/L"), (True, True, "T/L")):
            b = Params(**{**EXPLORATORY, "units": UNITS, "negotiator": "matrix",
                          "tenant_engine": te, "landlord_engine": le})
            out.append(dict(cell=f"K:{nm}", regime=regime, share=1.0,
                            negotiator="matrix", tenant_engine=te,
                            landlord_engine=le, params=dict(b.__dict__)))
    return out


def _init(prior):
    _CACHE["prior"] = prior


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    prior = pilot_prior(Params(**EXPLORATORY))
    sp = specs()
    print(f"[run] {len(sp)} cells", flush=True)
    with Pool(a.procs, initializer=_init, initargs=(prior,)) as pool:
        cells = pool.map(run_cell, sp, chunksize=1)
    from crabs.demographics import (LABELS, median_move_cost,
                                    share_cost_burdened, share_term_over_rent)
    meta = dict(version="crabs-1.0", phase="engine", units=UNITS,
                n_stations=len(MAIN_SEEDS),
                station_seeds=[MAIN_SEEDS[0], MAIN_SEEDS[-1]],
                demographics=dict(labels=LABELS,
                                  share_term_over_rent=share_term_over_rent(),
                                  share_cost_burdened=share_cost_burdened(),
                                  median_move_cost=median_move_cost()),
                runtime_s=round(time.time() - t0, 1))
    out = os.path.join(_HERE, "results_engine.json")
    with open(out, "w") as f:
        json.dump(dict(meta=meta, cells=cells), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
