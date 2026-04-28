"""
Tier 2 auction seller-side handlers (running an auction, not bidding in one).

Covers:
  - optimal_reserve: Myerson virtual-value-zero reserve
  - format_recommendation: which auction format given seller weights
  - simulate: Monte Carlo revenue / efficiency estimate
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from gametheory._internal import (
    VALID_AUCTION_FORMATS, validate_prior, sample_prior, myerson_reserve,
)


def optimal_reserve(
    *,
    bidder_value_prior: dict,
    n_bidders: int,
    seller_valuation: float,
) -> dict:
    """
    Myerson optimal reserve price. The reserve is independent of N for symmetric
    IPV and equals the value v* solving virtual_value(v*) = seller_valuation.
    """
    validate_prior(bidder_value_prior)
    if n_bidders < 1:
        raise ValueError("n_bidders must be >= 1")
    if seller_valuation < 0:
        raise ValueError("seller_valuation must be non-negative")
    family = bidder_value_prior["family"]

    reserve = myerson_reserve(bidder_value_prior, seller_valuation)

    rng = np.random.default_rng(seed=42)
    sims = np.column_stack([
        sample_prior(bidder_value_prior, 5000, rng) for _ in range(n_bidders)
    ])
    max_bid = sims.max(axis=1)
    if n_bidders > 1:
        second_high = np.partition(sims, -2, axis=1)[:, -2]
        revenue = np.where(max_bid >= reserve, np.maximum(reserve, second_high), 0.0)
        no_reserve_revenue = float(second_high.mean())
    else:
        revenue = np.where(max_bid >= reserve, reserve, 0.0)
        no_reserve_revenue = 0.0
    expected_revenue = float(revenue.mean())

    efficiency_loss = max(0.0, no_reserve_revenue - expected_revenue) if no_reserve_revenue > 0 else 0.0

    return {
        "reserve_price": round(reserve, 4),
        "expected_revenue": round(expected_revenue, 4),
        "expected_revenue_no_reserve": round(no_reserve_revenue, 4),
        "expected_efficiency_loss": round(efficiency_loss, 4),
        "rationale": (
            f"Myerson optimal reserve for {family} prior with seller_valuation="
            f"{seller_valuation:.2f}: solve virtual_value(v) = {seller_valuation:.2f} "
            f"→ v* = {reserve:.2f}. MC revenue estimate ({5000} sims, N={n_bidders}): "
            f"with reserve {expected_revenue:.2f}, without {no_reserve_revenue:.2f}."
        ),
    }


def format_recommendation(
    *,
    bidder_value_prior: dict,
    n_bidders: int,
    seller_valuation: float,
    weights: Optional[dict] = None,
) -> dict:
    """
    Recommend an auction format. Under symmetric IPV with risk-neutral bidders,
    Revenue Equivalence holds — all four standard formats yield the same expected
    revenue. The recommendation diverges based on:
      - speed weight: Vickrey/English close in one round; first-price needs sealed bids
      - transparency: English is publicly observable; first-price is sealed
      - complexity: Vickrey requires bidders to understand truthful bidding is dominant
                    (lab evidence: bidders often overbid in Vickrey because they don't trust it)
    """
    validate_prior(bidder_value_prior)
    weights = weights or {"revenue": 1.0, "speed": 0.0, "transparency": 0.0}
    w_rev = float(weights.get("revenue", 1.0))
    w_speed = float(weights.get("speed", 0.0))
    w_trans = float(weights.get("transparency", 0.0))

    # Get reserve-based revenue estimate (revenue equivalence means same across formats)
    res = optimal_reserve(
        bidder_value_prior=bidder_value_prior,
        n_bidders=n_bidders,
        seller_valuation=seller_valuation,
    )
    base_revenue = res["expected_revenue"]

    by_format = {
        "first_price": {
            "expected_revenue": base_revenue,
            "speed_score": 0.5,        # sealed bids; one round
            "transparency_score": 0.2,  # bids hidden until reveal
            "complexity_for_bidders": 0.6,  # BNE is non-trivial
        },
        "second_price_vickrey": {
            "expected_revenue": base_revenue,
            "speed_score": 0.7,        # one round, dominant strategy
            "transparency_score": 0.4,  # winner pays second-highest
            "complexity_for_bidders": 0.4,  # truthful is dominant if explained
        },
        "english_ascending": {
            "expected_revenue": base_revenue,
            "speed_score": 0.4,        # multiple rounds of bidding
            "transparency_score": 0.9,  # publicly visible bid trajectory
            "complexity_for_bidders": 0.2,  # intuitive
        },
    }

    # Score each format by weighted sum
    scores = {}
    for fmt, data in by_format.items():
        scores[fmt] = (
            w_rev * (data["expected_revenue"] / max(base_revenue, 1e-9))
            + w_speed * data["speed_score"]
            + w_trans * data["transparency_score"]
        )
    recommended = max(scores, key=scores.get)

    return {
        "recommended_format": recommended,
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "expected_revenue_by_format": {k: v["expected_revenue"] for k, v in by_format.items()},
        "rationale": (
            f"Symmetric IPV revenue equivalence: all formats give expected revenue "
            f"{base_revenue:.2f}. With weights revenue={w_rev:.2f}, speed={w_speed:.2f}, "
            f"transparency={w_trans:.2f}, recommended format is {recommended}."
        ),
    }


def simulate(
    *,
    auction_format: str,
    bidder_priors: list[dict],
    reserve_price: float,
    n_simulations: int = 10_000,
    seed: Optional[int] = None,
) -> dict:
    """
    Monte Carlo auction simulation. Returns mean revenue, 95% CI, and
    efficiency (fraction of trades where the highest-valuation bidder wins).
    """
    if auction_format not in VALID_AUCTION_FORMATS:
        raise ValueError(f"auction_format must be one of {VALID_AUCTION_FORMATS}")
    if not bidder_priors:
        raise ValueError("bidder_priors must be non-empty")
    for p in bidder_priors:
        validate_prior(p)
    if n_simulations < 100:
        raise ValueError("n_simulations must be >= 100")

    rng = np.random.default_rng(seed=seed if seed is not None else 42)
    n_bidders = len(bidder_priors)

    valuations = np.column_stack([
        sample_prior(p, n_simulations, rng) for p in bidder_priors
    ])

    # Sort each row to find highest and second-highest
    sorted_vals = np.sort(valuations, axis=1)
    highest = sorted_vals[:, -1]
    second_highest = sorted_vals[:, -2] if n_bidders > 1 else np.zeros(n_simulations)
    winner_idx = np.argmax(valuations, axis=1)

    # Determine revenue based on format
    if auction_format == "second_price_vickrey" or auction_format == "english_ascending":
        # Revenue = second-highest if highest >= reserve else 0
        # If second-highest < reserve, winner pays reserve (assuming highest >= reserve).
        revenue = np.where(
            highest >= reserve_price,
            np.maximum(reserve_price, second_highest),
            0.0,
        )
    else:  # first_price
        # Bidders shade their bids. For uniform we can compute analytical BNE
        # contribution but for mixed priors that's complex. Approximation:
        # under symmetric IPV with same prior, bid ≈ E[max v_{-i} | max < v]
        # which we approximate as v * (N-1)/N.
        bids = valuations * (n_bidders - 1) / n_bidders
        max_bids = bids.max(axis=1)
        revenue = np.where(max_bids >= reserve_price, max_bids, 0.0)

    mean_rev = float(np.mean(revenue))
    ci_lo = float(np.percentile(revenue, 2.5))
    ci_hi = float(np.percentile(revenue, 97.5))
    efficiency = float(np.mean(highest >= reserve_price))

    winner_dist = np.bincount(winner_idx[highest >= reserve_price], minlength=n_bidders)
    winner_dist = (winner_dist / max(winner_dist.sum(), 1)).tolist()

    return {
        "mean_revenue": round(mean_rev, 4),
        "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "efficiency": round(efficiency, 4),
        "winner_index_distribution": [round(p, 4) for p in winner_dist],
        "n_simulations": n_simulations,
    }
