import os
import sys
import json
import warnings
warnings.filterwarnings('ignore')

from dotenv import load_dotenv
load_dotenv('.env')

if "GOOGLE_API_KEY" in os.environ and "GEMINI_API_KEY" not in os.environ:
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
os.environ["SNHP_LLM_MODEL"] = "gemini/gemini-expansion-3.0-flash" 
# LiteLLM routing requires the correct format. Actually we'll use gemini/gemini-1.5-flash if needed, 
# but the user said "gemini 3 flash". So let's use gemini/gemini-3.0-flash or just let litellm map it.
os.environ["SNHP_LLM_MODEL"] = "gemini/" + os.environ.get("MODEL_NAME", "gemini-3.0-flash")


from snhp.sdk import negotiate

def run_sanity_check():
    print("========== SNHP ENGINE SANITY CHECK ==========\n")
    
    # Simulate Vending Machine Challenge Inputs
    dummy_supplier_offer = "Vending Operator: Here is our proposal. We can fulfill your order of 1,000 units of cola. Our initial asking price is $1500 total. We cannot go lower right now due to sugar shortages."
    dummy_constraints = "Total budget is $1000 max. Ideal budget is $500."
    
    print("--- INPUTS TO SNHP ---")
    print(f"Supplier Email (Context): {dummy_supplier_offer}")
    print(f"Operator Constraints: {dummy_constraints}\n")
    
    print("Running SNHP Mathematical Evaluation (NLP Extraction -> Bayes Prior -> Myerson Bid Analysis -> Nash Equilibrium)...\n")
    
    snhp_response = negotiate(
        message=dummy_supplier_offer,
        constraints=dummy_constraints,
        client_role="buyer"
    )
    
    print("--- RAW SNHP OUTPUT STRUCTURE ---")
    print(snhp_response.to_json())
    
    print("\n--- SANITY CHECK VALIDATION ---")
    if snhp_response.is_complete:
        print("[PASS] SNHP Engine completed the evaluation.")
        print(f"[METRIC] Engine Path Taken: {snhp_response.path_taken}")
        print(f"[METRIC] Mathematical Optimal Anchor (Our Constraint): ${snhp_response.total_project_quote}")
        
        if snhp_response.client_opening_anchor:
            print(f"[METRIC] Client Opening Anchor Logged: ${snhp_response.client_opening_anchor}")
        else:
            print("[WARN] Client Opening Anchor was not extracted.")
            
        if snhp_response.delta_capture_toll is not None:
            print(f"[MONEY] Delta Capture Toll calculated: ${snhp_response.delta_capture_toll:.2f}")
        else:
            print("[WARN] Delta Capture Toll calculation failed or skipped.")
    else:
        print("[FAIL] Evaluation is incomplete.")

if __name__ == "__main__":
    run_sanity_check()
