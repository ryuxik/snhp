"""
Generate realistic CraigslistBargains-format data for eval.

Based on He et al., 2018 "Decoupling Strategy and Generation in Negotiation Dialogues":
- 6 categories: housing, car, phone, bike, electronics, furniture
- Seller target = listing price, Buyer target = discount × listing price
- Discount factors: 0.5, 0.7, 0.9 (assigned to buyer scenarios)
- Deal rate ~70% (human-human), final price typically 15-40% below listing
- Buyer bottomline = target (max they'll pay)
- Seller bottomline = 0.6-0.8 × listing price

Price distributions per category from Craigslist 2018 listings:
  housing:     $400 - $3500  (rent)
  car:         $1000 - $25000
  phone:       $50 - $800
  bike:        $50 - $1500
  electronics: $20 - $500
  furniture:   $30 - $800
"""
import json
import random
import numpy as np
from typing import List, Dict

# Realistic price distributions per category (log-normal parameters)
CATEGORY_PARAMS = {
    "housing":     {"mu": 7.2, "sigma": 0.6, "min": 400, "max": 3500},
    "car":         {"mu": 8.5, "sigma": 0.8, "min": 1000, "max": 25000},
    "phone":       {"mu": 5.5, "sigma": 0.5, "min": 50, "max": 800},
    "bike":        {"mu": 5.5, "sigma": 0.7, "min": 50, "max": 1500},
    "electronics": {"mu": 4.8, "sigma": 0.7, "min": 20, "max": 500},
    "furniture":   {"mu": 5.0, "sigma": 0.6, "min": 30, "max": 800},
}

# Discount factors from the paper (buyer's target = discount × listing)
DISCOUNT_FACTORS = [0.5, 0.7, 0.9]

# Category weights (from paper's ~equal distribution)
CATEGORY_WEIGHTS = {
    "housing": 0.17, "car": 0.17, "phone": 0.17,
    "bike": 0.16, "electronics": 0.17, "furniture": 0.16,
}


def generate_listing_price(category: str) -> float:
    """Generate a realistic listing price for a category."""
    params = CATEGORY_PARAMS[category]
    price = np.random.lognormal(params["mu"], params["sigma"])
    price = np.clip(price, params["min"], params["max"])
    return round(price, 2)


def generate_scenario(scenario_id: int) -> Dict:
    """
    Generate one CraigslistBargains scenario.
    
    Models the actual negotiation dynamics from the paper:
    - Seller lists at listing_price, has bottomline (walkaway) at 60-85% of listing
    - Buyer has target (ideal) at discount × listing, bottomline (max) at 80-110% of target
    - Deal happens ~70% of the time when ZOPA exists
    - Deal price is drawn from the ZOPA with buyer-favorable skew
    """
    # Pick category
    category = random.choices(
        list(CATEGORY_WEIGHTS.keys()),
        weights=list(CATEGORY_WEIGHTS.values())
    )[0]
    
    listing_price = generate_listing_price(category)
    
    # Seller's private info
    seller_target = listing_price  # Seller wants listing price
    seller_bottomline = listing_price * random.uniform(0.55, 0.85)  # Walk-away
    
    # Buyer's private info (discount from paper)
    discount = random.choice(DISCOUNT_FACTORS)
    buyer_target = listing_price * discount  # Ideal price
    # Buyer's max WTP: slightly above target (they have some flex)
    buyer_bottomline = buyer_target * random.uniform(1.0, 1.25)
    
    # Does a deal happen?
    # ZOPA = buyer_bottomline - seller_bottomline
    zopa = buyer_bottomline - seller_bottomline
    
    if zopa > 0:
        # ZOPA exists — deal happens ~75% of the time (some fail due to negotiation friction)
        deal_happens = random.random() < 0.75
        if deal_happens:
            # Deal price: drawn from ZOPA, with slight buyer advantage
            # (empirically, deals cluster in lower half of ZOPA)
            zopa_frac = random.betavariate(2.0, 3.0)  # Skewed toward buyer
            deal_price = seller_bottomline + zopa * zopa_frac
            deal_price = round(deal_price, 2)
        else:
            deal_price = None
    else:
        # No ZOPA — deal rarely happens (5% compromise)
        deal_happens = random.random() < 0.05
        if deal_happens:
            # Compromise at midpoint of the gap
            deal_price = round((seller_bottomline + buyer_bottomline) / 2, 2)
        else:
            deal_price = None
    
    # Build dialogue acts (simplified — just key price offers)
    dialogue_acts = []
    utterances = []
    agent_turns = []
    
    # Round 1: Seller opens at listing price
    dialogue_acts.append({"intent": "init-price", "price": listing_price})
    utterances.append(f"I'm selling this for ${listing_price:.0f}")
    agent_turns.append(0)  # seller
    
    # Round 2: Buyer counters
    buyer_open = buyer_target * random.uniform(0.85, 1.0)
    dialogue_acts.append({"intent": "counter-price", "price": round(buyer_open, 2)})
    utterances.append(f"Would you take ${buyer_open:.0f}?")
    agent_turns.append(1)  # buyer
    
    if deal_happens:
        # Simulate 1-3 more rounds of back-and-forth
        n_rounds = random.randint(1, 3)
        current_seller_price = listing_price
        current_buyer_price = buyer_open
        
        for _ in range(n_rounds):
            # Seller concedes
            current_seller_price = current_seller_price - (current_seller_price - deal_price) * random.uniform(0.3, 0.6)
            dialogue_acts.append({"intent": "counter-price", "price": round(current_seller_price, 2)})
            utterances.append(f"How about ${current_seller_price:.0f}?")
            agent_turns.append(0)
            
            # Buyer concedes
            current_buyer_price = current_buyer_price + (deal_price - current_buyer_price) * random.uniform(0.3, 0.6)
            dialogue_acts.append({"intent": "counter-price", "price": round(current_buyer_price, 2)})
            utterances.append(f"I can do ${current_buyer_price:.0f}")
            agent_turns.append(1)
        
        # Final accept
        dialogue_acts.append({"intent": "accept", "price": deal_price})
        utterances.append("Deal!")
        agent_turns.append(random.choice([0, 1]))
    else:
        # Rejection
        dialogue_acts.append({"intent": "reject", "price": -1.0})
        utterances.append("Sorry, can't go that low.")
        agent_turns.append(0)
    
    return {
        "agent_info": [
            {"Bottomline": str(round(seller_bottomline, 2)), "Role": "seller", "Target": seller_target},
            {"Bottomline": str(round(buyer_bottomline, 2)), "Role": "buyer", "Target": buyer_target},
        ],
        "agent_turn": agent_turns,
        "dialogue_acts": dialogue_acts,
        "utterance": utterances,
        "items": [
            {
                "Category": category,
                "Images": "",
                "Price": listing_price,
                "Description": f"Sample {category} listing",
                "Title": f"{category.title()} Item #{scenario_id}",
            },
            {
                "Category": category,
                "Images": "",
                "Price": listing_price,
                "Description": f"Sample {category} listing",
                "Title": f"{category.title()} Item #{scenario_id}",
            },
        ],
        "_scenario_id": scenario_id,
        "_deal_price": deal_price,
        "_deal_made": deal_happens,
    }


def generate_dataset(n: int = 5000, seed: int = 42) -> List[Dict]:
    """Generate n scenarios matching CraigslistBargains distribution."""
    random.seed(seed)
    np.random.seed(seed)
    return [generate_scenario(i) for i in range(n)]


if __name__ == "__main__":
    data = generate_dataset(5000)
    
    # Stats
    deals = [d for d in data if d["_deal_made"]]
    no_deals = [d for d in data if not d["_deal_made"]]
    
    print(f"Generated {len(data)} scenarios")
    print(f"  Deals: {len(deals)} ({len(deals)/len(data):.1%})")
    print(f"  No deals: {len(no_deals)} ({len(no_deals)/len(data):.1%})")
    
    # Category breakdown
    from collections import Counter
    cats = Counter(d["items"][0]["Category"] for d in data)
    print(f"\n  Category distribution:")
    for cat, count in sorted(cats.items()):
        cat_deals = sum(1 for d in data if d["items"][0]["Category"] == cat and d["_deal_made"])
        print(f"    {cat:<15} {count:>5} scenarios, {cat_deals:>4} deals ({cat_deals/count:.0%})")
    
    # Price stats for deals
    deal_prices = [d["_deal_price"] for d in deals]
    listing_prices = [d["items"][0]["Price"] for d in deals]
    discounts = [(l - d) / l for l, d in zip(listing_prices, deal_prices)]
    
    print(f"\n  Deal price vs listing:")
    print(f"    Mean discount: {np.mean(discounts):.1%}")
    print(f"    Median discount: {np.median(discounts):.1%}")
    print(f"    Std discount: {np.std(discounts):.1%}")
    
    # Save
    with open("craigslist_bargains.json", "w") as f:
        json.dump(data, f, default=str)
    print(f"\nSaved to craigslist_bargains.json ({len(data)} scenarios)")
