"""BOBA experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL customer stream: arrivals, consumer draws,
flexibility flags, and balk-roll uniforms depend only on (master_seed, day,
tick, k), never on anything a policy did. Divergence starts only at each
consumer's decision against each arm's prices/quotes — the treatment
effect, isolated. Days carry no overnight state (batches are tossed at
close, the queue clears), so per-day metrics are independent draws; the
paired CI still uses 5-day blocks, which is conservative.

  python3 -m boba.run --days 30 --seed 20260710 --grid
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from boba.policies import (CartPolicy, ComputedMenu, MenuPolicy, StaticMenu,
                           buyer_disagreement, cart_nash, strategic_disclosure)
from boba.world import (DRINK_COST, DRINK_PRICE, PEAK_HOURS, QTY_CAP,
                        RENT_PER_DAY,
                        TICKS_PER_DAY, TOP_COST, BobaConfig, DEFAULT_CONFIG,
                        arrivals_at, balk_prob, best_menu_order, bundle_value,
                        close_out, expected_wait_minutes, expire_batches,
                        hour_of, maybe_cook, open_shop, outside_surplus,
                        release_scheduled, sample_consumer, serve_queue,
                        substream, take_pearls)

BOBA_VERSION = 1

ARMS = {
    "static": StaticMenu, "computed": ComputedMenu, "cart": CartPolicy,
    "menu": MenuPolicy,
    "menu-no-defer": lambda: MenuPolicy(defer_tiers=False),
    # BOBA #52: the capacity-smoothing ablation (pickup slots OFF) — the lever
    # is (cart − cart-nodefer), a within-model paired diff robust to the
    # balk-model baseline level.
    "cart-nodefer": lambda: CartPolicy(defer_slots=False),
    # BOBA P1a: stable-identity liar sweep (mirrors vend's a2a-liarsNN)
    "cart-liars25": lambda: CartPolicy(attest=False, liar_share=0.25),
    "cart-liars50": lambda: CartPolicy(attest=False, liar_share=0.50),
    "cart-liars100": lambda: CartPolicy(attest=False, liar_share=1.00),
    # BOBA P1a fix (#58): same liar sweep, observable-market-price floor ON
    "cart-liars25-floor": lambda: CartPolicy(attest=False, liar_share=0.25,
                                             market_floor=True),
    "cart-liars50-floor": lambda: CartPolicy(attest=False, liar_share=0.50,
                                             market_floor=True),
    "cart-liars100-floor": lambda: CartPolicy(attest=False, liar_share=1.00,
                                              market_floor=True),
}


def _settle(state, m, drink, qty, tops, price, surplus, slot_ticks=0):
    """Book a sale: revenue at the quoted total, ingredients at TRUE cost
    (the pearls c_eff=0 salvage logic steers decisions, never accounting —
    waste is charged when batches actually expire), pearls reserved at
    order time, drinks queued at their pickup slot."""
    m["revenue"] += price
    m["ingredient_cost"] += qty * (DRINK_COST[drink]
                                   + sum(TOP_COST[t] for t in tops))
    m["cups"] += qty
    m["toppings"] += qty * len(tops)
    m["deals"] += 1
    m["consumer_surplus"] += surplus
    if "pearls" in tops:
        take_pearls(state, qty)
    if slot_ticks > 0:
        due = min(state.tick + slot_ticks, TICKS_PER_DAY - 1)
        state.scheduled[due] = state.scheduled.get(due, 0) + qty
        m["deferred"] += 1
    else:
        state.queue.append(qty)


def run_day(policy, master_seed: int, day: int,
            cfg: BobaConfig = DEFAULT_CONFIG) -> dict:
    m = {"revenue": 0.0, "ingredient_cost": 0.0, "waste_cost": 0.0,
         "cups": 0, "toppings": 0, "deals": 0, "arrivals": 0,
         "balks": 0, "peak_balks": 0, "lost": 0, "deferred": 0,
         "negotiated": 0, "neg_shop_gain": 0.0, "consumer_surplus": 0.0,
         "peak_wait_sum": 0.0, "peak_arrivals": 0, "batches_cooked": 0,
         "liar_deals": 0}
    state = open_shop(day, cfg.balk_model)

    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        m["waste_cost"] += expire_batches(state)
        maybe_cook(state)                 # the operator's gut check
        release_scheduled(state)
        serve_queue(state)

        n = arrivals_at(master_seed, day, tick, cfg)
        m["arrivals"] += n
        for k in range(n):
            consumer = sample_consumer(master_seed, day, tick, k, cfg)
            peak = hour_of(tick) in PEAK_HOURS
            if peak:
                m["peak_wait_sum"] += expected_wait_minutes(state)
                m["peak_arrivals"] += 1

            # ── cart arm: the app quote happens BEFORE the walk-in balk ──
            if getattr(policy, "mode", "board") == "cart":
                # BOBA P1a: liar identity is a property of the PERSON
                # (stable across the day, keyed on uid, policy-independent
                # like vend's "liarid" stream) — never a property of the
                # policy's own randomness. attest defaults True (P0
                # arms, and MenuPolicy, which has no attest attr at all)
                # so this branch is a no-op — byte-identical to P0.
                attest = getattr(policy, "attest", True)
                liar_share = getattr(policy, "liar_share", 0.0)
                lied = False
                if not attest and liar_share > 0.0:
                    liar_roll = float(np.random.default_rng(
                        substream(master_seed, "liarid", consumer.uid)).random())
                    lied = liar_roll < liar_share
                if lied:
                    disclosed, outside_c = strategic_disclosure(
                        consumer, policy.attack_wtp_factor,
                        policy.attack_claim_walk)
                    deal = cart_nash(state, disclosed, policy.min_gain_abs,
                                     policy.min_gain_frac,
                                     defer_slots=policy.defer_slots,
                                     salvage=policy.salvage,
                                     quote_lookers=policy.quote_lookers,
                                     outside_consumer=outside_c,
                                     market_floor=getattr(
                                         policy, "market_floor", False))
                else:
                    deal = policy.quote_for(state, consumer)
                if deal is not None:
                    if lied:
                        # the deal was PRICED on a lie; the real person
                        # accepts/consumes on REAL preferences — never
                        # trust deal.value/u_buyer/d_buyer for a liar
                        true_value = bundle_value(consumer, deal.drink,
                                                  deal.qty, deal.tops)
                        surv = (1.0 - balk_prob(state)) \
                            if deal.slot_ticks == 0 else 1.0
                        u_buyer = surv * (true_value - deal.price) \
                            + (1.0 - surv) * outside_surplus(consumer) \
                            - consumer.defer_cost(deal.slot_ticks)
                        d_buyer = buyer_disagreement(state, consumer)
                        deal_value = true_value
                    else:
                        u_buyer, d_buyer, deal_value = \
                            deal.u_buyer, deal.d_buyer, deal.value
                    if u_buyer >= d_buyer - 1e-9:
                        # rational acceptance, enforced not assumed (TRUE
                        # utilities, always — a lie can win a quote, never
                        # a sale the buyer's real self wouldn't take)
                        if deal.slot_ticks == 0:
                            # a right-now app order still means standing in
                            # that line: it faces the SAME balk roll as a
                            # walk-in
                            roll = float(np.random.default_rng(
                                substream(master_seed, "balk", day, tick, k)).random())
                            if roll < balk_prob(state):
                                m["balks"] += 1
                                if peak:
                                    m["peak_balks"] += 1
                                continue
                        realized = deal_value - deal.price \
                            - consumer.defer_cost(deal.slot_ticks)
                        _settle(state, m, deal.drink, deal.qty, deal.tops,
                                deal.price, realized, deal.slot_ticks)
                        m["negotiated"] += 1
                        m["neg_shop_gain"] += deal.u_shop - deal.d_shop
                        m["liar_deals"] += int(lied)
                        continue

            # ── walk-in: balk BEFORE ordering, then shop the board ──
            b = balk_prob(state)
            roll = float(np.random.default_rng(
                substream(master_seed, "balk", day, tick, k)).random())
            if roll < b:
                m["balks"] += 1
                if peak:
                    m["peak_balks"] += 1
                continue
            drink_prices, top_prices = policy.boards(state)
            drink, qty, tops, s = best_menu_order(
                consumer, drink_prices, top_prices,
                pearls_ok=state.pearl_stock() >= QTY_CAP)
            s_out = outside_surplus(consumer)
            if drink is not None and s > 0 and s >= s_out:
                price = round(qty * (drink_prices[drink]
                                     + sum(top_prices[t] for t in tops)), 2)
                _settle(state, m, drink, qty, tops, price, s)
            else:
                m["lost"] += 1

    m["waste_cost"] += close_out(state)   # 22:00 wash-up: leftover pearls
    m["batches_cooked"] = state.batches_cooked
    m["margin"] = round(m["revenue"] - m["ingredient_cost"] - m["waste_cost"], 2)
    m["rent"] = RENT_PER_DAY              # reported alongside, not netted
    m["attach_rate"] = round(m["toppings"] / m["cups"], 3) if m["cups"] else 0.0
    m["avg_peak_wait"] = round(m["peak_wait_sum"] / m["peak_arrivals"], 2) \
        if m["peak_arrivals"] else 0.0
    for k in ("revenue", "ingredient_cost", "waste_cost",
              "consumer_surplus", "neg_shop_gain", "peak_wait_sum"):
        m[k] = round(m[k], 2)
    return m


def paired_ci(diffs: list[float], block: int = 1) -> dict:
    """Mean paired difference with a 95% t-interval on `block`-day means
    (copied from vend.run; boba days are independent, so blocking only
    widens the CI — conservative)."""
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


PAIRED_METRICS = ("margin", "revenue", "cups", "consumer_surplus",
                  "peak_balks", "waste_cost", "deferred", "toppings")


def run_experiment(arm_names: list[str], days: int, seed: int,
                   cfg: BobaConfig = DEFAULT_CONFIG) -> dict:
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        per_day = [run_day(policy, seed, d, cfg) for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        totals["attach_rate"] = round(totals["toppings"] / totals["cups"], 3) \
            if totals["cups"] else 0.0
        totals["avg_peak_wait"] = round(
            totals["peak_wait_sum"] / totals["peak_arrivals"], 2) \
            if totals["peak_arrivals"] else 0.0
        results[name] = {"totals": totals, "per_day": per_day}

    paired = {}
    base = arm_names[0]
    for name in arm_names[1:]:
        paired[f"{name}_vs_{base}"] = {
            metric: paired_ci([results[name]["per_day"][d][metric]
                               - results[base]["per_day"][d][metric]
                               for d in range(days)], block=5)
            for metric in PAIRED_METRICS
        }

    return {
        "boba_version": BOBA_VERSION,
        "config": {
            "seed": seed, "days": days, "arms": arm_names,
            "world": {"sigma_shock": cfg.sigma_shock,
                      "flexible_share": cfg.flexible_share},
            "menu": dict(DRINK_PRICE),
            "rent_per_day": RENT_PER_DAY,
            "notes": [
                "static arm = the posted calibration menu; appeal is inverted "
                "so that menu IS the profit-optimal all-day posted price",
                "discount-only: no arm prices above the menu",
                "paired seeds: identical arrival/WTP/flexibility streams",
                "computed arm's demand model = the true process (favorable)",
                "cart quotes fire BEFORE the walk-in balk (app ordering); "
                "now-slot deals still face the same balk roll",
                "margin is pre-rent; rent reported alongside",
            ],
        },
        "arms": {n: {"totals": r["totals"]} for n, r in results.items()},
        "paired": paired,
        "_per_day": {n: r["per_day"] for n, r in results.items()},
    }


def run_grid(arm_names: list[str], days: int, seed: int, out: str) -> int:
    """The pre-registered P0 grid: demand shock × pickup flexibility.
    30 paired days per cell."""
    grid = {}
    for ss in (0.0, 0.4):
        for fs in (0.15, 0.35):
            name = f"shock{ss:g}_flex{fs:g}"
            cfg = BobaConfig(sigma_shock=ss, flexible_share=fs)
            res = run_experiment(arm_names, days, seed, cfg)
            cell = {"world": res["config"]["world"],
                    "margin": {a: res["arms"][a]["totals"]["margin"]
                               for a in arm_names},
                    "totals": {a: {k: res["arms"][a]["totals"][k]
                                   for k in ("margin", "cups", "peak_balks",
                                             "waste_cost", "deferred",
                                             "attach_rate", "avg_peak_wait",
                                             "consumer_surplus")}
                               for a in arm_names},
                    "paired": {k: {mm: v[mm] for mm in
                                   ("margin", "consumer_surplus", "peak_balks",
                                    "waste_cost", "toppings", "deferred")}
                               for k, v in res["paired"].items()}}
            grid[name] = cell
            deltas = {k: v["margin"]["mean"] for k, v in res["paired"].items()}
            print(f"{name:<18} margin Δ/day vs {arm_names[0]}: {deltas}")
    with open(out, "w") as f:
        json.dump({"boba_version": BOBA_VERSION, "days": days, "seed": seed,
                   "arms": arm_names, "rent_per_day": RENT_PER_DAY,
                   "cells": grid}, f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--arms", default="static,computed,cart")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-shock", type=float, default=0.0)
    ap.add_argument("--flexible-share", type=float, default=0.30)
    ap.add_argument("--grid", action="store_true",
                    help="run the shock × flexibility grid (30 days/cell)")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        return run_grid(arm_names, args.days, args.seed,
                        args.out or "boba/results.json")

    cfg = BobaConfig(sigma_shock=args.sigma_shock,
                     flexible_share=args.flexible_share)
    res = run_experiment(arm_names, args.days, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        summary = {n: res["arms"][n]["totals"]["margin"] for n in arm_names}
        print(f"wrote {args.out} — margin by arm: {summary}")
        for k, v in res["paired"].items():
            print(f"  {k}: margin Δ {v['margin']['mean']} CI95 {v['margin']['ci95']}"
                  f" · CS Δ {v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
