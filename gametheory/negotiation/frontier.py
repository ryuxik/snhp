"""The Pareto-frontier oracle + the leaderboard metric — ONE implementation.

Three surfaces report "dollars left on the table": the arena science
(arena/scenarios.bundle_frontier), the gauntlet leaderboard
(arena/gauntlet/protocol), and the public MCP advisor (score_deal). They must
agree by construction, so the joint-welfare enumeration and the metric formulas
live here, at the engine layer, and everyone imports them.

Conventions: per-issue option utilities in [0,1] (normalize with
bundle._norm01 first — the same normalizer negotiate_bundle applies), priority
weights normalized to sum 1, "naive" = every issue at its middle option.
"""
from __future__ import annotations

import itertools
import math

NOTIONAL = 10_000        # $ per deal for the dollars-left framing
LOGROLL_MIN_HEADROOM = 0.02  # below this, a scenario has no meaningful logroll
MAX_OUTCOMES = 4000      # enumeration cap (same as negotiate_bundle)


def norm_weights(w, n: int) -> list[float]:
    """Non-negative weights → simplex; empty/degenerate → uniform."""
    a = [max(0.0, float(x)) for x in list(w)[:n]]
    a += [0.0] * (n - len(a))
    s = sum(a)
    return [x / s for x in a] if s > 1e-9 else [1.0 / n] * n


def joint_frontier(u_a: list, u_b: list, w_a, w_b) -> tuple[float, float]:
    """(max joint welfare, naive middle-split welfare) over the outcome space.

    u_a/u_b: per issue, one utility per option, each side's OWN scale already
    normalized to [0,1]. w_a/w_b: per-issue priority weights (any scale).
    """
    n = len(u_a)
    if n == 0 or len(u_b) != n:
        raise ValueError("u_a and u_b must list the same non-zero number of issues")
    n_outcomes = math.prod(len(o) for o in u_a)
    if n_outcomes > MAX_OUTCOMES:
        raise ValueError(f"outcome space is {n_outcomes} combinations (> {MAX_OUTCOMES})")
    wa, wb = norm_weights(w_a, n), norm_weights(w_b, n)

    def joint(combo):
        return (sum(wa[i] * u_a[i][combo[i]] for i in range(n))
                + sum(wb[i] * u_b[i][combo[i]] for i in range(n)))

    best = max(joint(c) for c in itertools.product(*[range(len(o)) for o in u_a]))
    naive = joint(tuple(len(o) // 2 for o in u_a))
    return float(best), float(naive)


def deal_metrics(joint: float, best: float, naive: float,
                 notional: float = NOTIONAL) -> dict:
    """The leaderboard metric, from a realized joint welfare + the oracle pair."""
    if best <= 1e-9:
        return {"capture": 0.0, "logroll": None, "dollars_left": 0.0}
    headroom = best - naive
    return {
        "capture": float(joint / best),
        "logroll": (float((joint - naive) / headroom)
                    if headroom > LOGROLL_MIN_HEADROOM else None),
        "dollars_left": float(max(0.0, (best - joint) / best) * notional),
    }
