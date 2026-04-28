"""
Unified Game Theory Core.
Serves as the entrypoint for mathematical calculations.
"""

from typing import Dict, Any, Optional
from .core_math.rubinstein import compute_discount_factor, rubinstein_equilibrium
from .core_math.bayesian import (
    myerson_bid_analysis, 
    should_probe_first, 
    deadweight_loss_warning
)
from .market.priors import establish_prior

def calculate_optimal_counter(
    free_bounds: Dict[str, Any],
    client_constraints: Dict[str, Any],
    market_data: Optional[Dict[str, Any]],
    historical_avg: Optional[float],
    pipeline_count: int
) -> Dict[str, Any]:
    """
    Unified entry point enforcing the Zero-Tuning Abstraction.
    All parameters are purely derived from the language inputs or databases.
    """
    flat_fee_mode = free_bounds.get("total_hours") is None and free_bounds.get("hourly_rate") is None

    if flat_fee_mode:
        user_target = free_bounds.get("ideal_price", 0)
        user_batna = free_bounds.get("min_price", user_target * 0.85)
    else:
        user_target = free_bounds.get("hourly_rate") or 0
        user_batna = free_bounds.get("hourly_batna") or (user_target * 0.85)

    mu, sigma, p50 = establish_prior(market_data, user_target, historical_avg, flat_fee_mode)

    urgency = client_constraints.get("urgency_score", 0.5)
    timeline_days = client_constraints.get("timeline_days")

    delta_client = compute_discount_factor(urgency, timeline_days, 0)
    delta_freelancer = compute_discount_factor(0.2, None, pipeline_count)

    myerson = myerson_bid_analysis(user_batna, mu, sigma)
    optimal_target = myerson["optimal_bid"]

    total_hours = free_bounds.get("total_hours")
    
    if flat_fee_mode:
        anchor_total = optimal_target
        estimated_total_hours = None
    else:
        if not total_hours:
            if free_bounds.get("ideal_price") and user_target > 0:
                total_hours = free_bounds["ideal_price"] / user_target
            elif free_bounds.get("ideal_price") and market_data:
                total_hours = free_bounds["ideal_price"] / market_data["hourly"]["median"]
            elif free_bounds.get("min_price") and user_batna > 0:
                total_hours = free_bounds["min_price"] / user_batna
            else:
                total_hours = 40.0
                
        anchor_total = optimal_target * total_hours
        estimated_total_hours = total_hours

    anchor_days = client_constraints.get("timeline_days") or free_bounds.get("ideal_days") or 14
    anchor_revisions = free_bounds.get("ideal_revisions") or 1

    surplus = anchor_total - free_bounds["min_price"]
    rub = rubinstein_equilibrium(delta_freelancer, delta_client, surplus)

    voi = should_probe_first(mu, sigma, delta_freelancer, user_batna)
    p_accept = myerson["acceptance_probability"]
    dw_warning = deadweight_loss_warning(p_accept)

    return {
        "optimal_anchor": optimal_target,
        "target_days": int(anchor_days),
        "target_revisions": int(anchor_revisions),
        "total_project_quote": anchor_total,
        "estimated_total_hours": estimated_total_hours,
        "acceptance_probability": p_accept,
        "market_median": p50,
        "should_probe": voi["should_probe"],
        "deadweight_warning": dw_warning,
        "concession_ladder": rub["concession_ladder"],
        "minimum_batna_total": free_bounds["min_price"]
    }
