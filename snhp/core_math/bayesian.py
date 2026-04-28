import numpy as np
import math
from numba import jit
from scipy import stats
from typing import Tuple, Dict, Any, Optional

@jit(nopython=True)
def _optimal_bid_search(reservation_rate: float, mu: float, sigma: float, search_res: int, upper: float) -> float:
    candidates = np.linspace(reservation_rate, upper, search_res)
    best_candidate = candidates[0]
    max_payoff = -1.0
    
    # Numba lacks scipy.stats, so we build CDF via math.erfc
    for i in range(search_res):
        c = candidates[i]
        # CDF of lognorm(mu, sigma) = 0.5 + 0.5 * erf((ln(c) - mu)/(sigma * sqrt(2)))
        # survival = 1 - CDF = 0.5 * erfc((ln(c) - mu)/(sigma * sqrt(2)))
        if c <= 0:
            continue
        z = (math.log(c) - mu) / (sigma * math.sqrt(2.0))
        survival = 0.5 * math.erfc(z)
        
        margin = c - reservation_rate
        payoff = margin * survival
        if payoff > max_payoff:
            max_payoff = payoff
            best_candidate = c
            
    return best_candidate

def acceptance_probability(offer_rate: float, mu: float, sigma: float) -> float:
    return float(1.0 - stats.lognorm.cdf(offer_rate, s=sigma, scale=np.exp(mu)))

def _expected_payoff(offer_rate: float, reservation_rate: float, mu: float, sigma: float) -> float:
    margin = offer_rate - reservation_rate
    survival = acceptance_probability(offer_rate, mu, sigma)
    return margin * survival

def optimal_bid_myerson(reservation_rate: float, mu: float, sigma: float, search_resolution: int = 1000) -> float:
    # Use scipy to quickly find the 99th percentile upper bound for search, then Numba search
    dist = stats.lognorm(s=sigma, scale=np.exp(mu))
    upper = dist.ppf(0.99)
    return float(_optimal_bid_search(reservation_rate, mu, sigma, search_resolution, upper))

def myerson_bid_analysis(reservation_rate: float, mu: float, sigma: float) -> Dict[str, Any]:
    b_star = optimal_bid_myerson(reservation_rate, mu, sigma)
    survival = acceptance_probability(b_star, mu, sigma)
    
    dist = stats.lognorm(s=sigma, scale=np.exp(mu))
    f_val = dist.pdf(b_star)
    inv_hazard = survival / f_val if f_val > 1e-10 else float('inf')

    return {
        "optimal_bid": round(b_star, 2),
        "acceptance_probability": round(survival, 4),
        "expected_payoff_per_unit": round((b_star - reservation_rate) * survival, 2),
        "inverse_hazard_rate": round(inv_hazard, 2),
        "markup_over_reservation": round(b_star - reservation_rate, 2),
        "markup_pct": round(((b_star / reservation_rate) - 1) * 100, 1) if reservation_rate > 0 else None,
    }

def von_neumann_optimal_bid(
    reservation_rate: float,
    mu: float,
    sigma: float,
    risk_aversion: float = 0.7,
    safety_percentile: float = 0.75,
) -> Dict[str, Any]:
    """
    Von Neumann-Morgenstern Expected Utility bid (CRRA risk-averse).

    Instead of maximizing risk-neutral E[payoff] = (b - v_s) × P(accept|b),
    maximizes E[U(payoff)] = (b - v_s)^α × P(accept|b)
    where α < 1 is the CRRA risk aversion parameter.

    This naturally penalizes aggressive bids: the concave utility function
    means the marginal value of each extra dollar extracted diminishes,
    while the marginal cost of lower deal probability stays constant.
    Result: the optimizer gravitates toward bids with higher deal completion.

    Safety clamp at the given percentile of buyer WTP distribution prevents
    pathological overbids in thin markets.

    Args:
        reservation_rate: Seller's walk-away price (BATNA)
        mu: Log-normal μ of buyer WTP distribution
        sigma: Log-normal σ of buyer WTP distribution
        risk_aversion: CRRA α parameter. 1.0 = risk-neutral, 0.5 = very risk-averse
        safety_percentile: Max bid = this percentile of buyer WTP (deal-kill prevention)

    Returns:
        Dict with optimal_bid, acceptance_probability, expected_utility, buyer_ceiling
    """
    from scipy.optimize import minimize_scalar

    dist = stats.lognorm(s=sigma, scale=np.exp(mu))

    # Safety ceiling: percentile of buyer WTP distribution.
    # P75 means "75% of buyers have WTP below this" → at least 25% accept.
    buyer_ceiling = float(dist.ppf(safety_percentile))
    upper_bound = max(buyer_ceiling, reservation_rate * 1.5 + 1.0)

    def neg_expected_utility(bid):
        if bid <= reservation_rate:
            return 0.0
        survival = float(1.0 - dist.cdf(bid))
        if survival <= 1e-10:
            return 0.0
        margin = bid - reservation_rate
        # CRRA utility: U(x) = x^α. Concave for α < 1.
        utility = (margin ** risk_aversion) * survival
        return -utility

    result = minimize_scalar(
        neg_expected_utility,
        bounds=(reservation_rate, upper_bound),
        method='bounded'
    )

    optimal_bid = min(result.x, buyer_ceiling)
    optimal_bid = max(optimal_bid, reservation_rate * 1.01)

    p_accept = acceptance_probability(optimal_bid, mu, sigma)

    return {
        "optimal_bid": round(float(optimal_bid), 2),
        "acceptance_probability": round(float(p_accept), 4),
        "expected_utility": round(float(-result.fun), 4),
        "buyer_ceiling": round(float(buyer_ceiling), 2),
        "risk_aversion": risk_aversion,
    }


def deadweight_loss_warning(p_accept: float) -> Optional[str]:
    if p_accept >= 0.60:
        return None
    if p_accept >= 0.30:
        return (
            f"Acceptance probability is {p_accept:.0%}. Roughly {1-p_accept:.0%} of efficient trades "
            "fail due to information asymmetry."
        )
    return (
        f"Acceptance probability is only {p_accept:.0%}. "
        "The Myerson-Satterthwaite bound implies significant deadweight loss."
    )

def should_probe_first(mu: float, sigma: float, delta_freelancer: float, reservation_rate: float) -> Dict[str, Any]:
    e_payoff_now = _expected_payoff(optimal_bid_myerson(reservation_rate, mu, sigma), reservation_rate, mu, sigma)
    cost_of_delay = (1.0 - delta_freelancer) * e_payoff_now
    
    distribution_variance = (np.exp(sigma**2) - 1) * np.exp(2*mu + sigma**2)
    distribution_cv = np.sqrt(distribution_variance) / np.exp(mu + sigma**2/2)
    
    voi_estimate = distribution_cv * e_payoff_now * 0.5
    net_voi = voi_estimate - cost_of_delay
    
    return {
        "should_probe": net_voi > 0,
        "voi_estimate": round(voi_estimate, 2),
        "cost_of_delay": round(cost_of_delay, 2),
        "net_voi": round(net_voi, 2),
        "distribution_cv": round(distribution_cv, 4),
    }
