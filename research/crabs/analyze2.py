"""Phase 2 verdicts: landlord types (K5, K6), broadcast (K7, K8), and the
EXPLORATORY shock section.

    python research/crabs/analyze2.py
    python research/crabs/analyze2.py --shocks

MEDIUM is our invention with no empirical anchor; every line involving it says
so (AMENDMENT 1 §A1.4).
"""
from __future__ import annotations

import argparse
import json
import os

import math


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


def paired(a, b):
    """Paired difference under common random numbers -> mean, SE."""
    d = [x - y for x, y in zip(a, b) if x == x and y == y]
    return mean(d), se(d)

ANNUAL_RENT = 24000.0
PCT1 = 0.01 * ANNUAL_RENT
_HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = ("institutional", "medium", "mom")
LABEL = {"institutional": "INSTITUTIONAL (200 hab, full RM)",
         "medium": "MEDIUM (40 hab, heuristic) *INVENTED*",
         "mom": "MOM-AND-POP (5 hab, rarely raises)"}


def load(fn):
    with open(os.path.join(_HERE, fn)) as f:
        return json.load(f)


def find(cells, **kw):
    out = [c for c in cells
           if all((abs(c.get(k, -1e9) - v) < 1e-9
                   if isinstance(v, float) else c.get(k) == v)
                  for k, v in kw.items())]
    if len(out) != 1:
        raise KeyError(f"{kw} -> {len(out)}")
    return out[0]


def types_table(cells, out):
    out.append("=" * 78)
    out.append("PHASE 2 -- LANDLORD TYPES (AMENDMENT 1 §A1.1)")
    out.append("=" * 78)
    out.append("Arm D, 39% ranked askers. 'gain from countering' = asker surplus")
    out.append("minus non-asker surplus in the SAME cell, so composition is")
    out.append("random and the difference is causal. $/crab-year.")
    for regime in ("loss", "gain"):
        out.append("")
        out.append(f"  {regime.upper()}-TO-LEASE")
        out.append(f"    {'type':>34s} {'gain':>7s} {'succ':>6s} {'reten':>6s} "
                   f"{'push':>7s} {'r/mkt':>6s} {'surplus':>8s} {'stn cash':>9s}")
        for t in TYPES:
            c = find(cells, type=t, regime=regime, arm="D", share=0.39)
            d = c["derived"]
            out.append(f"    {LABEL[t]:>34s} {d['gain_from_countering']:7.0f} "
                       f"{d['success_rate']:6.3f} {d['retention']:6.3f} "
                       f"{d['mean_offer_push']:+7.3f} {d['rent_ratio']:6.3f} "
                       f"{d['surplus_pcy']:8.0f} {d['station_cash_phy']:9.0f}")
    out.append("")


def kills_56(cells, out):
    verdicts = {}
    out.append("K5 -- landlord type is not actionable.")
    out.append(f"  Fires if mean crab gain from countering differs by < 1% of "
               f"annual rent (${PCT1:.0f}) across the three types.")
    fired_any = []
    for regime in ("loss", "gain"):
        g = {}
        for t in TYPES:
            c = find(cells, type=t, regime=regime, arm="D", share=0.39)
            a = c["per_station"]["surplus_asker"]
            n = c["per_station"]["surplus_nonasker"]
            m, s = paired(a, n)
            g[t] = (m, s)
        spread = max(v[0] for v in g.values()) - min(v[0] for v in g.values())
        fired = spread < PCT1
        fired_any.append(fired)
        out.append(f"  {regime}: " + "  ".join(
            f"{t}=${g[t][0]:+.0f}+/-{g[t][1]:.0f}" for t in TYPES))
        out.append(f"         spread = ${spread:.0f}  [bar ${PCT1:.0f}]  -> "
                   f"{'would fire' if fired else 'would not fire'}")
    fired = all(fired_any)
    verdicts["K5"] = fired
    out.append(f"  --> K5 {'FIRED' if fired else 'DID NOT FIRE'}")
    out.append("  CAVEAT, and it is a big one: the spread is created almost")
    out.append("  entirely by MEDIUM, which is OUR INVENTION. Excluding it and")
    out.append("  comparing only the two empirically anchored types:")
    grounded = []
    for regime in ("loss", "gain"):
        g = {}
        for t in ("institutional", "mom"):
            c = find(cells, type=t, regime=regime, arm="D", share=0.39)
            g[t] = paired(c["per_station"]["surplus_asker"],
                          c["per_station"]["surplus_nonasker"])
        sp = abs(g["institutional"][0] - g["mom"][0])
        grounded.append(sp < PCT1)
        out.append(f"    {regime}: institutional ${g['institutional'][0]:+.0f}"
                   f"+/-{g['institutional'][1]:.0f} vs mom ${g['mom'][0]:+.0f}"
                   f"+/-{g['mom'][1]:.0f}; spread ${sp:.0f} -> "
                   f"{'would fire' if sp < PCT1 else 'would not fire'}")
    out.append(f"    on grounded types only, K5 would "
               f"{'FIRE' if all(grounded) else 'NOT FIRE'}")

    out.append("")
    out.append("K6 -- the tool is worth least where we aimed it.")
    out.append("  Fires if crab gain from countering is HIGHEST against "
               "MOM-AND-POP.")
    hi = {}
    for regime in ("loss", "gain"):
        g = {t: paired(find(cells, type=t, regime=regime, arm="D",
                            share=0.39)["per_station"]["surplus_asker"],
                       find(cells, type=t, regime=regime, arm="D",
                            share=0.39)["per_station"]["surplus_nonasker"])[0]
             for t in TYPES}
        best = max(g, key=g.get)
        hi[regime] = best
        out.append(f"  {regime}: highest = {best} "
                   f"(${g[best]:+.0f}); order " +
                   " > ".join(f"{t}" for t in sorted(g, key=g.get, reverse=True)))
    fired = any(v == "mom" for v in hi.values())
    verdicts["K6"] = fired
    out.append(f"  --> K6 {'FIRED' if fired else 'DID NOT FIRE'}")
    return verdicts


def broadcast_table(cells, out):
    out.append("")
    out.append("=" * 78)
    out.append("ARM F -- BROADCAST (AMENDMENT 1 §A1.2)")
    out.append("=" * 78)
    out.append("The asker share is ENDOGENOUS: a crab asks when belief x value")
    out.append("beats its own cost of sending the message. Broadcast changes")
    out.append("beliefs, not the share directly. Control = same machinery with")
    out.append("broadcast off (crabs learn only from their own outcome).")
    out.append("")
    out.append(f"    {'cell':>30s} {'bcast':>6s} {'ask sh':>7s} {'belief':>7s} "
               f"{'scale':>6s} {'succ':>6s} {'surplus':>8s} {'askers':>8s} "
               f"{'non-ask':>8s} {'stn cash':>9s}")
    for regime in ("loss", "gain"):
        for arm in ("F", "F-adaptive"):
            for t in TYPES:
                if arm == "F-adaptive" and t != "institutional":
                    continue
                for bc in (False, True):
                    try:
                        c = find(cells, type=t, regime=regime, arm=arm,
                                 broadcast=bc)
                    except KeyError:
                        continue
                    d = c["derived"]
                    nm = f"{regime}/{arm}/{t}"
                    out.append(
                        f"    {nm:>30s} {str(bc):>6s} {d['ask_share']:7.3f} "
                        f"{d['mean_belief']:7.3f} {d['mean_ask_scale']:6.2f} "
                        f"{d['success_rate']:6.3f} {d['surplus_pcy']:8.0f} "
                        f"{d['surplus_asker']:8.0f} {d['surplus_nonasker']:8.0f} "
                        f"{d['station_cash_phy']:9.0f}")
    out.append("")


def kills_78(cells, out):
    verdicts = {}
    out.append("K7 -- our product is net-harmful at scale. "
               "(The one that matters most.)")
    out.append("  Fires if under BROADCAST + ADAPTIVE INSTITUTIONAL, TOTAL crab "
               f"surplus is lower than under no-broadcast by >= ${PCT1:.0f}.")
    fired_any = []
    for regime in ("loss", "gain"):
        on = find(cells, type="institutional", regime=regime, arm="F-adaptive",
                  broadcast=True)
        off = find(cells, type="institutional", regime=regime, arm="F-adaptive",
                   broadcast=False)
        m, s = paired(off["per_station"]["surplus_pcy"],
                      on["per_station"]["surplus_pcy"])
        fired = m >= PCT1
        fired_any.append(fired)
        out.append(f"  {regime}: total surplus off-broadcast "
                   f"${off['derived']['surplus_pcy']:.0f}, on-broadcast "
                   f"${on['derived']['surplus_pcy']:.0f}")
        out.append(f"         harm from broadcast = ${m:+.0f} +/- {s:.0f} SE  "
                   f"[bar ${PCT1:.0f}]  (positive = broadcast made crabs worse "
                   f"off)")
        out.append(f"         ask share {off['derived']['ask_share']:.3f} -> "
                   f"{on['derived']['ask_share']:.3f}; station cash "
                   f"${off['derived']['station_cash_phy']:.0f} -> "
                   f"${on['derived']['station_cash_phy']:.0f}")
    fired = any(fired_any)
    verdicts["K7"] = fired
    out.append(f"  --> K7 {'FIRED' if fired else 'DID NOT FIRE'}")

    out.append("")
    out.append("K8 -- broadcast only helps the loud.")
    out.append("  Fires if under BROADCAST, non-asker surplus FALLS while asker "
               "surplus RISES, versus no-broadcast.")
    fired_any = []
    for regime in ("loss", "gain"):
        for arm in ("F", "F-adaptive"):
            for t in TYPES:
                if arm == "F-adaptive" and t != "institutional":
                    continue
                try:
                    on = find(cells, type=t, regime=regime, arm=arm,
                              broadcast=True)
                    off = find(cells, type=t, regime=regime, arm=arm,
                               broadcast=False)
                except KeyError:
                    continue
                da, _ = paired(on["per_station"]["surplus_asker"],
                               off["per_station"]["surplus_asker"])
                dn, dns = paired(on["per_station"]["surplus_nonasker"],
                                 off["per_station"]["surplus_nonasker"])
                f = (da > 0.0) and (dn < 0.0)
                fired_any.append(f)
                out.append(f"  {regime}/{arm}/{t}: askers ${da:+.0f}, "
                           f"non-askers ${dn:+.0f} +/- {dns:.0f} -> "
                           f"{'would fire' if f else 'no'}")
    fired = any(fired_any)
    verdicts["K8"] = fired
    out.append(f"  --> K8 {'FIRED' if fired else 'DID NOT FIRE'}")
    return verdicts


def shocks_report(cells, out, data_units=None):
    data_units = data_units or {"institutional": 200, "medium": 40, "mom": 5}
    out.append("=" * 78)
    out.append("EXPLORATORY -- SHOCKS. NO KILL CONDITIONS. NOT EVIDENCE.")
    out.append("=" * 78)
    out.append("AMENDMENT 1 §A1.3: these exist for mechanism intuition and for")
    out.append("an article. No product decision may rest on them. If they are")
    out.append("ever promoted to evidence, that is a failure.")
    out.append("The station does NOT foresee either shock: its policy is solved")
    out.append("on a neutral forecast, so it is surprised, as an operator is.")
    out.append("Surplus is also shown as %AR (percent of that year's annual")
    out.append("market rent) because market rent itself moves 3x across the")
    out.append("migration -- dollar surplus is not comparable across years.")
    out.append("vac/hab = vacancy months per habitat that year.")
    names = {"flu": "CRAB FLU -- demand collapse, years 3-10",
             "migration": "THE AI CRAB MIGRATION -- arrivals years 2-7, "
                          "half depart year 8"}
    for shock in ("flu", "migration"):
        out.append("")
        out.append(f"### {names[shock]}")
        for t in TYPES:
            try:
                c = find(cells, type=t, shock=shock)
            except KeyError:
                continue
            out.append(f"  {LABEL[t]}")
            units = data_units[t]
            out.append(f"    {'yr':>3s} {'market':>7s} {'r/mkt':>6s} "
                       f"{'reten':>6s} {'succ':>6s} {'vac/hab':>8s} "
                       f"{'incumbent $':>12s} {'inc %AR':>8s} {'rich %AR':>9s}")
            for row in c["series"]:
                ar = 12.0 * row["market"]
                rich = (f"{100*row['surplus_wealthy']/ar:9.1f}"
                        if row["n_wealthy"] > 0 else "        -")
                out.append(f"    {row['year']:3d} {row['market']:7.0f} "
                           f"{row['rent_ratio']:6.3f} {row['retention']:6.3f} "
                           f"{row['success_rate']:6.3f} "
                           f"{row['vacancy_months']/units:8.3f} "
                           f"{row['surplus_incumbent']:12.0f} "
                           f"{100*row['surplus_incumbent']/ar:8.1f} {rich}")
    out.append("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="exploratory")
    ap.add_argument("--shocks", action="store_true")
    a = ap.parse_args()
    fn = (f"results_phase2_{a.spec}{'_shocks' if a.shocks else ''}.json")
    data = load(fn)
    cells = data["cells"]
    out = [f"crabs {data['meta']['version']}  phase 2  spec {data['meta']['spec']}"
           f"  runtime {data['meta']['runtime_s']}s"]
    out.append("NOTE: Phase 1's validation gate FAILED under both "
               "specifications. Everything below inherits that: it is "
               "mechanism, not measurement.")
    out.append("NOTE: the MEDIUM landlord policy is OUR INVENTION with no "
               "empirical anchor (AMENDMENT 1 §A1.4).")
    out.append("")
    if a.shocks:
        shocks_report(cells, out)
        print("\n".join(out))
        return
    types_table(cells, out)
    v = kills_56(cells, out)
    broadcast_table(cells, out)
    v.update(kills_78(cells, out))
    out.append("")
    out.append("-" * 78)
    out.append("PHASE 2 SUMMARY  " + "   ".join(
        f"{k}: {'FIRED' if x else 'DID NOT FIRE'}" for k, x in v.items()))
    out.append("-" * 78)
    print("\n".join(out))


if __name__ == "__main__":
    main()
