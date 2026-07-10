"""Pricing arms — cliff/1 (the industry control) and markdown/1 (the engine).

Both post one price per style×size per week; the runner enforces the
discount-only clamp (never above MSRP) at settlement, and MarkdownPolicy
additionally never RAISES a price week-over-week — markdowns are permanent
in the trade, and a price that can bounce back up would make the waiter's
drift belief incoherent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.special import erfc

from fashion.world import (SIZE_SHARE, WEEKS, WTP_SIGMA, Style, arrival_rate,
                           cliff_mult, decay)

N_GRID = 20
_SQRT2 = math.sqrt(2.0)


@dataclass
class CliffPolicy:
    """The industry control, honestly implemented: MSRP weeks 1–8, −30%
    weeks 9–11, −50% weeks 12–14, −70% weeks 15–16 — per style, uniform
    across sizes, blind to stock and to demand. This is what it replaces."""
    policy_id: str = "cliff/1"

    def price_board(self, week: int, inv: dict[tuple[str, str], int],
                    catalog: dict[str, Style]) -> dict[tuple[str, str], float]:
        m = cliff_mult(week)
        return {cell: round(catalog[cell[0]].msrp * m, 2)
                for cell, s in inv.items() if s > 0}


@dataclass
class MarkdownPolicy:
    """markdown/1 — weekly finite-horizon re-solve per style×size.

    Each week, for each cell with stock s and remaining weeks w..15, pick
    the price p (grid of N_GRID points in [salvage, MSRP], searched from
    the top so ties resolve to the HIGHER price) maximizing

        p · min(D(p), s)  +  salvage · (s − min(D(p), s))

    where D(p) = Σ_t rate(t)·attention·size_share·SF(p; appeal_est·decay(t))
    is expected remaining demand at p held for the rest of the season.
    Unit cost is sunk at the buy, so revenue+salvage argmax = margin argmax.

    Honesty notes (flagged in results):
      * min(D, s) is where the stockout hazard lives: once expected demand
        covers the stock, cutting price buys nothing — scarce cells hold
        at MSRP while the cliff marks them down on schedule.
      * Fixed-price-resolve heuristic (GvR style): the solve assumes p is
        held to season end, then re-solves next week — the standard
        approximation to the declining optimal path.
      * The demand model is MYOPIC: every consumer is priced as loyal-now.
        Strategic waiters are in the world, not in the solver — real
        markdown tools share this blind spot, and H-F3 measures the cost.
      * NO in-season learning in P0: the solve runs on the buy-time appeal
        estimate (sigma_cal) all season. A sell-through posterior is the
        P1 learner, exactly as in vend.
      * TRUE arrival curve / attention / size curve are known (public
        calendar knowledge); only the appeal LEVEL is noisy — the same
        information split as vend.
    """
    policy_id: str = "markdown/1"
    _last: dict = field(default_factory=dict)   # markdowns are permanent

    def price_board(self, week: int, inv: dict[tuple[str, str], int],
                    catalog: dict[str, Style]) -> dict[tuple[str, str], float]:
        board = {}
        for (style, size), s in inv.items():
            if s <= 0:
                continue
            listing = catalog[style]
            p = self._solve(listing, size, week, s)
            p = min(p, self._last.get((style, size), listing.msrp))
            self._last[(style, size)] = p
            board[(style, size)] = p
        return board

    def _solve(self, listing: Style, size: str, week: int, stock: int) -> float:
        grid = np.linspace(listing.msrp, listing.salvage, N_GRID)  # descending
        weeks = np.arange(week, WEEKS)
        lam = arrival_rate(weeks) * listing.attention * SIZE_SHARE[size]
        scale = listing.appeal_est * decay(weeks)
        z = np.log(grid[:, None] / scale[None, :]) / WTP_SIGMA
        sf = 0.5 * erfc(z / _SQRT2)
        demand = (lam[None, :] * sf).sum(axis=1)
        sold = np.minimum(demand, float(stock))
        obj = grid * sold + listing.salvage * (stock - sold)
        return round(float(grid[int(np.argmax(obj))]), 2)
