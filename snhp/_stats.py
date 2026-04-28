"""
Statistical helpers shared across SNHP code.

Lives in its own module with NO snhp-package imports so it can be safely
imported from both `snhp.benchmark` (which uses the `snhp.` prefix) and
`b2b_round_robin.py` (which imports `negmas_agent` bare). Avoids the
import-chain issue that previously forced the math to be inlined twice.
"""
from __future__ import annotations

import math as _math
import numpy as np


_BOOTSTRAP_N = 1000
_MASTER_SEED = 42


def bootstrap_ci(data, n_boot: int = _BOOTSTRAP_N, alpha: float = 0.05):
    """Bootstrap CI on the mean. Returns (mean, lo, hi)."""
    if not data:
        return (0.0, 0.0, 0.0)
    rng = np.random.RandomState(_MASTER_SEED)
    arr = np.array(data)
    means = np.array([
        np.mean(rng.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    return (
        float(np.mean(arr)),
        float(np.percentile(means, 100 * alpha / 2)),
        float(np.percentile(means, 100 * (1 - alpha / 2))),
    )


def wilcoxon_approx(x, y) -> float:
    """Paired Wilcoxon signed-rank test using normal approximation. Returns p-value."""
    n = min(len(x), len(y))
    if n < 5:
        return 1.0
    diffs = [x[i] - y[i] for i in range(n)]
    diffs = [d for d in diffs if abs(d) > 1e-10]
    n = len(diffs)
    if n < 5:
        return 1.0
    abs_d = sorted(enumerate(diffs), key=lambda t: abs(t[1]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(abs(abs_d[j][1]) - abs(abs_d[i][1])) < 1e-10:
            j += 1
        avg_rank = (i + j + 1) / 2
        for k in range(i, j):
            ranks[abs_d[k][0]] = avg_rank
        i = j
    w_plus = sum(ranks[i] for i in range(n) if diffs[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if diffs[i] < 0)
    W = min(w_plus, w_minus)
    mu = n * (n + 1) / 4
    sigma = _math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma < 1e-10:
        return 1.0
    z = abs(W - mu) / sigma
    return 2 * (1 - 0.5 * (1 + _math.erf(z / _math.sqrt(2))))
