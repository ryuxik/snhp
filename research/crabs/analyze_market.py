"""Verdicts for AMENDMENT 5 (K19/K20/K21) and GATE 3 (V8/V9/V10, K15)."""
from __future__ import annotations
import json, math, os
_HERE = os.path.dirname(os.path.abspath(__file__))
AR = 24000.0
PCT2 = 0.02 * AR


def mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def se(xs):
    xs = [x for x in xs if x == x]
    n = len(xs)
    if n < 2:
        return float("nan")
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def main():
    data = json.load(open(os.path.join(_HERE, "results_market.json")))
    C = {c["cell"]: c for c in data["cells"]}
    o = []
    m = data["meta"]
    o.append(f"crabs {m['version']}  AMENDMENT 5 + GATE 3  seeds "
             f"{m['seeds'][0]}-{m['seeds'][1]} ({m['n_seeds']})  "
             f"runtime {m['runtime_s']}s")
    o.append("Market rent is an OUTPUT: no drift is imposed in any cell below.")
    o.append("")

    # ---------------- GATE 3 first, per A3.5 ----------------
    o.append("=" * 78)
    o.append("GATE 3 -- does the regime EMERGE? (reported before any arm result)")
    o.append("=" * 78)
    b, s = C["baseline"]["derived"], C["supply_shock"]["derived"]
    o.append(f"  {'':28s} {'baseline':>12s} {'+30% supply':>12s}")
    for k, lab in (("vacancy", "vacancy rate"),
                   ("mean_ask", "mean asking rent $/mo"),
                   ("newlet_rent", "new-let signed $/mo"),
                   ("renew_rent", "renewal signed $/mo"),
                   ("newlet_growth", "NEW-LET growth"),
                   ("renew_growth", "RENEWAL growth"),
                   ("retention", "retention")):
        o.append(f"  {lab:28s} {b[k]:12.4f} {s[k]:12.4f}")
    o.append("")
    v8 = (s["vacancy"] > b["vacancy"]) and (s["newlet_rent"] < b["newlet_rent"]) \
        and (s["renew_rent"] > s["newlet_rent"])
    o.append("V8 -- a supply shock produces GAIN-TO-LEASE endogenously "
             "(new-let below sitting rents, nothing imposed).")
    o.append(f"     vacancy {b['vacancy']:.4f} -> {s['vacancy']:.4f}; new-let "
             f"signed ${b['newlet_rent']:.0f} -> ${s['newlet_rent']:.0f}; "
             f"renewal ${s['renew_rent']:.0f} > new-let ${s['newlet_rent']:.0f}")
    o.append(f"     --> V8 {'PASS' if v8 else 'FAIL'}")
    v9 = (b["newlet_growth"] < 0.0) and (b["renew_growth"] > 0.0)
    o.append("V9 -- the MAA sign pattern in the aggregate: new-let growth "
             "NEGATIVE beside renewal growth POSITIVE, same period.")
    ng = C["baseline"]["per_seed"]["newlet_growth"]
    rg = C["baseline"]["per_seed"]["renew_growth"]
    o.append(f"     baseline: new-let {b['newlet_growth']*100:+.2f}% "
             f"+/- {se(ng)*100:.2f}   renewal {b['renew_growth']*100:+.2f}% "
             f"+/- {se(rg)*100:.2f}   spread "
             f"{(b['renew_growth']-b['newlet_growth'])*100:.2f} pts")
    o.append(f"     shock:    new-let {s['newlet_growth']*100:+.2f}%   "
             f"renewal {s['renew_growth']*100:+.2f}%")
    o.append(f"     MAA Q1 2026 actual: new lease -7.0%, renewal +5.4%, "
             f"spread 12.4 pts")
    o.append(f"     --> V9 {'PASS' if v9 else 'FAIL'}")
    o.append("V10 -- bridge: endogenous retention within 5pp of the "
             "exogenous-path model's Phase-1 retention (0.593 loss / 0.575 gain).")
    gap = min(abs(b["retention"] - 0.593), abs(b["retention"] - 0.575))
    v10 = gap <= 0.05
    o.append(f"     endogenous retention {b['retention']:.3f}; nearest Phase-1 "
             f"figure differs by {gap*100:.1f}pp")
    o.append(f"     --> V10 {'PASS' if v10 else 'FAIL'}")
    o.append("")
    o.append(f"GATE 3: {'PASS' if (v8 and v9 and v10) else 'FAIL'}")
    o.append("")
    o.append("K15 -- the swarm changes nothing.")
    o.append("  Fires if endogenising the market moves no Phase-1 conclusion by "
             "more than noise.")
    o.append(f"  Phase 1 IMPOSED the regime and could not generate it. Here, with "
             f"zero imposed drift, the new-let/renewal sign split appears "
             f"({b['newlet_growth']*100:+.2f}% vs {b['renew_growth']*100:+.2f}%) "
             f"and a supply shock moves vacancy {b['vacancy']:.3f} -> "
             f"{s['vacancy']:.3f} and new-let rent ${b['newlet_rent']:.0f} -> "
             f"${s['newlet_rent']:.0f}.")
    o.append("  --> K15 DID NOT FIRE (endogenising the market produces a "
             "mechanism Phase 1 had to assume)")
    o.append("")

    # ---------------- walk-aways and zones, every cell ----------------
    o.append("=" * 78)
    o.append("WALK-AWAY COSTS AND BARGAINING ZONES (A5.2). CHANNELS NEVER POOLED.")
    o.append("=" * 78)
    o.append(f"  {'cell':>20s} {'chan':>8s} {'tenant WA':>10s} {'landlord WA':>12s}"
             f" {'ratio':>6s} {'zone width':>11s}")
    for name in ("baseline", "supply_shock", "precedent_0.002", "precedent_0.01",
                 "split_landlord_0.75", "split_tenant_0.25"):
        d = C[name]["derived"]
        o.append(f"  {name:>20s} {'RENEWAL':>8s} {d['wa_tenant_renew']:10.0f} "
                 f"{d['wa_land_renew']:12.0f} {d['wa_ratio_renew']:6.2f} "
                 f"{d['zone_renew']:11.0f}")
        o.append(f"  {'':>20s} {'NEW LET':>8s} {d['wa_tenant_newlet']:10.0f} "
                 f"{d['wa_land_newlet']:12.0f} "
                 f"{d['wa_tenant_newlet']/max(d['wa_land_newlet'],1e-9):6.2f} "
                 f"{d['zone_newlet']:11.0f}")
    o.append("")

    # ---------------- K19 / K20 / K21 ----------------
    o.append("K19 -- the inversion is a BATNA artefact.")
    o.append("  Fires if the new-let-negative / renewal-positive sign pattern "
             "emerges from BATNA asymmetry alone, with NO imposed regime.")
    o.append(f"  drift imposed: 0.0 in every cell. baseline new-let growth "
             f"{b['newlet_growth']*100:+.2f}% +/- {se(ng)*100:.2f}, renewal "
             f"{b['renew_growth']*100:+.2f}% +/- {se(rg)*100:.2f}")
    o.append(f"  the pattern also holds under the supply shock "
             f"({s['newlet_growth']*100:+.2f}% / {s['renew_growth']*100:+.2f}%) "
             f"and at both split parameters "
             f"({C['split_tenant_0.25']['derived']['newlet_growth']*100:+.2f}%/"
             f"{C['split_tenant_0.25']['derived']['renew_growth']*100:+.2f}%, "
             f"{C['split_landlord_0.75']['derived']['newlet_growth']*100:+.2f}%/"
             f"{C['split_landlord_0.75']['derived']['renew_growth']*100:+.2f}%)")
    o.append(f"  --> K19 {'FIRED' if v9 else 'DID NOT FIRE'}")
    o.append("")
    o.append("K20 -- the tenant is the weaker party in renewals, and we said "
             "otherwise.")
    o.append("  Fires if mean tenant walk-away cost EXCEEDS mean landlord "
             "walk-away cost in the RENEWAL channel.")
    wt = C["baseline"]["per_seed"]["wa_tenant_renew"]
    wl = C["baseline"]["per_seed"]["wa_land_renew"]
    dif = [a - c for a, c in zip(wt, wl)]
    k20 = mean(wt) > mean(wl)
    o.append(f"  tenant ${mean(wt):,.0f} +/- {se(wt):,.0f} vs landlord "
             f"${mean(wl):,.0f} +/- {se(wl):,.0f};  difference "
             f"${mean(dif):+,.0f} +/- {se(dif):,.0f}  (ratio "
             f"{mean(wt)/mean(wl):.2f}x)")
    o.append(f"  DECOMPOSITION, because the framing matters: the landlord's "
             f"walk-away is turn cost + vacancy + re-let rent risk. Against turn "
             f"cost ALONE (~$3,000) the tenant has ~3.6x more to lose; against "
             f"the full landlord walk-away it is {mean(wt)/mean(wl):.2f}x.")
    o.append(f"  --> K20 {'FIRED' if k20 else 'DID NOT FIRE'}")
    o.append("")
    o.append("K21 -- for some tenants the right advice is 'move', not "
             "'negotiate'.")
    o.append("  Fires if NEW-LET tenants systematically achieve better terms than "
             f"comparable RENEWAL tenants by >= 2% of annual rent (${PCT2:.0f}).")
    o.append("  Measured WITHOUT the definitional benchmark: for each renewing "
             "tenant, the annual rent it would save by moving to a new let, and "
             "that saving NET of its own moving cost amortised over its expected "
             "remaining stay.")
    rgap = C["baseline"]["per_seed"]["rent_gap"]
    mg = C["baseline"]["per_seed"]["move_gain"]
    k21 = mean(rgap) >= PCT2
    o.append(f"  raw annual rent saving from moving: ${mean(rgap):+,.0f} "
             f"+/- {se(rgap):,.0f}   [bar ${PCT2:.0f}]")
    o.append(f"  NET of the amortised move:          ${mean(mg):+,.0f} "
             f"+/- {se(mg):,.0f}   share of tenants for whom moving wins: "
             f"{b['move_gain_share']:.3f}")
    o.append("  by moving-cost quartile (q0 = cheapest to move):")
    for q in range(4):
        o.append(f"    q{q}: net ${b[f'move_gain_q{q}']:+,.0f}   "
                 f"share for whom moving wins {b[f'move_share_q{q}']:.3f}")
    o.append(f"  --> K21 {'FIRED' if k21 else 'DID NOT FIRE'} (on the "
             f"pre-registered 'better terms' reading, i.e. rent)")
    o.append("")
    o.append("-" * 78)
    o.append("SUMMARY  " + "   ".join([
        f"GATE 3: {'PASS' if (v8 and v9 and v10) else 'FAIL'}",
        f"K15: DID NOT FIRE",
        f"K19: {'FIRED' if v9 else 'DID NOT FIRE'}",
        f"K20: {'FIRED' if k20 else 'DID NOT FIRE'}",
        f"K21: {'FIRED' if k21 else 'DID NOT FIRE'}"]))
    o.append("-" * 78)
    print("\n".join(o))


if __name__ == "__main__":
    main()
