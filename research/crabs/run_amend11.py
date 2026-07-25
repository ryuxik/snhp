"""AMENDMENT 11 — un-fit `p_exo_*` (Job 1) and the `belief0`/`courage_med`
ratio (Job 2), and re-run everything they touch (Job 3).

    python research/crabs/run_amend11.py j1      # Phase 1 under sourced p_exo
    python research/crabs/run_amend11.py j1m     # market: GATE 3 V10, K21
    python research/crabs/run_amend11.py j1a7    # A7's "either fact, not both"
    python research/crabs/run_amend11.py j1k18   # arm K turnover (K18)
    python research/crabs/run_amend11.py j2      # arm F: the counter rate
    python research/crabs/run_amend11.py all

Kills K31 and K32 are fixed in PREREG-A11.md, written before this file. Results
go to RESULTS-A11.md; PREREG.md and RESULTS.md are held open by another worker.

This file keeps its OWN solved-policy cache, keyed with `run.station_key`, and
rebuilds the station's switching-cost prior per variant -- `pilot_prior` runs a
simulation, so it is itself a function of `p_exo`. The shipped runners' partial
cache keys (fixed 2026-07-25, see PREREG-A11 §A11.5.3) are exactly the defect
that would have made a `p_exo` sweep silently reuse the fitted policy.
"""
from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from crabs.landlords import INSTITUTIONAL, MOM_AND_POP, TYPE_GEOMETRY, \
    make_landlord
from crabs.policies import StationDP
from crabs.run import (EXPLORATORY, MAIN_SEEDS, derive, pilot_prior,
                       station_key, _d)
from crabs.world import (ASK_PRICE, ASK_RANKED, CPS_NONHOUSING_SHARE,
                         COURAGE_MED_1H, P_EXO_CPS_NONHOUSING,
                         P_EXO_CPS_NONPRICE, Params, new_recorder,
                         regime_params, simulate_station)

# ------------------------------------------------------------------ variants
# PREREG-A11 §A11.2.5, fixed before the first run.
SHIPPED_MEAN = float(np.mean([0.24 + 0.18 * np.exp(-(j - 1) / 3.0)
                              for j in range(1, 9)]))          # 0.313859
_K1 = P_EXO_CPS_NONHOUSING / SHIPPED_MEAN
_K2 = P_EXO_CPS_NONPRICE / SHIPPED_MEAN

VARIANTS = {
    "F":   dict(p_exo_floor=0.24, p_exo_extra=0.18),            # shipped, fitted
    "S1":  dict(p_exo_floor=P_EXO_CPS_NONHOUSING, p_exo_extra=0.0),   # PRIMARY
    "S2":  dict(p_exo_floor=P_EXO_CPS_NONPRICE, p_exo_extra=0.0),
    "S1d": dict(p_exo_floor=0.24 * _K1, p_exo_extra=0.18 * _K1),
    "S2d": dict(p_exo_floor=0.24 * _K2, p_exo_extra=0.18 * _K2),
}
SWEEP = (0.03, 0.05, 0.075, P_EXO_CPS_NONHOUSING, 0.12, P_EXO_CPS_NONPRICE,
         0.18, 0.24, 0.29, 0.35, 0.42)

K31_LO, K31_HI = 0.52, 0.62          # PREREG-A11 §A11.2.7
K32_LO, K32_HI = 0.29, 0.49          # PREREG-A11 §A11.3.4 / §A11.5.2
CPS_TARGET = CPS_NONHOUSING_SHARE    # 0.612475, the S3 anchor

# Job 2. Only the RATIO belief0/courage_med enters the ask rule -- verified in
# PREREG-A11 §A11.5.1 -- so the grid is a grid of ratios, traced from BOTH ends
# to confirm they lie on one curve.
BELIEF0_UNINFORMATIVE = 0.50         # Beta(1,1) prior mean
RHO_SOURCED = BELIEF0_UNINFORMATIVE / COURAGE_MED_1H          # 27.73
COURAGE_GRID = (0.0045, 0.0090, COURAGE_MED_1H, 0.0361, 0.0721, 0.1803,
                0.36, 0.72, 1.44)
BELIEF_GRID = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.95)
CSIG_GRID = (0.4, 0.8, 1.2)

_C: dict = {}


# --------------------------------------------------------------------- utils
def prior_for(base: Params):
    """The station's tenure-conditional switching-cost prior. It is MEASURED off
    a pilot simulation, so it is a function of `p_exo` too and must be rebuilt
    per variant rather than shared."""
    key = base
    if key not in _C:
        _C[key] = pilot_prior(base)
    return _C[key]


def station(base: Params, regime: str, nodes, w, share=0.0, adaptive=False):
    p = regime_params(base, regime)
    key = station_key(p, nodes, w, share, adaptive)
    if key not in _C:
        _C[key] = StationDP(p, nodes, w, share=share, adaptive=adaptive)
    return _C[key]


def landlord(base: Params, ltype, regime, nodes, w, share=0.0, adaptive=False):
    p = regime_params(base, regime)
    key = (ltype,) + station_key(p, nodes, w, share, adaptive)
    if key not in _C:
        _C[key] = make_landlord(ltype, p, nodes, w, share=share,
                                adaptive=adaptive)
    return _C[key]


def agg_seeds(pb, pm, regime, stb, stm, share, strat, seeds, **kw):
    agg = new_recorder()
    per = {k: [] for k in ("retention", "counter", "success", "surplus_pcy",
                           "surplus_asker", "surplus_nonasker")}
    for s in seeds:
        r = simulate_station(pb, pm, s, regime, stb, stm, share, strat, **kw)
        for k, v in r.items():
            if not k.startswith("_"):
                agg[k] += v
        per["retention"].append(1.0 - _d(r["left"], r["renewals"]))
        per["counter"].append(_d(r["countered"], r["renewals"]))
        per["success"].append(_d(r["success"], r["countered"]))
        per["surplus_pcy"].append(_d(r["surplus"], r["crab_years"]))
        per["surplus_asker"].append(_d(r["surplus_asker"],
                                       r["crab_years_asker"]))
        per["surplus_nonasker"].append(_d(r["surplus_nonasker"],
                                          r["crab_years_nonasker"]))
    return agg, per


def se(xs):
    xs = [x for x in xs if x == x]
    return float(np.std(xs, ddof=1) / np.sqrt(len(xs))) if len(xs) > 1 else 0.0


def compose(agg):
    """The model's own reason-for-move composition, to be read against the CPS
    composition `p_exo` is now sourced from. AMENDMENT 11 instrumentation in
    `world.new_recorder`."""
    left = agg["left"]
    return dict(exo_share=_d(agg["left_exo"], left),
                endo_share=_d(agg["left_endo"], left),
                endo_only_share=_d(agg["left_endo_only"], left))


# ------------------------------------------------------------- JOB 1: phase 1
def j1():
    out = []
    for spec, over in (("registered", {}), ("exploratory", EXPLORATORY)):
        for vname, vp in VARIANTS.items():
            base = Params(**{**Params().__dict__, **over, **vp})
            nodes, w = prior_for(base)
            for regime in ("loss", "gain"):
                pb, pm = regime_params(base, "burn"), regime_params(base, regime)
                stb = station(base, "burn", nodes, w, 0.0, False)
                stm = station(base, regime, nodes, w, 0.39, False)
                agg, per = agg_seeds(pb, pm, regime, stb, stm, 0.39, ASK_PRICE,
                                     MAIN_SEEDS)
                d = derive(agg)
                row = dict(job="j1", spec=spec, variant=vname, regime=regime,
                           p_exo1=float(vp["p_exo_floor"] + vp["p_exo_extra"]),
                           p_exo8=float(vp["p_exo_floor"]
                                        + vp["p_exo_extra"]
                                        * np.exp(-7 / 3.0)),
                           **{k: d[k] for k in
                              ("retention", "turnover", "counter_rate",
                               "success_rate", "success_lt2", "success_ge2",
                               "tenure_ratio", "mean_offer_push", "rent_ratio",
                               "zero_increase_share", "surplus_pcy",
                               "station_cash_phy", "deadweight_phy")},
                           retention_se=se(per["retention"]),
                           **compose(agg))
                row["retention_ten"] = [d[f"retention_ten{j}"]
                                        for j in range(1, 9)]
                out.append(row)
                print(f"  j1 {spec:11} {vname:4} {regime:5} "
                      f"ret {row['retention']:.4f}+-{row['retention_se']:.4f} "
                      f"turn {row['turnover']:.4f} "
                      f"exo/left {row['exo_share']:.4f} "
                      f"succ {row['success_rate']:.4f} "
                      f"push {row['mean_offer_push']:+.4f}", flush=True)
    # the sweep, registered spec, for the S3 solve and the K31 curve
    for v in SWEEP:
        base = Params(**{**Params().__dict__, "p_exo_floor": float(v),
                         "p_exo_extra": 0.0})
        nodes, w = prior_for(base)
        for regime in ("loss", "gain"):
            pb, pm = regime_params(base, "burn"), regime_params(base, regime)
            stb = station(base, "burn", nodes, w, 0.0, False)
            stm = station(base, regime, nodes, w, 0.39, False)
            agg, per = agg_seeds(pb, pm, regime, stb, stm, 0.39, ASK_PRICE,
                                 MAIN_SEEDS)
            d = derive(agg)
            out.append(dict(job="j1sweep", spec="registered", variant="flat",
                            regime=regime, p_exo=float(v),
                            retention=d["retention"], turnover=d["turnover"],
                            retention_se=se(per["retention"]),
                            success_rate=d["success_rate"],
                            tenure_ratio=d["tenure_ratio"],
                            mean_offer_push=d["mean_offer_push"],
                            **compose(agg)))
            print(f"  j1sweep p_exo={v:.4f} {regime:5} "
                  f"ret {d['retention']:.4f} exo/left "
                  f"{compose(agg)['exo_share']:.4f}", flush=True)
    return out


# -------------------------------------------------- JOB 1: market (V10, K21)
def j1m():
    from crabs.market import MarketParams, simulate_market
    from crabs.run_market import SEEDS, derive_market
    out = []
    mp = MarketParams(n_stations=40, units=25)
    for vname in ("F", "S1", "S2"):
        base = Params(**{**Params().__dict__, **VARIANTS[vname]})
        p = regime_params(base, "burn")
        agg = None
        for s in SEEDS:
            r = simulate_market(p, mp, s, drift=0.0)
            c = {k: v for k, v in r.items() if not k.startswith("_")}
            agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
        d = derive_market(agg)
        row = dict(job="j1m", variant=vname,
                   **{k: d[k] for k in
                      ("retention", "renew_growth", "newlet_growth",
                       "rent_gap", "move_gain", "move_gain_share", "vacancy",
                       "wa_tenant_renew", "wa_land_renew", "wa_ratio_renew",
                       "zone_renew", "deadweight_phy")})
        for q in range(4):
            row[f"move_gain_q{q}"] = d[f"move_gain_q{q}"]
            row[f"move_share_q{q}"] = d[f"move_share_q{q}"]
        out.append(row)
        print(f"  j1m {vname:3} ret {row['retention']:.4f} "
              f"rent_gap {row['rent_gap']:+.0f} "
              f"move_gain {row['move_gain']:+.0f} "
              f"share {row['move_gain_share']:.4f}", flush=True)
    return out


# ------------------------------------- JOB 3: A7's "either fact, not both"
def j1a7():
    """A7 reported: capped push +10.73% with retention 60.1%; free push +13.81%
    with retention 56.1% -- 'you can have either observed fact, not both'. The
    audit's objection is that both facts are FITTED, so the trade-off may not be
    real. Re-run the pair with the non-rent half of turnover sourced."""
    out = []
    for vname in ("F", "S1", "S2"):
        for cap, ctag in ((0.12, "capped"), (2.00, "free")):
            base = Params(**{**Params().__dict__, **VARIANTS[vname],
                             "renewal_cap": cap})
            nodes, w = prior_for(base)
            for regime in ("loss", "gain"):
                pb, pm = regime_params(base, "burn"), regime_params(base, regime)
                stb = station(base, "burn", nodes, w, 0.0, False)
                stm = station(base, regime, nodes, w, 0.39, False)
                agg, per = agg_seeds(pb, pm, regime, stb, stm, 0.39, ASK_PRICE,
                                     MAIN_SEEDS)
                d = derive(agg)
                out.append(dict(job="j1a7", variant=vname, cap=ctag,
                                regime=regime, renewal_cap=cap,
                                retention=d["retention"],
                                retention_se=se(per["retention"]),
                                mean_offer_push=d["mean_offer_push"],
                                rent_ratio=d["rent_ratio"],
                                success_rate=d["success_rate"],
                                **compose(agg)))
                print(f"  j1a7 {vname:3} {ctag:6} {regime:5} "
                      f"push {d['mean_offer_push']:+.4f} "
                      f"ret {d['retention']:.4f}", flush=True)
    return out


# --------------------------------------------------------- JOB 3: K18 (arm K)
def j1k18():
    """K18 -- mutual engines destroy value. Fires only if T/L has BOTH higher
    turnover than N/N AND lower joint surplus. The turnover half is downstream
    of `p_exo`."""
    out = []
    for vname in ("F", "S1"):
        base0 = Params(**{**EXPLORATORY, **VARIANTS[vname], "units": 50})
        nodes, w = prior_for(base0)
        for regime in ("loss", "gain"):
            for te, le, nm in ((False, False, "N/N"), (True, True, "T/L")):
                base = Params(**{**base0.__dict__, "negotiator": "matrix",
                                 "tenant_engine": te, "landlord_engine": le})
                pb = regime_params(base, "burn")
                pm = regime_params(base, regime)
                stb = station(base, "burn", nodes, w, 0.0, False)
                stm = station(base, regime, nodes, w, 0.0, False)
                agg, per = agg_seeds(pb, pm, regime, stb, stm, 1.0, ASK_RANKED,
                                     MAIN_SEEDS)
                d = derive(agg)
                out.append(dict(job="j1k18", variant=vname, cell=nm,
                                regime=regime, turnover=d["turnover"],
                                joint_phy=d["joint_phy"],
                                joint_cash_phy=d["joint_cash_phy"],
                                tenant_phy=d["tenant_phy"],
                                landlord_phy=d["landlord_phy"],
                                retention=d["retention"],
                                **compose(agg)))
                print(f"  j1k18 {vname:3} {nm:4} {regime:5} "
                      f"turn {d['turnover']:.4f} joint {d['joint_phy']:.0f}",
                      flush=True)
    return out


# --------------------------------------------------------------- JOB 2: arm F
_BLIND_CHECKED = set()


def _assert_dp_blind_to_courage(dpbase, base, ltype, regime, nodes, w):
    """PRINCIPLE B, checked once per (type, regime) rather than assumed: the
    landlord's solved offer must be bit-identical whether it is built from the
    canonical base or from the one carrying this cell's `belief0` /
    `courage_med` / `courage_sigma`. If it ever is not, the landlord is reading
    the tenant's private cost of asking."""
    key = (ltype, regime)
    if key in _BLIND_CHECKED or dpbase == base:
        return
    _BLIND_CHECKED.add(key)
    a = landlord(dpbase, ltype, regime, nodes, w, 0.0, False)
    b = landlord(base, ltype, regime, nodes, w, 0.0, False)
    for r in (0.85, 1.0, 1.15, 1.3):
        for j in (1, 4, 8):
            assert a.offer(r, j) == b.offer(r, j), (ltype, regime, r, j)


def _armF(base0, ltype, regime, belief0, courage_med, csig, broadcast,
          adaptive, seeds):
    geo = TYPE_GEOMETRY[ltype]
    base = Params(**{**base0.__dict__, "units": geo["units"],
                     "belief0": belief0, "courage_med": courage_med,
                     "courage_sigma": csig})
    # The landlord cannot see the tenant's prior or its cost of asking, so the
    # solved policy and the pilot prior are built from a base with all three
    # held at their defaults. This is a Principle B statement, not an
    # optimisation -- if the DP moved with `courage_med` the landlord would be
    # reading a tenant's private state. `_assert_dp_blind_to_courage` checks it
    # once per process rather than assuming it, which is the mistake the shipped
    # cache key made.
    dpbase = Params(**{**base.__dict__, "belief0": 0.10, "courage_med": 0.18,
                       "courage_sigma": 0.80})
    nodes, w = prior_for(dpbase)
    pb, pm = regime_params(base, "burn"), regime_params(base, regime)
    stb = landlord(dpbase, INSTITUTIONAL, "burn", nodes, w, 0.0, False)
    if adaptive:
        stm = {s: landlord(dpbase, ltype, regime, nodes, w, s, True)
               for s in (0.0, 0.10, 0.25, 0.39, 0.50, 0.75, 1.0)}
    else:
        stm = landlord(dpbase, ltype, regime, nodes, w, 0.0, False)
    _assert_dp_blind_to_courage(dpbase, base, ltype, regime, nodes, w)
    agg, per = agg_seeds(pb, pm, regime, stb, stm, 0.0, ASK_RANKED, seeds,
                         learn=True, broadcast=broadcast)
    d = derive(agg)
    return dict(counter_rate=d["counter_rate"],
                counter_se=se(per["counter"]),
                ask_share=_d(agg["ask_share_sum"], agg["ask_share_n"]),
                belief=_d(agg["belief_sum"], agg["belief_n"]),
                ask_scale=_d(agg["ask_scale_sum"], agg["belief_n"]),
                success_rate=d["success_rate"], retention=d["retention"],
                surplus_pcy=d["surplus_pcy"],
                surplus_asker=d["surplus_asker"],
                surplus_nonasker=d["surplus_nonasker"],
                se_asker=se(per["surplus_asker"]),
                se_nonasker=se(per["surplus_nonasker"]),
                se_total=se(per["surplus_pcy"]),
                station_cash_phy=d["station_cash_phy"])


def j2():
    base0 = Params(**EXPLORATORY)
    out = []

    # (a) THE RATIO IS THE KNOB. Trace the same curve from both ends.
    for regime in ("loss", "gain"):
        for cm in COURAGE_GRID:
            r = _armF(base0, INSTITUTIONAL, regime, BELIEF0_UNINFORMATIVE, cm,
                      0.80, False, False, MAIN_SEEDS[:20])
            out.append(dict(job="j2rho", regime=regime, arm="courage",
                            belief0=BELIEF0_UNINFORMATIVE, courage_med=cm,
                            rho=BELIEF0_UNINFORMATIVE / cm, csig=0.80, **r))
            print(f"  j2rho {regime:5} cm={cm:<7.4f} rho={BELIEF0_UNINFORMATIVE/cm:>9.3f} "
                  f"counter {r['counter_rate']:.4f}", flush=True)
        for b0 in BELIEF_GRID:
            r = _armF(base0, INSTITUTIONAL, regime, b0, 0.18, 0.80, False,
                      False, MAIN_SEEDS[:20])
            out.append(dict(job="j2rho", regime=regime, arm="belief",
                            belief0=b0, courage_med=0.18, rho=b0 / 0.18,
                            csig=0.80, **r))
            print(f"  j2rho {regime:5} b0={b0:<7.4f} rho={b0/0.18:>9.3f} "
                  f"counter {r['counter_rate']:.4f}", flush=True)
        for cs in CSIG_GRID:
            r = _armF(base0, INSTITUTIONAL, regime, BELIEF0_UNINFORMATIVE,
                      COURAGE_MED_1H, cs, False, False, MAIN_SEEDS[:20])
            out.append(dict(job="j2sig", regime=regime, arm="csig",
                            belief0=BELIEF0_UNINFORMATIVE,
                            courage_med=COURAGE_MED_1H, rho=RHO_SOURCED,
                            csig=cs, **r))
            print(f"  j2sig {regime:5} csig={cs} counter {r['counter_rate']:.4f}",
                  flush=True)

    # (b) the full Phase-2 §7 arm F table, shipped ratio vs sourced ratio
    cells = [(INSTITUTIONAL, "loss", False), (INSTITUTIONAL, "loss", True),
             (MOM_AND_POP, "loss", False), (MOM_AND_POP, "loss", True),
             (INSTITUTIONAL, "gain", False), (INSTITUTIONAL, "gain", True),
             (MOM_AND_POP, "gain", False), (MOM_AND_POP, "gain", True)]
    pairs = (("shipped", 0.10, 0.18), ("sourced", BELIEF0_UNINFORMATIVE,
                                       COURAGE_MED_1H))
    for tag, b0, cm in pairs:
        for ltype, regime, bcast in cells:
            seeds = list(range(1000, 1000 + TYPE_GEOMETRY[ltype]["stations"]))
            r = _armF(base0, ltype, regime, b0, cm, 0.80, bcast, False, seeds)
            out.append(dict(job="j2table", tag=tag, type=ltype, regime=regime,
                            broadcast=bcast, belief0=b0, courage_med=cm,
                            rho=b0 / cm, adaptive=False, **r))
            print(f"  j2table {tag:7} {ltype:13} {regime:5} bc={int(bcast)} "
                  f"counter {r['counter_rate']:.4f} "
                  f"ask {r['surplus_asker']:.0f} "
                  f"non {r['surplus_nonasker']:.0f}", flush=True)
        # F-adaptive institutional -- the cell K7 and K8 are decided on
        for regime in ("loss", "gain"):
            for bcast in (False, True):
                seeds = list(range(1000, 1060))
                r = _armF(base0, INSTITUTIONAL, regime, b0, cm, 0.80, bcast,
                          True, seeds)
                out.append(dict(job="j2table", tag=tag, type="inst-adaptive",
                                regime=regime, broadcast=bcast, belief0=b0,
                                courage_med=cm, rho=b0 / cm, adaptive=True,
                                **r))
                print(f"  j2table {tag:7} inst-adaptive {regime:5} "
                      f"bc={int(bcast)} counter {r['counter_rate']:.4f} "
                      f"tot {r['surplus_pcy']:.0f} ask {r['surplus_asker']:.0f} "
                      f"non {r['surplus_nonasker']:.0f}", flush=True)
    return out


JOBS = dict(j1=j1, j1m=j1m, j1a7=j1a7, j1k18=j1k18, j2=j2)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = list(JOBS) if which == "all" else [which]
    t0 = time.time()
    # one file per job, so jobs can run concurrently without clobbering each
    # other; analyze_amend11.py merges them
    path = os.path.join(_HERE, f"results_amend11_{which}.json")
    blob = {"meta": {}, "rows": []}
    for nm in names:
        print(f"[{nm}]", flush=True)
        blob["rows"] += JOBS[nm]()
    blob["meta"].update(dict(
        version="crabs-1.0", amendment=11,
        cps_source="US Census Bureau, Geographic Mobility: 2023 (2023 CPS "
                   "ASEC), Tables 1 and 13, released 2024-12-10",
        p_exo_cps_nonhousing=P_EXO_CPS_NONHOUSING,
        p_exo_cps_nonprice=P_EXO_CPS_NONPRICE,
        cps_nonhousing_share=CPS_NONHOUSING_SHARE,
        courage_med_1h=COURAGE_MED_1H, rho_sourced=RHO_SOURCED,
        k31_band=[K31_LO, K31_HI], k32_band=[K32_LO, K32_HI],
        seeds=[MAIN_SEEDS[0], MAIN_SEEDS[-1]],
        runtime_s=round(time.time() - t0, 1)))
    with open(path, "w") as f:
        json.dump(blob, f, indent=1)
    print(f"[wrote] {path} in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
