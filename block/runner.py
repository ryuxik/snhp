"""Block twin-runner — the SAME seeded population walks through a STICKER
world and an SNHP world; the divergence is the product. B1/B2: all four
venues (vending, bodega, boba, fashion) on one clock.

  python3 -m block.runner --days 30 --seed 20260710 --regulars 25 \
      --out block/results.json
  python3 -m block.runner --days 30 --seed 20260710 --regulars 25 \
      --bodega-adopts --out block/results-adopt.json

Paired honesty rule (DESIGN §2): both worlds consume the identical
population stream (block/population.py is a pure function of the seed);
divergence starts only at the decision each shopper makes against each
world's prices. The ledger's paired deltas are therefore treatment effects,
variance-reduced the same way as every vend/fashion experiment. The one
earned exception: fashion waiters RETURN weekly only if they declined, so
return visits (kind="return") diverge per-world by design — the pairing
test covers every other arrival.

Choice model, per STREET shopper (home vending/bodega): best NET utility
among
    negotiated vending quote − walk_to_vending      (SNHP world only)
    negotiated bodega quote  − walk_to_bodega       (SNHP + bodega_adopts)
    vending sticker board    − walk_to_vending
    bodega posted prices     − walk_to_bodega
    skip (0)
where walk_to_home = 0 and walk_to_other = the shopper's cross-venue walk
cost. Acceptance mirrors vend's rational-acceptance gate: a negotiated deal
must beat every posted alternative — "never worse UX than static" is
enforced here, not assumed. Ties break by fixed precedence (vending deal,
bodega deal, vending board, bodega board) to keep the stream deterministic;
with bodega_adopts=False this reproduces B0's decision logic exactly.

BOBA shoppers (home boba) run boba/run's loop on the block: in the SNHP
world the cart quote fires BEFORE the walk-in balk (the order is a cart on
a phone), a now-slot deal still faces the same balk roll; otherwise they
balk-or-shop the posted menu against the coffee shop next door
(boba/world.OUTSIDE_MARKUP — the markup IS the friction).

FASHION shoppers (home fashion) shop ONE style in ONE size against the
standing weekly board; strategic waiters use fashion/world's one-step
lookahead and, if they decline, return at the next week boundary (venue
waiting list; processed FIFO at tick 0 of the boundary day).

Regulars (--regulars N): vend/regulars.py's fairness pool rides on the
vending venue in BOTH worlds, exactly as in B0 (identical seeded pools;
references and churn evolve per-world). A regular who declines the machine
walks to the bodega and buys the overlapping goods off the POSTED board if
that clears their walk cost — regulars keep the posted-board path even when
the bodega adopts (vend's psychology stays machine-scoped; documented).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from types import SimpleNamespace

import numpy as np

from block import calibration, population
from block.ledger import BlockLedger
from block.venues import (BlockConfig, BlockRegularPool, BobaVenue,
                          BodegaVenue, FashionVenue, VendingVenue,
                          build_block_catalog, build_fashion_plan)
from boba import world as boba_world
from fashion.world import decay as fashion_decay, waiter_buys_now
from vend.core import substream
from vend.regulars import regular_board_decision, settle_regular
from vend.world import TICKS_PER_DAY, best_bundle, bundle_value

BLOCK_VERSION = 2
WORLDS = ("sticker", "snhp")
VENUE_NAMES = ("vending", "bodega", "boba", "fashion")


# ── one street shopper's resolution ──────────────────────────────────────

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


def _settle_bodega_quote(bodega, ledger, base, item, qty, price, why,
                         surplus, raw, walk):
    ledger.record({"type": "venue_entered", "venue": "bodega", **base})
    q = bodega.settle_quote(item, qty, price, why, base["day"], base["tick"],
                            base["uid"])
    ledger.record({"type": "deal", "venue": "bodega", "sku": item, "qty": qty,
                   "unit_price": price, "spend": q.total,
                   "cogs": qty * bodega.costs[item],
                   "surplus": surplus, "raw_surplus": raw, "walk": walk,
                   "negotiated": True, **base})


def _resolve_shopper(world, sh, vend_v, bodega, ledger, day, tick):
    """Street lane (home vending/bodega). Candidates carry a fixed
    precedence; the winner is the max-utility candidate with u > 0, ties to
    the earlier entry — with no bodega quote this is EXACTLY B0's
    deal ≥ board ≥ bodega chain."""
    base = {"world": world, "day": day, "tick": tick, "uid": sh.uid,
            "persona": sh.persona, "kind": "street"}
    ledger.record({"type": "arrival", "home": sh.home, **base})

    walk_v = 0.0 if sh.home == "vending" else sh.cross_walk
    walk_b = 0.0 if sh.home == "bodega" else sh.cross_walk

    b_item = None
    u_bodega = float("-inf")
    if bodega is not None:
        b_item, b_qty, b_raw = best_bundle(sh.wtp, bodega.price_board(),
                                           bodega.stock_view())
        u_bodega = (b_raw - walk_b) if b_item is not None else float("-inf")

    v_sku = None
    u_board = float("-inf")
    if vend_v is not None:
        board = vend_v.price_board()
        v_prices = {s: p for s, (p, _w) in board.items()}
        v_stock = {s: vend_v.state.stock(s) for s in v_prices}
        v_sku, v_qty, v_raw = best_bundle(sh.wtp, v_prices, v_stock)
        u_board = (v_raw - walk_v) if v_sku is not None else float("-inf")

    candidates = []          # (utility, settle_thunk) in precedence order
    if vend_v is not None and world == "snhp":
        # truthful disclosure: WTP over the machine's SKUs + the RELATIVE
        # hassle of the bodega vs the machine (see VendingVenue.quote)
        disclosed = {s: sh.wtp[s] for s in vend_v.catalog}
        nq = vend_v.quote(disclosed, walk_b - walk_v)
        if nq is not None and nq.outcome is not None:
            o = nq.outcome
            raw_d = bundle_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price
            u_deal = raw_d - walk_v
            candidates.append((u_deal, lambda o=o, nq=nq, raw_d=raw_d,
                               u_deal=u_deal: _settle_vending(
                                   vend_v, ledger, base, o.sku, o.qty,
                                   o.unit_price, nq.why, u_deal, raw_d,
                                   walk_v, negotiated=True)))
    if bodega is not None and bodega.adopted:
        disclosed_b = {i: sh.wtp[i] for i in bodega.prices}
        bq = bodega.quote(disclosed_b, walk_v - walk_b)
        if bq is not None and bq.outcome is not None:
            o = bq.outcome
            raw_d = bundle_value(sh.wtp, o.sku, o.qty) - o.qty * o.unit_price
            u_deal = raw_d - walk_b
            candidates.append((u_deal, lambda o=o, bq=bq, raw_d=raw_d,
                               u_deal=u_deal: _settle_bodega_quote(
                                   bodega, ledger, base, o.sku, o.qty,
                                   o.unit_price, bq.why, u_deal, raw_d,
                                   walk_b)))
    if v_sku is not None:
        candidates.append((u_board, lambda: _settle_vending(
            vend_v, ledger, base, v_sku, v_qty, v_prices[v_sku],
            board[v_sku][1], u_board, v_raw, walk_v, negotiated=False)))
    if b_item is not None:
        candidates.append((u_bodega, lambda: _settle_bodega(
            bodega, ledger, base, b_item, b_qty, u_bodega, b_raw, walk_b)))

    best_u, settle = 0.0, None
    for u, thunk in candidates:
        if u > best_u:               # strict: ties keep the earlier candidate
            best_u, settle = u, thunk
    if settle is not None:
        settle()
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
    outside = {} if bodega is None else \
        {s: bodega.prices[s] for s in bodega.prices if s in reg.wtp}

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

    # walked: does the bodega actually get them? (money moves, vend's
    # reference psychology stays machine-scoped; posted board even when
    # the bodega adopts — documented)
    if bodega is not None:
        o_item, o_qty, o_raw = best_bundle(reg.wtp, outside, bodega.stock_view())
        if o_item is not None and o_raw - reg.walk_cost > 0:
            _settle_bodega(bodega, ledger, base, o_item, o_qty,
                           o_raw - reg.walk_cost, o_raw, reg.walk_cost)
            return
    ledger.record({"type": "no_sale", **base})


# ── one boba shopper's resolution (boba/run.py's loop, on the block) ─────

def _settle_boba(boba_v, ledger, base, drink, qty, tops, unit_price, spend,
                 slot_ticks, surplus, raw, negotiated, why):
    ledger.record({"type": "venue_entered", "venue": "boba", **base})
    boba_v.settle(drink, qty, tops, spend, slot_ticks, base["day"])
    ledger.record({"type": "deal", "venue": "boba", "sku": drink, "qty": qty,
                   "unit_price": unit_price, "spend": spend,
                   "cogs": qty * (boba_world.DRINK_COST[drink]
                                  + sum(boba_world.TOP_COST[t] for t in tops)),
                   "surplus": surplus, "raw_surplus": raw, "walk": 0.0,
                   "negotiated": negotiated, "tops": list(tops),
                   "slot_ticks": slot_ticks, "why": list(why), **base})


def _resolve_boba(world, sh, boba_v, ledger, day, tick, seed):
    base = {"world": world, "day": day, "tick": tick, "uid": sh.uid,
            "persona": sh.persona, "kind": "street"}
    ledger.record({"type": "arrival", "home": "boba", **base})
    st = boba_v.state
    consumer = boba_v.consumer_view(sh)
    # ONE paired balk roll per shopper (world-independent by construction:
    # keyed on the uid both worlds share); the threshold (queue state) is
    # each world's own
    roll = float(np.random.default_rng(
        substream(seed, "boba-balk", day, tick, sh.uid)).random())

    if world == "snhp":
        deal = boba_v.quote(consumer)
        if deal is not None and deal.u_buyer >= deal.d_buyer - 1e-9:
            # rational acceptance, enforced not assumed (truthful agents)
            if deal.slot_ticks == 0 and roll < boba_world.balk_prob(st):
                # a right-now app order still means standing in that line
                ledger.record({"type": "no_sale", "reason": "balk", **base})
                return
            raw = deal.value - deal.price
            surplus = raw - consumer.defer_cost(deal.slot_ticks)
            # per-unit re-rounding: spend == round(qty × unit, 2) exactly,
            # so the ledger's conservation law stays 2dp-exact (a ≤1¢
            # re-round of the cart total, booked identically on both sides)
            unit = round(deal.price / deal.qty, 2)
            spend = round(deal.qty * unit, 2)
            _settle_boba(boba_v, ledger, base, deal.drink, deal.qty,
                         deal.tops, unit, spend, deal.slot_ticks,
                         surplus, raw, True, deal.why)
            return

    # walk-in: balk BEFORE ordering, then shop the board vs the coffee shop
    if roll < boba_world.balk_prob(st):
        ledger.record({"type": "no_sale", "reason": "balk", **base})
        return
    drink_prices, top_prices = boba_v.boards()
    drink, qty, tops, s = boba_world.best_menu_order(
        consumer, drink_prices, top_prices,
        pearls_ok=st.pearl_stock() >= boba_world.QTY_CAP)
    s_out = boba_world.outside_surplus(consumer)
    if drink is not None and s > 0 and s >= s_out:
        unit = round(drink_prices[drink]
                     + sum(top_prices[t] for t in tops), 2)
        spend = round(qty * unit, 2)
        _settle_boba(boba_v, ledger, base, drink, qty, tops, unit, spend,
                     0, s, s, False, ["menu"])
    else:
        ledger.record({"type": "no_sale", "reason": "lost", **base})


# ── one fashion shopper's resolution ─────────────────────────────────────

def _resolve_fashion(world, sh, fash_v, ledger, day, tick, kind):
    base = {"world": world, "day": day, "tick": tick, "uid": sh.uid,
            "persona": sh.persona, "kind": kind}
    ledger.record({"type": "arrival", "home": "fashion", **base})
    week = fash_v.week
    cell = (sh.style, sh.size)
    stock = fash_v.inv.get(cell, 0)
    if stock <= 0:
        # their size is gone for good (waiters drop out too)
        ledger.record({"type": "no_sale", "reason": "stockout", **base})
        return
    price = fash_v.price(sh.style, sh.size)
    wtp_now = sh.fashion_wtp * float(fashion_decay(week))
    surplus = wtp_now - price
    if sh.waiter:
        wtp_next = sh.fashion_wtp * float(fashion_decay(week + 1))
        buy = waiter_buys_now(surplus, wtp_next, price, stock,
                              fash_v.sold_prev[cell],
                              week == fash_v.SEASON_WEEKS - 1)
    else:
        buy = surplus > 0
    if buy:
        ledger.record({"type": "venue_entered", "venue": "fashion", **base})
        spend, cogs = fash_v.settle(sh.style, sh.size, day)
        ledger.record({"type": "deal", "venue": "fashion", "sku": sh.style,
                       "size": sh.size, "qty": 1, "unit_price": price,
                       "spend": spend, "cogs": cogs, "surplus": surplus,
                       "raw_surplus": surplus, "walk": 0.0,
                       "negotiated": False, **base})
    else:
        if sh.waiter and week < fash_v.SEASON_WEEKS - 1:
            fash_v.waiting.append(sh)
            ledger.record({"type": "no_sale", "reason": "waiting", **base})
        else:
            ledger.record({"type": "no_sale", "reason": "lost", **base})


# ── world & twin loops ───────────────────────────────────────────────────

def run_world(world: str, days: int, seed: int, cfg: BlockConfig,
              ledger: BlockLedger, venues=VENUE_NAMES, catalog=None,
              fashion_plan=None) -> dict:
    has = set(venues)
    vend_v = VendingVenue(world, cfg, seed, catalog=catalog) \
        if "vending" in has else None
    bodega = BodegaVenue(world, cfg, seed,
                         vend_catalog=(vend_v.catalog if vend_v else None)) \
        if "bodega" in has else None
    boba_v = BobaVenue(world, seed) if "boba" in has else None
    fash_v = FashionVenue(world, cfg, seed, plan=fashion_plan) \
        if "fashion" in has else None
    pool = (BlockRegularPool(cfg.regulars, seed, vend_v.catalog)
            if vend_v is not None and cfg.regulars > 0 else None)
    churn = []
    for day in range(days):
        if vend_v is not None:
            vend_v.begin_day(day)
        if bodega is not None:
            bodega.begin_day(day)
        if boba_v is not None:
            boba_v.begin_day(day)
        returning = fash_v.begin_day(day) if fash_v is not None else []
        reg_visits = pool.visits_for_day(day) if pool is not None else {}
        stream = population.day_stream(seed, day)
        for tick in range(TICKS_PER_DAY):
            if vend_v is not None:
                vend_v.state.tick = tick
            if bodega is not None and bodega.adopted:
                bodega.state.tick = tick
            if boba_v is not None:
                boba_v.on_tick(tick)
            if tick == 0 and returning:
                # week boundary: last week's undecided waiters re-decide
                # against the fresh board, FIFO, before the day's street
                for sh in returning:
                    _resolve_fashion(world, sh, fash_v, ledger, day, tick,
                                     kind="return")
                returning = []
            for reg in reg_visits.get(tick, []):
                _resolve_regular(world, reg, vend_v, bodega, ledger, day, tick)
            shoppers = stream[tick]
            if vend_v is not None:
                vend_v.observe_arrivals(
                    tick, sum(1 for s in shoppers if s.home == "vending"))
            if bodega is not None and bodega.adopted:
                bodega.observe_arrivals(
                    tick, sum(1 for s in shoppers if s.home == "bodega"))
            for sh in shoppers:
                if sh.home in ("vending", "bodega"):
                    if vend_v is not None or bodega is not None:
                        _resolve_shopper(world, sh, vend_v, bodega, ledger,
                                         day, tick)
                elif sh.home == "boba":
                    if boba_v is not None:
                        _resolve_boba(world, sh, boba_v, ledger, day, tick,
                                      seed)
                elif sh.home == "fashion":
                    if fash_v is not None:
                        _resolve_fashion(world, sh, fash_v, ledger, day, tick,
                                         kind="street")
        if vend_v is not None:
            eod = vend_v.end_day()
            ledger.close_day(world, "vending", day,
                             eod["spoiled_units"], eod["spoilage_cost"])
        if bodega is not None:
            eodb = bodega.end_day()
            ledger.close_day(world, "bodega", day,
                             eodb["spoiled_units"], eodb["spoilage_cost"])
        if boba_v is not None:
            eodq = boba_v.end_day()
            ledger.close_day(world, "boba", day,
                             eodq["spoiled_units"], eodq["spoilage_cost"])
        if fash_v is not None:
            eodf = fash_v.end_day(day)
            ledger.close_day(world, "fashion", day,
                             eodf["spoiled_units"], eodf["spoilage_cost"])
        if pool is not None:
            churn.append({"day": day, "churned": pool.end_day(day),
                          "active": pool.active_count()})
    venue_objs = {}
    for name, obj in (("vending", vend_v), ("bodega", bodega),
                      ("boba", boba_v), ("fashion", fash_v)):
        if obj is not None:
            venue_objs[name] = obj
    return {"venues": venue_objs, "churn": churn}


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


_VENUE_CLASSES = {"vending": VendingVenue, "bodega": BodegaVenue,
                  "boba": BobaVenue, "fashion": FashionVenue}


def run_twin(days: int, seed: int, cfg: BlockConfig = BlockConfig(),
             venues=VENUE_NAMES):
    """Run BOTH worlds on the identical population. Returns
    (results_dict, ledger, worlds) — results carry no wall-clock except
    under 'meta' (popped by the determinism test)."""
    t0 = time.perf_counter()
    venues = tuple(venues)
    ledger = BlockLedger(rents={v: _VENUE_CLASSES[v].rent_per_day
                                for v in venues})
    catalog = build_block_catalog(cfg, seed) if "vending" in venues else None
    fashion_plan = build_fashion_plan(cfg, seed) if "fashion" in venues else None
    worlds = {w: run_world(w, days, seed, cfg, ledger, venues=venues,
                           catalog=catalog, fashion_plan=fashion_plan)
              for w in WORLDS}

    per_world = {}
    for w in WORLDS:
        per_world[w] = {
            "venues": {v: _venue_block(ledger, w, v, days) for v in venues},
            "traffic": [{"day": d, **ledger.traffic(w, d)} for d in range(days)],
            "churn": worlds[w]["churn"],
        }

    results = {
        "block_version": BLOCK_VERSION,
        "config": {
            "seed": seed, "days": days, "venues": list(venues),
            "sigma_cal": cfg.sigma_cal, "anchor_mult": cfg.anchor_mult,
            "regulars": cfg.regulars, "bodega_adopts": cfg.bodega_adopts,
            "shopper_fraction": round(population.SHOPPER_FRACTION, 4),
            "p_vending_home": round(population.P_VENDING_HOME, 4),
            "expected_daily": {k: round(v, 2)
                               for k, v in population.expected_daily().items()},
            "list_prices": ({s: l.list_price for s, l in catalog.items()}
                            if catalog else {}),
            "bodega_prices": {i: p for i, p, _ in calibration.BODEGA_CATALOG},
            "boba_menu": {d: p for d, p, _ in calibration.BOBA_MENU},
            "fashion_msrp": {s: m for s, m, _ in calibration.FASHION_LINES},
            "rents_per_day": {v: _VENUE_CLASSES[v].rent_per_day for v in venues},
            "notes": [
                "paired seeds: identical population stream across worlds (asserted in tests); fashion waiter RETURNS diverge per-world by design",
                "sticker = profit-optimal all-day price on a sigma_cal-noised operator estimate; boba sticker = the calibration menu; fashion sticker = the industry cliff calendar",
                "bodega posts calibration prices in BOTH worlds; with bodega_adopts the SNHP bodega ALSO quotes brokered Nash deals (discount-only off its posted board)",
                "believed outsides: machine->posted bodega board (x1.15 phantom off the true-mu sticker for non-overlap); adopted bodega->the machine's displayed list (x1.15 phantom otherwise); consumer acceptance always uses the REAL block alternatives",
                "boba: cart quotes fire BEFORE the walk-in balk; now-slot deals face the same balk roll; queue/batches are boba/world verbatim on block ticks 18..89",
                "fashion: weekly season tick every 7 block days, 14-week season; ONE buy at day 0 planned against the cliff; cogs booked at sale, season-end salvage writedown on the last day (runs < 98 days show margin gross of clearance risk)",
                "consumer_surplus is net of the cross-venue walk (or pickup-defer disutility) actually incurred",
                "vending pays no rent in calibration (lobby machine); bodega $400/day, boba $330/day, fashion $620/day",
                "no day-of-week / day shocks / same-day return queue (B0, carried)",
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


_VENUE_ALIASES = {"vend": "vending", "vending": "vending", "bodega": "bodega",
                  "boba": "boba", "fashion": "fashion"}


def parse_venues(spec: str) -> tuple[str, ...]:
    out = []
    for tok in spec.split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok not in _VENUE_ALIASES:
            raise ValueError(f"unknown venue {tok!r} "
                             f"(have {sorted(set(_VENUE_ALIASES))})")
        name = _VENUE_ALIASES[tok]
        if name not in out:
            out.append(name)
    if not out:
        raise ValueError("no venues selected")
    return tuple(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260710)
    ap.add_argument("--regulars", type=int, default=0)
    ap.add_argument("--sigma-cal", type=float, default=0.15)
    ap.add_argument("--anchor-mult", type=float, default=1.0)
    ap.add_argument("--venues", default="vend,bodega,boba,fashion",
                    help="comma list: vend,bodega,boba,fashion (default all)")
    ap.add_argument("--bodega-adopts", action="store_true",
                    help="SNHP world's bodega runs its own brokered-quote arm")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    venues = parse_venues(args.venues)
    cfg = BlockConfig(sigma_cal=args.sigma_cal, anchor_mult=args.anchor_mult,
                      regulars=args.regulars, bodega_adopts=args.bodega_adopts)
    results, ledger, _worlds = run_twin(args.days, args.seed, cfg,
                                        venues=venues)

    out = json.dumps(results, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out + "\n")
        print(f"wrote {args.out} ({results['meta']['elapsed_s']}s)")
    else:
        print(out)

    for venue in venues:
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
