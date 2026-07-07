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

print(json.dumps(OUT, indent=1))
