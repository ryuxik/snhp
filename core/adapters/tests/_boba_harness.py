"""A faithful copy of boba.run.run_day whose cart pricer is a parameter.

This is the sim-level reproduction harness (docs/REDESIGN.md Phase 2, G1):
byte-for-byte identical to boba.run.run_day EXCEPT that the two `cart_nash`
call sites are routed through a `pricer` argument with cart_nash's exact
signature. Passing `pricer=boba.policies.cart_nash` reproduces run_day
exactly (verified against boba.run.run_day in the golden test); passing
`pricer=core.adapters.boba.engine_cart_nash` swaps in the general engine.

`compare_with` runs a SECOND pricer at every cart quote and records any
(drink, tops, qty, slot, price) divergence into `mismatches` WITHOUT changing
the trajectory (the sim is always driven by `pricer`) — that is the cart-level
equivalence probe over the real, shipped sim trajectory.

boba/ is untouched: all world dynamics, _settle, and the accounting come
straight from boba.run / boba.world.
"""
from __future__ import annotations

import numpy as np

from boba.policies import (buyer_disagreement, cart_nash,
                           strategic_disclosure)
from boba.run import _settle
from boba.world import (DRINK_PRICE, PEAK_HOURS, QTY_CAP, RENT_PER_DAY,
                        TICKS_PER_DAY, TOP_PRICE, BobaConfig, DEFAULT_CONFIG,
                        arrivals_at, balk_prob, best_menu_order, bundle_value,
                        close_out, expected_wait_minutes, expire_batches,
                        hour_of, maybe_cook, open_shop, outside_surplus,
                        release_scheduled, sample_consumer, serve_queue,
                        substream)


def _call_pricer(pricer, policy, state, consumer, *, lied, outside_c):
    """Invoke `pricer` with the EXACT arguments boba.run.run_day passes at each
    of its two cart_nash call sites (honest vs lied). The lied branch, as in
    run_day, does NOT forward qty_appetite/min_price_frac (they default off)."""
    if lied:
        return pricer(state, consumer, policy.min_gain_abs, policy.min_gain_frac,
                      defer_slots=policy.defer_slots, salvage=policy.salvage,
                      quote_lookers=policy.quote_lookers,
                      outside_consumer=outside_c,
                      market_floor=getattr(policy, "market_floor", False))
    return pricer(state, consumer, policy.min_gain_abs, policy.min_gain_frac,
                  defer_slots=policy.defer_slots, salvage=policy.salvage,
                  quote_lookers=policy.quote_lookers,
                  market_floor=getattr(policy, "market_floor", False),
                  qty_appetite=getattr(policy, "qty_appetite", False),
                  min_price_frac=getattr(policy, "min_price_frac", 0.0))


def _deal_key(deal):
    if deal is None:
        return None
    return (deal.drink, deal.qty, frozenset(deal.tops), deal.slot_ticks,
            round(deal.price, 2))


def _mismatch(a, b) -> bool:
    """cart-level equivalence: same None-ness, same chosen cart, price within
    $0.01."""
    if (a is None) != (b is None):
        return True
    if a is None:
        return False
    return not (a.drink == b.drink and a.qty == b.qty
                and frozenset(a.tops) == frozenset(b.tops)
                and a.slot_ticks == b.slot_ticks
                and abs(a.price - b.price) <= 0.01 + 1e-9)


def run_day(policy, master_seed: int, day: int,
            cfg: BobaConfig = DEFAULT_CONFIG, *, pricer=cart_nash,
            compare_with=None, mismatches: list | None = None,
            counts: dict | None = None) -> dict:
    """boba.run.run_day with a pluggable cart pricer. See module docstring."""
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
        maybe_cook(state)
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

            if getattr(policy, "mode", "board") == "cart":
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
                    quote_consumer = disclosed
                else:
                    quote_consumer, outside_c = consumer, None
                deal = _call_pricer(pricer, policy, state, quote_consumer,
                                    lied=lied, outside_c=outside_c)
                if compare_with is not None:
                    other = _call_pricer(compare_with, policy, state,
                                         quote_consumer, lied=lied,
                                         outside_c=outside_c)
                    if counts is not None:
                        counts["total"] = counts.get("total", 0) + 1
                    if _mismatch(deal, other):
                        if counts is not None:
                            counts["mismatch"] = counts.get("mismatch", 0) + 1
                        if mismatches is not None:
                            mismatches.append({
                                "day": day, "tick": tick, "k": k, "lied": lied,
                                "driver": _deal_key(deal),
                                "other": _deal_key(other)})

                if deal is not None:
                    if lied:
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
                        if deal.slot_ticks == 0:
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

    m["waste_cost"] += close_out(state)
    m["batches_cooked"] = state.batches_cooked
    m["margin"] = round(m["revenue"] - m["ingredient_cost"] - m["waste_cost"], 2)
    m["rent"] = RENT_PER_DAY
    for k in ("revenue", "ingredient_cost", "waste_cost", "consumer_surplus",
              "neg_shop_gain", "peak_wait_sum"):
        m[k] = round(m[k], 2)
    return m
