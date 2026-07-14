"""
BOA Diagnostic: Isolate which component (Bidding, Opponent-model, Acceptance) is broken.

Strategy:
  1. Run SNHP with its own Bidding + Acceptance → baseline (current perf)
  2. Run SNHP-Bidding + Oracle-Acceptance → "always accept ≥ rv+0.02" 
     → If this wins, the ACCEPTANCE component is the bottleneck.
  3. Run Oracle-Bidding + SNHP-Acceptance → "always propose at 0.51"
     → If this wins, the BIDDING component is the bottleneck.
  4. Run SNHP-Bidding + Split-matching-Acceptance → accept like SplitTheDiff
     → We clone the best simple bot's accept threshold onto SNHP proposals.

This tells us exactly where the intelligence debt lives.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import statistics
import numpy as np
from multiprocessing import Pool, cpu_count
from negmas import make_issue, SAOMechanism
from negmas.sao import SAONegotiator, SAOState, ResponseType
from negmas.outcomes import Outcome
from typing import Optional, List

# Import our agent and the opponents
import negmas_agent
from negmas_agent import SNHPAgent, CrossSessionMemory
from b2b_opponents import B2B_OPPONENTS, B2BBase
from b2b_round_robin import (
    create_issues, create_ufuns, play_matchup,
    N_ROUNDS, BATNA_CENTER, bootstrap_ci
)

N_DIAG_ROUNDS = 10  # Per matchup


# ═══════════════════════════════════════════════════
#  VARIANT AGENTS: test each BOA component in isolation
# ═══════════════════════════════════════════════════

class SNHP_OracleAccept(SNHPAgent):
    """SNHP Bidding + trivially aggressive acceptance.
    Accepts anything >= rv + 0.02, or >= 0.42, whichever is higher.
    Like PrincipledNegotiator's acceptance (the tournament leader).
    """
    def respond(self, state, offer):
        self._ensure_initialized()
        if self.ufun is None:
            return ResponseType.REJECT_OFFER
        
        # Still observe for opponent modeling (keeps bidding informed)
        self.opponent_model.observe(offer, state.relative_time)
        
        my_utility = self.ufun(offer)
        if my_utility is None:
            return ResponseType.REJECT_OFFER
        
        t = state.relative_time
        rv = getattr(self.ufun, 'reserved_value', None)
        if rv is None or rv == float('-inf'):
            rv = 0.0
        
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        if total_steps <= 15:
            # Match Principled's acceptance: simple, accommodating
            if my_utility >= 0.52:
                return ResponseType.ACCEPT_OFFER
            if t > 0.50 and my_utility >= 0.47:
                return ResponseType.ACCEPT_OFFER
            if t > 0.80 and my_utility >= max(rv + 0.02, 0.42):
                return ResponseType.ACCEPT_OFFER
            return ResponseType.REJECT_OFFER
        else:
            # ANAC mode: defer to parent
            return super().respond(state, offer)


class SNHP_OracleBid(SNHPAgent):
    """Oracle Bidding (always propose at 0.51) + SNHP acceptance.
    If this outperforms full SNHP, the bidding is the problem.
    """
    def propose(self, state):
        self._ensure_initialized()
        if self.ufun is None or self._my_best is None:
            return self._my_best
        
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        if total_steps <= 15:
            # Simple proposal: find outcome nearest to 0.51 utility
            target = 0.51
            offer = self._find_pareto_outcome(target)
            
            if offer:
                self._my_offers.append(offer)
                u = self.ufun(offer)
                u_val = float(u) if u is not None else target
                self._my_utilities.append(u_val)
                self._last_target_utility = u_val
                self.opponent_model.record_our_offer(offer)
            return offer or self._my_best
        else:
            return super().propose(state)


class SNHP_BothOracle(SNHPAgent):
    """Oracle Bidding + Oracle Acceptance.
    This is the theoretical ceiling for SNHP given its logrolling engine.
    Proposes at 0.55→0.47 linearly (like Principled), accepts like Principled.
    Uses SNHP's Pareto-aware outcome selection for proposals.
    """
    def propose(self, state):
        self._ensure_initialized()
        if self.ufun is None or self._my_best is None:
            return self._my_best
        
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        t = state.relative_time
        
        if total_steps <= 15:
            # Observe opponent for logrolling intel
            # Opponent model is updated automatically via respond() calls
            
            # Principled-style linear concession
            if t < 0.50:
                target = 0.65 - 0.10 * (t / 0.50)  # 0.65 → 0.55
            else:
                target = 0.55 - 0.08 * ((t - 0.50) / 0.50)  # 0.55 → 0.47
            target = max(0.45, target)
            
            # Use SNHP's Pareto-aware outcome selection (our edge)
            offer = self._find_pareto_outcome(target)
            
            if offer:
                self._my_offers.append(offer)
                u = self.ufun(offer)
                u_val = float(u) if u is not None else target
                self._my_utilities.append(u_val)
                self._last_target_utility = u_val
                self.opponent_model.record_our_offer(offer)
            return offer or self._my_best
        else:
            return super().propose(state)
    
    def respond(self, state, offer):
        self._ensure_initialized()
        if self.ufun is None:
            return ResponseType.REJECT_OFFER
        
        self.opponent_model.observe(offer, state.relative_time)
        
        my_utility = self.ufun(offer)
        if my_utility is None:
            return ResponseType.REJECT_OFFER
        
        t = state.relative_time
        rv = getattr(self.ufun, 'reserved_value', None)
        if rv is None or rv == float('-inf'):
            rv = 0.0
        
        total_steps = getattr(self.nmi, 'n_steps', 100) or 100
        if total_steps <= 15:
            if my_utility >= 0.52:
                return ResponseType.ACCEPT_OFFER
            if t > 0.50 and my_utility >= 0.47:
                return ResponseType.ACCEPT_OFFER
            if t > 0.80 and my_utility >= max(rv + 0.02, 0.42):
                return ResponseType.ACCEPT_OFFER
            return ResponseType.REJECT_OFFER
        else:
            return super().respond(state, offer)


# ═══════════════════════════════════════════════════
#  DIAGNOSTIC RUNNER
# ═══════════════════════════════════════════════════

def _run_variant_vs_opponents(args):
    """Run a single variant against all opponents. Returns dict of results."""
    variant_name, variant_cls, n_rounds = args
    
    results = {}
    for opp_name, opp_cls in B2B_OPPONENTS.items():
        issues = create_issues()
        ufun_a, ufun_b = create_ufuns(issues, 10)
        
        negmas_agent._global_memory = CrossSessionMemory()
        
        util_a, util_b, dr = play_matchup(
            variant_cls, opp_cls, ufun_a, ufun_b, issues,
            10, n_rounds, BATNA_CENTER,
            a_uses_memory=False, b_uses_memory=False,
        )
        results[opp_name] = (util_a, util_b, dr)
    
    avg_util = statistics.mean(r[0] for r in results.values())
    avg_deal = statistics.mean(r[2] for r in results.values())
    return variant_name, avg_util, avg_deal, results


def run_boa_diagnostic():
    """Run all 4 variants and compare."""
    
    variants = {
        "SNHP (baseline)": SNHPAgent,
        "SNHP-Bid + Oracle-Accept": SNHP_OracleAccept,
        "Oracle-Bid + SNHP-Accept": SNHP_OracleBid,
        "Oracle-Bid + Oracle-Accept": SNHP_BothOracle,
    }
    
    n_cores = min(cpu_count(), 14)
    print(f"\n{'='*80}")
    print(f"  BOA COMPONENT DIAGNOSTIC — Which component is broken?")
    print(f"  Testing 4 variants × {len(B2B_OPPONENTS)} opponents × {N_DIAG_ROUNDS} rounds")
    print(f"  Workers: {n_cores} cores (parallel)")
    print(f"{'='*80}\n")
    
    tasks = [(name, cls, N_DIAG_ROUNDS) for name, cls in variants.items()]
    
    with Pool(n_cores) as pool:
        raw_results = pool.map(_run_variant_vs_opponents, tasks)
    
    # Display results
    print(f"\n{'='*80}")
    print(f"  RESULTS: Average across all {len(B2B_OPPONENTS)} opponents")
    print(f"{'='*80}\n")
    print(f"  {'Variant':<35} {'Avg Util':>10} {'Avg Deal%':>10} {'Δ vs Base':>10}")
    print(f"  {'-'*65}")
    
    baseline_util = None
    all_results = {}
    for name, avg_util, avg_deal, details in raw_results:
        if baseline_util is None:
            baseline_util = avg_util
        delta = avg_util - baseline_util
        delta_str = f"+{delta:.4f}" if delta >= 0 else f"{delta:.4f}"
        print(f"  {name:<35} {avg_util:>10.4f} {avg_deal:>9.0%} {delta_str:>10}")
        all_results[name] = (avg_util, avg_deal, details)
    
    # Component attribution
    print(f"\n{'='*80}")
    print(f"  COMPONENT ATTRIBUTION")
    print(f"{'='*80}\n")
    
    base = all_results["SNHP (baseline)"][0]
    oracle_a = all_results["SNHP-Bid + Oracle-Accept"][0]
    oracle_b = all_results["Oracle-Bid + SNHP-Accept"][0]
    both = all_results["Oracle-Bid + Oracle-Accept"][0]
    
    accept_impact = oracle_a - base
    bid_impact = oracle_b - base
    
    print(f"  Acceptance component impact:  {accept_impact:+.4f} utility")
    print(f"  Bidding component impact:     {bid_impact:+.4f} utility")
    print(f"  Both components impact:       {both - base:+.4f} utility")
    
    if accept_impact > bid_impact and accept_impact > 0.01:
        print(f"\n  ⚡ VERDICT: ACCEPTANCE is the primary bottleneck.")
        print(f"     SNHP's acceptance logic is costing {accept_impact:.4f} utility.")
        print(f"     Fix: lower acceptance thresholds to match Principled/SplitTheDiff.")
    elif bid_impact > accept_impact and bid_impact > 0.01:
        print(f"\n  ⚡ VERDICT: BIDDING is the primary bottleneck.")
        print(f"     SNHP's proposal logic is costing {bid_impact:.4f} utility.")
        print(f"     Fix: simplify proposals or improve logrolling quality.")
    elif both - base > 0.02:
        print(f"\n  ⚡ VERDICT: BOTH components contribute to the gap.")
        print(f"     Need to fix both bidding and acceptance.")
    else:
        print(f"\n  ✅ SNHP's BOA components are working correctly.")
        print(f"     The gap is within noise (Δ < 0.02).")
    
    # Per-opponent deep dive for the best variant
    best_variant = max(all_results.items(), key=lambda x: x[1][0])
    print(f"\n{'='*80}")
    print(f"  BEST VARIANT: {best_variant[0]} (avg={best_variant[1][0]:.4f})")
    print(f"  Per-opponent breakdown:")
    print(f"{'='*80}\n")
    
    baseline_details = all_results["SNHP (baseline)"][2]
    best_details = best_variant[1][2]
    
    print(f"  {'Opponent':<25} {'Base':>8} {'Best':>8} {'Δ':>8} {'Base DR':>8} {'Best DR':>8}")
    print(f"  {'-'*73}")
    for opp in sorted(baseline_details.keys()):
        bu, _, bdr = baseline_details[opp]
        vu, _, vdr = best_details[opp]
        delta = vu - bu
        print(f"  {opp:<25} {bu:>8.4f} {vu:>8.4f} {delta:>+8.4f} {bdr:>7.0%} {vdr:>7.0%}")


if __name__ == "__main__":
    run_boa_diagnostic()
