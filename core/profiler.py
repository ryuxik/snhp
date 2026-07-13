"""The divergence profiler — classify each dimension FREE / LEVER / AUTO.

The engine's job is to negotiate on the dimensions where a unit's cost
actually MOVES with shop state (drink/sku), and to just hand the buyer their
favorite of the dimensions where it doesn't (sweetness/ice). The profiler
measures which is which by probing the cost model directly:

  hold every other dimension at a baseline, vary this dimension across its
  options, and look at the spread in c_eff.

  zero spread  → FREE   (a costless customization; prune it from the search —
                        the buyer just gets their preferred option)
  positive     → LEVER  (changing the option moves cost; a real surface)
  can't tell   → AUTO   (single-option dim, nothing to vary) → treated as
                        FREE, the conservative default: a missed lever only
                        costs money, whereas inventing a fake one LEAKS margin
                        (docs/REDESIGN.md, the three hard risks).

This is deliberately cost-only (buyer-independent): a lever is a property of
the shop's economics, not of who is asking — the same reason the verticals
never key price on buyer identity.
"""
from __future__ import annotations

from core.offer_graph import (Config, DimKind, Dimension, Negotiability,
                              OfferGraph, qty_of)
from core.state import ShopState

_EPS = 1e-9


def _default_config(graph: OfferGraph) -> Config:
    """A baseline assignment: first option of each pick-one dim, empty
    add-on sets, qty 1 — the frame against which one dim is varied."""
    cfg: Config = {}
    for d in graph.dims:
        if d.kind == DimKind.QUANTITY:
            cfg[d.id] = 1
        elif d.kind == DimKind.ADDON:
            cfg[d.id] = frozenset()
        else:
            cfg[d.id] = d.options[0].id
    return cfg


def _variants(dim: Dimension, base: Config) -> list[Config]:
    """`base` with `dim` set to each of its options in turn (for ADDON: the
    empty set vs each single option — the marginal add)."""
    out = []
    if dim.kind == DimKind.QUANTITY:
        for q in (1, min(2, dim.qty_cap)):
            c = dict(base)
            c[dim.id] = q
            out.append(c)
    elif dim.kind == DimKind.ADDON:
        c0 = dict(base)
        c0[dim.id] = frozenset()
        out.append(c0)
        for o in dim.options:
            c = dict(base)
            c[dim.id] = frozenset({o.id})
            out.append(c)
    else:
        for o in dim.options:
            c = dict(base)
            c[dim.id] = o.id
            out.append(c)
    return out


def _classify(graph: OfferGraph, states, dim: Dimension) -> Negotiability:
    base = _default_config(graph)
    variants = _variants(dim, base)
    if len(variants) < 2:
        return Negotiability.FREE          # AUTO → FREE: nothing to vary
    spread = 0.0
    for st in states:
        costs = [graph.cost.quote(graph, st, c, qty_of(graph, c)).c_eff
                 for c in variants]
        spread = max(spread, max(costs) - min(costs))
    return Negotiability.LEVER if spread > _EPS else Negotiability.FREE


def profile(graph: OfferGraph, state: ShopState, buyer_sample=None
            ) -> dict[str, Negotiability]:
    """Classify every dimension. `buyer_sample` is accepted for API symmetry
    (a caller may pass representative buyers/states); the cost gradient is
    buyer-independent, so only the shop states matter here. Returns
    {dim_id: Negotiability}; the engine can use it to prune FREE dims to the
    buyer's favorite."""
    states = [state]
    return {d.id: _classify(graph, states, d) for d in graph.dims}
