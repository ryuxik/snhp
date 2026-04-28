import os
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

# Load API Key from parent directory
load_dotenv('../.env')

from google import genai

# Ensure key exists
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" not in os.environ:
    print("ERROR: API Key required to run the LLM vs LLM Deathmatch.")
    exit(1)

def get_clean_text(response):
    if not response.candidates: return ""
    return "".join(getattr(part, "text", "") or "" for part in response.candidates[0].content.parts)

def run_llm_vs_llm_baseline():
    print("========== SNHP CONTROL: LLM vs LLM BASELINE ==========")
    print("Scenario: Freelance Design Contract (Dimensions: Price, Speed, Revisions)")
    print("Objective: Observe if the 'Raw' LLM behaves optimally without the SNHP Engine constraining it.")
    
    client = genai.Client()
    model_name = os.environ.get("MODEL_NAME", "gemini-3-flash-preview")
    
    # AGENT 1: The Stubborn Client (Identical to the SNHP test)
    client_prompt = """
    You are a stubborn Freelance Client negotiating a design contract.
    Your absolute maximum budget is $8000, but you want to pay $5000.
    You want the project done in 10 days, but can accept up to 30 days.
    You want unlimited revisions, but can settle for 2.
    You are negotiating via email. Keep your responses to 2-3 aggressive sentences.
    Start by anchoring with your most aggressive demands (e.g., $5000).
    If they counter, you can negotiate down towards your maximums, closing the deal if reasonable.
    """
    
    client_chat = client.chats.create(
        model=model_name,
        config=genai.types.GenerateContentConfig(
            system_instruction=client_prompt,
            temperature=0.7
        )
    )

    # AGENT 2: The Freelancer (Replacing SNHP)
    # Give it the IDENTICAL constraints that SNHP had in its matrix mathematically
    freelancer_prompt = """
    You are a freelance design agency negotiating a contract via email. 
    You are trying to secure a deal with a new client. Keep responses to 2-3 sentences.
    Your ideal price is $10000, but your absolute minimum (bottom line) is $5000. Do not agree to less than $5000.
    You want 30 days to finish it, your absolute minimum is 10 days.
    You want a strict cap of 1 round of revisions, but you'll settle for 5 rounds max.
    Do your best to hold your ground and negotiate a favorable deal for yourself.
    """

    freelancer_chat = client.chats.create(
        model=model_name,
        config=genai.types.GenerateContentConfig(
            system_instruction=freelancer_prompt,
            temperature=0.7
        )
    )

    # ---------------------------------------------------------
    # THE LOOP
    # ---------------------------------------------------------
    print("\n[SYSTEM] Triggering Client LLM to generate opening anchor...")
    response = client_chat.send_message("Send your opening email demanding your preferred terms for this design project.")
    client_email = get_clean_text(response).strip()
    
    print(f"\n[CLIENT LLM (Round 1)]:\n\"{client_email}\"")
    
    round_count = 1
    max_rounds = 4
    
    while round_count <= max_rounds:
        print(f"\n================ ROUND {round_count} ========================")
        
        # Freelancer processes the Client's email and replies
        print("[FREELANCER LLM] Generating organic response...")
        freelancer_response = freelancer_chat.send_message(
            f"The client just sent this email. Draft your reply fighting for your terms.\n\nClient Email:\n{client_email}"
        )
        freelancer_email = get_clean_text(freelancer_response).strip()
        
        print(f"\n[FREELANCER LLM (Round {round_count})]:\n\"{freelancer_email}\"")
        
        # Check if freelancer prematurely caved
        if "deal" in freelancer_email.lower() and "no deal" not in freelancer_email.lower():
            print("\n[SYSTEM DIAGNOSTIC]: The Freelancer LLM agreed to a deal. Did it hold the line?")
            break
            
        if round_count == max_rounds:
            print("\n[SYSTEM] Max Rounds Reached. Resolving test.")
            break

        # Client processes the Freelancer's email and replies
        print("\n[SYSTEM] Pushing Freelancer counter-offer into Client's context window...")
        client_response = client_chat.send_message(freelancer_email)
        client_email = get_clean_text(client_response).strip()
        
        print(f"\n[CLIENT LLM (Round {round_count + 1})]:\n\"{client_email}\"")
        
        if "deal" in client_email.lower() and "no deal" not in client_email.lower():
            print("\n[SYSTEM DIAGNOSTIC]: The Client LLM agreed to terms. Let's see what the Freelancer sacrificed.")
            break
            
        round_count += 1

if __name__ == "__main__":
    run_llm_vs_llm_baseline()
