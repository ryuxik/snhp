import numpy as np
from numba import jit
from typing import Optional, Dict, Any

@jit(nopython=True)
def _compute_rubinstein_core(delta_freelancer: float, delta_client: float, surplus: float) -> tuple:
    denom = 1.0 - (delta_freelancer * delta_client)
    if denom < 1e-10:
        freelancer_share = 0.5
    else:
        freelancer_share = (1.0 - delta_client) / denom
        
    freelancer_value = freelancer_share * surplus
    client_value = (1.0 - freelancer_share) * surplus
    
    # Pre-allocate ladder array: (round_num, share, claim) for up to 4 rounds
    ladder_data = np.zeros((4, 3))
    current_claim = freelancer_share
    for r in range(4):
        ladder_data[r, 0] = r + 1
        ladder_data[r, 1] = current_claim
        ladder_data[r, 2] = current_claim * surplus
        current_claim *= delta_freelancer
        
    return freelancer_share, freelancer_value, client_value, ladder_data

def compute_discount_factor(urgency_score: float, days_until_deadline: Optional[int], pipeline_count: int) -> float:
    """
    Map observable signals to a discount factor \u03b4 \u2208 (0, 1).
    Higher \u03b4 = more patient = stronger bargaining position.
    """
    delta_from_urgency = 0.95 - (urgency_score * 0.45)

    if days_until_deadline is not None and days_until_deadline > 0:
        delta_from_days = min(0.95, 0.50 + (days_until_deadline / 30.0) * 0.45)
    else:
        delta_from_days = delta_from_urgency

    delta_base = np.sqrt(delta_from_urgency * delta_from_days)
    pipeline_boost = min(pipeline_count * 0.02, 0.10)

    return float(min(0.98, delta_base + pipeline_boost))

def rubinstein_equilibrium(delta_freelancer: float, delta_client: float, surplus: float) -> Dict[str, Any]:
    """
    Rubinstein (1982) alternating-offers SPE.
    """
    f_share, f_val, c_val, ladder_data = _compute_rubinstein_core(delta_freelancer, delta_client, surplus)
    
    ladder = []
    for r in range(4):
        ladder.append({
            "round": int(ladder_data[r, 0]),
            "freelancer_share_pct": round(float(ladder_data[r, 1]) * 100, 1),
            "surplus_claim": round(float(ladder_data[r, 2]), 2),
        })

    return {
        "freelancer_share": round(float(f_share), 4),
        "client_share": round(1.0 - float(f_share), 4),
        "freelancer_value": round(float(f_val), 2),
        "client_value": round(float(c_val), 2),
        "delta_freelancer": round(float(delta_freelancer), 4),
        "delta_client": round(float(delta_client), 4),
        "concession_ladder": ladder,
    }
