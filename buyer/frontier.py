"""buyer_frontier + regret — the metric that is missing everywhere (gap 2).

For sellers we compute the Pareto frontier and "dollars left on the table." The
buyer has had no such number. Define it:

  buyer_frontier = max, over the buyer's whole strategy space S, of the buyer's
                   REALIZED true-dollar surplus, holding the merchants' fixed
                   mechanisms and the buyer's true values/alternatives constant.
  buyer regret   = buyer_frontier − realized surplus.

S = {disclosure policy} × {which merchants to query} × {accept now / wait k}
    × {commit y/n}. Every enumerated point is a strategy the buyer's agent
COULD have played, so realized <= frontier and regret >= 0 by construction
(tested). The honest test: is a TRUTHFUL agent near this frontier under our
mechanism (low regret ⇒ a real buyer's tool), or far below it (high regret ⇒
the "buyer surplus" we report is mostly the seller conceding, and the frontier
is only reachable by gaming)? We report both the unrestricted frontier (the
liar battery is in S) and the attested frontier (S collapses to honesty).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from buyer.agent import disclosure_battery, fallback_surplus
from buyer.ledger import Receipt   # re-exported for agent.receipt
from buyer.merchant import Intent, Merchant
from buyer.values import bundle_surplus

__all__ = ["FrontierResult", "single_merchant_frontier", "shop_frontier",
           "regret", "Receipt"]


@dataclass(frozen=True)
class FrontierResult:
    surplus: float                 # max realized surplus over the strategy space
    strategy: str                  # the argmax strategy (disclosure/merchant)
    fallback: float                # best no-negotiation surplus (frontier floor)
    per_strategy: dict[str, float] = field(default_factory=dict)


def _quote_realized(true_wtp, walk_cost, merchant, disclosure, fallback,
                    friction) -> float:
    """Realized surplus from sending `disclosure` to `merchant`: accept the
    quote if it beats the walk-away, else take the walk-away. Always >=
    fallback (the buyer can decline)."""
    q = merchant.quote(disclosure, Intent())
    if q is None:
        return fallback
    s = bundle_surplus(true_wtp, q.sku, q.qty, q.unit_price) - friction
    return max(s, fallback)


def single_merchant_frontier(true_wtp: dict[str, float], walk_cost: float,
                             merchant: Merchant, *, friction: float = 0.0,
                             attested: bool = False) -> FrontierResult:
    """Max buyer surplus over the DISCLOSURE space at one merchant (plus the
    always-available walk-away). Under `attested` the space collapses to the
    honest report."""
    fb, fb_where = fallback_surplus(true_wtp, walk_cost, [merchant])
    best, best_strat = fb, f"walk:{fb_where}"
    per = {"walk_or_sticker": fb}
    for name, d in disclosure_battery(true_wtp, walk_cost, attested=attested):
        r = _quote_realized(true_wtp, walk_cost, merchant, d, fb, friction)
        per[name] = round(r, 6)
        if r > best + 1e-12:
            best, best_strat = r, name
    return FrontierResult(surplus=round(best, 6), strategy=best_strat,
                          fallback=round(fb, 6), per_strategy=per)


def shop_frontier(true_wtp: dict[str, float], walk_cost: float,
                  merchants: list[Merchant], *, friction: float = 0.0,
                  attested: bool = False) -> FrontierResult:
    """Max buyer surplus over {which merchant} × {disclosure} — the frontier
    once the buyer may SHOP across merchants. The floor is the best sticker
    across all boards + the competitor."""
    fb, fb_where = fallback_surplus(true_wtp, walk_cost, merchants)
    best, best_strat = fb, f"walk:{fb_where}"
    per = {"walk_or_sticker": fb}
    for m in merchants:
        for name, d in disclosure_battery(true_wtp, walk_cost, attested=attested):
            r = _quote_realized(true_wtp, walk_cost, m, d, fb, friction)
            key = f"{m.merchant_id}:{name}"
            per[key] = round(r, 6)
            if r > best + 1e-12:
                best, best_strat = r, key
    return FrontierResult(surplus=round(best, 6), strategy=best_strat,
                          fallback=round(fb, 6), per_strategy=per)


def regret(frontier: FrontierResult | float, realized: float) -> float:
    """frontier − realized, floored at 0 (numerical guard; it is >= 0 by
    construction because the agent's strategy is in the frontier's space)."""
    f = frontier.surplus if isinstance(frontier, FrontierResult) else frontier
    return round(max(0.0, f - realized), 6)
