"""Pricing policies — the four arms of the experiment behind one interface.

P0 ships the posted-board arms (static, gvr). The A2A and LLM arms (P1/P2)
implement the same interface but price per-intent instead of per-board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vend.core import MachineState
from vend.scenario import NashQuote, liar_disclosure, nash_quote
from vend.world import (TICKS_PER_DAY, WTP_MU, WTP_SIGMA, hour_of, rate_at,
                        wtp_mult_at)


def _profit_max_price(scale: float, cost: float) -> float:
    """argmax (p − cost) · SF(p) under the lognormal WTP prior — the
    capacity-free profit-optimal posted price for one crowd."""
    from scipy import stats
    from scipy.optimize import minimize_scalar
    res = minimize_scalar(
        lambda p: -(p - cost) * float(stats.lognorm.sf(p, s=WTP_SIGMA, scale=scale)),
        bounds=(cost, 4.0 * scale + cost), method="bounded")
    return float(res.x)



@dataclass
class StaticPolicy:
    """The control: a competent operator's fixed board (list = calibrated
    revenue-optimal all-day price; see world._revenue_optimal_list_price)."""
    policy_id: str = "static/1"

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        return {sku: (l.list_price, ["list price"])
                for sku, l in state.listings.items() if state.stock(sku) > 0}


@dataclass
class GvrPolicy:
    """Resolving Gallego–van Ryzin with the bid-price decomposition:

        price = clamp( max(p_hour, p_scarcity), floor, list )

    * p_hour — the unconstrained revenue-max price against the CURRENT
      hour's crowd (the 3pm stroller values a snack less than the lunch
      rush; when stock is slack, price each crowd on its own merits).
    * p_scarcity — the run-out price: the price at which expected demand
      over the units' remaining sell-window (to expiry, capped) just
      clears the stock on hand. Tight stock holds the price up — six
      sandwiches facing twelve willing buyers do NOT go on sale just
      because they expire tonight.

    The discount-only clamp eats all upside above list by design; the
    static list price is itself the calibrated all-day optimum, so every
    win over static is honest time/state discrimination, not a strawman.

    Model approximations (flagged in results): per-SKU demand share is
    uniform across SKUs; cross-hour consumer substitution not modeled.
    """
    policy_id: str = "gvr/1"
    _cache: dict = field(default_factory=dict)
    learner: "DemandLearner" = None    # set in __post_init__
    dow_mult: float = 1.0              # public calendar; runner sets daily

    def __post_init__(self):
        if self.learner is None:
            self.learner = DemandLearner()

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        board = {}
        mh = round(self.learner.mult_hat, 1)
        for sku, listing in state.listings.items():
            stock = state.stock(sku)
            if stock <= 0:
                continue
            dte = state.days_to_expiry(sku)
            key = (sku, stock, hour_of(state.tick), dte, state.day, mh,
                   round(self.dow_mult, 2))
            if key not in self._cache:
                self._cache[key] = self._solve(state, sku, stock, dte)
            board[sku] = self._cache[key]
        return board

    def _solve(self, state: MachineState, sku: str, stock: int,
               dte: int | None) -> tuple[float, list[str]]:
        from scipy import stats

        listing = state.listings[sku]
        n_skus = len(state.listings)

        # A unit expiring tonight is salvage-or-sold: its opportunity cost
        # is salvage. A durable unit displaces tomorrow's restock purchase:
        # its opportunity cost is unit_cost.
        c_eff = listing.salvage if (dte is not None and dte <= 0) else listing.unit_cost

        # p_hour: PROFIT-max against this hour's crowd, capacity-free.
        # Structural beliefs = the operator's estimate (not the truth).
        mu_est = listing.wtp_mu_est or WTP_MU[sku]
        mult_now = wtp_mult_at(state.tick)
        p_hour = _profit_max_price(mu_est * mult_now, c_eff)

        # p_scarcity: the run-out price over the stock's sell-window.
        # Restock is nightly (top-to-par), so stock on hand only competes
        # with the REST OF TODAY's demand; an unsold durable unit simply
        # displaces tomorrow's restock purchase (carry value = unit_cost,
        # which is already the floor). Expiry shows up in the floor, not
        # the window.
        window = list(range(state.tick, TICKS_PER_DAY))
        share = self.learner.share(sku, n_skus)
        scale_f = self.dow_mult * self.learner.mult_hat
        rates = [rate_at(t) / 6.0 * share * scale_f for t in window]
        lam_total = sum(rates)
        p_scar = 0.0
        if lam_total > 0 and stock < lam_total:
            mult_eff = (sum(r * wtp_mult_at(t) for r, t in zip(rates, window))
                        / lam_total)
            # SF(p_scar) = stock / lam_total  →  demand just clears stock.
            p_scar = float(stats.lognorm.isf(stock / lam_total, s=WTP_SIGMA,
                                             scale=mu_est * mult_eff))

        # Floor = the unit's opportunity cost (salvage when it dies tonight).
        raw = max(p_hour, p_scar)
        price = round(min(listing.list_price, max(raw, c_eff)), 2)

        h = hour_of(state.tick)
        if price >= listing.list_price:
            why = ["list price"]
            if p_scar > listing.list_price:
                why.append("stock tight vs demand ahead")
        else:
            why = [f"{'peak' if mult_now >= 1.0 else 'off-peak'} ({h}:00)",
                   f"stock {stock}/{listing.par_stock}"]
            if dte is not None and dte <= 2:
                why.append(f"expires in {dte} day{'s' if dte != 1 else ''}")
        return price, why


@dataclass
class A2APolicy:
    """Brokered A2A: every arrival's agent discloses to the neutral engine,
    which quotes the Nash point over the true joint frontier (scenario.py).
    The machine-face fallback is the plain sticker board — a consumer whose
    negotiation finds no mutual gain just shops the stickers, so the arm is
    never worse UX than static.

    attest=True: disclosures are verified (all truthful).
    attest=False: a `liar_share` of buyer agents run the anchoring attack
    (understate WTP, claim a free outside option) — the H3 experiment.
    """
    policy_id: str = "a2a-snhp/1"
    attest: bool = True
    liar_share: float = 0.0
    mode: str = "intent"
    learner: "DemandLearner" = None
    dow_mult: float = 1.0

    def __post_init__(self):
        if self.learner is None:
            self.learner = DemandLearner()

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        return {sku: (l.list_price, ["list price"])
                for sku, l in state.listings.items() if state.stock(sku) > 0}

    def quote_for(self, state: MachineState, consumer,
                  liar_roll: float) -> tuple[NashQuote, bool]:
        lied = (not self.attest) and liar_roll < self.liar_share
        if lied:
            wtp_d, walk_d = liar_disclosure(consumer.wtp, consumer.walk_cost)
        else:
            wtp_d, walk_d = consumer.wtp, consumer.walk_cost
        n = len(state.listings)
        return nash_quote(state, wtp_d, walk_d,
                          dow_mult=self.dow_mult,
                          mult_hat=self.learner.mult_hat,
                          share_fn=lambda s: self.learner.share(s, n)), lied


@dataclass
class DemandLearner:
    """What a real machine can actually know: today's crowd, inferred from
    arrivals seen so far (Gamma–Poisson posterior on the day's rate
    multiplier — the calendar's day-of-week effect is public and enters the
    base, so the posterior tracks the residual shock), and per-SKU demand
    shares learned by EWMA from the machine's OWN realized sales — the
    regime-consistent forecast that fixes P1's static-world assumption.
    WTP shocks stay unobserved (the machine sees feet, not wallets)."""
    prior_strength: float = 8.0     # pseudo-arrivals at multiplier 1
    share_ewma: float = 0.3

    def __post_init__(self):
        self._arr = 0.0
        self._base = 0.0
        self._shares: dict[str, float] = {}
        self._day_units: dict[str, float] = {}

    def begin_day(self):
        self._arr, self._base = 0.0, 0.0
        self._day_units = {}

    def observe_arrivals(self, expected_base: float, n: int):
        self._base += expected_base
        self._arr += n

    @property
    def mult_hat(self) -> float:
        return (self.prior_strength + self._arr) / (self.prior_strength + self._base)

    def sold(self, sku: str, units: int):
        self._day_units[sku] = self._day_units.get(sku, 0.0) + units

    def end_day(self):
        total = sum(self._day_units.values())
        if total <= 0:
            return
        for sku in set(self._shares) | set(self._day_units):
            obs = self._day_units.get(sku, 0.0) / total
            old = self._shares.get(sku)
            self._shares[sku] = obs if old is None else \
                (1 - self.share_ewma) * old + self.share_ewma * obs

    def share(self, sku: str, n_skus: int) -> float:
        # floored: a SKU with no sales history keeps a forecast pulse so its
        # stock isn't misread as pure excess
        if not self._shares:
            return 1.0 / n_skus
        return max(self._shares.get(sku, 1.0 / n_skus), 0.25 / n_skus)
