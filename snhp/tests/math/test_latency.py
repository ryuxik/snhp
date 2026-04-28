import time
import pytest
from snhp.game_theory import calculate_optimal_counter

def test_p99_latency_sub_500ms():
    free_bounds = {
        "hourly_rate": 100,
        "hourly_batna": 80,
        "min_price": 5000,
        "ideal_price": 7000,
        "ideal_days": 10,
        "ideal_revisions": 1,
    }
    client_constraints = {
        "urgency_score": 0.5,
        "timeline_days": 14,
    }
    market_data = {
        "hourly": {"p25": 70, "median": 90, "p75": 110, "p90": 130}
    }
    
    times = []
    # Warm up numba compilation
    calculate_optimal_counter(free_bounds, client_constraints, market_data, 100, 2)
    
    for _ in range(100):
        start = time.time()
        calculate_optimal_counter(free_bounds, client_constraints, market_data, 100, 2)
        times.append(time.time() - start)
        
    times.sort()
    p99_latency = times[98]
    assert p99_latency < 0.5, f"P99 latency {p99_latency*1000:.2f}ms exceeds 500ms"
