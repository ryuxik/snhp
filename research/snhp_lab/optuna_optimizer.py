#!/usr/bin/env python3
"""
SNHP Optuna Hyperparameter Optimizer
=====================================
Runs Bayesian optimization over the key SNHP parameters using the full
tournament as the objective. Designed to run in the background while
Phase 2 development continues.

Usage:
    python optuna_optimizer.py [--n-trials 200] [--n-rounds 20]
"""

import optuna
import json
import time
import sys
import os
import numpy as np
from datetime import datetime

# Suppress optuna logging noise
optuna.logging.set_verbosity(optuna.logging.WARNING)

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from b2b_round_robin import (
    create_issues, create_ufuns, play_matchup, BATNA_CENTER,
)
from b2b_opponents import B2B_OPPONENTS
from negmas.sao.negotiators import AspirationNegotiator
from negmas_agent import SNHPAgent, CrossSessionMemory
import negmas_agent


def objective(trial):
    """Single trial: set SNHP params, run mini-tournament, return avg utility."""
    
    # Parameters to optimize
    params = {
        'aspiration_start': trial.suggest_float('aspiration_start', 0.55, 0.72, step=0.01),
        'aspiration_floor': trial.suggest_float('aspiration_floor', 0.40, 0.50, step=0.01),
        'probe_target': trial.suggest_float('probe_target', 0.50, 0.68, step=0.01),
        'accept_early_bar': trial.suggest_float('accept_early_bar', 0.48, 0.58, step=0.01),
        'accept_early_cutoff': trial.suggest_float('accept_early_cutoff', 0.15, 0.40, step=0.01),
        'accept_late_bottom': trial.suggest_float('accept_late_bottom', 0.38, 0.48, step=0.01),
        'accept_late_start': trial.suggest_float('accept_late_start', 0.50, 0.70, step=0.01),
        'accept_late_curve': trial.suggest_float('accept_late_curve', 0.40, 0.80, step=0.02),
        'time_floor_rate': trial.suggest_float('time_floor_rate', 0.80, 1.30, step=0.02),
        'zeuthen_concession_scale': trial.suggest_float('zeuthen_concession_scale', 0.03, 0.10, step=0.005),
        'concession_cap_b2b': trial.suggest_float('concession_cap_b2b', 0.02, 0.06, step=0.002),
        'best_seen_time': trial.suggest_float('best_seen_time', 0.50, 0.75, step=0.05),
        'emergency_time': trial.suggest_float('emergency_time', 0.65, 0.85, step=0.02),
    }
    
    issues = create_issues()
    n_rounds = int(os.environ.get('OPTUNA_N_ROUNDS', '20'))
    
    total_utils = []
    
    # Run against all opponents with randomized ufuns
    all_opponents = list(B2B_OPPONENTS.items()) + [('Aspiration', AspirationNegotiator)]
    
    for opp_name, opp_cls in all_opponents:
        match_utils = []
        for seed in range(n_rounds):
            np.random.seed(seed * 1000 + trial.number)
            ufun_a, ufun_b = create_ufuns(issues, 10, randomize_weights=True)
            
            # Fresh memory per negotiation
            negmas_agent._global_memory = CrossSessionMemory()
            
            from negmas import SAOMechanism
            mech = SAOMechanism(issues=issues, n_steps=10)
            
            # Create SNHP with trial params
            agent = SNHPAgent(name='snhp')
            # Inject params via the tuned_params override
            agent._tuned_params = params
            
            opp = opp_cls(name='opp')
            mech.add(agent, ufun=ufun_a)
            mech.add(opp, ufun=ufun_b)
            
            result = mech.run()
            
            if result.agreement:
                u = float(ufun_a(result.agreement))
                match_utils.append(u)
            else:
                # Walkaway: use BATNA-weighted expected value
                match_utils.append(float(ufun_a.reserved_value or 0.0) * 0.4)
        
        avg_u = sum(match_utils) / len(match_utils) if match_utils else 0.0
        total_utils.append(avg_u)
    
    overall = sum(total_utils) / len(total_utils)
    return overall


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SNHP Optuna Optimizer')
    parser.add_argument('--n-trials', type=int, default=200, help='Number of trials')
    parser.add_argument('--n-rounds', type=int, default=15, help='Rounds per matchup')
    parser.add_argument('--db', type=str, default='optuna_snhp.db', help='SQLite DB path')
    args = parser.parse_args()
    
    os.environ['OPTUNA_N_ROUNDS'] = str(args.n_rounds)
    
    study = optuna.create_study(
        study_name='snhp_v2',
        direction='maximize',
        storage=f'sqlite:///{args.db}',
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    
    print(f"[{datetime.now().isoformat()}] Starting Optuna optimization")
    print(f"  Trials: {args.n_trials}, Rounds/matchup: {args.n_rounds}")
    print(f"  DB: {args.db}")
    print(f"  Previous trials: {len(study.trials)}")
    print()
    
    start = time.time()
    
    try:
        study.optimize(objective, n_trials=args.n_trials, show_progress_bar=False)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Saving best results so far...")
    
    elapsed = time.time() - start
    
    print(f"\n{'='*60}")
    print(f"  OPTUNA RESULTS ({len(study.trials)} trials, {elapsed:.0f}s)")
    print(f"{'='*60}")
    print(f"  Best value: {study.best_value:.4f}")
    print(f"  Best params:")
    for k, v in sorted(study.best_params.items()):
        print(f"    {k}: {v}")
    
    # Save best params
    results = {
        'best_value': study.best_value,
        'best_params': study.best_params,
        'n_trials': len(study.trials),
        'timestamp': datetime.now().isoformat(),
    }
    
    with open('optuna_best_params.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n  Saved to optuna_best_params.json")


if __name__ == '__main__':
    main()
