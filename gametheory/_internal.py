"""
Shared internals for the gametheory package: SNHP-import path setup, prior
validation, auction-format and prior-family Literal types.

Lives in one module so duplication doesn't accrete as more handlers are added.
"""
from __future__ import annotations

import os
import sys
from typing import Literal, get_args

import numpy as np
from scipy import stats
from scipy.optimize import brentq


# ─── SNHP import path setup ──────────────────────────────────────────────────
# The snhp/ package isn't a proper installed package — it's a sibling
# directory we reach into for math primitives. Centralizing the sys.path
# manipulation here means future reach-ins don't have to re-implement the
# pattern. Idempotent (no-op if already on path).

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SNHP_DIR = os.path.join(_REPO_ROOT, "snhp")


def ensure_snhp_path() -> None:
    if _SNHP_DIR not in sys.path:
        sys.path.insert(0, _SNHP_DIR)


# Eager: callers import from snhp at module load, so do this on import.
ensure_snhp_path()


# ─── Auction format & prior family Literal types ────────────────────────────

AuctionFormat = Literal["first_price", "second_price_vickrey", "english_ascending"]
PriorFamily = Literal["lognorm", "uniform"]

VALID_AUCTION_FORMATS: tuple[str, ...] = get_args(AuctionFormat)
VALID_PRIOR_FAMILIES: tuple[str, ...] = get_args(PriorFamily)


def validate_prior(prior: dict) -> None:
    """
    Validate a prior dict has the required shape:
      {family: "lognorm"|"uniform", params: {...required keys...}}
    Raises ValueError on any structural problem.
    """
    family = prior.get("family")
    if family not in VALID_PRIOR_FAMILIES:
        raise ValueError(
            f"prior.family must be one of {VALID_PRIOR_FAMILIES}, got {family!r}"
        )
    params = prior.get("params") or {}
    if family == "lognorm":
        if "mu" not in params or "sigma" not in params:
            raise ValueError("lognorm prior requires params.mu and params.sigma")
    elif family == "uniform":
        if "low" not in params or "high" not in params:
            raise ValueError("uniform prior requires params.low and params.high")
        if params["high"] <= params["low"]:
            raise ValueError("uniform high must exceed low")


# ─── Prior helpers (shared across Tier 2/Tier 3) ─────────────────────────────


def prior_to_scipy_dist(prior: dict):
    """Build a frozen scipy.stats distribution from a {family, params} dict."""
    family = prior["family"]
    params = prior["params"]
    if family == "uniform":
        return stats.uniform(loc=params["low"], scale=params["high"] - params["low"])
    return stats.lognorm(s=params["sigma"], scale=np.exp(params["mu"]))


def sample_prior(prior: dict, n: int, rng) -> np.ndarray:
    """Vectorized iid sample of size n from a {family, params} prior."""
    family = prior["family"]
    params = prior["params"]
    if family == "uniform":
        return rng.uniform(params["low"], params["high"], size=n)
    return rng.lognormal(mean=params["mu"], sigma=params["sigma"], size=n)


def myerson_reserve(prior: dict, seller_valuation: float) -> float:
    """
    Solve the Myerson virtual-value-equal-seller-valuation reserve. Closed
    form for uniform priors; numerical brentq solve for lognormal. Falls
    back to the lognormal median if no sign change in the search interval.
    """
    family = prior["family"]
    params = prior["params"]
    if family == "uniform":
        a, b = params["low"], params["high"]
        return max((b + seller_valuation) / 2.0, seller_valuation, a)
    mu, sigma = params["mu"], params["sigma"]
    dist = stats.lognorm(s=sigma, scale=np.exp(mu))

    def virtual_value_minus_seller(v: float) -> float:
        F = float(dist.cdf(v))
        f = float(dist.pdf(v))
        if f < 1e-12:
            return float("inf")
        return v - (1.0 - F) / f - seller_valuation

    try:
        r = float(brentq(
            virtual_value_minus_seller,
            np.exp(mu) * 0.01, np.exp(mu) * 100.0,
        ))
    except ValueError:
        r = float(np.exp(mu))
    return max(r, seller_valuation)
