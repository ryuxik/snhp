"""WHOLESALE runner — paired-week A/B across procurement arms.

Every arm faces the IDENTICAL demand stream: weekly forecasts and realized
demand depend only on (seed, week, venue, wholesaler), never on anything
an arm did. Divergence starts only at the deal each relationship strikes —
which is the treatment effect, isolated (vend/run.py's design, one tier up).

  python3 -m wholesale.run --weeks 26 --seeds 8 --grid \
      --out wholesale/results.json

Arms:
  ratecard        posted card + published volume breaks, venue picks its
                  best (or defects to cash-and-carry); delivery windows
                  FCFS — the industry control
  nego            Nash per relationship-week over the full bundle, the
                  wholesaler coordinating route density across the block
  nego-indep      H-W3 ablation: same Nash, but each negotiation is blind
                  to the wholesaler's other block commitments (windows are
                  priced as fresh stops; physical capacity still binds)
  nego-no-X       H-W1 issue ablations: X frozen at its rate-card default
                  (X in window | price | qty | terms | spoil)
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from wholesale import calibration as cal
from wholesale.calibration import V_ORDER, W_ORDER
from wholesale.scenario import Deal, Disagreement, build_ctx, disagreement, nash_deal
from wholesale.world import Schedule, week_demand, window_label

WHOLESALE_VERSION = 1

ARMS = ("ratecard", "nego", "nego-indep", "nego-no-window", "nego-no-price",
        "nego-no-qty", "nego-no-terms", "nego-no-spoil")
LEVER_ARMS = {"window": "nego-no-window", "price": "nego-no-price",
              "qty": "nego-no-qty", "terms": "nego-no-terms",
              "spoilage": "nego-no-spoil"}


def _fix_for(arm: str, dis: Disagreement) -> dict | None:
    """Issue-freeze for the H-W1 ablation arms: the frozen issue takes its
    rate-card default (FCFS window, break price, rate-card-optimal qty,
    best published terms, no sharing)."""
    return {"nego": None, "nego-indep": None,
            "nego-no-window": {"window": dis.window},
            "nego-no-price": {"discount": 0.0},
            "nego-no-qty": {"qty": dis.rc_q},
            "nego-no-terms": {"terms": dis.rc_terms},
            "nego-no-spoil": {"share": 0.0}}[arm]


def _score(ctx, env, channel, qty, price, window, terms, share,
           deal: Deal | None, dis: Disagreement) -> dict:
    """Realized scoring of the executed event against the week's realized
    demand (paired across arms). Route costs are billed at the
    wholesaler-week level (see run_week) — a shared window is ONE stop."""
    d = env.d_real
    sold, over = min(qty, d), max(0, qty - d)
    credit = 0.0
    if channel == "none":
        real_v = real_w = 0.0
    elif channel == "jetro":
        real_v = (ctx.R * sold + ctx.salv * over - price * qty
                  - (cal.JETRO_HAUL + cal.JETRO_TIME))
        real_w = 0.0
    else:
        credit = share * price * over if ctx.perishable else 0.0
        real_v = (ctx.R * sold + ctx.salv * over + credit
                  - price * qty * ctx.pv_v[terms] - float(ctx.recv[window]))
        real_w = price * qty * ctx.pv_w[terms] - ctx.cogs * qty - credit
    return {
        "wholesaler": ctx.wholesaler, "venue": ctx.venue, "channel": channel,
        "negotiated": channel == "nego", "qty": qty, "unit_price": price,
        "window": window, "terms": terms, "share": share,
        "exp_u_v": deal.u_v if deal else None,
        "exp_u_w": deal.u_w if deal else None,
        "d_v": dis.d_v, "d_w": dis.d_w, "event": dis.event,
        "list_value": deal.list_value if deal else None,
        "mu_w": round(env.mu_w, 2), "d_real": d, "sold": sold,
        "spoiled": over if (ctx.perishable and channel != "none") else 0,
        "credit": round(credit, 2),
        "real_u_v": real_v, "real_w_contrib": real_w,
    }


def run_week(arm: str, ctxs: dict, envs: dict):
    """One paired week of one arm: 12 relationship deals in fixed route
    order. Returns (records, schedules-by-wholesaler)."""
    schedules = {w: Schedule() for w in W_ORDER}
    records = []
    for w in W_ORDER:
        sch = schedules[w]
        for v in V_ORDER:
            ctx, env = ctxs[(w, v)], envs[(w, v)]
            coord = arm != "nego-indep"
            dis = disagreement(ctx, env, sch,
                               coordinate=True if arm == "ratecard" else coord)
            deal = None
            if arm != "ratecard":
                deal = nash_deal(ctx, env, sch, dis, coordinate=coord,
                                 fix=_fix_for(arm, dis))
            if deal is not None:
                sch.add(v, deal.window)
                rec = _score(ctx, env, "nego", deal.qty, deal.unit_price,
                             deal.window, deal.terms, deal.share, deal, dis)
            elif dis.event == "ratecard":     # the no-deal EVENT executes
                sch.add(v, dis.window)
                rec = _score(ctx, env, "ratecard", dis.rc_q,
                             float(ctx.break_price(dis.rc_q)), dis.window,
                             dis.rc_terms, 0.0, None, dis)
            elif dis.event == "jetro":
                rec = _score(ctx, env, "jetro", dis.jet_q,
                             round(cal.JETRO_PRICE_FRAC * ctx.base, 2),
                             None, "cod", 0.0, None, dis)
            else:
                rec = _score(ctx, env, "none", 0, 0.0, None, "cod", 0.0,
                             None, dis)
            records.append(rec)
    return records, schedules


def paired_ci(diff_sw: np.ndarray) -> dict:
    """Mean paired weekly difference with a 95% t-interval over SEED-level
    means (weeks within a seed share no state here, but seed-level blocks
    are the conservative, honest unit — vend's block-CI convention)."""
    seed_means = diff_sw.mean(axis=1)
    n = len(seed_means)
    mean = float(seed_means.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n_seeds": n}
    se = float(seed_means.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)],
            "n_seeds": n}


def run_cell(noise: float, flex: float, weeks: int, seeds: list[int],
             arms=ARMS, keep_records: bool = False) -> dict:
    """All arms on one grid cell, paired by (seed, week)."""
    ctxs = {(w, v): build_ctx(w, v, flex) for w in W_ORDER for v in V_ORDER}
    S, W = len(seeds), weeks
    acc = {arm: {
        "venue_side": np.zeros((S, W)), "whol_side": np.zeros((S, W)),
        "per_venue": {v: np.zeros((S, W)) for v in V_ORDER},
        "per_whol": {w: np.zeros((S, W)) for w in W_ORDER},
        "shared_windows": np.zeros((S, W)), "stops": np.zeros((S, W)),
        "am_stops": np.zeros((S, W)), "route_cost": np.zeros((S, W)),
        "negotiated": 0, "ratecard": 0, "jetro": 0, "none": 0,
    } for arm in arms}
    records_out = {arm: [] for arm in arms} if keep_records else None

    for si, seed in enumerate(seeds):
        for wk in range(W):
            envs = {(w, v): week_demand(seed, wk, w, v, noise)
                    for w in W_ORDER for v in V_ORDER}
            for arm in arms:
                recs, schedules = run_week(arm, ctxs, envs)
                a = acc[arm]
                for r in recs:
                    a["per_venue"][r["venue"]][si, wk] += r["real_u_v"]
                    a["per_whol"][r["wholesaler"]][si, wk] += r["real_w_contrib"]
                    a[r["channel"] if r["channel"] != "nego" else "negotiated"] += 1
                for w, sch in schedules.items():
                    a["per_whol"][w][si, wk] -= sch.realized_route_cost()
                    a["shared_windows"][si, wk] += sch.shared_windows()
                    a["stops"][si, wk] += sch.n_stops()
                    a["am_stops"][si, wk] += sch.am_stops()
                    a["route_cost"][si, wk] += sch.realized_route_cost()
                a["venue_side"][si, wk] = sum(
                    a["per_venue"][v][si, wk] for v in V_ORDER)
                a["whol_side"][si, wk] = sum(
                    a["per_whol"][w][si, wk] for w in W_ORDER)
                if keep_records:
                    records_out[arm].append(
                        {"seed": seed, "week": wk, "records": recs,
                         "schedules": schedules})

    n_rel = S * W * len(W_ORDER) * len(V_ORDER)
    summary = {}
    for arm in arms:
        a = acc[arm]
        summary[arm] = {
            "venue_side_week": round(float(a["venue_side"].mean()), 2),
            "wholesaler_side_week": round(float(a["whol_side"].mean()), 2),
            "joint_week": round(float(
                (a["venue_side"] + a["whol_side"]).mean()), 2),
            "per_venue_week": {v: round(float(a["per_venue"][v].mean()), 2)
                               for v in V_ORDER},
            "per_wholesaler_week": {w: round(float(a["per_whol"][w].mean()), 2)
                                    for w in W_ORDER},
            "negotiated_share": round(a["negotiated"] / n_rel, 4),
            "ratecard_share": round(a["ratecard"] / n_rel, 4),
            "jetro_share": round(a["jetro"] / n_rel, 4),
            "shared_windows_week": round(float(a["shared_windows"].mean()), 2),
            "stops_week": round(float(a["stops"].mean()), 2),
            "am_stops_week": round(float(a["am_stops"].mean()), 2),
            "route_cost_week": round(float(a["route_cost"].mean()), 2),
        }

    paired = {}
    base = acc["ratecard"]
    for arm in arms:
        if arm == "ratecard":
            continue
        a = acc[arm]
        paired[f"{arm}_vs_ratecard"] = {
            "venue_side": paired_ci(a["venue_side"] - base["venue_side"]),
            "wholesaler_side": paired_ci(a["whol_side"] - base["whol_side"]),
            "joint": paired_ci((a["venue_side"] + a["whol_side"])
                               - (base["venue_side"] + base["whol_side"])),
            "per_venue": {v: paired_ci(a["per_venue"][v] - base["per_venue"][v])
                          for v in V_ORDER},
            "per_wholesaler": {w: paired_ci(a["per_whol"][w] - base["per_whol"][w])
                               for w in W_ORDER},
        }

    levers = {}
    if "nego" in arms:
        nego_joint = acc["nego"]["venue_side"] + acc["nego"]["whol_side"]
        for lever, arm in LEVER_ARMS.items():
            if arm in arms:
                aj = acc[arm]["venue_side"] + acc[arm]["whol_side"]
                levers[lever] = paired_ci(nego_joint - aj)

    coordination = None
    if "nego" in arms and "nego-indep" in arms:
        coordination = {
            "wholesaler_side": paired_ci(acc["nego"]["whol_side"]
                                         - acc["nego-indep"]["whol_side"]),
            "joint": paired_ci(
                (acc["nego"]["venue_side"] + acc["nego"]["whol_side"])
                - (acc["nego-indep"]["venue_side"]
                   + acc["nego-indep"]["whol_side"])),
            "shared_windows_week": {
                "nego": summary["nego"]["shared_windows_week"],
                "nego-indep": summary["nego-indep"]["shared_windows_week"],
                "ratecard": summary["ratecard"]["shared_windows_week"]},
        }

    cell = {"noise": noise, "flex": flex, "weeks": weeks,
            "seeds": list(seeds), "arms": summary, "paired_vs_ratecard": paired,
            "levers": levers, "coordination": coordination}
    if keep_records:
        cell["_records"] = records_out
    return cell


def _hypotheses(cell: dict) -> dict:
    """The pre-registered readouts, computed from the headline cell."""
    lev = cell["levers"]
    nego = cell["paired_vs_ratecard"]["nego_vs_ratecard"]
    coord = cell["coordination"]
    w_gain = nego["wholesaler_side"]["mean"]
    c_gain = coord["wholesaler_side"]["mean"] if coord else None
    return {
        "H-W1_window_lever_vs_price_lever": {
            "window": lev.get("window"), "price": lev.get("price"),
            "qty": lev.get("qty"), "terms": lev.get("terms"),
            "spoilage": lev.get("spoilage"),
            "window_gt_price": bool(lev["window"]["mean"] > lev["price"]["mean"]),
        },
        "H-W2_both_sides_beat_ratecard": {
            "venue_side": nego["venue_side"],
            "wholesaler_side": nego["wholesaler_side"],
            "both_positive": bool(nego["venue_side"]["mean"] > 0
                                  and nego["wholesaler_side"]["mean"] > 0),
            "per_venue": nego["per_venue"],
            "per_wholesaler": nego["per_wholesaler"],
        },
        "H-W3_coordination_is_cross_venue": {
            "coordination_value": coord["wholesaler_side"] if coord else None,
            "shared_windows_week": coord["shared_windows_week"] if coord else None,
            "share_of_wholesaler_gain": (
                round(c_gain / w_gain, 3)
                if coord and w_gain and abs(w_gain) > 1e-9 else None),
        },
    }


def _print_tables(cell: dict, label: str) -> None:
    arms = [a for a in ("nego", "nego-indep") if a in cell["arms"]]
    print(f"\n── {label}: Δ vs ratecard, $/week realized "
          f"(paired, CI over seeds) " + "─" * 12)
    print(f"{'VENUE-SIDE':<12}" + "".join(f"{a:>26}" for a in arms))
    for v in V_ORDER:
        row = f"{v:<12}"
        for a in arms:
            ci = cell["paired_vs_ratecard"][f"{a}_vs_ratecard"]["per_venue"][v]
            row += f"{ci['mean']:>+10.2f} {str(ci['ci95']):>15}"
        print(row)
    tot_v = {a: cell["paired_vs_ratecard"][f"{a}_vs_ratecard"]["venue_side"]
             for a in arms}
    print(f"{'TOTAL':<12}" + "".join(
        f"{tot_v[a]['mean']:>+10.2f} {str(tot_v[a]['ci95']):>15}" for a in arms))
    print(f"{'WHOLESALER-SIDE':<12}")
    for w in W_ORDER:
        row = f"{w:<12}"
        for a in arms:
            ci = cell["paired_vs_ratecard"][f"{a}_vs_ratecard"]["per_wholesaler"][w]
            row += f"{ci['mean']:>+10.2f} {str(ci['ci95']):>15}"
        print(row)
    tot_w = {a: cell["paired_vs_ratecard"][f"{a}_vs_ratecard"]["wholesaler_side"]
             for a in arms}
    print(f"{'TOTAL':<12}" + "".join(
        f"{tot_w[a]['mean']:>+10.2f} {str(tot_w[a]['ci95']):>15}" for a in arms))
    if cell["levers"]:
        print("LEVERS (joint $/wk lost when the issue is frozen): "
              + "  ".join(f"{k} {ci['mean']:+.2f}"
                          for k, ci in cell["levers"].items()))
    if cell["coordination"]:
        c = cell["coordination"]
        print(f"COORDINATION (H-W3): wholesaler-side "
              f"{c['wholesaler_side']['mean']:+.2f} {c['wholesaler_side']['ci95']}"
              f" · shared windows/wk {c['shared_windows_week']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=20260710)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--grid", action="store_true",
                    help="run the demand-noise x flexibility grid")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    arm_names = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {list(ARMS)})", file=sys.stderr)
        return 2
    seeds = [args.seed0 + i for i in range(args.seeds)]

    cells_spec = [(cal.BASE_NOISE, cal.BASE_FLEX)]
    if args.grid:
        cells_spec += [(n, f) for n in cal.NOISE_GRID for f in cal.FLEX_GRID
                       if (n, f) != (cal.BASE_NOISE, cal.BASE_FLEX)]

    cells = {}
    for noise, flex in cells_spec:
        key = f"noise{noise:g}_flex{flex:g}"
        cells[key] = run_cell(noise, flex, args.weeks, seeds, arm_names)
        _print_tables(cells[key], key)

    base_key = f"noise{cal.BASE_NOISE:g}_flex{cal.BASE_FLEX:g}"
    results = {
        "wholesale_version": WHOLESALE_VERSION,
        "config": {
            "weeks": args.weeks, "seeds": seeds, "arms": list(arm_names),
            "windows": [window_label(i) for i in range(10)],
            "route": {"stop": cal.STOP_COST, "drop": cal.DROP_COST,
                      "shadow_am": cal.SHADOW_AM, "shadow_pm": cal.SHADOW_PM,
                      "am_stops_per_week": cal.AM_STOPS_PER_WEEK},
            "buffer": {"min": cal.BUFFER_MIN, "frac": cal.BUFFER_FRAC},
            "jetro": {"price_frac": cal.JETRO_PRICE_FRAC,
                      "trip_cost": cal.JETRO_HAUL + cal.JETRO_TIME},
            "demand_mu": {f"{w}->{v}": cal.DEMAND_MU[(w, v)]
                          for w in W_ORDER for v in V_ORDER},
            "notes": [
                "paired weeks: identical forecasts and realized demand across arms",
                "discount-only: negotiated price never above the published break price",
                "event-consistent disagreement: rate-card sale the wholesaler already had, or Jetro (wholesaler keeps nothing)",
                "route density explicit: a shared window bills one stop + drop fees",
                "surpluses are realized (post-demand), $ per block-week; CIs over seed means",
                "venue-side surplus includes attributable retail value, so LEVELS are large; the paired deltas are the experiment",
            ],
        },
        "headline_cell": base_key,
        "cells": cells,
        "hypotheses": _hypotheses(cells[base_key]),
    }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
            f.write("\n")
        print(f"\nwrote {args.out}")
    else:
        print(json.dumps(results["hypotheses"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
