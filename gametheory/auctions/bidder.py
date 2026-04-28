"""
Tier 2 auction bidder-side handlers.

Reuses snhp/core_math/bayesian.py for the lognormal Myerson math. The
bidder-side surface covers first-price (with BNE), second-price/Vickrey
(truthful is dominant), and English ascending. Multi-unit / combinatorial
auctions are explicitly out of scope for v1.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import stats

from gametheory._internal import (
    VALID_AUCTION_FORMATS,
    ensure_snhp_path,  # noqa: F401  (side-effect import)
    validate_prior,
)

from core_math.bayesian import (  # noqa: E402
    optimal_bid_myerson,
    acceptance_probability,
    von_neumann_optimal_bid,
)


def _first_price_bne_uniform(my_valuation: float, n_bidders: int,
                              low: float, high: float) -> float:
    """
    Closed-form first-price BNE for symmetric uniform[low, high] valuations.
    With N bidders total, equilibrium bid = low + (my_val - low) * (N-1)/N.
    """
    if my_valuation <= low:
        return float(low)
    return float(low + (my_valuation - low) * (n_bidders - 1) / n_bidders)


def _first_price_bne_lognormal(my_valuation: float, n_bidders: int,
                                mu: float, sigma: float) -> float:
    """
    Numerical first-price BNE for lognormal valuations with N bidders.

    BNE under symmetric IPV: b(v) = E[max v_{-i} | max v_{-i} <= v]
    For F(x) being the CDF of a single competitor, the max of (N-1) iid
    competitors has CDF F(x)^(N-1). Conditional expectation:
        b(v) = v - integral_0^v F(x)^(N-1) dx / F(v)^(N-1)
    """
    if my_valuation <= 0:
        return 0.0
    dist = stats.lognorm(s=sigma, scale=np.exp(mu))
    grid = np.linspace(1e-6, my_valuation, 200)
    f_pow = dist.cdf(grid) ** (n_bidders - 1)
    # Numerical integration via trapezoid
    integral = float(np.trapezoid(f_pow, grid))
    f_v = dist.cdf(my_valuation) ** (n_bidders - 1)
    if f_v < 1e-9:
        return float(my_valuation * 0.5)
    return float(my_valuation - integral / f_v)


def optimal_bid(
    *,
    auction_format: str,
    my_valuation: float,
    n_competing_bidders: int,
    competitor_value_prior: dict,
    reserve_price: Optional[float] = None,
    risk_aversion: float = 1.0,
) -> dict:
    """
    Recommend a bid for the given auction format. All values in arbitrary
    monetary units (the API doesn't care).

    Returns: {optimal_bid, expected_surplus, win_probability,
              dominant_strategy, rationale}.
    """
    if auction_format not in VALID_AUCTION_FORMATS:
        raise ValueError(
            f"auction_format must be one of {VALID_AUCTION_FORMATS}, got {auction_format!r}"
        )
    if my_valuation <= 0:
        raise ValueError("my_valuation must be positive")
    if n_competing_bidders < 1:
        raise ValueError("n_competing_bidders must be >= 1")
    validate_prior(competitor_value_prior)
    if not 0.1 <= risk_aversion <= 1.0:
        raise ValueError("risk_aversion must be in [0.1, 1.0] (CRRA α)")

    family = competitor_value_prior["family"]
    params = competitor_value_prior["params"]
    n_total = n_competing_bidders + 1  # bidders incl. me

    # ── Vickrey: dominant strategy is truthful ─────────────────────────
    if auction_format == "second_price_vickrey":
        bid = my_valuation
        if reserve_price is not None and bid < reserve_price:
            return {
                "optimal_bid": 0.0,
                "expected_surplus": 0.0,
                "win_probability": 0.0,
                "dominant_strategy": True,
                "rationale": (
                    f"Vickrey: truthful bid is dominant. Your valuation "
                    f"{my_valuation:.2f} is below reserve {reserve_price:.2f}; "
                    f"abstain (no positive expected surplus)."
                ),
            }
        # Win probability: (P(my_val > all competitors)) under iid prior
        if family == "lognorm":
            dist = stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
            p_win_each = float(dist.cdf(my_valuation))
        else:
            low, high = params["low"], params["high"]
            if my_valuation >= high:
                p_win_each = 1.0
            elif my_valuation <= low:
                p_win_each = 0.0
            else:
                p_win_each = float((my_valuation - low) / (high - low))
        win_prob = p_win_each ** n_competing_bidders
        # Expected surplus in Vickrey = E[my_val - second_highest | win]
        # Approximation: my_val - E[second_highest of N-1 competitors below my_val]
        # For uniform[low, high] given truncation: mean of max of (N-1) draws
        # below my_val is low + (my_val - low) * (N-1)/N.
        # We use this for a quick estimate; lognorm gets a numerical answer.
        if family == "uniform":
            second_highest_est = params["low"] + (my_valuation - params["low"]) * (n_competing_bidders - 1) / max(n_competing_bidders, 1)
        else:
            grid = np.linspace(1e-6, my_valuation, 200)
            cdf_vals = dist.cdf(grid)
            pdf_competitors_max = n_competing_bidders * (cdf_vals ** (n_competing_bidders - 1)) * dist.pdf(grid)
            second_highest_est = float(np.trapezoid(grid * pdf_competitors_max, grid)) / max(p_win_each ** n_competing_bidders, 1e-9)
            second_highest_est = float(np.clip(second_highest_est, 0.0, my_valuation))
        expected_surplus = win_prob * (my_valuation - second_highest_est)
        return {
            "optimal_bid": round(my_valuation, 4),
            "expected_surplus": round(expected_surplus, 4),
            "win_probability": round(win_prob, 4),
            "dominant_strategy": True,
            "rationale": (
                f"Vickrey: truthful bidding is the dominant strategy. Bid your "
                f"valuation {my_valuation:.2f}. Pay second-highest competing bid "
                f"if you win. Win prob {win_prob:.2%}."
            ),
        }

    # ── English ascending ──────────────────────────────────────────────
    if auction_format == "english_ascending":
        # Drop out at your valuation. Same revenue equivalence as Vickrey
        # under symmetric IPV. Reserve handled at runtime by the auctioneer.
        return {
            "optimal_bid": round(my_valuation, 4),
            "expected_surplus": None,  # depends on competitors' bids in real time
            "win_probability": None,
            "dominant_strategy": True,
            "rationale": (
                f"English ascending: stay in until current price reaches your "
                f"valuation {my_valuation:.2f}, then drop out. Equivalent to "
                f"Vickrey under symmetric IPV."
            ),
        }

    # ── First-price ────────────────────────────────────────────────────
    # Closed form for uniform; numerical inversion for lognormal.
    # Risk aversion (CRRA α<1) shifts BNE: with α<1 the bidder bids higher.
    if family == "uniform":
        bid = _first_price_bne_uniform(my_valuation, n_total,
                                        params["low"], params["high"])
    else:
        if risk_aversion < 1.0:
            # Reuse von_neumann_optimal_bid which handles risk aversion.
            # Note: that function uses (mu, sigma) as the bidder's lognormal
            # WTP, not competitor's. For BNE we want competitors' distribution.
            # We use it here as an approximation — for v1, document the
            # limitation. Production v2 should derive the risk-averse BNE
            # explicitly under N-bidder symmetric IPV.
            res = von_neumann_optimal_bid(
                reservation_rate=my_valuation * 0.6,  # placeholder
                mu=params["mu"], sigma=params["sigma"],
                risk_aversion=risk_aversion,
            )
            bid = min(res["optimal_bid"], my_valuation * 0.99)
        else:
            bid = _first_price_bne_lognormal(my_valuation, n_total,
                                              params["mu"], params["sigma"])

    if reserve_price is not None:
        if bid < reserve_price and my_valuation < reserve_price:
            return {
                "optimal_bid": 0.0,
                "expected_surplus": 0.0,
                "win_probability": 0.0,
                "dominant_strategy": False,
                "rationale": (
                    f"First-price with reserve {reserve_price:.2f}: your "
                    f"valuation {my_valuation:.2f} is below reserve, abstain."
                ),
            }
        bid = max(bid, reserve_price)

    # Win probability under N competitors using lognormal CDF
    if family == "lognorm":
        dist = stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))
        # Win iff bid > max of competitors' bids. Under symmetric BNE,
        # bid is monotone in valuation, so P(win) ≈ P(my_val > all comp_vals)
        p_each = float(dist.cdf(my_valuation))
    else:
        low, high = params["low"], params["high"]
        p_each = float(np.clip((my_valuation - low) / (high - low), 0.0, 1.0))
    win_prob = p_each ** n_competing_bidders
    expected_surplus = win_prob * (my_valuation - bid)

    return {
        "optimal_bid": round(float(bid), 4),
        "expected_surplus": round(float(expected_surplus), 4),
        "win_probability": round(float(win_prob), 4),
        "dominant_strategy": False,
        "rationale": (
            f"First-price BNE for {family} prior with {n_competing_bidders} "
            f"competitors: bid {bid:.2f} (your valuation {my_valuation:.2f}). "
            f"Win probability {win_prob:.2%}, expected surplus "
            f"{expected_surplus:.2f}."
        ),
    }
