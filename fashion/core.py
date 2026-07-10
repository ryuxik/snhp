"""Shared primitives for the FASHION sim.

Self-contained by design: `substream` is copied verbatim from vend/core.py
and `paired_ci` from vend/run.py (vend is being edited concurrently, so
fashion/ must not import it). Same house rules apply: every random draw
comes from a blake2b substream of the master seed, arms are compared on
paired seeds, and headline intervals are honest t-intervals.
"""
from __future__ import annotations

import functools
import hashlib
import math

import numpy as np


def substream(master_seed: int, *parts) -> int:
    """Deterministic child seed (the gauntlet pattern): blake2b of the
    master seed and any hashable parts, folded to 63 bits."""
    h = hashlib.blake2b(digest_size=8)
    h.update(str(master_seed).encode())
    for p in parts:
        h.update(b"|")
        h.update(str(p).encode())
    return int.from_bytes(h.digest(), "big") >> 1


def paired_ci(diffs: list[float], block: int = 1, nd: int = 2) -> dict:
    """Mean paired difference with a 95% t-interval.

    Unlike vend's day-level diffs (learner state carries across days),
    fashion SEASONS are independent replications by construction — every
    season draws a fresh buy, fresh calibration noise, and a fresh consumer
    stream from its own substream. So block=1 (plain t on season diffs) is
    the honest default here; `block` is kept for API parity and for anyone
    who later introduces cross-season state (e.g. the H-F3 waiter-training
    dynamic)."""
    d = np.asarray(diffs, dtype=float)
    if block > 1 and len(d) >= 2 * block:
        n_blocks = len(d) // block
        d = d[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    n = len(d)
    mean = float(d.mean())
    if n < 2:
        return {"mean": round(mean, nd), "ci95": None, "n": n}
    se = float(d.std(ddof=1) / math.sqrt(n))
    from scipy import stats
    t = float(stats.t.ppf(0.975, n - 1))
    return {"mean": round(mean, nd),
            "ci95": [round(mean - t * se, nd), round(mean + t * se, nd)],
            "n": n, "block": block}


@functools.lru_cache(maxsize=65536)
def poisson_cdf(k: int, mu: float) -> float:
    """P(Poisson(mu) <= k), exact term sum — used by the strategic waiter's
    survival estimate. Kept in pure math (no scipy) because it sits inside
    the per-consumer decision loop."""
    if k < 0:
        return 0.0
    if mu <= 0:
        return 1.0
    term = math.exp(-mu)
    total = term
    for j in range(1, k + 1):
        term *= mu / j
        total += term
    return min(total, 1.0)
