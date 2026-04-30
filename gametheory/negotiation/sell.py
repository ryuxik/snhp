"""
Tier 1 sell-side negotiation handler.

Wraps existing SNHP math primitives (Bayesian particle filter + Rubinstein
SPE) and exposes the empirical Pareto frontier via a single `pareto_knob`
control. Pure function — no I/O, no LLM calls. Safe to call at high frequency
on the math-only free billing tier.

Empirical anchor (snhp/pareto_frontier_seller.json from this session):
  pareto_knob 0.0 → asp_start=0.55, deal_rate≈76%, margin≈-0.05
  pareto_knob 0.5 → asp_start=0.72, balanced knee
  pareto_knob 1.0 → asp_start=0.89, deal_rate≈68%, margin≈+0.025
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from bayesian_agent import BayesianParticleFilter  # noqa: E402
from core_math.rubinstein import rubinstein_equilibrium  # noqa: E402


# Empirical Pareto endpoints. Updating these requires re-running
# snhp/optuna_tuner.py --pareto and updating both ends of the curve here.
_ASP_START_DEAL_RATE_MAX = 0.55  # max deal rate, min margin
_ASP_START_MARGIN_MAX = 0.89     # max margin, lower deal rate

_DEFAULT_PARTICLES = 500

# Bayesian filter contract grid. 50 points × 1D contract space; recreating
# this every call costs ~1µs but it's a clean module-level invariant.
_CONTRACT_GRID = np.linspace(0.0, 1.0, 50).reshape(-1, 1)


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


# PEER playbook (mirrors snhp.playbooks._PLAYBOOKS["PEER"]). Used by
# both sell and buy when peer_mode=True. Conservative defaults:
# - asp_start 0.92: open near max-self (signals preferences via outcome)
# - asp_floor 0.55: refuse to descend below cooperative Nash share
# - signaling rounds: hold at max-self for 1-2 rounds
_PEER_ASP_START = 0.92
_PEER_ASP_FLOOR = 0.55
_PEER_SIGNALING_ROUNDS = 2  # hold at near-max-self for first N proposals
_PEER_MAX_SELF_TARGET = 0.95  # what to recommend during signaling phase


def _peer_mode_recommendation(
    *,
    my_reservation: float,
    opponent_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
    role: str,
) -> dict:
    """Cooperative recommendation when both parties are SNHP-protocol peers.

    Phase 1 (rounds 0-1, signaling): recommend opening near max-self
    (~0.95). The high opening reveals our preferences via the offer's
    issue values, letting the verified peer infer our weights without
    explicit disclosure. Two peers signaling simultaneously converge on
    the asymmetric Pareto outcome by round 3-4.

    Phase 2 (rounds 2+, descent): descend from asp_start (0.92) toward
    asp_floor (0.55) via cubic schedule. Slower than Rubinstein-aspiration
    so cooperation has time to crystallize.

    Acceptance: accept if peer offers ≥ asp_floor AND we're past round 2
    (signaling complete).
    """
    rounds_used = len(my_offer_history) + len(opponent_offer_history)
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))
    n_my_offers = len(my_offer_history)

    # Phase 1: signaling
    if n_my_offers < _PEER_SIGNALING_ROUNDS:
        recommended = _PEER_MAX_SELF_TARGET
        phase = "peer_signaling"
        rationale = (
            f"PEER mode round {n_my_offers + 1}/{_PEER_SIGNALING_ROUNDS}: "
            f"open at {_PEER_MAX_SELF_TARGET:.2f} to signal preferences "
            f"via offer issue values. Verified peer will infer your "
            f"weights and signal back in kind."
        )
    else:
        # Phase 2: cubic descent
        descent_t = max(0.0, (time_fraction - 0.2) / 0.8)
        recommended = _PEER_ASP_START - (_PEER_ASP_START - _PEER_ASP_FLOOR) * (descent_t ** 3)
        phase = "peer_descent"
        rationale = (
            f"PEER mode descent: t={time_fraction:.2f}, recommended "
            f"{recommended:.3f} (cubic descent from {_PEER_ASP_START:.2f} "
            f"toward floor {_PEER_ASP_FLOOR:.2f}). Both peers should "
            f"converge near the asymmetric Pareto outcome."
        )
    recommended = max(my_reservation + 0.05, min(0.97, recommended))

    # Acceptance prob estimate: in peer mode, peer is also descending
    # symmetrically, so probability is high once past signaling.
    if n_my_offers < _PEER_SIGNALING_ROUNDS:
        accept_prob = 0.10  # signaling phase: peer also opening high, won't accept
    else:
        # Estimate from opponent's most recent offer + descent trajectory
        if opponent_offer_history:
            opp_last = opponent_offer_history[-1]
            # If their last offer is above our floor, they're cooperating
            accept_prob = 0.85 if opp_last >= _PEER_ASP_FLOOR else 0.40
        else:
            accept_prob = 0.60

    expected_payoff = accept_prob * recommended + (1.0 - accept_prob) * my_reservation

    return {
        "recommended_offer": round(recommended, 4),
        "acceptance_probability": round(accept_prob, 4),
        "expected_payoff": round(expected_payoff, 4),
        "rationale": rationale,
        "peer_mode": True,
        "peer_phase": phase,
        "peer_asp_floor": _PEER_ASP_FLOOR,
        "posterior": {
            "n_particles": 0,
            "estimated_opp_reservation": my_reservation,  # symmetric assumption
        },
    }


def _validate(my_reservation: float, pareto_knob: float, deadline_rounds: int):
    if not 0.0 <= my_reservation <= 1.0:
        raise ValueError(f"my_reservation must be in [0, 1], got {my_reservation}")
    if not 0.0 <= pareto_knob <= 1.0:
        raise ValueError(f"pareto_knob must be in [0, 1], got {pareto_knob}")
    if deadline_rounds < 1:
        raise ValueError(f"deadline_rounds must be >= 1, got {deadline_rounds}")


def sell_next_offer(
    *,
    my_reservation: float,
    opponent_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
    pareto_knob: float = 0.5,
    buyer_wtp_prior: Optional[dict] = None,
    n_particles: int = _DEFAULT_PARTICLES,
    peer_mode: bool = False,
) -> dict:
    """
    Recommend the next sell-side offer given the negotiation state.

    `peer_mode=True` activates the cooperative architecture used by the
    full SNHP agent when its counterparty is a verified SNHP-protocol
    peer (cryptographic attestation): max-self signaling for rounds 0-1,
    then descent toward PEER playbook floor (0.55). This produces
    higher joint welfare than the standard Rubinstein+aspiration descent
    because both peers can find the asymmetric Pareto outcome.

    `pareto_knob ∈ [0, 1]` interpolates between the two empirically-mapped
    extremes from the seller-side Pareto frontier (only applies when
    peer_mode=False):
      0.0 → max deal rate (asp_start=0.55)
      1.0 → max H2H margin (asp_start=0.89)

    `buyer_wtp_prior` is an optional Gaussian prior on buyer willingness-to-
    pay in our utility space, supplied if the caller has historical data
    about this counterparty type. When None, we use an uninformative prior.

    Returns a structured dict (see plan / API spec).
    """
    _validate(my_reservation, pareto_knob, deadline_rounds)

    # ─── Peer-mode: cooperative architecture for verified SNHP peers ──
    # When both parties are protocol-staked SNHP nodes, the right
    # strategy is NOT Rubinstein+aspiration descent (which assumes an
    # adversarial opponent). It's the PEER playbook used by the full
    # SNHP agent: open at max-self for 1-2 rounds (signal preferences
    # via offer issue values), then descend slowly toward fair share.
    # Empirically reaches 96% of frontier vs 75-90% for vanilla descent.
    if peer_mode:
        return _peer_mode_recommendation(
            my_reservation=my_reservation,
            opponent_offer_history=opponent_offer_history,
            my_offer_history=my_offer_history,
            deadline_rounds=deadline_rounds,
            role="seller",
        )

    # ── Aspiration curve from the Pareto knob ──────────────────────────
    asp_start = _lerp(_ASP_START_DEAL_RATE_MAX, _ASP_START_MARGIN_MAX, pareto_knob)
    # Schelling commitment: never recommend below my reservation + a small
    # buffer for negotiating room. The aspiration curve floor IS reservation
    # — at deadline we're willing to take any deal above walk-away. (Earlier
    # versions floored at 0.40 absolute / 0.6×asp_start; that was tuned for
    # multi-attribute B2B with logrolling and starves single-axis games of
    # the deals the math should land.)
    schelling_floor = my_reservation + min(0.05, 0.5 * (1.0 - my_reservation))
    asp_floor = my_reservation

    # Total alternating-offer rounds elapsed = sum of both histories. Earlier
    # `max(len(mine), len(theirs))` underestimated by ~2× — a 10-round game
    # with both sides at 5 offers reads as t=0.5, not t≈1.0, leaving SNHP's
    # aspiration almost undecayed at the deadline.
    rounds_used = len(my_offer_history) + len(opponent_offer_history)
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))

    # Power-law concession (see negmas_agent.py:propose). base_exp=3 means
    # most of the concession happens late — preserves margin against a
    # firm-but-time-aware opponent, but still concedes against deadlines.
    base_exp = 3.0
    aspiration = asp_start - (asp_start - asp_floor) * (time_fraction ** base_exp)

    # ── Bayesian inference on opponent's offers ────────────────────────
    if buyer_wtp_prior is not None:
        prior_mu = float(buyer_wtp_prior.get("mu", 0.5))
        prior_sigma = float(buyer_wtp_prior.get("sigma", 0.2))
        b_filter = BayesianParticleFilter(
            num_variables=1, num_particles=n_particles,
            historical_prior=[prior_mu], uncertainty=prior_sigma,
        )
    else:
        b_filter = BayesianParticleFilter(
            num_variables=1, num_particles=n_particles, uncertainty=0.2
        )

    # Iterate over the full opponent history so the posterior compounds
    # evidence (the SNHP fix from this session — single-anchor updates
    # under-update against slow-conceders).
    for opp_util_to_us in opponent_offer_history:
        # In a 1D zero-sum projection, opp's utility from their own offer ≈
        # 1 - (opp's offer in our utility space). The filter expects the
        # opponent's contract features; we use their utility from their
        # own offer as the anchor.
        opp_util_to_self = max(0.0, min(1.0, 1.0 - float(opp_util_to_us)))
        anchor = np.array([opp_util_to_self])
        b_filter.update_beliefs(anchor, _CONTRACT_GRID)

    inferred_weights = b_filter.get_inferred_weights()
    inferred_opp_weight = float(inferred_weights[0])
    spread = float(np.std(b_filter.particles[:, 0]))
    confidence = float(np.clip(1.0 - spread * 2.5, 0.05, 0.95))

    # ── Rubinstein equilibrium floor ───────────────────────────────────
    # Opp's reservation estimate: scaled by inferred preference. A buyer
    # who values price heavily (weight ≈ 1) has lower BATNA in our space.
    opp_rv_estimate = float(np.clip(0.4 - 0.2 * inferred_opp_weight, 0.1, 0.6))
    surplus = max(0.01, (1.0 - my_reservation) - opp_rv_estimate)

    my_discount = 0.95
    opp_discount = 0.92
    # Use the role-aware Rubinstein call. Sell-side is first-mover by
    # convention so we take freelancer_share directly.
    rub = rubinstein_equilibrium(my_discount, opp_discount, surplus)
    rubinstein_floor = my_reservation + surplus * rub["freelancer_share"]

    # ── Recommendation ─────────────────────────────────────────────────
    # Rubinstein gives the SPE share assuming the opponent is also playing
    # equilibrium. Many real opponents (aspiration, anchor-and-retreat,
    # vanilla LLMs) instead concede over time. If we've observed concession
    # — opp's last offer is meaningfully better than their first — we trust
    # the aspiration curve to land deals; otherwise we hold at Rubinstein.
    if len(opponent_offer_history) >= 2:
        opp_concession = opponent_offer_history[-1] - opponent_offer_history[0]
    else:
        opp_concession = 0.0
    if opp_concession > 0.05:
        recommended = max(aspiration, schelling_floor)
    else:
        recommended = max(aspiration, rubinstein_floor)
    recommended = min(recommended, 0.99)

    # ── Acceptance probability ─────────────────────────────────────────
    # P(opp accepts) ≈ probability the offer leaves opp above their BATNA.
    # In zero-sum projection, opp_util_from_offer = 1 - recommended.
    opp_util_from_offer = 1.0 - recommended
    if opp_util_from_offer <= opp_rv_estimate:
        accept_prob = 0.05
    else:
        accept_prob = float(np.clip(
            (opp_util_from_offer - opp_rv_estimate) / (1.0 - opp_rv_estimate + 1e-9),
            0.05, 0.95,
        ))

    expected_payoff = accept_prob * recommended + (1.0 - accept_prob) * my_reservation

    return {
        "recommended_offer": round(recommended, 4),
        "acceptance_probability": round(accept_prob, 4),
        "expected_payoff": round(expected_payoff, 4),
        "rationale": (
            f"pareto_knob={pareto_knob:.2f} → asp_start={asp_start:.3f}; "
            f"round {rounds_used}/{deadline_rounds} (t={time_fraction:.2f}) → "
            f"aspiration={aspiration:.3f}; Rubinstein floor={rubinstein_floor:.3f}; "
            f"recommended max={recommended:.3f}. Inferred opponent "
            f"price-weight {inferred_opp_weight:.2f} (confidence {confidence:.2f})."
        ),
        "posterior": {
            "inferred_opp_price_weight": round(inferred_opp_weight, 4),
            "confidence": round(confidence, 4),
            "n_particles": n_particles,
            "estimated_opp_reservation": round(opp_rv_estimate, 4),
        },
        "rubinstein_share": round(rub["freelancer_share"], 4),
        "schelling_floor": round(schelling_floor, 4),
    }
