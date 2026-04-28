import numpy as np
from typing import Tuple, Dict, Any, Optional

def fit_market_distribution(p25: float, p50: float, p75: float, p90: float) -> Tuple[float, float]:
    """
    Fit a log-normal distribution to market rate percentiles.
    Returns (mu, sigma) of the underlying normal distribution.
    Uses the IQR method: sigma = (ln(p75) - ln(p25)) / (2 * z_0.25)
    where z_0.25 = 0.6745.
    """
    mu = np.log(p50)
    sigma = (np.log(p75) - np.log(p25)) / (2 * 0.6745)
    return float(mu), float(sigma)

def establish_prior(market_data: Optional[Dict], user_target: float, historical_avg: Optional[float] = None, is_flat_fee: bool = False) -> Tuple[float, float, float]:
    """
    Fuses public market data with user history to establish the prior.
    Returns (mu, sigma, median).
    """
    rate = user_target or 0
    if market_data and not is_flat_fee:
        p25 = market_data["hourly"]["p25"]
        p50 = market_data["hourly"]["median"]
        p75 = market_data["hourly"]["p75"]
        p90 = market_data["hourly"]["p90"]
        # Blend in history if provided
        if historical_avg and historical_avg > 0:
            weight = 0.3 # Give user history 30% weight
            p50 = (p50 * (1.0 - weight)) + (historical_avg * weight)
            # Rebalance bounds relative to new median
            p25 = p50 * 0.75
            p75 = p50 * 1.25
            p90 = p50 * 1.75
    else:
        # Fallback to user rate geometry
        p25, p50, p75, p90 = rate * 0.75, rate, rate * 1.25, rate * 1.75
        if p50 == 0:
            p25, p50, p75, p90 = 10, 20, 30, 40 # ultimate absolute fallback
            
    mu, sigma = fit_market_distribution(p25, p50, p75, p90)
    return mu, sigma, p50
