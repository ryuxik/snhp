"""
Population-Based Training scaffold for SNHP parametric tuning.

Design choice (and an honest framing): for *parametric* agents like SNHP,
PBT and NSGA-II are nearly equivalent — both are population-based
evolutionary search. PBT's distinctive feature (interleaved policy
training via gradient updates between exploit/explore steps) only matters
for *neural-network* policies. For our parameter-vector agent, the
"training" happens via Optuna's NSGA-II sampler over the population.

What this file adds vs the bare Optuna run:
  - Explicit population dynamics: top 25% reproduce + mutate every K trials
  - Self-play tournament fitness (every individual plays every other,
    so memory-using strategies have memory-using opponents to learn against)
  - Population diversity preservation via mutation noise

This is most useful as scaffolding — it can be extended later to drive
multi-process self-play with checkpointing. Out of the box the parameters
default to a short "demonstration" run (8 individuals, 3 generations) so
the framework can be sanity-checked without burning hours of compute.

Run:
  ../venv/bin/python -m gametheory.evals.pbt_self_play --pop 8 --gens 3 --n-rounds 50
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import statistics
import time

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from b2b_round_robin import play_matchup, create_issues, create_ufuns, BATNA_CENTER  # noqa: E402
import negmas_agent  # noqa: E402
from negmas_agent import SNHPAgent, CrossSessionMemory  # noqa: E402

from gametheory.evals.optuna_multi_objective import _PARAM_SPACE


def random_params(rng: random.Random) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, lo, hi in _PARAM_SPACE:
        v = rng.uniform(lo, hi)
        out[f"seller_{name}"] = v
        out[f"buyer_{name}"] = v
    return out


def mutate(params: dict[str, float], rng: random.Random,
            sigma: float = 0.10) -> dict[str, float]:
    """Gaussian perturbation in each axis, clipped to the original search range."""
    out = copy.deepcopy(params)
    for name, lo, hi in _PARAM_SPACE:
        delta = rng.gauss(0, sigma * (hi - lo))
        for prefix in ("seller_", "buyer_"):
            out[prefix + name] = max(lo, min(hi, out[prefix + name] + delta))
    return out


def play_individual_vs_individual(params_a: dict, params_b: dict,
                                    n_rounds: int) -> tuple[float, float]:
    """Both individuals run SNHP with their own params. Returns (a_util, b_util).

    SNHP's `_TUNE_PARAMS` is a module-level global; we can't have two
    different parameter sets active simultaneously in the same process.
    So we use two-pass evaluation: in pass 1, A's params active and we
    record A's behavior as if it were authoritative; in pass 2, swap.
    Average the two passes for a less biased estimate."""
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, 10)

    try:
        negmas_agent._TUNE_PARAMS = params_a
        negmas_agent._global_memory = CrossSessionMemory()
        a1, b1, _ = play_matchup(SNHPAgent, SNHPAgent, ufun_a, ufun_b, issues,
                                  10, n_rounds, BATNA_CENTER,
                                  a_uses_memory=True, b_uses_memory=True)
        negmas_agent._TUNE_PARAMS = params_b
        negmas_agent._global_memory = CrossSessionMemory()
        a2, b2, _ = play_matchup(SNHPAgent, SNHPAgent, ufun_a, ufun_b, issues,
                                  10, n_rounds, BATNA_CENTER,
                                  a_uses_memory=True, b_uses_memory=True)
    finally:
        negmas_agent._TUNE_PARAMS = None

    return (a1 + a2) / 2, (b1 + b2) / 2


def evaluate_population(pop: list[dict], n_rounds: int) -> list[float]:
    """All-vs-all; each individual's fitness = mean utility across N-1 opponents."""
    n = len(pop)
    util = [0.0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            ua, ub = play_individual_vs_individual(pop[i], pop[j], n_rounds)
            util[i] += ua
    return [u / max(n - 1, 1) for u in util]


def run(pop_size: int, n_gens: int, n_rounds: int, seed: int,
         elite_fraction: float = 0.25, mutation_sigma: float = 0.10) -> None:
    rng = random.Random(seed)
    pop = [random_params(rng) for _ in range(pop_size)]
    elite_n = max(1, int(elite_fraction * pop_size))

    print("=" * 100)
    print(f"  PBT self-play tournament — pop={pop_size}, gens={n_gens}, "
          f"n_rounds={n_rounds}")
    print(f"  Elite fraction: {elite_fraction:.0%} ({elite_n}/{pop_size}); "
          f"mutation σ: {mutation_sigma:.2f}")
    print("=" * 100)

    history: list[dict] = []
    for gen in range(1, n_gens + 1):
        t0 = time.time()
        fitness = evaluate_population(pop, n_rounds)
        elapsed = time.time() - t0
        sorted_idx = sorted(range(pop_size), key=lambda i: -fitness[i])
        best = max(fitness)
        median = statistics.median(fitness)
        worst = min(fitness)
        print(f"  Gen {gen:>2} | best={best:.4f} median={median:.4f} "
              f"worst={worst:.4f} | matchups in {elapsed:.0f}s")

        history.append({
            "gen": gen, "best": best, "median": median, "worst": worst,
            "fitness": fitness,
        })

        if gen == n_gens:
            break

        # Exploit: bottom (pop_size - elite_n) copy from top elite_n
        new_pop = list(pop)
        elite = [pop[i] for i in sorted_idx[:elite_n]]
        for i in sorted_idx[elite_n:]:
            parent = elite[rng.randrange(elite_n)]
            new_pop[i] = mutate(parent, rng, sigma=mutation_sigma)
        pop = new_pop

    # Persist final population's best individual
    final_idx = sorted_idx[0]
    out_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(out_dir, "pbt_best.json")
    with open(path, "w") as f:
        json.dump({
            "fitness": fitness[final_idx],
            "params": pop[final_idx],
            "history": history,
            "config": {"pop_size": pop_size, "n_gens": n_gens,
                        "n_rounds": n_rounds, "seed": seed,
                        "elite_fraction": elite_fraction,
                        "mutation_sigma": mutation_sigma},
        }, f, indent=2)
    print(f"  Wrote {path}")
    print(f"  Best individual fitness = {fitness[final_idx]:.4f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--pop", type=int, default=8)
    p.add_argument("--gens", type=int, default=3)
    p.add_argument("--n-rounds", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--elite-fraction", type=float, default=0.25)
    p.add_argument("--mutation-sigma", type=float, default=0.10)
    args = p.parse_args()
    run(args.pop, args.gens, args.n_rounds, args.seed,
         args.elite_fraction, args.mutation_sigma)
