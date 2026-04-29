"""
Final tournament: detector-enabled SNHP with multi-objective Optuna params,
versus the full 21-strategy field at n_rounds=100. Goal: match or beat
Aspiration's avg utility ranking that the long-horizon study found.

Loads three operating points produced by `optuna_multi_objective.py`:
  - optuna_pareto_avg.json   — params that maximize avg utility
  - optuna_pareto_h2h.json   — params that maximize H2H win rate
  - optuna_pareto_self.json  — params that maximize self-play joint surplus

Each is run as a separate SNHP variant with the AspirationDetector enabled,
plus a baseline (vanilla SNHP, no detector, default params) as a control.

Run:
  ../venv/bin/python -m gametheory.evals.final_tournament
"""
from __future__ import annotations

import multiprocessing
import statistics
import time
from collections import defaultdict

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import (  # noqa: E402
    _run_single_matchup, BATNA_CENTER, N_STEPS, ELO_INIT, update_elo,
    bootstrap_ci,
)
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402
from negmas_agent import SNHPAgent  # noqa: E402

from gametheory.agents.aspiration_detector import SNHPWithAspirationDetector
from gametheory.agents import snhp_variants


N_ROUNDS = 100
N_WORKERS = min(14, multiprocessing.cpu_count())
def build_roster() -> dict:
    roster: dict[str, dict] = {}
    for name, cls in B2B_OPPONENTS.items():
        roster[name] = {"class": cls, "uses_memory": False}
    roster["Aspiration"] = {"class": AspirationNegotiator, "uses_memory": False}

    # Always include vanilla SNHP as control.
    roster["SNHP_Default"] = {"class": SNHPAgent, "uses_memory": True}
    roster["SNHP_Detector"] = {
        "class": SNHPWithAspirationDetector, "uses_memory": True,
    }

    # Each available Pareto operating point. Classes are pre-registered
    # in `snhp_variants` at module import so spawn-mode workers can pickle.
    pareto_labels = (
        # v1 (3-objective Optuna run)
        "SNHP_PMaxAvg", "SNHP_PMaxH2H", "SNHP_PMaxSelf",
        # v2 (4-objective: adds anti_aspiration)
        "SNHP_v2_PMaxAvg", "SNHP_v2_PMaxH2H", "SNHP_v2_PMaxSelf",
        "SNHP_v2_AntiAsp",
    )
    for label in pareto_labels:
        cls = getattr(snhp_variants, label, None)
        if cls is None:
            print(f"  [warn] {label} not registered — Optuna run hasn't "
                  f"produced this Pareto operating point; skipping.")
            continue
        roster[label] = {"class": cls, "uses_memory": True}

    return roster


def run() -> None:
    roster = build_roster()
    names = list(roster.keys())
    n = len(names)

    jobs = []
    for name_a in names:
        for name_b in names:
            pa, pb = roster[name_a], roster[name_b]
            jobs.append((
                name_a, name_b, pa["class"], pb["class"],
                pa["uses_memory"], pb["uses_memory"],
                N_STEPS, N_ROUNDS, BATNA_CENTER, 1.0, 1.0,
            ))

    print("=" * 100)
    print(f"  FINAL TOURNAMENT — detector + Optuna Pareto params")
    print(f"  {n} players × {N_ROUNDS} rounds × {len(jobs)} matchups")
    snhp_names = [name for name in names
                  if name.startswith("SNHP_") or name == "SNHP_Default"]
    print(f"  SNHP variants in play: {snhp_names}")
    print("=" * 100)

    t0 = time.time()
    with multiprocessing.Pool(N_WORKERS) as pool:
        results = pool.map(_run_single_matchup, jobs)
    print(f"  Completed in {time.time() - t0:.0f}s")

    scores: dict[str, list[float]] = defaultdict(list)
    pairwise: dict[tuple[str, str], tuple[float, float, float]] = {}
    elo = {name: ELO_INIT for name in names}
    for name_a, name_b, util_a, util_b, dr in results:
        scores[name_a].append(util_a)
        pairwise[(name_a, name_b)] = (util_a, util_b, dr)
        if name_a != name_b:
            if util_a > util_b + 0.005:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 1.0)
            elif abs(util_a - util_b) <= 0.005:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 0.5)
            else:
                elo[name_a], elo[name_b] = update_elo(elo[name_a], elo[name_b], 0.0)

    # Rankings
    rows = []
    for name in names:
        utils = scores[name]
        wins = ties = losses = 0
        for opp in names:
            if opp == name:
                continue
            ua, ub, _ = pairwise[(name, opp)]
            if ua > ub + 0.005:
                wins += 1
            elif abs(ua - ub) <= 0.005:
                ties += 1
            else:
                losses += 1
        _, ci_lo, ci_hi = bootstrap_ci(utils)
        rows.append({
            "name": name, "avg": statistics.mean(utils),
            "ci": (ci_lo, ci_hi),
            "w": wins, "t": ties, "l": losses,
        })
    rows.sort(key=lambda r: r["avg"], reverse=True)

    print()
    print("=" * 100)
    print(f"  FINAL RANKINGS at n_rounds={N_ROUNDS}")
    print("=" * 100)
    asp_rank = next((i for i, r in enumerate(rows, 1) if r["name"] == "Aspiration"),
                     None)
    print(f"  {'#':>3} {'Player':<22} {'AvgUtil':>9} {'95% CI':>18} "
          f"{'W':>3} {'T':>3} {'L':>3} {'H2H%':>5}")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        h2h = r["w"] / max(r["w"] + r["t"] + r["l"], 1) * 100
        marker = ""
        if r["name"].startswith("SNHP_"):
            marker = "  ⭐"
        elif r["name"] == "Aspiration":
            marker = "  ⬅ baseline"
        print(f"  {i:>3} {r['name']:<22} {r['avg']:>9.4f} "
              f"[{r['ci'][0]:.4f},{r['ci'][1]:.4f}] {r['w']:>3} {r['t']:>3} "
              f"{r['l']:>3} {h2h:>4.0f}%{marker}")

    # Aspiration H2H check
    print()
    print("=" * 100)
    print("  Direct head-to-head vs Aspiration (the gap-closer test)")
    print("=" * 100)
    for r in rows:
        if not r["name"].startswith("SNHP_"):
            continue
        ua, ub, _ = pairwise[(r["name"], "Aspiration")]
        margin = ua - ub
        sign = "+" if margin >= 0 else ""
        outcome = "WIN" if margin > 0.005 else ("TIE" if abs(margin) <= 0.005 else "LOSE")
        print(f"  {r['name']:<22} | "
              f"SNHP={ua:.4f}  Asp={ub:.4f}  margin={sign}{margin:.4f}  {outcome}")

    # Self-play check
    print()
    print("=" * 100)
    print("  Self-play utility (variant vs itself)")
    print("=" * 100)
    for r in rows:
        if not r["name"].startswith("SNHP_"):
            continue
        ua, ub, dr = pairwise[(r["name"], r["name"])]
        print(f"  {r['name']:<22} | self-play: {ua:.4f} / {ub:.4f}  "
              f"deal_rate={dr:.0%}")


if __name__ == "__main__":
    run()
