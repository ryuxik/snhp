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
) -> dict:
    """
    Recommend the next sell-side offer given the negotiation state.

    All utilities are normalized to [0, 1] in OUR utility space (higher =
    better for us). `opponent_offer_history` is the opponent's sequence of
    offers evaluated in our utility space — caller is responsible for the
    projection.

    `pareto_knob ∈ [0, 1]` interpolates between the two empirically-mapped
    extremes from the seller-side Pareto frontier:
      0.0 → max deal rate (asp_start=0.55)
      1.0 → max H2H margin (asp_start=0.89)

    `buyer_wtp_prior` is an optional Gaussian prior on buyer willingness-to-
    pay in our utility space, supplied if the caller has historical data
    about this counterparty type. When None, we use an uninformative prior.

    Returns a structured dict (see plan / API spec).
    """
    _validate(my_reservation, pareto_knob, deadline_rounds)

    # ── Aspiration curve from the Pareto knob ──────────────────────────
    asp_start = _lerp(_ASP_START_DEAL_RATE_MAX, _ASP_START_MARGIN_MAX, pareto_knob)
    # Schelling commitment margin: never aim below my BATNA + small buffer.
    schelling_floor = max(my_reservation + 0.05, 0.40)
    asp_floor = max(asp_start * 0.6, schelling_floor)

    rounds_used = max(len(my_offer_history), len(opponent_offer_history))
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))

    # Power-law concession matches the SNHP empirical curve (see
    # negmas_agent.py:propose). base_exp 3 is the SNHP default for B2B
    # short games; tuned per-role values live in optimal_params.json but
    # the v1 handler keeps it simple.
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
