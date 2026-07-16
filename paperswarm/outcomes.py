"""Outcome tracker (SPEC.md Phase 1: "our OWN outcome tracker building the
sold-comp DB — no restricted APIs").

Re-polls tracked listings to terminal state (sold price / ended-unsold) and
writes realized comps. This is how we earn the right to mark inventory: marks
key off OUR observed sales, never off asks or a restricted sold-listings API.
Real-mode final-price observability via the Browse API is best-effort; when we
cannot observe a hammer we record UNSOLD/UNKNOWN rather than invent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .comps import Comps
from .feed import EbayFeed, Listing
from .identity import Identity, parse_identity
from .timeutil import iso, now_utc, parse_iso

STATUS_LIVE = "LIVE"
STATUS_SOLD = "SOLD"
STATUS_UNSOLD = "UNSOLD"


@dataclass(frozen=True)
class TerminalOutcome:
    listing_id: str
    status: str                 # LIVE | SOLD | UNSOLD
    hammer: float | None
    end_time: str | None

    @property
    def is_terminal(self) -> bool:
        return self.status in (STATUS_SOLD, STATUS_UNSOLD)


class OutcomeTracker:
    def __init__(self, feed: EbayFeed, comps: Comps):
        self.feed = feed
        self.comps = comps

    # -- observe a single listing's terminal state -------------------------
    def observe(self, listing: Listing, as_of: datetime | None = None) -> TerminalOutcome:
        """Return the listing's terminal state, or LIVE if not yet ended."""
        as_of = as_of or now_utc()

        if self.feed.fixture:
            outcomes = self.feed._load_fixture("outcomes.json")
            rec = outcomes.get(listing.listing_id)
            if not rec:
                return TerminalOutcome(listing.listing_id, STATUS_LIVE, None, None)
            return TerminalOutcome(
                listing.listing_id, rec["status"],
                rec.get("hammer"), rec.get("end_time"),
            )

        # Real mode: a listing is terminal once its close time has passed.
        if listing.close_time is None or as_of < listing.close_time:
            return TerminalOutcome(listing.listing_id, STATUS_LIVE, None, None)

        detail = self.feed.get_item(listing.listing_id)  # metered
        bid_count = detail.get("bidCount", listing.raw.get("bidCount", 0)) or 0
        price_obj = detail.get("currentBidPrice") or detail.get("price") or {}
        try:
            final_price = float(price_obj.get("value")) if price_obj.get("value") else None
        except (TypeError, ValueError):
            final_price = None
        end_time = detail.get("itemEndDate") or iso(listing.close_time)

        if bid_count and final_price:
            return TerminalOutcome(listing.listing_id, STATUS_SOLD, final_price, end_time)
        return TerminalOutcome(listing.listing_id, STATUS_UNSOLD, None, end_time)

    # -- record a terminal outcome as a comp -------------------------------
    def record(self, listing: Listing, identity: Identity,
               outcome: TerminalOutcome) -> bool:
        """Write a realized comp for a terminal, identified listing."""
        if not outcome.is_terminal or not identity.is_identified:
            return False
        return self.comps.record(
            card_name=identity.card_name, number=identity.number,
            grade=identity.grade, cert=identity.cert,
            listing_id=listing.listing_id, status=outcome.status,
            sold_price=outcome.hammer,
            sold_time=outcome.end_time or iso(now_utc()),
        )

    # -- sweep a batch ------------------------------------------------------
    def sweep(self, listings: list[Listing],
              as_of: datetime | None = None) -> list[TerminalOutcome]:
        """Observe + record terminal outcomes for a batch, building the comp DB.

        Returns every terminal outcome (for the fill engine to resolve open bids).
        """
        terminal: list[TerminalOutcome] = []
        for listing in listings:
            outcome = self.observe(listing, as_of)
            if not outcome.is_terminal:
                continue
            aspects = {}
            if self.feed.fixture:
                # Cheap: fixtures carry aspects; skip a metered detail call.
                detail = self.feed.get_item(listing.listing_id)
                aspects = EbayFeed.aspects_from_detail(detail)
            identity = parse_identity(listing.title, aspects)
            self.record(listing, identity, outcome)
            terminal.append(outcome)
        return terminal
