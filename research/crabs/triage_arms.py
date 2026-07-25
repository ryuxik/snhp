"""TRIAGE (b), (c), (d) -- the exception queue, informativeness, and the split.

    python research/crabs/triage_arms.py --part queue
    python research/crabs/triage_arms.py --part info
    python research/crabs/triage_arms.py --part split

(b) "menu costs + an exception queue made countering pay WORSE, and most
    counterers are unread rather than refused" -- rests on `queue_frac = 0.15`,
    which SPEC-A2 §A2-5 itself calls "a working guess" (INVENTED). Swept.

(c) "asking works only because it is informative, so its value depends on asking
    being rare" -- the mechanism in the code is `weights_counter`, the
    switching-cost distribution the station believes it faces GIVEN a counter.
    Decomposed into two knobs, one at a time:
        tool + prior      vs  tool + NO prior          = the SIGNAL channel
        tool + NO prior   vs  random_at at same share  = the SELECTION channel

(d) the 61/39 split -- arm F's endogenous counter rate, which `courage_med`
    (CIRCULAR: "set so the endogenous counter rate lands near the observed 39%")
    and `belief0` (INVENTED: "0.10 -> 61% never try") produce. Both swept, and
    the question is whether the DIRECTION of (c) survives, not the level.

Geometry, seeds and every unswept parameter are run3.py's / run2.py's, unchanged.
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

from crabs.emergent import EmergentDP
from crabs.run import EXPLORATORY, N_NODES, PILOT_SEEDS, derive, _d
from crabs.run3 import INST, PRIMITIVES, STATIONS
from crabs.world import (ASK_PRICE, ASK_RANKED, Params, new_recorder,
                         regime_params, simulate_station, switching_cost_nodes)

_C: dict = {}
ANNUAL = 24000.0
# AMENDMENT 8: `move_med` is CALIBRATED (SPEC §4/§8, "calibrated to observed
# elasticity") and A8's derived-from-search rebuild puts the median at 1.48
# months, not 3.60. Every claim that rests on it is run at BOTH.
MOVE_MEDS = (3.60, 1.48)


def _base(units=INST, **over):
    return Params(**{**EXPLORATORY, **PRIMITIVES, "units": units, **over})


def _prior_for(base):
    """The station's switching-cost quadrature. The NODES depend on `move_med`,
    so a move_med sweep that reuses one prior would give the station a belief
    about a distribution that is not the one it faces. One per value."""
    key = ("prior", round(base.move_med, 6), round(base.move_sigma, 6))
    if key not in _C:
        nodes, _ = switching_cost_nodes(base, N_NODES)
        _C[key] = (nodes, np.tile(np.ones(N_NODES) / N_NODES, (9, 1)))
    return _C[key]


def _dp(base, regime, wc=None):
    key = (regime, base.units, base.menu_costs, base.queue_frac, base.ask_mode,
           base.engage_margin, base.no_concessions, base.face_premium,
           round(base.move_med, 6), round(base.courage_med, 6),
           round(base.belief0, 6), wc is not None)
    if key not in _C:
        nodes, w = _prior_for(base)
        _C[key] = EmergentDP(regime_params(base, regime), nodes, w,
                             weights_counter=wc)
    return _C[key]


def counter_prior(base, regime, ask_mode):
    """run3.counter_prior, verbatim in behaviour: the switching-cost
    distribution the station believes it faces GIVEN a counter, measured on the
    pilot seeds."""
    key = ("cp", regime, ask_mode, base.units, round(base.engage_margin, 4),
           round(base.move_med, 6))
    if key in _C:
        return _C[key]
    nodes, w = _prior_for(base)
    _, edges = switching_cost_nodes(base, N_NODES)
    jm = base.j_max
    marg = np.ones(N_NODES) / N_NODES
    p = Params(**{**base.__dict__, "ask_mode": ask_mode, "meas_years": 8})
    stb, stm = _dp(p, "burn"), _dp(p, regime)
    counts = np.zeros((jm + 1, N_NODES))
    for seed in PILOT_SEEDS:
        rec = simulate_station(regime_params(p, "burn"),
                               regime_params(p, regime), seed, regime, stb, stm,
                               1.0, ASK_RANKED, collect=True)
        for j, c in rec["_casker"]:
            counts[min(j, jm), int(np.searchsorted(edges, c))] += 1.0
    out = counts + 100.0 * marg[None, :]
    out = out / out.sum(axis=1, keepdims=True)
    _C[key] = out
    return out


def run_cell(spec):
    base = Params(**spec["params"])
    regime = spec["regime"]
    wc = counter_prior(base, regime, base.ask_mode) if spec.get("counter_prior") \
        else None
    stb, stm = _dp(base, "burn"), _dp(base, regime, wc)
    agg = new_recorder()
    per = {k: [] for k in ("surplus_pcy", "surplus_asker", "surplus_nonasker",
                           "success", "counter_rate", "retention")}
    for seed in range(1000, 1000 + STATIONS[base.units]):
        rec = simulate_station(regime_params(base, "burn"),
                               regime_params(base, regime), seed, regime, stb,
                               stm, spec["share"],
                               ASK_PRICE if spec["strategy"] == "price"
                               else ASK_RANKED,
                               learn=bool(spec.get("learn")),
                               broadcast=bool(spec.get("broadcast")))
        for k, v in rec.items():
            if not k.startswith("_"):
                agg[k] += v
        d = derive(rec)
        for k in per:
            per[k].append(d["success_rate"] if k == "success" else d[k])
    out = {k: v for k, v in spec.items() if k != "params"}
    d = derive(agg)
    d["gain_from_countering"] = d["surplus_asker"] - d["surplus_nonasker"]
    d["reviewed_share"] = _d(agg["reviewed"], agg["countered"] + agg["queue_denied"])
    d["unread_share"] = _d(agg["queue_denied"], agg["countered"] + agg["queue_denied"])
    d["mean_belief"] = _d(agg["belief_sum"], agg["belief_n"])
    d["ask_share_end"] = _d(agg["ask_share_sum"], agg["ask_share_n"])
    out["derived"] = d
    out["se"] = {k: float(np.nanstd(v, ddof=1) / np.sqrt(len(v)))
                 for k, v in per.items()}
    # paired SE on the asker-minus-nonasker difference, per station
    diff = np.array(per["surplus_asker"]) - np.array(per["surplus_nonasker"])
    diff = diff[np.isfinite(diff)]
    out["se"]["gain_from_countering"] = float(
        np.std(diff, ddof=1) / np.sqrt(diff.size)) if diff.size > 1 else float("nan")
    return out


# ---------------------------------------------------------------- (b) the queue
def queue_specs():
    out = []
    for regime in ("loss", "gain"):
        for mm in MOVE_MEDS:
            tag = "" if mm == 3.60 else f" [move_med={mm}]"
            out.append(dict(cell=f"baseline:no_menu_costs{tag}", regime=regime,
                            share=0.39, strategy="ranked",
                            queue_frac=float("nan"), move_med=mm,
                            params=dict(_base(move_med=mm).__dict__)))
            qfs = ((0.0, 0.02, 0.05, 0.10, 0.15, 0.25, 0.50, 1.00, 2.00)
                   if mm == 3.60 else (0.05, 0.15, 0.50))
            for qf in qfs:
                out.append(dict(cell=f"armG:queue_frac={qf}{tag}", regime=regime,
                                share=0.39, strategy="ranked", queue_frac=qf,
                                move_med=mm,
                                params=dict(_base(menu_costs=True, move_med=mm,
                                                  queue_frac=qf).__dict__)))
    return out


# -------------------------------------------------------- (c) informativeness
def info_specs():
    out = []
    for regime in ("loss", "gain"):
        for mm in MOVE_MEDS:
            tag = "" if mm == 3.60 else f"|mm={mm}"
            # Phase 1's control: a random 39% counter, no counter-specific belief
            out.append(dict(cell=f"assigned:0.39{tag}", regime=regime,
                            share=0.39, strategy="ranked", move_med=mm,
                            params=dict(_base(move_med=mm).__dict__)))
            for mode in ("tool", "everyone", "selfselect"):
                for cp in (True, False):
                    out.append(dict(cell=f"{mode}:prior={cp}{tag}",
                                    regime=regime, share=0.39,
                                    strategy="ranked", counter_prior=cp,
                                    move_med=mm,
                                    params=dict(_base(ask_mode=mode,
                                                      move_med=mm).__dict__)))
            # selfselect traces the whole share range through ONE knob
            ems = ((0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0) if mm == 3.60
                   else (0.0, 2.0, 8.0, 32.0))
            for em in ems:
                for cp in (True, False):
                    out.append(dict(cell=f"selfselect:em={em}:prior={cp}{tag}",
                                    regime=regime, share=0.39,
                                    strategy="ranked", counter_prior=cp,
                                    move_med=mm,
                                    params=dict(_base(ask_mode="selfselect",
                                                      engage_margin=em,
                                                      move_med=mm).__dict__)))
            # random askers at a matched share: the SELECTION control
            shs = ((0.01, 0.025, 0.05, 0.10, 0.20, 0.39, 0.60, 0.80, 1.00)
                   if mm == 3.60 else (0.025, 0.20, 1.00))
            for sh in shs:
                out.append(dict(cell=f"random_at:{sh}{tag}", regime=regime,
                                share=sh, strategy="ranked", move_med=mm,
                                params=dict(_base(ask_mode="random_at",
                                                  move_med=mm).__dict__)))
    return out


# ------------------------------------------------------------- (d) the split
def split_specs():
    """Arm F: nobody is assigned to ask. The counter rate is an OUTPUT of
    `courage_med` and `belief0`. Phase-1 StationDP institutional (units 50, the
    Phase-1 geometry) so the comparison is to Phase 2's arm F, not to GATE 2."""
    out = []
    for regime in ("loss", "gain"):
        for mm in MOVE_MEDS:
            tag = "" if mm == 3.60 else f"|mm={mm}"
            for cm in (0.045, 0.09, 0.18, 0.36, 0.72):
                out.append(dict(cell=f"armF:courage_med={cm}{tag}",
                                regime=regime, share=0.0, strategy="ranked",
                                learn=True, move_med=mm,
                                params=dict(_base(courage_med=cm,
                                                  move_med=mm).__dict__)))
            for b0 in (0.025, 0.05, 0.10, 0.20, 0.40, 0.80):
                out.append(dict(cell=f"armF:belief0={b0}{tag}", regime=regime,
                                share=0.0, strategy="ranked", learn=True,
                                move_med=mm,
                                params=dict(_base(belief0=b0,
                                                  move_med=mm).__dict__)))
    return out


def _init(_unused=None):
    pass


PARTS = dict(queue=queue_specs, info=info_specs, split=split_specs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=sorted(PARTS))
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    sp = PARTS[a.part]()
    print(f"[run] {a.part}: {len(sp)} cells", flush=True)
    with Pool(a.procs, initializer=_init, initargs=(None,)) as pool:
        cells = pool.map(run_cell, sp, chunksize=1)
    out = os.path.join(_HERE, f"results_triage_{a.part}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(part=a.part, primitives=PRIMITIVES,
                                 stations=STATIONS[INST], units=INST,
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    hdr = (f"{'cell':34}{'reg':>5}{'ask':>7}{'succ':>7}{'read':>7}"
           f"{'gainCounter':>13}{'  se':>7}{'surplus':>9}{'r/mkt':>7}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for c in cells:
        d = c["derived"]
        print(f"{c['cell']:34}{c['regime']:>5}{d['counter_rate']:>7.3f}"
              f"{d['success_rate']:>7.3f}{d['reviewed_share']:>7.3f}"
              f"{d['gain_from_countering']:>13.0f}"
              f"{c['se']['gain_from_countering']:>7.0f}"
              f"{d['surplus_pcy']:>9.0f}{d['rent_ratio']:>7.3f}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
