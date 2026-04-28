"""
SNHP Market Intelligence Layer.

Matches negotiation context to a freelancer category, then returns
percentile-based market rate data to inform Bayesian priors.
All math is deterministic — LLM is only used for category matching.
"""

import json
import os
from typing import Optional

MARKET_DATA_PATH = os.path.join(os.path.dirname(__file__), "market_data.json")


def _load_market_data() -> dict:
    with open(MARKET_DATA_PATH, "r") as f:
        return json.load(f)


def match_category(client_email: str, freelancer_constraints: str) -> Optional[str]:
    """
    Simple keyword-based category matcher.
    Scans both the client email and freelancer constraints for category keywords.
    Returns the best-matching category key, or None if no match.
    """
    data = _load_market_data()
    combined_text = (client_email + " " + freelancer_constraints).lower()

    best_category = None
    best_score = 0

    for cat_key, cat_data in data["categories"].items():
        score = 0
        for keyword in cat_data["keywords"]:
            if keyword.lower() in combined_text:
                score += 1
        if score > best_score:
            best_score = score
            best_category = cat_key

    return best_category


def get_market_rates(category: str) -> Optional[dict]:
    """Returns the hourly percentile bands for a given category."""
    data = _load_market_data()
    cat = data["categories"].get(category)
    if not cat:
        return None
    return {
        "label": cat["label"],
        "hourly": cat["hourly"],
        "day_rate": cat["day_rate"],
    }


def compute_leverage_factor(
    urgency_score: float,
    freelancer_pipeline: int,
    user_rate: float,
    market_median: float,
    market_p75: float,
) -> float:
    """
    Compute a context-aware leverage multiplier based on real signals.

    Returns a float between 0.0 and 0.50 (i.e., 0% to 50% premium).

    Components:
      - Urgency premium: Tight deadlines weaken the client's BATNA.
      - Scarcity premium: If the freelancer has a full pipeline, their
        walk-away is stronger.
      - Market position premium: If the freelancer's rate is already
        above-median, their positioning justifies a premium.

    All weights are deterministic and auditable.
    """
    # 1. Urgency component (0.0 – 0.15)
    #    urgency_score is 0.0 (relaxed) to 1.0 (extremely urgent)
    urgency_premium = min(urgency_score * 0.15, 0.15)

    # 2. Pipeline scarcity (0.0 – 0.15)
    #    More active jobs = stronger BATNA = higher premium
    pipeline_premium = min(freelancer_pipeline * 0.05, 0.15)

    # 3. Market position (0.0 – 0.20)
    #    How far above/below median is the freelancer's desired rate?
    if market_median > 0:
        position_ratio = user_rate / market_median
        if position_ratio >= 1.0:
            # Above median → justify premium toward p75
            market_premium = min((position_ratio - 1.0) * 0.40, 0.20)
        else:
            # Below median → no market premium, but no penalty either
            market_premium = 0.0
    else:
        market_premium = 0.0

    total = urgency_premium + pipeline_premium + market_premium
    return round(min(total, 0.50), 4)
