"""
B2B Multi-Source Procurement Benchmark — Repeated Games.

Key difference from single-shot: CrossSessionMemory persists across rounds,
letting SNHP's Thompson Sampling bandit learn per-opponent-type optimal
aggression. This is SNHP's asymmetric advantage over stateless agents.

Dynamic BATNA model:
  BATNA = base_batna × pool_factor(n_alternatives) × deadline_factor(days_left)

Benchmark structure:
  - 14 opponent archetypes (7 original + 7 world-class)
  - 5 repeated rounds per opponent (memory persists)
  - 3 market conditions (Sole-Urgent, Typical, Commodity)
  - Aspiration baseline comparison (no memory advantage)
"""

from negmas.sao import SAOMechanism
from negmas.sao.negotiators import AspirationNegotiator
from negmas.outcomes import make_issue
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import IdentityFun, AffineFun
import numpy as np
import statistics
from typing import Dict, List, Tuple
from collections import defaultdict

import negmas_agent
from negmas_agent import SNHPAgent, CrossSessionMemory
from b2b_opponents import B2B_OPPONENTS


# ─── Dynamic BATNA ────────────────────────────────

BASE_BATNA = 0.40

def pool_factor(n_alternatives: int) -> float:
    if n_alternatives <= 1: return 0.60
    elif n_alternatives <= 2: return 0.75
    elif n_alternatives <= 3: return 0.85
    elif n_alternatives <= 4: return 0.92
    else: return 1.00

def deadline_factor(days_remaining: int) -> float:
    if days_remaining <= 2: return 0.60
    elif days_remaining <= 7: return 0.75
    elif days_remaining <= 14: return 0.85
    elif days_remaining <= 30: return 0.92
    else: return 1.00

def compute_batna(pool_size: int, days_left: int) -> float:
    return BASE_BATNA * pool_factor(pool_size) * deadline_factor(days_left)


MARKET_CONDITIONS = {
    "Sole-Urgent":  {"pool": 1, "days": 3,  "label": "1 vendor, 3d"},
    "Typical":      {"pool": 3, "days": 14, "label": "3 vendors, 14d"},
    "Commodity":    {"pool": 5, "days": 30, "label": "5 vendors, 30d"},
}


def create_issues():
    return [
        make_issue(name="price", values=50),
        make_issue(name="delivery", values=5),
        make_issue(name="warranty", values=4),
        make_issue(name="payment", values=3),
    ]


def create_ufuns(issues, n_steps: int = 10):
    """Balanced 4-issue utility functions."""
    weights = {"price": 0.40, "delivery": 0.25, "warranty": 0.20, "payment": 0.15}
    temp = SAOMechanism(issues=issues, n_steps=n_steps)
    iss = temp.outcome_space.issues

    seller_ufun = LUFun(
        values={"price": IdentityFun(), "delivery": IdentityFun(),
                "warranty": AffineFun(slope=-1, bias=3),
                "payment": AffineFun(slope=-1, bias=2)},
        weights=weights, issues=iss,
    ).normalize()

    buyer_ufun = LUFun(
        values={"price": AffineFun(slope=-1, bias=49),
                "delivery": AffineFun(slope=-1, bias=4),
                "warranty": IdentityFun(), "payment": IdentityFun()},
        weights=weights, issues=iss,
    ).normalize()

    return seller_ufun, buyer_ufun


def run_repeated_matchup(snhp_class, opp_class, seller_ufun, buyer_ufun,
                         issues, n_steps: int, n_rounds: int, batna: float,
                         persist_memory: bool = True):
    """
    Run N rounds of repeated negotiations.
    
    If persist_memory=True, CrossSessionMemory carries across rounds (SNHP advantage).
    If False, resets each round (stateless baseline behavior).
    
    Returns per-round utility list to show learning curve.
    """
    memory = CrossSessionMemory()
    round_utils = []
    round_deals = []

    for r in range(n_rounds):
        if persist_memory:
            negmas_agent._global_memory = memory  # PERSIST — this is the key
        else:
            negmas_agent._global_memory = CrossSessionMemory()  # RESET

        mech = SAOMechanism(issues=issues, n_steps=n_steps)
        snhp = snhp_class(name=f"snhp_r{r}")
        opp = opp_class(name=f"opp_r{r}")
        mech.add(snhp, ufun=seller_ufun)
        mech.add(opp, ufun=buyer_ufun)

        result = mech.run()

        if result.agreement is not None:
            su = seller_ufun(result.agreement)
            su_val = float(su) if su is not None else 0.0
            round_utils.append(su_val)
            round_deals.append(True)
        else:
            round_utils.append(batna)
            round_deals.append(False)

    return round_utils, round_deals


def run_b2b_benchmark(n_rounds: int = 5, n_reps: int = 10, n_steps: int = 10):
    """
    Full B2B repeated-game benchmark.
    
    For each opponent × market condition:
      - Run n_reps independent series of n_rounds repeated negotiations
      - Average per-round utilities to show learning curve
      - Compare SNHP (with memory) vs SNHP (without) vs Aspiration baseline
    """
    issues = create_issues()
    seller_ufun, buyer_ufun = create_ufuns(issues, n_steps)

    print("=" * 115)
    print("  SNHP B2B REPEATED-GAME BENCHMARK")
    print(f"  4 issues | {n_steps} steps | {n_rounds} rounds | {n_reps} reps | Dynamic BATNA")
    print("=" * 115)

    # BATNA table
    print(f"\n  {'Condition':<16} {'BATNA':>8}")
    print("  " + "-" * 28)
    for cn, c in MARKET_CONDITIONS.items():
        print(f"  {cn:<16} {compute_batna(c['pool'], c['days']):>8.3f}")

    # Run for Typical market (most representative)
    cond = MARKET_CONDITIONS["Typical"]
    batna = compute_batna(cond["pool"], cond["days"])

    print(f"\n  Market: Typical ({cond['label']}, BATNA={batna:.3f})")
    print(f"\n  {'Opponent':<22} {'R1':>7} {'R2':>7} {'R3':>7} {'R4':>7} {'R5':>7} "
          f"{'Δ(R5-R1)':>9} {'NoMem':>7} {'Base':>7} {'MemAdv':>8}")
    print("  " + "-" * 105)

    all_results = {}

    for opp_name, OppClass in B2B_OPPONENTS.items():
        # SNHP with memory (repeated games)
        per_round_sums = [0.0] * n_rounds
        for rep in range(n_reps):
            utils, deals = run_repeated_matchup(
                SNHPAgent, OppClass, seller_ufun, buyer_ufun,
                issues, n_steps, n_rounds, batna, persist_memory=True
            )
            for r in range(n_rounds):
                per_round_sums[r] += utils[r]
        
        per_round_avg = [s / n_reps for s in per_round_sums]

        # SNHP without memory (single-shot comparison)
        nomem_sums = [0.0] * n_rounds
        for rep in range(n_reps):
            utils, deals = run_repeated_matchup(
                SNHPAgent, OppClass, seller_ufun, buyer_ufun,
                issues, n_steps, n_rounds, batna, persist_memory=False
            )
            for r in range(n_rounds):
                nomem_sums[r] += utils[r]
        nomem_avg = statistics.mean([s / n_reps for s in nomem_sums])

        # Aspiration baseline
        base_sums = [0.0] * n_rounds
        for rep in range(n_reps):
            utils, deals = run_repeated_matchup(
                AspirationNegotiator, OppClass, seller_ufun, buyer_ufun,
                issues, n_steps, n_rounds, batna, persist_memory=False
            )
            for r in range(n_rounds):
                base_sums[r] += utils[r]
        base_avg = statistics.mean([s / n_reps for s in base_sums])

        delta = per_round_avg[-1] - per_round_avg[0]
        mem_advantage = statistics.mean(per_round_avg) - nomem_avg
        
        r_vals = " ".join(f"{v:>7.4f}" for v in per_round_avg)
        icon = "📈" if delta > 0.01 else ("📉" if delta < -0.01 else "➖")
        
        print(f"  {opp_name:<22} {r_vals} {delta:>+9.4f} "
              f"{nomem_avg:>7.4f} {base_avg:>7.4f} {mem_advantage:>+8.4f} {icon}")

        all_results[opp_name] = {
            "per_round": per_round_avg,
            "nomem": nomem_avg,
            "base": base_avg,
            "learning": delta,
            "mem_advantage": mem_advantage,
        }

    # ─── Summary ──────────────────────────────────────

    print("\n" + "=" * 115)
    print("  SUMMARY")
    print("=" * 115)

    learners = sum(1 for r in all_results.values() if r["learning"] > 0.01)
    mem_winners = sum(1 for r in all_results.values() if r["mem_advantage"] > 0.005)
    base_winners = sum(1 for r in all_results.values() 
                       if statistics.mean(r["per_round"]) > r["base"] + 0.005)
    
    total = len(B2B_OPPONENTS)
    print(f"  Agents showing learning (R5 > R1 + 0.01): {learners}/{total}")
    print(f"  Memory advantage over no-memory SNHP:     {mem_winners}/{total}")
    print(f"  SNHP beats Aspiration baseline:            {base_winners}/{total}")

    # ─── Cross-Market Condition Table ──────────────────

    print(f"\n  Cross-Market: SNHP (avg over {n_rounds} rounds) vs Aspiration Baseline")
    print(f"\n  {'Opponent':<22} {'SoleUrg':>8} {'Typical':>8} {'Commodity':>8} "
          f"{'Overall':>9} {'Base':>8} {'Verdict':>10}")
    print("  " + "-" * 85)

    for opp_name, OppClass in B2B_OPPONENTS.items():
        cross_snhp = []
        cross_base = []
        
        for cn, c in MARKET_CONDITIONS.items():
            b = compute_batna(c["pool"], c["days"])
            
            # SNHP with memory
            utils_total = []
            for rep in range(n_reps):
                utils, _ = run_repeated_matchup(
                    SNHPAgent, OppClass, seller_ufun, buyer_ufun,
                    issues, n_steps, n_rounds, b, persist_memory=True
                )
                utils_total.extend(utils)
            cross_snhp.append(statistics.mean(utils_total))
            
            # Baseline
            utils_total = []
            for rep in range(n_reps):
                utils, _ = run_repeated_matchup(
                    AspirationNegotiator, OppClass, seller_ufun, buyer_ufun,
                    issues, n_steps, n_rounds, b, persist_memory=False
                )
                utils_total.extend(utils)
            cross_base.append(statistics.mean(utils_total))

        avg_s = statistics.mean(cross_snhp)
        avg_b = statistics.mean(cross_base)
        delta = avg_s - avg_b
        verdict = "✅ WIN" if delta > 0.005 else ("➖ TIE" if abs(delta) <= 0.005 else "❌ LOSE")
        
        vals = " ".join(f"{v:>8.4f}" for v in cross_snhp)
        print(f"  {opp_name:<22} {vals} {avg_s:>9.4f} {avg_b:>8.4f} {verdict:>10}")

    wins = sum(1 for opp_name in B2B_OPPONENTS 
               if all_results[opp_name].get("cross_win", False))
    
    return all_results


if __name__ == "__main__":
    run_b2b_benchmark(n_rounds=5, n_reps=10, n_steps=10)
