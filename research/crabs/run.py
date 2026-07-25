"""Arm runner for PREREG.md. Seeds are fixed in code (SPEC §9) and reported.

    python research/crabs/run.py --phase 1
    python research/crabs/run.py --phase 1 --sens          # sensitivity sweeps
    python research/crabs/run.py --phase 1 --seeds heldout

Phase 1 = PREREG §4 arms A-E x {loss, gain} regimes.
"""
from __future__ import annotations

import argparse
import hashlib
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

from crabs.policies import StationDP
from crabs.world import (ASK_PRICE, ASK_RANKED, KIND_NAMES, Params,
                         new_recorder, regime_params, simulate_station,
                         switching_cost_nodes)

# ------------------------------------------------------------------- seeds
PILOT_SEEDS = list(range(9000, 9020))
MAIN_SEEDS = list(range(1000, 1060))
HELDOUT_SEEDS = list(range(7000, 7060))

N_NODES = 32                 # switching-cost quadrature nodes in the station's prior
PILOT_PRIOR = 100.0          # Dirichlet smoothing on the tenure-conditional prior
SHARES = (0.0, 0.10, 0.25, 0.50, 0.75, 1.0)

_CACHE: dict = {}

# ---------------------------------------------------------------- specifications
# REGISTERED: exactly the parameters declared in SPEC.md before the first run.
# EXPLORATORY: the registered spec plus unit-level dispersion in turn exposure.
# Adopted AFTER the registered gate failed, so every result computed under it is
# exploratory by PREREG §3 and its gate is re-run on held-out seeds. The change
# was motivated by a structural defect -- the concession decision is a single
# deterministic threshold evaluated on a tightly clustered state, so the counter
# success rate is all-or-nothing rather than a rate -- and NOT by the level of
# any gate number. It deliberately does NOT add the mechanism under test (a
# counter as an elasticity signal), which would make the experiment circular.
EXPLORATORY = dict(
    sigma_turn=0.5,          # make-ready ranges from a touch-up to a full
                             # renovation; p10/p90 ratio ~3.6x
    sigma_vac=0.4,           # days-vacant swings with expiry month and unit
                             # desirability; p10/p90 ratio ~2.8x
    turn_tenure_slope=0.25,  # an 8-year habitat costs ~32% more to make ready
                             # than a 1-year habitat
)


# ------------------------------------------------------- station calibration
def pilot_prior(base: Params, n_iter: int = 2):
    """The station's tenure-conditional switching-cost prior.

    Survivors have high switching costs, so the marginal distribution is the
    wrong prior for a long-tenured crab. We give the station the correct one,
    measured off a pilot run on dedicated seeds (SPEC §5). This makes the
    station STRONGER: a naive prior would over-concede to long-tenure crabs and
    flatter V3."""
    nodes, edges = switching_cost_nodes(base, N_NODES)
    jm = base.j_max
    marg = np.ones(N_NODES) / N_NODES
    w = np.tile(marg, (jm + 1, 1))
    pb = regime_params(base, "burn")
    pb = Params(**{**pb.__dict__, "meas_years": 12})
    for _ in range(n_iter):
        st = StationDP(pb, nodes, w)
        counts = np.zeros((jm + 1, N_NODES))
        for seed in PILOT_SEEDS:
            rec = simulate_station(pb, pb, seed, "burn", st, st, 0.39,
                                   ASK_PRICE, collect=True)
            for j, c in rec["_csamples"]:
                counts[min(j, jm), int(np.searchsorted(edges, c))] += 1.0
        w = counts + PILOT_PRIOR * marg[None, :]
        w = w / w.sum(axis=1, keepdims=True)
    return nodes, w


def prior_key(nodes, w) -> str:
    """Exact fingerprint of the station's switching-cost prior. The solved policy
    is a function of it as much as of `Params`, and it is a process-level global
    in this runner, so it goes in the cache key rather than being assumed
    constant."""
    return hashlib.blake2b(np.ascontiguousarray(nodes, dtype=float).tobytes()
                           + np.ascontiguousarray(w, dtype=float).tobytes(),
                           digest_size=8).hexdigest()


def station_key(p: Params, nodes, w, share: float, adaptive: bool):
    """Cache key for a solved station policy.

    DEFECT FIXED 2026-07-25 (AMENDMENT 11, reported by the triage worker).
    The key used to be `(regime, share, adaptive, face_premium, p_substitute,
    p_continue)` -- the regime label plus exactly the three parameters
    `sens_specs` happens to sweep. Every OTHER parameter `StationDP` reads was
    absent from it, so a sweep of `p_exo_*`, `move_med`, `renewal_cap`,
    `turn_cost`, `q_new`, `nu` or `kappa_crab` silently reused a policy solved
    for a DIFFERENT parameter value and reported it as the swept cell's result.
    Nothing shipped in `RESULTS.md` went through that path -- `phase1_specs`
    holds `base` fixed and `sens_specs` sweeps only keyed parameters, which is
    why the defect survived -- but every sweep added later did.

    Keying on the whole frozen `Params` cannot go stale: over-keying costs one
    extra solve, under-keying is a wrong number that looks right. `regime` is
    absent because `regime_params` has already written it into `drift` and
    `vacancy`, which are fields of the key."""
    return (p, prior_key(nodes, w), round(float(share), 4), bool(adaptive))


def _station(base: Params, regime: str, nodes, w, share: float, adaptive: bool):
    p = regime_params(base, regime)
    key = station_key(p, nodes, w, share, adaptive)
    if key not in _CACHE:
        _CACHE[key] = StationDP(p, nodes, w, share=share, adaptive=adaptive)
    return _CACHE[key]


# ------------------------------------------------------------------ one cell
def run_cell(spec: dict) -> dict:
    base = Params(**spec["params"])
    regime, share = spec["regime"], spec["share"]
    strat = ASK_RANKED if spec["strategy"] == "ranked" else ASK_PRICE
    nodes, w = _CACHE["prior"]
    p_burn = regime_params(base, "burn")
    p_meas = regime_params(base, regime)
    st_burn = _station(base, "burn", nodes, w, 0.0, False)
    st_meas = _station(base, regime, nodes, w, share, spec["adaptive"])

    agg = new_recorder()
    per = {k: [] for k in ("surplus_pcy", "surplus_asker", "surplus_nonasker",
                           "retention", "success", "station_cash")}
    for seed in spec["seeds"]:
        rec = simulate_station(p_burn, p_meas, seed, regime, st_burn, st_meas,
                               share, strat)
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
    out = dict(spec)
    out.pop("params")
    out["agg"] = agg
    out["derived"] = derive(agg)
    out["per_station"] = per
    return out


def _d(a, b):
    return float(a) / float(b) if b else float("nan")


def derive(a: dict) -> dict:
    d = {
        "station_years": a["habitat_years"] / 50.0,
        "habitat_years": a["habitat_years"],
        "renewals": a["renewals"],
        "retention": 1.0 - _d(a["left"], a["renewals"]),
        "retention_asker": 1.0 - _d(a["left_asker"], a["renewals_asker"]),
        "retention_nonasker": 1.0 - _d(a["left_nonasker"], a["renewals_nonasker"]),
        "counter_rate": _d(a["countered"], a["renewals"]),
        "success_rate": _d(a["success"], a["countered"]),
        "success_rate_price": _d(a["success_price"], a["countered"]),
        "success_lt2": _d(a["success_lt2"], a["countered_lt2"]),
        "success_ge2": _d(a["success_ge2"], a["countered_ge2"]),
        "tenure_ratio": _d(_d(a["success_ge2"], a["countered_ge2"]),
                           _d(a["success_lt2"], a["countered_lt2"])),
        "surplus_pcy": _d(a["surplus"], a["crab_years"]),
        "surplus_asker": _d(a["surplus_asker"], a["crab_years_asker"]),
        "surplus_nonasker": _d(a["surplus_nonasker"], a["crab_years_nonasker"]),
        "station_cash_phy": _d(a["station_cash"], a["habitat_years"]),
        "station_obj_phy": _d(a["station_objective"], a["habitat_years"]),
        "turn_cost_phy": _d(a["turn_cost_paid"], a["habitat_years"]),
        "market_rent": _d(a["market_sum"], a["habitat_years"]) / 12.0,
        "rent_ratio": _d(a["rent_ratio_sum"], a["rent_ratio_n"]),
        "mean_offer_push": _d(a["push_sum"], a["push_n"]),
        "concession_pcy": _d(a["concession_value"], a["crab_years"]),
        "rounds_per_renewal": _d(a["rounds"], a["renewals"]),
        "calib_pred_leave": _d(a["pred_leave"], a["renewals"]),
        "calib_real_leave": _d(a["real_leave"], a["renewals"]),
        "ledger_gap": (a["station_cash"] - (a["crab_cash"] + a["arrival_cash"]
                                            - a["turn_cost_paid"])),
        # AMENDMENT 4: rent is a pure transfer, so it cancels in the joint total.
        # Joint surplus moves ONLY through deadweight (turn cost, vacancy, moving
        # cost) and through the preference-intensity premium. Both forms are
        # reported because they can point in opposite directions.
        "joint_cash_phy": _d(a["market_sum"] - a["turn_cost_paid"]
                             - a["vacancy_lost"] - a["move_cost_paid"],
                             a["habitat_years"]),
        "joint_phy": _d(a["market_sum"] + a["welfare_extra"]
                        - a["turn_cost_paid"] - a["vacancy_lost"]
                        - a["move_cost_paid"], a["habitat_years"]),
        "tenant_phy": _d(a["surplus"] + a["welfare_extra"], a["habitat_years"]),
        "tenant_cash_phy": _d(a["surplus"], a["habitat_years"]),
        "landlord_phy": _d(a["crab_cash"] - a["turn_cost_paid"],
                           a["habitat_years"]),
        "welfare_phy": _d(a["welfare_extra"], a["habitat_years"]),
        "deadweight_phy": _d(a["turn_cost_paid"] + a["vacancy_lost"]
                             + a["move_cost_paid"], a["habitat_years"]),
        "turnover": _d(a["left"], a["renewals"]),
        "zero_increase_share": _d(a["zero_increase"], a["renewals"]),
        "engine_util": _d(a["engine_util_sum"], a["engine_util_n"]),
        "issues_per_grant": _d(a["issues_conceded"], a["bundles_granted"]),
    }
    for k in KIND_NAMES:
        d[f"grant_share_{k}"] = _d(a[f"grant_{k}"], a["countered"])
    for j in range(1, 9):
        d[f"retention_ten{j}"] = 1.0 - _d(a[f"ten{j}_left"], a[f"ten{j}_renewals"])
    return d


# ------------------------------------------------------------------- phase 1
def phase1_specs(base: Params, seeds) -> list:
    pd = dict(base.__dict__)
    out = []
    for regime in ("loss", "gain"):
        common = dict(params=pd, regime=regime, seeds=seeds)
        out.append(dict(arm="A", share=0.39, strategy="price",
                        adaptive=False, **common))
        out.append(dict(arm="B", share=1.0, strategy="price",
                        adaptive=False, **common))
        out.append(dict(arm="C", share=1.0, strategy="ranked",
                        adaptive=False, **common))
        for s in SHARES:
            out.append(dict(arm="D", share=s, strategy="ranked",
                            adaptive=False, **common))
        for s in SHARES:
            out.append(dict(arm="E", share=s, strategy="ranked",
                            adaptive=True, **common))
    return out


def _init(prior):
    _CACHE["prior"] = prior


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, default=1)
    ap.add_argument("--seeds", default="main", choices=("main", "heldout"))
    ap.add_argument("--sens", action="store_true")
    ap.add_argument("--spec", default="registered",
                    choices=("registered", "exploratory"))
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    base = Params(**EXPLORATORY) if a.spec == "exploratory" else Params()
    seeds = MAIN_SEEDS if a.seeds == "main" else HELDOUT_SEEDS
    t0 = time.time()
    print(f"[pilot] calibrating the station's tenure-conditional prior "
          f"(seeds {PILOT_SEEDS[0]}-{PILOT_SEEDS[-1]}) ...", flush=True)
    prior = pilot_prior(base)
    print(f"[pilot] done in {time.time()-t0:.1f}s", flush=True)

    specs = phase1_specs(base, seeds)
    if a.sens:
        specs = sens_specs(base, seeds)

    print(f"[run] {len(specs)} cells x {len(seeds)} stations", flush=True)
    with Pool(a.procs, initializer=_init, initargs=(prior,)) as pool:
        cells = pool.map(run_cell, specs, chunksize=1)

    meta = dict(
        version="crabs-1.0", phase=a.phase, seeds_used=a.seeds, spec=a.spec,
        pilot_seeds=[PILOT_SEEDS[0], PILOT_SEEDS[-1]],
        station_seeds=[seeds[0], seeds[-1]], n_stations=len(seeds),
        params=dict(base.__dict__), anchor_annual_rent=24000.0,
        n_nodes=N_NODES, runtime_s=round(time.time() - t0, 1),
    )
    out = a.out or os.path.join(
        _HERE, f"results_phase{a.phase}_{a.spec}{'_sens' if a.sens else ''}"
               f"{'_heldout' if a.seeds == 'heldout' else ''}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=meta, cells=cells), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s", flush=True)


def sens_specs(base: Params, seeds) -> list:
    """Sensitivity on the three parameters SPEC §6-§7 flagged as decisive."""
    out = []
    for fp in (0.0, 0.5, 1.0, 2.0, 4.0):
        b = Params(**{**base.__dict__, "face_premium": fp})
        for regime in ("loss", "gain"):
            for arm, sh, strat in (("B", 1.0, "price"), ("C", 1.0, "ranked")):
                out.append(dict(arm=arm, share=sh, strategy=strat,
                                adaptive=False, regime=regime, seeds=seeds,
                                params=dict(b.__dict__), sens="face_premium",
                                sens_val=fp))
    for ps in (0.0, 0.35, 0.7, 1.0):
        b = Params(**{**base.__dict__, "p_substitute": ps})
        for regime in ("loss", "gain"):
            for arm, sh, strat in (("B", 1.0, "price"), ("C", 1.0, "ranked")):
                out.append(dict(arm=arm, share=sh, strategy=strat,
                                adaptive=False, regime=regime, seeds=seeds,
                                params=dict(b.__dict__), sens="p_substitute",
                                sens_val=ps))
    for pc in (0.3, 0.6, 0.9):
        b = Params(**{**base.__dict__, "p_continue": pc})
        for regime in ("loss", "gain"):
            for arm, sh, strat in (("B", 1.0, "price"), ("C", 1.0, "ranked")):
                out.append(dict(arm=arm, share=sh, strategy=strat,
                                adaptive=False, regime=regime, seeds=seeds,
                                params=dict(b.__dict__), sens="p_continue",
                                sens_val=pc))
    return out


if __name__ == "__main__":
    main()
