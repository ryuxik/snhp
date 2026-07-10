"""FASHION experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL season: the same buy (depth is drawn before
any pricing decision exists), the same weekly consumer stream (arrivals and
shopper draws depend only on (master_seed, week, k), never on anything a
policy did). Divergence starts at each shopper's decision against each
arm's prices — the treatment effect, isolated.

  python3 -m fashion.run --seasons 40 --seed 20260710 --grid \
      --out fashion/results.json
"""
from __future__ import annotations

import argparse
import json
import sys

from fashion.core import paired_ci, substream
from fashion.policies import CliffPolicy, MarkdownPolicy
from fashion.world import (DEFAULT_CONFIG, SIZES, WEEKS, FashionConfig,
                           arrivals_at, build_catalog, planned_depth,
                           sample_shopper, waiter_buys_now)

FASHION_VERSION = 1

ARMS = {
    "cliff": CliffPolicy,
    "markdown": MarkdownPolicy,
}

# Units by realized discount depth off MSRP. Buckets align with the cliff's
# rungs so "units at each markdown depth" reads the same for both arms.
_BUCKETS = [(0.005, "units_full"), (0.301, "units_d30"),
            (0.501, "units_d50"), (0.701, "units_d70")]


def _bucket(discount: float) -> str:
    for edge, name in _BUCKETS:
        if discount <= edge:
            return name
    return "units_d70plus"


def run_season(policy, catalog, depth, master_seed: int,
               cfg: FashionConfig = DEFAULT_CONFIG) -> dict:
    """One season of one arm. Weekly loop: policy posts a board, new
    arrivals then returning waiters (FIFO — the same deterministic order in
    both arms) decide against it; unsold units salvage at season end.
    Consumer surplus is booked at the WTP of the PURCHASE week (staleness
    already applied). The discount-only clamp is enforced HERE, at
    settlement — a policy that prices above MSRP cannot transact."""
    inv = dict(depth)
    m = {k: 0 for k in ("units_bought", "units_sold", "units_full",
                        "units_d30", "units_d50", "units_d70",
                        "units_d70plus", "salvage_units", "arrivals",
                        "returns", "lost_stockout", "buyers_waiter",
                        "buyers_loyal", "cells_sold_out")}
    m.update({k: 0.0 for k in ("revenue", "salvage_revenue", "buy_cost",
                               "gross_margin", "consumer_surplus",
                               "cs_waiter", "cs_loyal", "sell_through")})
    m["units_bought"] = sum(depth.values())
    m["buy_cost"] = sum(n * catalog[st].unit_cost
                        for (st, _sz), n in depth.items())
    sold_prev = {cell: 0 for cell in depth}
    waiting: list = []
    sellout: dict[str, int] = {}

    for week in range(WEEKS):
        board = policy.price_board(week, inv, catalog)
        for (st, _sz), p in board.items():
            if p > catalog[st].msrp + 1e-9:
                raise ValueError(f"discount-only violated: {st} at {p} "
                                 f"above MSRP {catalog[st].msrp}")
        sold_this = {cell: 0 for cell in depth}
        n_new = arrivals_at(master_seed, week)
        newcomers = [sample_shopper(master_seed, week, k, catalog, cfg)
                     for k in range(n_new)]
        m["arrivals"] += n_new
        m["returns"] += len(waiting)
        still_waiting = []

        for c in newcomers + waiting:
            cell = (c.style, c.size)
            stock = inv.get(cell, 0)
            if stock <= 0:
                m["lost_stockout"] += 1     # their size is gone for good
                continue
            price = board[cell]
            surplus = c.wtp(week) - price
            if c.waiter:
                buy = waiter_buys_now(surplus, c.wtp(week + 1), price, stock,
                                      sold_prev[cell], week == WEEKS - 1)
            else:
                buy = surplus > 0
            if buy:
                inv[cell] = stock - 1
                sold_this[cell] += 1
                m["revenue"] += price
                m["units_sold"] += 1
                m[_bucket(1.0 - price / catalog[c.style].msrp)] += 1
                m["consumer_surplus"] += surplus
                if c.waiter:
                    m["cs_waiter"] += surplus
                    m["buyers_waiter"] += 1
                else:
                    m["cs_loyal"] += surplus
                    m["buyers_loyal"] += 1
            elif c.waiter and week < WEEKS - 1:
                still_waiting.append(c)     # returns weekly until sold out

        waiting = still_waiting
        sold_prev = sold_this
        for style in catalog:
            if style not in sellout and \
                    sum(inv[(style, sz)] for sz in SIZES) == 0:
                sellout[style] = week

    for (style, _sz), s in inv.items():
        m["salvage_units"] += s
        m["salvage_revenue"] += s * catalog[style].salvage
    m["cells_sold_out"] = sum(1 for cell, s in inv.items()
                              if s == 0 and depth[cell] > 0)
    # the −70% rung and deeper: the cliff's own clearance price lands exactly
    # in units_d70, so "fewer deep-clearance units" is d70 + d70plus
    m["units_deep"] = m["units_d70"] + m["units_d70plus"]
    m["sell_through"] = round(100.0 * m["units_sold"] / m["units_bought"], 2) \
        if m["units_bought"] else 0.0
    m["gross_margin"] = m["revenue"] + m["salvage_revenue"] - m["buy_cost"]
    for k in ("revenue", "salvage_revenue", "buy_cost", "gross_margin",
              "consumer_surplus", "cs_waiter", "cs_loyal"):
        m[k] = round(m[k], 2)
    m["sellout_week"] = {st: sellout.get(st) for st in catalog}
    return m


_PAIRED_METRICS = (("gross_margin", 2), ("revenue", 2),
                   ("consumer_surplus", 2), ("cs_waiter", 2),
                   ("sell_through", 2), ("units_full", 2),
                   ("units_deep", 2), ("salvage_units", 2))


def run_experiment(arm_names: list[str], seasons: int, seed: int,
                   cfg: FashionConfig = DEFAULT_CONFIG) -> dict:
    """N independent seasons; within each, every arm gets the same buy and
    the same shoppers. Fresh calibration noise AND fresh buy error per
    season — the CI averages over miscalibration draws, not one lucky one."""
    per_season: dict[str, list[dict]] = {name: [] for name in arm_names}
    for s_i in range(seasons):
        ms = substream(seed, "season", s_i)
        catalog = build_catalog(cfg, ms)
        depth = planned_depth(catalog, cfg, ms)
        for name in arm_names:
            per_season[name].append(
                run_season(ARMS[name](), catalog, depth, ms, cfg))

    arms = {}
    for name in arm_names:
        rows = per_season[name]
        totals = {k: round(sum(r[k] for r in rows) / seasons, 2)
                  for k in rows[0] if isinstance(rows[0][k], (int, float))}
        sellout = {}
        for style in rows[0]["sellout_week"]:
            wk = [r["sellout_week"][style] for r in rows
                  if r["sellout_week"][style] is not None]
            sellout[style] = {
                "rate": round(len(wk) / seasons, 2),
                "mean_week": round(sum(wk) / len(wk), 1) if wk else None}
        arms[name] = {"per_season_means": totals, "sellout": sellout}

    paired = {}
    base = arm_names[0]
    for name in arm_names[1:]:
        paired[f"{name}_vs_{base}"] = {
            metric: paired_ci([per_season[name][s][metric]
                               - per_season[base][s][metric]
                               for s in range(seasons)], block=1, nd=nd)
            for metric, nd in _PAIRED_METRICS}

    return {
        "fashion_version": FASHION_VERSION,
        "config": {
            "seed": seed, "seasons": seasons, "arms": arm_names,
            "world": {"sigma_buy": cfg.sigma_buy, "sigma_cal": cfg.sigma_cal,
                      "waiter_share": cfg.waiter_share},
            "notes": [
                "one buy at week 0, no restock; both arms work the SAME buy",
                "buy planned against the CLIFF calendar (the industry plan)",
                "one-style shoppers: no cross-style substitution in P0",
                "markdown/1 demand model is myopic (waiters not modeled) and "
                "unlearned (buy-time estimate all season)",
                "discount-only: no arm can transact above MSRP (runner-enforced)",
                "paired seeds: identical buy + shopper stream across arms",
                "seasons are independent replications -> plain t CIs (block=1)",
            ],
        },
        "arms": arms,
        "paired": paired,
        "_per_season": per_season,
    }


GRID_SIGMA_BUY = (0.15, 0.35)
GRID_SIGMA_CAL = (0.0, 0.2)
GRID_WAITER = (0.15, 0.45)


def run_grid(arm_names: list[str], seasons: int, seed: int, out: str) -> int:
    """The pre-registered P0 grid: buy error × calibration noise × waiter
    share, plus a perfect-information control cell (sigma_buy=0, sigma_cal=0,
    waiter_share=0) where the arms SHOULD be close — the anti-claim row."""
    cells = [("control_perfect", FashionConfig(0.0, 0.0, 0.0))]
    for sb in GRID_SIGMA_BUY:
        for sc in GRID_SIGMA_CAL:
            for ws in GRID_WAITER:
                cells.append((f"buy{sb:g}_cal{sc:g}_wait{ws:g}",
                              FashionConfig(sb, sc, ws)))
    grid = {}
    for name, cfg in cells:
        res = run_experiment(arm_names, seasons, seed, cfg)
        cell = {"world": res["config"]["world"],
                "gross_margin": {a: res["arms"][a]["per_season_means"]
                                 ["gross_margin"] for a in arm_names},
                "sell_through": {a: res["arms"][a]["per_season_means"]
                                 ["sell_through"] for a in arm_names},
                "units_deep": {a: res["arms"][a]["per_season_means"]
                               ["units_deep"] for a in arm_names},
                "cs_waiter": {a: res["arms"][a]["per_season_means"]
                              ["cs_waiter"] for a in arm_names},
                "paired": res["paired"]}
        grid[name] = cell
        for k, v in res["paired"].items():
            gm = v["gross_margin"]
            print(f"{name:<24} {k}: margin Δ/season {gm['mean']:>9.2f} "
                  f"CI95 {gm['ci95']} · -70%+ units Δ "
                  f"{v['units_deep']['mean']:>7.2f}")
    with open(out, "w") as f:
        json.dump({"fashion_version": FASHION_VERSION, "seasons": seasons,
                   "seed": seed, "arms": arm_names, "cells": grid}, f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--arms", default="cliff,markdown")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-buy", type=float, default=0.15)
    ap.add_argument("--sigma-cal", type=float, default=0.0)
    ap.add_argument("--waiter-share", type=float, default=0.15)
    ap.add_argument("--grid", action="store_true",
                    help="run the pre-registered buy×cal×waiter grid")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        return run_grid(arm_names, args.seasons, args.seed,
                        args.out or "fashion/results.json")

    cfg = FashionConfig(sigma_buy=args.sigma_buy, sigma_cal=args.sigma_cal,
                        waiter_share=args.waiter_share)
    res = run_experiment(arm_names, args.seasons, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        gm = {n: res["arms"][n]["per_season_means"]["gross_margin"]
              for n in arm_names}
        print(f"wrote {args.out} — gross margin/season by arm: {gm}")
        for k, v in res["paired"].items():
            print(f"  {k}: margin Δ {v['gross_margin']['mean']} "
                  f"CI95 {v['gross_margin']['ci95']} · CS Δ "
                  f"{v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
