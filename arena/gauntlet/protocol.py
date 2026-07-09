"""Gauntlet match protocol + frontier scoring.

A match: one seat (the CANDIDATE — an LLM, the naive baseline, or the engine
itself) vs the standardized EngineSeat counterparty, on a seeded BundleScenario
with Dirichlet-drawn TRUE priorities per side. Alternating offers (seller opens),
accept adopts the opponent's latest package verbatim, deadline ends in no deal
(both take BATNA). Same semantics as arena.executor.run_bundle_negotiation, so
gauntlet numbers live on the arena science's own scale.

Scoring is against the scenario's Pareto oracle (arena.scenarios.bundle_frontier):

  capture      = realized joint / frontier max        (headline efficiency)
  logroll      = (joint - naive) / (best - naive)     (did they trade across
                                                       issues, or just split?)
  dollars_left = (best - joint) / best * NOTIONAL     (the shareable number)

Both sides are scored on their TRUE weights; walks/timeouts realize the two
BATNAs. `logroll` is None when the scenario has no meaningful logroll headroom
(best - naive < 0.02) — those matches still count for capture and deal rate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

from arena.config import ArenaConfig
from arena.scenarios import BundleScenario, bundle_frontier, gen_bundle_scenario
from arena.gauntlet.agents import (
    Action, BATNA, EngineSeat, SeatView, engine_advice,
)
from gametheory.negotiation.frontier import NOTIONAL, deal_metrics

DEADLINE = 8            # total alternating turns (seller opens)


@dataclass
class MatchResult:
    scenario_id: int
    role: str                   # the candidate's role
    condition: str              # "solo" | "advised" | "engine" | "naive"
    deal: bool
    walked_by: Optional[str]    # "candidate" | "engine" | "timeout" | None
    rounds: int
    package: Optional[dict]
    u_candidate: float          # true-weight utility (BATNA if no deal)
    u_engine: float
    joint: float
    frontier_best: float
    frontier_naive: float
    capture: float
    logroll: Optional[float]
    dollars_left: float
    followed_advice: Optional[float]  # advised: fraction of turns advice adopted
    format_failures: int
    transcript: list = None           # [{t, who, role, act, pkg}] — replay fuel

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 4)
        return d


def gen_gauntlet_scenarios(n: int, seed: int, n_issues: int = 4):
    """The fixed, versioned scenario set: (BundleScenario, w_seller, w_buyer)
    triples. Dirichlet(1) priorities per side — the same distribution the
    arena's science panel uses — drawn from a dedicated seeded RNG so every
    model faces the IDENTICAL gauntlet."""
    rng = np.random.default_rng(seed)
    cfg = ArenaConfig()
    out = []
    for _ in range(n):
        sc = gen_bundle_scenario(cfg, "contract", rng, n_issues=n_issues)
        w_s = rng.dirichlet(np.ones(n_issues))
        w_b = rng.dirichlet(np.ones(n_issues))
        out.append((sc, w_s, w_b))
    return out


def _issues_for(sc: BundleScenario, role: str) -> list:
    """negotiate_bundle-style issue dicts from a role's frame (mirror of
    arena.executor._bundle_issues, duplicated to keep the gauntlet importable
    without the executor's Side/Genome machinery)."""
    issues = []
    for (name, labels), dirs in zip(sc.issues, sc.seller_dirs):
        if role == "seller":
            my_u = list(dirs)
            their_u = [round(1.0 - d, 4) for d in dirs]
        else:
            my_u = [round(1.0 - d, 4) for d in dirs]
            their_u = list(dirs)
        issues.append({"name": name, "options": list(labels),
                       "my_utility": my_u, "their_utility": their_u})
    return issues


def _true_utility(issues: list, weights: dict, package: dict) -> float:
    total = 0.0
    for iss in issues:
        w = float(weights.get(iss["name"], 0.0))
        opt = package.get(iss["name"])
        idx = iss["options"].index(opt) if opt in iss["options"] else 0
        total += w * float(iss["my_utility"][idx])
    return float(total)


def run_match(candidate, sc: BundleScenario, w_seller, w_buyer, *,
              role: str, condition: str, scenario_id: int,
              match_seed: int, deadline: int = DEADLINE) -> MatchResult:
    """Play one candidate-vs-engine match and score it against the frontier."""
    names = [name for name, _ in sc.issues]
    w_s = {n: float(w) for n, w in zip(names, w_seller)}
    w_b = {n: float(w) for n, w in zip(names, w_buyer)}
    cand_role, eng_role = role, ("buyer" if role == "seller" else "seller")
    cand_issues = _issues_for(sc, cand_role)
    eng_issues = _issues_for(sc, eng_role)
    cand_w = w_s if cand_role == "seller" else w_b
    eng_w = w_s if eng_role == "seller" else w_b

    engine = EngineSeat(match_seed)
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
            issues=cand_issues if is_cand else eng_issues,
            weights=cand_w if is_cand else eng_w,
            my_offers=list(offers[actor_role]),
            opp_offers=list(offers["seller" if actor_role == "buyer" else "buyer"]),
            turn=turn, deadline=deadline,
        )
        if is_cand and condition == "advised":
            view.advisor = engine_advice(view, match_seed + 7919)
        act: Action = (candidate if is_cand else engine).act(view)
        if is_cand and condition == "advised":
            advice_turns += 1
            if act.meta.get("followed_advice"):
                advice_hits += 1
        opp_key = "seller" if actor_role == "buyer" else "buyer"
        who = "cand" if is_cand else "eng"
        if act.kind == "accept" and offers[opp_key]:
            close_pkg = offers[opp_key][-1]
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "accept", "pkg": dict(close_pkg)})
        elif act.kind == "walk":
            walked_by = "candidate" if is_cand else "engine"
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "walk", "pkg": None})
        elif act.kind == "offer" and act.package:
            offers[actor_role].append(dict(act.package))
            transcript.append({"t": turn, "who": who, "role": actor_role,
                               "act": "offer", "pkg": dict(act.package)})
        else:                                   # illegal accept with no offer etc.
            walked_by = "candidate" if is_cand else "engine"
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
    u_eng = u_b if cand_role == "seller" else u_s
    joint = u_s + u_b
    met = deal_metrics(joint, best, naive)   # the ONE shared metric implementation

    return MatchResult(
        scenario_id=scenario_id, role=cand_role, condition=condition,
        deal=close_pkg is not None, walked_by=walked_by, rounds=turn,
        package=close_pkg, u_candidate=float(u_cand), u_engine=float(u_eng),
        joint=float(joint), frontier_best=float(best), frontier_naive=float(naive),
        capture=met["capture"],
        logroll=met["logroll"],
        dollars_left=met["dollars_left"],
        followed_advice=(advice_hits / advice_turns) if advice_turns else None,
        format_failures=getattr(candidate, "format_failures", 0) - fmt_before,
        transcript=transcript,
    )


def aggregate(results: list[MatchResult]) -> dict:
    """One leaderboard row from a list of matches (single model+condition)."""
    if not results:
        return {}
    deals = [r for r in results if r.deal]
    logrolls = [r.logroll for r in results if r.logroll is not None]
    advised = [r.followed_advice for r in results if r.followed_advice is not None]
    return {
        "matches": len(results),
        "deal_rate": round(len(deals) / len(results), 4),
        "capture": round(float(np.mean([r.capture for r in results])), 4),
        "logroll": round(float(np.mean(logrolls)), 4) if logrolls else None,
        "dollars_left": round(float(np.mean([r.dollars_left for r in results])), 2),
        "own_utility": round(float(np.mean([r.u_candidate for r in results])), 4),
        "engine_utility": round(float(np.mean([r.u_engine for r in results])), 4),
        "mean_rounds": round(float(np.mean([r.rounds for r in results])), 2),
        "advice_follow": round(float(np.mean(advised)), 4) if advised else None,
        "format_failures": int(sum(r.format_failures for r in results)),
    }
