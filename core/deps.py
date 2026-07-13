"""Dependency edges between options — the availability graph.

Real menus have constraints: an option is only offered when another is
chosen (a topping that needs a base that carries it), two options exclude
each other, one requires another. This module owns the `is_valid(config)`
predicate that prunes the enumeration in OfferGraph.enumerate_configs.

All three relations are keyed by option id and reference option ids:
  valid_on[o]  = o may be selected only if ALL of these are present
                 (availability gating — e.g. "pearls" only if a milk-tea base)
  requires[o]  = selecting o forces ALL of these to also be present
  excludes[o]  = selecting o forbids ANY of these from being present

An empty DepGraph (the default) admits every combination — the verticals
today have no cross-option constraints, so this is purely additive headroom.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.offer_graph import DimKind, selected_option_ids


@dataclass
class DepGraph:
    valid_on: dict[str, set[str]] = field(default_factory=dict)
    requires: dict[str, set[str]] = field(default_factory=dict)
    excludes: dict[str, set[str]] = field(default_factory=dict)

    def _selected(self, graph, config) -> set[str]:
        chosen: set[str] = set()
        for dim in graph.dims:
            chosen.update(selected_option_ids(dim, config.get(dim.id)))
        return chosen

    def is_valid(self, graph, config) -> bool:
        chosen = self._selected(graph, config)
        for o in chosen:
            need = self.valid_on.get(o)
            if need and not need <= chosen:
                return False
            req = self.requires.get(o)
            if req and not req <= chosen:
                return False
            exc = self.excludes.get(o)
            if exc and exc & chosen:
                return False
        return True
