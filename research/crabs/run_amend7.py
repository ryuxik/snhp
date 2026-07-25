"""AMENDMENT 7 -- derive the renewal ceiling instead of imposing it.

`world.py` shipped `renewal_cap = 0.12`, justified in SPEC.md §5 as "2022
renewals averaged +10.7% while asking rents rose faster". That is an observed
OUTCOME installed as a hard CONSTRAINT, and it double-counts: the station's DP
already prices the risk that the crab leaves, so restraint at renewal was
supposed to EMERGE.

This runner removes the ceiling and reports what number falls out.

    python research/crabs/run_amend7.py                 # registered spec
    python research/crabs/run_amend7.py --spec exploratory

Sweep: cap in {0.06, 0.12 (as shipped), 0.25, 0.50, 2.0 (free)}. The value at
which the cap stops binding IS the derived ceiling. Everything else -- seeds,
arms, geometry -- is Phase 1 arm A unchanged (SPEC §9), so the only thing that
moves between cells is the ceiling.
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

from crabs.policies import QA, RS, StationDP
from crabs.run import EXPLORATORY, MAIN_SEEDS, N_NODES, derive, pilot_prior
from crabs.world import (ASK_PRICE, Params, regime_params, simulate_station)

CAPS = (0.06, 0.12, 0.25, 0.50, 2.00)
SHIPPED_CAP = 0.12
FREE_CAP = 2.00
PCTS = (5, 10, 25, 50, 75, 90, 95, 99, 100)

_CACHE: dict = {}


def _init(payload):
    _CACHE.update(payload)


def run_cell(spec: dict) -> dict:
    base = Params(**spec["params"])
    regime = spec["regime"]
    pk = spec.get("prior_key")
    nodes, w = _CACHE[("prior", round(base.renewal_cap, 6)) if pk is None
                      else ("prior", round(pk[0], 6), pk[1])]
    p_burn = regime_params(base, "burn")
    p_meas = regime_params(base, regime)
    # The burn-in runs arm A's policy in EVERY cell (SPEC §3) -- and under the
    # SAME ceiling as the measurement window, because a station does not change
    # its policy regime at the burn-in boundary.
    st_burn = StationDP(p_burn, nodes, w)
    st_meas = StationDP(p_meas, nodes, w)

    from crabs.world import new_recorder
    agg = new_recorder()
    pushes, r_pre, at_cap, at_grid = [], [], 0.0, 0.0
    per_seed_push, per_seed_ret = [], []
    for seed in spec["seeds"]:
        rec = simulate_station(p_burn, p_meas, seed, regime, st_burn, st_meas,
                               0.39, ASK_PRICE, collect_pushes=True)
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        sp = []
        for (r, j, q) in rec["_pushes"]:
            sp.append(q / r - 1.0)
            r_pre.append(r)
            if q >= r * (1.0 + base.renewal_cap) - 0.01 - 1e-9:
                at_cap += 1.0
            if q >= QA[-1] - 1e-9:
                at_grid += 1.0
        pushes.extend(sp)
        per_seed_push.append(float(np.mean(sp)) if sp else float("nan"))
        per_seed_ret.append(1.0 - (rec["left"] / rec["renewals"]
                                   if rec["renewals"] else float("nan")))

    a = np.asarray(pushes)
    rp = np.asarray(r_pre)
    d = derive(agg)
    out = dict(cap=base.renewal_cap, regime=regime, spec=spec["spec"],
               face_premium=base.face_premium, tag=spec.get("tag", "sweep"))
    out["n_renewals"] = int(a.size)
    out["push_mean"] = float(a.mean())
    out["push_sd"] = float(a.std())
    out["push_pct"] = {str(p): float(np.percentile(a, p)) for p in PCTS}
    out["push_min"] = float(a.min())
    out["share_at_cap"] = at_cap / max(1.0, a.size)
    out["share_at_action_grid_top"] = at_grid / max(1.0, a.size)
    out["share_push_le_0"] = float((a <= 1e-9).mean())
    out["share_push_ge_10pct"] = float((a >= 0.10).mean())
    out["share_push_gt_shipped_cap"] = float((a > SHIPPED_CAP + 1e-9).mean())
    # histogram, so the shape is on the record and not only its quantiles
    edges = [-0.20, -0.10, -0.05, 0.0, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15,
             0.20, 0.25, 0.30, 0.40, 1.00]
    h, _ = np.histogram(a, bins=edges)
    out["hist_edges"] = edges
    out["hist"] = [int(x) for x in h]
    # the PRE-renewal rent of record, which is the state the push is applied to
    out["r_pre_mean"] = float(rp.mean())
    out["r_pre_p50"] = float(np.percentile(rp, 50))
    # per-seed spread, so the mean carries an interval rather than a point
    ps = np.asarray(per_seed_push)
    out["push_mean_se"] = float(ps.std(ddof=1) / np.sqrt(ps.size))
    pr = np.asarray(per_seed_ret)
    out["retention_se"] = float(pr.std(ddof=1) / np.sqrt(pr.size))
    for k in ("retention", "rent_ratio", "zero_increase_share", "surplus_pcy",
              "station_cash_phy", "station_obj_phy", "turnover",
              "success_rate", "counter_rate", "market_rent", "deadweight_phy",
              "joint_cash_phy", "landlord_phy", "tenant_cash_phy",
              # PREREG GATE 1 quantities, so it is visible whether the ceiling
              # was also holding V1 and V3 down
              "success_rate_price", "success_lt2", "success_ge2",
              "tenure_ratio", "ledger_gap",
              "grant_share_one_time", "grant_share_fees", "grant_share_term",
              "grant_share_rent", "retention_asker", "retention_nonasker"):
        out[k] = d[k]
    # new-let / renewal spread: a NEW let signs at market (ratio 1.0), a renewing
    # crab is offered `q`. The spread is what the sitting crab is NOT charged.
    out["mean_offer_ratio"] = d["mean_offer_push"] * 0.0 + float(
        agg["offer_ratio_sum"] / agg["push_n"])
    out["newlet_minus_renewal_pct_of_market"] = 1.0 - out["mean_offer_ratio"]
    return out


def policy_scan(base: Params, nodes, w, regime: str) -> dict:
    """What the DP would choose at every point of the state grid, with no
    ceiling. Independent of which states the simulation actually visits."""
    p = regime_params(base, regime)
    st = StationDP(p, nodes, w)
    rows = {}
    for j in (1, 2, 4, 8):
        q = np.array([st.offer(float(r), j) for r in RS])
        rows[str(j)] = dict(
            r=[float(x) for x in RS],
            q=[float(x) for x in q],
            push=[float(x) for x in (q / RS - 1.0)],
        )
    # the ceiling the DP imposes on ITSELF: the highest offer ratio it ever
    # picks anywhere on the grid, and the tightest it holds relative to market
    qall = np.array([[st.offer(float(r), j) for r in RS]
                     for j in range(1, base.j_max + 1)])
    return dict(regime=regime, rows=rows,
                q_max=float(qall.max()), q_min=float(qall.min()),
                q_at_grid_top=bool(qall.max() >= QA[-1] - 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="registered",
                    choices=("registered", "exploratory"))
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    t0 = time.time()
    base0 = Params(**EXPLORATORY) if a.spec == "exploratory" else Params()
    payload, specs = {}, []
    for cap in CAPS:
        b = Params(**{**base0.__dict__, "renewal_cap": cap})
        print(f"[pilot] cap={cap} ...", flush=True)
        payload[("prior", round(cap, 6))] = pilot_prior(b)
        for regime in ("loss", "gain"):
            specs.append(dict(params=dict(b.__dict__), regime=regime,
                              seeds=MAIN_SEEDS, spec=a.spec, tag="sweep"))
    # ---- ABLATION (DESIGN-PRINCIPLES C.2). "Elasticity alone gives X%" is a
    # mechanism claim, so it gets run without the other channel that could be
    # producing it. FACE_RENT_PREMIUM makes a dollar of face rent worth 2x its
    # cash (SPEC §6); if the free-choice push is really an artefact of
    # capitalisation rather than of elasticity, it collapses at premium 0.
    for fp in (0.0, 0.5, 2.0):
        b = Params(**{**base0.__dict__, "renewal_cap": FREE_CAP,
                      "face_premium": fp})
        key = ("prior", round(FREE_CAP, 6), fp)
        print(f"[pilot] free cap, face_premium={fp} ...", flush=True)
        payload[key] = pilot_prior(b)
        payload[("prior", round(FREE_CAP, 6))] = payload.get(
            ("prior", round(FREE_CAP, 6)))
        for regime in ("loss", "gain"):
            specs.append(dict(params=dict(b.__dict__), regime=regime,
                              seeds=MAIN_SEEDS, spec=a.spec, tag="ablate_face",
                              prior_key=[FREE_CAP, fp]))
    print(f"[pilot] done in {time.time()-t0:.1f}s", flush=True)

    with Pool(a.procs, initializer=_init, initargs=(payload,)) as pool:
        cells = pool.map(run_cell, specs, chunksize=1)

    free = Params(**{**base0.__dict__, "renewal_cap": FREE_CAP})
    nodes, w = payload[("prior", round(FREE_CAP, 6))]
    scans = [policy_scan(free, nodes, w, rg) for rg in ("loss", "gain")]

    out = a.out or os.path.join(_HERE, f"results_amend7_{a.spec}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(spec=a.spec, caps=list(CAPS),
                                 seeds=[MAIN_SEEDS[0], MAIN_SEEDS[-1]],
                                 arm="A (share 0.39, price ladder)",
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells, policy_free=scans), f, indent=1)
    print(f"[run] wrote {out} in {time.time()-t0:.1f}s", flush=True)

    # ------------------------------------------------------------ the table
    print("\nAMENDMENT 7 -- renewal push when the ceiling is removed "
          f"({a.spec} spec, arm A, 60 stations)\n")
    hdr = (f"{'cap':>6} {'regime':>6} {'mean':>8} {'p50':>8} {'p90':>8} "
           f"{'max':>8} {'@cap':>7} {'ret':>7} {'r':>7} {'q':>7}")
    print(hdr)
    print("-" * len(hdr))
    for c in cells:
        if c["tag"] != "sweep":
            continue
        print(f"{c['cap']:>6.2f} {c['regime']:>6} "
              f"{c['push_mean']*100:>7.2f}% {c['push_pct']['50']*100:>7.2f}% "
              f"{c['push_pct']['90']*100:>7.2f}% {c['push_pct']['100']*100:>7.2f}% "
              f"{c['share_at_cap']*100:>6.1f}% {c['retention']*100:>6.2f}% "
              f"{c['rent_ratio']:>7.4f} {c['mean_offer_ratio']:>7.4f}")
    print("\nfree-choice policy (cap=2.0), max offer ratio on the state grid:")
    for s in scans:
        print(f"  {s['regime']}: q_max={s['q_max']:.3f} q_min={s['q_min']:.3f} "
              f"action-grid ceiling hit: {s['q_at_grid_top']}")
    print("\nABLATION at the free cap -- how much of the push is elasticity and "
          "how much is face-rent capitalisation?")
    print(f"{'face_prem':>10} {'regime':>6} {'mean push':>10} {'ret':>8} "
          f"{'q':>8}")
    for c in cells:
        if c["cap"] != FREE_CAP:
            continue
        print(f"{c['face_premium']:>10.1f} {c['regime']:>6} "
              f"{c['push_mean']*100:>9.2f}% {c['retention']*100:>7.2f}% "
              f"{c['mean_offer_ratio']:>8.4f}")


if __name__ == "__main__":
    main()
