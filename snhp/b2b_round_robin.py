"""
All-vs-All B2B Round Robin Tournament.

Every agent plays every other agent in a symmetric tournament.
Reveals dominant strategies, exploitable weaknesses, and Nash insights.

Players: 14 B2B archetypes + SNHP + Aspiration baseline = 16 agents.
Each matchup: 5 repeated games, Balanced scenario, Typical market.

Realism features:
- Random game length U(7,13) — defeats backward induction
- Must-deal rounds (30%) — simulates urgent procurement
- Walk-away reputation tax — cross-match deal-rate penalty
- Variable BATNA U(0.32,0.48) — shifting outside options
- BATNA noise ±10% — agents don't know their exact reservation
- Relationship premium (+0.03) — repeat deal bonus
- Market position variance (±0.05) — random power shifts

Output: Full ranking table + pairwise matrix.
"""

from negmas.sao import SAOMechanism
from negmas.sao.negotiators import AspirationNegotiator
from negmas.outcomes import make_issue
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import IdentityFun, AffineFun
import numpy as np
import statistics
import math
import sys
import json
import os
import time
import multiprocessing
from typing import Dict, List, Tuple, Type
from collections import defaultdict

import negmas_agent
from negmas_agent import SNHPAgent, CrossSessionMemory
from b2b_opponents import B2B_OPPONENTS, B2BBase


# ─── Setup ────────────────────────────────────────

BATNA_CENTER = 0.40   # Center of BATNA distribution
BATNA_RANGE = 0.08    # ±0.08 → U(0.32, 0.48)
BATNA_NOISE = 0.10    # ±10% noise on perceived reservation value
N_ROUNDS = 20            # ↑ from 5: reduces SE by ~2x for reliable rankings
N_STEPS = 10          # Nominal; actual steps randomized per round
RANDOMIZE_STEPS = True
N_WORKERS = min(14, multiprocessing.cpu_count())  # M4 Mac Pro: 14 cores

# Realism knobs
MUST_DEAL_BASE_PROB = 0.10    # Base forced-walkaway probability (round 1)
MUST_DEAL_ESCALATION = 0.15   # Each no-deal round adds this to the probability
WALKAWAY_REP_TAX = 0.02       # Each walk-away degrades future BATNA
RELATIONSHIP_PREMIUM = 0.03   # Bonus for repeat deals with same partner
MARKET_POWER_RANGE = 0.05     # ±0.05 random power modifier per round
STEP_SHRINK_PER_NODEAL = 1    # Game shortens by 1 step per consecutive no-deal
WALKAWAY_ALT_PROB = 0.40      # Prob of getting alternative deal after walk-away
RANDOMIZE_WEIGHTS = True      # Dirichlet-randomize ufun weights per round

# ─── ASYMMETRIC MARKET CONDITIONS ──────────────────
# Multiplier on walk-away pressure for each side.
# seller_pressure=1.5, buyer_pressure=1.0 → "buyer's market" (sellers desperate)
# seller_pressure=1.0, buyer_pressure=1.5 → "seller's market" (buyers desperate)
# Both 1.0 → symmetric (default)
SELLER_PRESSURE = 1.0
BUYER_PRESSURE = 1.0


# ─── STATISTICAL TOOLS ─────────────────────────────
# Von Neumann Standard: every ranking claim backed by a test.

BOOTSTRAP_N = 1000       # Resamples for confidence intervals
MASTER_SEED = 42         # For reproducible bootstrap
ELO_K = 32               # Elo K-factor
ELO_INIT = 1500          # Starting Elo


def bootstrap_ci(data, n_boot=BOOTSTRAP_N, alpha=0.05):
    """Bootstrap 95% confidence interval. Returns (mean, lo, hi)."""
    if not data:
        return (0.0, 0.0, 0.0)
    rng = np.random.RandomState(MASTER_SEED)
    arr = np.array(data)
    means = np.array([
        np.mean(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    return (float(np.mean(arr)),
            float(np.percentile(means, 100 * alpha / 2)),
            float(np.percentile(means, 100 * (1 - alpha / 2))))


def wilcoxon_approx(x, y):
    """Paired Wilcoxon signed-rank test (normal approx). Returns p-value."""
    n = min(len(x), len(y))
    if n < 5:
        return 1.0
    diffs = [x[i] - y[i] for i in range(n)]
    diffs = [d for d in diffs if abs(d) > 1e-10]
    n = len(diffs)
    if n < 5:
        return 1.0
    abs_d = sorted(enumerate(diffs), key=lambda t: abs(t[1]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(abs(abs_d[j][1]) - abs(abs_d[i][1])) < 1e-10:
            j += 1
        avg_rank = (i + j + 1) / 2
        for k in range(i, j):
            ranks[abs_d[k][0]] = avg_rank
        i = j
    w_plus = sum(ranks[i] for i in range(n) if diffs[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if diffs[i] < 0)
    W = min(w_plus, w_minus)
    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma < 1e-10:
        return 1.0
    z = abs(W - mu) / sigma
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def update_elo(ra, rb, score_a):
    """Update Elo ratings. score_a: 1=win, 0.5=draw, 0=loss."""
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    return ra + ELO_K * (score_a - ea), rb + ELO_K * ((1 - score_a) - (1 - ea))


def create_issues():
    return [
        make_issue(name="price", values=50),
        make_issue(name="delivery", values=5),
        make_issue(name="warranty", values=4),
        make_issue(name="payment", values=3),
    ]


def create_ufuns(issues, n_steps=10, reserved_value=None, randomize_weights=False):
    if reserved_value is None:
        reserved_value = BATNA_CENTER
    
    if randomize_weights:
        # ─── DIRICHLET-RANDOMIZED WEIGHTS ──────────────────────
        # Each round simulates a different deal context:
        #   - Sometimes price dominates (commodity purchase)
        #   - Sometimes delivery is critical (JIT manufacturing)
        #   - Sometimes warranty matters most (safety-critical)
        #
        # Alpha vectors encode the MEAN archetype with concentration ~5:
        #   Seller: price=0.50, delivery=0.15, warranty=0.10, payment=0.25
        #   Buyer:  price=0.20, delivery=0.30, warranty=0.40, payment=0.10
        #
        # Dirichlet(5 * mean) produces realistic variation while
        # preserving the "what each side cares about" identity.
        concentration = 5.0
        alpha_a = np.array([0.50, 0.15, 0.10, 0.25]) * concentration
        alpha_b = np.array([0.20, 0.30, 0.40, 0.10]) * concentration
        
        raw_a = np.random.dirichlet(alpha_a)
        raw_b = np.random.dirichlet(alpha_b)
        
        issue_names = ["price", "delivery", "warranty", "payment"]
        weights_a = {name: float(w) for name, w in zip(issue_names, raw_a)}
        weights_b = {name: float(w) for name, w in zip(issue_names, raw_b)}
    else:
        # FIXED weights — original deterministic behavior
        weights_a = {"price": 0.50, "delivery": 0.15, "warranty": 0.10, "payment": 0.25}
        weights_b = {"price": 0.20, "delivery": 0.30, "warranty": 0.40, "payment": 0.10}
    
    temp = SAOMechanism(issues=issues, n_steps=n_steps)
    iss = temp.outcome_space.issues

    # Seller: wants high price, fast payment; less concerned about warranty/delivery
    ufun_a = LUFun(
        values={"price": IdentityFun(), "delivery": IdentityFun(),
                "warranty": AffineFun(slope=-1, bias=3),
                "payment": AffineFun(slope=-1, bias=2)},
        weights=weights_a, issues=iss,
    ).normalize()
    ufun_a.reserved_value = reserved_value

    # Buyer: wants low price, strong warranty, fast delivery; flexible on payment
    ufun_b = LUFun(
        values={"price": AffineFun(slope=-1, bias=49),
                "delivery": AffineFun(slope=-1, bias=4),
                "warranty": IdentityFun(), "payment": IdentityFun()},
        weights=weights_b, issues=iss,
    ).normalize()
    ufun_b.reserved_value = reserved_value

    return ufun_a, ufun_b


def _play_alternative_round(cls_agent, ufun_a, ufun_b, issues, n_steps,
                             a_uses_memory=False, is_seller=True, batna=0.40):
    """Play a quick 1-round alternative negotiation after walking away.
    
    Simulates real B2B: walking from a bad deal lets you try another vendor.
    The alternative is a random cooperative opponent (average market partner).
    Returns the utility achieved, or BATNA if no deal.
    """
    # Alternative pool: any agent from the full market (you don't pick your next lead)
    alt_pool = list(B2B_OPPONENTS.values()) + [AspirationNegotiator]
    alt_cls = np.random.choice(alt_pool)
    
    mech = SAOMechanism(issues=issues, n_steps=n_steps)
    
    if a_uses_memory:
        _global_memory_backup = negmas_agent._global_memory
        negmas_agent._global_memory = CrossSessionMemory()
    
    if is_seller:
        agent = cls_agent(name='alt_seller')
        opponent = alt_cls(name='alt_buyer')
        mech.add(agent, ufun=ufun_a)
        mech.add(opponent, ufun=ufun_b)
    else:
        opponent = alt_cls(name='alt_seller')
        agent = cls_agent(name='alt_buyer')
        mech.add(opponent, ufun=ufun_a)
        mech.add(agent, ufun=ufun_b)
    
    result = mech.run()
    
    if a_uses_memory:
        negmas_agent._global_memory = _global_memory_backup
    
    if result.agreement is not None:
        my_ufun = ufun_a if is_seller else ufun_b
        u = my_ufun(result.agreement)
        return max(float(u) if u is not None else 0.0, batna)
    else:
        return batna


def play_matchup(ClassA: Type, ClassB: Type, ufun_a, ufun_b, issues,
                 n_steps: int, n_rounds: int, batna: float,
                 a_uses_memory: bool = False, b_uses_memory: bool = False,
                 prior_deals_ab: int = 0,
                 seller_pressure: float = 1.0, buyer_pressure: float = 1.0):
    """
    Play A vs B for n_rounds. Returns (avg_util_a, avg_util_b, deal_rate).
    
    Realistic B2B mechanics:
    - Random step count per round (breaks backward induction)
    - Variable BATNA per round (shifting outside options)
    - BATNA noise (agents don't know exact reservation value)
    - Must-deal rounds: 30% chance agent MUST close (walk-away = severe penalty)
    - Walk-away reputation tax: each walk-away degrades future BATNA
    - Relationship premium: repeat deals with same partner earn +0.03
    - Market position variance: random ±0.05 power modifier per round
    """
    memory_a = CrossSessionMemory()
    memory_b = CrossSessionMemory()
    utils_a, utils_b = [], []
    deals = 0
    
    # Track cumulative reputation damage from walk-aways
    rep_damage_a = 0.0
    rep_damage_b = 0.0
    
    # Track deals in this matchup for relationship premium
    matchup_deals = prior_deals_ab
    
    # ─── PARALLEL DEAL PRESSURE ──────────────────────
    # Each consecutive no-deal round escalates pressure:
    # - Forced walk-away probability increases
    # - Game length shrinks (other vendor is about to close)
    consecutive_nodeals = 0

    for r in range(n_rounds):
        # Randomize game length to break backward induction
        if RANDOMIZE_STEPS:
            base_steps = np.random.randint(7, 14)  # Uniform(7,13)
        else:
            base_steps = n_steps
        
        # Shrink game by consecutive no-deals (parallel vendor closing)
        round_steps = max(5, base_steps - consecutive_nodeals * STEP_SHRINK_PER_NODEAL)
        
        # ─── Variable BATNA: outside options shift each round ───
        round_batna = np.random.uniform(
            BATNA_CENTER - BATNA_RANGE,
            BATNA_CENTER + BATNA_RANGE
        )
        
        # ─── Market Position: random power modifier ────────────
        power_a = np.random.uniform(-MARKET_POWER_RANGE, MARKET_POWER_RANGE)
        power_b = np.random.uniform(-MARKET_POWER_RANGE, MARKET_POWER_RANGE)
        
        # ─── ESCALATING FORCED WALK-AWAY (ASYMMETRIC) ─────────
        # Each no-deal round increases the chance the parallel deal closes.
        # Seller (A) and Buyer (B) face different pressure based on market.
        base_prob = MUST_DEAL_BASE_PROB + consecutive_nodeals * MUST_DEAL_ESCALATION
        a_must_deal_prob = min(0.85, base_prob * seller_pressure)
        b_must_deal_prob = min(0.85, base_prob * buyer_pressure)
        a_must_deal = np.random.random() < a_must_deal_prob
        b_must_deal = np.random.random() < b_must_deal_prob
        
        # Compute effective BATNA (degraded by past walk-aways)
        effective_batna_a = max(0.05, round_batna - rep_damage_a)
        effective_batna_b = max(0.05, round_batna - rep_damage_b)
        
        # ─── BATNA Noise: agents don't know exact reservation ──
        # Their ufun gets a noisy reservation value (±10%)
        noise_a = np.random.uniform(1.0 - BATNA_NOISE, 1.0 + BATNA_NOISE)
        noise_b = np.random.uniform(1.0 - BATNA_NOISE, 1.0 + BATNA_NOISE)
        perceived_batna_a = effective_batna_a * noise_a
        perceived_batna_b = effective_batna_b * noise_b
        
        # Create ufuns with noisy reservation values and randomized weights
        round_ufun_a, round_ufun_b = create_ufuns(
            issues, round_steps, 
            reserved_value=perceived_batna_a,
            randomize_weights=RANDOMIZE_WEIGHTS,
        )
        round_ufun_b.reserved_value = perceived_batna_b
        
        if a_uses_memory:
            negmas_agent._global_memory = memory_a
        else:
            negmas_agent._global_memory = CrossSessionMemory()
        
        mech = SAOMechanism(issues=issues, n_steps=round_steps)
        agent_a = ClassA(name=f"a_r{r}")
        agent_b = ClassB(name=f"b_r{r}")
        
        mech.add(agent_a, ufun=round_ufun_a)
        mech.add(agent_b, ufun=round_ufun_b)
        
        result = mech.run()

        if result.agreement is not None:
            ua = round_ufun_a(result.agreement)
            ub = round_ufun_b(result.agreement)
            u_a_raw = float(ua) if ua is not None else 0.0
            u_b_raw = float(ub) if ub is not None else 0.0
            
            # ─── Relationship Premium: repeat deals earn trust bonus ──
            if matchup_deals > 0:
                u_a_raw += RELATIONSHIP_PREMIUM
                u_b_raw += RELATIONSHIP_PREMIUM
            
            # ─── Market Position: apply power modifier ────────────
            u_a_raw += power_a
            u_b_raw += power_b
            
            utils_a.append(max(0.0, u_a_raw))
            utils_b.append(max(0.0, u_b_raw))
            deals += 1
            matchup_deals += 1
            consecutive_nodeals = 0  # Deal breaks the escalation
        else:
            # Walk-away: apply must-deal penalty OR try alternative deal
            # In real B2B, walking away means you can pursue other leads.
            # Agents who walk from bad deals get a shot at better ones.
            
            if a_must_deal:
                # Agent A HAD to deal but failed — severe penalty
                utils_a.append(0.10)
            elif np.random.random() < WALKAWAY_ALT_PROB:
                # Alternative deal opportunity: 1-round with a cooperative partner
                # Shorter game (only 7 steps) since you're starting late
                alt_u = _play_alternative_round(
                    ClassA, ufun_a, ufun_b, issues, 7,
                    a_uses_memory=a_uses_memory, is_seller=True,
                    batna=effective_batna_a)
                utils_a.append(alt_u)
            else:
                utils_a.append(effective_batna_a)
            
            if b_must_deal:
                utils_b.append(0.10)
            elif np.random.random() < WALKAWAY_ALT_PROB:
                alt_u = _play_alternative_round(
                    ClassB, ufun_a, ufun_b, issues, 7,
                    a_uses_memory=b_uses_memory, is_seller=False,
                    batna=effective_batna_b)
                utils_b.append(alt_u)
            else:
                utils_b.append(effective_batna_b)
            
            # Both agents accumulate reputation damage from walk-aways
            rep_damage_a += WALKAWAY_REP_TAX
            rep_damage_b += WALKAWAY_REP_TAX
            consecutive_nodeals += 1  # Escalate parallel deal pressure

    return (
        statistics.mean(utils_a),
        statistics.mean(utils_b),
        deals / n_rounds,
    )


def _run_single_matchup(args):
    """Worker function for parallel matchup execution.
    Must be at module level for multiprocessing pickle.
    """
    name_a, name_b, cls_a, cls_b, a_mem, b_mem, n_steps, n_rounds, batna, sp, bp = args
    
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, n_steps)
    
    util_a, util_b, dr = play_matchup(
        cls_a, cls_b, ufun_a, ufun_b, issues,
        n_steps, n_rounds, batna,
        a_uses_memory=a_mem,
        b_uses_memory=b_mem,
        seller_pressure=sp, buyer_pressure=bp,
    )
    return (name_a, name_b, util_a, util_b, dr)


def run_round_robin(seller_pressure=None, buyer_pressure=None):
    """Full all-vs-all round robin tournament.
    
    Args:
        seller_pressure: Walk-away pressure multiplier for seller (A). >1 = buyer's market.
        buyer_pressure: Walk-away pressure multiplier for buyer (B). >1 = seller's market.
    """
    sp = seller_pressure if seller_pressure is not None else SELLER_PRESSURE
    bp = buyer_pressure if buyer_pressure is not None else BUYER_PRESSURE

    # Build player roster
    all_players = {}
    for name, cls in B2B_OPPONENTS.items():
        all_players[name] = {"class": cls, "uses_memory": False}
    all_players["SNHP"] = {"class": SNHPAgent, "uses_memory": True}
    all_players["Aspiration"] = {"class": AspirationNegotiator, "uses_memory": False}

    player_names = list(all_players.keys())
    n = len(player_names)

    # Score tracking
    scores = defaultdict(list)  # name → list of utilities across all matchups
    pairwise = {}  # (a, b) → (util_a, util_b, deal_rate)
    elo = {name: ELO_INIT for name in player_names}

    n_rounds = N_ROUNDS
    print("=" * 115)
    steps_desc = "U(7,13) random" if RANDOMIZE_STEPS else str(N_STEPS)
    batna_desc = f"U({BATNA_CENTER-BATNA_RANGE:.2f},{BATNA_CENTER+BATNA_RANGE:.2f})"
    print(f"  ALL-VS-ALL ROUND ROBIN — {n} players × {n_rounds} rounds × {steps_desc} steps")
    market_desc = f"Market: Sell×{sp:.1f}/Buy×{bp:.1f}" if sp != 1.0 or bp != 1.0 else "Market: Symmetric"
    print(f"  BATNA={batna_desc} ±{BATNA_NOISE:.0%}noise | Walk-away={MUST_DEAL_BASE_PROB:.0%}+{MUST_DEAL_ESCALATION:.0%}/nodeal | "
          f"Rep.tax={WALKAWAY_REP_TAX} | {market_desc}")
    print(f"  StepShrink={STEP_SHRINK_PER_NODEAL}/nodeal | Power=±{MARKET_POWER_RANGE} | Rel.prem={RELATIONSHIP_PREMIUM} | WalkAlt={WALKAWAY_ALT_PROB:.0%}")
    print(f"  Workers: {N_WORKERS} cores (parallel)")
    print("=" * 115)

    # ─── BUILD MATCHUP JOBS ───────────────────────────
    jobs = []
    for name_a in player_names:
        for name_b in player_names:
            pa = all_players[name_a]
            pb = all_players[name_b]
            jobs.append((
                name_a, name_b,
                pa["class"], pb["class"],
                pa["uses_memory"], pb["uses_memory"],
                N_STEPS, n_rounds, BATNA_CENTER,
                sp, bp,
            ))
    
    total_matchups = len(jobs)
    print(f"\n  Dispatching {total_matchups} matchups across {N_WORKERS} cores...")
    t0 = time.time()

    # ─── PARALLEL EXECUTION ───────────────────────────
    with multiprocessing.Pool(N_WORKERS) as pool:
        results = pool.map(_run_single_matchup, jobs)
    
    elapsed = time.time() - t0
    print(f"  ✅ {total_matchups} matchups completed in {elapsed:.1f}s "
          f"({total_matchups/elapsed:.1f} matchups/sec)")

    # ─── COLLECT RESULTS ──────────────────────────────
    for name_a, name_b, util_a, util_b, dr in results:
        scores[name_a].append(util_a)
        pairwise[(name_a, name_b)] = (util_a, util_b, dr)
        
        # Update Elo (sequential — fast)
        if name_a != name_b:
            if util_a > util_b + 0.005:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 1.0)
            elif abs(util_a - util_b) <= 0.005:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 0.5)
            else:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 0.0)

    # ─── Rankings with CIs ────────────────────────────

    print("\n" + "=" * 115)
    print("  FINAL RANKINGS (with 95% Bootstrap CI)")
    print("=" * 115)

    rankings = []
    for name in player_names:
        avg = statistics.mean(scores[name])
        med = statistics.median(scores[name])
        mn = min(scores[name])
        mx = max(scores[name])
        ci_mean, ci_lo, ci_hi = bootstrap_ci(scores[name])
        
        # Count wins/ties/losses
        wins, ties, losses = 0, 0, 0
        for opp in player_names:
            if opp == name:
                continue
            my_u = pairwise[(name, opp)][0]
            their_u = pairwise[(opp, name)][0]
            if my_u > their_u + 0.005:
                wins += 1
            elif abs(my_u - their_u) <= 0.005:
                ties += 1
            else:
                losses += 1

        rankings.append({
            "name": name,
            "avg": avg,
            "med": med,
            "min": mn,
            "max": mx,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "elo": elo.get(name, ELO_INIT),
            "wins": wins,
            "ties": ties,
            "losses": losses,
        })

    rankings.sort(key=lambda x: x["avg"], reverse=True)
    
    # ─── Bootstrap rank distribution ─────────────────
    rng = np.random.RandomState(MASTER_SEED + 999)
    rank_counts = {name: [] for name in player_names}
    for _ in range(BOOTSTRAP_N):
        boot_means = {}
        for name in player_names:
            arr = np.array(scores[name])
            idx = rng.randint(0, len(arr), size=len(arr))
            boot_means[name] = float(np.mean(arr[idx]))
        sorted_names = sorted(boot_means.keys(), key=lambda nm: boot_means[nm], reverse=True)
        for rank_i, nm in enumerate(sorted_names, 1):
            rank_counts[nm].append(rank_i)

    print(f"\n  {'#':>3} {'Player':<22} {'Avg':>8} {'95% CI':>16} {'Rank CI':>10} "
          f"{'Elo':>6} {'W':>3} {'T':>3} {'L':>3} {'Score':>7}")
    print("  " + "-" * 105)

    for rank, r in enumerate(rankings, 1):
        score_pct = r["wins"] / max(1, r["wins"] + r["ties"] + r["losses"])
        rank_lo = int(np.percentile(rank_counts[r['name']], 2.5))
        rank_hi = int(np.percentile(rank_counts[r['name']], 97.5))
        marker = " ⭐" if r["name"] == "SNHP" else ""
        print(f"  {rank:>3} {r['name']:<22} {r['avg']:>8.4f} "
              f"[{r['ci_lo']:.4f},{r['ci_hi']:.4f}] "
              f"[{rank_lo:>2}-{rank_hi:>2}] "
              f"{r['elo']:>6.0f} "
              f"{r['wins']:>3} {r['ties']:>3} {r['losses']:>3} "
              f"{score_pct:>6.0%}{marker}")

    # ─── SNHP Analysis ────────────────────────────────

    snhp_rank = next(i for i, r in enumerate(rankings, 1) if r["name"] == "SNHP")
    asp_rank = next(i for i, r in enumerate(rankings, 1) if r["name"] == "Aspiration")
    
    print(f"\n  SNHP Rank: #{snhp_rank}/{n}")
    print(f"  Aspiration Rank: #{asp_rank}/{n}")

    # Show SNHP's matchup detail with significance
    print(f"\n  SNHP Matchup Details (N={n_rounds} rounds):")
    print(f"  {'Opponent':<22} {'SNHP':>8} {'Opp':>8} {'Deal%':>7} {'Result':>8}")
    print("  " + "-" * 60)

    for opp in player_names:
        if opp == "SNHP":
            continue
        su, ou, dr = pairwise[("SNHP", opp)]
        opp_against_snhp = pairwise[(opp, "SNHP")][0]
        result = "✅ WIN" if su > opp_against_snhp + 0.005 else (
            "➖ TIE" if abs(su - opp_against_snhp) <= 0.005 else "❌ LOSE")
        print(f"  {opp:<22} {su:>8.4f} {opp_against_snhp:>8.4f} {dr:>6.0%} {result:>8}")
    
    # ─── Significance vs Baselines ────────────────────
    print(f"\n  SIGNIFICANCE TESTS (Wilcoxon signed-rank, α=0.05)")
    print(f"  {'Comparison':<35} {'SNHP':>8} {'Other':>8} {'Δ':>8} {'p':>8} {'Result':>12}")
    print("  " + "-" * 85)
    for bm in ["Aspiration", "Split-the-Diff", "Fair Demand", "The Closer"]:
        if bm in scores and "SNHP" in scores:
            s, b = scores["SNHP"], scores[bm]
            n_cmp = min(len(s), len(b))
            if n_cmp >= 5:
                p = wilcoxon_approx(s[:n_cmp], b[:n_cmp])
                diff = statistics.mean(s[:n_cmp]) - statistics.mean(b[:n_cmp])
                sig = "SNHP BETTER" if diff > 0 and p < 0.05 else (
                      "SNHP WORSE" if diff < 0 and p < 0.05 else "NO DIFF")
                print(f"  {'SNHP vs ' + bm:<35} {statistics.mean(s[:n_cmp]):>8.4f} "
                      f"{statistics.mean(b[:n_cmp]):>8.4f} {diff:>+8.4f} {p:>8.4f} {sig:>12}")

    # ─── Dominance Analysis ───────────────────────────

    print(f"\n" + "=" * 110)
    print("  DOMINANCE ANALYSIS")
    print("=" * 110)

    # Find if any player dominates (beats all others)
    dominant = [r for r in rankings if r["losses"] == 0]
    if dominant:
        print(f"\n  DOMINANT STRATEGIES (0 losses):")
        for d in dominant:
            print(f"    {d['name']}: {d['wins']}W/{d['ties']}T/{d['losses']}L, avg={d['avg']:.4f}")
    else:
        print(f"\n  No dominant strategy found (every player loses to someone)")
        # Find rock-paper-scissors cycles
        top3 = rankings[:3]
        print(f"  Top 3: {', '.join(r['name'] for r in top3)}")
        for a in top3:
            for b in top3:
                if a["name"] != b["name"]:
                    u = pairwise[(a["name"], b["name"])][0]
                    v = pairwise[(b["name"], a["name"])][0]
                    arrow = ">" if u > v + 0.005 else ("<" if v > u + 0.005 else "=")
                    print(f"    {a['name']} {arrow} {b['name']} ({u:.4f} vs {v:.4f})")

    # ─── Strategy Insights ────────────────────────────

    print(f"\n  STRATEGY INSIGHTS:")
    
    # Highest average utility
    print(f"  Highest avg utility:  {rankings[0]['name']} ({rankings[0]['avg']:.4f})")
    print(f"  Lowest variance:      ", end="")
    variances = [(name, np.std(scores[name])) for name in player_names]
    variances.sort(key=lambda x: x[1])
    print(f"{variances[0][0]} (σ={variances[0][1]:.4f})")
    
    # Most exploitable
    print(f"  Most exploitable:     {rankings[-1]['name']} (avg={rankings[-1]['avg']:.4f})")
    
    # Best against SNHP
    best_vs_snhp = max(
        [(opp, pairwise[(opp, "SNHP")][0]) for opp in player_names if opp != "SNHP"],
        key=lambda x: x[1]
    )
    print(f"  Best against SNHP:    {best_vs_snhp[0]} ({best_vs_snhp[1]:.4f})")

    return rankings, pairwise, scores


if __name__ == "__main__":
    # CLI flags
    if "--quick" in sys.argv:
        N_ROUNDS = 5
        print("  [Quick mode: N=5 rounds]")
    
    if "--multi-market" in sys.argv:
        # Run 3 market conditions for full B2B realism
        print("\n" + "#" * 115)
        print("  SYMMETRIC MARKET (Baseline)")
        print("#" * 115)
        run_round_robin(seller_pressure=1.0, buyer_pressure=1.0)
        
        print("\n" + "#" * 115)
        print("  BUYER'S MARKET (Seller under pressure)")
        print("#" * 115)
        run_round_robin(seller_pressure=1.5, buyer_pressure=1.0)
        
        print("\n" + "#" * 115)
        print("  SELLER'S MARKET (Buyer under pressure)")
        print("#" * 115)
        run_round_robin(seller_pressure=1.0, buyer_pressure=1.5)
    else:
        run_round_robin()
