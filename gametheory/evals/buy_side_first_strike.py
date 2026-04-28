"""
Sprint 2 acceptance test #2 — buy-side improvement vs no-defense.

The buy-side margin claim (-0.025 max in alternating-offers SAO) was
measured for *unmodified* SNHP-as-buyer. The first-strike API converts
the buyer from second-mover into first-mover-on-reservation by making
their walk-away credible. We need empirical evidence that the conversion
actually improves H2H margin, not just the cryptographic primitive.

Experimental design:
  - Fix SNHP as the buyer (always added second to the SAO mechanism).
  - Iterate over each B2B opponent strategy as the seller.
  - Run two configurations:
       BASELINE     — vanilla SNHP buy-side
       FIRST_STRIKE — SNHP commits to reservation from round 0:
                       propose() always offers at reservation utility,
                       respond() only accepts >= reservation
  - Measure per-opponent: avg buyer utility, deal rate, walk-away cost.
  - Aggregate: mean margin (utility - reservation) across opponents.

Interpretation:
  - First-strike should HELP against opponents whose tactic is to
    extract concessions (Anchorer, Cialdini, BATNA Bluffer, GoodCop/BadCop).
  - First-strike should HURT against opponents who walk easily (Nibbler,
    Silent Hardliner) — deal rate drops without margin offsetting.
  - Net effect = the empirical claim that the cryptographic primitive
    is worth shipping.

Run:
  ../venv/bin/python -m gametheory.evals.buy_side_first_strike
"""
from __future__ import annotations

import os
import statistics
import sys
from typing import Type

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "snhp",
))

import numpy as np  # noqa: E402

from negmas.sao import SAOState, ResponseType  # noqa: E402

from b2b_opponents import B2B_OPPONENTS  # noqa: E402
from b2b_round_robin import play_matchup, create_issues, create_ufuns  # noqa: E402
import negmas_agent  # noqa: E402
from negmas_agent import SNHPAgent  # noqa: E402


# ─── First-strike modified buyer ─────────────────────────────────────────────


class SNHPFirstStrikeBuyer(SNHPAgent):
    """
    SNHP buyer with a CREDIBLE commitment to a reservation floor:
      - propose() asks aggressively (slow concession from 0.85 toward R+0.05)
      - respond() refuses anything that gives buyer utility < reservation
    Mechanism: this models the equilibrium effect of declare_first_strike —
    the buyer's walk-away is binding, so under must-deal pressure they take
    the walk-away penalty rather than concede below R, while a vanilla
    buyer would concede.
    """

    _FS_OPENING_UTIL = 0.85
    _FS_CONCESSION_PER_STEP = 0.015

    def propose(self, state: SAOState):
        rv = float(self.ufun.reserved_value or 0.0)
        floor = rv + 0.05
        step = max(0, getattr(state, "step", 0))
        target = max(floor, self._FS_OPENING_UTIL - step * self._FS_CONCESSION_PER_STEP)

        outcomes = list(self.nmi.outcomes or [])
        if not outcomes:
            return None
        scored = [(float(self.ufun(o)), o) for o in outcomes]
        above = [(u, o) for u, o in scored if u >= target - 1e-6]
        if above:
            return min(above, key=lambda x: x[0] - target)[1]
        return max(scored, key=lambda x: x[0])[1]

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        offer = state.current_offer
        if offer is None:
            return ResponseType.REJECT_OFFER
        u = float(self.ufun(offer)) if self.ufun(offer) is not None else 0.0
        rv = float(self.ufun.reserved_value or 0.0)
        return ResponseType.ACCEPT_OFFER if u >= rv else ResponseType.REJECT_OFFER


# ─── Focused buy-side matchup runner ─────────────────────────────────────────


def play_buy_side_matchup(
    BuyerCls: Type, SellerCls: Type, n_rounds: int = 20, n_steps: int = 10,
    buyer_pressure: float = 1.0,
) -> tuple[float, float, float]:
    """
    Opponent-as-seller (A, added first) vs Buyer-class (B, added second).
    Wraps the existing b2b_round_robin.play_matchup. `buyer_pressure > 1.0`
    raises the buyer's must-deal probability, simulating "buyer under
    pressure to close" — the regime where commitment value shows up.
    """
    np.random.seed(42)
    issues = create_issues()
    ufun_a, ufun_b = create_ufuns(issues, n_steps)
    seller_avg, buyer_avg, deal_rate = play_matchup(
        SellerCls, BuyerCls, ufun_a, ufun_b, issues,
        n_steps=n_steps, n_rounds=n_rounds, batna=0.40,
        seller_pressure=1.0, buyer_pressure=buyer_pressure,
    )
    return buyer_avg, seller_avg, deal_rate


# ─── Run experiment ──────────────────────────────────────────────────────────


_EXPLOITER_OPPONENTS = {
    # The strategies whose value comes from extracting concessions.
    # Hypothesized to be where first-strike helps most.
    "Anchorer", "BATNA Bluffer", "Cialdini", "GoodCop/BadCop", "Anchoring Bias",
}


def run_experiment(n_rounds: int = 20, buyer_pressure: float = 1.0) -> dict:
    print(f"Running buy-side tournament: SNHP-buyer vs each opponent, "
          f"n_rounds={n_rounds}, buyer_pressure={buyer_pressure}")
    print()
    print(f"{'Opponent':<22} | {'BASE buyer':>10} {'FS buyer':>10} {'Δ buyer':>9} | "
          f"{'BASE deal':>9} {'FS deal':>9}")
    print("-" * 90)

    rows = []
    for name, SellerCls in B2B_OPPONENTS.items():
        u_base, _, dr_base = play_buy_side_matchup(
            SNHPAgent, SellerCls, n_rounds=n_rounds,
            buyer_pressure=buyer_pressure,
        )
        u_fs, _, dr_fs = play_buy_side_matchup(
            SNHPFirstStrikeBuyer, SellerCls, n_rounds=n_rounds,
            buyer_pressure=buyer_pressure,
        )
        delta = u_fs - u_base
        rows.append({
            "opponent": name,
            "buyer_util_base": u_base,
            "buyer_util_fs": u_fs,
            "delta_buyer_util": delta,
            "deal_rate_base": dr_base,
            "deal_rate_fs": dr_fs,
            "is_exploiter": name in _EXPLOITER_OPPONENTS,
        })
        flag = " ⭐" if name in _EXPLOITER_OPPONENTS else ""
        print(f"{name:<22} | {u_base:>10.4f} {u_fs:>10.4f} {delta:>+9.4f} | "
              f"{dr_base:>9.0%} {dr_fs:>9.0%}{flag}")

    print("-" * 90)
    base_avg = statistics.mean(r["buyer_util_base"] for r in rows)
    fs_avg = statistics.mean(r["buyer_util_fs"] for r in rows)
    base_deal = statistics.mean(r["deal_rate_base"] for r in rows)
    fs_deal = statistics.mean(r["deal_rate_fs"] for r in rows)
    print(f"{'OVERALL MEAN':<22} | {base_avg:>10.4f} {fs_avg:>10.4f} {fs_avg - base_avg:>+9.4f} | "
          f"{base_deal:>9.0%} {fs_deal:>9.0%}")

    exploiters = [r for r in rows if r["is_exploiter"]]
    if exploiters:
        ex_base = statistics.mean(r["buyer_util_base"] for r in exploiters)
        ex_fs = statistics.mean(r["buyer_util_fs"] for r in exploiters)
        ex_dr_base = statistics.mean(r["deal_rate_base"] for r in exploiters)
        ex_dr_fs = statistics.mean(r["deal_rate_fs"] for r in exploiters)
        print(f"{'EXPLOITER SUBSET ⭐':<22} | {ex_base:>10.4f} {ex_fs:>10.4f} {ex_fs - ex_base:>+9.4f} | "
              f"{ex_dr_base:>9.0%} {ex_dr_fs:>9.0%}")

    print()
    print("Reservation values are randomized per round (BATNA noise); "
          "absolute utility levels reflect 'utility above floor'.")
    return {
        "rows": rows,
        "overall_base_buyer_util": base_avg,
        "overall_fs_buyer_util": fs_avg,
        "overall_delta": fs_avg - base_avg,
        "overall_base_deal_rate": base_deal,
        "overall_fs_deal_rate": fs_deal,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--buyer-pressure", type=float, default=1.0,
                    help="Buyer must-deal multiplier (>1 = buyer under pressure)")
    p.add_argument("--n-rounds", type=int, default=20)
    args = p.parse_args()
    out = run_experiment(n_rounds=args.n_rounds, buyer_pressure=args.buyer_pressure)
    delta = out["overall_delta"]
    msg = "FIRST-STRIKE HELPS" if delta > 0 else "FIRST-STRIKE HURTS"
    print()
    print(f"=> Δ overall buyer utility = {delta:+.4f}  →  {msg}")
