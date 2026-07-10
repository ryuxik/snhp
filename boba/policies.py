"""Pricing policies — the three arms of the boba experiment.

  static/1   — the posted calibration menu (block/calibration.py), verbatim.
               By construction of world.DRINK_APPEAL it is the profit-optimal
               all-day posted price: a competent gut menu, not a strawman.
  computed/1 — hourly re-price per drink: profit-max against THIS hour's
               crowd vs a capacity run-out shadow (hold at list when the
               window's expected demand exceeds the bar-minutes left),
               plus an end-of-batch pearls markdown. Discount-only.
  cart/1     — per-arrival Nash quote over (drink × toppings × qty ×
               price rung × pickup slot). Machine utility = margin +
               capacity-relief value of deferred peak slots + pearls-expiry
               salvage logic; buyer utility = bundle value − price − defer
               disutility; disagreement = the event-consistent no-deal
               world (walk in: balk with prob b to the coffee shop, else
               buy the sticker menu). Discount-only vs the menu.

Model notes: the computed arm's demand belief equals the true process
(favorable to it, flagged in results); cart topping subsets are searched as
nested prefixes ranked by (value − opportunity cost) — the jointly optimal
family except in rare ceiling-binding corners.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from boba.world import (DRINK_APPEAL, DRINK_COST, DRINK_PRICE, HOURLY_RATE,
                        HOURLY_WTP_MULT, PEARL_COST, QTY_CAP,
                        TICKS_PER_DAY, TOP_APPEAL, TOP_COST, TOP_LIKE_PROB,
                        TOP_PRICE, TOP_SIGMA, WTP_SIGMA,
                        Consumer, ShopState, _pstar_single, _sf, balk_prob,
                        best_menu_order, bundle_value, capacity_relief,
                        expected_cups_per_arrival, hour_of, outside_surplus,
                        service_rate_at, slot_capacity)

PRICE_RUNGS = 8
BATCH_CLEARANCE_WINDOW = 6      # ticks (1 hour) before expiry counts as "soon"

# Pearl attach rate at the list price — the shop's structural forecast of
# how fast a batch drains (used only for the clearance trigger).
PEARL_ATTACH_LIST = TOP_LIKE_PROB["pearls"] * _sf(
    TOP_PRICE["pearls"], TOP_APPEAL["pearls"], TOP_SIGMA)


def pearls_expiring_excess(state: ShopState) -> bool:
    """True when the earliest live batch dies within the hour AND holds
    more servings than list-price demand can drain before then — the
    end-of-batch markdown surface (BOBA.md #3)."""
    live = [b for b in state.batches if b.servings > 0]
    if not live:
        return False
    first = min(live, key=lambda b: b.expires_tick)
    ticks_left = first.expires_tick - state.tick
    if ticks_left > BATCH_CLEARANCE_WINDOW or ticks_left <= 0:
        return False
    exp_pearls = sum(
        HOURLY_RATE[hour_of(t)] / 6.0 * expected_cups_per_arrival(hour_of(t))
        * PEARL_ATTACH_LIST
        for t in range(state.tick, min(first.expires_tick, TICKS_PER_DAY)))
    return first.servings > exp_pearls


def top_c_eff(state: ShopState, top: str) -> float:
    """Opportunity cost of one topping serving: pearls from a batch that is
    about to be waste are free to move (salvage 0); everything else costs
    its ingredients."""
    if top == "pearls" and pearls_expiring_excess(state):
        return 0.0
    return TOP_COST[top]


def sticker_boards() -> tuple[dict[str, float], dict[str, float]]:
    """THE calibration menu — the control arm's product and every other
    arm's fallback, one implementation."""
    return dict(DRINK_PRICE), dict(TOP_PRICE)


@dataclass
class StaticMenu:
    """The control: the shop's posted gut menu, all day, every day."""
    policy_id: str = "static/1"

    def boards(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        return sticker_boards()


@dataclass
class ComputedMenu:
    """GvR-for-boba: once an hour, re-solve each drink's posted price
    against the current crowd, with a capacity run-out shadow — when the
    expected list-price demand between now and the next staffing change
    exceeds the bar-minutes left (net of the standing queue), there is no
    reason to discount: the queue will eat every slot at full price. The
    discount-only clamp eats all upside above list by design. Pearls get a
    computed end-of-batch markdown (price re-solved at salvage cost 0).

    Prices are decided from the state at the hour's FIRST arrival and held
    for the hour ("hourly re-price") — deterministic given the run."""
    policy_id: str = "computed/1"
    _cache: dict = field(default_factory=dict)

    def boards(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        key = (state.day, hour_of(state.tick))
        if key not in self._cache:
            self._cache[key] = self._solve(state)
        return self._cache[key]

    def _solve(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        h = hour_of(state.tick)
        mult = HOURLY_WTP_MULT[h]
        hold_at_list = self._runout_binding(state)
        drinks = {}
        for d, lp in DRINK_PRICE.items():
            if hold_at_list:
                drinks[d] = lp
                continue
            p_hour = _pstar_single(round(DRINK_APPEAL[d] * mult, 6),
                                   round(DRINK_COST[d], 6), WTP_SIGMA)
            drinks[d] = round(min(lp, max(DRINK_COST[d], p_hour)), 2)
        tops = dict(TOP_PRICE)
        if pearls_expiring_excess(state):
            clear = _pstar_single(round(TOP_APPEAL["pearls"], 6), 0.0, TOP_SIGMA)
            tops["pearls"] = round(min(TOP_PRICE["pearls"], max(0.05, clear)), 2)
        return drinks, tops

    def _runout_binding(self, state: ShopState) -> bool:
        """Expected drinks demanded AT LIST between now and the next
        staffing boundary vs bar capacity left (net of the queue)."""
        t0 = state.tick
        boundaries = [24, 54, TICKS_PER_DAY]     # 14:00, 19:00, close
        t_end = next(b for b in boundaries if b > t0)
        cap = sum(service_rate_at(t) * 10.0 for t in range(t0, t_end)) \
            - state.queue_drinks()
        demand = sum(HOURLY_RATE[hour_of(t)] / 6.0
                     * expected_cups_per_arrival(hour_of(t))
                     for t in range(t0, t_end))
        return demand > cap


@dataclass(frozen=True)
class CartDeal:
    drink: str
    qty: int
    tops: tuple[str, ...]
    price: float               # cart TOTAL, discount-only vs the menu
    slot_ticks: int            # 0 = now, 3 = +30 min, 6 = +60 min
    value: float               # buyer's bundle value (for realized surplus)
    u_shop: float              # EXPECTED margin + relief of this outcome
    d_shop: float              # shop's event-consistent disagreement
    u_buyer: float             # EXPECTED value − price − defer disutility
    d_buyer: float             # buyer's event-consistent disagreement
    relief: float
    why: tuple[str, ...]

    @property
    def list_value(self) -> float:
        return self.qty * (DRINK_PRICE[self.drink]
                           + sum(TOP_PRICE[t] for t in self.tops))


@dataclass
class CartPolicy:
    """The negotiated cart: quote BEFORE the walk-in balk (the order is a
    cart on a phone). Fallback is the plain sticker menu, so the arm is
    never worse UX than static.

    The three ablation switches exist to decompose the edge honestly in
    RESULTS.md (all default ON = the full arm):
      defer_slots   — offer +30/+60 pickup slots (capacity smoothing)
      salvage       — pearls from an expiring batch cost 0 (batch clearance)
      quote_lookers — negotiate with buyers who would NOT have bought at
                      the sticker (personalized sub-list conversion)
    """
    policy_id: str = "cart/1"
    mode: str = "cart"
    min_gain_abs: float = 0.25      # don't-negotiate-for-pennies buffer:
    min_gain_frac: float = 0.10     # max($0.25, 10% of cart list value)
    defer_slots: bool = True
    salvage: bool = True
    quote_lookers: bool = True

    def boards(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        return sticker_boards()

    def quote_for(self, state: ShopState, consumer: Consumer) -> CartDeal | None:
        return cart_nash(state, consumer, self.min_gain_abs, self.min_gain_frac,
                         defer_slots=self.defer_slots, salvage=self.salvage,
                         quote_lookers=self.quote_lookers)


def cart_nash(state: ShopState, consumer: Consumer,
              min_gain_abs: float = 0.25,
              min_gain_frac: float = 0.10, *,
              defer_slots: bool = True,
              salvage: bool = True,
              quote_lookers: bool = True) -> CartDeal | None:
    """Nash bargaining over the cart outcome space, in dollars.

    The disagreement point is one consistent no-deal EVENT for both sides:
    the buyer walks to the counter — with prob b (the live balk risk) the
    queue turns them away to the coffee shop, else they buy their best
    sticker order. So:
        d_buyer = (1-b)·sticker surplus + b·outside surplus
        d_shop  = (1-b)·sticker margin           (balked buyers pay nothing)
    NOW-slot deals face the SAME balk risk (an app order for right-now
    pickup still means standing in that line), so their utilities carry the
    survival weight (1-b) too — the physics a deal cannot negotiate away.
    Deferred slots are balk-free (the customer comes back to a made drink):
    at a hot queue BOTH sides prefer the +30/+60 slot even before capacity
    relief, which is the smoothing logroll working as designed.
    A buyer who would have paid the menu price gets a discount only out of
    newly created surplus (toppings above cost, freed peak capacity, pearls
    that would have been waste) — never out of margin the shop already had.
    """
    b = balk_prob(state)
    pearls_stocked = state.pearl_stock()
    s_out = outside_surplus(consumer)

    # the sticker counterfactual, via the same canonical chooser the
    # simulated walk-in uses (with the same pearls-availability rule)
    d0, q0, t0, s_menu = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                         pearls_ok=pearls_stocked >= QTY_CAP)
    ceff = {t: (top_c_eff(state, t) if salvage else TOP_COST[t])
            for t in TOP_PRICE}
    if d0 is not None and s_menu > 0 and s_menu >= s_out:
        margin_menu = q0 * (DRINK_PRICE[d0] - DRINK_COST[d0]) \
            + q0 * sum(TOP_PRICE[t] - ceff[t] for t in t0)
        d_b = (1.0 - b) * s_menu + b * s_out
        d_s = (1.0 - b) * margin_menu
    else:
        if not quote_lookers:
            return None            # ablation: only quote would-be buyers
        d_b, d_s = s_out, 0.0

    # toppings worth keeping: value above opportunity cost, searched as
    # nested prefixes of the (value − c_eff) ranking
    ranked = sorted((t for t in TOP_PRICE if consumer.top_wtp[t] > ceff[t]),
                    key=lambda t: consumer.top_wtp[t] - ceff[t], reverse=True)
    subsets = [tuple(ranked[:i]) for i in range(len(ranked) + 1)]

    slots = [0] + [s for s in ((3, 6) if defer_slots else ())
                   if state.tick + s < TICKS_PER_DAY]
    slot_room = {s: (slot_capacity(state, state.tick + s) if s > 0 else QTY_CAP)
                 for s in slots}
    relief = {(q, s): capacity_relief(state, q, s)
              for q in range(1, QTY_CAP + 1) for s in slots}
    defer = {s: consumer.defer_cost(s) for s in slots}

    best, best_score = None, None
    for d in DRINK_PRICE:
        if consumer.wtp[d] <= DRINK_COST[d]:
            continue                       # no joint gain is possible here
        for T in subsets:
            tval = sum(consumer.top_wtp[t] for t in T)
            tcost = sum(ceff[t] for t in T)
            tlist = sum(TOP_PRICE[t] for t in T)
            lad = 0.0
            for q in range(1, QTY_CAP + 1):
                if "pearls" in T and pearls_stocked < q:
                    break
                lad += consumer.qty_decay ** (q - 1)
                val = (consumer.wtp[d] + tval) * lad
                cost = q * (DRINK_COST[d] + tcost)
                listv = q * (DRINK_PRICE[d] + tlist)
                if cost >= listv:
                    rungs = [round(listv, 2)]
                else:
                    step = (listv - cost) / (PRICE_RUNGS - 1)
                    rungs = [round(cost + i * step, 2)
                             for i in range(PRICE_RUNGS)]
                for s in slots:
                    if s > 0 and slot_room[s] < q:
                        continue           # that pickup slot is sold out
                    r = relief[(q, s)]
                    dis = defer[s]
                    surv = (1.0 - b) if s == 0 else 1.0
                    for p in rungs:
                        gs = surv * (p - cost) + r - d_s
                        gb = surv * (val - p) + (1.0 - surv) * s_out - dis - d_b
                        if gs >= -1e-9 and gb >= -1e-9:
                            score = (gs * gb, gs + gb)
                            if best_score is None or score > best_score:
                                best = (d, q, T, p, s, r, val, cost, listv)
                                best_score = score
    if best is None or (best_score[0] <= 0 and best_score[1] <= 1e-9):
        return None                        # nothing improves on no-deal

    d, q, T, p, s, r, val, cost, listv = best
    surv = (1.0 - b) if s == 0 else 1.0
    u_s = surv * (p - cost) + r
    # the buffer: the shop's believed gain must clear max($0.25, 10% of the
    # cart's list value) — forecast noise must not leak margin
    if u_s - d_s < max(min_gain_abs, min_gain_frac * listv):
        return None
    u_b = surv * (val - p) + (1.0 - surv) * s_out - defer[s]
    why = ["negotiated cart"]
    if s > 0:
        why.append(f"+{s * 10}-min pickup frees peak capacity")
    if "pearls" in T and top_c_eff(state, "pearls") == 0.0:
        why.append("pearls from the expiring batch")
    if p < listv - 1e-9:
        why.append(f"${listv - p:.2f} under the menu")
    else:
        why.append("at menu")
    return CartDeal(drink=d, qty=q, tops=T, price=p, slot_ticks=s,
                    value=val, u_shop=u_s, d_shop=d_s, u_buyer=u_b,
                    d_buyer=d_b, relief=r, why=tuple(why))
