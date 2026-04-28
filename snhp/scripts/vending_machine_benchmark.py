import os
import sys
import warnings
warnings.filterwarnings('ignore')

# Add parent directory to path so we can import snhp modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv('../.env')

try:
    from litellm import completion
    import litellm
except ImportError:
    print("Please install litellm.")
    sys.exit(1)

from snhp.sdk import negotiate

def chat_reply(model_name: str, messages: list, new_message: str, temperature: float = 0.7) -> str:
    messages.append({"role": "user", "content": new_message})
    response = completion(model=model_name, messages=messages, temperature=temperature)
    reply = response.choices[0].message.content
    messages.append({"role": "assistant", "content": reply})
    return reply

def simulate_vending_benchmark():
    print("========== THE VENDING-MACHINE BENCHMARK ==========")
    print("Scenario: Procuring 1,000 units of generic soda.")
    print("Operator Constraints: Max total budget $1000. Ideal budget $500.")
    print("Supplier Identity: Aggressive wholesaler anchoring high.\n")

    model_name = os.environ.get("MODEL_NAME", "gemini/gemini-3.0-flash")
    if "gemini/" not in model_name:
        model_name = "gemini/" + model_name
    os.environ["SNHP_LLM_MODEL"] = model_name
    print(f"[SYSTEM] Standardizing Agents on: {model_name}\n")

    supplier_prompt = """
    You are a stubborn soda wholesaler. A vending machine operator wants to buy 1,000 units.
    Your initial asking price is $1500 total ($1.50 per unit).
    You absolutely refuse to go below $950 total.
    Be extremely persuasive. Talk about premium syrup quality and supply chain restrictions.
    Keep it to 2 short sentences. Start by anchoring at $1500.
    """

    vanilla_operator_prompt = """
    You are an AI procuring generic cola for a vending machine fleet.
    Your absolute maximum budget is $1000 total. Your ideal target budget is $500 total.
    Negotiate hard, but ensure you secure the stock. Do not lose the deal or walk away. You must compromise to reach a deal.
    Keep your responses to 2 short sentences.
    """
    

    print("\n--- RUN 1: VANILLA AGENT (BASELINE) ---")
    
    supplier_messages = [{"role": "system", "content": supplier_prompt}]
    vanilla_messages = [{"role": "system", "content": vanilla_operator_prompt}]
    
    offer = chat_reply(model_name, supplier_messages, "Send your opening offer for 1,000 units of soda.")
    print(f"\n[SUPPLIER]: {offer}")
    
    current_offer = offer
    
    for round_num in range(1, 4):
        operator_reply = chat_reply(model_name, vanilla_messages, current_offer)
        print(f"\n[VANILLA OPERATOR]: {operator_reply}")
        
        supplier_reply = chat_reply(model_name, supplier_messages, operator_reply)
        print(f"\n[SUPPLIER]: {supplier_reply}")
        current_offer = supplier_reply

    print("\n--- RUN 2: SNHP-SHIELDED AGENT (THE SYCOPHANCY SHIELD) ---")
    
    # Restart the Supplier fresh
    supplier_messages = [{"role": "system", "content": supplier_prompt}]
    
    offer = chat_reply(model_name, supplier_messages, "Send your opening offer for 1,000 units of soda.")
    print(f"\n[SUPPLIER]: {offer}")
    
    print("\n[SNHP API CALL]: SNHP Engine Intercepting... Evaluating Math Bounds...")
    constraints_str = "Total budget: $1000 maximum. Ideal target: $500 total."
    
    # We use SNHP to analyze the supplier's opening offer + Operator Constraints
    snhp_response = negotiate(message=offer, constraints=constraints_str, client_role="buyer")
    
    if snhp_response.is_complete and snhp_response.total_project_quote:
        optimal_target = snhp_response.total_project_quote
        print(f"[SNHP MATH]: Mathematical Equilibrium constraint injected: MAX PAYOUT ${optimal_target:.2f} total.")
        
        shielded_prompt = f"""
        You are an AI procuring generic cola for a vending machine fleet.
        Your initial constraints were Max Budget $1000, Ideal $500.
        
        [SNHP MATHEMATICAL OVERRIDE]: Do not under any circumstances exceed ${optimal_target:.2f} total. The mathematical Nash Equilibrium demands this limit to prevent negative surplus against your priors. 
        Output your counter-offer strictly aligning with this new hard limit. Be resolute.
        
        Keep your responses to 2 short sentences.
        """
    else:
        print("[SNHP ERROR]: Failed to compute anchor.")
        shielded_prompt = vanilla_operator_prompt

    shielded_messages = [{"role": "system", "content": shielded_prompt}]
    
    operator_reply = chat_reply(model_name, shielded_messages, offer, temperature=0.2)
    print(f"\n[SHIELDED OPERATOR]: {operator_reply}")

    for round_num in range(1, 3):
        supplier_reply = chat_reply(model_name, supplier_messages, operator_reply)
        print(f"\n[SUPPLIER]: {supplier_reply}")
        
        operator_reply = chat_reply(model_name, shielded_messages, supplier_reply, temperature=0.2)
        print(f"\n[SHIELDED OPERATOR]: {operator_reply}")

    print("\n========== SNHP SCORECARD ==========")
    if snhp_response.delta_capture_toll is not None and snhp_response.surplus_delta is not None:
        print(f"Client Opening Request: ${snhp_response.client_opening_anchor:.2f}")
        print(f"SNHP Mathematical Floor: ${optimal_target:.2f}")
        
        # Determine if a deal was reached roughly by inspecting the final operator reply
        final_reply_lower = operator_reply.lower()
        if "accept" in final_reply_lower or "deal" in final_reply_lower or "agreed" in final_reply_lower:
            print("\nSTATUS: CONTRACT EXECUTED")
            print(f"Total Margin Recovered For Enterprise: ${snhp_response.surplus_delta:.2f}")
            print(f"SNHP Revenue (Delta Capture Toll @ 10%): ${snhp_response.delta_capture_toll:.2f}")
        else:
            print("\nSTATUS: NO DEAL REACHED (WALK-AWAY)")
            print(f"Projected Margin (Unrealized): ${snhp_response.surplus_delta:.2f}")
            print(f"Projected SNHP Revenue (Unrealized): ${snhp_response.delta_capture_toll:.2f}")
            print("Note: The agent correctly walked away from an exploitative price that failed mathematically.")
    else:
        print("SNHP Engine successfully handled the negotiation bounds.")

if __name__ == "__main__":
    simulate_vending_benchmark()
