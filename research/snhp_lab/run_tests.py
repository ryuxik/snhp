import numpy as np
import time
from engram import Engram
from nash_solver import generate_contract_space, filter_pareto_frontier, find_nash_bargaining_solution
from bayesian_agent import BayesianParticleFilter

def run_nash_solver_tests():
    print("--- Running Component 1 & 2: Nash Solver Tests ---")
    start = time.time()
    
    # 3 Variables. Values representing scaled benefit [0.0 to 1.0] for the BUYER.
    options = [[0.0, 0.5, 1.0], [0.0, 0.5, 1.0], [0.0, 0.5, 1.0]]
    contract_matrix = generate_contract_space(options)
    
    # Test 1: Symmetric Weights
    buyer_engram = Engram(raw_weights=[1, 1, 1], batna=0.0)
    buyer_utils = buyer_engram.evaluate_bulk(contract_matrix)
    
    seller_engram = Engram(raw_weights=[1, 1, 1], batna=0.0)
    # Seller's utility is inverted from the features
    seller_utils = seller_engram.evaluate_bulk(1.0 - contract_matrix)
    
    pareto_indices = filter_pareto_frontier(contract_matrix, buyer_utils, seller_utils)
    nash_idx = find_nash_bargaining_solution(pareto_indices, buyer_utils, seller_utils, 0.01, 0.01)
    
    nash_contract = contract_matrix[nash_idx]
    print(f"Symmetric Nash Contract Output: {nash_contract}")
    # Due to linear utility without convexity, any contract whose features sum to 1.5 
    # yields the exact same maximum Nash product (1.5 * 1.5 = 2.25). 
    assert np.allclose(np.sum(nash_contract), 1.5), "Failed symmetric test! Did not pick a Pareto optimal median sum."
    
    # Test 2: Extreme Asymmetric Weights
    buyer_engram_asym = Engram(raw_weights=[1, 0, 0], batna=0.0)
    b_asym_utils = buyer_engram_asym.evaluate_bulk(contract_matrix)
    
    seller_engram_asym = Engram(raw_weights=[0, 0, 1], batna=0.0)
    s_asym_utils = seller_engram_asym.evaluate_bulk(1.0 - contract_matrix)
    
    pareto_indices_asym = filter_pareto_frontier(contract_matrix, b_asym_utils, s_asym_utils)
    nash_idx_asym = find_nash_bargaining_solution(pareto_indices_asym, b_asym_utils, s_asym_utils, 0.01, 0.01)
    
    nash_contract_asym = contract_matrix[nash_idx_asym]
    print(f"Asymmetric Nash Contract Output: {nash_contract_asym}")
    
    # The buyer wants feature 0 maximized. The seller wants feature 2 minimized.
    assert nash_contract_asym[0] == 1.0, "Buyer's asymmetric priority failed."
    assert nash_contract_asym[2] == 0.0, "Seller's asymmetric priority failed."

    print(f"Nash Solver mathematical assertions passed in {time.time() - start:.4f}s!\n")

def run_bayesian_agent_tests():
    print("--- Running Component 3: Bayesian Agent Tests ---")
    start = time.time()
    
    options = [[0.0, 0.5, 1.0], [0.0, 0.5, 1.0], [0.0, 0.5, 1.0]]
    contract_matrix = generate_contract_space(options)
    
    agent = BayesianParticleFilter(num_variables=3, num_particles=50000)
    
    # Simulate the opponent anchoring aggressively on Variable 2 (Index 1)
    # The opponent proposes a contract that scores [0.0, 1.0, 0.0] on THEIR utility scale.
    anchor = np.array([0.0, 1.0, 0.0]) 
    
    agent.update_beliefs(anchor, contract_matrix)
    inferred_weights = agent.get_inferred_weights()
    
    print(f"Inferred Opponent Weight Distribution: {inferred_weights}")
    
    assert inferred_weights[1] > inferred_weights[0], "Bayesian culling failed to upweigh Variable 2."
    assert inferred_weights[1] > inferred_weights[2], "Bayesian culling failed to upweigh Variable 2."
    
    print(f"Bayesian Particle Filter tests passed in {time.time() - start:.4f}s!")

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_nash_solver_tests()
    run_bayesian_agent_tests()
