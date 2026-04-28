import numpy as np
from engram import Engram
from nash_solver import generate_contract_space
from bayesian_agent import BayesianParticleFilter

def run_priors_simulation():
    print("\n========== BAYESIAN PRIORS A/B TEST: COLD START vs WARM START ==========")
    fast_options = [[0.0, 0.25, 0.5, 0.75, 1.0]] * 3
    contract_matrix = generate_contract_space(fast_options)
    
    # The opponent's TRUE hidden weighting: [Price: 0.7, Speed: 0.1, Rev: 0.2]
    # The opponent maliciously anchors demanding MAXIMUM speed: [0.5, 1.0, 0.0]
    deceptive_anchor = [0.5, 1.0, 0.0]
    
    print("Opponent explicitly anchors demanding MAXIMUM Delivery Speed: [0.5, 1.0, 0.0]")
    
    # ------------------
    # TEST A: COLD START
    # ------------------
    cold_filter = BayesianParticleFilter(3, 50000)
    cold_filter.update_beliefs(deceptive_anchor, contract_matrix)
    cold_weights = cold_filter.get_inferred_weights()
    print(f"\n[Test A] Cold Start Inferred Weights (Round 1): {np.round(cold_weights, 3)}")
    
    # ------------------
    # TEST B: WARM START (Informative Prior)
    # ------------------
    # Our DB shows this opponent historically mostly cares about Price (0.6).
    fuzzy_historical_prior = [0.6, 0.2, 0.2]
    print(f"\nSeeding Warm Start Bayesian Agent with fuzzy memory: {fuzzy_historical_prior}")
    
    warm_filter = BayesianParticleFilter(3, 50000, historical_prior=fuzzy_historical_prior, uncertainty=0.15)
    warm_filter.update_beliefs(deceptive_anchor, contract_matrix)
    warm_weights = warm_filter.get_inferred_weights()
    print(f"[Test B] Warm Start Inferred Weights (Round 1): {np.round(warm_weights, 3)}")
    
    # ------------------
    # TEST C: INACCURATE WARM START (Bad CRM Data)
    # ------------------
    # Our CRM data is completely wrong. It thinks they care mostly about Revisions (0.6).
    bad_historical_prior = [0.2, 0.2, 0.6]
    print(f"\nSeeding Inaccurate Warm Start (Bad Memory): {bad_historical_prior}")
    
    # Since we know the CRM might be old, we pass a higher uncertainty (0.3)
    noisy_filter = BayesianParticleFilter(3, 50000, historical_prior=bad_historical_prior, uncertainty=0.3)
    noisy_filter.update_beliefs(deceptive_anchor, contract_matrix)
    noisy_weights = noisy_filter.get_inferred_weights()
    print(f"[Test C] Noisy Start Inferred Weights (Round 1): {np.round(noisy_weights, 3)}")
    
    print("\n>>> SNHP Prior Analysis:")
    # Check if the cold start was tricked by the anchor (believing Speed > Price)
    if cold_weights[1] > cold_weights[0] and warm_weights[0] > warm_weights[1]:
        print("Success: The Cold Start agent was massively tricked by the anchor (believed Speed was priority).")
        print("Success: The Warm Start (Fuzzy Prior) agent completely ignored the anchor deception on Round 1 and held mathematically true to the historical Price priority.")
        
    assert warm_weights[0] > warm_weights[1], "Warm start failed to shield against anchor!"

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_priors_simulation()
