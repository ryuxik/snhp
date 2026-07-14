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
    margin = r.battery - d * r.step_cost()
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
        spare = max(0.0, r.battery - approach - 0.15 * W.BATTERY_MAX)
        trips = spare / max(cycle_cost, 1e-9)
        claim = stock / max(1.0, len(w.robots) / 2)
        return (W.FUTURE_DISCOUNT * min(trips * r.cap, claim)
                * rate * W.V_DELIVER)
    return 0.0


def phi(r, w) -> float:
    if r.stranded:
        return -W.P_STRAND
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
        if r.battery > cost_to_ref:
            v += full
        else:
            v += 0.5 * full * r.battery / (cost_to_ref + 1e-9)

    v += _future_trips_value(r, w)

    if w.hazard_phi:
        v -= W.P_STRAND * stranding_hazard(r, w)
    else:
        _, d = w.nearest_charger(r)
        if r.battery < d * r.step_cost():
            v -= W.P_STRAND
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
    r.battery = min(W.BATTERY_MAX, b0 + delta)
    p1 = phi(r, w)
    r.battery = b0
    grad = (p1 - p0) / max(1e-9, delta)
    if grad > 1e-9:
        r.ev = float(min(W.EV_MAX, max(W.EV_MIN, grad)))
