"""The typed offer graph — the *dimensions* half of the unified engine.

The thesis (docs/REDESIGN.md): boba.cart_nash and vend.nash_quote are the
same Nash-floor search; they differ only in (a) which dimensions a
configuration has and (b) what makes a unit's cost move with shop state.
This module owns (a): a configuration is a choice over a small, typed set of
dimensions, and the engine (core/engine.py) prices any such configuration
with the one shared skeleton.

Dimension kinds, mapped to the two shipped verticals:

  CHOICE       pick exactly one option        boba drink / vend sku
  ADDON        pick a subset of options       boba toppings
  PREFERENCE   pick exactly one, ZERO cost    boba sweetness / ice level
               gradient (a costless customization — never a price lever)
  FULFILLMENT  pick exactly one; carries a    boba pickup slot (+30/+60)
               buyer `defer_cost`, a possible seller `credit` (capacity
               relief), and a survival factor (an immediate slot still faces
               the walk-in balk; a deferred one is balk-free)
  QUANTITY     an integer 1..qty_cap          boba cups / vend units

A `Config` assigns every dimension: an option id for CHOICE/PREFERENCE/
FULFILLMENT, a frozenset of option ids for ADDON, an int for QUANTITY.
"""
from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass, field
from typing import Iterator

# Guard on the ADDON 2^n enumeration. The verticals have ≤4 toppings on one
# addon dim; anything past this is a modeling error (a preference or choice
# masquerading as an addon), so we fail loud rather than hang.
MAX_ADDON_OPTIONS = 12                  # 2^12 = 4096 subsets, per addon dim


class DimKind(enum.Enum):
    CHOICE = "choice"
    ADDON = "addon"
    PREFERENCE = "preference"
    FULFILLMENT = "fulfillment"
    QUANTITY = "quantity"


class Negotiability(enum.Enum):
    """The profiler's verdict on a dimension (core/profiler.py):

      FREE   changing the option does NOT move c_eff — a costless lever the
             buyer just gets their favorite of (sweetness/ice). Prunable.
      LEVER  changing the option moves c_eff and the shop can observe the
             state that drives it — a real negotiation surface (drink/sku).
      AUTO   undecided; the engine treats it conservatively (defaults to
             FREE — a missed lever only costs money, a fake one *leaks*).

    Populated live by the engine from the profiler on first quote (C2);
    the engine reads FREE-classified PREFERENCE dims to prune the search.
    """
    FREE = "free"
    LEVER = "lever"
    AUTO = "auto"


@dataclass(frozen=True)
class Option:
    """One selectable option on a dimension.

    `price_delta` is this option's contribution to the cart's LIST value —
    the sticker the discount is measured against (boba DRINK_PRICE/TOP_PRICE,
    vend list_price). Everything else is per-option cost data consumed by the
    pluggable cost model (core/cost.py); the engine reads only `stock_limited`
    (a HARD availability gate) itself.
    """
    id: str
    label: str = ""
    price_delta: float = 0.0        # contribution to list value
    # HARD availability gate (A1). When True the engine forbids this option in
    # any config at qty > floor(state.stock(id)) — the general form of
    # cart_nash `pearls_stocked < q: break` (policies.py:320) and vend's
    # `range(1, min(QTY_CAP, stock)+1)` qty cap. Distinct from the SOFT
    # scarcity_shadow *pricing* in core/cost.py.
    stock_limited: bool = False
    # cost-model inputs (read only by core/cost.py components) --------------
    unit_cost: float = 0.0          # base marginal cost of one unit
    salvage: float = 0.0            # cost when this option's batch is expiring
    perishable: bool = False        # eligible for salvage_on_expiry
    # fulfillment inputs ----------------------------------------------------
    immediate: bool = True          # True → faces the walk-in balk (surv=1-b)
    slot_ticks: int = 0             # deferral horizon (0 = now)


@dataclass
class Dimension:
    id: str
    kind: DimKind
    options: tuple[Option, ...] = ()
    qty_cap: int = 1                       # only meaningful for QUANTITY
    negotiable: Negotiability = Negotiability.AUTO

    def __post_init__(self) -> None:
        self.options = tuple(self.options)
        self._by_id = {o.id: o for o in self.options}
        if self.kind == DimKind.ADDON and len(self.options) > MAX_ADDON_OPTIONS:
            raise ValueError(
                f"ADDON dim {self.id!r} has {len(self.options)} options "
                f"(> {MAX_ADDON_OPTIONS}); its 2^n subset enumeration is "
                "intractable — model it as CHOICE/PREFERENCE dims instead.")

    def option(self, oid: str) -> Option:
        return self._by_id[oid]


def normalize_config(cfg: "Config | None") -> "Config | None":
    """Coerce any ADDON selection given as a list/tuple/set into a frozenset,
    so external callers (JSON, price_config) whose add-on sets are lists still
    compare equal to the enumerated frozensets (A4). Idempotent."""
    if cfg is None:
        return None
    out = {}
    for k, v in cfg.items():
        if isinstance(v, (list, tuple, set)) and not isinstance(v, frozenset):
            out[k] = frozenset(v)
        else:
            out[k] = v
    return out


def selected_option_ids(dim: Dimension, sel) -> list[str]:
    """The option ids a config assigns to `dim`. QUANTITY selects no priced
    option (its `sel` is an int); everything else selects one or a subset.
    Tolerates a missing (None) selection and a list/set add-on selection."""
    if dim.kind == DimKind.QUANTITY:
        return []
    if dim.kind == DimKind.ADDON:
        return sorted(sel) if sel else []
    return [sel] if sel is not None else []


# A Config maps dim_id -> option id (CHOICE/PREFERENCE/FULFILLMENT)
#                       -> frozenset[option id] (ADDON)
#                       -> int qty (QUANTITY)
Config = dict


def freeze_config(cfg: Config) -> tuple:
    """A hashable, order-stable key for a config (frozensets → sorted tuples)
    — used to cache per-config economics and to make the search deterministic
    (property P6)."""
    items = []
    for k in sorted(cfg):
        v = cfg[k]
        if isinstance(v, (frozenset, set, list, tuple)):
            v = tuple(sorted(v))
        items.append((k, v))
    return tuple(items)


def qty_of(graph: "OfferGraph", cfg: Config) -> int:
    """The quantity a config buys (1 if the graph has no QUANTITY dim OR the
    config omits it — A4: partial configs must not crash)."""
    for d in graph.dims:
        if d.kind == DimKind.QUANTITY:
            return int(cfg.get(d.id, 1))
    return 1


def with_qty(graph: "OfferGraph", cfg: Config, qty: int) -> Config:
    """`cfg` with its QUANTITY dim set to `qty` (identity if there is none) —
    used to probe marginal cost/value of the q-th unit."""
    out = dict(cfg)
    for d in graph.dims:
        if d.kind == DimKind.QUANTITY:
            out[d.id] = qty
    return out


@dataclass
class OfferGraph:
    """The dimensions + their dependency edges + the pluggable cost model.
    Outside-option parameters live on the buyer (core/engine.Buyer), not
    here — the graph is what the *shop* posts, symmetric across buyers."""
    dims: list[Dimension]
    deps: "DepGraph" = None            # type: ignore[assignment]
    cost: "CostModel" = None           # type: ignore[assignment]
    name: str = ""

    def __post_init__(self) -> None:
        self.dims = list(self.dims)
        if self.deps is None:
            from core.deps import DepGraph
            self.deps = DepGraph()
        if self.cost is None:
            # A4: a directly-built graph must never NoneType-crash at quote.
            from core.cost import compose, const
            self.cost = compose(const())

    def dim(self, dim_id: str) -> Dimension:
        for d in self.dims:
            if d.id == dim_id:
                return d
        raise KeyError(dim_id)

    def enumerate_configs(self, pin: dict | None = None) -> Iterator[Config]:
        """Every dependency-valid configuration, in a deterministic order.

        The cartesian product of: one option per CHOICE/PREFERENCE/
        FULFILLMENT dim, every subset per ADDON dim (empty included), and
        1..qty_cap per QUANTITY dim. `pin` (dim_id → value) FIXES those dims
        to a single value instead of expanding them — the engine passes the
        profiler's FREE preference pins here so the search enumerates only the
        real levers (C1). Dependency-invalid combinations are pruned by
        `deps.is_valid` (core/deps.py)."""
        pin = pin or {}
        dims = sorted(self.dims, key=lambda d: d.id)
        per_dim: list[list[tuple[str, object]]] = []
        for d in dims:
            if d.id in pin:
                per_dim.append([(d.id, pin[d.id])])
            elif d.kind == DimKind.ADDON:
                opts = [o.id for o in d.options]
                subs: list[tuple[str, object]] = []
                for r in range(len(opts) + 1):
                    for combo in itertools.combinations(opts, r):
                        subs.append((d.id, frozenset(combo)))
                per_dim.append(subs)
            elif d.kind == DimKind.QUANTITY:
                per_dim.append([(d.id, q) for q in range(1, d.qty_cap + 1)])
            else:
                per_dim.append([(d.id, o.id) for o in d.options])
        for combo in itertools.product(*per_dim):
            cfg = dict(combo)
            if self.deps.is_valid(self, cfg):
                yield cfg
