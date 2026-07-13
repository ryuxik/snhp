"""P3 — the divergence profiler classifies a zero-cost-gradient PREFERENCE
dimension FREE and a cost-moving dimension LEVER."""
from __future__ import annotations

from core.cost import compose, const
from core.deps import DepGraph
from core.offer_graph import (DimKind, Dimension, Negotiability, Option,
                              OfferGraph)
from core.profiler import profile
from core.state import ShopState


def _graph():
    # a CHOICE whose options have DIFFERENT unit costs → cost gradient → LEVER
    drink = Dimension("drink", DimKind.CHOICE, options=(
        Option("milk-tea", price_delta=5.0, unit_cost=1.4),
        Option("matcha", price_delta=6.0, unit_cost=2.1)))
    # a PREFERENCE with ZERO cost on every option → no gradient → FREE
    sweet = Dimension("sweet", DimKind.PREFERENCE, options=(
        Option("0", price_delta=0.0, unit_cost=0.0),
        Option("50", price_delta=0.0, unit_cost=0.0),
        Option("100", price_delta=0.0, unit_cost=0.0)))
    # an ADDON with a real cost → LEVER
    tops = Dimension("tops", DimKind.ADDON, options=(
        Option("pearls", price_delta=1.0, unit_cost=0.3),))
    return OfferGraph(dims=[drink, sweet, tops], deps=DepGraph(),
                      cost=compose(const()))


def test_p3_preference_is_free_choice_is_lever():
    graph = _graph()
    cls = profile(graph, ShopState(), buyer_sample=None)
    assert cls["sweet"] == Negotiability.FREE
    assert cls["drink"] == Negotiability.LEVER
    assert cls["tops"] == Negotiability.LEVER


def test_c2_quote_populates_live_negotiable():
    """C2: after a quote(), each dim's `.negotiable` is populated from the
    profiler (no longer write-only dead state) — and the engine reads it to
    prune FREE preference dims."""
    from core.engine import SeparableBuyer, quote
    graph = _graph()
    buyer = SeparableBuyer(values={("drink", "milk-tea"): 6.5,
                                   ("drink", "matcha"): 4.0,
                                   ("tops", "pearls"): 1.6}, qty_decay=0.3)
    assert graph.dim("sweet").negotiable == Negotiability.AUTO   # before
    quote(graph, ShopState(), buyer)
    assert graph.dim("sweet").negotiable == Negotiability.FREE   # after (read)
    assert graph.dim("drink").negotiable == Negotiability.LEVER


def test_p3_zero_cost_choice_is_free():
    """A CHOICE whose options happen to cost the SAME has no cost gradient —
    the profiler calls it FREE (there is no lever there to work), independent
    of the fact that it's a CHOICE kind."""
    flat = Dimension("size", DimKind.CHOICE, options=(
        Option("s", price_delta=3.0, unit_cost=1.0),
        Option("m", price_delta=4.0, unit_cost=1.0),
        Option("l", price_delta=5.0, unit_cost=1.0)))
    graph = OfferGraph(dims=[flat], deps=DepGraph(), cost=compose(const()))
    cls = profile(graph, ShopState(), buyer_sample=None)
    assert cls["size"] == Negotiability.FREE
