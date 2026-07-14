"""The general offer-graph engine (core/) over HTTP — compile / profile /
quote a declarative JSON menu spec. The missing product brick: an external
agent can run the F1-validated general engine on THEIR menu without
installing anything.

BOTH formats accepted. `spec` may be either the RAW `dims` offer-graph spec
(exactly core.api.build_graph's declarative dict) OR the FRIENDLY menu the
public "run it on your own menu" page (arena/web/yourmenu.js) has a shop owner
PASTE — the one an external agent reading that page would POST back. A spec
carrying `items` is compiled through gametheory.server.menu_spec.friendly_to_dims
(a field-for-field port of the page's own menuToSpec) BEFORE validation, so the
hosted engine prices a pasted menu identically to the page; a spec carrying
`dims` is used as-is.

    RAW dims spec (the engine's native format):
    {"name": "corner coffee cart",
     "dims": [
       {"id": "item", "kind": "choice", "options": [
          {"id": "oat-latte", "price_delta": 5.25, "unit_cost": 1.20}, ...]},
       {"id": "extras",  "kind": "addon",       "options": [...]},
       {"id": "cup",     "kind": "preference",  "options": [...]},
       {"id": "pickup",  "kind": "fulfillment", "options": [
          {"id": "now",   "immediate": true,  "slot_ticks": 0},
          {"id": "in-20", "immediate": false, "slot_ticks": 2}]},
       {"id": "qty",     "kind": "quantity",   "qty_cap": 3}],
     "deps": {"valid_on": {...}, "requires": {...}, "excludes": {...}},
     "cost": ["const", "salvage_on_expiry", "scarcity_shadow",
              {"batch_economies": {"setup": 1.0, "marginal": 0.2}}]}

    FRIENDLY pasted menu (what yourmenu.js accepts; compiled to the above):
    {"name": "corner coffee cart",
     "items":  [{"id": "oat-latte", "price": 5.25, "cost": 1.20}, ...],
     "addons": [{"id": "extra-shot", "price": 1.00, "cost": 0.28}, ...],
     "preferences": [{"id": "cup", "options": [{"id": "for-here"}, ...]}],
     "slots":  [{"id": "now", "minutes": 0}, {"id": "in-20", "minutes": 20}],
     "max_qty": 3}

Three endpoints — stateless, no persistence, free-tier math:

  POST /v1/offer/compile   spec → compiled graph summary (dims, options,
                           cost stack, enumeration count)
  POST /v1/offer/profile   {spec, state?} → FREE / LEVER per dimension with
                           the one-line why (the divergence profiler — the
                           signature endpoint)
  POST /v1/offer/quote     {spec, state?, buyer, config?, opts?} → the Quote
                           receipt (price/listv/save/feasible/why).
                           HARD: discount-only, never above list.

HONESTY: every quote is advisory engine output on a caller-supplied menu —
never a binding offer from any seller. Responses say so ("advisory": true
plus a note) and state the discount-only invariant ("never_above_list":
true), which is ALSO re-enforced in code here (a final clamp on top of the
engine's own rung guard).

Guards: conservative input caps (dims / options / qty_cap / enumeration
size — the per-dim option cap reuses core.offer_graph.MAX_ADDON_OPTIONS),
finite numbers only, friendly 422s. capacity_relief needs a live Python
function, so it is NOT expressible in the JSON spec (the validator says so).
Rate limiting and the body-size cap come from the app-wide middleware
(gametheory/server/middleware.py) since everything lives under /v1/.
"""
from __future__ import annotations

import math
import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)

from core.api import build_graph
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as _engine_quote
from core.offer_graph import (MAX_ADDON_OPTIONS, DimKind, Dimension,
                              Negotiability, OfferGraph, qty_of)
# Read-only reuse of the profiler's own probe helpers so the $-spread we
# report is exactly the spread the classifier saw (the JS page re-implements
# this probe because core/js doesn't export it; the Python module does).
from core.profiler import _default_config, _variants
from core.profiler import profile as _core_profile
from core.state import ShopState
from gametheory.server.menu_spec import friendly_to_dims, is_friendly

router = APIRouter(prefix="/v1/offer", tags=["offer"])

# ─── conservative input caps (public, unauthenticated endpoint) ─────────────
MAX_DIMS = 8
MAX_OPTIONS_PER_DIM = MAX_ADDON_OPTIONS      # 12 — one cap for every dim kind
MAX_QTY_CAP = 12
MAX_CONFIGS = 20_000                         # total enumerable configurations
MAX_STATE_KEYS = 128
MAX_COST_ENTRIES = 8

_KINDS = ("choice", "addon", "preference", "fulfillment", "quantity")
_COST_TOKENS = ("const", "salvage_on_expiry", "scarcity_shadow")

ADVISORY_NOTE = ("simulated advisory output from the SNHP offer-graph engine "
                 "on a caller-supplied menu — not a binding offer from any "
                 "seller")


# ─── the spec models (validation = the friendly 422s) ───────────────────────


class OptionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    price_delta: float = Field(default=0.0, ge=0.0, le=1e9, allow_inf_nan=False,
        description="This option's contribution to the cart's LIST price")
    unit_cost: float = Field(default=0.0, ge=0.0, le=1e9, allow_inf_nan=False)
    salvage: float = Field(default=0.0, ge=0.0, le=1e9, allow_inf_nan=False)
    perishable: bool = False
    stock_limited: bool = False
    immediate: bool = True                     # fulfillment: faces the balk
    slot_ticks: int = Field(default=0, ge=0, le=10_000)


class DimSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    kind: str
    options: list[OptionSpec] = Field(default_factory=list,
                                      max_length=MAX_OPTIONS_PER_DIM)
    qty_cap: int = Field(default=1, ge=1, le=MAX_QTY_CAP)
    negotiable: Optional[Literal["free", "lever", "auto"]] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        k = v.strip().lower()
        if k not in _KINDS:
            raise ValueError(
                f"unknown dimension kind {v!r} — use one of: {', '.join(_KINDS)}")
        return k

    @model_validator(mode="after")
    def _shape(self) -> "DimSpec":
        if self.kind == "quantity":
            if self.options:
                raise ValueError(
                    f"dimension {self.id!r} is QUANTITY — it takes qty_cap "
                    "(an integer), not options")
        elif not self.options:
            raise ValueError(
                f"dimension {self.id!r} ({self.kind}) needs at least one option")
        seen: set[str] = set()
        for o in self.options:
            if o.id in seen:
                raise ValueError(
                    f"dimension {self.id!r} has duplicate option id {o.id!r}")
            seen.add(o.id)
        return self


class DepsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_on: dict[str, list[str]] = Field(default_factory=dict)
    requires: dict[str, list[str]] = Field(default_factory=dict)
    excludes: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("valid_on", "requires", "excludes")
    @classmethod
    def _small(cls, v: dict) -> dict:
        if len(v) > MAX_STATE_KEYS:
            raise ValueError(f"too many dependency edges (max {MAX_STATE_KEYS})")
        for k, ids in v.items():
            if len(ids) > MAX_OPTIONS_PER_DIM * MAX_DIMS:
                raise ValueError(f"deps[{k!r}] references too many options")
        return v


class MenuSpec(BaseModel):
    """core.api.build_graph's declarative spec, validated for hosting.

    DUAL-ACCEPT: a body carrying `items` is the FRIENDLY pasted menu (what
    arena/web/yourmenu.js accepts) and is compiled to the raw `dims` spec via
    menu_spec.friendly_to_dims before the hosting checks below run — so the
    hosted engine takes the exact JSON an agent reads off that page. A body
    carrying `dims` is the native spec and passes through untouched."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=120)
    dims: list[DimSpec] = Field(min_length=1, max_length=MAX_DIMS)
    deps: DepsSpec = Field(default_factory=DepsSpec)
    cost: list[str | dict] = Field(default_factory=lambda: ["const"],
                                   max_length=MAX_COST_ENTRIES)

    @model_validator(mode="before")
    @classmethod
    def _accept_friendly(cls, data):
        """Friendly menu (has `items`) → raw dims spec, before field checks.
        friendly_to_dims raises a ValueError (friendly, multi-problem) that
        pydantic surfaces as the 422, exactly like the page's error list."""
        if is_friendly(data):
            if "dims" in data:
                raise ValueError(
                    "send either the friendly 'items' menu or the raw 'dims' "
                    "spec, not both")
            return friendly_to_dims(data)
        return data

    @model_validator(mode="after")
    def _validate(self) -> "MenuSpec":
        # unique dim ids; at most one QUANTITY and one FULFILLMENT dim (the
        # engine reads the first of each — more than one is a modeling error)
        seen: set[str] = set()
        for d in self.dims:
            if d.id in seen:
                raise ValueError(f"duplicate dimension id {d.id!r}")
            seen.add(d.id)
        for kind in ("quantity", "fulfillment"):
            n = sum(1 for d in self.dims if d.kind == kind)
            if n > 1:
                raise ValueError(f"at most one {kind.upper()} dimension (got {n})")

        # globally-unique option ids: shop state (inventory/expiring/demand)
        # and deps are keyed by option id, so a collision would be ambiguous
        opt_ids: set[str] = set()
        for d in self.dims:
            for o in d.options:
                if o.id in opt_ids:
                    raise ValueError(
                        f"option id {o.id!r} appears on more than one "
                        "dimension — option ids must be unique across the menu")
                opt_ids.add(o.id)

        # deps must reference known options
        for rel in ("valid_on", "requires", "excludes"):
            edges: dict = getattr(self.deps, rel)
            for k, ids in edges.items():
                for oid in [k, *ids]:
                    if oid not in opt_ids:
                        raise ValueError(
                            f"deps.{rel} references unknown option id {oid!r}")

        # cost stack: zero-arg tokens as strings; batch_economies as a dict
        for e in self.cost:
            if isinstance(e, str):
                if e == "capacity_relief":
                    raise ValueError(
                        "capacity_relief needs a live Python function and "
                        "can't be expressed in a JSON spec — self-host "
                        "core/ to use it")
                if e == "batch_economies":
                    raise ValueError(
                        'batch_economies takes arguments — pass it as '
                        '{"batch_economies": {"setup": 1.0, "marginal": 0.2}}')
                if e not in _COST_TOKENS:
                    raise ValueError(
                        f"unknown cost component {e!r} — use "
                        f"{', '.join(_COST_TOKENS)} or "
                        '{"batch_economies": {...}}')
            elif isinstance(e, dict):
                if set(e) != {"batch_economies"}:
                    raise ValueError(
                        "a dict cost entry must be exactly "
                        '{"batch_economies": {"setup": ..., "marginal": ...}}')
                args = e["batch_economies"]
                if not isinstance(args, dict) or "setup" not in args:
                    raise ValueError('batch_economies needs {"setup": <number>} '
                                     '(optional "marginal")')
                extra = set(args) - {"setup", "marginal"}
                if extra:
                    raise ValueError(
                        f"batch_economies got unknown argument(s) {sorted(extra)}")
                for k in ("setup", "marginal"):
                    x = args.get(k, 0.0)
                    if x is None and k == "marginal":
                        continue
                    if (not isinstance(x, (int, float)) or isinstance(x, bool)
                            or not math.isfinite(x) or x < 0 or x > 1e9):
                        raise ValueError(
                            f"batch_economies.{k} must be a finite number ≥ 0")
            else:
                raise ValueError(f"cost entries are strings or a "
                                 f'{{"batch_economies": ...}} dict, got {e!r}')

        # enumeration guard: the search is the cartesian product below
        combos = 1.0
        for d in self.dims:
            if d.kind == "quantity":
                combos *= d.qty_cap
            elif d.kind == "addon":
                combos *= 2 ** len(d.options)
            else:
                combos *= max(1, len(d.options))
        if combos > MAX_CONFIGS:
            raise ValueError(
                f"this menu enumerates ~{combos:,.0f} configurations — above "
                f"the hosted cap of {MAX_CONFIGS:,}; trim add-ons, options, "
                "or qty_cap (or self-host core/)")
        return self


def _finite_dict(v: dict, what: str, lo: float = 0.0) -> dict:
    if len(v) > MAX_STATE_KEYS:
        raise ValueError(f"{what}: too many entries (max {MAX_STATE_KEYS})")
    for k, x in v.items():
        if not math.isfinite(x) or x < lo or abs(x) > 1e9:
            raise ValueError(f"{what}[{k!r}] must be a finite number ≥ {lo:g}")
    return v


class StateSpec(BaseModel):
    """The shop moment the cost model reads (core/state.ShopState). All
    fields optional — an omitted state is a neutral shop (no inventory
    signals, nothing expiring, unconstrained capacity)."""
    model_config = ConfigDict(extra="forbid")
    tick: int = Field(default=0, ge=0)
    inventory: dict[str, float] = Field(default_factory=dict,
        description="option_id -> units on hand (finite stock)")
    capacity: dict[int, float] = Field(default_factory=dict,
        description="slot_ticks -> units a deferred slot can still absorb")
    expiring: list[str] = Field(default_factory=list, max_length=MAX_STATE_KEYS,
        description="option ids currently priced at salvage (batch expiring)")
    expected_demand: dict[str, float] = Field(default_factory=dict,
        description="option_id -> expected rest-of-horizon list-price demand")

    @field_validator("inventory", "capacity", "expected_demand")
    @classmethod
    def _finite(cls, v: dict, info) -> dict:
        return _finite_dict(v, info.field_name)


class BuyerSpec(BaseModel):
    """A separable buyer (core/engine.SeparableBuyer): per-option dollar
    values, a quantity-decay ladder, and scalar outside/balk/defer reports."""
    model_config = ConfigDict(extra="forbid")
    values: dict[str, dict[str, float]] = Field(default_factory=dict,
        description="dim_id -> option_id -> per-unit dollar value")
    qty_decay: float = Field(default=0.15, ge=0.0, le=1.0, allow_inf_nan=False,
        description="each extra unit is worth this fraction of the previous")
    outside: float = Field(default=0.0, ge=0.0, le=1e9, allow_inf_nan=False,
        description="the buyer's outside-option surplus in dollars")
    balk: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False,
        description="probability a walk-in is turned away by the queue")
    defer: dict[int, float] = Field(default_factory=dict,
        description="slot_ticks -> dollar cost of waiting for that slot")

    @field_validator("defer")
    @classmethod
    def _defer_ok(cls, v: dict) -> dict:
        return _finite_dict(v, "buyer.defer")

    @field_validator("values")
    @classmethod
    def _values_ok(cls, v: dict) -> dict:
        if len(v) > MAX_DIMS * 2:
            raise ValueError("buyer.values: too many dimensions")
        for dim_id, opts in v.items():
            _finite_dict(opts, f"buyer.values[{dim_id!r}]", lo=-1e9)
        return v


class QuoteOptsSpec(BaseModel):
    """The hosted subset of core/engine.QuoteOpts."""
    model_config = ConfigDict(extra="forbid")
    quote_lookers: bool = Field(default=True,
        description="False = refuse buyers who'd never pay list (IC floor)")
    min_price_frac: float = Field(default=0.0, ge=0.0, le=1.0,
        description="never quote below this fraction of list")
    qty_appetite: bool = Field(default=False,
        description="don't upsell a unit the buyer values below its cost")
    seller_weight: float = Field(default=0.5, ge=0.0, le=1.0,
        description="0.5 = symmetric Nash; →1 tilts surplus to the seller")


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: MenuSpec
    state: Optional[StateSpec] = None


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: MenuSpec
    state: Optional[StateSpec] = None
    buyer: BuyerSpec
    config: Optional[dict] = Field(default=None,
        description="pin dims: dim_id -> option id | [option ids] (addon) | "
                     "int (quantity). Omit to search every valid cart.")
    opts: QuoteOptsSpec = Field(default_factory=QuoteOptsSpec)


# ─── spec → engine objects ───────────────────────────────────────────────────


def _graph(spec: MenuSpec) -> OfferGraph:
    try:
        return build_graph(spec.model_dump(exclude_none=True))
    except (ValueError, KeyError) as e:          # belt-and-braces: the models
        raise ValueError(f"could not compile spec: {e}")   # above should catch


def _shop_state(s: Optional[StateSpec]) -> ShopState:
    if s is None:
        return ShopState()
    return ShopState(tick=s.tick, inventory=dict(s.inventory),
                     capacity=dict(s.capacity), expiring=set(s.expiring),
                     expected_demand=dict(s.expected_demand))


def _sep_buyer(b: BuyerSpec) -> SeparableBuyer:
    values = {(dim_id, oid): x
              for dim_id, opts in b.values.items() for oid, x in opts.items()}
    return SeparableBuyer(values=values, qty_decay=b.qty_decay,
                          outside=b.outside, balk=b.balk, defer=dict(b.defer))


def _engine_config(graph: OfferGraph, config: Optional[dict]):
    """Validate a caller config against the compiled graph (friendly errors
    instead of engine KeyErrors) and coerce add-on lists to frozensets."""
    if not config:
        return None
    dims = {d.id: d for d in graph.dims}
    out: dict = {}
    for k, v in config.items():
        d = dims.get(k)
        if d is None:
            raise ValueError(f"config: unknown dimension {k!r} "
                             f"(this menu's dims: {sorted(dims)})")
        opt_ids = [o.id for o in d.options]
        if d.kind == DimKind.QUANTITY:
            if not isinstance(v, int) or isinstance(v, bool) \
                    or not 1 <= v <= d.qty_cap:
                raise ValueError(f"config[{k!r}]: quantity must be an integer "
                                 f"between 1 and {d.qty_cap}")
            out[k] = v
        elif d.kind == DimKind.ADDON:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise ValueError(f"config[{k!r}]: an add-on selection is a "
                                 "list of option ids (may be empty)")
            unknown = set(v) - set(opt_ids)
            if unknown:
                raise ValueError(f"config[{k!r}]: unknown option(s) "
                                 f"{sorted(unknown)} — options: {opt_ids}")
            out[k] = frozenset(v)
        else:
            if not isinstance(v, str) or v not in opt_ids:
                raise ValueError(f"config[{k!r}]: pick one of {opt_ids}")
            out[k] = v
    return out


def _json_config(cfg: Optional[dict]) -> Optional[dict]:
    if cfg is None:
        return None
    return {k: (sorted(v) if isinstance(v, (frozenset, set)) else v)
            for k, v in cfg.items()}


# ─── the three operations (shared by HTTP and MCP) ──────────────────────────


def _compile_impl(spec: MenuSpec) -> dict:
    graph = _graph(spec)
    n_configs = sum(1 for _ in graph.enumerate_configs())   # ≤ MAX_CONFIGS
    dims = []
    for d in graph.dims:
        row: dict = {"id": d.id, "kind": d.kind.value}
        if d.kind == DimKind.QUANTITY:
            row["qty_cap"] = d.qty_cap
        else:
            row["options"] = [
                {"id": o.id, "label": o.label, "price_delta": o.price_delta,
                 "unit_cost": o.unit_cost, "salvage": o.salvage,
                 "perishable": o.perishable, "stock_limited": o.stock_limited,
                 "immediate": o.immediate, "slot_ticks": o.slot_ticks}
                for o in d.options]
        dims.append(row)
    cost_stack = [e if isinstance(e, str) else "batch_economies"
                  for e in spec.cost]
    return {"name": graph.name, "dims": dims, "cost_stack": cost_stack,
            "configs": n_configs,
            "note": ("compiled OK — the engine will search these "
                     f"{n_configs} dependency-valid configurations")}


def _probe_spread(graph: OfferGraph, state: ShopState, dim: Dimension) -> float:
    """The dollar spread the profiler's cost probe saw for this dimension —
    the exact probe core/profiler runs, reused so the number we print is the
    number the verdict came from."""
    variants = _variants(dim, _default_config(graph))
    if len(variants) < 2:
        return 0.0
    costs = [graph.cost.quote(graph, state, c, qty_of(graph, c)).c_eff
             for c in variants]
    return max(costs) - min(costs)


def _why(dim: Dimension, verdict: Negotiability, spread: float) -> str:
    if verdict == Negotiability.LEVER:
        return (f"changing '{dim.id}' moves the shop's effective cost by up "
                f"to ${spread:.2f} — a real negotiation surface")
    if dim.kind == DimKind.FULFILLMENT:
        return ("zero unit-cost spread — timing's economics flow through the "
                "balk/capacity channels at quote time, not through cost")
    if dim.kind == DimKind.QUANTITY:
        return "quantity moves no cost here — nothing to negotiate on volume"
    return ("zero cost spread across its options — a costless customization; "
            "the buyer just gets their favorite, it is never priced")


def _profile_impl(spec: MenuSpec, state: Optional[StateSpec]) -> dict:
    graph = _graph(spec)
    st = _shop_state(state)
    prof = _core_profile(graph, st)
    dims = []
    for d in graph.dims:
        verdict = prof[d.id]
        spread = _probe_spread(graph, st, d)
        dims.append({"dim": d.id, "kind": d.kind.value,
                     "verdict": verdict.value.upper(),
                     "cost_spread": round(spread, 2),
                     "why": _why(d, verdict, spread)})
    return {"name": graph.name, "dims": dims,
            "verdicts": {row["dim"]: row["verdict"] for row in dims},
            "note": ("FREE = costless customization, never a price lever; "
                     "LEVER = changing it moves the shop's cost, a real "
                     "negotiation surface. Verdicts are properties of the "
                     "menu's economics, not of any buyer.")}


def _quote_impl(spec: MenuSpec, state: Optional[StateSpec], buyer: BuyerSpec,
                config: Optional[dict], opts: QuoteOptsSpec) -> dict:
    graph = _graph(spec)
    st = _shop_state(state)
    by = _sep_buyer(buyer)
    cfg = _engine_config(graph, config)
    qopts = QuoteOpts(quote_lookers=opts.quote_lookers,
                      min_price_frac=opts.min_price_frac,
                      qty_appetite=opts.qty_appetite,
                      seller_weight=opts.seller_weight)
    q = _engine_quote(graph, st, by, config=cfg, opts=qopts)

    base = {"never_above_list": True, "advisory": True, "note": ADVISORY_NOTE}
    if q is None:
        return {**base, "outcome": "walk", "quote": None,
                "why": ["no available configuration beats this buyer's "
                        "outside option at or below list — nothing to quote "
                        "(a looker is refused rather than priced below the "
                        "menu, and phantom stock is never sold)"]}

    # HARD discount-only enforcement: the engine's rungs are already clamped
    # ≤ list, but the promise is load-bearing, so re-enforce it here too.
    price = round(min(q.price, q.listv), 2)
    outcome = "negotiated" if q.feasible else "at_list"
    return {**base, "outcome": outcome, "quote": {
        "config": _json_config(q.config),
        "price": price,
        "listv": round(q.listv, 2),
        "save": round(max(0.0, q.listv - price), 2),
        "cost": round(q.cost, 4),
        "value": round(q.value, 4),
        "seller_gain": round(q.seller_gain, 4),
        "buyer_gain": round(q.buyer_gain, 4),
        "feasible": q.feasible,
        "why": q.why,
    }}


# ─── dict-in / dict-out surface (the MCP tools call these) ──────────────────


def _friendly(e: ValidationError) -> str:
    parts = []
    for err in e.errors()[:5]:
        loc = ".".join(str(x) for x in err["loc"]) or "body"
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts)


def profile_menu(spec: dict, state: Optional[dict] = None) -> dict:
    """Validate raw dicts and profile — raises ValueError on bad input."""
    try:
        ms = MenuSpec.model_validate(spec)
        st = StateSpec.model_validate(state) if state is not None else None
    except ValidationError as e:
        raise ValueError(_friendly(e))
    return _profile_impl(ms, st)


def quote_menu(spec: dict, buyer: dict, state: Optional[dict] = None,
               config: Optional[dict] = None, *, quote_lookers: bool = True,
               min_price_frac: float = 0.0, qty_appetite: bool = False,
               seller_weight: float = 0.5) -> dict:
    """Validate raw dicts and quote — raises ValueError on bad input."""
    try:
        ms = MenuSpec.model_validate(spec)
        st = StateSpec.model_validate(state) if state is not None else None
        by = BuyerSpec.model_validate(buyer)
        op = QuoteOptsSpec(quote_lookers=quote_lookers,
                           min_price_frac=min_price_frac,
                           qty_appetite=qty_appetite,
                           seller_weight=seller_weight)
    except ValidationError as e:
        raise ValueError(_friendly(e))
    return _quote_impl(ms, st, by, config, op)


# ─── HTTP handlers ───────────────────────────────────────────────────────────


def _free_headers(response: Response, t0: float) -> None:
    response.headers["X-GT-Cost-USD"] = "0"
    response.headers["X-GT-Latency-Ms"] = f"{(time.time() - t0) * 1000:.1f}"


@router.post(
    "/compile",
    summary="Compile a JSON menu spec into an offer graph (summary)",
    description=(
        "Body: the declarative menu spec itself (dims of kind choice / addon "
        "/ preference / fulfillment / quantity, each with typed options, an "
        "optional deps graph, and a cost stack of const / salvage_on_expiry "
        "/ scarcity_shadow / batch_economies). Returns the compiled graph "
        "summary — dims, options, cost stack, and how many dependency-valid "
        "configurations the engine will search. Free, stateless, nothing is "
        "stored. Malformed or oversized specs get a 422 with a plain-English "
        "reason."
    ),
)
def offer_compile(spec: MenuSpec, response: Response):
    t0 = time.time()
    try:
        out = _compile_impl(spec)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _free_headers(response, t0)
    return out


@router.post(
    "/profile",
    summary="Profile a menu: FREE vs LEVER per dimension (the divergence profiler)",
    description=(
        "The signature endpoint. Give it {spec, state?} and every dimension "
        "is classified by probing the cost model: FREE (zero cost gradient — "
        "a costless customization the buyer just gets their favorite of, "
        "never a price lever) or LEVER (changing the option moves the shop's "
        "effective cost — a real negotiation surface). Each verdict carries "
        "the probed dollar spread and a one-line why. Verdicts are properties "
        "of the menu's economics, not of any buyer."
    ),
)
def offer_profile(req: ProfileRequest, response: Response):
    t0 = time.time()
    try:
        out = _profile_impl(req.spec, req.state)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _free_headers(response, t0)
    return out


@router.post(
    "/quote",
    summary="Quote a buyer on a menu — Nash split, discount-only (never above list)",
    description=(
        "Give it {spec, state?, buyer, config?, opts?} and get the Quote "
        "receipt: price, listv, save, feasible, why. The engine searches "
        "every valid configuration (or prices the pinned `config`), anchors "
        "the disagreement on the buyer's best full-price menu order, and "
        "picks the Nash split of the created surplus. HARD GUARANTEE: "
        "discount-only — the price is never above the menu's list value "
        "(`never_above_list: true`, enforced in code). Quotes are advisory "
        "engine output on a caller-supplied menu, not a binding offer "
        "(`advisory: true`)."
    ),
)
def offer_quote(req: QuoteRequest, response: Response):
    t0 = time.time()
    try:
        out = _quote_impl(req.spec, req.state, req.buyer, req.config, req.opts)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _free_headers(response, t0)
    return out
