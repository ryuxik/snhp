"""Block B0 twin-runner — the SAME seeded population walks through a STICKER
world and an SNHP world; the divergence is the product.

  python3 -m block.runner --days 30 --seed 20260710 --regulars 25 \
      --out block/results.json

Paired honesty rule (DESIGN §2): both worlds consume the identical
population stream (block/population.py is a pure function of the seed);
divergence starts only at the decision each shopper makes against each
world's prices. The ledger's paired deltas are therefore treatment effects,
variance-reduced the same way as every vend/fashion experiment.

Choice model, per shopper: best NET utility among
    negotiated vending quote − walk_to_vending      (SNHP world only)
    vending sticker board    − walk_to_vending
    bodega posted prices     − walk_to_bodega
    skip (0)
where walk_to_home = 0 and walk_to_other = the shopper's cross-venue walk
cost. Acceptance mirrors vend's rational-acceptance gate: a negotiated deal
must beat the board AND the real bodega — "never worse UX than static" is
enforced here, not assumed. Ties break toward the deal, then the board,
then the bodega (fixed precedence keeps the stream deterministic).

Regulars (--regulars N): vend/regulars.py's fairness pool rides on the
vending venue in BOTH worlds (identical seeded pools; references and churn
evolve per-world — that endogeneity IS the fairness experiment). A regular
who declines the machine walks to the bodega and buys the overlapping goods
(cola-20oz, chips) if that clears their walk cost — their dollars stay on
the block and on the ledger. B0 keeps vend's psychology machine-scoped:
bodega purchases move money, not reference prices.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from types import SimpleNamespace

from block import calibration, population
from block.ledger import BlockLedger
from block.venues import (BlockConfig, BlockRegularPool, BodegaVenue,
                          VendingVenue, build_block_catalog)
from vend.regulars import regular_board_decision, settle_regular
from vend.world import TICKS_PER_DAY, best_bundle, bundle_value

BLOCK_VERSION = 1
WORLDS = ("sticker", "snhp")


# ── one shopper's resolution ─────────────────────────────────────────────

def _settle_vending(vend_v, ledger, base, sku, qty, price, why,
                    surplus, raw, walk, negotiated):
    ledger.record({"type": "venue_entered", "venue": "vending", **base})
    q = vend_v.settle(sku, qty, price, why, base["day"], base["tick"], base["uid"])
    ledger.record({"type": "deal", "venue": "vending", "sku": sku, "qty": qty,
                   "unit_price": price, "spend": q.total,
                   "cogs": qty * vend_v.catalog[sku].unit_cost,
                   "surplus": surplus, "raw_surplus": raw, "walk": walk,
                   "negotiated": negotiated, **base})


def _settle_bodega(bodega, ledger, base, item, qty, surplus, raw, walk):
    ledger.record({"type": "venue_entered", "venue": "bodega", **base})
    spend, cogs = bodega.settle(item, qty, base["day"])
    ledger.record({"type": "deal", "venue": "bodega", "sku": item, "qty": qty,
                   "unit_price": bodega.prices[item], "spend": spend,
                   "cogs": cogs, "surplus": surplus, "raw_surplus": raw,
                   "walk": walk, "negotiated": False, **base})


def _resolve_shopper(world, sh, vend_v, bodega, ledger, day, tick):
    base = {"world": world, "day": day, "tick": tick, "uid": sh.uid,
            "persona": sh.persona, "kind": "street"}
    ledger.record({"type": "arrival", "home": sh.home, **base})

    walk_v = 0.0 if sh.home == "vending" else sh.cross_walk
    walk_b = 0.0 if sh.home == "bodega" else sh.cross_walk

    b_item, b_qty, b_raw = best_bundle(sh.wtp, bodega.price_board(),
                                       bodega.stock_view())
    u_bodega = (b_raw - walk_b) if b_item is not None else float("-inf")

    board = vend_v.price_board()
    v_prices = {s: p for s, (p, _w) in board.items()}
    v_stock = {s: vend_v.state.stock(s) for s in v_prices}
    v_sku, v_qty, v_raw = best_bundle(sh.wtp, v_prices, v_stock)
    u_board = (v_raw - walk_v) if v_sku is not None else float("-inf")

    if world == "snhp":
        # truthful disclosure: WTP over the machine's SKUs + the RELATIVE
        # hassle of the bodega vs the machine (see VendingVenue.quote)
        disclosed = {s: sh.wtp[s] for s in vend_v.catalog}
        nq = vend_v.quote(disclosed, walk_b - walk_v)
        if nq is not None and nq.outcome is not None:
            o = nq.outcome
            raw = bundle_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price
            u_deal = raw - walk_v
            if u_deal > 0 and u_deal >= u_board and u_deal >= u_bodega:
                _settle_vending(vend_v, ledger, base, o.sku, o.qty,
                                o.unit_price, nq.why, u_deal, raw, walk_v,
                                negotiated=True)
                return

    if v_sku is not None and u_board > 0 and u_board >= u_bodega:
        _settle_vending(vend_v, ledger, base, v_sku, v_qty, v_prices[v_sku],
                        board[v_sku][1], u_board, v_raw, walk_v,
                        negotiated=False)
    elif b_item is not None and u_bodega > 0:
        _settle_bodega(bodega, ledger, base, b_item, b_qty, u_bodega, b_raw,
                       walk_b)
    else:
        ledger.record({"type": "no_sale", **base})


# ── one regular's resolution (vend/run.py's pattern, on the block) ───────

def _resolve_regular(world, reg, vend_v, bodega, ledger, day, tick):
    base = {"world": world, "day": day, "tick": tick, "uid": reg.uid,
            "persona": "regular", "kind": "regular"}
    ledger.record({"type": "arrival", "home": "vending", **base})
    policy = vend_v.policy
    # the regular's real outside option: the goods the bodega ACTUALLY
    # carries, at its actual prices — dollars stay on the block
    outside = {s: bodega.prices[s] for s in bodega.prices if s in reg.wtp}

    if getattr(policy, "mode", "board") == "intent":
        # the buyer's agent discloses EFFECTIVE willingness — raw value
        # capped by reference tolerance (vend fairness-v2, verbatim)
        wtp_eff = {s: min(reg.wtp[s], reg.ref[s] * 1.15 + 0.25)
                   for s in reg.wtp}
        shim = SimpleNamespace(wtp=wtp_eff, walk_cost=reg.walk_cost,
                               uid=reg.uid)
        nq, _ = policy.quote_for(vend_v.state, shim, 1.0)   # regulars honest
        if nq.outcome is not None:
            o = nq.outcome
            raw = bundle_value(reg.wtp, o.sku, o.qty) - o.qty * o.unit_price
            fair = reg.fairness(o.sku, o.unit_price, o.qty,
                                vend_v.catalog[o.sku].list_price)
            if raw + fair > 0:
                _settle_vending(vend_v, ledger, base, o.sku, o.qty,
                                o.unit_price, nq.why, raw, raw, 0.0,
                                negotiated=True)
                settle_regular(reg, o.sku, o.unit_price, o.qty)
                return

    board = vend_v.price_board()
    prices = {s: p for s, (p, _w) in board.items()}
    stock = {s: vend_v.state.stock(s) for s in prices}
    sku, qty, raw, faced = regular_board_decision(reg, prices, stock, outside)
    if sku is not None:
        _settle_vending(vend_v, ledger, base, sku, qty, faced,
                        board[sku][1], raw, raw, 0.0, negotiated=False)
        settle_regular(reg, sku, faced, qty)
        return

    # walked: does the bodega actually get them? (B0: money moves, vend's
    # reference psychology stays machine-scoped)
    o_item, o_qty, o_raw = best_bundle(reg.wtp, outside, bodega.stock_view())
    if o_item is not None and o_raw - reg.walk_cost > 0:
        _settle_bodega(bodega, ledger, base, o_item, o_qty,
                       o_raw - reg.walk_cost, o_raw, reg.walk_cost)
    else:
        ledger.record({"type": "no_sale", **base})


# ── world & twin loops ───────────────────────────────────────────────────

def run_world(world: str, days: int, seed: int, cfg: BlockConfig,
              ledger: BlockLedger, catalog=None) -> dict:
    vend_v = VendingVenue(world, cfg, seed, catalog=catalog)
    bodega = BodegaVenue(world)
    pool = (BlockRegularPool(cfg.regulars, seed, vend_v.catalog)
            if cfg.regulars > 0 else None)
    churn = []
    for day in range(days):
        vend_v.begin_day(day)
        bodega.begin_day(day)
        reg_visits = pool.visits_for_day(day) if pool is not None else {}
        stream = population.day_stream(seed, day)
        for tick in range(TICKS_PER_DAY):
            vend_v.state.tick = tick
            for reg in reg_visits.get(tick, []):
                _resolve_regular(world, reg, vend_v, bodega, ledger, day, tick)
            shoppers = stream[tick]
            vend_v.observe_arrivals(
                tick, sum(1 for s in shoppers if s.home == "vending"))
            for sh in shoppers:
                _resolve_shopper(world, sh, vend_v, bodega, ledger, day, tick)
        eod = vend_v.end_day()
        ledger.close_day(world, "vending", day,
                         eod["spoiled_units"], eod["spoilage_cost"])
        eodb = bodega.end_day()
        ledger.close_day(world, "bodega", day,
                         eodb["spoiled_units"], eodb["spoilage_cost"])
        if pool is not None:
            churn.append({"day": day, "churned": pool.end_day(day),
                          "active": pool.active_count()})
    return {"venues": {"vending": vend_v, "bodega": bodega}, "churn": churn}


def _round2(d: dict) -> dict:
    return {k: (round(v, 2) if isinstance(v, float) else v)
            for k, v in d.items()}


def _venue_block(ledger: BlockLedger, world: str, venue: str, days: int) -> dict:
    per_day = [_round2(ledger.day_metrics(world, venue, d)) for d in range(days)]
    totals: dict = {}
    for d in range(days):
        m = ledger.day_metrics(world, venue, d)
        for k, v in m.items():
            totals[k] = totals.get(k, 0) + v
    return {"totals": _round2(totals), "per_day": per_day}


def run_twin(days: int, seed: int, cfg: BlockConfig = BlockConfig()):
    """Run BOTH worlds on the identical population. Returns
    (results_dict, ledger, worlds) — results carry no wall-clock except
    under 'meta' (popped by the determinism test)."""
    t0 = time.perf_counter()
    ledger = BlockLedger(rents={"vending": VendingVenue.rent_per_day,
                                "bodega": BodegaVenue.rent_per_day})
    catalog = build_block_catalog(cfg, seed)
    worlds = {w: run_world(w, days, seed, cfg, ledger, catalog=catalog)
              for w in WORLDS}

    per_world = {}
    for w in WORLDS:
        per_world[w] = {
            "venues": {v: _venue_block(ledger, w, v, days)
                       for v in ("vending", "bodega")},
            "traffic": [{"day": d, **ledger.traffic(w, d)} for d in range(days)],
            "churn": worlds[w]["churn"],
        }

    results = {
        "block_version": BLOCK_VERSION,
        "config": {
            "seed": seed, "days": days,
            "sigma_cal": cfg.sigma_cal, "anchor_mult": cfg.anchor_mult,
            "regulars": cfg.regulars,
            "shopper_fraction": round(population.SHOPPER_FRACTION, 4),
            "p_vending_home": round(population.P_VENDING_HOME, 4),
            "expected_daily": {k: round(v, 2)
                               for k, v in population.expected_daily().items()},
            "list_prices": {s: l.list_price for s, l in catalog.items()},
            "bodega_prices": {i: p for i, p, _ in calibration.BODEGA_CATALOG},
            "rents_per_day": {"vending": VendingVenue.rent_per_day,
                              "bodega": BodegaVenue.rent_per_day},
            "notes": [
                "paired seeds: identical population stream across worlds (asserted in tests)",
                "sticker = profit-optimal all-day price on a sigma_cal-noised operator estimate",
                "bodega posts calibration prices in BOTH worlds (adopts SNHP in a later phase)",
                "machine's believed outside = Listing.bodega_price (actual bodega for overlapping goods, x1.15 phantom off the true-mu sticker otherwise); consumer acceptance uses the REAL block alternatives",
                "consumer_surplus is net of the cross-venue walk actually incurred",
                "vending pays no rent in calibration (lobby machine); bodega rent $400/day",
                "no day-of-week / day shocks / return queue in B0 (documented in population.py)",
            ],
        },
        "per_world": per_world,
        "paired_deltas": ledger.paired_deltas(days),
        "hud": {
            "shoppers_kept_usd": round(sum(
                ledger.block_day_delta(d, "consumer_surplus")
                for d in range(days)), 2),
            "merchants_earned_usd": round(sum(
                ledger.block_day_delta(d, "margin") for d in range(days)), 2),
        },
    }
    results["meta"] = {"elapsed_s": round(time.perf_counter() - t0, 2)}
    return results, ledger, worlds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--regulars", type=int, default=0)
    ap.add_argument("--sigma-cal", type=float, default=0.15)
    ap.add_argument("--anchor-mult", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cfg = BlockConfig(sigma_cal=args.sigma_cal, anchor_mult=args.anchor_mult,
                      regulars=args.regulars)
    results, ledger, _worlds = run_twin(args.days, args.seed, cfg)

    out = json.dumps(results, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        print(f"wrote {args.out} ({results['meta']['elapsed_s']}s)")
    else:
        print(out)

    for venue in ("vending", "bodega"):
        st = results["per_world"]["sticker"]["venues"][venue]["totals"]
        sn = results["per_world"]["snhp"]["venues"][venue]["totals"]
        pd = results["paired_deltas"][venue]
        print(f"{venue:<8} margin/day sticker {st['margin']/args.days:8.2f}"
              f" · snhp {sn['margin']/args.days:8.2f}"
              f" · Δ {pd['margin']['mean']} CI95 {pd['margin']['ci95']}"
              f" · CS Δ {pd['consumer_surplus']['mean']}")
    print(f"HUD: shoppers kept ${results['hud']['shoppers_kept_usd']}"
          f" · merchants earned ${results['hud']['merchants_earned_usd']}"
          f" (over {args.days} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
