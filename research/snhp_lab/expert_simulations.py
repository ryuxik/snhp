import numpy as np
from engram import Engram
from nash_solver import generate_contract_space, filter_pareto_frontier, find_nash_bargaining_solution
from bayesian_agent import BayesianParticleFilter

def run_boulware_simulation():
    print("\n========== EXPERT SIM: THE BOULWARE ULTIMATUM ==========")
    # Buyer's BATNA drops dead at 0.5 utility. 
    b_engram = Engram([0.5, 0.3, 0.2], batna=0.5)
    
    # Opponent's Boulware ultimatum: highly favorable to them, almost ruinous for us, but yielding 0.52 marginal utility.
    boulware_ultimatum = np.array([0.8, 0.4, 0.0])
    
    print(f"Opponent Ultimatum: {boulware_ultimatum}")
    
    utility = b_engram.evaluate(boulware_ultimatum)
    print(f"SNHP Mathematical Evaluation: Utility = {utility:.3f} | BATNA = {b_engram.batna}")
    
    if utility >= b_engram.batna:
        print("SNHP Decision: RATIONAL ACCEPTANCE.")
        print("Analysis: The human ego would reject this insult, but SNHP determines it holds +0.02 marginal positive value. Deal Accepted.")
    else:
        print("SNHP Decision: REJECT. Drops beneath BATNA.")
        
    assert utility >= b_engram.batna, "Test logic error, utility should be theoretically acceptable."

def run_nibbler_simulation():
    print("\n========== EXPERT SIM: THE NIBBLER ==========")
    fast_options = [[0.0, 0.25, 0.5, 0.75, 1.0]] * 3
    contract_matrix = generate_contract_space(fast_options)
    
    b_engram = Engram([0.4, 0.4, 0.2], batna=0.2)
    b_utils = b_engram.evaluate_bulk(contract_matrix)
    s_engram = Engram([0.3, 0.3, 0.4], batna=0.2)
    s_utils = s_engram.evaluate_bulk(1.0 - contract_matrix)
    
    pareto_indices = filter_pareto_frontier(contract_matrix, b_utils, s_utils)
    nash_idx = find_nash_bargaining_solution(pareto_indices, b_utils, s_utils, 0.2, 0.2)
    
    nash_contract = contract_matrix[nash_idx]
    print(f"Original Nash Deal: {nash_contract}")
    
    nash_buyer_util = b_engram.evaluate(nash_contract)
    nash_seller_util = s_engram.evaluate(1.0 - nash_contract)
    nash_product = (nash_buyer_util - 0.2) * (nash_seller_util - 0.2)
    
    # Nibble: Opponent demands Price goes from current contract down 0.25 (favoring Seller).
    nibble_contract = np.copy(nash_contract)
    nibble_contract[0] = max(0.0, nash_contract[0] - 0.25)
    
    print(f"Opponent's Last Minute 'Nibble': {nibble_contract}")
    
    nibble_buyer_util = b_engram.evaluate(nibble_contract)
    nibble_seller_util = s_engram.evaluate(1.0 - nibble_contract)
    nibble_product = (nibble_buyer_util - 0.2) * (nibble_seller_util - 0.2)
    
    print(f"Nash Product vs Nibble Product: {nash_product:.3f} vs {nibble_product:.3f}")
    if nibble_product < nash_product:
        print("SNHP Decision: NIBBLE REJECTED.")
        print("Analysis: SNHP detects the Nibble fractures the mathematical Pareto efficiency frontier.")
    else:
        print("SNHP Decision: NIBBLE ACCEPTED.")
        
    assert nibble_product < nash_product, "The Nibble shouldn't mathematically beat a true Nash equilibrium!"

def run_goodcop_badcop_simulation():
    print("\n========== EXPERT SIM: OSCILLATING GOOD COP / BAD COP ==========")
    contract_matrix = generate_contract_space([[0.0, 0.25, 0.5, 0.75, 1.0]]*3)
    filter_agent = BayesianParticleFilter(3, 50000)
    
    # Bad Cop Anchor 
    bad_cop_anchor = np.array([0.0, 1.0, 0.0])
    
    # Good Cop Anchor (Massive 25% "concession" across two variables)
    good_cop_anchor = np.array([0.25, 0.75, 0.0])
    
    print(f"Round 1 (Bad Cop): 'We refuse to accept anything less than {bad_cop_anchor}'")
    filter_agent.update_beliefs(bad_cop_anchor, contract_matrix)
    r1_weights = filter_agent.get_inferred_weights()
    print(f"   SNHP Inference R1: {np.round(r1_weights, 3)}")
    
    print(f"\nRound 2 (Good Cop): 'Okay let's be reasonable. We will concede massively. How about {good_cop_anchor}'")
    filter_agent.update_beliefs(good_cop_anchor, contract_matrix)
    r2_weights = filter_agent.get_inferred_weights()
    print(f"   SNHP Inference R2: {np.round(r2_weights, 3)}")
    
    print("\nAnalysis: SNHP experiences zero emotional 'relief'. It processes the Good Cop concession simply as a continuous likelihood update. It correctly infers the opponent's core priority remains squarely locked on Variable 2 (Speed).")

    assert np.argmax(r2_weights) == 1, "Agent was emotionally swayed away from the true priority base!"


if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_boulware_simulation()
    run_nibbler_simulation()
    run_goodcop_badcop_simulation()
