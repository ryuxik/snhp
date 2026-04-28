"""
Myerson optimal auction design with asymmetric independent private values.

Under symmetric regular IPV the mechanism collapses to second-price-with-
reserve. Asymmetric priors yield per-bidder reserves and an allocation
rule that picks the highest *virtual* value (not the highest raw bid).
"""
from __future__ import annotations

import numpy as np
from typing import Literal

from gametheory._internal import (
    validate_prior, prior_to_scipy_dist, sample_prior, myerson_reserve,
)


_MAX_BIDDERS = 50
_DEFAULT_SIMULATIONS = 5_000

# Lognormal is non-regular (heavy-tailed → ironing required) above this sigma;
# the exact cutoff varies with mu but 1.2 is a conservative practical bound.
_LOGNORM_REGULAR_SIGMA_CUTOFF = 1.2


def _virtual_values(prior: dict, samples: np.ndarray) -> np.ndarray:
    """ψ(v) = v - (1 - F(v))/f(v) over an array of valuations."""
    family = prior["family"]
    params = prior["params"]
    if family == "uniform":
        return 2.0 * samples - params["high"]
    dist = prior_to_scipy_dist(prior)
    F = dist.cdf(samples)
    f = dist.pdf(samples)
    f_safe = np.where(f < 1e-12, 1e-12, f)
    return samples - (1.0 - F) / f_safe


def optimal_auction_design(
    *,
    bidder_priors: list[dict],
    seller_valuation: float,
    objective: Literal["revenue", "welfare"] = "revenue",
    n_simulations: int = _DEFAULT_SIMULATIONS,
    seed: int = 42,
) -> dict:
    if objective not in {"revenue", "welfare"}:
        raise ValueError(f"objective must be 'revenue' or 'welfare', got {objective!r}")
    if not bidder_priors:
        raise ValueError("bidder_priors must be non-empty")
    if len(bidder_priors) > _MAX_BIDDERS:
        raise ValueError(
            f"n_bidders={len(bidder_priors)} > {_MAX_BIDDERS}; "
            "the math is fine but the MC estimate becomes slow"
        )
    if seller_valuation < 0:
        raise ValueError("seller_valuation must be non-negative")
    for p in bidder_priors:
        validate_prior(p)

    n = len(bidder_priors)
    rng = np.random.default_rng(seed)
    valuations = np.column_stack([
        sample_prior(p, n_simulations, rng) for p in bidder_priors
    ])

    if objective == "welfare":
        winner = np.argmax(valuations, axis=1)
        revenue = (np.partition(valuations, -2, axis=1)[:, -2]
                   if n > 1 else np.zeros(n_simulations))
        return {
            "mechanism": "vcg_no_reserve",
            "reserve_prices": {},
            "expected_revenue": round(float(revenue.mean()), 4),
            "expected_welfare": round(float(
                valuations[np.arange(n_simulations), winner].mean()
            ), 4),
            "ironing_required": False,
            "rationale": (
                "Welfare-optimal under IPV is VCG: highest-valuation bidder "
                "wins, pays second-highest. No reserves needed."
            ),
        }

    bidder_ids = [p.get("id", f"bidder_{i}") for i, p in enumerate(bidder_priors)]
    reserves = {
        bidder_ids[i]: round(myerson_reserve(p, seller_valuation), 4)
        for i, p in enumerate(bidder_priors)
    }
    ironing_required = any(
        p["family"] == "lognorm"
        and p["params"]["sigma"] >= _LOGNORM_REGULAR_SIGMA_CUTOFF
        for p in bidder_priors
    )

    virtual = np.column_stack([
        _virtual_values(p, valuations[:, i]) for i, p in enumerate(bidder_priors)
    ])
    max_virtual = virtual.max(axis=1)
    winner = virtual.argmax(axis=1)
    sells = max_virtual >= seller_valuation

    chosen_reserves = np.array([reserves[bidder_ids[w]] for w in winner])
    if n > 1:
        # Threshold pricing approximation: max(winner's reserve, second-highest
        # valuation). Exact under symmetric IPV; an upper bound otherwise.
        second_high = np.partition(valuations, -2, axis=1)[:, -2]
        price = np.maximum(chosen_reserves, second_high)
    else:
        price = chosen_reserves
    revenue = np.where(sells, price, 0.0)

    return {
        "mechanism": "myerson_optimal",
        "reserve_prices": reserves,
        "expected_revenue": round(float(revenue.mean()), 4),
        "expected_welfare": round(float(np.where(
            sells, valuations[np.arange(n_simulations), winner], 0.0
        ).mean()), 4),
        "ironing_required": ironing_required,
        "rationale": (
            f"Revenue-optimal mechanism: allocate to argmax virtual value. "
            f"Bidder-specific reserves: {reserves}. "
            f"{'Ironing required for non-regular priors.' if ironing_required else 'All priors regular; no ironing.'}"
        ),
    }
