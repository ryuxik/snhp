"""SLOT-ECONOMICS experiment runner — paired-seed A/B across pricing arms.

Every arm faces the IDENTICAL customer stream: arrivals, customer draws,
flexibility flags, and no-show rolls depend only on (venue, master_seed,
day, tick, k / uid), never on anything a policy did. Divergence starts
only at each customer's decision against each arm's board or quote — the
treatment effect, isolated. The WORLD carries no overnight state (the
occupancy grid resets at open); since the relief fix the nego arms carry
their HourMarginLearner across days (each day's realized per-hour margins
fold into the EWMA), so their per-day metrics are not strictly
independent draws — the paired CI's 5-day blocks absorb that dependence
as well as day-level noise.

  python3 -m slots.run --venue bar --days 30 --seed 20260710
  python3 -m slots.run --grid --days 30 --seed 20260710   # all venues
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from slots.policies import ARMS
from slots.world import (DEFAULT_CONFIG, SlotConfig, VENUE_NAMES, Booking,
                         arrivals_at, best_board_booking, congestion_ratio,
                         fresh_day, noshow_roll, occupy, release,
                         sample_customer, venue)

SLOTS_VERSION = 2      # v2: relief fix (post-registration, CRITICAL-ANALYSIS §3)


def _book(state, m, cust, start, n, price, cs):
    """Place a booking: claim the span now; settle revenue at SERVICE.
    A booking that starts this very tick is a walk-in — the customer is
    standing there, so it settles (shows) immediately; a future start
    waits in `pending` for its no-show roll."""
    v = state.venue
    dur = n * v.step_ticks
    occupy(state, start, dur)
    b = Booking(uid=cust.uid, start=start, dur=dur, price=price,
                cost=v.unit_cost(n, cust.kind), cs=cs)
    m["bookings"] += 1
    if start == state.tick:
        _settle(m, b, v)
    else:
        state.pending.append(b)
    return b


def _settle(m, b, v):
    m["revenue"] += b.price
    m["cost"] += b.cost
    m["shows"] += 1
    m["consumer_surplus"] += b.cs
    m["sold_unit_ticks"] += b.dur
    # realized margin by hour (spread evenly over the span) — the feed for
    # the nego arm's HourMarginLearner; settled bookings only, so no-shows
    # contribute nothing, exactly as they pay nothing
    hm = m.setdefault("_hour_margin", {})
    per_tick = (b.price - b.cost) / b.dur
    for t in range(b.start, b.start + b.dur):
        h = v.hour_of(t)
        hm[h] = hm.get(h, 0.0) + per_tick


def _due(state, m, master_seed):
    """Reservations coming due this tick: roll the (person-stable)
    no-show. A flake pays nothing and hands the whole span back for
    resale; whatever is not resold perishes — the cost of no-shows is
    borne as dead slot-time, identically across arms."""
    v = state.venue
    still = []
    for b in state.pending:
        if b.start > state.tick:
            still.append(b)
        elif noshow_roll(v, master_seed, state.day, b.uid):
            release(state, b.start, b.dur)
            m["noshows"] += 1
        else:
            _settle(m, b, v)
    state.pending = still


def run_day(policy, venue_name: str, master_seed: int, day: int,
            cfg: SlotConfig = DEFAULT_CONFIG) -> dict:
    v = venue(venue_name)
    m = {"revenue": 0.0, "cost": 0.0, "arrivals": 0, "bookings": 0,
         "shows": 0, "noshows": 0, "lost": 0, "lost_to_outside": 0,
         "consumer_surplus": 0.0, "negotiated": 0, "neg_venue_gain": 0.0,
         "shifted_deals": 0, "shift_ticks": 0, "trimmed_deals": 0,
         "relief_credited": 0.0, "discount_given": 0.0,
         "sold_unit_ticks": 0, "peak_sold_ticks": 0}
    state = fresh_day(v, day)

    for tick in range(v.ticks):
        state.tick = tick
        _due(state, m, master_seed)

        n_new = arrivals_at(v, master_seed, day, tick, cfg)
        m["arrivals"] += n_new
        for k in range(n_new):
            cust = sample_customer(v, master_seed, day, tick, k, cfg)
            if cust is None:
                m["lost"] += 1          # cannot fit before close
                continue

            # ── nego arm: the quote happens first ──
            if getattr(policy, "mode", "board") == "nego":
                deal = policy.quote_for(state, cust)
                if deal is not None and deal.u_buyer >= deal.d_buyer - 1e-9:
                    # rational acceptance, enforced not assumed
                    _book(state, m, cust, deal.start, deal.n, deal.price,
                          deal.cs)
                    m["negotiated"] += 1
                    m["neg_venue_gain"] += deal.u_venue - deal.d_venue
                    m["relief_credited"] += deal.relief
                    m["discount_given"] += deal.list_price - deal.price
                    if deal.shifted:
                        m["shifted_deals"] += 1
                        m["shift_ticks"] += abs(deal.start - cust.desired)
                    if deal.trimmed:
                        m["trimmed_deals"] += 1
                    continue
                # no mutual gain (or buyer declined): fall through to list

            # ── the posted board ──
            mult = policy.mult_of(state)
            start, n, price, sur = best_board_booking(state, cust, mult)
            if start is not None and sur > 0 and sur >= cust.outside:
                _book(state, m, cust, start, n, price, sur)
            elif cust.outside > 0:
                m["lost_to_outside"] += 1
            else:
                m["lost"] += 1

    # the last ticks' reservations all came due inside the loop (start
    # < ticks by construction); anything still pending is a bug.
    assert not state.pending, "pending bookings survived the day"
    # feed the day's realized per-hour margins and final occupancy to arms
    # that learn from their own history (the nego arms' HourMarginLearner)
    hour_margin = m.pop("_hour_margin", {})
    if hasattr(policy, "end_day"):
        policy.end_day(v, hour_margin, state.occupied)
    peak = np.zeros(v.ticks, dtype=bool)
    for h in v.peak_hours:
        peak[v.hidx(h) * 6:(v.hidx(h) + 1) * 6] = True
    m["peak_sold_ticks"] = int(state.occupied[peak].sum())
    # slot-time conservation: sold (accounting) + idle (grid) = capacity.
    # Two independent computations — the tests assert they agree.
    m["idle_unit_ticks"] = int((v.capacity - state.occupied).sum())
    m["margin"] = round(m["revenue"] - m["cost"], 2)
    m["occupancy"] = round(m["sold_unit_ticks"] / (v.capacity * v.ticks), 4)
    for k in ("revenue", "cost", "consumer_surplus", "neg_venue_gain",
              "relief_credited", "discount_given"):
        m[k] = round(m[k], 2)
    return m


def paired_ci(diffs: list[float], block: int = 1) -> dict:
    """Mean paired difference with a 95% t-interval on `block`-day means
    (copied from vend.run; slot days are independent, so blocking only
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


PAIRED_METRICS = ("margin", "revenue", "bookings", "consumer_surplus",
                  "shifted_deals", "sold_unit_ticks", "noshows",
                  "relief_credited", "discount_given")


def run_experiment(arm_names: list[str], venue_name: str, days: int,
                   seed: int, cfg: SlotConfig = DEFAULT_CONFIG) -> dict:
    v = venue(venue_name)
    results = {}
    for name in arm_names:
        policy = ARMS[name]()
        per_day = [run_day(policy, venue_name, seed, d, cfg)
                   for d in range(days)]
        totals = {k: round(sum(m[k] for m in per_day), 2)
                  for k in per_day[0] if isinstance(per_day[0][k], (int, float))}
        totals["occupancy"] = round(
            totals["sold_unit_ticks"] / (v.capacity * v.ticks * days), 4)
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
        "slots_version": SLOTS_VERSION,
        "config": {
            "seed": seed, "days": days, "arms": arm_names,
            "venue": venue_name,
            "world": {"sigma_shock": cfg.sigma_shock,
                      "flexible_share": cfg.flexible_share,
                      "capacity": v.capacity, "ticks": v.ticks,
                      "noshow_prob": v.noshow_prob,
                      "peak_hours": list(v.peak_hours),
                      "congestion_ratio": round(congestion_ratio(v), 3)},
            "notes": [
                "static arm = ratio-appeal inversion makes list the "
                "profit-optimal all-day posted price (strong baseline)",
                "discount-only: no arm prices above list",
                "paired seeds: identical arrival/WTP/flexibility/no-show "
                "streams across arms",
                "D-hat forecast = true structural process without the day "
                "shock (favorable to computed and nego equally)",
                "unsold slot-time perishes; no-shows pay nothing and "
                "release their span at start time",
            ],
        },
        "arms": {n: {"totals": r["totals"]} for n, r in results.items()},
        "paired": paired,
        "_per_day": {n: r["per_day"] for n, r in results.items()},
    }


def run_grid(arm_names: list[str], venue_names: list[str], days: int,
             seed: int, out: str) -> int:
    """The pre-registered grid: flexibility share {0.15, 0.35} x demand
    shock sigma {0, 0.4}, 30 paired days per cell, per venue."""
    grid = {}
    for vn in venue_names:
        cells = {}
        for ss in (0.0, 0.4):
            for fs in (0.15, 0.35):
                cell_name = f"shock{ss:g}_flex{fs:g}"
                cfg = SlotConfig(sigma_shock=ss, flexible_share=fs)
                res = run_experiment(arm_names, vn, days, seed, cfg)
                cells[cell_name] = {
                    "world": res["config"]["world"],
                    "totals": {a: {k: res["arms"][a]["totals"][k]
                                   for k in ("margin", "bookings", "shows",
                                             "noshows", "occupancy",
                                             "shifted_deals", "trimmed_deals",
                                             "relief_credited",
                                             "discount_given",
                                             "consumer_surplus",
                                             "lost_to_outside")}
                               for a in arm_names},
                    "paired": {k: {mm: v[mm] for mm in
                                   ("margin", "consumer_surplus",
                                    "shifted_deals", "sold_unit_ticks",
                                    "relief_credited", "discount_given")}
                               for k, v in res["paired"].items()},
                }
                deltas = {k.split("_vs_")[0]: v["margin"]["mean"]
                          for k, v in res["paired"].items()}
                print(f"{vn:<8} {cell_name:<18} margin Δ/day vs static: {deltas}")
        grid[vn] = {"congestion_ratio": round(congestion_ratio(venue(vn)), 3),
                    "cells": cells}
    with open(out, "w") as f:
        json.dump({"slots_version": SLOTS_VERSION, "days": days,
                   "seed": seed, "arms": arm_names, "venues": grid},
                  f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", choices=VENUE_NAMES, default=None,
                    help="single venue (default: all three in --grid)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--arms", default="static,computed,nego,nego-noshift")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sigma-shock", type=float, default=0.0)
    ap.add_argument("--flexible-share", type=float, default=0.30)
    ap.add_argument("--grid", action="store_true",
                    help="run the flexibility x shock grid (30 days/cell)")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        venues = [args.venue] if args.venue else list(VENUE_NAMES)
        return run_grid(arm_names, venues, args.days, args.seed,
                        args.out or "slots/results.json")

    if not args.venue:
        print("pick --venue or use --grid", file=sys.stderr)
        return 2
    cfg = SlotConfig(sigma_shock=args.sigma_shock,
                     flexible_share=args.flexible_share)
    res = run_experiment(arm_names, args.venue, args.days, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        summary = {n: res["arms"][n]["totals"]["margin"] for n in arm_names}
        print(f"wrote {args.out} — margin by arm: {summary}")
        for k, v in res["paired"].items():
            print(f"  {k}: margin Δ {v['margin']['mean']} CI95 "
                  f"{v['margin']['ci95']} · CS Δ {v['consumer_surplus']['mean']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
