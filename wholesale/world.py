"""Wholesale world mechanics — deterministic demand streams (paired across
arms by construction), the weekly delivery-window schedule, and the route
economics of a distributor's truck serving one block.

Treatment isolation: every draw is a pure function of (master_seed, week,
venue[, wholesaler]) — an ARM parameter does not exist in any signature
here, so all arms face identical forecasts and identical realized demand
(asserted in tests). Divergence starts only at the deal each arm strikes.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from wholesale import calibration as cal

# ── windows: Mon-Fri x AM/PM, index = day*2 + half ───────────────────────
N_WINDOWS = 10
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri")


def window_label(iw: int) -> str:
    return f"{DAY_NAMES[iw // 2]}-{'AM' if iw % 2 == 0 else 'PM'}"


def is_am(iw: int) -> bool:
    return iw % 2 == 0


def shadow(iw: int) -> float:
    """Slot shadow value: what the wholesaler's route forgoes elsewhere by
    spending this window on the block. Mornings are scarce."""
    return cal.SHADOW_AM if is_am(iw) else cal.SHADOW_PM


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (vend/gauntlet pattern): blake2b of the
    master seed and any hashable parts, folded to 63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


# ── demand: discretized-normal newsvendor machinery ──────────────────────

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def demand_pmf(mu: float, sigma: float, support_max: int) -> np.ndarray:
    """pmf of weekly case demand on 0..support_max: a normal(mu, sigma)
    discretized at half-integer edges; the negative tail folds into 0 and
    the upper tail into the top bin."""
    edges = np.array([_norm_cdf((k + 0.5 - mu) / sigma)
                      for k in range(support_max)])
    pmf = np.empty(support_max + 1)
    pmf[0] = edges[0]
    pmf[1:support_max] = np.diff(edges)
    pmf[support_max] = 1.0 - edges[-1]
    return pmf


def sold_curve(pmf: np.ndarray) -> np.ndarray:
    """e_sold[q] = E[min(q, D)] for q = 0..K, via the survival identity
    E[min(q, D)] = sum_{k<q} P(D > k)."""
    surv = 1.0 - np.cumsum(pmf)
    return np.concatenate([[0.0], np.cumsum(surv[:-1])])


def draw_from_pmf(pmf: np.ndarray, u: float) -> int:
    return int(np.searchsorted(np.cumsum(pmf), u, side="left").clip(0, len(pmf) - 1))


@dataclass(frozen=True)
class WeekDemand:
    """One relationship-week's demand environment: the forecast the venue
    discloses at negotiation time (mu_w, sigma -> pmf, e_sold) and the
    realization d_real that scores the deal afterwards."""
    mu_w: float
    sigma: float
    pmf: np.ndarray
    e_sold: np.ndarray     # E[min(q, D)] indexable by integer q (0..cap)
    d_real: int


def forecast_mult(seed: int, week: int, venue: str) -> float:
    """Venue-level weekly demand factor (shared across that venue's three
    supply categories — one crowd shows up), lognormal with mean 1."""
    rng = np.random.default_rng(substream(seed, "fw", week, venue))
    return float(math.exp(rng.normal(0.0, cal.SIGMA_FORECAST)
                          - cal.SIGMA_FORECAST ** 2 / 2))


def week_demand(seed: int, week: int, wholesaler: str, venue: str,
                noise: float) -> WeekDemand:
    """Paired by construction: pure function of (seed, week, wholesaler,
    venue, noise) — no arm parameter exists."""
    cap = cal.STORAGE_CAP[(wholesaler, venue)]
    mu_w = cal.DEMAND_MU[(wholesaler, venue)] * forecast_mult(seed, week, venue)
    sigma = max(noise * mu_w, 1e-6)
    pmf = demand_pmf(mu_w, sigma, cap)
    u = float(np.random.default_rng(
        substream(seed, "dreal", week, venue, wholesaler)).random())
    return WeekDemand(mu_w, sigma, pmf, sold_curve(pmf), draw_from_pmf(pmf, u))


# ── the truck's weekly schedule (one per wholesaler-week) ────────────────

@dataclass
class Schedule:
    """Stops on the block this week. One physical stop max per window;
    extra venues in the same window ride as DROPS on that stop (route
    density). AM stops are capped per week (mornings are scarce)."""
    stops: dict = field(default_factory=dict)   # window -> [venue, ...]

    def has_stop(self, iw: int) -> bool:
        return iw in self.stops

    def am_stops(self) -> int:
        return sum(1 for iw in self.stops if is_am(iw))

    def can_new_stop(self, iw: int) -> bool:
        return iw not in self.stops and (
            not is_am(iw) or self.am_stops() < cal.AM_STOPS_PER_WEEK)

    def feasible(self, iw: int) -> bool:
        return self.has_stop(iw) or self.can_new_stop(iw)

    def incremental_cost(self, iw: int) -> float:
        """The wholesaler's marginal cost of delivering into window iw:
        a drop fee if the truck already stops there, else a fresh stop
        plus the slot's shadow value; inf if the window is unschedulable."""
        if self.has_stop(iw):
            return cal.DROP_COST
        if self.can_new_stop(iw):
            return cal.STOP_COST + shadow(iw)
        return math.inf

    def add(self, venue: str, iw: int) -> None:
        if not self.feasible(iw):
            raise ValueError(f"window {window_label(iw)} unschedulable")
        self.stops.setdefault(iw, []).append(venue)

    def realized_route_cost(self) -> float:
        """A shared window bills ONE stop (+ shadow) plus per-extra-venue
        drop fees — the route-density accounting, asserted in tests."""
        return sum(cal.STOP_COST + shadow(iw) + cal.DROP_COST * (len(vs) - 1)
                   for iw, vs in self.stops.items())

    def shared_windows(self) -> int:
        return sum(1 for vs in self.stops.values() if len(vs) >= 2)

    def n_stops(self) -> int:
        return len(self.stops)


def fcfs_window(schedule: Schedule, pref) -> int:
    """The industry control's dispatch: the venue asks for its favorite
    windows in order; the dispatcher grants the first it can serve (an
    existing stop always takes another drop; a new stop needs capacity).
    Always resolves: an occupied window is itself feasible."""
    for iw in pref:
        if schedule.feasible(iw):
            return iw
    raise RuntimeError("no feasible window — impossible by construction")
