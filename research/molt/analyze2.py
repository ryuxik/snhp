"""Molt Season v2 — read K8..K13 off the results JSON (PREREG AMENDMENT 1 §A1.8).

    python research/molt/analyze2.py [results_v2_main.json]
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(_HERE, "results_v2_main.json")
    r = json.load(open(path))
    S = r["mean_salary"]
    BAR = 0.02 * S
    print(f"mean salary ${S:,.0f}   bar (2%) ${BAR:,.0f}   "
          f"tau_verifiable={r['tau_verifiable']:.4f}")

    for cred in ("verifiable", "unverifiable"):
        print("\n" + "=" * 86)
        print(f"CREDIBILITY: {cred.upper()}")
        print("=" * 86)
        on = r[cred]["clock_on"]
        off = r[cred]["clock_off"]
        m = on["means"]
        print(f"n = {m['A_sign']['n']:,} crab-seasons per arm\n")

        slow = [a for a in m if a.startswith("B|")]
        best_first = [a for a in slow if a.endswith("|best_first")]

        # ---- the arms, headline table
        print(f"{'arm':38s}{'crab $':>10}{'works $':>11}{'joint $':>11}"
              f"{'days':>7}{'left%':>7}{'conc $':>9}")
        for a in ("A_sign", "D_sitting_crab", "E_sitting_works"):
            _row(a, m[a])
        # the strongest slow opponent, by joint
        rank = sorted(best_first, key=lambda a: -(m[a]["joint"]))
        for a in rank[:3]:
            _row(a, m[a])
        print("  ... weakest three:")
        for a in rank[-3:]:
            _row(a, m[a])

        # ---- K8
        champ = rank[0]
        k8_on = on["paired"][f"D_sitting_crab-{champ}"]
        k8_off = off["paired"][f"D_sitting_crab-{champ}"]
        fired = k8_off["joint"] < BAR
        print(f"\nK8  THE MONEY STORY — engine vs the best archetype "
              f"({champ.split('|')[1]}, best_first)")
        print(f"    clock ON   joint {k8_on['joint']:+9,.0f} ±{k8_on['joint_se']:,.0f}"
              f"   crab {k8_on['crab']:+8,.0f}   works {k8_on['works']:+9,.0f}"
              f"   days {k8_on['days']:+7.1f}")
        print(f"    clock OFF  joint {k8_off['joint']:+9,.0f} ±{k8_off['joint_se']:,.0f}"
              f"   crab {k8_off['crab']:+8,.0f}   works {k8_off['works']:+9,.0f}")
        print(f"    -> {'FIRES — the money story is the clock' if fired else 'does not fire'}"
              f"  (bar {BAR:,.0f})")

        # ---- K9
        print("\nK9  THE SIZE OF MY THUMB — money_first vs best_first, same archetype")
        worst = 0.0
        for a in r[cred]["clock_on"]["means"]:
            pass
        for arch in r["reported_archetypes"]:
            mf, bf = f"B|{arch}|money_first", f"B|{arch}|best_first"
            if mf not in m or bf not in m:
                continue
            gap_conc = m[mf]["concession"] - m[bf]["concession"]
            gap_crab = m[bf]["crab"] - m[mf]["crab"]
            worst = max(worst, abs(gap_conc), abs(gap_crab))
            print(f"    {arch:20s} concession {m[mf]['concession']:8,.0f} -> "
                  f"{m[bf]['concession']:8,.0f} ({gap_conc:+7,.0f})   "
                  f"crab {m[mf]['crab']:8,.0f} -> {m[bf]['crab']:8,.0f} "
                  f"({gap_crab:+7,.0f})")
        print(f"    largest ordering effect {worst:,.0f} vs bar {BAR:,.0f} -> "
              f"{'FIRES — the v1 figure was an agenda artifact' if worst > BAR else 'does not fire — the agenda objection is answered'}")

        # ---- K10
        k10 = on["paired"]["K10_disclose-K10_silent"]
        fired = k10["crab"] < BAR
        print(f"\nK10 DOES DISCLOSURE PAY — same crab, forced to show vs forced silent")
        print(f"    crab {k10['crab']:+8,.0f} ±{k10['crab_se']:,.0f}   "
              f"works {k10['works']:+9,.0f}   left {100*k10['left']:+.1f}pp")
        print(f"    -> {'FIRES — showing the letter is worth nothing' if fired else 'does not fire — showing the letter pays'}")

        # ---- K11
        print(f"\nK11 DID THE MATCH VALUE DO ANYTHING — rank corr(match, concession) "
              f"= {on['k11_rank_corr']:.3f} on n={on['k11_n']:,}")
        print(f"    -> {'FIRES — firm-specific value is inert' if abs(on['k11_rank_corr']) < 0.15 else 'does not fire'}")

        # ---- K12
        adv = {a: on["paired"][f"D_sitting_crab-{a}"]["joint"] for a in best_first}
        lo_a = min(adv, key=lambda a: adv[a])
        hi_a = max(adv, key=lambda a: adv[a])
        ratio = adv[hi_a] / adv[lo_a] if adv[lo_a] > 0 else float("inf")
        print(f"\nK12 ARCHETYPE DEPENDENCE — engine advantage across all "
              f"{len(best_first)} archetypes")
        print(f"    weakest  {lo_a.split('|')[1]:22s} {adv[lo_a]:+9,.0f}")
        print(f"    strongest{hi_a.split('|')[1]:>22s} {adv[hi_a]:+9,.0f}   ratio {ratio:.2f}x")
        print(f"    -> {'FIRES — report per archetype, no single headline' if ratio > 2.0 else 'does not fire'}")

        # ---- K13
        print("\nK13 THE SPLIT")
        for a in ("D_sitting_crab", "E_sitting_works"):
            pr = on["paired"][f"D_sitting_crab-{champ}"] if a == "D_sitting_crab" \
                else paired_from(on, a, champ)
            j = pr["joint"]
            if abs(j) > 1:
                print(f"    {a:18s} joint {j:+9,.0f} = crab {pr['crab']:+8,.0f} "
                      f"({100*pr['crab']/j:5.1f}%) + works {pr['works']:+9,.0f} "
                      f"({100*pr['works']/j:5.1f}%)")

    # cross-regime: what is the letter worth?
    print("\n" + "=" * 86)
    print("THE PRICE OF THE OFFER LETTER (verifiable minus unverifiable)")
    print("=" * 86)
    for arm in ("A_sign", "D_sitting_crab"):
        v = r["verifiable"]["clock_on"]["means"][arm]
        u = r["unverifiable"]["clock_on"]["means"][arm]
        print(f"  {arm:18s} crab {v['crab'] - u['crab']:+9,.0f}   "
              f"works {v['works'] - u['works']:+9,.0f}   "
              f"left {100*(v['left'] - u['left']):+5.1f}pp")


def paired_from(on, a, b):
    # E vs the champion isn't precomputed; approximate from means-differences
    m = on["means"]
    return {"joint": m[a]["joint"] - m[b]["joint"],
            "crab": m[a]["crab"] - m[b]["crab"],
            "works": m[a]["works"] - m[b]["works"]}


def _row(a, d):
    label = a if not a.startswith("B|") else \
        "B " + a.split("|")[1] + " /" + a.split("|")[2][:4]
    print(f"{label:38s}{d['crab']:>10,.0f}{d['works']:>11,.0f}{d['joint']:>11,.0f}"
          f"{d['days']:>7.1f}{100*d['left']:>7.1f}{d['concession']:>9,.0f}")


if __name__ == "__main__":
    main()
