"""The pluggable, state-dependent cost model — the *what-moves-with-state*
half of the unified engine.

A `CostModel.quote(graph, state, config, qty)` returns a `CostQuote`:

  c_eff          the total effective marginal cost of the whole config at
                 this qty. It floors the price (rungs run from c_eff up to
                 list) and it is what the seller's gain is measured against:
                 seller gain = surv·(price − c_eff) + credit − disagreement.
  credit         a lump added to the seller's gain that is NOT a price
                 (boba capacity relief: a deferred slot frees a peak sale).
  floors_at_list when the config's cost already meets/beats list, so there
                 is nothing to negotiate — a single rung at list.

The verticals differ ONLY here. boba's cost is `qty·(drink + toppings)` with
a salvage carve-out for expiring pearls; vend's is the same goods cost with a
finite-stock *shadow*: a unit the machine expects to sell at list later is
worth list to keep, so discounting it displaces that sale. Both are just
choices of the components below, which COMPOSE.

The components and where they come from:

  const()              per-option unit cost × qty            (both verticals)
  salvage_on_expiry()  a perishable option's cost → salvage  (boba top_c_eff,
                       when its batch is expiring in excess    vend c_eff)
  scarcity_shadow()    finite stock: displaced units re-      (vend
                       priced at list, not at cost            machine_margin)
  capacity_relief(fn)  a `credit` from a deferred slot        (boba
                       freeing peak capacity                   capacity_relief)
  batch_economies(...) c_eff(q)=setup+q·marginal, so per-     (NEW; Phase-2
                       unit cost FALLS with qty                primitive that
                       makes quantity a real standalone lever — today cost is
                       linear in qty in both shipped engines, so qty is $0
                       standalone; see docs/REDESIGN.md Phase 2.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from core.offer_graph import Config, DimKind, OfferGraph, selected_option_ids
from core.state import ShopState


@dataclass
class CostQuote:
    c_eff: float
    credit: float = 0.0
    floors_at_list: bool = False
    # Optional bespoke price-rung grid (TOTAL prices for the whole config at
    # this qty), supplied by a vertical whose ladder the engine's even
    # floor→list spacing cannot reproduce. Default None → the engine builds
    # the rungs itself (unchanged for boba and every generic graph). vend uses
    # it to reproduce scenario.enumerate_outcomes' TWO-COST split: the rungs
    # are floored at the RAW per-unit c_eff (salvage/unit_cost) and rounded
    # PER-UNIT (×qty), while `c_eff` above stays the displacement-adjusted cost
    # the gain/disagreement are measured against (core/adapters/vend.py).
    rungs: tuple[float, ...] | None = None


class CostModel(Protocol):
    def quote(self, graph: OfferGraph, state: ShopState,
              config: Config, qty: int) -> CostQuote: ...


# ── composable component markers ─────────────────────────────────────────
# Each is a tiny declarative marker; CompositeCost interprets them. Keeping
# them data (not closures) makes a cost model introspectable and picklable.
@dataclass(frozen=True)
class _Const:
    pass


@dataclass(frozen=True)
class _Salvage:
    pass


@dataclass(frozen=True)
class _Scarcity:
    pass


@dataclass(frozen=True)
class _CapacityRelief:
    # fn(graph, state, config, qty) -> credit dollars
    fn: Callable[[OfferGraph, ShopState, Config, int], float]


@dataclass(frozen=True)
class _BatchEconomies:
    setup: float
    marginal: float | None = None      # None → sum of chosen options' unit_cost


def const() -> _Const:
    """The goods baseline: c_eff = qty · Σ(chosen options' unit_cost). Always
    present in spirit (options default to unit_cost 0); listing it documents
    intent."""
    return _Const()


def salvage_on_expiry() -> _Salvage:
    """A perishable option whose batch is expiring in excess costs its
    `salvage` value, not its `unit_cost` — the ingredient is already sunk and
    would otherwise be waste (boba pearls → 0; vend expiring SKU → listing
    salvage). Reads state.expiring (an adapter sets it from the vertical's
    clearance trigger)."""
    return _Salvage()


def scarcity_shadow() -> _Scarcity:
    """Finite-stock shadow pricing (vend.machine_margin). For a CHOICE option
    with stock s and expected list demand D, `excess = max(0, s−D)` units are
    surplus and cheap to move at c_eff; the rest are *displaced* list sales
    and cost list, not c_eff:

        c_eff(choice, q) = (q − displaced)·ce + displaced·list
        displaced        = min(q, max(0, q − excess))

    This is exactly vend's margin rearranged: margin = q·p − c_eff, so
    q·p − [(q−displaced)·ce + displaced·list] reproduces vend's
    (q−displaced)(p−ce) + displaced(p−list) at every price, including list."""
    return _Scarcity()


def capacity_relief(
        fn: Callable[[OfferGraph, ShopState, Config, int], float]
) -> _CapacityRelief:
    """A `credit` (not a price) added to the seller's gain when a fulfillment
    choice frees scarce capacity (boba: a +30/+60 slot rescues a peak sale
    that would have balked). `fn` is the vertical's relief valuation; it reads
    the config's fulfillment option and qty from state."""
    return _CapacityRelief(fn)


def batch_economies(setup: float, marginal: float | None = None
                    ) -> _BatchEconomies:
    """c_eff(q) = setup + q·marginal — a fixed setup amortized over the batch,
    so per-unit cost DECLINES with qty. This is the new primitive that makes
    quantity a real standalone lever (docs/REDESIGN.md Phase 2). `marginal`
    defaults to the summed unit_cost of the chosen options."""
    return _BatchEconomies(setup, marginal)


class CompositeCost:
    """Interprets a set of components into one CostModel. Phases (so mixed
    models compose without double-counting a shared channel):

      1. resolve each chosen option's effective unit cost   (const, salvage)
      2. assemble goods cost                                 (const, scarcity)
      3. optionally override with a batch cost shape         (batch_economies)
      4. add non-price credits                               (capacity_relief)

    salvage + capacity_relief (the pairing the spec calls out) compose
    cleanly: salvage lowers c_eff in phase 1, capacity_relief raises credit in
    phase 4 — different channels, no interaction. salvage + scarcity compose
    too: scarcity reads the salvage-resolved ce.
    """

    def __init__(self, *components):
        self.components = components
        self._const = any(isinstance(c, _Const) for c in components)
        self._salvage = any(isinstance(c, _Salvage) for c in components)
        self._scarcity = any(isinstance(c, _Scarcity) for c in components)
        self._batch = next((c for c in components
                            if isinstance(c, _BatchEconomies)), None)
        self._relief = [c.fn for c in components
                        if isinstance(c, _CapacityRelief)]

    # phase 1 --------------------------------------------------------------
    def _unit_cost(self, state: ShopState, opt) -> float:
        if self._salvage and opt.perishable and opt.id in state.expiring:
            return opt.salvage
        return opt.unit_cost

    def quote(self, graph: OfferGraph, state: ShopState,
              config: Config, qty: int) -> CostQuote:
        goods = 0.0
        unit_sum = 0.0                 # Σ resolved unit costs (batch marginal)
        for dim in graph.dims:
            if dim.kind == DimKind.QUANTITY:
                continue
            for oid in selected_option_ids(dim, config.get(dim.id)):
                opt = dim.option(oid)
                ce = self._unit_cost(state, opt)
                unit_sum += ce
                if (self._scarcity and dim.kind == DimKind.CHOICE
                        and opt.id in state.inventory):
                    s = state.inventory[opt.id]
                    D = state.expected_demand.get(opt.id, 0.0)
                    excess = max(0.0, s - D)
                    displaced = min(float(qty), max(0.0, qty - excess))
                    goods += (qty - displaced) * ce + displaced * opt.price_delta
                else:
                    goods += qty * ce

        if self._batch is not None:
            marginal = (self._batch.marginal if self._batch.marginal is not None
                        else unit_sum)
            c_eff = self._batch.setup + qty * marginal
        else:
            c_eff = goods

        credit = sum(fn(graph, state, config, qty) for fn in self._relief)
        # A2(i): when the config's effective cost already meets/beats its list
        # value there is nothing to negotiate — signal a single at-list rung so
        # the engine never tries (and never rounds) below cost.
        listv = _list_value(graph, config, qty)
        return CostQuote(c_eff=c_eff, credit=credit,
                         floors_at_list=c_eff >= listv - 1e-9)


def _list_value(graph: OfferGraph, config: Config, qty: int) -> float:
    """Σ(chosen options' price_delta) · qty — the sticker the discount is
    measured against. Duplicated by core.engine._list_value (kept here so the
    cost model is self-contained); both must agree."""
    total = 0.0
    for dim in graph.dims:
        if dim.kind == DimKind.QUANTITY:
            continue
        for oid in selected_option_ids(dim, config.get(dim.id)):
            total += dim.option(oid).price_delta
    return qty * total


def compose(*components) -> CompositeCost:
    """Build one CostModel from composable components (see module docstring)."""
    return CompositeCost(*components)
