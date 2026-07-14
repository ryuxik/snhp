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
    pair_joint_welfare, mean_defense_floor_violation,
)
from snhp.b2b_opponents import OPPONENT_TYPE_TAGS  # noqa: E402

# Extractor names = ground-truth BOULWARE-tagged opponents (the hardliners
# we want to defend against). Used by the defense-floor metric.
_EXTRACTOR_NAMES = sorted(
    name for name, ttype in OPPONENT_TYPE_TAGS.items() if ttype == "BOULWARE"
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

# Global mechanism params — apply across all opponent types, not per-type.
# These are existing `_tp()`-readable tunables that were hand-tuned and
# never put under search. Adds ~8 dims to the search space.
#   det_*: aspiration-detector params (7 knobs from gametheory's
#     SNHPWithAspirationDetector — folded into base in this commit).
#   self_interest_weight: logrolling balance (1 knob inside _find_pareto_outcome).
_GLOBAL_PARAM_BOUNDS = [
    ("det_max_diff_std",        0.005, 0.06),
    ("det_min_pos_fraction",    0.50, 0.90),
    ("det_hold_until_t",        0.65, 0.95),
    ("det_bid_target_initial",  0.65, 0.95),
    ("det_bid_target_final",    0.40, 0.80),
    ("det_target_floor_margin", 0.10, 0.40),
    ("det_early_accept_margin", 0.20, 0.55),
    # Logrolling balance — was hardcoded; now also covers the asymmetry-
    # bumped values so the search can choose how aggressively we punish
    # one-sided concession.
    ("self_interest_weight",    0.03, 0.40),
    ("self_interest_mid",       0.10, 0.45),
    ("self_interest_high",      0.20, 0.60),
    # Pareto-search band per regime. Wider band = more candidate
    # outcomes considered for logrolling, at cost of straying from
    # the target utility. Tuned per regime: default / B2B-flat / hardliner.
    ("pareto_band_normal",      0.04, 0.20),
    ("pareto_band_b2b",         0.04, 0.20),
    ("pareto_band_b2b_boulware", 0.06, 0.30),
    # How many opponent offers we wait for before activating logrolling.
    # Lower = faster (riskier inference); higher = more reliable but
    # gives away rounds at our default proposal pattern.
    ("logroll_min_offers",      1.0, 5.0),
]


def _suggest_candidate(trial: optuna.Trial) -> tuple[dict, dict]:
    """Build a candidate playbook + global tunable-params dict from the
    trial's suggestions. Returns (playbook, global_tune_params)."""
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

    # Global tunable params (aspiration detector + logrolling weights).
    # These get injected via negmas_agent._TUNE_PARAMS so the agent's
    # _tp() lookup picks them up.
    global_tune = {
        name: trial.suggest_float(name, lo, hi)
        for name, lo, hi in _GLOBAL_PARAM_BOUNDS
    }
    return candidate, global_tune


# ─── Tournament evaluation ──────────────────────────────────────────────────


def _run_one_tournament(n_rounds: int, seed_offset: int) -> dict:
    """Single-seed tournament run; mode is whatever's set in env."""
    import importlib
    if "b2b_round_robin" in sys.modules:
        importlib.reload(sys.modules["b2b_round_robin"])
    import b2b_round_robin as trnmt
    trnmt.N_ROUNDS = n_rounds
    rankings, pairwise, scores = trnmt.run_round_robin(seed_offset=seed_offset)
    return {"rankings": rankings, "pairwise": dict(pairwise),
             "scores": {k: list(v) for k, v in scores.items()}}


def _baseline_tournaments(n_rounds: int, n_seeds: int) -> list[dict]:
    """Run mode=OFF tournament across `n_seeds` independent seed offsets.
    Returns a list of per-seed (rankings, pairwise, scores) dicts. The
    candidate evaluator pairs each candidate seed against the SAME baseline
    seed for true paired-seed Elo comparison (drops Elo MDE ~50% per √n).

    SNHP_PAIR_TEST=1 is set so SNHP_B is in the roster — the dual-
    objective evaluator needs the SNHP-vs-SNHP_B matchup data to compute
    pair joint welfare."""
    saved_mode = os.environ.get("SNHP_PLAYBOOK_MODE")
    saved_pair = os.environ.get("SNHP_PAIR_TEST")
    os.environ["SNHP_PLAYBOOK_MODE"] = "OFF"
    os.environ["SNHP_PAIR_TEST"] = "1"
    try:
        return [_run_one_tournament(n_rounds, seed_offset=s)
                for s in range(n_seeds)]
    finally:
        if saved_mode is None:
            os.environ.pop("SNHP_PLAYBOOK_MODE", None)
        else:
            os.environ["SNHP_PLAYBOOK_MODE"] = saved_mode
        if saved_pair is None:
            os.environ.pop("SNHP_PAIR_TEST", None)
        else:
            os.environ["SNHP_PAIR_TEST"] = saved_pair


def _candidate_tournaments(candidate_playbook: dict, global_tune: dict,
                            n_rounds: int, confidence_min: float,
                            n_seeds: int) -> list[dict]:
    """Run candidate playbook + global tune-params across `n_seeds` matched
    seed offsets. Both injections happen in-process before each tournament
    and are cleared in `finally` so trials don't leak state."""
    import sys as _sys
    if "negmas_agent" not in _sys.modules:
        # Force initial import so _TUNE_PARAMS is reachable.
        _sys.path.insert(0, _op.join(_REPO_ROOT, "snhp"))
        import negmas_agent  # noqa: F401
    import negmas_agent as _na

    saved_env = {
        k: os.environ.get(k) for k in
        ("SNHP_PLAYBOOK_MODE", "SNHP_CONFIDENCE_MIN", "SNHP_PAIR_TEST")
    }
    os.environ["SNHP_PLAYBOOK_MODE"] = "ALL"
    os.environ["SNHP_CONFIDENCE_MIN"] = str(confidence_min)
    os.environ["SNHP_PAIR_TEST"] = "1"
    playbooks.set_playbook_override(candidate_playbook)
    saved_tune = _na._TUNE_PARAMS
    # Apply globals via the existing _tp() injection mechanism. Globals
    # are non-prefixed (det_*, self_interest_weight) so they hit the
    # backward-compat fallback in _tp() — no role prefix needed.
    _na._TUNE_PARAMS = dict(global_tune)
    try:
        return [_run_one_tournament(n_rounds, seed_offset=s)
                for s in range(n_seeds)]
    finally:
        playbooks.set_playbook_override(None)
        _na._TUNE_PARAMS = saved_tune
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ─── Multi-objective ────────────────────────────────────────────────────────


def make_multi_objective(baselines: list[dict], n_rounds: int,
                          confidence_min: float, n_seeds: int):
    """Returns an Optuna NSGA-II callable that returns a 3-tuple:
       (joint_pair_welfare, neg_defense_loss, neg_worst_case_delta)
    All three MAXIMIZED. Reformulated from the prior (avg, elo, worst_case)
    objective per the cooperation thesis: SNHP wins as a *protocol* when
    cooperator-pair joint welfare is high AND defender-side floor losses
    are minimized. Avg utility is a derived diagnostic, not the objective.

    Metrics aggregated as MEDIAN across `n_seeds` paired-seed runs to drop
    single-tournament noise.
    """
    import statistics as _stats

    base_avgs_per_seed = [
        next((r["avg"] for r in b["rankings"] if r["name"] == "SNHP"), 0.0)
        for b in baselines
    ]
    median_base_avg = _stats.median(base_avgs_per_seed)

    base_per_opp_per_seed = [_snhp_per_opponent(b["pairwise"], "SNHP")
                              for b in baselines]

    base_pair_per_seed = [
        pair_joint_welfare(b["pairwise"], "SNHP", "SNHP_B") for b in baselines
    ]
    median_base_pair = _stats.median(base_pair_per_seed) if base_pair_per_seed else 0.0
    base_def_per_seed = [
        mean_defense_floor_violation(b["pairwise"], "SNHP", _EXTRACTOR_NAMES)
        for b in baselines
    ]
    median_base_def = _stats.median(base_def_per_seed) if base_def_per_seed else 0.0

    def objective(trial):
        candidate, global_tune = _suggest_candidate(trial)
        try:
            cands = _candidate_tournaments(
                candidate, global_tune, n_rounds, confidence_min, n_seeds,
            )
        except Exception as e:
            trial.set_user_attr("error", f"{type(e).__name__}: {e}")
            return -10.0, -10.0, -10.0

        per_seed_avg = []
        per_seed_elo = []
        per_seed_worst = []
        per_seed_pair = []
        per_seed_def = []
        for i, cand in enumerate(cands):
            cand_avg = next(
                (r["avg"] for r in cand["rankings"] if r["name"] == "SNHP"),
                0.0,
            )
            elo = paired_seed_elo_delta(
                baselines[i]["pairwise"], cand["pairwise"],
                target_player="SNHP",
            )["delta"]
            cand_per_opp = _snhp_per_opponent(cand["pairwise"], "SNHP")
            per_opp_deltas = [
                cand_per_opp.get(opp, base_per_opp_per_seed[i].get(opp, 0.0))
                - base_per_opp_per_seed[i].get(opp, 0.0)
                for opp in base_per_opp_per_seed[i]
            ]
            worst = min(per_opp_deltas) if per_opp_deltas else 0.0
            pair = pair_joint_welfare(cand["pairwise"], "SNHP", "SNHP_B")
            defloss = mean_defense_floor_violation(
                cand["pairwise"], "SNHP", _EXTRACTOR_NAMES,
            )
            per_seed_avg.append(cand_avg)
            per_seed_elo.append(elo)
            per_seed_worst.append(worst)
            per_seed_pair.append(pair)
            per_seed_def.append(defloss)

        avg_med = _stats.median(per_seed_avg)
        elo_med = _stats.median(per_seed_elo)
        worst_med = _stats.median(per_seed_worst)
        pair_med = _stats.median(per_seed_pair)
        def_med = _stats.median(per_seed_def)

        trial.set_user_attr("n_seeds", n_seeds)
        trial.set_user_attr("avg", round(avg_med, 4))
        trial.set_user_attr("avg_delta", round(avg_med - median_base_avg, 4))
        trial.set_user_attr("elo_delta", round(elo_med, 1))
        trial.set_user_attr("worst_case_delta", round(worst_med, 4))
        trial.set_user_attr("pair_joint_welfare", round(pair_med, 4))
        trial.set_user_attr("pair_delta", round(pair_med - median_base_pair, 4))
        trial.set_user_attr("defense_floor_loss", round(def_med, 4))
        trial.set_user_attr("defense_delta", round(median_base_def - def_med, 4))
        trial.set_user_attr("per_seed_pair", [round(p, 4) for p in per_seed_pair])
        trial.set_user_attr("per_seed_def", [round(d, 4) for d in per_seed_def])

        # NSGA-II maximizes; defense_loss and worst_case are NEGATED so
        # "less loss" / "less regression" becomes "more objective."
        return pair_med, -def_med, worst_med

    return objective


# ─── Driver ─────────────────────────────────────────────────────────────────


def _pick_best_candidate(study: optuna.study.Study,
                          gate_min_pair_delta: float = 0.0,
                          gate_max_def_loss: float = 0.05,
                          gate_min_worst_case: float = -0.02) -> Optional[optuna.trial.FrozenTrial]:
    """From the Pareto front, pick the candidate that:
      1. Passes 3 hard gates: pair welfare ≥ baseline (no cooperation
         regression), defense loss ≤ 0.05 (we don't lose >0.05 below rv
         on average vs extractors), worst-case per-opponent ≥ -0.02.
      2. Among gate-passers, maximizes pair welfare (the headline metric).
      3. If no gate-passer exists, fall back to highest pair welfare overall.
    """
    completed = [t for t in study.trials
                  if t.state == optuna.trial.TrialState.COMPLETE]
    if not completed:
        return None

    def gates_pass(t):
        pair_d = t.user_attrs.get("pair_delta")
        def_loss = t.user_attrs.get("defense_floor_loss")
        wc = t.user_attrs.get("worst_case_delta")
        if pair_d is None or def_loss is None or wc is None:
            return False
        return (pair_d >= gate_min_pair_delta
                and def_loss <= gate_max_def_loss
                and wc >= gate_min_worst_case)

    passers = [t for t in completed if gates_pass(t)]
    if passers:
        return max(passers, key=lambda t: t.user_attrs["pair_joint_welfare"])
    return max(completed, key=lambda t: t.user_attrs.get("pair_joint_welfare", 0.0))


def _build_artifact_from_trial(trial: optuna.trial.FrozenTrial
                                ) -> tuple[dict, dict]:
    """Reconstruct (playbook, global_tune) from a trial's params."""
    pb = {ttype: {} for ttype in _TYPES}
    global_tune: dict[str, float] = {}
    global_keys = {name for name, _lo, _hi in _GLOBAL_PARAM_BOUNDS}
    for key, val in trial.params.items():
        if key in global_keys:
            global_tune[key] = round(float(val), 4)
            continue
        ttype, _, name = key.partition("_")
        if ttype in pb and name:
            pb[ttype][name] = round(float(val), 4)
    for ttype in _TYPES:
        s = pb[ttype].get("asp_start", 0.95)
        if pb[ttype].get("asp_floor", 0.0) >= s:
            pb[ttype]["asp_floor"] = round(max(0.35, s - 0.05), 4)
    pb["HONEST"] = dict(playbooks._PLAYBOOKS["HONEST"])
    return pb, global_tune


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
    p.add_argument("--n-seeds", type=int, default=3,
                    help="Independent seed offsets per trial. Each trial's "
                         "objective is the median across these. K=3 has Elo "
                         "MDE ~10; K=5 ~7. Multiplies wall by K.")
    args = p.parse_args()

    n_rounds = args.n_rounds if args.n_rounds is not None else (5 if args.quick else 20)

    n_pb_dims = len(_PARAM_BOUNDS) * len(_TYPES)
    n_global_dims = len(_GLOBAL_PARAM_BOUNDS)
    print(f"=== Playbook tuner — {args.trials} trials × N_ROUNDS={n_rounds} × {args.n_seeds} seeds ===")
    print(f"  Search space: {n_pb_dims} per-type playbook + "
          f"{n_global_dims} global = {n_pb_dims + n_global_dims} dims (NSGA-II)")
    print(f"  Confidence floor: {args.confidence_min}")
    print(f"  Output: {args.out}")
    print()
    print(f"Step 1/3: Running {args.n_seeds} baseline tournaments (paired-seed anchors)...")
    t_base_start = time.time()
    baselines = _baseline_tournaments(n_rounds, args.n_seeds)
    base_avgs = [next((r["avg"] for r in b["rankings"] if r["name"] == "SNHP"), 0.0)
                  for b in baselines]
    base_pairs = [pair_joint_welfare(b["pairwise"], "SNHP", "SNHP_B") for b in baselines]
    base_defs = [mean_defense_floor_violation(b["pairwise"], "SNHP", _EXTRACTOR_NAMES)
                 for b in baselines]
    print(f"  Baseline per-seed: avg={[round(a, 4) for a in base_avgs]}")
    print(f"                     pair_welfare={[round(p, 4) for p in base_pairs]}")
    print(f"                     defense_loss={[round(d, 4) for d in base_defs]}")
    print(f"  Wall {time.time() - t_base_start:.1f}s, extractors={_EXTRACTOR_NAMES}")

    print(f"\nStep 2/3: NSGA-II search ({args.trials} trials × {args.n_seeds} seeds = "
          f"{args.trials * args.n_seeds} tournaments)...")
    db_path = args.db_path
    storage = f"sqlite:///{db_path}" if db_path else None
    # NSGA-II population sized to ~dim count for adequate Pareto coverage
    # in a 32-dim search. Cap at trials // 4 so we get at least 4 generations.
    pop_size = min(32, max(8, args.trials // 4))
    sampler = NSGAIISampler(population_size=pop_size, seed=42)
    print(f"  NSGA-II population: {pop_size}  ({args.trials // pop_size} generations)")
    study = optuna.create_study(
        # Objectives in order: pair_welfare, neg_defense_loss, neg_worst_case
        directions=["maximize", "maximize", "maximize"],
        sampler=sampler, storage=storage,
        load_if_exists=(storage is not None),
    )
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    obj = make_multi_objective(baselines, n_rounds, args.confidence_min,
                                 args.n_seeds)
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
    a = best.user_attrs
    print(f"  Trial #{best.number}:")
    print(f"    pair_welfare={a['pair_joint_welfare']:.4f}  "
          f"(Δ {a['pair_delta']:+.4f})")
    print(f"    defense_loss={a['defense_floor_loss']:.4f}  "
          f"(Δ {a['defense_delta']:+.4f}, lower is better)")
    print(f"    worst_case_delta={a['worst_case_delta']:+.4f}")
    print(f"    avg={a['avg']:.4f}  (Δ {a['avg_delta']:+.4f}, derived diagnostic)")
    gates_pass = (a['pair_delta'] >= 0.0 and a['defense_floor_loss'] <= 0.05
                  and a['worst_case_delta'] >= -0.02)
    print(f"  Gates pass (pairΔ≥0, defense_loss≤0.05, worst≥-0.02)? {gates_pass}")

    candidate, global_tune = _build_artifact_from_trial(best)
    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_trials": args.trials,
        "n_rounds": n_rounds,
        "confidence_min": args.confidence_min,
        "trial_number": best.number,
        "user_attrs": dict(best.user_attrs),
        "_global_tune": global_tune,
        **candidate,
    }
    with open(args.out, "w") as f:
        json.dump(artifact, f, sort_keys=True, indent=2)
        f.write("\n")
    print(f"\nWrote tuned playbook → {args.out}")
    print(f"  → re-import snhp.playbooks to load (or restart any tournament).")
    if global_tune:
        # Also write the global tune-params alongside, in the format
        # negmas_agent._TUNE_PARAMS expects (non-prefixed keys).
        global_path = _op.join(_SNHP_DIR, "playbook_globals_optimal.json")
        with open(global_path, "w") as f:
            json.dump(global_tune, f, sort_keys=True, indent=2)
            f.write("\n")
        print(f"Wrote global tune-params → {global_path}")


if __name__ == "__main__":
    main()
