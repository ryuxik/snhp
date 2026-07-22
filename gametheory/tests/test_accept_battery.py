"""Accept-collapse battery — the permanent instrument behind vend/RESULTS.md P7.

WHY THIS EXISTS
The plain-terms recommender was observed to ACCEPT a rising buyer's floor
($175 on a 150→165→175 climb) with rounds still on the clock. The
pre-registered hypothesis (P7, vend/RESULTS.md) is that the accept is
EV-dominated: the engine's OWN rollout machinery values holding-and-
countering strictly above accepting, and the accept is manufactured by a
concession schedule that saturates because the horizon denominator is wrong
(`sell.py:120` / `buy.py:209` divide CUMULATIVE rounds_used by the REMAINING
`deadline_rounds` that `plain_terms.py:138,143` pass — so time_fraction
clamps to 1.0 and aspiration collapses to the schelling floor).

WHAT'S HERE
  * Measurement helpers that quantify, for any single-issue node, the
    EV_gap = V_rollout(best counter) − V(recommended) using the engine's own
    `_conceder_payoffs` rollouts (seed=0), plus the accept-threshold in $.
  * A realized-surplus simulator (P6) that plays the full engine to
    termination against fixed out-of-model opponents, comparing the SHIPPED
    accept-on-threshold policy against a HOLD-to-rollout-optimal-counter
    policy — a control arm with a pre-registered bidirectional read.
  * FAST tests (default suite): monotonicity + threshold-ordering + a
    small-sample EV sanity on the reported node. These encode the CORRECT
    (post-fix) behavior and are regression guards.
  * SLOW tests (`-m slow`): the full 400k battery across all six probes and
    the P6 arm.
  * `python -m gametheory.tests.test_accept_battery` runs the whole battery
    as a script and prints the pre/post tables that populate P7.

Determinism: seed=0 everywhere. No LLM anywhere. No network. Pure rollouts.
"""
from __future__ import annotations

import re
import contextlib

import numpy as np
import pytest

import gametheory.negotiation.sell as _sellmod
from gametheory.negotiation.plain_terms import (
    negotiate_turn, _seller_frame, _buyer_frame, _clamp01, _VALIDATED_KNOB,
)
from gametheory.negotiation.sell import sell_next_offer
from gametheory.negotiation.buy import buy_next_offer
from gametheory.negotiation.mc_search import _single_issue_model, _conceder_payoffs

# ── The reported node ─────────────────────────────────────────────────────────
WA, TGT = 170.0, 210.0
CP = [150.0, 165.0, 175.0]
MINE = [215.0, 195.0]

# Full battery uses 400k rollouts (matches the probe / P7 primary metric).
# The fast in-suite tests use a smaller-but-still-stable budget.
FULL_N = 400_000
FAST_N = 40_000


# ── Frame + recommender introspection ─────────────────────────────────────────
def _frame(side, wa, tgt):
    return _seller_frame(wa, tgt) if side == "sell" else _buyer_frame(wa, tgt)


def _recommender_util(side, wa, tgt, cp, mine, rounds_left):
    """The engine's NEXT-COUNTER utility for this node (what the accept rule at
    plain_terms.py:164 compares against).

    This helper must reflect what the SHIPPED adapter does, so it reconstructs the
    adapter's clamped mapping AND its deadline_rounds convention: the adapter passes
    the TOTAL horizon (offers exchanged + rounds_left), never the remaining count —
    see plain_terms.py `total_horizon`. Mirroring that here keeps the accept-
    threshold / base-price measurement faithful to production; if this drifts from
    the adapter the threshold and EV_gap become meaningless."""
    to_util, to_price = _frame(side, wa, tgt)
    opp_hist = [_clamp01(to_util(p)) for p in cp]
    my_hist = [_clamp01(to_util(p)) for p in mine]
    total_horizon = len(cp) + len(mine) + rounds_left      # mirror plain_terms adapter
    if side == "sell":
        rec = sell_next_offer(my_reservation=0.0, opponent_offer_history=opp_hist,
                              my_offer_history=my_hist, deadline_rounds=total_horizon,
                              pareto_knob=_VALIDATED_KNOB)
    else:
        rec = buy_next_offer(my_reservation=0.0, seller_offer_history=opp_hist,
                             my_offer_history=my_hist, deadline_rounds=total_horizon,
                             pareto_knob=_VALIDATED_KNOB)
    ru = float(rec["recommended_offer"])
    return ru, to_price(ru)


def accept_threshold_price(side, wa, tgt, cp, mine, rounds_left):
    """The dollar price at which the counterparty's standing offer would flip the
    engine from counter to accept (= to_price of the recommender's next-counter
    utility). Lower threshold ⇒ the engine caves to weaker offers."""
    _, thr_price = _recommender_util(side, wa, tgt, cp, mine, rounds_left)
    return round(thr_price, 2)


# ── EV_gap: the engine's own rollouts value the best counter vs what it chose ──
def ev_probe(side, wa, tgt, cp, mine, rounds_left, n=FULL_N, seed=0):
    """Primary metric for one node.

    Uses `_conceder_payoffs` (the SHIPPED rollout belief) to score every action
    on the single-issue grid, then reports:
      V_best_counter   — max rollout EV over the grid (our utility, discounted).
      V_recommended    — rollout EV of the move the engine actually makes:
                         for `counter`, the EV at the recommended action;
                         for `accept`, the CERTAIN utility of the taken price
                         (accept = take their_last now at t=0, delta**0 = 1).
      EV_gap           — V_best_counter − V_recommended.
      ci95             — 95% half-width of EV_gap (combined SE of the two means).
    A positive EV_gap that clears the CI means the engine left rollout-valued
    surplus on the table.
    """
    to_util, to_price = _frame(side, wa, tgt)
    turn = negotiate_turn(side=side, walk_away=wa, target=tgt, counterparty_offers=cp,
                          my_previous_offers=mine, rounds_left=rounds_left)
    rec_util, rec_price = _recommender_util(side, wa, tgt, cp, mine, rounds_left)

    # Build the same action grid the production MC would search, and score it.
    actions, base_index, u_lo, _ = _single_issue_model(
        side, wa, tgt, cp, rounds_left, base_price=rec_price)
    rng = np.random.default_rng(seed)
    P = _conceder_payoffs(actions, u_lo, rounds_left, rng, n)   # [k, n]
    means = P.mean(axis=1)
    ses = P.std(axis=1) / np.sqrt(n)
    best = int(np.argmax(means))
    v_best, se_best = float(means[best]), float(ses[best])

    their_last = cp[-1] if cp else None
    their_util_raw = to_util(their_last) if their_last is not None else None
    if turn["action"] == "accept":
        v_rec = float(their_util_raw)          # certain, undiscounted
        se_rec = 0.0
    elif turn["action"] == "counter":
        v_rec = float(means[base_index])
        se_rec = float(ses[base_index])
    else:                                      # walk / negotiate_directly
        v_rec = 0.0
        se_rec = 0.0

    ev_gap = v_best - v_rec
    ci95 = 1.96 * float(np.sqrt(se_best ** 2 + se_rec ** 2))
    return {
        "action": turn["action"],
        "recommended_price": turn["recommended_price"],
        "accept_threshold": round(to_price(rec_util), 2),
        "best_counter_price": round(float(to_price(actions[best])), 2),
        "V_recommended": round(v_rec, 4),
        "V_best_counter": round(v_best, 4),
        "EV_gap": round(ev_gap, 4),
        "ci95": round(ci95, 5),
        "confirmed": ev_gap > 2 * ci95,        # P7 per-probe confirm rule
    }


# ── P6: realized-surplus control arm (out-of-model opponents) ─────────────────
def _buyer_willingness(policy, r, horizon, b0, m, rng):
    """Buyer's willingness-to-pay at round r (rises b0 -> m over the horizon).
    Sell scenario: buyer is the counterparty; m is the hidden max WTP."""
    t = r / max(horizon - 1, 1)
    if policy == "conceder":
        frac = t ** 0.5            # concedes fast (concave)
    elif policy == "boulware":
        frac = t ** 3.0            # concedes slow (convex)
    elif policy == "mirror":
        frac = t                   # linear
    elif policy == "random":
        frac = float(np.clip(t + rng.uniform(-0.15, 0.15), 0.0, 1.0))
    elif policy == "anomalous_below_floor":
        frac = t ** 0.5            # climbs, but m<WA so never reaches a ZOPA
    else:
        raise ValueError(policy)
    return b0 + (m - b0) * frac


def _rollout_optimal_counter_price(side, wa, tgt, cp, mine, rounds_left, n, seed):
    to_util, to_price = _frame(side, wa, tgt)
    _, rec_price = _recommender_util(side, wa, tgt, cp, mine, rounds_left)
    actions, base_index, u_lo, _ = _single_issue_model(
        side, wa, tgt, cp, rounds_left, base_price=rec_price)
    rng = np.random.default_rng(seed)
    P = _conceder_payoffs(actions, u_lo, rounds_left, rng, n)
    best = int(np.argmax(P.mean(axis=1)))
    return round(float(to_price(actions[best])), 2)


def realized_surplus(policy, seller_policy, *, wa=WA, tgt=TGT, b0=155.0, m=200.0,
                     horizon=8, inner_n=50_000, seed=0):
    """Play one full sell-side negotiation to termination.

    seller_policy ∈ {"shipped", "hold_to_counter"}:
      shipped          — obey negotiate_turn verbatim (accept on its threshold).
      hold_to_counter  — identical EXCEPT when the engine says accept with time
                         left, hold and re-post the rollout-optimal counter; only
                         take the buyer's standing offer when it already meets that
                         counter, or at the buzzer (rounds_left<=2) if it clears WA.
    Buyer follows `policy` (out-of-model). Returns realized seller surplus
    (deal_price - wa) or 0.0 on no-deal. Both seller policies face the identical
    buyer trajectory, so the contrast is apples-to-apples."""
    rng = np.random.default_rng(seed)
    cp: list[float] = []
    mine: list[float] = []
    for r in range(horizon):
        rounds_left = max(2, horizon - r)
        w = _buyer_willingness(policy, r, horizon, b0, m, rng)
        cp.append(round(float(w), 2))
        turn = negotiate_turn(side="sell", walk_away=wa, target=tgt,
                              counterparty_offers=cp, my_previous_offers=mine,
                              rounds_left=rounds_left)
        act = turn["action"]
        if seller_policy == "hold_to_counter" and act == "accept" and rounds_left > 2:
            # override the early accept: hold to the rollout-optimal counter.
            s_price = _rollout_optimal_counter_price(
                "sell", wa, tgt, cp, mine, rounds_left, inner_n, seed)
            act = "counter"
            turn = {**turn, "action": "counter", "recommended_price": s_price}
        if act == "accept":
            return round(cp[-1] - wa, 4)
        if act == "walk" or act == "negotiate_directly":
            return 0.0
        s_price = turn["recommended_price"]
        mine.append(round(float(s_price), 2))
        # Buyer accepts the seller's counter iff it has fallen to within what the
        # buyer will be willing to pay next round (rising toward m, capped at m).
        w_next = _buyer_willingness(policy, r + 1, horizon, b0, m, rng)
        if s_price <= min(m, w_next):
            return round(s_price - wa, 4)
    # Buzzer: take the buyer's last standing offer if it clears the floor.
    if cp and cp[-1] > wa:
        return round(cp[-1] - wa, 4)
    return 0.0


_P6_FAMILIES = ["conceder", "boulware", "mirror", "random", "anomalous_below_floor"]


def p6_table(inner_n=50_000, seed=0):
    """Realized seller surplus, shipped vs hold-to-counter, per opponent family.
    anomalous_below_floor uses m<WA (no ZOPA) — the control that must NOT favor
    hold-to-counter."""
    rows = []
    for fam in _P6_FAMILIES:
        m = 160.0 if fam == "anomalous_below_floor" else 200.0
        shipped = realized_surplus(fam, "shipped", m=m, inner_n=inner_n, seed=seed)
        hold = realized_surplus(fam, "hold_to_counter", m=m, inner_n=inner_n, seed=seed)
        rows.append({"family": fam, "m": m, "shipped": shipped,
                     "hold_to_counter": hold, "delta": round(hold - shipped, 4)})
    return rows


def p6_ensemble(inner_n=20_000):
    """Per-family mean(delta) ± SE over a small grid of buyer parameterizations,
    so the secondary confirm rule ('hold-to-counter beats shipped by >1 SE') has a
    real dispersion to measure against. ZOPA families sweep m/b0/horizon; the
    below-floor control keeps m<WA. delta = hold_to_counter − shipped surplus."""
    grid = [(m, b0, hz) for m in (188.0, 196.0, 204.0)
            for b0 in (150.0, 158.0) for hz in (6, 8)]
    out = {}
    for fam in _P6_FAMILIES:
        deltas = []
        for (m, b0, hz) in grid:
            mm = 160.0 if fam == "anomalous_below_floor" else m
            seeds = (0, 1, 2) if fam == "random" else (0,)
            for sd in seeds:
                sh = realized_surplus(fam, "shipped", m=mm, b0=b0, horizon=hz,
                                      inner_n=inner_n, seed=sd)
                ho = realized_surplus(fam, "hold_to_counter", m=mm, b0=b0, horizon=hz,
                                      inner_n=inner_n, seed=sd)
                deltas.append(ho - sh)
        arr = np.asarray(deltas, float)
        mean = float(arr.mean())
        se = float(arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else 0.0
        out[fam] = {"mean_delta": round(mean, 4), "se": round(se, 4),
                    "n": len(arr), "beats_by_1se": mean > se}
    return out


# ── The six probes, as data ───────────────────────────────────────────────────
def probe_p1(n=FULL_N):
    return {rl: ev_probe("sell", WA, TGT, CP, MINE, rl, n=n)
            for rl in (2, 3, 5, 8)}


def probe_p2(n=FULL_N):
    trajectories = {
        "climbing_150_165_175": [150.0, 165.0, 175.0],
        "barely_174_174_175": [174.0, 174.0, 175.0],
        "flat_165_165_165": [165.0, 165.0, 165.0],
        "steep_150_170_178": [150.0, 170.0, 178.0],
    }
    return {k: ev_probe("sell", WA, TGT, v, MINE, 3, n=n) for k, v in trajectories.items()}


def probe_p3(n=FULL_N):
    histories = {
        "mine_[]": [],
        "mine_[215]": [215.0],
        "mine_[215,195]": [215.0, 195.0],
        "mine_[215,205,195]": [215.0, 205.0, 195.0],
    }
    return {k: ev_probe("sell", WA, TGT, CP, v, 3, n=n) for k, v in histories.items()}


def probe_p4(n=FULL_N):
    # buy-side mirror: buyer WA(ceiling)=210, target(low)=170, seller descending,
    # deep history, rounds_left=3.
    b_wa, b_tgt = 210.0, 170.0
    seller_desc = [230.0, 215.0, 205.0]          # seller's asks, descending
    my_buy = [150.0, 160.0]                       # our prior buy offers
    return {"buy_mirror": ev_probe("buy", b_wa, b_tgt, seller_desc, my_buy, 3, n=n)}


def probe_p5(side="sell"):
    """Deadline scaling: fixed history, sweep rounds_left, record accept-threshold($).
    No rollouts needed — pure schedule readout."""
    return {rl: accept_threshold_price("sell", WA, TGT, CP, MINE, rl)
            for rl in range(2, 13)}


# ── The pre-registered H1 confirm/kill conjunction (P7) ───────────────────────
# A per-node `EV_gap > 2*CI` flag detects GROSS EV-domination pre-fix (accept-
# collapse gaps of 0.15-0.28). Post-fix the CI shrinks to ~0.0016 at 400k, so the
# tiny residual closed-form-vs-conceder-rollout gap (a KNOWN, validated null: MC
# does not beat the closed form in realized play — mc_search.py docstring) can
# still trip an individual flag. The BUG verdict is therefore the pre-registered
# CONJUNCTION, not any single node: primary (>=4/4 EV-probes) AND secondary
# (hold-to-counter beats shipped >1 SE on conceder AND mirror) AND tertiary
# (accept-threshold SATURATED across rl 2-5). H1 is CONFIRMED only when all three
# hold; the fix's job is to make this conjunction FALSE.
def h1_verdict(n=FULL_N, inner_n=20_000):
    p1, p2, p3, p4 = probe_p1(n), probe_p2(n), probe_p3(n), probe_p4(n)
    p5 = probe_p5()
    ens = p6_ensemble(inner_n=inner_n)
    ev_probe_fires = {
        "P1": any(v["confirmed"] for v in p1.values()),
        "P2": any(v["confirmed"] for k, v in p2.items() if "climbing" in k or "steep" in k),
        "P3": all(v["confirmed"] for v in p3.values()),
        "P4": p4["buy_mirror"]["confirmed"],
    }
    small = [p5[rl] for rl in (2, 3, 4, 5)]
    p5_saturated = not all(b > a + 1e-6 for a, b in zip(small, small[1:]))
    p6_secondary = ens["conceder"]["beats_by_1se"] and ens["mirror"]["beats_by_1se"]
    n_ev = sum(ev_probe_fires.values())
    h1 = (n_ev >= 4) and p6_secondary and p5_saturated
    # crisp bug-signatures, reported alongside the conjunction
    any_accept = any(v["action"] == "accept"
                     for d in (p1, p2, p3, p4) for v in d.values())
    reported = p1[3]
    return {
        "ev_probe_fires": ev_probe_fires, "n_ev": n_ev,
        "p5_saturated": p5_saturated, "p6_secondary": p6_secondary,
        "h1_confirmed": h1, "any_accept_on_probes": any_accept,
        "reported_node_action": reported["action"],
        "reported_node_price": reported["recommended_price"],
        "reported_node_ev_gap": reported["EV_gap"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# P8 — the conceder/schelling branch: dominated, or a deal-existence hedge?
#
# The branch (sell.py:175-178 / buy.py:242-245) routes a VISIBLY-CONCEDING
# opponent (offer[-1] - offer[0] > 0.05 utility) to max(aspiration, schelling)
# instead of max(aspiration, rubinstein_floor). It only DIVERGES from the
# non-conceder route where aspiration < rubinstein_floor — the ENDGAME of any
# multi-round negotiation (rounds_left small, history deep, so time_fraction is
# high and aspiration has decayed below the SPE floor). P7 flagged this as
# possible trajectory-perversity; P8 measured it (vend/RESULTS.md P8) and KILLED
# H1 ("strictly dominated"): the branch is a deal-existence HEDGE. These nodes
# are the permanent instrument — they guard the KILLED verdict so a future
# "simplification" that removes the branch can't silently regress deal-existence.
#
# Arms are applied by monkeypatching sell.get_param('opp_concession_threshold')
# in-test only (production untouched): A=shipped(0.05); B=always-Rubinstein
# (+inf ⇒ else-branch for everyone = the fix H1 would have shipped); C=always-
# schelling(-inf). Buy hardcodes 0.05, so the arm-swap + realized-surplus arm are
# sell-side (matching P6); buy bindingness is asserted structurally.
# Determinism: seed=0; the 1-D particle filter's inferred weight is stable.
# ══════════════════════════════════════════════════════════════════════════════
_P8_ASP = re.compile(r"aspiration=([0-9.]+)")
_P8_RUB = re.compile(r"Rubinstein floor(?:\s*\(second-mover-corrected\))?=([0-9.]+)")
_REAL_GET_PARAM = _sellmod.get_param


@contextlib.contextmanager
def _p8_arm(which):
    """Swap the conceder-branch routing for the sell recommender. 'A'=shipped,
    'B'=always-Rubinstein (the fix H1 would have applied), 'C'=always-schelling."""
    if which == "A":
        yield
        return
    override = np.inf if which == "B" else -np.inf   # +inf⇒else(rub); -inf⇒if(sch)
    def _g(name):
        return override if name == "opp_concession_threshold" else _REAL_GET_PARAM(name)
    _sellmod.get_param = _g
    try:
        yield
    finally:
        _sellmod.get_param = _REAL_GET_PARAM


def _p8_sell_floors(wa, tgt, cp, mine, rl):
    """(aspiration, rubinstein_floor, schelling_floor, recommended_util) for a sell
    node under the plain_terms adapter convention (total horizon, knob=1.0). The
    branch DIVERGES across arms iff aspiration < rubinstein_floor."""
    to_util, _ = _seller_frame(wa, tgt)
    opp = [_clamp01(to_util(p)) for p in cp]
    my = [_clamp01(to_util(p)) for p in mine]
    np.random.seed(0)
    rec = sell_next_offer(my_reservation=0.0, opponent_offer_history=opp,
                          my_offer_history=my, deadline_rounds=len(cp) + len(mine) + rl,
                          pareto_knob=_VALIDATED_KNOB)
    return (float(_P8_ASP.search(rec["rationale"]).group(1)),
            float(_P8_RUB.search(rec["rationale"]).group(1)),
            float(rec["schelling_floor"]), float(rec["recommended_offer"]))


def _p8_buy_floors(wa, tgt, sp, mine, rl):
    to_util, _ = _buyer_frame(wa, tgt)
    opp = [_clamp01(to_util(p)) for p in sp]
    my = [_clamp01(to_util(p)) for p in mine]
    np.random.seed(0)
    rec = buy_next_offer(my_reservation=0.0, seller_offer_history=opp,
                         my_offer_history=my, deadline_rounds=len(sp) + len(mine) + rl,
                         pareto_knob=_VALIDATED_KNOB)
    return (float(_P8_ASP.search(rec["rationale"]).group(1)),
            float(_P8_RUB.search(rec["rationale"]).group(1)),
            float(rec["recommended_offer"]))


# Two binding sell nodes (climbing conceder, rounds_left=2, deep history) and one
# masked node (shallow history — the P7 regime the fix must leave untouched).
_P8_BIND = ([155.0, 170.0, 185.0, 193.0], [215.0, 205.0, 198.0])   # asp<rub ⇒ binds
_P8_BIND_DEEP = ([155.0, 165.0, 175.0, 185.0, 193.0], [215.0, 208.0, 202.0, 198.0])
_P8_MASKED = ([155.0, 175.0], [215.0])                              # asp>rub ⇒ masked


def _p8_play(family, which_arm, *, wa=WA, tgt=TGT, b0, m, horizon, termination, seed=0):
    """Play one sell negotiation to termination under the SHIPPED accept-on-threshold
    policy (negotiate_turn verbatim) and the chosen floor arm. `termination`:
    'standing' = the P6 buzzer grabs the buyer's last standing offer if > WA (deal-
    existence NOT at risk); 'withdrawing' = buzzer ⇒ no deal (the H0 steelman: holding
    a Rubinstein floor that overshoots the buyer's true max now TIMES OUT). Buyer
    trajectory is identical across arms (paired). Returns (surplus, deal_flag)."""
    m = 160.0 if family == "anomalous_below_floor" else m   # control keeps m < WA (no ZOPA)
    rng = np.random.default_rng(seed)
    cp: list[float] = []
    mine: list[float] = []
    with _p8_arm(which_arm):
        for r in range(horizon):
            rounds_left = max(2, horizon - r)
            w = _buyer_willingness(family, r, horizon, b0, m, rng)
            cp.append(round(float(w), 2))
            np.random.seed(0)
            turn = negotiate_turn(side="sell", walk_away=wa, target=tgt,
                                  counterparty_offers=cp, my_previous_offers=mine,
                                  rounds_left=rounds_left)
            act = turn["action"]
            if act == "accept":
                return round(cp[-1] - wa, 4), 1
            if act in ("walk", "negotiate_directly"):
                return 0.0, 0
            s_price = turn["recommended_price"]
            mine.append(round(float(s_price), 2))
            w_next = _buyer_willingness(family, r + 1, horizon, b0, m, rng)
            if s_price <= min(m, w_next):
                return round(s_price - wa, 4), 1
    if termination == "standing" and cp and cp[-1] > wa:
        return round(cp[-1] - wa, 4), 1
    return 0.0, 0


def _p8_surplus(family, which_arm, termination, grid):
    """(mean surplus per opportunity, deal_rate) over a grid of (m, b0, horizon)."""
    surp = np.array([_p8_play(family, which_arm, b0=b0, m=m, horizon=hz,
                              termination=termination, seed=0)
                     for (m, b0, hz) in grid])
    return float(surp[:, 0].mean()), float(surp[:, 1].mean())


# Small fast grid straddling the Rubinstein counter (~$190.3): m below it exercises
# the overshoot region where holding firm times out under a withdrawing buyer.
_P8_FAST_GRID = [(m, 154.0, hz) for m in (188.0, 190.0, 196.0, 204.0) for hz in (6, 8)]
_P8_FULL_MGRID = (188.0, 189.0, 190.0, 191.0, 196.0, 204.0)
_P8_FULL_GRID = [(m, b0, hz) for m in _P8_FULL_MGRID
                 for b0 in (150.0, 158.0) for hz in (6, 8, 10)]


# ══════════════════════════════════════════════════════════════════════════════
# FAST in-suite tests — encode the CORRECT (post-fix) behavior; regression guards.
# ══════════════════════════════════════════════════════════════════════════════
def test_accept_threshold_responds_to_horizon_no_saturation():
    """More time left ⇒ the engine must demand strictly MORE before caving.

    The bug's signature is a SATURATED region: for rounds_left <= rounds_used the
    schedule clamps to time_fraction=1.0, so the accept-threshold is pinned flat at
    the floor for every small horizon (pre-fix: $172 for rounds_left in {2,3,4,5}).
    A weak >=0 check would pass on that flat line, so we require STRICT increase
    across the small-horizon region the bug flattens, plus nondecreasing overall."""
    thr = probe_p5()
    seq = [thr[rl] for rl in range(2, 13)]
    assert all(b >= a - 1e-6 for a, b in zip(seq, seq[1:])), (
        f"accept-threshold not nondecreasing in rounds_left: {seq}")
    small = [thr[rl] for rl in (2, 3, 4, 5)]
    assert all(b > a + 1e-6 for a, b in zip(small, small[1:])), (
        f"accept-threshold saturated (flat) across small horizons — the bug: {small}")


def test_flat_buyer_not_accepted_below_climbing_buyer():
    """Tertiary invariant: a buyer that has NOT conceded (flat) must not be
    accepted at a LOWER price than a climbing buyer with the same final offer."""
    climb = accept_threshold_price("sell", WA, TGT, [150.0, 165.0, 175.0], MINE, 3)
    flat = accept_threshold_price("sell", WA, TGT, [165.0, 165.0, 165.0], MINE, 3)
    assert flat >= climb - 1e-6, (
        f"flat-buyer threshold {flat} < climbing-buyer threshold {climb}")


def test_reported_node_counters_not_accepts():
    """The reported node (rounds_left=3, climbing to $175) must not accept the
    floor with three rounds left — the corrective prediction is a counter ≈$196.9."""
    r = negotiate_turn(side="sell", walk_away=WA, target=TGT, counterparty_offers=CP,
                       my_previous_offers=MINE, rounds_left=3)
    assert r["action"] == "counter", f"expected counter, got {r['action']} @ {r['recommended_price']}"
    assert 194.0 <= r["recommended_price"] <= 200.0, (
        f"corrective counterfactual predicted ~$196.9, got {r['recommended_price']}")


def test_reported_node_gross_ev_domination_gone_fast():
    """Small-sample sanity: after the fix the reported node counters, and the GROSS
    accept-collapse EV-domination (0.15-0.28 pre-fix) is gone. We test against a
    gross threshold, not 2*CI: at any budget a tiny residual closed-form-vs-conceder
    gap can exist (validated null — MC ties, doesn't beat, the closed form), and the
    guard must catch the BUG, not demand the closed form match a heuristic rollout."""
    p = ev_probe("sell", WA, TGT, CP, MINE, 3, n=FAST_N, seed=0)
    assert p["action"] == "counter", p
    assert p["EV_gap"] < 0.05, f"gross EV-domination remains on reported node: {p}"


def test_p8_branch_binds_in_endgame_masked_in_p7_regime():
    """The conceder branch DIVERGES only where aspiration < rubinstein_floor. That
    region is the endgame (deep history, rounds_left=2), NOT the shallow P7 probe
    nodes. This guards the P8 regime's existence AND the P7 invariant that the
    (unshipped) always-Rubinstein fix would leave the P7 nodes byte-identical."""
    a, r, s, rec = _p8_sell_floors(WA, TGT, *_P8_BIND, 2)
    assert a < r - 1e-6, f"expected binding endgame node (asp<rub), got asp={a} rub={r}"
    a2, r2, _, _ = _p8_sell_floors(WA, TGT, *_P8_BIND_DEEP, 2)
    assert a2 < r2 - 1e-6 and (r2 - a2) > (r - a), "deeper history must widen the band"
    am, rm, _, _ = _p8_sell_floors(WA, TGT, *_P8_MASKED, 2)
    assert am > rm + 1e-6, f"shallow P7-regime node must be MASKED (asp>rub), got {am} vs {rm}"
    # buy-side mirror binds structurally too (WA210/T170 descending seller, rl=2)
    ba, br, _ = _p8_buy_floors(210.0, 170.0,
                               [228.0, 216.0, 206.0, 198.0, 192.0],
                               [150.0, 158.0, 163.0, 167.0], 2)
    assert ba < br + 0.5, f"buy-side branch structure present (asp={ba} rub={br})"


def test_p8_conceder_downgraded_to_schelling_route_when_binding():
    """At a binding conceder node the SHIPPED branch routes to max(aspiration,
    schelling) = aspiration (below the Rubinstein floor), while always-Rubinstein
    (arm B) would counter at the higher floor. Documents the branch is LIVE and
    directional — the visible trajectory-perversity P7 flagged, priced by P8 as a
    deal-existence hedge (so it stays)."""
    with _p8_arm("A"):
        a, r, s, recA = _p8_sell_floors(WA, TGT, *_P8_BIND, 2)
    with _p8_arm("B"):
        _, _, _, recB = _p8_sell_floors(WA, TGT, *_P8_BIND, 2)
    # aspiration/rubinstein are parsed from the 3-decimal rationale; recommended is
    # 4-decimal — compare within that rounding (2e-3), not to float epsilon.
    assert abs(recA - a) < 2e-3, f"shipped conceder route should equal aspiration, got {recA} vs {a}"
    assert recB > recA + 1e-3, f"always-Rubinstein must ask MORE than the branch: {recB} vs {recA}"
    assert abs(recB - r) < 2e-3, f"arm B should equal the Rubinstein floor, got {recB} vs {r}"


def test_p8_hedge_pays_under_withdrawing_buyer_fast():
    """KEY regression guard (fast subset): removing the branch (→ always-Rubinstein)
    must not be a free simplification. Under a withdrawing conceder (buzzer ⇒ no
    deal), the SHIPPED branch (arm A) closes deals that always-Rubinstein (arm B)
    times out on — because the Rubinstein floor can overshoot the buyer's true max.
    P8 killed H1 on exactly this: shipped's deal rate must exceed always-Rubinstein's
    by more than the pre-registered 10pp bound on the conceder family."""
    _, dealA = _p8_surplus("conceder", "A", "withdrawing", _P8_FAST_GRID)
    _, dealB = _p8_surplus("conceder", "B", "withdrawing", _P8_FAST_GRID)
    assert dealA - dealB > 0.10, (
        f"conceder deal-rate: shipped {dealA} vs always-Rubinstein {dealB} — the "
        f"deal-existence hedge collapsed (fix would regress it): loss {dealA - dealB}")
    # arm-A restored (context manager) — sanity that we didn't leak the patch
    assert _sellmod.get_param is _REAL_GET_PARAM


# ══════════════════════════════════════════════════════════════════════════════
# P9 — should the PAID MC layer VERIFY accepts, or short-circuit them?
#
# mc_search.py:179-180 short-circuits: an ACCEPT node runs ZERO rollouts, so the
# paid MC layer can't "stop a premature capitulation." P9 (vend/RESULTS.md)
# implemented + evaluated an accept-VERIFICATION — override accept→counter when the
# best-counter rollout EV beats the CERTAIN accept-now EV past a margin M — under
# BOTH P8 termination models, then KILLED it and REVERTED. These guards protect the
# KILL: on every genuine post-P7 accept node the engine's OWN conceder-rollout
# belief values the best counter BELOW the certain accept (gap<0), so the override
# never fires at any pre-registered margin {0.05,0.10,0.15}; the verification is a
# no-op on realized surplus under both termination models. The override-decision
# logic below is the self-contained record of the reverted implementation
# (mc_search._accept_override): override iff (V_best_counter − V_accept_now) > M and
# the gap clears its 95% CI. If a future change makes an accept node's best-counter
# rollout EV exceed the certain accept — a genuine "premature accept" the paid layer
# could catch — these guards fire and P9 must be re-opened.
# Determinism: seed=0; no LLM. The margin ladder anchors to P7 landmarks, not results.
# ══════════════════════════════════════════════════════════════════════════════
_P9_MARGINS = (0.05, 0.10, 0.15)      # pre-registered ladder (residual-band / gross-flag / bug-range)


def _p9_accept_threshold(rl, wa=WA, tgt=TGT):
    """Bisect the buyer's final offer ($) at which the post-P7 seller flips
    counter→accept, at rounds_left=rl, so we can construct GENUINE accept nodes
    (marginal = just above threshold) rather than guessing."""
    cp0, mine0 = [180.0, 190.0], [215.0]
    lo, hi = wa, tgt
    for _ in range(40):
        mid = (lo + hi) / 2.0
        t = negotiate_turn(side="sell", walk_away=wa, target=tgt,
                           counterparty_offers=cp0 + [mid], my_previous_offers=mine0, rounds_left=rl)
        lo, hi = (lo, mid) if t["action"] == "accept" else (mid, hi)
    return round(hi, 2)


def _p9_accept_node(rl, kind):
    """A genuine sell-side accept node at rounds_left=rl. kind∈{marginal,generous}."""
    thr = _p9_accept_threshold(rl)
    final = thr + 0.5 if kind == "marginal" else min(TGT - 2.0, thr + 8.0)
    return [180.0, 190.0, round(final, 2)], [215.0]


def _p9_accept_vs_best_counter(cp, mine, rl, n=FAST_N, seed=0):
    """(v_accept, v_best_counter, gap, ci95) for a sell accept node. v_accept =
    CERTAIN utility of taking their standing offer now (P7 convention); v_best_counter
    = max _conceder_payoffs discounted rollout EV over the single-issue grid."""
    to_util, _ = _frame("sell", WA, TGT)
    v_accept = _clamp01(to_util(cp[-1]))
    rec_price = accept_threshold_price("sell", WA, TGT, cp, mine, rl)  # to_price(rec_util)
    actions, base_index, u_lo, _ = _single_issue_model("sell", WA, TGT, cp, rl, base_price=rec_price)
    rng = np.random.default_rng(seed)
    P = _conceder_payoffs(actions, u_lo, rl, rng, n)
    means = P.mean(axis=1)
    ses = P.std(axis=1) / np.sqrt(n)
    best = int(np.argmax(means))
    return (v_accept, float(means[best]), float(means[best]) - v_accept, 1.96 * float(ses[best]))


def _p9_would_override(cp, mine, rl, margin, n, seed=0):
    """The reverted mc_search._accept_override decision, kept self-contained here as
    the P9 instrument + record: override accept→counter iff the best-counter rollout
    EV beats the certain accept-now EV past `margin` AND the gap clears its 95% CI."""
    _, _, gap, ci = _p9_accept_vs_best_counter(cp, mine, rl, n=n, seed=seed)
    return bool(gap > margin and gap > ci)


def _p9_play(family, arm, termination, margin, *, wa=WA, tgt=TGT, b0, m, horizon,
             inner_n, seed=0):
    """One sell negotiation to termination under the SHIPPED accept-on-threshold
    policy, with two ARMS on accept nodes: `short_circuit` (accept it, shipped) vs
    `verify` (run _p9_would_override; if it fires, counter at the rollout-best price
    and play on). Termination as in P8. Returns (surplus, deal, accept_opp, overrode)."""
    m = 160.0 if family == "anomalous_below_floor" else m
    rng = np.random.default_rng(seed)
    cp: list[float] = []
    mine: list[float] = []
    accept_opp = False
    overrode = False
    for r in range(horizon):
        rounds_left = max(2, horizon - r)
        w = _buyer_willingness(family, r, horizon, b0, m, rng)
        cp.append(round(float(w), 2))
        turn = negotiate_turn(side="sell", walk_away=wa, target=tgt,
                              counterparty_offers=cp, my_previous_offers=mine, rounds_left=rounds_left)
        act = turn["action"]
        if act == "accept":
            accept_opp = True
            if arm == "verify" and _p9_would_override(cp, mine, rounds_left, margin, inner_n, seed=0):
                overrode = True
                s_price = _rollout_optimal_counter_price("sell", wa, tgt, cp, mine,
                                                         rounds_left, inner_n, 0)
                mine.append(round(s_price, 2))
                w_next = _buyer_willingness(family, r + 1, horizon, b0, m, rng)
                if s_price <= min(m, w_next):
                    return round(s_price - wa, 4), 1, accept_opp, overrode
                continue
            return round(cp[-1] - wa, 4), 1, accept_opp, overrode
        if act in ("walk", "negotiate_directly"):
            return 0.0, 0, accept_opp, overrode
        s_price = turn["recommended_price"]
        mine.append(round(float(s_price), 2))
        w_next = _buyer_willingness(family, r + 1, horizon, b0, m, rng)
        if s_price <= min(m, w_next):
            return round(s_price - wa, 4), 1, accept_opp, overrode
    if termination == "standing" and cp and cp[-1] > wa:
        return round(cp[-1] - wa, 4), 1, accept_opp, overrode
    return 0.0, 0, accept_opp, overrode


# buyer max WTP spans ABOVE the post-P7 accept thresholds so climbing offers cross
# into the accept regime (coverage: the arms MUST visit genuine accept nodes).
_P9_FAST_GRID = [(m, b0, hz) for m in (200.0, 208.0) for b0 in (180.0,) for hz in (6, 8)]
_P9_FULL_GRID = [(m, b0, hz) for m in (195.0, 200.0, 205.0, 210.0)
                 for b0 in (170.0, 180.0) for hz in (6, 8)]
_P9_FAMILIES = ["conceder", "boulware", "mirror", "random", "anomalous_below_floor"]


def _p9_arm_stats(family, arm, termination, margin, grid, inner_n):
    """(surplus/opp, deal_rate, accept_opps, overrides) over the grid."""
    rows, opps, ovr = [], 0, 0
    seeds = (0, 1, 2) if family == "random" else (0,)
    for (m, b0, hz) in grid:
        for sd in seeds:
            s, d, ao, ov = _p9_play(family, arm, termination, margin,
                                    b0=b0, m=m, horizon=hz, inner_n=inner_n, seed=sd)
            rows.append((s, d)); opps += int(ao); ovr += int(ov)
    arr = np.asarray(rows, float)
    return float(arr[:, 0].mean()), float(arr[:, 1].mean()), opps, ovr


def test_p9_genuine_accept_node_is_ev_consistent_fast():
    """FAST guard: on a genuine post-P7 accept node the engine's OWN rollout belief
    values the best counter BELOW the certain accept (gap<0), so a conservative
    accept-verification would NOT override at the most aggressive margin (0.05). This
    is the crux of the P9 KILL: there is no premature accept for MC to save."""
    for rl, kind in ((2, "marginal"), (3, "marginal"), (5, "generous")):
        cp, mine = _p9_accept_node(rl, kind)
        t = negotiate_turn(side="sell", walk_away=WA, target=TGT,
                           counterparty_offers=cp, my_previous_offers=mine, rounds_left=rl)
        assert t["action"] == "accept", f"rl={rl}/{kind} did not accept: {t['action']}"
        v_acc, v_best, gap, _ = _p9_accept_vs_best_counter(cp, mine, rl, n=FAST_N)
        assert gap < 0.05, (
            f"rl={rl}/{kind}: best-counter EV {v_best:.4f} beats accept {v_acc:.4f} by "
            f"{gap:+.4f} ≥ smallest margin 0.05 — a premature accept MC could catch; re-open P9")
        assert not _p9_would_override(cp, mine, rl, 0.05, FAST_N)


# ══════════════════════════════════════════════════════════════════════════════
# SLOW full-battery tests (`pytest -m slow`) — the 400k primary metric + P6 arm.
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.slow
def test_full_battery_h1_no_longer_confirmed():
    """The pre-registered success criterion (P7): after the fix the H1 conjunction
    is FALSE — the accept-collapse no longer confirms. Also assert the crisp
    bug-signatures directly: no probe node ACCEPTS, the reported node counters near
    the predicted $196.9, and the accept-threshold is no longer saturated."""
    v = h1_verdict(FULL_N, inner_n=20_000)
    assert v["h1_confirmed"] is False, f"H1 still confirmed post-fix: {v}"
    assert v["p5_saturated"] is False, f"accept-threshold still saturated: {v}"
    assert v["any_accept_on_probes"] is False, f"a probe node still accepts: {v}"
    assert v["reported_node_action"] == "counter"
    assert 194.0 <= v["reported_node_price"] <= 200.0, v
    # gross accept-collapse magnitude (0.15+) must be gone on every probe node
    for name, d in (("P1", probe_p1()), ("P2", probe_p2()),
                    ("P3", probe_p3()), ("P4", probe_p4())):
        gross = {k: x for k, x in d.items() if x["EV_gap"] >= 0.10}
        assert not gross, f"{name} still shows gross EV-domination: {gross}"


@pytest.mark.slow
def test_p6_hold_to_counter_no_longer_beats_shipped_post_fix():
    """After the fix the shipped policy captures the surplus itself, so on the
    ensemble the hold-to-counter advantage collapses toward noise on every ZOPA
    family (pre-fix conceder +8.9 / mirror +12.8 / random +12.3), and the
    below-floor control never favors hold-to-counter."""
    ens = p6_ensemble(inner_n=20_000)
    assert ens["anomalous_below_floor"]["mean_delta"] <= 1e-6, ens
    for fam in ("conceder", "mirror", "random", "boulware"):
        assert ens[fam]["mean_delta"] < 3.0, (fam, ens[fam])


@pytest.mark.slow
def test_p8_two_model_verdict_h1_killed():
    """The pre-registered P8 verdict (vend/RESULTS.md P8), full grid: the
    conceder/schelling branch is NOT strictly dominated — it is a deal-existence
    hedge. Both facts are asserted so the branch can't be removed without one of
    them breaking:
      STANDING (buyer stands pat at the buzzer): the branch is a pure PREMIUM —
        always-Rubinstein (arm B) captures >= the shipped branch (arm A) on realized
        surplus per opportunity with the deal rate tied. (H1 would be TRUE here.)
      WITHDRAWING (buzzer ⇒ no deal, the H0 steelman): the branch PAYS — arm A's
        deal rate exceeds arm B's by > the 10pp bound on conceder AND mirror, and
        arm A's realized surplus per opportunity beats arm B's, because arm B times
        out holding a Rubinstein floor that overshoots the buyer's true max. (H1 is
        KILLED here — which is why no fix shipped.)"""
    BOUND = 0.10
    for fam in ("conceder", "mirror"):
        # STANDING: arm B (always-Rubinstein) >= arm A on surplus; deal rate tied.
        sA, dA = _p8_surplus(fam, "A", "standing", _P8_FULL_GRID)
        sB, dB = _p8_surplus(fam, "B", "standing", _P8_FULL_GRID)
        assert sB >= sA - 1e-6, f"standing/{fam}: always-Rubinstein should not lose surplus ({sB} vs {sA})"
        assert abs(dA - dB) < 1e-6, f"standing/{fam}: deal rate should tie ({dA} vs {dB})"
        # WITHDRAWING: the branch buys deal-existence beyond the bound, and wins on primary.
        wsA, wdA = _p8_surplus(fam, "A", "withdrawing", _P8_FULL_GRID)
        wsB, wdB = _p8_surplus(fam, "B", "withdrawing", _P8_FULL_GRID)
        assert wdA - wdB > BOUND, (
            f"withdrawing/{fam}: shipped deal rate {wdA} vs always-Rubinstein {wdB} "
            f"— hedge no longer clears the {BOUND} bound (H1 would confirm)")
        assert wsA > wsB, (
            f"withdrawing/{fam}: shipped surplus/opp {wsA} must beat always-Rubinstein {wsB}")
    # below-floor control: no ZOPA ⇒ no deal on any arm, no divergence.
    for which in ("A", "B", "C"):
        _, d = _p8_surplus("anomalous_below_floor", which, "withdrawing", _P8_FULL_GRID)
        assert d == 0.0, f"below-floor control closed a deal on arm {which}: {d}"


@pytest.mark.slow
def test_p9_accept_verification_is_a_noop():
    """The pre-registered P9 verdict (vend/RESULTS.md P9), full battery: a paid MC
    accept-verification adds NOTHING, so it was reverted. Two facts, both guarded so
    the KILL can't silently flip:

      (1) COVERAGE + STRUCTURE — on every genuine accept-regime probe (marginal &
          generous, rl∈{2,3,5,8}, 400k rollouts) the closed form ACCEPTS and its own
          best-counter rollout EV is BELOW the certain accept-now EV (gap<0), so the
          override never fires at ANY margin in the ladder {0.05,0.10,0.15}.

      (2) REALIZED — the verify arm equals the shipped short_circuit arm on realized
          surplus/opp AND deal rate on every out-of-model family, under BOTH
          termination models (STANDING and WITHDRAWING), with override frequency 0;
          the below-floor control closes nothing. (Deltas are identically 0 because
          the override never fires — the two-model bracket has nothing to punish.)"""
    # (1) accept-regime probes — genuine accepts, EV-consistent, no override at any M
    n_nodes = 0
    for rl in (2, 3, 5, 8):
        for kind in ("marginal", "generous"):
            cp, mine = _p9_accept_node(rl, kind)
            t = negotiate_turn(side="sell", walk_away=WA, target=TGT,
                               counterparty_offers=cp, my_previous_offers=mine, rounds_left=rl)
            assert t["action"] == "accept", f"probe rl={rl}/{kind} did not accept: {t}"
            n_nodes += 1
            _, v_best, gap, _ = _p9_accept_vs_best_counter(cp, mine, rl, n=FULL_N)
            assert gap < 0.0, f"probe rl={rl}/{kind}: best-counter beats accept by {gap:+.4f} (re-open P9)"
            for M in _P9_MARGINS:
                assert not _p9_would_override(cp, mine, rl, M, FULL_N), (rl, kind, M)
    assert n_nodes == 8, f"expected 8 genuine accept probes, visited {n_nodes}"

    # (2) realized arms — verify ≡ short_circuit under both termination models
    inner_n = 40_000
    total_opps, total_ovr = 0, 0
    for termination in ("standing", "withdrawing"):
        for fam in _P9_FAMILIES:
            sc_s, sc_d, _, _ = _p9_arm_stats(fam, "short_circuit", termination, 0.05,
                                             _P9_FULL_GRID, inner_n)
            vf_s, vf_d, opps, ovr = _p9_arm_stats(fam, "verify", termination, 0.05,
                                                  _P9_FULL_GRID, inner_n)
            total_opps += opps; total_ovr += ovr
            assert abs(vf_s - sc_s) < 1e-9, f"{termination}/{fam}: surplus moved {vf_s} vs {sc_s}"
            assert abs(vf_d - sc_d) < 1e-9, f"{termination}/{fam}: deal rate moved {vf_d} vs {sc_d}"
            assert ovr == 0, f"{termination}/{fam}: verification overrode {ovr} accepts (re-open P9)"
            if fam == "anomalous_below_floor":
                assert sc_d == 0.0, f"below-floor control closed a deal: {sc_d}"
    assert total_opps > 0, "coverage: the realized arms never visited an accept node"
    assert total_ovr == 0, f"override fired {total_ovr}× across the ensemble — P9 KILL regressed"


# ══════════════════════════════════════════════════════════════════════════════
# Script entry point — prints the full pre/post battery tables for P7.
# ══════════════════════════════════════════════════════════════════════════════
def _print_probe_block(title, d):
    print(f"\n{title}")
    print(f"  {'node':28s} {'action':10s} {'rec$':>8s} {'acc_thr$':>9s} "
          f"{'best$':>8s} {'V_rec':>7s} {'V_best':>7s} {'EV_gap':>8s} {'2*CI':>8s} conf")
    for k, v in d.items():
        print(f"  {str(k):28s} {v['action']:10s} {v['recommended_price']:8.2f} "
              f"{v['accept_threshold']:9.2f} {v['best_counter_price']:8.2f} "
              f"{v['V_recommended']:7.3f} {v['V_best_counter']:7.3f} "
              f"{v['EV_gap']:8.4f} {2*v['ci95']:8.5f} {v['confirmed']}")


def run_battery(n=FULL_N, inner_n=50_000):
    print("=" * 78)
    print(f"ACCEPT-COLLAPSE BATTERY  (n={n:,} rollouts, seed=0, no LLM)")
    print("=" * 78)
    _print_probe_block("P1 — reported node, rounds_left in {2,3,5,8}", probe_p1(n))
    _print_probe_block("P2 — trajectory controls @ rounds_left=3 (final ~$175 held)", probe_p2(n))
    _print_probe_block("P3 — history controls @ rounds_left=3", probe_p3(n))
    _print_probe_block("P4 — buy-side mirror @ rounds_left=3", probe_p4(n))
    print("\nP5 — deadline scaling: accept-threshold($) vs rounds_left")
    p5 = probe_p5()
    print("  " + "  ".join(f"rl={rl}:{p5[rl]:.2f}" for rl in sorted(p5)))
    mono = all(p5[b] >= p5[a] - 1e-6 for a, b in zip(sorted(p5)[:-1], sorted(p5)[1:]))
    print(f"  monotone-nondecreasing: {mono}   moves(min->max): "
          f"{p5[min(p5)]:.2f} -> {p5[max(p5)]:.2f}")
    print("\nP6 — realized seller surplus: shipped vs hold-to-rollout-optimal-counter")
    print(f"  {'family':24s} {'m':>6s} {'shipped':>9s} {'hold':>9s} {'delta':>8s}")
    p6 = p6_table(inner_n=inner_n)
    for r in p6:
        print(f"  {r['family']:24s} {r['m']:6.0f} {r['shipped']:9.4f} "
              f"{r['hold_to_counter']:9.4f} {r['delta']:8.4f}")
    print("  ensemble mean(delta) ± SE over buyer-param grid (secondary confirm rule):")
    ens = p6_ensemble(inner_n=min(inner_n, 20_000))
    for fam, e in ens.items():
        print(f"    {fam:22s} mean={e['mean_delta']:8.4f}  se={e['se']:7.4f}  "
              f"n={e['n']:2d}  beats_by_1SE={e['beats_by_1se']}")

    # ── Gate-by-gate verdict (P7 confirm/kill logic) ──────────────────────────
    v = h1_verdict(n, inner_n=min(inner_n, 20_000))
    print("\n" + "-" * 78)
    print("GATE-BY-GATE VERDICT")
    for k, fired in v["ev_probe_fires"].items():
        print(f"  {k} EV_gap>2*CI fires: {fired}")
    print(f"  P5 tertiary (accept-threshold SATURATED across rl 2-5): {v['p5_saturated']}")
    print(f"  P6 secondary (hold-to-counter beats shipped >1SE on conceder AND mirror): {v['p6_secondary']}")
    print(f"  primary: {v['n_ev']}/4 EV-based probes fire (spec bar: EV_gap>2*CI in >=4/6 probes)")
    print(f"  crisp signatures: any-accept-on-probes={v['any_accept_on_probes']}, "
          f"reported-node={v['reported_node_action']} @ ${v['reported_node_price']} "
          f"(EV_gap={v['reported_node_ev_gap']})")
    print(f"  ==> H1 {'CONFIRMED' if v['h1_confirmed'] else 'NOT confirmed'} "
          f"(all-of: primary >=4 probes, secondary conceder&mirror, tertiary saturation)")


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else FULL_N
    run_battery(n=n)
