"""BuyerLedger — the consumer-facing receipts data structure.

Closes gap 3 (aggregate/anonymous surplus). vend totals consumer surplus in
one bucket; here every dollar is attributed to a `uid`, persists across visits
and merchants, and carries its own regret. This is the "your agent saved you
$X this month, and left $Y on the table" object.

Conservation invariant (tested): Σ over uids of lifetime_surplus == the
aggregate consumer surplus the run reports. Nothing is created or lost in the
per-uid split.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Receipt:
    uid: int
    merchant_id: str | None       # None = walked / no purchase
    strategy: str                 # naive | honest | shop | time | commit | coordinate
    sku: str | None
    qty: int
    unit_price: float
    list_price: float
    realized_surplus: float       # true buyer surplus net of friction
    outside_surplus: float        # best walk-away alternative
    frontier_surplus: float       # max over the buyer's strategy space
    regret: float                 # frontier − realized (>= 0 by construction)
    day: int = 0

    @property
    def saved_vs_list(self) -> float:
        """Dollars under list on this receipt (0 if walked / bought at list)."""
        if self.sku is None:
            return 0.0
        return round(self.qty * (self.list_price - self.unit_price), 2)


class BuyerLedger:
    def __init__(self):
        self._rows: list[Receipt] = []

    def record(self, r: Receipt) -> None:
        self._rows.append(r)

    # ── per-uid views (the receipts a consumer would see) ──
    def rows_for(self, uid: int) -> list[Receipt]:
        return [r for r in self._rows if r.uid == uid]

    def lifetime_surplus(self, uid: int) -> float:
        return round(sum(r.realized_surplus for r in self.rows_for(uid)), 6)

    def lifetime_regret(self, uid: int) -> float:
        return round(sum(r.regret for r in self.rows_for(uid)), 6)

    def lifetime_saved_vs_list(self, uid: int) -> float:
        return round(sum(r.saved_vs_list for r in self.rows_for(uid)), 2)

    def uids(self) -> list[int]:
        seen, out = set(), []
        for r in self._rows:
            if r.uid not in seen:
                seen.add(r.uid)
                out.append(r.uid)
        return out

    # ── aggregate views (what a vend-style run would report) ──
    def aggregate_surplus(self) -> float:
        return round(sum(r.realized_surplus for r in self._rows), 6)

    def aggregate_regret(self) -> float:
        return round(sum(r.regret for r in self._rows), 6)

    def aggregate_frontier(self) -> float:
        return round(sum(r.frontier_surplus for r in self._rows), 6)

    def all_rows(self) -> list[Receipt]:
        return list(self._rows)

    def conserves(self, tol: float = 1e-6) -> bool:
        """Σ per-uid lifetime surplus == aggregate surplus (the split loses
        nothing). The conservation test calls this directly."""
        per_uid = sum(self.lifetime_surplus(u) for u in self.uids())
        return abs(per_uid - self.aggregate_surplus()) < tol
