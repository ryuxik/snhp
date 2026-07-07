"""Yan Diomande (RB Leipzig), July 2026 — one real bid, one fake bid, and a seller
who thinks waiting pays.

VERIFIED record (mainstream-anchored only):
  - Liverpool bid EUR 100m (90 + 10 add-ons), ~June 17-18: rejected (Ornstein/Sky DE).
  - The viral "EUR 116m second bid": fabricated (DaveOCKOP -> aggregators -> fake
    Bild attribution); Sky DE's Hinze: "there has not yet been a second offer."
  - Leipzig threshold: "in excess of EUR 130m" to change stance (ESPN/Ornstein).
  - June 28: player agrees 5-yr deal with PSG (RMC/ESPN/Athletic/Romano);
    Liverpool exits to alternatives (Sky, June 30).
  - Leipzig's menu (Romano June 29): >EUR 100m to leave NOW, or lower price with a
    one-season loan-back. Alternative plan: new contract + leave in 2027 via clause.
  - Mintzlaff (kicker, April): wouldn't sell "regardless of the price"; another
    season makes him "even more expensive."
  - Precedent: Leipzig held Gvardiol one year after his 2022 WC, sold at EUR 90m record.
  - Contract to 2030, no clause. TM value EUR 90m (May 27); CIES EUR 119m (June).
All money EUR m.
"""
import json
import numpy as np
from snhp.core_math.rubinstein import rubinstein_equilibrium

RNG = np.random.default_rng(33)
OUT = {}

PARAMS = dict(
    v_psg_lo=110.0, v_psg_hi=145.0,   # PSG ceiling: framework ~100 + confident, vs 130 threshold
    v_liv_lo=95.0, v_liv_hi=110.0,    # Liverpool: bid 100, "reluctant to go higher" (Sky)
    r_now_lo=110.0, r_now_hi=140.0,   # Leipzig now-price reserve: rejected 100; 130 threshold public
    keep_season=12.0,                  # one more season of a Rookie-of-the-Year winger (sporting EV)
    delta_leipzig=0.94, delta_psg=0.86,
)
N = 100_000

# ----------------------------------------------------------------------------
# A. Revealed-preference bounds (logic, not simulation)
# ----------------------------------------------------------------------------
OUT["revealed"] = {
    "v_liverpool_geq": 100.0,
    "leipzig_continuation_gt": 100.0,
    "only_mainstream_ask": 130.0,
    "fabricated_rungs": [116.0, 148.0, 160.0],
}

# ----------------------------------------------------------------------------
# B. What the player's choice did: auction (both live) vs bilateral (PSG only)
# ----------------------------------------------------------------------------
v_psg = RNG.uniform(PARAMS["v_psg_lo"], PARAMS["v_psg_hi"], N)
v_liv = RNG.uniform(PARAMS["v_liv_lo"], PARAMS["v_liv_hi"], N)
r_now = RNG.uniform(PARAMS["r_now_lo"], PARAMS["r_now_hi"], N)

hi = np.maximum(v_psg, v_liv); second = np.minimum(v_psg, v_liv)
auction = np.where(hi >= r_now, np.maximum(second, r_now), np.nan)      # English w/ reserve
d1, d2 = PARAMS["delta_leipzig"], PARAMS["delta_psg"]
share = d1 * (1 - d2) / (1 - d1 * d2)                                    # seller responder share
bilat = np.where(v_psg >= r_now, r_now + share * (v_psg - r_now), np.nan)

def stats(a):
    a = a[~np.isnan(a)]
    return {"p10": round(float(np.percentile(a, 10)), 1), "median": round(float(np.median(a)), 1),
            "p90": round(float(np.percentile(a, 90)), 1), "p_deal": round(len(a) / N, 3)}

OUT["mechanisms"] = {
    "auction_if_liverpool_stayed": stats(auction),
    "bilateral_psg_rubinstein": stats(bilat),
    "seller_share": round(share, 3),
    "choice_cost_to_psg_median": round(float(np.nanmedian(bilat) - np.nanmedian(auction)), 1),
}

# ----------------------------------------------------------------------------
# C. Mintzlaff's bet: hold a 19-year-old one more year
#    V_2027 = V_now_market * lognormal(growth, risk). Compare selling now at the
#    bilateral price vs holding (keep a season's sporting value, sell in 2027,
#    possibly via the Romano-reported new-contract-with-2027-clause).
# ----------------------------------------------------------------------------
V_MKT = 100.0            # between TM 90 and CIES 119
growth_grid = np.arange(-0.10, 0.451, 0.05)
risk = 0.35              # teenager variance: injury/form/regression
hold_rows = []
for g in growth_grid:
    v27 = V_MKT * np.exp(RNG.normal(np.log(1 + g) - risk**2 / 2, risk, N))
    # in 2027 they sell at a bilateral-ish share of a fresh market (assume same share)
    ev_hold = float(np.mean(v27)) * 0.95 + PARAMS["keep_season"]   # small friction, plus the season
    hold_rows.append({"growth": round(float(g), 2), "ev_hold": round(ev_hold, 1)})
sell_now_median = float(np.nanmedian(bilat))
be = next((r["growth"] for r in hold_rows if r["ev_hold"] >= sell_now_median), None)
OUT["mintzlaff_bet"] = {
    "sell_now_median": round(sell_now_median, 1),
    "hold_curve": hold_rows,
    "breakeven_growth": be,
    "gvardiol_precedent": "held post-WC 2022, sold 2023 at 90 (club record)",
}

# ----------------------------------------------------------------------------
# D. The menu: pricing immediacy. Seller indifference:
#    P_now  ~  P_later_discounted + keep_season  =>  immediacy premium.
# ----------------------------------------------------------------------------
p_later = bilat * 0.97                      # 2027 delivery at similar bargaining position
premium = PARAMS["keep_season"] + (bilat - p_later)
OUT["menu"] = {
    "immediacy_premium_median": round(float(np.nanmedian(premium)), 1),
    "note": "what 'Diomande now' should cost above 'Diomande in 2027 + loan-back'",
}

# ----------------------------------------------------------------------------
# E. Prediction bands
# ----------------------------------------------------------------------------
pred = bilat[~np.isnan(bilat)]
OUT["prediction"] = {
    "if_sold_this_window": stats(bilat),
    "p_geq_120": round(float((pred >= 120).mean()), 3),
    "p_geq_130": round(float((pred >= 130).mean()), 3),
    "p_lt_110": round(float((pred < 110).mean()), 3),
    "refs": {"leipzig_record_sale": 90.0, "bundesliga_record_fixed": 125.0, "leipzig_paid": 20.0},
}

print(json.dumps(OUT, indent=1))
