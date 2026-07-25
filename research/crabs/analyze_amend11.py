"""Verdicts for AMENDMENT 11 (K31, K32) and every before/after table.

    python research/crabs/analyze_amend11.py

Reads results_amend11.json. Every bar comes from PREREG-A11.md, written before
run_amend11.py existed.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_RESEARCH = os.path.dirname(_HERE)
for _p in (_RESEARCH, os.path.dirname(_RESEARCH)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

import glob
ROWS, META = [], {}
for _f in sorted(glob.glob(os.path.join(_HERE, "results_amend11_*.json"))):
    _b = json.load(open(_f))
    ROWS += _b["rows"]
    META.update(_b["meta"])
K31_LO, K31_HI = META["k31_band"]
K32_LO, K32_HI = META["k32_band"]
CPS = META["cps_nonhousing_share"]


def sel(job, **kw):
    out = [r for r in ROWS if r.get("job") == job
           and all(r.get(k) == v for k, v in kw.items())]
    return out


def one(job, **kw):
    m = sel(job, **kw)
    assert len(m) == 1, (job, kw, len(m))
    return m[0]


def hdr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def j1():
    hdr("JOB 1 — Phase 1 under sourced p_exo (arm A, 39% price askers)")
    for spec in ("registered", "exploratory"):
        print(f"\n--- {spec} spec ---")
        print(f"{'var':5} {'reg':5} {'p_exo(1)':>9} {'p_exo(8)':>9} "
              f"{'retention':>10} {'turnover':>9} {'exo/left':>9} "
              f"{'endoonly':>9} {'succ':>7} {'ten ratio':>10} {'push':>8}")
        for r in sel("j1", spec=spec):
            print(f"{r['variant']:5} {r['regime']:5} {r['p_exo1']:9.4f} "
                  f"{r['p_exo8']:9.4f} {r['retention']:10.4f} "
                  f"{r['turnover']:9.4f} {r['exo_share']:9.4f} "
                  f"{r['endo_only_share']:9.4f} {r['success_rate']:7.4f} "
                  f"{r['tenure_ratio']:10.3f} {r['mean_offer_push']:+8.4f}")

    hdr("K31 — the sourced hazard does not reproduce observed retention")
    print(f"Fires if S1 retention is outside {K31_LO:.2f}-{K31_HI:.2f} "
          f"(observed ~57.3%). Registered spec, arm A, both regimes.")
    fired = []
    for regime in ("loss", "gain"):
        r = one("j1", spec="registered", variant="S1", regime=regime)
        f = not (K31_LO <= r["retention"] <= K31_HI)
        fired.append(f)
        b = one("j1", spec="registered", variant="F", regime=regime)
        print(f"  {regime:5}: fitted {b['retention']:.4f} -> sourced "
              f"{r['retention']:.4f} +- {r['retention_se']:.4f}   "
              f"{'FIRES' if f else 'does NOT fire'}")
    print(f"  VERDICT: K31 {'FIRED' if all(fired) else ('FIRED in one regime' if any(fired) else 'DID NOT FIRE')}")

    hdr("The composition check — the model's reason-for-move mix vs CPS")
    print(f"CPS 2023, renters: non-housing share of moves = {CPS:.4f}")
    print(f"{'var':5} {'reg':5} {'exo/left':>9} {'vs CPS':>9}")
    for r in sel("j1", spec="registered"):
        print(f"{r['variant']:5} {r['regime']:5} {r['exo_share']:9.4f} "
              f"{r['exo_share'] - CPS:+9.4f}")

    hdr("S3 — composition-anchored p_exo (level free, CPS mix imposed)")
    print(f"{'p_exo':>8} {'reg':5} {'retention':>10} {'turnover':>9} "
          f"{'exo/left':>9} {'succ':>7}")
    for r in sorted(sel("j1sweep"), key=lambda x: (x["regime"], x["p_exo"])):
        print(f"{r['p_exo']:8.4f} {r['regime']:5} {r['retention']:10.4f} "
              f"{r['turnover']:9.4f} {r['exo_share']:9.4f} "
              f"{r['success_rate']:7.4f}")
    for regime in ("loss", "gain"):
        rs = sorted([r for r in sel("j1sweep") if r["regime"] == regime],
                    key=lambda x: x["exo_share"])
        xs = [r["exo_share"] for r in rs]
        if min(xs) <= CPS <= max(xs):
            pe = float(np.interp(CPS, xs, [r["p_exo"] for r in rs]))
            ret = float(np.interp(CPS, xs, [r["retention"] for r in rs]))
            print(f"  {regime}: S3 p_exo = {pe:.4f}  ->  retention {ret:.4f}  "
                  f"{'INSIDE' if K31_LO <= ret <= K31_HI else 'OUTSIDE'} the "
                  f"K31 band")
        else:
            print(f"  {regime}: CPS composition {CPS:.4f} is not reachable "
                  f"on the swept grid (range {min(xs):.4f}-{max(xs):.4f})")
    print("\n  and the p_exo that reproduces observed retention (~0.573):")
    for regime in ("loss", "gain"):
        rs = sorted([r for r in sel("j1sweep") if r["regime"] == regime],
                    key=lambda x: x["retention"])
        xs = [r["retention"] for r in rs]
        if min(xs) <= 0.573 <= max(xs):
            print(f"    {regime}: p_exo = "
                  f"{float(np.interp(0.573, xs, [r['p_exo'] for r in rs])):.4f}"
                  f"   (CPS-sourced is {META['p_exo_cps_nonhousing']:.4f})")
        else:
            print(f"    {regime}: not reachable on the grid "
                  f"({min(xs):.4f}-{max(xs):.4f})")


def j1m():
    rows = sel("j1m")
    if not rows:
        return
    hdr("JOB 3 — the market channel: GATE 3 V10, and K21")
    print(f"{'var':4} {'retention':>10} {'vacancy':>8} {'renew g':>9} "
          f"{'newlet g':>9} {'rent gap':>9} {'move gain':>10} {'wins':>7}")
    for r in rows:
        print(f"{r['variant']:4} {r['retention']:10.4f} {r['vacancy']:8.4f} "
              f"{r['renew_growth']:+9.4f} {r['newlet_growth']:+9.4f} "
              f"{r['rent_gap']:+9.0f} {r['move_gain']:+10.0f} "
              f"{r['move_gain_share']:7.4f}")
    print("\nV10 — market retention vs Phase 1's, same p_exo (bar: within 5pp)")
    for r in rows:
        p1 = one("j1", spec="registered", variant=r["variant"], regime="gain")
        gap = abs(r["retention"] - p1["retention"])
        print(f"  {r['variant']:4}: market {r['retention']:.4f} vs phase1 "
              f"{p1['retention']:.4f}  gap {gap*100:5.2f}pp  "
              f"{'PASS' if gap <= 0.05 else 'FAIL'}")
    print("\nK21 quartiles — net annual gain from moving, by moving-cost quartile")
    print(f"{'var':4} " + " ".join(f"{'q'+str(q):>18}" for q in range(4)))
    for r in rows:
        cells = [f"{r[f'move_gain_q{q}']:+8.0f}/{100*r[f'move_share_q{q}']:5.1f}%"
                 for q in range(4)]
        print(f"{r['variant']:4} " + " ".join(f"{c:>18}" for c in cells))
    print("  (bar: K21 fires on RAW annual saving >= $480; raw = rent gap)")
    for r in rows:
        print(f"  {r['variant']:4}: raw {r['rent_gap']:+.0f} vs $480 -> "
              f"{'FIRES' if r['rent_gap'] >= 480 else 'does NOT fire'}")


def j1a7():
    rows = sel("j1a7")
    if not rows:
        return
    hdr("JOB 3 — A7's 'you can have either observed fact, not both'")
    print("A7 reported (registered spec, gain): capped push +10.73% with "
          "retention 60.1%;\nfree push +13.81% with retention 56.1%. Both "
          "facts were FITTED. Re-run with\nthe non-rent half of turnover "
          "sourced:")
    print(f"\n{'var':4} {'cap':7} {'reg':5} {'push':>8} {'retention':>10} "
          f"{'r/mkt':>7} {'succ':>7}")
    for r in rows:
        print(f"{r['variant']:4} {r['cap']:7} {r['regime']:5} "
              f"{r['mean_offer_push']:+8.4f} {r['retention']:10.4f} "
              f"{r['rent_ratio']:7.4f} {r['success_rate']:7.4f}")
    print("\n  the trade-off, stated as A7 stated it (push target +10.7%, "
          "retention target ~57.3%):")
    for v in ("F", "S1", "S2"):
        for regime in ("loss", "gain"):
            try:
                c = one("j1a7", variant=v, cap="capped", regime=regime)
                f = one("j1a7", variant=v, cap="free", regime=regime)
            except AssertionError:
                continue
            print(f"  {v:3} {regime:5}: capped push {c['mean_offer_push']:+.4f}"
                  f" ret {c['retention']:.4f} | free push "
                  f"{f['mean_offer_push']:+.4f} ret {f['retention']:.4f}"
                  f"  | cap costs {100*(f['retention']-c['retention']):+.2f}pp "
                  f"retention for {100*(c['mean_offer_push']-f['mean_offer_push']):+.2f}pp push")


def j1k18():
    rows = sel("j1k18")
    if not rows:
        return
    hdr("JOB 3 — K18: mutual engines destroy value")
    print("Fires only if T/L has BOTH higher turnover than N/N AND lower joint "
          "surplus.")
    print(f"\n{'var':4} {'reg':5} {'cell':5} {'turnover':>9} {'joint':>9} "
          f"{'tenant':>9} {'landlord':>9}")
    for r in rows:
        print(f"{r['variant']:4} {r['regime']:5} {r['cell']:5} "
              f"{r['turnover']:9.4f} {r['joint_phy']:9.0f} "
              f"{r['tenant_phy']:9.0f} {r['landlord_phy']:9.0f}")
    for v in ("F", "S1"):
        for regime in ("loss", "gain"):
            try:
                nn = one("j1k18", variant=v, cell="N/N", regime=regime)
                tl = one("j1k18", variant=v, cell="T/L", regime=regime)
            except AssertionError:
                continue
            up = tl["turnover"] > nn["turnover"]
            dn = tl["joint_phy"] < nn["joint_phy"]
            print(f"  {v:3} {regime:5}: turnover {nn['turnover']:.4f} -> "
                  f"{tl['turnover']:.4f} ({'UP' if up else 'down'}), joint "
                  f"{nn['joint_phy']:.0f} -> {tl['joint_phy']:.0f} "
                  f"({'DOWN' if dn else 'up'})  -> "
                  f"{'FIRES' if (up and dn) else 'does NOT fire'}")


def j2():
    rows = sel("j2rho")
    if not rows:
        return
    hdr("JOB 2 — the counter rate, and the one knob it depends on")
    print("PREREG-A11 §A11.5.1: only rho = belief0 / courage_med enters the ask "
          "rule.\nTraced from BOTH ends; if they lie on one curve, the study "
          "carried one degree\nof freedom under two names.\n")
    for regime in ("loss", "gain"):
        print(f"--- {regime} ---")
        print(f"{'swept':8} {'belief0':>8} {'courage':>9} {'rho':>10} "
              f"{'counter':>9} {'+-':>7} {'belief':>8} {'succ':>7}")
        for r in sorted([x for x in rows if x["regime"] == regime],
                        key=lambda x: x["rho"]):
            print(f"{r['arm']:8} {r['belief0']:8.4f} {r['courage_med']:9.4f} "
                  f"{r['rho']:10.3f} {r['counter_rate']:9.4f} "
                  f"{r['counter_se']:7.4f} {r['belief']:8.4f} "
                  f"{r['success_rate']:7.4f}")

    hdr("K32 — the free counter rate")
    rho_s = META["rho_sourced"]
    print(f"Fires if the counter rate at the SOURCED ratio "
          f"rho* = {rho_s:.2f} lands outside {K32_LO:.2f}-{K32_HI:.2f}.")
    fired = []
    for regime in ("loss", "gain"):
        m = [r for r in rows if r["regime"] == regime
             and abs(r["rho"] - rho_s) < 1e-6]
        if not m:
            continue
        r = m[0]
        f = not (K32_LO <= r["counter_rate"] <= K32_HI)
        fired.append(f)
        base = [x for x in rows if x["regime"] == regime
                and abs(x["rho"] - 0.10 / 0.18) < 1e-3]
        b = base[0]["counter_rate"] if base else float("nan")
        print(f"  {regime:5}: shipped rho 0.556 -> {b:.4f} | sourced rho "
              f"{rho_s:.2f} -> {r['counter_rate']:.4f} +- "
              f"{r['counter_se']:.4f}   {'FIRES' if f else 'does NOT fire'}")
    print(f"  VERDICT: K32 {'FIRED' if all(fired) and fired else 'DID NOT FIRE'}")

    hdr("The identified set — is rho identified by this model at all?")
    for regime in ("loss", "gain"):
        rs = sorted([x for x in rows if x["regime"] == regime],
                    key=lambda x: x["rho"])
        cr = [x["counter_rate"] for x in rs]
        print(f"  {regime}: counter rate spans {min(cr):.4f} to {max(cr):.4f} "
              f"over rho {rs[0]['rho']:.3f} to {rs[-1]['rho']:.1f}")
        # interpolate on log(rho): the curve is a lognormal CDF in log rho
        lr = np.log([x["rho"] for x in rs])
        cr_ = np.array(cr)
        ordr = np.argsort(cr_)
        lo = float(np.exp(np.interp(K32_LO, cr_[ordr], lr[ordr])))
        hi = float(np.exp(np.interp(K32_HI, cr_[ordr], lr[ordr])))
        at39 = float(np.exp(np.interp(0.39, cr_[ordr], lr[ordr])))
        print(f"     rho consistent with the observed 29-49%: "
              f"{lo:.3f} to {hi:.3f}   (rho hitting 39% exactly: {at39:.3f})")
        print(f"     = at an uninformative prior (0.50), courage_med "
              f"{0.50/hi:.4f} to {0.50/lo:.4f} months "
              f"(${0.50/hi*2000:.0f}-${0.50/lo*2000:.0f}) "
              f"= {0.50/hi*2000/36.06:.1f} to {0.50/lo*2000/36.06:.1f} "
              f"hours of the ACS renter wage to send one email")
        print(f"     at 39% exactly: courage_med {0.50/at39:.4f} months "
              f"(${0.50/at39*2000:.0f}) = {0.50/at39*2000/36.06:.1f} hours")
        # elasticity: pp per doubling of rho, near the sourced point
        near = [x for x in rs if x["rho"] >= 1.0]
        if len(near) >= 2:
            d = [(np.log2(b["rho"] / a["rho"]),
                  b["counter_rate"] - a["counter_rate"])
                 for a, b in zip(near, near[1:]) if b["rho"] > a["rho"]]
            if d:
                el = float(np.mean([y / x for x, y in d if x > 0]))
                print(f"     elasticity above rho=1: {100*el:+.2f}pp per "
                      f"doubling of rho")

    sg = sel("j2sig")
    if sg:
        print("\n  courage_sigma robustness at the sourced ratio:")
        for r in sg:
            print(f"    {r['regime']:5} csig {r['csig']:.1f} -> counter "
                  f"{r['counter_rate']:.4f}")


def j2table():
    rows = sel("j2table")
    if not rows:
        return
    hdr("JOB 3 — Phase 2 §7 arm F, shipped ratio vs sourced ratio")
    print(f"{'tag':8} {'type':14} {'reg':5} {'bc':3} {'counter':>8} "
          f"{'belief':>7} {'scale':>6} {'succ':>7} {'total':>8} {'askers':>8} "
          f"{'non':>8} {'cash':>8}")
    for r in rows:
        print(f"{r['tag']:8} {r['type']:14} {r['regime']:5} "
              f"{int(r['broadcast']):3} {r['counter_rate']:8.4f} "
              f"{r['belief']:7.4f} {r['ask_scale']:6.3f} "
              f"{r['success_rate']:7.4f} {r['surplus_pcy']:8.0f} "
              f"{r['surplus_asker']:8.0f} {r['surplus_nonasker']:8.0f} "
              f"{r['station_cash_phy']:8.0f}")

    hdr("K7 — our product is net-harmful at scale (THE LIVE PAGE CLAIM)")
    print("Fires if under BROADCAST + ADAPTIVE INSTITUTIONAL total crab surplus "
          "is LOWER\nthan under no-broadcast by >= $240. The page states the "
          "DIRECTION only.")
    for tag in ("shipped", "sourced"):
        for regime in ("loss", "gain"):
            try:
                off = one("j2table", tag=tag, type="inst-adaptive",
                          regime=regime, broadcast=False)
                on = one("j2table", tag=tag, type="inst-adaptive",
                         regime=regime, broadcast=True)
            except AssertionError:
                continue
            harm = off["surplus_pcy"] - on["surplus_pcy"]
            sem = float(np.hypot(off["se_total"], on["se_total"]))
            print(f"  {tag:8} {regime:5}: off {off['surplus_pcy']:.0f} -> on "
                  f"{on['surplus_pcy']:.0f}   harm {harm:+.0f} +- {sem:.0f}  "
                  f"({'HELPED' if harm < 0 else 'HARMED'})  "
                  f"{'FIRES' if harm >= 240 else 'does NOT fire'}")

    hdr("K8 — broadcast only helps the loud")
    print("Fires if under broadcast, non-asker surplus FALLS while asker "
          "surplus RISES.")
    print(f"{'tag':8} {'type':14} {'reg':5} {'d askers':>10} {'d non':>10} "
          f"{'fires':>7}")
    for tag in ("shipped", "sourced"):
        for r in [x for x in rows if x["tag"] == tag and x["broadcast"]]:
            try:
                off = one("j2table", tag=tag, type=r["type"],
                          regime=r["regime"], broadcast=False)
            except AssertionError:
                continue
            da = r["surplus_asker"] - off["surplus_asker"]
            dn = r["surplus_nonasker"] - off["surplus_nonasker"]
            sen = float(np.hypot(r["se_nonasker"], off["se_nonasker"]))
            fires = da > 0 and dn < 0
            print(f"{tag:8} {r['type']:14} {r['regime']:5} {da:+10.0f} "
                  f"{dn:+7.0f}+-{sen:<4.0f} {'YES' if fires else 'no':>7}")


if __name__ == "__main__":
    j1()
    j1m()
    j1a7()
    j1k18()
    j2()
    j2table()
