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

import functools

from boba.world import (DRINK_APPEAL, DRINK_COST, DRINK_PRICE, HOURLY_RATE,
                        HOURLY_WTP_MULT, PEAK_HOURS, PEARL_COST, QTY_CAP,
                        TICKS_PER_DAY, TOP_APPEAL, TOP_COST, TOP_LIKE_PROB,
                        TOP_PRICE, TOP_SIGMA, WTP_SIGMA,
                        Consumer, ShopState, _pstar_single, _sf, _value_price,
                        balk_prob, best_menu_order, bundle_value, capacity_relief,
                        expected_cups_per_arrival, hour_of, outside_surplus,
                        qty_ladder, service_rate_at, slot_capacity)

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

    BOBA P1a liar-battery knobs (default OFF = byte-identical to P0):
      attest             — False enables the attack (mirrors vend.A2APolicy)
      liar_share         — fraction of buyers (by stable uid) who deviate
      attack_wtp_factor  — strategic_disclosure's wtp_factor for liars
      attack_claim_walk  — strategic_disclosure's claim_walk for liars
    """
    policy_id: str = "cart/1"
    mode: str = "cart"
    min_gain_abs: float = 0.25      # don't-negotiate-for-pennies buffer:
    min_gain_frac: float = 0.10     # max($0.25, 10% of cart list value)
    defer_slots: bool = True
    salvage: bool = True
    quote_lookers: bool = True
    attest: bool = True
    liar_share: float = 0.0
    attack_wtp_factor: float = 0.55
    attack_claim_walk: bool = True
    # BOBA P1a fix (#58): validate the outside-option claim against observable
    # competitor prices. Default OFF = byte-identical to P0 (a no-op for honest
    # buyers regardless, since their disclosed valuation IS their claim).
    market_floor: bool = False
    # plausibility clamps (default off = byte-identical to P0): cap qty to the
    # buyer's genuine appetite, and floor the price at a fraction of the menu.
    qty_appetite: bool = False
    min_price_frac: float = 0.0

    def boards(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        return sticker_boards()

    def quote_for(self, state: ShopState, consumer: Consumer) -> CartDeal | None:
        return cart_nash(state, consumer, self.min_gain_abs, self.min_gain_frac,
                         defer_slots=self.defer_slots, salvage=self.salvage,
                         quote_lookers=self.quote_lookers,
                         market_floor=self.market_floor,
                         qty_appetite=self.qty_appetite,
                         min_price_frac=self.min_price_frac)


def cart_nash(state: ShopState, consumer: Consumer,
              min_gain_abs: float = 0.25,
              min_gain_frac: float = 0.10, *,
              defer_slots: bool = True,
              salvage: bool = True,
              quote_lookers: bool = True,
              outside_consumer: Consumer | None = None,
              market_floor: bool = False,
              qty_appetite: bool = False,
              min_price_frac: float = 0.0) -> CartDeal | None:
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

    `outside_consumer` (BOBA P1 liar battery): the consumer object used to
    price the OUTSIDE alternative (the coffee-shop-next-door surplus),
    independent of `consumer` — the disclosed one used for everything else
    (bundle value, the sticker counterfactual). Defaults to `consumer`
    itself (honest disclosure, byte-identical to P0). This is boba's analog
    of vend's zero-walk claim: vend's buyer can zero the walk-cost friction
    that gates its bodega surplus, independent of its WTP lie; boba's
    outside_surplus has no separate friction term (the 10% markup is the
    world's, not the consumer's), so the equivalent lie is claiming a
    DIFFERENT (typically truer, larger) valuation of the coffee shop next
    door than the one used to lowball this counter — 'I don't want much of
    this menu, but I'd happily pay full price two doors down.'

    `market_floor` (BOBA P1a fix, issue #58): bound that outside-option term
    by an OBSERVABLE competitor-price floor. The WTP-understatement is
    genuinely private, but the OUTSIDE-OPTION claim is NOT — in a dense block
    the rival carts' posted prices are public. So the buyer's claimed BATNA is
    validated against them: the outside surplus can be no richer than what the
    buyer's OWN disclosed valuation earns at the observable competitor board
    (`outside_surplus` already prices against the +10%-markup posted menu). A
    buyer who lowballs their in-store WTP cannot ALSO claim they'd 'happily pay
    full price two doors down' — the same person can't value the same drink low
    here and high there, and the shop can SEE the there-price. This is NOT the
    RealPage move: we use competitors' PUBLIC prices only to CHECK a buyer's
    self-serving claim, never to coordinate OUR OWN price off a rival's — our
    prices never reference theirs, we only refuse to credit an unobservable
    outside-option story. It floors the observable lie (claim_walk) and leaves
    the genuinely-private WTP-understatement (which shrinks the disclosed menu
    counterfactual d_shop) untouched — that residual is vend's finite-stock
    shadow-pricing job, out of scope here.
    """
    b = balk_prob(state)
    pearls_stocked = state.pearl_stock()
    s_out = outside_surplus(outside_consumer if outside_consumer is not None
                            else consumer)
    if market_floor:
        s_out = min(s_out, outside_surplus(consumer))

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
                # plausibility: don't upsell a cup the buyer values below cost
                # (relief/topping harvest inflating qty is "a bug wearing a
                # bundle" — world.bundle_value note; opt-in, off = byte-ident.)
                if qty_appetite and q > 1 and \
                        consumer.wtp[d] * consumer.qty_decay ** (q - 1) < DRINK_COST[d]:
                    break
                lad += consumer.qty_decay ** (q - 1)
                val = (consumer.wtp[d] + tval) * lad
                cost = q * (DRINK_COST[d] + tcost)
                listv = q * (DRINK_PRICE[d] + tlist)
                # plausibility floor: no deal below min_price_frac of the menu
                # (a real shop's deepest genuine markdown; caps the relief-
                # forecast's price pull; 0.0 = off = byte-identical).
                lo = max(cost, min_price_frac * listv)
                if lo >= listv:
                    rungs = [round(listv, 2)]
                else:
                    step = (listv - lo) / (PRICE_RUNGS - 1)
                    rungs = [round(lo + i * step, 2)
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


# ── BOBA P1a: the liar battery ───────────────────────────────────────────
def strategic_disclosure(consumer: Consumer, wtp_factor: float = 1.0,
                         claim_walk: bool = False
                         ) -> tuple[Consumer, Consumer | None]:
    """boba's analog of vend.scenario.strategic_disclosure(wtp_factor,
    zero_walk): scale every disclosed drink AND topping WTP by wtp_factor
    (<1 understates/anchors, >1 overstates) — the same lever vend sweeps.
    `claim_walk` is boba's analog of vend's zero-walk claim: vend can
    independently zero the walk-cost friction gating its bodega surplus;
    boba's outside_surplus has no separate friction term to zero (the 10%
    markup is the world's, not the consumer's), so the structurally
    equivalent lie is decoupling the coffee-shop valuation from the
    in-store anchoring lie — claim_walk=True reports it at TRUE (unscaled)
    value regardless of wtp_factor, inflating the buyer's apparent BATNA
    exactly the way zero_walk inflates vend's, independent of the anchor.

    Returns (disclosed_consumer, outside_consumer): the first feeds every
    other part of cart_nash (bundle value, the sticker counterfactual); the
    second is what outside_surplus is priced against (None ⇒ honest, use
    the disclosed consumer itself, byte-identical to not lying at all)."""
    disclosed = Consumer(fav=consumer.fav,
                         wtp={d: v * wtp_factor for d, v in consumer.wtp.items()},
                         top_wtp={t: v * wtp_factor for t, v in consumer.top_wtp.items()},
                         flexible=consumer.flexible, qty_decay=consumer.qty_decay,
                         uid=consumer.uid)
    return disclosed, (consumer if claim_walk else None)


def buyer_disagreement(state: ShopState, consumer: Consumer) -> float:
    """The buyer's TRUE no-deal payoff: the same event-consistent mixture
    cart_nash computes internally for d_buyer (full-cart settings —
    salvage doesn't enter d_buyer, only d_shop), exposed standalone so the
    liar battery can check a lying buyer's REAL acceptance against their
    REAL alternative, never the disclosed one they used to angle for a
    quote, and so the menu-fairness arm (which never negotiates at all)
    has the same honest yardstick to accept or decline a posted price
    against."""
    b = balk_prob(state)
    s_out = outside_surplus(consumer)
    pearls_stocked = state.pearl_stock()
    d0, q0, t0, s_menu = best_menu_order(consumer, DRINK_PRICE, TOP_PRICE,
                                         pearls_ok=pearls_stocked >= QTY_CAP)
    if d0 is not None and s_menu > 0 and s_menu >= s_out:
        return (1.0 - b) * s_menu + b * s_out
    return s_out


# ── BOBA P1b: menu fairness — a small, person-independent public menu ────
@dataclass(frozen=True)
class MenuTier:
    """One posted price board on the menu-fairness broker's public list —
    identical for every persona who sees it. `drink_prices`/`top_prices`
    are plain dicts (never a function of who's asking); `slot_ticks` is 0
    (now) or +30/+60 for a balk-free deferred pickup; `min_qty` is the
    tier's screening friction for a same-time, same-drink markdown — a
    flat discount with NO friction is not a menu, it's a price cut everyone
    takes (P0's diagnosed cannibalization failure, one level up); requiring
    qty≥2 makes it a real bulk deal, self-selected by who actually wants
    more, exactly like a retail '2 for' rack."""
    name: str
    drink_prices: dict
    top_prices: dict
    slot_ticks: int = 0
    min_qty: int = 1


def _best_order_min_qty(consumer: Consumer, drink_prices: dict,
                        top_prices: dict, min_qty: int,
                        pearls_ok: bool = True
                        ) -> tuple[str | None, int, tuple[str, ...], float]:
    """world.best_menu_order restricted to qty >= min_qty — the bundle
    tier's screening device: the discount only unlocks if the buyer
    commits to the larger order, so it can't be harvested by everyone for
    free (unlike a flat same-qty markdown, which any buyer trivially takes
    regardless of whether they were ever price-sensitive)."""
    best = (None, 0, (), 0.0)
    avail = [t for t in top_prices if pearls_ok or t != "pearls"]
    for q in range(min_qty, QTY_CAP + 1):
        lad = qty_ladder(consumer.qty_decay, q)
        chosen = tuple(t for t in avail
                       if consumer.top_wtp[t] * lad > q * top_prices[t])
        top_val = sum(consumer.top_wtp[t] for t in chosen)
        top_price = sum(top_prices[t] for t in chosen)
        for d, p in drink_prices.items():
            s = (consumer.wtp[d] + top_val) * lad - q * (p + top_price)
            if s > best[3]:
                best = (d, q, chosen, s)
    return best


@functools.lru_cache(maxsize=None)
def menu_for_context(hour: int) -> tuple[MenuTier, ...]:
    """THE person-independent menu (BOBA P1's mitigation for the 45%
    discrimination ceiling): a small set of PUBLIC price boards derived
    ONLY from the hour — population WTP statistics (DRINK_APPEAL/TOP_APPEAL
    at this hour's multiplier), never any individual's disclosed
    willingness. Same hour ⇒ byte-identical tuple of tiers for every
    persona (this function doesn't even accept a consumer argument) —
    self-SELECTION off a fixed list, not price discrimination. Each tier
    pairs one posted markdown (world._value_price, the person-independent
    analog of the cart's personalized looker conversion) with a REAL
    screening friction — a menu with none collapses into a flat discount
    everyone takes, which is P0's cannibalization failure recurring at the
    bundle level:

      list       — the static board, always available, no friction.
      topper     — drink at list, TOPPINGS at the value markdown. Self-
                   limiting without a min_qty trick: best_menu_order only
                   adds a topping the buyer actually wants above its
                   price, so a buyer with no topping taste sees this tier
                   collapse to identical-to-list; the friction here is
                   genuine desire for a topping, not price sensitivity
                   alone (a real, if partial, discrimination leak — see
                   RESULTS.md).
      bundle     — drink AND toppings at the value markdown, but ONLY at
                   qty>=2 (`min_qty`) — a bulk deal. Screens on quantity:
                   worth taking only if the decayed 2nd/3rd cup clears the
                   discounted price, which a genuine solo buyer's low
                   qty_decay makes unlikely.
      value-defer30/60 — the SAME value prices plus a balk-free pickup
                   slot, offered only in the structurally congested hours
                   (PEAK_HOURS). Screens on flexibility (RIGID_DEFER costs
                   real dollars) — the pre-registered fairness-CLEAN
                   logistics lever.

    Pearls-expiry salvage is deliberately omitted (P0 found it worth
    ~$0.05/day — immaterial, and it's a live-batch signal that would force
    a finer-grained, tick-level cache key for no measurable gain)."""
    mult = HOURLY_WTP_MULT[hour]
    value_drinks = {d: _value_price(round(DRINK_APPEAL[d] * mult, 6),
                                    round(DRINK_COST[d], 6), DRINK_PRICE[d],
                                    WTP_SIGMA)
                    for d in DRINK_PRICE}
    value_tops = {t: _value_price(round(TOP_APPEAL[t], 6),
                                  round(TOP_COST[t], 6), TOP_PRICE[t],
                                  TOP_SIGMA)
                 for t in TOP_PRICE}
    tiers = [MenuTier("list", DRINK_PRICE, TOP_PRICE, 0, 1),
            MenuTier("topper", DRINK_PRICE, value_tops, 0, 1),
            MenuTier("bundle", value_drinks, value_tops, 0, 2)]
    if hour in PEAK_HOURS:
        tiers.append(MenuTier("value-defer30", value_drinks, value_tops, 3, 1))
        tiers.append(MenuTier("value-defer60", value_drinks, value_tops, 6, 1))
    return tuple(tiers)


def menu_pick(state: ShopState, consumer: Consumer, *,
             defer_tiers: bool = True) -> CartDeal | None:
    """The menu-fair quote: the buyer self-selects the best-for-THEM option
    off menu_for_context's PUBLIC tiers, using their own TRUE preferences —
    no disclosure, no negotiation, nothing keyed on who they are. Returns
    the same CartDeal shape cart_nash does so the P0 runner's cart branch
    (balk timing, settlement, accounting) works unmodified.

    `defer_tiers=False` is the decomposition ablation (RESULTS.md): drop
    the value-defer tiers to isolate the (topper + bundle) discrimination-
    lite tiers from the capacity-smoothing logroll."""
    b = balk_prob(state)
    s_out = outside_surplus(consumer)
    d_buyer = buyer_disagreement(state, consumer)
    pearls_stocked = state.pearl_stock()
    best = None
    for tier in menu_for_context(hour_of(state.tick)):
        if tier.slot_ticks > 0 and not defer_tiers:
            continue
        chooser = (_best_order_min_qty if tier.min_qty > 1 else best_menu_order)
        args = (consumer, tier.drink_prices, tier.top_prices,
                tier.min_qty) if tier.min_qty > 1 else (
                consumer, tier.drink_prices, tier.top_prices)
        drink, qty, tops, sval = chooser(
            *args, pearls_ok=pearls_stocked >= QTY_CAP)
        if drink is None or sval <= 0:
            continue
        if tier.slot_ticks > 0:
            if slot_capacity(state, state.tick + tier.slot_ticks) < qty:
                continue                    # that pickup slot is sold out
        price = round(qty * (tier.drink_prices[drink]
                             + sum(tier.top_prices[t] for t in tops)), 2)
        val = bundle_value(consumer, drink, qty, tops)
        surv = (1.0 - b) if tier.slot_ticks == 0 else 1.0
        dis = consumer.defer_cost(tier.slot_ticks)
        u_b = surv * (val - price) + (1.0 - surv) * s_out - dis
        if u_b < d_buyer - 1e-9:
            continue                        # not worth it to THIS buyer
        ceff = {t: top_c_eff(state, t) for t in tops}
        cost = qty * (DRINK_COST[drink] + sum(ceff[t] for t in tops))
        relief = capacity_relief(state, qty, tier.slot_ticks) \
            if tier.slot_ticks else 0.0
        u_s = surv * (price - cost) + relief
        # the buyer picks whichever tier maximizes THEIR OWN surplus — the
        # broker never steers the choice, it only fixes the price boards
        if best is None or u_b > best[0]:
            best = (u_b, tier, drink, qty, tops, price, val, u_s, relief)
    if best is None:
        return None
    u_b, tier, drink, qty, tops, price, val, u_s, relief = best
    listv = qty * (DRINK_PRICE[drink] + sum(TOP_PRICE[t] for t in tops))
    why = [f"menu: {tier.name}"]
    if tier.slot_ticks > 0:
        why.append(f"+{tier.slot_ticks * 10}-min pickup, same posted price")
    if price < listv - 1e-9:
        why.append(f"${listv - price:.2f} under the menu (posted, not personal)")
    else:
        why.append("at menu")
    return CartDeal(drink=drink, qty=qty, tops=tops, price=price,
                    slot_ticks=tier.slot_ticks, value=val, u_shop=u_s,
                    d_shop=0.0, u_buyer=u_b, d_buyer=d_buyer, relief=relief,
                    why=tuple(why))


@dataclass
class MenuPolicy:
    """BOBA P1b: the menu-fair broker. `boards()` fallback and `mode` match
    CartPolicy exactly so the P0 runner's cart branch handles it with zero
    changes — the only difference is HOW the quote is produced (self-
    selection off a small public menu, not a bespoke Nash search)."""
    policy_id: str = "menu/1"
    mode: str = "cart"
    defer_tiers: bool = True

    def boards(self, state: ShopState) -> tuple[dict[str, float], dict[str, float]]:
        return sticker_boards()

    def quote_for(self, state: ShopState, consumer: Consumer) -> CartDeal | None:
        return menu_pick(state, consumer, defer_tiers=self.defer_tiers)
