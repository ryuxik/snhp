"""BAKESHOP experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL world: arrivals, consumer draws, day shocks,
event-spike days, and the morning bake / weekly order (with its gut
miscalibration error) depend only on (master_seed, day, tick, k, cfg),
never on anything a policy did. Divergence starts at each consumer's
decision against each arm's prices/quotes — the treatment effect,
isolated. (The 2pm mini-bake reacts to the arm's own shelf — the same
deterministic gut rule for every arm, boba's maybe_cook pattern.)

Days carry overnight state (day-old shelves, the florist's aging week), so
per-day diffs are serially dependent — the headline CI uses 5-day block
means, which widens the interval honestly.

  python3 -m bakeshop.run --venue bakery --days 30 --seed 20260710
  python3 -m bakeshop.run --grid --out bakeshop/results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from bakeshop.policies import (ComputedPolicy, ControlPolicy, NegoPolicy,
                               RegimePolicy)
from bakeshop.world import (BakeshopConfig, DEFAULT_CONFIG, ShopState,
                            arrivals_at, begin_day, best_board_basket,
                            end_of_day, get_venue, is_spike_day,
                            maybe_minibake, outside_surplus,
                            sample_consumer, TICKS_PER_HOUR)

BAKESHOP_VERSION = 2   # 2026-07-10: CRITICAL-ANALYSIS §9 fix — floral
                       # shrink recalibration (receiving loss, quality-
                       # tiered markdown ladder, extended vase life) +
                       # the regime/1 regime-switching arm

ARMS = {
    "control": ControlPolicy,
    "computed": ComputedPolicy,
    "computed-agedonly": lambda: ComputedPolicy(
        policy_id="computed-agedonly/1", aged_only=True),
    "nego": NegoPolicy,
    "nego-nopairs": lambda: NegoPolicy(policy_id="nego-nopairs/1",
                                       pairs=False),
    "regime": RegimePolicy,
}

GRID_SIGMAS = (0.15, 0.35)       # bake/order gut miscalibration
GRID_SPIKES = (0.0, 0.1)         # P(event-spike day)


def _settle(state, venue, m, lines, revenue, surplus):
    """Book a sale of [(sku, age, qty)] lines at `revenue` total. Costs
    book at consumption (sold here, wasted at end of life) — waste
    conservation (produced = sold + shelved + wasted) is a test."""
    for sku, age, qty in lines:
        it = venue.item(sku)
        state.take(sku, age, qty)
        m["cogs_sold"] += qty * it.unit_cost
        m["units"] += qty
        m["list_value_sold"] += qty * it.list_price
        if age >= 1:
            m["aged_units"] += qty       # aged_revenue booked by callers
    m["revenue"] += revenue
    m["deals"] += 1
    m["consumer_surplus"] += surplus


def run_day(policy, state, venue, master_seed: int, day: int,
            cfg: BakeshopConfig = DEFAULT_CONFIG) -> dict:
    m = {"revenue": 0.0, "cogs_sold": 0.0, "units": 0, "aged_units": 0,
         "aged_revenue": 0.0, "list_value_sold": 0.0, "deals": 0,
         "arrivals": 0, "lost_outside": 0, "lost": 0,
         "negotiated": 0, "pair_deals": 0, "neg_gain": 0.0,
         "consumer_surplus": 0.0, "produced_units": 0, "produced_cost": 0.0,
         "spike": int(is_spike_day(master_seed, day, cfg))}
    morning, pu, pc = begin_day(state, venue, master_seed, cfg)
    m["produced_units"] += pu
    m["produced_cost"] += pc

    for tick in range(venue.ticks_per_day):
        state.tick = tick
        if venue.minibake_hour is not None \
                and venue.hour_of(tick) == venue.minibake_hour \
                and tick % TICKS_PER_HOUR == 0:
            xu, xc = maybe_minibake(state, venue, morning)
            m["produced_units"] += xu
            m["produced_cost"] += xc

        n = arrivals_at(venue, master_seed, day, tick, cfg)
        m["arrivals"] += n
        for k in range(n):
            consumer = sample_consumer(venue, master_seed, day, tick, k, cfg)
            s_out = outside_surplus(venue, consumer)
            board = policy.board(state, venue, master_seed, cfg)
            stock = {c: state.stock(*c) for c in board}
            b_lines, s_board = best_board_basket(venue, consumer, board,
                                                 stock)

            # ── nego arm: the brokered quote happens first ──
            if getattr(policy, "mode", "board") == "nego":
                deal = policy.quote_for(state, venue, consumer,
                                        master_seed, cfg)
                if deal is not None:
                    s_true = deal.value - deal.price
                    # rational acceptance, enforced not assumed: the deal
                    # must beat BOTH the buyer's alternatives (the control
                    # board they could just shop, and the walk outside)
                    if s_true > 1e-9 and s_true >= max(s_out, s_board) - 1e-9:
                        aged_rev = sum(
                            deal.price * (q * venue.item(sku).list_price
                                          / deal.list_value)
                            for sku, age, q in deal.lines if age >= 1)
                        _settle(state, venue, m,
                                [(s, a, q) for s, a, q in deal.lines],
                                deal.price, s_true)
                        m["aged_revenue"] += aged_rev
                        m["negotiated"] += 1
                        m["pair_deals"] += int(len(deal.lines) > 1)
                        m["neg_gain"] += deal.u_shop - deal.d_shop
                        continue
                # no mutual gain (or buyer declined): fall through to board

            if b_lines and s_board > 1e-9 and s_board >= s_out:
                rev = sum(q * p for _, _, q, p in b_lines)
                aged_rev = sum(q * p for _, a, q, p in b_lines if a >= 1)
                _settle(state, venue, m,
                        [(s, a, q) for s, a, q, _ in b_lines], rev, s_board)
                m["aged_revenue"] += aged_rev
            elif s_out > 1e-9:
                m["lost_outside"] += 1
            else:
                m["lost"] += 1

    eod = end_of_day(state, venue)
    m["waste_units"] = eod["waste_units"]
    m["waste_cost"] = eod["waste_cost"]
    m["profit"] = round(m["revenue"] - m["cogs_sold"] - m["waste_cost"], 2)
    m["depth"] = round(1.0 - m["revenue"] / m["list_value_sold"], 4) \
        if m["list_value_sold"] > 0 else 0.0
    for k in ("revenue", "cogs_sold", "aged_revenue", "list_value_sold",
              "consumer_surplus", "neg_gain", "produced_cost"):
        m[k] = round(m[k], 2)
    return m


def paired_ci(diffs: list[float], block: int = 1) -> dict:
    """Mean paired difference with a 95% t-interval on `block`-day means
    (copied from vend.run; overnight inventory makes days serially
    dependent, so blocking widens the CI honestly)."""
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        n_blocks = len(d) // block
        d = d[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)],
            "n": n, "block": block}


PAIRED_METRICS = ("profit", "revenue", "consumer_surplus", "waste_cost",
                  "aged_units", "units")


def run_experiment(arm_names: list[str], venue_name: str, days: int,
                   seed: int, cfg: BakeshopConfig = DEFAULT_CONFIG) -> dict:
    venue = get_venue(venue_name)
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        state = ShopState(venue_name)
        per_day = [run_day(policy, state, venue, seed, d, cfg)
                   for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        totals["depth"] = round(
            1.0 - totals["revenue"] / totals["list_value_sold"], 4) \
            if totals["list_value_sold"] > 0 else 0.0
        results[name] = {"totals": totals, "per_day": per_day}

    paired = {}
    base = arm_names[0]
    compare = [(name, base) for name in arm_names[1:]]
    for a, b in (("nego", "computed"), ("nego", "nego-nopairs"),
                ("regime", "computed"), ("regime", "nego")):
        if a in arm_names and b in arm_names:
            compare.append((a, b))
    for name, ref in compare:
        paired[f"{name}_vs_{ref}"] = {
            metric: paired_ci([results[name]["per_day"][d][metric]
                               - results[ref]["per_day"][d][metric]
                               for d in range(days)],
                              block=5)   # 5-day blocks vs overnight-lot autocorrelation
            for metric in PAIRED_METRICS
        }

    # H-B3 needs the spike-day subset: mean paired profit deltas on spike
    # vs calm days (point estimates; the cell CI is the headline)
    spike_days = [d for d in range(days)
                  if results[base]["per_day"][d]["spike"]]
    calm_days = [d for d in range(days) if d not in spike_days]
    subset = {}
    for name, ref in compare:
        row = {}
        for label, ds in (("spike", spike_days), ("calm", calm_days)):
            if ds:
                row[label] = round(float(np.mean(
                    [results[name]["per_day"][d]["profit"]
                     - results[ref]["per_day"][d]["profit"] for d in ds])), 2)
        subset[f"{name}_vs_{ref}"] = row

    return {
        "bakeshop_version": BAKESHOP_VERSION,
        "config": {
            "seed": seed, "days": days, "venue": venue_name,
            "arms": arm_names,
            "world": {"sigma_miscal": cfg.sigma_miscal,
                      "spike_prob": cfg.spike_prob,
                      "sigma_day": cfg.sigma_day},
            "list_prices": {it.sku: it.list_price for it in venue.items},
            "notes": [
                "control arm = the cultural calendar; per-SKU appeal is "
                "inverted so the list price IS the profit-optimal all-day "
                "fresh sticker (competent, not a strawman)",
                "discount-only: no arm prices above list",
                "paired seeds: identical arrivals/WTP/shocks/spikes AND "
                "identical morning bake / weekly order across arms",
                "dynamic arms' demand model = the true structural process "
                "(favorable); no arm sees today's day shock",
                "waste books at cost at end of life; no salvage channel",
            ],
        },
        "arms": {n: {"totals": r["totals"]} for n, r in results.items()},
        "paired": paired,
        "spike_split": subset,
        "n_spike_days": len(spike_days),
        "_per_day": {n: r["per_day"] for n, r in results.items()},
    }


def run_grid(arm_names: list[str], venues: list[str], days: int, seed: int,
             out: str) -> int:
    """The pre-registered grid: bake/order miscalibration × event-spike
    frequency, 30 paired days per cell, both venues."""
    doc = {"bakeshop_version": BAKESHOP_VERSION, "days": days, "seed": seed,
           "arms": arm_names, "venues": {}}
    for venue_name in venues:
        cells = {}
        for sc in GRID_SIGMAS:
            for sp in GRID_SPIKES:
                cfg = BakeshopConfig(sigma_miscal=sc, spike_prob=sp)
                name = f"cal{sc:g}_spike{sp:g}"
                res = run_experiment(arm_names, venue_name, days, seed, cfg)
                cells[name] = {
                    "world": res["config"]["world"],
                    "n_spike_days": res["n_spike_days"],
                    "totals": {a: {k: res["arms"][a]["totals"][k]
                                   for k in ("profit", "revenue", "units",
                                             "aged_units", "waste_cost",
                                             "waste_units", "depth",
                                             "consumer_surplus",
                                             "pair_deals", "negotiated")}
                               for a in arm_names},
                    "paired": {k: {mm: v[mm] for mm in
                                   ("profit", "consumer_surplus",
                                    "waste_cost", "aged_units")}
                               for k, v in res["paired"].items()},
                    "spike_split": res["spike_split"],
                }
                deltas = {k.replace("_vs_control", ""):
                          v["profit"]["mean"]
                          for k, v in res["paired"].items()
                          if k.endswith("_vs_control")}
                print(f"{venue_name:<8} {name:<18} profit Δ/day vs control: "
                      f"{deltas}")
        doc["venues"][venue_name] = {"cells": cells}
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", choices=("bakery", "flowers"), default=None)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--arms",
                    default="control,computed,computed-agedonly,nego,"
                            "nego-nopairs")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-miscal", type=float, default=0.15)
    ap.add_argument("--spike-prob", type=float, default=0.0)
    ap.add_argument("--grid", action="store_true",
                    help="miscalibration × spike-frequency grid, both "
                         "venues unless --venue is given")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})",
              file=sys.stderr)
        return 2

    if args.grid:
        venues = [args.venue] if args.venue else ["bakery", "flowers"]
        return run_grid(arm_names, venues, args.days, args.seed,
                        args.out or "bakeshop/results.json")

    if not args.venue:
        print("--venue is required outside --grid", file=sys.stderr)
        return 2
    cfg = BakeshopConfig(sigma_miscal=args.sigma_miscal,
                         spike_prob=args.spike_prob)
    res = run_experiment(arm_names, args.venue, args.days, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        summary = {n: res["arms"][n]["totals"]["profit"] for n in arm_names}
        print(f"wrote {args.out} — profit by arm: {summary}")
        for k, v in res["paired"].items():
            print(f"  {k}: profit Δ {v['profit']['mean']} "
                  f"CI95 {v['profit']['ci95']}"
                  f" · CS Δ {v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
