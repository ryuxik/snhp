"""The buyer's OWN preference model — diminishing-marginal bundle value in
dollars. Decoupled from any sim (the agent must not import a sim's internals),
but numerically identical to vend.world.bundle_value so a vend-backed world and
the buyer's accounting agree unit-for-unit. That identity is guarded by a test
(tests/test_values_sync.py), not an import — the whole point of the coupling
rule is that the buyer can outlive vend.

Everything the buyer does is graded in these dollars:
  * realized surplus  = bundle_value(true_wtp, sku, qty) − qty·price − friction
  * outside surplus    = best bundle at a competitor's board − walk cost
  * regret             = frontier − realized (frontier over the strategy space)
"""
from __future__ import annotations

QTY_DECAY = 0.55        # 2nd unit worth 55% of the 1st, 3rd 55% of the 2nd
QTY_CAP = 3             # a single visit buys at most 3 of one SKU


def bundle_value(wtp: dict[str, float], sku: str, qty: int) -> float:
    """Total dollar value of `qty` units of `sku` to a buyer with per-unit
    (first-unit) willingness-to-pay `wtp`, with diminishing marginal utility.
    THE one value function behind every buyer number in this package."""
    return sum(wtp[sku] * (QTY_DECAY ** (i - 1)) for i in range(1, qty + 1))


def best_bundle(wtp: dict[str, float], prices: dict[str, float],
                stock: dict[str, int] | None = None
                ) -> tuple[str | None, int, float]:
    """Utility-maximizing (sku, qty, surplus$) against a price board, capped
    per-SKU by stock DURING the search (a short SKU loses to a stocked
    alternative instead of being clamped after). Returns (None, 0, 0.0) if no
    positive-surplus purchase exists."""
    best: tuple[str | None, int, float] = (None, 0, 0.0)
    for sku, p in prices.items():
        cap = QTY_CAP if stock is None else min(QTY_CAP, stock.get(sku, 0))
        u = 0.0
        for n in range(1, cap + 1):
            u += wtp[sku] * (QTY_DECAY ** (n - 1))
            s = u - n * p
            if s > best[2]:
                best = (sku, n, s)
    return best


def bundle_surplus(wtp: dict[str, float], sku: str, qty: int,
                   unit_price: float) -> float:
    """Buyer's true dollar surplus from buying `qty` of `sku` at `unit_price`."""
    return bundle_value(wtp, sku, qty) - qty * unit_price
