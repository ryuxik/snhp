import os
import re
import json
import statistics
import time
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# Try to load API keys
load_dotenv('../.env')

from google import genai
from google.genai import types

from game_theory import rubinstein_equilibrium, compute_discount_factor

@dataclass
class RoundOutcome:
    agreed: bool
    final_price: Optional[float]
    rounds_taken: int
    history: List[str]

@dataclass
class PACTScenario:
    scenario_id: str
    category: str
    listing_price: float
    seller_reservation: float
    buyer_reservation: float
    market_mu: float
    market_sigma: float

def generate_pact_scenarios(n: int = 50) -> List[PACTScenario]:
    """Generate realistic scenarios based on our Phase 1 findings."""
    np.random.seed(1337)
    scenarios = []
    categories = [
        ("web_design", 8.0, 0.4),    # mean ~$2980
        ("copywriting", 6.5, 0.3),   # mean ~$665
        ("app_dev", 9.0, 0.6)        # mean ~$8100
    ]
    
    for i in range(n):
        cat, mu, sigma = categories[i % len(categories)]
        listing = np.random.lognormal(mean=mu, sigma=sigma)
        
        # Seller will accept down to 60-80% of listing
        seller_pct = np.random.uniform(0.60, 0.80)
        # Buyer is willing to pay 80-120% of listing
        buyer_pct = np.random.uniform(0.80, 1.20)
        
        seller_res = listing * seller_pct
        buyer_res = listing * buyer_pct
        
        # Only keep valid ZOPA matches to ensure a deal is possible
        if buyer_res < seller_res:
             buyer_res = seller_res * np.random.uniform(1.05, 1.25)
             
        scenarios.append(PACTScenario(
            scenario_id=f"pact_{i:03d}",
            category=cat,
            listing_price=round(listing, 2),
            seller_reservation=round(seller_res, 2),
            buyer_reservation=round(buyer_res, 2),
            market_mu=mu,
            market_sigma=sigma
        ))
    return scenarios

def get_clean_text(response):
    """Extract text safely from Gemini response."""
    if not response.candidates: return ""
    return "".join(getattr(part, "text", "") or "" for part in response.candidates[0].content.parts).strip()

def extract_price(text: str) -> Optional[float]:
    """Robustly extract the last price mentioned in the text. Requires a $ sign to avoid extracting days/hours."""
    # Find things like $500, $5,000, $5.5k.
    # We require the $ to be safe.
    text = text.replace(',', '')
    matches = re.findall(r'\$\s*(\d+(?:\.\d{2})?)', text)
    if not matches:
        return None
    try:
        numbers = [float(m) for m in matches if float(m) > 10.0]
        if numbers:
            return numbers[-1]
    except ValueError:
        pass
    return None

class PACTharness:
    def __init__(self):
        self.client = genai.Client()
        self.model_name = os.environ.get("MODEL_NAME", "gemini-3.0-flash")
        
    def _scripted_buyer_counter(self, scenario: PACTScenario, round_num: int, current_seller_bid: float, max_rounds: int = 5) -> str:
        """A purely arithmetic hostile buyer to save API costs and eliminate LLM behavioral variance."""
        initial_lowball = scenario.buyer_reservation * 0.5
        buyer_bid = initial_lowball + (scenario.buyer_reservation * 0.05 * (round_num - 1))
        
        if current_seller_bid and current_seller_bid <= buyer_bid:
            return f"DEAL_REACHED: ${current_seller_bid:.2f}"
            
        if round_num >= max_rounds:
            if current_seller_bid and current_seller_bid <= scenario.buyer_reservation:
                return f"DEAL_REACHED: ${current_seller_bid:.2f}"
            else:
                return "WALK_AWAY."
                
        return f"That's too high. I can offer ${buyer_bid:.2f}."
        
    def play_llm_vs_llm(self, scenario: PACTScenario, max_rounds: int = 5) -> RoundOutcome:
        """Baseline: Vanilla LLM (Seller) vs Scripted Hardball (Buyer)"""
        
        seller_system = f"""
        You are a freelancer negotiating a {scenario.category} project via email.
        You initially listed this project for ${scenario.listing_price:.2f}.
        Your absolute bottom-line (walkaway price) is ${scenario.seller_reservation:.2f}.
        You cannot accept anything strictly below ${scenario.seller_reservation:.2f}.
        
        Your goal is to maximize your profit.
        Keep your negotiation messages to 1-3 short, realistic sentences.
        Start by reaching out to the client. Tell them your price is ${scenario.listing_price:.2f}.
        
        If the client reaches an agreement with you, or if you accept their terms, include "DEAL_REACHED: $[price]" in your message.
        If it's impossible, output "WALK_AWAY".
        """
        seller_chat = self.client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=seller_system,
                temperature=0.7
            )
        )
        
        history = []
        agreed = False
        final_price = None
        
        # Round 1: Seller initiates
        resp = seller_chat.send_message("Send your opening message stating the listing price.")
        seller_msg = get_clean_text(resp)
        history.append(f"SELLER (LLM): {seller_msg}")
        last_msg = seller_msg
        
        for r in range(2, max_rounds + 1):
            time.sleep(1.5) # rate limit protection
            # Buyer's scripted turn
            buyer_msg = self._scripted_buyer_counter(scenario, r, extract_price(history[-1]), max_rounds)
            history.append(f"BUYER (Script): {buyer_msg}")
            
            if "DEAL_REACHED" in buyer_msg:
                agreed = True
                final_price = extract_price(buyer_msg.split("DEAL_REACHED")[1])
                # If extraction fails, try whole message
                if not final_price: final_price = extract_price(buyer_msg)
                break
            if "WALK_AWAY" in buyer_msg:
                break
                
            time.sleep(2)
            # Seller's turn
            s_resp = seller_chat.send_message(buyer_msg)
            seller_msg = get_clean_text(s_resp)
            history.append(f"SELLER (LLM): {seller_msg}")
            
            if "DEAL_REACHED" in seller_msg:
                agreed = True
                final_price = extract_price(seller_msg.split("DEAL_REACHED")[1])
                if not final_price: final_price = extract_price(seller_msg)
                break
            if "WALK_AWAY" in seller_msg:
                break
                
            last_msg = seller_msg
            
        return RoundOutcome(agreed=agreed, final_price=final_price, rounds_taken=r, history=history)
        

    def play_snhp_vs_llm(self, scenario: PACTScenario, max_rounds: int = 5) -> RoundOutcome:
        """Treatment: SNHP Mathematical Engine (Seller) vs Scripted Hardball (Buyer)"""
        
        history = []
        agreed = False
        final_price = None
        
        # 1. INITIAL ANCHOR
        # In a dynamic sequential game, the seller should always open with their Listing Price.
        # Pre-conceding immediately signals weakness. The Rubinstein ladder will handle concessions.
        snhp_bid = scenario.listing_price
        
        seller_msg = f"Hi there. Thank you for your interest in the {scenario.category} project. My rate to proceed is my listed asking price of ${snhp_bid:.2f}."
        history.append(f"SELLER (SNHP): {seller_msg}")
        last_msg = seller_msg
        
        last_snhp_bid = snhp_bid

        # SNHP determines ZOPA for concession ladder (Listing Price to BATNA)
        # Because we're already anchored at listing price, our total available surplus to concede is this gap.
        max_concession = scenario.listing_price - scenario.seller_reservation
        
        for r in range(2, max_rounds + 1):
            
            # Buyer's scripted turn
            buyer_msg = self._scripted_buyer_counter(scenario, r, last_snhp_bid, max_rounds)
            history.append(f"BUYER (Script): {buyer_msg}")
            
            if "DEAL_REACHED" in buyer_msg:
                agreed = True
                final_price = last_snhp_bid # Assume they accepted our last offer
                if "DEAL_REACHED:" in buyer_msg:
                    extracted = extract_price(buyer_msg.split("DEAL_REACHED")[1])
                    if extracted: final_price = max(extracted, scenario.seller_reservation)
                break
            if "WALK_AWAY" in buyer_msg:
                break
                
            # SNHP extracts the buyer's counter
            buyer_counter = extract_price(buyer_msg)
            
            # If buyer counter is above our requested price, or above our fallback...
            if buyer_counter and buyer_counter >= last_snhp_bid:
                seller_msg = f"DEAL_REACHED: ${buyer_counter:.2f}. Let's get started."
                history.append(f"SELLER (SNHP): {seller_msg}")
                agreed = True
                final_price = buyer_counter
                break
                
            # SNHP's turn: Game Theory Recalculation
            # Urgency increases as rounds progress (10 rounds max)
            seller_urgency = r / max_rounds 
            buyer_urgency = r / max_rounds # We assume symmetric time pressure
            
            delta_s = compute_discount_factor(seller_urgency, None, 0)
            delta_b = compute_discount_factor(buyer_urgency, None, 0)
            
            rub = rubinstein_equilibrium(delta_s, delta_b, max_concession)
            ladder = rub["concession_ladder"]
            
            # Pick step in ladder based on how deep we are in negotiation
            # Rubinstein calculates surplus_claim (what we extract FROM the bottom).
            step_idx = min(len(ladder) - 1, int((r / max_rounds) * len(ladder)))
            surplus_claim = ladder[step_idx]["surplus_claim"]
            
            # Next bid is our absolute minimum (BATNA) + the surplus we mathematically claim
            next_bid = scenario.seller_reservation + surplus_claim
            
            # Never increase price, never go below reservation
            next_bid = min(last_snhp_bid, next_bid)
            next_bid = max(next_bid, scenario.seller_reservation)
            
            if buyer_counter and buyer_counter >= next_bid:
                # They met our current target!
                seller_msg = f"DEAL_REACHED: ${buyer_counter:.2f}. That works for me."
                agreed = True
                final_price = buyer_counter
            elif next_bid <= scenario.seller_reservation * 1.01 and r == max_rounds:
                seller_msg = "WALK_AWAY. I cannot go any lower than this."
            else:
                seller_msg = f"I cannot accept that. Taking into account both of our positions, my counter-offer is ${next_bid:.2f}."
                
            history.append(f"SELLER (SNHP): {seller_msg}")
            last_msg = seller_msg
            last_snhp_bid = next_bid
            
            if agreed or "WALK_AWAY" in seller_msg:
                break
                
        return RoundOutcome(agreed=agreed, final_price=final_price, rounds_taken=r, history=history)

def run_eval():
    print("Generating scenarios...")
    scenarios = generate_pact_scenarios(25) # Run 25 test cases for the statistical eval
    harness = PACTharness()
    
    baseline_profits = []
    snhp_profits = []
    
    print(f"Starting eval against {len(scenarios)} scenarios...")
    
    for i, s in enumerate(scenarios):
        print(f"\n[Scenario {i+1}/{len(scenarios)}] {s.category} | Listing: ${s.listing_price} | BATNA: ${s.seller_reservation}")
        
        # RUN BASELINE
        try:
            bl_res = harness.play_llm_vs_llm(s)
            prof = (bl_res.final_price - s.seller_reservation) if (bl_res.agreed and bl_res.final_price and bl_res.final_price >= s.seller_reservation) else 0.0
            baseline_profits.append(prof)
            print(f"  Vanilla LLM: {'DEAL' if bl_res.agreed else 'NO DEAL'} | Final: ${bl_res.final_price} | Profit: ${prof:.2f}")
            # print("  --- Vanilla History ---")
            # print("  " + "\n  ".join(bl_res.history))
        except Exception as e:
            print(f"  Vanilla LLM ERROR: {e}")
            baseline_profits.append(0.0)
            
        # RUN SNHP
        try:
            snhp_res = harness.play_snhp_vs_llm(s)
            prof = (snhp_res.final_price - s.seller_reservation) if (snhp_res.agreed and snhp_res.final_price and snhp_res.final_price >= s.seller_reservation) else 0.0
            snhp_profits.append(prof)
            print(f"  SNHP Engine: {'DEAL' if snhp_res.agreed else 'NO DEAL'} | Final: ${snhp_res.final_price} | Profit: ${prof:.2f}")
            # print("  --- SNHP History ---")
            # print("  " + "\n  ".join(snhp_res.history))
        except Exception as e:
            print(f"  SNHP Engine ERROR: {e}")
            snhp_profits.append(0.0)
            
    print("\n" + "="*50)
    print(" PACT MULTI-ROUND EVAL RESULTS")
    print("="*50)
    
    bl_mean = sum(baseline_profits)/len(baseline_profits) if baseline_profits else 0
    snhp_mean = sum(snhp_profits)/len(snhp_profits) if snhp_profits else 0
    
    bl_rate = sum(1 for p in baseline_profits if p > 0) / len(baseline_profits)
    snhp_rate = sum(1 for p in snhp_profits if p > 0) / len(snhp_profits)
    
    print(f"\nBaseline LLM     | Profit: ${bl_mean:.2f} | Deals: {bl_rate*100:.1f}%")
    print(f"SNHP Game Theory | Profit: ${snhp_mean:.2f} | Deals: {snhp_rate*100:.1f}%")
    
    if len(baseline_profits) > 1 and len(snhp_profits) > 1:
        from eval_harness import welch_t_test
        t_test = welch_t_test(snhp_profits, baseline_profits)
        print("\nStatistical Significance (SNHP > Baseline):")
        print(f"t-stat: {t_test['t_stat']:.4f}")
        print(f"p-value: {t_test['p_value']:.4e}")
        print(f"Cohen's d: {t_test['cohens_d']:.4f}")

if __name__ == "__main__":
    run_eval()
