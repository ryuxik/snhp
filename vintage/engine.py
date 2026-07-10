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
world/runner, not here. The engine never sees appeal or WTP; post-reg FIX B
lets it LEARN the population's shading distribution and huff rate from its
own counter-round history (ShadingLearner), censoring-aware.
"""
from __future__ import annotations

import math

import numpy as np

from vintage.calibration import (BELIEF_GRID_N, BELIEF_GRID_Z, BELIEF_SIGMA,
                                 BUFFER_ABS, BUFFER_FRAC, COUNTER_GRID_N,
                                 DAILY_DISCOUNT, FALLBACK_PRIOR_N,
                                 HOLDING_COST, HUFF_BELIEF,
                                 HUFF_PRIOR_STRENGTH, P_HUFF,
                                 PRICE_FLOOR_FRAC, PRICE_GRID_N, RETAG_GRID_N,
                                 RHO_PRIOR_MEAN, RHO_PRIOR_STRENGTH,
                                 SHADE_CENTER_HI, SHADE_CENTER_LO,
                                 SHADE_CENTER_N, SHADE_HALFWIDTH,
                                 SHADE_LIK_EPS, SIGMA_WTP, TOLERANCE,
                                 TRAFFIC_MEAN)
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

class ShadingLearner:
    """FIX B (post-registration, CRITICAL-ANALYSIS §4a): population-level
    inference about the counter round, learned from the engine's OWN
    accept/huff/reject/fallback history. Three learned quantities:

    * The shading-CENTER posterior: a grid over centers m with the belief
      s | m ~ U[m − W, m + W] (W = SHADE_HALFWIDTH). The counter round is
      CENSORED evidence about s = offer/WTP: an ACCEPTED counter at c on
      offer x reveals WTP ≥ c, i.e. s ≤ x/c (an upper bound); a non-huff
      REJECT reveals WTP < c, i.e. s > x/c (a lower bound). A HUFF reveals
      NOTHING about shading — huffing is price-blind ("they came with a
      number") — so the shading update SKIPS it rather than mistaking
      pride for poverty.
    * The huff rate: a Beta posterior over counter outcomes (huff vs not),
      prior worth HUFF_PRIOR_STRENGTH counters at mean HUFF_BELIEF.
    * F̂, the browser's continuation value to the STORE: the mean realized
      fallback margin (fallback price − the engine's own waiting value on
      the fallback piece; zero when the browser buys nothing) over observed
      non-huff dead negotiations. A huffed browser's continuation is
      censored — never observed — so the reject-branch mean stands in for
      it, which is exact because the huff roll is independent of price and
      WTP. F̂ is what a counter gambles: huff-cost = F̂, walk-prob = ĥ.
    """

    def __init__(self):
        self._m = np.linspace(SHADE_CENTER_LO, SHADE_CENTER_HI, SHADE_CENTER_N)
        self._w = np.full(SHADE_CENTER_N, 1.0 / SHADE_CENTER_N)
        self._huff_a = HUFF_PRIOR_STRENGTH * HUFF_BELIEF
        self._huff_b = HUFF_PRIOR_STRENGTH * (1.0 - HUFF_BELIEF)
        self._fb_sum = 0.0
        self._fb_n = FALLBACK_PRIOR_N

    @property
    def p_huff(self) -> float:
        """Posterior-mean P(a countered browser walks out regardless)."""
        return self._huff_a / (self._huff_a + self._huff_b)

    @property
    def fallback_value(self) -> float:
        """F̂: mean margin the store still earns from a browser whose
        negotiation dies WITHOUT a huff (they shop the board)."""
        return self._fb_sum / self._fb_n

    def p_stick(self, offer: float, counters) -> np.ndarray:
        """Posterior P(WTP ≥ c) = P(s ≤ offer/c), mixture over centers."""
        r = offer / np.asarray(counters, dtype=float)
        lik = np.clip((r[:, None] - (self._m[None, :] - SHADE_HALFWIDTH))
                      / (2.0 * SHADE_HALFWIDTH), 0.0, 1.0)
        return lik @ self._w

    def observe_counter(self, offer: float, counter: float,
                        outcome: str) -> None:
        """One counter round's outcome: 'accept' | 'huff' | 'reject'."""
        if outcome == "huff":
            self._huff_a += 1.0
            return                       # censored: says nothing about shading
        self._huff_b += 1.0
        r = offer / counter
        p = np.clip((r - (self._m - SHADE_HALFWIDTH))
                    / (2.0 * SHADE_HALFWIDTH),
                    SHADE_LIK_EPS, 1.0 - SHADE_LIK_EPS)
        w = self._w * (p if outcome == "accept" else 1.0 - p)
        total = w.sum()
        if total > 0:
            self._w = w / total

    def observe_continuation(self, value: float) -> None:
        """Realized continuation margin of a non-huff dead negotiation
        (fallback sale margin over that piece's waiting value, or 0)."""
        self._fb_sum += value
        self._fb_n += 1.0


def decide_offer(offer: float, ask: float, tag: float, v_wait: float,
                 learner: ShadingLearner | None = None) -> tuple[str, float]:
    """Accept / counter / DECLINE, event-consistently, with the counter's
    huff externality priced (FIX B). The floor is unchanged and tested: the
    engine NEVER accepts below the disagreement value plus the buffer.
    Above it, expected value decides between three actions:
      accept  — the bird in hand: EV = offer (the browser buys THIS piece);
      counter — EV = ĥ·v_wait + (1−ĥ)·[P̂(stick)·c + (1−P̂)·(v_wait + F̂)]:
                a counter gambles the browser's continuation value F̂ on the
                huff — the store-level cost the old engine ignored;
      decline — no number, no huff: the piece waits, the browser shops the
                board. EV = v_wait + F̂.
    Returns ("accept", offer), ("counter", c) with c in (offer, ask], or
    ("decline", 0.0). A counter AT ask is the engine saying the tag is firm;
    ties prefer accept, then the counter (the pre-fix behavior)."""
    if learner is None:
        learner = ShadingLearner()       # prior beliefs: the unlearned engine
    floor = v_wait + buffer(tag)
    h, fb = learner.p_huff, learner.fallback_value
    ev_decline = v_wait + fb
    lo = max(floor, offer + 0.01)
    if lo >= ask:
        cands = np.array([float(ask)])   # only the firm counter is legal
    else:
        cands = np.linspace(lo, ask, COUNTER_GRID_N)
    p = learner.p_stick(offer, cands)
    ev = h * v_wait + (1.0 - h) * (p * cands + (1.0 - p) * (v_wait + fb))
    j = int(np.argmax(ev[::-1]))         # ties resolve to the HIGHER price
    c_star, ev_star = float(cands[::-1][j]), float(ev[::-1][j])
    ev_accept = offer if offer >= floor else -np.inf
    if ev_accept >= ev_star and ev_accept >= ev_decline:
        return ("accept", offer)
    if ev_star >= ev_decline - 1e-12:
        return ("counter", min(ask, float(math.ceil(c_star))))
    return ("decline", 0.0)


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


# ── retag/1's bidirectional re-solve (FIX A, post-registration) ─────────────

def solve_price_free(beliefs: Beliefs, uid: int, tag: float,
                     traffic: float = TRAFFIC_MEAN) -> float:
    """The SAME posterior-mean-PV objective as solve_price with the
    discount-only shackle removed: the posted price may move UP as well as
    DOWN, toward the posterior-optimal posted price. One-of-one goods have
    no reference price to protect (CRITICAL-ANALYSIS §4b) — the ceiling
    existed to protect reference prices, so nothing pins the price to the
    owner's guess here. Bounded by the item's OWN appeal posterior: floor
    PRICE_FLOOR_FRAC x tag (house floor, unchanged), ceiling the top of the
    posterior support — the engine never posts a price its own beliefs give
    zero probability of being worth. Whole dollars, like every tag."""
    mu, w, rho = beliefs._mu[uid], beliefs._w[uid], beliefs.rho
    lo = PRICE_FLOOR_FRAC * tag
    hi = float(mu.max())
    if hi <= lo:
        return float(lo)
    best_p, best_v = hi, -np.inf
    for p in np.linspace(hi, lo, RETAG_GRID_N):        # from the top:
        sf = lognorm_sf_vec(float(p), mu, SIGMA_WTP)   # ties keep price high
        lam = 1.0 - (1.0 - rho * sf) ** traffic
        v = float(w @ _pv(lam, float(p)))
        if v > best_v + 1e-9:
            best_p, best_v = float(p), v
    return float(min(hi, max(lo, round(best_p))))
