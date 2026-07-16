"""MPX agents + the shared economic primitives (SPEC "Agents").

The utility/cost functions here are the SINGLE source of truth: the market
scores realized trades with them AND the auditor's oracle (audit.py) scores
counterfactual bundles with the SAME functions.  The auditor "knows the
buyer/supplier utility functions" (SPEC A1) precisely because they are these.

Agent policies are deterministic; the only randomness is the market's seeded
RNG, consumed in a fixed order (market.py).  The variant agents (Deceptive,
Stale) are honest-looking WITHIN MPX's message rules -- MPX cannot see the
difference (SPEC: "all within MPX's rules -- MPX simply cannot detect them").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# --- Economic primitives (auditor-known utility functions) ------------------


def unit_realized_value(unit_value: float, urgency: float, lateness: int) -> float:
    """Per-unit value after lateness decay (SPEC: urgency = value decay/tick
    late). Floored at 0 -- a very late unit is worthless, not negative."""
    return max(0.0, unit_value - urgency * max(0, lateness))


def buyer_gross_value(delivered_qty: float, need_qty: int, unit_value: float,
                      urgency: float, lateness: int,
                      residual_frac: float = 0.0) -> float:
    """Buyer's realized gross value for `delivered_qty` units against a need of
    `need_qty` at `lateness` ticks late.  Units up to need_qty are valued at the
    (decayed) unit value; units beyond the need are excess and worth only
    residual_frac of it (default 0 -- a double-buy has ~no marginal value; this
    is A3's harm channel)."""
    uv = unit_realized_value(unit_value, urgency, lateness)
    on_need = min(delivered_qty, need_qty)
    excess = max(0.0, delivered_qty - need_qty)
    return on_need * uv + excess * uv * residual_frac


def supplier_cost(qty: float, ship_date: int, c0: float, c1: float,
                  cap: float, expedite: float) -> float:
    """Supplier cost to make `qty` and hit `ship_date`.

    Base cost is convex in qty (c0 linear + c1 quadratic).  Promising a date
    faster than the natural lead (qty/cap) incurs an expedite surcharge
    proportional to how far it is pulled in.  This makes ship_date a REAL
    negotiable issue with a price tradeoff -- which is exactly what price-only
    MPX cannot express (A1)."""
    natural = qty / cap if cap > 0 else 0.0
    base = c0 * qty + c1 * qty * qty
    pull_in = max(0.0, natural - ship_date)
    return base + expedite * qty * pull_in


def joint_surplus(qty: float, ship_date: int, need_qty: int, need_by: int,
                  unit_value: float, urgency: float,
                  c0: float, c1: float, cap: float, expedite: float,
                  residual_frac: float = 0.0) -> float:
    """Total pie for a (qty, ship_date) contract -- PRICE CANCELS.  The oracle
    (A1) maximizes this over feasible (qty, ship_date); price only splits it."""
    lateness = max(0, ship_date - need_by)
    val = buyer_gross_value(qty, need_qty, unit_value, urgency, lateness,
                            residual_frac)
    cost = supplier_cost(qty, ship_date, c0, c1, cap, expedite)
    return val - cost


# --- Demand / supply data ---------------------------------------------------


@dataclass
class DemandLine:
    """One buyer need (SPEC: "demand schedule with per-item urgency")."""

    line_id: int
    item: str
    qty: int
    unit_value: float
    need_by: int          # lead ticks the buyer wants it within
    urgency: float        # value decay/unit/tick late
    release_tick: int     # tick the need becomes active
    chain_only: bool = False   # servable ONLY via a broker (A4)

    # mutable book-keeping (truth)
    committed: bool = False
    committed_tick: int = -1
    delivered_qty: float = 0.0
    fulfilled: bool = False
    last_rfq_tick: int = -10_000   # cooldown anchor (no per-tick RFQ spam)
    attempts: int = 0              # failed sourcing rounds
    dead: bool = False             # abandoned after too many failed rounds


@dataclass
class SupplierParams:
    c0: float
    c1: float
    cap: float            # ship capacity (units/tick)
    expedite: float
    inventory: float
    markup: float         # opening markup over cost
    min_markup: float     # walk-away floor markup


# --- Agents -----------------------------------------------------------------


@dataclass
class BuyerAgent:
    """Enterprise buyer (SPEC: budget, demand schedule, urgency)."""

    agent_id: str
    budget: float
    lines: list[DemandLine]
    lag: int = 0          # StaleBuyer: order-book belief lags `lag` ticks (A3)
    spent: float = 0.0

    # ---- belief of own order-book (StaleBuyer lags this) ----------------
    def line_is_open(self, line: DemandLine, tick: int) -> bool:
        """Should the buyer still be sourcing this line? Honest buyer sees the
        truth instantly; StaleBuyer's view of its OWN commitments lags `lag`
        ticks, so it re-orders lines it already committed (A3 double-buy)."""
        if tick < line.release_tick or line.dead:
            return False
        # A committed line is closed once the buyer BELIEVES it committed.
        if line.committed and line.committed_tick >= 0:
            if line.committed_tick <= tick - self.lag:
                return False   # belief has caught up -> line closed
            # else: within the lag window, buyer still believes it open
        return not line.fulfilled

    def believed_budget(self, tick: int, spend_log: list[tuple[int, float]]) -> float:
        """Remaining budget as the buyer BELIEVES it (StaleBuyer's spend view
        lags `lag` ticks -> it thinks it has money it already committed)."""
        if self.lag == 0:
            return self.budget - self.spent
        seen = sum(amt for (t, amt) in spend_log if t <= tick - self.lag)
        return self.budget - seen

    def reservation(self, quote_qty: int, quote_date: int, line: DemandLine) -> float:
        """Max total price the buyer will pay for the QUOTED bundle = the gross
        value it expects from those terms.  Urgency makes a late quoted date
        cheap to the buyer -- the seed of A1's foregone trades."""
        lateness = max(0, quote_date - line.need_by)
        # buyer scores against remaining unmet need on this line
        unmet = max(0, line.qty - int(line.delivered_qty))
        eff_need = unmet if unmet > 0 else line.qty
        return buyer_gross_value(quote_qty, eff_need, line.unit_value,
                                 line.urgency, lateness)


@dataclass
class SupplierAgent:
    """Supplier (SPEC: inventory, cost curve, ship capacity/tick).

    Deception is a knob, not a bug (A2). A DeceptiveSupplier looks identical in
    every MPX message; it simply, on a fraction `bad_prob` of orders (SPEC's
    "under-delivers at rate d"), ships `short_frac` less than promised and late,
    while keeping the full pay-on-accept.  On the other orders it performs
    honestly -- which is exactly why its public star mean lags reality."""

    agent_id: str
    items: list[str]
    params: SupplierParams
    deceptive: bool = False
    bad_prob: float = 0.0        # per-order probability of a shortfall (rate d)
    short_frac: float = 0.0      # fraction of qty withheld on a bad order
    revenue: float = 0.0
    realized_cost: float = 0.0

    def quote_terms(self, item: str, req_qty: int, need_by: int,
                    max_lot: int) -> Optional[tuple[int, int, float, float]]:
        """Naive-but-competent quote: sell as much as inventory/lot allow at the
        CHEAPEST-for-me ship date (natural lead, no expedite), priced at
        cost*(1+markup).  Returns (qty, ship_date, price, floor_price).

        The supplier ignores the buyer's urgency (it cannot see it and could not
        negotiate the date anyway) -- this is the structural A1 loss.  A
        DeceptiveSupplier overrides the PROMISED ship_date to look on-time while
        it will actually ship at the natural (later) lead and short the qty."""
        p = self.params
        qty = min(req_qty, int(p.inventory), max_lot)
        if qty <= 0:
            return None
        natural = math.ceil(qty / p.cap) if p.cap > 0 else 0
        promised = natural
        if self.deceptive:
            # overstate: claim it can hit the buyer's deadline (it cannot). It
            # does NOT charge an expedite premium for the fake date -- it prices
            # honestly on its natural cost and wins selection on the false
            # promise, so its ONLY edge is the under-delivery windfall (A2).
            promised = min(natural, need_by)
        cost = supplier_cost(qty, natural, p.c0, p.c1, p.cap, p.expedite)
        price = cost * (1.0 + p.markup)
        floor = cost * (1.0 + p.min_markup)
        return qty, promised, price, floor

    def actual_delivery(self, qty: int, promised_date: int,
                        roll: float) -> tuple[float, int]:
        """What ACTUALLY ships (truth). Honest = full qty at the natural lead.
        Deceptive: on a `bad_prob` fraction of orders (drawn by the market's
        seeded RNG -> `roll`) it withholds `short_frac` of the qty and slips to
        the natural (later) lead; otherwise it performs normally.  Either way it
        already banked the full price on accept -- that windfall on the bad
        orders is the ONLY channel by which it out-earns an honest peer."""
        p = self.params
        natural = math.ceil(qty / p.cap) if p.cap > 0 else 0
        if not self.deceptive:
            return float(qty), natural
        if roll < self.bad_prob:
            return qty * (1.0 - self.short_frac), max(promised_date, natural)
        return float(qty), natural


@dataclass
class BrokerAgent:
    """Two-hop intermediary, NO inventory (SPEC: BrokerAgent). Quotes the buyer,
    then sources from a supplier AFTER the buyer has committed -- MPX has no
    pre-commitment, so the broker is exposed to spot moves/hold-up (A4)."""

    agent_id: str
    items: list[str]
    markup: float
    handling: int                 # extra ship ticks the broker adds
    est_unit_cost: float          # broker's ex-ante estimate of upstream cost

    def quote_terms(self, req_qty: int, need_by: int,
                    max_lot: int) -> tuple[int, int, float, float]:
        """Quote the buyer off an ESTIMATE of upstream cost (it has not sourced
        yet). ship_date = deadline + handling."""
        qty = min(req_qty, max_lot)
        est_cost = self.est_unit_cost * qty
        price = est_cost * (1.0 + self.markup)
        ship_date = need_by + self.handling
        floor = est_cost * 1.0     # broker will not knowingly quote below est cost
        return qty, ship_date, price, floor
