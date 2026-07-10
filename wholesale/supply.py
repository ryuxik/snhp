"""The SUPPLY side as the MIRROR of the buyer's-agent subsystem (task #64, S1).

The binding insight: a venue's procurement is a `BuyerAgent` where the VENUE is
the buyer and a SUPPLIER is the `Merchant`. buyer/ was built merchant-agnostic
(it talks ONLY to the `Merchant` protocol), so a supplier is just another
Merchant — one that sells *cases* with route / window / terms / spoilage
structure instead of snacks. This module REUSES the buyer machinery; it does not
reimplement shop / commit / coordinate / frontier / regret.

Two adapters, exactly mirroring buyer/merchant.py's VendMerchant/ToyMerchant:

  * `SupplierMerchant`  wraps one wholesale (wholesaler, venue) relationship at a
                        (seed, week, flex, noise). Its `quote()` runs the REAL
                        multi-issue engine — wholesale.scenario.nash_deal over
                        price × window × case-size × terms × spoilage against the
                        event-consistent disagreement — and maps the Deal onto a
                        buyer.merchant.Quote. It reproduces wholesale/'s own
                        numbers to the cent (test_supply.py).
  * `ProcurementAgent`  is `BuyerAgent` with the venue as buyer: honest (attested)
                        forecast disclosure, accept the Nash deal iff it beats
                        the venue's no-deal EVENT (rate-card order or the Jetro
                        cash-and-carry run). Because the forecast is verifiable at
                        settlement, the supply interface is ATTESTED BY
                        CONSTRUCTION — the disclosure frontier collapses to
                        honesty and procurement regret is 0, exactly the buyer's
                        attested-frontier result one tier down.

The value-model mismatch (why the Quote carries u_buyer/d_buyer): the consumer's
value is buyer.values.bundle_value (linear-with-decay); a venue's value is a
NEWSVENDOR (R·E[min(q,D)] + salvage·overage − financing − receiving labor). So
the SupplierMerchant computes the venue-side utility internally and carries it on
the Quote (u_buyer = deal.u_v, d_buyer = deal.d_v) — the same trick the buyer
Quote already uses for the merchant side (u_machine). The `Supplier` protocol
extends `Merchant` with `no_deal_surplus()` (the venue's disagreement event
value) because a newsvendor fallback is not a linear-bundle walk-away.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from buyer.agent import BuyerAgent
from buyer.merchant import BoardItem, Disclosure, Intent, Merchant, Quote

from wholesale import calibration as cal
from wholesale.scenario import (Deal, Disagreement, RelCtx, build_ctx,
                                disagreement, nash_deal)
from wholesale.world import (Schedule, WeekDemand, substream, week_demand,
                             window_label)


# ── the supply interface: Merchant + the venue's newsvendor fallback ────────

@runtime_checkable
class Supplier(Merchant, Protocol):
    """A Merchant whose buyer is a venue. Adds ONE method to the protocol: the
    venue's no-deal event value (its best rate-card order or Jetro run), because
    a venue's fallback is a newsvendor optimization, not a linear-bundle
    walk-away. Everything else is the plain Merchant surface the buyer agent
    already speaks."""
    def no_deal_surplus(self) -> float: ...


# ── SupplierMerchant: the wholesale adapter (mirror of VendMerchant) ────────

class SupplierMerchant:
    """Wraps ONE (wholesaler, venue) relationship-week. Route density is a
    SHARED `Schedule` per wholesaler (the block's second cross-venue
    coordination market, mirroring the resident cluster): the same object is
    handed to every venue a wholesaler serves, so a stop booked for one venue is
    a cheap drop for the next. `coordinate=False` is the H-W3 ablation (each
    window priced as a fresh stop)."""

    def __init__(self, wholesaler: str, venue: str, ctx: RelCtx,
                 env: WeekDemand, schedule: Schedule, *,
                 coordinate: bool = True, fix: dict | None = None):
        self.merchant_id = f"{wholesaler}"          # the supplier
        self.wholesaler = wholesaler
        self.venue = venue
        self.sku = f"{wholesaler}-case"             # the composite supplier case
        self._ctx = ctx
        self._env = env
        self._sch = schedule
        self._coordinate = coordinate
        self._fix = fix
        # computed lazily on the first quote (needs the CURRENT schedule state)
        self._dis: Disagreement | None = None
        self.last_deal: Deal | None = None

    @classmethod
    def from_wholesale(cls, wholesaler: str, venue: str, *, seed: int, week: int,
                       flex: float = cal.BASE_FLEX, noise: float = cal.BASE_NOISE,
                       schedule: Schedule | None = None, coordinate: bool = True,
                       fix: dict | None = None) -> "SupplierMerchant":
        ctx = build_ctx(wholesaler, venue, flex)
        env = week_demand(seed, week, wholesaler, venue, noise)
        return cls(wholesaler, venue, ctx, env, schedule or Schedule(),
                   coordinate=coordinate, fix=fix)

    # ── the Merchant protocol ──
    def board(self) -> dict[str, BoardItem]:
        """The sticker: the published rate-card base price, MOQ..cap of stock."""
        return {self.sku: BoardItem(list_price=self._ctx.base,
                                    stock=self._ctx.cap)}

    def outside_prices(self) -> dict[str, float]:
        """The venue's ever-present competitor: Jetro cash-and-carry (x0.93 of
        the base, no breaks, own haul)."""
        return {self.sku: round(cal.JETRO_PRICE_FRAC * self._ctx.base, 2)}

    def salvage_floor(self, sku: str) -> float:
        """The supplier's participation floor: its marginal cost of goods per
        case (the disagreement-point that stops a buying club extracting below
        it — the procurement monopsony guardrail)."""
        return self._ctx.cogs

    def _disagreement(self) -> Disagreement:
        if self._dis is None:
            self._dis = disagreement(self._ctx, self._env, self._sch,
                                     coordinate=self._coordinate)
        return self._dis

    def no_deal_surplus(self) -> float:
        """The venue's no-deal EVENT value (rate-card order or Jetro run) — the
        fallback the procurement agent grades an offer against."""
        return self._disagreement().d_v

    def quote(self, disclosure: Disclosure, intent: Intent) -> Quote | None:
        """Run the real multi-issue Nash bundle and map the Deal → Quote. The
        disclosure is honest by construction (attested supply interface); its
        wtp is carried for protocol conformance but the venue's value lives in
        the calibrated RelCtx (ctx.R) — the wholesale engine's own input."""
        dis = self._disagreement()
        deal = nash_deal(self._ctx, self._env, self._sch, dis,
                         coordinate=self._coordinate, fix=self._fix)
        self.last_deal = deal
        if deal is None:
            return None
        why = ("negotiated procurement", window_label(deal.window),
               f"{deal.qty} cases @ ${deal.unit_price:.2f}", deal.terms)
        return Quote(merchant_id=self.merchant_id, sku=self.sku, qty=deal.qty,
                     unit_price=deal.unit_price,
                     list_price=float(self._ctx.break_price(deal.qty)),
                     why=why, d_machine=deal.d_w, u_machine=deal.u_w,
                     salvage_floor=self._ctx.cogs,
                     u_buyer=deal.u_v, d_buyer=deal.d_v)

    def settle(self, quote: Quote) -> None:
        """Book the delivery onto the SHARED truck schedule (route density)."""
        if self.last_deal is not None:
            self._sch.add(self.venue, self.last_deal.window)

    def settle_no_deal(self) -> str:
        """Execute the no-deal EVENT: a rate-card order still rides the truck (it
        books its FCFS window); a Jetro run / no-buy touches no stop. Returns the
        event name. Mirrors wholesale.run.run_week's fallback branch."""
        dis = self._disagreement()
        if dis.event == "ratecard":
            self._sch.add(self.venue, dis.window)
        return dis.event


# ── ProcurementAgent: BuyerAgent with the venue as buyer (mirror) ───────────

@dataclass
class ProcurementAgent(BuyerAgent):
    """`BuyerAgent` retargeted: the buyer is a VENUE, the merchants are its
    SUPPLIERS. Overrides the two value primitives (true_surplus / fallback)
    because the venue's value is a newsvendor carried on the Quote (u_buyer),
    not the consumer's linear bundle. disclose() and the identity/wallet plumbing
    are inherited verbatim — the agent still only speaks the Merchant surface
    (plus the supply interface's no_deal_surplus)."""

    def true_surplus(self, quote: Quote | None) -> float:
        """The venue's realized utility of accepting `quote` (its newsvendor
        value net of financing/receiving), carried on the Quote by the adapter.
        −inf if there is nothing to accept."""
        if quote is None:
            return float("-inf")
        return quote.u_buyer - self.friction

    def fallback(self, merchants: list) -> tuple[float, str | None]:
        """The best no-deal event across the queried suppliers (rate-card /
        Jetro). Suppliers expose it via no_deal_surplus()."""
        best_s, best_m = 0.0, None
        for m in merchants:
            s = m.no_deal_surplus() if hasattr(m, "no_deal_surplus") else 0.0
            if s > best_s:
                best_s, best_m = s, m.merchant_id
        return best_s, best_m

    def negotiate(self, merchant, *, attested: bool = True, intent=None):
        """Disclose (honest, attested), accept the Nash deal iff it beats the
        venue's no-deal event, else fall back to that event — the venue is NEVER
        worse off than its rate-card / Jetro option (the mirror of the buyer's
        'never worse than the sticker' guarantee)."""
        fb = merchant.no_deal_surplus() if hasattr(merchant, "no_deal_surplus") \
            else self.fallback([merchant])[0]
        q = merchant.quote(self.disclose(attested=attested), intent or Intent())
        s = self.true_surplus(q)
        if q is not None and s >= fb - 1e-9:
            return q, s, "nego"
        return None, fb, "no_deal"

    def receipt(self, *args, **kwargs):
        """GUARD the inherited BuyerAgent.receipt(): it grades regret via
        single_merchant_frontier → bundle_surplus (the CONSUMER linear-decay
        value model) applied to CASE quantities — silently wrong for a venue's
        newsvendor value (which lives on the Quote as u_buyer). Procurement uses
        procurement_frontier / procurement_regret instead, so the wrong path is
        made loud rather than returning garbage."""
        raise NotImplementedError(
            "use procurement_frontier/procurement_regret for procurement agents")


def procurement_agent(venue: str, suppliers: list[SupplierMerchant], *,
                      friction: float = 0.0, uid: int | None = None
                      ) -> ProcurementAgent:
    """Build a venue's procurement agent: its per-case value (wtp) is the
    calibrated attributable retail value R of each supplier's case."""
    wtp = {s.sku: s._ctx.R for s in suppliers}
    return ProcurementAgent(uid=uid if uid is not None
                            else substream("procuid", venue) % 10**8,
                            wtp=wtp, walk_cost=0.0, policy="honest",
                            friction=friction)


# ── procurement frontier + regret (mirror of buyer/frontier.py) ─────────────

@dataclass(frozen=True)
class ProcFrontier:
    surplus: float          # max venue utility over the (attested) strategy space
    fallback: float         # the no-deal event value (frontier floor)
    strategy: str


def procurement_frontier(agent: ProcurementAgent, supplier: SupplierMerchant
                         ) -> ProcFrontier:
    """Max venue utility over the disclosure space at one supplier. The supply
    interface is ATTESTED (the forecast is verified at settlement), so the space
    collapses to the honest report — exactly the buyer's attested frontier. The
    frontier is therefore max(honest Nash deal, no-deal event); realized == it,
    so procurement regret is 0 by construction (asserted in tests)."""
    fb = supplier.no_deal_surplus()
    q = supplier.quote(agent.disclose(attested=True), Intent())
    deal_u = agent.true_surplus(q) if q is not None else float("-inf")
    best = max(fb, deal_u if deal_u != float("-inf") else fb)
    return ProcFrontier(surplus=round(best, 6), fallback=round(fb, 6),
                        strategy="nego" if deal_u >= fb else "no_deal")


def procurement_regret(frontier: ProcFrontier, realized: float) -> float:
    """frontier − realized, floored at 0 (>= 0 by construction)."""
    return round(max(0.0, frontier.surplus - realized), 6)
