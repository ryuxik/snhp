import numpy as np
from engram import Engram
from nash_solver import generate_contract_space, filter_pareto_frontier, find_nash_bargaining_solution

def run_walkaway_simulation():
    print("\n========== FRICTION SCENARIO: THE WALK-AWAY ==========")
    fast_options = [[0.0, 0.25, 0.5, 0.75, 1.0]] * 3
    contract_matrix = generate_contract_space(fast_options)
    
    # Both parties have MASSIVE BATNA requirements due to external leverage.
    b_engram = Engram([0.3, 0.3, 0.4], batna=0.8)  # Requires 80% theoretical maximum utility.
    b_utils = b_engram.evaluate_bulk(contract_matrix)
    
    s_engram = Engram([0.4, 0.3, 0.3], batna=0.8)
    s_utils = s_engram.evaluate_bulk(1.0 - contract_matrix)
    
    pareto_indices = filter_pareto_frontier(contract_matrix, b_utils, s_utils)
    nash_idx = find_nash_bargaining_solution(pareto_indices, b_utils, s_utils, 0.8, 0.8)
    
    if nash_idx is None:
        print(">>> SNHP Analysis: MATHEMATICAL DEADLOCK DETECTED.")
        print("    No contract exists in the discrete state space that satisfies both BATNAs.")
        print("    Action: Terminate Negotiation. Implement Brutally Honest Walk-Away Protocol.")
    else:
        print(f"Nash found: {contract_matrix[nash_idx]}")
        
    assert nash_idx is None, "Engine hallucinated a compromise where none was possible!"

def run_serial_multi_round_simulation():
    print("\n========== FRICTION SCENARIO: GRINDING SERIAL MULTI-ROUND ==========")
    print("Round 1: Full 3D Contract Space Active.")
    print("Opponent: 'We refuse to discuss Price until you lock in the fastest Delivery Time (1.0).'")
    
    # We concede on timeline to keep the deal alive. 
    # The mathematical dimension physically collapses.
    print("--> SNHP Action: Conceding Timeline dimension. Collapsing multi-verse grid...")
    collapsed_options = [[0.0, 0.25, 0.5, 0.75, 1.0], [1.0], [0.0, 0.25, 0.5, 0.75, 1.0]]
    contract_matrix = generate_contract_space(collapsed_options)
    
    print(f"Round 2: Contract permutations reduced. New state space bounded to {len(contract_matrix)} discrete options.")
    
    b_engram = Engram([0.6, 0.1, 0.3], batna=0.0)
    b_utils = b_engram.evaluate_bulk(contract_matrix)
    
    s_engram = Engram([0.2, 0.7, 0.1], batna=0.0)
    s_utils = s_engram.evaluate_bulk(1.0 - contract_matrix)
    
    pareto_indices = filter_pareto_frontier(contract_matrix, b_utils, s_utils)
    nash_idx = find_nash_bargaining_solution(pareto_indices, b_utils, s_utils, 0.0, 0.0)
    
    print("\n>>> SNHP Analysis: Recalculating Nash within physically restricted sub-space.")
    print(f"New Pareto-Optimal Nash Contract: [Price: {contract_matrix[nash_idx][0]}, Speed: {contract_matrix[nash_idx][1]}, Revs: {contract_matrix[nash_idx][2]}]")
    print("Result: Since we lost Timeline (1.0), SNHP organically balanced the remaining variables (Price and Revisions).")
    print("It did not 'punish' the opponent by taking 100% of Price, because driving the opponent's utility to zero kills the Nash Product.")
    
    assert contract_matrix[nash_idx][1] == 1.0, "Timeline constraint violated!"
    assert contract_matrix[nash_idx][0] > 0.0, "SNHP completely abandoned the deal structure unnecessarily."

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_walkaway_simulation()
    run_serial_multi_round_simulation()
