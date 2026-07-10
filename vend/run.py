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
from vend.policies import GvrPolicy, StaticPolicy
from vend.world import (TICKS_PER_DAY, arrivals_at, build_catalog, end_of_day,
                        fresh_machine, hour_of, sample_consumer)

VEND_VERSION = 1
ARMS = {"static": StaticPolicy, "gvr": GvrPolicy}


def run_day(policy, state, catalog, master_seed: int, day: int) -> dict:
    m = {"revenue": 0.0, "cogs_sold": 0.0, "units": 0, "deals": 0,
         "arrivals": 0, "returns": 0, "stockouts": 0, "lost_to_outside": 0,
         "consumer_surplus": 0.0, "quotes": 0}
    return_queue: list[tuple[int, object]] = []

    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        due = [c for t, c in return_queue if t == tick]
        return_queue = [(t, c) for t, c in return_queue if t > tick]

        n_new = arrivals_at(master_seed, day, tick)
        consumers = ([sample_consumer(master_seed, day, tick, k, catalog)
                      for k in range(n_new)] + due)
        m["arrivals"] += n_new
        m["returns"] += len(due)

        for k, consumer in enumerate(consumers):
            board = policy.price_board(state)
            prices = {sku: p for sku, (p, _) in board.items()}
            m["quotes"] += 1

            # Stockout accounting: their favorite (at list) is unstocked.
            fav = max(consumer.wtp, key=lambda s: consumer.wtp[s] - catalog[s].list_price)
            if state.stock(fav) == 0:
                m["stockouts"] += 1

            sku, qty, s_in = consumer.best_bundle(prices) if prices else (None, 0, 0.0)
            if sku is not None:
                qty = min(qty, state.stock(sku))
                s_in = sum(consumer.marginal(sku, i) for i in range(1, qty + 1)) \
                    - qty * prices[sku]

            outside_prices = {s: catalog[s].list_price * 1.15 for s in catalog}
            o_sku, o_qty, o_s = consumer.best_bundle(outside_prices)
            s_out = (o_s - consumer.walk_cost) if o_sku else 0.0

            if sku is not None and s_in > 0 and s_in >= s_out:
                unit_price, why = board[sku]
                quote = make_quote(
                    state, policy.policy_id,
                    seed=substream(master_seed, "q", day, tick, k),
                    items=[QuoteItem(sku=sku, quantity=qty, unit_price=unit_price,
                                     list_price=catalog[sku].list_price)],
                    why=list(why), hour=hour_of(tick))
                state.take(sku, qty)
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

    eod = end_of_day(state)
    m["spoiled_units"] = eod["spoiled_units"]
    m["spoilage_cost"] = eod["spoilage_cost"]
    m["profit"] = round(m["revenue"] - m["cogs_sold"] - m["spoilage_cost"], 2)
    for k in ("revenue", "cogs_sold", "consumer_surplus"):
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


def run_experiment(arm_names: list[str], days: int, seed: int) -> dict:
    catalog = build_catalog()
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        state = fresh_machine("sim-01", catalog)
        per_day = [run_day(policy, state, catalog, seed, d) for d in range(days)]
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260713)
    ap.add_argument("--arms", default="static,gvr")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    res = run_experiment(arm_names, args.days, args.seed)
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
