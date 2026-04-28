"""
Targeted parameter sweep — close the gap to Aspiration at 100 rounds.

At n_rounds=100, Aspiration ranks #1 with avg utility 0.5489; SNHP_Default
is #4 at 0.5181 — gap of 0.031 (outside MC noise of ~0.02).

Hypotheses:
  H1: SNHP opens too low. aspiration_start=0.62 vs Aspiration ~1.0.
  H2: SNHP's floor is too high. aspiration_floor=0.45 + accept_late_bottom=0.43
      vs Aspiration's floor at reservation (~0.40). Walk-aways on closeable deals.
  H3: SNHP's Bayesian concession over-slows against tough opponents.

Variants tested:
  - SNHP_HighStart   — H1: aspiration_start = 0.92
  - SNHP_LowFloor    — H2: aspiration_floor + accept_late_bottom near reservation
  - SNHP_FastConcede — H3: 2x concession_cap, lower late_curve (faster final approach)
  - SNHP_Aspirational — H1+H2+H3 combined (closest mimic of Aspiration's schedule)
  - SNHP_LooseAccept — H2 variant: lenient acceptance bars

Compares each variant against Aspiration's 0.5489 baseline.

Run:
  ../venv/bin/python -m gametheory.evals.snhp_match_aspiration
"""
from __future__ import annotations

import multiprocessing
import os
import statistics
import sys
import time
from collections import defaultdict
from typing import Type

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "snhp",
))

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import (  # noqa: E402
    _run_single_matchup, BATNA_CENTER, N_STEPS, ELO_INIT, update_elo,
    bootstrap_ci,
)
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402
import negmas_agent  # noqa: E402
from negmas_agent import SNHPAgent  # noqa: E402

from gametheory.evals.long_horizon_variants import _SNHPVariant


N_ROUNDS = 100
N_WORKERS = min(14, multiprocessing.cpu_count())


# ─── Variants targeting each hypothesis ──────────────────────────────────────


class SNHP_Default(SNHPAgent):
    """Baseline."""


class SNHP_HighStart(_SNHPVariant):
    """H1: open aggressively (close to 1.0) like Aspiration."""
    _VARIANT_PARAMS = {
        "aspiration_start": 0.92,         # default 0.62
    }


class SNHP_LowFloor(_SNHPVariant):
    """H2: drop floor & late acceptance to reservation+epsilon."""
    _VARIANT_PARAMS = {
        "aspiration_floor": 0.41,         # default 0.45
        "accept_late_bottom": 0.40,       # default 0.43
        "accept_early_bar": 0.48,         # default 0.54
    }


class SNHP_FastConcede(_SNHPVariant):
    """H3: concede faster end-to-end, less Bayesian slowdown."""
    _VARIANT_PARAMS = {
        "concession_cap_b2b": 0.080,      # default 0.041 (2x)
        "accept_late_curve": 0.40,        # steeper late-game curve
        "time_floor_rate": 0.85,          # hit floor sooner (default 0.90)
    }


class SNHP_Aspirational(_SNHPVariant):
    """All three hypotheses combined — closest mimic of Aspiration."""
    _VARIANT_PARAMS = {
        "aspiration_start": 0.92,
        "aspiration_floor": 0.41,
        "concession_cap_b2b": 0.080,
        "accept_early_bar": 0.46,
        "accept_late_bottom": 0.40,
        "accept_late_curve": 0.40,
        "time_floor_rate": 0.85,
        "retract_prob_b2b": 0.000,
    }


class SNHP_LooseAccept(_SNHPVariant):
    """H2: lenient acceptance only (keep concession dynamics intact)."""
    _VARIANT_PARAMS = {
        "accept_early_bar": 0.46,
        "accept_late_bottom": 0.40,
        "accept_late_start": 0.50,        # start late phase earlier
    }


VARIANTS: dict[str, Type] = {
    "SNHP_Default": SNHP_Default,
    "SNHP_HighStart": SNHP_HighStart,
    "SNHP_LowFloor": SNHP_LowFloor,
    "SNHP_FastConcede": SNHP_FastConcede,
    "SNHP_Aspirational": SNHP_Aspirational,
    "SNHP_LooseAccept": SNHP_LooseAccept,
}


def build_roster() -> dict:
    roster: dict[str, dict] = {}
    for name, cls in B2B_OPPONENTS.items():
        roster[name] = {"class": cls, "uses_memory": False}
    roster["Aspiration"] = {"class": AspirationNegotiator, "uses_memory": False}
    for name, cls in VARIANTS.items():
        roster[name] = {"class": cls, "uses_memory": True}
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
    print(f"  ASPIRATION-CHASE TOURNAMENT: {n} players × {N_ROUNDS} rounds × "
          f"{len(jobs)} matchups")
    print(f"  Goal: identify which SNHP-variant matches or beats Aspiration's "
          f"0.5489 avg utility.")
    print("=" * 100)
    t0 = time.time()
    with multiprocessing.Pool(N_WORKERS) as pool:
        results = pool.map(_run_single_matchup, jobs)
    print(f"  Completed in {time.time() - t0:.1f}s")

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

    # ─── Rankings (full field) ──────────────────────────────────────────────
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
            "ci": (ci_lo, ci_hi), "elo": elo[name],
            "w": wins, "t": ties, "l": losses,
        })
    rows.sort(key=lambda r: r["avg"], reverse=True)

    asp_avg = next(r["avg"] for r in rows if r["name"] == "Aspiration")

    print()
    print("=" * 100)
    print(f"  RANKINGS (n_rounds={N_ROUNDS}). Aspiration baseline: {asp_avg:.4f}")
    print("=" * 100)
    print(f"  {'#':>2} {'Player':<22} {'AvgUtil':>8} {'95% CI':>18} "
          f"{'Δ vs Asp':>9} {'W':>3} {'T':>3} {'L':>3} {'H2H%':>5}")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        h2h = r["w"] / max(r["w"] + r["t"] + r["l"], 1) * 100
        delta = r["avg"] - asp_avg
        sign = "+" if delta >= 0 else ""
        marker = ""
        if r["name"] == "Aspiration":
            marker = "  ⬅ baseline"
        elif r["name"] in VARIANTS:
            marker = "  ⭐ variant"
        print(f"  {i:>2} {r['name']:<22} {r['avg']:>8.4f} "
              f"[{r['ci'][0]:.4f},{r['ci'][1]:.4f}] {sign}{delta:>7.4f} "
              f"{r['w']:>3} {r['t']:>3} {r['l']:>3} {h2h:>4.0f}%{marker}")

    # ─── Per-variant: where exactly do we gain vs SNHP_Default? ──────────────
    print()
    print("=" * 100)
    print("  DIAGNOSTIC: per-opponent utility delta (variant - Default)")
    print("=" * 100)
    default_pairs = {opp: pairwise[("SNHP_Default", opp)][0]
                     for opp in names if opp != "SNHP_Default"}
    diag_opps = [n for n in names
                 if not n.startswith("SNHP_") and n != "Aspiration"]
    print(f"  {'Variant':<22} | "
          + " | ".join(f"{o[:11]:>11}" for o in diag_opps[:8]))
    print("-" * 100)
    for variant in VARIANTS:
        if variant == "SNHP_Default":
            continue
        cells = []
        for opp in diag_opps[:8]:
            ua = pairwise[(variant, opp)][0]
            db = default_pairs[opp]
            d = ua - db
            cells.append(f"{('+' if d >= 0 else ''):>1}{d:>+10.3f}")
        print(f"  {variant:<22} | " + " | ".join(cells))
    print(f"  ({len(diag_opps)} non-SNHP opponents total; first 8 shown)")

    # ─── Variant vs Aspiration head-to-head ──────────────────────────────────
    print()
    print("=" * 100)
    print("  VARIANT vs ASPIRATION direct H2H")
    print("=" * 100)
    print(f"  {'Variant':<22} | {'V util':>8} {'A util':>8} {'Margin':>8} {'Result':>10}")
    print("-" * 100)
    for variant in VARIANTS:
        ua, ub, _ = pairwise[(variant, "Aspiration")]
        margin = ua - ub
        result = "WIN" if margin > 0.005 else ("TIE" if abs(margin) <= 0.005 else "LOSE")
        print(f"  {variant:<22} | {ua:>8.4f} {ub:>8.4f} {margin:>+8.4f} {result:>10}")

    # ─── Self-play stress check (variant vs itself) ──────────────────────────
    print()
    print("=" * 100)
    print("  SELF-PLAY check (variant vs itself, both sides):")
    print("=" * 100)
    for variant in VARIANTS:
        ua, ub, dr = pairwise[(variant, variant)]
        print(f"  {variant:<22} | self-play: {ua:>5.3f} / {ub:.3f}  "
              f"deal_rate={dr:.0%}")


if __name__ == "__main__":
    run()
