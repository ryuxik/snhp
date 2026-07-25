"""TRIAGE (e) -- the externality that is printed on a live user-facing page.

    python research/crabs/triage_extern.py --part k3
    python research/crabs/triage_extern.py --part k8

Claim: "as more crabs counter, stations raise the OPENING offer for everyone,
and the ones who counter recover more than the increase while the quiet ones
absorb it."  K3 (arm E, Phase 1) and K8 (arm F broadcast, Phase 2).

Both run through the ADAPTIVE station, whose whole channel RESULTS §K2/§K7 says
is `FACE_RENT_PREMIUM`: "at premium 0 the adaptive station has no reason to make
the swap and the effect disappears."  That is the sweep this file exists for.

Three things are varied, one at a time:
  face_premium   {0, 0.5, 1.0, 2.0, 4.0}   INVENTED (SPEC §6)
  p_substitute   {0, 0.35, 0.7, 1.0}       INVENTED (SPEC §7)
  renewal_cap    {0.12, 2.00}              CIRCULAR (AMENDMENT 7)

and the MECHANISM is ablated: arm D at the same asker share is the same world
with an adaptive station that cannot see the share at all. If the non-asker loss
survives there, it is not "the landlord raised the offer on everyone".
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

from crabs import run as R
from crabs import run2 as R2
from crabs.landlords import INSTITUTIONAL, make_landlord
from crabs.policies import StationDP
from crabs.world import Params, regime_params

# ---------------------------------------------------------------------------
# CACHE-COLLISION FIX. `run._station` keys its station cache on
# (regime, share, adaptive, face_premium, p_substitute, p_continue) and
# `run2._get` on (type, regime, share, adaptive, units, face_premium,
# sigma_turn). Neither includes `renewal_cap` or `move_med`, both of which
# change the SOLVED policy (the action mask and the leave table). Sweeping
# either through the shipped runners silently reuses another cell's station.
# Both are replaced here with a key over the full parameter set. Nothing in the
# shipped code is edited; this is the runner this file uses.
_STATIONS: dict = {}


def _pkey(base: Params):
    return tuple(sorted((k, str(v)) for k, v in base.__dict__.items()))


def _station_fixed(base: Params, regime: str, nodes, w, share: float,
                   adaptive: bool):
    key = (_pkey(base), regime, round(share, 6), bool(adaptive))
    if key not in _STATIONS:
        _STATIONS[key] = StationDP(regime_params(base, regime), nodes, w,
                                   share=share, adaptive=adaptive)
    return _STATIONS[key]


def _get_fixed(base, ltype, regime, nodes, w, share, adaptive):
    key = (_pkey(base), ltype, regime, round(share, 6), bool(adaptive))
    if key not in _STATIONS:
        _STATIONS[key] = make_landlord(ltype, regime_params(base, regime),
                                       nodes, w, share=share, adaptive=adaptive)
    return _STATIONS[key]


R._station = _station_fixed
R2._get = _get_fixed

SWEEPS = (
    [("face_premium", v) for v in (0.0, 0.5, 1.0, 2.0, 4.0)]
    + [("p_substitute", v) for v in (0.0, 0.35, 0.7, 1.0)]
    + [("renewal_cap", v) for v in (0.12, 2.00)]
    + [("move_med", v) for v in (1.48, 3.60)]
    + [("courage_med", v) for v in (0.09, 0.18, 0.36)]
    + [("belief0", v) for v in (0.05, 0.10, 0.20)]
)
ARM_E_SWEEPS = [(n, v) for n, v in SWEEPS
                if n not in ("courage_med", "belief0")]


def _init_k3(prior):
    R._CACHE["prior"] = prior
    R._station = _station_fixed


def _init_k8(prior):
    R2._CACHE["prior"] = prior
    R2._get = _get_fixed


# ------------------------------------------------------------------- K3, arm E
def k3_specs(seeds, spec_name):
    base0 = Params(**R.EXPLORATORY) if spec_name == "exploratory" else Params()
    out = []
    for name, val in ARM_E_SWEEPS:       # arm E has no belief machinery
        b = Params(**{**base0.__dict__, name: val})
        for regime in ("loss", "gain"):
            for arm, sh, ad in (("E", 0.0, True), ("E", 0.75, True),
                                ("D", 0.0, False), ("D", 0.75, False)):
                out.append(dict(arm=arm, share=sh, strategy="ranked",
                                adaptive=ad, regime=regime, seeds=seeds,
                                sweep=name, sweep_val=val, spec=spec_name,
                                params=dict(b.__dict__)))
    return out


def run_k3(a):
    t0 = time.time()
    base0 = Params(**R.EXPLORATORY) if a.spec == "exploratory" else Params()
    seeds = R.MAIN_SEEDS if a.seeds == "main" else R.HELDOUT_SEEDS
    sp = k3_specs(seeds, a.spec)
    print(f"[run] k3: {len(sp)} cells", flush=True)
    cells = []
    # one pilot prior per move_med: the quadrature NODES depend on it
    for mm in sorted({s["params"]["move_med"] for s in sp}):
        prior = R.pilot_prior(Params(**{**base0.__dict__, "move_med": mm}))
        sub = [s for s in sp if s["params"]["move_med"] == mm]
        with Pool(a.procs, initializer=_init_k3, initargs=(prior,)) as pool:
            cells.extend(pool.map(R.run_cell, sub, chunksize=1))
    def pick(name, val, regime, arm, share):
        for c in cells:
            if (c["sweep"] == name and c["sweep_val"] == val
                    and c["regime"] == regime and c["arm"] == arm
                    and abs(c["share"] - share) < 1e-9):
                return c
        raise KeyError((name, val, regime, arm, share))

    rows = []
    for name, val in ARM_E_SWEEPS:
        for regime in ("loss", "gain"):
            for arm in ("E", "D"):
                b0 = pick(name, val, regime, arm, 0.0)
                h = pick(name, val, regime, arm, 0.75)
                s0 = b0["derived"]["surplus_pcy"]
                nonask = h["derived"]["surplus_nonasker"]
                ask = h["derived"]["surplus_asker"]
                se = float(np.nanstd(h["per_station"]["surplus_nonasker"],
                                     ddof=1) / np.sqrt(len(seeds)))
                se0 = float(np.nanstd(b0["per_station"]["surplus_pcy"],
                                      ddof=1) / np.sqrt(len(seeds)))
                rows.append(dict(
                    sweep=name, val=val, regime=regime, arm=arm,
                    S0=s0, nonasker=nonask, asker=ask,
                    harm=s0 - nonask, se=float(np.hypot(se, se0)),
                    fires=bool(s0 - nonask >= 240.0),
                    rmkt0=b0["derived"]["rent_ratio"],
                    rmkt75=h["derived"]["rent_ratio"],
                    success75=h["derived"]["success_rate"]))
    out = os.path.join(_HERE, f"results_triage_k3_{a.spec}_{a.seeds}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(spec=a.spec, seeds=a.seeds,
                                 runtime_s=round(time.time() - t0, 1)),
                       rows=rows, cells=cells), f)
    hdr = (f"{'sweep':16}{'val':>6}{'reg':>5}{'arm':>4}{'S0':>9}{'nonasker':>10}"
           f"{'harm':>8}{'se':>6}{'bar240':>8}{'r/mkt 0':>9}{'r/mkt .75':>10}"
           f"{'succ':>7}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['sweep']:16}{r['val']:>6.2f}{r['regime']:>5}{r['arm']:>4}"
              f"{r['S0']:>9.0f}{r['nonasker']:>10.0f}{r['harm']:>8.0f}"
              f"{r['se']:>6.0f}{'FIRES' if r['fires'] else '-':>8}"
              f"{r['rmkt0']:>9.4f}{r['rmkt75']:>10.4f}{r['success75']:>7.3f}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


# ------------------------------------------------------------- K8, arm F bcast
def k8_specs(spec_name):
    base0 = Params(**R.EXPLORATORY) if spec_name == "exploratory" else Params()
    out = []
    for name, val in SWEEPS:
        b = Params(**{**base0.__dict__, name: val})
        for regime in ("loss", "gain"):
            for bc in (False, True):
                out.append(dict(params=dict(b.__dict__), type=INSTITUTIONAL,
                                regime=regime, arm="F-adaptive", share=0.0,
                                strategy="ranked", adaptive=True, broadcast=bc,
                                sweep=name, sweep_val=val))
    return out


def run_k8(a):
    t0 = time.time()
    base0 = Params(**R.EXPLORATORY) if a.spec == "exploratory" else Params()
    sp = k8_specs(a.spec)
    print(f"[run] k8: {len(sp)} cells", flush=True)
    cells = []
    for mm in sorted({s["params"]["move_med"] for s in sp}):
        prior = R.pilot_prior(Params(**{**base0.__dict__, "move_med": mm}))
        sub = [s for s in sp if s["params"]["move_med"] == mm]
        with Pool(a.procs, initializer=_init_k8, initargs=(prior,)) as pool:
            cells.extend(pool.map(R2.run_cell, sub, chunksize=1))
    rows = []
    for name, val in SWEEPS:
        for regime in ("loss", "gain"):
            off = [c for c in cells if c["sweep"] == name
                   and c["sweep_val"] == val and c["regime"] == regime
                   and not c["broadcast"]][0]
            on = [c for c in cells if c["sweep"] == name
                  and c["sweep_val"] == val and c["regime"] == regime
                  and c["broadcast"]][0]
            da, db = on["derived"], off["derived"]
            se_n = float(np.nanstd(np.array(on["per_station"]["surplus_nonasker"])
                                   - np.array(off["per_station"]["surplus_nonasker"]),
                                   ddof=1) / np.sqrt(60))
            rows.append(dict(
                sweep=name, val=val, regime=regime,
                share_off=db["ask_share"], share_on=da["ask_share"],
                asker=da["surplus_asker"] - db["surplus_asker"],
                nonasker=da["surplus_nonasker"] - db["surplus_nonasker"],
                se_nonasker=se_n,
                total=da["surplus_pcy"] - db["surplus_pcy"],
                rmkt_off=db["rent_ratio"], rmkt_on=da["rent_ratio"],
                success_off=db["success_rate"], success_on=da["success_rate"],
                fires=bool((da["surplus_asker"] - db["surplus_asker"]) > 0
                           and (da["surplus_nonasker"]
                                - db["surplus_nonasker"]) < 0)))
    out = os.path.join(_HERE, f"results_triage_k8_{a.spec}.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(spec=a.spec,
                                 runtime_s=round(time.time() - t0, 1)),
                       rows=rows, cells=cells), f)
    hdr = (f"{'sweep':16}{'val':>6}{'reg':>5}{'share off':>10}{'on':>7}"
           f"{'askers':>9}{'nonaskers':>11}{'se':>6}{'total':>8}{'K8':>7}"
           f"{'r/mkt off':>11}{'on':>8}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['sweep']:16}{r['val']:>6.2f}{r['regime']:>5}"
              f"{r['share_off']:>10.3f}{r['share_on']:>7.3f}"
              f"{r['asker']:>9.0f}{r['nonasker']:>11.0f}{r['se_nonasker']:>6.0f}"
              f"{r['total']:>8.0f}{'FIRES' if r['fires'] else '-':>7}"
              f"{r['rmkt_off']:>11.4f}{r['rmkt_on']:>8.4f}")
    print(f"\n[wrote {out} in {time.time()-t0:.1f}s]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=("k3", "k8"))
    ap.add_argument("--spec", default="exploratory",
                    choices=("registered", "exploratory"))
    ap.add_argument("--seeds", default="main", choices=("main", "heldout"))
    ap.add_argument("--procs", type=int, default=8)
    a = ap.parse_args()
    (run_k3 if a.part == "k3" else run_k8)(a)


if __name__ == "__main__":
    main()
