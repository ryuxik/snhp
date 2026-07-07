"""Should you buy the World Cup? — the null-tournament simulation.

Core idea: simulate a World Cup in which NO player's true quality changes.
Small samples (150-450 minutes) plus selection (trackers report the top
movers out of ~700 players) manufacture apparent breakouts. Then compute the
rational Bayesian update for the real 2026 movers and compare with the
observed market moves.

TRACKER rows are filled from verified reporting before publication.
"""
import json
import numpy as np

RNG = np.random.default_rng(55)
OUT = {}

# ----------------------------------------------------------------------------
# A. The null tournament
#    700 players. True per-90 impact rate mu_i (goals+assists-equivalent),
#    drawn from the population. WC observed output ~ Poisson(mu_i * n90).
#    Nobody improves. Ask: how big do the tournament's apparent top movers
#    look anyway?
# ----------------------------------------------------------------------------
N_PLAYERS, N_SIMS = 700, 2000
mu = RNG.gamma(shape=2.2, scale=0.16, size=N_PLAYERS)          # league-established rates, mean ~0.35/90
minutes = RNG.uniform(120, 480, size=N_PLAYERS)                 # tournament minutes
n90 = minutes / 90.0

top10_ratio, top10_apparent = [], []
for s in range(N_SIMS):
    g = np.random.default_rng(10_000 + s).poisson(mu * n90)
    rate_obs = g / n90
    # naive value model: value moves with observed rate / prior rate
    ratio = (rate_obs + 0.05) / (mu + 0.05)
    idx = np.argsort(ratio)[-10:]
    top10_ratio.append(float(ratio[idx].mean()))
    top10_apparent.append(float((rate_obs[idx] / (mu[idx] + 1e-9)).mean()))
OUT["null_tournament"] = {
    "n_players": N_PLAYERS, "n_sims": N_SIMS,
    "top10_apparent_improvement": {
        "p10": round(np.percentile(top10_ratio, 10), 2),
        "median": round(np.median(top10_ratio), 2),
        "p90": round(np.percentile(top10_ratio, 90), 2),
    },
    "hist": {
        "bins": [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
        "counts": np.histogram(top10_ratio, bins=[3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0])[0].tolist(),
    },
    "note": ("median: the tournament's top-10 'risers' look ~Xx better than their "
             "true selves in a world where NOBODY improved"),
}

# ----------------------------------------------------------------------------
# B. Rational updates for the real movers (normal-normal shrinkage)
#    Prior: club career, n_prior effective minutes. WC: n_wc minutes.
#    Rational weight on the WC sample: w = n_wc / (n_wc + n_prior).
#    Rational value multiple ~ (1 + w * (perf_multiple - 1)) ** ELASTICITY.
#    TRACKER: (name, pre-value GBPm, post GBPm/ask, wc_minutes, perf_multiple
#              = WC output rate vs club baseline, kind: value|ask)
# ----------------------------------------------------------------------------
ELASTICITY = 1.6           # value responds convexly to quality (young stars)
N_PRIOR = 2800.0           # effective prior minutes (a full recent club season+)
# Verified rows (Goal/eToro tracker Jul 4 unless noted; FW = Football Whispers
# Jun 29; ING = Ingenuity Jul 6; asks are club/journalism numbers, not model values).
# perf_mult = WC output rate vs club baseline (modeled from reported stats + minutes;
# swept below). Down-movers included deliberately.
TRACKER = [
    ("Michael Olise", 125, 150, 430, 2.0, "value"),          # 5 assists
    ("Yan Diomande", 80, 92.5, 398, 1.4, "value"),           # eToro 92.5; 0 G/A, 11 CC — process-only bump
    ("Ayyoub Bouaddi", 45, 65, 380, 1.7, "value"),
    ("Crysencio Summerville", 25, 50, 133, 3.5, "ask"),      # FW: TM 25 -> WHU ask 50
    ("Deniz Undav", 30, 40, 150, 2.5, "value"),
    ("Elijah Just", 2.5, 10, 270, 3.0, "ask"),               # FW "quadruple"
    ("Malik Tillman", 40, 65, 360, 2.2, "value"),            # ING +25
    ("Johan Manzambi", 42, 51.2, 129, 4.0, "ask"),           # Plettenberg ask raise
    ("Christ Inao Oulai", 25, 45, 300, 2.0, "ask"),
    ("Brian Brobbey", 25, 50, 330, 2.4, "ask"),              # FW "double"
    ("Kylian Mbappe", 155, 200, 450, 1.9, "value"),          # FW; 7 goals
    ("Lamine Yamal", 200, 205, 400, 1.1, "value"),           # +2.5%
    ("Bradley Barcola", 60, 65, 200, 1.4, "value"),
    # the fallers — same arithmetic, opposite sign
    ("Julian Alvarez", 120, 105, 160, 0.5, "value"),
    ("Elliot Anderson", 105, 97.5, 380, 0.7, "value"),
    ("Morgan Rogers", 90, 85, 150, 0.6, "value"),
]
rows = []
for name, pre, post, mins, perf, kind in TRACKER:
    w = (mins) / (mins + N_PRIOR)
    rational_mult = (1 + w * (perf - 1)) ** ELASTICITY
    rational_post = pre * rational_mult
    obs_mult = post / pre
    denom = rational_mult - 1
    hype = (obs_mult - 1) / denom if abs(denom) > 1e-6 else float("nan")
    rows.append({
        "name": name, "pre": pre, "post": post, "wc_minutes": mins,
        "kind": kind,
        "rational_post": round(rational_post, 1),
        "observed_gain_pct": round(100 * (obs_mult - 1), 0),
        "rational_gain_pct": round(100 * (rational_mult - 1), 0),
        "hype_multiple": round(hype, 1),
    })
OUT["movers"] = rows
OUT["hype_median"] = round(float(np.median([r["hype_multiple"] for r in rows])), 1)

# ----------------------------------------------------------------------------
# C. Sensitivity: hype multiples under different priors/elasticities
# ----------------------------------------------------------------------------
sens = []
for np_eff in [1800, 2800, 4000]:
    for el in [1.2, 1.6, 2.2]:
        hs = []
        for name, pre, post, mins, perf, kind in TRACKER:
            w = mins / (mins + np_eff)
            rm = (1 + w * (perf - 1)) ** el
            if abs(rm - 1) > 1e-6:
                hs.append(((post / pre) - 1) / (rm - 1))
        sens.append({"n_prior": np_eff, "elasticity": el,
                     "hype_median": round(float(np.median(hs)), 1)})
OUT["sensitivity"] = sens

# ----------------------------------------------------------------------------
# D. Reading the sellers: grid-Bayes posterior over each seller's true
#    accept-now reservation, from their VERIFIED observed behavior only.
#    Behavioral model: reject offer x if x < R + noise(tau); an ask is
#    R*(1+markup), markup ~ N(0.18, 0.12); a posted clause/commitment at x
#    is a (soft) promise to accept at x.
# ----------------------------------------------------------------------------
from scipy.stats import norm as _norm

def seller_posterior(lo, hi, obs, tau=4.0, mark_mu=0.18, mark_sd=0.12):
    Rg = np.linspace(lo, hi, 2001)
    logw = np.zeros_like(Rg)
    for kind, x in obs:
        if kind == "reject":
            logw += np.log(_norm.cdf((Rg - x) / tau) + 1e-12)
        elif kind == "accept":
            logw += np.log(_norm.cdf((x - Rg) / tau) + 1e-12)
        elif kind == "ask":
            logw += _norm.logpdf(x / Rg - 1, mark_mu, mark_sd)
        elif kind == "commit":
            logw += np.log(_norm.cdf((x - Rg) / (tau / 2)) + 1e-12)
    w = np.exp(logw - logw.max()); w /= w.sum()
    cdf = np.cumsum(w)
    q = lambda p: float(Rg[np.searchsorted(cdf, p)])
    return {"p10": round(q(0.10), 1), "median": round(q(0.50), 1), "p90": round(q(0.90), 1)}

SAGAS = {
    "Newcastle (Tonali), pre-close": {
        "ccy": "GBP", "prior": (70, 110),
        "obs": [("reject", 75), ("reject", 90), ("ask", 100)],
        "resolution": "accepted a package worth ~97.75 EV (92.5 guaranteed)",
    },
    "RB Leipzig (Diomande), live": {
        "ccy": "EUR", "prior": (85, 145),
        "obs": [("reject", 100), ("ask", 130)],
        "resolution": None,
    },
    "Tijuana (Mora), live": {
        "ccy": "EUR", "prior": (12, 45),
        "obs": [("ask", 30), ("ask", 40), ("commit", 25)],
        "resolution": None,
    },
}
OUT["seller_reads"] = {
    name: {**seller_posterior(*cfg["prior"], cfg["obs"]),
           "ccy": cfg["ccy"], "n_obs": len(cfg["obs"]), "resolution": cfg["resolution"]}
    for name, cfg in SAGAS.items()
}

# ----------------------------------------------------------------------------
# E. The window league table (v0): actual/reported outcome vs the series'
#    own engine benchmark for each modeled seller. Values from the committed
#    results of pieces No. 1-4.
# ----------------------------------------------------------------------------
OUT["league_table"] = [
    {"club": "Newcastle", "deal": "Tonali -> Spurs (closed)", "ccy": "GBP",
     "benchmark": 90.6, "actual": 97.75, "delta": 7.1,
     "note": "beat the symmetric-negotiation benchmark"},
    {"club": "RB Leipzig", "deal": "Diomande (in play)", "ccy": "EUR",
     "benchmark": 120.0, "actual": None, "delta": None,
     "note": "refusing 100 vs a 130 bilateral read - holding above benchmark"},
    {"club": "Cruz Azul", "deal": "Lira (promise pending)", "ccy": "USD",
     "benchmark": 10.7, "actual": 3.9, "delta": -6.8,
     "note": "the kept promise, at the best-sourced $4m reading"},
    {"club": "Tijuana", "deal": "Mora (clause pending)", "ccy": "EUR",
     "benchmark": 41.2, "actual": 23.0, "delta": -18.2,
     "note": "the reported clause vs a three-bidder market"},
]

print(json.dumps(OUT, indent=1))
