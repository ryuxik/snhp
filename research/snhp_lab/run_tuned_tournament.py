"""
Run the b2b_round_robin tournament with Optuna-tuned SNHP parameters.

Loads `optimal_params.json` (produced by optuna_tuner.py) and injects them
into the SNHP agent before running the round-robin. Useful after a retune
to verify the new parameters in the full evaluation harness.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import negmas_agent
from b2b_round_robin import run_round_robin


def main():
    params_path = os.path.join(os.path.dirname(__file__), "optimal_params.json")
    if not os.path.exists(params_path):
        print(f"No optimal_params.json found at {params_path}; running with defaults.")
    else:
        with open(params_path) as f:
            data = json.load(f)
        params = data.get("params") or data
        negmas_agent._TUNE_PARAMS = params
        print(f"Loaded {len(params)} tuned parameters from {params_path}")
        print(f"Best validation utility from tuning run: "
              f"{data.get('best_utility', 'N/A')}")

    run_round_robin()


if __name__ == "__main__":
    main()
