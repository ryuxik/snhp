"""Verdicts for AMENDMENT 3 (K1 re-run, K13, K14) and AMENDMENT 4 (K16-K18)."""
from __future__ import annotations
import json, math, os
_HERE = os.path.dirname(os.path.abspath(__file__))
ANNUAL_RENT = 24000.0
PCT1, PCT2 = 0.01 * ANNUAL_RENT, 0.02 * ANNUAL_RENT


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
    d = [x - y for x, y in zip(a, b) if x == x and y == y]
    return mean(d), se(d)


def main():
    data = json.load(open(os.path.join(_HERE, "results_engine.json")))
    C = {(c["cell"], c["regime"]): c for c in data["cells"]}
    o = []
    m = data["meta"]
    dm = m["demographics"]
    o.append(f"crabs {m['version']}  AMENDMENT 3 + 4  seeds "
             f"{m['station_seeds'][0]}-{m['station_seeds'][1]}  units {m['units']}"
             f"  runtime {m['runtime_s']}s")
    o.append("")
    o.append("=" * 78)
    o.append("GROUNDING OF THE AGENT UTILITIES (AMENDMENT 3 §A3.2)")
    o.append("=" * 78)
    for k, v in dm["labels"].items():
        o.append(f"  {k:20s} {v}")
    o.append(f"  -> share of tenants weighting TERM above RENT: "
             f"{dm['share_term_over_rent']:.3f}  (if this were ~0, logrolling "
             f"could not help and K13 would deserve to fire)")
    o.append(f"  -> share cost-burdened at the anchor rent: "
             f"{dm['share_cost_burdened']:.3f}  (published ~0.50)")
    o.append(f"  -> median moving cost: ${dm['median_move_cost']:,.0f}  "
             f"(Phase 1's calibrated ~$7,200)")
    o.append("")

    # ---------------- K1 re-run, reported before K13 (A3.5) ----------------
    o.append("=" * 78)
    o.append("K1 RE-RUN AGAINST THE REAL ENGINE  (reported first, per A3.5)")
    o.append("=" * 78)
    o.append("Phase 1 fired K1 against our own reimplementation of ranked asks.")
    o.append("Here the crab's side is gametheory.negotiation.bundle.")
    o.append("negotiate_bundle (multi-issue) or .plain_terms.negotiate_turn")
    o.append("(rent only). All crabs counter; the station is unchanged.")
    o.append("")
    hdr = (f"{'negotiator':>15s} {'regime':>6s} {'tenant cash':>12s} "
           f"{'welfare':>8s} {'joint cash':>11s} {'joint+welf':>11s} "
           f"{'turnover':>9s} {'succ':>6s} {'iss/grant':>10s}")
    for regime in ("loss", "gain"):
        o.append(hdr)
        for neg in ("ladder", "engine_single", "engine_bundle"):
            d = C[(f"K1:{neg}", regime)]["derived"]
            o.append(f"{neg:>15s} {regime:>6s} {d['tenant_cash_phy']:12.0f} "
                     f"{d['welfare_phy']:8.0f} {d['joint_cash_phy']:11.0f} "
                     f"{d['joint_phy']:11.0f} {d['turnover']:9.3f} "
                     f"{d['success_rate']:6.3f} {d['issues_per_grant']:10.2f}")
        o.append("")

    o.append("K13 -- logrolling does nothing here.")
    o.append(f"  Fires if multi-issue bundling does not beat single-issue rent "
             f"bargaining by >= 2% of annual rent (${PCT2:.0f}).")
    fired13 = []
    for regime in ("loss", "gain"):
        mb = C[(f"K1:engine_bundle", regime)]["per_station"]
        ms = C[(f"K1:engine_single", regime)]["per_station"]
        for metric, label in (("tenant_cash_phy", "tenant CASH (primary)"),
                              ("tenant_phy", "tenant cash+welfare")):
            v, s = paired(mb[metric], ms[metric])
            o.append(f"  {regime} {label:24s} bundle - single = ${v:+.0f} "
                     f"+/- {s:.0f}  [bar ${PCT2:.0f}]")
        v, _ = paired(mb["tenant_cash_phy"], ms["tenant_cash_phy"])
        fired13.append(not (v >= PCT2))
    f13 = all(fired13)
    o.append(f"  --> K13 {'FIRED' if f13 else 'DID NOT FIRE'}  (decided on "
             f"tenant CASH, the pre-registered unit)")
    o.append("")
    o.append("K14 -- the engine is worse than the hand-rolled ladder.")
    o.append("  Fires if negotiate_bundle underperforms Phase 1's RANKED_LADDER "
             "on crab surplus.")
    fired14 = []
    for regime in ("loss", "gain"):
        mb = C[(f"K1:engine_bundle", regime)]["per_station"]
        ml = C[(f"K1:ladder", regime)]["per_station"]
        v, s = paired(mb["tenant_cash_phy"], ml["tenant_cash_phy"])
        o.append(f"  {regime}: engine - ladder = ${v:+.0f} +/- {s:.0f} "
                 f"(tenant cash)")
        fired14.append(v < 0.0)
    f14 = any(fired14)
    o.append(f"  --> K14 {'FIRED' if f14 else 'DID NOT FIRE'}")
    o.append("")

    # ---------------- ARM K: joint surplus FIRST (A4.3) ----------------
    o.append("=" * 78)
    o.append("ARM K -- THE ENGINE MATRIX (AMENDMENT 4). JOINT SURPLUS FIRST.")
    o.append("=" * 78)
    o.append("Rent is a pure transfer between the pair, so it CANCELS in the")
    o.append("joint total. Joint surplus can move only through deadweight")
    o.append("(turn cost + vacancy + moving cost, destroyed not transferred)")
    o.append("and through the preference-intensity premium. Both are shown,")
    o.append("because they point in opposite directions.")
    o.append("")
    for regime in ("loss", "gain"):
        o.append(f"  {regime.upper()}-TO-LEASE   (all $/habitat-year)")
        o.append(f"    {'cell':>5s} {'joint CASH':>11s} {'joint+welf':>11s} "
                 f"{'deadweight':>11s} {'turnover':>9s} {'welfare':>8s} "
                 f"{'succ':>6s}")
        for nm in ("N/N", "T/N", "N/L", "T/L"):
            d = C[(f"K:{nm}", regime)]["derived"]
            o.append(f"    {nm:>5s} {d['joint_cash_phy']:11.0f} "
                     f"{d['joint_phy']:11.0f} {d['deadweight_phy']:11.0f} "
                     f"{d['turnover']:9.3f} {d['welfare_phy']:8.0f} "
                     f"{d['success_rate']:6.3f}")
        base = C[("K:N/N", regime)]["per_station"]
        o.append(f"    vs N/N (paired):")
        for nm in ("T/N", "N/L", "T/L"):
            pr = C[(f"K:{nm}", regime)]["per_station"]
            jc, jcs = paired(pr["joint_cash_phy"], base["joint_cash_phy"])
            jw, jws = paired(pr["joint_phy"], base["joint_phy"])
            o.append(f"      {nm:>5s} joint CASH ${jc:+.0f} +/- {jcs:.0f}   "
                     f"joint+welfare ${jw:+.0f} +/- {jws:.0f}")
        o.append("")
    o.append("  THE SPLIT (reported second, per A4.3)")
    for regime in ("loss", "gain"):
        o.append(f"    {regime}: {'cell':>5s} {'tenant':>9s} {'landlord':>9s} "
                 f"{'tenant share of joint':>22s}")
        for nm in ("N/N", "T/N", "N/L", "T/L"):
            d = C[(f"K:{nm}", regime)]["derived"]
            j = d["joint_phy"]
            o.append(f"           {nm:>5s} {d['tenant_phy']:9.0f} "
                     f"{d['landlord_phy']:9.0f} "
                     f"{(d['tenant_phy']/j if j else float('nan')):22.3f}")
    o.append("")

    # ---------------- K16, K17, K18 ----------------
    o.append("K16 -- we arm the stronger side more than the weaker.")
    o.append("  Fires if the LANDLORD's gain in N/L exceeds the TENANT's gain "
             "in T/N, each against N/N.")
    f16 = []
    for regime in ("loss", "gain"):
        base = C[("K:N/N", regime)]["per_station"]
        lg, lgs = paired(C[("K:N/L", regime)]["per_station"]["landlord_phy"],
                         base["landlord_phy"])
        tg, tgs = paired(C[("K:T/N", regime)]["per_station"]["tenant_phy"],
                         base["tenant_phy"])
        o.append(f"  {regime}: landlord gain in N/L = ${lg:+.0f} +/- {lgs:.0f}; "
                 f"tenant gain in T/N = ${tg:+.0f} +/- {tgs:.0f}")
        f16.append(lg > tg)
    o.append(f"  --> K16 {'FIRED' if any(f16) else 'DID NOT FIRE'}")
    o.append("")
    o.append("K17 -- it is an arms race, not value creation.")
    o.append("  Fires if joint surplus in T/L is within noise of N/N.")
    f17 = []
    for regime in ("loss", "gain"):
        base = C[("K:N/N", regime)]["per_station"]
        pr = C[("K:T/L", regime)]["per_station"]
        for metric, label in (("joint_cash_phy", "joint CASH"),
                              ("joint_phy", "joint+welfare")):
            v, s = paired(pr[metric], base[metric])
            within = abs(v) < 2.0 * s if s == s else True
            o.append(f"  {regime} {label:14s} T/L - N/N = ${v:+.0f} +/- {s:.0f}"
                     f"  -> {'WITHIN noise' if within else 'outside noise'}")
        v, s = paired(pr["joint_cash_phy"], base["joint_cash_phy"])
        f17.append(abs(v) < 2.0 * s if s == s else True)
    o.append(f"  --> K17 {'FIRED' if all(f17) else 'DID NOT FIRE'}  (decided on "
             f"joint CASH; the welfare reading is reported above)")
    o.append("")
    o.append("K18 -- mutual engines destroy value.")
    o.append("  Fires if T/L has BOTH a higher turnover rate than N/N AND lower "
             "joint surplus.")
    f18 = []
    for regime in ("loss", "gain"):
        base = C[("K:N/N", regime)]["derived"]
        tl = C[("K:T/L", regime)]["derived"]
        pr = C[("K:T/L", regime)]["per_station"]
        bs = C[("K:N/N", regime)]["per_station"]
        dt, dts = paired(pr["turnover"], bs["turnover"])
        dj, djs = paired(pr["joint_cash_phy"], bs["joint_cash_phy"])
        o.append(f"  {regime}: turnover {base['turnover']:.3f} -> "
                 f"{tl['turnover']:.3f} (delta {dt:+.4f} +/- {dts:.4f}); "
                 f"joint CASH delta ${dj:+.0f} +/- {djs:.0f}")
        f18.append(dt > 0.0 and dj < 0.0)
    o.append(f"  --> K18 {'FIRED' if any(f18) else 'DID NOT FIRE'}")
    o.append("")
    o.append("-" * 78)
    o.append("SUMMARY  " + "   ".join([
        f"K13: {'FIRED' if f13 else 'DID NOT FIRE'}",
        f"K14: {'FIRED' if f14 else 'DID NOT FIRE'}",
        f"K16: {'FIRED' if any(f16) else 'DID NOT FIRE'}",
        f"K17: {'FIRED' if all(f17) else 'DID NOT FIRE'}",
        f"K18: {'FIRED' if any(f18) else 'DID NOT FIRE'}"]))
    o.append("-" * 78)
    print("\n".join(o))


if __name__ == "__main__":
    main()
