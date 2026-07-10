"""VINTAGE experiment runner — paired-seed A/B across the three arms.

Every arm faces the IDENTICAL store-life: the same one-of-one items arrive
on the same days (attributes depend only on (master, day, k)), the same
browsers walk in, and the same (browser, item) private draws — connection,
WTP, huff roll — fire, memoized in one PairDraws shared by all arms of a
replicate. Divergence starts at prices and offers — the treatment effect,
isolated. Replicates are independent stores (fresh master per rep), so the
headline CIs are plain paired t over rep-level totals (block=1, documented
in core.paired_ci).

  python3 -m vintage.run --grid --days 60 --reps 8 --seed 20260710 \
      --out vintage/results.json

Post-registration (2026-07-10, CRITICAL-ANALYSIS §4): offer/1 fixed (learned
shading/huff/fallback, decline action), retag/1 and retag+offer/1 added
(bidirectional posted retagging). Same seeds; sticker/1 and hazard/1 rows
reproduce the v1 results exactly.
"""
from __future__ import annotations

import argparse
import json
import sys

from vintage.calibration import (CLASS_EDGE, DTS_COHORT_MARGIN, GRID_SHADING,
                                 GRID_SIGMA_TAG, HOLDING_COST, P_HUFF,
                                 TOLERANCE)
from vintage.core import paired_ci, substream
from vintage.policies import ARMS
from vintage.world import (Browser, Item, PairDraws, VintageConfig,
                           browsers_for_day, items_for_day)

VINTAGE_VERSION = 2   # v2: post-reg fixes A (retag arms) + B (offer/1 fixed)

_COUNT_KEYS = ("sourced_units", "units_sold", "browsers", "connections",
               "sales_ask", "sales_offer", "sales_counter", "offers_made",
               "counters_made", "declines", "huffs", "counter_rejects",
               "fallback_sales", "inventory_eod")
_CASH_KEYS = ("revenue", "cogs_sold", "sourced_cost", "holding_cost")


# ── one browser's visit ─────────────────────────────────────────────────────

def visit_board(browser: Browser, inventory: dict[int, Item], policy,
                day: int, cache: PairDraws) -> tuple[int, tuple | None]:
    """sticker/1 and hazard/1: buy the max-surplus connecting item at its
    posted price, or walk. Returns (n_connections, sale) with sale =
    (uid, price, channel) or None."""
    n_conn, best = 0, None
    for uid, item in inventory.items():
        connect, wtp, _ = cache.get(browser, item)
        if not connect:
            continue
        n_conn += 1
        s = wtp - policy.price(item, day)
        if s > 0 and (best is None or s > best[0]):
            best = (s, uid, policy.price(item, day))
    return n_conn, (None if best is None else (best[1], best[2], "ask"))


def visit_offer(browser: Browser, inventory: dict[int, Item], policy,
                day: int, cache: PairDraws) -> tuple[int, tuple | None, dict]:
    """offer/1 (and retag+offer/1): the browser targets the connecting item
    with the greatest OPTIMISTIC surplus (wtp − expected pay, where expected
    pay = the shaded offer capped at the ask) — the piece a haggler actually
    walks up with. Offers land in whole dollars; the ceiling is the CURRENT
    tag (policy.price). If the target's game dies on a rejected counter OR a
    DECLINE they fall back to their best sticker-beating alternative among
    the OTHER pieces (never worse UX than the sticker board, enforced not
    assumed — and a decline is not a free conversion at ask: the declined
    browser never buys the target that visit). A huffed browser leaves the
    store; the huff attaches to being COUNTERED — 'they came with a number'
    — never to a numberless decline. The policy's learner observes every
    counter outcome and every non-huff dead negotiation's continuation."""
    from vintage.engine import counter_response
    flags = {"offer": 0, "counter": 0, "decline": 0, "huff": 0, "reject": 0,
             "fallback": 0}
    conn = []
    for uid, item in inventory.items():
        connect, wtp, huff_roll = cache.get(browser, item)
        if connect:
            conn.append((uid, item, wtp, huff_roll))
    if not conn:
        return 0, None, flags

    def optimistic(t):
        _, item, wtp, _ = t
        return wtp - min(policy.price(item, day), browser.shading * wtp)

    def shop_on(dead_uid):
        """The dead-negotiation continuation: best sticker-beating
        alternative among the OTHER connecting pieces. Feeds the learner's
        F-hat with the realized margin over the fallback piece's own
        waiting value (0 when they buy nothing) — censoring-aware: huffed
        browsers never reach here, so F-hat is learned purely from
        observed continuations."""
        fallback = None
        for uid2, item2, wtp2, _ in conn:
            if uid2 == dead_uid:
                continue
            s = wtp2 - policy.price(item2, day)
            if s > 0 and (fallback is None or s > fallback[0]):
                fallback = (s, uid2, policy.price(item2, day), item2)
        if fallback is None:
            policy.observe_continuation(0.0)
            return None
        policy.observe_continuation(fallback[2]
                                    - policy.wait_value(fallback[3]))
        flags["fallback"] = 1
        return (fallback[1], fallback[2], "ask")

    uid, item, wtp, huff_roll = max(conn, key=optimistic)
    ask = policy.price(item, day)
    offer = min(ask, max(1.0, float(int(browser.shading * wtp))))
    if offer >= ask:                       # they'd pay the tag: plain sale
        return len(conn), (uid, ask, "ask"), flags
    flags["offer"] = 1
    action, price = policy.decide(offer, item)
    if action == "accept":
        return len(conn), (uid, offer, "offer"), flags
    if action == "decline":                # no number given, no huff risked
        flags["decline"] = 1
        return len(conn), shop_on(uid), flags
    flags["counter"] = 1
    if counter_response(wtp, price, huff_roll):
        policy.observe_counter(offer, price, "accept")
        return len(conn), (uid, price, "counter"), flags
    if huff_roll < P_HUFF:                 # walked out on being countered
        policy.observe_counter(offer, price, "huff")
        flags["huff"] = 1
        return len(conn), None, flags
    policy.observe_counter(offer, price, "reject")
    flags["reject"] = 1                    # counter above their WTP: shop on
    return len(conn), shop_on(uid), flags


# ── one store-life of one arm ───────────────────────────────────────────────

def run_store(policy, cfg: VintageConfig, master_seed: int, days: int,
              cache: PairDraws) -> dict:
    inventory: dict[int, Item] = {}
    ledger: dict[int, dict] = {}
    per_day = []
    for day in range(days):
        m = {k: 0 for k in _COUNT_KEYS}
        m.update({k: 0.0 for k in _CASH_KEYS})
        for item in items_for_day(master_seed, day, cfg):
            inventory[item.uid] = item
            ledger[item.uid] = {"item": item, "sold_day": None,
                                "price": None, "channel": None}
            policy.admit(item)
            m["sourced_units"] += 1
            m["sourced_cost"] += item.cost
        policy.day_start(day, inventory)
        browsers = browsers_for_day(master_seed, day, cfg)
        m["browsers"] = len(browsers)
        for b in browsers:
            if policy.uses_offers:
                n_conn, sale, flags = visit_offer(b, inventory, policy, day, cache)
                m["offers_made"] += flags["offer"]
                m["counters_made"] += flags["counter"]
                m["declines"] += flags["decline"]
                m["huffs"] += flags["huff"]
                m["counter_rejects"] += flags["reject"]
                m["fallback_sales"] += flags["fallback"]
            else:
                n_conn, sale = visit_board(b, inventory, policy, day, cache)
            m["connections"] += n_conn
            if sale is not None:
                uid, price, channel = sale
                item = inventory[uid]
                # f-hat learns price/ask against the CURRENT tag (for the
                # retag arms the posted price, not the owner's original)
                ask_now = policy.price(item, day)
                del inventory[uid]
                policy.on_sale(uid, price, len(browsers), ask=ask_now)
                ledger[uid].update(sold_day=day, price=price, channel=channel)
                m["revenue"] += price
                m["cogs_sold"] += item.cost
                m["units_sold"] += 1
                m[f"sales_{channel}"] += 1
        policy.end_of_day(day, inventory, len(browsers))
        m["inventory_eod"] = len(inventory)
        m["holding_cost"] = round(HOLDING_COST * len(inventory), 2)
        for k in _CASH_KEYS:
            m[k] = round(m[k], 2)
        per_day.append(m)
    return {"per_day": per_day, "ledger": ledger, "inventory": inventory}


# ── accounting ──────────────────────────────────────────────────────────────

def item_class(item: Item) -> str:
    """H-V1's decomposition axis: the owner's error on THIS piece."""
    if item.tag <= item.appeal / CLASS_EDGE:
        return "under"
    if item.tag >= item.appeal * CLASS_EDGE:
        return "over"
    return "fair"


def median_dts(ledger: dict, days: int) -> float | None:
    """Median days-to-sale over the fair-exposure cohort (items sourced ≥
    DTS_COHORT_MARGIN days before the horizon). Unsold items are CENSORED,
    not dropped: the median is the smallest d by which half the cohort had
    sold — None (right-censored) if a majority never sold. Dropping the
    unsold would let an arm look fast by only selling its easy pieces."""
    cohort = [r for r in ledger.values()
              if r["item"].arrival_day <= days - DTS_COHORT_MARGIN]
    n = len(cohort)
    sold = sorted(r["sold_day"] - r["item"].arrival_day
                  for r in cohort if r["sold_day"] is not None)
    if n == 0 or 2 * len(sold) < n:
        return None
    return float(sold[(n + 1) // 2 - 1])


def aggregate(run: dict, days: int) -> dict:
    per_day, ledger = run["per_day"], run["ledger"]
    t = {k: sum(d[k] for d in per_day) for k in _COUNT_KEYS + _CASH_KEYS}
    t["inventory_eod"] = per_day[-1]["inventory_eod"]
    t["gross_margin"] = t["revenue"] - t["cogs_sold"]
    t["net_margin"] = t["gross_margin"] - t["holding_cost"]
    t["ending_cost"] = sum(i.cost for i in run["inventory"].values())
    t["ending_appeal"] = sum(i.appeal for i in run["inventory"].values())
    t["sell_through"] = round(100.0 * t["units_sold"] / t["sourced_units"], 2) \
        if t["sourced_units"] else 0.0
    for k in ("revenue", "cogs_sold", "sourced_cost", "holding_cost",
              "gross_margin", "net_margin", "ending_cost", "ending_appeal"):
        t[k] = round(t[k], 2)
    t["median_dts"] = median_dts(ledger, days)
    cohort = [r for r in ledger.values()
              if r["item"].arrival_day <= days - DTS_COHORT_MARGIN]
    t["cohort_n"] = len(cohort)
    t["share_sold_14d"] = round(sum(
        1 for r in cohort
        if r["sold_day"] is not None
        and r["sold_day"] - r["item"].arrival_day <= 14) / len(cohort), 3) \
        if cohort else None
    classes = {}
    for cls in ("under", "fair", "over"):
        recs = [r for r in ledger.values() if item_class(r["item"]) == cls]
        sold = [r for r in recs if r["sold_day"] is not None]
        classes[cls] = {
            "n": len(recs), "sold": len(sold),
            "revenue": round(sum(r["price"] for r in sold), 2),
            "margin": round(sum(r["price"] - r["item"].cost for r in sold), 2),
            "unsold_appeal": round(sum(r["item"].appeal for r in recs
                                       if r["sold_day"] is None), 2)}
    t["classes"] = classes
    return t


# ── the experiment ──────────────────────────────────────────────────────────

_PAIRED_METRICS = (("net_margin", 2), ("gross_margin", 2), ("revenue", 2),
                   ("units_sold", 2), ("holding_cost", 2), ("ending_cost", 2))


def _h2_paired_days(led_a: dict, led_b: dict, days: int) -> float | None:
    """Mean (a − b) days-to-sale over items sold in BOTH arms — the
    selection-proof read on velocity (medians can move on composition
    alone: an arm that also sells the hard pieces adds SLOW sales)."""
    diffs = [led_a[u]["sold_day"] - led_b[u]["sold_day"]
             for u in led_a
             if led_a[u]["sold_day"] is not None
             and led_b[u]["sold_day"] is not None]
    return round(sum(diffs) / len(diffs), 2) if diffs else None


def run_experiment(arm_names: list[str], days: int, reps: int, seed: int,
                   cfg: VintageConfig = VintageConfig()) -> dict:
    per_rep: dict[str, list[dict]] = {n: [] for n in arm_names}
    h2_paired = []
    for r in range(reps):
        master = substream(seed, "rep", r)
        cache = PairDraws()
        ledgers = {}
        for name in arm_names:
            run = run_store(ARMS[name](), cfg, master, days, cache)
            per_rep[name].append(aggregate(run, days))
            ledgers[name] = run["ledger"]
        if "offer" in ledgers and "sticker" in ledgers:
            h2_paired.append(_h2_paired_days(ledgers["offer"],
                                             ledgers["sticker"], days))

    arms = {}
    for name in arm_names:
        rows = per_rep[name]
        totals = {k: round(sum(r[k] for r in rows) / reps, 2)
                  for k in rows[0]
                  if k not in ("median_dts", "share_sold_14d", "classes")
                  and isinstance(rows[0][k], (int, float))}
        meds = [r["median_dts"] for r in rows]
        known = [m for m in meds if m is not None]
        totals["median_dts"] = round(sum(known) / len(known), 1) if known else None
        totals["median_dts_censored_reps"] = meds.count(None)
        shares = [r["share_sold_14d"] for r in rows
                  if r["share_sold_14d"] is not None]
        totals["share_sold_14d"] = round(sum(shares) / len(shares), 3) \
            if shares else None
        arms[name] = {"per_rep_means": totals,
                      "classes": {cls: {k: round(sum(
                          r["classes"][cls][k] for r in rows) / reps, 2)
                          for k in rows[0]["classes"][cls]}
                          for cls in ("under", "fair", "over")}}

    paired = {}
    base = arm_names[0]
    for name in arm_names[1:]:
        paired[f"{name}_vs_{base}"] = {
            metric: paired_ci([per_rep[name][r][metric]
                               - per_rep[base][r][metric]
                               for r in range(reps)], block=1, nd=nd)
            for metric, nd in _PAIRED_METRICS}

    h1 = h2 = None
    if "offer" in per_rep and "sticker" in per_rep:
        d_cls = {cls: [per_rep["offer"][r]["classes"][cls]["margin"]
                       - per_rep["sticker"][r]["classes"][cls]["margin"]
                       for r in range(reps)] for cls in ("under", "fair", "over")}
        h1 = {f"d_margin_{cls}": paired_ci(d_cls[cls]) for cls in d_cls}
        h1["under_minus_over"] = paired_ci(
            [d_cls["under"][r] - d_cls["over"][r] for r in range(reps)])
        h2 = {"paired_both_sold_d_days": paired_ci(
            [x for x in h2_paired if x is not None])}

    # post-reg: the under/fair/over margin decomposition vs the base arm,
    # for EVERY treatment arm (FIX A's pre-registered report is retag/1's
    # under-tag recovery; classes are identical across arms — paired items)
    decomp = {}
    for name in arm_names[1:]:
        d_cls = {cls: [per_rep[name][r]["classes"][cls]["margin"]
                       - per_rep[base][r]["classes"][cls]["margin"]
                       for r in range(reps)] for cls in ("under", "fair", "over")}
        decomp[f"{name}_vs_{base}"] = {
            **{f"d_margin_{cls}": paired_ci(d_cls[cls]) for cls in d_cls},
            "under_minus_over": paired_ci(
                [d_cls["under"][r] - d_cls["over"][r] for r in range(reps)])}

    return {
        "vintage_version": VINTAGE_VERSION,
        "config": {
            "seed": seed, "days": days, "reps": reps, "arms": arm_names,
            "world": {"sigma_tag": cfg.sigma_tag, "shading": cfg.shading},
            "notes": [
                "one-of-one inventory: sold is gone; unsold ages; sourcing continues",
                "browsers see tags; appeal (true value) is hidden from every arm",
                "paired seeds: identical items, browsers, and (browser,item) "
                "draws across arms via one memoized PairDraws per replicate",
                "engine learns rho + per-item appeal posteriors from its OWN "
                "sales history (censoring-aware); it never sees the true "
                "connection rate, tag noise, or shading center",
                "post-reg FIX B: the offer engine LEARNS the population "
                "shading center, huff rate, and fallback value from its own "
                "counter-round history (censoring-aware: huffs update only "
                "the huff rate) and may DECLINE without countering; a "
                "decline carries no huff (the huff attaches to being handed "
                "a NUMBER) and never converts the target at ask",
                "post-reg FIX A: retag/1 and retag+offer/1 may re-tag "
                "POSTED prices UP as well as down (at admission, then at "
                "most weekly per item), bounded by the item's own appeal "
                "posterior; one-of-one goods have no reference price, so "
                "discount-only is out of scope for them by design",
                "engine DOES know sigma_wtp and the store's mean traffic "
                "(flagged, house precedent); the huff level is now only a "
                "weak prior at the true mean",
                "discount-only holds in sticker/offer/hazard: they never "
                "transact above the owner's tag; the retag arms never "
                "transact above their CURRENT posted tag",
                f"counter tolerance {TOLERANCE} (rational boundary); huff "
                f"P={P_HUFF}",
                "replicates are independent stores -> plain t CIs (block=1)",
            ],
        },
        "arms": arms, "paired": paired, "h1": h1, "h2": h2, "decomp": decomp,
        "_per_rep": {n: [{k: v for k, v in row.items() if k != "classes"}
                         for row in rows] for n, rows in per_rep.items()},
    }


def run_grid(arm_names: list[str], days: int, reps: int, seed: int,
             out: str) -> int:
    """The pre-registered grid: tag-noise sigma x shading factor,
    60 paired days per cell (one-of-one needs longer), reps independent
    stores per cell."""
    cells = {}
    for st in GRID_SIGMA_TAG:
        for sh in GRID_SHADING:
            name = f"tag{st:g}_shade{sh:g}"
            res = run_experiment(arm_names, days, reps, seed,
                                 VintageConfig(sigma_tag=st, shading=sh))
            cells[name] = {
                "world": res["config"]["world"],
                "arms": {a: res["arms"][a] for a in arm_names},
                "paired": res["paired"], "h1": res["h1"], "h2": res["h2"],
                "decomp": res["decomp"]}
            for k, v in res["paired"].items():
                nm = v["net_margin"]
                print(f"{name:<18} {k}: net Δ/store {nm['mean']:>8.2f} "
                      f"CI95 {nm['ci95']} · units Δ "
                      f"{v['units_sold']['mean']:>6.2f}")
    with open(out, "w") as f:
        json.dump({"vintage_version": VINTAGE_VERSION, "days": days,
                   "reps": reps, "seed": seed, "arms": arm_names,
                   "cells": cells}, f, indent=1)
    print(f"wrote {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--reps", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--arms", default="sticker,offer,hazard,retag,retag+offer")
    ap.add_argument("--sigma-tag", type=float, default=0.3)
    ap.add_argument("--shading", type=float, default=0.85)
    ap.add_argument("--out", default=None)
    ap.add_argument("--grid", action="store_true",
                    help="run the pre-registered sigma_tag x shading grid")
    args = ap.parse_args(argv)

    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        print(f"unknown arms: {unknown} (have {sorted(ARMS)})", file=sys.stderr)
        return 2

    if args.grid:
        return run_grid(arm_names, args.days, args.reps, args.seed,
                        args.out or "vintage/results.json")

    cfg = VintageConfig(sigma_tag=args.sigma_tag, shading=args.shading)
    res = run_experiment(arm_names, args.days, args.reps, args.seed, cfg)
    out = json.dumps(res, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        nets = {n: res["arms"][n]["per_rep_means"]["net_margin"]
                for n in arm_names}
        print(f"wrote {args.out} — net margin/store by arm: {nets}")
        for k, v in res["paired"].items():
            print(f"  {k}: net Δ {v['net_margin']['mean']} "
                  f"CI95 {v['net_margin']['ci95']}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
