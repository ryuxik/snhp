"""Smoke tests: prove the engine can EXPRESS both shipped verticals as
OfferGraph instances and quote them. This is a SHAPE test — it does not try
to reproduce boba's or vend's exact dollar numbers (that's Phase 2's golden
gate). It only shows the dimensions and cost components fit.
"""
from __future__ import annotations

from core.cost import (batch_economies, capacity_relief, compose, const,
                       salvage_on_expiry, scarcity_shadow)
from core.deps import DepGraph
from core.engine import QuoteOpts, SeparableBuyer, quote
from core.offer_graph import (DimKind, Dimension, Option, OfferGraph, qty_of)
from core.state import ShopState


# ── boba-like: drink CHOICE + toppings ADDON + qty QUANTITY + pickup ──────
#    FULFILLMENT + sweetness PREFERENCE; cost = const + salvage + relief.
def _boba_relief(graph, state, config, qty):
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            opt = d.option(config[d.id])
            if not opt.immediate and opt.slot_ticks > 0:
                return qty * 0.5          # a freed peak slot rescues a sale
    return 0.0


def _boba_graph():
    drink = Dimension("drink", DimKind.CHOICE, options=(
        Option("classic-milk-tea", price_delta=5.0, unit_cost=1.4),
        Option("matcha-latte", price_delta=6.0, unit_cost=2.1)))
    tops = Dimension("tops", DimKind.ADDON, options=(
        Option("pearls", price_delta=1.0, unit_cost=0.3, perishable=True,
               salvage=0.0),
        Option("cheese-foam", price_delta=1.2, unit_cost=0.5)))
    sweet = Dimension("sweet", DimKind.PREFERENCE, options=(
        Option("50", price_delta=0.0), Option("100", price_delta=0.0)))
    pickup = Dimension("pickup", DimKind.FULFILLMENT, options=(
        Option("now", immediate=True, slot_ticks=0),
        Option("d30", immediate=False, slot_ticks=3),
        Option("d60", immediate=False, slot_ticks=6)))
    qty = Dimension("qty", DimKind.QUANTITY, qty_cap=3)
    return OfferGraph(
        dims=[drink, tops, sweet, pickup, qty], deps=DepGraph(),
        cost=compose(const(), salvage_on_expiry(), capacity_relief(_boba_relief)),
        name="boba-like")


def test_boba_shape_quotes():
    graph = _boba_graph()
    state = ShopState(tick=20, expiring={"pearls"})    # pearls batch clearing
    buyer = SeparableBuyer(
        values={("drink", "classic-milk-tea"): 6.5, ("drink", "matcha-latte"): 4.0,
                ("tops", "pearls"): 1.6, ("tops", "cheese-foam"): 0.4},
        qty_decay=0.6, outside=1.0, balk=0.3,
        defer={0: 0.0, 3: 0.30, 6: 0.50})
    q = quote(graph, state, buyer, opts=QuoteOpts())
    assert q is not None
    assert q.price <= q.listv + 1e-9              # discount-only holds
    assert q.config is not None
    # the receipt is well-formed
    assert isinstance(q.why, list) and q.why


def test_boba_fixed_config_pricer():
    graph = _boba_graph()
    state = ShopState(tick=20)
    buyer = SeparableBuyer(
        values={("drink", "classic-milk-tea"): 6.5, ("drink", "matcha-latte"): 4.0,
                ("tops", "pearls"): 1.6, ("tops", "cheese-foam"): 0.4},
        qty_decay=0.6, outside=1.0, balk=0.0, defer={0: 0.0, 3: 0.3, 6: 0.5})
    fixed = {"drink": "classic-milk-tea", "tops": frozenset({"pearls"}),
             "sweet": "50", "pickup": "now", "qty": 1}
    q = quote(graph, state, buyer, config=fixed)
    assert q is not None
    assert q.config["drink"] == "classic-milk-tea"
    assert q.config["qty"] == 1
    assert q.price <= q.listv + 1e-9


# ── vend-like: sku CHOICE + qty QUANTITY, scarcity_shadow cost ────────────
def _vend_graph():
    # SKUs are stock_limited (A1 hard qty cap) AND scarcity-shadowed (soft
    # displacement pricing) — the two roles vend's stock plays.
    sku = Dimension("sku", DimKind.CHOICE, options=(
        Option("chips", price_delta=2.50, unit_cost=1.00, stock_limited=True),
        Option("soda", price_delta=2.00, unit_cost=0.80, stock_limited=True)))
    qty = Dimension("qty", DimKind.QUANTITY, qty_cap=3)
    return OfferGraph(dims=[sku, qty], deps=DepGraph(),
                      cost=compose(const(), scarcity_shadow()), name="vend-like")


def test_vend_shape_quotes():
    graph = _vend_graph()
    # chips are in EXCESS (stock 6 vs expected demand 1) → cheap to move;
    # soda is scarce (stock 1 vs demand 4) → discounting displaces a list sale
    state = ShopState(tick=10, inventory={"chips": 6.0, "soda": 1.0},
                      expected_demand={"chips": 1.0, "soda": 4.0})
    buyer = SeparableBuyer(
        values={("sku", "chips"): 3.0, ("sku", "soda"): 2.6},
        qty_decay=0.5, outside=0.5, balk=0.0)          # no balk in vend
    q = quote(graph, state, buyer, opts=QuoteOpts(min_gain_abs=0.0,
                                                  min_gain_frac=0.0))
    assert q is not None
    assert q.price <= q.listv + 1e-9


def test_vend_seller_weight_tilt():
    """The asymmetric-Nash hook (vend seller_weight): w=1.0 hands the seller
    all surplus above the buyer's floor, so the seller gain is ≥ the w=0.5
    gain and the price is ≥ the symmetric price — never below the floor,
    never above list."""
    graph = _vend_graph()
    state = ShopState(tick=10, inventory={"chips": 6.0, "soda": 6.0},
                      expected_demand={"chips": 1.0, "soda": 1.0})
    buyer = SeparableBuyer(values={("sku", "chips"): 3.0, ("sku", "soda"): 2.6},
                           qty_decay=0.5, outside=0.0, balk=0.0)
    sym = quote(graph, state, buyer,
                opts=QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0,
                               seller_weight=0.5))
    tilt = quote(graph, state, buyer,
                 opts=QuoteOpts(min_gain_abs=0.0, min_gain_frac=0.0,
                                seller_weight=1.0))
    assert sym is not None and tilt is not None
    assert tilt.price <= tilt.listv + 1e-9
    assert tilt.seller_gain >= sym.seller_gain - 1e-9


# ── batch_economies: the NEW primitive making qty a real lever ────────────
def test_batch_economies_per_unit_cost_falls_with_qty():
    """c_eff(q) = setup + q·marginal ⇒ per-unit cost strictly declines with
    qty (setup amortizes). This is what makes quantity a standalone lever."""
    sku = Dimension("sku", DimKind.CHOICE, options=(
        Option("widget", price_delta=4.0, unit_cost=0.2),))
    qty = Dimension("qty", DimKind.QUANTITY, qty_cap=3)
    graph = OfferGraph(dims=[sku, qty], deps=DepGraph(),
                       cost=compose(batch_economies(setup=1.0, marginal=0.2)))
    state = ShopState()
    c1 = graph.cost.quote(graph, state, {"sku": "widget", "qty": 1}, 1).c_eff
    c2 = graph.cost.quote(graph, state, {"sku": "widget", "qty": 2}, 2).c_eff
    c3 = graph.cost.quote(graph, state, {"sku": "widget", "qty": 3}, 3).c_eff
    assert c1 == 1.2 and c2 == 1.4 and c3 == 1.6          # setup + q·marginal
    assert c1 / 1 > c2 / 2 > c3 / 3                        # per-unit falls

    buyer = SeparableBuyer(values={("sku", "widget"): 5.0}, qty_decay=0.9)
    q = quote(graph, state, buyer, opts=QuoteOpts(min_gain_abs=0.0,
                                                  min_gain_frac=0.0))
    assert q is not None and q.price <= q.listv + 1e-9


# ── api.compile builds a working graph from a declarative spec ────────────
def test_compile_from_spec():
    from core.api import build_graph, compile, price_config, quote as api_quote
    assert compile is build_graph          # C2: alias kept, builtin un-shadowed
    spec = {
        "name": "spec-boba",
        "dims": [
            {"id": "drink", "kind": "CHOICE", "options": [
                {"id": "milk-tea", "price_delta": 5.0, "unit_cost": 1.4},
                {"id": "matcha", "price_delta": 6.0, "unit_cost": 2.1}]},
            {"id": "qty", "kind": "QUANTITY", "qty_cap": 2},
        ],
        "cost": ["const"],
    }
    graph = build_graph(spec)
    buyer = SeparableBuyer(values={("drink", "milk-tea"): 6.5,
                                   ("drink", "matcha"): 4.0}, qty_decay=0.5)
    q = api_quote(graph, ShopState(), buyer)
    assert q is not None and q.price <= q.listv + 1e-9
    q2 = price_config(graph, ShopState(), buyer,
                      {"drink": "milk-tea", "qty": 1})
    assert q2 is not None and q2.config["drink"] == "milk-tea"
