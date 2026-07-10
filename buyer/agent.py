"""BuyerAgent — the buyer as a first-class player (gap 1).

It has its own objective (true dollar surplus), its own identity (uid + Wallet),
and its own strategy space. Given true values and a set of Merchants, it chooses
a disclosure, decides whether to negotiate, shop, time, or commit, and
accepts/declines against its best walk-away option.

The disclosure battery and the fallback (walk-away) helper live here because
they are the buyer's primitives; frontier.py imports them to enumerate the
strategy space, and the agent imports frontier lazily (in `receipt`) so the two
don't form an import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from buyer.merchant import Disclosure, Intent, Merchant, Quote
from buyer.values import best_bundle, bundle_surplus


# ── the disclosure strategy space (the "liar battery", buyer-side) ──────────

# (name, wtp_factor, zero_walk). honest is the identity report. The rest are
# the strategic misreports vend's H3 anchoring exploit characterized: scale
# disclosed WTP, optionally claim a free outside option.
_BATTERY_SPEC: list[tuple[str, float, bool]] = [
    ("honest", 1.00, False),
    ("honest_freewalk", 1.00, True),
    ("under85", 0.85, False),
    ("under70", 0.70, False),
    ("under55", 0.55, False),
    ("under55_freewalk", 0.55, True),
    ("under40_freewalk", 0.40, True),
    ("over115", 1.15, False),
    ("over130", 1.30, False),
]


def disclosure_battery(true_wtp: dict[str, float], walk_cost: float, *,
                       attested: bool = False, reliability: float = 0.0
                       ) -> list[tuple[str, Disclosure]]:
    """All disclosures the buyer could send. Under `attested` the merchant only
    honors verified truth, so the battery collapses to the honest report —
    which is exactly why an attested mechanism can leave a truthful agent AT
    its frontier (no gaming strategy is available to anyone)."""
    out = []
    for name, factor, zero_walk in _BATTERY_SPEC:
        if attested and name != "honest":
            continue
        wtp = {s: v * factor for s, v in true_wtp.items()}
        out.append((name, Disclosure(wtp=wtp,
                                     walk_cost=0.0 if zero_walk else walk_cost,
                                     attested=attested, reliability=reliability)))
    return out


def fallback_surplus(true_wtp: dict[str, float], walk_cost: float,
                     merchants: list[Merchant]) -> tuple[float, str | None]:
    """The best surplus available with NO negotiation: buy at some merchant's
    sticker board, or walk to the ever-present competitor (−walk). Returns
    (surplus, merchant_id | None). This is the naive buyer's outcome and the
    floor of the frontier (declining always leaves it available)."""
    best_s, best_m = 0.0, None
    for m in merchants:
        board = m.board()
        prices = {s: b.list_price for s, b in board.items()}
        stock = {s: b.stock for s, b in board.items()}
        _, _, s = best_bundle(true_wtp, prices, stock)
        if s > best_s:
            best_s, best_m = s, m.merchant_id
    # the competitor (bodega): same across merchants in single-merchant runs.
    if merchants:
        _, _, s_out = best_bundle(true_wtp, merchants[0].outside_prices())
        s_out = max(0.0, s_out - walk_cost)
        if s_out > best_s:
            best_s, best_m = s_out, "outside"
    return best_s, best_m


@dataclass
class BuyerAgent:
    uid: int
    wtp: dict[str, float]          # TRUE per-unit willingness to pay
    walk_cost: float
    policy: str = "honest"         # disclosure policy name (a battery entry)
    friction: float = 0.0          # $ switch-cost to accept a negotiated quote
    wallet: object | None = None   # portable identity (Wallet), B4+

    # ── disclosure ──
    def disclose(self, name: str | None = None, *, attested: bool = False
                 ) -> Disclosure:
        name = name or self.policy
        spec = {n: (f, z) for n, f, z in _BATTERY_SPEC}
        factor, zero_walk = spec.get(name, (1.0, False))
        reliability = getattr(self.wallet, "reliability", 0.0) if self.wallet else 0.0
        return Disclosure(wtp={s: v * factor for s, v in self.wtp.items()},
                          walk_cost=0.0 if zero_walk else self.walk_cost,
                          attested=attested, reliability=reliability)

    # ── evaluation primitives (all in the buyer's true dollars) ──
    def true_surplus(self, quote: Quote | None) -> float:
        """Realized surplus of accepting `quote`, net of friction. −inf if
        there is nothing to accept."""
        if quote is None:
            return float("-inf")
        return bundle_surplus(self.wtp, quote.sku, quote.qty,
                              quote.unit_price) - self.friction

    def fallback(self, merchants: list[Merchant]) -> tuple[float, str | None]:
        return fallback_surplus(self.wtp, self.walk_cost, merchants)

    # ── B1 decision: disclose (per policy) at a single merchant, accept if it
    #    beats the walk-away. The agent NEVER accepts a quote worse than what
    #    it could get by walking — "never worse UX than the sticker" is a
    #    decision here, not an assumption. ──
    def negotiate(self, merchant: Merchant, *, attested: bool = False,
                  intent: Intent | None = None
                  ) -> tuple[Quote | None, float, str]:
        """Returns (accepted_quote_or_None, realized_surplus, strategy)."""
        fb, _ = self.fallback([merchant])
        q = merchant.quote(self.disclose(attested=attested), intent or Intent())
        s = self.true_surplus(q)
        if q is not None and s > fb:
            return q, s, self.policy
        return None, fb, "naive"

    def receipt(self, merchant: Merchant, *, attested: bool = False,
                day: int = 0, strategy_label: str | None = None):
        """Produce a ledger Receipt with the agent's realized surplus AND its
        regret against the single-merchant frontier. Lazy import of frontier
        breaks the agent<->frontier cycle."""
        from buyer.frontier import Receipt, single_merchant_frontier
        fr = single_merchant_frontier(self.wtp, self.walk_cost, merchant,
                                       friction=self.friction, attested=attested)
        q, realized, strat = self.negotiate(merchant, attested=attested)
        return Receipt(
            uid=self.uid, merchant_id=(q.merchant_id if q else None),
            strategy=strategy_label or strat,
            sku=(q.sku if q else None), qty=(q.qty if q else 0),
            unit_price=(q.unit_price if q else 0.0),
            list_price=(q.list_price if q else 0.0),
            realized_surplus=round(realized, 6),
            outside_surplus=round(fr.fallback, 6),
            frontier_surplus=round(fr.surplus, 6),
            regret=round(max(0.0, fr.surplus - realized), 6), day=day)
