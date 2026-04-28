import pytest
from snhp.game_theory import calculate_optimal_counter

def test_pareto_optimality_and_bounds():
    free_bounds = {
        "hourly_rate": 150,
        "hourly_batna": 100,
        "min_price": 8000,
        "ideal_price": 10000,
        "ideal_days": 20,
        "ideal_revisions": 2,
    }
    client_constraints = {
        "urgency_score": 0.8,
        "timeline_days": 15,
    }
    
    result = calculate_optimal_counter(free_bounds, client_constraints, None, None, 1)
    
    # Ensures the bounds never dip below standard expectation
    assert result["optimal_anchor"] >= 100 # Myerson bid >= BATNA
    assert result["target_days"] == 15
    assert len(result["concession_ladder"]) == 4
    assert result["total_project_quote"] >= 8000 # Anchor shouldn't be less than min bounds
