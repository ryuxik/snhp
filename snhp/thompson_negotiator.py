"""
Von Neumann Adaptive Negotiator — Thompson Sampling over Seller Budge.

This module implements a rolling Bayesian update over the hedge exponent
(seller willingness-to-budge) using Thompson Sampling. Instead of a fixed
alpha=0.4 for all scenarios, the engine learns per-category optimal
aggressiveness from observed deal outcomes.

Theory:
    In Von Neumann's framework, a mixed strategy is a probability 
    distribution over pure strategies. Here, the "pure strategy" is a 
    specific hedge exponent alpha ∈ [0, 1], and the "mixed strategy" is 
    a Beta distribution over alpha that we sample from and update.

    Thompson Sampling (Bayesian bandit) is the optimal exploration-exploitation
    tradeoff for this setting: it samples from the posterior belief about 
    which alpha works best, then updates the belief based on the outcome.

    The "seller willingness to budge" is captured by the posterior:
    - High alpha → seller is aggressive, expects buyer to budge
    - Low alpha → seller budges toward midpoint, expects buyer to hold firm
    - The posterior concentration tracks how much data we have

Usage:
    negotiator = ThompsonNegotiator()
    
    # For each negotiation:
    bid = negotiator.compute_bid(scenario, mu, sigma)
    
    # After observing outcome (deal closed or not):
    negotiator.update(scenario.category, deal_closed=True, profit=42.0)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import sys, os
_snhp_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_snhp_dir, "core_math"))

from rubinstein import compute_discount_factor, rubinstein_equilibrium
from bayesian import acceptance_probability


# ═══════════════════════════════════════════════════
#  Bayesian Posterior over Seller Budge
# ═══════════════════════════════════════════════════

@dataclass
class BudgePosterior:
    """
    Beta posterior over the hedge exponent alpha.
    
    We discretize alpha into K arms (e.g., [0.1, 0.2, ..., 1.0])
    and maintain a Beta(a_k, b_k) posterior for each arm's "success rate",
    where success = deal closed with positive profit.
    
    Thompson Sampling: sample from each arm's posterior, pick the arm
    with the highest sample × expected profit.
    """
    # Arms = discretized alpha values
    arms: np.ndarray = field(default_factory=lambda: np.linspace(0.1, 1.0, 10))
    # Beta parameters: successes (deals closed) and failures (deals killed)
    alpha_params: np.ndarray = field(default_factory=lambda: np.ones(10) * 2.0)  # prior a=2
    beta_params: np.ndarray = field(default_factory=lambda: np.ones(10) * 2.0)   # prior b=2
    # Profit tracking per arm (for expected profit weighting)
    total_profit: np.ndarray = field(default_factory=lambda: np.zeros(10))
    arm_counts: np.ndarray = field(default_factory=lambda: np.zeros(10))
    # Total observations
    n_observations: int = 0
    
    def sample_alpha(self, rng: Optional[np.random.Generator] = None) -> Tuple[float, int]:
        """
        Thompson Sampling: sample deal rate from each arm's posterior,
        weight by expected profit, pick the best arm.
        
        Returns (alpha_value, arm_index) for downstream update.
        """
        if rng is None:
            rng = np.random.default_rng()
        
        # Sample deal rate from Beta posterior for each arm
        sampled_rates = np.array([
            rng.beta(self.alpha_params[i], self.beta_params[i])
            for i in range(len(self.arms))
        ])
        
        # Expected profit per arm (mean profit when deal closes)
        mean_profits = np.where(
            self.arm_counts > 0,
            self.total_profit / np.maximum(self.arm_counts, 1),
            1.0  # prior: assume $1 profit if no data
        )
        
        # Score = sampled_deal_rate × mean_profit_per_deal
        scores = sampled_rates * mean_profits
        
        best_arm = int(np.argmax(scores))
        return float(self.arms[best_arm]), best_arm
    
    def update(self, arm_index: int, deal_closed: bool, profit: float = 0.0):
        """Update posterior after observing a deal outcome."""
        if deal_closed:
            self.alpha_params[arm_index] += 1.0
            self.total_profit[arm_index] += profit
            self.arm_counts[arm_index] += 1.0
        else:
            self.beta_params[arm_index] += 1.0
        self.n_observations += 1
    
    def best_arm_greedy(self) -> Tuple[float, int]:
        """Exploitation-only: return the arm with highest posterior mean × profit."""
        posterior_means = self.alpha_params / (self.alpha_params + self.beta_params)
        mean_profits = np.where(
            self.arm_counts > 0,
            self.total_profit / np.maximum(self.arm_counts, 1),
            1.0
        )
        scores = posterior_means * mean_profits
        best = int(np.argmax(scores))
        return float(self.arms[best]), best
    
    def summary(self) -> Dict[str, Any]:
        """Human-readable summary of the posterior."""
        posterior_means = self.alpha_params / (self.alpha_params + self.beta_params)
        return {
            "arms": [round(float(a), 2) for a in self.arms],
            "deal_rates": [round(float(m), 3) for m in posterior_means],
            "arm_counts": [int(c) for c in self.arm_counts],
            "total_observations": self.n_observations,
            "best_arm": round(float(self.arms[np.argmax(posterior_means)]), 2),
        }


# ═══════════════════════════════════════════════════
#  Thompson Sampling Negotiator
# ═══════════════════════════════════════════════════

class ThompsonNegotiator:
    """
    Von Neumann Adaptive Negotiator with Thompson Sampling.
    
    Maintains a per-category BudgePosterior that learns the optimal
    hedge exponent (seller willingness-to-budge) from observed outcomes.
    
    In the first few negotiations per category, it explores different
    aggressiveness levels. As it observes deal outcomes, it converges
    to the optimal alpha for that market segment.
    
    Integration:
        This wraps the Von Neumann ZOPA-Rubinstein composite from the
        eval harness. The only parameter that varies is the hedge exponent
        alpha, which controls the blend between midpoint (safe) and
        Rubinstein (aggressive).
    """
    
    def __init__(self, seed: int = 42):
        self.posteriors: Dict[str, BudgePosterior] = defaultdict(BudgePosterior)
        self.rng = np.random.default_rng(seed)
        self._last_arm_index: Dict[str, int] = {}
        self._last_bid: Dict[str, float] = {}
    
    def compute_bid(
        self,
        seller_reservation: float,
        listing_price: float,
        mu: float,
        sigma: float,
        category: str = "default",
        seller_urgency: float = 0.3,
        buyer_urgency: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Compute a bid using Thompson Sampling over the hedge exponent.
        
        Returns dict with bid, alpha used, arm index (for update), and metadata.
        """
        zopa_width = listing_price - seller_reservation
        if zopa_width <= 0:
            return {
                "bid": seller_reservation * 1.01,
                "alpha": 0.0,
                "arm_index": 0,
                "strategy": "no_zopa",
            }
        
        # Rubinstein patience-based surplus split
        delta_seller = compute_discount_factor(seller_urgency, None, 0)
        delta_buyer = compute_discount_factor(buyer_urgency, None, 0)
        rub = rubinstein_equilibrium(delta_seller, delta_buyer, zopa_width)
        seller_share = rub["freelancer_share"]
        
        rubinstein_bid = seller_reservation + zopa_width * seller_share
        midpoint = (listing_price + seller_reservation) / 2
        
        # Thompson Sampling: sample alpha from posterior
        posterior = self.posteriors[category]
        sampled_alpha, arm_index = posterior.sample_alpha(self.rng)
        
        # Blend: alpha controls mix of midpoint (safe) vs Rubinstein (aggressive)
        bid = midpoint + (rubinstein_bid - midpoint) * sampled_alpha
        
        # Safety bounds
        bid = min(bid, listing_price * 0.95)
        bid = max(bid, seller_reservation * 1.01)
        
        # Cache for update
        self._last_arm_index[category] = arm_index
        self._last_bid[category] = bid
        
        return {
            "bid": round(float(bid), 2),
            "alpha": round(float(sampled_alpha), 3),
            "arm_index": arm_index,
            "rubinstein_bid": round(float(rubinstein_bid), 2),
            "midpoint": round(float(midpoint), 2),
            "seller_share": round(float(seller_share), 4),
            "strategy": "thompson_vn",
            "n_observations": posterior.n_observations,
        }
    
    def update(self, category: str, deal_closed: bool, profit: float = 0.0):
        """
        Update the posterior for a category after observing a deal outcome.
        Call this after compute_bid() with the actual result.
        """
        arm_index = self._last_arm_index.get(category, 0)
        self.posteriors[category].update(arm_index, deal_closed, profit)
    
    def get_category_summary(self, category: str) -> Dict[str, Any]:
        """Get the posterior summary for a category."""
        return self.posteriors[category].summary()
    
    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """Get posterior summaries for all categories."""
        return {cat: self.get_category_summary(cat) for cat in self.posteriors}


# ═══════════════════════════════════════════════════
#  Benchmark: Thompson vs Fixed Alpha
# ═══════════════════════════════════════════════════

def run_thompson_benchmark(n_scenarios: int = 5000, seed: int = 42):
    """
    Compare Thompson Sampling negotiator vs fixed-alpha strategies.
    
    Simulates sequential negotiation across categories, where Thompson
    learns from outcomes while fixed strategies don't adapt.
    """
    from eval_harness import generate_synthetic_scenarios
    from priors import fit_market_distribution
    import statistics
    
    scenarios = generate_synthetic_scenarios(n_scenarios)
    
    # Pre-fit distributions per category
    categories = set(s.category for s in scenarios)
    cat_dists = {}
    for cat in categories:
        dp = [s.actual_deal_price for s in scenarios 
              if s.category == cat and s.actual_deal_price and s.actual_deal_price > 0]
        if len(dp) < 10:
            dp = [s.actual_deal_price for s in scenarios 
                  if s.actual_deal_price and s.actual_deal_price > 0]
        dp = sorted(dp)
        n = len(dp)
        cat_dists[cat] = fit_market_distribution(
            dp[int(n*0.25)], dp[int(n*0.50)], dp[int(n*0.75)], dp[int(n*0.90)])
    
    # Shuffle scenarios to simulate sequential arrival
    rng = np.random.default_rng(seed)
    shuffled = list(scenarios)
    rng.shuffle(shuffled)
    
    # Thompson Sampling negotiator
    thompson = ThompsonNegotiator(seed=seed)
    
    # Track profits for each strategy
    thompson_profits = []
    fixed_04_profits = []
    midpoint_profits = []
    
    for s in shuffled:
        mu, sigma = cat_dists.get(s.category, (5.5, 0.8))
        
        # Thompson bid
        result = thompson.compute_bid(
            s.seller_reservation, s.listing_price, mu, sigma,
            category=s.category,
            seller_urgency=s.seller_urgency,
            buyer_urgency=s.buyer_urgency,
        )
        t_bid = result["bid"]
        t_deal = t_bid <= s.buyer_reservation
        t_profit = t_bid - s.seller_reservation if t_deal else 0.0
        thompson.update(s.category, t_deal, t_profit)
        thompson_profits.append(t_profit)
        
        # Fixed alpha=0.4 (our calibrated static strategy)
        zopa = s.listing_price - s.seller_reservation
        if zopa > 0:
            delta_s = compute_discount_factor(s.seller_urgency, None, 0)
            delta_b = compute_discount_factor(s.buyer_urgency, None, 0)
            rub = rubinstein_equilibrium(delta_s, delta_b, zopa)
            rub_bid = s.seller_reservation + zopa * rub['freelancer_share']
            mid = (s.listing_price + s.seller_reservation) / 2
            p_acc = acceptance_probability(rub_bid, mu, sigma)
            alpha = max(0.0, min(1.0, p_acc)) ** 0.4
            f_bid = mid + (rub_bid - mid) * alpha
            f_bid = min(f_bid, s.listing_price * 0.95)
            f_bid = max(f_bid, s.seller_reservation * 1.01)
        else:
            f_bid = s.seller_reservation * 1.01
        f_deal = f_bid <= s.buyer_reservation
        f_profit = f_bid - s.seller_reservation if f_deal else 0.0
        fixed_04_profits.append(f_profit)
        
        # Midpoint baseline
        m_bid = (s.listing_price + s.seller_reservation) / 2
        m_deal = m_bid <= s.buyer_reservation
        m_profit = m_bid - s.seller_reservation if m_deal else 0.0
        midpoint_profits.append(m_profit)
    
    # Results
    from scipy.stats import ttest_rel
    
    print("=" * 70)
    print("  THOMPSON SAMPLING vs FIXED STRATEGIES")
    print("=" * 70)
    print()
    
    strategies = [
        ("Thompson (adaptive)", thompson_profits),
        ("Fixed α=0.4 (static)", fixed_04_profits),
        ("Midpoint (baseline)", midpoint_profits),
    ]
    
    print("  Strategy                   Mean Profit  Deal Rate")
    print("  " + "-" * 50)
    for name, profits in strategies:
        mean_p = statistics.mean(profits)
        rate = sum(1 for p in profits if p > 0) / len(profits)
        print(f"  {name:<28s} ${mean_p:>10.2f}  {rate:>8.1%}")
    
    print()
    print("  PAIRED T-TESTS")
    print("  " + "-" * 50)
    
    # Thompson vs Midpoint
    t, p = ttest_rel(thompson_profits, midpoint_profits)
    sig = "✅ SIGNIFICANT" if p < 0.008333 else "❌ not significant"
    print(f"  Thompson vs Midpoint: t={t:.4f}  p={p:.6f}  {sig}")
    
    # Thompson vs Fixed
    t, p = ttest_rel(thompson_profits, fixed_04_profits)
    sig = "✅ SIGNIFICANT" if p < 0.008333 else "❌ not significant"
    print(f"  Thompson vs Fixed:    t={t:.4f}  p={p:.6f}  {sig}")
    
    # Fixed vs Midpoint (sanity check)
    t, p = ttest_rel(fixed_04_profits, midpoint_profits)
    sig = "✅ SIGNIFICANT" if p < 0.008333 else "❌ not significant"
    print(f"  Fixed vs Midpoint:    t={t:.4f}  p={p:.6f}  {sig}")
    
    print()
    print("  CATEGORY POSTERIORS (learned by Thompson)")
    print("  " + "-" * 50)
    for cat, summary in thompson.get_all_summaries().items():
        best = summary["best_arm"]
        n_obs = summary["total_observations"]
        print(f"  {cat:20s}: best_alpha={best:.2f}  observations={n_obs}")
    
    # Learning curve: show profit in windows of 500
    print()
    print("  LEARNING CURVE (Thompson profit in windows of 500)")
    print("  " + "-" * 50)
    window = 500
    for i in range(0, len(thompson_profits), window):
        chunk = thompson_profits[i:i+window]
        mid_chunk = midpoint_profits[i:i+window]
        t_mean = statistics.mean(chunk)
        m_mean = statistics.mean(mid_chunk)
        diff = t_mean - m_mean
        print(f"  Scenarios {i+1:>5}-{min(i+window, len(thompson_profits)):>5}: "
              f"Thompson=${t_mean:.2f}  Midpoint=${m_mean:.2f}  Δ={diff:>+.2f}")
    
    return thompson


if __name__ == "__main__":
    run_thompson_benchmark(n_scenarios=5000)
