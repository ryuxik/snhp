#!/usr/bin/env python3
"""
SNHP Extraction Benchmark
===========================
Runs 200 emails through the extraction pipeline and measures accuracy.

Usage:
    python extraction_benchmark.py --model gpt-4o-mini --n-seeds 3
    python extraction_benchmark.py --model gemini/gemini-2.0-flash --n-seeds 3
    python extraction_benchmark.py --dry-run  # Show stats without LLM calls
"""

import os
import sys
import json
import time
import argparse
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extraction_benchmark_data import BENCHMARK_EMAILS


# ──────────────────────────────────────────────
# Accuracy metrics
# ──────────────────────────────────────────────

@dataclass
class FieldResult:
    """Result for a single field extraction."""
    field: str
    expected: Optional[float]
    extracted: Optional[float]
    is_correct: bool  # Within tolerance
    is_present: bool  # Field was non-null in extraction


def check_numeric_field(expected, extracted, tolerance=0.05):
    """Check if extracted value is within ±tolerance of expected."""
    if expected is None:
        return True  # Can't be wrong if we don't have ground truth
    if extracted is None:
        return False  # Missing extraction = wrong
    if expected == 0:
        return abs(extracted) < 1.0  # Close to zero
    return abs(extracted - expected) / abs(expected) <= tolerance


def evaluate_extraction(ground_truth: dict, extracted: dict) -> list:
    """Compare extracted fields against ground truth, return per-field results."""
    
    # Mapping: ground_truth key → extractor output key
    field_mapping = {
        # Core fields (must be >90%)
        "free_hourly_rate": "free_hourly_rate",
        "free_hourly_batna": "free_hourly_batna",
        "free_min_total": "free_minimum_batna_price",
        
        # Secondary fields (must be >75%)
        "free_duration_days": "free_duration_days",
        "free_max_hours_per_day": "free_max_hours_per_day",
        "free_revisions": "free_revisions",
        "client_budget": "client_explicit_budget",
        "client_rate_offer": "client_explicit_hourly_rate",
        "client_timeline_days": "client_timeline_days",
    }
    
    results = []
    for gt_key, ext_key in field_mapping.items():
        expected = ground_truth.get(gt_key)
        raw_extracted = extracted.get(ext_key)
        
        # Normalize to float
        try:
            extracted_val = float(raw_extracted) if raw_extracted is not None else None
        except (ValueError, TypeError):
            extracted_val = None
        
        try:
            expected_val = float(expected) if expected is not None else None
        except (ValueError, TypeError):
            expected_val = None
        
        is_correct = check_numeric_field(expected_val, extracted_val, tolerance=0.10)
        
        results.append(FieldResult(
            field=gt_key,
            expected=expected_val,
            extracted=extracted_val,
            is_correct=is_correct,
            is_present=extracted_val is not None,
        ))
    
    return results


def compute_stats(all_results: list) -> dict:
    """Compute per-field and overall accuracy from a list of FieldResult lists."""
    
    field_stats = defaultdict(lambda: {"correct": 0, "total": 0, "present": 0})
    
    for result_list in all_results:
        for r in result_list:
            if r.expected is not None:  # Only count fields where we have ground truth
                field_stats[r.field]["total"] += 1
                if r.is_correct:
                    field_stats[r.field]["correct"] += 1
                if r.is_present:
                    field_stats[r.field]["present"] += 1
    
    # Core vs secondary
    core_fields = {"free_hourly_rate", "free_hourly_batna", "free_min_total", "client_budget"}
    secondary_fields = {"free_duration_days", "free_max_hours_per_day", "free_revisions", 
                        "client_rate_offer", "client_timeline_days"}
    
    core_correct = sum(field_stats[f]["correct"] for f in core_fields if field_stats[f]["total"] > 0)
    core_total = sum(field_stats[f]["total"] for f in core_fields if field_stats[f]["total"] > 0)
    
    sec_correct = sum(field_stats[f]["correct"] for f in secondary_fields if field_stats[f]["total"] > 0)
    sec_total = sum(field_stats[f]["total"] for f in secondary_fields if field_stats[f]["total"] > 0)
    
    # Binomial CI
    def binomial_ci(k, n, z=1.96):
        if n == 0:
            return 0.0, 0.0, 0.0
        p = k / n
        se = (p * (1 - p) / n) ** 0.5
        return p, max(0, p - z * se), min(1, p + z * se)
    
    core_acc, core_lo, core_hi = binomial_ci(core_correct, core_total)
    sec_acc, sec_lo, sec_hi = binomial_ci(sec_correct, sec_total)
    
    return {
        "field_stats": dict(field_stats),
        "core_accuracy": core_acc,
        "core_ci": (core_lo, core_hi),
        "core_n": core_total,
        "secondary_accuracy": sec_acc,
        "secondary_ci": (sec_lo, sec_hi),
        "secondary_n": sec_total,
    }


# ──────────────────────────────────────────────
# Main benchmark runner
# ──────────────────────────────────────────────

def run_benchmark(model: str, n_seeds: int = 1, max_emails: int = None, dry_run: bool = False):
    """Run the full extraction benchmark."""
    
    emails = BENCHMARK_EMAILS[:max_emails] if max_emails else BENCHMARK_EMAILS
    
    print(f"{'='*70}")
    print(f"  SNHP EXTRACTION BENCHMARK")
    print(f"  Model: {model}")
    print(f"  Emails: {len(emails)} | Seeds: {n_seeds}")
    print(f"{'='*70}\n")
    
    if dry_run:
        # Just show dataset statistics
        print("DRY RUN — showing dataset statistics only\n")
        categories = defaultdict(int)
        for e in emails:
            categories[e["category"]] += 1
        for cat, count in sorted(categories.items()):
            print(f"  {cat:<15} {count} emails")
        
        # Show ground truth coverage
        field_coverage = defaultdict(int)
        for e in emails:
            for k, v in e["ground_truth"].items():
                if v is not None:
                    field_coverage[k] += 1
        print(f"\n  Ground truth coverage:")
        for field, count in sorted(field_coverage.items()):
            print(f"    {field:<25} {count}/{len(emails)} ({count/len(emails):.0%})")
        return
    
    # Import the extractor
    os.environ["SNHP_LLM_MODEL"] = model
    from llm_extractor import extract_all_parameters
    
    all_seed_stats = []
    
    for seed in range(n_seeds):
        print(f"\n{'─'*50}")
        print(f"  Seed {seed + 1}/{n_seeds}")
        print(f"{'─'*50}")
        
        all_results = []
        errors = 0
        latencies = []
        
        for i, entry in enumerate(emails):
            t0 = time.time()
            
            # Retry with exponential backoff for rate limits
            extracted = None
            last_err = None
            for attempt in range(3):
                try:
                    extracted = extract_all_parameters(
                        entry["client_email"], 
                        entry["freelancer_constraints"]
                    )
                    break
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        wait = 2 ** (attempt + 1)  # 2s, 4s
                        time.sleep(wait)
            
            if extracted is None:
                errors += 1
                print(f"  [{i+1:3d}/{len(emails)}] {entry['id']:<20} ERROR after 3 retries: {last_err}", flush=True)
                continue
            
            latency = time.time() - t0
            latencies.append(latency)
            
            results = evaluate_extraction(entry["ground_truth"], extracted)
            all_results.append(results)
            
            # Progress — log EVERY email
            n_correct = sum(1 for r in results if r.is_correct)
            n_total = sum(1 for r in results if r.expected is not None)
            status = "✓" if n_correct == n_total else "✗"
            print(f"  [{i+1:3d}/{len(emails)}] {entry['id']:<20} {n_correct}/{n_total} fields {status} ({latency:.1f}s)", flush=True)
            
            # Rate limit protection: 0.5s delay between calls
            time.sleep(0.5)
        
        stats = compute_stats(all_results)
        all_seed_stats.append(stats)
        
        print(f"\n  Seed {seed+1} Results:")
        print(f"  Core accuracy:      {stats['core_accuracy']:.1%} [{stats['core_ci'][0]:.1%}, {stats['core_ci'][1]:.1%}] (N={stats['core_n']})")
        print(f"  Secondary accuracy: {stats['secondary_accuracy']:.1%} [{stats['secondary_ci'][0]:.1%}, {stats['secondary_ci'][1]:.1%}] (N={stats['secondary_n']})")
        print(f"  Errors: {errors}/{len(emails)}")
        if latencies:
            print(f"  Latency: mean={sum(latencies)/len(latencies):.2f}s, p95={sorted(latencies)[int(len(latencies)*0.95)]:.2f}s")
        
        print(f"\n  Per-field breakdown:")
        for field, fs in sorted(stats["field_stats"].items()):
            if fs["total"] > 0:
                acc = fs["correct"] / fs["total"]
                print(f"    {field:<25} {acc:5.1%} ({fs['correct']}/{fs['total']})")
    
    # Cross-seed summary
    if n_seeds > 1:
        print(f"\n{'='*70}")
        print(f"  CROSS-SEED SUMMARY ({n_seeds} seeds)")
        print(f"{'='*70}")
        
        core_accs = [s["core_accuracy"] for s in all_seed_stats]
        sec_accs = [s["secondary_accuracy"] for s in all_seed_stats]
        
        import numpy as np
        print(f"  Core accuracy:      mean={np.mean(core_accs):.1%} ± {np.std(core_accs):.1%}")
        print(f"  Secondary accuracy: mean={np.mean(sec_accs):.1%} ± {np.std(sec_accs):.1%}")
        
        cv_core = np.std(core_accs) / np.mean(core_accs) if np.mean(core_accs) > 0 else 0
        cv_sec = np.std(sec_accs) / np.mean(sec_accs) if np.mean(sec_accs) > 0 else 0
        print(f"  Intra-model CV:     core={cv_core:.1%}, secondary={cv_sec:.1%}")
        print(f"  Target: CV < 5%     {'PASS' if cv_core < 0.05 else 'FAIL'}")
    
    # Save results
    results_file = f"extraction_benchmark_{model.replace('/', '_')}.json"
    with open(results_file, "w") as f:
        json.dump({
            "model": model,
            "n_emails": len(emails),
            "n_seeds": n_seeds,
            "seeds": [
                {
                    "core_accuracy": s["core_accuracy"],
                    "core_ci": s["core_ci"],
                    "secondary_accuracy": s["secondary_accuracy"],
                    "secondary_ci": s["secondary_ci"],
                    "per_field": {k: {"accuracy": v["correct"]/v["total"] if v["total"] > 0 else None, "n": v["total"]} 
                                 for k, v in s["field_stats"].items()},
                }
                for s in all_seed_stats
            ],
        }, f, indent=2)
    print(f"\n  Saved to {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SNHP Extraction Benchmark")
    parser.add_argument("--model", type=str, default="gemini/gemini-3-flash-preview", help="LLM model name")
    parser.add_argument("--n-seeds", type=int, default=1, help="Number of seeds to run")
    parser.add_argument("--max-emails", type=int, default=None, help="Limit emails for testing")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without LLM calls")
    args = parser.parse_args()
    
    run_benchmark(args.model, args.n_seeds, args.max_emails, args.dry_run)
