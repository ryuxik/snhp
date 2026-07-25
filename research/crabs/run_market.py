"""AMENDMENT 5 (K19/K20/K21) and GATE 3 / AMENDMENT 3 §A3.3 (V8/V9/V10, K15).

    python research/crabs/run_market.py

Channels are reported separately and never pooled. Walk-away costs and zone
widths appear in every cell. Nothing imposes the regime: `drift = 0` throughout,
so any new-let-negative / renewal-positive pattern is emergent.
"""
from __future__ import annotations

import json, math, os, sys, time
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from crabs.market import MarketParams, simulate_market
from crabs.world import Params, regime_params

SEEDS = list(range(1000, 1030))
ANNUAL_RENT = 24000.0


def _d(a, b):
    return a / b if b else float("nan")


def derive_market(r):
    d = {
        "vacancy": _d(r["vacant_years"], r["habitat_years"]),
        "retention": 1.0 - _d(r["n_renewal_left"], r["n_renewal"]),
        # channels, never pooled
        "renew_growth": _d(r["renew_growth_sum"], r["renew_growth_n"]),
        "newlet_growth": _d(r["newlet_growth_sum"], r["newlet_growth_n"]),
        "renew_rent": _d(r["renew_rent_sum"], r["n_renewal_signed"]),
        "newlet_rent": _d(r["newlet_rent_sum"], r["n_newlet_signed"]),
        "newlet_vs_ask": _d(r["newlet_vs_ask_sum"], r["n_newlet_signed"]),
        "mean_ask": _d(r["ask_sum"], r["ask_n"]),
        # walk-aways and zones, per channel
        "wa_tenant_renew": _d(r["wa_tenant_renew"], r["wa_n_renew"]),
        "wa_land_renew": _d(r["wa_land_renew"], r["wa_n_renew"]),
        "zone_renew": _d(r["zone_renew_sum"], r["wa_n_renew"]),
        "wa_tenant_newlet": _d(r["wa_tenant_newlet"], r["wa_n_newlet"]),
        "wa_land_newlet": _d(r["wa_land_newlet"], r["wa_n_newlet"]),
        "zone_newlet": _d(r["zone_newlet_sum"], r["wa_n_newlet"]),
        "wa_ratio_renew": _d(_d(r["wa_tenant_renew"], r["wa_n_renew"]),
                             _d(r["wa_land_renew"], r["wa_n_renew"])),
        # K21, measured without the definitional benchmark
        "rent_gap": _d(r["rent_gap_sum"], r["move_gain_n"]),
        "move_gain": _d(r["move_gain_sum"], r["move_gain_n"]),
        "move_gain_share": _d(r["move_gain_pos"], r["move_gain_n"]),
        "turn_events_per_hab": _d(r["turn_events"], r["habitat_years"]),
        "secured_offer": _d(r["secured_offer"], r["secured_n"]),
        "unsecured_offer": _d(r["unsecured_offer"], r["unsecured_n"]),
        "secured_surp": _d(r["secured_surp"], r["secured_n"]),
        "unsecured_surp": _d(r["unsecured_surp"], r["unsecured_n"]),
        "deadweight_phy": _d(r["turn_cost_paid"] + r["vacancy_lost"]
                             + r["move_cost_paid"], r["habitat_years"]),
    }
    for b in range(4):
        d[f"elapsed{b}_offer"] = _d(r[f"renew_elapsed{b}_offer"],
                                    r[f"renew_elapsed{b}_n"])
        d[f"elapsed{b}_surp"] = _d(r[f"renew_elapsed{b}_surp"],
                                   r[f"renew_elapsed{b}_n"])
    for q in range(4):
        d[f"move_gain_q{q}"] = _d(r[f"move_gain_q{q}"], r[f"move_gain_q{q}_n"])
        d[f"move_share_q{q}"] = _d(r[f"move_gain_q{q}_pos"],
                                   r[f"move_gain_q{q}_n"])
    return d


def run_cell(spec):
    p = regime_params(Params(), "burn")
    mp = MarketParams(**spec["mp"])
    agg, per, series = None, [], []
    for seed in SEEDS:
        r = simulate_market(p, mp, seed, drift=spec["drift"],
                            record_series=spec.get("series", False))
        if spec.get("series"):
            series.append(r["_series"])
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = clean if agg is None else {k: agg[k] + v for k, v in clean.items()}
        per.append(derive_market(clean))
    out = {k: v for k, v in spec.items() if k != "mp"}
    out["mp"] = spec["mp"]
    out["derived"] = derive_market(agg)
    out["per_seed"] = {k: [x[k] for x in per] for k in per[0]}
    if series:
        n = len(series[0])
        out["series"] = [
            {k: float(np.mean([s[i][k] for s in series]))
             for k in series[0][0]} for i in range(n)]
    return out


def specs():
    base = dict(n_stations=40, units=25)
    return [
        dict(cell="baseline", drift=0.0, mp=dict(base), series=True),
        dict(cell="supply_shock", drift=0.0,
             mp=dict(base, completions_frac=0.30), series=True),
        dict(cell="precedent_0.002", drift=0.0, mp=dict(base, precedent=0.002)),
        dict(cell="precedent_0.01", drift=0.0, mp=dict(base, precedent=0.01)),
        dict(cell="split_landlord_0.75", drift=0.0,
             mp=dict(base, lambda_split=0.75)),
        dict(cell="split_tenant_0.25", drift=0.0,
             mp=dict(base, lambda_split=0.25)),
    ] + [dict(cell=f"eta_{e}", drift=0.0, mp=dict(base, eta_demand=e),
              series=(e == 1.0))
         for e in (0.5, 1.0, 1.5, 2.0)] + [
        # AMENDMENT 6a, folded into the SAME Gate-3 attempt as elastic demand
        dict(cell="a6a_base", drift=0.0, mp=dict(base, deadline_shape=True),
             series=True),
        dict(cell="a6a_shock", drift=0.0,
             mp=dict(base, deadline_shape=True, completions_frac=0.30)),
        dict(cell="a6a_noshape", drift=0.0, mp=dict(base, deadline_shape=False)),
        dict(cell="a6a_linear", drift=0.0,
             mp=dict(base, deadline_shape=True, tenant_clock_linear=True)),
        dict(cell="a6a_secured", drift=0.0,
             mp=dict(base, deadline_shape=True, secured_share=0.5)),
    ]


def main():
    t0 = time.time()
    sp = specs()
    with Pool(6) as pool:
        cells = pool.map(run_cell, sp, chunksize=1)
    meta = dict(version="crabs-1.0", phase="market", seeds=[SEEDS[0], SEEDS[-1]],
                n_seeds=len(SEEDS), runtime_s=round(time.time() - t0, 1))
    out = os.path.join(_HERE, "results_market.json")
    with open(out, "w") as f:
        json.dump(dict(meta=meta, cells=cells), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
