"""
SNHP Eval Cost Estimator.

Pre-experiment cost analysis for running SNHP evaluation against
CraigslistBargains and PACT datasets.

Usage:
    python eval_cost_estimator.py
    python eval_cost_estimator.py --dataset craigslist --sample-size 500
    python eval_cost_estimator.py --dataset pact --sample-size 200 --rounds 10
"""

import argparse
import math
import json


# ─── Gemini API Pricing (April 2026) ───

PRICING = {
    "gemini-3-flash-preview": {
        "label": "Gemini 3 Flash Preview",
        "input_per_1m": 0.30,
        "output_per_1m": 2.50,
    },
    "gemini-2.5-flash": {
        "label": "Gemini 2.5 Flash",
        "input_per_1m": 0.30,
        "output_per_1m": 2.50,
    },
    "gemini-2.5-flash-lite": {
        "label": "Gemini 2.5 Flash Lite",
        "input_per_1m": 0.10,
        "output_per_1m": 0.40,
    },
    "gemini-3-pro-preview": {
        "label": "Gemini 3 Pro Preview",
        "input_per_1m": 1.25,
        "output_per_1m": 10.00,
    },
}


# ─── SNHP Token Estimates Per Call ───

# Each SNHP evaluation makes 3 LLM calls:
#   1. extract_utility_from_email     (~300 input, ~100 output tokens)
#   2. extract_client_constraints     (~300 input, ~80 output tokens)
#   3. extract_freelancer_constraints (~250 input, ~100 output tokens)
#   4. generate_decoder_email         (~400 input, ~150 output tokens) [if Path B]
#
# Total per single evaluation:
TOKENS_PER_EVAL = {
    "input": 1250,   # ~1.25K input tokens per call
    "output": 430,   # ~430 output tokens per call
}

# For PACT multi-round: each round adds another evaluation cycle
ADDITIONAL_ROUND_TOKENS = {
    "input": 800,    # Shorter — just the counter-offer extraction
    "output": 300,
}


# ─── Dataset Characteristics ───

DATASETS = {
    "craigslist": {
        "label": "CraigslistBargains",
        "total_dialogues": 6682,
        "description": "Stanford NLP buyer-seller dialogues with ground truth prices.",
        "format": "Single-shot evaluation: feed listing + buyer target → measure bid quality.",
        "evals_per_sample": 1,  # One SNHP eval per dialogue
        "rounds_per_sample": 1,
    },
    "pact": {
        "label": "PACT Bilateral Bargaining",
        "total_games": 1000,
        "description": "LLM vs LLM negotiation games (20-round matches).",
        "format": "Multi-round: SNHP plays one side against an LLM opponent.",
        "evals_per_sample": 1,   # Initial eval
        "default_rounds": 10,    # Up to 10 counter-offer rounds
    },
}


# ─── Power Analysis ───

def compute_sample_size(
    effect_size: float = 0.3,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """
    Compute minimum sample size for a two-sample t-test.

    Uses the approximation:
        n ≈ 2 × ((z_alpha/2 + z_beta) / effect_size)²

    where effect_size is Cohen's d.

    Demis Hassabis principle: "If you can't measure it rigorously,
    you can't improve it systematically."
    """
    # z-scores for common alpha and power values
    z_alpha = {0.01: 2.576, 0.05: 1.960, 0.10: 1.645}.get(alpha, 1.960)
    z_beta = {0.80: 0.842, 0.85: 1.036, 0.90: 1.282, 0.95: 1.645}.get(power, 0.842)

    n = 2 * ((z_alpha + z_beta) / effect_size) ** 2
    return math.ceil(n)


def estimate_cost(
    dataset: str,
    sample_size: int,
    rounds: int,
    model: str,
    repetitions: int = 1,
) -> dict:
    """Estimate total API cost for an eval run."""
    pricing = PRICING[model]

    if dataset == "craigslist":
        total_input = sample_size * TOKENS_PER_EVAL["input"] * repetitions
        total_output = sample_size * TOKENS_PER_EVAL["output"] * repetitions
    elif dataset == "pact":
        # Initial eval + N rounds of counter-offers
        per_game_input = (
            TOKENS_PER_EVAL["input"]
            + (rounds - 1) * ADDITIONAL_ROUND_TOKENS["input"]
        )
        per_game_output = (
            TOKENS_PER_EVAL["output"]
            + (rounds - 1) * ADDITIONAL_ROUND_TOKENS["output"]
        )
        total_input = sample_size * per_game_input * repetitions
        total_output = sample_size * per_game_output * repetitions
    else:
        raise ValueError(f"Unknown dataset: {dataset}")

    input_cost = (total_input / 1_000_000) * pricing["input_per_1m"]
    output_cost = (total_output / 1_000_000) * pricing["output_per_1m"]
    total_cost = input_cost + output_cost

    return {
        "model": pricing["label"],
        "model_id": model,
        "dataset": DATASETS.get(dataset, {}).get("label", dataset),
        "sample_size": sample_size,
        "rounds": rounds,
        "repetitions": repetitions,
        "total_evals": sample_size * repetitions * (rounds if dataset == "pact" else 1),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "total_cost": round(total_cost, 4),
    }


def print_report(results: list, power_info: dict):
    print("=" * 70)
    print("  SNHP EVAL COST ESTIMATE")
    print("=" * 70)
    print()

    print("POWER ANALYSIS (Demis Hassabis Standard)")
    print("-" * 40)
    print(f"  Significance level (α):  {power_info['alpha']}")
    print(f"  Statistical power (1-β): {power_info['power']}")
    print(f"  Effect sizes tested:     {power_info['effect_sizes']}")
    print()

    for es, n in power_info["required_samples"].items():
        print(f"  Cohen's d = {es:<6} → min n = {n} per group")
    print()

    print("COST ESTIMATES")
    print("-" * 70)
    print(f"{'Dataset':<22} {'Model':<20} {'Samples':>7} {'Rounds':>6} "
          f"{'Tokens (M)':>10} {'Cost':>10}")
    print("-" * 70)

    grand_total = 0
    for r in results:
        total_tokens_m = (r["total_input_tokens"] + r["total_output_tokens"]) / 1_000_000
        print(f"{r['dataset']:<22} {r['model']:<20} {r['sample_size']:>7} "
              f"{r['rounds']:>6} {total_tokens_m:>10.2f} ${r['total_cost']:>9.2f}")
        grand_total += r["total_cost"]

    print("-" * 70)
    print(f"{'GRAND TOTAL':>68} ${grand_total:>9.2f}")
    print()

    # Contextual warning
    if grand_total < 1.0:
        print("✅ Estimated cost is under $1. This is well within free tier limits.")
    elif grand_total < 10.0:
        print("✅ Estimated cost is under $10. Very affordable experiment.")
    elif grand_total < 50.0:
        print("⚠️  Estimated cost is $10-$50. Consider using Flash Lite to reduce.")
    else:
        print("🚨 Estimated cost exceeds $50. Consider reducing sample size or using Batch API (50% discount).")

    print()
    return grand_total


def main():
    parser = argparse.ArgumentParser(description="SNHP Eval Cost Estimator")
    parser.add_argument("--dataset", choices=["craigslist", "pact", "both"],
                        default="both", help="Dataset to evaluate against")
    parser.add_argument("--sample-size", type=int, default=None,
                        help="Override sample size (default: power analysis minimum)")
    parser.add_argument("--rounds", type=int, default=10,
                        help="Rounds per PACT game (default: 10)")
    parser.add_argument("--model", default="gemini-3-flash-preview",
                        choices=list(PRICING.keys()))
    parser.add_argument("--effect-size", type=float, default=0.3,
                        help="Minimum effect size to detect (Cohen's d, default: 0.3)")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.80)
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Repetitions per sample (for variance estimation)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    # Power analysis
    effect_sizes = {"small": 0.2, "medium": 0.3, "large": 0.5}
    required_samples = {}
    for label, es in effect_sizes.items():
        required_samples[label] = compute_sample_size(es, args.alpha, args.power)

    target_n = args.sample_size or compute_sample_size(args.effect_size, args.alpha, args.power)

    power_info = {
        "alpha": args.alpha,
        "power": args.power,
        "effect_sizes": effect_sizes,
        "required_samples": required_samples,
        "target_n": target_n,
    }

    # Cost estimation
    results = []
    datasets_to_eval = ["craigslist", "pact"] if args.dataset == "both" else [args.dataset]

    for ds in datasets_to_eval:
        for model_id in [args.model]:
            rounds = args.rounds if ds == "pact" else 1
            r = estimate_cost(ds, target_n, rounds, model_id, args.repetitions)
            results.append(r)

    # Also compute with Flash Lite for comparison
    if args.model != "gemini-2.5-flash-lite":
        for ds in datasets_to_eval:
            rounds = args.rounds if ds == "pact" else 1
            r = estimate_cost(ds, target_n, rounds, "gemini-2.5-flash-lite", args.repetitions)
            results.append(r)

    if args.json:
        print(json.dumps({"power_analysis": power_info, "estimates": results}, indent=2))
    else:
        print_report(results, power_info)


if __name__ == "__main__":
    main()
