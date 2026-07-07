"""FIFA World Cup 2026 final ticket pricing — the market FIFA built, modeled.

PLACEHOLDER PARAMS pending bracket/price verification (marked TODO-VERIFY).
All prices USD, 'get-in' = cheapest available on secondary market.

Observed anchors (from the July 7 research sweep, to be re-verified):
  - Final get-in today (Jul 7): ~$9,346; StubHub range ~$7.3k-27k.
  - QF get-ins fell 50-68% from June 24 peaks after all three co-hosts
    were eliminated; listings ballooned 28,285 -> 49,415.
  - FIFA resale marketplace: 15% buyer fee + 15% seller fee.
  - The final: July 19, MetLife.
"""
import json
import numpy as np

RNG = np.random.default_rng(77)
OUT = {}

# ----------------------------------------------------------------------------
# PARAMS (TODO-VERIFY: bracket, team demand multipliers, matchup probabilities)
# ----------------------------------------------------------------------------
P0 = 9346.0                       # today's final get-in (Forbes, July 7 afternoon)
DAYS_TO_FINAL = 12
# Team demand multipliers for a MetLife final (modeled, swept below; 1.0 = neutral).
# Anchors: NY-area diaspora (Colombian and Argentine communities are large),
# England traveling/expat support, France/Spain global draw.
TEAM_M = {
    "England": 1.9, "Argentina": 1.9, "France": 1.4, "Spain": 1.3,
    "Colombia": 1.3, "Morocco": 1.15, "Norway": 0.85, "Belgium": 0.85,
    "Switzerland": 0.8,
}
# VERIFIED bracket (July 7): SF1 = FRA/MAR winner vs ESP/BEL winner (Jul 14, Dallas);
# SF2 = NOR/ENG winner vs ARG/(SUI-or-COL) winner (Jul 15, Atlanta). Final Jul 19, MetLife.
SF1 = ["France", "Spain", "Morocco", "Belgium"]
SF2 = ["Argentina", "England", "Norway", "Colombia", "Switzerland"]
# FanDuel reach-the-final odds, July 7 (vig-inclusive implied), normalized per side.
P_REACH = {"France": 0.53, "Spain": 0.38, "Morocco": 0.09, "Belgium": 0.08,
           "Argentina": 0.45, "England": 0.35, "Norway": 0.15,
           "Colombia": 0.10, "Switzerland": 0.04}

def _norm(side):
    tot = sum(P_REACH[t] for t in side)
    return {t: P_REACH[t] / tot for t in side}

PA, PB = _norm(SF1), _norm(SF2)

# Demand -> price elasticity for the FINAL. Calibration anchor: while QF get-ins
# fell 57-68% on co-host elimination, the final fell only ~20% — final demand is
# event-anchored, far less matchup-sensitive than early rounds. Central 1.2,
# swept 0.8-1.6 in the MC.
ELAST = 1.2
def matchup_price(a, b, elast=ELAST, tm=TEAM_M):
    m = (tm[a] + tm[b]) / 2
    m_expected_today = sum(PA[x] * PB[y] * (tm[x] + tm[y]) / 2
                           for x in PA for y in PB)
    return P0 * (m / m_expected_today) ** elast

# ----------------------------------------------------------------------------
# A. Scenario table: expected final get-in per matchup
# ----------------------------------------------------------------------------
scen = []
for a in PA:
    for b in PB:
        scen.append({"final": f"{a} v {b}", "p": round(PA[a] * PB[b], 3),
                     "get_in": round(matchup_price(a, b), -1)})
scen.sort(key=lambda s: -s["get_in"])
OUT["scenarios"] = scen
e_after = sum(s["p"] * s["get_in"] for s in scen)
OUT["buy_now_or_wait"] = {
    "today": P0,
    "expected_after_semis": round(e_after, -1),
    "wait_saves_expected": round(P0 - e_after, -1),
    "p_price_above_today": round(sum(s["p"] for s in scen if s["get_in"] > P0), 3),
    "spike_scenario": scen[0],
    "crash_scenario": scen[-1],
}

# ----------------------------------------------------------------------------
# B. The 30% wedge: FIFA's resale fee vs market clearing
#    Seller reservations anchored at purchase cost (dynamic-pricing peaks);
#    buyer values ~ current demand. Trade clears iff v_b*(1-fb...) formal:
#    buyer pays 1.15P, seller nets 0.85P -> trade iff v_b >= (1.15/0.85)*r_s.
# ----------------------------------------------------------------------------
N = 200_000
r_s = RNG.lognormal(np.log(0.9 * P0), 0.45, N)   # seller reservations (many bought at peaks)
v_b = RNG.lognormal(np.log(0.8 * P0), 0.55, N)   # buyer values in the crashed market
fees = np.arange(0.0, 0.61, 0.02)
curve = []
for f in fees:
    wedge = 1.0 / (1.0 - f)                       # combined take f of transaction value
    ok = v_b >= r_s * wedge
    price = np.where(ok, (v_b + r_s * wedge) / 2, np.nan)   # midpoint split
    vol = float(np.mean(ok))
    rev = float(np.nanmean(price) * vol * f) if vol > 0 else 0.0
    curve.append({"fee": round(f, 2), "clears_pct": round(100 * vol, 1),
                  "fifa_rev_index": round(rev, 1)})
best = max(curve, key=lambda c: c["fifa_rev_index"])
at30 = min(curve, key=lambda c: abs(c["fee"] - 0.30))
OUT["wedge"] = {
    "curve": curve[::3],
    "fifa_fee": 0.30, "at_30": at30, "revenue_optimal_fee": best,
    "trades_killed_at_30_pct": round(curve[0]["clears_pct"] - at30["clears_pct"], 1),
}

# Partition for the widget: does the final include a marquee draw
# (Argentina or England from SF2, i.e. the Atlanta side)?
big = {t: (t in ("Argentina", "England")) for t in PB}
p_big = sum(PB[t] for t in PB if big[t])
e_big = sum(PA[a] * PB[b] * matchup_price(a, b) for a in PA for b in PB if big[b]) / p_big
e_small = sum(PA[a] * PB[b] * matchup_price(a, b) for a in PA for b in PB if not big[b]) / (1 - p_big)
OUT["widget_partition"] = {
    "p_big_default": round(p_big, 3),
    "e_getin_if_big": round(e_big, -1),
    "e_getin_if_small": round(e_small, -1),
}

# ----------------------------------------------------------------------------
# B2. MC sweep: bands per headline scenario over multiplier noise and elasticity
# ----------------------------------------------------------------------------
NMC = 8000
kk = np.random.default_rng(9)
headline = [("France", "Argentina"), ("Spain", "England"),
            ("France", "England"), ("Belgium", "Norway")]
bands = {}
for a, b in headline:
    vals = []
    for _ in range(NMC):
        tm = {t: m * kk.lognormal(0, 0.12) for t, m in TEAM_M.items()}
        e = kk.uniform(0.8, 1.6)
        vals.append(matchup_price(a, b, elast=e, tm=tm))
    vals = np.array(vals)
    bands[f"{a} v {b}"] = {"p10": round(float(np.percentile(vals, 10)), -1),
                           "median": round(float(np.median(vals)), -1),
                           "p90": round(float(np.percentile(vals, 90)), -1)}
OUT["scenario_bands"] = bands

# ----------------------------------------------------------------------------
# C. The engine's schedule: price the final's remaining seats like a
#    profit-maximizing seller (Gallego-van Ryzin, same module as piece No. 3),
#    normalized to today's get-in. Buyer WTP ~ lognormal around the
#    scenario-expected value; arrivals over the 12 remaining days.
# ----------------------------------------------------------------------------
from gametheory.mechanism.posted_price import posted_price_optimal

WTP_MED = float(sum(s["p"] * s["get_in"] for s in scen))   # scenario-expected get-in
PRIOR = {"family": "lognorm", "params": {"mu": float(np.log(WTP_MED)), "sigma": 0.5}}
gvr = posted_price_optimal(
    buyer_arrival_prior=PRIOR, arrival_rate_per_second=6 / DAYS_TO_FINAL,
    inventory=1, horizon_seconds=DAYS_TO_FINAL, seed=42,
)
OUT["engine_schedule"] = {
    "static_price": gvr["static_price"],
    "static_ev": gvr["static_expected_revenue"],
    "sellthrough": gvr["sellthrough_rate"],
    "note": ("the optimal ask for a marginal final seat starts above today's market and "
             "marks down into July 19 — the same markdown law FIFA's own last-3-days "
             "price cuts obeyed in the group stage"),
}

print(json.dumps(OUT, indent=1))
