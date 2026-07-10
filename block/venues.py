"""Venue adapters — each sim wrapped onto the block clock.

B0 ships two venues:

  * VendingVenue — the vend/ machine verbatim (Listings, lots, nightly
    restock/spoilage, the Quote protocol with its type-enforced invariants),
    wearing the NYC catalog from block/calibration.py. Sticker world →
    StaticPolicy board; SNHP world → A2APolicy brokered Nash quotes
    (vend.scenario.nash_quote via the policy, library defaults, attested).
  * BodegaVenue — a posted-price venue with its own deep inventory at
    calibration.BODEGA_CATALOG prices in BOTH worlds: B0 models the bodega
    as a non-adopter (it adopts SNHP in a later phase); its role here is to
    be the machine's REAL outside option, and to catch the machine's
    overflow and defectors.

Layering rule (B0 hard requirement): venues know their own inventory,
prices, and policy. They know NOTHING about the ledger — settles return
receipts (vend Quotes / plain spend tuples) and keep venue-side per-day
revenue counters so the ledger's event-side aggregates can be cross-checked
for exact money conservation. They also know nothing about consumers'
identities beyond what the protocol allows (disclosed WTP + walk cost).

Honesty notes on the machine's believed outside option: Listing.bodega_price
is the ACTUAL bodega posted price for goods the bodega carries (cola-20oz
3.25, chips 2.50) and a ×1.15 phantom off the UN-anchored profit-optimal
sticker otherwise (vend's BODEGA_MARKUP convention: the competitor prices
off true demand, never off our anchor). The Nash engine's disagreement
point uses these; the CONSUMER's acceptance in the runner uses the real
block alternatives (actual bodega catalog, actual walk), so engine
misbelief can only cost the machine a declined quote, never the buyer.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from block import calibration
from block.population import expected_home_rate
from vend.core import Listing, QuoteItem, make_quote, substream
from vend.policies import A2APolicy, StaticPolicy
from vend.regulars import Regular, RegularPool
from vend.scenario import NashQuote
from vend.world import (TICKS_PER_DAY, WTP_SIGMA, WorldConfig as VendWorldConfig,
                        _profit_optimal_list_price, end_of_day, fresh_machine,
                        hour_of)

NON_OVERLAP_OUTSIDE_MARKUP = 1.15   # vend.world.BODEGA_MARKUP, kept explicit


@dataclass(frozen=True)
class BlockConfig:
    """B0 world knobs. sigma_cal defaults ON (0.15, the P1.5 grid's central
    cell): a competent NYC operator prices from finite history, not
    omniscience — this is also where much of the SNHP world's recovery
    margin lives. anchor_mult is the probe knob for the substitution and
    fairness tests (1.0 = the honest sticker)."""
    sigma_cal: float = 0.15
    anchor_mult: float = 1.0
    regulars: int = 0


def build_block_catalog(cfg: BlockConfig, master_seed: int) -> dict[str, Listing]:
    """The machine's NYC board. List price = vend's profit-optimal single
    price on a sigma_cal-NOISED operator estimate of each SKU's wtp_mu
    (μ̂ = μ·lognormal(0, σ_cal)), times the anchor probe. bodega_price =
    the actual bodega posted price where the bodega carries the good, else
    the ×1.15 phantom off the TRUE-μ optimal sticker (anchor-independent —
    the outside world does not reprice when we anchor)."""
    bodega_posted = {item: price for item, price, _cost in calibration.BODEGA_CATALOG}
    cat: dict[str, Listing] = {}
    for sku, mu, cost, salv, life, par in calibration.VENDING_CATALOG:
        if cfg.sigma_cal > 0:
            rng = np.random.default_rng(substream(master_seed, "cal", sku))
            mu_est = float(mu * rng.lognormal(0.0, cfg.sigma_cal))
        else:
            mu_est = mu
        lp = round(_profit_optimal_list_price(mu_est, cost) * cfg.anchor_mult, 2)
        outside = bodega_posted.get(sku) if sku in bodega_posted else round(
            _profit_optimal_list_price(mu, cost) * NON_OVERLAP_OUTSIDE_MARKUP, 2)
        cat[sku] = Listing(sku=sku, list_price=lp, unit_cost=cost, salvage=salv,
                           shelf_life_days=life, par_stock=par,
                           wtp_mu_est=mu_est, bodega_price=outside)
    return cat


class VendingVenue:
    """The vend machine on the block. Same Listing/lot/Quote machinery,
    same policies; only the crowd curve fed to the learner is the block's."""

    name = "vending"
    rent_per_day = 0.0   # office-lobby machine: calibration.py carries no
                         # vending rent (location commission is a pilot-data
                         # calibration TARGET, deliberately absent in B0)

    def __init__(self, world: str, cfg: BlockConfig, master_seed: int,
                 catalog: dict[str, Listing] | None = None):
        if world not in ("sticker", "snhp"):
            raise ValueError(f"unknown world {world!r}")
        self.world = world
        self.master_seed = master_seed
        self.catalog = catalog if catalog is not None \
            else build_block_catalog(cfg, master_seed)
        self.policy = StaticPolicy() if world == "sticker" else A2APolicy()
        self.state = fresh_machine(f"block-vend-{world}", self.catalog)
        # venue-side truth, cross-checked by the conservation tests
        self.revenue_by_day: dict[int, float] = {}
        self.units_vended = 0
        self.units_stocked = sum(l.quantity for l in self.state.lots)

    @property
    def learner(self):
        return getattr(self.policy, "learner", None)

    def begin_day(self, day: int) -> None:
        if self.learner is not None:
            self.learner.begin_day(1.0)     # B0: no public calendar yet

    def observe_arrivals(self, tick: int, n: int) -> None:
        """Feed the demand learner what a real machine can see: its own
        crowd. Expected base = the block's analytic vending-home curve."""
        if self.learner is not None:
            self.learner.observe_arrivals(expected_home_rate("vending", tick), n)

    def price_board(self) -> dict[str, tuple[float, list[str]]]:
        return self.policy.price_board(self.state)

    def quote(self, disclosed_wtp: dict[str, float],
              disclosed_walk: float) -> NashQuote | None:
        """Brokered Nash quote (SNHP world only; the sticker world has no
        negotiation surface). `disclosed_walk` is the buyer's RELATIVE
        hassle of the bodega vs the machine from where they stand: positive
        for a vending-home shopper (the bodega costs a walk), negative for
        a bodega-home one (the MACHINE costs the walk) — the truthful
        disclosure that makes the engine's disagreement point match the
        buyer's real acceptance threshold."""
        if not isinstance(self.policy, A2APolicy):
            return None
        shim = SimpleNamespace(wtp=disclosed_wtp, walk_cost=disclosed_walk, uid=0)
        nq, _lied = self.policy.quote_for(self.state, shim, 1.0)  # attested
        return nq

    def settle(self, sku: str, qty: int, unit_price: float, why: list[str],
               day: int, tick: int, uid: int):
        """The one sale path: constructs a protocol Quote (discount-only and
        receipt invariants enforced at construction), vends the stock,
        teaches the learner, and books venue-side revenue."""
        q = make_quote(self.state, self.policy.policy_id,
                       seed=substream(self.master_seed, "q", self.world, day,
                                      tick, uid),
                       items=[QuoteItem(sku, qty, unit_price,
                                        self.catalog[sku].list_price)],
                       why=list(why), hour=hour_of(tick))
        self.state.take(sku, qty)
        if self.learner is not None:
            self.learner.sold(sku, qty)
        self.units_vended += qty
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + q.total
        return q

    def end_day(self) -> dict:
        """Expire lots (salvage), restock to par, close the learner's day.
        Returns vend's spoilage accounting; also books stocked units."""
        if self.learner is not None:
            # censoring-aware: a sold-out SKU's sales truncate its true
            # demand — the estimate may only rise on sellout days
            self.learner.end_day(frozenset(
                sku for sku in self.state.listings
                if self.state.stock(sku) == 0))
        live_before = sum(l.quantity for l in self.state.lots if l.quantity > 0)
        eod = end_of_day(self.state, master_seed=self.master_seed)
        live_after = sum(l.quantity for l in self.state.lots if l.quantity > 0)
        self.units_stocked += live_after - (live_before - eod["spoiled_units"])
        return eod


class BodegaVenue:
    """Posted-price venue with deep daily-restocked inventory. Identical in
    BOTH worlds for B0 — the bodega hasn't adopted SNHP yet (that's a later
    phase); here it anchors the block's outside option and picks up the
    machine's overflow. No deli-waste model yet (B0 treats bodega stock as
    non-perishable within the day; spoilage bins arrive with the render)."""

    name = "bodega"
    rent_per_day = calibration.BODEGA_RENT_PER_DAY
    PAR_PER_ITEM = 300    # "deep": ~3× the heaviest plausible single-item day

    def __init__(self, world: str):
        self.world = world
        self.prices = {item: price for item, price, _c in calibration.BODEGA_CATALOG}
        self.costs = {item: cost for item, _p, cost in calibration.BODEGA_CATALOG}
        self.stock = {item: self.PAR_PER_ITEM for item in self.prices}
        self.revenue_by_day: dict[int, float] = {}
        self.units_vended = 0
        self.units_stocked = sum(self.stock.values())

    def begin_day(self, day: int) -> None:
        for item in self.stock:
            need = self.PAR_PER_ITEM - self.stock[item]
            if need > 0:
                self.stock[item] += need
                self.units_stocked += need

    def price_board(self) -> dict[str, float]:
        return dict(self.prices)

    def stock_view(self) -> dict[str, int]:
        return dict(self.stock)

    def settle(self, item: str, qty: int, day: int) -> tuple[float, float]:
        """Sell qty of item; returns (spend, cogs). Validates stock before
        mutating (same discipline as MachineState.take)."""
        if self.stock.get(item, 0) < qty:
            raise ValueError(f"insufficient bodega stock for {item}")
        self.stock[item] -= qty
        spend = round(qty * self.prices[item], 2)
        self.units_vended += qty
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + spend
        return spend, qty * self.costs[item]

    def end_day(self) -> dict:
        return {"spoiled_units": 0, "spoilage_cost": 0.0}


def _regular_tick_weights() -> np.ndarray:
    """Habitual visit times for the machine's regulars: the block's own
    vending crowd curve, normalized (not vend's office-tower curve)."""
    w = np.array([expected_home_rate("vending", t) for t in range(TICKS_PER_DAY)],
                 dtype=float)
    return w / w.sum()


class BlockRegularPool(RegularPool):
    """vend's fairness pool (reference prices, sticker shock, churn,
    replenishment — all of vend/regulars.py verbatim) wearing NYC tastes:
    WTPs draw around the NYC vending μ's, visit times follow the block's
    machine crowd, and the market reference is the UN-anchored
    profit-optimal NYC sticker — what these goods 'usually cost' nearby."""

    def __init__(self, n: int, master_seed: int, catalog: dict[str, Listing]):
        self._tick_weights = _regular_tick_weights()   # before super() spawns
        market_ref = {sku: _profit_optimal_list_price(mu, cost)
                      for sku, mu, cost, *_ in calibration.VENDING_CATALOG}
        super().__init__(VendWorldConfig(regulars=n), master_seed, catalog,
                         market_ref)

    def _spawn(self, i: int) -> Regular:
        rng = np.random.default_rng(substream(self.seed, "regpool", i))
        home = int(rng.choice(TICKS_PER_DAY, p=self._tick_weights))
        mu = {sku: m for sku, m, *_ in calibration.VENDING_CATALOG}
        wtp = {s: float(rng.lognormal(np.log(mu[s]), WTP_SIGMA))
               for s in self.catalog}
        return Regular(uid=substream(self.seed, "reg", i), wtp=wtp,
                       walk_cost=float(rng.uniform(0.5, 2.0)),
                       visit_prob=float(rng.uniform(0.25, 0.75)),
                       home_tick=home, ref=dict(self.market_ref))
