"""AMENDMENT 3 §A3.2 — agent utilities drawn from demographics, not taste.

EVERY distribution is labelled ANCHORED (traceable to published data) or
INVENTED (our choice, no published counterpart). The labels are reproduced in
the results table, per A3.5.

    income        ANCHORED level / INVENTED dispersion. ACS median renter
                  household income is ~$54k; a market-rate $2,000/mo apartment
                  skews to a higher-income segment, so the median here is
                  $75,000. sigma_log = 0.55 is INVENTED.
    cost burden   DERIVED: rent/income > 0.30. At the anchor rent this makes
                  ~55% of tenants cost-burdened, against a published ~50%.
    utility       DERIVED, not assumed: CRRA over residual income (eta = 1.5).
                  A cost-burdened tenant therefore has a steeper marginal
                  utility of rent automatically -- we do not impose it.
    household     ANCHORED (approx). ACS renter household size shares.
    job flex      INVENTED. Beta(2,3).
    moving cost   INVENTED functional form, ANCHORED scale: rises with household
                  size and income, falls with job flexibility, with the constant
                  set so the median total switching cost matches the ~$7,200
                  Phase 1 calibrated to observed retention/elasticity.
    priorities    INVENTED, and unavoidably so: nobody has published tenant
                  priority weights across rent/term/credit/fees. This is the
                  same evidence gap the article is about. Dirichlet(2.5, 1.0,
                  1.2, 0.8) over (rent, term, credit, fees).

The Dirichlet is the whole point of A3.2: a tenant who values term above rent is
what logrolling exists for. `share_term_over_rent()` reports how many there are,
so if the answer were zero we would say logrolling cannot help and K1/K13 deserve
to fire.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ANCHOR_RENT = 2000.0
ISSUES = ("rent", "term", "one_time_credit", "fees")

# --- ANCHORED level, INVENTED dispersion ---
INCOME_MEDIAN = 75_000.0
INCOME_SIGMA = 0.55
# --- ANCHORED (approx), ACS renter household size ---
HH_SIZES = (1, 2, 3, 4)
HH_PROBS = (0.37, 0.31, 0.16, 0.16)
# --- INVENTED ---
JOB_FLEX_A, JOB_FLEX_B = 2.0, 3.0
MOVE_C0 = 4750.0
CRRA_ETA = 1.5
# --- INVENTED, and the evidence gap the article is about ---
DIRICHLET_ALPHA = (2.5, 1.0, 1.2, 0.8)

BURDEN_THRESHOLD = 0.30

LABELS = {
    "income": "ANCHORED level (ACS renter median, market-rate segment) / "
              "INVENTED dispersion",
    "cost_burden": "DERIVED from rent/income > 0.30",
    "utility_of_rent": "DERIVED: CRRA(eta=1.5) over residual income",
    "household_size": "ANCHORED (approx) ACS renter household size",
    "job_flexibility": "INVENTED Beta(2,3)",
    "moving_cost": "INVENTED form, ANCHORED scale (median ~$7,200)",
    "priority_weights": "INVENTED Dirichlet(2.5,1.0,1.2,0.8) -- no published "
                        "counterpart exists",
    "station_costs": "ANCHORED NAA/IREM/BOMA turn cost, vacancy, opex",
    "station_priorities": "DERIVED from the station's own NPV, not drawn",
}


@dataclass(frozen=True)
class Tenant:
    income: float
    hh_size: int
    job_flex: float
    move_cost: float          # dollars
    w: tuple                  # priority weights over ISSUES
    burdened: bool


def draw_tenant(u) -> Tenant:
    """One tenant from a vector of uniforms (so it stays inside the simulation's
    common-random-number scheme -- no fresh RNG)."""
    from crabs.world import _norm_ppf
    income = float(np.exp(np.log(INCOME_MEDIAN) + INCOME_SIGMA
                          * _norm_ppf(u[0])))
    cum = np.cumsum(HH_PROBS)
    hh = int(HH_SIZES[int(np.searchsorted(cum, min(u[1], 0.999)))])
    job = float(_beta_ppf(u[2], JOB_FLEX_A, JOB_FLEX_B))
    move = (MOVE_C0 * hh ** 0.45 * (income / INCOME_MEDIAN) ** 0.25
            / (0.5 + job))
    w = _dirichlet_from_uniforms(u[3:7], DIRICHLET_ALPHA)
    return Tenant(income=income, hh_size=hh, job_flex=job, move_cost=move, w=w,
                  burdened=(12.0 * ANCHOR_RENT / income) > BURDEN_THRESHOLD)


def _beta_ppf(x, a, b, n=64):
    """Inverse Beta CDF by a fixed grid, so it is deterministic and needs no
    scipy at simulation time."""
    g = (np.arange(n) + 0.5) / n
    pdf = g ** (a - 1.0) * (1.0 - g) ** (b - 1.0)
    cdf = np.cumsum(pdf)
    cdf /= cdf[-1]
    return float(g[int(np.searchsorted(cdf, min(max(x, 1e-6), 1 - 1e-6)))])


def _dirichlet_from_uniforms(us, alpha):
    """Dirichlet via normalised Gamma draws, using the uniforms already in the
    CRN stream. Gamma inverse-CDF by a fixed grid -- deterministic."""
    out = []
    for x, a in zip(us, alpha):
        out.append(_gamma_ppf(x, a))
    s = sum(out)
    return tuple(v / s for v in out) if s > 0 else tuple(1.0 / len(alpha)
                                                         for _ in alpha)


_GAMMA_GRID = np.linspace(1e-4, 14.0, 900)


def _gamma_ppf(x, a):
    pdf = _GAMMA_GRID ** (a - 1.0) * np.exp(-_GAMMA_GRID)
    cdf = np.cumsum(pdf)
    cdf /= cdf[-1]
    return float(_GAMMA_GRID[int(np.searchsorted(
        cdf, min(max(x, 1e-6), 1 - 1e-6)))])


# ------------------------------------------------------------------ utilities
def crra(x, eta=CRRA_ETA):
    """Utility of residual income. Steeper where income is low, which is what
    makes a cost-burdened tenant more rent-sensitive without being told to be."""
    x = np.maximum(np.asarray(x, dtype=float), 1.0)
    if abs(eta - 1.0) < 1e-9:
        return np.log(x)
    return (x ** (1.0 - eta) - 1.0) / (1.0 - eta)


def share_term_over_rent(n=200_000, seed=99) -> float:
    """How many tenants weight term above rent. If this were ~0, logrolling could
    not help and K13 would deserve to fire on the population, not the engine."""
    rng = np.random.default_rng(np.random.SeedSequence([seed]))
    d = rng.dirichlet(DIRICHLET_ALPHA, n)
    return float(np.mean(d[:, 1] > d[:, 0]))


def share_cost_burdened(n=200_000, seed=98, rent=ANCHOR_RENT) -> float:
    rng = np.random.default_rng(np.random.SeedSequence([seed]))
    inc = rng.lognormal(np.log(INCOME_MEDIAN), INCOME_SIGMA, n)
    return float(np.mean(12.0 * rent / inc > BURDEN_THRESHOLD))


def median_move_cost(n=200_000, seed=97) -> float:
    rng = np.random.default_rng(np.random.SeedSequence([seed]))
    u = rng.random((n, 7))
    vals = [draw_tenant(u[i]).move_cost for i in range(0, n, 200)]
    return float(np.median(vals))
