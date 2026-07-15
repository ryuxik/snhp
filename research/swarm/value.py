"""Φ and the ONE routing function (SPEC.md v4.0).

Panel mandate (PANEL_V4.md, M4): the movement policy and Φ's load term must
consume the SAME `delivery_target()` — three separate re-entry paths for the
v2.1 silent-dead-issue bug existed when they could diverge. Tariffs enter
per-unit credit here and nowhere else; EV (the energy shadow price that
trades credit against haul distance) is endogenous per robot — a lagged
finite-difference ∂Φ/∂battery — instead of a hand-set constant.
"""
from __future__ import annotations

import math

from swarm import world as W


def safe_return_threshold(r, w) -> float:
    """Battery level below which an unloaded robot should head to charge."""
    _, d = w.nearest_charger(r)
    return (d + 4) * r.eff * 1.2


def _ref_score(r, w, ref_idx: int, from_pos) -> float:
    """Net value of hauling the current load from `from_pos` to refinery
    `ref_idx`: tariff-adjusted credit minus energy cost at the robot's own
    shadow price."""
    credit = w.credit_rate(r.company, ref_idx) * W.V_DELIVER * max(r.load, 1)
    haul = W.manhattan(from_pos, w.refineries[ref_idx]) * r.eff * (1 + W.LOADED_MULT)
    return credit - haul * r.ev


def delivery_target(r, w, from_pos=None, sticky: bool = True) -> int:
    """Index of the refinery this robot should deliver to. Hysteresis: keep
    the current target unless a challenger wins by TARGET_MARGIN (prevents
    argmax flip-flop when deals change load mid-route — panel M4)."""
    pos = from_pos if from_pos is not None else r.pos
    scores = [_ref_score(r, w, i, pos) for i in range(len(w.refineries))]
    best = max(range(len(scores)), key=lambda i: scores[i])
    if (sticky and from_pos is None and r.target_ref is not None
            and r.target_ref < len(scores)
            and scores[r.target_ref] >= scores[best] - W.TARGET_MARGIN):
        return r.target_ref
    if sticky and from_pos is None:
        r.target_ref = best
    return best


def stranding_hazard(r, w) -> float:
    """P(strand soon), smooth in the energy margin to the charger (-hz Φ)."""
    _, d = w.nearest_charger(r)
    margin = r.bat() - d * r.step_cost()
    return 1.0 / (1.0 + math.exp(margin / W.HAZARD_SCALE))


def _future_trips_value(r, w) -> float:
    """Value of the (source, refinery) loop the movement policy will ACTUALLY
    run: own sector while stocked, cross-mining fallback — NOT a max over
    sectors (v2.1 lesson: a free max prices sector swaps at zero and silently
    kills the issue). The refinery leg uses the same delivery_target scoring,
    tariff-aware."""
    cand = r.sector if w.stock[r.sector] > 0 else w.best_claim(r)
    for s in (cand,):
        stock = w.stock[s]
        if stock <= 0:
            continue
        src = w.sources[s]
        ref = delivery_target(r, w, from_pos=src, sticky=False)
        rate = w.credit_rate(r.company, ref)
        leg = W.manhattan(src, w.refineries[ref])
        approach = W.manhattan(r.pos, src) * r.eff
        cycle_cost = 2 * leg * r.eff * (1 + W.LOADED_MULT / 2)
        spare = max(0.0, r.bat() - approach - 0.15 * W.BATTERY_MAX)
        trips = spare / max(cycle_cost, 1e-9)
        claim = stock / max(1.0, len(w.robots) / 2)
        return (W.FUTURE_DISCOUNT * min(trips * r.cap, claim)
                * rate * W.V_DELIVER)
    return 0.0


def v_life(r, w) -> float:
    """v9: the drone's REMAINING CAREER value — its fleet-share of the whole
    remaining field (a chassis re-claims sectors as they deplete, so the
    career is field-bound, not sector-bound), net of haul energy at the
    robot's own shadow price, plus the cargo it would take down with it,
    plus exogenous replacement capital. Independent of current charge (a
    dying robot's low battery must not talk itself into being worthless).
    Decays to ~0 as the field depletes, so endgame abandonment stays
    rational while early-run drones are expensive to lose."""
    doomed = r.load * W.V_DELIVER + w.strand_cap
    # nominal fleet size, not live count: a deal's own execution can strand
    # the donor, and an alive-count share would make evaluated Φ diverge
    # from executed Φ (the one invariant every arm asserts per deal)
    share = sum(w.stock) / max(1, len(w.robots))
    cand = r.sector if w.stock[r.sector] > 0 else w.best_claim(r)
    if share <= 0 or w.stock[cand] <= 0:
        return doomed
    src = w.sources[cand]
    ref = delivery_target(r, w, from_pos=src, sticky=False)
    rate = w.credit_rate(r.company, ref)
    leg = W.manhattan(src, w.refineries[ref])
    cycle_cost = 2 * leg * r.eff * (1 + W.LOADED_MULT / 2)
    net_per_unit = max(0.0, rate * W.V_DELIVER
                       - cycle_cost * r.ev / max(r.cap, 1))
    return share * net_per_unit + doomed


def _strand_price(r, w) -> float:
    """What Φ charges for a stranding: the drone's remaining career under
    v9 life-pricing, the flat P_STRAND otherwise. Used consistently in the
    stranded state, the hazard term, and (through both) rescue surplus."""
    return v_life(r, w) if w.life_pricing else W.P_STRAND


def phi(r, w) -> float:
    if r.stranded:
        return -_strand_price(r, w)
    v = 0.0

    # value of the load currently carried — tariff-aware, same routing the
    # policy will use (panel M4: an un-tariffed load term would misprice
    # every border cargo bundle identically in evaluation and execution,
    # invisible to the evaluated==executed assert)
    if r.load > 0:
        ref = delivery_target(r, w, sticky=False)
        rate = w.credit_rate(r.company, ref)
        cost_to_ref = (W.manhattan(r.pos, w.refineries[ref])
                       * r.eff * (1 + W.LOADED_MULT))
        full = r.load * rate * W.V_DELIVER
        if r.bat() > cost_to_ref:
            v += full
        else:
            v += 0.5 * full * r.bat() / (cost_to_ref + 1e-9)

    v += _future_trips_value(r, w)

    if w.hazard_phi:
        v -= _strand_price(r, w) * stranding_hazard(r, w)
    else:
        _, d = w.nearest_charger(r)
        if r.bat() < d * r.step_cost():
            v -= _strand_price(r, w)
    return v


def update_ev(r, w, delta: float = 2.0) -> None:
    """Lagged endogenous energy shadow price: EV ← ∂Φ/∂battery by finite
    difference at the robot's current state, clamped. Called every few ticks
    by the arm loop; `w.freeze_ev` pins it for estimator-sensitivity runs."""
    if w.freeze_ev is not None:
        r.ev = w.freeze_ev
        return
    b0 = r.battery
    p0 = phi(r, w)
    # perturb the BELIEVED reading, not the true axis: Φ consumes bat(), so
    # stepping .battery by delta measured (1+gauge_bias)·∂Φ/∂believed — a
    # second, unintended miscalibration channel (review). At zero bias this
    # is identical to the old step.
    step = delta / max(0.05, 1.0 + r.gauge_bias)
    r.battery = min(W.BATTERY_MAX, b0 + step)
    p1 = phi(r, w)
    r.battery = b0
    grad = (p1 - p0) / max(1e-9, delta)
    if grad > 1e-9:
        r.ev = float(min(W.EV_MAX, max(W.EV_MIN, grad)))


def phi_true(r, w) -> float:
    """Φ with the gauge suspended — the ground truth for poisoning audits."""
    saved = r.gauge_bias
    r.gauge_bias = 0.0
    try:
        return phi(r, w)
    finally:
        r.gauge_bias = saved


def stranding_hazard_true(r, w) -> float:
    """stranding_hazard with the gauge suspended: audit fields in the deal
    log are ground truth, not belief (review: the distress label followed
    the miscalibrated gauge under v7)."""
    saved = r.gauge_bias
    r.gauge_bias = 0.0
    try:
        return stranding_hazard(r, w)
    finally:
        r.gauge_bias = saved
