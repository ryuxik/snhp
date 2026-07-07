"""Gilberto Mora (Tijuana), July 2026 — rumor-stage deal modeled on the SNHP engine.

Reported facts:
  - 17 (born Oct 14, 2008 — turns 18 Oct 14, 2026; FIFA Art. 19 bars an
    international move before then). Youngest player at WC 2026; Mexico out in
    the R16 (3-2 vs England, July 5).
  - New 3-year Tijuana extension with a "highly tailored and clearly structured
    release mechanism" (agent: Rafaela Pimenta).
  - July 2026 reports value him >EUR 40m; Tijuana's floor EUR 15m, expecting
    "almost double" (~EUR 30m).
  - Interest: Real Madrid, Barcelona, Man City, Chelsea, Man United, AC Milan.

Everything else is modeled and swept. All money in EUR m.
"""
import json
import numpy as np

from gametheory.auctions.seller import optimal_reserve
from gametheory._internal import sample_prior, myerson_reserve
from snhp.nash_solver import filter_pareto_frontier, find_nash_bargaining_solution

RNG = np.random.default_rng(7)
OUT = {}

# ----------------------------------------------------------------------------
# A. The mechanism question: 6-club auction vs the release clause (posted price)
# ----------------------------------------------------------------------------
MEDIAN_V = 40.0          # reported market valuation
SIGMA = 0.35             # wonderkid dispersion: P10 ~= 26, P90 ~= 63
V0 = 15.0                # Tijuana's stated floor = value of keeping him (+ later sale)
PRIOR = {"family": "lognorm", "params": {"mu": float(np.log(MEDIAN_V)), "sigma": SIGMA}}
NSIM = 200_000

def order_stats(prior, n, nsim, rng):
    v = np.sort(sample_prior(prior, nsim * n, rng).reshape(nsim, n), axis=1)
    return v[:, -1], (v[:, -2] if n > 1 else np.full(nsim, np.nan))

# expected price under an English auction (2nd-highest value), N = 1..6
auction_curve = []
for n in range(1, 7):
    hi, second = order_stats(PRIOR, n, NSIM, np.random.default_rng(100 + n))
    if n == 1:
        # bilateral: Nash split of [V0, v] — midpoint of the ZOPA when v > V0
        price = float(np.mean(np.where(hi > V0, (hi + V0) / 2, np.nan)[~np.isnan(np.where(hi > V0, (hi + V0) / 2, np.nan))]))
        auction_curve.append({"n": n, "exp_price": round(price, 1), "mode": "bilateral Nash"})
    else:
        auction_curve.append({"n": n, "exp_price": round(float(second.mean()), 1), "mode": "English, no reserve"})
OUT["auction_curve"] = auction_curve

# engine's Myerson reserve + revenue for the 6-bidder auction
res6 = optimal_reserve(bidder_value_prior=PRIOR, n_bidders=6, seller_valuation=V0)
OUT["myerson_6"] = res6

# posted price (the release clause): E[revenue] = R*P(sale) + V0*P(no sale)
hi6, _ = order_stats(PRIOR, 6, NSIM, np.random.default_rng(200))
Rs = np.arange(15, 75.5, 0.5)
posted = []
for R in Rs:
    p_sale = float((hi6 >= R).mean())
    ev = R * p_sale + V0 * (1 - p_sale)
    posted.append({"R": float(R), "p_sale": round(p_sale, 4), "ev": round(ev, 2)})
best = max(posted, key=lambda d: d["ev"])
at30 = min(posted, key=lambda d: abs(d["R"] - 30.0))
auction_ev6 = auction_curve[-1]["exp_price"]
OUT["posted_price"] = {
    "optimal_clause": best,          # revenue-maximizing take-it price vs 6 bidders
    "clause_at_30": at30,            # Tijuana's reported expectation
    "auction_ev_6bidders": auction_ev6,
    "gap_30_vs_auction": round(auction_ev6 - at30["ev"], 1),
    "gap_optimal_vs_auction": round(auction_ev6 - best["ev"], 1),
    "curve": posted[::4],            # downsampled for the chart (every EUR 2m)
}

# ----------------------------------------------------------------------------
# B. The package: what the efficient deal looks like (bundle frontier)
# ----------------------------------------------------------------------------
G_OPTS = [20.0, 25.0, 30.0, 35.0, 40.0, 45.0]      # guaranteed fee
R_OPTS = [0.0, 0.10, 0.15, 0.20, 0.25]              # sell-on %
A_OPTS = [0.0, 5.0, 10.0, 15.0]                     # milestone add-ons
L_OPTS = ["none", "6mo", "12mo"]                    # loan-back at Tijuana

BASE = dict(
    sellon_T=22.0,   # Tijuana EV of a 100% resale share => 2.2 per 10% (their beliefs)
    sellon_B=16.0,   # buyer's expected cost of the same share (they discount resale worlds)
    p_T=0.60,        # Tijuana P(milestone add-ons pay)
    c_B=0.45,        # buyer effective cost per EUR 1 of add-on
    loan_T={"none": 0.0, "6mo": 2.0, "12mo": 3.5},   # Apertura + shirt sales + send-off
    loan_B={"none": 0.0, "6mo": 0.3, "12mo": 1.5},   # Art. 19 blocks pre-Oct registration anyway
    R_T=28.0,        # Tijuana reservation: the auction/keep-him outside option
    W_B=48.0,        # lead buyer's ceiling (total EV cost)
)

def package_values(p):
    pkgs, vt, cb = [], [], []
    for g in G_OPTS:
        for r in R_OPTS:
            for a in A_OPTS:
                for l in L_OPTS:
                    pkgs.append({"g": g, "r": r, "a": a, "l": l})
                    vt.append(g + r * p["sellon_T"] + p["p_T"] * a + p["loan_T"][l])
                    cb.append(g + r * p["sellon_B"] + p["c_B"] * a + p["loan_B"][l])
    return pkgs, np.array(vt), np.array(cb)

pkgs, vt, cb = package_values(BASE)
s_t, s_b = vt - BASE["R_T"], BASE["W_B"] - cb
feas = (s_t >= 0) & (s_b >= 0)
idx = np.where(feas)[0]
joint = s_t + s_b
pareto = filter_pareto_frontier(np.arange(len(pkgs)).reshape(-1, 1)[idx], s_t[idx], s_b[idx])
nash = find_nash_bargaining_solution(pareto, s_t[idx], s_b[idx], 0.0, 0.0)
nash_i = int(idx[int(nash)])
best_i = int(idx[np.argmax(joint[idx])])

# the "clause-only" counterfactual: fee EUR 30m, nothing else
plain_i = next(i for i, p in enumerate(pkgs) if p == {"g": 30.0, "r": 0.0, "a": 0.0, "l": "none"})

OUT["bundle"] = {
    "n_packages": len(pkgs), "n_feasible": int(len(idx)), "n_pareto": int(len(pareto)),
    "nash_pkg": pkgs[nash_i], "nash_s_t": round(s_t[nash_i], 2), "nash_s_b": round(s_b[nash_i], 2),
    "best_joint_pkg": pkgs[best_i], "max_joint": round(joint[best_i], 2),
    "plain_clause_30": {"s_t": round(s_t[plain_i], 2), "s_b": round(s_b[plain_i], 2),
                        "joint": round(joint[plain_i], 2)},
    "joint_gain_structured": round(joint[best_i] - joint[plain_i], 2),
}
pset = set(int(idx[j]) for j in pareto)
OUT["frontier_points"] = sorted(
    [{"s_t": round(s_t[i], 2), "s_b": round(s_b[i], 2),
      "pkg": f"€{pkgs[i]['g']:.0f}m + {pkgs[i]['r']*100:.0f}% sell-on + €{pkgs[i]['a']:.0f}m adds, loan {pkgs[i]['l']}"}
     for i in pset], key=lambda d: d["s_t"])
seen, cloud = set(), []
for i in idx:
    key = (round(s_t[i], 1), round(s_b[i], 1))
    if key not in seen:
        seen.add(key); cloud.append([key[0], key[1]])
OUT["cloud_points"] = cloud

# ----------------------------------------------------------------------------
# C. Monte Carlo over everything modeled
# ----------------------------------------------------------------------------
N = 10_000
med = RNG.uniform(30, 55, N)
sig = RNG.uniform(0.25, 0.50, N)
nbid = RNG.integers(2, 7, N)          # 2..6 credible bidders
sell_T = RNG.uniform(16, 30, N)       # Tijuana sell-on EV per 100%
sell_B = RNG.uniform(10, 26, N)       # buyer cost per 100%
res = {"auction_minus_30": [], "sellon_efficient": 0, "opt_clause": [], "auction_ev": []}
for k in range(N):
    prior = {"family": "lognorm", "params": {"mu": float(np.log(med[k])), "sigma": float(sig[k])}}
    n = int(nbid[k])
    v = np.sort(np.random.default_rng(3000 + k).lognormal(np.log(med[k]), sig[k], size=(2000, n)), axis=1)
    hi, second = v[:, -1], v[:, -2]
    a_ev = float(second.mean())
    p30 = float((hi >= 30).mean())
    ev30 = 30 * p30 + V0 * (1 - p30)
    res["auction_ev"].append(a_ev)
    res["auction_minus_30"].append(a_ev - ev30)
    if sell_T[k] > sell_B[k]:
        res["sellon_efficient"] += 1
    # optimal clause via engine's Myerson reserve (posted price ~ reserve logic)
    res["opt_clause"].append(myerson_reserve(prior, V0))
gap = np.array(res["auction_minus_30"]); oc = np.array(res["opt_clause"]); aev = np.array(res["auction_ev"])
OUT["monte_carlo"] = {
    "n": N,
    "auction_ev": {"p10": round(np.percentile(aev, 10), 1), "median": round(np.median(aev), 1),
                   "p90": round(np.percentile(aev, 90), 1)},
    "auction_minus_clause30": {"p10": round(np.percentile(gap, 10), 1),
                               "median": round(np.median(gap), 1),
                               "p90": round(np.percentile(gap, 90), 1),
                               "pct_positive": round(100 * float((gap > 0).mean()), 1)},
    "optimal_clause_myerson": {"p10": round(np.percentile(oc, 10), 1),
                               "median": round(np.median(oc), 1),
                               "p90": round(np.percentile(oc, 90), 1)},
    "pct_sellon_efficient": round(100 * res["sellon_efficient"] / N, 1),
    "gap_hist": np.histogram(gap, bins=[0, 5, 10, 15, 20, 25, 30, 40, 60])[0].tolist(),
    "gap_hist_bins": "0-5,5-10,10-15,15-20,20-25,25-30,30-40,40-60",
    "pct_gap_below_0": round(100 * float((gap <= 0).mean()), 1),
}

# ----------------------------------------------------------------------------
# D. Reality stress: correlated valuations (shared scouting information)
#    v_i = exp(mu + sigma*(sqrt(rho)*Z + sqrt(1-rho)*e_i)) — Gaussian copula.
# ----------------------------------------------------------------------------
corr = {}
for n in [2, 3, 6]:
    row = {}
    for rho in [0.0, 0.5, 0.7, 0.9]:
        r = np.random.default_rng(500 + n * 10 + int(rho * 10))
        Z = r.standard_normal((NSIM, 1))
        E = r.standard_normal((NSIM, n))
        v = np.exp(np.log(MEDIAN_V) + SIGMA * (np.sqrt(rho) * Z + np.sqrt(1 - rho) * E))
        row[f"rho_{rho}"] = round(float(np.sort(v, axis=1)[:, -2].mean()), 1)
    corr[f"n_{n}"] = row
OUT["correlated_valuations"] = corr

print(json.dumps(OUT, indent=1, default=str))
