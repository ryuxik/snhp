"""
Leaderboard runner — uses the existing NegMAS multi-attribute round-robin
in `snhp/b2b_round_robin.py` (the same harness SNHP was tuned against)
and emits a JSON artifact for the public landing page.

  python -m leaderboard.run                  # full round-robin, no LLM (~2-4 min)
  python -m leaderboard.run --quick          # N_ROUNDS=5, much faster
  python -m leaderboard.run --with-gemini    # adds GeminiFlashVanilla
                                              # (requires GOOGLE_API_KEY)

The output `leaderboard/results/leaderboard.json` is what the landing page
reads. Contains rankings (with bootstrap CIs and Elo), pairwise stats,
and a config block so a reader can verify what was actually run.
"""
from __future__ import annotations

import argparse
import json
import os
import os.path as _op
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Reach into snhp/ the way the rest of the repo does.
_REPO_ROOT = _op.dirname(_op.dirname(_op.abspath(__file__)))
sys.path.insert(0, _op.join(_REPO_ROOT, "snhp"))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true",
                    help="N_ROUNDS=5 instead of 20. Still produces meaningful "
                         "ranks, much faster.")
    p.add_argument("--multi-market", action="store_true",
                    help="Run three market scenarios (symmetric, buyers', "
                         "sellers') and emit a combined leaderboard.")
    p.add_argument("--with-gemini", action="store_true",
                    help="Add GeminiFlashVanilla as a player (needs GOOGLE_API_KEY).")
    p.add_argument("--out-dir", type=Path,
                    default=Path(__file__).parent / "results")
    args = p.parse_args()

    if args.quick:
        os.environ["SNHP_TOURNAMENT_QUICK"] = "1"

    if args.with_gemini and not os.environ.get("GOOGLE_API_KEY", "").strip():
        print("WARNING: --with-gemini requested but GOOGLE_API_KEY not set. "
              "Gemini will use heuristic fallback (clearly labeled in output).")

    # Import the tournament module + register the LLM player BEFORE
    # `run_round_robin` reads the roster. The roster is built per-call from
    # B2B_OPPONENTS + the SNHP/Aspiration fixed slots, so we monkey-add to
    # the OPPONENTS dict.
    import b2b_round_robin as trnmt
    from b2b_opponents import B2B_OPPONENTS

    if args.quick:
        trnmt.N_ROUNDS = 5

    extra_player_names: list[str] = []
    if args.with_gemini:
        from leaderboard.agents.gemini_negmas import GeminiFlashVanilla
        B2B_OPPONENTS["GeminiFlashVanilla"] = GeminiFlashVanilla
        extra_player_names.append("GeminiFlashVanilla")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.multi_market:
        markets = [
            ("symmetric",    1.0, 1.0),
            ("buyers_market", 1.5, 1.0),  # seller under pressure
            ("sellers_market", 1.0, 1.5),  # buyer under pressure
        ]
    else:
        markets = [("symmetric", 1.0, 1.0)]

    market_results: dict[str, dict] = {}
    total_t0 = time.time()
    for market_name, sp, bp in markets:
        print(f"\n=== Running {market_name} (seller_pressure={sp}, buyer_pressure={bp}) ===")
        t0 = time.time()
        rankings, pairwise, _scores = trnmt.run_round_robin(
            seller_pressure=sp, buyer_pressure=bp,
        )
        elapsed = time.time() - t0
        market_results[market_name] = {
            "wall_seconds": round(elapsed, 1),
            "seller_pressure": sp,
            "buyer_pressure": bp,
            "rankings": rankings,
            "pairwise": [
                {"a": k[0], "b": k[1],
                 "a_util": round(v[0], 4),
                 "b_util": round(v[1], 4),
                 "deal_rate": round(v[2], 4)}
                for k, v in pairwise.items()
            ],
        }

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness": "snhp/b2b_round_robin.py (multi-attribute SAO, NegMAS)",
        "config": {
            "n_rounds": trnmt.N_ROUNDS,
            "n_steps": trnmt.N_STEPS,
            "randomize_steps": trnmt.RANDOMIZE_STEPS,
            "batna_center": trnmt.BATNA_CENTER,
            "batna_range": trnmt.BATNA_RANGE,
            "must_deal_base_prob": trnmt.MUST_DEAL_BASE_PROB,
            "n_workers": trnmt.N_WORKERS,
            "total_wall_seconds": round(time.time() - total_t0, 1),
        },
        "extra_players": extra_player_names,
        "markets": market_results,
    }

    out_path = args.out_dir / "leaderboard.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=_json_default))
    print(f"\nWrote {out_path}")
    print(f"\nSNHP rank by market:")
    for market_name, market_data in market_results.items():
        for i, row in enumerate(market_data["rankings"], start=1):
            if row["name"] == "SNHP":
                print(f"  {market_name:<16} rank {i:>2}/{len(market_data['rankings'])}  "
                      f"avg={row['avg']:.4f}  W/T/L={row['wins']}/{row['ties']}/{row['losses']}")
                break


def _json_default(o):
    """Best-effort JSON encoder for numpy types and any straggler."""
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


if __name__ == "__main__":
    main()
