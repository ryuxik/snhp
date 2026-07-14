"""Boba vertical expressed as a core OfferGraph — the G1 golden-master adapter.

Since the engine flip, boba.policies.cart_nash is a thin delegation to
`engine_cart_nash` below: the bespoke Nash-search body was deleted after the
golden gates proved the engine reproduces it on the shipped trajectories
(100% of 11,443 replayed ship-config quotes; committed band byte-exact). This
adapter constructs boba's offer graph, its state-dependent cost model, a
per-quote ShopState, and a per-consumer SeparableBuyer from boba's OWN
constants and world helpers, and runs core.engine.quote over them.

KNOWN BOUNDARY (documented at the flip, 2026-07-14): at EXACT decimal ties on
the min-gain buffer max($0.25, 0.10·list), the bespoke pricer's and the
engine's one-ulp-different float expression trees could disagree — under the
P0 default config (clamps off) 2 of 2,316 replayed quotes hit such a tie
(witness: seed 20260710 day 0 tick 36 — cart_nash listv = 30.900000000000002 /
d_s = 7.45, gs−thr = −4e-16, walks; engine listv = 30.9 / d_s =
7.449999999999999, gs = thr = 3.09, deals). The deployed clamps (qty_appetite,
min_price_frac=0.6) kept every golden trajectory off ties. The P0 artifacts
affected by the ulp-tie deltas were re-pinned from their committed generators
at the flip (verdicts unchanged).

The mapping (docs/REDESIGN.md Phase 2), dimension by dimension:

  drink   CHOICE       price_delta=DRINK_PRICE, unit_cost=DRINK_COST
  tops    ADDON        price_delta=TOP_PRICE,   unit_cost=TOP_COST; pearls are
                       `stock_limited` (the pearls_stocked<q HARD gate) and
                       `perishable`/salvage 0 (top_c_eff → 0 when the batch is
                       expiring in excess).
  pickup  FULFILLMENT  now (immediate, slot 0) / +30 (slot 3) / +60 (slot 6),
                       each carrying the buyer's defer_cost and the shop's
                       capacity_relief credit for a deferred peak slot.
  qty     QUANTITY     1..QTY_CAP.

  (sweetness / ice — cart_nash omits them; so does this graph.)

The cost model composes const() + salvage_on_expiry() + capacity_relief(fn):
  - const/salvage reproduce cart_nash's `ceff[t]` (salvage-adjusted topping
    cost) and the drink cost;
  - capacity_relief(fn) reproduces the `r = capacity_relief(state, q, s)` credit
    added to the shop's gain for a deferred peak slot.

`engine_cart_nash` is a DROP-IN for boba.policies.cart_nash (same signature,
same CartDeal|None return, same None semantics), so the sim harness swaps the
pricer with a one-token change.
"""
from __future__ import annotations

from core.cost import capacity_relief, compose, const, salvage_on_expiry
from core.deps import DepGraph
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as _core_quote
from core.offer_graph import DimKind, Dimension, OfferGraph, Option
from core.state import ShopState

from boba import world
from boba.policies import CartDeal, pearls_expiring_excess, top_c_eff

PICKUP_SLOTS = (("now", True, 0), ("d30", False, 3), ("d60", False, 6))
_NEG_INF = float("-inf")


# ── the graph (built once; it is the static menu, buyer-independent) ───────
def _relief(graph: OfferGraph, state: ShopState, config, qty: int) -> float:
    """capacity_relief credit for the config's fulfillment slot — boba's
    `r = world.capacity_relief(boba_state, q, s)` (policies.py:306). Reads the
    live boba ShopState stashed in state.extra['boba']; a now/absent slot pays
    nothing (world.capacity_relief returns 0 for slot_ticks<=0)."""
    boba_state = state.extra.get("boba")
    if boba_state is None:
        return 0.0
    slot_ticks = 0
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            slot_ticks = d.option(config[d.id]).slot_ticks
            break
    if slot_ticks <= 0:
        return 0.0
    return world.capacity_relief(boba_state, qty, slot_ticks)


def build_graph() -> OfferGraph:
    """boba's offer graph from world.DRINK_*/TOP_* — no shop state, no buyer."""
    drink = Dimension("drink", DimKind.CHOICE, options=tuple(
        Option(d, label=d, price_delta=world.DRINK_PRICE[d],
               unit_cost=world.DRINK_COST[d])
        for d in world.DRINK_PRICE))
    tops = Dimension("tops", DimKind.ADDON, options=tuple(
        Option(t, label=t, price_delta=world.TOP_PRICE[t],
               unit_cost=world.TOP_COST[t],
               perishable=(t == "pearls"), salvage=0.0,
               stock_limited=(t == "pearls"))
        for t in world.TOP_PRICE))
    pickup = Dimension("pickup", DimKind.FULFILLMENT, options=tuple(
        Option(name, immediate=imm, slot_ticks=st)
        for name, imm, st in PICKUP_SLOTS))
    qty = Dimension("qty", DimKind.QUANTITY, qty_cap=world.QTY_CAP)
    return OfferGraph(
        dims=[drink, tops, pickup, qty], deps=DepGraph(),
        cost=compose(const(), salvage_on_expiry(), capacity_relief(_relief)),
        name="boba")


GRAPH = build_graph()


# ── per-quote projections of the live boba world ───────────────────────────
def shop_state(boba_state, *, defer_slots: bool = True,
               salvage: bool = True) -> ShopState:
    """Project boba.world.ShopState onto the generic core ShopState.

    - inventory['pearls'] = live pearl stock → the stock_limited HARD gate
      reproduces `pearls_stocked < q: break` (policies.py:320).
    - expiring = {'pearls'} iff the batch is clearing (salvage on) → the
      salvage_on_expiry cost carve-out reproduces top_c_eff → 0.
    - capacity[3/6] = slot_capacity(...) when the deferred slot is offered
      (defer_slots on AND it lands before close), else -inf to force-drop it —
      reproducing cart_nash's `slots`/`slot_room` construction (policies.py:302).
    - extra['boba'] = the live boba state, for the relief credit.
    """
    inventory = {"pearls": float(boba_state.pearl_stock())}
    expiring = ({"pearls"} if salvage and pearls_expiring_excess(boba_state)
                else set())
    capacity = {}
    for st in (3, 6):
        if defer_slots and boba_state.tick + st < world.TICKS_PER_DAY:
            capacity[st] = world.slot_capacity(boba_state, boba_state.tick + st)
        else:
            capacity[st] = _NEG_INF          # slot not offered → always dropped
    return ShopState(tick=boba_state.tick, inventory=inventory,
                     capacity=capacity, expiring=expiring,
                     extra={"boba": boba_state})


def buyer_for(boba_state, consumer, outside_consumer=None, *,
              market_floor: bool = False) -> SeparableBuyer:
    """A SeparableBuyer from a boba Consumer.

    `consumer` is the DISCLOSED consumer (== the true one when honest); its
    wtp / top_wtp / qty_decay drive value and appetite. `outside_consumer`
    (cart_nash's liar-battery hook) prices the outside option independently —
    None ⇒ the disclosed consumer itself. `market_floor` caps the claimed
    outside surplus by the disclosed consumer's own (policies.py:277)."""
    s_out = world.outside_surplus(
        outside_consumer if outside_consumer is not None else consumer)
    if market_floor:
        s_out = min(s_out, world.outside_surplus(consumer))
    values = {}
    for d in world.DRINK_PRICE:
        values[("drink", d)] = consumer.wtp[d]
    for t in world.TOP_PRICE:
        values[("tops", t)] = consumer.top_wtp[t]
    defer = {st: consumer.defer_cost(st) for st in (0, 3, 6)}
    return SeparableBuyer(values=values, qty_decay=consumer.qty_decay,
                          outside=s_out, balk=world.balk_prob(boba_state),
                          defer=defer)


def cart_nash_search_filter(boba_state, consumer, *, salvage: bool = True):
    """Build cart_nash's EXACT (incomplete) search space as a search_filter.

    cart_nash restricts its Nash search two ways the engine's full enumeration
    does not (policies.py:298, 311):
      - a drink d is searched only if `consumer.wtp[d] > DRINK_COST[d]` (no
        joint gain otherwise);
      - topping subsets are the NESTED PREFIXES of the toppings ranked by
        `top_wtp[t] − ceff[t]` (descending), among those with
        `top_wtp[t] > ceff[t]` — NOT every subset.

    Restricting only the SEARCH (never the disagreement, which stays the full
    best_menu_order counterfactual) reproduces cart_nash cart-for-cart,
    including the rare corner where its prefix search MISSES a better non-prefix
    topping set (e.g. {pearls, pudding} when the ranking is
    [pearls, cheese-foam, pudding])."""
    ceff = {t: (top_c_eff(boba_state, t) if salvage else world.TOP_COST[t])
            for t in world.TOP_PRICE}
    ranked = sorted((t for t in world.TOP_PRICE if consumer.top_wtp[t] > ceff[t]),
                    key=lambda t: consumer.top_wtp[t] - ceff[t], reverse=True)
    allowed_tops = {frozenset(ranked[:i]) for i in range(len(ranked) + 1)}
    allowed_drinks = {d for d in world.DRINK_PRICE
                      if consumer.wtp[d] > world.DRINK_COST[d]}

    def _filter(graph, state, buyer, config) -> bool:
        if config.get("drink") not in allowed_drinks:
            return False
        return frozenset(config.get("tops") or ()) in allowed_tops

    return _filter


# ── the drop-in pricer ─────────────────────────────────────────────────────
def engine_cart_nash(boba_state, consumer, min_gain_abs: float = 0.25,
                     min_gain_frac: float = 0.10, *,
                     defer_slots: bool = True, salvage: bool = True,
                     quote_lookers: bool = True,
                     outside_consumer=None, market_floor: bool = False,
                     qty_appetite: bool = False,
                     min_price_frac: float = 0.0) -> CartDeal | None:
    """core.engine.quote wearing boba.policies.cart_nash's signature.

    Returns a CartDeal (boba's own dataclass) on a negotiated discount, else
    None — reproducing cart_nash's None semantics EXACTLY: the engine's
    feasible=False at-list fallback (a menu-buyer with no beating deal) maps
    back to None, so the sim's walk-in branch prices the menu the same way it
    does for cart_nash's None."""
    state = shop_state(boba_state, defer_slots=defer_slots, salvage=salvage)
    buyer = buyer_for(boba_state, consumer, outside_consumer,
                      market_floor=market_floor)
    opts = QuoteOpts(
        min_price_frac=min_price_frac, qty_appetite=qty_appetite,
        qty_appetite_scope="choice" if qty_appetite else "bundle",
        quote_lookers=quote_lookers, min_gain_abs=min_gain_abs,
        min_gain_frac=min_gain_frac, price_rungs=8, seller_weight=0.5,
        prune_free=True,
        search_filter=cart_nash_search_filter(boba_state, consumer,
                                              salvage=salvage))
    q = _core_quote(GRAPH, state, buyer, opts=opts)
    if q is None or not q.feasible:
        return None
    drink = q.config["drink"]
    tops = tuple(sorted(q.config["tops"]))
    qty = int(q.config["qty"])
    slot_ticks = GRAPH.dim("pickup").option(q.config["pickup"]).slot_ticks
    d_seller = q.audit.get("d_seller", 0.0)
    d_buyer = q.audit.get("d_buyer", 0.0)
    # boba's canonical receipt strings (cart_nash's exact formats — the arena
    # trace generator asserts on them, e.g. "pearls from the expiring batch"),
    # rebuilt here instead of passing the engine's generic q.why through.
    why = ["negotiated cart"]
    if slot_ticks > 0:
        why.append(f"+{slot_ticks * 10}-min pickup frees peak capacity")
    if "pearls" in tops and top_c_eff(boba_state, "pearls") == 0.0:
        why.append("pearls from the expiring batch")
    if q.price < q.listv - 1e-9:
        why.append(f"${q.listv - q.price:.2f} under the menu")
    else:
        why.append("at menu")
    return CartDeal(
        drink=drink, qty=qty, tops=tops, price=q.price, slot_ticks=slot_ticks,
        value=q.value, u_shop=q.seller_gain + d_seller, d_shop=d_seller,
        u_buyer=q.buyer_gain + d_buyer, d_buyer=d_buyer,
        relief=q.audit.get("credit", 0.0), why=tuple(why))
