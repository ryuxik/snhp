"""core — the general offer-graph negotiation engine.

Unifies boba.cart_nash and vend.nash_quote into one Nash-floor search over a
typed offer graph (dimensions) with a pluggable, state-dependent cost model
(what makes a unit's cost move with shop state). See docs/REDESIGN.md Phase 1.
"""
from core.cost import (CompositeCost, CostModel, CostQuote, batch_economies,
                       capacity_relief, compose, const, salvage_on_expiry,
                       scarcity_shadow)
from core.deps import DepGraph
from core.engine import (Buyer, Quote, QuoteOpts, SeparableBuyer, qty_ladder,
                        quote)
from core.offer_graph import (Config, DimKind, Dimension, Negotiability,
                              Option, OfferGraph, freeze_config, qty_of)
from core.profiler import profile
from core.state import Batch, ShopState

__all__ = [
    "OfferGraph", "Dimension", "Option", "DimKind", "Negotiability", "Config",
    "freeze_config", "qty_of",
    "DepGraph", "ShopState", "Batch",
    "CostModel", "CostQuote", "CompositeCost", "compose", "const",
    "salvage_on_expiry", "scarcity_shadow", "capacity_relief", "batch_economies",
    "Buyer", "SeparableBuyer", "Quote", "QuoteOpts", "quote", "qty_ladder",
    "profile",
]
