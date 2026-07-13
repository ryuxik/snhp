"""The thin public surface: build_graph / profile / quote / price_config, plus
menu / simulate stubs that land in later phases.

This is the module a vertical adapter (or an external "run it on your menu"
caller) imports. `build_graph` (aliased `compile`) builds an OfferGraph from a
declarative spec; `quote` and `price_config` are the two entry points into the
shared engine.
"""
from __future__ import annotations

from core.cost import (CompositeCost, batch_economies, capacity_relief,
                       compose, const, salvage_on_expiry, scarcity_shadow)
from core.deps import DepGraph
from core.engine import Buyer, Quote, QuoteOpts, SeparableBuyer, quote as _quote
from core.offer_graph import (Config, DimKind, Dimension, Negotiability,
                              Option, OfferGraph)
from core.profiler import profile as _profile
from core.state import ShopState

# component tokens a JSON/dict spec may name under spec["cost"]
_COST_TOKENS = {
    "const": lambda a: const(),
    "salvage_on_expiry": lambda a: salvage_on_expiry(),
    "scarcity_shadow": lambda a: scarcity_shadow(),
    "batch_economies": lambda a: batch_economies(**a),
    # capacity_relief needs a python fn, so it can't come from pure JSON; pass
    # it as a live component in spec["cost"] instead of a token.
}


def build_graph(spec: dict) -> OfferGraph:
    """Build an OfferGraph from a declarative spec:

        {
          "name": "...",
          "dims": [
            {"id": "drink", "kind": "CHOICE", "options": [
                {"id": "milk-tea", "price_delta": 5.0, "unit_cost": 1.4}, ...]},
            {"id": "qty", "kind": "QUANTITY", "qty_cap": 3},
            ...],
          "deps": {"valid_on": {...}, "requires": {...}, "excludes": {...}},
          "cost": ["const", "salvage_on_expiry", {"batch_economies":
                    {"setup": 1.0, "marginal": 0.2}}, <live component>],
        }

    `kind` is a DimKind name (case-insensitive). Cost entries are either a
    token string, a {token: kwargs} dict, or a live component object
    (e.g. capacity_relief(fn), which can't be serialized)."""
    dims = []
    for d in spec.get("dims", []):
        kind = DimKind[d["kind"].upper()] if isinstance(d["kind"], str) else d["kind"]
        opts = tuple(_option(o) for o in d.get("options", []))
        neg = d.get("negotiable", Negotiability.AUTO)
        if isinstance(neg, str):
            neg = Negotiability[neg.upper()]
        dims.append(Dimension(id=d["id"], kind=kind, options=opts,
                              qty_cap=int(d.get("qty_cap", 1)), negotiable=neg))

    dep = spec.get("deps", {})
    deps = DepGraph(
        valid_on={k: set(v) for k, v in dep.get("valid_on", {}).items()},
        requires={k: set(v) for k, v in dep.get("requires", {}).items()},
        excludes={k: set(v) for k, v in dep.get("excludes", {}).items()},
    )

    cost = _build_cost(spec.get("cost", ["const"]))
    return OfferGraph(dims=dims, deps=deps, cost=cost, name=spec.get("name", ""))


# `compile` shadowed the builtin; `build_graph` is the real name, the alias
# keeps older callers working (C2).
compile = build_graph


def _option(o) -> Option:
    if isinstance(o, Option):
        return o
    return Option(
        id=o["id"], label=o.get("label", ""),
        price_delta=float(o.get("price_delta", 0.0)),
        stock_limited=bool(o.get("stock_limited", False)),
        unit_cost=float(o.get("unit_cost", 0.0)),
        salvage=float(o.get("salvage", 0.0)),
        perishable=bool(o.get("perishable", False)),
        immediate=bool(o.get("immediate", True)),
        slot_ticks=int(o.get("slot_ticks", 0)),
    )


def _build_cost(entries) -> CompositeCost:
    if isinstance(entries, CompositeCost):
        return entries
    components = []
    for e in entries:
        if isinstance(e, str):
            components.append(_COST_TOKENS[e]({}))
        elif isinstance(e, dict):
            (token, args), = e.items()
            components.append(_COST_TOKENS[token](args))
        else:
            components.append(e)              # a live component object
    return compose(*components)


def profile(graph: OfferGraph, state: ShopState, buyer_sample=None):
    """Classify each dimension FREE / LEVER / AUTO (see core.profiler)."""
    return _profile(graph, state, buyer_sample)


def quote(graph: OfferGraph, state: ShopState, buyer: Buyer, *,
          config: Config | None = None, opts: QuoteOpts = QuoteOpts()
          ) -> Quote | None:
    """Search all valid configs for the best Nash split (or price a fixed
    `config`). See core.engine.quote."""
    return _quote(graph, state, buyer, config=config, opts=opts)


def price_config(graph: OfferGraph, state: ShopState, buyer: Buyer,
                 config: Config, opts: QuoteOpts = QuoteOpts()) -> Quote | None:
    """Price ONE fixed configuration (generalizes the JS quoteConfig /
    boba priceCart): the choice/add-ons/qty are pinned, only the price (and
    any unspecified fulfillment slot) is negotiated."""
    return _quote(graph, state, buyer, config=config, opts=opts)


def menu(graph: OfferGraph, state: ShopState, *args, **kwargs):
    """Posted person-independent price boards (boba.menu_pick / fashion's
    posted mode). Lands in Phase 2–3 — the self-selection-off-a-fixed-list
    surface, once the golden-master ports pin its numbers."""
    raise NotImplementedError("menu() lands in Phase 2–3 (see docs/REDESIGN.md)")


def simulate(graph: OfferGraph, *args, **kwargs):
    """Roll a day of arrivals through the engine and account the ledger
    (the per-vertical run.py, generalized). Lands in Phase 3."""
    raise NotImplementedError("simulate() lands in Phase 3 (see docs/REDESIGN.md)")
