"""
Cooperative recommendation for verified SNHP peers — used by both
`gametheory.negotiation.sell` and `gametheory.negotiation.buy`.

All parameters live in `_config.py` and are env-overridable
(`SNHP_PEER_ASP_START`, etc.). See `_config.py` for metadata + rationale
on each value. This module is just the algorithm.

The PEER playbook is single, not variant-keyed. See CHANGELOG.md
(2026-05-01) for the failed peer_cs experiment that motivated the revert.
"""
from __future__ import annotations

from gametheory.negotiation._config import get_param, get_int_param


def peer_recommendation(
    *,
    my_reservation: float,
    opponent_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
) -> dict:
    """Cooperative target-utility recommendation when the counterparty is
    a verified SNHP-protocol peer.

    Phase 1 (rounds 0-1, signaling): recommend opening near max-self
    (~0.95). The high opening reveals our preferences via the offer's
    issue values, letting the verified peer infer our weights without
    explicit disclosure. Two peers signaling simultaneously converge on
    the asymmetric Pareto outcome by round 3-4.

    Phase 2 (rounds 2+, descent): descend from asp_start (0.92) toward
    asp_floor (0.55) via cubic schedule. Slower than Rubinstein-aspiration
    so cooperation has time to crystallize.

    Returns the recommended target plus schema-compat fields. Note on
    `acceptance_probability`: in peer mode this is set to a single
    neutral 0.5. The previous variant-keyed implementation returned
    a 4-branch heuristic (0.10 / 0.40 / 0.60 / 0.85) that was never
    used by any consumer for the accept decision (the LLM scaffold
    decides freely; HTTP/MCP clients don't gate on it). The signaling-
    phase 0.10 was actively misleading when surfaced in LLM prompts.
    Adversarial-mode callers (peer_mode=False) compute their own
    acceptance_probability from inferred opponent reservation, which
    *is* useful — that path is unchanged.
    """
    asp_start = get_param("peer_asp_start")
    asp_floor = get_param("peer_asp_floor")
    signaling_rounds = get_int_param("peer_signaling_rounds")
    max_self_target = get_param("peer_max_self_target")
    descent_exp = get_param("peer_descent_exp")
    descent_offset = get_param("peer_descent_offset")
    reservation_buffer = get_param("peer_reservation_buffer")
    recommended_ceiling = get_param("peer_recommended_ceiling")

    rounds_used = len(my_offer_history) + len(opponent_offer_history)
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))
    n_my_offers = len(my_offer_history)

    if n_my_offers < signaling_rounds:
        recommended = max_self_target
        phase = "peer_signaling"
        rationale = (
            f"PEER round {n_my_offers + 1}/{signaling_rounds}: "
            f"open at {max_self_target:.2f} to signal preferences "
            f"via offer issue values. Verified peer will infer your "
            f"weights and signal back in kind."
        )
    else:
        descent_span = max(0.001, 1.0 - descent_offset)
        descent_t = max(0.0, (time_fraction - descent_offset) / descent_span)
        recommended = asp_start - (asp_start - asp_floor) * (descent_t ** descent_exp)
        phase = "peer_descent"
        rationale = (
            f"PEER descent: t={time_fraction:.2f}, recommended "
            f"{recommended:.3f} (exp={descent_exp:.2f} from {asp_start:.2f} "
            f"toward floor {asp_floor:.2f}). Both peers should "
            f"converge near the asymmetric Pareto outcome."
        )
    recommended = max(my_reservation + reservation_buffer,
                       min(recommended_ceiling, recommended))

    return {
        "recommended_offer": round(recommended, 4),
        "acceptance_probability": 0.5,  # neutral; see docstring
        "expected_payoff": round(recommended, 4),  # peer mode: high P(deal), so EP ≈ target
        "rationale": rationale,
        "peer_mode": True,
        "peer_phase": phase,
        "peer_asp_floor": asp_floor,
        # Schema-compat for SellNextOfferResponse / BuyNextOfferResponse.
        # Echo defaults — these fields don't carry strategic meaning in
        # peer mode (PEER playbook, not Rubinstein/Schelling), but the
        # response schema mandates them.
        "rubinstein_share": 0.5,
        "schelling_floor": asp_floor,
        "posterior": {
            "inferred_opp_price_weight": 0.5,
            "confidence": 0.5,
            "n_particles": 0,
            "estimated_opp_reservation": my_reservation,
        },
    }
