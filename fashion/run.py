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

from collections import defaultdict

from fashion.core import paired_ci, substream
from fashion.policies import CliffPolicy, MarkdownPolicy
from fashion.world import (DEFAULT_CONFIG, SIZES, WEEKS, FashionConfig,
                           arrivals_at, build_catalog, planned_depth,
                           sample_return, sample_shopper, waiter_buys_now)

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
                        "revisits", "returns", "returns_restocked",
                        "returns_postseason", "lost_stockout",
                        "buyers_waiter", "buyers_loyal", "cells_sold_out")}
    m.update({k: 0.0 for k in ("revenue", "refunds", "net_revenue",
                               "salvage_revenue", "buy_cost", "gross_margin",
                               "consumer_surplus", "cs_waiter", "cs_loyal",
                               "sell_through", "return_rate_realized")})
    m["units_bought"] = sum(depth.values())
    m["buy_cost"] = sum(n * catalog[st].unit_cost
                        for (st, _sz), n in depth.items())
    sold_prev = {cell: 0 for cell in depth}
    waiting: list = []
    sellout: dict[str, int] = {}
    # scheduled product returns: absolute_week -> [(cell, paid, surplus, waiter)]
    pending: dict[int, list] = defaultdict(list)

    for week in range(WEEKS):
        # Returns due this week land BEFORE pricing, so a returned unit is on
        # the rack at THIS week's price (a full-price sale returned into
        # clearance re-sells at clearance — the mechanism under test).
        for cell, paid, surplus, is_waiter in pending.pop(week, []):
            m["returns"] += 1
            m["refunds"] += paid
            m["consumer_surplus"] -= surplus      # refunded → net surplus ~0
            if is_waiter:
                m["cs_waiter"] -= surplus
            else:
                m["cs_loyal"] -= surplus
            inv[cell] = inv.get(cell, 0) + 1      # back into sellable stock
            m["returns_restocked"] += 1
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
        m["revisits"] += len(waiting)     # waiter re-shop visits (not product returns)
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
                lag = sample_return(master_seed, c.uid, cfg)
                if lag is not None:
                    # identity-keyed: same flag+lag in both arms; only the
                    # refund PRICE and return WEEK differ (paired mechanism).
                    pending[week + lag].append((cell, price, surplus, c.waiter))
            elif c.waiter and week < WEEKS - 1:
                still_waiting.append(c)     # returns weekly until sold out

        waiting = still_waiting
        sold_prev = sold_this
        for style in catalog:
            if style not in sellout and \
                    sum(inv[(style, sz)] for sz in SIZES) == 0:
                sellout[style] = week

    # Returns that arrive AFTER the last selling week never re-enter the rack:
    # refund the buyer, reverse their surplus, and the unit salvages.
    for wk, evts in pending.items():
        for cell, paid, surplus, is_waiter in evts:
            style = cell[0]
            m["returns"] += 1
            m["returns_postseason"] += 1
            m["refunds"] += paid
            m["consumer_surplus"] -= surplus
            if is_waiter:
                m["cs_waiter"] -= surplus
            else:
                m["cs_loyal"] -= surplus
            m["salvage_units"] += 1
            m["salvage_revenue"] += catalog[style].salvage

    for (style, _sz), s in inv.items():
        m["salvage_units"] += s
        m["salvage_revenue"] += s * catalog[style].salvage
    m["cells_sold_out"] = sum(1 for cell, s in inv.items()
                              if s == 0 and depth[cell] > 0)
    # the −70% rung and deeper: the cliff's own clearance price lands exactly
    # in units_d70, so "fewer deep-clearance units" is d70 + d70plus
    m["units_deep"] = m["units_d70"] + m["units_d70plus"]
    # sell-through is GROSS (sale transactions ÷ units bought); with returns a
    # unit can transact more than once, so this can exceed the net kept rate.
    m["sell_through"] = round(100.0 * m["units_sold"] / m["units_bought"], 2) \
        if m["units_bought"] else 0.0
    m["return_rate_realized"] = round(
        100.0 * m["returns"] / m["units_sold"], 2) if m["units_sold"] else 0.0
    # net revenue = gross sale revenue − refunds; margin nets refunds too.
    m["net_revenue"] = m["revenue"] - m["refunds"]
    m["gross_margin"] = m["net_revenue"] + m["salvage_revenue"] - m["buy_cost"]
    for k in ("revenue", "refunds", "net_revenue", "salvage_revenue",
              "buy_cost", "gross_margin", "consumer_surplus", "cs_waiter",
              "cs_loyal"):
        m[k] = round(m[k], 2)
    m["sellout_week"] = {st: sellout.get(st) for st in catalog}
    return m


_PAIRED_METRICS = (("gross_margin", 2), ("revenue", 2), ("net_revenue", 2),
                   ("refunds", 2), ("returns", 2), ("consumer_surplus", 2),
                   ("cs_waiter", 2), ("sell_through", 2), ("units_full", 2),
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
                      "waiter_share": cfg.waiter_share,
                      "return_rate": cfg.return_rate},
            "notes": [
                "one buy at week 0, no restock; both arms work the SAME buy",
                "buy planned against the CLIFF calendar (the industry plan)",
                "one-style shoppers: no cross-style substitution in P0",
                "markdown/1 demand model is myopic (waiters not modeled) and "
                "unlearned (buy-time estimate all season)",
                "discount-only: no arm can transact above MSRP (runner-enforced)",
                "paired seeds: identical buy + shopper stream across arms",
                "seasons are independent replications -> plain t CIs (block=1)",
                "returns: a sale returns w.p. return_rate after a 1-3wk lag, "
                "refunded at PAID price, re-shelved if a selling week remains "
                "(else salvage); return draw keyed on shopper IDENTITY not arm",
                "sell_through / unit buckets are GROSS (a returned-then-resold "
                "unit transacts twice); net kept = units_sold - returns",
            ],
        },
        "arms": arms,
        "paired": paired,
        "_per_season": per_season,
    }


GRID_SIGMA_BUY = (0.15, 0.35)
GRID_SIGMA_CAL = (0.0, 0.2)
GRID_WAITER = (0.15, 0.45)
RETURN_GRID = (0.0, 0.17, 0.26)   # NRF 2024: 0 (P0 repro), 16.9% retail, 26% online apparel


def _grid_cells(return_rate: float = 0.0) -> list[tuple[str, FashionConfig]]:
    """The 9-cell pre-registered grid: a perfect-information control
    (σ_buy=σ_cal=waiters=0, the anti-claim row) plus buy×cal×waiter =
    2×2×2. All cells carry the same `return_rate`."""
    cells = [("control_perfect", FashionConfig(0.0, 0.0, 0.0, return_rate))]
    for sb in GRID_SIGMA_BUY:
        for sc in GRID_SIGMA_CAL:
            for ws in GRID_WAITER:
                cells.append((f"buy{sb:g}_cal{sc:g}_wait{ws:g}",
                              FashionConfig(sb, sc, ws, return_rate)))
    return cells


def run_grid(arm_names: list[str], seasons: int, seed: int, out: str,
             return_rate: float = 0.0) -> int:
    """The pre-registered P0 grid at a single return rate."""
    grid = {}
    for name, cfg in _grid_cells(return_rate):
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
                   "seed": seed, "arms": arm_names, "return_rate": return_rate,
                   "cells": grid}, f, indent=1)
    print(f"wrote {out}")
    return 0


def run_returns_sweep(arm_names: list[str], seasons: int, seed: int,
                      out: str) -> int:
    """THE returns experiment: run the 9-cell markdown-beats-cliff grid at
    each return rate in RETURN_GRID (0 = P0 repro, 0.17 retail, 0.26 online
    apparel) and ask whether the markdown edge SURVIVES returns.

    Because build_catalog / planned_depth do NOT depend on return_rate, a given
    season seed draws the IDENTICAL buy and shopper stream at every r — so the
    per-season markdown−cliff EDGE is paired across r, and we can put a paired
    t-CI on the *change in edge* vs r=0 (a difference-in-differences). No win
    claim is made where a CI includes zero."""
    if arm_names[:2] != ["cliff", "markdown"]:
        print("returns-sweep expects arms=cliff,markdown", file=sys.stderr)
        return 2
    base_cells = _grid_cells(0.0)
    sweep = {}
    for name, cfg0 in base_cells:
        world = {"sigma_buy": cfg0.sigma_buy, "sigma_cal": cfg0.sigma_cal,
                 "waiter_share": cfg0.waiter_share}
        by_r = {}
        edge0 = None
        did = {}
        for r in RETURN_GRID:
            cfg = FashionConfig(cfg0.sigma_buy, cfg0.sigma_cal,
                                cfg0.waiter_share, r)
            res = run_experiment(arm_names, seasons, seed, cfg)
            edge = [res["_per_season"]["markdown"][s]["gross_margin"]
                    - res["_per_season"]["cliff"][s]["gross_margin"]
                    for s in range(seasons)]
            cliff_gm = res["arms"]["cliff"]["per_season_means"]["gross_margin"]
            md_gm = res["arms"]["markdown"]["per_season_means"]["gross_margin"]
            gm_ci = res["paired"]["markdown_vs_cliff"]["gross_margin"]
            pm = res["arms"]
            by_r[f"{r:g}"] = {
                "cliff_gm": cliff_gm, "markdown_gm": md_gm,
                "delta": gm_ci,
                "delta_pct": round(100.0 * gm_ci["mean"] / cliff_gm, 1)
                if cliff_gm else None,
                "survives": gm_ci["ci95"] is not None
                and gm_ci["ci95"][0] > 0,
                "sell_through": {a: pm[a]["per_season_means"]["sell_through"]
                                 for a in arm_names},
                "return_rate_realized": {
                    a: pm[a]["per_season_means"]["return_rate_realized"]
                    for a in arm_names},
                "returns": {a: pm[a]["per_season_means"]["returns"]
                            for a in arm_names},
                "units_deep": {a: pm[a]["per_season_means"]["units_deep"]
                               for a in arm_names},
                "cs_waiter_delta":
                    res["paired"]["markdown_vs_cliff"]["cs_waiter"],
            }
            if r == 0.0:
                edge0 = edge
            else:
                did[f"{r:g}"] = paired_ci(
                    [edge[s] - edge0[s] for s in range(seasons)], nd=2)
        sweep[name] = {"world_base": world, "by_r": by_r, "edge_did": did}
        c = sweep[name]["by_r"]
        print(f"{name:<22} Δ%  r0={c['0']['delta_pct']:>5}  "
              f"r0.17={c['0.17']['delta_pct']:>5}  "
              f"r0.26={c['0.26']['delta_pct']:>5}  | survives "
              f"{c['0']['survives']}/{c['0.17']['survives']}/"
              f"{c['0.26']['survives']}  | DiD@.26 {did['0.26']['mean']:>8} "
              f"{did['0.26']['ci95']}")
    with open(out, "w") as f:
        json.dump({"fashion_version": FASHION_VERSION, "seasons": seasons,
                   "seed": seed, "arms": arm_names,
                   "return_grid": list(RETURN_GRID), "cells": sweep}, f,
                  indent=1)
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
    ap.add_argument("--return-rate", type=float, default=0.0)
    ap.add_argument("--grid", action="store_true",
                    help="run the pre-registered buy×cal×waiter grid")
    ap.add_argument("--returns-grid", action="store_true",
                    help="run the 9-cell grid at each return rate (0/0.17/0.26)")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.returns_grid:
        return run_returns_sweep(arm_names, args.seasons, args.seed,
                                 args.out or "fashion/results.json")

    if args.grid:
        return run_grid(arm_names, args.seasons, args.seed,
                        args.out or "fashion/results.json", args.return_rate)

    cfg = FashionConfig(sigma_buy=args.sigma_buy, sigma_cal=args.sigma_cal,
                        waiter_share=args.waiter_share,
                        return_rate=args.return_rate)
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
