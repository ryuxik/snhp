"""BOBA IC probe (Task #68B) — the capacity-venue CONTRAST to vend/battery.py.

Same three instruments (unilateral deviation probe, sup-over-types, MDE, plus a
STATE-CONDITIONED adaptive liar and a per-issue misreport), pointed at the soft-
capacity world where the seller's reservation is report-DEPENDENT (a freed slot
is worth only its resale, which a claimed outside option can talk down). The
prediction (§3, CRITICAL-ANALYSIS §10): here the leak is not a sup-over-types
subtlety hiding under a ≈0 pooled mean (as at vend) — it is LARGE and shows up
in the POOLED mean itself, and the ADAPTIVE liar (lie only when the queue is
building, i.e. exactly when the shop's disagreement is most manipulable)
concentrates it further.

  python3 -m boba.battery --probe --seeds 20260713,7,20260710,101,42,2026 \
      --days 120 --out boba/battery.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np
from scipy import stats

from boba.policies import (CartPolicy, buyer_disagreement, cart_nash,
                           sticker_boards, strategic_disclosure)
from boba.run import _settle
from boba.world import (DRINK_PRICE, QTY_CAP, TICKS_PER_DAY, TOP_PRICE,
                        BobaConfig, arrivals_at, balk_prob, best_menu_order,
                        bundle_value, close_out, expire_batches, maybe_cook,
                        open_shop, outside_surplus, release_scheduled,
                        sample_consumer, serve_queue, substream)

BATTERY_VERSION = 1
BALK_TIGHT = 0.10      # balk prob above which the shop is "capacity-tight"
OUT_THRESH = 1.0       # $ of outside surplus above which a buyer is "high-outside"

# adaptive = lie only when the queue is building (balk risk >= BALK_TIGHT), the
# regime where the shop's disagreement branch is most manipulable.
STRATEGIES = [
    {"name": "uniform_wtp",       "mode": "uniform",  "factor": 0.7,  "claim_walk": False},
    {"name": "uniform_wtp+walk",  "mode": "uniform",  "factor": 0.7,  "claim_walk": True},
    {"name": "adaptive_wtp+walk", "mode": "adaptive", "factor": 0.7,  "claim_walk": True},
    {"name": "pertopping_wtp",    "mode": "toppings", "factor": 0.7,  "claim_walk": False},
    {"name": "walk_only",         "mode": "uniform",  "factor": 1.0,  "claim_walk": True},
]


def block_ci(diffs, block=5):
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        nb = len(d) // block
        d = d[:nb * block].reshape(nb, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 3), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 3), "ci95": [round(mean - t * se, 3),
                                             round(mean + t * se, 3)],
            "n": n, "sd_block": round(float(d.std(ddof=1)), 4)}


def pooled_block_ci(per_seed, block=5):
    blocks = []
    for series in per_seed:
        d = np.asarray(series, dtype=float)
        if block > 1 and len(d) >= 2 * block:
            nb = len(d) // block
            d = d[:nb * block].reshape(nb, block).mean(axis=1)
        blocks.extend(d.tolist())
    b = np.asarray(blocks, dtype=float)
    n = len(b)
    mean = float(b.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 3), "ci95": None, "n": n}
    se = float(b.std(ddof=1) / math.sqrt(n))
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 3), "ci95": [round(mean - t * se, 3),
                                             round(mean + t * se, 3)],
            "n": n, "sd_block": round(float(b.std(ddof=1)), 4)}


def mde(sd_block, n, alpha=0.05, power=0.80):
    if n < 2:
        return float("nan")
    df = n - 1
    return (float(stats.t.ppf(1 - alpha / 2, df))
            + float(stats.t.ppf(power, df))) * sd_block / math.sqrt(n)


def _disclose(strat, state, consumer):
    f, cw, mode = strat["factor"], strat["claim_walk"], strat["mode"]
    if mode in ("uniform", "adaptive"):
        if mode == "adaptive" and balk_prob(state) < BALK_TIGHT:
            return consumer, None      # truthful when the queue is slack
        return strategic_disclosure(consumer, f, cw)
    if mode == "toppings":
        # understate only toppings (per-issue), drink truthful
        from boba.world import Consumer
        disc = Consumer(fav=consumer.fav, wtp=dict(consumer.wtp),
                        top_wtp={t: v * f for t, v in consumer.top_wtp.items()},
                        flexible=consumer.flexible, qty_decay=consumer.qty_decay,
                        uid=consumer.uid)
        return disc, (consumer if cw else None)
    raise ValueError(mode)


def _welfare(state, consumer, disc, outside_c, broll, pol):
    """The buyer's TRUE realized welfare for a disclosure `disc` against the
    current state, using balk roll `broll`. Never settles — pure evaluation."""
    deal = cart_nash(state, disc, pol.min_gain_abs, pol.min_gain_frac,
                     defer_slots=pol.defer_slots, salvage=pol.salvage,
                     quote_lookers=pol.quote_lookers, outside_consumer=outside_c)
    b = balk_prob(state)
    if deal is not None:
        true_value = bundle_value(consumer, deal.drink, deal.qty, deal.tops)
        surv = (1.0 - b) if deal.slot_ticks == 0 else 1.0
        u_buyer = surv * (true_value - deal.price) \
            + (1.0 - surv) * outside_surplus(consumer) \
            - consumer.defer_cost(deal.slot_ticks)
        d_buyer = buyer_disagreement(state, consumer)
        if u_buyer >= d_buyer - 1e-9:
            if deal.slot_ticks == 0 and broll < b:
                return 0.0, "balk", deal
            realized = true_value - deal.price - consumer.defer_cost(deal.slot_ticks)
            return realized, "cart", deal
    # walk-in fallback (board), same balk roll
    if broll < b:
        return 0.0, "balk", None
    dp, tp = sticker_boards()
    drink, qty, tops, s = best_menu_order(
        consumer, dp, tp, pearls_ok=state.pearl_stock() >= QTY_CAP)
    s_out = outside_surplus(consumer)
    if drink is not None and s > 0 and s >= s_out:
        return s, "board", (drink, qty, tops)
    return (s_out if s_out > 0 else 0.0), "outside", None


def probe_day(pol, master_seed, day, cfg, records):
    state = open_shop(day, cfg.balk_model)
    for tick in range(TICKS_PER_DAY):
        state.tick = tick
        expire_batches(state)
        maybe_cook(state)
        release_scheduled(state)
        serve_queue(state)
        n = arrivals_at(master_seed, day, tick, cfg)
        for k in range(n):
            consumer = sample_consumer(master_seed, day, tick, k, cfg)
            broll = float(np.random.default_rng(
                substream(master_seed, "balk", day, tick, k)).random())
            b_here = balk_prob(state)
            s_out = outside_surplus(consumer)
            h_welf, h_kind, h_deal = _welfare(state, consumer, consumer, None,
                                              broll, pol)
            rec = {"day": day, "tight": b_here >= BALK_TIGHT,
                   "high_out": s_out >= OUT_THRESH, "gains": {}}
            for strat in STRATEGIES:
                disc, outc = _disclose(strat, state, consumer)
                l_welf, _, _ = _welfare(state, consumer, disc, outc, broll, pol)
                rec["gains"][strat["name"]] = round(l_welf - h_welf, 4)
            records.append(rec)
            # settle the HONEST outcome into the world
            if h_kind == "cart" and h_deal is not None:
                _settle(state, {"revenue": 0.0, "ingredient_cost": 0.0, "cups": 0,
                                "toppings": 0, "deals": 0, "consumer_surplus": 0.0,
                                "deferred": 0}, h_deal.drink, h_deal.qty,
                        h_deal.tops, h_deal.price, 0.0, h_deal.slot_ticks)
            elif h_kind == "board" and h_deal is not None:
                drink, qty, tops = h_deal
                price = qty * (DRINK_PRICE[drink] + sum(TOP_PRICE[t] for t in tops))
                _settle(state, {"revenue": 0.0, "ingredient_cost": 0.0, "cups": 0,
                                "toppings": 0, "deals": 0, "consumer_surplus": 0.0,
                                "deferred": 0}, drink, qty, tops, price, 0.0, 0)
    close_out(state)


def run_probe(seeds, days, cfg):
    strata = ["all", "tight", "high_out", "tight_high_out", "slack_lowout"]
    series = {st["name"]: {k: [] for k in strata} for st in STRATEGIES}
    n_probed = {k: 0 for k in strata}
    raw_max = {st["name"]: 0.0 for st in STRATEGIES}

    def instr(rec, key):
        return {"all": True, "tight": rec["tight"], "high_out": rec["high_out"],
                "tight_high_out": rec["tight"] and rec["high_out"],
                "slack_lowout": (not rec["tight"]) and (not rec["high_out"]),
                }[key]

    for seed in seeds:
        recs = []
        for d in range(days):
            probe_day(CartPolicy(), seed, d, cfg, recs)
        for k in strata:
            n_probed[k] += sum(1 for r in recs if instr(r, k))
        for st in STRATEGIES:
            name = st["name"]
            for k in strata:
                perday = [0.0] * days
                for r in recs:
                    if instr(r, k):
                        perday[r["day"]] += r["gains"][name]
                series[name][k].append(perday)
            raw_max[name] = max(raw_max[name],
                                max((r["gains"][name] for r in recs), default=0.0))

    out = {"seeds": seeds, "days": days, "n_probed_by_stratum": n_probed,
           "strategies": {}}
    for st in STRATEGIES:
        name = st["name"]
        srow = {"spec": st, "raw_max_single_buyer_gain": round(raw_max[name], 3),
                "strata": {}}
        for k in strata:
            ci = pooled_block_ci(series[name][k])
            ci["mde_dollar_per_day"] = round(mde(ci.get("sd_block", 0.0),
                                                 ci["n"]), 3) if ci["n"] >= 2 else None
            srow["strata"][k] = ci
        means = {k: srow["strata"][k]["mean"] for k in strata}
        sup = max(means, key=means.get)
        srow["sup_over_types"] = {"stratum": sup, "mean_gain_per_day": means[sup],
                                  "ci95": srow["strata"][sup]["ci95"]}
        srow["pooled_mean_gain_per_day"] = srow["strata"]["all"]["mean"]
        srow["significantly_positive_strata"] = [
            k for k in strata
            if srow["strata"][k]["ci95"] and srow["strata"][k]["ci95"][0] > 0]
        out["strategies"][name] = srow
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="20260713,7,20260710,101,42,2026")
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--flexible-share", type=float, default=0.35)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=args.flexible_share)

    payload = {"battery_version": BATTERY_VERSION, "task": "ic-battery-68B-boba",
               "seeds": seeds, "days": args.days,
               "world": "soft-capacity boba (flexible_share=0.35, no shock); "
                        "attestation OFF; report-DEPENDENT reservation"}
    if args.probe:
        res = run_probe(seeds, args.days, cfg)
        payload["probe"] = res
        print(f"probed buyers by stratum: {res['n_probed_by_stratum']}")
        print(f"  {'strategy':20} {'pooled mean/CI':26} {'SUP stratum':16} {'sup mean/CI':22} {'sig+'}")
        for name, s in res["strategies"].items():
            pm = s["strata"]["all"]; sup = s["sup_over_types"]
            print(f"  {name:20} {pm['mean']:+8.2f} {str(pm['ci95']):18} "
                  f"{sup['stratum']:16} {sup['mean_gain_per_day']:+8.2f} "
                  f"{str(sup['ci95']):18} {s['significantly_positive_strata']}")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(payload, f, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
