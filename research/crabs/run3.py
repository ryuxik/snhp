"""GATE 2 (V4-V7, K9), the primitive ablation, and arms G-J (K10-K12).
AMENDMENT 2, run per AMENDMENT 6 §A6.4 regardless of Gate 3's outcome.

    python research/crabs/run3.py && python research/crabs/analyze3.py

Every primitive value is fixed in SPEC-A2.md, written before any Phase-3 output
existed. Nothing here is tuned to V4-V7.
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

from crabs.emergent import EmergentDP
from crabs.run import EXPLORATORY, N_NODES, PILOT_SEEDS, derive, _d
from crabs.world import (ASK_PRICE, ASK_RANKED, Params, new_recorder,
                         regime_params, simulate_station, switching_cost_nodes)

# --- SPEC-A2 §A2-2: declared before any run, never tuned to V4-V7 -----------
PRIMITIVES = dict(
    risk_rho=5.0, comp_sigma0=0.25, nonpec0=0.5, raise_cost0=0.6,
    u_personal=10.0, turn_scale_beta=1.0, u_cap=50.0, size_scaled_face=True,
)
INST, MOM = 200, 5
STATIONS = {INST: 60, MOM: 500}
ABLATE = ("risk_rho", "comp_sigma0", "nonpec0", "raise_cost0",
          "turn_scale_beta", "size_scaled_face")
_C: dict = {}


def _base(units, **over):
    return Params(**{**EXPLORATORY, **PRIMITIVES, "units": units, **over})


def _dp(base, regime, wc=None):
    key = (regime, base.units, base.risk_rho, base.comp_sigma0, base.nonpec0,
           base.raise_cost0, base.turn_scale_beta, base.size_scaled_face,
           base.agent_bonus, base.menu_costs, base.ask_mode, base.no_concessions,
           wc is not None)
    if key not in _C:
        nodes, w = _C["prior"]
        _C[key] = EmergentDP(regime_params(base, regime), nodes, w,
                             weights_counter=wc)
    return _C[key]


def counter_prior(base, regime, ask_mode):
    """The switching-cost distribution the station believes it faces GIVEN a
    counter (arms H/I). Measured on pilot seeds, never assumed."""
    nodes, w = _C["prior"]
    _, edges = switching_cost_nodes(base, N_NODES)
    jm = base.j_max
    marg = np.ones(N_NODES) / N_NODES
    p = Params(**{**base.__dict__, "ask_mode": ask_mode, "meas_years": 8})
    stb = _dp(p, "burn")
    stm = _dp(p, regime)
    counts = np.zeros((jm + 1, N_NODES))
    for seed in PILOT_SEEDS:
        rec = simulate_station(regime_params(p, "burn"), regime_params(p, regime),
                               seed, regime, stb, stm, 1.0, ASK_RANKED,
                               collect=True)
        for j, c in rec["_casker"]:
            counts[min(j, jm), int(np.searchsorted(edges, c))] += 1.0
    out = counts + 100.0 * marg[None, :]
    return out / out.sum(axis=1, keepdims=True)


def run_cell(spec):
    base = Params(**spec["params"])
    regime = spec["regime"]
    wc = None
    if spec.get("counter_prior"):
        wc = counter_prior(base, regime, base.ask_mode)
    stb = _dp(base, "burn")
    stm = _dp(base, regime, wc)
    agg = new_recorder()
    per = {k: [] for k in ("success", "zero_increase_share", "mean_offer_push",
                           "surplus_pcy", "surplus_asker", "surplus_nonasker",
                           "station_cash_phy", "retention")}
    seeds = list(range(1000, 1000 + STATIONS[base.units]))
    for seed in seeds:
        rec = simulate_station(regime_params(base, "burn"),
                               regime_params(base, regime), seed, regime, stb,
                               stm, spec["share"],
                               ASK_PRICE if spec["strategy"] == "price"
                               else ASK_RANKED)
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        d = derive(rec)
        for k in per:
            per[k].append(d[k] if k != "success" else d["success_rate"])
    out = {k: v for k, v in spec.items() if k != "params"}
    out["units"] = base.units
    out["derived"] = derive(agg)
    out["per_station"] = per
    return out


def specs():
    out = []
    for u in (INST, MOM):
        for regime in ("loss", "gain"):
            # GATE 2 baseline: primitives only, no arm-G-J mechanism
            out.append(dict(cell="gate2", regime=regime, share=0.39,
                            strategy="price", params=dict(_base(u).__dict__)))
            # primitive ablation, one at a time
            for a in ABLATE:
                off = {a: (False if a == "size_scaled_face" else 0.0)}
                out.append(dict(cell=f"ablate:{a}", regime=regime, share=0.39,
                                strategy="price",
                                params=dict(_base(u, **off).__dict__)))
            # arms G-J, each alone
            out.append(dict(cell="armG", regime=regime, share=0.39,
                            strategy="ranked",
                            params=dict(_base(u, menu_costs=True).__dict__)))
            for mode in ("tool", "everyone", "selfselect"):
                out.append(dict(cell=f"armH:{mode}", regime=regime, share=0.39,
                                strategy="ranked", counter_prior=True,
                                params=dict(_base(u, ask_mode=mode).__dict__)))
            out.append(dict(cell="armI:noconc", regime=regime, share=0.39,
                            strategy="ranked",
                            params=dict(_base(u, ask_mode="selfselect",
                                              no_concessions=True).__dict__)))
            out.append(dict(cell="armJ", regime=regime, share=0.39,
                            strategy="ranked",
                            params=dict(_base(u, agent_bonus=1.0).__dict__)))
    return out


def _init(prior):
    _C["prior"] = prior


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    nodes, edges = switching_cost_nodes(_base(INST), N_NODES)
    prior = (nodes, np.tile(np.ones(N_NODES) / N_NODES, (9, 1)))
    sp = specs()
    print(f"[run] {len(sp)} cells", flush=True)
    with Pool(a.procs, initializer=_init, initargs=(prior,)) as pool:
        cells = pool.map(run_cell, sp, chunksize=1)
    meta = dict(version="crabs-1.0", phase="gate2", primitives=PRIMITIVES,
                geometry={str(k): v for k, v in STATIONS.items()},
                runtime_s=round(time.time() - t0, 1))
    out = os.path.join(_HERE, "results_gate2.json")
    with open(out, "w") as f:
        json.dump(dict(meta=meta, cells=cells), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
