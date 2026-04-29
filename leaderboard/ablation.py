"""
Ablation-matrix runner for the SNHP exploitation-mode rollout.

Runs the 13 cells defined in the plan against the existing NegMAS B2B
tournament harness (snhp/b2b_round_robin.run_round_robin). Each cell
sets a different combination of env vars that the Phase B agent code
reads to choose its playbook / classifier behavior:

  SNHP_PLAYBOOK_MODE   = OFF | ALL | BOULWARE_ONLY | CONCEDER_ONLY |
                         MIRROR_ONLY | RANDOM_ONLY | PROBABILISTIC | ORACLE
  SNHP_CONFIDENCE_MIN  = float in [0, 1] — gate exploit weight
  SNHP_FORCE_MISCLASS  = (unset) | RANDOM | ADVERSARIAL — stress modes

If the agent code doesn't yet implement a mode (Phase A self-test before
Phase B lands), the cells degenerate to baseline behavior — which is
exactly what we want for self-testing the framework: all cells produce
the same numbers, gates trivially PASS against a paired-seed baseline.

Output: leaderboard/results/ablation_<git_sha>.json — top-level dict
with one entry per cell, plus a `gates` summary keyed by candidate cell.

Run:
    python -m leaderboard.ablation                # default symmetric, paired seeds
    python -m leaderboard.ablation --quick        # N_ROUNDS=5 (faster smoke)
    python -m leaderboard.ablation --skip-stress  # skip cells 10-11 (force-misclass)

Exit code 0 iff all gates PASS for cell `exploit_all_conf_0.65`. Non-zero
on any gate failure — suitable for CI / pre-merge hooks.
"""
from __future__ import annotations

import argparse
import json
import os
import os.path as _op
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = _op.dirname(_op.dirname(_op.abspath(__file__)))
sys.path.insert(0, _op.join(_REPO_ROOT, "snhp"))
sys.path.insert(0, _REPO_ROOT)

from snhp.eval_metrics import (  # noqa: E402
    compute_all, evaluate_gates, to_json, CellMeta,
)
from snhp.b2b_opponents import OPPONENT_TYPE_TAGS  # noqa: E402


# ─── Cell definitions ────────────────────────────────────────────────────────

# Each cell is (cell_id, env_overrides, description). The env_overrides
# are read by Phase B agent code (b2b_round_robin / negmas_agent). For
# Phase A self-test before Phase B lands, all cells produce identical
# results — that's by design (proves the framework is wired correctly).
_CELLS = [
    ("baseline", {
        "SNHP_PLAYBOOK_MODE": "OFF",
    }, "Anchor — current SNHP, no exploitation mode"),
    ("exploit_all_conf_0.65", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.65",
    }, "Headline candidate — combined playbooks, default confidence floor"),
    ("boulware_only", {
        "SNHP_PLAYBOOK_MODE": "BOULWARE_ONLY",
    }, "Type-isolation: BOULWARE playbook only"),
    ("conceder_only", {
        "SNHP_PLAYBOOK_MODE": "CONCEDER_ONLY",
    }, "Type-isolation: CONCEDER playbook only"),
    ("mirror_only", {
        "SNHP_PLAYBOOK_MODE": "MIRROR_ONLY",
    }, "Type-isolation: MIRROR playbook only"),
    ("random_only", {
        "SNHP_PLAYBOOK_MODE": "RANDOM_ONLY",
    }, "Type-isolation: RANDOM playbook only"),
    ("exploit_all_conf_0.30", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.30",
    }, "Threshold sweep — aggressive (low confidence floor)"),
    ("exploit_all_conf_0.50", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.50",
    }, "Threshold sweep — middle"),
    ("exploit_all_conf_0.70", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.70",
    }, "Threshold sweep — conservative"),
    ("misclass_random", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.65",
        "SNHP_FORCE_MISCLASS": "RANDOM",
    }, "Stress: classifier forced to output random labels"),
    ("misclass_adversarial", {
        "SNHP_PLAYBOOK_MODE": "ALL",
        "SNHP_CONFIDENCE_MIN": "0.65",
        "SNHP_FORCE_MISCLASS": "ADVERSARIAL",
    }, "Stress: classifier forced to pick the worst playbook for true type"),
    ("probabilistic", {
        "SNHP_PLAYBOOK_MODE": "PROBABILISTIC",
    }, "Mixed strategy: softmax over confidence, no hard threshold"),
    ("oracle", {
        "SNHP_PLAYBOOK_MODE": "ORACLE",
    }, "Upper bound: classifier sees ground-truth opponent type tags"),
]


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _run_one_cell(cell_id: str, env_overrides: dict, *,
                   quick: bool, n_rounds: int | None) -> dict:
    """Run a single cell. Sets the env vars, runs the tournament, returns
    the (rankings, pairwise, scores) tuple wrapped with metadata."""
    # Apply env overrides for this cell's run.
    saved_env: dict[str, str | None] = {}
    for k, v in env_overrides.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = str(v)
    # Also clear any env var that's NOT in this cell's overrides but is
    # in the union of all override keys (so cell N doesn't inherit cell N-1's settings).
    all_keys = set()
    for _id, env, _desc in _CELLS:
        all_keys.update(env.keys())
    for k in all_keys:
        if k not in env_overrides:
            saved_env.setdefault(k, os.environ.get(k))
            os.environ.pop(k, None)

    try:
        # Lazy import so the env vars take effect for fresh worker processes.
        import importlib
        if "b2b_round_robin" in sys.modules:
            importlib.reload(sys.modules["b2b_round_robin"])
        import b2b_round_robin as trnmt  # noqa: E402

        if n_rounds is not None:
            trnmt.N_ROUNDS = n_rounds
        elif quick:
            trnmt.N_ROUNDS = 5

        t0 = time.time()
        rankings, pairwise, scores = trnmt.run_round_robin(seed_offset=0)
        wall_s = time.time() - t0

        return {
            "cell_id": cell_id,
            "env": env_overrides,
            "rankings": rankings,
            "pairwise": dict(pairwise),
            "scores": {k: list(v) for k, v in scores.items()},
            "wall_s": wall_s,
            "n_rounds": trnmt.N_ROUNDS,
        }
    finally:
        # Restore env so the next cell starts clean.
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _build_artifact(cell_run: dict, *, baseline_run: dict | None,
                     git_sha: str) -> dict:
    meta = CellMeta(
        git_sha=git_sha,
        cell=cell_run["cell_id"],
        wall_s=cell_run["wall_s"],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    config = {
        "n_rounds": cell_run["n_rounds"],
        **cell_run["env"],
    }
    artifact = compute_all(
        meta=meta,
        config=config,
        rankings=cell_run["rankings"],
        pairwise=cell_run["pairwise"],
        scores_per_match_for_target=cell_run["scores"].get("SNHP", []),
        type_tags=OPPONENT_TYPE_TAGS,
        baseline_pairwise=(baseline_run["pairwise"] if baseline_run else None),
        baseline_avg=(
            next((r["avg"] for r in baseline_run["rankings"] if r["name"] == "SNHP"), None)
            if baseline_run else None
        ),
    )
    return artifact


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true",
                    help="N_ROUNDS=5 instead of 20. Faster smoke test.")
    p.add_argument("--n-rounds", type=int, default=None,
                    help="Override N_ROUNDS explicitly (e.g. 10 for medium runs).")
    p.add_argument("--skip-stress", action="store_true",
                    help="Skip misclass_random and misclass_adversarial cells.")
    p.add_argument("--cells", nargs="+", default=None,
                    help="Run only these cell IDs (default: all 13).")
    p.add_argument("--out-dir", type=Path,
                    default=Path(_op.dirname(_op.abspath(__file__))) / "results")
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    git_sha = _git_sha()

    # Filter cells per CLI args.
    cells_to_run = list(_CELLS)
    if args.cells:
        wanted = set(args.cells)
        cells_to_run = [c for c in cells_to_run if c[0] in wanted]
    if args.skip_stress:
        cells_to_run = [c for c in cells_to_run
                         if c[0] not in ("misclass_random", "misclass_adversarial")]

    # Phase 1: run all cells (baseline first so we have it for delta computation)
    cells_to_run.sort(key=lambda c: 0 if c[0] == "baseline" else 1)
    runs: dict[str, dict] = {}
    for cell_id, env, desc in cells_to_run:
        print(f"\n=== Cell: {cell_id} — {desc} ===")
        for k, v in env.items():
            print(f"    {k}={v}")
        runs[cell_id] = _run_one_cell(
            cell_id, env, quick=args.quick, n_rounds=args.n_rounds,
        )

    # Phase 2: build artifacts (with baseline-relative deltas)
    baseline_run = runs.get("baseline")
    artifacts: dict[str, dict] = {}
    for cell_id, run in runs.items():
        is_baseline = (cell_id == "baseline")
        artifact = _build_artifact(
            run,
            baseline_run=(None if is_baseline else baseline_run),
            git_sha=git_sha,
        )
        # Stress-misclass average for gate g5
        misclass_avg = None
        if "misclass_adversarial" in runs and not is_baseline:
            adv = runs["misclass_adversarial"]
            misclass_avg = next(
                (r["avg"] for r in adv["rankings"] if r["name"] == "SNHP"),
                None,
            )
        artifact["gates"] = evaluate_gates(
            artifact,
            baseline_artifact=(None if is_baseline else
                                _build_artifact(baseline_run, baseline_run=None, git_sha=git_sha)),
            misclass_stress_avg=misclass_avg,
        )
        artifacts[cell_id] = artifact

    # Phase 3: write per-cell artifact files + combined summary
    for cell_id, artifact in artifacts.items():
        path = args.out_dir / f"ablation_{git_sha}_{cell_id}.json"
        to_json(artifact, str(path))
        print(f"  wrote {path}")

    summary = {
        "git_sha": git_sha,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cells_run": list(artifacts.keys()),
        "headline_per_cell": {
            cell_id: artifact["headline"] for cell_id, artifact in artifacts.items()
        },
        "gates_per_cell": {
            cell_id: artifact["gates"] for cell_id, artifact in artifacts.items()
        },
    }
    summary_path = args.out_dir / f"ablation_{git_sha}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, sort_keys=True, indent=2)
        f.write("\n")
    print(f"\nSummary written to {summary_path}")

    # Headline check: did the candidate cell pass all gates?
    candidate_gates = artifacts.get("exploit_all_conf_0.65", {}).get("gates", {})
    failures = [k for k, v in candidate_gates.items() if isinstance(v, str) and v.startswith("FAIL")]
    if failures:
        print(f"\n❌ Candidate cell failed gates: {failures}")
        sys.exit(1)
    else:
        print(f"\n✅ All gates PASS for candidate cell `exploit_all_conf_0.65`")


if __name__ == "__main__":
    main()
