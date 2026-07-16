"""MPX v1 message types + negotiation state machine (SPEC "MPX v1").

The protocol is the *only* place message rules live: agents supply policy
(what price to counter, what qty/date to quote) but cannot break the MESSAGE
RULES here. The two rules the audit turns on are enforced structurally:

  1. COUNTER carries a price and NOTHING else -- qty/ship_date are
     take-it-or-leave-it (SPEC: "price ONLY -- qty/ship_date are
     take-it-or-leave-it").  A caller literally cannot express a qty/date
     counter; there is no field for it.  This is A1's mechanism.
  2. At most 3 buyer COUNTERs per session (SPEC: "COUNTER(price') x<=3
     rounds").  The state machine raises after the 3rd.

Settlement is OPTIMISTIC: payment transfers on ACCEPT, delivery happens
ship_date ticks later and MAY arrive late/short (SPEC).  The protocol models
the message flow; the market (market.py) executes the money/goods.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class ProtocolError(RuntimeError):
    """Illegal MPX transition (a caller tried to break a MESSAGE RULE)."""


MAX_COUNTERS = 3  # SPEC: COUNTER x<=3 rounds


class State(enum.Enum):
    """Negotiation-session lifecycle (SPEC message flow)."""

    QUOTED = "quoted"        # supplier QUOTE on the table
    COUNTERED = "countered"  # >=1 buyer COUNTER exchanged, still open
    ACCEPTED = "accepted"    # price agreed; payment due on accept (optimistic)
    SETTLED = "settled"      # payment transferred (market did the money)
    DELIVERED = "delivered"  # goods arrived (possibly late/short)
    RATED = "rated"          # buyer left stars
    FAILED = "failed"        # walked away / expired, no trade


# --- Messages ---------------------------------------------------------------
# Frozen so a logged message can never be mutated after the fact (audit-grade).


@dataclass(frozen=True)
class RFQ:
    """Buyer request for quote (SPEC: RFQ(buyer, item, qty, need_by))."""

    rfq_id: int
    buyer_id: str
    item: str
    qty: int
    need_by: int          # lead ticks from rfq_tick the buyer wants it within
    rfq_tick: int
    unit_value: float     # buyer's private value/unit (auditor-known, not sent)
    urgency: float        # value decay/unit per tick late (private)
    budget_left: float    # buyer's own belief of remaining budget (private)


@dataclass(frozen=True)
class Quote:
    """Supplier offer (SPEC: QUOTE(supplier, price, qty, ship_date, expires)).

    qty and ship_date are TAKE-IT-OR-LEAVE-IT: they never change after this
    message.  Only `price` is negotiable, via Counter.
    """

    quote_id: int
    rfq_id: int
    supplier_id: str
    price: float          # total price for the whole quoted qty
    qty: int              # take-it-or-leave-it
    ship_date: int        # PROMISED lead ticks to delivery (take-it-or-leave-it)
    expires: int          # absolute tick after which the quote is dead
    is_broker: bool = False


@dataclass(frozen=True)
class Counter:
    """Buyer counter -- PRICE ONLY (SPEC). There is deliberately no qty/date
    field: the protocol makes a bundle counter inexpressible."""

    price: float


@dataclass(frozen=True)
class Rating:
    """Self-reported stars, 1-5, public running mean per supplier (SPEC)."""

    supplier_id: str
    stars: int
    rfq_id: int


@dataclass
class Session:
    """One buyer<->supplier negotiation over one Quote. Enforces the MESSAGE
    RULES; the agreed terms it exposes are what the market then settles.

    Invariant: qty and ship_date are fixed to the Quote for the whole session.
    Only `standing_price` moves, and only through counter()/concede()/accept.
    """

    quote: Quote
    rfq: RFQ
    state: State = State.QUOTED
    counters: int = 0                      # buyer counters used (<= MAX_COUNTERS)
    standing_price: float = field(init=False)
    agreed_price: Optional[float] = None

    def __post_init__(self) -> None:
        self.standing_price = self.quote.price

    # -- buyer moves -------------------------------------------------------
    def counter(self, msg: Counter) -> None:
        """Buyer proposes a new PRICE. Enforces the <=3 round cap. The new ask
        becomes the standing price the supplier may accept or concede against."""
        if self.state not in (State.QUOTED, State.COUNTERED):
            raise ProtocolError(f"counter illegal in {self.state}")
        if self.counters >= MAX_COUNTERS:
            raise ProtocolError("counter cap exceeded (MPX allows <=3)")
        if not isinstance(msg, Counter):
            raise ProtocolError("counter payload is not price-only")
        self.counters += 1
        self.standing_price = float(msg.price)
        self.state = State.COUNTERED

    def accept(self) -> None:
        """Buyer accepts the standing price -> ACCEPTED (payment now due)."""
        if self.state not in (State.QUOTED, State.COUNTERED):
            raise ProtocolError(f"accept illegal in {self.state}")
        self.agreed_price = self.standing_price
        self.state = State.ACCEPTED

    def walk(self) -> None:
        """Buyer (or expiry) ends the session with no trade."""
        if self.state in (State.SETTLED, State.DELIVERED, State.RATED):
            raise ProtocolError(f"walk illegal in {self.state}")
        self.state = State.FAILED

    # -- supplier move -----------------------------------------------------
    def concede(self, new_price: float) -> None:
        """Supplier answers a counter with a new take-it-or-leave-it price
        (still price-only). Does not consume a buyer round."""
        if self.state != State.COUNTERED:
            raise ProtocolError(f"concede illegal in {self.state}")
        self.standing_price = float(new_price)

    # -- market moves (money/goods) ---------------------------------------
    def settle(self) -> None:
        if self.state != State.ACCEPTED:
            raise ProtocolError(f"settle illegal in {self.state}")
        self.state = State.SETTLED

    def deliver(self) -> None:
        if self.state != State.SETTLED:
            raise ProtocolError(f"deliver illegal in {self.state}")
        self.state = State.DELIVERED

    def rate(self) -> None:
        if self.state != State.DELIVERED:
            raise ProtocolError(f"rate illegal in {self.state}")
        self.state = State.RATED

    @property
    def counters_remaining(self) -> int:
        return MAX_COUNTERS - self.counters
