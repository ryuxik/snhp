"""arena/gauntlet/pool.py — the counterparty POOL, exactly as frozen in
PREREG-pool.md (2026-07-18). Do not tune anything here without a NEW
registration: the parameters below are load-bearing pre-registered constants,
and "if these parameters make separation trivial or impossible, that is the
result."

The pool (3 scripted counterparties, all deterministic given the view — no RNG):

  NAIVE     — the existing arena.gauntlet.agents.NaiveSeat (split-the-difference).
  HARDBALL  — proposes its own-best package (argmax own true-weight utility over
              the scenario's package space) every turn; accepts an opponent
              package iff own true-weight utility >= 0.65; never walks before
              the deadline (timeout realizes BATNA).
  CONCEDER  — proposes packages descending from its own-best in ~0.15
              own-utility steps per turn (nearest feasible package); accepts an
              opponent package iff own utility >= 0.45, or on either of the
              last two turns iff >= its BATNA.

Utilities mirror how EngineSeat/NaiveSeat compute them: a package's own
true-weight utility is agents._package_utility (sum over issues of
weight x my_utility[option]); the package space is the product of each issue's
options (separable, so the per-issue argmax IS the global argmax — we still
enumerate the space, per the registration's wording, with deterministic
tie-breaks).

`run_pool_match` mirrors arena.gauntlet.protocol.run_match SEMANTICS exactly
(alternating offers, seller opens, accept adopts the opponent's latest package
verbatim, deadline -> both BATNA, frontier scoring via the same helpers) but
takes a PLUGGABLE counterparty seat instead of the hardcoded EngineSeat.
run_match itself is untouched. In the returned MatchResult, `u_engine` holds
the COUNTERPARTY's utility and `walked_by` uses "counterparty" for the pool
side (the field names come from the shared dataclass).
"""
from __future__ import annotations

import itertools

import numpy as np

from arena.scenarios import BundleScenario, bundle_frontier
from arena.gauntlet.agents import (
    Action, BATNA, NaiveSeat, SeatView, _package_utility, engine_advice,
)
from arena.gauntlet.protocol import (
    DEADLINE, MatchResult, _issues_for, _true_utility,
)
from gametheory.negotiation.frontier import deal_metrics

# ── FROZEN pool parameters (PREREG-pool.md — do not tune) ───────────────────
HARDBALL_ACCEPT = 0.65     # accept iff own true-weight utility >= this
CONCEDER_ACCEPT = 0.45     # accept iff own utility >= this ...
CONCEDER_STEP = 0.15       # ... concede ~this much own-utility per own turn
_EPS = 1e-9


# ── package-space enumeration (deterministic) ───────────────────────────────
def _package_space(view: SeatView) -> list:
    """Every package as (own_utility, idx_tuple, package_dict), enumerated in
    lexicographic option-index order — a stable, deterministic ordering."""
    out = []
    ranges = [range(len(iss["options"])) for iss in view.issues]
    for idx in itertools.product(*ranges):
        pkg = {iss["name"]: iss["options"][i]
               for iss, i in zip(view.issues, idx)}
        out.append((_package_utility(view, pkg), idx, pkg))
    return out


def _own_best_package(view: SeatView) -> dict:
    """argmax own true-weight utility over the package space; ties broken to
    the lexicographically smallest option-index tuple (deterministic)."""
    space = _package_space(view)
    best = min(space, key=lambda t: (-t[0], t[1]))
    return dict(best[2])


# ── the pool seats ──────────────────────────────────────────────────────────
class HardballSeat:
    """PREREG HARDBALL: own-best every turn; accept iff own utility >= 0.65;
    never walks (a timeout realizes BATNA for both)."""
    name = "hardball"

    def act(self, view: SeatView) -> Action:
        if view.opp_offers and _package_utility(
                view, view.opp_offers[-1]) >= HARDBALL_ACCEPT - _EPS:
            return Action("accept")
        return Action("offer", _own_best_package(view))


class ConcederSeat:
    """PREREG CONCEDER: on its k-th own turn (k = view.turn // 2, 0-based)
    proposes the feasible package NEAREST to own-best utility minus 0.15*k
    (ties: higher utility, then lexicographic index); accepts iff own utility
    >= 0.45, or on either of the last two turns iff >= BATNA."""
    name = "conceder"

    def act(self, view: SeatView) -> Action:
        if view.opp_offers:
            u = _package_utility(view, view.opp_offers[-1])
            endgame = view.turn >= view.deadline - 2
            if u >= CONCEDER_ACCEPT - _EPS or (endgame and u >= BATNA - _EPS):
                return Action("accept")
        space = _package_space(view)
        u_best = max(t[0] for t in space)
        k = view.turn // 2                       # my own turn count so far
        target = u_best - CONCEDER_STEP * k
        pick = min(space, key=lambda t: (abs(t[0] - target), -t[0], t[1]))
        return Action("offer", dict(pick[2]))


def make_pool_seat(name: str):
    """Counterparty factory. All three are stateless + deterministic."""
    if name == "naive":
        return NaiveSeat()
    if name == "hardball":
        return HardballSeat()
    if name == "conceder":
        return ConcederSeat()
    raise ValueError(f"unknown pool member {name!r} (naive|hardball|conceder)")


POOL_MEMBERS = ("naive", "hardball", "conceder")

# FROZEN parameter export — recorded inside gauntlet-cert/3 certificates so a
# verifier sees exactly which pool the claim is against.
POOL_PARAMETERS = {
    "hardball_accept": HARDBALL_ACCEPT,
    "conceder_accept": CONCEDER_ACCEPT,
    "conceder_step": CONCEDER_STEP,
    "batna": BATNA,
}


def pool_match_seed(seed: int, sid: int, role: str, cp: str) -> int:
    """Deterministic per-match seed for engine/champion candidates in pool
    matches (the pool seats and NaiveSeat use no RNG). Domain-tagged 'pool:'
    so pool runs never collide with leaderboard runs. ONE recipe shared by
    pool_experiment and certify."""
    import hashlib
    h = hashlib.blake2b(f"pool:{seed}:{sid}:{role}:{cp}".encode(),
                        digest_size=8).digest()
    return int.from_bytes(h, "big") & 0x7FFFFFFF


# ── the pool match runner (run_match semantics, pluggable counterparty) ─────
def run_pool_match(candidate, counterparty, sc: BundleScenario, w_seller,
                   w_buyer, *, role: str, condition: str, scenario_id: int,
                   deadline: int = DEADLINE, advised: bool = False,
                   advice_seed: int | None = None) -> MatchResult:
    """One candidate-vs-pool-member match, scored against the frontier oracle —
    the exact semantics of protocol.run_match (seller opens, alternating,
    accept adopts the latest opposing package verbatim, deadline -> both take
    BATNA, TRUE-weight scoring) with the counterparty seat injected.

    `advised=True` injects the SNHP engine's recommendation into the candidate's
    view on each of its turns — the same `engine_advice(view, seed)` call and
    the same `followed_advice` accounting run_match uses, so the advised arm is
    the pool analogue of the original protocol's advised condition."""
    names = [name for name, _ in sc.issues]
    w_s = {n: float(w) for n, w in zip(names, w_seller)}
    w_b = {n: float(w) for n, w in zip(names, w_buyer)}
    cand_role, cp_role = role, ("buyer" if role == "seller" else "seller")
    cand_issues = _issues_for(sc, cand_role)
    cp_issues = _issues_for(sc, cp_role)
    cand_w = w_s if cand_role == "seller" else w_b
    cp_w = w_s if cp_role == "seller" else w_b

    offers = {"seller": [], "buyer": []}
    close_pkg, walked_by = None, None
    advice_hits, advice_turns = 0, 0
    fmt_before = getattr(candidate, "format_failures", 0)
    transcript = []

    turn = 0
    while turn < deadline and close_pkg is None and walked_by is None:
        actor_role = "seller" if turn % 2 == 0 else "buyer"
        is_cand = actor_role == cand_role
        view = SeatView(
            role=actor_role,
            issues=cand_issues if is_cand else cp_issues,
            weights=cand_w if is_cand else cp_w,
            my_offers=list(offers[actor_role]),
            opp_offers=list(offers["seller" if actor_role == "buyer" else "buyer"]),
            turn=turn, deadline=deadline,
        )
        if is_cand and advised:
            # same call + seed-offset convention as protocol.run_match
            view.advisor = engine_advice(view, (advice_seed or 0) + 7919)
        act: Action = (candidate if is_cand else counterparty).act(view)
        if is_cand and advised:
            advice_turns += 1
            if act.meta.get("followed_advice"):
                advice_hits += 1
        opp_key = "seller" if actor_role == "buyer" else "buyer"
        who = "cand" if is_cand else "pool"
        if act.kind == "accept" and offers[opp_key]:
            close_pkg = offers[opp_key][-1]
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "accept", "pkg": dict(close_pkg)})
        elif act.kind == "walk":
            walked_by = "candidate" if is_cand else "counterparty"
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "walk", "pkg": None})
        elif act.kind == "offer" and act.package:
            offers[actor_role].append(dict(act.package))
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "offer", "pkg": dict(act.package)})
        else:                                   # illegal accept with no offer etc.
            walked_by = "candidate" if is_cand else "counterparty"
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "walk", "pkg": None})
        turn += 1

    # score on TRUE weights; the oracle is always (w_seller, w_buyer) framed
    best, naive = bundle_frontier(sc, w_seller, w_buyer)
    if close_pkg is not None:
        s_issues = _issues_for(sc, "seller")
        b_issues = _issues_for(sc, "buyer")
        u_s = _true_utility(s_issues, w_s, close_pkg)
        u_b = _true_utility(b_issues, w_b, close_pkg)
    else:
        u_s = u_b = BATNA
        if walked_by is None:
            walked_by = "timeout"
    u_cand = u_s if cand_role == "seller" else u_b
    u_cp = u_b if cand_role == "seller" else u_s
    joint = u_s + u_b
    met = deal_metrics(joint, best, naive)   # the ONE shared metric implementation

    return MatchResult(
        scenario_id=scenario_id, role=cand_role, condition=condition,
        deal=close_pkg is not None, walked_by=walked_by, rounds=turn,
        package=close_pkg, u_candidate=float(u_cand), u_engine=float(u_cp),
        joint=float(joint), frontier_best=float(best), frontier_naive=float(naive),
        capture=met["capture"],
        logroll=met["logroll"],
        dollars_left=met["dollars_left"],
        followed_advice=(advice_hits / advice_turns) if advice_turns else None,
        format_failures=getattr(candidate, "format_failures", 0) - fmt_before,
        transcript=transcript,
    )
