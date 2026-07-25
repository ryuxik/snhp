"""Molt Season v3 — read K14..K18 off the results JSON (AMENDMENT 2 §A2.5).

    python research/molt/analyze3.py [results_v3_main.json]
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
V2_EQUAL_SPEED = 3837          # the figure K14 is measured against


def champ(reg):
    m = reg["clock_on"]["means"]
    bf = [a for a in m if a.endswith("|best_first")]
    return max(bf, key=lambda a: m[a]["joint"])


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(_HERE, "results_v3_main.json")
    r = json.load(open(path))
    S = r["mean_salary"]
    BAR = 0.02 * S
    print(f"mean salary ${S:,.0f}   bar ${BAR:,.0f}   "
          f"K14 threshold ${V2_EQUAL_SPEED + BAR:,.0f} "
          f"(v2's ${V2_EQUAL_SPEED:,} + bar)")

    for cred in ("verifiable", "unverifiable"):
        reg = r[cred]
        on, off = reg["clock_on"], reg["clock_off"]
        m = on["means"]
        ch = champ(reg)
        print("\n" + "=" * 88)
        print(f"{cred.upper()}   n={m['A_sign']['n']:,}   best opponent: "
              f"{ch.split('|')[1]}")
        print("=" * 88)
        print(f"{'arm':26s}{'utility':>11}{'CASH':>11}{'works':>12}"
              f"{'joint':>12}{'days':>7}{'left%':>7}")
        for a in ("A_sign", ch, "D_sitting_crab", "E_sitting_works", "E_biased"):
            d = m[a]
            lab = a if not a.startswith("B|") else "B " + a.split("|")[1]
            print(f"{lab:26s}{d['crab']:>11,.0f}{d['cash']:>11,.0f}"
                  f"{d['works']:>12,.0f}{d['joint']:>12,.0f}{d['days']:>7.1f}"
                  f"{100*d['left']:>7.1f}")

        p_on = on["paired"][f"D_sitting_crab-{ch}"]
        p_off = off["paired"][f"D_sitting_crab-{ch}"]
        print(f"\n  engine - best archetype, clock ON : joint {p_on['joint']:+9,.0f}"
              f"  utility {p_on['crab']:+8,.0f}  CASH {p_on['cash']:+8,.0f}")
        print(f"  engine - best archetype, clock OFF: joint {p_off['joint']:+9,.0f}"
              f"  utility {p_off['crab']:+8,.0f}  CASH {p_off['cash']:+8,.0f}")

        if cred == "verifiable":
            fired = p_off["joint"] < V2_EQUAL_SPEED + BAR
            print(f"\nK14 DOES BUDGET STRUCTURE RESCUE LOGROLLING")
            print(f"    equal-speed joint {p_off['joint']:+,.0f} vs threshold "
                  f"{V2_EQUAL_SPEED + BAR:,.0f}  -> "
                  f"{'FIRES — logrolling tested properly and found small' if fired else 'does not fire — structure rescues it'}")

            fired15 = p_on["cash"] < 0
            print(f"\nK15 CASH, NOT UTILITY")
            print(f"    engine's effect on the crab's cash {p_on['cash']:+,.0f}"
                  f"  -> {'FIRES — lead with cash' if fired15 else 'does not fire'}")

            bstay = on["both_stay"].get("Split-the-Diff")
            if bstay:
                print(f"    both-stay (n={bstay['n']:,}): slow cash "
                      f"{bstay['slow']['cash']:,.0f} -> sitting "
                      f"{bstay['sitting']['cash']:,.0f} "
                      f"({bstay['sitting']['cash']-bstay['slow']['cash']:+,.0f})")
                print(f"    grants under the engine: title "
                      f"{100*bstay['sitting']['granted_title']:.0f}%  pto "
                      f"{100*bstay['sitting']['granted_pto']:.0f}%  berth "
                      f"{100*bstay['sitting']['granted_berth']:.0f}%  deepwater "
                      f"{100*bstay['sitting']['granted_deep']:.0f}%")
                ranked = sorted(
                    (("title", bstay["sitting"]["granted_title"]),
                     ("pto", bstay["sitting"]["granted_pto"]),
                     ("berth", bstay["sitting"]["granted_berth"]),
                     ("deepwater", bstay["sitting"]["granted_deep"])),
                    key=lambda kv: -kv[1])
                top2 = [k for k, _ in ranked[:2]]
                print(f"\nK18 DID PTO MATTER — top two non-cash grants: {top2}"
                      f"  -> {'does not fire' if 'pto' in top2 else 'FIRES — PTO was cosmetic'}")

            k17 = on["paired"]["E_biased-E_sitting_works"]
            fired17 = k17["cash"] < -BAR
            print(f"\nK17 WHO SETS THE EXCHANGE RATE — employer engine biased "
                  f"{r.get('employer_rate_bias', 1.5)}x")
            print(f"    crab's cash {k17['cash']:+,.0f}   utility {k17['crab']:+,.0f}"
                  f"   works {k17['works']:+,.0f}")
            print(f"    -> {'FIRES — a named risk on the demo' if fired17 else 'does not fire'}")

    # ---- K16 the break-even
    if "perk_sweep" in r:
        print("\n" + "=" * 88)
        print("K16 THE BREAK-EVEN (verifiable, seed 7) — engine minus best archetype")
        print("=" * 88)
        print(f"{'perk rate':>11}{'utility':>12}{'CASH':>12}{'joint':>12}"
              f"{'equal-speed joint':>20}")
        prev_rate, prev_u, be = None, None, None
        for k in sorted(r["perk_sweep"], key=float):
            reg = r["perk_sweep"][k]
            ch = champ(reg)
            po = reg["clock_on"]["paired"][f"D_sitting_crab-{ch}"]
            pf = reg["clock_off"]["paired"][f"D_sitting_crab-{ch}"]
            print(f"{float(k):>10.2f}x{po['crab']:>12,.0f}{po['cash']:>12,.0f}"
                  f"{po['joint']:>12,.0f}{pf['joint']:>20,.0f}")
            if prev_u is not None and prev_u < 0 <= po["crab"]:
                be = prev_rate + (float(k) - prev_rate) * (-prev_u) / (po["crab"] - prev_u)
            prev_rate, prev_u = float(k), po["crab"]
        if be is not None:
            print(f"\n    break-even perk rate ~ {be:.2f}x  -> "
                  f"{'FIRES — label the employee claim rate-dependent' if be > 0.75 else 'does not fire'}")
        else:
            print("\n    the crab's utility gain does not cross zero in the swept range")


if __name__ == "__main__":
    main()
