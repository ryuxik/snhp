"""The shared quote() — the ONE Nash-floor search both verticals run.

This is boba.cart_nash and vend.nash_quote lifted one abstraction level: the
skeleton is identical; the dimensions come from the OfferGraph and the cost
comes from its CostModel. The formulas below match cart_nash line-for-line
(with vend's seller_weight tilt folded in as a hook).

The skeleton, in order:

  0. Availability gates (HARD) — drop any config that would sell more of a
     stock-limited item than exists, or promise a deferred slot with less
     capacity than the order needs. This is cart_nash's `pearls_stocked < q:
     break` (policies.py:320) and `slot_room[s] < q: continue` (:343), and
     vend's `min(QTY_CAP, stock)` qty cap — separate from any SOFT scarcity
     pricing. Applied BEFORE the disagreement, so the menu counterfactual can
     never be inflated by phantom stock (vend's over-stock-disagreement fix).

  1. Disagreement point — the full-price ("menu") counterfactual, the one
     no-deal EVENT both sides face. The buyer walks to the counter: with prob
     b (the balk risk) the queue turns them away to their outside option,
     else they buy their best sticker order. So d_buyer mixes menu surplus
     and outside surplus by the survival weight, and d_seller is the menu
     margin the shop already had (NO relief credit — cart_nash policies.py:290).
     A buyer who would have paid list gets a discount ONLY out of newly-created
     surplus — never out of standing margin. If they were never a menu buyer
     and we refuse lookers, return None: the IC hard floor.

  2. Configs × price rungs — for each valid config, rungs from the state-
     dependent cost floor up to list (discount-only, never above; never below
     cost — the floor rung is rounded UP to the cent).

  3. Nash split — pick the (config, rung) maximizing the (generalized) Nash
     product of gains above disagreement, lexicographic tiebreak on joint
     gain. Feasible iff BOTH gains ≥ 0.

  4. Guards — never below marginal cost (a relief credit must not fund a
     below-cost sale), min-gain floor, never-above-list, and the opt-in
     plausibility clamps. When nothing beats disagreement, the buyer pays the
     menu.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from core.cost import CostQuote
from core.offer_graph import (Config, DimKind, Negotiability, OfferGraph,
                              freeze_config, normalize_config, qty_of,
                              selected_option_ids, with_qty)
from core.profiler import profile
from core.state import ShopState


# ── the buyer side ───────────────────────────────────────────────────────
class Buyer(Protocol):
    """Minimal, separable buyer. Value of a config = (base choice value + Σ
    add-on values) scaled by a qty ladder — matching cart_nash's
    `val = (wtp[d] + tval) · lad`. Everything else the split needs is a
    scalar the buyer reports."""
    qty_decay: float

    def value(self, graph: OfferGraph, config: Config) -> float: ...
    def outside_surplus(self) -> float: ...
    def balk_prob(self, state: ShopState) -> float: ...
    def defer_cost(self, slot: int) -> float: ...


def qty_ladder(decay: float, qty: int) -> float:
    """Σ decay^(i) for i in 0..qty-1 — the diminishing-cups multiplier
    (boba.world.qty_ladder / vend's QTY_DECAY sum)."""
    return sum(decay ** i for i in range(qty))


@dataclass
class SeparableBuyer:
    """The default concrete buyer: per-option values, a decay, and scalar
    outside/balk/defer reports. Expresses both a boba consumer (drink +
    topping WTPs, defer table) and a vend buyer (per-SKU WTP, zero balk)."""
    values: dict            # (dim_id, option_id) -> per-unit dollar value
    qty_decay: float = 0.15
    outside: float = 0.0
    balk: float = 0.0
    defer: dict = field(default_factory=dict)      # slot -> defer cost

    def value(self, graph: OfferGraph, config: Config) -> float:
        base = 0.0
        qty = 1
        for d in graph.dims:
            sel = config.get(d.id)
            if d.kind == DimKind.QUANTITY:
                qty = int(sel) if sel is not None else 1     # A4
            elif d.kind == DimKind.ADDON:
                base += sum(self.values.get((d.id, o), 0.0) for o in (sel or ()))
            elif d.kind in (DimKind.CHOICE, DimKind.PREFERENCE):
                if sel is not None:
                    base += self.values.get((d.id, sel), 0.0)
            # FULFILLMENT contributes no value (only a defer_cost)
        return base * qty_ladder(self.qty_decay, qty)

    def outside_surplus(self) -> float:
        return self.outside

    def balk_prob(self, state: ShopState) -> float:
        return self.balk

    def defer_cost(self, slot: int) -> float:
        return self.defer.get(slot, 0.0)


# ── options & receipt ────────────────────────────────────────────────────
@dataclass(frozen=True)
class QuoteOpts:
    min_price_frac: float = 0.0     # rung floor at k·list (plausibility clamp)
    min_gain_abs: float = 0.25      # don't-negotiate-for-pennies buffer:
    min_gain_frac: float = 0.10     # max($0.25, 10% of list)
    qty_appetite: bool = False      # don't upsell a unit valued below its cost
    qty_appetite_scope: str = "bundle"  # "bundle" = full per-unit bundle
                                    # marginal (value − cost of the q-th unit);
                                    # "choice" = cart_nash's CHOICE-value-only
                                    # test (drink value vs drink cost, toppings
                                    # ignored — policies.py:326). Default-OFF
                                    # (only read when qty_appetite=True), so
                                    # non-boba verticals are unaffected.
    quote_lookers: bool = True      # False = refuse non-menu-buyers (IC floor)
    seller_weight: float = 0.5      # 0.5 = symmetric Nash; →1 = seller keeps
                                    # all surplus above the buyer's floor
    price_rungs: int = 8            # PRICE_RUNGS
    prune_free: bool = True         # C1: pin FREE preference dims (profiler)
    search_filter: object = None    # optional (graph, state, buyer, config) →
                                    # bool restricting ONLY the negotiation
                                    # search to a bespoke candidate family — the
                                    # DISAGREEMENT (menu counterfactual) still
                                    # ranges over the full available set.
                                    # Default None = search everything. Boba-
                                    # mode uses it to reproduce cart_nash's
                                    # incomplete search (drink-skip +
                                    # (value−c_eff)-ranked nested topping
                                    # prefixes, policies.py:298-314) while the
                                    # disagreement matches best_menu_order.


@dataclass
class Quote:
    """The receipt. `feasible=True` is a negotiated discount; `feasible=False`
    means no split beat the menu, so the buyer pays list. A None return from
    quote() is a *walk* (a refused looker or a non-buyer with no deal)."""
    config: Config | None
    price: float
    listv: float
    cost: float
    value: float
    save: float
    seller_gain: float
    buyer_gain: float
    feasible: bool
    why: list[str]
    audit: dict = field(default_factory=dict)     # p-free primitives for tests


# ── per-config economics ─────────────────────────────────────────────────
@dataclass
class _Econ:
    qty: int
    val: float
    listv: float
    cost: float
    credit: float
    floors: bool
    immediate: bool
    slot: int


def _list_value(graph: OfferGraph, config: Config, qty: int) -> float:
    total = 0.0
    for dim in graph.dims:
        if dim.kind == DimKind.QUANTITY:
            continue
        for oid in selected_option_ids(dim, config.get(dim.id)):
            total += dim.option(oid).price_delta
    return qty * total


def _fulfillment(graph: OfferGraph, config: Config) -> tuple[bool, int]:
    """(immediate, slot_ticks) of the config's fulfillment choice. No
    FULFILLMENT dim → a single immediate now-slot (still balk-exposed)."""
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            opt = d.option(config[d.id])
            return opt.immediate, opt.slot_ticks
    return True, 0


def _available(graph: OfferGraph, state: ShopState, config: Config,
               qty: int) -> bool:
    """HARD availability gate (A1). A stock-limited option cannot appear at
    qty beyond its live stock; a deferred fulfillment slot with less live
    capacity than the order needs is dropped. Immediate slots aren't capacity-
    gated (they face the balk, not slot capacity), and a slot/option absent
    from state is treated as unconstrained."""
    for dim in graph.dims:
        for oid in selected_option_ids(dim, config.get(dim.id)):
            opt = dim.option(oid)
            if opt.stock_limited and qty > math.floor(state.stock(oid) + 1e-9):
                return False
    for dim in graph.dims:
        if dim.kind == DimKind.FULFILLMENT:
            opt = dim.option(config[dim.id])
            if not opt.immediate and opt.slot_ticks in state.capacity:
                if state.capacity[opt.slot_ticks] < qty - 1e-9:
                    return False
    return True


def _config_econ(graph: OfferGraph, state: ShopState, buyer: Buyer,
                 config: Config) -> _Econ:
    qty = qty_of(graph, config)
    val = buyer.value(graph, config)
    listv = _list_value(graph, config, qty)
    cq: CostQuote = graph.cost.quote(graph, state, config, qty)
    immediate, slot = _fulfillment(graph, config)
    return _Econ(qty, val, listv, cq.c_eff, cq.credit, cq.floors_at_list,
                 immediate, slot)


def _exceeds_appetite(graph: OfferGraph, state: ShopState, buyer: Buyer,
                      config: Config, qty: int, scope: str = "bundle") -> bool:
    """Plausibility clamp (cart_nash `qty_appetite`): don't add a q-th unit
    whose marginal buyer value falls below its marginal cost. The q-th unit's
    value is `per_unit_value · decay^(q-1)` (the derivative of
    val = per_unit_value · ladder).

    Two scopes:
      "bundle" (default) — generalizes cart_nash to the WHOLE per-unit bundle:
                marginal value of the full (choice + add-ons) unit vs its
                marginal cost c_eff(q) − c_eff(q−1).
      "choice" — cart_nash's exact CHOICE-value-only test (policies.py:326):
                `wtp[d] · decay^(q-1) < DRINK_COST[d]`, i.e. the marginal
                value of ONLY the CHOICE dims' selections vs ONLY their unit
                cost, ignoring add-ons. Boba-mode: matches the shipped pricer,
                which caps qty on the drink's own appetite and lets a topping-
                rich cart carry its full quantity.
    """
    if scope == "choice":
        # marginal value/cost of the CHOICE dims alone (add-ons emptied, qty 1)
        choice_only: Config = {}
        choice_cost = 0.0
        for d in graph.dims:
            if d.kind == DimKind.QUANTITY:
                choice_only[d.id] = 1
            elif d.kind == DimKind.ADDON:
                choice_only[d.id] = frozenset()
            else:
                sel = config.get(d.id)
                choice_only[d.id] = sel
                if d.kind == DimKind.CHOICE and sel is not None:
                    choice_cost += d.option(sel).unit_cost
        marginal_value = (buyer.value(graph, choice_only)
                          * buyer.qty_decay ** (qty - 1))
        return marginal_value < choice_cost      # cart_nash: strict, no eps
    per_unit_value = buyer.value(graph, with_qty(graph, config, 1))
    marginal_value = per_unit_value * buyer.qty_decay ** (qty - 1)
    c_q = graph.cost.quote(graph, state, config, qty).c_eff
    c_qm1 = graph.cost.quote(graph, state, with_qty(graph, config, qty - 1),
                             qty - 1).c_eff
    marginal_cost = c_q - c_qm1
    return marginal_value < marginal_cost - 1e-12


def _matches(cfg: Config, partial: Config | None) -> bool:
    if partial is None:
        return True
    for k, v in partial.items():
        cv = cfg.get(k)
        if isinstance(v, frozenset) or isinstance(cv, frozenset):
            if frozenset(v or ()) != frozenset(cv or ()):
                return False
        elif cv != v:
            return False
    return True


def _ceil_cent(x: float) -> float:
    """Round UP to the next cent (never below the input) — used on the cost
    floor so the bottom rung can't round below marginal cost (A2)."""
    return math.ceil(round(x, 9) * 100 - 1e-9) / 100.0


def _rungs(lo: float, listv: float, floors: bool, n: int) -> list[float]:
    """Even price rungs from the state-dependent floor `lo` up to list.

    The floor is rounded UP to the cent (A2): the bottom rung is therefore
    never below `lo` (= max(cost, min_price_frac·list)), so a feasible deal is
    never below marginal cost. Every rung is also clamped ≤ `listv` (the HARD
    never-above-list guard; round() could otherwise nudge a rung a few mils
    above a non-round list). `n ≤ 1` or a pinned floor → the single list rung.
    """
    lo_c = _ceil_cent(lo)
    if floors or lo_c >= listv or n <= 1:
        return [min(round(listv, 2), listv)]
    step = (listv - lo_c) / (n - 1)
    return [min(max(round(lo_c + i * step, 2), lo_c), listv) for i in range(n)]


# ── FREE-dimension pruning (C1) ──────────────────────────────────────────
def _ensure_profiled(graph: OfferGraph, state: ShopState) -> None:
    """Populate each dim's `.negotiable` from the profiler, once (C2 — the
    field is now the live source of truth, not write-only state). Cached: a
    PREFERENCE dim's cost gradient is zero by construction (state-invariant),
    so one classification is valid for every state and buyer."""
    if getattr(graph, "_profiled", False):
        return
    prof = profile(graph, state)
    for d in graph.dims:
        d.negotiable = prof[d.id]
    graph._profiled = True


def _pref_pins(graph: OfferGraph, state: ShopState, buyer: Buyer) -> dict:
    """Pin each FREE preference dim (read from dim.negotiable) to the buyer's
    best-valued option. This is behaviour-identical to enumerating it: a
    higher-valued preference option dominates a lower one at every price (same
    list, same cost), so the optimum — and the menu counterfactual — always
    pick the argmax anyway. Ties break to the first option, matching the
    enumeration's first-wins tiebreak, so pruning never changes the reported
    config either."""
    _ensure_profiled(graph, state)
    pins = {}
    for d in graph.dims:
        if d.kind != DimKind.PREFERENCE or d.negotiable != Negotiability.FREE:
            continue
        best_id, best_v = None, None
        for o in d.options:
            v = buyer.value(graph, {d.id: o.id})
            if best_v is None or v > best_v:
                best_id, best_v = o.id, v
        pins[d.id] = best_id
    return pins


def quote(graph: OfferGraph, state: ShopState, buyer: Buyer, *,
          config: Config | None = None, opts: QuoteOpts = QuoteOpts()
          ) -> Quote | None:
    """Price the offer graph for this buyer against this shop state.

    `config` (a full or partial assignment) constrains the search: a full
    config prices exactly that cart (generalizing boba priceCart / the JS
    quoteConfig); a partial one fixes some dims and searches the rest; None
    searches everything (cart_nash / nash_quote).
    """
    config = normalize_config(config)          # A4: lists → frozensets
    b = buyer.balk_prob(state)
    surv0 = 1.0 - b                    # the immediate walk-in's survival weight
    s_out = buyer.outside_surplus()

    # C1: pin FREE preference dims so the search enumerates only real levers.
    pin = _pref_pins(graph, state, buyer) if opts.prune_free else {}

    # candidate configs (available, dependency-valid, matching the constraint,
    # within the buyer's qty appetite when that clamp is on)
    cand: list[Config] = []
    for c in graph.enumerate_configs(pin=pin):
        if not _matches(c, config):
            continue
        q = qty_of(graph, c)
        if not _available(graph, state, c, q):        # A1 HARD gates
            continue
        if opts.qty_appetite and q > 1 and _exceeds_appetite(
                graph, state, buyer, c, q, opts.qty_appetite_scope):
            continue
        cand.append(c)
    if not cand:
        return None

    # Per-config economics are computed LAZILY and cached: the full CostQuote
    # (the state-dependent cost model) is only needed for the menu config and
    # the search-relevant configs, never for every immediate config the
    # disagreement's argmax scans — those need only value and list (cheap).
    econ: dict = {}

    def econ_of(c: Config) -> _Econ:
        key = freeze_config(c)
        e = econ.get(key)
        if e is None:
            e = _config_econ(graph, state, buyer, c)
            econ[key] = e
        return e

    # ── 1. disagreement point ────────────────────────────────────────────
    # The menu counterfactual is a WALK-IN purchase — immediate fulfillment
    # only (you can't get the sticker board's price on a deferred slot; that
    # slot is the deal). Best menu surplus = max over immediate configs of
    # (value − list): what the buyer keeps paying full price. Scored on
    # value−list alone (no cost model) so the menu argmax is cheap.
    s_menu, menu_c = None, None
    for c in cand:
        immediate, _slot = _fulfillment(graph, c)
        if not immediate:
            continue
        s = buyer.value(graph, c) - _list_value(graph, c, qty_of(graph, c))
        if s_menu is None or s > s_menu:
            s_menu, menu_c = s, c

    menu_buyer = menu_c is not None and s_menu > 0 and s_menu >= s_out
    if menu_buyer:
        em = econ_of(menu_c)
        # margin the shop already had. NO relief credit here (A3 / cart_nash
        # policies.py:290): the menu counterfactual is an immediate walk-in,
        # and crediting it would silently inflate d_seller and kill real deals.
        margin_menu = surv0 * (em.listv - em.cost)
        d_buyer = surv0 * s_menu + (1.0 - surv0) * s_out
        d_seller = margin_menu
    else:
        if not opts.quote_lookers:
            # IC HARD FLOOR: this buyer was never going to pay the menu (their
            # best sticker surplus ≤ their outside option). Refuse to invent a
            # sub-menu quote — that is exactly the channel a WTP-lie exploits.
            return None
        d_buyer, d_seller = s_out, 0.0

    # ── 2–3. search configs × rungs for the best Nash split ───────────────
    best = None
    best_score = None
    w = opts.seller_weight
    sf = opts.search_filter
    for c in cand:
        if sf is not None and not sf(graph, state, buyer, c):
            continue          # restricted to the vertical's search family (the
                              # disagreement above still saw the full menu set)
        e = econ_of(c)
        surv = surv0 if e.immediate else 1.0        # deferred slots are balk-free
        defer = buyer.defer_cost(e.slot)
        lo = max(e.cost, opts.min_price_frac * e.listv)
        for p in _rungs(lo, e.listv, e.floors, opts.price_rungs):
            gs = surv * (p - e.cost) + e.credit - d_seller
            gb = surv * (e.val - p) + (1.0 - surv) * s_out - defer - d_buyer
            if gs >= -1e-9 and gb >= -1e-9:
                # symmetric Nash is the exact gs·gb (byte-identical to the
                # shipped artifacts); w>0.5 tilts surplus above the floors to
                # the seller. Feasibility (gs,gb ≥ 0) still gates, so the tilt
                # never prices below the buyer's floor or above list.
                nash = (gs * gb if w == 0.5
                        else (max(0.0, gs) ** w) * (max(0.0, gb) ** (1.0 - w)))
                score = (nash, gs + gb)
                if best_score is None or score > best_score:
                    best = (c, p, surv, defer, e)
                    best_score = score

    # nothing improves on no-deal → buyer pays the menu (or walks)
    if best is None or (best_score[0] <= 0 and best_score[1] <= 1e-9):
        return _fallback(graph, state, buyer, econ, config, menu_buyer, menu_c,
                         surv0, s_out, d_buyer, d_seller)

    c, p, surv, defer, e = best
    # ── 4. guards ─────────────────────────────────────────────────────────
    # (A2iii) never below marginal cost: a relief `credit` may make gs ≥ 0 at a
    # sub-cost price, but the shop must not SELL below cost — fall back to list.
    if p < e.cost - 1e-9:
        return _fallback(graph, state, buyer, econ, config, menu_buyer, menu_c,
                         surv0, s_out, d_buyer, d_seller)
    # min-gain floor: the shop's BELIEVED gain must clear max($0.25, 10%·list)
    # so forecast noise can't leak standing margin. Below it, no deal → menu.
    u_s = surv * (p - e.cost) + e.credit
    if u_s - d_seller < max(opts.min_gain_abs, opts.min_gain_frac * e.listv):
        return _fallback(graph, state, buyer, econ, config, menu_buyer, menu_c,
                         surv0, s_out, d_buyer, d_seller)

    gs = u_s - d_seller
    gb = surv * (e.val - p) + (1.0 - surv) * s_out - defer - d_buyer
    why = ["negotiated"]
    if e.slot > 0:
        why.append(f"+{e.slot}-tick deferred slot frees capacity")
    if p < e.listv - 1e-9:
        why.append(f"${e.listv - p:.2f} under list")
    else:
        why.append("at list")
    return Quote(config=c, price=p, listv=e.listv, cost=e.cost, value=e.val,
                 save=e.listv - p, seller_gain=gs, buyer_gain=gb, feasible=True,
                 why=why,
                 audit=_audit(surv, s_out, e.credit, defer, d_buyer, d_seller,
                              e.val, e.cost))


def _audit(surv, s_out, credit, defer, d_buyer, d_seller, val, cost) -> dict:
    return dict(surv=surv, s_out=s_out, credit=credit, defer=defer,
                d_buyer=d_buyer, d_seller=d_seller, val=val, cost=cost)


def _fallback(graph, state, buyer, econ, config, menu_buyer, menu_c,
              surv0, s_out, d_buyer, d_seller) -> Quote | None:
    """No negotiated split beat disagreement. A fully-specified fixed-config
    request is offered at its own list (priceCart always returns the cart); a
    genuine menu-buyer pays the menu; anyone else walks (None) — never a
    sub-menu price, never above list."""
    if config is not None and _is_full(graph, config):
        e = _econ_or_compute(graph, state, buyer, econ, dict(config))
        return _at_list(dict(config), e, "no discount beats list; at list")
    if menu_buyer:
        e = econ[freeze_config(menu_c)]
        return _at_list(menu_c, e, "no deal beats the menu; buyer pays list")
    return None


def _at_list(cfg, e: _Econ, note: str) -> Quote:
    return Quote(config=cfg, price=e.listv, listv=e.listv, cost=e.cost,
                 value=e.val, save=0.0, seller_gain=0.0, buyer_gain=0.0,
                 feasible=False, why=[note],
                 audit=_audit(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, e.val, e.cost))


def _is_full(graph: OfferGraph, config: Config) -> bool:
    return all(d.id in config for d in graph.dims)


def _econ_or_compute(graph, state, buyer, econ, cfg) -> _Econ:
    key = freeze_config(cfg)
    if key in econ:
        return econ[key]
    return _config_econ(graph, state, buyer, cfg)
