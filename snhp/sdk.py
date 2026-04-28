import os
import json
import logging
import numpy as np

# Removed legacy google.genai dependency block

from .models import SNHPResponse, ConcessionStep

from .engram import Engram
from .nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
from .bayesian_agent import BayesianParticleFilter
from .llm_extractor import (
    extract_all_parameters,
    _call_llm,
)
from .market_intel import match_category, get_market_rates
from .history_store import compute_historical_stats
from .game_theory import calculate_optimal_counter

def compute_freelancer_bounds(ext: dict) -> dict:
    ideal_price = None
    min_price = ext.get("minimum_batna_price")

    if ext.get("total_budget"):
        ideal_price = ext["total_budget"]
    elif ext.get("hourly_rate"):
        rate = ext["hourly_rate"]
        if ext.get("max_hours_total"):
            ideal_price = rate * ext["max_hours_total"]
        elif ext.get("max_hours_per_day") and ext.get("duration_days"):
            ideal_price = rate * ext["max_hours_per_day"] * ext["duration_days"]

    if min_price is None and ext.get("hourly_batna"):
        batna_rate = ext["hourly_batna"]
        if ext.get("max_hours_total"):
            min_price = batna_rate * ext["max_hours_total"]
        elif ext.get("max_hours_per_day") and ext.get("duration_days"):
            min_price = batna_rate * ext["max_hours_per_day"] * ext["duration_days"]

    if min_price is None and ideal_price is not None:
        min_price = ideal_price * 0.8  # Autonomic python fallback

    total_hours = None
    if ext.get("max_hours_per_day") and ext.get("duration_days"):
        total_hours = ext["max_hours_per_day"] * ext["duration_days"]
    elif ext.get("max_hours_total"):
        total_hours = ext["max_hours_total"]

    return {
        "ideal_price": ideal_price,
        "min_price": min_price,
        "ideal_days": ext.get("duration_days"),
        "max_days": ext.get("max_duration_days"),
        "ideal_revisions": ext.get("revisions"),
        "max_revisions": ext.get("max_revisions"),
        "hourly_rate": ext.get("hourly_rate"),
        "hourly_batna": ext.get("hourly_batna"),
        "total_hours": total_hours,
        "preferred_payment_days": ext.get("preferred_payment_days"),
    }


def check_missing_freelancer_fields(bounds: dict) -> list:
    missing = []
    if bounds["ideal_price"] is None:
        missing.append("your ideal rate or total budget")
    if bounds["min_price"] is None:
        missing.append("your walk-away minimum rate or total")
    return missing


def generate_decoder_email(client_email, constraints_str, numbers: dict, mode: str, tone: str = "professional", negotiation_context: str = None):
    if mode == "anchor":
        strategy_note = (
            "This is an OPENING ANCHOR backed by market data. "
            "Be confident and justified, not aggressive. Frame the rate as standard for your market."
        )
    else:
        strategy_note = (
            "This is a FINAL OPTIMIZED OFFER based on game theory. Frame it as a fair, structured compromise."
        )
    
    # Tone modulation
    tone_instructions = {
        "professional": "Use a professional, polished business tone.",
        "friendly": "Use a warm, conversational and approachable tone. Be personable but still competent.",
        "firm": "Use a confident, assertive tone. Be direct and leave little room for haggling.",
    }
    tone_note = tone_instructions.get(tone, tone_instructions["professional"])
    
    # Multi-round context
    context_note = ""
    if negotiation_context:
        context_note = f"\n    Previous negotiation context: {negotiation_context}\n    Reference prior rounds naturally in your reply.\n"

    numbers_str = f"- Price: ${numbers['price']:.2f}\n"
    if numbers.get('days') is not None:
        numbers_str += f"    - Timeline: {numbers['days']:.0f} days\n"
    if numbers.get('revisions') is not None:
        numbers_str += f"    - Revisions: {numbers['revisions']:.0f} rounds\n"
    if numbers.get('payment_days') is not None:
        pt = numbers['payment_days']
        numbers_str += f"    - Payment Terms: {'upon completion' if pt == 0 else f'net-{pt}'} days\n"

    prompt = f"""
    You are a professional freelance negotiator drafting a reply email.

    The opposing client wrote: 
    <client_email>
    {client_email}
    </client_email>

    Your freelancer's constraints: 
    <freelancer_constraints>
    {constraints_str}
    </freelancer_constraints>

    Strategy: {strategy_note}
    Tone: {tone_note}
{context_note}
    You MUST use these exact numbers — do NOT invent or alter them:
{numbers_str}

    Draft a brief, 3-sentence professional reply.
    """

    try:
        return _call_llm(prompt, temperature=0.7)
    except Exception as e:
        import sys
        print(f"[SNHP EXCEPTION] Decoder LLM Call Failed: {e}", file=sys.stderr)
        return f"Based on optimization: I can offer this at ${numbers['price']:.2f}. Let me know if you would like to proceed."


def run_path_a(client_email, constraints_str, opp_utility, free_bounds, client_anchor, client_role, tone="professional", negotiation_context=None) -> SNHPResponse:
    logging.info("PATH A: Complete information — Nash grid.")

    resolution = 5
    dims_features = []
    
    # Base Dimension (0): Price
    dims_features.append(np.linspace(0, 1, resolution))
    anchor_weights = [opp_utility['price_weight']]
    snhp_weights = [0.5]
    
    # Optional Dimension (1): Speed/Time
    idx_days = -1
    if free_bounds.get("ideal_days") is not None and free_bounds.get("max_days") is not None:
        idx_days = len(dims_features)
        dims_features.append(np.linspace(0, 1, resolution))
        anchor_weights.append(opp_utility['speed_weight'])
        snhp_weights.append(0.2)
        
    # Optional Dimension (2): Revisions
    idx_revisions = -1
    if free_bounds.get("ideal_revisions") is not None and free_bounds.get("max_revisions") is not None:
        idx_revisions = len(dims_features)
        dims_features.append(np.linspace(0, 1, resolution))
        anchor_weights.append(opp_utility['revisions_weight'])
        snhp_weights.append(0.3)
    
    # Optional Dimension (3): Payment Terms
    idx_payment = -1
    client_pay_days = opp_utility.get('payment_terms_days')
    free_pay_days = free_bounds.get('preferred_payment_days')
    if client_pay_days is not None and free_pay_days is not None and client_pay_days != free_pay_days:
        idx_payment = len(dims_features)
        dims_features.append(np.linspace(0, 1, resolution))
        # Payment terms weight: low priority vs price, but non-trivial
        anchor_weights.append(0.1)
        snhp_weights.append(0.15)
        
    num_dims = len(dims_features)

    anchor = np.array(anchor_weights)
    opponent_batna = opp_utility['batna_threshold']
    freelancer_batna = 0.05
    snhp_engram = Engram(snhp_weights, batna=freelancer_batna)

    if num_dims == 1:
        contract_matrix = np.array(dims_features[0]).reshape(-1, 1)
    else:
        meshes = np.meshgrid(*dims_features)
        contract_matrix = np.array(meshes).T.reshape(-1, num_dims)

    b_filter = BayesianParticleFilter(num_variables=num_dims, num_particles=5000, uncertainty=0.2)
    b_filter.update_beliefs(anchor, contract_matrix)
    inferred = b_filter.get_inferred_weights()
    opponent_engram = Engram(inferred, batna=opponent_batna)

    u_snhp = snhp_engram.evaluate_bulk(contract_matrix)
    u_opp = opponent_engram.evaluate_bulk(1.0 - contract_matrix)

    pareto_indices = filter_pareto_frontier(contract_matrix, u_snhp, u_opp)
    # Opponent BATNA was inferred from extracted utility weights, not observed
    # → Bayesian-Nash heuristic, not classical Nash. See nash_solver.py docstring.
    best_idx = find_nash_bargaining_solution(
        pareto_indices, u_snhp, u_opp,
        snhp_engram.batna, opponent_engram.batna,
        batna_b_inferred=True,
    )

    if best_idx is None:
        return SNHPResponse(
            is_complete=False,
            missing_fields=["The gap between your minimum and their stated budget is too wide for a viable deal. The strongest move is to walk away or request they revisit their budget."]
        )

    best = contract_matrix[best_idx]
    b = free_bounds

    final_price = b["min_price"] + (best[0] * (b["ideal_price"] - b["min_price"]))
    
    final_days = b.get("ideal_days")
    if idx_days != -1:
        final_days = b["ideal_days"] + (best[idx_days] * (b["max_days"] - b["ideal_days"]))
        
    final_revisions = b.get("ideal_revisions")
    if idx_revisions != -1:
        final_revisions = b["max_revisions"] - (best[idx_revisions] * (b["max_revisions"] - b["ideal_revisions"]))

    final_payment_days = free_pay_days
    if idx_payment != -1:
        # Interpolate: 0 = freelancer's preference, 1 = client's preference
        pay_min = min(free_pay_days, client_pay_days)
        pay_max = max(free_pay_days, client_pay_days)
        final_payment_days = int(pay_min + best[idx_payment] * (pay_max - pay_min))

    numbers = {"price": final_price, "days": final_days, "revisions": final_revisions, "payment_days": final_payment_days}
    drafted = generate_decoder_email(client_email, constraints_str, numbers, mode="nash", tone=tone, negotiation_context=negotiation_context)

    return SNHPResponse(
        is_complete=True,
        path_taken="Nash",
        optimal_anchor=final_price,
        target_days=int(final_days) if final_days is not None else None,
        target_revisions=int(final_revisions) if final_revisions is not None else None,
        target_payment_days=final_payment_days,
        total_project_quote=final_price,
        draft_email=drafted
    ).apply_delta_capture(client_anchor, client_role=client_role)


def run_path_b(client_email, constraints_str, client_constraints, free_bounds, free_extracted, client_anchor, client_role, tone="professional", negotiation_context=None) -> SNHPResponse:
    logging.info("PATH B: Incomplete information — Myerson/Rubinstein engine.")

    category = free_extracted.get("category_hint") or match_category(client_email, constraints_str)
    market = get_market_rates(category) if category else None
    history = compute_historical_stats()

    hist_avg = history.get("avg_hourly")
    pipeline = history.get("active_pipeline", 0)

    # Calculate optimal math core via unified Engine Facade
    math_core = calculate_optimal_counter(
        free_bounds=free_bounds,
        client_constraints=client_constraints,
        market_data=market,
        historical_avg=hist_avg,
        pipeline_count=pipeline
    )

    anchor_total = math_core["total_project_quote"]
    anchor_days = math_core["target_days"]
    anchor_revisions = math_core["target_revisions"]

    numbers = {"price": anchor_total, "days": anchor_days, "revisions": anchor_revisions}
    drafted = generate_decoder_email(client_email, constraints_str, numbers, mode="anchor", tone=tone, negotiation_context=negotiation_context)

    concession_ladder = []
    batna_total = math_core["minimum_batna_total"]
    
    round_labels = ["If they reject initial quote", "If they push back again", "If they push back a third time", "Final compromise"]
    
    for i, step in enumerate(math_core["concession_ladder"]):
        step_total = batna_total + step["surplus_claim"]
        label = round_labels[i] if i < len(round_labels) else f"Counter-offer {i+1}"
        concession_ladder.append(ConcessionStep(label=label, amount=step_total))

    return SNHPResponse(
        is_complete=True,
        path_taken="Rubinstein",
        optimal_anchor=math_core["optimal_anchor"],
        target_days=anchor_days,
        target_revisions=anchor_revisions,
        total_project_quote=anchor_total,
        estimated_total_hours=math_core["estimated_total_hours"],
        acceptance_probability=math_core["acceptance_probability"],
        market_median=math_core["market_median"],
        market_high=math_core["market_median"] * 1.25, # Derived approximation
        should_probe=math_core["should_probe"],
        deadweight_warning=math_core["deadweight_warning"],
        concession_ladder=concession_ladder,
        minimum_batna_total=batna_total,
        draft_email=drafted,
        historical_count=history.get("count"),
        historical_avg=hist_avg
    ).apply_delta_capture(client_anchor, client_role=client_role)


def negotiate(message: str, constraints, client_role: str = "seller", tone: str = "professional", negotiation_context: str = None) -> SNHPResponse:
    if isinstance(constraints, dict):
        constraints_str = json.dumps(constraints)
    else:
        constraints_str = str(constraints)

    logging.info("SNHP Engine v3 SDK — extracting...")

    print("[SNHP] Extracting all parameters in a single pass...", flush=True)
    all_params = extract_all_parameters(message, constraints_str)
    print("[SNHP] Extraction complete.", flush=True)

    opp_utility = {
        "price_weight": all_params.get("opp_utility_price_weight", 0.65),
        "speed_weight": all_params.get("opp_utility_speed_weight", 0.05),
        "revisions_weight": all_params.get("opp_utility_revisions_weight", 0.3),
        "batna_threshold": all_params.get("opp_utility_batna_threshold", 0.7),
        "payment_terms_days": all_params.get("client_payment_terms_days"),
    }

    client_constraints = {
        "explicit_budget": all_params.get("client_explicit_budget"),
        "explicit_hourly_rate": all_params.get("client_explicit_hourly_rate"),
        "timeline_days": all_params.get("client_timeline_days"),
        "max_revisions": all_params.get("client_max_revisions"),
        "urgency_score": all_params.get("client_urgency_score", 0.5),
        "is_competitive_bid": all_params.get("client_is_competitive_bid", False)
    }

    free_extracted = {
        "hourly_rate": all_params.get("free_hourly_rate"),
        "total_budget": all_params.get("free_total_budget"),
        "duration_days": all_params.get("free_duration_days"),
        "max_duration_days": all_params.get("free_max_duration_days"),
        "max_hours_per_day": all_params.get("free_max_hours_per_day"),
        "max_hours_total": all_params.get("free_max_hours_total"),
        "revisions": all_params.get("free_revisions"),
        "max_revisions": all_params.get("free_max_revisions"),
        "minimum_batna_price": all_params.get("free_minimum_batna_price"),
        "hourly_batna": all_params.get("free_hourly_batna"),
        "category_hint": all_params.get("free_category_hint"),
        "preferred_payment_days": all_params.get("free_preferred_payment_days"),
    }

    free_bounds = compute_freelancer_bounds(free_extracted)

    missing = check_missing_freelancer_fields(free_bounds)
    if missing:
        return SNHPResponse(is_complete=False, missing_fields=missing)

    client_has_budget = (
        client_constraints.get("explicit_budget") is not None
        or client_constraints.get("explicit_hourly_rate") is not None
    )

    client_anchor = None
    if client_constraints.get("explicit_budget"):
        client_anchor = client_constraints.get("explicit_budget")
    elif client_constraints.get("explicit_hourly_rate") and free_bounds.get("total_hours"):
        client_anchor = client_constraints.get("explicit_hourly_rate") * free_bounds.get("total_hours")

    if client_has_budget:
        return run_path_a(message, constraints_str, opp_utility, free_bounds, client_anchor, client_role, tone=tone, negotiation_context=negotiation_context)
    else:
        return run_path_b(message, constraints_str, client_constraints, free_bounds, free_extracted, client_anchor, client_role, tone=tone, negotiation_context=negotiation_context)
