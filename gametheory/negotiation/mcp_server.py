"""SNHP Advisor — an MCP server that gives any agent the negotiation engine.

The published pattern is "LLM talks, engine decides" (OG-Narrator '24, ASTRA
'25): language models model counterparties well but anchor and fail to logroll;
a deterministic solver computing the offers fixes it. This server exposes the
SNHP engine's validated solvers as three tools any MCP-capable agent (Claude,
or anything speaking MCP) can call mid-negotiation:

  advise_price   — single-issue dollar negotiation (negotiate_turn): what to
                   offer/accept/walk, in real dollars.
  advise_bundle  — multi-issue package negotiation (negotiate_bundle): the
                   logrolled package that beats splitting every issue.
  score_deal     — the Pareto oracle: given both sides' true weights, how much
                   of the achievable joint surplus a package captured and how
                   many dollars were left on the table (the SNHP leaderboard
                   metric, callable on your own negotiations).

Run (stdio, for Claude Code / Claude Desktop):
    python -m gametheory.negotiation.mcp_server

Register with Claude Code:
    claude mcp add snhp-advisor -- python -m gametheory.negotiation.mcp_server
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Optional

import numpy as np
from mcp.server.fastmcp import FastMCP

from gametheory.negotiation.bundle import BundleInputError, _norm01, negotiate_bundle
from gametheory.negotiation.frontier import (
    MAX_OUTCOMES as _MAX_OUTCOMES, deal_metrics, joint_frontier, norm_weights,
)
from gametheory.negotiation.plain_terms import NegotiationInputError, negotiate_turn


def _seed_from_args(*parts) -> None:
    """Deterministic advice: seed the global NumPy RNG from the call's inputs
    (the particle filter draws from it). Identical calls → identical advice."""
    blob = json.dumps(parts, sort_keys=True, default=str).encode()
    h = hashlib.blake2b(blob, digest_size=8).digest()
    np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)

mcp = FastMCP(
    "snhp-advisor",
    instructions=(
        "SNHP negotiation engine. Call advise_price (single-issue, dollars) or "
        "advise_bundle (multi-issue packages) BEFORE sending each offer in a "
        "negotiation — you speak, the engine computes the move. Call score_deal "
        "after a deal closes to measure surplus captured vs the Pareto frontier."
    ),
)


@mcp.tool()
def advise_price(
    side: str,
    walk_away: float,
    target: float,
    counterparty_offers: Optional[list[float]] = None,
    my_previous_offers: Optional[list[float]] = None,
    rounds_left: int = 8,
    item: str = "this",
) -> dict:
    """One single-issue negotiation turn, entirely in real dollars.

    Args:
        side: "sell" or "buy" — which side YOU are.
        walk_away: your reservation — the worst price you'd accept
            (seller: your floor; buyer: your ceiling).
        target: your aspiration price (seller: high; buyer: low).
        counterparty_offers: the other side's offers so far, oldest first.
        my_previous_offers: your own prior offers, oldest first.
        rounds_left: roughly how many back-and-forths remain.
        item: what's being traded (used in the drafted message).

    Returns action ("counter"|"accept"|"walk"), recommended_price, a
    ready-to-send message, rationale, expected_settlement, and confidence.
    """
    try:
        _seed_from_args("advise_price", side, walk_away, target,
                        counterparty_offers, my_previous_offers, rounds_left)
        return negotiate_turn(
            side=side, walk_away=float(walk_away), target=float(target),
            counterparty_offers=counterparty_offers,
            my_previous_offers=my_previous_offers,
            rounds_left=int(rounds_left), item=item)
    except (NegotiationInputError, ValueError, TypeError) as e:
        return {"error": str(e)}


@mcp.tool()
def advise_bundle(
    issues: list[dict],
    their_offers: Optional[list[dict]] = None,
    my_priorities: Optional[dict] = None,
    my_batna: float = 0.40,
    their_batna_estimate: float = 0.40,
    cooperation: Optional[float] = None,
) -> dict:
    """Recommend a multi-issue package by logrolling (concede where you care
    little, win where you care much — the trade that beats splitting every
    issue down the middle).

    Args:
        issues: one dict per issue: {"name": str, "options": [labels],
            "my_utility": [one number per option — how good it is for YOU, any
            scale], "their_utility": [your read of THEIR per-option direction]}.
            2+ issues required (that's what makes logrolling possible).
        their_offers: full packages the other side has proposed, oldest first,
            each {issue_name: option_label}. Omit on your opening offer.
        my_priorities: {issue_name: weight} — how much each issue matters to
            you (any scale). Omitted = all equal.
        my_batna: your walk-away utility in [0,1] (0.40 if unsure).
        their_batna_estimate: your estimate of theirs in [0,1].
        cooperation: optional [0,1] tilt — 0 adversarial Nash, 1 max joint
            welfare. Leave unset for the default.

    Returns action ("counter"|"accept"|"walk"), recommended_offer (a full
    package), the trade logic, inferred counterparty priorities, and
    acceptance probability.
    """
    try:
        _seed_from_args("advise_bundle", issues, their_offers, my_priorities,
                        my_batna, their_batna_estimate, cooperation)
        out = negotiate_bundle(
            issues=issues, their_offers=their_offers,
            my_priorities=my_priorities, my_batna=float(my_batna),
            their_batna_estimate=float(their_batna_estimate),
            cooperation=cooperation)
    except (BundleInputError, ValueError, TypeError) as e:
        return {"error": str(e)}
    if out.get("action") == "use_negotiate_turn":
        # route to THIS server's tool name, not the engine's internal one
        out["action"] = "use_advise_price"
        out["message"] = ("This is a single-issue negotiation — call the "
                          "advise_price tool, which speaks plain dollars.")
    return out


@mcp.tool()
def score_deal(
    issues: list[dict],
    my_weights: dict,
    their_weights: dict,
    package: dict,
    notional: float = 10_000.0,
) -> dict:
    """Score a settled package against the exact Pareto frontier — the SNHP
    leaderboard metric ("dollars left on the table") for YOUR negotiation.

    Args:
        issues: one dict per issue: {"name": str, "options": [labels],
            "my_utility": [per-option value to me], "their_utility":
            [per-option value to them]} — both sides' TRUE per-option values.
        my_weights: {issue_name: weight} — my true priorities (any scale).
        their_weights: {issue_name: weight} — their true priorities.
        package: the settled deal, {issue_name: option_label}.
        notional: deal size in dollars for the dollars-left framing.

    Returns realized joint welfare, the frontier best, the naive middle-split
    baseline, frontier capture, logroll capture, and dollars_left_on_table.
    """
    # validate before touching anything — a tool must return {"error": ...},
    # never a raw exception, and never enumerate an unbounded outcome space
    for iss in issues:
        missing = [k for k in ("name", "options", "my_utility", "their_utility")
                   if not isinstance(iss, dict) or iss.get(k) is None]
        if missing:
            return {"error": f"each issue needs name/options/my_utility/"
                             f"their_utility; one is missing {missing}"}
        if not (len(iss["options"]) == len(iss["my_utility"]) == len(iss["their_utility"])):
            return {"error": f"issue {iss['name']!r}: options/my_utility/their_utility "
                             f"must be the same length"}
    n_outcomes = math.prod(len(iss["options"]) for iss in issues) if issues else 0
    if not issues or n_outcomes > _MAX_OUTCOMES:
        return {"error": f"outcome space is {n_outcomes} combinations "
                         f"(limit {_MAX_OUTCOMES}); use fewer issues or coarser options"}
    names = [iss["name"] for iss in issues]
    opts = {iss["name"]: list(iss["options"]) for iss in issues}
    mu, tu = {}, {}
    try:
        for iss in issues:
            mu[iss["name"]] = [float(x) for x in iss["my_utility"]]
            tu[iss["name"]] = [float(x) for x in iss["their_utility"]]
    except (TypeError, ValueError) as e:
        return {"error": f"utilities must be numbers: {e}"}

    # normalize per issue with the SAME normalizer negotiate_bundle applies
    # (arena scenarios are already [0,1]-spanning, so leaderboard parity holds)
    mu_n = {n: list(_norm01(mu[n])) for n in names}
    tu_n = {n: list(_norm01(tu[n])) for n in names}
    wm = norm_weights([my_weights.get(n, 0.0) for n in names], len(names))
    wt = norm_weights([their_weights.get(n, 0.0) for n in names], len(names))

    def utilities(combo):
        u_me = sum(wm[i] * mu_n[n][combo[i]] for i, n in enumerate(names))
        u_them = sum(wt[i] * tu_n[n][combo[i]] for i, n in enumerate(names))
        return u_me, u_them

    # the shared oracle + metric — the leaderboard's exact implementation
    best, naive = joint_frontier([mu_n[n] for n in names], [tu_n[n] for n in names],
                                 wm, wt)
    try:
        chosen = tuple(opts[n].index(package[n]) for n in names)
    except (KeyError, ValueError) as e:
        return {"error": f"package must map every issue to one of its options ({e})"}
    u_me, u_them = utilities(chosen)
    joint = u_me + u_them
    met = deal_metrics(joint, best, naive, notional=float(notional))
    return {
        "my_utility": round(u_me, 4),
        "their_utility": round(u_them, 4),
        "joint_welfare": round(joint, 4),
        "frontier_best": round(best, 4),
        "naive_split": round(naive, 4),
        "frontier_capture": round(met["capture"], 4),
        "logroll_capture": (None if met["logroll"] is None
                            else round(met["logroll"], 4)),
        "dollars_left_on_table": round(met["dollars_left"], 2),
    }


if __name__ == "__main__":
    mcp.run()
