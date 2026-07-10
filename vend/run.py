"""VEND experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL customer stream: arrivals and consumer draws
depend only on (master_seed, day, tick, k), never on anything a policy did.
Divergence starts only at the decision each consumer makes against each
arm's prices — which is the treatment effect, isolated.

  python3 -m vend.run --days 30 --seed 20260713 --arms static,gvr \
      --out vend/results.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from vend.core import QuoteItem, make_quote, substream
from vend.policies import A2APolicy, GvrPolicy, StaticPolicy
from vend.scenario import buyer_value
from vend.world import (DEFAULT_CONFIG, TICKS_PER_DAY, WorldConfig,
                        arrivals_at, build_catalog, day_state, end_of_day,
                        fresh_machine, hour_of, rate_at, sample_consumer)

VEND_VERSION = 1
def _llm_arm():
    from vend.llm_arm import LLMQuotePolicy
    return LLMQuotePolicy()


ARMS = {
    "static": StaticPolicy,
    "gvr": GvrPolicy,
    "a2a": A2APolicy,                                           # attested, all truthful
    "a2a-liars25": lambda: A2APolicy(attest=False, liar_share=0.25),
    "a2a-liars50": lambda: A2APolicy(attest=False, liar_share=0.50),
    "a2a-liars100": lambda: A2APolicy(attest=False, liar_share=1.00),
    "llm": _llm_arm,       # P2: LLM-priced machine (API spend; not byte-deterministic)
}


def run_day(policy, state, catalog, master_seed: int, day: int,
            cfg: WorldConfig = DEFAULT_CONFIG) -> dict:
    m = {"revenue": 0.0, "cogs_sold": 0.0, "units": 0, "deals": 0,
         "arrivals": 0, "returns": 0, "stockouts": 0, "lost_to_outside": 0,
         "consumer_surplus": 0.0, "quotes": 0,
         "negotiated": 0, "neg_machine_gain": 0.0, "liar_deals": 0}
    return_queue: list[tuple[int, object]] = []

    # what the policy may know today: the calendar (public) + its learner
    ds = day_state(cfg, master_seed, day)
    learner = getattr(policy, "learner", None)
    if hasattr(policy, "dow_mult"):
        policy.dow_mult = ds.dow_mult
    if learner:
        learner.begin_day()

    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        due = [c for t, c in return_queue if t == tick]
        return_queue = [(t, c) for t, c in return_queue if t > tick]

        n_new = arrivals_at(master_seed, day, tick, cfg)
        if learner:
            # base = the KNOWN expectation (rate curve × calendar); the
            # posterior tracks the residual day shock
            learner.observe_arrivals(rate_at(tick) / 6.0 * ds.dow_mult, n_new)
        consumers = ([sample_consumer(master_seed, day, tick, k, catalog, cfg)
                      for k in range(n_new)] + due)
        m["arrivals"] += n_new
        m["returns"] += len(due)

        for k, consumer in enumerate(consumers):
            m["quotes"] += 1

            # Stockout accounting: their favorite (at list) is unstocked.
            fav = max(consumer.wtp, key=lambda s: consumer.wtp[s] - catalog[s].list_price)
            if state.stock(fav) == 0:
                m["stockouts"] += 1

            outside_prices = {s: catalog[s].list_price * 1.15 for s in catalog}
            o_sku, o_qty, o_s = consumer.best_bundle(outside_prices)
            s_out = (o_s - consumer.walk_cost) if o_sku else 0.0

            # ── intent arms: the brokered A2A negotiation happens first ──
            if getattr(policy, "mode", "board") == "intent":
                liar_roll = float(np.random.default_rng(
                    substream(master_seed, "liar", day, tick, k)).random())
                nq, lied = policy.quote_for(state, consumer, liar_roll)
                if nq.outcome is not None:
                    o = nq.outcome
                    s_true = buyer_value(consumer.wtp, o.sku, o.qty) \
                        - o.qty * o.unit_price
                    if s_true > 0 and s_true >= s_out:
                        quote = make_quote(
                            state, policy.policy_id,
                            seed=substream(master_seed, "q", day, tick, k),
                            items=[QuoteItem(o.sku, o.qty, o.unit_price,
                                             catalog[o.sku].list_price)],
                            why=nq.why, hour=hour_of(tick))
                        state.take(o.sku, o.qty)
                        if learner:
                            learner.sold(o.sku, o.qty)
                        m["revenue"] += quote.total
                        m["cogs_sold"] += o.qty * catalog[o.sku].unit_cost
                        m["units"] += o.qty
                        m["deals"] += 1
                        m["negotiated"] += 1
                        m["neg_machine_gain"] += nq.u_machine - nq.d_machine
                        m["liar_deals"] += int(lied)
                        m["consumer_surplus"] += s_true
                        continue
                # no mutual gain (or buyer declined): fall through to stickers

            board = policy.price_board(state)
            prices = {sku: p for sku, (p, _) in board.items()}

            sku, qty, s_in = consumer.best_bundle(prices) if prices else (None, 0, 0.0)
            if sku is not None:
                qty = min(qty, state.stock(sku))
                s_in = sum(consumer.marginal(sku, i) for i in range(1, qty + 1)) \
                    - qty * prices[sku]

            if sku is not None and s_in > 0 and s_in >= s_out:
                unit_price, why = board[sku]
                quote = make_quote(
                    state, policy.policy_id,
                    seed=substream(master_seed, "q", day, tick, k),
                    items=[QuoteItem(sku=sku, quantity=qty, unit_price=unit_price,
                                     list_price=catalog[sku].list_price)],
                    why=list(why), hour=hour_of(tick))
                state.take(sku, qty)
                if learner:
                    learner.sold(sku, qty)
                m["revenue"] += quote.total
                m["cogs_sold"] += qty * catalog[sku].unit_cost
                m["units"] += qty
                m["deals"] += 1
                m["consumer_surplus"] += s_in
            else:
                if s_out > 0:
                    m["lost_to_outside"] += 1
                rng = np.random.default_rng(substream(master_seed, "ret", day, tick, k))
                if rng.random() < consumer.patience:
                    delay = int(rng.integers(6, 24))
                    if tick + delay < TICKS_PER_DAY:
                        return_queue.append((tick + delay, consumer))

    if learner:
        learner.end_day()
    eod = end_of_day(state, cfg, master_seed)
    m["spoiled_units"] = eod["spoiled_units"]
    m["spoilage_cost"] = eod["spoilage_cost"]
    m["profit"] = round(m["revenue"] - m["cogs_sold"] - m["spoilage_cost"], 2)
    for k in ("revenue", "cogs_sold", "consumer_surplus", "neg_machine_gain"):
        m[k] = round(m[k], 2)
    return m


def paired_ci(diffs: list[float]) -> dict:
    """Mean paired difference with a 95% t-interval."""
    d = np.asarray(diffs, dtype=float)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, 2), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 2),
            "ci95": [round(mean - t * se, 2), round(mean + t * se, 2)], "n": n}


def run_experiment(arm_names: list[str], days: int, seed: int,
                   cfg: WorldConfig = DEFAULT_CONFIG) -> dict:
    catalog = build_catalog(cfg, seed)
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        state = fresh_machine("sim-01", catalog, cfg, seed)
        per_day = [run_day(policy, state, catalog, seed, d, cfg)
                   for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        results[name] = {"totals": totals, "per_day": per_day}

    paired = {}
    base = arm_names[0]
    for name in arm_names[1:]:
        paired[f"{name}_vs_{base}"] = {
            metric: paired_ci([results[name]["per_day"][d][metric]
                               - results[base]["per_day"][d][metric]
                               for d in range(days)])
            for metric in ("profit", "revenue", "consumer_surplus",
                           "spoilage_cost", "units")
        }

    return {
        "vend_version": VEND_VERSION,
        "config": {
            "seed": seed, "days": days, "arms": arm_names,
            "world": {"sigma_cal": cfg.sigma_cal, "sigma_rate": cfg.sigma_rate,
                      "sigma_wtp": cfg.sigma_wtp, "dow": cfg.dow,
                      "glut_prob": cfg.glut_prob},
            "list_prices": {s: l.list_price for s, l in catalog.items()},
            "notes": [
                "static arm = PROFIT-optimal all-day single price (strong baseline)",
                "all arms maximize profit (margin), not revenue",
                "machine's demand model = the true one (favorable to dynamic arms)",
                "discount-only: no arm can price above list (type-enforced)",
                "paired seeds: identical customer streams across arms",
            ],
        },
        "arms": {n: {"totals": r["totals"]} for n, r in results.items()},
        "paired": paired,
        "_per_day": {n: r["per_day"] for n, r in results.items()},
    }


def run_grid(arm_names: list[str], days: int, seed: int, out: str) -> int:
    """The P1.5 pre-registered grid: operator miscalibration × demand shock,
    with the office-tower calendar and glut days ON (that's the realistic
    texture the sticker can't see). Cell (0, 0) with dow/glut off replicates
    P0/P1 exactly and runs first as the control."""
    cells = [("control", WorldConfig())]
    for sc in (0.0, 0.15, 0.30):
        for sr in (0.0, 0.30, 0.60):
            cells.append((f"cal{sc:g}_shock{sr:g}",
                          WorldConfig(sigma_cal=sc, sigma_rate=sr,
                                      sigma_wtp=sr / 2, dow=True,
                                      glut_prob=0.15)))
    grid = {}
    for name, cfg in cells:
        res = run_experiment(arm_names, days, seed, cfg)
        cell = {"world": res["config"]["world"],
                "profit": {a: res["arms"][a]["totals"]["profit"] for a in arm_names},
                "paired": {k: {"profit": v["profit"],
                               "consumer_surplus": v["consumer_surplus"]}
                           for k, v in res["paired"].items()}}
        grid[name] = cell
        deltas = {k: v["profit"]["mean"] for k, v in res["paired"].items()}
        print(f"{name:<22} profit Δ/day vs {arm_names[0]}: {deltas}")
    with open(out, "w") as f:
        json.dump({"vend_version": VEND_VERSION, "days": days, "seed": seed,
                   "arms": arm_names, "cells": grid}, f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260713)
    ap.add_argument("--arms", default="static,gvr")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-cal", type=float, default=0.0)
    ap.add_argument("--sigma-rate", type=float, default=0.0)
    ap.add_argument("--sigma-wtp", type=float, default=0.0)
    ap.add_argument("--dow", action="store_true")
    ap.add_argument("--glut", type=float, default=0.0)
    ap.add_argument("--grid", action="store_true",
                    help="run the P1.5 miscalibration × shock grid")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        return run_grid(arm_names, args.days, args.seed,
                        args.out or "vend/grid.json")

    cfg = WorldConfig(sigma_cal=args.sigma_cal, sigma_rate=args.sigma_rate,
                      sigma_wtp=args.sigma_wtp, dow=args.dow,
                      glut_prob=args.glut)
    res = run_experiment(arm_names, args.days, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        summary = {n: res["arms"][n]["totals"]["profit"] for n in arm_names}
        print(f"wrote {args.out} — profit by arm: {summary}")
        for k, v in res["paired"].items():
            print(f"  {k}: profit Δ {v['profit']['mean']} CI95 {v['profit']['ci95']}"
                  f" · CS Δ {v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
