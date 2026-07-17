"""The negotiation arms (SPEC.md §8) — all LLM-free, all seeded.

ARM-I  item-by-item sequential, cash equalization allowed PER ITEM (forbidding
       side payments here while allowing them in the bundle would be a strawman
       — the deadlock must emerge from values exceeding feasible fragmented
       cash, not from protocol asymmetry).
ARM-O  oracle bundle: true utilities -> Pareto frontier -> classical Nash point
       (both BATNAs true) -> continuous cash post-pass on the wallet. The
       measurement ceiling; never shown as product.

ARM-B (elicited posteriors) lands in step 2 with divorce/elicit.py.

Acceptance is a utility RULE with seeded noise — LLM goodwill cannot dissolve
the conflict here by construction (SPEC.md §8.3).
"""
from __future__ import annotations

import copy
import itertools

import numpy as np

from snhp.nash_solver import filter_pareto_frontier, find_nash_bargaining_solution

from divorce.personas import ASSETS, WALLET_VALUE, Persona

# ARM-I protocol constants (part of the registration; freeze with SPEC.md §8).
EXCHANGE_BUDGET = 40          # R: total exchanges across all assets
WALLET_SPLIT_EXCHANGES = 2    # splitting the cash 50/50 costs a token exchange each
OPEN_DEMAND = 0.9             # proposer's opening demand, as a fraction of stake
DEMAND_DECAY = 0.65           # per own proposal
DEMAND_FLOOR = 0.05           # below this the proposer has conceded to ~court
ACCEPT_NOISE_SD = 150.0       # $ sd of seeded noise on the acceptance threshold
TRANSFER_STEP = 500.0         # cash offer granularity


# ─── Outcome space (shared by the bundle arms) ──────────────────────────────

def enumerate_outcomes() -> list[dict[str, float]]:
    """Every combination of asset options, as side-A share dicts (1,320 rows)."""
    grids = [a["shares_a"] for a in ASSETS]
    names = [a["name"] for a in ASSETS]
    return [dict(zip(names, combo)) for combo in itertools.product(*grids)]


def _flip(shares_a: dict[str, float]) -> dict[str, float]:
    return {a: 1.0 - s for a, s in shares_a.items()}


def outcome_utilities(pa: Persona, pb: Persona,
                      outcomes: list[dict[str, float]]) -> tuple[np.ndarray, np.ndarray]:
    u_a = np.array([pa.utility(o) for o in outcomes])
    u_b = np.array([pb.utility(_flip(o)) for o in outcomes])
    return u_a, u_b


# ─── ARM-O: oracle bundle ───────────────────────────────────────────────────

def refine_wallet_generic(alpha_a: float, alpha_b: float, lam_a: float,
                          lam_b: float, walk_a: float, walk_b: float) -> float:
    """Continuous cash post-pass (SPEC.md §5): with utilities linear in the
    wallet share s, the Nash product is a concave quadratic in s — closed-form
    vertex, clipped to [0,1]. alpha_a/alpha_b = each side's utility at s = 0
    (side B holding all cash). Parameterized so the mediator can run it on
    ELICITED estimates without ever holding a Persona (SPEC.md §4.ii)."""
    beta_a = WALLET_VALUE * (1.0 + lam_a)         # du_A/ds
    beta_b = WALLET_VALUE * (1.0 + lam_b)         # -du_B/ds
    s = (beta_a * (alpha_b - walk_b) - beta_b * (alpha_a - walk_a)) \
        / (2.0 * beta_a * beta_b)
    return float(np.clip(s, 0.0, 1.0))


def _refine_wallet(pa: Persona, pb: Persona, shares_a: dict[str, float]) -> dict[str, float]:
    base = dict(shares_a, wallet=0.0)
    s = refine_wallet_generic(pa.utility(base), pb.utility(_flip(base)),
                              pa.lam, pb.lam, pa.walk_away, pb.walk_away)
    return dict(shares_a, wallet=s)


def run_arm_o(pa: Persona, pb: Persona,
              outcomes: list[dict[str, float]] | None = None) -> dict:
    """True utilities -> frontier -> classical Nash point -> cash post-pass.
    Returns settled=False (NO DECREE) when no outcome clears both BATNAs."""
    outcomes = outcomes if outcomes is not None else enumerate_outcomes()
    u_a, u_b = outcome_utilities(pa, pb, outcomes)
    pareto = filter_pareto_frontier(None, u_a, u_b)
    best = find_nash_bargaining_solution(pareto, u_a, u_b, pa.walk_away, pb.walk_away)
    if best is None:
        return {"settled": False, "shares_a": None,
                "u_a": pa.walk_away, "u_b": pb.walk_away, "joint_surplus": 0.0,
                "ir_a": True, "ir_b": True, "ef_a": None, "ef_b": None}
    shares_a = _refine_wallet(pa, pb, outcomes[best])
    fa, fb = pa.utility(shares_a), pb.utility(_flip(shares_a))
    return {
        "settled": True, "shares_a": shares_a, "u_a": fa, "u_b": fb,
        "joint_surplus": (fa - pa.walk_away) + (fb - pb.walk_away),
        "ir_a": bool(fa >= pa.walk_away), "ir_b": bool(fb >= pb.walk_away),
        # EF on possession values, spite excluded (SPEC.md §6): do I value my
        # pile at least as much as I value theirs?
        "ef_a": bool(pa.possession_value(shares_a)
                     >= pa.possession_value(_flip(shares_a))),
        "ef_b": bool(pb.possession_value(_flip(shares_a))
                     >= pb.possession_value(shares_a)),
    }


# ─── ARM-I: item-by-item sequential ─────────────────────────────────────────
#
# Per-item delta convention: settling one item at share s (vs its 0.5 court
# expectation) with signed transfer t (positive = I pay) is worth
#     delta = (1 + lam) * ((s - 0.5) * v - t)
# — both the asset term and the transfer factor by (1 + lam), because a dollar
# to the ex both leaves my pocket and lands in theirs (spite).

def _propose(p: Persona, asset: dict, my_budget: float, their_budget: float,
             demand: float):
    """Proposer p's offer at concession level `demand`: target own delta of
    demand * stake, hit it by adjusting the cash leg per allocation option,
    clip to what each side can actually pay. p knows NOTHING about the other
    side's values — concession means lowering p's own take, not modeling the
    opponent. Returns (option_index, signed_transfer, delta_p)."""
    v = p.values[asset["name"]]
    stake = 0.5 * v * (1.0 + p.lam)               # p's max conceivable item gain
    target = demand * stake
    a_side = p.side == "A"

    best = None
    for opt_idx, s_a in enumerate(asset["shares_a"]):
        share = s_a if a_side else 1.0 - s_a
        raw = (share - 0.5) * v - target / (1.0 + p.lam)  # exact-target transfer
        raw = float(np.clip(raw, -their_budget, my_budget))
        # Snap to the cash grid on BOTH sides of the target: rounding one way
        # can cross the self-harm line, but the floored full-share candidate
        # always survives, so at least one proposal exists.
        for t in {np.floor(raw / TRANSFER_STEP) * TRANSFER_STEP,
                  np.ceil(raw / TRANSFER_STEP) * TRANSFER_STEP}:
            t = float(np.clip(t, -their_budget, my_budget))
            delta = (1.0 + p.lam) * ((share - 0.5) * v - t)
            if delta < 0:
                continue                          # never propose self-harm
            # Closest to the concession target; tie-break toward taking the
            # asset ("I keep the dog, here's $X" — the demo's offer shape).
            key = (abs(delta - target), -share)
            if best is None or key < best[0]:
                best = (key, opt_idx, t, delta)
    assert best is not None  # floored t at share >= 0.5 is always a candidate
    _, opt_idx, t, delta = best
    return opt_idx, t, delta


def run_arm_i(pa: Persona, pb: Persona, rng: np.random.Generator,
              budget: int = EXCHANGE_BUDGET, respond=None) -> dict:
    """Item-by-item: the wallet splits 50/50 first (cash is cash — and becomes
    the budget for per-item equalization), then each remaining asset gets its
    own alternating-offers mini-negotiation with per-side concession
    schedules. An item where both schedules exhaust unaccepted is abandoned
    (lawyers move on); anything unsettled at the end goes to court and BOTH
    sides pay their fight cost — going to court at all costs the retainer.

    `respond` (SPEC.md §8 trap check): optional external accept/reject decider
    with signature (responder_persona, asset_name, responder_share, cashflow,
    delta, rule_threshold) -> bool. The utility rule's verdict is still
    computed either way — the trap check grades the decider against it."""
    exchanges = budget - WALLET_SPLIT_EXCHANGES
    shares_a: dict[str, float] = {"wallet": 0.5}
    settled: dict[str, bool] = {"wallet": True}
    per_item_exchanges: dict[str, int] = {"wallet": WALLET_SPLIT_EXCHANGES}
    net_recv = {"A": 0.0, "B": 0.0}               # net cash received via deals
    exchange_log: list[dict] = []                 # the demo's Act I montage feed

    # Easiest items first — the STRONGEST reasonable item-by-item protocol
    # (biggest-first would let the dog starve the espresso machine of airtime
    # and hand K1 a strawman win). The contested monster lands last, with the
    # residual budget — which is also exactly the demo's freeze-frame beat.
    items = sorted((a for a in ASSETS if a["name"] != "wallet"),
                   key=lambda a: max(pa.values[a["name"]], pb.values[a["name"]]))
    sides = {"A": pa, "B": pb}
    # Every settled item dodges its share of the retainer: a myopic-but-sane
    # lawyer accepts small per-item losses to keep the case out of court.
    credit = {s: sides[s].fight_cost / len(items) for s in sides}

    def cash_avail(side: str) -> float:
        return max(0.0, WALLET_VALUE / 2.0 + net_recv[side])

    for asset in items:
        name = asset["name"]
        used, done = 0, False
        if exchanges > 0:
            # The side that values the item more opens (deterministic).
            turn = "A" if pa.values[name] >= pb.values[name] else "B"
            demand = {"A": OPEN_DEMAND, "B": OPEN_DEMAND}
            while exchanges > 0:
                p = sides[turn]
                other = "B" if turn == "A" else "A"
                q = sides[other]
                opt_idx, t, _ = _propose(p, asset, cash_avail(turn),
                                         cash_avail(other), demand[turn])
                exchanges -= 1
                used += 1
                s_a = asset["shares_a"][opt_idx]
                q_share = s_a if other == "A" else 1.0 - s_a
                q_cashflow = t  # positive t = proposer pays: q receives it
                delta_q = (1.0 + q.lam) * ((q_share - 0.5) * q.values[name] + q_cashflow)
                threshold = -credit[other] + rng.normal(0.0, ACCEPT_NOISE_SD)
                accepted = (delta_q >= threshold if respond is None else
                            respond(q, name, q_share, q_cashflow, delta_q, threshold))
                exchange_log.append({"asset": name, "proposer": turn,
                                     "share_a": s_a, "transfer": t,
                                     "accepted": bool(accepted)})
                if accepted:
                    shares_a[name] = s_a
                    settled[name] = True
                    net_recv[turn] -= t
                    net_recv[other] += t
                    done = True
                    break
                demand[turn] *= DEMAND_DECAY
                if demand["A"] < DEMAND_FLOOR and demand["B"] < DEMAND_FLOOR:
                    break                          # both fully conceded: deadlock
                turn = other
        if not done:
            settled[name] = False
        per_item_exchanges[name] = used

    litigating = not all(settled.get(a["name"], False) for a in ASSETS)
    for asset in ASSETS:                           # unsettled -> court expectation
        shares_a.setdefault(asset["name"], 0.5)

    def total(p: Persona, my_shares: dict[str, float]) -> float:
        # Transfers are zero-sum: my cash +T, the ex's -T => +T(1+lam) to me.
        u = p.utility(my_shares) + net_recv[p.side] * (1.0 + p.lam)
        return u - (p.fight_cost if litigating else 0.0)

    fa = total(pa, shares_a)
    fb = total(pb, _flip(shares_a))
    n_settled = sum(1 for a in ASSETS if settled.get(a["name"], False))
    return {
        "settled_fraction": n_settled / len(ASSETS),
        "fully_settled": not litigating,
        "u_a": fa, "u_b": fb,
        "joint_surplus": (fa - pa.walk_away) + (fb - pb.walk_away),
        "ir_a": bool(fa >= pa.walk_away), "ir_b": bool(fb >= pb.walk_away),
        "per_item_exchanges": per_item_exchanges,
        "unsettled": [a["name"] for a in ASSETS if not settled.get(a["name"], False)],
        "net_recv": dict(net_recv),
        "exchange_log": exchange_log,
        "shares_a": shares_a,
    }


# ─── Pettiness tax (SPEC.md §7): a real counterfactual ──────────────────────

def pettiness_tax(pa: Persona, pb: Persona,
                  outcomes: list[dict[str, float]] | None = None,
                  actual_o: dict | None = None) -> dict[str, float]:
    """Joint value each side's hill spike destroys, isolated from everything
    else: compare the ORACLE settlement under actual (spiked) preferences with
    the ORACLE settlement under that side's despiked preferences, both
    allocations valued by the despiked utilities (one measuring stick).

    Two prior definitions were bugs worth remembering: diffing surpluses-over-
    walkaway double-counts the spike (despiking lowers the court expectation
    too); and diffing against the ELICITED settlement conflates hill cost with
    the elicitation gap (hill-free personas showed thousands in "tax" that was
    really K3's ~10%). Oracle-vs-oracle isolates the spite: this tax is a
    property of the preference profile, not of mediation noise."""
    outcomes = outcomes if outcomes is not None else enumerate_outcomes()
    actual_o = actual_o if actual_o is not None else run_arm_o(pa, pb, outcomes)
    out = {}
    for label in ("a", "b"):
        p = pa if label == "a" else pb
        clone = copy.deepcopy(p)
        clone.values[clone.hill] /= clone.hill_mult
        clone.__post_init__()                      # recompute court/BATNA
        da, db = (clone, pb) if label == "a" else (pa, clone)
        cf = run_arm_o(da, db, outcomes)

        def joint_despiked(shares_a):
            return da.utility(shares_a) + db.utility(_flip(shares_a))

        if not (cf["settled"] and actual_o["settled"]):
            out[label] = 0.0
            continue
        out[label] = max(0.0, joint_despiked(cf["shares_a"])
                         - joint_despiked(actual_o["shares_a"]))
    return out
