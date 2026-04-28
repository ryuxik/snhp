"""
Extended multi-objective Optuna run — v2.

Differences from v1:
  - 4 objectives (added `anti_aspiration_margin`): explicitly maximize
    SNHP-util minus Aspiration-util in the direct head-to-head.
  - Detector thresholds (`det_*`) included in the search space so Optuna
    jointly tunes the base SNHP params + the deterministic-opponent
    detector behavior.
  - Larger budget: 200 trials, NSGA-II population_size=40.
  - Agent under test is `SNHPWithAspirationDetector` (so detector knobs
    actually affect behavior during evaluation).

Compute: ~80s/trial × 200 trials = ~4-4.5h on a 14-core box (within-trial
evaluation is sequential).

Run:
  ../venv/bin/python -m gametheory.evals.optuna_multi_objective_v2
"""
from __future__ import annotations

import argparse
import json
import os
import time

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

import optuna  # noqa: E402
from optuna.samplers import NSGAIISampler  # noqa: E402

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import play_matchup, create_issues, create_ufuns, BATNA_CENTER  # noqa: E402
import negmas_agent  # noqa: E402
from negmas_agent import CrossSessionMemory  # noqa: E402
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402

from gametheory.agents.aspiration_detector import SNHPWithAspirationDetector
from gametheory.agents.snhp_variants import SNHP_Hardline, SNHP_Conceder


N_ROUNDS = 100
N_STEPS = 10
DEFAULT_TRIALS = 200
DEFAULT_POP = 40


# Base params (same shape as v1) plus detector knobs at the bottom.
_BASE_PARAM_SPACE = [
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

_DETECTOR_PARAM_SPACE = [
    ("det_max_diff_std",          0.005, 0.06),
    ("det_min_pos_fraction",      0.55, 0.95),
    ("det_hold_until_t",          0.60, 0.95),
    ("det_bid_target_initial",    0.70, 0.95),
    ("det_bid_target_final",      0.45, 0.85),
    ("det_target_floor_margin",   0.10, 0.45),
    ("det_early_accept_margin",   0.20, 0.55),
]

_PARAM_SPACE = _BASE_PARAM_SPACE + _DETECTOR_PARAM_SPACE


def build_opponent_pool() -> dict:
    pool = dict(B2B_OPPONENTS)
    pool["Aspiration"] = AspirationNegotiator
    pool["SNHP_Hardline"] = SNHP_Hardline
    pool["SNHP_Conceder"] = SNHP_Conceder
    return pool


def _evaluate_role(params: dict, opp_cls: type, role: str) -> tuple[float, float]:
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, N_STEPS)
    negmas_agent._global_memory = CrossSessionMemory()
    try:
        negmas_agent._TUNE_PARAMS = params
        if role == "seller":
            ua, ub, _ = play_matchup(
                SNHPWithAspirationDetector, opp_cls, ufun_a, ufun_b, issues,
                N_STEPS, N_ROUNDS, BATNA_CENTER,
                a_uses_memory=True, b_uses_memory=False,
            )
            return ua, ub
        ua, ub, _ = play_matchup(
            opp_cls, SNHPWithAspirationDetector, ufun_a, ufun_b, issues,
            N_STEPS, N_ROUNDS, BATNA_CENTER,
            a_uses_memory=False, b_uses_memory=True,
        )
        return ub, ua
    finally:
        negmas_agent._TUNE_PARAMS = None


def _evaluate_self_play(params: dict) -> tuple[float, float]:
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, N_STEPS)
    negmas_agent._global_memory = CrossSessionMemory()
    try:
        negmas_agent._TUNE_PARAMS = params
        ua, ub, _ = play_matchup(
            SNHPWithAspirationDetector, SNHPWithAspirationDetector,
            ufun_a, ufun_b, issues,
            N_STEPS, N_ROUNDS, BATNA_CENTER,
            a_uses_memory=True, b_uses_memory=True,
        )
        return ua, ub
    finally:
        negmas_agent._TUNE_PARAMS = None


def make_objective(opp_pool: dict):
    def objective(trial):
        params: dict[str, float] = {}
        for name, lo, hi in _PARAM_SPACE:
            v = trial.suggest_float(name, lo, hi)
            params[f"seller_{name}"] = v
            params[f"buyer_{name}"] = v

        snhp_utils, opp_utils, h2h_wins = [], [], 0
        anti_aspiration = 0.0
        for opp_name, opp_cls in opp_pool.items():
            sa, oa = _evaluate_role(params, opp_cls, "seller")
            sb, ob = _evaluate_role(params, opp_cls, "buyer")
            avg_snhp = (sa + sb) / 2
            avg_opp = (oa + ob) / 2
            snhp_utils.append(avg_snhp)
            opp_utils.append(avg_opp)
            if avg_snhp > avg_opp + 0.005:
                h2h_wins += 1
            if opp_name == "Aspiration":
                anti_aspiration = avg_snhp - avg_opp

        avg_util = sum(snhp_utils) / len(snhp_utils)
        h2h_score = h2h_wins / len(opp_pool)
        sa_self, sb_self = _evaluate_self_play(params)
        self_play_pareto = sa_self + sb_self

        trial.set_user_attr("avg_util", avg_util)
        trial.set_user_attr("h2h_score", h2h_score)
        trial.set_user_attr("anti_aspiration", anti_aspiration)
        trial.set_user_attr("self_play_a", sa_self)
        trial.set_user_attr("self_play_b", sb_self)
        return (avg_util, h2h_score, self_play_pareto, anti_aspiration)

    return objective


def run(n_trials: int, n_pop: int, db_path: str, study_name: str) -> None:
    pool = build_opponent_pool()
    print("=" * 100)
    print(f"  EXTENDED OPTUNA RUN (v2)")
    print(f"  Trials: {n_trials} | Population: {n_pop} | n_rounds: {N_ROUNDS}")
    print(f"  Opponent pool: {len(pool)} | Search space: {len(_PARAM_SPACE)} dims")
    print(f"  Objectives: max(avg_util, h2h_score, self_play, anti_aspiration)")
    print(f"  Storage: {db_path}")
    print("=" * 100)

    sampler = NSGAIISampler(population_size=n_pop, mutation_prob=0.1,
                              crossover_prob=0.9)
    study = optuna.create_study(
        study_name=study_name, storage=db_path, sampler=sampler,
        directions=["maximize", "maximize", "maximize", "maximize"],
        load_if_exists=True,
    )
    t0 = time.time()
    study.optimize(make_objective(pool), n_trials=n_trials,
                    show_progress_bar=True)
    elapsed = time.time() - t0
    print(f"\n  Completed {n_trials} trials in {elapsed:.0f}s "
          f"({elapsed / n_trials:.1f}s/trial)")

    print()
    print("=" * 100)
    print(f"  PARETO FRONT — {len(study.best_trials)} non-dominated solutions")
    print("=" * 100)
    print(f"  {'#':>3} {'avg_util':>9} {'h2h':>5} {'self':>7} {'anti_asp':>9}")
    print("-" * 60)
    for t in sorted(study.best_trials, key=lambda x: -x.values[0])[:15]:
        print(f"  {t.number:>3} {t.values[0]:>9.4f} {t.values[1]:>5.2f} "
              f"{t.values[2]:>7.4f} {t.values[3]:>+9.4f}")

    best_avg = max(study.best_trials, key=lambda t: t.values[0])
    best_h2h = max(study.best_trials, key=lambda t: t.values[1])
    best_self = max(study.best_trials, key=lambda t: t.values[2])
    best_anti = max(study.best_trials, key=lambda t: t.values[3])
    print()
    print("  Best per objective:")
    print(f"   max avg_util       → trial #{best_avg.number}: avg={best_avg.values[0]:.4f}")
    print(f"   max h2h_score      → trial #{best_h2h.number}: h2h={best_h2h.values[1]:.2f}")
    print(f"   max self_play      → trial #{best_self.number}: self={best_self.values[2]:.4f}")
    print(f"   max anti_aspiration → trial #{best_anti.number}: anti_asp={best_anti.values[3]:+.4f}")

    out_dir = os.path.dirname(os.path.abspath(__file__))
    for tag, trial in [("avg", best_avg), ("h2h", best_h2h),
                        ("self", best_self), ("anti_asp", best_anti)]:
        params: dict[str, float] = {}
        for name, _, _ in _PARAM_SPACE:
            v = trial.params[name]
            params[f"seller_{name}"] = v
            params[f"buyer_{name}"] = v
        path = os.path.join(out_dir, f"optuna_v2_pareto_{tag}.json")
        with open(path, "w") as f:
            json.dump({
                "trial_number": trial.number,
                "values": list(trial.values),
                "params": params,
                "user_attrs": dict(trial.user_attrs),
            }, f, indent=2)
        print(f"   wrote {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n-trials", type=int, default=DEFAULT_TRIALS)
    p.add_argument("--population-size", type=int, default=DEFAULT_POP)
    p.add_argument("--db", type=str,
                    default="sqlite:///snhp_tune_v2.db")
    p.add_argument("--study-name", type=str, default="snhp-nsga2-v2")
    args = p.parse_args()
    run(args.n_trials, args.population_size, args.db, args.study_name)
