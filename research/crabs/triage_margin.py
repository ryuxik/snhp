"""TRIAGE (a) -- is "a landlord at its own optimum is indifferent at the margin,
so a randomly-chosen counter earns it nothing" ANALYTIC, or a parameter readout?

No simulation: this reads the station's own dynamic program directly.

The analytic claim, derived and then checked numerically:

    W(q, z) = (1 - pl(g - z)) * (S(q) - z) + pl(g - z) * T
    g(q)    = 12*kappa*(q-1) + 12*lambda*(q-r) - a(j)     (crab's gain from leaving)
    S(q)    = 12*q*(1+fp) - qs + d1*V(q/(1+g_mkt), j+1)   (station's stay value)

    dW/dz |z=0  =  pl'(g)*(S-T) - (1-pl)
    dW/dq       = -pl'(g)*gamma*(S-T) + (1-pl)*sigma  ==  0  at the optimum

      gamma = dg/dq = 12*(kappa_crab + lambda_ref)      <- the CRAB's valuation
      sigma = dS/dq = 12*(1+face_premium) + d1*dV/dr'   <- the STATION's

    substituting the optimality condition:

        dW/dz |z=0  =  (1 - pl) * (sigma/gamma - 1)

So the first-order value of a marginal cash concession is NOT zero and is NOT
structural. It is (1-pl) times how much more a marginal dollar of headline rent
is worth to the station than to the crab. Indifference holds only where
sigma == gamma, i.e. where

    12*(1 + face_premium) + persistence  ==  12*(kappa_crab + lambda_ref)

which is a horse race between three constants PARAM_SOURCES calls INVENTED.

This script measures sigma, gamma, the predicted A = (1-pl)(sigma/gamma - 1) and
the ACTUAL numerical dW/dz, at the station's own chosen offer, over the state
grid, for a sweep of face_premium / kappa_crab / lambda_ref / renewal_cap.
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

from crabs.policies import QA, StationDP
from crabs.run import EXPLORATORY, pilot_prior
from crabs.world import (FEES, ONE_TIME, RENT, TERM, Params, regime_params)

KINDS = {"ONE_TIME": ONE_TIME, "FEES": FEES, "TERM": TERM, "RENT": RENT}
RGRID = (0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30)
JGRID = (1, 3, 5, 8)
EPS = 1e-4                      # marginal concession size, months of crab value


def _margin(st: StationDP, p: Params, r: float, j: int) -> dict:
    """Everything the analytic decomposition needs, at the station's own q*."""
    q = st.offer(r, j)
    W = lambda qq: st.npv(qq, r, j, None)
    w0 = W(q)
    step = float(QA[1] - QA[0])
    up, dn = W(q + step), W(q - step)
    # the cap binds when the largest grid action inside it is chosen, i.e. when
    # the station would move UP if it were allowed to
    at_cap = bool(q >= r * (1.0 + p.renewal_cap) - step - 1e-9)
    at_top = bool(q >= QA[-1] - 1e-9)

    # ---- gamma: the crab's marginal valuation of q (analytic, exact)
    gamma = 12.0 * (p.kappa_crab + p.lambda_ref)
    # ---- sigma: the station's marginal stay-value in q (numeric on the DP)
    d1 = p.disc_station * (1.0 + st.gv)
    j2 = min(j + 1, p.j_max)
    S = lambda qq: (12.0 * qq * (1.0 + p.face_premium)
                    - st._qsit[min(j, p.j_max + 1)]
                    + d1 * st._Vg(st.V, qq / (1.0 + st.g), j2))
    sigma = (S(q + step) - S(q - step)) / (2.0 * step)

    gain = (12.0 * p.kappa_crab * (q - 1.0) + p.lambda_ref * 12.0 * (q - r)
            - st._attach[min(j, p.j_max + 1)])
    pl = float(st.leave_prob(gain, j))
    pred_A = (1.0 - pl) * (sigma / gamma - 1.0)

    out = dict(r=r, j=j, q=float(q), push=float(q / r - 1.0), at_cap=at_cap,
               at_grid_top=at_top, pl=pl, sigma=float(sigma), gamma=float(gamma),
               sigma_over_gamma=float(sigma / gamma), pred_A=float(pred_A),
               dW_dq_up=float(up - w0), dW_dq_dn=float(w0 - dn))
    # ---- the ACTUAL first-order value of each instrument, per unit of crab
    # value delivered. Two epsilons, so convergence is visible rather than
    # assumed.
    for name, kind in KINDS.items():
        row = {}
        for eps_s in (1e-3, 1e-4):
            # size is in units of ask_frac; convert so crab value ~ eps_s months
            size = eps_s
            cv = float(st.crab_value(p, q, (kind, size), st.g))
            if cv <= 0.0:
                row[f"A_{eps_s:g}"] = float("nan")
                continue
            row[f"A_{eps_s:g}"] = float(
                (st.npv(q, r, j, (kind, size)) - w0) / cv)
        # and at the sizes the grant menu actually offers (SPEC §7)
        for f in (0.3, 0.6, 1.0):
            cv = float(st.crab_value(p, q, (kind, f), st.g))
            row[f"gap_{f}"] = float(st.npv(q, r, j, (kind, f)) - w0)
            row[f"cv_{f}"] = cv
            row[f"grants_{f}"] = bool(cv > 0.0
                                      and st.npv(q, r, j, (kind, f)) >= w0)
        out[name] = row
    return out


def cell(base: Params, regime: str, nodes, w, label: str) -> dict:
    p = regime_params(base, regime)
    st = StationDP(p, nodes, w)
    rows = [_margin(st, p, r, j) for r in RGRID for j in JGRID]
    grants = {k: float(np.mean([any(x[k][f"grants_{f}"] for f in (0.3, 0.6, 1.0))
                                for x in rows])) for k in KINDS}
    return dict(label=label, regime=regime, face_premium=base.face_premium,
                kappa_crab=base.kappa_crab, lambda_ref=base.lambda_ref,
                renewal_cap=base.renewal_cap, nu=base.nu,
                move_med=base.move_med, rows=rows,
                share_constrained=float(np.mean(
                    [x["dW_dq_up"] > 1e-9 for x in rows])),
                share_at_cap=float(np.mean([x["at_cap"] for x in rows])),
                mean_sigma_over_gamma=float(np.mean(
                    [x["sigma_over_gamma"] for x in rows])),
                mean_pred_A=float(np.mean([x["pred_A"] for x in rows])),
                mean_A_onetime=float(np.nanmean(
                    [x["ONE_TIME"]["A_0.0001"] for x in rows])),
                any_grant_share=grants)


def main():
    t0 = time.time()
    base0 = Params(**EXPLORATORY)
    print("[pilot] ...", flush=True)
    nodes, w = pilot_prior(base0)
    cells = []
    sweeps = [("baseline", {})]
    for fp in (0.0, 0.5, 1.0, 2.0, 4.0):
        sweeps.append((f"face_premium={fp}", dict(face_premium=fp)))
    for kc in (0.8, 1.2, 1.6, 2.4, 3.2):
        sweeps.append((f"kappa_crab={kc}", dict(kappa_crab=kc)))
    for lr in (0.0, 0.25, 0.5, 1.0):
        sweeps.append((f"lambda_ref={lr}", dict(lambda_ref=lr)))
    for rc in (0.06, 0.12, 0.25, 2.00):
        sweeps.append((f"renewal_cap={rc}", dict(renewal_cap=rc)))
    for nu in (0.3, 0.6, 1.2):
        sweeps.append((f"nu={nu}", dict(nu=nu)))
    # AMENDMENT 8: move_med is CALIBRATED and derives to 1.48, not 3.60. The
    # station's quadrature NODES depend on it, so this sweep gets its own prior.
    for mm in (1.48, 3.60, 7.20):
        sweeps.append((f"move_med={mm}", dict(move_med=mm)))
    for label, over in sweeps:
        b = Params(**{**base0.__dict__, **over})
        nn, ww = (pilot_prior(b) if "move_med" in over else (nodes, w))
        for regime in ("loss", "gain"):
            cells.append(cell(b, regime, nn, ww, label))
        print(f"  {label:22} done ({time.time()-t0:.0f}s)", flush=True)

    out = os.path.join(_HERE, "results_triage_margin.json")
    with open(out, "w") as f:
        json.dump(dict(meta=dict(runtime_s=round(time.time() - t0, 1),
                                 rgrid=RGRID, jgrid=JGRID), cells=cells), f)

    print("\nTRIAGE (a): is the station indifferent at the margin?\n")
    hdr = (f"{'sweep':22} {'reg':>5} {'sig/gam':>8} {'pred A':>8} "
           f"{'act A':>8} {'@cap':>6} {'constr':>7} {'grant:1T':>9} "
           f"{'grant:RENT':>11}")
    print(hdr)
    print("-" * len(hdr))
    for c in cells:
        print(f"{c['label']:22} {c['regime']:>5} "
              f"{c['mean_sigma_over_gamma']:>8.3f} {c['mean_pred_A']:>8.4f} "
              f"{c['mean_A_onetime']:>8.4f} {c['share_at_cap']*100:>5.0f}% "
              f"{c['share_constrained']*100:>6.0f}% "
              f"{c['any_grant_share']['ONE_TIME']*100:>8.0f}% "
              f"{c['any_grant_share']['RENT']*100:>10.0f}%")
    print(f"\n[wrote {out}]")


if __name__ == "__main__":
    main()
