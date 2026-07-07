"""Tonali -> Tottenham (July 2026) modeled on the SNHP engine.

Reported facts (Sky/ESPN, July 2026):
  - Total package L100m: L92.5m guaranteed + L7.5m add-ons tied to European qualification.
  - Spurs' opening bid L75m, rejected; deal closed July 2, 61 days before the Sept 1 deadline.
  - Newcastle: willing sellers (bought L55m in 2023, ~2yrs left on contract), said they
    "very likely" expect the full L100m. Man City interest in the background.
  - Spurs: nearly relegated last season, hired De Zerbi, spending big (Fernandes L85m).

Everything else (reservations, subjective probabilities) is MODELED and swept in the MC.
All money in Lm.
"""
import json
import numpy as np

from gametheory.negotiation.plain_terms import negotiate_turn
from snhp.nash_solver import filter_pareto_frontier, find_nash_bargaining_solution
from snhp.core_math.rubinstein import rubinstein_equilibrium, compute_discount_factor

RNG = np.random.default_rng(42)
OUT = {}

# ----------------------------------------------------------------------------
# Issue space: guaranteed fee, Europe-conditional add-on, schedule, sell-on
# ----------------------------------------------------------------------------
G_OPTS = [80.0, 85.0, 87.5, 90.0, 92.5, 95.0, 100.0]   # guaranteed fee
A_OPTS = [0.0, 5.0, 7.5, 10.0, 15.0]                   # add-on, pays iff Europe
S_OPTS = ["upfront", "2 instalments", "4 instalments"] # payment schedule
R_OPTS = [0.0, 0.10, 0.15]                             # sell-on %

ACTUAL = {"g": 92.5, "a": 7.5, "s": "4 instalments", "r": 0.0}

BASE = dict(
    p_N=0.70,        # Newcastle's subjective P(add-on triggers)  ("very likely")
    c_S=0.40,        # Spurs' effective cost per L1 of conditional add-on
                     #   (subjective P(Europe) x (1 - self-financing offset))
    R_N=82.0,        # Newcastle reservation, total expected value  (City as outside option)
    W_S=106.0,       # Spurs ceiling, total expected cost
    sched_N={"upfront": 2.5, "2 instalments": 1.2, "4 instalments": 0.0},  # NUFC PV premium for early cash
    sched_S={"upfront": 2.0, "2 instalments": 1.0, "4 instalments": 0.0},  # THFC financing cost of early cash
    sellon_base=10.0,   # E[future resale fee] x 1.0 => sell-on EV per unit r, to seller
    sellon_buyer_mult=1.3,  # buyer's cost multiplier (flexibility/option penalty)
)


def package_values(params):
    """Return (packages, V_N seller EV, C_S buyer expected cost) over the full space."""
    pkgs, vn, cs = [], [], []
    for g in G_OPTS:
        for a in A_OPTS:
            for s in S_OPTS:
                for r in R_OPTS:
                    pkgs.append({"g": g, "a": a, "s": s, "r": r})
                    vn.append(g + params["p_N"] * a + params["sched_N"][s]
                              + r * params["sellon_base"])
                    cs.append(g + params["c_S"] * a + params["sched_S"][s]
                              + r * params["sellon_base"] * params["sellon_buyer_mult"])
    return pkgs, np.array(vn), np.array(cs)


def analyse(params):
    pkgs, vn, cs = package_values(params)
    s_n = vn - params["R_N"]          # Newcastle surplus
    s_s = params["W_S"] - cs          # Spurs surplus
    feasible = (s_n >= 0) & (s_s >= 0)
    idx = np.where(feasible)[0]
    contracts = np.arange(len(pkgs)).reshape(-1, 1)
    pareto = filter_pareto_frontier(contracts[idx], s_n[idx], s_s[idx])
    nash = find_nash_bargaining_solution(pareto, s_n[idx], s_s[idx], 0.0, 0.0)
    nash_i = int(idx[int(nash)]) if nash is not None else None
    return pkgs, s_n, s_s, idx, pareto, nash, nash_i


# ----------------------------------------------------------------------------
# Part 1: base-case frontier, Nash point, and where the actual deal sits
# ----------------------------------------------------------------------------
pkgs, s_n, s_s, idx, pareto, nash, nash_i = analyse(BASE)
joint = s_n + s_s
act_i = next(i for i, p in enumerate(pkgs) if p == ACTUAL)
max_joint = joint[idx].max()
best_i = idx[np.argmax(joint[idx])]

# actual deal with each schedule (schedule unreported)
sched_variants = {}
for s in S_OPTS:
    i = next(i for i, p in enumerate(pkgs) if p == {**ACTUAL, "s": s})
    sched_variants[s] = {"joint": round(joint[i], 2), "s_n": round(s_n[i], 2), "s_s": round(s_s[i], 2)}

OUT["base_case"] = {
    "n_packages": len(pkgs),
    "n_feasible": int(len(idx)),
    "n_pareto": int(len(pareto)),
    "actual": {"pkg": ACTUAL, "s_n": round(s_n[act_i], 2), "s_s": round(s_s[act_i], 2),
               "joint": round(joint[act_i], 2)},
    "actual_by_schedule": sched_variants,
    "max_joint": round(max_joint, 2),
    "joint_left_on_table": round(max_joint - joint[act_i], 2),
    "best_joint_pkg": pkgs[best_i],
    "nash_pkg": pkgs[nash_i] if nash_i is not None else None,
    "nash_s_n": round(s_n[nash_i], 2) if nash_i is not None else None,
    "nash_s_s": round(s_s[nash_i], 2) if nash_i is not None else None,
    "newcastle_share_actual": round(s_n[act_i] / joint[act_i], 3),
}

# Pareto frontier coordinates for the chart
OUT["frontier_points"] = sorted(
    [{"s_n": round(s_n[idx[i]], 2), "s_s": round(s_s[idx[i]], 2), "pkg": pkgs[idx[i]]}
     for i in range(len(idx)) if idx[i] in set(idx[j] for j in pareto)],
    key=lambda d: d["s_n"])
# cloud (downsample: unique (s_n,s_s) rounded)
seen, cloud = set(), []
for i in idx:
    key = (round(s_n[i], 1), round(s_s[i], 1))
    if key not in seen:
        seen.add(key)
        cloud.append({"s_n": key[0], "s_s": key[1]})
OUT["cloud_points"] = cloud

# ----------------------------------------------------------------------------
# Part 2: single-issue replay — what does the engine tell each side to do?
# ----------------------------------------------------------------------------
# Newcastle's seat after Spurs' rejected L75m opener (guaranteed-fee dimension only)
ncl_view = negotiate_turn(side="sell", walk_away=82.0, target=105.0,
                          counterparty_offers=[75.0], rounds_left=8, item="the player")
OUT["engine_counter_after_75"] = {k: ncl_view[k] for k in
                                  ("action", "recommended_price", "expected_settlement", "confidence")
                                  if k in ncl_view}

# Engine vs engine: both seats run SNHP, alternate until accept
sell_offers, buy_offers, transcript = [], [75.0], [("THFC", 75.0)]
settle = None
for rd in range(8, 0, -1):
    s = negotiate_turn(side="sell", walk_away=82.0, target=105.0,
                       counterparty_offers=buy_offers, my_previous_offers=sell_offers,
                       rounds_left=rd)
    if s["action"] == "accept":
        settle = ("NUFC accepts", buy_offers[-1]); break
    sell_offers.append(s["recommended_price"]); transcript.append(("NUFC", s["recommended_price"]))
    b = negotiate_turn(side="buy", walk_away=106.0, target=78.0,
                       counterparty_offers=sell_offers, my_previous_offers=buy_offers,
                       rounds_left=rd)
    if b["action"] == "accept":
        settle = ("THFC accepts", sell_offers[-1]); break
    buy_offers.append(b["recommended_price"]); transcript.append(("THFC", b["recommended_price"]))
OUT["engine_vs_engine"] = {"transcript": [(w, round(p, 2)) for w, p in transcript],
                           "settlement": settle}

# ----------------------------------------------------------------------------
# Part 3: Monte Carlo over the modeled beliefs (the rigor pass)
# ----------------------------------------------------------------------------
N = 10_000
draws = dict(
    p_N=RNG.uniform(0.50, 0.85, N),
    c_S=RNG.uniform(0.30, 0.65, N),
    R_N=RNG.uniform(76.0, 88.0, N),
    W_S=RNG.uniform(100.0, 112.0, N),
    up_N=RNG.uniform(1.5, 3.5, N),   # NUFC upfront premium
    up_S=RNG.uniform(1.0, 3.0, N),   # THFC upfront cost
)
res = {"addon_on_at_best": 0, "addon_max_at_best": 0, "actual_gap": [], "nash_g": [],
       "ncl_share_actual": [], "infeasible": 0, "actual_within_1m": 0}
for k in range(N):
    p = dict(BASE)
    p.update(p_N=draws["p_N"][k], c_S=draws["c_S"][k], R_N=draws["R_N"][k], W_S=draws["W_S"][k],
             sched_N={"upfront": draws["up_N"][k], "2 instalments": draws["up_N"][k] / 2, "4 instalments": 0.0},
             sched_S={"upfront": draws["up_S"][k], "2 instalments": draws["up_S"][k] / 2, "4 instalments": 0.0})
    pk, vn, cs = package_values(p)
    sn, ss = vn - p["R_N"], p["W_S"] - cs
    feas = (sn >= 0) & (ss >= 0)
    if not feas.any():
        res["infeasible"] += 1; continue
    j = sn + ss
    jf = np.where(feas, j, -np.inf)
    bi = int(np.argmax(jf))
    if pk[bi]["a"] > 0: res["addon_on_at_best"] += 1
    if pk[bi]["a"] == 15.0: res["addon_max_at_best"] += 1
    ai = act_i  # same ordering every draw
    gap = jf[bi] - j[ai]
    res["actual_gap"].append(gap)
    if gap <= 1.0: res["actual_within_1m"] += 1
    if sn[ai] > 0 and ss[ai] > 0:
        res["ncl_share_actual"].append(sn[ai] / j[ai])
    # Nash guaranteed fee: among feasible, maximize sn*ss
    prod = np.where(feas, np.maximum(sn, 0) * np.maximum(ss, 0), -1)
    res["nash_g"].append(pk[int(np.argmax(prod))]["g"])

gaps = np.array(res["actual_gap"]); nash_g = np.array(res["nash_g"]); shares = np.array(res["ncl_share_actual"])
valid = N - res["infeasible"]
OUT["monte_carlo"] = {
    "n": N, "n_valid": valid, "pct_infeasible": round(100 * res["infeasible"] / N, 2),
    "pct_addon_efficient": round(100 * res["addon_on_at_best"] / valid, 1),
    "pct_addon_maxed": round(100 * res["addon_max_at_best"] / valid, 1),
    "actual_gap_joint_Lm": {"p10": round(np.percentile(gaps, 10), 2),
                             "median": round(np.median(gaps), 2),
                             "p90": round(np.percentile(gaps, 90), 2)},
    "pct_actual_within_1m_of_frontier": round(100 * res["actual_within_1m"] / valid, 1),
    "nash_guaranteed_fee": {"p10": round(np.percentile(nash_g, 10), 1),
                            "median": round(np.median(nash_g), 1),
                            "p90": round(np.percentile(nash_g, 90), 1)},
    "newcastle_share_at_actual": {"p10": round(np.percentile(shares, 10), 3),
                                  "median": round(np.median(shares), 3),
                                  "p90": round(np.percentile(shares, 90), 3)},
    "gap_hist": np.histogram(gaps, bins=[-0.01, 0.5, 1, 2, 3, 4, 5, 7, 10, 20])[0].tolist(),
}

# ----------------------------------------------------------------------------
# Part 4: deadline dynamics (Rubinstein with the engine's own discount model)
# ----------------------------------------------------------------------------
# Deltas from the engine's urgency model: NUFC low urgency + City in pipeline;
# THFC high urgency (De Zerbi rebuild), 61 days to deadline at close.
d_ncl = compute_discount_factor(urgency_score=0.25, days_until_deadline=61, pipeline_count=2)
d_thfc = compute_discount_factor(urgency_score=0.75, days_until_deadline=61, pipeline_count=0)
ZOPA = BASE["W_S"] - BASE["R_N"]  # 24
rub = rubinstein_equilibrium(delta_freelancer=d_ncl, delta_client=d_thfc, surplus=ZOPA)
OUT["rubinstein"] = {"delta_ncl": round(d_ncl, 3), "delta_thfc": round(d_thfc, 3),
                     "zopa": ZOPA, "equilibrium": {k: (round(v, 3) if isinstance(v, float) else v)
                                                   for k, v in rub.items()}}
# sweep: seller share vs relative patience
sweep = []
for u_thfc in [0.2, 0.4, 0.6, 0.8]:
    d2 = compute_discount_factor(u_thfc, 61, 0)
    r2 = rubinstein_equilibrium(delta_freelancer=d_ncl, delta_client=d2, surplus=ZOPA)
    share = r2.get("freelancer_share", r2.get("share_freelancer"))
    sweep.append({"thfc_urgency": u_thfc, "delta_thfc": round(d2, 3),
                  "ncl_share": share})
OUT["rubinstein_sweep"] = sweep

print(json.dumps(OUT, indent=1, default=str))
