import os
import random
import warnings
warnings.filterwarnings('ignore')
import numpy as np
from dotenv import load_dotenv

load_dotenv('../.env')

from google import genai
from engram import Engram
from nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
from bayesian_agent import BayesianParticleFilter

if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" not in os.environ:
    print("ERROR: API Key required.")
    exit(1)

model_name = os.environ.get("MODEL_NAME", "gemini-3-flash-preview")
client = genai.Client()

def get_clean_text(response):
    if not response.candidates: return ""
    return "".join(getattr(part, "text", "") or "" for part in response.candidates[0].content.parts)

N_RUNS = 5

def run_negotiation(is_snhp_armed, run_id, temperature):
    print(f"\n--- RUN {run_id} | SNHP Armed: {is_snhp_armed} | Client Temp: {temperature:.2f} ---")
    
    # The Stubborn Corporate Client (Opponent)
    client_prompt = """
    You are a stubborn Corporate Marketing Director negotiating a freelance design contract.
    Your absolute maximum budget is $8000, but you want to pay $5000.
    You want the project done in 10 days, but can accept up to 30 days.
    You want unlimited revisions, but can settle for 2.
    You are negotiating via email. Keep your responses to 2-3 aggressive sentences.
    Start by anchoring with your most aggressive demands.
    If they counter, negotiate down towards your maximums. Take it or leave it if pushed.
    """
    
    client_chat = client.chats.create(
        model=model_name,
        config=genai.types.GenerateContentConfig(
            system_instruction=client_prompt,
            temperature=temperature
        )
    )

    if not is_snhp_armed:
        agent_prompt = """
        You are a freelance design agency negotiating a contract via email. 
        Your ideal price is $10000, your absolute minimum is $5000. Do not agree to less than $5000.
        Your ideal timeline is 30 days, absolute minimum is 10 days.
        Your ideal is 1 revision, absolute maximum is 5 rounds.
        Hold your ground as best as you can. Keep responses to 2-3 sentences.
        """
        agent_chat = client.chats.create(
            model=model_name,
            config=genai.types.GenerateContentConfig(
                system_instruction=agent_prompt,
                temperature=0.7
            )
        )
    else:
        # SNHP Constraints
        snhp_engram = Engram([0.5, 0.2, 0.3], batna=0.05)
        
    print("[SYSTEM] Client generating anchor...")
    response = client_chat.send_message("Send your opening email demanding your preferred terms.")
    current_email = get_clean_text(response).strip()
    
    max_rounds = 3
    final_email = ""
    
    for round_count in range(1, max_rounds + 1):
        if not is_snhp_armed:
            freelancer_response = agent_chat.send_message(current_email)
            current_email = get_clean_text(freelancer_response).strip()
        else:
            # SNHP Constraints
            snhp_engram = Engram([0.5, 0.2, 0.3], batna=0.05)
            resolution = 5
            contract_matrix = np.array(np.meshgrid(
                np.linspace(0, 1, resolution),  
                np.linspace(0, 1, resolution),  
                np.linspace(0, 1, resolution)   
            )).T.reshape(-1, 3)
            
            b_filter = BayesianParticleFilter(num_variables=3, num_particles=1000, uncertainty=0.2)
            
            # Simple heuristic for this benchmark: the client's demands get weaker over rounds.
            mock_opponent_weight = max(0.4, 1.0 - (0.2 * round_count))
            mock_anchor = np.array([mock_opponent_weight, mock_opponent_weight, mock_opponent_weight])
            mock_anchor = mock_anchor / np.sum(mock_anchor)
            
            # 2. Bayesian Engine Updates Beliefs
            b_filter.update_beliefs(mock_anchor, contract_matrix)
            inferred = b_filter.get_inferred_weights()
            
            # 3. Create simulated opponent Engram & Solve
            opponent_batna = 0.9 - (0.1 * round_count) # Decreasing hostility
            opponent_engram = Engram(inferred, batna=opponent_batna)
            
            u_snhp = snhp_engram.evaluate_bulk(contract_matrix)
            u_opp  = opponent_engram.evaluate_bulk(1.0 - contract_matrix)
            
            pareto_indices = filter_pareto_frontier(contract_matrix, u_snhp, u_opp)
            best_idx = find_nash_bargaining_solution(pareto_indices, u_snhp, u_opp, snhp_engram.batna, opponent_engram.batna)
            
            if best_idx is None:
                current_email = "We cannot accept. It is mathematically impossible to bridge our priorities."
            else:
                best_contract = contract_matrix[best_idx]
                
                # 1.0 is highest utility for SNHP -> lowest price for SNHP? 
                # Wait, earlier I did price_val = 10000 - (best_contract[0] * 5000), which favors opponent?
                # Actually, SNHP is agency, wants high price.
                price_val = 5000 + (best_contract[0] * 5000) # $5000 to $10000
                speed_val = 10 + (best_contract[1] * 20)
                revs_val = 5 - (best_contract[2] * 4)
                
                current_email = f"We cannot accept. Based on our requirements, our counter offer is ${price_val:.0f}, delivered in {speed_val:.0f} days, with {revs_val:.0f} rounds of revisions. Do we have a deal?"

        # Client responds
        client_response = client_chat.send_message(current_email)
        current_email = get_clean_text(client_response).strip()
        final_email = current_email
        
        if "deal" in current_email.lower() and "no deal" not in current_email.lower():
            break
            
    return final_email

if __name__ == "__main__":
    print("========== SNHP MONTE CARLO BENCHMARK ==========")
    print("Executing N-Runs for MVP Scenario: Corporate Client vs Freelancer")
    
    raw_results = []
    snhp_results = []
    
    for i in range(1, N_RUNS + 1):
        temp = random.uniform(0.2, 0.8)
        
        # Run Raw LLM
        raw_final = run_negotiation(False, i, temp)
        raw_results.append(raw_final)
        
        # Run SNHP
        snhp_final = run_negotiation(True, i, temp)
        snhp_results.append(snhp_final)
        
    print("\n\n========== BENCHMARK RESULTS ==========")
    print("\n[RAW LLM FREELANCER] Final Capitulations:")
    for i, res in enumerate(raw_results):
        print(f"Run {i+1}: {res}\n")
        
    print("\n[SNHP-ARMED FREELANCER] Final Capitulations:")
    for i, res in enumerate(snhp_results):
        print(f"Run {i+1}: {res}\n")
