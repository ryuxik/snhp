"""Pricing policies — the four arms of the experiment behind one interface.

P0 ships the posted-board arms (static, gvr). The A2A and LLM arms (P1/P2)
implement the same interface but price per-intent instead of per-board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vend.core import MachineState
from vend.scenario import NashQuote, liar_disclosure, nash_quote
from vend.world import (QTY_CAP, QTY_DECAY, TICKS_PER_DAY, WTP_MU, WTP_SIGMA,
                        hour_of, rate_at, wtp_mult_at)


import functools


@functools.lru_cache(maxsize=8192)
def _profit_max_price(scale: float, cost: float) -> float:
    """argmax (p − cost) · SF(p) under the lognormal WTP prior — the
    capacity-free profit-optimal posted price for one crowd. Cached: only
    ~(skus × hour-multipliers × cost-states × mult-buckets) distinct inputs
    exist, and the scipy solve is the expensive part."""
    from scipy import stats
    from scipy.optimize import minimize_scalar
    res = minimize_scalar(
        lambda p: -(p - cost) * float(stats.lognorm.sf(p, s=WTP_SIGMA, scale=scale)),
        bounds=(cost, 4.0 * scale + cost), method="bounded")
    return float(res.x)



def sticker_board(state: MachineState) -> dict[str, tuple[float, list[str]]]:
    """THE sticker board — the control arm's product and every intent arm's
    fallback. One implementation so 'never worse UX than static' stays true
    by construction."""
    return {sku: (l.list_price, ["list price"])
            for sku, l in state.listings.items() if state.stock(sku) > 0}


@dataclass
class StaticPolicy:
    """The control: a competent operator's fixed board (list = calibrated
    PROFIT-optimal all-day price; see world._profit_optimal_list_price)."""
    policy_id: str = "static/1"

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        return sticker_board(state)


@dataclass
class GvrPolicy:
    """Resolving Gallego–van Ryzin with the bid-price decomposition:

        price = clamp( max(p_hour, p_scarcity), floor, list )

    * p_hour — the unconstrained PROFIT-max price against the CURRENT
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
    traffic_scale: float = 1.0         # calibrated-traffic knob; runner sets
                                       # daily from cfg (see run.py) — the
                                       # p_scarcity solve below is built off
                                       # the hot-profile rate_at() table, so a
                                       # thinned machine must scale it down or
                                       # scarcity pricing fires constantly
                                       # (it always "looks" demand-constrained)

    def __post_init__(self):
        if self.learner is None:
            self.learner = DemandLearner()

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        if getattr(self, "_cache_day", None) != state.day:
            self._cache.clear()          # day-stamped entries can never recur
            self._cache_day = state.day
        board = {}
        # Quantized context: the SOLVE uses these exact rounded values, so
        # the cache key fully determines the price (no first-tick-in-band
        # path dependence).
        mh = round(self.learner.mult_hat, 1)
        dm = round(self.dow_mult, 2)
        ts = round(self.traffic_scale, 3)
        for sku, listing in state.listings.items():
            stock = state.stock(sku)
            if stock <= 0:
                continue
            dte = state.days_to_expiry(sku)
            key = (sku, stock, hour_of(state.tick), dte, state.day, mh, dm, ts)
            if key not in self._cache:
                self._cache[key] = self._solve(state, sku, stock, dte, mh, dm, ts)
            board[sku] = self._cache[key]
        return board

    def _solve(self, state: MachineState, sku: str, stock: int,
               dte: int | None, mh: float, dm: float,
               ts: float = 1.0) -> tuple[float, list[str]]:
        from scipy import stats

        from vend.scenario import c_eff as _c_eff

        listing = state.listings[sku]
        n_skus = len(state.listings)
        c_eff = _c_eff(state, sku)

        # p_hour: PROFIT-max against this hour's crowd, capacity-free.
        # Structural beliefs = the operator's estimate (never the truth).
        mu_est = listing.wtp_mu_est
        if mu_est <= 0:
            raise ValueError(f"Listing {sku!r} has no operator demand estimate "
                             "— build catalogs via world.build_catalog")
        mult_now = wtp_mult_at(state.tick)
        p_hour = _profit_max_price(round(mu_est * mult_now, 6), round(c_eff, 6))

        # p_scarcity: the run-out price over the stock's sell-window.
        # Restock is nightly (top-to-par), so stock on hand only competes
        # with the REST OF TODAY's demand. The window starts at the CURRENT
        # HOUR's first tick — the same granularity as the cache key, so the
        # cached price is a pure function of the key.
        hour_start = (hour_of(state.tick) - 7) * 6
        window = list(range(hour_start, TICKS_PER_DAY))
        share = self.learner.share(sku, n_skus)
        rates = [rate_at(t) / 6.0 * share * dm * mh * ts for t in window]
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
class StrongPostedPolicy:
    """The STRONGEST posted baseline (referee item #48, CRITICAL-ANALYSIS §2):
    a choice-model-aware, JOINTLY-optimized board. The point of this arm is to
    give *inference* its best possible shot, so that "disclosure beats
    inference" is only claimed if the negotiation still wins after the posted
    arm is made as smart as a posted price can be.

    Where gvr fails (per RESULTS.md P0): it prices each SKU independently
    against a uniform per-SKU demand share, so an off-peak chips discount just
    diverts buyers who would have paid list for cola — cross-SKU
    cannibalization it cannot see. This arm fixes exactly that:

      (a) CHOICE MODEL — it models the buyer as choosing the best-surplus
          bundle across the WHOLE board (plus the bodega outside option),
          under the operator's own lognormal WTP belief — the same discrete
          choice the simulated consumer actually makes (world.best_bundle).
          A synthetic panel drawn from that belief (seeded → deterministic)
          stands in for the crowd; lowering one SKU's price steals demand
          from its substitutes in the panel, so substitution is priced in.
      (b) JOINT OPTIMIZATION — it optimizes the entire price vector together
          by coordinate ascent over the panel's expected profit, not SKU by
          SKU. Warm-started at the list board (itself the calibrated all-day
          optimum), every move it makes is a genuine cross-SKU improvement.
      (c) SAME INFORMATION AS A2A — the crowd belief uses the operator's
          wtp_mu_est (what set the sticker), and the scarcity shadow value
          uses `expected_list_demand` with the learner's mult_hat / share /
          daily — the IDENTICAL call the a2a arm makes in nash_quote. It sees
          the crowd; it just never sees the individual buyer's wallet. That
          missing individual signal is precisely the disclosure value the
          experiment isolates.

    Discount-only and floored at opportunity cost, like every arm. Model
    approximations (flagged, and symmetric with the a2a arm's own): the
    crowd is priced at the CURRENT hour's WTP multiplier (re-solved hourly);
    the scarcity shadow value is a smooth bid price sv = c_eff + (list −
    c_eff)·clip(D_list/stock, 0, 1) rather than the a2a arm's per-transaction
    excess split; today's unobserved WTP shock is not modeled (no arm sees
    it — the machine sees feet, not wallets)."""
    policy_id: str = "posted-strong/1"
    mode: str = "board"
    learner: "DemandLearner" = None
    dow_mult: float = 1.0
    traffic_scale: float = 1.0
    panel_size: int = 400
    rungs: int = 12
    sweeps: int = 3
    _cache: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.learner is None:
            self.learner = DemandLearner()
        self._panel = None           # (Z[C,S], walk[C], sku_order) — built lazily
        self._cache_day = None

    def _build_panel(self, skus: list[str]):
        import numpy as np
        # The operator's synthetic crowd: independent per-SKU lognormal WTP
        # multipliers + a walk-cost draw, from the STRUCTURAL distribution the
        # operator knows (world.WTP_SIGMA, walk ~ U[0.5,2.0]). Fixed seed →
        # the board is a pure function of state (deterministic, cacheable).
        rng = np.random.default_rng(20260710)
        C, S = self.panel_size, len(skus)
        Z = rng.lognormal(0.0, WTP_SIGMA, size=(C, S))
        walk = rng.uniform(0.5, 2.0, size=C)
        self._panel = (Z, walk, list(skus))

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        import numpy as np
        from vend.scenario import c_eff as _c_eff, expected_list_demand

        if self._cache_day != state.day:
            self._cache.clear()
            self._cache_day = state.day

        live = [s for s in state.listings if state.stock(s) > 0]
        if not live:
            return {}
        if self._panel is None or self._panel[2] != list(state.listings):
            self._build_panel(list(state.listings))

        mh = round(self.learner.mult_hat, 1)
        dm = round(self.dow_mult, 2)
        ts = round(self.traffic_scale, 3)
        stock_t = tuple(state.stock(s) for s in live)
        dte_t = tuple((state.days_to_expiry(s) or -99) for s in live)
        key = (tuple(live), stock_t, dte_t, hour_of(state.tick), state.day,
               mh, dm, ts)
        if key not in self._cache:
            self._cache[key] = self._solve(state, live, mh, dm, ts)
        return self._cache[key]

    def _solve(self, state, live, mh, dm, ts):
        import numpy as np
        from vend.scenario import c_eff as _c_eff, expected_list_demand

        Zfull, walk, order = self._panel
        idx = [order.index(s) for s in live]
        Z = Zfull[:, idx]                                   # [C, S_live]
        C, S = Z.shape
        n_all = len(state.listings)

        listings = state.listings
        mu = np.array([listings[s].wtp_mu_est for s in live])
        lp = np.array([listings[s].list_price for s in live])
        ce = np.array([_c_eff(state, s) for s in live])
        bod = np.array([listings[s].bodega_price for s in live])
        stk = np.array([state.stock(s) for s in live], dtype=float)

        # scarcity shadow value: same demand info the a2a arm uses (mult_hat,
        # share, daily) via the IDENTICAL expected_list_demand call.
        D = np.array([expected_list_demand(
            state, s, dow_mult=self.dow_mult, mult_hat=self.learner.mult_hat,
            share=self.learner.share(s, n_all), emp_daily=self.learner.daily(s),
            traffic_scale=self.traffic_scale) for s in live])
        sv = ce + (lp - ce) * np.clip(np.where(stk > 0, D / np.maximum(stk, 1e-9), 1.0),
                                      0.0, 1.0)

        mult_now = wtp_mult_at(state.tick)
        W = Z * (mu * mult_now)                             # [C, S] first-unit WTP
        qs = np.arange(1, QTY_CAP + 1)                      # [Q]
        G = np.cumsum(QTY_DECAY ** (qs - 1))                # bundle value multipliers
        BV = W[:, :, None] * G[None, None, :]               # [C, S, Q]
        # stock cap: qty q infeasible where q > stock
        qmask = qs[None, :] <= stk[:, None]                 # [S, Q]
        neg = -1e18

        # outside option: best bodega bundle surplus − walk (exactly run.py's
        # s_out; o_sku=None ⇒ s_out=0 handled by the >0 gate below)
        sur_bod = np.where(qmask[None], BV - qs[None, None, :] * bod[None, :, None], neg)
        best_bod = sur_bod.reshape(C, -1).max(axis=1)       # [C]
        s_out = np.where(best_bod > 0, best_bod - walk, 0.0)

        def objective(p):
            sur = np.where(qmask[None], BV - qs[None, None, :] * p[None, :, None], neg)
            sku_sur = sur.max(axis=2)                       # [C, S] best qty per SKU
            qbest = sur.argmax(axis=2) + 1                  # [C, S]
            s_in = sku_sur.max(axis=1)                      # [C]
            sbest = sku_sur.argmax(axis=1)                  # [C]
            buy = (s_in > 0) & (s_in >= s_out)
            csku = sbest[buy]
            cq = qbest[buy, csku]
            contrib = cq * (p[csku] - sv[csku])
            return float(contrib.sum()) / C

        # coordinate ascent, warm-started at the list board (the calibrated
        # all-day optimum) — every accepted move is a joint improvement.
        p = lp.copy()
        for _ in range(self.sweeps):
            for j in range(S):
                grid = np.linspace(ce[j], lp[j], self.rungs)
                best_v, best_p = -1e18, p[j]
                for cand in grid:
                    p[j] = cand
                    v = objective(p)
                    if v > best_v:
                        best_v, best_p = v, cand
                p[j] = best_p

        board = {}
        for j, s in enumerate(live):
            price = round(float(min(lp[j], max(p[j], ce[j]))), 2)  # plain float
            if price < lp[j] - 1e-9:
                why = ["choice-priced (whole-board)",
                       f"${lp[j] - price:.2f} under list"]
            else:
                why = ["list price"]
            board[s] = (price, why)
        return board


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
    traffic_scale: float = 1.0     # calibrated-traffic knob; runner sets
                                   # daily from cfg (see run.py) — feeds the
                                   # cold-start structural demand fallback in
                                   # expected_list_demand (scenario.py) so an
                                   # unsold SKU isn't read as list-bound
                                   # excess=0 against a hot-profile forecast
    # don't-negotiate-for-pennies, SCALED with transaction size (fairness v2:
    # a flat $1 was a 50% margin floor on a $2 item — it gated quotes away
    # from exactly the small-basket regulars the anchor shocks)
    min_gain: float = 0.75        # $ floor
    min_gain_frac: float = 0.15   # of the bundle's list value
    # Buffer frontier (documented, all points tested): $1 flat → control tie
    # (−$0.72) but gates quotes off small baskets (regulars unprotected);
    # 0.25/0.10 → full pool protection but −$5.43 control leak; 0.75/0.15 →
    # control −$1.98 [−2.70,−1.25] AND full pool protection at ×1.25 with
    # the ~+$33/day harvest intact. Perfect calibration doesn't exist in
    # the field; the ~2% concession buys the customer base.

    def __post_init__(self):
        if self.learner is None:
            self.learner = DemandLearner()

    def price_board(self, state: MachineState) -> dict[str, tuple[float, list[str]]]:
        return sticker_board(state)

    attack_factor: float = 0.55     # attack battery: disclosed-WTP scale
    attack_zero_walk: bool = True   # ...and whether liars claim a free outside

    def quote_for(self, state: MachineState, consumer,
                  liar_roll: float) -> tuple[NashQuote, bool]:
        from vend.scenario import strategic_disclosure
        lied = (not self.attest) and liar_roll < self.liar_share
        if lied:
            wtp_d, walk_d = strategic_disclosure(
                consumer.wtp, consumer.walk_cost,
                self.attack_factor, self.attack_zero_walk)
        else:
            wtp_d, walk_d = consumer.wtp, consumer.walk_cost
        n = len(state.listings)
        return nash_quote(state, wtp_d, walk_d,
                          dow_mult=self.dow_mult,
                          mult_hat=self.learner.mult_hat,
                          share_fn=lambda s: self.learner.share(s, n),
                          daily_fn=self.learner.daily,
                          min_gain=self.min_gain,
                          min_gain_frac=self.min_gain_frac,
                          traffic_scale=self.traffic_scale), lied


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
        self._daily: dict[str, float] = {}   # EWMA realized units/day (dow-normalized)
        self._dow_today = 1.0

    def begin_day(self, dow_mult: float = 1.0):
        self._arr, self._base = 0.0, 0.0
        self._day_units = {}
        self._dow_today = max(dow_mult, 1e-6)

    def observe_arrivals(self, expected_base: float, n: int):
        self._base += expected_base
        self._arr += n

    @property
    def mult_hat(self) -> float:
        return (self.prior_strength + self._arr) / (self.prior_strength + self._base)

    def sold(self, sku: str, units: int):
        self._day_units[sku] = self._day_units.get(sku, 0.0) + units

    def end_day(self, censored: frozenset = frozenset()):
        """`censored`: SKUs that SOLD OUT today. A sellout truncates observed
        sales below true demand; treating it as a demand observation drags
        the estimate down exactly where it should go up — and the Nash
        search then fires where the forecast hallucinates excess (adverse
        selection on our own noise, found by the Block twin-run). Censored
        days may only RAISE the level estimate, never lower it."""
        total = sum(self._day_units.values())
        if total > 0:
            for sku in set(self._shares) | set(self._day_units):
                obs = self._day_units.get(sku, 0.0) / total
                old = self._shares.get(sku)
                self._shares[sku] = obs if old is None else \
                    (1 - self.share_ewma) * old + self.share_ewma * obs
        # regime-consistent demand level: realized units/day in THIS ARM's
        # world (dow-normalized), not a static-world formula — the fix for
        # the self-invalidating displacement forecast
        for sku in set(self._daily) | set(self._day_units):
            obs = self._day_units.get(sku, 0.0) / self._dow_today
            old = self._daily.get(sku)
            if old is None:
                self._daily[sku] = obs
            elif sku in censored:
                # demand ≥ observed sales, strictly (we ran out): escalate
                # until sellouts stop — under permanent censoring a flat
                # max() anchors on the first truncated day forever
                self._daily[sku] = max(old, obs) * 1.2
            else:
                self._daily[sku] = (1 - self.share_ewma) * old \
                    + self.share_ewma * obs

    def daily(self, sku: str) -> float | None:
        """EWMA realized units/day for this SKU in this arm's own regime
        (None until a day of history exists)."""
        return self._daily.get(sku)

    def share(self, sku: str, n_skus: int) -> float:
        # floored: a SKU with no sales history keeps a forecast pulse so its
        # stock isn't misread as pure excess
        if not self._shares:
            return 1.0 / n_skus
        return max(self._shares.get(sku, 1.0 / n_skus), 0.25 / n_skus)
