"""
Tier 1 buy-side handlers (Sprint 2).

The Pareto evidence shows buy-side cannot reach positive H2H margin via
parameter tuning alone in alternating-offers SAO. The defenses bundled here
attack the structural disadvantage from a different angle:

  1. detect_anchor_attack — z-score the seller's opening offer against a
     market prior. If anomalously high, recommend ignore / counter / walk.
  2. buy_next_offer — wraps the same SNHP math used sell-side but applies
     the buyer-side Pareto knob and a defense bundle.

The other half of the buy-side answer is the cryptographic first-strike in
gametheory.crypto.first_strike — a mechanism-design solution rather than a
strategy-tuning solution.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from bayesian_agent import BayesianParticleFilter  # noqa: E402
from core_math.rubinstein import rubinstein_equilibrium  # noqa: E402


# Empirical buy-side Pareto endpoints from snhp/pareto_frontier_buyer.json
# (this session's NSGA-II tuning). The buy-side curve is shifted: best
# margin is -0.025, not positive. The knob still trades deal-rate vs margin.
_BUY_ASP_START_DEAL_RATE_MAX = 0.527
_BUY_ASP_START_MARGIN_MAX = 0.867

_DEFAULT_PARTICLES = 500
_CONTRACT_GRID = np.linspace(0.0, 1.0, 50).reshape(-1, 1)


_VALID_DEFENSES = {
    "schelling_commitment",
    "anchor_attack_detection",
    "first_strike",  # informational — actual commit-reveal is a separate endpoint
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


# ─── Anchor-attack detection ─────────────────────────────────────────────────


def detect_anchor_attack(
    *,
    opponent_offer_history: list[float],
    market_prior: dict,
) -> dict:
    """
    Z-score the opponent's opening offer against a market prior on what a
    typical seller asks (in OUR utility space — low utility for us means
    seller asked high). If the opening is more than 2.5σ below the market
    mean (= more aggressive than 99% of typical sellers), flag as anchor
    attack and recommend a defense.

    market_prior shape: {mu: float, sigma: float} where mu is the mean
    utility-to-buyer of typical seller openings, and sigma is the std.

    Returns:
      {is_anchor_attack, z_score, severity ∈ [0,1], recommended_response,
       rationale}
    """
    if not opponent_offer_history:
        return {
            "is_anchor_attack": False,
            "z_score": 0.0,
            "severity": 0.0,
            "recommended_response": "ignore",
            "rationale": "No opponent offer to evaluate yet.",
        }
    if "mu" not in market_prior or "sigma" not in market_prior:
        raise ValueError("market_prior must contain {mu, sigma}")

    mu = float(market_prior["mu"])
    sigma = max(float(market_prior["sigma"]), 1e-6)
    opening = float(opponent_offer_history[0])

    # Negative z = opening was MORE aggressive (lower buyer-utility) than mean.
    z = (opening - mu) / sigma
    is_attack = z < -2.5
    severity = float(np.clip(-z / 4.0, 0.0, 1.0))  # z=-4 → severity 1.0

    if is_attack and severity > 0.7:
        recommended = "walk_away"
    elif is_attack:
        recommended = "counter_with_market"
    elif z < -1.5:
        recommended = "counter_with_market"
    else:
        recommended = "ignore"

    return {
        "is_anchor_attack": bool(is_attack),
        "z_score": round(z, 4),
        "severity": round(severity, 4),
        "recommended_response": recommended,
        "rationale": (
            f"Opening offer gives buyer utility {opening:.3f}; market prior "
            f"mean {mu:.3f}, sigma {sigma:.3f} → z-score {z:+.2f}. "
            f"{'ANCHOR ATTACK detected (z<-2.5).' if is_attack else 'Within normal range.'} "
            f"Recommended: {recommended}."
        ),
    }


# ─── buy_next_offer ──────────────────────────────────────────────────────────


def buy_next_offer(
    *,
    my_reservation: float,
    seller_offer_history: list[float],
    my_offer_history: list[float],
    deadline_rounds: int,
    pareto_knob: float = 0.5,
    defenses: Optional[list[str]] = None,
    market_prior: Optional[dict] = None,
    n_particles: int = _DEFAULT_PARTICLES,
    peer_mode: bool = False,
) -> dict:
    """
    Recommend the next buyer-side offer.

    Same shape as sell.next_offer with two additions:
      - `defenses` is a list of opt-in defense names (validated; unknown
        names raise rather than silently drop).
      - `market_prior` is required when `anchor_attack_detection` is in
        `defenses`; otherwise ignored.
      - `peer_mode=True` activates the cooperative architecture (PEER
        playbook + signaling) when counterparty is a verified SNHP peer.

    Returns offer + acceptance_probability + warnings (a list of detected
    issues, including any anchor-attack flag) + defense_actions (suggestions
    the calling agent can act on).
    """
    if not 0.0 <= my_reservation <= 1.0:
        raise ValueError(f"my_reservation must be in [0, 1], got {my_reservation}")
    if not 0.0 <= pareto_knob <= 1.0:
        raise ValueError(f"pareto_knob must be in [0, 1], got {pareto_knob}")
    if deadline_rounds < 1:
        raise ValueError("deadline_rounds must be >= 1")

    # Peer-mode delegates to the shared cooperative recommendation.
    if peer_mode:
        from gametheory.negotiation.sell import _peer_mode_recommendation
        result = _peer_mode_recommendation(
            my_reservation=my_reservation,
            opponent_offer_history=seller_offer_history,
            my_offer_history=my_offer_history,
            deadline_rounds=deadline_rounds,
            role="buyer",
        )
        result["warnings"] = []
        result["defense_actions"] = []
        return result

    # Default omits anchor_attack_detection because that defense requires a
    # market_prior; we don't make the default raise on callers who don't
    # supply one. Pass it explicitly together with market_prior to opt in.
    defenses = defenses if defenses is not None else ["schelling_commitment"]
    unknown = [d for d in defenses if d not in _VALID_DEFENSES]
    if unknown:
        raise ValueError(
            f"unknown defense(s) {unknown}; valid: {sorted(_VALID_DEFENSES)}"
        )

    warnings: list[dict] = []
    defense_actions: list[dict] = []

    # ── Defense: anchor-attack detection ────────────────────────────────
    if "anchor_attack_detection" in defenses:
        if market_prior is None:
            raise ValueError(
                "anchor_attack_detection defense requires market_prior={mu, sigma}"
            )
        attack = detect_anchor_attack(
            opponent_offer_history=seller_offer_history,
            market_prior=market_prior,
        )
        if attack["is_anchor_attack"]:
            warnings.append({
                "code": "anchor_attack_detected",
                "severity": "high" if attack["severity"] > 0.7 else "medium",
                "msg": attack["rationale"],
            })
            defense_actions.append({
                "action": attack["recommended_response"],
                "z_score": attack["z_score"],
            })

    # ── Aspiration curve from buyer-side Pareto knob ────────────────────
    asp_start = _lerp(_BUY_ASP_START_DEAL_RATE_MAX, _BUY_ASP_START_MARGIN_MAX, pareto_knob)
    # Schelling commitment is just-above reservation; floor of the aspiration
    # curve IS reservation so we'll close at deadline if there's any deal in
    # the zone of agreement.
    schelling_floor = my_reservation + min(0.05, 0.5 * (1.0 - my_reservation))
    asp_floor = my_reservation

    # Total alternating-offer rounds elapsed — sum, not max (see sell.py).
    rounds_used = len(my_offer_history) + len(seller_offer_history)
    time_fraction = min(1.0, rounds_used / max(deadline_rounds, 1))
    base_exp = 3.0
    aspiration = asp_start - (asp_start - asp_floor) * (time_fraction ** base_exp)

    # ── Bayesian inference on seller offers ─────────────────────────────
    b_filter = BayesianParticleFilter(
        num_variables=1, num_particles=n_particles, uncertainty=0.2
    )
    for seller_util_to_us in seller_offer_history:
        seller_util_to_self = max(0.0, min(1.0, 1.0 - float(seller_util_to_us)))
        b_filter.update_beliefs(np.array([seller_util_to_self]), _CONTRACT_GRID)
    inferred = b_filter.get_inferred_weights()
    inferred_seller_weight = float(inferred[0])
    spread = float(np.std(b_filter.particles[:, 0]))
    confidence = float(np.clip(1.0 - spread * 2.5, 0.05, 0.95))

    # ── Rubinstein floor (buyer = SECOND mover, so 1 - first-mover share) ─
    seller_rv_estimate = float(np.clip(0.4 - 0.2 * inferred_seller_weight, 0.1, 0.6))
    surplus = max(0.01, (1.0 - my_reservation) - seller_rv_estimate)
    my_discount = 0.92
    seller_discount = 0.95
    rub_swapped = rubinstein_equilibrium(seller_discount, my_discount, surplus)
    my_share = 1.0 - rub_swapped["freelancer_share"]
    rubinstein_floor = my_reservation + surplus * my_share

    # ── Recommendation ──────────────────────────────────────────────────
    # Same logic as sell.py: only enforce the SPE floor when the opponent
    # is also playing a firm/equilibrium strategy. Against a conceding
    # opponent, trust the aspiration curve to land deals.
    if len(seller_offer_history) >= 2:
        opp_concession = seller_offer_history[-1] - seller_offer_history[0]
    else:
        opp_concession = 0.0
    if opp_concession > 0.05:
        recommended = max(aspiration, schelling_floor)
    else:
        recommended = max(aspiration, rubinstein_floor)
    recommended = min(recommended, 0.99)

    seller_util_from_offer = 1.0 - recommended
    if seller_util_from_offer <= seller_rv_estimate:
        accept_prob = 0.05
    else:
        accept_prob = float(np.clip(
            (seller_util_from_offer - seller_rv_estimate)
            / (1.0 - seller_rv_estimate + 1e-9),
            0.05, 0.95,
        ))

    expected_payoff = accept_prob * recommended + (1.0 - accept_prob) * my_reservation

    return {
        "recommended_offer": round(recommended, 4),
        "acceptance_probability": round(accept_prob, 4),
        "expected_payoff": round(expected_payoff, 4),
        "warnings": warnings,
        "defense_actions": defense_actions,
        "rationale": (
            f"buyer-side, pareto_knob={pareto_knob:.2f} → asp_start={asp_start:.3f}; "
            f"round {rounds_used}/{deadline_rounds} (t={time_fraction:.2f}) → "
            f"aspiration={aspiration:.3f}; Rubinstein floor (second-mover-corrected)"
            f"={rubinstein_floor:.3f}; recommended max={recommended:.3f}. "
            f"Inferred seller price-weight {inferred_seller_weight:.2f} (confidence {confidence:.2f})."
        ),
        "posterior": {
            "inferred_seller_price_weight": round(inferred_seller_weight, 4),
            "confidence": round(confidence, 4),
            "n_particles": n_particles,
            "estimated_seller_reservation": round(seller_rv_estimate, 4),
        },
        "rubinstein_share": round(my_share, 4),
        "schelling_floor": round(asp_floor, 4),
    }
