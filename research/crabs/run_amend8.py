"""AMENDMENT 8 — derive the switching cost from search, and see what falls out.

    python research/crabs/run_amend8.py

Reports, in PREREG A8.4's order:
  1. the derived distribution vs the drawn lognormal (median 3.6 mo / $7,200)
  2. whether it varies with market tightness, and by how much
  3. the A7 free-cap push re-run on derived costs
  4. K20 and K26 re-checked
  5. GATE 3 V8/V9/V10, reported not chased

Geometry, seeds and every non-A8 parameter are run_market.py's, unchanged, so
the only thing that moves is whether switching cost is drawn or derived.
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

from crabs import searchcost as SC
from crabs.market import MarketParams, simulate_market
from crabs.run_market import SEEDS, derive_market
from crabs.world import Params, regime_params

BASE_MP = dict(n_stations=40, units=25)
CALIBRATED_MED = 3.6            # the value A8 is testing, never used as a target


# --------------------------------------------------------------- 1. the draw
def spells(mp_kw: dict, seeds=None) -> list:
    """Every search spell, matched and abandoned alike (PRINCIPLE D)."""
    p = regime_params(Params(), "burn")
    out = []
    for seed in (seeds or SEEDS):
        r = simulate_market(p, MarketParams(**{**BASE_MP, **mp_kw,
                                               "derive_switching": True}), seed)
        out.extend(r["_derived"])
    return out


def _cost(sp, **over):
    return SC.derived_cost(sp["attempts"], sp["months"], sp["broker"], **over)


def distribution_cell(spec: dict) -> dict:
    sp = spells(spec["mp"])
    all_c = [d["cost"] for d in sp]
    matched = [d["cost"] for d in sp if d["matched"]]
    out = dict(cell=spec["cell"], mp=spec["mp"])
    out["all"] = SC.summary(all_c, "every spell (UNCONDITIONAL)")
    out["matched_only"] = SC.summary(matched, "matched only (CONDITIONAL)")
    out["match_rate"] = float(np.mean([d["matched"] for d in sp]))
    out["k27_fires"] = bool(SC.k27(float(np.median(all_c))))
    # decomposition of the MEDIAN spell, so the reader can see how much of the
    # answer is search and how much is the physical-move constant
    med_at = float(np.median([d["attempts"] for d in sp]))
    med_mo = float(np.median([d["months"] for d in sp]))
    out["median_spell"] = dict(attempts=med_at, months=med_mo)
    out["decomposition"] = dict(
        spell_overhead=SC.SPELL_COST,
        viewings=med_at * SC.VIEW_COST,
        time_in_search=med_mo * SC.TIME_COST,
        physical_move=SC.MOVE_PHYSICAL,
        broker_expected=SC.BROKER_SHARE * SC.BROKER_FEE,
        overrun_share=float(np.mean([d["months"] > 3.0 for d in sp])),
    )
    out["search_only_median"] = float(np.median(
        [_cost(d, move_physical=0.0, broker_fee=0.0) for d in sp]))
    # 2. tightness
    tg = [(d["tightness"], d["cost"]) for d in sp if d["tightness"] is not None]
    if tg:
        t = np.array([x[0] for x in tg])
        c = np.array([x[1] for x in tg])
        qs = np.quantile(t, [0.25, 0.5, 0.75])
        buckets = []
        for lo, hi, lbl in ((-1e9, qs[0], "slackest quartile"),
                            (qs[0], qs[1], "q2"), (qs[1], qs[2], "q3"),
                            (qs[2], 1e9, "tightest quartile")):
            m = (t > lo) & (t <= hi)
            if m.sum():
                buckets.append(dict(label=lbl, n=int(m.sum()),
                                    tightness=float(t[m].mean()),
                                    median=float(np.median(c[m])),
                                    mean=float(c[m].mean())))
        out["by_tightness"] = buckets
        out["tightness_corr"] = float(np.corrcoef(t, c)[0, 1])
    # K26: a crab that already SECURED an alternative has paid the search cost
    sec = [d["cost"] for d in sp if d["secured"]]
    uns = [d["cost"] for d in sp if not d["secured"]]
    if sec and uns:
        out["secured_median"] = float(np.median(sec))
        out["unsecured_median"] = float(np.median(uns))
        out["secured_n"] = len(sec)
    return out


def sweep_cell(spec: dict) -> dict:
    """PRINCIPLE C: the two constants A8 invents are swept, so that the derived
    median is reported as a range and not as a point that happens to land."""
    sp = spells(BASE_MP)
    out = dict(cell="sweep", rows=[])
    for name, vals in SC.SWEEPS.items():
        for v in vals:
            kw = {"move_physical": SC.MOVE_PHYSICAL,
                  "time_cost": SC.TIME_COST, "broker_fee": SC.BROKER_FEE}
            if name == "MOVE_PHYSICAL":
                kw["move_physical"] = v
                cs = [_cost(d, **kw) for d in sp]
            elif name == "TIME_COST":
                kw["time_cost"] = v
                cs = [_cost(d, **kw) for d in sp]
            else:                       # BROKER_SHARE: re-weight, not re-draw
                cs = [SC.derived_cost(d["attempts"], d["months"],
                                      (i / len(sp)) < v, **{
                                          k: kw[k] for k in
                                          ("move_physical", "time_cost",
                                           "broker_fee")})
                      for i, d in enumerate(sp)]
            med = float(np.median(cs))
            out["rows"].append(dict(param=name, value=v, median=med,
                                    dollars=med * 2000.0,
                                    k27_fires=bool(SC.k27(med))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=6)
    a = ap.parse_args()
    t0 = time.time()

    # Tightness is varied through the two knobs that make a market tight or
    # slack WITHOUT touching anything on the cost side: how many searchers
    # arrive, and how many leavers exit the metro instead of re-entering the
    # pool. ONE KNOB each, relative to baseline.
    specs = [
        dict(cell="baseline", mp=dict()),
        dict(cell="tight:inflow_0.150", mp=dict(searcher_inflow=0.150)),
        dict(cell="tight:inflow_0.110", mp=dict(searcher_inflow=0.110)),
        dict(cell="slack:inflow_0.050", mp=dict(searcher_inflow=0.050)),
        dict(cell="slack:inflow_0.030", mp=dict(searcher_inflow=0.030)),
        dict(cell="slack:supply_shock", mp=dict(completions_frac=0.30)),
        dict(cell="tight:exit_0.05", mp=dict(exit_share=0.05)),
        dict(cell="slack:exit_0.30", mp=dict(exit_share=0.30)),
    ]
    with Pool(a.procs) as pool:
        cells = pool.map(distribution_cell, specs, chunksize=1)
    sw = sweep_cell({})

    out = os.path.join(_HERE, "results_amend8.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 n_seeds=len(SEEDS),
                                 constants=dict(
                                     VIEW_COST=SC.VIEW_COST,
                                     SPELL_COST=SC.SPELL_COST,
                                     TIME_COST=SC.TIME_COST,
                                     MOVE_PHYSICAL=SC.MOVE_PHYSICAL,
                                     BROKER_FEE=SC.BROKER_FEE,
                                     BROKER_SHARE=SC.BROKER_SHARE,
                                     OVERRUN_COST=SC.OVERRUN_COST),
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells, sweep=sw), f, indent=1)

    base = cells[0]
    print("\n=== A8.4(1) the derived distribution vs the drawn lognormal ===\n")
    print(f"{'':28} {'median':>9} {'$':>8} {'mean':>8} {'p10':>7} {'p90':>7} "
          f"{'fit sd':>7}")
    d = base["all"]
    print(f"{'DERIVED (every spell)':28} {d['median']:>9.2f} "
          f"{d['dollars_median']:>8.0f} {d['mean']:>8.2f} {d['p10']:>7.2f} "
          f"{d['p90']:>7.2f} {d['fit_sigma']:>7.2f}")
    m = base["matched_only"]
    print(f"{'  (matched only, CONDIT.)':28} {m['median']:>9.2f} "
          f"{m['dollars_median']:>8.0f} {m['mean']:>8.2f} {m['p10']:>7.2f} "
          f"{m['p90']:>7.2f} {m['fit_sigma']:>7.2f}")
    print(f"{'DRAWN (move_med, shipped)':28} {CALIBRATED_MED:>9.2f} "
          f"{CALIBRATED_MED*2000:>8.0f} {'--':>8} {'--':>7} {'--':>7} "
          f"{Params().move_sigma:>7.2f}")
    print(f"\nmatch rate {base['match_rate']:.3f};  median spell: "
          f"{base['median_spell']['attempts']:.0f} attempts over "
          f"{base['median_spell']['months']:.0f} months;  "
          f"search-only median {base['search_only_median']:.2f} mo")
    print("decomposition of the median spell (months of rent):")
    for k, v in base["decomposition"].items():
        print(f"    {k:22} {v:.3f}")
    print(f"\nK27 (fires if median outside {SC.K27_LO}-{SC.K27_HI} mo): "
          f"{'FIRES' if base['k27_fires'] else 'does not fire'}")

    print("\n=== A8.4(2) does it vary with tightness? ===\n")
    print(f"{'cell':24} {'match':>6} {'median':>8} {'$':>8} {'mean':>8} "
          f"{'corr(tight,cost)':>17}")
    for c in cells:
        print(f"{c['cell']:24} {c['match_rate']:>6.3f} "
              f"{c['all']['median']:>8.2f} {c['all']['dollars_median']:>8.0f} "
              f"{c['all']['mean']:>8.2f} {c.get('tightness_corr', float('nan')):>17.3f}")
    print("\nwithin the baseline, by tightness at entry:")
    for b in base.get("by_tightness", []):
        print(f"    {b['label']:20} tightness {b['tightness']:>6.2f}  "
              f"n={b['n']:>5}  median {b['median']:.2f} mo  "
              f"mean {b['mean']:.2f}")

    print("\n=== A8.4 sensitivity of the derived median to A8's own constants ===\n")
    print(f"{'parameter':16} {'value':>7} {'median mo':>10} {'$':>8}  K27")
    for r in sw["rows"]:
        print(f"{r['param']:16} {r['value']:>7.3f} {r['median']:>10.2f} "
              f"{r['dollars']:>8.0f}  {'FIRES' if r['k27_fires'] else 'ok'}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
