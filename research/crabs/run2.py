"""Phase 2 runner: landlord types, arm F BROADCAST, and the exploratory shocks.

    python research/crabs/run2.py --spec exploratory
    python research/crabs/run2.py --spec exploratory --shocks

PREREG AMENDMENT 1. Phase 1 is reported before this is run, so Phase 2 cannot
be tuned to rescue it. Kills K5-K8 are evaluated by analyze2.py; the shocks are
EXPLORATORY, carry no kills, and are reported separately.
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

from crabs.landlords import (INSTITUTIONAL, MEDIUM, MOM_AND_POP, TYPE_GEOMETRY,
                             make_landlord)
from crabs.policies import StationDP
from crabs.run import EXPLORATORY, MAIN_SEEDS, N_NODES, derive, pilot_prior, _d
from crabs.world import (ASK_PRICE, ASK_RANKED, Params, Shock, new_recorder,
                         regime_params, simulate_station)

TYPES = (INSTITUTIONAL, MEDIUM, MOM_AND_POP)
P2_SHARES = (0.0, 0.39, 0.75, 1.0)
ADAPT_SHARES = (0.0, 0.10, 0.25, 0.39, 0.50, 0.75, 1.0)
SHOCK_YEARS = 14

_CACHE: dict = {}


def _seeds(n: int, base: int = 1000):
    return list(range(base, base + n))


# --------------------------------------------------------------------- shocks
def make_shock(name: str) -> Shock:
    """EXPLORATORY (AMENDMENT 1 §A1.3). Fourteen measured years each."""
    n = SHOCK_YEARS
    drift = np.zeros(n)
    vac = np.ones(n)
    wealth = np.zeros(n)
    exodus = np.zeros(n)
    if name == "flu":
        # CRAB FLU: demand collapses for 8 periods. Vacancies spike, market rent
        # falls. Does tenant leverage actually appear, or do stations hold rent
        # and eat the vacancy?
        drift[3:11] = -0.10
        vac[3:11] = 2.0
        drift[11:] = +0.02
        vac[11:] = 1.3
    elif name == "migration":
        # THE AI CRAB MIGRATION: high-budget crabs arrive over 6 periods and bid
        # the comp up; then half of them leave at once.
        drift[2:8] = +0.08
        wealth[2:8] = 3.0        # months of extra tolerance for above-market rent
        drift[8] = -0.15
        exodus[8] = 0.5
    else:
        raise ValueError(name)
    return Shock(name=name, drift=drift, vac_mult=vac, wealth=wealth,
                 exodus=exodus)


# ---------------------------------------------------------------- one cell
def run_cell(spec: dict) -> dict:
    base = Params(**spec["params"])
    ltype, regime, arm = spec["type"], spec["regime"], spec["arm"]
    nodes, w = _CACHE["prior"]
    geo = TYPE_GEOMETRY[ltype]
    base = Params(**{**base.__dict__, "units": geo["units"]})
    if spec.get("shock"):
        base = Params(**{**base.__dict__, "meas_years": SHOCK_YEARS})
    p_burn = regime_params(base, "burn")
    p_meas = regime_params(base, "burn" if spec.get("shock") else regime)
    shock = make_shock(spec["shock"]) if spec.get("shock") else None

    st_burn = _get(base, INSTITUTIONAL, "burn", nodes, w, 0.0, False)
    if spec["adaptive"]:
        # An adaptive operator re-estimates adoption every year, so it is a
        # family of policies indexed by asker share, selected from what it
        # observed last year.
        st_meas = {s: _get(base, ltype, p_meas_regime(spec), nodes, w, s, True)
                   for s in ADAPT_SHARES}
    else:
        st_meas = _get(base, ltype, p_meas_regime(spec), nodes, w,
                       spec["share"], False)

    learn = arm.startswith("F")
    broadcast = bool(spec.get("broadcast"))
    strat = ASK_PRICE if spec["strategy"] == "price" else ASK_RANKED

    agg = new_recorder()
    per = {k: [] for k in ("surplus_pcy", "surplus_asker", "surplus_nonasker",
                           "retention", "success", "station_cash",
                           "ask_share")}
    years = []
    for seed in _seeds(geo["stations"]):
        sm = st_meas
        if ltype == MOM_AND_POP and not isinstance(sm, dict):
            # the documented 18.0% who hold a strict no-increase policy, drawn
            # per station from its own seed
            hold = float(np.random.default_rng(
                np.random.SeedSequence([seed, 77])).random()) < 0.180
            sm = _mom_variant(base, p_meas_regime(spec), nodes, w, hold)
        rec = simulate_station(p_burn, p_meas, seed, regime, st_burn, sm,
                               spec["share"], strat, learn=learn,
                               broadcast=broadcast, shock=shock,
                               series=bool(spec.get("shock")))
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        per["surplus_pcy"].append(_d(rec["surplus"], rec["crab_years"]))
        per["surplus_asker"].append(_d(rec["surplus_asker"],
                                       rec["crab_years_asker"]))
        per["surplus_nonasker"].append(_d(rec["surplus_nonasker"],
                                          rec["crab_years_nonasker"]))
        per["retention"].append(1.0 - _d(rec["left"], rec["renewals"]))
        per["success"].append(_d(rec["success"], rec["countered"]))
        per["station_cash"].append(_d(rec["station_cash"], rec["habitat_years"]))
        per["ask_share"].append(_d(rec["ask_share_sum"], rec["ask_share_n"]))
        if spec.get("shock"):
            years.append(rec["_years"])
    out = {k: v for k, v in spec.items() if k != "params"}
    out["agg"] = agg
    d = derive(agg)
    d["station_years"] = agg["habitat_years"] / geo["units"]
    d["ask_share"] = _d(agg["ask_share_sum"], agg["ask_share_n"])
    d["mean_belief"] = _d(agg["belief_sum"], agg["belief_n"])
    d["mean_ask_scale"] = _d(agg["ask_scale_sum"], agg["belief_n"])
    d["surplus_wealthy"] = _d(agg["surplus_wealthy"], agg["wealthy_years"])
    d["gain_from_countering"] = d["surplus_asker"] - d["surplus_nonasker"]
    out["derived"] = d
    out["per_station"] = per
    if years:
        out["series"] = _mean_series(years)
    return out


def p_meas_regime(spec):
    return "burn" if spec.get("shock") else spec["regime"]


def _get(base, ltype, regime, nodes, w, share, adaptive):
    key = (ltype, regime, round(share, 4), bool(adaptive), base.units,
           base.face_premium, base.sigma_turn)
    if key not in _CACHE:
        p = regime_params(base, regime)
        _CACHE[key] = make_landlord(ltype, p, nodes, w, share=share,
                                    adaptive=adaptive)
    return _CACHE[key]


def _mom_variant(base, regime, nodes, w, hold):
    key = ("momv", regime, bool(hold), base.units, base.sigma_turn)
    if key not in _CACHE:
        p = regime_params(base, regime)
        ll = make_landlord(MOM_AND_POP, p, nodes, w)
        ll.no_increase = hold
        _CACHE[key] = ll
    return _CACHE[key]


def _mean_series(years):
    n = len(years[0])
    keys = [k for k in years[0][0] if k != "year"]
    out = []
    for i in range(n):
        row = {"year": i}
        for k in keys:
            row[k] = float(np.mean([y[i][k] for y in years]))
        # retention that year, pooled
        nr = float(np.sum([y[i]["n_renew"] for y in years]))
        nl = float(np.sum([y[i]["n_left"] for y in years]))
        na = float(np.sum([y[i]["n_ask"] for y in years]))
        ns = float(np.sum([y[i]["n_succ"] for y in years]))
        row["retention"] = 1.0 - (nl / nr if nr else float("nan"))
        row["success_rate"] = ns / na if na else float("nan")
        out.append(row)
    return out


# ------------------------------------------------------------------- specs
def phase2_specs(base: Params) -> list:
    pd = dict(base.__dict__)
    out = []
    for ltype in TYPES:
        for regime in ("loss", "gain"):
            c = dict(params=pd, type=ltype, regime=regime)
            out.append(dict(arm="A", share=0.39, strategy="price",
                            adaptive=False, **c))
            out.append(dict(arm="B", share=1.0, strategy="price",
                            adaptive=False, **c))
            out.append(dict(arm="C", share=1.0, strategy="ranked",
                            adaptive=False, **c))
            for s in P2_SHARES:
                out.append(dict(arm="D", share=s, strategy="ranked",
                                adaptive=False, **c))
            for bc in (False, True):
                out.append(dict(arm="F", share=0.0, strategy="ranked",
                                adaptive=False, broadcast=bc, **c))
            if ltype == INSTITUTIONAL:
                for s in (0.39, 0.75, 1.0):
                    out.append(dict(arm="E", share=s, strategy="ranked",
                                    adaptive=True, **c))
                for bc in (False, True):
                    out.append(dict(arm="F-adaptive", share=0.0,
                                    strategy="ranked", adaptive=True,
                                    broadcast=bc, **c))
    return out


def shock_specs(base: Params) -> list:
    pd = dict(base.__dict__)
    out = []
    for name in ("flu", "migration"):
        for ltype in TYPES:
            out.append(dict(params=pd, type=ltype, regime="burn", arm="D",
                            share=0.39, strategy="ranked", adaptive=False,
                            shock=name))
    return out


def _init(prior):
    _CACHE["prior"] = prior


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="exploratory",
                    choices=("registered", "exploratory"))
    ap.add_argument("--shocks", action="store_true")
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()

    base = Params(**EXPLORATORY) if a.spec == "exploratory" else Params()
    t0 = time.time()
    print("[pilot] calibrating station prior ...", flush=True)
    prior = pilot_prior(base)
    specs = shock_specs(base) if a.shocks else phase2_specs(base)
    print(f"[run] {len(specs)} cells", flush=True)
    with Pool(a.procs, initializer=_init, initargs=(prior,)) as pool:
        cells = pool.map(run_cell, specs, chunksize=1)
    meta = dict(version="crabs-1.0", phase=2, spec=a.spec,
                shocks=bool(a.shocks), params=dict(base.__dict__),
                anchor_annual_rent=24000.0,
                geometry={k: v for k, v in TYPE_GEOMETRY.items()},
                runtime_s=round(time.time() - t0, 1))
    out = os.path.join(_HERE, f"results_phase2_{a.spec}"
                              f"{'_shocks' if a.shocks else ''}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=meta, cells=cells), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
