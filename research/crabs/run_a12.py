"""AMENDMENT 12.

    python research/crabs/run_a12.py j1        # the two vacancy reports
    python research/crabs/run_a12.py j1wa      # the walk-away cross, in MONTHS
    python research/crabs/run_a12.py j2        # Phase 1: the match_sd grid
    python research/crabs/run_a12.py j2m       # market channel, same grid
    python research/crabs/run_a12.py j2k35     # what a 5% discount buys
    python research/crabs/run_a12.py j2hunt    # the Principle E bug hunt

JOB 1 is forensic, not experimental: it reads statistics off code that already
existed and adds ONE default-off ablation knob (`stagger_expiry`). It carries no
kill condition because there is no hypothesis to kill -- two amendments reported
two numbers about the same simulation and at most one of them can mean what it
was taken to mean.

  AMENDMENT 10  derived `vacancy` = 4.376 months time-to-let (fixed point).
  AMENDMENT 11  `market.py`'s baseline vacancy rate is 0.0000 in every cell.

JOB 2 (`run_a12.py j2*`) is pre-registered in PREREG-A12.md.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import replace
from multiprocessing import Pool

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from crabs.run_amend10 import BAND_HI, BAND_LO, SEARCH_PART, SWEEP, crossing
from crabs.run_market import SEEDS, derive_market
from crabs.world import ANCHOR_RENT, Params, regime_params

CENTRAL = 1.00        # MOVE_PHYSICAL, the central declared estimate ($2,000)


# --------------------------------------------------------------- plumbing ---
def _agg(p, mp_kw, seeds, drift=0.0):
    from crabs import market
    agg = None
    for s in seeds:
        r = market.simulate_market(p, market.MarketParams(
            n_stations=40, units=25, **mp_kw), s, drift=drift)
        c = {k: v for k, v in r.items() if not k.startswith("_")}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    return agg


def _row(tag, agg):
    d = derive_market(agg)
    return dict(
        cell=tag,
        stock_vacancy=d["vacancy"],
        flow_vacancy=d["vacancy_flow"],
        let_months=d["let_months"],
        dom_at_signing=d["dom_at_signing"],
        market_rent=d["market_rent_renew"],
        retention=d["retention"],
        wa_t_months=d["wa_tenant_renew_months"],
        wa_l_months=d["wa_land_renew_months"],
        wa_ratio=d["wa_ratio_renew"],
        wa_t_dollars=d["wa_tenant_renew"],
        wa_l_dollars=d["wa_land_renew"],
        lets=agg["n_newlet_signed"],
        leaves=agg["n_renewal_left"],
        habitat_years=agg["habitat_years"],
        unmatched=agg["n_unmatched"],
    )


# ------------------------------------------------------------------- j1 ----
def _j1_cell(spec):
    p = regime_params(Params(), "burn")
    return _row(spec["cell"], _agg(p, spec["mp"], SEEDS))


def j1():
    """The two reports, the definitional gap, and the one-knob ablation."""
    t0 = time.time()
    specs = [
        dict(cell="baseline", mp=dict()),
        dict(cell="stagger_expiry", mp=dict(stagger_expiry=True)),
        dict(cell="supply_shock", mp=dict(completions_frac=0.30)),
        dict(cell="supply_shock+stagger",
             mp=dict(completions_frac=0.30, stagger_expiry=True)),
    ] + [dict(cell=f"eta_{e:g}", mp=dict(eta_demand=e))
         for e in (0.0, 0.5, 1.0, 1.5, 2.0)]
    with Pool(6) as pool:
        rows = pool.map(_j1_cell, specs, chunksize=1)

    # the queue profile: WHEN in the year listings and searchers arrive
    prof = _month_profile()

    out = dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]], n_seeds=len(SEEDS),
                         anchor_rent=ANCHOR_RENT,
                         runtime_s=round(time.time() - t0, 1)),
               cells=rows, month_profile=prof)
    with open(os.path.join(_HERE, "results_a12_j1.json"), "w") as f:
        json.dump(out, f, indent=1)

    print(f"\n{'cell':22} {'stock':>8} {'flow':>8} {'let_mo':>7} {'dom':>6} "
          f"{'M_obs':>8} {'reten':>6} {'wa_t mo':>8} {'wa_l mo':>8} {'ratio':>6}")
    for r in rows:
        print(f"{r['cell']:22} {r['stock_vacancy']:8.4f} {r['flow_vacancy']:8.4f} "
              f"{r['let_months']:7.3f} {r['dom_at_signing']:6.3f} "
              f"{r['market_rent']:8.1f} {r['retention']:6.4f} "
              f"{r['wa_t_months']:8.3f} {r['wa_l_months']:8.3f} "
              f"{r['wa_ratio']:6.3f}")

    print("\nqueue profile, per station-year (baseline): when do listings and "
          "searchers arrive?")
    print(f"{'mo':>3} {'listings':>10} {'searchers':>10} {'lets':>8}")
    for m, (v, s, l) in enumerate(zip(prof["listings"], prof["searchers"],
                                      prof["lets"])):
        print(f"{m:3d} {v:10.1f} {s:10.1f} {l:8.1f}")
    print(f"\nmean month a leaver enters the pool: "
          f"{prof['mean_pool_entry_month']:.3f}")
    print(f"[{time.time()-t0:.1f}s]")


def _month_profile(seeds=None):
    """Instrumented rerun: listings on the market, searchers in the pool and
    lets signed, by month of the year. Patched in memory so that the shipped
    recorder does not grow twelve keys for one diagnostic."""
    import types
    seeds = seeds or SEEDS[:10]
    src = open(os.path.join(_HERE, "market.py")).read()
    src = src.replace(
        "        renew_M_sum=z, newlet_M_sum=z,\n    )",
        "        renew_M_sum=z, newlet_M_sum=z,\n    )\n"
        "    for _m in range(12):\n"
        "        r[f'_vm{_m}'] = z\n        r[f'_pm{_m}'] = z\n"
        "        r[f'_lm{_m}'] = z\n"
        "    r['_entry_sum'] = z\n    r['_entry_n'] = z\n")
    src = src.replace(
        '                rec["vacant_months"] += len(listings)',
        '                rec["vacant_months"] += len(listings)\n'
        '                rec[f"_vm{mo}"] += len(listings)\n'
        '                rec[f"_pm{mo}"] += len(carry)')
    src = src.replace('                    rec["depth_sum"] += depth\n',
                      '                    rec["depth_sum"] += depth\n'
                      '                    rec[f"_lm{mo}"] += 1.0\n')
    src = src.replace(
        "                        pool.append((leave_month, _to_searcher(crab, u)))",
        "                        pool.append((leave_month, _to_searcher(crab, u)))\n"
        "                        if R is not None:\n"
        "                            rec['_entry_sum'] += leave_month\n"
        "                            rec['_entry_n'] += 1.0")
    mod = types.ModuleType("crabs.market_a12diag")
    sys.modules["crabs.market_a12diag"] = mod
    exec(compile(src, "market_a12diag.py", "exec"), mod.__dict__)
    p = regime_params(Params(), "burn")
    agg = None
    for s in seeds:
        r = mod.simulate_market(p, mod.MarketParams(n_stations=40, units=25), s)
        c = {k: v for k, v in r.items() if not str(k).startswith("__")}
        c = {k: v for k, v in c.items() if not isinstance(v, list)}
        agg = c if agg is None else {k: agg[k] + v for k, v in c.items()}
    n = len(seeds) * 10 * 40          # seed-station-years
    return dict(
        listings=[agg[f"_vm{m}"] / n for m in range(12)],
        searchers=[agg[f"_pm{m}"] / n for m in range(12)],
        lets=[agg[f"_lm{m}"] / n for m in range(12)],
        mean_pool_entry_month=agg["_entry_sum"] / agg["_entry_n"])


# ----------------------------------------------------------------- j1wa ----
def _wa_cell(spec):
    from crabs import market
    market.RELET_RISK_ON = spec["relet"]
    base = Params(**{**Params().__dict__,
                     "move_med": SEARCH_PART + spec["move_physical"],
                     "move_sigma": 0.21})
    p = regime_params(base, "burn")
    if spec["vacancy"] is not None:
        p = replace(p, vacancy=spec["vacancy"])
    d = derive_market(_agg(p, dict(), SEEDS))
    return dict(move_physical=spec["move_physical"], relet=spec["relet"],
                vac_mode=spec["vac_mode"], vacancy=spec["vacancy"],
                ratio=d["wa_ratio_renew"],
                wa_t_months=d["wa_tenant_renew_months"],
                wa_l_months=d["wa_land_renew_months"],
                wa_t_dollars=d["wa_tenant_renew"],
                wa_l_dollars=d["wa_land_renew"],
                market_rent=d["market_rent_renew"],
                let_months=d["let_months"])


def j1wa():
    """AMENDMENT 10's K20/K30 cross, re-reported in months of market rent."""
    t0 = time.time()
    from crabs.market import BASE_LET_MONTHS
    modes = (("fitted", None), ("derived", 4.375915286695956),
             ("upstream", BASE_LET_MONTHS))
    specs = [dict(move_physical=m, relet=rl, vac_mode=nm, vacancy=v)
             for m in SWEEP for rl in (True, False) for nm, v in modes]
    with Pool(8) as pool:
        cells = pool.map(_wa_cell, specs, chunksize=1)
    with open(os.path.join(_HERE, "results_a12_j1wa.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 anchor_rent=ANCHOR_RENT,
                                 band=[BAND_LO, BAND_HI],
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=cells), f, indent=1)

    print(f"\nAt MOVE_PHYSICAL = {CENTRAL} (the central declared estimate, "
          f"$2,000 physical move)\n")
    print(f"{'vacancy':>9} {'relet':>6} {'wa_t mo':>8} {'wa_l mo':>8} "
          f"{'ratio':>6} | {'$ at M_obs':>19} | {'$ at ANCHOR $2,000':>21}")
    for nm, v in modes:
        for rl in (True, False):
            c = next(x for x in cells if x["move_physical"] == CENTRAL
                     and x["relet"] is rl and x["vac_mode"] == nm)
            at_m = f"T {c['wa_t_dollars']:6.0f} L {c['wa_l_dollars']:6.0f}"
            at_a = (f"T {c['wa_t_months']*ANCHOR_RENT:6.0f} "
                    f"L {c['wa_l_months']*ANCHOR_RENT:6.0f}")
            print(f"{nm:>9} {str(rl):>6} {c['wa_t_months']:8.3f} "
                  f"{c['wa_l_months']:8.3f} {c['ratio']:6.3f} | {at_m:>19} "
                  f"| {at_a:>21}")

    print("\ncrossings of ratio = 1.0 (band "
          f"[{BAND_LO*2000:.0f}, {BAND_HI*2000:.0f}]):")
    for nm, v in modes:
        for rl in (True, False):
            rows = [c for c in cells if c["relet"] is rl
                    and c["vac_mode"] == nm]
            rows = [dict(move_physical=r["move_physical"], ratio=r["ratio"])
                    for r in rows]
            x = crossing(rows)
            inside = (x == x) and BAND_LO <= x <= BAND_HI
            print(f"  vacancy={nm:<9} RELET_RISK_ON={str(rl):<6} -> "
                  + (f"${x*2000:7.0f}" if x == x else "never crosses".rjust(8))
                  + ("   INSIDE BAND" if inside else "   outside"))
    print(f"\n[{time.time()-t0:.1f}s]")


# ============================================================== JOB 2 ========
# Everything below is fixed in PREREG-A12.md §A12.2, complete before this code
# existed. Nothing here may be changed after a number has been seen.

from crabs.policies import StationDP                                  # noqa: E402
from crabs.run import MAIN_SEEDS, derive, pilot_prior, station_key    # noqa: E402
from crabs.world import (ASK_PRICE, CPS_EXO_SHARE_M3, CPS_MATCH_HAZARD,  # noqa
                         CPS_MATCH_SHARE, CPS_RENT_HAZARD, CPS_RENT_SHARE,
                         MATCH_EMAX, P_EXO_CPS_M3, P_EXO_CPS_NONHOUSING,
                         new_recorder, simulate_station)

HELDOUT_SEEDS = list(range(7000, 7060))

# §A12.2.5, fixed before the first run
MATCH_GRID = (0.00, 0.10, 0.20, 0.35, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00)
PEXO = {"M3": P_EXO_CPS_M3, "M1": P_EXO_CPS_NONHOUSING}   # M3 is PRIMARY
K33_LO, K33_HI = 0.52, 0.62                # §A12.2.7
COMP_TOL = 0.05                            # §A12.2.8
RENT_HAZ_LO, RENT_HAZ_HI = 0.010, 0.026    # §A12.2.8
OFFER_CUT = 0.05                           # §A12.2.9
K35_REL = 0.10                             # §A12.2.9

_C2: dict = {}


def _prior(base):
    if base not in _C2:
        _C2[base] = pilot_prior(base)
    return _C2[base]


def _phase1(base, regime, seeds=None):
    """One Phase 1 arm-A cell: registered spec, 39% price askers."""
    nodes, w = _prior(base)
    pb, pm = regime_params(base, "burn"), regime_params(base, regime)
    kb, km = station_key(pb, nodes, w, 0.0, False), \
        station_key(pm, nodes, w, 0.39, False)
    if kb not in _C2:
        _C2[kb] = StationDP(pb, nodes, w, share=0.0, adaptive=False)
    if km not in _C2:
        _C2[km] = StationDP(pm, nodes, w, share=0.39, adaptive=False)
    agg = new_recorder()
    rets = []
    for s in (seeds or MAIN_SEEDS):
        r = simulate_station(pb, pm, s, regime, _C2[kb], _C2[km], 0.39,
                             ASK_PRICE)
        for k, v in r.items():
            if not k.startswith("_"):
                agg[k] += v
        rets.append(1.0 - (r["left"] / r["renewals"] if r["renewals"] else 0.0))
    return agg, derive(agg), rets


def _compose(agg):
    """§A12.2.4. Three exhaustive channels over `left`, plus each one's annual
    hazard over `renewals` -- the unconditional denominator, per Principle D."""
    left, ren = agg["left"], agg["renewals"]
    f = lambda a, b: (a / b) if b else float("nan")          # noqa: E731
    return dict(
        exo_share=f(agg["left_exo"], left),
        rent_share=f(agg["left_rent"], left),
        match_share=f(agg["left_match"], left),
        exo_haz=f(agg["left_exo"], ren),
        rent_haz=f(agg["left_rent"], ren),
        match_haz=f(agg["left_match"], ren),
        mean_match=f(agg["match_sum"], agg["match_n"]))


def _comp_pass(c):
    return (abs(c["exo_share"] - CPS_EXO_SHARE_M3) <= COMP_TOL
            and abs(c["rent_share"] - CPS_RENT_SHARE) <= COMP_TOL
            and abs(c["match_share"] - CPS_MATCH_SHARE) <= COMP_TOL
            and RENT_HAZ_LO <= c["rent_haz"] <= RENT_HAZ_HI)


def _interp(xs, ys, target):
    """The x at which y first crosses `target`, linearly. NaN if it never
    does inside the swept range."""
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if (y0 - target) * (y1 - target) <= 0.0 and y0 != y1:
            return x0 + (target - y0) / (y1 - y0) * (x1 - x0)
    return float("nan")


def _j2_cell(spec):
    base = Params(**{**Params().__dict__,
                     "p_exo_floor": PEXO[spec["pexo"]], "p_exo_extra": 0.0,
                     "match_sd": spec["sd"], "offer_cut": spec.get("cut", 0.0),
                     "match_option": spec.get("match_option", True)})
    agg, d, rets = _phase1(base, spec["regime"],
                           HELDOUT_SEEDS if spec.get("heldout") else None)
    row = dict(spec)
    row.update(retention=d["retention"], turnover=d["turnover"],
               retention_se=float(np.std(rets, ddof=1) / np.sqrt(len(rets))),
               push=d["mean_offer_push"], success=d["success_rate"],
               rent_ratio=d["rent_ratio"], surplus_pcy=d["surplus_pcy"],
               **_compose(agg))
    return row


def j2():
    """The grid, K33 and K34."""
    t0 = time.time()
    specs = [dict(sd=sd, pexo=pe, regime=rg)
             for pe in ("M3", "M1") for rg in ("loss", "gain")
             for sd in MATCH_GRID]
    with Pool(6) as pool:
        rows = pool.map(_j2_cell, specs, chunksize=1)

    out = dict(meta=dict(seeds=[MAIN_SEEDS[0], MAIN_SEEDS[-1]],
                         grid=list(MATCH_GRID), match_emax=MATCH_EMAX,
                         targets=dict(exo=CPS_EXO_SHARE_M3,
                                      rent=CPS_RENT_SHARE,
                                      match=CPS_MATCH_SHARE,
                                      match_haz=CPS_MATCH_HAZARD,
                                      rent_haz=CPS_RENT_HAZARD),
                         runtime_s=round(time.time() - t0, 1)),
               cells=rows)
    with open(os.path.join(_HERE, "results_a12_j2.json"), "w") as f:
        json.dump(out, f, indent=1)
    _report_j2(rows)
    print(f"[{time.time()-t0:.1f}s]")


def _report_j2(rows):
    print(f"\nCPS targets: exo {CPS_EXO_SHARE_M3:.4f}  rent {CPS_RENT_SHARE:.4f}"
          f"  match {CPS_MATCH_SHARE:.4f} | match haz "
          f"{CPS_MATCH_HAZARD*100:.4f}%/yr  rent haz {CPS_RENT_HAZARD*100:.4f}%/yr")
    for pe in ("M3", "M1"):
        for rg in ("loss", "gain"):
            sel = [r for r in rows if r["pexo"] == pe and r["regime"] == rg]
            sel.sort(key=lambda r: r["sd"])
            print(f"\n--- p_exo={pe} ({PEXO[pe]:.6f})  regime={rg}")
            print(f"{'match_sd':>9} {'reten':>8} {'+-':>6} {'exo':>7} {'rent':>7}"
                  f" {'match':>7} | {'m.haz%':>7} {'r.haz%':>7} | {'push':>8}"
                  f" {'mean m':>7}  K33  comp")
            for r in sel:
                inb = K33_LO <= r["retention"] <= K33_HI
                print(f"{r['sd']:9.2f} {r['retention']:8.4f} "
                      f"{r['retention_se']:6.4f} {r['exo_share']:7.4f} "
                      f"{r['rent_share']:7.4f} {r['match_share']:7.4f} | "
                      f"{r['match_haz']*100:7.3f} {r['rent_haz']*100:7.3f} | "
                      f"{r['push']:+8.4f} {r['mean_match']:7.3f}  "
                      f"{'IN ' if inb else '-- '}  {'PASS' if _comp_pass(r) else '----'}")
            xs = [r["sd"] for r in sel]
            s_star = _interp(xs, [r["match_haz"] for r in sel],
                             CPS_MATCH_HAZARD)
            s_ret = _interp(xs, [r["retention"] for r in sel], 0.573)
            print(f"    sigma* (match hazard = CPS 3.1418%/yr) = {s_star:.4f}"
                  f"    match_sd reproducing retention 0.573 = {s_ret}")
    prim = [r for r in rows if r["pexo"] == "M3"]
    any_in = [r for r in prim if K33_LO <= r["retention"] <= K33_HI]
    print(f"\nK33 (fires if NO grid point puts M3 retention in "
          f"[{K33_LO}, {K33_HI}]): "
          f"{'FIRES' if not any_in else 'does NOT fire'}"
          f"   ({len(any_in)}/{len(prim)} cells in band)")
    if not any_in:
        print("K34 is VACUOUS by its own definition -- retention never arrives, "
              "so there is no cell at which to test the composition.")
    else:
        ok = [r for r in any_in if _comp_pass(r)]
        print(f"K34 (fires if composition fails at EVERY in-band cell): "
              f"{'FIRES' if not ok else 'does NOT fire'}"
              f"   ({len(ok)}/{len(any_in)} in-band cells also match CPS)")


def j2k35():
    """§A12.2.9. What a flat 5% renewal discount buys in retention, with and
    without the match channel, on an identical population."""
    t0 = time.time()
    import json as _j
    with open(os.path.join(_HERE, "results_a12_j2.json")) as f:
        grid = _j.load(f)["cells"]
    sds = {}
    for pe in ("M3", "M1"):
        for rg in ("loss", "gain"):
            sel = sorted([r for r in grid if r["pexo"] == pe
                          and r["regime"] == rg], key=lambda r: r["sd"])
            s = _interp([r["sd"] for r in sel],
                        [r["match_haz"] for r in sel], CPS_MATCH_HAZARD)
            sds[(pe, rg)] = s
    specs = []
    for (pe, rg), s in sds.items():
        if s != s:
            continue
        for sd in (0.0, round(float(s), 4), 1.00, 3.00):
            for cut in (0.0, OFFER_CUT):
                specs.append(dict(sd=sd, pexo=pe, regime=rg, cut=cut))
    with Pool(6) as pool:
        rows = pool.map(_j2_cell, specs, chunksize=1)
    with open(os.path.join(_HERE, "results_a12_j2k35.json"), "w") as f:
        json.dump(dict(meta=dict(sigma_star=
                                 {f"{k[0]}/{k[1]}": v for k, v in sds.items()},
                                 offer_cut=OFFER_CUT,
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=rows), f, indent=1)

    print(f"\nK35 -- what a {OFFER_CUT:.0%} renewal discount buys in retention\n")
    print(f"{'pexo':>5} {'regime':>7} {'match_sd':>9} {'ret(no cut)':>12} "
          f"{'ret(cut)':>10} {'d ret':>8} {'rel to sd=0':>12}")
    for pe in ("M3", "M1"):
        for rg in ("loss", "gain"):
            base_d = None
            for sd in sorted({r["sd"] for r in rows
                              if r["pexo"] == pe and r["regime"] == rg}):
                def g(cut):
                    return next(r for r in rows if r["pexo"] == pe
                                and r["regime"] == rg and r["sd"] == sd
                                and r["cut"] == cut)
                a, b = g(0.0), g(OFFER_CUT)
                d = b["retention"] - a["retention"]
                if sd == 0.0:
                    base_d = d
                rel = d / base_d if base_d else float("nan")
                print(f"{pe:>5} {rg:>7} {sd:9.4f} {a['retention']:12.4f} "
                      f"{b['retention']:10.4f} {d:+8.4f} {rel:12.3f}")
    print(f"\n[{time.time()-t0:.1f}s]")


def _j2m_cell(spec):
    pe, sd = spec["pexo"], spec["sd"]
    base = Params(**{**Params().__dict__,
                     "p_exo_floor": PEXO[pe], "p_exo_extra": 0.0,
                     "match_sd": sd})
    p = regime_params(base, "burn")
    agg = _agg(p, dict(), SEEDS)
    d = derive_market(agg)
    L = max(agg["n_renewal_left"], 1.0)
    N = max(agg["n_renewal"], 1.0)
    return dict(pexo=pe, sd=sd, retention=d["retention"],
                exo_share=agg["n_left_exo"] / L,
                rent_share=agg["n_left_rent"] / L,
                match_share=agg["n_left_match"] / L,
                match_haz=agg["n_left_match"] / N,
                rent_haz=agg["n_left_rent"] / N,
                mean_match=agg["match_sum"] / max(agg["match_n"], 1.0),
                newlet_match=agg["newlet_match_sum"]
                / max(agg["n_newlet_signed"], 1.0),
                renew_growth=d["renew_growth"],
                newlet_growth=d["newlet_growth"],
                market_rent=d["market_rent_renew"],
                let_months=d["let_months"],
                wa_ratio=d["wa_ratio_renew"])


def j2m():
    """The market channel over the same grid: retention, composition, and what
    the searcher's choice on match does to prices."""
    t0 = time.time()
    specs = [dict(pexo=pe, sd=sd) for pe in ("M3", "M1") for sd in MATCH_GRID]
    with Pool(8) as pool:
        rows = pool.map(_j2m_cell, specs, chunksize=1)
    print(f"\n{'pexo':>5} {'sd':>5} {'reten':>8} {'exo':>7} {'rent':>7} "
          f"{'match':>7} {'m.haz%':>7} {'mean m':>7} {'newlet m':>8} "
          f"{'M rent':>8}")
    for r in rows:
        print(f"{r['pexo']:>5} {r['sd']:5.2f} {r['retention']:8.4f} "
              f"{r['exo_share']:7.4f} {r['rent_share']:7.4f} "
              f"{r['match_share']:7.4f} {r['match_haz']*100:7.3f} "
              f"{r['mean_match']:7.3f} {r['newlet_match']:8.3f} "
              f"{r['market_rent']:8.1f}")
    with open(os.path.join(_HERE, "results_a12_j2m.json"), "w") as f:
        json.dump(dict(meta=dict(seeds=[SEEDS[0], SEEDS[-1]],
                                 runtime_s=round(time.time() - t0, 1)),
                       cells=rows), f, indent=1)
    print(f"[{time.time()-t0:.1f}s]")




def j2hunt():
    """The Principle E hunt, run whether or not the result went our way."""
    t0 = time.time()
    specs = []
    for sd in (0.0, 1.00, 3.00):
        for rg in ("loss", "gain"):
            specs.append(dict(sd=sd, pexo="M3", regime=rg, tag="main"))
            specs.append(dict(sd=sd, pexo="M3", regime=rg, tag="heldout",
                              heldout=True))
            specs.append(dict(sd=sd, pexo="M3", regime=rg, tag="no_option",
                              match_option=False))
    with Pool(6) as pool:
        rows = pool.map(_j2_cell, specs, chunksize=1)
    with open(os.path.join(_HERE, "results_a12_j2hunt.json"), "w") as f:
        json.dump(dict(meta=dict(runtime_s=round(time.time() - t0, 1)),
                       cells=rows), f, indent=1)
    print(f"\n{'tag':>13} {'regime':>7} {'sd':>5} {'reten':>8} {'exo':>7} "
          f"{'rent':>7} {'match':>7} {'m.haz%':>7} {'push':>8}")
    for r in sorted(rows, key=lambda r: (r["tag"], r["regime"], r["sd"])):
        print(f"{r['tag']:>13} {r['regime']:>7} {r['sd']:5.2f} "
              f"{r['retention']:8.4f} {r['exo_share']:7.4f} "
              f"{r['rent_share']:7.4f} {r['match_share']:7.4f} "
              f"{r['match_haz']*100:7.3f} {r['push']:+8.4f}")
    print(f"\n[{time.time()-t0:.1f}s]")


MODES = {"j1": j1, "j1wa": j1wa, "j2": j2, "j2m": j2m, "j2k35": j2k35,
         "j2hunt": j2hunt}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "j1"
    MODES[which]()
