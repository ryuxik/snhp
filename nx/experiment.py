"""experiment.py — the pre-registered three-arm deal-formation kill (PREREG.md).

n = 240 seeded MPX-shaped procurement scenarios drawn from the UNION of the
ranges MERIDIAN already samples (see PREREG.md for the mapping). Three arms, all
scripted/deterministic, no LLM, no network:

  ARM-CHECKOUT      take-it-or-leave-it: seller posts the quoted config at list;
                    buyer accepts iff IR-positive at list.
  ARM-CHEAP-HAGGLE  price-only counters, 8 rounds, qty/ship_date frozen at the
                    quoted config (the MPX pattern with the round cap lifted).
  ARM-NX            full bundle proposals over the MPX mount (nx/bridge.py).

Outputs results/experiment.json (per-scenario records + aggregate) and prints the
three deal rates and the KILL-NX verdict, computed mechanically.

    python -m nx.experiment            # or: python nx/experiment.py
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from nx.bridge import (MPXScenario, feasible_configs, floor_price, list_price,  # noqa: E402
                       oracle_joint, quoted_config, realized_joint, reservation,
                       run_nx_session)

MASTER_SEED = 20260718
N_SCENARIOS = 240
CHEAP_HAGGLE_ROUNDS = 8
KILL_HAGGLE_FRAC = 0.80     # forward kill threshold (PREREG, frozen)
KILL_LIFT_FRAC = 1.10       # reverse kill threshold (PREREG, frozen)
RESULTS_DIR = Path(__file__).with_name("results")
_EPS = 1e-6


# ── scenario generator (union of meridian's own ranges — see PREREG) ────────
def make_scenario(i: int) -> MPXScenario:
    """Scenario i drawn from numpy.default_rng(MASTER_SEED + i), consumed in a
    fixed order so the set is byte-reproducible."""
    r = np.random.default_rng(MASTER_SEED + i)
    need_qty = int(r.integers(8, 41))                 # market line qty draw
    need_by = int(r.integers(1, 10))                  # union A1(1..4) / default(2..9)
    unit_value = float(r.uniform(65.0, 130.0))        # union A1 / default
    urgency = float(r.uniform(0.5, 9.0))              # union A2(0.5..3) / A1(3..9)
    cap = float(r.integers(2, 10))                    # union A1(2..5) / default(3..9)
    c0 = float(r.uniform(30.0, 55.0))                 # supplier draw
    c1 = float(r.uniform(0.02, 0.08))                 # supplier draw
    expedite = float(r.uniform(1.5, 4.0))             # supplier draw
    inventory = float(r.integers(200, 601))           # supplier draw
    markup = float(r.uniform(0.18, 0.32))             # supplier draw
    min_markup = float(r.uniform(0.03, 0.08))         # supplier draw
    return MPXScenario(
        session_ref=f"nx-scn-{i:04d}", item="item0", need_qty=need_qty,
        need_by=need_by, unit_value=unit_value, urgency=urgency, c0=c0, c1=c1,
        cap=cap, expedite=expedite, inventory=inventory, markup=markup,
        min_markup=min_markup)


CONSTRAINED_SEED = 900000


def make_scenario_constrained(i: int) -> MPXScenario:
    """EXPLORATORY (not pre-registered) — the CONSTRAINED regime: tight deadlines
    and high urgency, i.e. meridian's own A1 bundling-stress ranges (need_by 1..4,
    urgency 3..9, cap 2..5, unit_value 65..110; `meridian/audit.py` A1_REGIME).
    Supplier draws are unchanged from the neutral generator. This locates the
    boundary where bundling becomes load-bearing for deal EXISTENCE; it does not
    establish the registered headline (see PREREG.md + RESULTS.md)."""
    r = np.random.default_rng(CONSTRAINED_SEED + i)
    need_qty = int(r.integers(8, 41))
    need_by = int(r.integers(1, 5))                   # A1: tight deadlines
    unit_value = float(r.uniform(65.0, 110.0))        # A1
    urgency = float(r.uniform(3.0, 9.0))              # A1: high urgency
    c0 = float(r.uniform(30.0, 55.0))
    c1 = float(r.uniform(0.02, 0.08))
    cap = float(r.integers(2, 6))                     # A1: tight capacity
    expedite = float(r.uniform(1.5, 4.0))
    inventory = float(r.integers(200, 601))
    markup = float(r.uniform(0.18, 0.32))
    min_markup = float(r.uniform(0.03, 0.08))
    return MPXScenario(
        session_ref=f"nx-con-{i:04d}", item="item0", need_qty=need_qty,
        need_by=need_by, unit_value=unit_value, urgency=urgency, c0=c0, c1=c1,
        cap=cap, expedite=expedite, inventory=inventory, markup=markup,
        min_markup=min_markup)


REGIMES = {
    "neutral": {"gen": make_scenario, "seed": MASTER_SEED,
                "out": "experiment.json", "preregistered": True,
                "desc": "union of meridian A1/A2/A3 + market draws (PREREG.md)"},
    "constrained": {"gen": make_scenario_constrained, "seed": CONSTRAINED_SEED,
                    "out": "experiment-constrained.json", "preregistered": False,
                    "desc": "EXPLORATORY: meridian A1 tight-deadline/high-urgency"},
}


# ── ARM-CHEAP-HAGGLE: price-only, 8 rounds, config frozen at the quote ──────
def cheap_haggle(s: MPXScenario, rounds: int = CHEAP_HAGGLE_ROUNDS) -> dict:
    """Run a real price-only haggle at the QUOTED config: seller opens at list,
    buyer counters down, seller concedes, up to `rounds` buyer counters. qty and
    ship_date never move (the MPX message rule). A price-only bargainer strikes a
    deal iff the quoted config's ZOPA is nonempty (R >= F); the extra rounds only
    split an existing ZOPA — they cannot create one. We run the loop for real and
    the outcome is asserted against R(quote) >= F(quote)."""
    q, d = quoted_config(s)
    R = reservation(s, q, d)
    F = floor_price(s, q, d)
    L = list_price(s, q, d)
    ceiling = min(L, R)                       # buyer never pays above list or value
    if R < F - _EPS or ceiling < F - _EPS:    # no price ZOPA at the frozen config
        return {"deal": False, "price": None, "rounds": rounds,
                "joint_surplus": 0.0}
    # deterministic split inside [F, ceiling] over up to `rounds` counters
    seller_ask = L
    buyer_bid = F + 0.15 * (ceiling - F)
    target = F + 0.5 * (ceiling - F)
    used = 0
    for _ in range(rounds):
        if buyer_bid >= seller_ask - _EPS:
            price = min(seller_ask, ceiling)
            return {"deal": True, "price": round(price, 6), "rounds": used,
                    "joint_surplus": realized_joint(s, q, d)}
        used += 1
        seller_ask = max(target, seller_ask - 0.5 * (seller_ask - target))
        buyer_bid = min(seller_ask, buyer_bid + 0.5 * (seller_ask - buyer_bid))
    price = min(max(target, F), ceiling)      # converged inside the ZOPA
    return {"deal": True, "price": round(price, 6), "rounds": used,
            "joint_surplus": realized_joint(s, q, d)}


# ── ARM-CHECKOUT: take-it-or-leave-it at list ──────────────────────────────
def checkout(s: MPXScenario) -> dict:
    q, d = quoted_config(s)
    R, L = reservation(s, q, d), list_price(s, q, d)
    deal = R >= L - _EPS
    return {"deal": bool(deal), "price": round(L, 6) if deal else None,
            "joint_surplus": realized_joint(s, q, d) if deal else 0.0}


# ── run one scenario across all three arms + analytic cross-checks ──────────
def run_scenario(i: int, gen=make_scenario) -> dict:
    s = gen(i)
    q, d = quoted_config(s)
    R_q, F_q, L_q = reservation(s, q, d), floor_price(s, q, d), list_price(s, q, d)
    quoted_feasible = R_q >= F_q - _EPS
    any_feasible = len(feasible_configs(s)) > 0
    o_joint = oracle_joint(s)

    co = checkout(s)
    ch = cheap_haggle(s)
    nx = run_nx_session(s)

    # analytic cross-checks (a weak/lucky policy cannot silently move the verdict)
    assert co["deal"] == (R_q >= L_q - _EPS)
    assert ch["deal"] == quoted_feasible, (i, ch["deal"], quoted_feasible)
    assert nx.settled == any_feasible, (i, nx.settled, any_feasible)

    return {
        "i": i, "session_ref": s.session_ref,
        "params": {"need_qty": s.need_qty, "need_by": s.need_by,
                   "unit_value": round(s.unit_value, 3), "urgency": round(s.urgency, 3),
                   "cap": s.cap, "c0": round(s.c0, 3), "c1": round(s.c1, 4),
                   "expedite": round(s.expedite, 3), "inventory": s.inventory,
                   "markup": round(s.markup, 4), "min_markup": round(s.min_markup, 4)},
        "quoted_config": [q, d], "quoted_feasible": bool(quoted_feasible),
        "oracle_any_feasible": bool(any_feasible), "oracle_joint": round(o_joint, 4),
        "checkout": {"deal": co["deal"], "joint": round(co["joint_surplus"], 4)},
        "cheap_haggle": {"deal": ch["deal"], "rounds": ch["rounds"],
                         "joint": round(ch["joint_surplus"], 4)},
        "nx": {"deal": nx.settled, "qty": nx.agreed_qty, "ship_date": nx.agreed_ship_date,
               "price": round(nx.agreed_price, 4) if nx.agreed_price is not None else None,
               "rounds": nx.rounds_used, "joint": round(nx.joint_surplus, 4),
               "recovery": (round(nx.joint_surplus / o_joint, 4) if o_joint > _EPS else None)},
    }


def _rate(records, arm) -> float:
    return sum(1 for r in records if r[arm]["deal"]) / len(records)


def _mean(xs) -> float:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m nx.experiment",
        description="SNHP-NX/1 three-arm deal-formation experiment")
    ap.add_argument("--regime", choices=sorted(REGIMES), default="neutral",
                    help="'neutral' = the PRE-REGISTERED scenario set (default); "
                         "'constrained' = the EXPLORATORY tight-deadline regime")
    args = ap.parse_args(argv)
    reg = REGIMES[args.regime]

    records = [run_scenario(i, reg["gen"]) for i in range(N_SCENARIOS)]

    r_checkout = _rate(records, "checkout")
    r_haggle = _rate(records, "cheap_haggle")
    r_nx = _rate(records, "nx")

    # KILL-NX (bidirectional, thresholds frozen in PREREG)
    haggle_ratio = (r_haggle / r_nx) if r_nx > 0 else float("inf")
    lift_ratio = (r_nx / r_checkout) if r_checkout > 0 else float("inf")
    forward_kill = haggle_ratio >= KILL_HAGGLE_FRAC          # bundling not necessary
    reverse_kill = lift_ratio < KILL_LIFT_FRAC               # NX adds nothing
    survives = (not forward_kill) and (not reverse_kill)
    verdict = ("SURVIVES" if survives else
               "KILLED-forward(cheap-haggle recovers >=80% of NX)" if forward_kill else
               "KILLED-reverse(NX not materially above checkout)")

    # per-arm surplus stats (realized joint on struck deals; recovery vs oracle)
    def joints(arm):
        return [r[arm]["joint"] for r in records if r[arm]["deal"]]
    surplus = {
        "checkout": {"n_deals": sum(r["checkout"]["deal"] for r in records),
                     "mean_joint_on_deals": round(_mean(joints("checkout")), 3),
                     "total_joint": round(sum(r["checkout"]["joint"] for r in records), 3)},
        "cheap_haggle": {"n_deals": sum(r["cheap_haggle"]["deal"] for r in records),
                         "mean_joint_on_deals": round(_mean(joints("cheap_haggle")), 3),
                         "total_joint": round(sum(r["cheap_haggle"]["joint"] for r in records), 3)},
        "nx": {"n_deals": sum(r["nx"]["deal"] for r in records),
               "mean_joint_on_deals": round(_mean(joints("nx")), 3),
               "total_joint": round(sum(r["nx"]["joint"] for r in records), 3),
               "mean_recovery_vs_oracle": round(
                   _mean([r["nx"]["recovery"] for r in records if r["nx"]["deal"]]), 4),
               "mean_rounds": round(_mean([r["nx"]["rounds"] for r in records if r["nx"]["deal"]]), 3)},
    }
    total_oracle = sum(r["oracle_joint"] for r in records)
    surplus["checkout"]["capture_vs_oracle"] = round(
        surplus["checkout"]["total_joint"] / total_oracle, 4) if total_oracle else None
    surplus["cheap_haggle"]["capture_vs_oracle"] = round(
        surplus["cheap_haggle"]["total_joint"] / total_oracle, 4) if total_oracle else None
    surplus["nx"]["capture_vs_oracle"] = round(
        surplus["nx"]["total_joint"] / total_oracle, 4) if total_oracle else None

    out = {
        "meta": {"regime": args.regime, "preregistered": reg["preregistered"],
                 "master_seed": reg["seed"], "n_scenarios": N_SCENARIOS,
                 "cheap_haggle_rounds": CHEAP_HAGGLE_ROUNDS,
                 "kill_haggle_frac": KILL_HAGGLE_FRAC, "kill_lift_frac": KILL_LIFT_FRAC,
                 "generator": reg["desc"],
                 "policies": "scripted/deterministic; buyer=gt_negotiate_bundle, no LLM"},
        "deal_rates": {"checkout": round(r_checkout, 4),
                       "cheap_haggle": round(r_haggle, 4), "nx": round(r_nx, 4)},
        "kill_nx": {"haggle_over_nx": round(haggle_ratio, 4),
                    "nx_over_checkout": round(lift_ratio, 4),
                    "forward_kill_fires": bool(forward_kill),
                    "reverse_kill_fires": bool(reverse_kill),
                    "verdict": verdict},
        "oracle": {"total_joint": round(total_oracle, 3),
                   "n_any_feasible": sum(r["oracle_any_feasible"] for r in records),
                   "n_quoted_feasible": sum(r["quoted_feasible"] for r in records)},
        "surplus": surplus,
        "records": records,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / reg["out"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)

    # ── mechanical report to stdout ──
    if not reg["preregistered"]:
        print(f"[nx] *** EXPLORATORY regime {args.regime!r} — NOT pre-registered; "
              f"locates a boundary, does not establish the headline ***")
    print(f"[nx] regime={args.regime}  ({reg['desc']})")
    print(f"[nx] {N_SCENARIOS} scenarios, master seed {reg['seed']}")
    print(f"[nx] deal rates:  checkout={r_checkout:.3f}  "
          f"cheap-haggle={r_haggle:.3f}  nx={r_nx:.3f}")
    print(f"[nx] oracle: {out['oracle']['n_any_feasible']}/{N_SCENARIOS} any-config "
          f"feasible; {out['oracle']['n_quoted_feasible']}/{N_SCENARIOS} quoted-config "
          f"feasible")
    print(f"[nx] KILL-NX: cheap-haggle/nx = {haggle_ratio:.3f} "
          f"(forward kill fires iff >= {KILL_HAGGLE_FRAC})")
    print(f"[nx] KILL-NX: nx/checkout    = {lift_ratio:.3f} "
          f"(reverse kill fires iff <  {KILL_LIFT_FRAC})")
    print(f"[nx] VERDICT: {verdict}"
          + ("" if reg["preregistered"] else "   [EXPLORATORY — not the registered verdict]"))
    print(f"[nx] surplus capture vs oracle:  checkout={surplus['checkout']['capture_vs_oracle']}  "
          f"cheap-haggle={surplus['cheap_haggle']['capture_vs_oracle']}  "
          f"nx={surplus['nx']['capture_vs_oracle']}")
    print(f"[nx] nx mean recovery vs oracle (on deals) = "
          f"{surplus['nx']['mean_recovery_vs_oracle']}; "
          f"nx mean rounds = {surplus['nx']['mean_rounds']}")
    print(f"[nx] results -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
