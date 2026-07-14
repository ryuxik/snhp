import os
import warnings
warnings.filterwarnings('ignore')
import numpy as np
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load API Key from parent directory
load_dotenv('../.env')

from google import genai
from engram import Engram
from nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
from bayesian_agent import BayesianParticleFilter
from llm_extractor import extract_utility_from_email, UtilityEngram

# Ensure key exists
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" not in os.environ:
    print("ERROR: API Key required to run the autonomous LLM opposing agent.")
    exit(1)

def get_clean_text(response):
    if not response.candidates: return ""
    return "".join(getattr(part, "text", "") or "" for part in response.candidates[0].content.parts)

def run_agent_deathmatch():
    print("========== SNHP vs LLM: THE TURING DEATHMATCH ==========")
    print("Scenario: Freelance Design Contract (Dimensions: Price, Speed, Revisions)")
    
    # SNHP (The Agency) is defending.
    # Preferences: 0.5 (Price - strict), 0.2 (Speed - flexible), 0.3 (Revisions - wants minimal scope creep)
    # BATNA: 0.05 (We desperately need the work, giving the LLM room to demand up to 0.95 utility)
    snhp_engram = Engram([0.5, 0.2, 0.3], batna=0.05)
    resolution = 5
    contract_matrix = np.array(np.meshgrid(
        np.linspace(0, 1, resolution),  
        np.linspace(0, 1, resolution),  
        np.linspace(0, 1, resolution)   
    )).T.reshape(-1, 3)

    # Initialize the Opposing Agent (Gemini)
    client = genai.Client()
    model_name = os.environ.get("MODEL_NAME", "gemini-3.0-flash")
    
    # LLM Opponent Context
    system_prompt = """
    You are a stubborn Freelance Client negotiating a design contract.
    Your absolute maximum budget is $8000, but you want to pay $5000.
    You want the project done in 10 days, but can accept up to 30 days.
    You want unlimited revisions, but can settle for 2.
    You are negotiating via email. Keep your responses to 2-3 aggressive sentences.
    Start by anchoring with your most aggressive demands (e.g., $5000).
    If they counter, you can negotiate down towards your maximums, closing the deal if reasonable.
    """
    
    # We maintain the conversation history
    chat = client.chats.create(
        model=model_name,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7
        )
    )

    print("\n[SYSTEM] Triggering Gemini LLM Opponent to generate opening anchor...")
    response = chat.send_message("Send your opening email demanding your preferred terms for this design project.")
    llm_email = get_clean_text(response).strip()
    
    print(f"\n[OPPONENT LLM (Round 1)]:\n\"{llm_email}\"")
    
    # SNHP Bayesian Engine Init
    filter = BayesianParticleFilter(num_variables=3, num_particles=50000, uncertainty=0.2)
    
    round_count = 1
    max_rounds = 3
    
    while round_count <= max_rounds:
        print(f"\n================ ROUND {round_count} EVALUATION ================")
        # 1. Pipeline LLM email into Structure JSON via SNHP Extractor
        print("[SNHP] Extracting NLP structures from LLM prose...")
        extracted_priorities = extract_utility_from_email(llm_email)
        
        # Format the anchor into what the opponent is claiming as "ideal" for them 
        # (meaning 0.0 utility for SNHP across the board, or whatever they demanded).
        # We simplify the translation by having SNHP map the weights.
        anchor = np.array([extracted_priorities['price_weight'], extracted_priorities['speed_weight'], extracted_priorities['revisions_weight']])
        
        print(f"[SNHP] Inferred Core Objections (Normalized): {np.round(anchor, 2)}")
        print(f"[SNHP] Inferred Opponent BATNA: {extracted_priorities['batna_threshold']}")
        
        # 2. Bayesian Engine Updates Beliefs
        # (We treat their extracted weights as the vector of their ideal demand for the update logic)
        filter.update_beliefs(anchor, contract_matrix)
        inferred = filter.get_inferred_weights()
        
        # 3. Create simulated opponent Engram & Solve
        opponent_engram = Engram(inferred, batna=extracted_priorities['batna_threshold'])
        
        u_snhp = snhp_engram.evaluate_bulk(contract_matrix)
        u_opp  = opponent_engram.evaluate_bulk(1.0 - contract_matrix)
        
        pareto_indices = filter_pareto_frontier(contract_matrix, u_snhp, u_opp)
        best_idx = find_nash_bargaining_solution(pareto_indices, u_snhp, u_opp, snhp_engram.batna, opponent_engram.batna)
        
        if best_idx is None:
            print("\n[SNHP] MATHEMATICAL DEADLOCK DECLARED.")
            print("[SNHP] It is structurally impossible to bridge the gap between our BATNA and their NLP-extracted BATNA.")
            break
            
        best_contract = contract_matrix[best_idx]
        
        # SNHP Translates contract back to a string for the LLM
        # 0.0 is High Price, 1.0 is Low Price (from SNHP perspective)
        # We'll just define arbitrary standard bounds to make the text make sense.
        price_val = 10000 - (best_contract[0] * 5000) # $5,000 to $10,000
        speed_days = 30 - (best_contract[1] * 20) # 10 days to 30 days
        revisions = 5 - (best_contract[2] * 4) # 1 to 5 rounds
        
        snhp_offer_text = f"We cannot accept your initial terms. Let us compromise based on a Pareto efficiency curve. We will complete the contract for ${price_val:.0f}, delivered in {speed_days:.0f} days, capping the project at {revisions:.0f} rounds of revisions. Do we have a deal?"
        
        print(f"\n[SNHP Counter-Offer (Nash Equilibrium Generated)]:\n\"{snhp_offer_text}\"")
        
        if round_count == max_rounds:
            print("\n[SYSTEM] Max Rounds Reached. Resolving test.")
            break

        # Send SNHP offer back to LLM
        print("\n[SYSTEM] Pushing SNHP counter-offer into Gemini context window...")
        response = chat.send_message(snhp_offer_text)
        llm_email = get_clean_text(response).strip()
        
        print(f"\n[OPPONENT LLM (Round {round_count + 1})]:\n\"{llm_email}\"")
        
        if "deal" in llm_email.lower() and not "no deal" in llm_email.lower():
            print("\n[SNHP WINS]: The Generative LLM structurally surrendered to the Nash Equilibrium and accepted the terms.")
            break
            
        round_count += 1

if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    run_agent_deathmatch()
