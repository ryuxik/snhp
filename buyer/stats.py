"""Paired-difference statistics. Copied (not imported) from vend's pattern so
the buyer package stays decoupled — no win claim when the 95% CI includes 0."""
from __future__ import annotations

import math


def paired_ci(diffs: list[float]) -> dict:
    """Mean paired difference with a 95% t-interval. Observations here are
    independent buyers (paired on identity across arms), so no blocking is
    needed. Returns mean, ci95=[lo,hi], n, and `significant` (CI excludes 0)."""
    import numpy as np
    d = np.asarray(diffs, dtype=float)
    n = len(d)
    mean = float(d.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 4), "ci95": None, "n": n,
                "significant": False}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    lo, hi = mean - t * se, mean + t * se
    return {"mean": round(mean, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "n": n, "significant": bool(lo > 0 or hi < 0)}


def mean_ci(xs: list[float]) -> dict:
    """95% CI for a single mean (level, not a paired diff)."""
    import numpy as np
    x = np.asarray(xs, dtype=float)
    n = len(x)
    mean = float(x.mean()) if n else 0.0
    if n < 2:
        return {"mean": round(mean, 4), "ci95": None, "n": n}
    se = float(x.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, 4),
            "ci95": [round(mean - t * se, 4), round(mean + t * se, 4)], "n": n}
