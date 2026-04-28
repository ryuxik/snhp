"""
SNHP Statistical Benchmark — Rigorous Tournament with Confidence Intervals.

Von Neumann Standard: Every claim about ranking or improvement must be
backed by a statistical test. No more N=5 point estimates.

Features:
  - N=30 rounds per matchup (configurable)
  - Seed-controlled randomness for paired A/B comparisons
  - Bootstrap 95% CI on mean utility and rankings
  - Wilcoxon signed-rank tests for pairwise significance
  - Elo ratings for intransitive ranking
  - Decomposed metrics: deal rate, conditional utility, joint surplus
  - Exploitation resistance score (variance across opponent types)
  - --baseline flag for paired strategy comparisons

Usage:
  python statistical_benchmark.py                    # Full benchmark
  python statistical_benchmark.py --quick             # Quick mode (N=10)
  python statistical_benchmark.py --compare baseline  # Compare vs saved baseline
"""

from negmas.sao import SAOMechanism
from negmas.sao.negotiators import AspirationNegotiator
from negmas.outcomes import make_issue
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import IdentityFun, AffineFun
import numpy as np
import statistics
import json
import os
import sys
import math
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field, asdict

import negmas_agent
from negmas_agent import SNHPAgent, CrossSessionMemory
from b2b_opponents import B2B_OPPONENTS

# ─── Configuration ────────────────────────────────

N_ROUNDS = 30           # Rounds per matchup (30 → SE ≈ 0.02)
BOOTSTRAP_N = 1000      # Bootstrap resamples for CI
CONFIDENCE = 0.95       # Confidence level for intervals
MASTER_SEED = 42        # For reproducibility
ELO_K = 32              # Elo K-factor
ELO_INIT = 1500         # Starting Elo

# B2B Parameters (matching round_robin)
BATNA_CENTER = 0.40
BATNA_RANGE = 0.08
BATNA_NOISE = 0.10
MARKET_POWER_RANGE = 0.05
MUST_DEAL_BASE_PROB = 0.10
MUST_DEAL_ESCALATION = 0.15
WALKAWAY_REP_TAX = 0.02
RELATIONSHIP_PREMIUM = 0.03
WALKAWAY_ALT_PROB = 0.40

# ─── Data Structures ─────────────────────────────

@dataclass
class MatchResult:
    """Single round outcome."""
    deal: bool
    utility_a: float
    utility_b: float
    joint_surplus: float  # u_a + u_b if deal, else 0
    steps_taken: int
    
@dataclass
class MatchupStats:
    """Statistics for one A-vs-B matchup across all rounds."""
    player_a: str
    player_b: str
    n_rounds: int
    raw_utils_a: List[float] = field(default_factory=list)
    raw_utils_b: List[float] = field(default_factory=list)
    deals: List[bool] = field(default_factory=list)
    joint_surpluses: List[float] = field(default_factory=list)
    
    @property
    def mean_a(self) -> float:
        return statistics.mean(self.raw_utils_a) if self.raw_utils_a else 0
    
    @property
    def mean_b(self) -> float:
        return statistics.mean(self.raw_utils_b) if self.raw_utils_b else 0
    
    @property
    def deal_rate(self) -> float:
        return sum(self.deals) / max(len(self.deals), 1)
    
    @property
    def cond_util_a(self) -> float:
        """Utility conditional on deal being made."""
        deal_utils = [u for u, d in zip(self.raw_utils_a, self.deals) if d]
        return statistics.mean(deal_utils) if deal_utils else 0
    
    @property
    def mean_joint_surplus(self) -> float:
        return statistics.mean(self.joint_surpluses) if self.joint_surpluses else 0


@dataclass
class PlayerStats:
    """Aggregate stats for one player across all opponents."""
    name: str
    matchups: Dict[str, MatchupStats] = field(default_factory=dict)
    elo: float = ELO_INIT
    
    @property
    def all_utils(self) -> List[float]:
        return [u for m in self.matchups.values() for u in m.raw_utils_a]
    
    @property
    def mean_utility(self) -> float:
        utils = self.all_utils
        return statistics.mean(utils) if utils else 0
    
    @property
    def overall_deal_rate(self) -> float:
        all_deals = [d for m in self.matchups.values() for d in m.deals]
        return sum(all_deals) / max(len(all_deals), 1)
    
    @property
    def exploitation_resistance(self) -> float:
        """Low variance across opponents = hard to exploit."""
        per_opp = [m.mean_a for m in self.matchups.values()]
        return statistics.stdev(per_opp) if len(per_opp) > 1 else 0


# ─── Issue/Utility Setup ─────────────────────────

def create_issues():
    return [
        make_issue(name="price", values=50),
        make_issue(name="delivery", values=5),
        make_issue(name="warranty", values=4),
        make_issue(name="payment", values=3),
    ]


def create_ufuns(issues, n_steps=10, reserved_value=None):
    if reserved_value is None:
        reserved_value = BATNA_CENTER
    
    weights_a = {"price": 0.50, "delivery": 0.15, "warranty": 0.10, "payment": 0.25}
    weights_b = {"price": 0.20, "delivery": 0.30, "warranty": 0.40, "payment": 0.10}
    
    temp = SAOMechanism(issues=issues, n_steps=n_steps)
    iss = temp.outcome_space.issues

    ufun_a = LUFun(
        values={"price": IdentityFun(), "delivery": IdentityFun(),
                "warranty": AffineFun(slope=-1, bias=3),
                "payment": AffineFun(slope=-1, bias=2)},
        weights=weights_a, issues=iss,
    ).normalize()
    ufun_a.reserved_value = reserved_value

    ufun_b = LUFun(
        values={"price": AffineFun(slope=-1, bias=49),
                "delivery": AffineFun(slope=-1, bias=4),
                "warranty": IdentityFun(), "payment": IdentityFun()},
        weights=weights_b, issues=iss,
    ).normalize()
    ufun_b.reserved_value = reserved_value

    return ufun_a, ufun_b


# ─── Statistical Tools ───────────────────────────

def bootstrap_ci(data: List[float], n_boot: int = BOOTSTRAP_N, 
                 alpha: float = 1 - CONFIDENCE) -> Tuple[float, float, float]:
    """Bootstrap confidence interval. Returns (mean, lo, hi)."""
    if not data:
        return (0.0, 0.0, 0.0)
    
    rng = np.random.RandomState(MASTER_SEED)
    arr = np.array(data)
    means = np.array([
        np.mean(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    
    lo = np.percentile(means, 100 * alpha / 2)
    hi = np.percentile(means, 100 * (1 - alpha / 2))
    return (float(np.mean(arr)), float(lo), float(hi))


def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    """
    Paired Wilcoxon signed-rank test.
    Returns (test_statistic, approximate_p_value).
    Uses normal approximation for N > 20.
    """
    n = min(len(x), len(y))
    if n < 5:
        return (0.0, 1.0)
    
    diffs = [x[i] - y[i] for i in range(n)]
    # Remove zeros
    diffs = [d for d in diffs if abs(d) > 1e-10]
    n = len(diffs)
    if n < 5:
        return (0.0, 1.0)
    
    # Rank absolute differences
    abs_diffs = [(abs(d), i) for i, d in enumerate(diffs)]
    abs_diffs.sort()
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(abs_diffs[j][0] - abs_diffs[i][0]) < 1e-10:
            j += 1
        avg_rank = (i + j + 1) / 2  # Average rank for ties
        for k in range(i, j):
            ranks[abs_diffs[k][1]] = avg_rank
        i = j
    
    # W+ = sum of ranks for positive differences
    w_plus = sum(ranks[i] for i in range(n) if diffs[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if diffs[i] < 0)
    
    W = min(w_plus, w_minus)
    
    # Normal approximation
    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma < 1e-10:
        return (W, 1.0)
    
    z = (W - mu) / sigma
    # Two-tailed p-value using normal approximation
    p = 2 * (1 - _norm_cdf(abs(z)))
    
    return (float(W), float(p))


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def update_elo(rating_a: float, rating_b: float, score_a: float, 
               k: float = ELO_K) -> Tuple[float, float]:
    """Update Elo ratings. score_a: 1=win, 0.5=draw, 0=loss."""
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a
    new_a = rating_a + k * (score_a - expected_a)
    new_b = rating_b + k * ((1 - score_a) - expected_b)
    return new_a, new_b


# ─── Core Matchup Runner ─────────────────────────

def play_single_round(ClassA, ClassB, ufun_a, ufun_b, issues,
                      rng: np.random.RandomState, round_idx: int,
                      memory_a=None, memory_b=None,
                      a_uses_memory=False, b_uses_memory=False) -> MatchResult:
    """Play one round with controlled randomness."""
    
    # Deterministic randomness from the provided RNG
    n_steps = rng.randint(7, 14)
    round_batna = rng.uniform(BATNA_CENTER - BATNA_RANGE, BATNA_CENTER + BATNA_RANGE)
    power_a = rng.uniform(-MARKET_POWER_RANGE, MARKET_POWER_RANGE)
    power_b = rng.uniform(-MARKET_POWER_RANGE, MARKET_POWER_RANGE)
    noise_a = rng.uniform(1.0 - BATNA_NOISE, 1.0 + BATNA_NOISE)
    noise_b = rng.uniform(1.0 - BATNA_NOISE, 1.0 + BATNA_NOISE)
    
    perceived_batna_a = round_batna * noise_a
    perceived_batna_b = round_batna * noise_b
    
    round_ufun_a, round_ufun_b = create_ufuns(issues, n_steps, perceived_batna_a)
    round_ufun_b.reserved_value = perceived_batna_b
    
    if a_uses_memory and memory_a:
        negmas_agent._global_memory = memory_a
    else:
        negmas_agent._global_memory = CrossSessionMemory()
    
    mech = SAOMechanism(issues=issues, n_steps=n_steps)
    agent_a = ClassA(name=f"a_r{round_idx}")
    agent_b = ClassB(name=f"b_r{round_idx}")
    mech.add(agent_a, ufun=round_ufun_a)
    mech.add(agent_b, ufun=round_ufun_b)
    
    result = mech.run()
    
    if result.agreement is not None:
        ua = float(round_ufun_a(result.agreement) or 0) + power_a
        ub = float(round_ufun_b(result.agreement) or 0) + power_b
        ua = max(0, ua)
        ub = max(0, ub)
        return MatchResult(
            deal=True, utility_a=ua, utility_b=ub,
            joint_surplus=ua + ub, steps_taken=n_steps
        )
    else:
        return MatchResult(
            deal=False, utility_a=round_batna, utility_b=round_batna,
            joint_surplus=0.0, steps_taken=n_steps
        )


def play_matchup(ClassA, ClassB, issues, n_rounds: int, seed: int,
                 a_uses_memory=False, b_uses_memory=False) -> MatchupStats:
    """Play a full matchup with seed-controlled randomness."""
    rng = np.random.RandomState(seed)
    ufun_a, ufun_b = create_ufuns(issues)
    
    memory_a = CrossSessionMemory() if a_uses_memory else None
    memory_b = CrossSessionMemory() if b_uses_memory else None
    
    stats = MatchupStats(
        player_a=ClassA.__name__ if hasattr(ClassA, '__name__') else str(ClassA),
        player_b=ClassB.__name__ if hasattr(ClassB, '__name__') else str(ClassB),
        n_rounds=n_rounds,
    )
    
    for r in range(n_rounds):
        result = play_single_round(
            ClassA, ClassB, ufun_a, ufun_b, issues, rng, r,
            memory_a, memory_b, a_uses_memory, b_uses_memory
        )
        stats.raw_utils_a.append(result.utility_a)
        stats.raw_utils_b.append(result.utility_b)
        stats.deals.append(result.deal)
        stats.joint_surpluses.append(result.joint_surplus)
    
    return stats


# ─── Tournament Runner ───────────────────────────

def run_statistical_tournament(n_rounds: int = N_ROUNDS, 
                                save_baseline: bool = False,
                                compare_baseline: Optional[str] = None):
    """
    Full statistical tournament with confidence intervals and significance tests.
    """
    issues = create_issues()
    
    # Build roster
    all_players = {}
    for name, cls in B2B_OPPONENTS.items():
        all_players[name] = {"class": cls, "uses_memory": False}
    all_players["SNHP"] = {"class": SNHPAgent, "uses_memory": True}
    all_players["Aspiration"] = {"class": AspirationNegotiator, "uses_memory": False}
    
    player_names = list(all_players.keys())
    n_players = len(player_names)
    
    # Initialize stats
    player_stats: Dict[str, PlayerStats] = {
        name: PlayerStats(name=name) for name in player_names
    }
    
    print("=" * 115)
    print(f"  SNHP STATISTICAL BENCHMARK — Von Neumann Standard")
    print(f"  {n_players} players × {n_rounds} rounds/matchup × {BOOTSTRAP_N} bootstrap resamples")
    print(f"  Master seed: {MASTER_SEED} | CI: {CONFIDENCE:.0%} | Elo K={ELO_K}")
    print("=" * 115)
    
    total = n_players * (n_players - 1)
    done = 0
    matchup_seed = MASTER_SEED
    
    pairwise = {}
    
    for name_a in player_names:
        for name_b in player_names:
            if name_a == name_b:
                continue
            
            pa = all_players[name_a]
            pb = all_players[name_b]
            
            matchup_seed += 1  # Deterministic, reproducible seed per matchup
            
            stats = play_matchup(
                pa["class"], pb["class"], issues, n_rounds, matchup_seed,
                a_uses_memory=pa["uses_memory"],
                b_uses_memory=pb["uses_memory"],
            )
            
            player_stats[name_a].matchups[name_b] = stats
            pairwise[(name_a, name_b)] = stats
            
            # Update Elo
            if stats.mean_a > stats.mean_b + 0.005:
                score = 1.0
            elif abs(stats.mean_a - stats.mean_b) <= 0.005:
                score = 0.5
            else:
                score = 0.0
            
            player_stats[name_a].elo, player_stats[name_b].elo = update_elo(
                player_stats[name_a].elo, player_stats[name_b].elo, score
            )
            
            done += 1
            if done % 20 == 0:
                print(f"  ... {done}/{total} matchups complete")
    
    # ─── Rankings with CI ─────────────────────────
    
    print("\n" + "=" * 115)
    print("  RANKINGS WITH CONFIDENCE INTERVALS")
    print("=" * 115)
    
    ranking_data = []
    for name in player_names:
        ps = player_stats[name]
        mean, ci_lo, ci_hi = bootstrap_ci(ps.all_utils)
        ranking_data.append({
            "name": name,
            "mean": mean,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "elo": ps.elo,
            "deal_rate": ps.overall_deal_rate,
            "exploit_resist": ps.exploitation_resistance,
        })
    
    ranking_data.sort(key=lambda x: x["mean"], reverse=True)
    
    # Bootstrap rank distribution
    all_data = {name: player_stats[name].all_utils for name in player_names}
    rng = np.random.RandomState(MASTER_SEED + 999)
    rank_counts = {name: [] for name in player_names}
    
    for _ in range(BOOTSTRAP_N):
        boot_means = {}
        for name, utils in all_data.items():
            if utils:
                idx = rng.randint(0, len(utils), size=len(utils))
                boot_means[name] = np.mean([utils[i] for i in idx])
            else:
                boot_means[name] = 0
        sorted_names = sorted(boot_means.keys(), key=lambda n: boot_means[n], reverse=True)
        for rank, name in enumerate(sorted_names, 1):
            rank_counts[name].append(rank)
    
    print(f"\n  {'#':>3} {'Player':<22} {'Mean':>8} {'95% CI':>16} {'Rank CI':>12} "
          f"{'Elo':>6} {'Deal%':>7} {'ExplRes':>8}")
    print("  " + "-" * 105)
    
    for rank, r in enumerate(ranking_data, 1):
        rank_lo = int(np.percentile(rank_counts[r["name"]], 2.5))
        rank_hi = int(np.percentile(rank_counts[r["name"]], 97.5))
        marker = " ⭐" if r["name"] == "SNHP" else ""
        print(f"  {rank:>3} {r['name']:<22} {r['mean']:>8.4f} "
              f"[{r['ci_lo']:.4f}, {r['ci_hi']:.4f}] "
              f"[{rank_lo:>2}-{rank_hi:>2}] "
              f"{r['elo']:>6.0f} {r['deal_rate']:>6.0%} "
              f"{r['exploit_resist']:>8.4f}{marker}")
    
    # ─── SNHP Matchup Details ─────────────────────
    
    print(f"\n  SNHP PAIRWISE ANALYSIS (N={n_rounds} per matchup)")
    print(f"  {'Opponent':<22} {'SNHP':>8} {'Opp':>8} {'Deal%':>7} "
          f"{'p-value':>9} {'Signif':>8}")
    print("  " + "-" * 75)
    
    snhp_utils_all = []
    opp_utils_all = []
    
    for opp in player_names:
        if opp == "SNHP":
            continue
        
        if ("SNHP", opp) in pairwise:
            ms = pairwise[("SNHP", opp)]
            
            # Get opponent's utility when playing against SNHP
            opp_ms = pairwise.get((opp, "SNHP"))
            opp_against_snhp = opp_ms.mean_a if opp_ms else 0
            
            # Wilcoxon test: SNHP utils vs opponent's utils against SNHP
            _, p_val = wilcoxon_signed_rank(ms.raw_utils_a, 
                                             opp_ms.raw_utils_a if opp_ms else [])
            
            sig = "***" if p_val < 0.001 else ("**" if p_val < 0.01 else 
                  ("*" if p_val < 0.05 else "n.s."))
            result = "✅" if ms.mean_a > opp_against_snhp + 0.005 else (
                     "➖" if abs(ms.mean_a - opp_against_snhp) <= 0.005 else "❌")
            
            print(f"  {opp:<22} {ms.mean_a:>8.4f} {opp_against_snhp:>8.4f} "
                  f"{ms.deal_rate:>6.0%} {p_val:>9.4f} {sig:>5} {result}")
    
    # ─── Significance Summary ─────────────────────
    
    print(f"\n  SIGNIFICANCE TESTS (Wilcoxon signed-rank, α=0.05)")
    print(f"  {'Comparison':<40} {'Diff':>8} {'p-value':>9} {'Result':>10}")
    print("  " + "-" * 70)
    
    # SNHP vs each key benchmark
    for benchmark in ["Aspiration", "Split-the-Diff", "Fair Demand"]:
        if benchmark in player_stats and "SNHP" in player_stats:
            snhp_u = player_stats["SNHP"].all_utils
            bench_u = player_stats[benchmark].all_utils
            n = min(len(snhp_u), len(bench_u))
            if n > 0:
                diff = statistics.mean(snhp_u[:n]) - statistics.mean(bench_u[:n])
                _, p = wilcoxon_signed_rank(snhp_u[:n], bench_u[:n])
                result = "SNHP BETTER" if diff > 0 and p < 0.05 else (
                         "SNHP WORSE" if diff < 0 and p < 0.05 else "NO DIFF")
                print(f"  {'SNHP vs ' + benchmark:<40} {diff:>+8.4f} {p:>9.4f} {result:>10}")
    
    # ─── Save Results ─────────────────────────────
    
    results = {
        "config": {
            "n_rounds": n_rounds,
            "master_seed": MASTER_SEED,
            "n_players": n_players,
        },
        "rankings": ranking_data,
        "snhp_detail": {
            opp: {
                "mean_a": ms.mean_a,
                "mean_b": ms.mean_b,
                "deal_rate": ms.deal_rate,
            }
            for opp, ms in player_stats.get("SNHP", PlayerStats("SNHP")).matchups.items()
        }
    }
    
    if save_baseline:
        path = os.path.join(os.path.dirname(__file__), "baseline_results.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n  ✅ Baseline saved to {path}")
    
    # ─── Baseline Comparison ──────────────────────
    
    if compare_baseline:
        path = os.path.join(os.path.dirname(__file__), f"{compare_baseline}_results.json")
        if os.path.exists(path):
            with open(path) as f:
                baseline = json.load(f)
            
            print(f"\n  BASELINE COMPARISON (vs {compare_baseline})")
            print(f"  {'Metric':<30} {'Current':>10} {'Baseline':>10} {'Δ':>10}")
            print("  " + "-" * 65)
            
            curr_snhp = next((r for r in ranking_data if r["name"] == "SNHP"), None)
            base_snhp = next((r for r in baseline["rankings"] if r["name"] == "SNHP"), None)
            
            if curr_snhp and base_snhp:
                for metric in ["mean", "deal_rate", "elo"]:
                    c = curr_snhp[metric]
                    b = base_snhp[metric]
                    fmt = ".4f" if metric == "mean" else (".0%" if metric == "deal_rate" else ".0f")
                    print(f"  {metric:<30} {c:>10{fmt}} {b:>10{fmt}} {c-b:>+10{fmt}}")
    
    snhp_rank = next(i for i, r in enumerate(ranking_data, 1) if r["name"] == "SNHP")
    rank_lo = int(np.percentile(rank_counts["SNHP"], 2.5))
    rank_hi = int(np.percentile(rank_counts["SNHP"], 97.5))
    
    print(f"\n  ═══════════════════════════════════════════════")
    print(f"  SNHP RANK: #{snhp_rank} [{rank_lo}-{rank_hi}] / {n_players}")
    print(f"  ═══════════════════════════════════════════════")
    
    return results


if __name__ == "__main__":
    n_rounds = N_ROUNDS
    save = False
    compare = None
    
    if "--quick" in sys.argv:
        n_rounds = 10
        print("  [Quick mode: N=10 rounds per matchup]")
    if "--save-baseline" in sys.argv:
        save = True
    if "--compare" in sys.argv:
        idx = sys.argv.index("--compare")
        if idx + 1 < len(sys.argv):
            compare = sys.argv[idx + 1]
    
    run_statistical_tournament(n_rounds=n_rounds, save_baseline=save, 
                                compare_baseline=compare)
