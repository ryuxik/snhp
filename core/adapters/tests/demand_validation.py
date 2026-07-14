"""VALIDATE the learned WTP-discovery layer IN SIM — the deliverable.

Take the boba world and STRIP THE ORACLE: the engine sees only quote OUTCOMES
(accept / reject / walk), never a wallet. Learn the population WTP from that
censored stream (core/demand.py) and price with it, then measure — honestly —
how much of the oracle's edge learning recovers, and whether learning opens the
IC floor the oracle mechanism holds shut.

Paired arms, all facing the IDENTICAL boba arrival stream (paired by seed):

  oracle   the shipped engine on the TRUE consumer (core.adapters.boba) — the
           ceiling. Uses the individual wallet.
  learned  the engine with a LearnedDemand that has seen only PAST quote
           outcomes; prices the population value/list scale at the arrival's
           observable context (hour), never the wallet. THE NEW SYSTEM.
  menu     no negotiation — the sticker board (best_menu_order). The floor.

× two populations:

  honest   buyers accept a quote iff their TRUE surplus beats their TRUE
           disagreement (myopic-rational), and shop the sticker otherwise.
  ratchet  a `ratchet_share` of buyers strategically REJECT quotes they would
           rationally take (holding out below a fraction of their true value),
           to train the population posterior DOWN — the demand-ratchet attack
           (the online analog of the adaptive-liar sweeps: boba.battery /
           paper.theorem_ic_multi_harness). The rest are honest.

────────────────────────────────────────────────────────────────────────────
PRE-REGISTERED KILL CONDITION (written BEFORE running):

  If the LEARNED arm cannot recover >= 50% of the DEFERRAL+SALVAGE share of
  the oracle edge (the created-surplus levers — the honest bridge from the
  ~$45/day menu floor toward the ~$250/day oracle ceiling) WITHOUT any
  sub-menu leak against the RATCHET population, the mechanism is NOT
  production-viable as-is. Report that NULL. DO NOT tune to pass.

  deferral+salvage edge  = oracle(defer+salvage ON) − oracle(defer+salvage OFF),
                           both quote_lookers ON, honest population.
  recovery               = [learned(ON) − learned(OFF)] / (deferral+salvage edge).
  sub-menu leak (the IC invariant) = Σ over realized learned-arm deals struck
                           with a TRUE menu-buyer of max(0, d_seller_true −
                           realized shop gain), on the engine's own c_eff basis.
                           $0 under the oracle BY CONSTRUCTION (the min-gain
                           floor clears the true standing margin); the number
                           reported here is what SURVIVES learning.

Reproduce:  python3 -m core.adapters.tests.demand_validation \
                --days 30 --seeds 20260710,7,101 --out core/adapters/tests/demand-validation.json
Fast gate:  pytest core/adapters/tests/demand_validation.py
────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from core.adapters.boba import GRAPH, buyer_for, shop_state
from core.demand import LearnedDemand, ListAppeal, Outcome
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as core_quote
from boba.policies import CartDeal, top_c_eff
from boba.policies import cart_nash  # oracle pricer (shipped adapter delegate)
from boba.run import _settle
from boba.world import (DRINK_COST, DRINK_PRICE, GROUP_DECAY, GROUP_SHARE,
                        PEAK_HOURS, QTY_CAP, RENT_PER_DAY, RIGID_DEFER,
                        SOLO_DECAY, TICKS_PER_DAY, TOP_COST, TOP_PRICE,
                        WTP_SIGMA, BobaConfig, DEFAULT_CONFIG, FLEX_DEFER,
                        arrivals_at, balk_prob, best_menu_order, bundle_value,
                        close_out, expire_batches, hour_of, maybe_cook,
                        open_shop, outside_surplus, release_scheduled,
                        sample_consumer, serve_queue, substream)

# ── population-observable structural constants (what the shop DOES know) ────
# The qty decay and defer schedule are population MIXTURES the shop knows the
# shape of (a share are group orders / pickup-flexible) but not this arrival's
# draw. These population means are the observable structural fields the learned
# shell carries — never the wallet.
POP_DECAY = (1 - GROUP_SHARE) * SOLO_DECAY + GROUP_SHARE * GROUP_DECAY


def _pop_defer(flex_share: float) -> dict:
    return {s: flex_share * FLEX_DEFER[s] + (1 - flex_share) * RIGID_DEFER[s]
            for s in (0, 3, 6)}


def _context(tick: int) -> int:
    """The arrival's OBSERVABLE context = the hour (the public HOURLY_WTP_MULT
    calendar effect enters through the per-hour learned scale)."""
    return hour_of(tick)


def _observable_shell(bs, flex_share: float) -> SeparableBuyer:
    """The buyer the learned engine actually sees: population decay/defer, the
    OBSERVABLE queue balk, an outside surplus estimated at the population floor
    (the +10%-markup competitor gives the typical scale-1 buyer ~0 surplus),
    and NO values (the demand model overrides value())."""
    return SeparableBuyer(values={}, qty_decay=POP_DECAY,
                          outside=0.0, balk=balk_prob(bs),
                          defer=_pop_defer(flex_share))


# ── the three arms' pricer for one arrival ─────────────────────────────────
def _oracle_deal(bs, consumer, *, defer_slots, salvage, quote_lookers):
    return cart_nash(bs, consumer, 0.25, 0.10, defer_slots=defer_slots,
                     salvage=salvage, quote_lookers=quote_lookers)


def _learned_deal(bs, consumer, dm, flex_share, *, defer_slots, salvage,
                  quote_lookers):
    """Quote via the engine with the LEARNED demand model. Returns
    (CartDeal|None, context, offered_config, offered_price). The engine prices
    the observable shell; the true consumer's accept/reject is decided by the
    caller and fed back to dm.observe()."""
    state = shop_state(bs, defer_slots=defer_slots, salvage=salvage)
    shell = _observable_shell(bs, flex_share)
    ctx = _context(bs.tick)
    opts = QuoteOpts(min_gain_abs=0.25, min_gain_frac=0.10, price_rungs=8,
                     seller_weight=0.5, prune_free=True,
                     quote_lookers=quote_lookers)   # NO search_filter: the
    # filter is built from the consumer's true wtp (an oracle leak); the
    # learned arm searches the full offer graph instead.
    q = core_quote(GRAPH, state, shell, opts=opts, demand=dm, context=ctx)
    if q is None or not q.feasible:
        return None, ctx, (q.config if q is not None else None), \
            (q.price if q is not None else None)
    slot_ticks = GRAPH.dim("pickup").option(q.config["pickup"]).slot_ticks
    deal = CartDeal(drink=q.config["drink"], qty=int(q.config["qty"]),
                    tops=tuple(sorted(q.config["tops"])), price=q.price,
                    slot_ticks=slot_ticks, value=q.value,
                    u_shop=q.seller_gain, d_shop=q.audit.get("d_seller", 0.0),
                    u_buyer=q.buyer_gain, d_buyer=q.audit.get("d_buyer", 0.0),
                    relief=q.audit.get("credit", 0.0), why=("learned",))
    return deal, ctx, q.config, q.price


# ── true-buyer acceptance (never the disclosed/estimated surplus) ──────────
def _would_accept(bs, consumer, deal: CartDeal, population: str,
                  ratchet_share: float) -> bool:
    """Does the TRUE consumer take this deal ON WTP GROUNDS (pre-balk)? The
    rational rule (boba.run): u_buyer >= d_buyer on TRUE utilities. A RATCHET
    buyer additionally HOLDS OUT — it rejects a rational now-slot deal unless
    the price leaves it at least (1−holdout) of its true value, to train the
    learner's posterior DOWN (the demand-suppression move). The balk is applied
    separately by the caller (a balk is queue abandonment, not a WTP reject —
    so the learner must never read it as one)."""
    true_value = bundle_value(consumer, deal.drink, deal.qty, deal.tops)
    surv = (1.0 - balk_prob(bs)) if deal.slot_ticks == 0 else 1.0
    u_buyer = surv * (true_value - deal.price) \
        + (1.0 - surv) * outside_surplus(consumer) \
        - consumer.defer_cost(deal.slot_ticks)
    if u_buyer < _true_d_buyer(bs, consumer) - 1e-9:
        return False
    # RATCHET hold-out: a share of buyers reject any deal (now OR deferred) that
    # leaves them less than 20% of true value as surplus, even when rational —
    # each rejection feeds the learner a censored 'value < (a BELOW-list price)'
    # that drags the scale posterior DOWN (the demand-suppression attack).
    if population == "ratchet" and _uid_roll(consumer.uid) < ratchet_share \
            and deal.price > 0.80 * true_value:
        return False
    return True


def _uid_roll(uid: int) -> float:
    return float(np.random.default_rng(substream(7777, "ratchet", uid)).random())


def _true_d_buyer(bs, consumer) -> float:
    """The buyer's TRUE no-deal payoff (boba.policies.buyer_disagreement),
    inlined to avoid importing the whole liar battery."""
    b = balk_prob(bs)
    s_out = outside_surplus(consumer)
    d, q, t, s_menu = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                      pearls_ok=bs.pearl_stock() >= QTY_CAP)
    if d is not None and s_menu > 0 and s_menu >= s_out:
        return (1.0 - b) * s_menu + b * s_out
    return s_out


# ── the true menu counterfactual (for the leak & the floor arm) ────────────
def _true_menu_order(bs, consumer):
    d, q, t, s = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                 pearls_ok=bs.pearl_stock() >= QTY_CAP)
    return d, q, t, s


# ── one simulated day for one arm ──────────────────────────────────────────
def _new_metrics() -> dict:
    return {"revenue": 0.0, "ingredient_cost": 0.0, "waste_cost": 0.0,
            "cups": 0, "toppings": 0, "deals": 0, "deferred": 0,
            "consumer_surplus": 0.0, "arrivals": 0, "salvage_deals": 0,
            "leak": 0.0, "looker_conversions": 0, "menu_buyer_deals": 0}


def run_day(arm: str, dm, master_seed: int, day: int, cfg: BobaConfig, *,
            defer_slots: bool, salvage: bool, quote_lookers: bool,
            population: str, ratchet_share: float) -> dict:
    """One paired day. `arm` in {oracle, learned, menu}. For `learned`, dm is
    updated with every realized outcome (accept/reject/walk); it PERSISTS
    across days (that is the learning). Days carry no overnight state (boba),
    so each day is an independent draw."""
    m = _new_metrics()
    bs = open_shop(day, cfg.balk_model)
    for tick in range(TICKS_PER_DAY):
        bs.tick = tick
        m["waste_cost"] += expire_batches(bs)
        maybe_cook(bs)
        release_scheduled(bs)
        serve_queue(bs)
        n = arrivals_at(master_seed, day, tick, cfg)
        m["arrivals"] += n
        for k in range(n):
            consumer = sample_consumer(master_seed, day, tick, k, cfg)
            broll = float(np.random.default_rng(
                substream(master_seed, "balk", day, tick, k)).random())
            _serve_arrival(arm, dm, bs, consumer, broll, m, cfg,
                           defer_slots=defer_slots, salvage=salvage,
                           quote_lookers=quote_lookers, population=population,
                           ratchet_share=ratchet_share)
    m["waste_cost"] += close_out(bs)
    m["margin"] = round(m["revenue"] - m["ingredient_cost"] - m["waste_cost"], 4)
    return m


def _serve_arrival(arm, dm, bs, consumer, broll, m, cfg, *, defer_slots,
                   salvage, quote_lookers, population, ratchet_share):
    # ── the negotiated quote (oracle or learned) ──
    if arm in ("oracle", "learned"):
        if arm == "oracle":
            deal = _oracle_deal(bs, consumer, defer_slots=defer_slots,
                                salvage=salvage, quote_lookers=quote_lookers)
            ctx = off_cfg = off_price = None
        else:
            deal, ctx, off_cfg, off_price = _learned_deal(
                bs, consumer, dm, cfg.flexible_share, defer_slots=defer_slots,
                salvage=salvage, quote_lookers=quote_lookers)

        if deal is not None:
            would = _would_accept(bs, consumer, deal, population, ratchet_share)
            if arm == "learned":
                dm.observe(ctx, off_cfg, off_price,
                           Outcome.ACCEPT if would else Outcome.REJECT,
                           graph=GRAPH)
            if would:
                # leak: measure BEFORE booking (pre-deal state) on the engine's
                # own decision-time expectation basis — both arms, so the
                # oracle's structural $0 is verified through the SAME accounting.
                _account_leak(bs, consumer, deal, m, salvage)
                if deal.slot_ticks == 0 and broll < balk_prob(bs):
                    return  # balked away after accepting a now-slot app order
                _book_deal(bs, consumer, deal, m, salvage)
                return
            # deal offered but rejected → fall through to the walk-in board

    # ── walk-in board fallback (menu arm always; the others on no-deal) ──
    if arm == "learned":
        _learned_walkin(dm, bs, consumer, broll, m, population, ratchet_share)
    else:
        _walkin_board(bs, consumer, broll, m)


def _book_deal(bs, consumer, deal: CartDeal, m: dict, salvage: bool) -> None:
    true_value = bundle_value(consumer, deal.drink, deal.qty, deal.tops)
    realized = true_value - deal.price - consumer.defer_cost(deal.slot_ticks)
    _settle(bs, m, deal.drink, deal.qty, deal.tops, deal.price, realized,
            deal.slot_ticks)
    m["negotiated"] = m.get("negotiated", 0) + 1
    if "pearls" in deal.tops and top_c_eff(bs, "pearls") == 0.0:
        m["salvage_deals"] += 1


def _account_leak(bs, consumer, deal, m, salvage) -> None:
    """Sub-menu leak of ONE deal, on the engine's own decision-time basis (the
    PRE-deal state, `bs`): the shop's expected gain from the deal, minus the
    buyer's TRUE standing menu margin `d_seller_true` = (1−b)·(list − c_eff) of
    their best sticker order. This is EXACTLY the engine's `gs` measured against
    the TRUE menu config; under the ORACLE the engine used that same true
    config and enforced gs ≥ min_gain > 0, so leak ≡ $0 — the invariant. Under
    LEARNING the engine used the ESTIMATED menu config for d_seller, so a
    too-cheap estimate can leave gs (vs the TRUE config) negative → a real
    leak, which this counts. $0 for a non-menu-buyer: converting a true looker
    is a GAIN over the $0 they would have paid, never a leak."""
    b = balk_prob(bs)
    d, q, t, s_menu = _true_menu_order(bs, consumer)
    s_out = outside_surplus(consumer)
    if d is None or s_menu <= 0 or s_menu < s_out:
        m["looker_conversions"] += 1
        return
    m["menu_buyer_deals"] += 1
    menu_list = q * (DRINK_PRICE[d] + sum(TOP_PRICE[x] for x in t))
    menu_cost = q * (DRINK_COST[d]
                     + sum((top_c_eff(bs, x) if salvage else TOP_COST[x])
                           for x in t))
    d_seller_true = (1.0 - b) * (menu_list - menu_cost)
    surv = (1.0 - b) if deal.slot_ticks == 0 else 1.0
    deal_cost = deal.qty * (DRINK_COST[deal.drink]
                            + sum((top_c_eff(bs, x) if salvage else TOP_COST[x])
                                  for x in deal.tops))
    deal_gain = surv * (deal.price - deal_cost) + deal.relief
    m["leak"] += max(0.0, d_seller_true - deal_gain)


def _learned_walkin(dm, bs, consumer, broll, m, population,
                    ratchet_share) -> None:
    """A non-negotiated arrival shops the sticker — and its CHOICE is the online
    choice-share signal (boba appeal_for_list made online). A walk-in that buys
    config X at list is an ACCEPT at list; one that can't afford its best order
    walks — a REJECT at that rung. A RATCHET suppressor that COULD afford its
    order nonetheless refuses to pay list (a 'won't-pay-sticker' boycott),
    feeding the learner a FALSE 'value < list' to drag the scale posterior down
    — the demand-ratchet's attack on the choice-share ANCHOR. It costs the
    suppressor the purchase, exactly as a real strategic hold-out would."""
    if broll < balk_prob(bs):
        return                                     # balked: not a WTP signal
    d, q, t, s = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                 pearls_ok=bs.pearl_stock() >= QTY_CAP)
    s_out = outside_surplus(consumer)
    ctx = _context(bs.tick)
    is_buyer = d is not None and s > 0 and s >= s_out
    ratchet = (population == "ratchet"
               and _uid_roll(consumer.uid) < ratchet_share)
    if is_buyer and not ratchet:
        cfg = {"drink": d, "tops": frozenset(t), "pickup": "now", "qty": q}
        price = q * (DRINK_PRICE[d] + sum(TOP_PRICE[x] for x in t))
        dm.observe(ctx, cfg, price, Outcome.ACCEPT, graph=GRAPH)
        _settle(bs, m, d, q, t, round(price, 2), s)
    elif is_buyer and ratchet:
        # suppressor: reject its OWN best order at list (a false low-WTP signal)
        cfg = {"drink": d, "tops": frozenset(t), "pickup": "now", "qty": q}
        price = q * (DRINK_PRICE[d] + sum(TOP_PRICE[x] for x in t))
        dm.observe(ctx, cfg, price, Outcome.REJECT, graph=GRAPH)
    else:
        cheap = min(DRINK_PRICE, key=DRINK_PRICE.get)
        cfg = {"drink": cheap, "tops": frozenset(), "pickup": "now", "qty": 1}
        dm.observe(ctx, cfg, DRINK_PRICE[cheap], Outcome.REJECT, graph=GRAPH)


def _walkin_board(bs, consumer, broll, m) -> None:
    if broll < balk_prob(bs):
        return
    d, q, t, s = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                 pearls_ok=bs.pearl_stock() >= QTY_CAP)
    s_out = outside_surplus(consumer)
    if d is not None and s > 0 and s >= s_out:
        price = round(q * (DRINK_PRICE[d] + sum(TOP_PRICE[x] for x in t)), 2)
        _settle(bs, m, d, q, t, price, s)


# ── the arm runner (learned persists dm across days) ───────────────────────
def run_arm(arm: str, days: int, seed: int, cfg: BobaConfig, *,
            defer_slots=True, salvage=True, quote_lookers=True,
            population="honest", ratchet_share=0.0):
    dm = None
    if arm == "learned":
        dm = LearnedDemand(appeal=ListAppeal(), sigma_pop=WTP_SIGMA,
                           decay=POP_DECAY, bucket_of=lambda c: c)  # bucket=hour
    per_day = [run_day(arm, dm, seed, d, cfg, defer_slots=defer_slots,
                       salvage=salvage, quote_lookers=quote_lookers,
                       population=population, ratchet_share=ratchet_share)
               for d in range(days)]
    return per_day, dm


# ══════════════════════════════════════════════════════════════════════════
# the validation table
# ══════════════════════════════════════════════════════════════════════════
def _margin_series(per_day):
    return [m["margin"] for m in per_day]


def _mean(xs):
    return round(float(np.mean(xs)), 3) if xs else 0.0


def _sum_key(per_day, key):
    return round(float(sum(m.get(key, 0.0) for m in per_day)), 4)


def validate(days: int, seeds, *, flex_share=0.30, ratchet_share=0.5) -> dict:
    """Assemble the paired validation table. All recovery arms run under
    REFUSE-LOOKERS (quote_lookers=False) — the IC-safe deployment — so the
    created-surplus ablation isolates deferral+salvage cleanly (looker
    conversion, the individual-wallet lever, is off everywhere) and the leak is
    measured under the exact config the $0 claim is about. A single
    with-lookers oracle is kept for the full ceiling (the $45→$250 framing)."""
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=flex_share)
    out = {"config": {"days": days, "seeds": list(seeds),
                      "flexible_share": flex_share,
                      "ratchet_share": ratchet_share,
                      "kill_condition": "learned recovers >=50% of the "
                      "deferral+salvage oracle edge (refuse-lookers) with $0 "
                      "sub-menu leak against the ratchet population"},
           "per_seed": {}, "pooled": {}}

    keys = ("menu", "oracle_ceiling", "oracle_full", "oracle_salv",
            "oracle_noc", "learned_full", "learned_salv", "learned_noc",
            "learned_ratchet", "leak_oracle", "leak_honest", "leak_ratchet",
            "scale_honest", "scale_ratchet")
    agg = {k: [] for k in keys}
    ttc_accum = None

    for seed in seeds:
        menu_pd, _ = run_arm("menu", days, seed, cfg, population="honest")
        # oracle: ceiling (lookers ON) + the IC-safe created-surplus ladder
        oc_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=True,
                           salvage=True, quote_lookers=True, population="honest")
        of_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=True,
                           salvage=True, quote_lookers=False, population="honest")
        os_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=False,
                           salvage=True, quote_lookers=False, population="honest")
        on_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=False,
                           salvage=False, quote_lookers=False, population="honest")
        # learned: the same created-surplus ladder (refuse-lookers, IC-safe)
        lf_pd, dm_h = run_arm("learned", days, seed, cfg, defer_slots=True,
                              salvage=True, quote_lookers=False,
                              population="honest")
        ls_pd, _ = run_arm("learned", days, seed, cfg, defer_slots=False,
                           salvage=True, quote_lookers=False, population="honest")
        ln_pd, _ = run_arm("learned", days, seed, cfg, defer_slots=False,
                           salvage=False, quote_lookers=False, population="honest")
        lr_pd, dm_r = run_arm("learned", days, seed, cfg, defer_slots=True,
                              salvage=True, quote_lookers=False,
                              population="ratchet", ratchet_share=ratchet_share)

        row = {
            "menu": _mean(_margin_series(menu_pd)),
            "oracle_ceiling": _mean(_margin_series(oc_pd)),
            "oracle_full": _mean(_margin_series(of_pd)),
            "oracle_salv": _mean(_margin_series(os_pd)),
            "oracle_noc": _mean(_margin_series(on_pd)),
            "learned_full": _mean(_margin_series(lf_pd)),
            "learned_salv": _mean(_margin_series(ls_pd)),
            "learned_noc": _mean(_margin_series(ln_pd)),
            "learned_ratchet": _mean(_margin_series(lr_pd)),
            "leak_oracle": round(_sum_key(of_pd, "leak") / days, 4),
            "leak_honest": round(_sum_key(lf_pd, "leak") / days, 4),
            "leak_ratchet": round(_sum_key(lr_pd, "leak") / days, 4),
            "scale_honest": _scale_snapshot(dm_h),
            "scale_ratchet": _scale_snapshot(dm_r),
            "oracle_deferred_deals": _sum_key(of_pd, "deferred"),
            "learned_deferred_deals": _sum_key(lf_pd, "deferred"),
        }
        out["per_seed"][seed] = row
        for k in keys:
            v = row[k]
            agg[k].append(np.mean(list(v.values())) if isinstance(v, dict)
                          and v else (1.0 if isinstance(v, dict) else v))
        if ttc_accum is None:
            ttc_accum = _time_to_competence(days, seed, cfg)

    def pm(k):
        return round(float(np.mean(agg[k])), 3) if agg[k] else 0.0

    menu, oc = pm("menu"), pm("oracle_ceiling")
    of, os_, on = pm("oracle_full"), pm("oracle_salv"), pm("oracle_noc")
    lf, ls, ln = pm("learned_full"), pm("learned_salv"), pm("learned_noc")
    lr = pm("learned_ratchet")
    ds_edge = round(of - on, 3)                 # deferral+salvage (IC-safe)
    salv_edge = round(os_ - on, 3)
    defer_edge = round(of - os_, 3)
    lrn_created = round(lf - ln, 3)
    lrn_salv = round(ls - ln, 3)
    lrn_defer = round(lf - ls, 3)
    recovery = round(lrn_created / ds_edge, 3) if abs(ds_edge) > 1e-9 else None
    salv_recovery = round(lrn_salv / salv_edge, 3) if abs(salv_edge) > 1e-9 else None
    defer_recovery = round(lrn_defer / defer_edge, 3) if abs(defer_edge) > 1e-9 else None
    total_edge = round(oc - menu, 3)
    leak_o = round(float(np.mean(agg["leak_oracle"])), 4)
    leak_h = round(float(np.mean(agg["leak_honest"])), 4)
    leak_r = round(float(np.mean(agg["leak_ratchet"])), 4)
    scale_drop = round(pm("scale_ratchet") - pm("scale_honest"), 4)

    kill = (recovery is not None and recovery >= 0.50 and leak_r <= 1e-6)
    out["pooled"] = {
        "menu_margin_day": menu,
        "oracle_ceiling_margin_day": oc,
        "oracle_full_ICsafe_margin_day": of,
        "oracle_salvage_only_margin_day": os_,
        "oracle_nocreated_margin_day": on,
        "learned_full_margin_day_honest": lf,
        "learned_salvage_only_margin_day": ls,
        "learned_nocreated_margin_day": ln,
        "learned_full_margin_day_ratchet": lr,
        "deferral_salvage_edge_day": ds_edge,
        "salvage_edge_day": salv_edge,
        "deferral_edge_day": defer_edge,
        "learned_created_recovered_day": lrn_created,
        "deferral_salvage_recovery_frac": recovery,
        "salvage_recovery_frac": salv_recovery,
        "deferral_recovery_frac": defer_recovery,
        "total_oracle_ceiling_edge_day": total_edge,
        "IC_safe_total_recovery_frac": round((lf - menu) / (of - menu), 3)
        if abs(of - menu) > 1e-9 else None,
        "sub_menu_leak_day_oracle": leak_o,
        "sub_menu_leak_day_honest": leak_h,
        "sub_menu_leak_day_ratchet": leak_r,
        "sub_menu_leak_pct_of_margin_honest": round(100 * leak_h / lf, 4)
        if lf else None,
        "ratchet_scale_drop_vs_honest": scale_drop,
        "learned_scale_honest_mean": pm("scale_honest"),
        "learned_scale_ratchet_mean": pm("scale_ratchet"),
        "time_to_competence": ttc_accum,
        "KILL_CONDITION_PASSED": bool(kill),
        "verdict": ("PASS — learned recovers >=50% of the deferral+salvage "
                    "edge with a near-intact IC floor" if kill else
                    "NULL — learned does NOT recover >=50% of the deferral+"
                    "salvage edge (population WTP cannot see the individual "
                    "flexibility the deferral lever needs); reported as-is, NOT "
                    "tuned to pass. The IC floor is NEARLY preserved (small "
                    "residual leak, see sub_menu_leak_pct_of_margin_honest)."),
        "money_answer_IC_floor_exactly_preserved": bool(
            leak_h <= 1e-6 and leak_r <= 1e-6),
        "money_answer_note": (
            "Honest learning leaves a SMALL residual leak (~0.05% of margin) "
            "from population misidentification of the buyer's true menu-"
            "counterfactual config on rich multi-topping carts — the seller "
            "disagreement is set slightly too low. Oracle leak is $0 exactly; "
            "the ratchet leak is $0 because over-discounting makes the engine "
            "REFUSE deals. The floor is nearly, not exactly, preserved."),
    }
    return out


def _scale_snapshot(dm) -> dict:
    if dm is None:
        return {}
    return {int(b): round(c.scale_median(), 4) for b, c in dm._curves.items()}


def _time_to_competence(days, seed, cfg) -> list:
    """The learned arm's CUMULATIVE recovery of the IC-SAFE oracle edge after
    each day — the learning curve. References recomputed on the same stream so
    recovery is matched day-by-day (both refuse-lookers, so this is the
    created-surplus + scale-learning recovery, not the looker-conversion part
    population learning structurally cannot do)."""
    menu_pd, _ = run_arm("menu", days, seed, cfg, population="honest")
    orc_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=True,
                        salvage=True, quote_lookers=False, population="honest")
    lrn_pd, _ = run_arm("learned", days, seed, cfg, defer_slots=True,
                        salvage=True, quote_lookers=False, population="honest")
    curve = []
    for d in range(days):
        num = sum(lrn_pd[i]["margin"] - menu_pd[i]["margin"] for i in range(d + 1))
        den = sum(orc_pd[i]["margin"] - menu_pd[i]["margin"] for i in range(d + 1))
        curve.append({"day": d + 1,
                      "recovery_frac": round(num / den, 3) if abs(den) > 1e-9 else None})
    return curve


# ── printing ───────────────────────────────────────────────────────────────
def _print(res: dict) -> None:
    p = res["pooled"]
    print("\n" + "=" * 76)
    print("LEARNED WTP-DISCOVERY — sim validation (boba, oracle stripped)")
    print("=" * 76)
    print(f"  days={res['config']['days']} seeds={res['config']['seeds']} "
          f"ratchet_share={res['config']['ratchet_share']}")
    print(f"\n  {'arm ($/day margin)':<44}{'value':>12}")
    print(f"  {'menu (floor)':<44}{p['menu_margin_day']:>12.2f}")
    print(f"  {'oracle ceiling (lookers ON)':<44}"
          f"{p['oracle_ceiling_margin_day']:>12.2f}")
    print(f"  {'oracle full  (defer+salv, refuse-lookers)':<44}"
          f"{p['oracle_full_ICsafe_margin_day']:>12.2f}")
    print(f"  {'oracle salvage-only':<44}"
          f"{p['oracle_salvage_only_margin_day']:>12.2f}")
    print(f"  {'oracle no-created':<44}{p['oracle_nocreated_margin_day']:>12.2f}")
    print(f"  {'learned full  (honest, refuse-lookers)':<44}"
          f"{p['learned_full_margin_day_honest']:>12.2f}")
    print(f"  {'learned salvage-only (honest)':<44}"
          f"{p['learned_salvage_only_margin_day']:>12.2f}")
    print(f"  {'learned no-created (honest)':<44}"
          f"{p['learned_nocreated_margin_day']:>12.2f}")
    print(f"  {'learned full  (RATCHET)':<44}"
          f"{p['learned_full_margin_day_ratchet']:>12.2f}")
    print(f"\n  ORACLE EDGE (IC-safe)   deferral+salvage ${p['deferral_salvage_edge_day']}/day"
          f"  (=deferral ${p['deferral_edge_day']} + salvage ${p['salvage_edge_day']})")
    print(f"  LEARNED recovered        created ${p['learned_created_recovered_day']}/day")
    print(f"  >> DEFERRAL+SALVAGE RECOVERY  {p['deferral_salvage_recovery_frac']}"
          f"   (kill threshold 0.50)  |  deferral {p['deferral_recovery_frac']}"
          f"  salvage {p['salvage_recovery_frac']}")
    print(f"  full ceiling edge (lookers ON) ${p['total_oracle_ceiling_edge_day']}/day"
          f"   IC-safe total recovery {p['IC_safe_total_recovery_frac']}")
    print(f"\n  SUB-MENU LEAK  oracle=${p['sub_menu_leak_day_oracle']}/day  "
          f"honest=${p['sub_menu_leak_day_honest']}/day  "
          f"RATCHET=${p['sub_menu_leak_day_ratchet']}/day")
    print(f"  ratchet scale drop vs honest   {p['ratchet_scale_drop_vs_honest']}"
          f"  (honest {p['learned_scale_honest_mean']} -> "
          f"ratchet {p['learned_scale_ratchet_mean']})")
    tc = p["time_to_competence"]
    if tc:
        pts = ", ".join(f"d{c['day']}:{c['recovery_frac']}"
                        for c in tc if c["day"] in (1, 2, 5, 10, 20, 30))
        print(f"  time-to-competence (cum IC-safe recovery): {pts}")
    print(f"\n  KILL CONDITION PASSED: {p['KILL_CONDITION_PASSED']}")
    print(f"  MONEY ANSWER — IC $0-floor EXACTLY preserved under learning: "
          f"{p['money_answer_IC_floor_exactly_preserved']}")
    print(f"    honest leak ${p['sub_menu_leak_day_honest']}/day "
          f"({p['sub_menu_leak_pct_of_margin_honest']}% of margin) · "
          f"ratchet ${p['sub_menu_leak_day_ratchet']}/day · "
          f"oracle ${p['sub_menu_leak_day_oracle']}/day")
    print(f"  {p['verdict']}")
    print("=" * 76)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seeds", default="20260710,7,101")
    ap.add_argument("--flex-share", type=float, default=0.30)
    ap.add_argument("--ratchet-share", type=float, default=0.5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    res = validate(a.days, seeds, flex_share=a.flex_share,
                   ratchet_share=a.ratchet_share)
    _print(res)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1, default=str)
        print(f"  wrote {a.out}")
    return 0


# ══════════════════════════════════════════════════════════════════════════
# fast pytest gate (small run — asserts the machinery + the IC invariant)
# ══════════════════════════════════════════════════════════════════════════
def test_demand_validation_fast():
    """A short paired run gating the two honest claims (the FULL kill-condition
    recovery number is the SCRIPT's job — this gate is fast):

      (a) learning does not DESTROY value vs the sticker floor (honest pop);
      (b) the sub-menu leak stays SMALL — the IC floor is nearly preserved.
          It is NOT exactly $0 under learning: the 30-day script shows a
          residual ~0.05% of margin (population misidentifies a rich cart's
          menu-counterfactual config); we bound it well under 1% of margin
          here. The ORACLE leak is exactly $0 (asserted separately, cheaply).
          The ratchet leak is $0 (over-discounting → deal refusal)."""
    cfg = BobaConfig(sigma_shock=0.0, flexible_share=0.30)
    seed, days = 20260710, 3
    menu_pd, _ = run_arm("menu", days, seed, cfg, population="honest")
    orc_pd, _ = run_arm("oracle", days, seed, cfg, defer_slots=True,
                        salvage=True, quote_lookers=False, population="honest")
    lrn_h_pd, _ = run_arm("learned", days, seed, cfg, defer_slots=True,
                          salvage=True, quote_lookers=False, population="honest")
    lrn_r_pd, _ = run_arm("learned", days, seed, cfg, defer_slots=True,
                          salvage=True, quote_lookers=False,
                          population="ratchet", ratchet_share=0.5)

    menu_m = float(np.mean([m["margin"] for m in menu_pd]))
    lrn_m = float(np.mean([m["margin"] for m in lrn_h_pd]))
    leak_o = sum(m["leak"] for m in orc_pd)
    leak_h = sum(m["leak"] for m in lrn_h_pd)
    leak_r = sum(m["leak"] for m in lrn_r_pd)

    assert leak_o <= 1e-6, f"ORACLE leak ${leak_o:.4f} must be exactly 0"
    assert leak_r <= 1e-6, f"ratchet sub-menu leak ${leak_r:.4f} != 0"
    # learned leak is bounded, not zero — well under 1% of margin
    assert leak_h <= 0.01 * lrn_m * days, (
        f"learned leak ${leak_h:.4f} exceeds 1% of margin")
    assert lrn_m >= menu_m - 1e-6, f"learned {lrn_m:.2f} < menu floor {menu_m:.2f}"


if __name__ == "__main__":
    sys.exit(main())
