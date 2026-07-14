import numpy as np
from engram import Engram
from engram import Engram
from bayesian_agent import BayesianParticleFilter

def run_greenpoint_simulation():
    print("========== SNHP: THE GREENPOINT SUBLEASE ==========")
    print("Context: It is Springtime in Brooklyn. The rental market is vicious.")
    print("Dimensions: [Monthly Rent, Lease Duration, Upfront Deposit]\n")

    # The Tenant's (SNHP) preferences:
    # 0: Rent (Cares heavily about keeping rent affordable) -> Weight 0.6
    # 1: Lease Duration (Wants to lock in 24 months to avoid next spring's hike) -> Weight 0.3
    # 2: Deposit (Prefers keeping cash liquid) -> Weight 0.1
    # BATNA: 0.45 (Walk away if the deal doesn't meet basic affordability and stability)
    snhp_tenant_engram = Engram([0.6, 0.3, 0.1], batna=0.45)
    print(f"Tenant True Priorities: Rent=60%, Duration=30%, Deposit=10% (BATNA: {snhp_tenant_engram.batna})")

    # Generate Contract Matrix (0.0 represents terrible for tenant (High Rent), 1.0 represents perfect for tenant)
    print("\nGenerating Brooklyn Rental Contract Space... (Grid Search)")
    resolution = 5
    contract_matrix = np.array(np.meshgrid(
        np.linspace(0, 1, resolution),  # Rent
        np.linspace(0, 1, resolution),  # Lease Duration
        np.linspace(0, 1, resolution)   # Deposit
    )).T.reshape(-1, 3)

    # Landlord FOMO Email
    landlord_email = "Hey man, getting crazy traffic on the 1BR. I have three people coming to view it at 5PM with cashier's checks. The rent is $4,800 firm. I need first, last, and 1 month security deposit upfront. And I am strictly doing a 12-month lease. Take it or leave it, let me know by 1PM."
    
    print("\n>>> LANDLORD EMAIL RECEIVED:")
    print(f"\"{landlord_email}\"")

    # NLP Extraction Mapping (Mocking the llm_extractor output for reliability in this script)
    # The landlord is demanding maximum utility on all fronts (0.0 utility for the tenant).
    landlord_anchor = np.array([0.0, 0.0, 0.0])
    
    print("\nSNHP NLP Translation Layer parses the emotional FOMO tactic.")
    print(f"Extracted Anchor (Normalized for Tenant): {landlord_anchor} (Total Hostility)")

    # CRM Prior for this Management Company (They historically care mostly about pure cashflow/rent)
    crm_prior = [0.8, 0.1, 0.1]
    
    print(f"\nSeeding SNHP Bayesian Engine with Corporate Landlord CRM Data: {crm_prior}")
    filter = BayesianParticleFilter(num_variables=3, num_particles=50000, historical_prior=crm_prior, uncertainty=0.2)
    filter.update_beliefs(landlord_anchor, contract_matrix)
    inferred_landlord_weights = filter.get_inferred_weights()
    
    print(f"\n>>> SNHP Bayesian Analysis Complete:")
    print(f"Inferred Landlord True Utilities: Rent={inferred_landlord_weights[0]:.2f}, Duration={inferred_landlord_weights[1]:.2f}, Deposit={inferred_landlord_weights[2]:.2f}")
    print("Insight: The Bayesian engine cuts through the FOMO. It knows the landlord doesn't actually care about a 12-month lease; they just want the rent money.")

    # Instantiate the Landlord's shadow engram
    shadow_landlord_engram = Engram(inferred_landlord_weights, batna=0.3)

    print("\nSolving for Pareto-Optimal Nash Bargaining Solution...")
    
    utilities_tenant = snhp_tenant_engram.evaluate_bulk(contract_matrix)
    utilities_landlord = shadow_landlord_engram.evaluate_bulk(1.0 - contract_matrix)
    
    from nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
    pareto_indices = filter_pareto_frontier(contract_matrix, utilities_tenant, utilities_landlord)
    best_index = find_nash_bargaining_solution(pareto_indices, utilities_tenant, utilities_landlord, snhp_tenant_engram.batna, shadow_landlord_engram.batna)
    
    print(f"\n======================================")
    if best_index is None:
        print(f"SNHP DECISION ENGINE: MATHEMATICAL DEADLOCK")
        print(f"======================================")
        print("Analysis: Structurally impossible to meet both BATNAs.")
    else:
        best_contract = contract_matrix[best_index]
        u_t = utilities_tenant[best_index]
        u_l = utilities_landlord[best_index]
        print(f"SNHP DECISION ENGINE: RATIONAL DEAL FOUND")
        print(f"======================================")
        print(f"Recommended Counter-Offer [Rent Utility, Duration Utility, Deposit Utility]: {best_contract}")
        print(f"Tenant Expected Utility: {u_t:.3f}")
        print(f"Projected Landlord Utility: {u_l:.3f}")
        
        # Translate back to real-world terms
        rent_price = 5000 - (best_contract[0] * 1000) # 0.0 -> 5000, 1.0 -> 4000
        duration_months = 12 + (best_contract[1] * 12) # 0.0 -> 12, 1.0 -> 24
        deposit_months = 3 - (best_contract[2] * 2) # 0.0 -> 3, 1.0 -> 1
        
        print("\n>>> SNHP DRAFTED COUNTER-EMAIL:")
        print(f"\"Hey, I can put down a deposit in the next hour to secure it. Let's do ${rent_price:.0f}/mo. I'll agree to the {deposit_months:.0f} month deposit upfront if we lock it in for a {duration_months:.0f}-month lease to save you the hassle of listing it again next Spring. Send the paperwork.\"")

if __name__ == "__main__":
    run_greenpoint_simulation()
