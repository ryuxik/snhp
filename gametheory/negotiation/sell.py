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
from gametheory.negotiation._config import get_param, get_int_param

from bayesian_agent import BayesianParticleFilter  # noqa: E402
from core_math.rubinstein import rubinstein_equilibrium  # noqa: E402


# All tunable values live in `_config.py`. The two empirical endpoints
# (Pareto frontier extrema) are exposed here as module-level for
# convenience; their actual values are pulled from _config so env-var
# overrides work.
def _asp_start_deal_rate_max() -> float: return get_param("asp_start_deal_rate_max")
def _asp_start_margin_max() -> float: return get_param("asp_start_margin_max")

# Bayesian filter contract grid built lazily per-call (param tunable).
def _contract_grid():
    n = get_int_param("bayesian_contract_grid_n")
    return np.linspace(0.0, 1.0, n).reshape(-1, 1)


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


from gametheory.negotiation._peer import peer_recommendation


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
    n_particles: Optional[int] = None,  # default pulled from _config
    peer_mode: bool = False,
) -> dict:
    """
    Recommend the next sell-side offer given the negotiation state.

    `peer_mode=True` activates the cooperative architecture used by the
    full SNHP agent when its counterparty is a verified SNHP-protocol
    peer (cryptographic attestation): max-self signaling for rounds 0-1,
    then cubic descent toward the PEER floor (0.55). Validated in the
    N=20 NegMAS LLM tournament at U(7,13) negotiation rounds: +0.186
    joint welfare lift, p=0.0004. At ≤6-round horizons the lift
    compresses to ~+0.07 and is not stat-sig at n=20 — improving
    short-horizon behavior is a research direction (mechanism change),
    not a parameter-tuning question.

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
        return peer_recommendation(
            my_reservation=my_reservation,
            opponent_offer_history=opponent_offer_history,
            my_offer_history=my_offer_history,
            deadline_rounds=deadline_rounds,
        )

    # All magic numbers come from _config.py; env-overridable via SNHP_*.
    if n_particles is None:
        n_particles = get_int_param("bayesian_n_particles")

    asp_start = _lerp(_asp_start_deal_rate_max(), _asp_start_margin_max(), pareto_knob)
    schelling_buf_abs = get_param("schelling_buffer_abs")
    schelling_buf_rel = get_param("schelling_buffer_rel")
    schelling_floor = my_reservation + min(schelling_buf_abs, schelling_buf_rel * (1.0 - my_reservation))
    asp_floor = my_reservation

    rounds_used = len(my_offer_history) + len(opponent_offer_history)
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))

    base_exp = get_param("concession_exponent")
    aspiration = asp_start - (asp_start - asp_floor) * (time_fraction ** base_exp)

    # ── Bayesian inference on opponent's offers ────────────────────────
    bayesian_uncertainty = get_param("bayesian_uncertainty")
    if buyer_wtp_prior is not None:
        prior_mu = float(buyer_wtp_prior.get("mu", 0.5))
        prior_sigma = float(buyer_wtp_prior.get("sigma", bayesian_uncertainty))
        b_filter = BayesianParticleFilter(
            num_variables=1, num_particles=n_particles,
            historical_prior=[prior_mu], uncertainty=prior_sigma,
        )
    else:
        b_filter = BayesianParticleFilter(
            num_variables=1, num_particles=n_particles, uncertainty=bayesian_uncertainty
        )

    contract_grid = _contract_grid()
    for opp_util_to_us in opponent_offer_history:
        opp_util_to_self = max(0.0, min(1.0, 1.0 - float(opp_util_to_us)))
        anchor = np.array([opp_util_to_self])
        b_filter.update_beliefs(anchor, contract_grid)

    inferred_weights = b_filter.get_inferred_weights()
    inferred_opp_weight = float(inferred_weights[0])
    spread = float(np.std(b_filter.particles[:, 0]))
    confidence = float(np.clip(
        1.0 - spread * get_param("bayesian_confidence_slope"),
        get_param("accept_prob_clamp_low"),
        get_param("accept_prob_clamp_high"),
    ))

    # ── Rubinstein equilibrium floor ───────────────────────────────────
    opp_rv_intercept = get_param("opp_rv_estimate_intercept")
    opp_rv_slope = get_param("opp_rv_estimate_slope")
    opp_rv_clip_lo = get_param("opp_rv_estimate_clip_low")
    opp_rv_clip_hi = get_param("opp_rv_estimate_clip_high")
    opp_rv_estimate = float(np.clip(
        opp_rv_intercept - opp_rv_slope * inferred_opp_weight,
        opp_rv_clip_lo, opp_rv_clip_hi,
    ))
    surplus = max(0.01, (1.0 - my_reservation) - opp_rv_estimate)

    my_discount = get_param("rubinstein_my_discount")
    opp_discount = get_param("rubinstein_opp_discount")
    rub = rubinstein_equilibrium(my_discount, opp_discount, surplus)
    rubinstein_floor = my_reservation + surplus * rub["freelancer_share"]

    # ── Recommendation ─────────────────────────────────────────────────
    if len(opponent_offer_history) >= 2:
        opp_concession = opponent_offer_history[-1] - opponent_offer_history[0]
    else:
        opp_concession = 0.0
    if opp_concession > get_param("opp_concession_threshold"):
        recommended = max(aspiration, schelling_floor)
    else:
        recommended = max(aspiration, rubinstein_floor)
    recommended = min(recommended, get_param("recommended_ceiling_adversarial"))

    # ── Acceptance probability ─────────────────────────────────────────
    accept_clamp_lo = get_param("accept_prob_clamp_low")
    accept_clamp_hi = get_param("accept_prob_clamp_high")
    opp_util_from_offer = 1.0 - recommended
    if opp_util_from_offer <= opp_rv_estimate:
        accept_prob = accept_clamp_lo
    else:
        accept_prob = float(np.clip(
            (opp_util_from_offer - opp_rv_estimate) / (1.0 - opp_rv_estimate + 1e-9),
            accept_clamp_lo, accept_clamp_hi,
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
