"""
Optuna CMA-ES Auto-Tuner for SNHP Negotiation Parameters.

Uses Covariance Matrix Adaptation Evolution Strategy (CMA-ES) to optimize
the continuous hyperparameters of the SNHP negotiation agent against the
full B2B opponent field.

Key parameters tuned:
  - probe_target: utility target for diagnostic probes
  - aspiration_start: initial demand level
  - aspiration_floor: minimum demand level
  - time_floor_rate: how fast aspiration descends via time pressure
  - counter_anchor_cap: max aspiration after counter-anchoring
  - accept_early/mid/late: acceptance thresholds per phase
  - retract_prob: probability of retraction in B2B
  - concession_cap: per-step concession limit

Architecture:
  - CMA-ES sampler for continuous optimization
  - Each trial runs N=5 quick rounds per matchup (tournament) 
  - Objective: maximize avg utility across all opponents
  - Parallelized with SQLite-backed storage
  - M4 Mac Pro: 14 core parallel trial evaluation

Based on 2026 SOTA:
  - BOA framework (decouple optimization targets)
  - Optuna CMA-ES (gradient-free black-box optimization)
  - ANAC competition proven methodology
"""

import sys
import os
from typing import Optional
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import optuna
from optuna.samplers import CmaEsSampler, TPESampler, NSGAIISampler
import statistics
import numpy as np
import json
import time
from multiprocessing import Pool, cpu_count

import negmas_agent
from negmas_agent import SNHPAgent, CrossSessionMemory
from b2b_opponents import B2B_OPPONENTS
from b2b_round_robin import (
    create_issues, create_ufuns, play_matchup, BATNA_CENTER
)

# Tuning config
N_TUNE_ROUNDS = 5       # Rounds per matchup during tuning (fast)
N_TRIALS = 100           # Total optimization trials
DB_PATH = "sqlite:///snhp_tune.db"
STUDY_NAME = "snhp-b2b-cmaes-v1"

# Role tags — must match negmas_agent._snhp_role property values
ROLE_SELLER = "seller"
ROLE_BUYER = "buyer"
ROLES = (ROLE_SELLER, ROLE_BUYER)


def _inject_params(params: dict):
    """Monkey-patch SNHP parameters for this trial.
    
    We use module-level globals that the agent reads during initialization.
    This avoids modifying the agent class for each trial.
    """
    negmas_agent._TUNE_PARAMS = params


def _clear_params():
    """Remove tuning params."""
    negmas_agent._TUNE_PARAMS = None


def _evaluate_agent(args):
    """
    Evaluate SNHP with specific params against one opponent in a specific role.
    role="seller" → SNHP plays first (Class A); role="buyer" → SNHP plays
    second (Class B). Returns (opp_name, snhp_util, opp_util, deal_rate).

    Both sides' utilities are returned so the objective can compute either
    raw mean utility OR head-to-head margin.
    """
    params, opp_name, opp_cls, n_rounds, role = args

    _inject_params(params)

    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, 10)
    negmas_agent._global_memory = CrossSessionMemory()

    if role == ROLE_SELLER:
        util_a, util_b, dr = play_matchup(
            SNHPAgent, opp_cls, ufun_a, ufun_b, issues,
            10, n_rounds, BATNA_CENTER,
            a_uses_memory=False, b_uses_memory=False,
        )
        snhp_util, opp_util = util_a, util_b
    elif role == ROLE_BUYER:
        util_a, util_b, dr = play_matchup(
            opp_cls, SNHPAgent, ufun_a, ufun_b, issues,
            10, n_rounds, BATNA_CENTER,
            a_uses_memory=False, b_uses_memory=False,
        )
        snhp_util, opp_util = util_b, util_a
    else:
        raise ValueError(f"Unknown role: {role!r}; expected one of {ROLES}")

    _clear_params()
    return opp_name, snhp_util, opp_util, dr


# Search space template; the role prefix gets prepended at trial time.
# Several upper bounds were widened to let SNHP explore extractor-style
# configurations (Anchorer opens at 0.97; SNHP's previous max-aggressive
# corner of 0.65 / 0.48 couldn't out-anchor it). The widened ranges:
#   aspiration_start    0.65 → 0.92  — open closer to opponent extractors
#   aspiration_floor    0.48 → 0.62  — hold a higher floor
#   counter_anchor_cap  0.65 → 0.85  — push back harder on extreme lowballs
#   accept_early_bar    0.58 → 0.75  — refuse mediocre early offers
#   accept_late_bottom  0.45 → 0.55  — keep firmer floor late
#   commitment_margin   0.10 → 0.20  — wider Schelling commitment options
_PARAM_SPACE = [
    ("probe_target",            0.45, 0.75),
    ("aspiration_start",        0.50, 0.92),
    ("aspiration_floor",        0.35, 0.62),
    ("time_floor_rate",         0.50, 1.80),
    ("counter_anchor_cap",      0.50, 0.85),
    ("accept_early_bar",        0.45, 0.75),
    ("accept_early_cutoff",     0.20, 0.50),
    ("accept_mid_offset",      -0.05, 0.05),
    ("accept_late_start",       0.55, 0.85),
    ("accept_late_bottom",      0.35, 0.55),
    ("accept_late_curve",       0.30, 1.20),
    ("emergency_time",          0.65, 0.95),
    ("emergency_margin",        0.01, 0.06),
    ("best_seen_time",          0.45, 0.85),
    ("best_seen_margin",        0.01, 0.06),
    ("convergence_time",        0.40, 0.70),
    ("convergence_gap",         0.02, 0.10),
    ("retract_prob_b2b",        0.00, 0.10),
    ("concession_cap_b2b",      0.005, 0.06),
    ("zeuthen_concession_scale", 0.01, 0.15),
    ("commitment_margin",       0.00, 0.20),
]


def make_objective(role: str, margin_weight: float = 0.5):
    """
    Build an Optuna objective bound to a specific role. Each suggested
    parameter is prefixed with the role so two studies don't collide and
    the resulting params can be merged into one role-aware dict.

    Objective is `avg(SNHP_util) + margin_weight * avg(SNHP_util - opp_util)`,
    which equals `(1+α)*avg(SNHP) − α*avg(opp)`. Setting margin_weight=0
    recovers the original mean-utility objective; positive values reward
    head-to-head extraction at the cost of pure mean utility. Default 0.5
    is the empirical sweet spot — heavy enough to bend behavior toward
    extraction, light enough not to collapse the deal rate.

    Three trial attributes are recorded for diagnostic dashboards:
      - avg_snhp_util  (raw mean utility)
      - avg_h2h_margin (mean of SNHP_util - opp_util)
      - avg_deal_rate  (fraction of matchups that closed a deal)
    """
    def objective(trial):
        params = {}
        for name, lo, hi in _PARAM_SPACE:
            params[f"{role}_{name}"] = trial.suggest_float(f"{role}_{name}", lo, hi)

        total_snhp = 0.0
        total_opp = 0.0
        total_deal = 0.0
        n_opp = 0
        for opp_name, opp_cls in B2B_OPPONENTS.items():
            _, snhp_u, opp_u, dr = _evaluate_agent(
                (params, opp_name, opp_cls, N_TUNE_ROUNDS, role)
            )
            total_snhp += snhp_u
            total_opp += opp_u
            total_deal += dr
            n_opp += 1

        avg_snhp = total_snhp / n_opp
        avg_opp = total_opp / n_opp
        avg_margin = avg_snhp - avg_opp
        trial.set_user_attr("avg_snhp_util", avg_snhp)
        trial.set_user_attr("avg_opp_util", avg_opp)
        trial.set_user_attr("avg_h2h_margin", avg_margin)
        trial.set_user_attr("avg_deal_rate", total_deal / n_opp)
        return avg_snhp + margin_weight * avg_margin

    return objective


_X0_BASE = {
    "probe_target": 0.52,
    "aspiration_start": 0.55,
    "aspiration_floor": 0.40,
    "time_floor_rate": 1.2,
    "counter_anchor_cap": 0.55,
    "accept_early_bar": 0.50,
    "accept_early_cutoff": 0.35,
    "accept_mid_offset": 0.0,
    "accept_late_start": 0.70,
    "accept_late_bottom": 0.38,
    "accept_late_curve": 0.6,
    "emergency_time": 0.80,
    "emergency_margin": 0.02,
    "best_seen_time": 0.65,
    "best_seen_margin": 0.02,
    "convergence_time": 0.55,
    "convergence_gap": 0.04,
    "retract_prob_b2b": 0.01,
    "concession_cap_b2b": 0.04,
    "zeuthen_concession_scale": 0.05,
    "commitment_margin": 0.03,
}


def run_optimization(role: str = ROLE_SELLER, db_path: Optional[str] = None,
                      study_name: Optional[str] = None,
                      result_path: Optional[str] = None,
                      margin_weight: float = 0.5):
    """
    Run a CMA-ES optimization study for the given role ('seller' or 'buyer').
    Each role's parameter set is namespaced with the role prefix
    (e.g. 'seller_probe_target') so two studies can be merged into one
    role-aware dict consumed by negmas_agent._tp().
    """
    print(f"\n{'='*70}")
    print(f"  SNHP Auto-Tuner — Optuna CMA-ES (role={role})")
    print(f"  {N_TRIALS} trials × {len(B2B_OPPONENTS)} opponents × {N_TUNE_ROUNDS} rounds")
    print(f"  Search space: {len(_PARAM_SPACE)} continuous parameters (prefixed {role}_)")
    print(f"{'='*70}\n")

    db_path = db_path or f"sqlite:///snhp_tune_{role}.db"
    study_name = study_name or f"snhp-b2b-cmaes-{role}"
    result_path = result_path or os.path.join(
        os.path.dirname(__file__), f"optimal_params_{role}.json"
    )

    # Warm-start with the role-prefixed defaults
    x0 = {f"{role}_{k}": v for k, v in _X0_BASE.items()}

    sampler = CmaEsSampler(x0=x0, sigma0=0.05, n_startup_trials=10)

    study = optuna.create_study(
        study_name=study_name, storage=db_path,
        sampler=sampler, direction="maximize",
        load_if_exists=True,
    )

    print(f"  Starting optimization ({N_TRIALS} trials, margin_weight={margin_weight})...\n")
    start = time.time()
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(make_objective(role, margin_weight=margin_weight),
                    n_trials=N_TRIALS, show_progress_bar=True)
    elapsed = time.time() - start

    print(f"\n{'='*70}")
    print(f"  OPTIMIZATION COMPLETE — {elapsed:.0f}s ({elapsed/N_TRIALS:.1f}s/trial)")
    print(f"{'='*70}\n")

    best = study.best_trial
    print(f"  Best trial: #{best.number}")
    print(f"  Best objective (utility + {margin_weight}*margin): {best.value:.4f}")
    print(f"  Best avg SNHP utility: {best.user_attrs.get('avg_snhp_util', 'N/A'):.4f}")
    print(f"  Best avg H2H margin:   {best.user_attrs.get('avg_h2h_margin', 'N/A'):+.4f}")
    print(f"  Best deal rate:        {best.user_attrs.get('avg_deal_rate', 'N/A'):.2%}")

    with open(result_path, "w") as f:
        json.dump({
            "role": role,
            "margin_weight": margin_weight,
            "best_objective": best.value,
            "best_snhp_util": best.user_attrs.get("avg_snhp_util"),
            "best_h2h_margin": best.user_attrs.get("avg_h2h_margin"),
            "best_deal_rate": best.user_attrs.get("avg_deal_rate", 0),
            "params": best.params,
            "n_trials": N_TRIALS,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    print(f"\n  Saved optimal {role} params to: {result_path}")


def make_multi_objective(role: str):
    """
    Multi-objective version of make_objective. Returns (avg_snhp_util,
    avg_h2h_margin) so NSGA-II can build a Pareto frontier instead of
    collapsing the tradeoff into a single scalar.
    """
    def objective(trial):
        params = {}
        for name, lo, hi in _PARAM_SPACE:
            params[f"{role}_{name}"] = trial.suggest_float(f"{role}_{name}", lo, hi)

        total_snhp = 0.0
        total_opp = 0.0
        total_deal = 0.0
        n_opp = 0
        for opp_name, opp_cls in B2B_OPPONENTS.items():
            _, snhp_u, opp_u, dr = _evaluate_agent(
                (params, opp_name, opp_cls, N_TUNE_ROUNDS, role)
            )
            total_snhp += snhp_u
            total_opp += opp_u
            total_deal += dr
            n_opp += 1

        avg_snhp = total_snhp / n_opp
        avg_margin = avg_snhp - total_opp / n_opp
        trial.set_user_attr("avg_snhp_util", avg_snhp)
        trial.set_user_attr("avg_h2h_margin", avg_margin)
        trial.set_user_attr("avg_deal_rate", total_deal / n_opp)
        return avg_snhp, avg_margin

    return objective


def run_pareto(role: str = ROLE_SELLER, n_trials: int = 200,
                db_path: Optional[str] = None,
                study_name: Optional[str] = None,
                result_path: Optional[str] = None):
    """
    Multi-objective Pareto optimization (NSGA-II) across (snhp_util,
    h2h_margin). Saves the full Pareto frontier to a per-role JSON for
    later inspection / point-picking. Does NOT write optimal_params.json
    directly — that's done by `pick_pareto_point()` after a frontier is
    available, since the choice of "best" depends on user preference.
    """
    print(f"\n{'='*70}")
    print(f"  SNHP Auto-Tuner — Optuna NSGA-II Multi-Objective (role={role})")
    print(f"  {n_trials} trials × {len(B2B_OPPONENTS)} opponents × {N_TUNE_ROUNDS} rounds")
    print(f"  Objectives: maximize SNHP utility AND maximize H2H margin")
    print(f"{'='*70}\n")

    db_path = db_path or f"sqlite:///snhp_tune_pareto_{role}.db"
    study_name = study_name or f"snhp-b2b-nsga2-{role}"
    result_path = result_path or os.path.join(
        os.path.dirname(__file__), f"pareto_frontier_{role}.json"
    )

    sampler = NSGAIISampler(population_size=40)
    study = optuna.create_study(
        study_name=study_name, storage=db_path,
        sampler=sampler,
        directions=["maximize", "maximize"],
        load_if_exists=True,
    )

    print(f"  Starting NSGA-II ({n_trials} trials)...\n")
    start = time.time()
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(make_multi_objective(role), n_trials=n_trials, show_progress_bar=True)
    elapsed = time.time() - start

    print(f"\n{'='*70}")
    print(f"  PARETO COMPLETE — {elapsed:.0f}s ({elapsed/n_trials:.1f}s/trial)")
    print(f"{'='*70}\n")

    pareto_points = []
    for t in study.best_trials:
        pareto_points.append({
            "trial_number": t.number,
            "snhp_util": t.values[0],
            "h2h_margin": t.values[1],
            "deal_rate": t.user_attrs.get("avg_deal_rate", 0),
            "params": t.params,
        })
    pareto_points.sort(key=lambda p: p["snhp_util"])

    print(f"  Pareto frontier: {len(pareto_points)} non-dominated points")
    print(f"  {'snhp_util':>10} {'h2h_margin':>12} {'deal_rate':>10}")
    print(f"  {'-'*10} {'-'*12} {'-'*10}")
    for p in pareto_points:
        print(f"  {p['snhp_util']:>10.4f} {p['h2h_margin']:>+12.4f} {p['deal_rate']:>10.2%}")

    with open(result_path, "w") as f:
        json.dump({
            "role": role,
            "n_trials": n_trials,
            "n_pareto_points": len(pareto_points),
            "pareto_frontier": pareto_points,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    print(f"\n  Saved frontier to: {result_path}")
    return pareto_points


def pick_pareto_point(strategy: str = "balanced") -> dict:
    """
    Pick a single (seller_params, buyer_params) configuration from the two
    saved Pareto frontiers and write it to optimal_params.json.

    Strategies:
      - "max_util":   highest SNHP utility (bottom-right of frontier)
      - "max_margin": highest head-to-head margin (top-left)
      - "balanced":   knee point — argmax of (snhp_util + h2h_margin)
                       balanced equally between the two objectives
    """
    seller_path = os.path.join(os.path.dirname(__file__), "pareto_frontier_seller.json")
    buyer_path = os.path.join(os.path.dirname(__file__), "pareto_frontier_buyer.json")
    merged_path = os.path.join(os.path.dirname(__file__), "optimal_params.json")

    merged_params: dict = {}
    metadata = {}
    for role, path in [(ROLE_SELLER, seller_path), (ROLE_BUYER, buyer_path)]:
        if not os.path.exists(path):
            print(f"  Missing {path}; skipping {role}")
            continue
        with open(path) as f:
            front = json.load(f)["pareto_frontier"]
        if not front:
            continue

        if strategy == "max_util":
            chosen = max(front, key=lambda p: p["snhp_util"])
        elif strategy == "max_margin":
            chosen = max(front, key=lambda p: p["h2h_margin"])
        elif strategy == "balanced":
            chosen = max(front, key=lambda p: p["snhp_util"] + p["h2h_margin"])
        else:
            raise ValueError(f"Unknown strategy {strategy!r}")

        merged_params.update(chosen["params"])
        metadata[role] = {
            "strategy": strategy,
            "snhp_util": chosen["snhp_util"],
            "h2h_margin": chosen["h2h_margin"],
            "deal_rate": chosen["deal_rate"],
            "trial_number": chosen["trial_number"],
        }

    with open(merged_path, "w") as f:
        json.dump({
            "params": merged_params,
            "metadata_per_role": metadata,
            "selection_strategy": strategy,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    print(f"  Wrote {len(merged_params)} params to {merged_path} (strategy={strategy})")


def merge_role_params():
    """
    Merge optimal_params_seller.json and optimal_params_buyer.json into a
    single optimal_params.json that the agent can load.
    """
    seller_path = os.path.join(os.path.dirname(__file__), "optimal_params_seller.json")
    buyer_path = os.path.join(os.path.dirname(__file__), "optimal_params_buyer.json")
    merged_path = os.path.join(os.path.dirname(__file__), "optimal_params.json")

    merged: dict = {}
    metadata = {}
    for role, path in [(ROLE_SELLER, seller_path), (ROLE_BUYER, buyer_path)]:
        if not os.path.exists(path):
            print(f"  Warning: {path} not found; skipping {role} merge")
            continue
        with open(path) as f:
            d = json.load(f)
        merged.update(d.get("params", {}))
        metadata[role] = {
            "best_utility": d.get("best_utility"),
            "best_deal_rate": d.get("best_deal_rate"),
            "n_trials": d.get("n_trials"),
            "timestamp": d.get("timestamp"),
        }

    with open(merged_path, "w") as f:
        json.dump({
            "params": merged,
            "metadata_per_role": metadata,
            "merged_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    print(f"  Merged {len(merged)} params into {merged_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SNHP CMA-ES tuner (per-role)")
    parser.add_argument("--role", choices=[ROLE_SELLER, ROLE_BUYER, "both"],
                        default=ROLE_SELLER,
                        help="Which role to tune. 'both' runs seller then buyer "
                             "and merges results into optimal_params.json.")
    parser.add_argument("--margin-weight", type=float, default=0.5,
                        help="Head-to-head margin weight α in objective "
                             "avg(SNHP) + α * avg(SNHP - opp). 0=pure utility, "
                             "0.5=balanced (default), 1.0+=h2h-dominant. "
                             "Ignored when --pareto is set.")
    parser.add_argument("--pareto", action="store_true",
                        help="Multi-objective NSGA-II Pareto search instead of "
                             "scalar CMA-ES. Saves pareto_frontier_<role>.json "
                             "instead of optimal_params_<role>.json.")
    parser.add_argument("--pareto-trials", type=int, default=200,
                        help="Trials per role for Pareto search (default 200; "
                             "NSGA-II is sample-hungrier than CMA-ES).")
    parser.add_argument("--pareto-pick", choices=["max_util", "max_margin", "balanced"],
                        default=None,
                        help="After Pareto search, pick a point and write "
                             "optimal_params.json. 'balanced' = knee point.")
    args = parser.parse_args()

    if args.pareto:
        roles = [ROLE_SELLER, ROLE_BUYER] if args.role == "both" else [args.role]
        for r in roles:
            run_pareto(r, n_trials=args.pareto_trials)
        if args.pareto_pick:
            pick_pareto_point(strategy=args.pareto_pick)
    elif args.role == "both":
        run_optimization(ROLE_SELLER, margin_weight=args.margin_weight)
        run_optimization(ROLE_BUYER, margin_weight=args.margin_weight)
        merge_role_params()
    else:
        run_optimization(args.role, margin_weight=args.margin_weight)
