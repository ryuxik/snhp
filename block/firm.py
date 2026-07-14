"""A procure→hold→resell FIRM on the block's two-sided SNHP rail.

THE SHARP QUESTION
------------------
Does an SNHP-priced *two-sided* rail let a firm run a business that is
impossible on sticker pricing? We add ONE new actor to the block — a firm
that PROCURES perishable stock from a venue, HOLDS it (carrying + spoilage
cost), and RESELLS it to a slice of the crowd, with its own P&L — and
characterize what business, if any, develops.

The firm is a THIN actor over the real primitives, never a re-derivation:
  * it BUYS by calling the venue's own `quote(disclosed_wtp, walk)` path as a
    disclosed-WTP buyer, then `settle(...)` (block/venues.py::VendingVenue).
    Near-expiry stock is priced cheap by the venue's SALVAGE channel
    (`vend.scenario.c_eff` → salvage when a lot dies tonight); under STICKER
    the board is fixed at list, so there is no cheap-buy path at all.
  * it RESELLS by pricing its inventory through the SAME Nash engine
    (`vend.scenario.nash_quote`), acting as a mini-SNHP-shop with the lever:
    discount-only off its own list, never above it, price-sensitive buyers
    self-select onto discounts.
  * every buy and sell is `record()`ed into the shared BlockLedger, so money
    conservation holds ACROSS the firm (block/ledger.py). The firm is booked
    as its own ledger "venue", so its P&L is `day_metrics(...,'firm',...)`
    margin — no bespoke accounting.

WHY A WASTE REGIME HAS TO BE MADE EXPLICIT (read this before trusting a number)
------------------------------------------------------------------------------
At the block's shipped calibration the vending venue's perishables are
SUPPLY-CONSTRAINED (demand > the 6-unit par, so they sell out): there is
ZERO near-expiry salvage stock for any firm to arbitrage. Worse, under SNHP
the venue's negotiation clears even a 6x overstock to its OWN street crowd
(deep discounts down to salvage) — zero waste survives to the firm. Waste
only survives where the venue's crowd ISN'T: fresh stock overstocked for the
weekday lunch crowd and stranded on a dead (office-tower) weekend.

So the firm's INPUT (near-expiry salvage stock) is not a given — it is a
consequence of a waste regime we introduce EXPLICITLY and SWEEP, applied
byte-identically to both worlds and every arm:
  * 1-day shelf life on the fresh SKUs (prepared food: made today, gone
    tomorrow — the block's 2-day sandwich never reaches its own expiry with
    stock, because earliest-lot-first depletion clears it);
  * `overstock` — a perishable par multiplier (fresh retail overstocks to
    avoid stockouts / keep shelves full: a documented driver of 30-40%
    fresh-category waste);
  * `dow` — the office-tower weekday/weekend arrival pattern (vend.world
    DOW_RATE), thinning the vending crowd so weekend fresh stock strands.
At (overstock=1, dow=off) this reproduces the shipped no-waste world, where
the firm makes ~$0 by construction — the null anchor. The headline result is
firm value AS A FUNCTION OF realized waste and of the reach gap, never a
single tuned number.

Determinism: every draw keys on `substream(seed, ...)`; the firm is off by
default (the base block loop is never touched — this module runs its own
vending-only twin so no committed artifact can move).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from block import population
from block.ledger import BlockLedger
from block.runner import build_world
from block.venues import BlockConfig, build_block_catalog
from vend.core import Listing, Lot, MachineState, substream
from vend.scenario import c_eff, nash_quote
from vend.world import QTY_CAP, TICKS_PER_DAY, DOW_RATE, bundle_value

# the two fresh SKUs on the block's vending catalog (the only clean
# quote+salvage perishable path the shipped block exposes)
FRESH_SKUS = ("sandwich", "fruit-cup")
FRESH_SHELF_LIFE = 1          # prepared food: made today, gone tomorrow
FIRM_BUYER_UID = -777         # sentinel uid for the firm at the venue's counter
PROCURE_TICK = TICKS_PER_DAY - 1   # end of day, when demand ahead ≈ 0 (excess)


# ══════════════════════════════════════════════════════════════════════════
# The firm's policy space (an optimizing PARAMETER SWEEP, not an LLM).
# ══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class FirmPolicy:
    """One firm strategy. The four named presets below are swept over their
    free parameters for maximum firm profit (block/firm_experiment.py)."""
    name: str
    # PROCURE: disclosed reservation value = frac × venue list (truthful: the
    # firm won't pay more than it can resell for). Must clear the venue's
    # min-gain buffer or the venue refuses to sell (no lowballing below cost+).
    procure_wtp_frac: float = 0.65
    # only buy stock the venue itself prices at salvage (expiring tonight AND
    # in shadow-excess) — waste by the venue's OWN assessment. False lets the
    # scarcity speculator also buy non-expiring excess (arbitrage).
    procure_expiring_only: bool = True
    max_units_per_day: int = 60        # capital/throughput cap
    # RESELL: firm list = cost basis × (1 + markup), capped at the venue list
    # (discount-only vs the origin, too). The lever discounts from there.
    resale_markup: float = 0.35
    resale_buffer_frac: float = 0.0    # firm's own min-gain (of firm list)
    seller_weight: float = 0.5
    # HOLD: 0 = resell same day (perishable spoils tonight). >0 = carry (the
    # scarcity speculator); each held unit-day pays `carry_cost_frac` × cost.
    hold_days: int = 0
    carry_cost_frac: float = 0.02


POLICIES: dict[str, FirmPolicy | None] = {
    # the baseline: no firm at all (the venues-sell-direct world).
    "none": None,
    # buy cheap, resell immediately at a small markup to whoever clears.
    "passthrough": FirmPolicy("passthrough", procure_wtp_frac=0.65,
                              resale_markup=0.15, hold_days=0),
    # buy the expiring fresh basket, resell a combined cheap basket to the
    # price-sensitive crowd the venue's own foot traffic doesn't include.
    "waste_aggregator": FirmPolicy("waste_aggregator", procure_wtp_frac=0.70,
                                   resale_markup=0.40, hold_days=0),
    # buy non-expiring excess when it's cheap/slow, hold, sell into scarcity.
    "scarcity_speculator": FirmPolicy("scarcity_speculator",
                                      procure_wtp_frac=0.60,
                                      procure_expiring_only=False,
                                      resale_markup=0.30, hold_days=2),
}


# ══════════════════════════════════════════════════════════════════════════
# The reach-gapped bargain crowd — the firm's resale outlet.
# ══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class BargainConfig:
    """The price-sensitive crowd the firm resells to. Present in BOTH worlds
    and EVERY arm (deterministic from the seed); the only thing that changes
    is whether the firm can serve them. `venue_reach` is the walk cost of
    getting to the venue itself (the office lobby) — the REACH GAP: high →
    the venue can't serve them directly and a middleman is the only channel;
    0 → the venue disintermediates the firm. This is the KILL-B axis."""
    per_day: int = 40
    wtp_frac_mu: float = 0.62      # mean WTP as a fraction of the venue mu
    wtp_sigma: float = 0.30
    venue_reach: float = 6.0       # $ hassle to reach the venue directly
    firm_reach: float = 0.5        # $ hassle to reach the firm's stall


@dataclass
class BargainBuyer:
    uid: int
    wtp: dict[str, float]          # over the fresh SKUs only
    venue_reach: float
    firm_reach: float


def bargain_crowd(seed: int, day: int, bcfg: BargainConfig,
                  catalog: dict[str, Listing]) -> list[BargainBuyer]:
    """Deterministic daily bargain buyers (paired across worlds by
    construction — no world/policy parameter enters)."""
    out: list[BargainBuyer] = []
    for k in range(bcfg.per_day):
        rng = np.random.default_rng(substream(seed, "bargain", day, k))
        wtp = {sku: float(rng.lognormal(
                   np.log(catalog[sku].wtp_mu_est * bcfg.wtp_frac_mu),
                   bcfg.wtp_sigma))
               for sku in FRESH_SKUS}
        out.append(BargainBuyer(uid=substream(seed, "bargain-uid", day, k),
                                wtp=wtp, venue_reach=bcfg.venue_reach,
                                firm_reach=bcfg.firm_reach))
    return out


# ══════════════════════════════════════════════════════════════════════════
# The firm.
# ══════════════════════════════════════════════════════════════════════════
@dataclass
class FirmLot:
    sku: str
    qty: int
    unit_cost: float          # the firm's cost basis (what it PAID the venue)
    expiry_day: int           # the unit dies at end of this day
    was_expiring: bool        # bought at the venue's salvage floor (would-be waste)


class Firm:
    """capital + per-good inventory (carrying + spoilage cost) + a daily
    policy. Booked as the ledger 'venue' `firm`, so its P&L is that venue's
    margin. Tracks the honest profit decomposition alongside."""

    RENT_PER_DAY = 0.0        # a market stall; a pilot would set an overhead

    def __init__(self, policy: FirmPolicy, capital: float = 1e9):
        self.policy = policy
        self.capital = capital
        self.inv: dict[str, list[FirmLot]] = {s: [] for s in FRESH_SKUS}
        # cash-flow accumulators (the conservation identity operands)
        self.procurement_spend = 0.0     # $ paid to venues (cash out)
        self.resale_revenue = 0.0        # $ from bargain buyers (cash in)
        self.cogs_sold = 0.0             # cost basis of units resold (FIFO)
        self.spoil_loss = 0.0            # cost basis of units spoiled held
        self.writeoff_loss = 0.0         # cost basis of units unsold at run end
        self.carry_cost = 0.0            # carrying-cost flow charged
        # decomposition accumulators (firm GROSS margin, by unit provenance)
        self.waste_units_sold = 0        # resold units bought at salvage floor
        self.arb_units_sold = 0          # resold units bought above salvage
        self.waste_margin = 0.0          # Σ (resale − cost) on waste units
        self.arb_margin = 0.0            # Σ (resale − cost) on arb units
        self.social_waste_cleared = 0.0  # Σ (resale − salvage) on waste units
        self.units_procured = 0
        self.units_resold = 0

    # ── inventory helpers ────────────────────────────────────────────────
    def stock(self, sku: str) -> int:
        return sum(l.qty for l in self.inv[sku])

    def _front_cost(self, sku: str) -> float:
        for l in self.inv[sku]:
            if l.qty > 0:
                return l.unit_cost
        return 0.0

    def _take_fifo(self, sku: str, n: int) -> tuple[float, int, float]:
        """Remove n units FIFO. Returns (total cost basis, waste units among
        them, salvage total of the waste units)."""
        cost = 0.0
        waste = 0
        salvage_tot = 0.0
        left = n
        for l in self.inv[sku]:
            if left <= 0:
                break
            take = min(l.qty, left)
            l.qty -= take
            left -= take
            cost += take * l.unit_cost
            if l.was_expiring:
                waste += take
        self.inv[sku] = [l for l in self.inv[sku] if l.qty > 0]
        return cost, waste, salvage_tot

    # ── (1) PROCURE ──────────────────────────────────────────────────────
    def procure(self, world: str, vend_v, ledger: BlockLedger, day: int) -> None:
        """Buy stock from the venue via its OWN quote path, as a disclosed-WTP
        buyer. Under SNHP the salvage channel prices near-expiry excess cheap;
        under STICKER there is no quote path (board fixed at list) so nothing
        below list is ever buyable — the whole asymmetry."""
        pol = self.policy
        vend_v.state.tick = PROCURE_TICK
        bought_today = 0
        for sku in FRESH_SKUS:
            lp = vend_v.catalog[sku].list_price
            disclosed_val = pol.procure_wtp_frac * lp
            # loop: each quote yields ≤ QTY_CAP units; repeat until the venue
            # stops offering below the firm's reservation (excess exhausted or
            # remaining stock is not-yet-expiring → floored at full cost).
            for _ in range(pol.max_units_per_day):
                if bought_today >= pol.max_units_per_day:
                    break
                stk = vend_v.state.stock(sku)
                if stk <= 0:
                    break
                dte = vend_v.state.days_to_expiry(sku)
                expiring = dte is not None and dte <= 0
                if pol.procure_expiring_only and not expiring:
                    break
                ce = c_eff(vend_v.state, sku)   # salvage iff expiring, else cost
                if world == "snhp":
                    disc = {s: 0.0 for s in vend_v.catalog}
                    disc[sku] = disclosed_val
                    nq = vend_v.quote(disc, 999.0)     # firm has no outside
                    if nq is None or nq.outcome is None or nq.outcome.sku != sku:
                        break
                    unit_price = nq.outcome.unit_price
                    qty = nq.outcome.qty
                    why = nq.why
                elif world == "sticker_clear":
                    # KILL-A robustness: the STRONGEST sticker baseline. A real
                    # sticker operator liquidates leftover stock rather than eat
                    # the loss — a flat closing-time clearance at the venue's
                    # own floor (salvage if expiring, else unit cost): the
                    # CHEAPEST plausible clearance, so the MOST favorable to the
                    # firm. Note SNHP's Nash split makes the firm pay ABOVE this
                    # floor (it splits surplus with the venue), so if the firm
                    # earns as much or more here, its business is created by a
                    # clearance channel and SNHP if anything TAXES it → KILL A.
                    unit_price = round(ce, 2)          # the venue's cost floor
                    qty = min(QTY_CAP, stk)
                    why = ["closing clearance"]
                else:
                    # STICKER: the only "quote" is the fixed board. The firm
                    # would pay list — never below its resale reservation, so
                    # a rational firm buys nothing. Enforce that explicitly.
                    unit_price = lp
                    qty = min(QTY_CAP, stk)
                    why = ["list price"]
                    if unit_price >= disclosed_val:
                        break
                # a rational firm never pays above its own reservation value,
                # and never at/above list (no resale margin there).
                if unit_price >= disclosed_val or unit_price >= lp:
                    break
                qty = min(qty, pol.max_units_per_day - bought_today)
                if qty <= 0:
                    break
                spend = round(qty * unit_price, 2)
                if spend > self.capital:
                    break
                q = vend_v.settle(sku, qty, unit_price, why, day,
                                  PROCURE_TICK, FIRM_BUYER_UID)
                # book the venue side (keeps vending conservation exact) and
                # the firm's cash out.
                ledger.record({"type": "venue_entered", "venue": "vending",
                               "world": world, "day": day, "tick": PROCURE_TICK,
                               "uid": FIRM_BUYER_UID, "persona": "firm",
                               "kind": "firm", "home": "vending"})
                ledger.record({"type": "deal", "venue": "vending", "world": world,
                               "day": day, "tick": PROCURE_TICK,
                               "uid": FIRM_BUYER_UID, "persona": "firm",
                               "kind": "firm", "home": "vending", "sku": sku,
                               "qty": qty, "unit_price": unit_price,
                               "spend": q.total,
                               "cogs": qty * vend_v.catalog[sku].unit_cost,
                               "surplus": 0.0, "raw_surplus": 0.0, "walk": 0.0,
                               "negotiated": world == "snhp", "buyer": "firm"})
                self.capital -= q.total
                self.procurement_spend += q.total
                self.units_procured += qty
                bought_today += qty
                # expiring fresh units die tonight; non-expiring carry to their
                # own expiry (dte days out).
                exp_day = day if expiring else day + (dte or 1)
                self.inv[sku].append(FirmLot(sku=sku, qty=qty,
                                             unit_cost=round(q.total / qty, 6),
                                             expiry_day=exp_day,
                                             was_expiring=bool(expiring)))

    # ── (3) RESELL — the firm as a mini-SNHP-shop ────────────────────────
    def _resale_quote(self, sku: str, buyer: BargainBuyer, vend_v):
        """Price one resale via the SAME Nash engine. Returns
        (qty, unit_price, buyer_surplus_net_reach) or None."""
        stk = self.stock(sku)
        if stk <= 0:
            return None
        cost_basis = self._front_cost(sku)
        lp_venue = vend_v.catalog[sku].list_price
        resale_list = round(min(lp_venue, cost_basis * (1.0 + self.policy.resale_markup)), 2)
        if resale_list <= cost_basis + 1e-9:
            return None
        lst = Listing(sku=sku, list_price=resale_list, unit_cost=cost_basis,
                      salvage=cost_basis, shelf_life_days=9999, par_stock=stk,
                      wtp_mu_est=vend_v.catalog[sku].wtp_mu_est,
                      bodega_price=lp_venue)    # buyer's outside = the venue list
        st = MachineState(f"firm-{sku}", {sku: lst},
                          lots=[Lot(sku=sku, quantity=stk, expires_day=9999)],
                          day=0, tick=0)
        # no internal outside: the buyer's REAL alternative (the venue direct)
        # is handled by the channel choice in _resolve_bargain, so the firm
        # prices against the disclosed WTP alone (walk=∞ ⇒ outside surplus 0).
        nq = nash_quote(st, {sku: buyer.wtp[sku]}, 999.0,
                        daily_fn=lambda s: 0.0,   # excess = full stock → clears to cost
                        min_gain=0.0,
                        min_gain_frac=self.policy.resale_buffer_frac,
                        seller_weight=self.policy.seller_weight)
        if nq.outcome is None:
            return None
        o = nq.outcome
        val = bundle_value(buyer.wtp, o.sku, o.qty)
        surplus = val - o.qty * o.unit_price - buyer.firm_reach
        if surplus <= 1e-9:
            return None
        return o.qty, o.unit_price, surplus

    def sell(self, world: str, sku: str, qty: int, unit_price: float,
             surplus: float, buyer: BargainBuyer, ledger: BlockLedger,
             day: int) -> None:
        cost, waste_units, _ = self._take_fifo(sku, qty)
        spend = round(qty * unit_price, 2)
        self.resale_revenue += spend
        self.capital += spend
        self.cogs_sold += cost
        self.units_resold += qty
        margin = spend - cost
        if waste_units > 0:
            self.waste_units_sold += waste_units
            # attribute margin pro-rata to the waste units in this line
            self.waste_margin += margin * (waste_units / qty)
            self.arb_margin += margin * ((qty - waste_units) / qty)
            self.arb_units_sold += (qty - waste_units)
            self.social_waste_cleared += sum(
                unit_price - vend_v_salvage(sku) for _ in range(waste_units))
        else:
            self.arb_units_sold += qty
            self.arb_margin += margin
        ledger.record({"type": "deal", "venue": "firm", "world": world,
                       "day": day, "tick": PROCURE_TICK, "uid": buyer.uid,
                       "persona": "bargain", "kind": "bargain", "home": "firm",
                       "sku": sku, "qty": qty, "unit_price": unit_price,
                       "spend": spend, "cogs": round(cost, 6),
                       "surplus": surplus, "raw_surplus": surplus, "walk": 0.0,
                       "negotiated": True, "buyer": "bargain"})

    # ── (2) HOLD / spoil / carry ─────────────────────────────────────────
    def close_day(self, world: str, ledger: BlockLedger, day: int) -> None:
        """Spoil expired lots (real loss), charge carrying cost on what's held
        over, and close the firm's ledger day."""
        spoil = 0.0
        for sku in FRESH_SKUS:
            keep = []
            for l in self.inv[sku]:
                if l.expiry_day <= day:
                    spoil += l.qty * l.unit_cost      # full loss (no salvage)
                    self.spoil_loss += l.qty * l.unit_cost
                else:
                    keep.append(l)
            self.inv[sku] = keep
        carry = 0.0
        for sku in FRESH_SKUS:
            for l in self.inv[sku]:
                c = l.qty * l.unit_cost * self.policy.carry_cost_frac
                carry += c
                self.carry_cost += c
        ledger.close_day(world, "firm", day,
                         spoiled_units=0,
                         spoilage_cost=round(spoil + carry, 6))

    def writeoff(self, world: str, ledger: BlockLedger, last_day: int) -> None:
        """Run end: any unsold inventory is a dead perishable — write it off
        so the firm's realized profit is conservative and the conservation
        identity closes exactly."""
        loss = 0.0
        for sku in FRESH_SKUS:
            for l in self.inv[sku]:
                loss += l.qty * l.unit_cost
                self.writeoff_loss += l.qty * l.unit_cost
            self.inv[sku] = []
        if loss > 0:
            # fold into the last day's firm spoilage line
            ledger.close_day(world, "firm", last_day,
                             spoiled_units=0, spoilage_cost=round(loss, 6))

    # ── conservation + decomposition ─────────────────────────────────────
    def profit(self, days: int) -> float:
        return round(self.resale_revenue - self.cogs_sold - self.spoil_loss
                     - self.writeoff_loss - self.carry_cost
                     - self.RENT_PER_DAY * days, 6)

    def conservation_residual(self) -> float:
        """procurement cash out == cost basis recovered on sales + cost basis
        lost to spoilage/writeoff. Nonzero ⇒ money created/destroyed inside
        the firm (KILL C)."""
        return round(self.procurement_spend
                     - (self.cogs_sold + self.spoil_loss + self.writeoff_loss), 6)

    def decomposition_residual(self) -> float:
        """firm gross margin == waste margin + arbitrage margin (exact)."""
        gross = round(self.resale_revenue - self.cogs_sold, 6)
        return round(gross - (self.waste_margin + self.arb_margin), 6)


# a tiny free function so `sell` can reach the venue salvage without holding a
# venue reference on the firm (kept stateless-ish for determinism)
_SALVAGE: dict[str, float] = {}


def vend_v_salvage(sku: str) -> float:
    return _SALVAGE.get(sku, 0.0)


# ══════════════════════════════════════════════════════════════════════════
# The paired twin day loop (vending-only, self-contained — never touches the
# committed multi-venue runner).
# ══════════════════════════════════════════════════════════════════════════
def _fresh_catalog(cfg: BlockConfig, seed: int, overstock: float
                   ) -> dict[str, Listing]:
    """The block vending catalog with the fresh SKUs made 1-day and
    overstocked by `overstock`× (both applied identically in both worlds)."""
    cat = build_block_catalog(cfg, seed)
    for sku in FRESH_SKUS:
        l = cat[sku]
        cat[sku] = Listing(sku=l.sku, list_price=l.list_price,
                           unit_cost=l.unit_cost, salvage=l.salvage,
                           shelf_life_days=FRESH_SHELF_LIFE,
                           par_stock=max(1, int(round(l.par_stock * overstock))),
                           wtp_mu_est=l.wtp_mu_est, bodega_price=l.bodega_price)
    return cat


def _retain(seed: int, day: int, uid: int, retain: float) -> bool:
    if retain >= 1.0:
        return True
    return np.random.default_rng(substream(seed, "retain", day, uid)).random() < retain


@dataclass(frozen=True)
class FirmRunConfig:
    days: int = 56
    seed: int = 20260710
    overstock: float = 4.0
    dow: bool = True
    bargain: BargainConfig = field(default_factory=BargainConfig)


def _resolve_bargain(world: str, buyer: BargainBuyer, vend_v, firm: Firm | None,
                     ledger: BlockLedger, day: int) -> None:
    """One bargain buyer picks the best available channel: the venue direct
    (paying venue_reach) or the firm's stall (paying firm_reach). In the
    firm-off arm only the venue-direct option exists — the disintermediation
    baseline the firm must beat (KILL B)."""
    from block.runner import _settle_vending
    vend_v.state.tick = PROCURE_TICK
    base = {"world": world, "day": day, "tick": PROCURE_TICK, "uid": buyer.uid,
            "persona": "bargain", "kind": "bargain"}
    ledger.record({"type": "arrival", "home": "bargain", **base})

    # venue-direct option
    v_choice = None
    if world == "snhp":
        disc = {s: buyer.wtp.get(s, 0.0) for s in vend_v.catalog}
        nq = vend_v.quote(disc, buyer.venue_reach)
        if nq is not None and nq.outcome is not None:
            o = nq.outcome
            raw = bundle_value(buyer.wtp, o.sku, o.qty) - o.qty * o.unit_price
            u = raw - buyer.venue_reach
            if u > 1e-9:
                v_choice = (u, o.sku, o.qty, o.unit_price, nq.why, raw)
    else:
        prices = {s: p for s, (p, _w) in vend_v.price_board().items()}
        stock = {s: vend_v.state.stock(s) for s in prices}
        from vend.world import best_bundle
        wtp_full = {s: buyer.wtp.get(s, 0.0) for s in vend_v.catalog}
        sku, qty, raw = best_bundle(wtp_full, prices, stock)
        if sku is not None:
            u = raw - buyer.venue_reach
            if u > 1e-9:
                v_choice = (u, sku, qty, prices[sku],
                            vend_v.price_board()[sku][1], raw)

    # firm option
    f_choice = None
    if firm is not None:
        for sku in FRESH_SKUS:
            q = firm._resale_quote(sku, buyer, vend_v)
            if q is not None:
                qty, unit_price, surplus = q
                if f_choice is None or surplus > f_choice[0]:
                    f_choice = (surplus, sku, qty, unit_price)

    best = "none"
    if v_choice is not None and (f_choice is None or v_choice[0] >= f_choice[0]):
        best = "venue"
    elif f_choice is not None:
        best = "firm"

    if best == "venue":
        u, sku, qty, unit_price, why, raw = v_choice
        _settle_vending(vend_v, ledger, base, sku, qty, unit_price, why,
                        u, raw, buyer.venue_reach, negotiated=(world == "snhp"))
    elif best == "firm":
        surplus, sku, qty, unit_price = f_choice
        ledger.record({"type": "venue_entered", "venue": "firm", **base})
        firm.sell(world, sku, qty, unit_price, surplus, buyer, ledger, day)
    else:
        ledger.record({"type": "no_sale", "reason": "unserved", **base})


def run_firm_world(world: str, ledger: BlockLedger, rcfg: FirmRunConfig,
                   cfg: BlockConfig, catalog: dict[str, Listing],
                   policy: FirmPolicy | None) -> Firm | None:
    """One world's vending-only day loop with the firm plugged in. Reuses the
    real VendingVenue (via build_world) and the Nash engine; the firm is a
    thin actor over them."""
    seed = rcfg.seed
    # sticker_clear rides the plain sticker venue (StaticPolicy board); only
    # the firm's PROCUREMENT path differs (a flat clearance vs the fixed board).
    base_world = "sticker" if world == "sticker_clear" else world
    st = build_world(base_world, seed, cfg, venues=("vending",), catalog=catalog)
    vend_v = st.vend_v
    for sku in FRESH_SKUS:
        _SALVAGE[sku] = vend_v.catalog[sku].salvage
    firm = Firm(policy) if policy is not None else None

    for day in range(rcfg.days):
        retain = DOW_RATE[day % 7] if rcfg.dow else 1.0
        vend_v.begin_day(day)
        stream = population.day_stream(seed, day)
        for tick in range(TICKS_PER_DAY):
            vend_v.state.tick = tick
            kept = [s for s in stream[tick]
                    if s.home == "vending" and _retain(seed, day, s.uid, retain)]
            vend_v.observe_arrivals(tick, len(kept))
            for sh in kept:
                from block.runner import _resolve_shopper
                _resolve_shopper(world, sh, vend_v, None, ledger, day, tick)
        # end of day: the firm procures the stranded near-expiry excess, THEN
        # the bargain crowd chooses its channel, THEN the venue salvages the
        # rest.
        if firm is not None:
            firm.procure(world, vend_v, ledger, day)
        for buyer in bargain_crowd(seed, day, rcfg.bargain, vend_v.catalog):
            _resolve_bargain(world, buyer, vend_v, firm, ledger, day)
        if firm is not None:
            firm.close_day(world, ledger, day)
        eod = vend_v.end_day()
        ledger.close_day(world, "vending", day,
                         eod["spoiled_units"], eod["spoilage_cost"])
    if firm is not None:
        firm.writeoff(world, ledger, rcfg.days - 1)
    return firm


def run_firm_twin(rcfg: FirmRunConfig, policy: FirmPolicy | None,
                  worlds: tuple[str, ...] = ("sticker", "snhp")
                  ) -> tuple[BlockLedger, dict[str, Firm | None]]:
    """Run each world on the IDENTICAL population + identical bargain crowd,
    with the same firm policy. Returns (ledger, {world: firm}). Worlds:
    "sticker" (fixed board), "snhp" (negotiation), "sticker_clear" (fixed
    board + a flat near-expiry clearance channel for the firm — the KILL-A
    robustness baseline)."""
    cfg = BlockConfig(sigma_cal=0.0)
    catalog = _fresh_catalog(cfg, rcfg.seed, rcfg.overstock)
    rents = {"vending": 0.0, "firm": Firm.RENT_PER_DAY}
    ledger = BlockLedger(rents=rents)
    firms = {}
    for world in worlds:
        firms[world] = run_firm_world(world, ledger, rcfg, cfg, catalog, policy)
    return ledger, firms
