"""
Round-robin tournament: each agent plays every other agent N times as both
seller and buyer, with reservations sampled iid from a fixed prior.

Output: leaderboard.json with per-agent rank, mean utility, deal rate,
and pairwise table. Plus a small set of saved transcripts for the
landing page's narrative-style cards.
"""
from __future__ import annotations

import json
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from leaderboard.agents import REGISTRY, LABELS
from leaderboard.protocol import play_game, GameOutcome


def run(
    *,
    agent_names: list[str],
    n_reps_per_pairing: int = 30,
    deadline_rounds: int = 10,
    reservation_low: float = 0.20,
    reservation_high: float = 0.50,
    seed: int = 42,
    out_dir: Path,
    capture_transcript_every: Optional[int] = None,
) -> dict:
    """Run a full round-robin and write `leaderboard.json` to `out_dir`."""
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Per-agent rolling stats. We track each AGENT's utility over every game
    # the agent played (in either role) — that's what gets ranked.
    util_samples: dict[str, list[float]] = {n: [] for n in agent_names}
    deal_count: dict[str, int] = {n: 0 for n in agent_names}
    games_played: dict[str, int] = {n: 0 for n in agent_names}
    pairwise_stats: dict[tuple[str, str], dict] = {}  # (a, b) → {a_util_mean, b_util_mean, deal_rate}

    saved_transcripts: list[dict] = []

    for a_name in agent_names:
        for b_name in agent_names:
            if a_name == b_name:
                continue
            pair_a_utils: list[float] = []
            pair_b_utils: list[float] = []
            pair_deals = 0
            for rep in range(n_reps_per_pairing):
                seller_res = rng.uniform(reservation_low, reservation_high)
                buyer_res = rng.uniform(reservation_low, reservation_high)
                a_outcome, b_outcome = play_game(
                    seller=REGISTRY[a_name],
                    buyer=REGISTRY[b_name],
                    seller_reservation=seller_res,
                    buyer_reservation=buyer_res,
                    deadline_rounds=deadline_rounds,
                )
                util_samples[a_name].append(a_outcome.my_utility)
                util_samples[b_name].append(b_outcome.my_utility)
                games_played[a_name] += 1
                games_played[b_name] += 1
                deal_count[a_name] += int(a_outcome.deal_closed)
                deal_count[b_name] += int(b_outcome.deal_closed)
                pair_a_utils.append(a_outcome.my_utility)
                pair_b_utils.append(b_outcome.my_utility)
                pair_deals += int(a_outcome.deal_closed)

                if (capture_transcript_every is not None
                        and rep % capture_transcript_every == 0
                        and len(saved_transcripts) < 10):
                    saved_transcripts.append({
                        "seller": a_name, "buyer": b_name,
                        "seller_reservation": round(seller_res, 3),
                        "buyer_reservation": round(buyer_res, 3),
                        "transcript": a_outcome.transcript,
                        "outcome": {
                            "deal_closed": a_outcome.deal_closed,
                            "seller_utility": round(a_outcome.my_utility, 3),
                            "buyer_utility": round(b_outcome.my_utility, 3),
                        },
                    })

            pairwise_stats[(a_name, b_name)] = {
                "a_util_mean": _safe_mean(pair_a_utils),
                "b_util_mean": _safe_mean(pair_b_utils),
                "deal_rate": pair_deals / n_reps_per_pairing,
            }

    # Per-agent aggregate ranking.
    rows = []
    for name in agent_names:
        utils = util_samples[name]
        rows.append({
            "name": name,
            "label": LABELS[name],
            "avg_utility": _safe_mean(utils),
            "median_utility": _safe_median(utils),
            "deal_rate": deal_count[name] / max(1, games_played[name]),
            "n_games": games_played[name],
            "ci95_low": _bootstrap_ci(utils, 0.025),
            "ci95_high": _bootstrap_ci(utils, 0.975),
        })
    rows.sort(key=lambda r: r["avg_utility"], reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
        row["avg_utility"] = round(row["avg_utility"], 4)
        row["median_utility"] = round(row["median_utility"], 4)
        row["deal_rate"] = round(row["deal_rate"], 4)
        row["ci95_low"] = round(row["ci95_low"], 4)
        row["ci95_high"] = round(row["ci95_high"], 4)

    leaderboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "n_reps_per_pairing": n_reps_per_pairing,
            "deadline_rounds": deadline_rounds,
            "reservation_low": reservation_low,
            "reservation_high": reservation_high,
            "seed": seed,
        },
        "rankings": rows,
        "pairwise": [
            {"seller": k[0], "buyer": k[1], **v}
            for k, v in pairwise_stats.items()
        ],
    }

    (out_dir / "leaderboard.json").write_text(
        json.dumps(leaderboard, indent=2, sort_keys=False))
    if saved_transcripts:
        (out_dir / "transcripts.json").write_text(
            json.dumps({"transcripts": saved_transcripts}, indent=2))

    return leaderboard


def _safe_mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else 0.0


def _safe_median(xs: list[float]) -> float:
    return statistics.median(xs) if xs else 0.0


def _bootstrap_ci(xs: list[float], q: float, n: int = 1000) -> float:
    """Cheap bootstrap CI quantile. Returns the q-th quantile of n
    bootstrap means."""
    if not xs:
        return 0.0
    rng = random.Random(0)
    means = []
    for _ in range(n):
        sample = [rng.choice(xs) for _ in range(len(xs))]
        means.append(sum(sample) / len(sample))
    means.sort()
    idx = max(0, min(len(means) - 1, int(q * len(means))))
    return means[idx]
