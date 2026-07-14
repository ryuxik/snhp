"""Vend vertical expressed as a core OfferGraph — the Phase-3a golden adapter.

Since the engine flip, vend.scenario.nash_quote is a thin delegation to
`engine_nash_quote` below (production, mounted in api.snhp.dev): the bespoke
Nash-search body was deleted after the golden gates proved the engine
reproduces it on the shipped trajectories (100% of 8,000+ replayed quotes;
committed sim totals byte-exact). This adapter builds vend's offer graph, its
finite-stock scarcity cost model, a per-quote ShopState, and a SeparableBuyer
from vend's OWN constants and world helpers, and runs core.engine.quote over
them.

KNOWN BOUNDARY (documented at the flip, 2026-07-14): at EXACT decimal ties on
the min-gain buffer, the bespoke pricer's thr = (min_gain_frac·list)·qty and
margin−d_s versus the engine's min_gain_frac·(qty·list) and (p−c_eff)−d_s
differ by one ulp and could disagree — 7 of 123,200 quotes in the old
block-flywheel sweep hit such a tie (witness: water-1L×3, margin−d_s =
0.9900000000000002 vs thr = 0.99). The affected artifacts were re-pinned from
their committed generators at the flip (28 leaves, ≤9e-4, verdicts unchanged).

The mapping (docs/REDESIGN.md Phase 3), dimension by dimension:

  sku   CHOICE     price_delta=list_price, unit_cost=unit_cost, salvage=salvage;
                   perishable (any SKU can expire) and stock_limited (the
                   qty cap = min(QTY_CAP, stock) — the HARD availability gate).
  qty   QUANTITY   1..QTY_CAP.

  (no toppings / fulfillment / preference — vend is sku × qty.)

The cost model is the ONE real difference from boba: finite stock with a
scarcity SHADOW. `machine_margin` re-prices a unit the machine expects to sell
at list later today at list, not at cost — selling it discounted DISPLACES that
sale. core.cost.scarcity_shadow is exactly this displacement rule, so the c_eff
it returns equals vend's displacement-adjusted cost. The reconciliation notes:

  * TWO-COST SPLIT. vend.scenario.enumerate_outcomes floors its price rungs at
    the RAW per-unit c_eff (salvage/unit_cost) while machine_margin measures the
    gain against the DISPLACEMENT-adjusted cost. The engine collapses these into
    one c_eff. The collapse leaves the DISAGREEMENT and the MARGIN untouched
    (both are the displacement-adjusted cost, which the engine already uses) —
    it changes ONLY the rung GRID. vend also rounds PER-UNIT prices (× qty),
    where the engine rounds TOTAL prices (diverging for qty > 1). Both are
    reproduced exactly by handing the engine vend's own rung grid through
    core.cost.CostQuote.rungs (VendCost below). `two_cost_split=False` disables
    it (collapsed, engine-generic rungs) so the divergence is measurable — the
    golden test runs both.

`engine_nash_quote` is a drop-in for vend.scenario.nash_quote: same signature,
same NashQuote return, same None semantics (a walk / no-mutual-gain → outcome
None, which the sim prices at the sticker board). On outcome=None the
disagreement fields still carry the real no-deal point (d_machine = the board
counterfactual's margin, d_buyer = the board surplus or the outside option),
exactly as nash_quote reports them — the engine's at-list fallback audit
carries them through. The one non-reproduced field: `joint_best` is the CHOSEN
outcome's realized joint gain clamped at 0 (0.0 on no-deal), not the
search-wide max nash_quote tracks — no caller reads it (verified repo-wide).
"""
from __future__ import annotations

from dataclasses import dataclass

from core.cost import CostQuote
from core.deps import DepGraph
from core.engine import QuoteOpts, SeparableBuyer
from core.engine import quote as _core_quote
from core.offer_graph import DimKind, Dimension, OfferGraph, Option
from core.state import ShopState

from vend.scenario import (NashQuote, Outcome, PRICE_RUNGS, c_eff,
                           expected_list_demand, outside_surplus)
from vend.world import QTY_CAP, QTY_DECAY

SKU_DIM = "sku"
QTY_DIM = "qty"


# ── the finite-stock cost model (scarcity_shadow + the two-cost rung grid) ──
@dataclass
class VendCost:
    """vend.scenario.machine_margin as a core CostModel.

    `c_eff` is the displacement-adjusted TOTAL cost the gain/disagreement are
    measured against (= list-value − machine_margin). `rungs` (when
    two_cost_split) is vend.enumerate_outcomes' EXACT price grid: PRICE_RUNGS
    per-unit rungs from the RAW per-unit c_eff up to list, rounded per unit and
    scaled by qty. With two_cost_split=False no grid is supplied and the engine
    builds its own (collapsed) rungs off the displacement-adjusted floor — the
    measurable divergence the golden test quantifies.
    """
    two_cost_split: bool = True
    price_rungs: int = PRICE_RUNGS

    def quote(self, graph: OfferGraph, state: ShopState, config, qty: int
              ) -> CostQuote:
        sku = config[SKU_DIM]
        opt = graph.dim(SKU_DIM).option(sku)
        # raw per-unit opportunity cost: salvage if this SKU dies tonight, else
        # unit cost (vend.scenario.c_eff, via state.expiring set by shop_state).
        ce = opt.salvage if (opt.perishable and sku in state.expiring) \
            else opt.unit_cost
        lp = opt.price_delta
        s = state.inventory.get(sku, 0.0)
        D = state.expected_demand.get(sku, 0.0)
        excess = max(0.0, s - D)                    # units nobody at list wants
        displaced = min(float(qty), max(0.0, qty - excess))
        # displacement-adjusted total cost: displaced units cost list (their
        # sale is merely moved forward), the rest cost c_eff. This is exactly
        # list_value − machine_margin, so gain = price − c_eff = margin.
        c_eff_total = (qty - displaced) * ce + displaced * lp

        rungs = None
        if self.two_cost_split:
            # vend.scenario.enumerate_outcomes, per-unit → total.
            if ce >= lp:
                unit_rungs = [lp]
            else:
                step = (lp - ce) / (self.price_rungs - 1)
                unit_rungs = [round(ce + i * step, 2)
                              for i in range(self.price_rungs)]
            rungs = tuple(qty * u for u in unit_rungs)

        return CostQuote(c_eff=c_eff_total, credit=0.0,
                         floors_at_list=(ce >= lp), rungs=rungs)


# ── the graph (static menu — cached per (menu, split mode)) ─────────────────
_GRAPH_CACHE: dict = {}


def _menu_sig(listings) -> tuple:
    return tuple(sorted(
        (sku, l.list_price, l.unit_cost, l.salvage) for sku, l in listings.items()))


def build_graph(listings, *, two_cost_split: bool = True) -> OfferGraph:
    """vend's offer graph from a catalog (dict[sku, Listing]).

    Every SKU is a CHOICE option carrying its list/cost/salvage; it is
    `stock_limited` (the qty cap = min(QTY_CAP, stock) HARD gate) and
    `perishable` (eligible for the salvage carve-out when it expires tonight).
    """
    sku = Dimension(SKU_DIM, DimKind.CHOICE, options=tuple(
        Option(s, label=s, price_delta=l.list_price, unit_cost=l.unit_cost,
               salvage=l.salvage, perishable=True, stock_limited=True)
        for s, l in listings.items()))
    qty = Dimension(QTY_DIM, DimKind.QUANTITY, qty_cap=QTY_CAP)
    return OfferGraph(dims=[sku, qty], deps=DepGraph(),
                      cost=VendCost(two_cost_split=two_cost_split),
                      name="vend")


def graph_for(listings, *, two_cost_split: bool = True) -> OfferGraph:
    key = (_menu_sig(listings), two_cost_split)
    g = _GRAPH_CACHE.get(key)
    if g is None:
        g = build_graph(listings, two_cost_split=two_cost_split)
        _GRAPH_CACHE[key] = g
    return g


# ── per-quote projections of the live machine ───────────────────────────────
def shop_state(state, *, dow_mult: float = 1.0, mult_hat: float = 1.0,
               share_fn=None, daily_fn=None, traffic_scale: float = 1.0
               ) -> ShopState:
    """Project vend.core.MachineState onto the generic core ShopState.

    - inventory[sku] = live stock → the stock_limited qty cap.
    - expiring = {sku : days_to_expiry <= 0} → the salvage carve-out (c_eff).
    - expected_demand[sku] = vend.scenario.expected_list_demand(...) with the
      IDENTICAL demand context nash_quote uses (dow_mult, mult_hat, the SKU's
      learned share, its EWMA realized daily, the traffic scale) → the scarcity
      shadow's displacement threshold. Computed ONLY for in-stock SKUs (the
      only ones that yield a config), matching nash_quote's sku_ctx loop.
    """
    listings = state.listings
    _share = share_fn if share_fn is not None else (lambda s: 1.0 / len(listings))
    inventory: dict[str, float] = {}
    expected_demand: dict[str, float] = {}
    expiring: set[str] = set()
    for sku in listings:
        stock = state.stock(sku)
        if stock <= 0:
            continue
        inventory[sku] = float(stock)
        emp = daily_fn(sku) if daily_fn is not None else None
        expected_demand[sku] = expected_list_demand(
            state, sku, dow_mult=dow_mult, mult_hat=mult_hat,
            share=_share(sku), emp_daily=emp, traffic_scale=traffic_scale)
        dte = state.days_to_expiry(sku)
        if dte is not None and dte <= 0:
            expiring.add(sku)
    return ShopState(tick=state.tick, inventory=inventory,
                     expected_demand=expected_demand, expiring=expiring,
                     extra={"vend": state})


def buyer_for(disclosed_wtp: dict[str, float], disclosed_walk_cost: float,
              catalog) -> SeparableBuyer:
    """A SeparableBuyer from a DISCLOSED buyer (== the true one when honest;
    the understated/free-walk report when a liar). Its per-SKU value and its
    outside option are both priced off the SAME disclosed report, exactly as
    nash_quote does — the buyer's value from disclosed_wtp, the outside surplus
    from the bodega board (catalog.bodega_price) minus the disclosed walk."""
    values = {(SKU_DIM, sku): disclosed_wtp[sku] for sku in catalog}
    s_out = max(0.0, outside_surplus(disclosed_wtp, disclosed_walk_cost, catalog))
    return SeparableBuyer(values=values, qty_decay=QTY_DECAY, outside=s_out,
                          balk=0.0, defer={})


def _cand_filter(allowed):
    """vend's `allowed` (Outcome → bool) as a core cand_filter — restricting the
    WHOLE candidate set (disagreement + search), exactly as nash_quote applies
    `allowed` to both its board-disagreement scan and enumerate_outcomes. In
    practice `allowed` is price-independent (it constrains the intent's SKU/qty
    — vend/api.py:152), so a dummy price probes it; the intent thus also gates
    the board counterfactual (a substitutes-forbidden buyer's threat point is
    their best ALLOWED board bundle)."""
    if allowed is None:
        return None

    def _f(graph, state, buyer, config) -> bool:
        return allowed(Outcome(config[SKU_DIM], int(config[QTY_DIM]), 0.0))
    return _f


# ── the drop-in pricer ──────────────────────────────────────────────────────
def engine_nash_quote(state, disclosed_wtp: dict[str, float],
                      disclosed_walk_cost: float, *,
                      dow_mult: float = 1.0, mult_hat: float = 1.0,
                      share_fn=None, allowed=None, daily_fn=None,
                      min_gain: float = 0.0, min_gain_frac: float = 0.0,
                      traffic_scale: float = 1.0,
                      seller_weight: float = 0.5,
                      two_cost_split: bool = True) -> NashQuote:
    """core.engine.quote wearing vend.scenario.nash_quote's signature.

    Returns a NashQuote (vend's own dataclass). A negotiated discount maps to an
    Outcome; the engine's feasible=False at-list fallback and its None walk both
    map to outcome=None, reproducing nash_quote's None semantics (the sim then
    prices the sticker board). d_machine / u_machine carry the seller
    disagreement + margin the sim reads for neg_machine_gain; the buyer-side and
    joint-surplus fields are populated for parity (unused by the sim)."""
    graph = graph_for(state.listings, two_cost_split=two_cost_split)
    sstate = shop_state(state, dow_mult=dow_mult, mult_hat=mult_hat,
                        share_fn=share_fn, daily_fn=daily_fn,
                        traffic_scale=traffic_scale)
    buyer = buyer_for(disclosed_wtp, disclosed_walk_cost, state.listings)
    opts = QuoteOpts(
        min_price_frac=0.0, qty_appetite=False, quote_lookers=True,
        min_gain_abs=min_gain, min_gain_frac=min_gain_frac,
        price_rungs=PRICE_RUNGS, seller_weight=seller_weight,
        prune_free=False, cand_filter=_cand_filter(allowed))
    q = _core_quote(graph, sstate, buyer, opts=opts)

    if q is None:
        # walk: never a board buyer (best board surplus ≤ 0 or < outside, or
        # nothing in stock / nothing allowed) — the bespoke pricer's
        # outside-branch disagreement: d_b = claimed outside, d_s = 0.
        return NashQuote(None, 0.0, buyer.outside, 0.0, 0.0, 0.0, 0.0, [])
    if not q.feasible:
        # at-list fallback: a board buyer no discount could beat — the board
        # disagreement stands, carried by the engine's fallback audit.
        return NashQuote(None, q.audit.get("d_seller", 0.0),
                         q.audit.get("d_buyer", 0.0), 0.0, 0.0, 0.0, 0.0, [])

    sku = q.config[SKU_DIM]
    qty = int(q.config[QTY_DIM])
    unit_price = round(q.price / qty, 2)
    d_s = q.audit.get("d_seller", 0.0)
    d_b = q.audit.get("d_buyer", 0.0)
    u_s = q.seller_gain + d_s          # margin of the quoted outcome
    u_b = q.buyer_gain + d_b           # buyer's claimed surplus
    joint_realized = q.seller_gain + q.buyer_gain
    lp = state.listings[sku].list_price
    dte = state.days_to_expiry(sku)
    why = ["negotiated for you", f"{qty} unit{'s' if qty > 1 else ''}"]
    if dte is not None and dte <= 1:
        why.append("takes stock expiring soon")
    if unit_price < lp:
        why.append(f"${lp - unit_price:.2f}/unit under list")
    else:
        why.append("at list")
    return NashQuote(Outcome(sku, qty, unit_price), d_s, d_b, u_s, u_b,
                     max(joint_realized, 0.0), joint_realized, why)
