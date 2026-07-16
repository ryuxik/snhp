"""Arm B skeleton — swarm with fixed assignment, no internal market (SPEC.md
Arms: "B (swarm, fixed assignment)"). Deterministic; pricing never touches an
LLM (SPEC: "No LLM 'vibes' prices").

  * Scout   : search -> LEADS (listing + identity + close time).
  * Pricer  : fair value = median trailing comps; max bid = fair_value *
              margin_requirement (a demanded margin of safety).
  * Treasury: bankroll / exposure caps / one bid per listing (in fills.py).

Cold-start (SPEC Phase 1): refuse bids until the comp store spans >=7 days.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from . import config
from .comps import Comps
from .feed import EbayFeed, Listing
from .fills import BidRejected, FillEngine
from .identity import Identity, parse_identity
from .timeutil import now_utc


@dataclass(frozen=True)
class Lead:
    listing: Listing
    identity: Identity
    comp_key: str


@dataclass(frozen=True)
class Quote:
    comp_key: str
    n_comps: int
    fair_value: float     # median trailing realized comps
    max_bid: float        # fair_value * margin_requirement


@dataclass(frozen=True)
class Decision:
    listing_id: str
    action: str           # "bid" | "skip"
    reason: str
    max_bid: float | None = None
    fair_value: float | None = None
    n_comps: int = 0


class Scout:
    """Per-niche searcher: produces auction LEADS with parsed identity."""

    def __init__(self, feed: EbayFeed):
        self.feed = feed

    def scout(self, query: str | None = None) -> list[Lead]:
        """Search -> auction leads we can identify (SPEC scout role)."""
        leads: list[Lead] = []
        for listing in self.feed.search(query):
            if not listing.is_auction:
                continue  # phase-1 fills are auction-only
            identity = parse_identity(listing.title)
            if not identity.is_identified:
                # Try one metered detail fetch for structured aspects.
                aspects = EbayFeed.aspects_from_detail(self.feed.get_item(listing.listing_id))
                identity = parse_identity(listing.title, aspects)
            if identity.comp_key:
                leads.append(Lead(listing, identity, identity.comp_key))
        return leads


class Pricer:
    """Comp-model fair value -> max bid. Deterministic, auditable (SPEC)."""

    def __init__(self, comps: Comps, cfg: config.PricerConfig | None = None):
        self.comps = comps
        self.cfg = cfg or config.DEFAULT_PRICER

    def price(self, comp_key: str, as_of: datetime | None = None) -> Quote | None:
        """Fair value = median trailing realized comps; None if too thin.

        max_bid = fair_value * margin_requirement (SPEC swarm Pricer).
        """
        as_of = as_of or now_utc()
        prices = self.comps.realized_prices(comp_key, as_of, self.cfg.comp_window_days)
        if len(prices) < self.cfg.min_comps:
            return None
        fair_value = statistics.median(prices)
        max_bid = round(fair_value * self.cfg.margin_requirement, 2)
        return Quote(comp_key, len(prices), round(fair_value, 2), max_bid)


class Desk:
    """Arm B desk: scout -> price -> treasury-gated commit, with cold-start."""

    def __init__(self, feed: EbayFeed, comps: Comps, engine: FillEngine,
                 cfg: config.RuntimeConfig | None = None):
        self.cfg = cfg or config.DEFAULT
        self.feed = feed
        self.comps = comps
        self.engine = engine
        self.scout = Scout(feed)
        self.pricer = Pricer(comps, self.cfg.pricer)

    def cold_started(self) -> bool:
        """True once the comp store spans >= cold_start_days (SPEC Phase 1)."""
        return self.comps.store_span_days() >= self.cfg.cold_start_days

    def decide(self, as_of: datetime | None = None,
               cold_start_override: bool = False) -> list[Decision]:
        """One decision cycle: commit bids the protocol permits.

        Refuses ALL bids until cold-start clears (test override provided).
        Every accepted bid becomes a hash-chained bid_commit receipt.
        """
        as_of = as_of or now_utc()

        if not (cold_start_override or self.cold_started()):
            span = round(self.comps.store_span_days(), 2)
            self.engine.led.note({
                "kind": "cold_start_refusal",
                "store_span_days": span,
                "required_days": self.cfg.cold_start_days,
                "as_of": as_of.isoformat(),
            })
            return [Decision("*", "skip",
                             f"cold_start: store spans {span}d < {self.cfg.cold_start_days}d")]

        decisions: list[Decision] = []
        for lead in self.scout.scout():
            quote = self.pricer.price(lead.comp_key, as_of)
            if quote is None:
                decisions.append(Decision(lead.listing.listing_id, "skip",
                                          "thin_comps", n_comps=0))
                continue
            try:
                self.engine.commit_bid(
                    lead.listing, quote.max_bid,
                    comp_key=lead.comp_key, commit_time=as_of,
                    arm="B", fair_value=quote.fair_value,
                )
                decisions.append(Decision(
                    lead.listing.listing_id, "bid", "committed",
                    max_bid=quote.max_bid, fair_value=quote.fair_value,
                    n_comps=quote.n_comps,
                ))
            except BidRejected as exc:
                decisions.append(Decision(
                    lead.listing.listing_id, "skip", exc.reason,
                    max_bid=quote.max_bid, fair_value=quote.fair_value,
                    n_comps=quote.n_comps,
                ))
        return decisions
