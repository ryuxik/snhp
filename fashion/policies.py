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
                           cliff_mult, decay, return_lag_pmf)

N_GRID = 20
_SQRT2 = math.sqrt(2.0)

# ── timeline-optimized markdown arm (opt/1) tuning ─────────────────────────
# The engine's belief about its OWN forward markdown pace, used ONLY to value
# the resale of a returned unit at the (lower) price it will fetch when it
# re-enters — i.e. to price the refund-vs-resale gap the returns-blind
# markdown/1 ignores. Set to the WTP-staleness rate (DECAY=0.96): the engine
# anticipates its price drifts down roughly as fast as demand goes stale.
# THE RESULT IS FRAGILE TO THIS BELIEF and the verdict is reported with a full
# sensitivity sweep {1.0, 0.98, 0.96, 0.92} — at its best (~0.98) the
# returns-aware solve only TIES markdown/1; a mis-set drift loses significantly.
# Flagged: an anticipation, not exact knowledge, and the fragility is the point.
ANTICIPATED_DRIFT = 0.96
# In-season demand learner (cumulative, censoring-aware sell-through). Per-week
# demand is tiny (~a few units/cell), so a per-week multiplicative nudge
# accumulates a small-sample DOWNWARD bias (Jensen on noisy ratios) AND a
# censoring bias (stockout weeks — the high-demand ones — would be dropped).
# So the learner instead accumulates observed vs buy-time-model-expected demand
# over the whole season and moves the appeal estimate off the CUMULATIVE ratio,
# which the LLN drives to 1 when the estimate is right. Censored (sold-out)
# weeks are kept as LOWER-BOUND evidence that can only push the estimate UP
# (never down) — the unsold-is-not-zero-demand rule, transposed.
LEARN_GAIN = 0.7             # ratio → appeal-multiplier exponent (SF elasticity)
LEARN_TOTAL_CLIP = (0.40, 2.50)  # bound on appeal_hat / appeal_est overall
LEARN_MIN_EXP = 8.0          # need this much cumulative expected demand before
                             # trusting the ratio (else hold the buy-time guess)


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


class AppealLearner:
    """In-season demand-curve learning (opt/1's 'learned demand' half).

    markdown/1 runs on the buy-time appeal estimate all season; this re-estimates
    a per-style appeal LEVEL from observed sell-through — the same information
    split as vend (structural curves known, level learned). Accumulates observed
    sales and the buy-time model's expected demand (at the STATIC appeal_est, a
    fixed reference so the ratio can't chase itself) and sets

        appeal_hat = appeal_est · clip( (obs_cum / exp_cum) ** GAIN , …)

    once enough evidence has accrued (LEARN_MIN_EXP). CENSORING-AWARE: a
    sold-out cell-week's sales are a LOWER BOUND on demand, so it is entered with
    exp capped at the observed units — it can only pull the estimate UP, never
    down (dropping such weeks, or counting them at face value, would bias the
    level down exactly where demand was strongest). obs_cum/exp_cum → 1 by the
    LLN when appeal_est is right, so a well-calibrated buyer is left ~undisturbed
    while a mis-estimated one gets corrected."""

    def __init__(self, catalog: dict[str, Style]):
        self._est = {st: s.appeal_est for st, s in catalog.items()}
        self._obs = {st: 0.0 for st in catalog}
        self._exp = {st: 0.0 for st in catalog}

    def appeal(self, style: str) -> float:
        exp = self._exp[style]
        if exp < LEARN_MIN_EXP:
            return self._est[style]           # too little signal → buy-time guess
        ratio = self._obs[style] / exp
        lo, hi = LEARN_TOTAL_CLIP
        return float(np.clip(self._est[style] * ratio ** LEARN_GAIN,
                             self._est[style] * lo, self._est[style] * hi))

    def accumulate(self, style: str, obs_sales: float, exp_demand: float,
                   censored: bool) -> None:
        """One cell-week. exp_demand is evaluated at the STATIC appeal_est. A
        censored (sold-out) week enters as a lower bound: exp is capped at the
        units actually sold, so it never argues the level is LOW."""
        if censored:
            exp_demand = min(exp_demand, obs_sales)
        self._obs[style] += obs_sales
        self._exp[style] += exp_demand


@dataclass
class OptMarkdownPolicy:
    """opt/1 — the timeline-optimized markdown arm (CRITICAL-ANALYSIS §4,
    fashion). Two upgrades over markdown/1, both on the TIME axis:

      1. LEARNED demand curve (AppealLearner): the appeal LEVEL is re-estimated
         weekly from observed, censoring-aware sell-through instead of frozen
         at the buy-time guess. Isolated cleanly at r=0 (returns off), where
         opt/1 is *exactly* markdown/1's myopic solve run on the learned
         appeal — so the r=0 opt−markdown gap is the pure value of learning.
      2. RETURN-TIMING in the solve: when returns are on, the solve stops
         assuming a flat held price and instead forward-simulates the season
         under an anticipated DECLINING path (ANTICIPATED_DRIFT), with returned
         units re-entering sellable stock at the published lag (return_lag_pmf)
         and RESELLING at the lower price they will actually fetch then —
         pricing the refund-vs-resale gap markdown/1 is blind to, plus the
         post-season-salvage risk of late sales whose returns miss the season.

    Honesty notes (flagged in results):
      * The return RATE and lag curve are treated as PUBLIC knowledge (a
        retailer knows both from history, like the arrival taper) — opt/1 does
        not have to learn them; only the appeal LEVEL is learned. The demand
        model stays MYOPIC about strategic waiters (same blind spot as
        markdown/1). Second-order recycling (a returned unit competing for a
        future demand slot) IS modeled via the pipeline; the anticipated future
        path is a drift belief, not a self-consistent fixed point — the verdict
        is reported with a drift sensitivity sweep.
      * At r=0 the drift/returns machinery is inert by construction, so the
        r=0 grid separates 'learned demand' from 'return-timing' exactly."""

    policy_id: str = "opt/1"
    return_rate: float = 0.0
    learn: bool = True          # in-season appeal learning (the 'learned
                                # demand' half); False → returns-timing only,
                                # on the static buy-time estimate (ablation)
    catalog: dict = None
    learner: AppealLearner = None
    _last: dict = field(default_factory=dict)   # markdowns are permanent
    _lag_pmf: dict = field(default_factory=return_lag_pmf)

    def _appeal(self, style: str) -> float:
        return (self.learner.appeal(style) if self.learn
                else self.catalog[style].appeal_est)

    def bind(self, catalog: dict[str, Style]) -> None:
        """The runner hands the catalog once (opt/1 needs it for the learner
        and to key the solve); kept off __init__ so ARMS[name]() still works."""
        self.catalog = catalog
        self.learner = AppealLearner(catalog)

    def price_board(self, week: int, inv: dict[tuple[str, str], int],
                    catalog: dict[str, Style]) -> dict[tuple[str, str], float]:
        if self.learner is None:
            self.bind(catalog)
        board = {}
        for (style, size), s in inv.items():
            if s <= 0:
                continue
            listing = catalog[style]
            ah = self._appeal(style)
            if self.return_rate > 0:
                p = self._solve_returns_aware(listing, size, week, s, ah)
            else:
                p = self._solve_myopic(listing, size, week, s, ah)
            p = min(p, self._last.get((style, size), listing.msrp))
            self._last[(style, size)] = p
            board[(style, size)] = p
        return board

    def observe_week(self, week: int, board: dict[tuple[str, str], float],
                     sold: dict[tuple[str, str], int],
                     start_stock: dict[tuple[str, str], int]) -> None:
        """Feed the learner one week of demand signal. Expected demand is scored
        at the STATIC buy-time appeal_est (a fixed reference); a cell that sold
        out is flagged censored so it enters as a lower bound only."""
        if self.learner is None or not self.learn:
            return
        for (style, size), p in board.items():
            u = sold.get((style, size), 0)
            s0 = start_stock.get((style, size), 0)
            d = (arrival_rate(week) * self.catalog[style].attention
                 * SIZE_SHARE[size]
                 * _sf(p, self.catalog[style].appeal_est * decay(week)))
            self.learner.accumulate(style, u, d, censored=(s0 <= u))

    def _solve_myopic(self, listing: Style, size: str, week: int, stock: int,
                      appeal_hat: float) -> float:
        """markdown/1's held-price finite-horizon solve, on the LEARNED appeal.
        Identical objective to MarkdownPolicy._solve so r=0 opt/1 = markdown/1
        + learning, nothing more."""
        grid = np.linspace(listing.msrp, listing.salvage, N_GRID)
        weeks = np.arange(week, WEEKS)
        lam = arrival_rate(weeks) * listing.attention * SIZE_SHARE[size]
        scale = appeal_hat * decay(weeks)
        z = np.log(grid[:, None] / scale[None, :]) / WTP_SIGMA
        sf = 0.5 * erfc(z / _SQRT2)
        demand = (lam[None, :] * sf).sum(axis=1)
        sold = np.minimum(demand, float(stock))
        obj = grid * sold + listing.salvage * (stock - sold)
        return round(float(grid[int(np.argmax(obj))]), 2)

    def _solve_returns_aware(self, listing: Style, size: str, week: int,
                             stock: int, appeal_hat: float) -> float:
        """Forward-simulate the remaining season for every candidate starting
        price, under an anticipated declining path, with the return pipeline:
        a sale at price p_t returns w.p. r after a lag (return_lag_pmf), is
        refunded at p_t, and RE-ENTERS sellable stock at t+lag reselling at the
        lower p_{t+lag} (or salvages if the season is over). The committed
        decision is the current-week price (t=week, drift factor 1)."""
        grid = np.linspace(listing.msrp, listing.salvage, N_GRID)   # (G,)
        G = grid.size
        r = self.return_rate
        lam0 = listing.attention * SIZE_SHARE[size]
        A = np.full(G, float(stock))               # available stock per candidate
        pending = np.zeros((G, WEEKS))             # re-entry inflow by abs. week
        revenue = np.zeros(G)
        refunds = np.zeros(G)
        salv = np.zeros(G)
        for t in range(week, WEEKS):
            A = A + pending[:, t]
            drift = ANTICIPATED_DRIFT ** (t - week)
            p_t = np.maximum(grid * drift, listing.salvage)         # (G,)
            d_t = arrival_rate(t) * lam0 * _sf_vec(p_t, appeal_hat * decay(t))
            u_t = np.minimum(d_t, A)
            A = A - u_t
            revenue += p_t * u_t
            ret = r * u_t
            refunds += p_t * ret
            for lag, wl in self._lag_pmf.items():
                tw = t + lag
                if tw <= WEEKS - 1:
                    pending[:, tw] += ret * wl
                else:
                    salv += listing.salvage * ret * wl
        salv += listing.salvage * A
        obj = revenue - refunds + salv
        return round(float(grid[int(np.argmax(obj))]), 2)


def _sf(price: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return float(0.5 * erfc(math.log(price / scale) / WTP_SIGMA / _SQRT2))


def _sf_vec(price, scale: float):
    price = np.asarray(price, dtype=float)
    if scale <= 0:
        return np.zeros_like(price)
    return 0.5 * erfc(np.log(price / scale) / WTP_SIGMA / _SQRT2)
