"""Tests for the learned WTP-discovery layer (core/demand.py) + its engine
wiring. Four claims:

  1. the CENSORED accept_curve recovers a KNOWN WTP distribution to tolerance;
  2. the posterior CONVERGES to the population oracle under an honest stream;
  3. supplying `demand=None` is BYTE-IDENTICAL to the oracle path (additive);
  4. the IC leak stays $0 — a PROPERTY test over generated buyers: when the
     engine prices a LEARNED posterior with refuse-lookers, every accepted deal
     clears the buyer's TRUE standing menu margin (the invariant survives
     learning because the seller disagreement is on OBSERVABLES, not the
     estimate).

Pure stdlib + numpy (already present); reuses core/tests/generators.py.
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from core.demand import (AcceptCurve, BuyerPosterior, ContextGate, EwmaRate,
                         LearnedDemand, ListAppeal, Outcome,
                         choice_share_inversion, _norm_ppf)
from core.engine import QuoteOpts, SeparableBuyer, qty_ladder
from core.engine import quote as core_quote
from core.offer_graph import DimKind, qty_of
from core.tests.generators import generate


# ── 1. the censored accept_curve recovers a KNOWN WTP distribution ─────────
@pytest.mark.parametrize("true_scale", [0.7, 1.0, 1.4])
def test_accept_curve_recovers_known_scale(true_scale):
    """Buyers have a value/list ratio θ ~ lognormal(median=true_scale, σ). The
    curve sees only (normalized price x, accept = θ≥x) and must recover the
    median to within 5%."""
    sigma = 0.40
    rng = np.random.default_rng(11)
    curve = AcceptCurve(sigma_pop=sigma, prior_m=0.0, prior_sigma=0.9)
    for _ in range(6000):
        theta = true_scale * math.exp(rng.normal(0.0, sigma))
        x = math.exp(rng.normal(0.0, 0.6))          # a spread of offered rungs
        curve.observe(x, theta >= x)
    est = curve.scale_median()
    assert abs(est - true_scale) / true_scale < 0.05, (true_scale, est)


def test_accept_curve_is_censored_interval_estimator():
    """A pure interval-censoring sanity check (no logistic noise limit): if
    every buyer has EXACTLY θ=1.0, accepts below 1 and rejects above 1 pin the
    median to ~1.0 from two-sided censoring alone."""
    curve = AcceptCurve(sigma_pop=0.25, prior_m=0.4, prior_sigma=1.0)
    rng = np.random.default_rng(3)
    for _ in range(3000):
        x = math.exp(rng.normal(0.0, 0.4))
        curve.observe(x, 1.0 >= x)                   # deterministic threshold
    assert abs(curve.scale_median() - 1.0) < 0.05


def test_choice_share_inversion_matches_curve():
    """choice_share_inversion is the online appeal_for_list — it must agree
    with an AcceptCurve fed the same censored (price, accept) stream."""
    rng = np.random.default_rng(5)
    obs = []
    for _ in range(4000):
        theta = 1.2 * math.exp(rng.normal(0.0, 0.45))
        x = math.exp(rng.normal(0.0, 0.6))
        obs.append((x, theta >= x))
    s = choice_share_inversion(obs, sigma_pop=0.45)
    assert abs(s - 1.2) / 1.2 < 0.06


def test_norm_ppf_accuracy():
    assert abs(_norm_ppf(0.5)) < 1e-9
    assert abs(_norm_ppf(0.975) - 1.959963985) < 1e-6
    assert abs(_norm_ppf(0.025) + 1.959963985) < 1e-6


# ── 2. the posterior converges to the population oracle ────────────────────
def test_posterior_converges_to_population_oracle():
    """On a one-CHOICE graph with a KNOWN population value/list ratio, the
    LearnedDemand's expected_value converges to the population-mean oracle
    value from accept/reject alone."""
    from core.offer_graph import Dimension, Option, OfferGraph
    from core.deps import DepGraph
    from core.cost import compose, const
    graph = OfferGraph(
        dims=[Dimension("d", DimKind.CHOICE,
                        options=(Option("a", price_delta=4.0, unit_cost=1.0),)),
              Dimension("qty", DimKind.QUANTITY, qty_cap=1)],
        deps=DepGraph(), cost=compose(const()), name="mini")
    cfg = {"d": "a", "qty": 1}
    true_scale, sigma = 1.25, 0.35
    dm = LearnedDemand(appeal=ListAppeal(), sigma_pop=sigma, decay=0.0,
                       prior_m=0.0, prior_sigma=0.9)
    appeal = ListAppeal().appeal(graph, cfg, 0.0)        # == 4.0 (list value)
    rng = np.random.default_rng(7)
    for _ in range(5000):
        theta = true_scale * math.exp(rng.normal(0.0, sigma))
        true_value = theta * appeal
        price = appeal * math.exp(rng.normal(0.0, 0.5))
        dm.observe("ctx", cfg, price, Outcome.ACCEPT if true_value >= price
                   else Outcome.REJECT, graph=graph)
    est = dm.expected_value(graph, cfg, "ctx")
    pop_oracle = true_scale * appeal                     # population-mean value
    assert abs(est - pop_oracle) / pop_oracle < 0.06, (est, pop_oracle)


# ── 3. demand=None is byte-identical to the oracle path (additive) ─────────
def test_demand_none_byte_identical():
    """The engine with demand=None must return EXACTLY the default quote — the
    additivity guarantee that keeps the core suite green."""
    for seed in range(60):
        case = generate(seed)
        q0 = core_quote(case.graph, case.state, case.buyer, opts=case.opts)
        q1 = core_quote(case.graph, case.state, case.buyer, opts=case.opts,
                        demand=None)
        if q0 is None:
            assert q1 is None
            continue
        assert q1 is not None
        assert q0.config == q1.config
        assert q0.price == q1.price
        assert q0.feasible == q1.feasible
        assert q0.seller_gain == q1.seller_gain


# ── 4. the IC leak stays $0 under a learned posterior (property test) ───────
# The invariant that matters: a TRUE menu-buyer (someone who would pay the
# sticker) must never be discounted out of the shop's STANDING margin, even
# when a badly-mistrained posterior prices the deal. We exercise it on a
# capacity-smoothing graph — a deferred slot with a relief credit — the exact
# lever that lets a menu-buyer get a deal under refuse-lookers (the boba
# deferral channel), then sweep an ADVERSARIAL learned scale AND the buyer's
# true value, and confirm every accepted menu-buyer deal has $0 leak.
def _smoothing_graph():
    from core.offer_graph import Dimension, Option, OfferGraph
    from core.deps import DepGraph
    from core.cost import capacity_relief, compose, const

    def relief(graph, state, config, qty):
        for d in graph.dims:
            if d.kind == DimKind.FULFILLMENT:
                opt = d.option(config[d.id])
                if not opt.immediate and opt.slot_ticks > 0:
                    return qty * 0.8            # a peak-capacity relief credit
        return 0.0

    return OfferGraph(
        dims=[Dimension("drink", DimKind.CHOICE,
                        options=(Option("tea", price_delta=5.0, unit_cost=1.5),)),
              Dimension("top", DimKind.ADDON,
                        options=(Option("pearls", price_delta=1.0, unit_cost=0.3),)),
              Dimension("slot", DimKind.FULFILLMENT,
                        options=(Option("now", immediate=True, slot_ticks=0),
                                 Option("later", immediate=False, slot_ticks=3))),
              Dimension("qty", DimKind.QUANTITY, qty_cap=2)],
        deps=DepGraph(), cost=compose(const(), capacity_relief(relief)),
        name="smoothing")


def _observable_shell(buyer: SeparableBuyer) -> SeparableBuyer:
    """A shell carrying only OBSERVABLE structural fields (decay, balk, defer),
    no wallet — exactly what a demand-driven engine sees in production."""
    return SeparableBuyer(values={}, qty_decay=buyer.qty_decay,
                          outside=0.0, balk=buyer.balk, defer=dict(buyer.defer))


_CASES = [(scale, drink_v, top_v)
          for scale in (0.5, 0.7, 0.9, 1.1, 1.3, 1.6)
          for drink_v in (5.5, 7.0, 9.0)
          for top_v in (0.6, 1.2, 2.0)]


@pytest.mark.parametrize("scale,drink_v,top_v", _CASES)
def test_ic_leak_zero_under_learned_posterior(scale, drink_v, top_v):
    """PROPERTY (the standing-margin-LEVEL channel): on the capacity-smoothing
    graph, a true menu-buyer priced by an ADVERSARIAL learned SCALE is never
    discounted below the shop's standing menu margin — the leak (engine c_eff
    basis) is $0 for every accepted menu-buyer deal, for any scale in
    [0.5,1.6]. This is the structural half of the IC floor: d_seller runs on
    OBSERVABLES, so a wrong scale cannot lower it. (The OTHER channel — a wrong
    scale misidentifying WHICH config is the menu counterfactual, possible only
    with heterogeneous multi-option carts — is not exercised here; it is what
    the boba sim in demand_validation.py measures as the small residual leak.)"""
    graph = _smoothing_graph()
    from core.state import ShopState
    state = ShopState(tick=0)
    # a TRUE menu-buyer: values the cart well above list, low defer cost (so a
    # deferred deal is attractive), a real balk (so now-slot is balk-exposed).
    buyer = SeparableBuyer(
        values={("drink", "tea"): drink_v, ("top", "pearls"): top_v},
        qty_decay=0.3, outside=0.0, balk=0.25,
        defer={0: 0.0, 3: 0.1})
    opts = QuoteOpts(min_gain_abs=0.25, min_gain_frac=0.10, price_rungs=8,
                     seller_weight=0.5, quote_lookers=False)

    # is the buyer a TRUE menu-buyer, and what is their true standing margin?
    oracle_q = core_quote(graph, state, buyer, opts=opts)
    if oracle_q is None:
        return                                 # a looker — not our invariant
    d_seller_true = oracle_q.audit.get("d_seller", 0.0)
    d_buyer_true = oracle_q.audit.get("d_buyer", 0.0)
    if d_seller_true <= 1e-9:
        return                                 # not a menu-buyer (looker)

    # price with a deliberately-wrong learned scale (mistrained / ratcheted)
    dm = LearnedDemand(appeal=ListAppeal(), sigma_pop=0.45, decay=0.3,
                       prior_m=math.log(scale), prior_sigma=1e-3)
    q = core_quote(graph, state, _observable_shell(buyer), opts=opts,
                   demand=dm, context="c")
    if q is None or not q.feasible:
        return                                 # refused / at-list

    surv = _deal_surv(graph, q.config, buyer, state)
    true_value = buyer.value(graph, q.config)
    defer = _deal_defer(graph, q.config, buyer)
    u_buyer = surv * (true_value - q.price) \
        + (1 - surv) * buyer.outside_surplus() - defer
    if u_buyer < d_buyer_true - 1e-9:
        return                                 # the TRUE buyer walks

    e_cost = graph.cost.quote(graph, state, q.config, qty_of(graph, q.config))
    deal_gain = surv * (q.price - e_cost.c_eff) + e_cost.credit
    leak = max(0.0, d_seller_true - deal_gain)
    assert leak <= 1e-6, (
        f"leak ${leak:.4f} (d_seller_true {d_seller_true:.4f} > deal_gain "
        f"{deal_gain:.4f}) at scale={scale} drink_v={drink_v} top_v={top_v}")


def test_ic_leak_property_actually_exercises_deals():
    """Guard against a vacuous property test: the sweep above must strike real
    accepted menu-buyer deals (not skip every case)."""
    graph = _smoothing_graph()
    from core.state import ShopState
    state = ShopState(tick=0)
    struck = 0
    for scale, drink_v, top_v in _CASES:
        buyer = SeparableBuyer(
            values={("drink", "tea"): drink_v, ("top", "pearls"): top_v},
            qty_decay=0.3, outside=0.0, balk=0.25, defer={0: 0.0, 3: 0.1})
        opts = QuoteOpts(min_gain_abs=0.25, min_gain_frac=0.10, price_rungs=8,
                         quote_lookers=False)
        oq = core_quote(graph, state, buyer, opts=opts)
        if oq is None or oq.audit.get("d_seller", 0.0) <= 1e-9:
            continue
        dm = LearnedDemand(appeal=ListAppeal(), sigma_pop=0.45, decay=0.3,
                           prior_m=math.log(scale), prior_sigma=1e-3)
        q = core_quote(graph, state, _observable_shell(buyer), opts=opts,
                       demand=dm, context="c")
        if q is not None and q.feasible:
            surv = _deal_surv(graph, q.config, buyer, state)
            u = surv * (buyer.value(graph, q.config) - q.price) \
                - _deal_defer(graph, q.config, buyer)
            if u >= oq.audit.get("d_buyer", 0.0) - 1e-9:
                struck += 1
    assert struck >= 5, f"property test exercised only {struck} menu-buyer deals"


def _deal_surv(graph, config, buyer, state):
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            opt = d.option(config[d.id])
            return 1.0 if not opt.immediate else (1.0 - buyer.balk_prob(state))
    return 1.0 - buyer.balk_prob(state)


def _deal_defer(graph, config, buyer):
    for d in graph.dims:
        if d.kind == DimKind.FULFILLMENT:
            return buyer.defer_cost(d.option(config[d.id]).slot_ticks)
    return 0.0


# ── component smoke: EwmaRate + ContextGate behave ─────────────────────────
def test_ewma_rate_and_context_gate():
    r = EwmaRate(prior_strength=8.0)
    r.begin_day()
    r.observe_arrivals(10.0, 14)                # more arrivals than expected
    assert r.mult_hat > 1.0
    g = ContextGate(min_bucket=3, threshold=0.0)
    assert g.open("peak")                       # warmup opens the gate
    for _ in range(3):
        g.observe("peak", 1.0)
    assert g.open("peak")                       # positive EV keeps it open
    for _ in range(6):
        g.observe("off", -1.0)
    assert not g.open("off")                    # negative EV closes it
