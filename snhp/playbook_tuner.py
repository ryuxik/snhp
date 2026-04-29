"""
Optuna NSGA-II tuner for the per-type playbook params.

Search space: 5 params × 4 types = 20 continuous dimensions, namespaced as
`<TYPE>_<param>` (e.g. `BOULWARE_asp_start`, `CONCEDER_asp_floor`, ...).

Each trial:
  1. Constructs a candidate playbook spec from the suggested params.
  2. `playbooks.set_playbook_override(candidate)` to install it in-process.
  3. Sets SNHP_PLAYBOOK_MODE=ALL with a fixed confidence floor.
  4. Runs the full B2B round-robin (single market, paired seed_offset=0).
  5. Computes 3 objectives vs a frozen baseline tournament:
       - avg_snhp_util       (maximize)
       - elo_paired_delta    (maximize)
       - worst_case_min      (maximize — equiv to minimize worst regression)
  6. Records per-type bucketing + gate states as user attrs.

The output is a Pareto frontier (NSGA-II population). The runner picks
the candidate that passes the most regression gates AND has the highest
elo_paired_delta among gate-passers; that gets written to
snhp/playbook_optimal.json which is loaded automatically on next import.

Run:
    python -m snhp.playbook_tuner --trials 30 --n-rounds 20
    python -m snhp.playbook_tuner --quick        # N_ROUNDS=5 for fast iteration
"""
from __future__ import annotations

import argparse
import json
import os
import os.path as _op
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

# Reach into snhp/ + repo root for imports.
_SNHP_DIR = _op.dirname(_op.abspath(__file__))
_REPO_ROOT = _op.dirname(_SNHP_DIR)
sys.path.insert(0, _SNHP_DIR)
sys.path.insert(0, _REPO_ROOT)

import optuna
from optuna.samplers import NSGAIISampler

from snhp import playbooks
from snhp.eval_metrics import (  # noqa: E402
    paired_seed_elo_delta, _snhp_per_opponent,
)


# ─── Search space ───────────────────────────────────────────────────────────

# (param_name, low, high) bounds per type. Bounds derived from:
# - asp_start / asp_floor / accept_early_bar: must keep >= 0.40 to avoid
#   the agent capitulating below useful walk-away levels;
# - upper bounds for asp_start capped at 0.95 per von Neumann's
#   adaptive-opponent ceiling (above 0.95 mirrors punish faster than
#   the gain accrues);
# - commitment_margin: matches existing optuna_tuner range;
# - concession_cap: matches existing concession_cap_b2b range.
_PARAM_BOUNDS = [
    ("asp_start",         0.55, 0.95),
    ("asp_floor",         0.35, 0.85),
    ("accept_early_bar",  0.40, 0.90),
    ("commitment_margin", 0.005, 0.06),
    ("concession_cap",    0.005, 0.06),
]
_TYPES = ("BOULWARE", "CONCEDER", "MIRROR", "RANDOM")


def _suggest_playbook(trial: optuna.Trial) -> dict[str, dict[str, float]]:
    """Build a candidate playbook by suggesting all 20 params."""
    candidate = {}
    for ttype in _TYPES:
        candidate[ttype] = {}
        for name, lo, hi in _PARAM_BOUNDS:
            candidate[ttype][name] = trial.suggest_float(
                f"{ttype}_{name}", lo, hi,
            )
    # Constraint: asp_floor must be < asp_start (otherwise floor becomes a
    # hard ceiling and the curve degenerates). If suggested floor >= start,
    # cap the floor at start − 0.05.
    for ttype in _TYPES:
        s = candidate[ttype]["asp_start"]
        if candidate[ttype]["asp_floor"] >= s:
            candidate[ttype]["asp_floor"] = max(0.35, s - 0.05)
    # Always include the HONEST baseline so compose_belief_weighted_params
    # can reach it via the residual UNKNOWN mass.
    candidate["HONEST"] = dict(playbooks._PLAYBOOKS["HONEST"])
    return candidate


# ─── Tournament evaluation ──────────────────────────────────────────────────


def _baseline_tournament(n_rounds: int) -> dict:
    """Run a single mode=OFF tournament to anchor paired-seed comparisons.
    Returns rankings + pairwise. Cached across trials within one tuner run."""
    saved_mode = os.environ.get("SNHP_PLAYBOOK_MODE")
    os.environ["SNHP_PLAYBOOK_MODE"] = "OFF"
    try:
        import importlib
        if "b2b_round_robin" in sys.modules:
            importlib.reload(sys.modules["b2b_round_robin"])
        import b2b_round_robin as trnmt
        trnmt.N_ROUNDS = n_rounds
        rankings, pairwise, scores = trnmt.run_round_robin(seed_offset=0)
    finally:
        if saved_mode is None:
            os.environ.pop("SNHP_PLAYBOOK_MODE", None)
        else:
            os.environ["SNHP_PLAYBOOK_MODE"] = saved_mode
    return {"rankings": rankings, "pairwise": dict(pairwise),
             "scores": {k: list(v) for k, v in scores.items()}}


def _candidate_tournament(candidate_playbook: dict, n_rounds: int,
                           confidence_min: float) -> dict:
    """Run a tournament with the candidate playbook installed."""
    saved = {
        k: os.environ.get(k) for k in
        ("SNHP_PLAYBOOK_MODE", "SNHP_CONFIDENCE_MIN")
    }
    os.environ["SNHP_PLAYBOOK_MODE"] = "ALL"
    os.environ["SNHP_CONFIDENCE_MIN"] = str(confidence_min)
    playbooks.set_playbook_override(candidate_playbook)
    try:
        import importlib
        if "b2b_round_robin" in sys.modules:
            importlib.reload(sys.modules["b2b_round_robin"])
        import b2b_round_robin as trnmt
        trnmt.N_ROUNDS = n_rounds
        rankings, pairwise, scores = trnmt.run_round_robin(seed_offset=0)
    finally:
        playbooks.set_playbook_override(None)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return {"rankings": rankings, "pairwise": dict(pairwise),
             "scores": {k: list(v) for k, v in scores.items()}}


# ─── Multi-objective ────────────────────────────────────────────────────────


def make_multi_objective(baseline: dict, n_rounds: int,
                          confidence_min: float):
    """Returns an Optuna multi-objective callable that returns a 3-tuple:
       (avg_snhp_util, elo_paired_delta, min_per_opp_delta)
    All three are maximized."""
    base_snhp_per_opp = _snhp_per_opponent(baseline["pairwise"], "SNHP")
    base_avg = next(
        (r["avg"] for r in baseline["rankings"] if r["name"] == "SNHP"), 0.0
    )

    def objective(trial):
        candidate = _suggest_playbook(trial)
        try:
            cand = _candidate_tournament(candidate, n_rounds, confidence_min)
        except Exception as e:
            # Tournament failure → bottom of all 3 objectives.
            trial.set_user_attr("error", f"{type(e).__name__}: {e}")
            return 0.0, -1000.0, -1.0

        # Headline: SNHP avg utility
        avg = next(
            (r["avg"] for r in cand["rankings"] if r["name"] == "SNHP"), 0.0
        )

        # Paired-seed Elo delta vs frozen baseline
        elo = paired_seed_elo_delta(
            baseline["pairwise"], cand["pairwise"], target_player="SNHP",
        )["delta"]

        # Worst-case per-opponent delta (we want to MAXIMIZE the minimum)
        cand_snhp_per_opp = _snhp_per_opponent(cand["pairwise"], "SNHP")
        per_opp_deltas = []
        for opp, base_u in base_snhp_per_opp.items():
            cand_u = cand_snhp_per_opp.get(opp, base_u)
            per_opp_deltas.append(cand_u - base_u)
        worst_case = min(per_opp_deltas) if per_opp_deltas else 0.0

        # Diagnostic attrs
        trial.set_user_attr("avg", round(avg, 4))
        trial.set_user_attr("avg_delta", round(avg - base_avg, 4))
        trial.set_user_attr("elo_delta", round(elo, 1))
        trial.set_user_attr("worst_case_delta", round(worst_case, 4))
        trial.set_user_attr(
            "n_opponents_regressed",
            sum(1 for d in per_opp_deltas if d < -0.005),
        )

        return avg, elo, worst_case

    return objective


# ─── Driver ─────────────────────────────────────────────────────────────────


def _pick_best_candidate(study: optuna.study.Study,
                          gate_min_avg_drop_pct: float = -1.0,
                          gate_min_worst_case: float = -0.01,
                          gate_max_elo_drop: float = -10.0) -> Optional[optuna.trial.FrozenTrial]:
    """From the Pareto front, pick the candidate that:
      1. Passes all 3 hard gates (avg_drop, worst_case, elo).
      2. Among gate-passers, maximizes elo_delta.
      3. If no gate-passer exists, fall back to highest-avg trial.
    """
    completed = [t for t in study.trials
                  if t.state == optuna.trial.TrialState.COMPLETE]
    if not completed:
        return None

    def gates_pass(t):
        avg_d = t.user_attrs.get("avg_delta")
        wc = t.user_attrs.get("worst_case_delta")
        elo = t.user_attrs.get("elo_delta")
        if avg_d is None or wc is None or elo is None:
            return False
        # avg_drop_pct ≥ −1.0% — i.e., delta ≥ -0.01 × baseline_avg ≈ -0.005
        return (avg_d >= -0.005 and wc >= gate_min_worst_case
                and elo >= gate_max_elo_drop)

    passers = [t for t in completed if gates_pass(t)]
    if passers:
        return max(passers, key=lambda t: t.user_attrs["elo_delta"])
    # Fallback: highest avg
    return max(completed, key=lambda t: t.user_attrs.get("avg", 0.0))


def _build_playbook_from_trial(trial: optuna.trial.FrozenTrial
                                ) -> dict[str, dict[str, float]]:
    """Reconstruct the playbook dict from a trial's params."""
    pb = {ttype: {} for ttype in _TYPES}
    for key, val in trial.params.items():
        ttype, _, name = key.partition("_")
        if ttype in pb and name:
            pb[ttype][name] = round(float(val), 4)
    # Apply asp_floor < asp_start guard (same as suggest)
    for ttype in _TYPES:
        s = pb[ttype].get("asp_start", 0.95)
        if pb[ttype].get("asp_floor", 0.0) >= s:
            pb[ttype]["asp_floor"] = round(max(0.35, s - 0.05), 4)
    pb["HONEST"] = dict(playbooks._PLAYBOOKS["HONEST"])
    return pb


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trials", type=int, default=30,
                    help="Number of Optuna trials. Default 30 (~15 min at "
                         "N=20). Use 50-100 for fuller Pareto exploration.")
    p.add_argument("--quick", action="store_true",
                    help="N_ROUNDS=5 (fast iteration, but 5x noisier — only "
                         "for sanity-checking the harness).")
    p.add_argument("--n-rounds", type=int, default=None,
                    help="Override N_ROUNDS explicitly.")
    p.add_argument("--confidence-min", type=float, default=0.65,
                    help="Confidence floor for ALL playbook mode (0.65 default).")
    p.add_argument("--out", type=str,
                    default=_op.join(_SNHP_DIR, "playbook_optimal.json"),
                    help="Output JSON path for the best playbook.")
    p.add_argument("--db-path", type=str, default=None,
                    help="Optuna SQLite path (default: in-memory ephemeral).")
    args = p.parse_args()

    n_rounds = args.n_rounds if args.n_rounds is not None else (5 if args.quick else 20)

    print(f"=== Playbook tuner — {args.trials} trials × N_ROUNDS={n_rounds} ===")
    print(f"  Search space: 5 params × 4 types = 20 dims (NSGA-II)")
    print(f"  Confidence floor: {args.confidence_min}")
    print(f"  Output: {args.out}")
    print()
    print(f"Step 1/3: Running baseline tournament for paired-seed Elo anchor...")
    t_base_start = time.time()
    baseline = _baseline_tournament(n_rounds)
    base_avg = next(
        r["avg"] for r in baseline["rankings"] if r["name"] == "SNHP"
    )
    print(f"  Baseline SNHP avg utility = {base_avg:.4f}  "
          f"(wall {time.time() - t_base_start:.1f}s)")

    print(f"\nStep 2/3: NSGA-II search ({args.trials} trials)...")
    db_path = args.db_path
    storage = f"sqlite:///{db_path}" if db_path else None
    sampler = NSGAIISampler(population_size=min(20, args.trials // 2 + 4),
                             seed=42)
    study = optuna.create_study(
        directions=["maximize", "maximize", "maximize"],   # avg, elo, worst_case
        sampler=sampler, storage=storage,
        load_if_exists=(storage is not None),
    )
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    obj = make_multi_objective(baseline, n_rounds, args.confidence_min)
    t_search_start = time.time()
    study.optimize(obj, n_trials=args.trials, show_progress_bar=False)
    search_wall = time.time() - t_search_start
    print(f"  Search complete. Wall: {search_wall:.0f}s "
          f"({search_wall / args.trials:.1f}s/trial avg)")

    print(f"\nStep 3/3: Picking best gate-passing candidate...")
    best = _pick_best_candidate(study)
    if best is None:
        print("  ❌ No completed trials; aborting.")
        sys.exit(1)
    print(f"  Trial #{best.number}:  "
          f"avg={best.user_attrs['avg']:.4f}  "
          f"avg_delta={best.user_attrs['avg_delta']:+.4f}  "
          f"elo_delta={best.user_attrs['elo_delta']:+.1f}  "
          f"worst_case={best.user_attrs['worst_case_delta']:+.4f}")
    print(f"  Trial passed gates: avg_d≥-0.005, worst≥-0.01, elo≥-10? "
          f"{(best.user_attrs['avg_delta'] >= -0.005 and best.user_attrs['worst_case_delta'] >= -0.01 and best.user_attrs['elo_delta'] >= -10)}")

    candidate = _build_playbook_from_trial(best)
    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_trials": args.trials,
        "n_rounds": n_rounds,
        "confidence_min": args.confidence_min,
        "trial_number": best.number,
        "user_attrs": dict(best.user_attrs),
        **candidate,
    }
    with open(args.out, "w") as f:
        json.dump(artifact, f, sort_keys=True, indent=2)
        f.write("\n")
    print(f"\nWrote tuned playbook → {args.out}")
    print(f"  → re-import snhp.playbooks to load (or restart any tournament).")


if __name__ == "__main__":
    main()
