"""
Run the public leaderboard.

Usage:
  python -m leaderboard.run                # default 7-agent bracket, ~1 min
  python -m leaderboard.run --with-gemini  # include gemini-flash-vanilla
                                            # (needs GOOGLE_API_KEY)

Default agent panel deliberately omits the LLM — running without an API
key still produces a complete artifact for the landing page; the LLM
slot can be added once a key is exported.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from leaderboard.tournament import run as run_tournament


_DEFAULT_AGENTS = [
    "random",
    "fair-demand",
    "split-the-diff",
    "anchorer",
    "aspiration",
    "snhp-vanilla",
    "snhp-tuned",
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--with-gemini", action="store_true",
                    help="Include gemini-flash-vanilla (requires GOOGLE_API_KEY).")
    p.add_argument("--reps", type=int, default=30,
                    help="N reps per pairing (default 30).")
    p.add_argument("--rounds", type=int, default=10,
                    help="Deadline rounds per game (default 10).")
    p.add_argument("--out-dir", type=Path,
                    default=Path(__file__).parent / "results",
                    help="Output directory for leaderboard.json + transcripts.json.")
    args = p.parse_args()

    agents = list(_DEFAULT_AGENTS)
    if args.with_gemini:
        if not os.environ.get("GOOGLE_API_KEY", "").strip():
            print("WARNING: GOOGLE_API_KEY not set — gemini-flash-vanilla "
                  "will use the deterministic fallback (aspiration). "
                  "Export your key for a real LLM run.")
        agents.append("gemini-flash-vanilla")

    print(f"Running leaderboard: {len(agents)} agents × "
          f"{args.reps} reps × {args.rounds} rounds")
    print(f"Agents: {', '.join(agents)}")

    leaderboard = run_tournament(
        agent_names=agents,
        n_reps_per_pairing=args.reps,
        deadline_rounds=args.rounds,
        out_dir=args.out_dir,
        capture_transcript_every=10,
    )

    print()
    print(f"{'Rank':<5} {'Agent':<25} {'Avg utility':<14} {'Deal rate':<12}")
    print("-" * 60)
    for row in leaderboard["rankings"]:
        print(f"{row['rank']:<5} {row['name']:<25} {row['avg_utility']:<14.3f} "
              f"{row['deal_rate']:<12.1%}")
    print()
    print(f"Wrote {args.out_dir / 'leaderboard.json'}")


if __name__ == "__main__":
    main()
