"""Molt Season — read the kills off the results JSON.

    python research/molt/analyze.py [results_main.json]

Every kill in PREREG §4 is evaluated here in code, against the registered bar of
2% of mean salary, so the verdicts cannot drift while a document is written.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

ARM_LABEL = {"A_sign": "A SIGN IT", "B_slow": "B SLOW TALKS",
             "C_slow_engine": "C SLOW ENGINE", "D_sitting_crab": "D ONE SITTING",
             "E_sitting_works": "E WORKS HOLDS IT", "F_sitting_both": "F BOTH"}


def money(x):
    return f"{x:>10,.0f}"


def table(rep, cond):
    m = rep[cond]["means"]
    print(f"\n=== {cond}  (n={m['A_sign']['n']} crab-seasons/arm) ===")
    print(f"{'arm':16s}{'crab $':>10}{'works $':>11}{'joint $':>11}"
          f"{'days':>7}{'mtgs':>6}{'left%':>7}{'base%':>7}{'title%':>7}"
          f"{'paid $':>10}")
    for a, lab in ARM_LABEL.items():
        r = m[a]
        print(f"{lab:16s}{money(r['crab'])}{money(r['works'])}{money(r['joint'])}"
              f"{r['days']:>7.1f}{r['meetings']:>6.2f}{100*r['left']:>7.1f}"
              f"{100*r['base_pct']:>7.2f}{100*r['title']:>7.1f}"
              f"{money(r['cash_paid'])}")


def diff_line(rep, cond, key):
    d = rep[cond]["paired"][key]
    return (f"  {key:34s} crab {d['crab']:+9,.0f} ±{d['crab_se']:,.0f}   "
            f"works {d['works']:+9,.0f} ±{d['works_se']:,.0f}   "
            f"joint {d['joint']:+9,.0f} ±{d['joint_se']:,.0f}   "
            f"days {d['days']:+7.1f}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(_HERE, "results_main.json")
    rep = json.load(open(path))
    S = rep["mean_salary"]
    BAR = 0.02 * S
    print(f"mean salary ${S:,.0f} — the registered bar is 2% = ${BAR:,.0f}")

    for cond in ("clock_on", "clock_off"):
        table(rep, cond)
        print("  paired differences (per crab-season):")
        for k in ("B_slow-A_sign", "D_sitting_crab-A_sign",
                  "D_sitting_crab-B_slow", "C_slow_engine-B_slow",
                  "D_sitting_crab-C_slow_engine", "E_sitting_works-B_slow",
                  "F_sitting_both-B_slow"):
            if k in rep[cond]["paired"]:
                print(diff_line(rep, cond, k))

    print("\n" + "=" * 78)
    print("KILL VERDICTS (PREREG §4)")
    print("=" * 78)
    on, off = rep["clock_on"]["paired"], rep["clock_off"]["paired"]
    onm, offm = rep["clock_on"]["means"], rep["clock_off"]["means"]

    k1 = off["D_sitting_crab-B_slow"]["joint"]
    fired = k1 < BAR
    print(f"K1 TAUTOLOGY   zero-clock joint D-B = {k1:+,.0f} vs bar {BAR:,.0f} "
          f"-> {'FIRES' if fired else 'does not fire'}")

    d = on["D_sitting_crab-B_slow"]
    fired = (d["crab"] < BAR) and (d["works"] < BAR)
    print(f"K2 NO-MONEY    clock-on D-B crab {d['crab']:+,.0f}, "
          f"works {d['works']:+,.0f} vs bar {BAR:,.0f} "
          f"-> {'FIRES' if fired else 'does not fire'}")

    k3 = on["D_sitting_crab-C_slow_engine"]["joint"]
    fired = abs(k3) < BAR
    print(f"K3 STRAWMAN    joint D-C = {k3:+,.0f} vs bar {BAR:,.0f} "
          f"-> {'FIRES' if fired else 'does not fire'}")

    print("K4 CAPTURE SPLIT (no direction registered):")
    for a in ("D_sitting_crab", "E_sitting_works", "F_sitting_both"):
        p = on[f"{a}-B_slow"]
        j = p["joint"]
        if abs(j) > 1e-9:
            print(f"   {ARM_LABEL[a]:16s} joint {j:+,.0f} = crab {p['crab']:+,.0f}"
                  f" ({100*p['crab']/j:5.1f}%) + works {p['works']:+,.0f}"
                  f" ({100*p['works']/j:5.1f}%)")
    f = on["F_sitting_both-B_slow"]
    if abs(f["joint"]) > 1e-9:
        sh = max(f["crab"], f["works"]) / f["joint"]
        who = "crab" if f["crab"] > f["works"] else "Works"
        note = "REWRITE the other side's copy" if sh > 0.70 else "no rewrite trigger"
        print(f"   -> in F the {who} takes {100*sh:.0f}%  ({note})")

    dag = 100 * (onm["D_sitting_crab"]["agreed"] - onm["B_slow"]["agreed"])
    dlv = 100 * (onm["D_sitting_crab"]["left"] - onm["B_slow"]["left"])
    fired = (dag < -3.0) or (dlv > 2.0)
    print(f"K5 SPEED COST  agreement D-B {dag:+.1f}pp, departures D-B {dlv:+.1f}pp "
          f"-> {'FIRES' if fired else 'does not fire'}")

    sw = rep.get("sweeps", {})
    if "dirichlet=4.0" in sw and "dirichlet=1.4" in sw:
        a = sw["dirichlet=1.4"]["paired"]["D_sitting_crab-C_slow_engine"]["joint"]
        b = sw["dirichlet=4.0"]["paired"]["D_sitting_crab-C_slow_engine"]["joint"]
        fired = not (b <= 0.5 * a)
        print(f"K6 HETEROGENEITY D-C joint at alpha=1.4 {a:+,.0f} -> "
              f"alpha=4.0 {b:+,.0f} ({100*b/a if a else float('nan'):.0f}% of it) "
              f"-> {'FIRES (mechanism unidentified)' if fired else 'does not fire'}")

    yb, yd = onm["B_slow"]["works"], onm["D_sitting_crab"]["works"]
    fired = yb > yd
    print(f"K7 COMPANY-LOSES works under B {yb:,.0f} vs under D {yd:,.0f} "
          f"-> {'FIRES (the Works profits from slowness)' if fired else 'does not fire'}")

    print("\n" + "=" * 78)
    print("PREDICTION CHECK (PREREG §5)")
    print("=" * 78)
    b, dd = onm["B_slow"], onm["D_sitting_crab"]
    print(f"P1 mis-allocated concession vs elapsed time, B - D:")
    print(f"   permanent base granted   {100*b['base_pct']:.2f}% -> "
          f"{100*dd['base_pct']:.2f}%   (cash paid {b['cash_paid']:,.0f} -> "
          f"{dd['cash_paid']:,.0f})")
    print(f"   concession cost to Works  {b['concession']:,.0f} -> {dd['concession']:,.0f}"
          f"   = {b['concession']-dd['concession']:+,.0f}")
    print(f"   manager hours + distraction + replacement "
          f"{b['mgr']+b['distraction']+b['replacement']:,.0f} -> "
          f"{dd['mgr']+dd['distraction']+dd['replacement']:,.0f}"
          f"   = {(b['mgr']+b['distraction']+b['replacement'])-(dd['mgr']+dd['distraction']+dd['replacement']):+,.0f}")
    print(f"   crab ends up             {b['crab']:,.0f} -> {dd['crab']:,.0f}")

    if sw:
        print("\n" + "=" * 78)
        print("SWEEPS (seed 7) — joint D-B, then who captures it in F")
        print("=" * 78)
        for k, v in sw.items():
            p = v["paired"]["D_sitting_crab-B_slow"]
            f = v["paired"]["F_sitting_both-B_slow"]
            share = (100 * f["works"] / f["joint"]) if abs(f["joint"]) > 1 else float("nan")
            print(f"  {k:22s} joint {p['joint']:+9,.0f}  crab {p['crab']:+9,.0f}"
                  f"  works {p['works']:+9,.0f}   works share in F {share:5.0f}%")


if __name__ == "__main__":
    main()
