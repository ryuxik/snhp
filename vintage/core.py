"""Shared primitives for the VINTAGE sim.

Self-contained by design: `substream` is copied verbatim from vend/core.py
and `paired_ci` from fashion/core.py (those packages evolve concurrently, so
vintage/ must not import them). Same house rules apply: every random draw
comes from a blake2b substream of the master seed, arms are compared on
paired seeds, and headline intervals are honest t-intervals.
"""
from __future__ import annotations

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

    VINTAGE replicates are independent STORES (fresh sourcing, fresh
    browsers, fresh learner state per rep), so block=1 on rep-level diffs is
    the honest default. `block` is kept for day-level diagnostics, where
    one-of-one inventory carries state across days and plain daily t would
    be too tight."""
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


_SQRT2 = math.sqrt(2.0)


def lognorm_sf(price: float, scale: float, sigma: float) -> float:
    """P(X > price) under lognormal(log scale, sigma) — scalar, pure math."""
    if scale <= 0 or price <= 0:
        return 0.0 if scale <= 0 else 1.0
    z = math.log(price / scale) / sigma
    return 0.5 * math.erfc(z / _SQRT2)


def lognorm_sf_vec(price: float, scales: np.ndarray, sigma: float) -> np.ndarray:
    """Vectorized lognormal survival over an array of scales."""
    from scipy.special import erfc
    if price <= 0:
        return np.ones_like(scales)
    z = np.log(price / scales) / sigma
    return 0.5 * erfc(z / _SQRT2)
