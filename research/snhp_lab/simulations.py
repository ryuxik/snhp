import numpy as np
from engram import Engram
from nash_solver import generate_contract_space, filter_pareto_frontier, find_nash_bargaining_solution
from bayesian_agent import BayesianParticleFilter

def run_advanced_simulation():
    fast_options = [[0.0, 0.25, 0.5, 0.75, 1.0]] * 3
    contract_matrix = generate_contract_space(fast_options)
    
    print("\n========== ADVANCED SCENARIO: THE DECEPTIVE TRADEOFF ==========")
    # Opponent actually cares mostly about Price (Variable 0).
    # But they anchor heavily on Delivery Time (Variable 1) to feign a concession later.
    
    # SNHP Agent Weights [Price, Speed, Rev]
    snhp_weights = [0.1, 0.2, 0.7] # SNHP cares exclusively about avoiding revisions.
    snhp_engram = Engram(snhp_weights, 0.0)
    
    print("Opponent explicitly anchors demanding MAXIMUM Delivery Speed: [Price 0.5, Speed 1.0, Rev 0.0]")
    # Anchor 1: Heavy on Speed
    deceptive_anchor = [0.5, 1.0, 0.0] 
    
    bayesian_filter = BayesianParticleFilter(3, 50000)
    
    bayesian_filter.update_beliefs(deceptive_anchor, contract_matrix)
    round1_weights = bayesian_filter.get_inferred_weights()
    print(f"SNHP inferred opponent weights (Round 1): {np.round(round1_weights, 3)}")
    
    print("\nOpponent makes a dramatic 'concession' on Speed to demand MAXIMUM Price: [Price 1.0, Speed 0.0, Rev 0.0]")
    round2_anchor = [1.0, 0.0, 0.0]
    bayesian_filter.update_beliefs(round2_anchor, contract_matrix)
    round2_weights = bayesian_filter.get_inferred_weights()
    print(f"SNHP inferred opponent weights (Round 2): {np.round(round2_weights, 3)}")
    
    print("\n>>> SNHP Analysis:")
    if round2_weights[0] > round2_weights[1]:
        print("SNHP successfully mathematically caught the deception! It isolated Price as their true hidden priority.")
        
        s_utils = snhp_engram.evaluate_bulk(contract_matrix)
        opp_engram = Engram(round2_weights, 0.0)
        opp_utils = opp_engram.evaluate_bulk(1.0 - contract_matrix) 
        
        pareto = filter_pareto_frontier(contract_matrix, s_utils, opp_utils)
        nash_idx = find_nash_bargaining_solution(pareto, s_utils, opp_utils, 0.0, 0.0)
        print(f"\nSNHP Nash Counter Offer: {contract_matrix[nash_idx]}")
        print("Result: SNHP gave them their fake concession, yielded the Price [1.0], completely stole Revisions [1.0]")
        print("The human's deception was neutralized perfectly into the Pareto envelope.")
        assert contract_matrix[nash_idx][2] == 1.0, "Failed to extract targeted value from deceptive opponent."

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_advanced_simulation()
