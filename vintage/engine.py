"""The store-side engine: per-item Bayesian survival beliefs, a
censoring-aware learned connection rate, event-consistent continuation
values, and the accept/counter decision.

The disagreement point (vend's nash_quote discipline, transposed): the
store's alternative to ANY deal on item i is the EVENT of waiting for a
future connecting browser. Its value is computed from
  * the item's own survival history — every unsold day at a given price is
    evidence about its hidden appeal (a posterior over a log-grid around
    the tag), and
  * a connection rate rho LEARNED from the store's own sales, censoring-
    aware: a sale adds one event; an unsold item-day adds EXPOSURE weighted
    by the believed probability a connection would have cleared the price.
    An overpriced survivor adds almost no exposure — its sitting says
    nothing about traffic (unsold is NOT zero demand) — while a cheap
    survivor adds a lot (that silence is loud).
The buyer's alternative is walking (their disagreement is zero surplus);
their behavior — shading, counter tolerance, huff friction — lives in the
world/runner, not here. The engine never sees appeal or WTP.
"""
from __future__ import annotations

import math

import numpy as np

from vintage.calibration import (BELIEF_GRID_N, BELIEF_GRID_Z, BELIEF_SIGMA,
                                 BUFFER_ABS, BUFFER_FRAC, COUNTER_GRID_N,
                                 DAILY_DISCOUNT, HOLDING_COST, HUFF_BELIEF,
                                 P_HUFF, PRICE_FLOOR_FRAC, PRICE_GRID_N,
                                 RHO_PRIOR_MEAN, RHO_PRIOR_STRENGTH,
                                 SHADING_BELIEF_HI, SHADING_BELIEF_LO,
                                 SIGMA_WTP, TOLERANCE, TRAFFIC_MEAN)
from vintage.core import lognorm_sf_vec
from vintage.world import Item

_Z = np.linspace(-BELIEF_GRID_Z * BELIEF_SIGMA, BELIEF_GRID_Z * BELIEF_SIGMA,
                 BELIEF_GRID_N)
_PRIOR = np.exp(-0.5 * (_Z / BELIEF_SIGMA) ** 2)
_PRIOR = _PRIOR / _PRIOR.sum()


def buffer(tag: float) -> float:
    """Don't-negotiate-for-pennies, scaled with the piece (vend's min_gain
    pattern): the engine's believed gain over waiting must clear this."""
    return max(BUFFER_ABS, BUFFER_FRAC * tag)


def _pv(lam: np.ndarray | float, pay: float) -> np.ndarray | float:
    """Closed-form present value of holding one item: geometric sale time at
    daily hazard lam, payment `pay` on sale, HOLDING_COST every unsold day,
    DAILY_DISCOUNT on everything. Pure math:
        V = [lam*d*pay − h*d*(1−lam)] / (1 − d*(1−lam))."""
    d, h = DAILY_DISCOUNT, HOLDING_COST
    return (lam * d * pay - h * d * (1.0 - lam)) / (1.0 - d * (1.0 - lam))


class Beliefs:
    """One arm's engine state. Per-item: posterior weights over a log-grid
    of appeal values centered on the TAG (the owner's estimate is the prior
    — miscalibration and all). Store-level: the Gamma-style connection-rate
    posterior (events / effective exposure)."""

    def __init__(self):
        self._w: dict[int, np.ndarray] = {}
        self._mu: dict[int, np.ndarray] = {}
        self._events = RHO_PRIOR_STRENGTH
        self._exposure = RHO_PRIOR_STRENGTH / RHO_PRIOR_MEAN

    # ── admission / bookkeeping ────────────────────────────────────────────
    def admit(self, item: Item) -> None:
        self._mu[item.uid] = item.tag * np.exp(_Z)
        self._w[item.uid] = _PRIOR.copy()

    def has(self, uid: int) -> bool:
        return uid in self._w

    @property
    def rho(self) -> float:
        """Learned connection rate per browser per item (prior mean until
        sales history exists — never zero, never the true value by fiat)."""
        return self._events / self._exposure

    # ── evidence ───────────────────────────────────────────────────────────
    def e_sf(self, uid: int, price: float) -> float:
        """Posterior-mean P(a connecting browser's WTP clears `price`)."""
        return float(self._w[uid] @ lognorm_sf_vec(price, self._mu[uid],
                                                   SIGMA_WTP))

    def survival(self, uid: int, price: float, browsers: int) -> None:
        """End-of-day update for an UNSOLD item that faced `browsers` people
        at `price`: multiply by P(no sale | appeal) and renormalize; add the
        censoring-aware exposure (expected clearing connections per unit
        rho) to the rate learner."""
        self._exposure += browsers * self.e_sf(uid, price)
        sf = lognorm_sf_vec(price, self._mu[uid], SIGMA_WTP)
        w = self._w[uid] * (1.0 - self.rho * sf) ** browsers
        total = w.sum()
        if total > 0:
            self._w[uid] = w / total

    def sale(self, uid: int, price: float, browsers: int) -> None:
        """A sale is one event plus roughly half a day's exposure (the item
        was only on the rack until it sold). The item's posterior leaves
        with it — one-of-one."""
        self._events += 1.0
        self._exposure += 0.5 * browsers * self.e_sf(uid, price)
        del self._w[uid], self._mu[uid]

    # ── forecasts ──────────────────────────────────────────────────────────
    def hazard(self, uid: int, price: float,
               traffic: float = TRAFFIC_MEAN) -> float:
        """Posterior P(item sells within a day at `price`) — mixture over
        appeal, exact within the engine's model."""
        sf = lognorm_sf_vec(price, self._mu[uid], SIGMA_WTP)
        return float(self._w[uid] @ (1.0 - (1.0 - self.rho * sf) ** traffic))

    def continuation(self, uid: int, pay: float,
                     traffic: float = TRAFFIC_MEAN) -> float:
        """The disagreement value: expected discounted proceeds of WAITING,
        assuming future settlement at `pay` (posted price for hazard/1;
        f̂ x ask for offer/1 — future sales there settle via offers too).
        Mixture of closed forms over the appeal posterior; floored at zero
        because the store can always toss a true liability (free disposal)."""
        sf = lognorm_sf_vec(pay, self._mu[uid], SIGMA_WTP)
        lam = 1.0 - (1.0 - self.rho * sf) ** traffic
        return max(0.0, float(self._w[uid] @ _pv(lam, pay)))

    def appeal_mean(self, uid: int) -> float:
        return float(self._w[uid] @ self._mu[uid])


# ── the offer decision ──────────────────────────────────────────────────────

def p_counter_accept(offer: float, counter: float) -> float:
    """The ENGINE'S BELIEF that a counter sticks: the browser walks with
    HUFF_BELIEF regardless (haggle friction), else accepts iff their WTP ≥
    counter. The offer implies WTP = offer/s with s believed uniform on
    [SHADING_BELIEF_LO, SHADING_BELIEF_HI], so
        P(WTP ≥ c) = P(s ≤ offer/c),
    clamped. The engine does NOT know the true shading center."""
    ps = (offer / counter - SHADING_BELIEF_LO) \
        / (SHADING_BELIEF_HI - SHADING_BELIEF_LO)
    return (1.0 - HUFF_BELIEF) * min(1.0, max(0.0, ps))


def decide_offer(offer: float, ask: float, tag: float,
                 v_wait: float) -> tuple[str, float]:
    """Accept / counter, event-consistently. The floor is the disagreement
    value plus the buffer — the engine NEVER accepts below it (tested
    invariant). Above the floor it plays expected value: accept the bird in
    hand iff no counter beats it once walk-risk is priced in.

    Returns ("accept", offer) or ("counter", price) with price in
    (offer, ask]. A counter AT ask is the engine saying the tag is firm."""
    floor = v_wait + buffer(tag)
    lo = max(floor, offer + 0.01)
    if lo >= ask:
        return ("counter", ask)          # firm: waiting beats any discount
    grid = np.linspace(lo, ask, COUNTER_GRID_N)
    ev = np.array([p_counter_accept(offer, c) * c
                   + (1.0 - p_counter_accept(offer, c)) * v_wait
                   for c in grid])
    j = int(np.argmax(ev[::-1]))         # ties resolve to the HIGHER price
    c_star, ev_star = float(grid[::-1][j]), float(ev[::-1][j])
    if offer >= floor and offer >= ev_star:
        return ("accept", offer)
    return ("counter", min(ask, float(math.ceil(c_star))))


def counter_response(wtp: float, counter: float, huff_roll: float) -> bool:
    """The BROWSER'S side of the counter round (world truth, not belief):
    they walk out on P_HUFF regardless of the number, else accept iff the
    counter is within their tolerance of WTP."""
    if huff_roll < P_HUFF:
        return False
    return counter <= wtp * TOLERANCE


# ── hazard/1's computed markdown ───────────────────────────────────────────

def solve_price(beliefs: Beliefs, uid: int, current: float, tag: float,
                traffic: float = TRAFFIC_MEAN) -> float:
    """The weekly re-solve: pick the posted price maximizing the posterior-
    mean present value of the item (same closed form as the disagreement
    value — one economics, two uses). Discount-only and monotone: never
    above the current price (markdowns are permanent in the trade), never
    below PRICE_FLOOR_FRAC x tag. Fixed-price-resolve heuristic (GvR
    style): the solve assumes the price is held forever, then re-solves
    next week."""
    lo = PRICE_FLOOR_FRAC * tag
    if current <= lo:
        return current
    mu, w, rho = beliefs._mu[uid], beliefs._w[uid], beliefs.rho
    best_p, best_v = current, -np.inf
    for p in np.linspace(current, lo, PRICE_GRID_N):   # from the top:
        sf = lognorm_sf_vec(float(p), mu, SIGMA_WTP)   # ties keep price high
        lam = 1.0 - (1.0 - rho * sf) ** traffic
        v = float(w @ _pv(lam, float(p)))
        if v > best_v + 1e-9:
            best_p, best_v = float(p), v
    return min(current, max(lo, round(best_p)))
