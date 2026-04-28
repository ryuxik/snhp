"""
Gallego-van Ryzin posted-price optimization.

Returns both the optimal static price (deterministic upper bound;
ship-ready, near-optimal at high λT) and a dynamic price schedule from
backward DP over (inventory, time) — the operator sees the dynamic uplift
explicitly so they can decide whether the operational complexity is worth it.
"""
from __future__ import annotations

import numpy as np
from scipy import stats
from scipy.optimize import minimize_scalar

from gametheory._internal import validate_prior, prior_to_scipy_dist


_DEFAULT_SIMS = 2_000
_DP_PRICE_GRID = 50
_MIN_DP_BINS = 60
# DP step size targets P(sale per bin) ≤ this so the two-state
# (no-sale | one-sale) approximation stays tight. Cost: more bins.
_DP_BIN_TARGET_LOAD = 0.2


def _price_search_range(prior: dict) -> tuple[float, float]:
    family = prior["family"]
    params = prior["params"]
    if family == "uniform":
        return params["low"], params["high"]
    return float(np.exp(params["mu"]) * 0.05), float(np.exp(params["mu"]) * 5.0)


def _expected_revenue_static(price: float, dist, arrival_rate: float,
                              C: int, T: float) -> float:
    """E[revenue] for a static price under Poisson arrivals & iid WTPs.

    Sales over T = min(N, C) where N ~ Poisson(λ · (1-F(p)) · T). The
    closed form: E[min(N, C)] = λ · P(N ≤ C-1) + C · P(N > C).
    """
    sale_prob = float(1.0 - dist.cdf(price))
    if sale_prob <= 0 or arrival_rate <= 0 or T <= 0:
        return 0.0
    lam = arrival_rate * sale_prob * T
    cdf_C_minus_1 = stats.poisson.cdf(C - 1, lam)
    cdf_C = stats.poisson.cdf(C, lam)
    expected_sales = lam * cdf_C_minus_1 + C * (1.0 - cdf_C)
    return float(price * expected_sales)


def _optimize_static_price(prior: dict, arrival_rate: float, C: int, T: float
                            ) -> tuple[float, float]:
    dist = prior_to_scipy_dist(prior)
    lo, hi = _price_search_range(prior)
    res = minimize_scalar(
        lambda p: -_expected_revenue_static(p, dist, arrival_rate, C, T),
        bounds=(lo, hi), method="bounded",
        options={"xatol": (hi - lo) * 1e-4},
    )
    return float(res.x), float(-res.fun)


def _simulate_static(price: float, prior: dict, arrival_rate: float,
                      C: int, T: float, n_sims: int, seed: int) -> dict:
    """
    Vectorized via Poisson thinning: #accepted-arrivals ~ Poisson(λ · (1-F) · T).
    Capped at inventory C. One rng.poisson call replaces the n_sims × per-arrival
    sampling loop.
    """
    rng = np.random.default_rng(seed)
    dist = prior_to_scipy_dist(prior)
    sale_prob = float(1.0 - dist.cdf(price))
    if sale_prob <= 0 or arrival_rate <= 0 or T <= 0:
        return {"mean_revenue": 0.0, "sellthrough_rate": 0.0}
    n_sales = rng.poisson(arrival_rate * sale_prob * T, size=n_sims)
    sold = np.minimum(n_sales, C)
    return {
        "mean_revenue": float((price * sold).mean()),
        "sellthrough_rate": float(sold.mean() / max(C, 1)),
    }


def _build_dynamic_schedule(prior: dict, arrival_rate: float, C: int, T: float
                             ) -> tuple[list[dict], float]:
    """
    Backward DP on (inventory, time-bin) grid. Step size is chosen so
    P(sale per bin) <= ~_DP_BIN_TARGET_LOAD, keeping the two-state
    approximation tight. Returns (schedule_samples, V_at_C_t0).
    """
    dist = prior_to_scipy_dist(prior)
    lo, hi = _price_search_range(prior)
    price_grid = np.linspace(lo, hi, _DP_PRICE_GRID)
    sale_prob = 1.0 - dist.cdf(price_grid)

    n_bins = max(_MIN_DP_BINS, int(np.ceil(arrival_rate * T / _DP_BIN_TARGET_LOAD)))
    dt = T / n_bins
    arrival_per_bin = arrival_rate * dt  # ≤ _DP_BIN_TARGET_LOAD by construction

    V = np.zeros(C + 1)
    # Sample ~10 schedule waypoints across the horizon, ending at t=0.
    sample_every = max(1, n_bins // 10)
    sample_at = set(range(1, n_bins + 1, sample_every)) | {1, n_bins}
    schedule: list[dict] = []

    for k in range(n_bins, 0, -1):
        sell_prob = arrival_per_bin * sale_prob   # shape (_DP_PRICE_GRID,)
        # value[c, j] = sell · (price[j] + V[c-1]) + (1-sell) · V[c]
        # Vectorized over c=1..C and j=0.._DP_PRICE_GRID-1.
        c_idx = np.arange(1, C + 1)
        # shape (C, P): sell_prob broadcasts across c
        gain = sell_prob[None, :] * (price_grid[None, :] + V[c_idx - 1, None])
        keep = (1.0 - sell_prob)[None, :] * V[c_idx, None]
        value = gain + keep
        best_j = value.argmax(axis=1)
        V_new = V.copy()
        V_new[c_idx] = value[np.arange(C), best_j]
        V = V_new
        if k in sample_at:
            schedule.append({
                "t_seconds": round((k - 1) * dt, 3),
                "recommended_price": round(float(price_grid[best_j[-1]]), 4),
                "value_estimate": round(float(V[C]), 4),
            })

    schedule.sort(key=lambda s: s["t_seconds"])
    return schedule, float(V[C])


def posted_price_optimal(
    *,
    buyer_arrival_prior: dict,
    arrival_rate_per_second: float,
    inventory: int,
    horizon_seconds: float,
    n_simulations: int = _DEFAULT_SIMS,
    seed: int = 42,
) -> dict:
    """
    Optimal posted-price policy for the Gallego-van Ryzin model.

    `buyer_arrival_prior` is the WTP distribution (uniform[a,b] or
    lognorm{mu,sigma}). Returns:

      {
        static_price, static_expected_revenue, static_simulated_revenue,
        dynamic_schedule[],            # (t_seconds, price) waypoints
        dynamic_value_estimate,        # V_C at t=0 from the DP
        sellthrough_rate,
        rationale,
      }
    """
    validate_prior(buyer_arrival_prior)
    if arrival_rate_per_second <= 0:
        raise ValueError("arrival_rate_per_second must be positive")
    if inventory < 1:
        raise ValueError("inventory must be >= 1")
    if horizon_seconds <= 0:
        raise ValueError("horizon_seconds must be positive")

    p_static, rev_analytical = _optimize_static_price(
        buyer_arrival_prior, arrival_rate_per_second, inventory, horizon_seconds
    )
    sim = _simulate_static(
        p_static, buyer_arrival_prior, arrival_rate_per_second,
        inventory, horizon_seconds, n_simulations, seed,
    )
    schedule, dynamic_v0 = _build_dynamic_schedule(
        buyer_arrival_prior, arrival_rate_per_second, inventory, horizon_seconds
    )

    return {
        "static_price": round(p_static, 4),
        "static_expected_revenue": round(rev_analytical, 4),
        "static_simulated_revenue": round(sim["mean_revenue"], 4),
        "dynamic_schedule": schedule,
        "dynamic_value_estimate": round(dynamic_v0, 4),
        "sellthrough_rate": round(sim["sellthrough_rate"], 4),
        "rationale": (
            f"Static price p* = {p_static:.4f} maximizes p · λ(p) over the "
            f"horizon; analytical E[rev] = {rev_analytical:.2f}, MC "
            f"E[rev] = {sim['mean_revenue']:.2f} ({n_simulations} sims). "
            f"Dynamic policy V(C, 0) = {dynamic_v0:.2f}; uplift over static "
            f"= {(dynamic_v0 - rev_analytical):.2f}. "
            f"Sellthrough rate {sim['sellthrough_rate']:.2%}."
        ),
    }
