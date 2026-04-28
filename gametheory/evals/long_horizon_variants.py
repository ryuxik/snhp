"""
Long-horizon tournament with multiple SNHP variants.

Answers two questions raised after the standard tournament:
  (1) Long horizon — do SNHP's H2H win/loss numbers improve with more rounds
      per matchup (memory and Bayesian inference need iterations to pay off)?
  (2) Adaptive opponents — does a SNHP variant beat another SNHP variant in
      H2H? If memory + complex strategy is the moat, variants with different
      parameter settings should produce a partial order (some variants
      dominate others).

Setup:
  - Roster: existing 19 B2B opponents + Aspiration + 5 SNHP variants = 25
  - n_rounds = 100 per matchup (5x the standard tournament; ~5x runtime)
  - Pure NegMAS math; no LLM calls anywhere in the path.

Variants explored:
  - SNHP_Default        — baseline, no parameter overrides
  - SNHP_Hardline       — high opening, slow concession, demanding accept
  - SNHP_Conceder       — low opening, fast concession, lenient accept
  - SNHP_Patient        — pushes acceptance to the late game
  - SNHP_Aggressive     — high commitment, no late-game retraction

Run:
  ../venv/bin/python -m gametheory.evals.long_horizon_variants
"""
from __future__ import annotations

import multiprocessing
import statistics
import time
from collections import defaultdict
from typing import Type

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import (  # noqa: E402
    _run_single_matchup, BATNA_CENTER, N_STEPS, ELO_INIT, update_elo,
    bootstrap_ci,
)
from negmas.sao.negotiators import AspirationNegotiator  # noqa: E402
from negmas_agent import SNHPAgent  # noqa: E402

# Re-export from the canonical home so existing imports keep working.
from gametheory.agents.snhp_variants import (  # noqa: F401
    SNHPVariantBase as _SNHPVariant,
    SNHP_Hardline, SNHP_Conceder, SNHP_Patient, SNHP_Aggressive,
)


N_ROUNDS = 100  # 5x standard
N_WORKERS = min(14, multiprocessing.cpu_count())


class SNHP_Default(SNHPAgent):
    """Baseline — uses the default parameters / globally-set _TUNE_PARAMS."""


SNHP_VARIANTS: dict[str, Type] = {
    "SNHP_Default": SNHP_Default,
    "SNHP_Hardline": SNHP_Hardline,
    "SNHP_Conceder": SNHP_Conceder,
    "SNHP_Patient": SNHP_Patient,
    "SNHP_Aggressive": SNHP_Aggressive,
}


# ─── Tournament runner ──────────────────────────────────────────────────────


def build_roster() -> dict:
    roster: dict[str, dict] = {}
    for name, cls in B2B_OPPONENTS.items():
        roster[name] = {"class": cls, "uses_memory": False}
    roster["Aspiration"] = {"class": AspirationNegotiator, "uses_memory": False}
    for name, cls in SNHP_VARIANTS.items():
        roster[name] = {"class": cls, "uses_memory": True}
    return roster


def run() -> None:
    roster = build_roster()
    names = list(roster.keys())
    n = len(names)

    # Build all-vs-all jobs.
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
    print(f"  LONG-HORIZON TOURNAMENT: {n} players × {N_ROUNDS} rounds × "
          f"{len(jobs)} matchups")
    print(f"  No LLM calls; pure NegMAS math across {N_WORKERS} cores.")
    print("=" * 100)
    t0 = time.time()
    with multiprocessing.Pool(N_WORKERS) as pool:
        results = pool.map(_run_single_matchup, jobs)
    print(f"  Completed in {time.time() - t0:.1f}s "
          f"({len(jobs) / (time.time() - t0):.1f} matchups/s)")

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

    # ─── Rankings ────────────────────────────────────────────────────────────
    print()
    print("=" * 100)
    print(f"  FINAL RANKINGS (avg utility across all opponents, n_rounds={N_ROUNDS})")
    print("=" * 100)
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
    print(f"  {'#':>2} {'Player':<20} {'AvgUtil':>8} {'95% CI':>18} "
          f"{'Elo':>5} {'W':>3} {'T':>3} {'L':>3} {'H2H%':>5}")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        h2h = r["w"] / max(r["w"] + r["t"] + r["l"], 1) * 100
        marker = "  ⭐" if r["name"].startswith("SNHP") else ""
        print(f"  {i:>2} {r['name']:<20} {r['avg']:>8.4f} "
              f"[{r['ci'][0]:.4f},{r['ci'][1]:.4f}] {r['elo']:>5} "
              f"{r['w']:>3} {r['t']:>3} {r['l']:>3} {h2h:>4.0f}%{marker}")

    # ─── SNHP-vs-SNHP H2H matrix ─────────────────────────────────────────────
    snhp_names = [name for name in names if name in SNHP_VARIANTS]
    print()
    print("=" * 100)
    print("  SNHP-vs-SNHP HEAD-TO-HEAD MATRIX (row util in [row, col] matchup)")
    print("=" * 100)
    print(f"  {'':>20} | " + " | ".join(f"{n:>13}" for n in snhp_names))
    print("-" * 100)
    for row_name in snhp_names:
        cells = []
        for col_name in snhp_names:
            ua, ub, dr = pairwise[(row_name, col_name)]
            marker = "+" if ua > ub + 0.005 else ("=" if abs(ua - ub) <= 0.005 else "-")
            cells.append(f"{ua:>5.3f}/{ub:.3f} {marker}")
        print(f"  {row_name:>20} | " + " | ".join(cells))

    # ─── Cross-SNHP utility deltas ───────────────────────────────────────────
    print()
    print("=" * 100)
    print("  SNHP variants vs the FULL FIELD (ranked deltas vs Default baseline)")
    print("=" * 100)
    default_avg = next(r["avg"] for r in rows if r["name"] == "SNHP_Default")
    snhp_rows = sorted(
        [r for r in rows if r["name"] in SNHP_VARIANTS],
        key=lambda r: r["avg"], reverse=True,
    )
    for r in snhp_rows:
        delta = r["avg"] - default_avg
        sign = "+" if delta >= 0 else ""
        print(f"  {r['name']:<20} avg={r['avg']:.4f}  Δ-vs-Default={sign}{delta:.4f}  "
              f"H2H W/T/L = {r['w']}/{r['t']}/{r['l']}")

    # ─── SNHP variants vs the EXPLOITER subset (Anchorer, BATNA Bluffer, …) ─
    exploiters = ["Anchorer", "BATNA Bluffer", "Cialdini", "GoodCop/BadCop"]
    exploiters = [e for e in exploiters if e in pairwise.keys() or
                   any(e == n for n in names)]
    print()
    print("=" * 100)
    print(f"  SNHP variants vs EXPLOITER SUBSET ({', '.join(exploiters)})")
    print("=" * 100)
    print(f"  {'Variant':<20} | " + " | ".join(f"{e:>14}" for e in exploiters)
          + " | mean")
    print("-" * 100)
    for variant in snhp_names:
        cells = []
        utils = []
        for opp in exploiters:
            if (variant, opp) in pairwise:
                ua, ub, _ = pairwise[(variant, opp)]
                cells.append(f"{ua:>5.3f}/{ub:.3f}")
                utils.append(ua)
            else:
                cells.append(" " * 14)
        mean_u = statistics.mean(utils) if utils else 0
        print(f"  {variant:<20} | " + " | ".join(cells)
              + f" | {mean_u:.3f}")

    print()
    print("Notes:")
    print(" - Cell format: row_util / col_util.  '+' = row wins, '=' = tie, '-' = row loses.")
    print(" - The H2H% column above counts wins as fraction of (W+T+L) excluding self-play.")
    print(" - With n_rounds=100, MC standard error on per-matchup averages ~0.02 — "
          "differences <0.04 are not significant.")


if __name__ == "__main__":
    run()
