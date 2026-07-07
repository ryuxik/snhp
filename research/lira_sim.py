"""Erik Lira (Cruz Azul), July 2026 — the deliberate discount, modeled.

Reported facts:
  - 26 (May 8, 2000), DM, Cruz Azul captain. Contract to June 2029 (extension
    signed late 2025). Pumas -> Cruz Azul, Jan 2022, ~EUR 4m.
  - ETV ~EUR 11.6m (~$12m); Ajax's estimated offer EUR 12m (April).
  - WC 2026: started incl. the England R16; 1 assist + 88.3% passing + two
    clean sheets in the first two group games. Post-WC interest: Betis, Girona,
    Sevilla, Napoli, Ajax, Lens, Benfica, PL clubs (reports).
  - The extension reportedly includes a EUROPE-ONLY release clause set
    "accessible" at ~$7-8m as a gentleman's agreement (single-source report).

All money in $m. Everything modeled is swept in the MC.
"""
import json
import numpy as np

from gametheory.mechanism.posted_price import posted_price_optimal

RNG = np.random.default_rng(21)
OUT = {}

MEDIAN_V = 12.0     # market value of a WC-proven 26yo DM to a serious buyer
SIGMA = 0.25        # LOW dispersion: everyone knows what a 26yo DM is
CLAUSE = 7.5        # reported $7-8m, midpoint
NSIM = 200_000

def second_highest(median, sigma, n, seed):
    v = np.random.default_rng(seed).lognormal(np.log(median), sigma, size=(NSIM, n))
    v = np.sort(v, axis=1)
    return float(v[:, -2].mean()) if n > 1 else float(np.nan)

# ----------------------------------------------------------------------------
# A. The clause vs the market (compressed auction: low sigma)
# ----------------------------------------------------------------------------
curve = []
for n in range(1, 7):
    if n == 1:
        v = np.random.default_rng(100).lognormal(np.log(MEDIAN_V), SIGMA, NSIM)
        keep = 6.0  # sporting value floor of keeping the captain (modeled)
        price = float(np.mean((v[v > keep] + keep) / 2))
        curve.append({"n": 1, "exp_price": round(price, 2), "mode": "bilateral Nash"})
    else:
        curve.append({"n": n, "exp_price": round(second_highest(MEDIAN_V, SIGMA, n, 100 + n), 2),
                      "mode": "English, no reserve"})
OUT["curve"] = curve
n3 = curve[2]["exp_price"]
OUT["clause_gap"] = {
    "clause": CLAUSE,
    "vs_three_bidders": round(n3 - CLAUSE, 2),
    "vs_two": round(curve[1]["exp_price"] - CLAUSE, 2),
    "vs_six": round(curve[5]["exp_price"] - CLAUSE, 2),
    "p_trigger": round(float((np.random.default_rng(7).lognormal(np.log(MEDIAN_V), SIGMA, NSIM) > CLAUSE).mean()), 4),
}

# ----------------------------------------------------------------------------
# B. The window: Gallego-van Ryzin optimal posted price + markdown schedule
#    Units: "seconds" = days. This window: ~56 days to Sept 1, ~4 serious
#    buyer-arrivals expected (the WC spike). Next 12 months if he stays:
#    demand decays (age 27, no shop window) - fewer arrivals, lower WTP.
# ----------------------------------------------------------------------------
PRIOR_NOW = {"family": "lognorm", "params": {"mu": float(np.log(MEDIAN_V)), "sigma": SIGMA}}
now = posted_price_optimal(
    buyer_arrival_prior=PRIOR_NOW, arrival_rate_per_second=4 / 56,
    inventory=1, horizon_seconds=56, seed=42,
)
DECAY = 0.15  # WTP decay if he doesn't move in this window (age + hype half-life)
PRIOR_LATER = {"family": "lognorm", "params": {"mu": float(np.log(MEDIAN_V * (1 - DECAY))), "sigma": SIGMA}}
later = posted_price_optimal(
    buyer_arrival_prior=PRIOR_LATER, arrival_rate_per_second=3 / 365,
    inventory=1, horizon_seconds=365, seed=43,
)

# Fine-grained reference DP (audit fix: the engine's 50-point price grid
# quantizes schedule prices; per-bin sale prob uses the exact exponential form).
from scipy.stats import lognorm as _ln0

def fine_gvr(median, sigma, lam_total, salvage=0.0, nbins=4000, pgrid=None):
    dist = _ln0(s=sigma, scale=median)
    if pgrid is None:
        pgrid = np.linspace(6.0, 20.0, 1401)
    sf = dist.sf(pgrid)
    psale = 1 - np.exp(-(lam_total / nbins) * sf)
    V = salvage
    argmax_path = np.empty(nbins)
    for t in range(nbins - 1, -1, -1):
        vals = psale * pgrid + (1 - psale) * V
        i = int(np.argmax(vals))
        V = float(vals[i])
        argmax_path[t] = pgrid[i]
    return V, argmax_path

v0_now, path_now = fine_gvr(MEDIAN_V, SIGMA, 4.0)
v0_now_s, _ = fine_gvr(MEDIAN_V, SIGMA, 4.0, salvage=6.0)
v0_lat, _ = fine_gvr(MEDIAN_V * (1 - DECAY), SIGMA, 3.0)
v0_lat_s, _ = fine_gvr(MEDIAN_V * (1 - DECAY), SIGMA, 3.0, salvage=6.0)
# downsample the fine schedule to ~12 day-indexed waypoints over 56 days
idx = np.linspace(0, 3999, 12).astype(int)
schedule_fine = [[round(56 * i / 4000, 1), round(float(path_now[i]), 2)] for i in idx]

OUT["window"] = {
    "now": {"static_price": now["static_price"], "static_ev": now["static_expected_revenue"],
            "engine_dynamic_v0": now["dynamic_value_estimate"],
            "fine_dynamic_v0": round(v0_now, 2), "sellthrough": now["sellthrough_rate"],
            "schedule_fine": schedule_fine},
    "later_12mo": {"static_price": later["static_price"], "static_ev": later["static_expected_revenue"],
                   "fine_dynamic_v0": round(v0_lat, 2)},
    "window_premium_revenue_only": round(v0_now - v0_lat, 2),
    "window_premium_keepvalue_adj": round(v0_now_s - v0_lat_s, 2),
}

# ----------------------------------------------------------------------------
# C. MC sweep: the gentleman's discount and the hold-vs-sell call
#    Analytic GvR-style posted price per draw: Poisson(L) arrivals, EV(p) =
#    p * (1 - exp(-L * (1 - F(p)))).
# ----------------------------------------------------------------------------
N = 10_000
med = RNG.uniform(10, 14, N)
sig = RNG.uniform(0.18, 0.35, N)
nbid = RNG.integers(2, 7, N)
lam_now = RNG.uniform(2.5, 6.0, N)      # serious arrivals this window
lam_later = RNG.uniform(1.0, 4.0, N)    # arrivals over the next 12 months
decay = RNG.uniform(0.05, 0.30, N)      # WTP decay if he holds

from scipy.stats import lognorm as _ln
grid = np.linspace(6, 22, 161)
SALVAGE = 6.0
# the reported promise-price spread: Recórd/Ponce ~$4m (no formal clause),
# Esquivel $7m, Alarcón/Ponce $8-9m
PROMISE_GRID = np.arange(3.0, 10.01, 0.5)
res = {"gap3": [], "opt_clause": [], "hold_delta": [], "prob_below_all": []}
disc = np.empty((N, len(PROMISE_GRID)))
for k in range(N):
    d_now = _ln(s=sig[k], scale=med[k])
    ps_now = 1 - np.exp(-lam_now[k] * d_now.sf(grid))
    ev_now = grid * ps_now
    opt_p, opt_ev = grid[int(np.argmax(ev_now))], float(ev_now.max())
    # corrected discount (audit fix D): clause revenue is probabilistic too
    cl_ps = 1 - np.exp(-lam_now[k] * d_now.sf(PROMISE_GRID))
    disc[k] = opt_ev - PROMISE_GRID * cl_ps
    # keep-value-adjusted hold-vs-now (audit fix C)
    ev_now_s = ev_now + SALVAGE * (1 - ps_now)
    d_lat = _ln(s=sig[k], scale=med[k] * (1 - decay[k]))
    ps_lat = 1 - np.exp(-lam_later[k] * d_lat.sf(grid))
    ev_lat_s = grid * ps_lat + SALVAGE * (1 - ps_lat)
    res["hold_delta"].append(float(ev_now_s.max()) - float(ev_lat_s.max()))
    v = np.random.default_rng(9000 + k).lognormal(np.log(med[k]), sig[k], size=(1500, int(nbid[k])))
    second = float(np.sort(v, axis=1)[:, -2].mean())
    res["gap3"].append(second - CLAUSE)
    res["opt_clause"].append(opt_p)
    res["prob_below_all"].append(float((v.min(axis=1) > CLAUSE).mean()))

def pct(a):
    a = np.array(a)
    return {"p10": round(np.percentile(a, 10), 2), "median": round(np.median(a), 2),
            "p90": round(np.percentile(a, 90), 2)}

i75 = int(np.where(np.isclose(PROMISE_GRID, 7.5))[0][0])
i4 = int(np.where(np.isclose(PROMISE_GRID, 4.0))[0][0])
i9 = int(np.where(np.isclose(PROMISE_GRID, 9.0))[0][0])
OUT["monte_carlo"] = {
    "n": N,
    "auction_minus_clause_75": pct(res["gap3"]),
    "optimal_posted_price": pct(res["opt_clause"]),
    "discount_at_4": pct(disc[:, i4]),
    "discount_at_75": pct(disc[:, i75]),
    "discount_at_9": pct(disc[:, i9]),
    "pct_discount_positive_at_9": round(100 * float((disc[:, i9] > 0).mean()), 1),
    "sell_now_minus_hold_keepvalue_adj": pct(res["hold_delta"]),
    "pct_sell_now_wins": round(100 * float((np.array(res["hold_delta"]) > 0).mean()), 1),
    "mean_prob_clause75_below_every_bidder": round(float(np.mean(res["prob_below_all"])), 3),
    "promise_curve": [
        {"c": float(c), "p10": round(np.percentile(disc[:, j], 10), 2),
         "median": round(np.median(disc[:, j]), 2),
         "p90": round(np.percentile(disc[:, j], 90), 2)}
        for j, c in enumerate(PROMISE_GRID)
    ],
}

print(json.dumps(OUT, indent=1, default=str))
