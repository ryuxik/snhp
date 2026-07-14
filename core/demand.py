"""The pluggable, learned DEMAND / WTP-DISCOVERY model — the *what-does-the-
buyer-actually-pay* half of the unified engine, the online mirror of the cost
model (core/cost.py).

Every shipped sim prices against an ORACLE willingness-to-pay: the engine's
`Buyer.value(graph, config)` returns the buyer's TRUE per-config dollar value,
and `Buyer.outside_surplus()` their true outside option. Production cannot see
a wallet. It sees only QUOTE OUTCOMES — for each (config, price) it offered,
did the buyer accept, reject, or walk — and those are CENSORED: an accept says
value ≥ price at the OFFERED rung, a reject says value < it, never the exact
value. This module LEARNS the WTP scale from that censored stream and hands the
engine an estimate to use IN PLACE OF the oracle.

The four bespoke WTP inversions this generalizes (lift, don't reinvent):

  boba.world.appeal_for_list   invert a calibration menu to the WTP scale at
                               which a list price is profit-optimal (BATCH,
                               offline). -> `choice_share_inversion`, made
                               ONLINE: the WTP scale from observed CHOICE
                               SHARES / accept-at-list, updated per arrival.
  vend.policies.DemandLearner  EWMA of arrivals / per-SKU share feeding the
                               scarcity shadow. -> `EwmaRate`.
  buyer.preflearn.Posterior-   a censored Bayesian grid posterior over log-WTP
    Learner (update_accept)    from accept/reject. -> `AcceptCurve` (the heart):
                               a censored interval estimator that recovers the
                               WTP DISTRIBUTION from (offered rung, accepted?).
  boba.suggest (learned-when)  per-observable-bucket EV, train-on-past/deploy-
                               on-future. -> `ContextGate`: which contexts a
                               lever actually pays.

── how the estimate enters the engine (additive, IC-preserving) ─────────────

The engine takes an OPTIONAL `demand: DemandModel | None`. Default None → the
oracle path, byte-identical. When supplied, `demand.as_buyer(...)` wraps the
caller's buyer: `value`/`outside_surplus` come from the posterior, while the
OBSERVABLE structural fields (balk from the queue, the population qty decay and
defer schedule) pass through unchanged. The whole existing IC machinery then
runs against the LEARNED values with ZERO new code: the menu counterfactual,
refuse-lookers, never-above-list and the min-gain floor all read `buyer.value`.

How much of the IC floor is structural (and the one channel that ISN'T): the
seller's disagreement `d_seller = surv·(list − cost)` and every feasibility
test `gs = surv·(p − cost) + credit − d_seller ≥ {0, min_gain}` are computed on
OBSERVABLES — the shop's own menu list price and ingredient cost — NEVER on the
learned value. So the DOLLAR level of the standing margin is protected exactly:
a deal cannot be priced below `d_seller + min_gain` no matter how wrong the WTP
estimate is. The value estimate only chooses (a) whether to classify the
arrival as a menu-buyer or a refused looker, (b) where in [cost, list] the Nash
price lands, and (c) WHICH config is taken to be the buyer's menu counterfactual
(the argmax of estimated value − list). (c) is the residual leak channel: when
the population estimate misidentifies a rich cart's menu config, `d_seller` is
set against the WRONG (cheaper, lower-margin) config, and a deal can undercut
the buyer's TRUE standing margin. `core/adapters/tests/demand_validation.py`
measures it in sim: $0 under the oracle by construction, and — the honest
finding — a SMALL residual (~0.05% of margin, ~5% of menu-buyer deals, on
multi-topping carts) under honest learning, $0 under the ratchet (its
over-discounting makes the engine refuse deals). The floor is nearly, not
exactly, preserved; the harness reports the number, never tunes it away.

No new dependencies (numpy only, already present).
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np

from core.engine import Buyer, qty_ladder
from core.offer_graph import (Config, DimKind, OfferGraph, qty_of,
                              selected_option_ids)
from core.state import ShopState


# ── the observed signal ──────────────────────────────────────────────────
class Outcome(enum.Enum):
    """What a realized quote produced. CENSORED: an ACCEPT reveals value ≥ the
    offered price at that rung, a REJECT reveals value < it; WALK is a buyer
    who took neither this quote nor the sticker (their outside option won) —
    an accept/reject at their best AVAILABLE list rung, the choice-share
    signal `choice_share_inversion` reads."""
    ACCEPT = "accept"
    REJECT = "reject"
    WALK = "walk"


# ── the structural value template (scale-1 = the calibration population) ──
class AppealShape(Protocol):
    """The KNOWN shape of a config's value, at unit WTP scale. Learning a
    SCALE on top of a structural shape is exactly what appeal_for_list does
    offline (it inverts the shape — the calibrated menu — to the scale); here
    the shape is fixed and the scale is learned online. `value(config) = scale
    · appeal(graph, config, decay)`, so the scale is the qty-INDEPENDENT
    value/list ratio (the qty ladder lives in the shape, matching how
    core.engine.SeparableBuyer.value actually scales)."""
    def appeal(self, graph: OfferGraph, config: Config, decay: float) -> float: ...


@dataclass(frozen=True)
class ListAppeal:
    """The default, vertical-agnostic shape: appeal = (per-unit list value of
    the chosen options) · qty_ladder(decay, qty). Scale-1 ⇒ value = the
    sticker (a buyer who values the cart at exactly list). No vertical
    constants — the learned scale is the population's value/list ratio, and
    context bucketing (hour, choice) captures whatever structure the menu's
    flat sticker cannot.

    `hour_mult(context)` optionally folds a PUBLIC, observable demand
    multiplier (boba's HOURLY_WTP_MULT, a calendar fact) into the shape so it
    is not left for the scale to relearn per hour."""
    hour_mult: Callable[[object], float] | None = None

    def _perunit_list(self, graph: OfferGraph, config: Config) -> float:
        total = 0.0
        for dim in graph.dims:
            if dim.kind == DimKind.QUANTITY:
                continue
            for oid in selected_option_ids(dim, config.get(dim.id)):
                total += dim.option(oid).price_delta
        return total

    def appeal(self, graph: OfferGraph, config: Config, decay: float) -> float:
        q = qty_of(graph, config)
        base = self._perunit_list(graph, config) * qty_ladder(decay, q)
        return base


@dataclass
class CallableAppeal:
    """An AppealShape from a plain function — the escape hatch a vertical uses
    to supply its OWN calibrated shape (boba's DRINK_APPEAL/TOP_APPEAL ×
    hour multiplier), so scale-1 is that vertical's calibration population."""
    fn: Callable[[OfferGraph, Config, float, object], float]
    context: object = None

    def appeal(self, graph: OfferGraph, config: Config, decay: float) -> float:
        return self.fn(graph, config, decay, self.context)


# ══════════════════════════════════════════════════════════════════════════
# composable components
# ══════════════════════════════════════════════════════════════════════════

# ── ewma_rate — vend's arrival / multiplier learner ──────────────────────
@dataclass
class EwmaRate:
    """vend.policies.DemandLearner.mult_hat, distilled: a Gamma–Poisson
    posterior on the day's arrival-rate multiplier from arrivals seen so far,
    plus an EWMA of a realized per-context RATE. The demand model exposes it
    for parity with the vend scarcity shadow (a thinner crowd both lowers WTP
    pressure and, via the cost side, the displacement forecast); it does not
    itself price. `prior_strength` pseudo-arrivals anchor the multiplier at 1
    before evidence."""
    prior_strength: float = 8.0
    ewma: float = 0.3
    _arr: float = 0.0
    _base: float = 0.0
    _rate: dict = field(default_factory=dict)

    def begin_day(self) -> None:
        self._arr = 0.0
        self._base = 0.0

    def observe_arrivals(self, expected_base: float, n: int) -> None:
        self._base += expected_base
        self._arr += n

    @property
    def mult_hat(self) -> float:
        return (self.prior_strength + self._arr) / (self.prior_strength + self._base)

    def observe_rate(self, key, value: float) -> None:
        old = self._rate.get(key)
        self._rate[key] = value if old is None else \
            (1 - self.ewma) * old + self.ewma * value

    def rate(self, key) -> float | None:
        return self._rate.get(key)


# ── accept_curve — the censored WTP-scale estimator (the heart) ──────────
@dataclass
class AcceptCurve:
    """A CENSORED Bayesian grid posterior over the log WTP-SCALE m of one
    context. Each observation is (normalized price x = offered_price /
    structural appeal, accepted?): an interval-censored draw of a per-buyer
    scale θ ~ lognormal(median = e^m, σ = sigma_pop). Since a buyer accepts
    iff θ·appeal ≥ price iff θ ≥ x,

        P(accept at x | m) = P(θ ≥ x | m) = Φ( (m − ln x) / sigma_pop ),

    a probit in log-price. The posterior over m is a grid (exact, degeneracy-
    free — the same factorized-grid machinery as buyer.preflearn.Posterior-
    Learner, one dimension). `sigma_pop` is the KNOWN structural spread of the
    population's value/list ratio (a calibration constant, like preflearn's
    WTP_SIGMA / QTY_DECAY), so what is learned is the MEDIAN scale, from
    accept/reject alone. This is `appeal_for_list` made online and two-sided:
    appeal_for_list inverts one calibrated price to a scale; this inverts a
    stream of censored (price, accept?) pairs to the scale posterior.

    `noise_tau` softens the step probit into a logistic-probit blend so a
    near-boundary accept/reject is not treated as infinitely informative
    (buyers are imprecise, not omniscient — preflearn's ACCEPT_TAU)."""
    sigma_pop: float = 0.45
    prior_m: float = 0.0          # log-scale prior mean: 1.0 ⇒ list-calibrated
    prior_sigma: float = 0.8      # prior spread on the median log-scale
    grid_n: int = 81
    grid_span: float = 5.0        # ± sigmas of prior the grid spans
    noise_tau: float = 0.06       # answer-noise width on the normalized margin

    def __post_init__(self):
        lo = self.prior_m - self.grid_span * self.prior_sigma
        hi = self.prior_m + self.grid_span * self.prior_sigma
        self.grid_m = np.linspace(lo, hi, self.grid_n)
        w = np.exp(-0.5 * ((self.grid_m - self.prior_m) / self.prior_sigma) ** 2)
        self.w = w / w.sum()
        self.n_obs = 0

    def copy(self) -> "AcceptCurve":
        c = AcceptCurve.__new__(AcceptCurve)
        c.__dict__.update(self.__dict__)
        c.w = self.w.copy()
        return c

    def _p_accept_grid(self, x: float) -> np.ndarray:
        """P(accept at normalized price x | m) over the grid. The probit is
        smoothed by `noise_tau`: margin = m − ln x, converted to a probability
        by a logistic on the margin plus the structural probit, so both the
        population spread (sigma_pop) and answer noise (noise_tau) enter."""
        if x <= 1e-12:
            return np.ones_like(self.grid_m)
        margin = self.grid_m - math.log(x)                 # log-scale surplus
        # structural probit (population spread) blended with answer-noise logit
        probit = 0.5 * (1.0 + np.vectorize(math.erf)(
            margin / (self.sigma_pop * math.sqrt(2.0))))
        logit = 1.0 / (1.0 + np.exp(-np.clip(margin / self.noise_tau, -60, 60)))
        return np.clip(0.5 * (probit + logit), 1e-9, 1 - 1e-9)

    def observe(self, x: float, accepted: bool) -> None:
        like = self._p_accept_grid(x)
        nw = self.w * (like if accepted else (1.0 - like))
        z = nw.sum()
        if z > 1e-300:
            self.w = nw / z
            self.n_obs += 1

    # point estimates over the per-buyer scale θ (predictive, not just m) ----
    def scale_median(self) -> float:
        """Posterior-mean of the MEDIAN scale e^m — the typical buyer's
        value/list ratio at this context. The conservative estimate (half the
        population values the config at least this much), and the natural point
        the engine prices a no-wallet-visibility crowd at."""
        return float(self.w @ np.exp(self.grid_m))

    def scale_quantile(self, q: float) -> float:
        """The q-quantile of the PREDICTIVE per-buyer scale θ (marginalizing
        the posterior on m over the lognormal population spread). q=0.5 ≈
        scale_median; a lower q is a conservative value estimate that tightens
        the refuse-lookers floor against a noisy posterior."""
        z = _norm_ppf(q)
        # per-grid median e^m shifted by the population quantile e^{z·sigma}
        theta = np.exp(self.grid_m + z * self.sigma_pop)
        return float(self.w @ theta)

    def uncertainty(self) -> float:
        """Posterior sd of m — how unsure the scale still is (feeds the gate)."""
        m = float(self.w @ self.grid_m)
        return float(math.sqrt(max(0.0, self.w @ (self.grid_m - m) ** 2)))


def _norm_ppf(q: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation) — avoids a
    scipy import on the hot path. |error| < 1.2e-9 on (0,1)."""
    if q <= 0.0:
        return -8.0
    if q >= 1.0:
        return 8.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if q < plow:
        r = math.sqrt(-2 * math.log(q))
        return (((((c[0]*r+c[1])*r+c[2])*r+c[3])*r+c[4])*r+c[5]) / \
               ((((d[0]*r+d[1])*r+d[2])*r+d[3])*r+1)
    if q > phigh:
        r = math.sqrt(-2 * math.log(1 - q))
        return -(((((c[0]*r+c[1])*r+c[2])*r+c[3])*r+c[4])*r+c[5]) / \
                ((((d[0]*r+d[1])*r+d[2])*r+d[3])*r+1)
    r = q - 0.5
    t = r * r
    return (((((a[0]*t+a[1])*t+a[2])*t+a[3])*t+a[4])*t+a[5]) * r / \
           (((((b[0]*t+b[1])*t+b[2])*t+b[3])*t+b[4])*t+1)


# ── choice_share_inversion — population WTP scale from choice shares ─────
def choice_share_inversion(observations, sigma_pop: float = 0.45,
                           prior_m: float = 0.0, prior_sigma: float = 0.8
                           ) -> float:
    """appeal_for_list generalized ONLINE and two-sided: recover the
    population WTP-scale (value/list ratio) from a stream of CHOICE SHARES.
    `observations` is an iterable of (normalized_price, accepted?) — a bought-
    at-list is an accept, a walked-away is a reject at their best list rung.
    Offline this is exactly the menu inversion (feed the calibrated accept-
    fraction at list); online it is the running posterior. Returns the median
    scale. Thin wrapper over AcceptCurve so the two share one likelihood."""
    curve = AcceptCurve(sigma_pop=sigma_pop, prior_m=prior_m,
                        prior_sigma=prior_sigma)
    for x, acc in observations:
        curve.observe(x, bool(acc))
    return curve.scale_median()


# ── context_gate — boba-suggest's learned-when ───────────────────────────
@dataclass
class ContextGate:
    """boba.suggest's learned table, distilled: per-observable-bucket mean
    realized NET GAIN of attempting the lever (a negotiation / a deferred
    slot), with a min-sample trust floor and a pooled fallback. The demand
    model consults it to decide whether a context has EARNED a deviation from
    the plain menu — the online 'which contexts a lever actually pays.' It
    gates ATTEMPTS, never prices (pricing stays the IC-guarded Nash split), so
    a wrong gate costs a missed deal, never a leak."""
    min_bucket: int = 20
    threshold: float = 0.0
    _sum: dict = field(default_factory=dict)
    _cnt: dict = field(default_factory=dict)
    _psum: float = 0.0
    _pcnt: int = 0

    def observe(self, key, net_gain: float) -> None:
        self._sum[key] = self._sum.get(key, 0.0) + net_gain
        self._cnt[key] = self._cnt.get(key, 0) + 1
        self._psum += net_gain
        self._pcnt += 1

    def ev(self, key) -> float:
        n = self._cnt.get(key, 0)
        if n >= self.min_bucket:
            return self._sum[key] / n
        return self._psum / self._pcnt if self._pcnt else 0.0

    def open(self, key) -> bool:
        """Warmup (no pooled evidence yet) opens the gate — you cannot learn
        when a lever pays without trying it. After that, open iff the bucket's
        (or pooled) EV clears the threshold."""
        if self._pcnt < self.min_bucket:
            return True
        return self.ev(key) >= self.threshold


# ══════════════════════════════════════════════════════════════════════════
# the posterior the engine reads, and the estimated buyer it wraps
# ══════════════════════════════════════════════════════════════════════════
@dataclass
class BuyerPosterior:
    """The current best estimate the engine uses IN PLACE OF oracle WTP: a
    scalar value SCALE for this context, the structural appeal shape, and the
    estimated outside surplus. `value_of` maps a config to dollars exactly as
    core.engine.SeparableBuyer.value would, with the learned scale standing in
    for the unseen wallet."""
    scale: float
    outside: float
    appeal: AppealShape
    decay: float

    def value_of(self, graph: OfferGraph, config: Config) -> float:
        return self.scale * self.appeal.appeal(graph, config, self.decay)


@dataclass
class _EstimatedBuyer:
    """A core.engine.Buyer whose VALUE and OUTSIDE come from the posterior and
    whose STRUCTURAL fields (qty decay, balk, defer) are the OBSERVABLE ones
    the caller supplies — the shop sees its own queue (balk) and knows the
    population's decay/defer mix, but never this wallet. Drop-in: the engine's
    entire IC machinery reads it with no change."""
    post: BuyerPosterior
    qty_decay: float
    balk: float
    defer: dict

    def value(self, graph: OfferGraph, config: Config) -> float:
        return self.post.value_of(graph, config)

    def outside_surplus(self) -> float:
        return self.post.outside

    def balk_prob(self, state: ShopState) -> float:
        return self.balk

    def defer_cost(self, slot: int) -> float:
        return self.defer.get(slot, 0.0)


# ══════════════════════════════════════════════════════════════════════════
# the DemandModel protocol + the concrete learned model
# ══════════════════════════════════════════════════════════════════════════
class DemandModel(Protocol):
    """Composable, state-dependent WTP estimator — the online mirror of
    core.cost.CostModel."""
    def observe(self, context, offered_config: Config, offered_price: float,
                outcome: Outcome) -> None: ...
    def buyer_posterior(self, context) -> BuyerPosterior: ...
    def expected_value(self, graph: OfferGraph, config: Config,
                       context) -> float: ...
    def as_buyer(self, graph: OfferGraph, state: ShopState,
                 buyer: Buyer, context) -> Buyer: ...


@dataclass
class LearnedDemand:
    """The concrete learned WTP model: one AcceptCurve per context bucket
    (censored, online), an optional EwmaRate (vend parity), a ContextGate
    (learned-when), all over a shared structural AppealShape. The estimate it
    hands the engine is the population value/list scale at the arrival's
    context — never a wallet, because production has none.

    Parameters
      appeal        the structural value shape (default ListAppeal — generic).
      sigma_pop     known population spread of the value/list ratio.
      decay         the population qty decay (a structural constant, like
                    preflearn's known QTY_DECAY).
      bucket_of     context -> hashable bucket key (default identity); coarser
                    buckets learn faster, finer ones capture more structure.
      value_quantile which predictive quantile of the per-buyer scale to price
                    at. 0.5 (median) is the honest 'typical buyer' and keeps
                    the refuse-lookers floor conservative; a lower value trades
                    deals for an even tighter IC margin against a noisy start.
      prior_m/prior_sigma  the scale prior (m=0 ⇒ list-calibrated).
    """
    appeal: AppealShape = field(default_factory=ListAppeal)
    sigma_pop: float = 0.45
    decay: float = 0.15
    bucket_of: Callable[[object], object] | None = None
    value_quantile: float = 0.5
    prior_m: float = 0.0
    prior_sigma: float = 0.8
    grid_n: int = 81
    noise_tau: float = 0.06
    gate: ContextGate = None
    rate: EwmaRate = None

    def __post_init__(self):
        self._curves: dict = {}
        if self.gate is None:
            self.gate = ContextGate()
        if self.rate is None:
            self.rate = EwmaRate()

    # ── bucketing ──
    def _bucket(self, context):
        return self.bucket_of(context) if self.bucket_of is not None else context

    def _curve(self, context) -> AcceptCurve:
        b = self._bucket(context)
        c = self._curves.get(b)
        if c is None:
            c = AcceptCurve(sigma_pop=self.sigma_pop, prior_m=self.prior_m,
                            prior_sigma=self.prior_sigma, grid_n=self.grid_n,
                            noise_tau=self.noise_tau)
            self._curves[b] = c
        return c

    # ── the learned scale for a context ──
    def scale(self, context) -> float:
        return self._curve(context).scale_quantile(self.value_quantile)

    # ── DemandModel API ──
    def observe(self, context, offered_config: Config, offered_price: float,
                outcome: Outcome, *, graph: OfferGraph = None) -> None:
        """Fold a realized quote outcome into the context's AcceptCurve. The
        normalized price x = offered_price / appeal(config); an ACCEPT is a
        censored 'θ ≥ x', a REJECT / WALK a censored 'θ < x'. `graph` is
        required to compute the appeal of `offered_config` (the caller passes
        the graph it quoted on)."""
        if graph is None or offered_config is None:
            return
        a = self.appeal.appeal(graph, offered_config, self.decay)
        if a <= 1e-12:
            return
        x = offered_price / a
        self._curve(context).observe(x, outcome is Outcome.ACCEPT)

    def buyer_posterior(self, context, *, outside: float = 0.0) -> BuyerPosterior:
        return BuyerPosterior(scale=self.scale(context), outside=outside,
                              appeal=self.appeal, decay=self.decay)

    def expected_value(self, graph: OfferGraph, config: Config, context) -> float:
        return self.scale(context) * self.appeal.appeal(graph, config, self.decay)

    def as_buyer(self, graph: OfferGraph, state: ShopState, buyer: Buyer,
                 context) -> Buyer:
        """Wrap `buyer`: value/outside from the posterior, structural fields
        (qty decay, balk, defer) taken from the OBSERVABLE buyer the caller
        supplies. The caller is responsible for passing a buyer whose decay/
        balk/defer are the population/observable ones (never the true wallet's)
        — this is the whole point of the WTP-discovery layer, and the sim
        harness constructs exactly such an observable shell."""
        # outside: price the buyer's outside option at the learned scale on the
        # engine's own graph — the same scale, evaluated over the offer set,
        # gives a self-consistent d_buyer without a separate oracle.
        outside = self._outside_estimate(graph, state, buyer, context)
        post = self.buyer_posterior(context, outside=outside)
        decay = getattr(buyer, "qty_decay", self.decay)
        balk = buyer.balk_prob(state)
        defer = {s: buyer.defer_cost(s) for s in _defer_slots(graph)}
        return _EstimatedBuyer(post=post, qty_decay=decay, balk=balk, defer=defer)

    def _outside_estimate(self, graph, state, buyer, context) -> float:
        """The learned outside surplus. The buyer's outside option is priced by
        the SAME scale; with no separate competitor board wired in, the engine
        adapter supplies it via `buyer.outside_surplus()` on the observable
        shell (a population outside estimate). Defaults to that shell's value —
        the caller keeps outside estimation in one place."""
        try:
            return float(buyer.outside_surplus())
        except Exception:
            return 0.0


def _defer_slots(graph: OfferGraph) -> tuple[int, ...]:
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            return tuple(o.slot_ticks for o in d.options)
    return (0,)
