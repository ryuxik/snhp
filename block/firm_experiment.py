"""EXPERIMENT: what business develops on an SNHP two-sided rail?

    python3 -m block.firm_experiment --days 56 --out block/results-firm.json

═══════════════════════════════════════════════════════════════════════════
PRE-REGISTERED HYPOTHESES + KILL CONDITIONS (written BEFORE the run; if a KILL
fires we report the null and do NOT tune to avoid it — docs/REDESIGN Phase 5,
the task brief).
═══════════════════════════════════════════════════════════════════════════
We add ONE actor to the block: a FIRM that PROCURES perishable stock from a
venue, HOLDS it (carrying + spoilage cost), and RESELLS it to a slice of the
crowd, with its own P&L. We characterize what business, if any, develops, and
whether it is created by SNHP specifically.

  KILL A (not SNHP-specific).  If the firm's best profit on the SNHP block ≈
    its profit on a STICKER block, the business isn't created by SNHP → NULL.
    ROBUSTNESS: we also run "sticker_clear" — a sticker board PLUS a flat
    near-expiry clearance channel (a real operator liquidates rather than eat
    the salvage loss). If the firm makes as much on sticker_clear as on SNHP,
    its business is created by a CLEARANCE channel, not by negotiation → the
    sharper KILL A.

  KILL B (disintermediated).  If the firm cannot beat the baseline where the
    venue just SNHP-sells its OWN expiring stock directly to the crowd, then
    SNHP is efficient enough that a middleman adds nothing → NULL (a real,
    publishable result). Measured as: does firm-ON total welfare (venue margin
    + firm margin + bargain consumer surplus) exceed firm-OFF total welfare?

  KILL C (sim-exploit).  If firm profit does not fully decompose into
    ledger-conserving transactions (procurement cash out == cost basis
    recovered on sales + cost basis lost to spoilage/writeoff, to the cent),
    the firm found a HARNESS BUG, not a business → we FIX the harness and do
    NOT report the profit.

WHAT THE SWEEP CONTROLS (see block/firm.py header for why waste must be made
explicit — the shipped block has ZERO exploitable perishable waste):
  * waste supply  — `overstock` (perishable par multiplier) × `dow` (weekend
    demand collapse strands fresh stock). overstock=1, dow=off reproduces the
    shipped no-waste world → the firm makes ~$0 by construction (null anchor).
  * reach gap     — `venue_reach` (the bargain crowd's hassle to reach the
    venue directly). 0 ⇒ the venue disintermediates the firm; large ⇒ only a
    middleman can place the stranded waste. THE KILL-B axis.
The headline is the RELATIONSHIP (firm value vs waste and vs reach), never a
single tuned number.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from block.ledger import paired_ci
from block.firm import (POLICIES, BargainConfig, Firm, FirmPolicy,
                        FirmRunConfig, run_firm_twin)

# the policy parameter sweep (max firm profit — an optimizing sweep, not an LLM)
PROCURE_FRACS = (0.55, 0.70)
RESALE_MARKUPS = (0.20, 0.40, 0.60)


def _policy_variants(base: FirmPolicy):
    for pf in PROCURE_FRACS:
        for mk in RESALE_MARKUPS:
            yield FirmPolicy(name=base.name, procure_wtp_frac=pf,
                             procure_expiring_only=base.procure_expiring_only,
                             max_units_per_day=base.max_units_per_day,
                             resale_markup=mk,
                             resale_buffer_frac=base.resale_buffer_frac,
                             seller_weight=base.seller_weight,
                             hold_days=base.hold_days,
                             carry_cost_frac=base.carry_cost_frac)


# ── metric extraction from a finished ledger ─────────────────────────────
def world_metrics(led, world: str, days: int) -> dict:
    vend_margin = sum(led.day_metrics(world, "vending", d)["margin"]
                      for d in range(days))
    firm_margin = sum(led.day_metrics(world, "firm", d)["margin"]
                      for d in range(days))
    salv_u = sum(led.day_metrics(world, "vending", d)["spoiled_units"]
                 for d in range(days))
    salv_c = sum(led.day_metrics(world, "vending", d)["spoilage_cost"]
                 for d in range(days))
    bargain_cs = street_cs = 0.0
    bargain_served = bargain_arr = 0
    for e in led.events:
        if e.get("world") != world:
            continue
        if e["type"] == "deal" and e.get("persona") == "bargain":
            bargain_cs += e["surplus"]
            bargain_served += 1
        elif e["type"] == "deal" and e.get("kind") == "street":
            street_cs += e["surplus"]
        elif e["type"] == "arrival" and e.get("persona") == "bargain":
            bargain_arr += 1
    return {"vend_margin": round(vend_margin, 2),
            "firm_margin": round(firm_margin, 2),
            "bargain_cs": round(bargain_cs, 2),
            "street_cs": round(street_cs, 2),
            "bargain_served": bargain_served, "bargain_arrivals": bargain_arr,
            "salvage_units": salv_u, "salvage_cost": round(salv_c, 2),
            # TOTAL social welfare: every producer margin + EVERY consumer's
            # surplus (street included — the firm's procurement competes with
            # the venue's own crowd for the discounted excess, so omitting
            # street CS would overstate the firm's contribution).
            "welfare": round(vend_margin + firm_margin + bargain_cs
                             + street_cs, 2)}


def daily_welfare(led, world: str, days: int) -> list[float]:
    """venue margin + firm margin + bargain CS + street CS, per day (paired
    CIs). Street CS is included: the firm's end-of-day procurement changes the
    stock the NEXT day's street crowd sees, so it is part of the firm's effect."""
    barg = [0.0] * days
    strt = [0.0] * days
    for e in led.events:
        if e.get("world") != world or e["type"] != "deal":
            continue
        if e.get("persona") == "bargain":
            barg[e["day"]] += e["surplus"]
        elif e.get("kind") == "street":
            strt[e["day"]] += e["surplus"]
    return [led.day_metrics(world, "vending", d)["margin"]
            + led.day_metrics(world, "firm", d)["margin"] + barg[d] + strt[d]
            for d in range(days)]


def daily_firm_margin(led, world: str, days: int) -> list[float]:
    return [led.day_metrics(world, "firm", d)["margin"] for d in range(days)]


# ── the per-policy sweep (max firm profit in `opt_world`) ────────────────
def best_policy(base: FirmPolicy, rcfg: FirmRunConfig, worlds,
                opt_world: str = "snhp"):
    best = None
    for var in _policy_variants(base):
        led, firms = run_firm_twin(rcfg, var, worlds=worlds)
        prof = firms[opt_world].profit(rcfg.days)
        if best is None or prof > best[0]:
            best = (prof, var, led, firms)
    return best


def best_clearance_profit(rcfg: FirmRunConfig) -> float:
    """KILL-A robustness: the firm's BEST achievable profit on a sticker board
    WITH a flat closing-time clearance — optimized over ITS OWN params and
    over both procurement modes (expiring-only vs also-overstock). If this
    meets or beats the SNHP profit, the business is a clearance business, not
    an SNHP one."""
    best = 0.0
    for base in ("passthrough", "scarcity_speculator"):
        p, _v, _l, firms = best_policy(POLICIES[base], rcfg,
                                       worlds=("sticker_clear",),
                                       opt_world="sticker_clear")
        best = max(best, p)
    return round(best, 2)


def analyze_regime(rcfg: FirmRunConfig, worlds=("sticker", "snhp",
                                               "sticker_clear")) -> dict:
    days = rcfg.days
    # firm-OFF baseline (disintermediation): the venue sells its own waste.
    led_off, _ = run_firm_twin(rcfg, None, worlds=worlds)
    off = {w: world_metrics(led_off, w, days) for w in worlds}

    out = {"regime": {"days": days, "seed": rcfg.seed,
                      "overstock": rcfg.overstock, "dow": rcfg.dow,
                      "venue_reach": rcfg.bargain.venue_reach,
                      "firm_reach": rcfg.bargain.firm_reach,
                      "bargain_per_day": rcfg.bargain.per_day},
           "firm_off": off, "policies": {}}

    max_cons_resid = 0.0
    for name in ("passthrough", "waste_aggregator", "scarcity_speculator"):
        prof, var, led, firms = best_policy(POLICIES[name], rcfg, worlds)
        on = {w: world_metrics(led, w, days) for w in worlds}
        firm = firms["snhp"]
        cons_r = max(abs(firms[w].conservation_residual())
                     for w in worlds if firms[w] is not None)
        deco_r = max(abs(firms[w].decomposition_residual())
                     for w in worlds if firms[w] is not None)
        max_cons_resid = max(max_cons_resid, cons_r, deco_r)
        # firm-profit paired CI (snhp firm margin per day; sticker firm ≡ 0)
        prof_ci = paired_ci(daily_firm_margin(led, "snhp", days), block=5)
        # KILL B: firm-ON welfare vs firm-OFF welfare, paired daily
        dwed_on = daily_welfare(led, "snhp", days)
        dwed_off = daily_welfare(led_off, "snhp", days)
        welfare_delta = [a - b for a, b in zip(dwed_on, dwed_off)]
        wd_ci = paired_ci(welfare_delta, block=5)
        # value vs transfer: does the venue LOSE margin ≈ the firm's gain?
        venue_margin_delta = round(on["snhp"]["vend_margin"]
                                   - off["snhp"]["vend_margin"], 2)
        # CONSUMER effect (the rent-skimmer tell): total consumer surplus, both
        # crowds — does the firm HELP consumers or extract from them?
        cs_on = on["snhp"]["bargain_cs"] + on["snhp"]["street_cs"]
        cs_off = off["snhp"]["bargain_cs"] + off["snhp"]["street_cs"]
        consumer_surplus_delta = round(cs_on - cs_off, 2)
        # waste-clearing validation against the firm-OFF salvage counterfactual
        cf_salvage = off["snhp"]["salvage_units"]
        out["policies"][name] = {
            "best_params": {"procure_wtp_frac": var.procure_wtp_frac,
                            "resale_markup": var.resale_markup,
                            "hold_days": var.hold_days},
            "firm_profit": {w: on[w]["firm_margin"] for w in worlds},
            "firm_profit_snhp_ci": prof_ci,
            "on": on,
            "units": {w: {"procured": firms[w].units_procured,
                          "resold": firms[w].units_resold}
                      for w in worlds if firms[w] is not None},
            "decomposition_snhp": {
                "waste_units_sold": firm.waste_units_sold,
                "arb_units_sold": firm.arb_units_sold,
                "waste_margin": round(firm.waste_margin, 2),
                "arb_margin": round(firm.arb_margin, 2),
                "social_waste_cleared_usd": round(firm.social_waste_cleared, 2),
                "gross_margin": round(firm.resale_revenue - firm.cogs_sold, 2),
                "spoil_loss": round(firm.spoil_loss + firm.writeoff_loss, 2),
                "carry_cost": round(firm.carry_cost, 2),
                "counterfactual_salvage_units": cf_salvage,
                "waste_units_le_counterfactual":
                    firm.waste_units_sold <= cf_salvage},
            "system_effect_snhp": {
                "welfare_delta_vs_disintermediation": wd_ci,
                "venue_margin_delta": venue_margin_delta,
                "consumer_surplus_delta": consumer_surplus_delta,
                "bargain_cs_delta": round(on["snhp"]["bargain_cs"]
                                          - off["snhp"]["bargain_cs"], 2),
                "street_cs_delta": round(on["snhp"]["street_cs"]
                                         - off["snhp"]["street_cs"], 2),
                "waste_units_delta": on["snhp"]["salvage_units"]
                    - off["snhp"]["salvage_units"]},
            "conservation_residual": round(cons_r, 6),
            "decomposition_residual": round(deco_r, 6),
        }

    # KILL verdicts on the winning policy (max SNHP profit)
    winner = max(out["policies"],
                 key=lambda n: out["policies"][n]["firm_profit"]["snhp"])
    w = out["policies"][winner]
    snhp_p = w["firm_profit"]["snhp"]
    stick_p = w["firm_profit"]["sticker"]
    # the FAIR clearance baseline: best firm profit achievable under a flat
    # closing clearance, optimized over its own params (not SNHP's).
    clear_p = best_clearance_profit(rcfg)
    wd = w["system_effect_snhp"]["welfare_delta_vs_disintermediation"]
    se = w["system_effect_snhp"]
    out["best_clearance_profit"] = clear_p
    out["kills"] = {
        "winner": winner,
        "A_not_snhp_specific": {
            "snhp_profit": snhp_p, "plain_sticker_profit": stick_p,
            "best_clearance_profit": clear_p,
            "fired_vs_plain_sticker": abs(snhp_p - stick_p) < 0.05 * max(1.0, abs(snhp_p)),
            # a flat clearance lets the firm buy at the venue FLOOR; SNHP makes
            # it split with the venue (pays above floor). If clearance ≥ SNHP,
            # the business is a clearance business, not an SNHP one.
            "fired_vs_clearance": clear_p >= snhp_p - 0.05 * max(1.0, abs(snhp_p))},
        "B_disintermediated": {
            "welfare_delta_ci": wd,
            "consumer_surplus_delta": se["consumer_surplus_delta"],
            "venue_margin_delta": se["venue_margin_delta"],
            "fired": (wd["ci95"] is None) or (wd["ci95"][1] <= 0.0),
            "value_creator": (wd["ci95"] is not None) and (wd["ci95"][0] > 0.0),
            # a value CREATOR lifts total welfare AND doesn't extract from
            # consumers; a rent SKIMMER lifts its own profit while consumer
            # surplus falls.
            "rent_skimmer": se["consumer_surplus_delta"] < 0.0},
        "C_sim_exploit": {
            "max_residual_usd": round(max_cons_resid, 6),
            "fired": max_cons_resid > 0.01},
    }
    return out


# ── the sweeps (the honest curves) ───────────────────────────────────────
def reach_sweep(days, seed, overstock, dow, reaches) -> list[dict]:
    rows = []
    for vr in reaches:
        rcfg = FirmRunConfig(days=days, seed=seed, overstock=overstock, dow=dow,
                             bargain=BargainConfig(venue_reach=vr))
        led_off, _ = run_firm_twin(rcfg, None, worlds=("snhp",))
        _prof, _var, led_on, _firms = best_policy(
            POLICIES["waste_aggregator"], rcfg, worlds=("snhp",))
        won = daily_welfare(led_on, "snhp", days)
        woff = daily_welfare(led_off, "snhp", days)
        wd = paired_ci([a - b for a, b in zip(won, woff)], block=5)
        rows.append({"venue_reach": vr,
                     "firm_profit": _firms["snhp"].profit(days),
                     "welfare_delta_ci": wd,
                     "off_served": world_metrics(led_off, "snhp", days)["bargain_served"],
                     "on_served": world_metrics(led_on, "snhp", days)["bargain_served"],
                     "off_salvage": world_metrics(led_off, "snhp", days)["salvage_units"],
                     "on_salvage": world_metrics(led_on, "snhp", days)["salvage_units"]})
    return rows


def waste_sweep(days, seed, venue_reach, overstocks_dow) -> list[dict]:
    rows = []
    for overstock, dow in overstocks_dow:
        rcfg = FirmRunConfig(days=days, seed=seed, overstock=overstock, dow=dow,
                             bargain=BargainConfig(venue_reach=venue_reach))
        led_off, _ = run_firm_twin(rcfg, None, worlds=("snhp",))
        _prof, _var, led_on, firms = best_policy(
            POLICIES["waste_aggregator"], rcfg, worlds=("snhp",))
        rows.append({"overstock": overstock, "dow": dow,
                     "off_salvage_units": world_metrics(led_off, "snhp", days)["salvage_units"],
                     "firm_profit": round(firms["snhp"].profit(days), 2),
                     "firm_units_resold": firms["snhp"].units_resold})
    return rows


# ── driver ───────────────────────────────────────────────────────────────
def _fmt_ci(ci):
    if ci["ci95"] is None:
        return f"{ci['mean']:+.1f}"
    return f"{ci['mean']:+.1f} [{ci['ci95'][0]:+.1f},{ci['ci95'][1]:+.1f}]"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=56)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--overstock", type=float, default=4.0)
    ap.add_argument("--venue-reach", type=float, default=6.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    rcfg = FirmRunConfig(days=args.days, seed=args.seed,
                         overstock=args.overstock, dow=True,
                         bargain=BargainConfig(venue_reach=args.venue_reach))
    headline = analyze_regime(rcfg)
    reaches = reach_sweep(args.days, args.seed, args.overstock, True,
                          (0.0, 2.0, 4.0, 6.0, 8.0))
    wastes = waste_sweep(args.days, args.seed, args.venue_reach,
                         ((1.0, False), (2.0, True), (4.0, True), (6.0, True)))
    results = {"headline": headline, "reach_sweep": reaches,
               "waste_sweep": wastes,
               "meta": {"elapsed_s": round(time.perf_counter() - t0, 1)}}

    if args.out:
        with open(args.out, "w") as f:
            f.write(json.dumps(results, indent=1) + "\n")
        print(f"wrote {args.out} ({results['meta']['elapsed_s']}s)\n")

    # ── printed report ──
    r = headline
    print(f"REGIME: overstock={rcfg.overstock}x dow={rcfg.dow} "
          f"venue_reach=${rcfg.bargain.venue_reach} "
          f"firm_reach=${rcfg.bargain.firm_reach} · {args.days} days\n")
    print(f"{'policy':<20}{'firmP stic':>11}{'firmP SNHP':>11}"
          f"{'ΔW/day (CI)':>24}{'venueΔ':>9}{'consumerΔ':>11}")
    for name, p in r["policies"].items():
        fp = p["firm_profit"]
        se = p["system_effect_snhp"]
        print(f"{name:<20}{fp['sticker']:>11.1f}{fp['snhp']:>11.1f}"
              f"{_fmt_ci(se['welfare_delta_vs_disintermediation']):>24}"
              f"{se['venue_margin_delta']:>9.0f}{se['consumer_surplus_delta']:>11.0f}")
    print("  (ΔW/day is the paired daily welfare delta vs the venue-sells-direct"
          " baseline; venueΔ/consumerΔ are 56-day totals, $)")

    k = r["kills"]
    print(f"\nWINNER (max SNHP firm profit): {k['winner']}")
    dec = r["policies"][k["winner"]]["decomposition_snhp"]
    print(f"  profit provenance: WASTE-clearing {dec['waste_units_sold']} units "
          f"→ ${dec['waste_margin']}  vs  ARBITRAGE {dec['arb_units_sold']} units "
          f"→ ${dec['arb_margin']}  (spoil loss ${dec['spoil_loss']})")
    print(f"  waste units ≤ firm-off salvage counterfactual "
          f"({dec['waste_units_sold']} ≤ {dec['counterfactual_salvage_units']}): "
          f"{dec['waste_units_le_counterfactual']}; "
          f"social waste cleared ${dec['social_waste_cleared_usd']}")
    A, B, C = k["A_not_snhp_specific"], k["B_disintermediated"], k["C_sim_exploit"]
    print(f"\n  KILL A (not SNHP-specific):")
    print(f"    vs PLAIN sticker (no clearance): FIRED={A['fired_vs_plain_sticker']} "
          f"(SNHP ${A['snhp_profit']} vs sticker ${A['plain_sticker_profit']})")
    print(f"    vs sticker+CLEARANCE (fair, own-optimized): "
          f"FIRED={A['fired_vs_clearance']} "
          f"(best clearance ${A['best_clearance_profit']} vs SNHP ${A['snhp_profit']})")
    print(f"  KILL B (disintermediated): FIRED={B['fired']}  "
          f"value_creator={B['value_creator']}  rent_skimmer={B['rent_skimmer']}")
    print(f"    ΔW/day {_fmt_ci(B['welfare_delta_ci'])}  "
          f"consumerΔ ${B['consumer_surplus_delta']}  "
          f"venueΔ ${B['venue_margin_delta']} (56-day totals)")
    print(f"  KILL C (sim-exploit): FIRED={C['fired']} "
          f"(max ledger residual ${C['max_residual_usd']})")

    print("\nREACH SWEEP (KILL-B axis; waste_aggregator, SNHP):")
    print(f"  {'venue_reach':>11}{'firm$':>9}{'ΔW vs disinterm':>24}"
          f"{'off/on served':>15}{'off/on salvage':>16}")
    for row in reaches:
        served = f"{row['off_served']}/{row['on_served']}"
        salv = f"{row['off_salvage']}/{row['on_salvage']}"
        print(f"  {row['venue_reach']:>11.1f}{row['firm_profit']:>9.1f}"
              f"{_fmt_ci(row['welfare_delta_ci']):>24}{served:>15}{salv:>16}")

    print("\nWASTE SWEEP (firm value vs available waste; null anchor first):")
    print(f"  {'overstock/dow':>15}{'off_salvage':>13}{'firm$':>9}{'resold':>9}")
    for row in wastes:
        tag = f"{row['overstock']}x/{'dow' if row['dow'] else 'flat'}"
        print(f"  {tag:>15}{row['off_salvage_units']:>13}"
              f"{row['firm_profit']:>9.1f}{row['firm_units_resold']:>9}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
