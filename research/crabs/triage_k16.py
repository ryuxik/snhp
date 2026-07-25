"""TRIAGE (g) -- K16, "whoever holds the engine takes ~90% of the value".

    python research/crabs/triage_k16.py

Artefact #6 (DESIGN-PRINCIPLES A) says the 2x2 differed in far more than the
declared knob. `principles.matrix_arm_descriptor` names them: the landlord got a
brute-force enumeration (`landlord_opener`) over a rent grid the tenant was
forbidden, executed BEFORE the negotiation and resetting the status quo; the
tenant got `negotiate_bundle` reply-only, with two rounds against the landlord's
three; and the landlord's search reads the tenant's private Dirichlet weights and
job flexibility through `welfare_premium`.

This file rebuilds the cell with ONE knob and attributes the 8.5x to each
confound separately. `crabs.armk.negotiate_matrix` is monkey-patched rather than
edited, so nothing in the shipped code moves.

    shipped        as reported: landlord opener on the extended grid, 2 vs 3
                   rounds, private-weight read
    rounds         rounds equalised at N_ROUNDS in every cell
    noreach        landlord opener confined to the grid the tenant can also use
    cashonly       landlord opener may not read the tenant's private weights
    mirror         ALL of the above + the tenant gets the same weapon: a
                   brute-force opener over the same 64-point grid, constrained
                   to leave the other side no worse off. One knob: whose
                   objective the search maximises.

Also run: `break_damp` (INVENTED, "a 2-year lease halves the chance of a job move
happening at all") and `move_med` at A8's derived 1.48.
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

from crabs import armk
from crabs import run as R
from crabs.demographics import ISSUES
from crabs.engine_bridge import (N_ROUNDS, N_TENANT_RENT, RENT_FACTORS, Bundle,
                                 THEIR_BATNA_ESTIMATE, build_issues, bundle_npv,
                                 issue_dollars, tenant_batna_normalised,
                                 welfare_premium)
from crabs.policies import StationDP
from crabs.world import Params, new_recorder, regime_params, simulate_station
from crabs.world import ASK_RANKED

UNITS = 50
CFG: dict = dict(mode="shipped")
_CACHE: dict = {}

SHARED_GRID = [Bundle(ri, ci, fee, term)
               for ri in range(N_TENANT_RENT)
               for ci in (0, 1, 2, 3)
               for fee in (False, True)
               for term in (False, True)]


def _landlord_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul, cfg):
    """armk.landlord_opener, with the two confounds switchable."""
    grid = SHARED_GRID if cfg.get("noreach") else armk.LANDLORD_OPENERS
    best, best_v = Bundle(), bundle_npv(dp, p, j, r, q, Bundle(), tmul, vmul)
    for b in grid:
        d = issue_dollars(p, ten, q, M, g_obs, b)
        util = sum(d.values())
        if not cfg.get("cashonly"):
            util += welfare_premium(ten, d)     # <- reads ten.w, a private draw
        if util < -1e-9:
            continue
        v = bundle_npv(dp, p, j, r, q, b, tmul, vmul)
        if v > best_v:
            best, best_v = b, v
    return best


def _tenant_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul):
    """The MIRROR of `landlord_opener`: the same brute-force enumeration of the
    same grid, maximising the TENANT's own utility among packages that leave the
    landlord no worse off in NPV than its plain offer."""
    base_v = bundle_npv(dp, p, j, r, q, Bundle(), tmul, vmul)
    best, best_u = Bundle(), 0.0
    for b in SHARED_GRID:
        if bundle_npv(dp, p, j, r, q, b, tmul, vmul) < base_v - 1e-9:
            continue
        d = issue_dollars(p, ten, q, M, g_obs, b)
        u = sum(d.values()) + welfare_premium(ten, d)   # the tenant's OWN draw
        if u > best_u:
            best, best_u = b, u
    return best


def negotiate_matrix_triage(dp, p, ten, crab, q, r, j, M, g_obs, c_tot, seed,
                            tenant_engine, landlord_engine, tmul=None, vmul=1.0):
    from gametheory.negotiation.bundle import negotiate_bundle
    cfg = CFG

    t_issues, mu = build_issues(p, ten, q, M, g_obs)
    t_batna = tenant_batna_normalised(p, ten, q, r, j, M, c_tot)
    t_prio = {k: float(w) for k, w in zip(ISSUES, ten.w)}
    l_issues, l_prio, l_batna = armk.landlord_issues(dp, p, j, r, q, tmul, vmul)

    on_table = Bundle()
    if landlord_engine:
        on_table = _landlord_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul,
                                    cfg)
        if on_table.ri >= N_TENANT_RENT:
            q = q * RENT_FACTORS[on_table.ri]
            on_table = Bundle(0, on_table.ci, on_table.fee, on_table.term)
            t_issues, mu = build_issues(p, ten, q, M, g_obs)
            t_batna = tenant_batna_normalised(p, ten, q, r, j, M, c_tot)
            l_issues, l_prio, l_batna = armk.landlord_issues(dp, p, j, r, q,
                                                             tmul, vmul)
    tenant_offers, station_offers = [], [armk._offer_dict(on_table)]
    anchor, eng_util = None, None
    rounds = (N_ROUNDS if cfg.get("equal_rounds")
              else min(N_ROUNDS, armk.HEUR_ROUNDS if not tenant_engine
                       else N_ROUNDS))

    for rnd in range(rounds):
        if tenant_engine and rnd == 0 and cfg.get("mirror"):
            ask = _tenant_opener(dp, p, j, r, q, ten, M, g_obs, tmul, vmul)
        elif tenant_engine:
            res = negotiate_bundle(
                issues=t_issues, their_offers=station_offers,
                my_priorities=t_prio, my_batna=t_batna,
                their_batna_estimate=THEIR_BATNA_ESTIMATE,
                seed=int(seed) + rnd, rounds_left=rounds - rnd)
            eng_util = res.get("my_utility")
            if res["action"] in ("accept", "walk", "use_negotiate_turn"):
                break
            ask = armk._bundle_from_offer(res.get("recommended_offer") or {})
        else:
            ask = armk.heuristic_tenant_ask(p, ten, q, r, M, g_obs, rnd)
            if anchor is None:
                anchor = ask
        tenant_offers.append(armk._offer_dict(ask))

        base_v = bundle_npv(dp, p, j, r, q, on_table, tmul, vmul)
        if bundle_npv(dp, p, j, r, q, ask, tmul, vmul) >= base_v:
            return ask, rnd + 1, True, eng_util, q
        if landlord_engine:
            res = negotiate_bundle(
                issues=l_issues, their_offers=tenant_offers,
                my_priorities=l_prio, my_batna=l_batna,
                their_batna_estimate=0.45, seed=int(seed) + 977 + rnd,
                rounds_left=rounds - rnd)
            if res["action"] in ("walk", "use_negotiate_turn"):
                reply = None
            else:
                cand = armk._bundle_from_offer(res.get("recommended_offer") or {})
                reply = cand if bundle_npv(dp, p, j, r, q, cand, tmul,
                                           vmul) >= base_v else None
        else:
            reply = armk.heuristic_landlord_reply(dp, p, j, r, q, ten, M, g_obs,
                                                  ask, tmul, vmul)
            if reply is not None and bundle_npv(dp, p, j, r, q, reply, tmul,
                                                vmul) < base_v:
                reply = None
        if reply is None:
            break
        on_table = reply
        station_offers.append(armk._offer_dict(on_table))
        if tenant_engine:
            continue
        if armk.heuristic_tenant_accepts(p, ten, q, M, g_obs, on_table,
                                         anchor or ask):
            return on_table, rnd + 1, True, eng_util, q
    return (None if on_table.is_null() else on_table), rounds, True, eng_util, q


MODES = {
    "shipped":  dict(),
    "rounds":   dict(equal_rounds=True),
    "noreach":  dict(equal_rounds=True, noreach=True),
    "cashonly": dict(equal_rounds=True, cashonly=True),
    "mirror":   dict(equal_rounds=True, noreach=True, cashonly=True,
                     mirror=True),
}


def _init(prior):
    _CACHE["prior"] = prior
    armk.negotiate_matrix = negotiate_matrix_triage


def run_cell(spec):
    CFG.clear()
    CFG.update(MODES[spec["mode"]])
    base = Params(**spec["params"])
    nodes, w = _CACHE["prior"]
    regime = spec["regime"]
    key = (regime, base.units, base.break_damp, base.move_med)
    if key not in _CACHE:
        _CACHE[key] = StationDP(regime_params(base, regime), nodes, w)
    stm = _CACHE[key]
    bkey = ("burn",) + key[1:]
    if bkey not in _CACHE:
        _CACHE[bkey] = StationDP(regime_params(base, "burn"), nodes, w)
    stb = _CACHE[bkey]
    agg = new_recorder()
    per = {k: [] for k in ("joint_cash_phy", "tenant_cash_phy", "landlord_phy",
                           "turnover", "success", "deadweight_phy")}
    for seed in R.MAIN_SEEDS:
        rec = simulate_station(regime_params(base, "burn"),
                               regime_params(base, regime), seed, regime, stb,
                               stm, 1.0, ASK_RANKED)
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        d = R.derive(rec)
        for k in per:
            per[k].append(d["success_rate"] if k == "success" else d[k])
    out = {k: v for k, v in spec.items() if k != "params"}
    out["derived"] = R.derive(agg)
    out["per_station"] = per
    return out


def specs():
    out = []
    for mode in MODES:
        for bd, mm in (((0.5, 3.60),) if mode != "mirror"
                       else ((0.5, 3.60), (1.0, 3.60), (0.5, 1.48))):
            for regime in ("loss", "gain"):
                for te, le, nm in ((False, False, "N/N"), (True, False, "T/N"),
                                   (False, True, "N/L"), (True, True, "T/L")):
                    b = Params(**{**R.EXPLORATORY, "units": UNITS,
                                  "negotiator": "matrix", "tenant_engine": te,
                                  "landlord_engine": le, "break_damp": bd,
                                  "move_med": mm})
                    out.append(dict(mode=mode, cell=nm, regime=regime,
                                    break_damp=bd, move_med=mm,
                                    params=dict(b.__dict__)))
    # the shipped cell also gets the break_damp / move_med variants, so the two
    # are attributable separately from the mirror
    for bd, mm in ((1.0, 3.60), (0.5, 1.48)):
        for regime in ("loss", "gain"):
            for te, le, nm in ((False, False, "N/N"), (True, False, "T/N"),
                               (False, True, "N/L"), (True, True, "T/L")):
                b = Params(**{**R.EXPLORATORY, "units": UNITS,
                              "negotiator": "matrix", "tenant_engine": te,
                              "landlord_engine": le, "break_damp": bd,
                              "move_med": mm})
                out.append(dict(mode="shipped", cell=nm, regime=regime,
                                break_damp=bd, move_med=mm,
                                params=dict(b.__dict__)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    sp = specs()
    print(f"[run] k16: {len(sp)} cells", flush=True)
    cells = []
    for mm in sorted({s["move_med"] for s in sp}):
        prior = R.pilot_prior(Params(**{**R.EXPLORATORY, "move_med": mm}))
        sub = [s for s in sp if s["move_med"] == mm]
        with Pool(a.procs, initializer=_init, initargs=(prior,)) as pool:
            cells.extend(pool.map(run_cell, sub, chunksize=1))

    def get(mode, regime, nm, bd, mm):
        for c in cells:
            if (c["mode"] == mode and c["regime"] == regime and c["cell"] == nm
                    and c["break_damp"] == bd and c["move_med"] == mm):
                return c
        return None

    rows = []
    variants = [(m, 0.5, 3.60) for m in MODES]
    variants += [("shipped", 1.0, 3.60), ("shipped", 0.5, 1.48),
                 ("mirror", 1.0, 3.60), ("mirror", 0.5, 1.48)]
    for mode, bd, mm in variants:
        for regime in ("loss", "gain"):
            nn, tn, nl, tl = (get(mode, regime, x, bd, mm)
                              for x in ("N/N", "T/N", "N/L", "T/L"))
            if nn is None or tn is None or nl is None or tl is None:
                continue
            lg = nl["derived"]["landlord_phy"] - nn["derived"]["landlord_phy"]
            tg = (tn["derived"]["tenant_cash_phy"]
                  - nn["derived"]["tenant_cash_phy"])
            se_l = float(np.std(np.array(nl["per_station"]["landlord_phy"])
                                - np.array(nn["per_station"]["landlord_phy"]),
                                ddof=1) / np.sqrt(60))
            se_t = float(np.std(np.array(tn["per_station"]["tenant_cash_phy"])
                                - np.array(nn["per_station"]["tenant_cash_phy"]),
                                ddof=1) / np.sqrt(60))
            rows.append(dict(
                mode=mode, break_damp=bd, move_med=mm, regime=regime,
                landlord_gain=lg, tenant_gain=tg, se_landlord=se_l,
                se_tenant=se_t,
                ratio=(lg / tg if abs(tg) > 1e-9 else float("nan")),
                joint_TL=(tl["derived"]["joint_cash_phy"]
                          - nn["derived"]["joint_cash_phy"]),
                joint_NL=(nl["derived"]["joint_cash_phy"]
                          - nn["derived"]["joint_cash_phy"]),
                success_NL=nl["derived"]["success_rate"],
                success_TN=tn["derived"]["success_rate"]))

    out = os.path.join(_HERE, "results_triage_k16.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(units=UNITS, modes=list(MODES),
                                 runtime_s=round(time.time() - t0, 1)),
                       rows=rows, cells=cells), f)

    hdr = (f"{'mode':10}{'brk':>5}{'move':>6}{'reg':>6}{'landlord N/L':>14}"
           f"{'se':>6}{'tenant T/N':>12}{'se':>6}{'ratio':>8}"
           f"{'joint T/L':>11}{'succ N/L':>10}{'succ T/N':>10}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['mode']:10}{r['break_damp']:>5.1f}{r['move_med']:>6.2f}"
              f"{r['regime']:>6}{r['landlord_gain']:>14.0f}{r['se_landlord']:>6.0f}"
              f"{r['tenant_gain']:>12.0f}{r['se_tenant']:>6.0f}"
              f"{r['ratio']:>8.2f}{r['joint_TL']:>11.0f}"
              f"{r['success_NL']:>10.3f}{r['success_TN']:>10.3f}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
