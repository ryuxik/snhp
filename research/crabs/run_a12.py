"""AMENDMENT 12.

    python research/crabs/run_a12.py j1        # the two vacancy reports
    python research/crabs/run_a12.py j1wa      # the walk-away cross, in MONTHS

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


MODES = {"j1": j1, "j1wa": j1wa}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "j1"
    MODES[which]()
