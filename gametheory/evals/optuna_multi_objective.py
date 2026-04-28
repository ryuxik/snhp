"""
Multi-objective Optuna NSGA-II tune for SNHP at long horizon.

Three objectives, all maximized:
  1. avg_utility   — mean SNHP utility across the opponent pool
  2. h2h_score     — fraction of opponents we strictly beat
  3. self_play_pareto — joint utility (SNHP_self_a + SNHP_self_b) when SNHP
                        plays itself; the network-effect / marketplace metric

Opponent pool extended vs the existing tuner:
  - 19 B2B stateless opponents (Anchorer, Nibbler, etc.)
  - AspirationNegotiator         (the long-horizon winner — must beat)
  - SNHP_Hardline, SNHP_Conceder (adaptive opponents — memory has someone to learn)

n_rounds = 100 per matchup. NSGA-II returns the Pareto frontier of
(avg_util, h2h_score, self_play_pareto); the operator picks an operating
point per market segment.

Run:
  ../venv/bin/python -m gametheory.evals.optuna_multi_objective --n-trials 50

Cost: ~75-80s per trial at n_rounds=100 with 22 opponents (within-trial
evaluation is sequential — the 14-core machine doesn't help here because
the SNHP agent reads parameters from a process-global). 50 trials ≈
60-65 min wall-clock. Optuna trials themselves run sequentially under
NSGA-II, so multiprocessing.Pool only helps once we refactor SNHP to
take params via constructor instead of via the module-level global.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "snhp",
))

import optuna  # noqa: E402
from optuna.samplers import NSGAIISampler  # noqa: E402

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import play_matchup, create_issues, create_ufuns, BATNA_CENTER  # noqa: E402
import negmas_agent  # noqa: E402
from negmas_agent import SNHPAgent, CrossSessionMemory  # noqa: E402
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402

from gametheory.evals.long_horizon_variants import SNHP_Hardline, SNHP_Conceder
from gametheory.agents.aspiration_detector import SNHPWithAspirationDetector


# ─── Search space ───────────────────────────────────────────────────────────
# Subset of `snhp/optuna_tuner.py:_PARAM_SPACE`. Drops six knobs that prior
# tuning showed had near-zero gradient at long horizon: probe_target,
# accept_mid_offset, best_seen_time, best_seen_margin, convergence_time,
# convergence_gap. Kept the rest, with `concession_cap_b2b` upper bound
# widened to 0.08 (vs 0.06) to let the optimizer try faster-conceding
# variants — the long-horizon data showed conceders aren't strictly
# dominated; the upper bound just blocked exploration.


_PARAM_SPACE = [
    ("aspiration_start",        0.50, 0.95),
    ("aspiration_floor",        0.35, 0.62),
    ("time_floor_rate",         0.50, 1.80),
    ("counter_anchor_cap",      0.50, 0.85),
    ("accept_early_bar",        0.40, 0.75),
    ("accept_early_cutoff",     0.20, 0.50),
    ("accept_late_start",       0.55, 0.85),
    ("accept_late_bottom",      0.35, 0.55),
    ("accept_late_curve",       0.30, 1.20),
    ("emergency_time",          0.65, 0.95),
    ("emergency_margin",        0.01, 0.06),
    ("retract_prob_b2b",        0.00, 0.10),
    ("concession_cap_b2b",      0.005, 0.08),
    ("zeuthen_concession_scale", 0.01, 0.15),
    ("commitment_margin",       0.00, 0.20),
]


N_ROUNDS = 100
N_STEPS = 10
ROLE_SELLER = "seller"
ROLE_BUYER = "buyer"


def build_opponent_pool() -> Dict[str, type]:
    pool: Dict[str, type] = dict(B2B_OPPONENTS)
    pool["Aspiration"] = AspirationNegotiator
    # Adaptive memory-using opponents — force the optimizer to handle agents that learn.
    pool["SNHP_Hardline"] = SNHP_Hardline
    pool["SNHP_Conceder"] = SNHP_Conceder
    pool["SNHP_WithDetector"] = SNHPWithAspirationDetector
    return pool


# ─── Objective ──────────────────────────────────────────────────────────────


def _evaluate_one_role(params: dict, opp_cls: type, role: str, n_rounds: int) -> tuple[float, float, float]:
    """
    Returns (snhp_util, opp_util, deal_rate) for SNHP-with-`params` vs opp_cls
    in the given role.
    """
    negmas_agent._TUNE_PARAMS = params
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, N_STEPS)
    negmas_agent._global_memory = CrossSessionMemory()

    if role == ROLE_SELLER:
        ua, ub, dr = play_matchup(
            SNHPAgent, opp_cls, ufun_a, ufun_b, issues,
            N_STEPS, n_rounds, BATNA_CENTER,
            a_uses_memory=True, b_uses_memory=False,
        )
        snhp, opp = ua, ub
    else:
        ua, ub, dr = play_matchup(
            opp_cls, SNHPAgent, ufun_a, ufun_b, issues,
            N_STEPS, n_rounds, BATNA_CENTER,
            a_uses_memory=False, b_uses_memory=True,
        )
        snhp, opp = ub, ua
    negmas_agent._TUNE_PARAMS = None
    return snhp, opp, dr


def _evaluate_self_play(params: dict, n_rounds: int) -> tuple[float, float]:
    """SNHP-with-params vs SNHP-with-params; returns (a_util, b_util) — both should be high."""
    negmas_agent._TUNE_PARAMS = params
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, N_STEPS)
    negmas_agent._global_memory = CrossSessionMemory()
    ua, ub, _ = play_matchup(
        SNHPAgent, SNHPAgent, ufun_a, ufun_b, issues,
        N_STEPS, n_rounds, BATNA_CENTER,
        a_uses_memory=True, b_uses_memory=True,
    )
    negmas_agent._TUNE_PARAMS = None
    return ua, ub


def make_multi_objective(opp_pool: Dict[str, type], n_rounds: int):
    def objective(trial):
        # Build full role-prefixed param dict.
        params: dict[str, float] = {}
        for name, lo, hi in _PARAM_SPACE:
            v = trial.suggest_float(name, lo, hi)
            params[f"seller_{name}"] = v
            params[f"buyer_{name}"] = v

        snhp_utils, opp_utils, h2h_wins = [], [], 0
        for opp_name, opp_cls in opp_pool.items():
            # Average over both roles (seller and buyer) so we don't overfit to one side.
            sa, oa, _ = _evaluate_one_role(params, opp_cls, ROLE_SELLER, n_rounds)
            sb, ob, _ = _evaluate_one_role(params, opp_cls, ROLE_BUYER, n_rounds)
            avg_snhp = (sa + sb) / 2
            avg_opp = (oa + ob) / 2
            snhp_utils.append(avg_snhp)
            opp_utils.append(avg_opp)
            if avg_snhp > avg_opp + 0.005:
                h2h_wins += 1

        avg_util = sum(snhp_utils) / len(snhp_utils)
        h2h_score = h2h_wins / len(opp_pool)

        sa_self, sb_self = _evaluate_self_play(params, n_rounds)
        self_play_pareto = sa_self + sb_self  # joint surplus

        trial.set_user_attr("avg_util", avg_util)
        trial.set_user_attr("h2h_score", h2h_score)
        trial.set_user_attr("self_play_a", sa_self)
        trial.set_user_attr("self_play_b", sb_self)
        trial.set_user_attr("opp_util", sum(opp_utils) / len(opp_utils))
        return (avg_util, h2h_score, self_play_pareto)

    return objective


# ─── Driver ─────────────────────────────────────────────────────────────────


def run(n_trials: int, db_path: str, study_name: str, n_rounds: int) -> None:
    pool = build_opponent_pool()
    print("=" * 100)
    print(f"  NSGA-II MULTI-OBJECTIVE OPTUNA RE-TUNE")
    print(f"  Trials: {n_trials} | n_rounds: {n_rounds} | "
          f"opponent pool: {len(pool)} ({len(pool) - 19} extra adaptive)")
    print(f"  Objectives: max(avg_util, h2h_score, self_play_pareto)")
    print(f"  Storage: {db_path}")
    print("=" * 100)

    sampler = NSGAIISampler(population_size=20, mutation_prob=0.1, crossover_prob=0.9)
    study = optuna.create_study(
        study_name=study_name, storage=db_path,
        sampler=sampler,
        directions=["maximize", "maximize", "maximize"],
        load_if_exists=True,
    )

    t0 = time.time()
    study.optimize(make_multi_objective(pool, n_rounds), n_trials=n_trials,
                    show_progress_bar=True)
    elapsed = time.time() - t0
    print(f"\n  Completed {n_trials} trials in {elapsed:.0f}s "
          f"({elapsed / n_trials:.1f}s/trial)")

    # Pareto front
    print()
    print("=" * 100)
    print(f"  PARETO FRONT — {len(study.best_trials)} non-dominated solutions")
    print("=" * 100)
    print(f"  {'#':>3} {'avg_util':>9} {'h2h':>5} {'self_play':>10}")
    print("-" * 50)
    for t in sorted(study.best_trials,
                    key=lambda x: -x.values[0]):
        print(f"  {t.number:>3} {t.values[0]:>9.4f} {t.values[1]:>5.2f} "
              f"{t.values[2]:>10.4f}")

    # Pick three operating points: max avg_util, max h2h, max self-play
    best_avg = max(study.best_trials, key=lambda t: t.values[0])
    best_h2h = max(study.best_trials, key=lambda t: t.values[1])
    best_self = max(study.best_trials, key=lambda t: t.values[2])
    print()
    print("  Top operating points (one per objective):")
    print(f"   max avg_util    → trial #{best_avg.number}: {best_avg.values}")
    print(f"   max h2h_score   → trial #{best_h2h.number}: {best_h2h.values}")
    print(f"   max self_play   → trial #{best_self.number}: {best_self.values}")

    # Persist all three
    out_dir = os.path.dirname(os.path.abspath(__file__))
    import json
    for tag, trial in [("avg", best_avg), ("h2h", best_h2h), ("self", best_self)]:
        params: dict[str, float] = {}
        for name, _, _ in _PARAM_SPACE:
            v = trial.params[name]
            params[f"seller_{name}"] = v
            params[f"buyer_{name}"] = v
        path = os.path.join(out_dir, f"optuna_pareto_{tag}.json")
        with open(path, "w") as f:
            json.dump({
                "trial_number": trial.number,
                "values": trial.values,
                "params": params,
                "user_attrs": dict(trial.user_attrs),
            }, f, indent=2)
        print(f"   wrote {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n-trials", type=int, default=50)
    p.add_argument("--n-rounds", type=int, default=100)
    p.add_argument("--db", type=str,
                    default="sqlite:///snhp_tune_multi_n100.db")
    p.add_argument("--study-name", type=str,
                    default="snhp-nsga2-n100-extended-pool")
    args = p.parse_args()
    run(args.n_trials, args.db, args.study_name, args.n_rounds)
