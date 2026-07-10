"""Venue adapters — each sim wrapped onto the block clock.

B1/B2 ship all four venues:

  * VendingVenue — the vend/ machine verbatim (Listings, lots, nightly
    restock/spoilage, the Quote protocol with its type-enforced invariants),
    wearing the NYC catalog from block/calibration.py. Sticker world →
    StaticPolicy board; SNHP world → A2APolicy brokered Nash quotes
    (vend.scenario.nash_quote via the policy, library defaults, attested).
  * BodegaVenue — a posted-price venue with its own deep inventory at
    calibration.BODEGA_CATALOG prices. Non-adopter by default (B0,
    preserved): same posted board in BOTH worlds. With
    BlockConfig.bodega_adopts=True the SNHP world's bodega ALSO runs a
    brokered-quote arm over its own catalog (vend's A2APolicy pattern —
    Listings built from the posted prices, operator demand estimates, the
    machine's ACTUAL displayed prices as the outside option for overlapping
    goods: symmetric endogeneity). Discount-only off its own stickers.
  * BobaVenue (B1) — boba/'s world+policies on the block's 10-minute ticks,
    hours 10:00–22:00 inside the block day. Queue, barista-minutes,
    balking, and tapioca batches all live inside the venue (boba/world
    verbatim). Sticker world → StaticMenu; SNHP world → cart/1 Nash quotes
    (quote-before-balk; now-slot deals still face the walk-in balk roll).
  * FashionVenue (B2) — multi-timescale: fashion's WEEKLY season tick
    advances every 7 block days; season length =
    calibration.FASHION_SEASON_WEEKS; ONE buy at block day 0 (planned
    against the cliff calendar per fashion/world logic, with
    calibration.FASHION_LINES). Sticker world → the industry cliff
    calendar; SNHP world → markdown/1's weekly per-cell re-solve
    (discount-only, markdowns permanent). Sales book DAILY into the ledger
    (cogs recognized at sale — retail matching); the season-end salvage
    writedown books on the season's last day.

Layering rule (B0 hard requirement, unchanged): venues know their own
inventory, prices, and policy. They know NOTHING about the ledger — settles
return receipts and keep venue-side per-day revenue counters so the
ledger's event-side aggregates can be cross-checked for exact money
conservation. They also know nothing about consumers' identities beyond
what the protocol allows (disclosed WTP + walk cost).

Honesty notes on believed outside options: Listing.bodega_price on the
MACHINE is the ACTUAL bodega posted price for goods the bodega carries and
a ×1.15 phantom off the UN-anchored profit-optimal sticker otherwise; it
stays the POSTED bodega board even when the bodega adopts (the machine
cannot see brokered quotes). The adopted BODEGA's believed outside is the
machine's actual displayed list price for overlapping goods and a ×1.15
phantom (the deli around the corner) otherwise. Every engine's misbelief
can only cost ITS OWN venue a declined quote, never the buyer: the
CONSUMER's acceptance in the runner always uses the real block
alternatives.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from block import calibration
from boba import world as boba_world
from boba.policies import CartDeal, CartPolicy, StaticMenu
from fashion import world as fashion_world
from fashion.core import substream as fashion_substream
from block.population import (BOBA_CLOSE_TICK, BOBA_OPEN_TICK,
                              FASHION_APPEAL, FASHION_ATTENTION,
                              FASHION_SEASON_WEEKS, FASHION_W0_DAILY,
                              GOOD_MU, expected_home_rate,
                              fashion_cliff_mult)
from vend.core import Listing, MachineState, Lot, QuoteItem, make_quote, substream
from vend.policies import A2APolicy, StaticPolicy
from vend.regulars import Regular, RegularPool
from vend.scenario import NashQuote
from vend.world import (TICKS_PER_DAY, WTP_SIGMA, WorldConfig as VendWorldConfig,
                        _profit_optimal_list_price, end_of_day, fresh_machine,
                        hour_of)

NON_OVERLAP_OUTSIDE_MARKUP = 1.15   # vend.world.BODEGA_MARKUP, kept explicit


@dataclass(frozen=True)
class BlockConfig:
    """Block world knobs. sigma_cal defaults ON (0.15, the P1.5 grid's
    central cell): a competent NYC operator prices from finite history, not
    omniscience — this is also where much of the SNHP world's recovery
    margin lives. anchor_mult is the probe knob for the substitution and
    fairness tests (1.0 = the honest sticker). bodega_adopts=False
    preserves B0's non-adopter bodega (identical posted board in both
    worlds); True gives the SNHP world's bodega its own brokered-quote arm
    — the sticker world NEVER changes (asserted in tests)."""
    sigma_cal: float = 0.15
    anchor_mult: float = 1.0
    regulars: int = 0
    bodega_adopts: bool = False


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


def build_bodega_catalog(cfg: BlockConfig, master_seed: int,
                         vend_catalog: dict[str, Listing] | None
                         ) -> dict[str, Listing]:
    """The adopted bodega's protocol view of its own shelf. list_price = the
    POSTED calibration price (adoption adds a negotiation surface, it does
    NOT reprice the stickers — discount-only off the board customers see).
    wtp_mu_est = a sigma_cal-noised operator estimate of the good's WTP mean
    (its own substream — the bodega's calibration errors are independent of
    the machine's). bodega_price (the engine's believed OUTSIDE) = the
    machine's ACTUAL displayed list price where the machine carries the
    good (symmetric endogeneity), else a ×1.15 phantom (the deli around the
    corner). Non-perishable within the model: shelf life is effectively
    infinite, so c_eff is always unit cost."""
    cat: dict[str, Listing] = {}
    for item, price, cost in calibration.BODEGA_CATALOG:
        mu = GOOD_MU[item]
        if cfg.sigma_cal > 0:
            rng = np.random.default_rng(substream(master_seed, "bodega-cal", item))
            mu_est = float(mu * rng.lognormal(0.0, cfg.sigma_cal))
        else:
            mu_est = mu
        if vend_catalog is not None and item in vend_catalog:
            outside = vend_catalog[item].list_price
        else:
            outside = round(price * NON_OVERLAP_OUTSIDE_MARKUP, 2)
        cat[item] = Listing(sku=item, list_price=price, unit_cost=cost,
                            salvage=0.0, shelf_life_days=3650,
                            par_stock=BodegaVenue.PAR_PER_ITEM,
                            wtp_mu_est=mu_est, bodega_price=outside)
    return cat


class BodegaVenue:
    """Posted-price venue with deep daily-restocked inventory. Non-adopter
    by default (B0, preserved byte-for-byte): identical posted board in
    BOTH worlds; it anchors the block's outside option and picks up the
    machine's overflow. With cfg.bodega_adopts=True, the SNHP world's
    bodega ALSO quotes brokered Nash deals over its own catalog (vend's
    A2APolicy verbatim, attested, library min-gain buffer); the posted
    board stays exactly the calibration prices in every mode. No deli-waste
    model yet (stock non-perishable within the day)."""

    name = "bodega"
    rent_per_day = calibration.BODEGA_RENT_PER_DAY
    PAR_PER_ITEM = 300    # "deep": ~3× the heaviest plausible single-item day

    def __init__(self, world: str, cfg: BlockConfig | None = None,
                 master_seed: int = 0,
                 vend_catalog: dict[str, Listing] | None = None):
        self.world = world
        self.master_seed = master_seed
        self.prices = {item: price for item, price, _c in calibration.BODEGA_CATALOG}
        self.costs = {item: cost for item, _p, cost in calibration.BODEGA_CATALOG}
        self.adopted = bool(cfg is not None and cfg.bodega_adopts
                            and world == "snhp")
        if self.adopted:
            self.catalog = build_bodega_catalog(cfg, master_seed, vend_catalog)
            self.policy = A2APolicy()
            self.state = MachineState("block-bodega-snhp", self.catalog,
                                      lots=[])
            for item in self.prices:      # opening fill, like the dict path
                self.state.lots.append(Lot(sku=item, quantity=self.PAR_PER_ITEM,
                                           expires_day=3650))
            self._stock = None
        else:
            self.catalog = None
            self.policy = None
            self.state = None
            self._stock = {item: self.PAR_PER_ITEM for item in self.prices}
        self.revenue_by_day: dict[int, float] = {}
        self.units_vended = 0
        self.units_stocked = self.PAR_PER_ITEM * len(self.prices)

    @property
    def learner(self):
        return getattr(self.policy, "learner", None)

    def _stock_of(self, item: str) -> int:
        return (self.state.stock(item) if self.adopted
                else self._stock.get(item, 0))

    def begin_day(self, day: int) -> None:
        if self.adopted:
            self.state.day = day
            if self.learner is not None:
                self.learner.begin_day(1.0)      # no public calendar yet
            for item in self.prices:
                need = self.PAR_PER_ITEM - self.state.stock(item)
                if need > 0:
                    self.state.lots.append(Lot(sku=item, quantity=need,
                                               expires_day=day + 3650))
                    self.units_stocked += need
        else:
            for item in self._stock:
                need = self.PAR_PER_ITEM - self._stock[item]
                if need > 0:
                    self._stock[item] += need
                    self.units_stocked += need

    def observe_arrivals(self, tick: int, n: int) -> None:
        """Adopted only: feed the demand learner the bodega's own crowd
        (expected base = the block's analytic bodega-home curve)."""
        if self.learner is not None:
            self.learner.observe_arrivals(expected_home_rate("bodega", tick), n)

    def price_board(self) -> dict[str, float]:
        return dict(self.prices)

    def stock_view(self) -> dict[str, int]:
        return {item: self._stock_of(item) for item in self.prices}

    def quote(self, disclosed_wtp: dict[str, float],
              disclosed_walk: float) -> NashQuote | None:
        """Brokered Nash quote over the bodega's own catalog (adopted SNHP
        bodega only). `disclosed_walk` is the buyer's RELATIVE hassle of
        the MACHINE vs the bodega from where they stand — the mirror image
        of VendingVenue.quote: positive for a bodega-home shopper (the
        machine costs a walk), negative for a vending-home one."""
        if not self.adopted:
            return None
        shim = SimpleNamespace(wtp=disclosed_wtp, walk_cost=disclosed_walk, uid=0)
        nq, _lied = self.policy.quote_for(self.state, shim, 1.0)  # attested
        return nq

    def settle(self, item: str, qty: int, day: int) -> tuple[float, float]:
        """Sell qty at the POSTED price; returns (spend, cogs). Validates
        stock before mutating (same discipline as MachineState.take)."""
        if self._stock_of(item) < qty:
            raise ValueError(f"insufficient bodega stock for {item}")
        if self.adopted:
            self.state.take(item, qty)
            if self.learner is not None:
                self.learner.sold(item, qty)
        else:
            self._stock[item] -= qty
        spend = round(qty * self.prices[item], 2)
        self.units_vended += qty
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + spend
        return spend, qty * self.costs[item]

    def settle_quote(self, item: str, qty: int, unit_price: float,
                     why: list[str], day: int, tick: int, uid: int):
        """The negotiated sale path (adopted only): constructs a protocol
        Quote (discount-only vs the POSTED price and receipt invariants
        enforced at construction), takes stock, teaches the learner, and
        books venue-side revenue."""
        q = make_quote(self.state, self.policy.policy_id,
                       seed=substream(self.master_seed, "bq", self.world, day,
                                      tick, uid),
                       items=[QuoteItem(item, qty, unit_price,
                                        self.prices[item])],
                       why=list(why), hour=hour_of(tick))
        self.state.take(item, qty)
        if self.learner is not None:
            self.learner.sold(item, qty)
        self.units_vended += qty
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + q.total
        return q

    def end_day(self) -> dict:
        if self.learner is not None:
            self.learner.end_day(frozenset(
                item for item in self.prices if self._stock_of(item) == 0))
        return {"spoiled_units": 0, "spoilage_cost": 0.0}


class BobaVenue:
    """boba/'s shop on the block clock (B1). The queue, barista-minutes,
    balk physics, and tapioca batches are boba/world verbatim; only the
    clock is translated (block tick − 18 = boba tick; the two hour_of
    functions agree inside the 10:00–22:00 window). Sticker world posts
    the calibration menu (StaticMenu); SNHP world quotes negotiated carts
    (cart/1) with the sticker menu as fallback — never worse UX than
    static, enforced by the runner's acceptance gate.

    Venue-side conservation counters (cross-checked in tests): every cup is
    ORDERED (settled, revenue booked) then SERVED by the bar or left in the
    queue/schedule at close; every pearl serving is COOKED then TAKEN by an
    order or WASTED (batch expiry + the 22:00 wash-up)."""

    name = "boba"
    rent_per_day = calibration.BOBA_RENT_PER_DAY
    OPEN_TICK = BOBA_OPEN_TICK          # 18 → 10:00 on the block clock
    CLOSE_TICK = BOBA_CLOSE_TICK        # 90 → 22:00

    def __init__(self, world: str, master_seed: int):
        if world not in ("sticker", "snhp"):
            raise ValueError(f"unknown world {world!r}")
        self.world = world
        self.master_seed = master_seed
        self.policy = StaticMenu() if world == "sticker" else CartPolicy()
        self.state: boba_world.ShopState | None = None
        self.revenue_by_day: dict[int, float] = {}
        self.units_vended = 0            # cups ordered (settled)
        self.cups_served = 0             # cups actually made by the bar
        self.pearls_cooked = 0           # servings
        self.pearls_taken = 0
        self.pearls_wasted = 0
        self.ordered_by_day: dict[int, int] = {}
        self.served_by_day: dict[int, int] = {}
        self.leftover_by_day: dict[int, int] = {}   # unserved at close
        self._waste_cost = 0.0
        self._waste_units = 0
        self._day = -1

    def begin_day(self, day: int) -> None:
        """10:00 doors: fresh state, batch 1 cooked (boba/world.open_shop)."""
        self.state = boba_world.open_shop(day)
        self._waste_cost = 0.0
        self._waste_units = 0
        self._day = day

    def is_open(self, block_tick: int) -> bool:
        return self.OPEN_TICK <= block_tick < self.CLOSE_TICK

    def on_tick(self, block_tick: int) -> None:
        """One tick of shop physics, in boba/run's exact order: expire
        batches → operator's cook check → release due pickups → bar work.
        Runs BEFORE this tick's arrivals are resolved."""
        if not self.is_open(block_tick):
            return
        st = self.state
        st.tick = block_tick - self.OPEN_TICK
        before = st.pearl_stock()
        self._waste_cost += boba_world.expire_batches(st)
        expired = before - st.pearl_stock()
        self.pearls_wasted += expired
        self._waste_units += expired
        boba_world.maybe_cook(st)
        boba_world.release_scheduled(st)
        made = boba_world.serve_queue(st)
        self.cups_served += made
        self.served_by_day[self._day] = self.served_by_day.get(self._day, 0) + made

    def consumer_view(self, sh) -> boba_world.Consumer:
        """The block Shopper's boba tastes as a boba/world Consumer (the
        hourly WTP multiplier was applied at sample time, as boba does)."""
        return boba_world.Consumer(
            fav=sh.boba_fav,
            wtp={d: sh.wtp[d] for d in boba_world.DRINKS},
            top_wtp=dict(sh.top_wtp),
            flexible=sh.boba_flexible, qty_decay=sh.boba_decay, uid=sh.uid)

    def quote(self, consumer: boba_world.Consumer) -> CartDeal | None:
        """cart/1 Nash quote (SNHP world only — the sticker shop has no
        negotiation surface)."""
        if not isinstance(self.policy, CartPolicy):
            return None
        return self.policy.quote_for(self.state, consumer)

    def boards(self) -> tuple[dict[str, float], dict[str, float]]:
        return self.policy.boards(self.state)

    def settle(self, drink: str, qty: int, tops: tuple[str, ...],
               spend: float, slot_ticks: int, day: int) -> None:
        """Book a sale (boba/run._settle's physics): revenue at the settled
        spend, pearls reserved at ORDER time, drinks queued at their pickup
        slot (deferred slots clamp to the last open tick)."""
        st = self.state
        if "pearls" in tops:
            boba_world.take_pearls(st, qty)      # validates before mutating
            self.pearls_taken += qty
        if slot_ticks > 0:
            due = min(st.tick + slot_ticks, boba_world.TICKS_PER_DAY - 1)
            st.scheduled[due] = st.scheduled.get(due, 0) + qty
        else:
            st.queue.append(qty)
        self.units_vended += qty
        self.ordered_by_day[day] = self.ordered_by_day.get(day, 0) + qty
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + spend

    def end_day(self) -> dict:
        """22:00 wash-up: leftover pearls tossed (boba/world.close_out);
        whatever the bar didn't get to stays counted as leftover (revenue
        was booked at order — boba/run's convention, kept)."""
        st = self.state
        leftover = st.queue_drinks() + sum(st.scheduled.values())
        self.leftover_by_day[self._day] = leftover
        before = st.pearl_stock()
        self._waste_cost += boba_world.close_out(st)
        self.pearls_wasted += before
        self._waste_units += before
        self.pearls_cooked += st.batches_cooked * boba_world.BATCH_SERVINGS
        return {"spoiled_units": self._waste_units,
                "spoilage_cost": round(self._waste_cost, 2)}


# ── fashion (B2): weekly season inside the daily block ────────────────────

class BlockCliffPolicy:
    """The industry control on the block: MSRP for the first half of the
    season, then −30/−50/−70 on the compressed trade calendar
    (population.fashion_cliff_mult) — per style, uniform across sizes,
    blind to stock and demand."""
    policy_id = "cliff/1"

    def price_board(self, week: int, inv: dict, catalog: dict) -> dict:
        m = fashion_cliff_mult(week)
        return {cell: round(catalog[cell[0]].msrp * m, 2)
                for cell, s in inv.items() if s > 0}


class BlockMarkdownPolicy:
    """markdown/1 on the block: fashion/policies.MarkdownPolicy's exact
    solve (finite-horizon weekly re-price per style×size, min(D, s) stockout
    clamp, markdowns permanent, discount-only) with the BLOCK's demand
    curve — the derived fashion-lane arrival scale, weekly taper, uniform
    attention, fashion's size curve and season decay. Same honesty notes:
    fixed-price-resolve heuristic, myopic about waiters, no in-season
    learning (buy-time appeal estimate all season)."""
    policy_id = "markdown/1"
    N_GRID = 20

    def __init__(self):
        self._last: dict = {}            # markdowns are permanent

    def price_board(self, week: int, inv: dict, catalog: dict) -> dict:
        board = {}
        for (style, size), s in inv.items():
            if s <= 0:
                continue
            listing = catalog[style]
            p = self._solve(listing, size, week, s)
            p = min(p, self._last.get((style, size), listing.msrp))
            self._last[(style, size)] = p
            board[(style, size)] = p
        return board

    def _solve(self, listing, size: str, week: int, stock: int) -> float:
        import math as _math
        grid = np.linspace(listing.msrp, listing.salvage, self.N_GRID)
        weeks = np.arange(week, FASHION_SEASON_WEEKS)
        lam = (7.0 * FASHION_W0_DAILY * fashion_world.ARRIVAL_TAPER ** weeks
               * listing.attention * fashion_world.SIZE_SHARE[size])
        scale = listing.appeal_est * fashion_world.DECAY ** weeks
        z = np.log(grid[:, None] / scale[None, :]) / fashion_world.WTP_SIGMA
        from scipy.special import erfc
        sf = 0.5 * erfc(z / _math.sqrt(2.0))
        demand = (lam[None, :] * sf).sum(axis=1)
        sold = np.minimum(demand, float(stock))
        obj = grid * sold + listing.salvage * (stock - sold)
        return round(float(grid[int(np.argmax(obj))]), 2)


FASHION_SIGMA_BUY = 0.15     # fashion/world DEFAULT_CONFIG.sigma_buy


def build_fashion_plan(cfg: BlockConfig, master_seed: int
                       ) -> tuple[dict[str, fashion_world.Style],
                                  dict[tuple[str, str], int]]:
    """The boutique's season: catalog + ONE buy, drawn before any pricing
    decision exists and shared by BOTH worlds (the game is 'work the
    inventory you're stuck with', never 'buy better'). fashion/world's
    logic with the block's numbers: appeal = 0.90 × MSRP
    (population.FASHION_APPEAL); the operator's estimate is sigma_cal-noised
    (its own substream); landed cost straight from calibration.FASHION_LINES
    (not the COST_FRAC convention); salvage = calibration.FASHION_SALVAGE_FRAC
    × cost. The plan prices every arrival as a loyal-now buyer against the
    CLIFF calendar — exactly as naive as real open-to-buy plans."""
    catalog: dict[str, fashion_world.Style] = {}
    for style, msrp, cost in calibration.FASHION_LINES:
        appeal = FASHION_APPEAL[style]
        if cfg.sigma_cal > 0:
            rng = np.random.default_rng(
                fashion_substream(master_seed, "fash-cal", style))
            est = float(appeal * rng.lognormal(0.0, cfg.sigma_cal))
        else:
            est = appeal
        catalog[style] = fashion_world.Style(
            style=style, msrp=msrp, unit_cost=cost,
            salvage=round(calibration.FASHION_SALVAGE_FRAC * cost, 2),
            appeal=appeal, appeal_est=est, attention=FASHION_ATTENTION[style])

    depth: dict[tuple[str, str], int] = {}
    for style, listing in catalog.items():
        planned = sum(
            7.0 * FASHION_W0_DAILY * fashion_world.ARRIVAL_TAPER ** w
            * listing.attention
            * fashion_world.wtp_sf(listing.msrp * fashion_cliff_mult(w),
                                   listing.appeal_est
                                   * float(fashion_world.decay(w)))
            for w in range(FASHION_SEASON_WEEKS))
        for size in fashion_world.SIZES:
            rng = np.random.default_rng(
                fashion_substream(master_seed, "fash-buy", style, size))
            err = float(rng.lognormal(-FASHION_SIGMA_BUY ** 2 / 2,
                                      FASHION_SIGMA_BUY))
            depth[(style, size)] = max(
                0, int(round(planned * fashion_world.SIZE_SHARE[size] * err)))
    return catalog, depth


class FashionVenue:
    """The boutique on the block (B2), multi-timescale: the season week
    advances every 7 block days (week = day // 7, clamped to the season);
    prices re-solve at each week boundary and hold within the week; sales
    happen DAILY against the standing weekly board. ONE buy at block day 0,
    no restock ever.

    Ledger accounting (the documented B2 choice): weekly results AGGREGATE
    into the daily ledger — each sale books revenue and cogs (unit landed
    cost) on the day it happens (retail matching), and the season-end
    salvage writedown (cost − salvage per unsold unit) books as spoilage on
    the season's LAST day. Summed over a full season this reproduces
    fashion/'s gross margin exactly: revenue + salvage − buy cost. Runs
    shorter than a season therefore show fashion margin gross of the
    eventual clearance risk — flagged in RESULTS.

    Strategic waiters who decline join the venue's waiting list and
    re-decide at the NEXT week boundary (fashion/run's weekly returns on
    the block calendar); their walk-away/return divergence is earned
    per-world, which is why the pairing test excludes kind='return'."""

    name = "fashion"
    rent_per_day = calibration.FASHION_RENT_PER_DAY
    SEASON_WEEKS = FASHION_SEASON_WEEKS

    def __init__(self, world: str, cfg: BlockConfig, master_seed: int,
                 plan: tuple | None = None):
        if world not in ("sticker", "snhp"):
            raise ValueError(f"unknown world {world!r}")
        self.world = world
        self.catalog, depth = plan if plan is not None \
            else build_fashion_plan(cfg, master_seed)
        self.depth = dict(depth)
        self.inv = dict(depth)
        self.policy = BlockCliffPolicy() if world == "sticker" \
            else BlockMarkdownPolicy()
        self.board: dict[tuple[str, str], float] = {}
        self.week = -1
        self.waiting: list = []          # declined waiters, FIFO
        self.sold_prev = {cell: 0 for cell in depth}
        self._sold_this = {cell: 0 for cell in depth}
        self.revenue_by_day: dict[int, float] = {}
        self.units_vended = 0
        self.units_stocked = sum(depth.values())
        self.season_closed = False

    def begin_day(self, day: int) -> list:
        """Advance the block calendar; at a week boundary, re-solve the
        board (both policies), roll the sell-through observation window,
        and hand the runner the returning waiters. Returns [] mid-week."""
        w = min(day // 7, self.SEASON_WEEKS - 1)
        if w == self.week:
            return []
        self.week = w
        self.sold_prev = self._sold_this
        self._sold_this = {cell: 0 for cell in self.depth}
        self.board = self.policy.price_board(w, self.inv, self.catalog)
        for (style, _sz), p in self.board.items():
            if p > self.catalog[style].msrp + 1e-9:
                raise ValueError(f"discount-only violated: {style} at {p}")
        returning, self.waiting = self.waiting, []
        return returning

    def price(self, style: str, size: str) -> float | None:
        return self.board.get((style, size))

    def settle(self, style: str, size: str, day: int) -> tuple[float, float]:
        """Sell one unit at the standing weekly price; returns (spend, cogs).
        Validates stock before mutating."""
        cell = (style, size)
        if self.inv.get(cell, 0) <= 0:
            raise ValueError(f"insufficient fashion stock for {cell}")
        price = self.board[cell]
        self.inv[cell] -= 1
        self._sold_this[cell] += 1
        self.units_vended += 1
        self.revenue_by_day[day] = self.revenue_by_day.get(day, 0.0) + price
        return price, self.catalog[style].unit_cost

    def end_day(self, day: int) -> dict:
        """Season's last day: the unsold rack goes to the jobber — the
        writedown (cost − salvage per unit) books as spoilage, which makes
        the ledger's season total equal fashion/'s gross margin exactly."""
        if day == self.SEASON_WEEKS * 7 - 1 and not self.season_closed:
            self.season_closed = True
            units = sum(self.inv.values())
            cost = sum(n * (self.catalog[st].unit_cost - self.catalog[st].salvage)
                       for (st, _sz), n in self.inv.items())
            return {"spoiled_units": units, "spoilage_cost": round(cost, 2)}
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
