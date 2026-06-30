"""
Multi-issue negotiation (logrolling) — the agent-facing entry point.

negotiate_turn handles a single PRICE. Real B2B deals have several linked issues
at once (a job offer = base + equity + signing; a SaaS contract = price + seats +
term + SLA). The value there is LOGROLLING (Raiffa): concede on issues you care
about less and the other side cares about more, in exchange for the issues you
care about most — a trade that makes BOTH sides better off than splitting every
issue down the middle.

This module generalizes the validated SNHP logrolling engine (snhp/benchmark.py
`snhp_propose_offer_v1`, which was hardwired to one fixed 4-issue B2B template) to
ANY set of caller-defined issues. The pipeline is unchanged and reuses the same
primitives the research stack does:

  1. Build the full outcome space (every combination of the options you give).
  2. Score each outcome's utility to YOU from your per-option values + priorities.
  3. INFER the other side's per-issue priorities from the offers they've made, via
     the same BayesianParticleFilter the single-issue path uses.
  4. Score each outcome's utility to THEM under those inferred priorities.
  5. Keep the Pareto frontier; pick the Bayesian-Nash bargaining solution.
  6. Return the package to propose, the trade logic, and their inferred priorities.

Everything is in your own units/labels in and out — no game theory exposed.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from gametheory._internal import ensure_snhp_path  # noqa: F401  (side-effect import)

from bayesian_agent import BayesianParticleFilter  # noqa: E402
from nash_solver import filter_pareto_frontier, find_nash_bargaining_solution  # noqa: E402


# The Pareto filter is O(n^2); keep the outcome space sane. 4 issues x 7 options
# = 2401; a job offer (7x5x4) = 140. Real contracts live well under this.
_MAX_OUTCOMES = 4000
_N_PARTICLES = 500
_PRIOR_UNCERTAINTY = 0.2


class BundleInputError(ValueError):
    """Bad real-world inputs (e.g. mismatched option/utility lengths)."""


def _norm01(vals: list[float]) -> np.ndarray:
    """Normalize a per-option value vector to [0,1]. Flat -> all 0.5 (indifferent)."""
    a = np.asarray(vals, dtype=np.float64)
    lo, hi = a.min(), a.max()
    if hi - lo < 1e-12:
        return np.full_like(a, 0.5)
    return (a - lo) / (hi - lo)


def _validate(issues: list[dict]) -> None:
    if not issues:
        raise BundleInputError("Provide at least one issue (two+ for real logrolling).")
    for iss in issues:
        name = iss.get("name")
        opts = iss.get("options")
        mu = iss.get("my_utility")
        tu = iss.get("their_utility")
        if not name or not opts:
            raise BundleInputError(f"Each issue needs a 'name' and 'options'; got {iss!r}")
        if mu is None or tu is None:
            raise BundleInputError(
                f"Issue {name!r} needs 'my_utility' and 'their_utility' (one number per "
                f"option — how good each option is to you / to them; any scale)."
            )
        if not (len(opts) == len(mu) == len(tu)):
            raise BundleInputError(
                f"Issue {name!r}: options ({len(opts)}), my_utility ({len(mu)}), and "
                f"their_utility ({len(tu)}) must be the same length."
            )


@dataclass
class _BundleModel:
    """The full math pipeline for a bundle (shared by the closed form and the MC
    refinement). particles/probabilities expose the belief over their weights so a
    Monte-Carlo rollout can sample opponents."""
    names: list
    options: list
    my_w: np.ndarray
    my_u: list
    their_u: list
    idx_grid: np.ndarray
    my_per_dim: np.ndarray
    their_per_dim: np.ndarray
    u_self: np.ndarray
    u_opp: np.ndarray
    their_w: np.ndarray
    confidence: float
    particles: np.ndarray         # [n_particles, n_issues] — belief over their weights
    probabilities: np.ndarray     # [n_particles] — posterior weight per particle
    pareto_idx: np.ndarray
    best_idx: Optional[int]


def _build_model(issues, their_offers, my_priorities, my_batna, their_batna_estimate):
    """Build the outcome space, infer their priorities, and pick the Nash package.
    Assumes `issues` is validated and has >= 2 issues. Raises BundleInputError on a
    too-large outcome space or malformed counter-offers."""
    n_issues = len(issues)
    names = [iss["name"] for iss in issues]
    options = [list(iss["options"]) for iss in issues]
    my_u = [_norm01(iss["my_utility"]) for iss in issues]
    their_u = [_norm01(iss["their_utility"]) for iss in issues]

    if my_priorities:
        try:
            w = np.array([float(my_priorities.get(n, 0.0)) for n in names], dtype=np.float64)
        except (TypeError, ValueError):
            raise BundleInputError("my_priorities values must be numbers — a weight per issue.")
        if np.any(w < 0):
            raise BundleInputError("my_priorities weights must be non-negative.")
        if w.sum() <= 0:
            w = np.ones(n_issues)
    else:
        w = np.ones(n_issues)
    my_w = w / w.sum()

    n_outcomes = math.prod(len(o) for o in options)
    if n_outcomes > _MAX_OUTCOMES:
        raise BundleInputError(
            f"Outcome space is {n_outcomes} combinations (> {_MAX_OUTCOMES}). Reduce "
            f"the number of issues or options per issue (coarser buckets are fine).")
    idx_grid = np.array(list(itertools.product(*[range(len(o)) for o in options])), dtype=np.int32)
    my_per_dim = np.column_stack([my_u[i][idx_grid[:, i]] for i in range(n_issues)])
    their_per_dim = np.column_stack([their_u[i][idx_grid[:, i]] for i in range(n_issues)])
    u_self = my_per_dim @ my_w

    # Belief over their per-issue priorities. We always build the particle filter
    # (so MC has a prior to sample even cold) but only adopt the inferred point
    # estimate when they've actually made offers — cold-start their_w stays the
    # validated uniform default, leaving the closed-form package unchanged.
    bf = BayesianParticleFilter(
        num_variables=n_issues, num_particles=_N_PARTICLES, uncertainty=_PRIOR_UNCERTAINTY)
    if their_offers:
        for offer in their_offers:
            missing = [names[i] for i in range(n_issues) if offer.get(names[i]) is None]
            if missing:
                raise BundleInputError(
                    f"Each counterparty offer must specify every issue; this one is "
                    f"missing {missing}.")
            anchor = np.array([
                their_u[i][_option_index(options[i], offer[names[i]])]
                for i in range(n_issues)
            ], dtype=np.float64)
            bf.update_beliefs(anchor, their_per_dim)
        their_w = bf.get_inferred_weights()
        their_w = their_w / their_w.sum()
        spread = float(np.std(bf.particles, axis=0).mean())
        confidence = float(np.clip(1.0 - spread * 2.5, 0.05, 0.95))
    else:
        their_w = np.ones(n_issues) / n_issues
        confidence = 0.30

    u_opp = their_per_dim @ their_w
    pareto_idx = filter_pareto_frontier(idx_grid.astype(np.float64), u_self, u_opp)
    best_idx = find_nash_bargaining_solution(
        pareto_idx, u_self, u_opp, my_batna, their_batna_estimate, batna_b_inferred=True)

    return _BundleModel(
        names=names, options=options, my_w=my_w, my_u=my_u, their_u=their_u,
        idx_grid=idx_grid, my_per_dim=my_per_dim, their_per_dim=their_per_dim,
        u_self=u_self, u_opp=u_opp, their_w=their_w, confidence=confidence,
        particles=bf.particles, probabilities=bf.probabilities,
        pareto_idx=pareto_idx, best_idx=best_idx)


def negotiate_bundle(
    *,
    issues: list[dict],
    their_offers: Optional[list[dict]] = None,
    my_priorities: Optional[dict] = None,
    my_batna: float = 0.40,
    their_batna_estimate: float = 0.40,
) -> dict:
    """
    Recommend a multi-issue package by logrolling. See module docstring.

    issues: list of {"name", "options", "my_utility", "their_utility"} — one
        utility number per option (any scale, normalized internally). their_utility
        is your read of how the OTHER side ranks the options on that issue (their
        preference direction); their relative PRIORITY across issues is inferred.
    their_offers: list of {issue_name: option_label} the other side has put on the
        table, oldest first. Drives the priority inference. Omit on your opener.
    my_priorities: optional {issue_name: weight} — how much each issue matters to
        you (any scale, normalized). Omitted -> all issues weighted equally.

    Returns {action, recommended_offer (issue->option), message, my_utility,
    their_expected_utility, inferred_their_priorities, trade_logic, fit,
    confidence, acceptance_probability}.
    """
    _validate(issues)
    n_issues = len(issues)
    if n_issues < 2:
        return {
            "action": "use_negotiate_turn",
            "recommended_offer": None,
            "message": ("This is a single-issue negotiation — use gt_negotiate_turn, "
                        "which speaks plain dollars."),
            "my_utility": None,
            "their_expected_utility": None,
            "inferred_their_priorities": {},
            "trade_logic": "Logrolling needs 2+ issues to trade across.",
            "fit": {"score": "marginal", "reason": "single issue — use gt_negotiate_turn"},
            "confidence": 0.0,
            "acceptance_probability": None,
        }
    m = _build_model(issues, their_offers, my_priorities, my_batna, their_batna_estimate)
    names, options = m.names, m.options
    my_w, my_u, their_u = m.my_w, m.my_u, m.their_u
    idx_grid, my_per_dim = m.idx_grid, m.my_per_dim
    u_self, u_opp = m.u_self, m.u_opp
    their_w, confidence = m.their_w, m.confidence
    pareto_idx, best_idx = m.pareto_idx, m.best_idx

    inferred = {names[i]: round(float(their_w[i]), 3) for i in range(n_issues)}

    if best_idx is None or u_self[best_idx] <= my_batna:
        return {
            "action": "walk",
            "recommended_offer": None,
            "message": (
                "No package here beats your walk-away across these issues — better to "
                "walk or change the issue set."
            ),
            "my_utility": round(float(my_batna), 3),
            "their_expected_utility": None,
            "inferred_their_priorities": inferred,
            "trade_logic": "No viable trade given current positions.",
            "fit": {"score": "poor", "reason": "no package clears your walk-away"},
            "confidence": round(confidence, 3),
            "acceptance_probability": 0.10,
        }

    rec = {names[i]: options[i][int(idx_grid[best_idx, i])] for i in range(n_issues)}
    rec_u_self = float(u_self[best_idx])
    rec_u_opp = float(u_opp[best_idx])

    trade = _trade_logic(names, my_w, their_w, idx_grid[best_idx], my_per_dim[best_idx])
    accept_prob = _acceptance_probability(rec_u_opp, their_batna_estimate, confidence)

    # Accept if their latest full offer is already as good for us as our counter.
    action, accept_note = "counter", ""
    if their_offers:
        latest = their_offers[-1]
        try:
            u_latest = float(sum(
                my_w[i] * my_u[i][_option_index(options[i], latest.get(names[i]))]
                for i in range(n_issues)
            ))
            if u_latest >= rec_u_self - 0.02:
                action = "accept"
                accept_note = (
                    f"Their latest terms are already worth ~{u_latest:.2f} to you "
                    f"(about the same as countering) — take it."
                )
        except BundleInputError:
            pass

    fit = _fit(rec_u_self, my_batna, confidence)
    msg = _message(rec, trade, action, accept_note)

    return {
        "action": action,
        "recommended_offer": rec,
        "message": msg,
        "my_utility": round(rec_u_self, 3),
        "their_expected_utility": round(rec_u_opp, 3),
        "inferred_their_priorities": inferred,
        "trade_logic": trade,
        "fit": fit,
        "confidence": round(confidence, 3),
        "acceptance_probability": round(accept_prob, 3),
    }


def _option_index(opts: list, label) -> int:
    """Resolve an offered option to its index — accepts the label or an int index."""
    if label is None:
        raise BundleInputError("offer is missing a value for one of the issues")
    if label in opts:
        return opts.index(label)
    if isinstance(label, (int, np.integer)) and 0 <= int(label) < len(opts):
        return int(label)
    raise BundleInputError(f"Offered value {label!r} is not one of the options {opts}.")


def _trade_logic(names, my_w, their_w, chosen_idx, my_per_dim_row) -> str:
    """Explain the logroll: where you give (you weight low, they weight high) vs hold."""
    gap = their_w - my_w  # >0: they care more than you -> good place to concede
    give_i = int(np.argmax(gap))
    hold_i = int(np.argmax(my_w))
    if give_i == hold_i or gap[give_i] <= 0.01:
        return (
            f"Priorities are fairly aligned; the package balances all {len(names)} "
            f"issues near the efficient frontier."
        )
    return (
        f"Give ground on '{names[give_i]}' (you weight it less, they weight it most) "
        f"to hold firm on '{names[hold_i]}' (your top priority). That trade is what "
        f"makes the package beat splitting every issue down the middle."
    )


def _acceptance_probability(their_u: float, their_batna: float, confidence: float) -> float:
    """Rough P(they accept): higher when the package clears their BATNA, scaled by confidence."""
    margin = their_u - their_batna
    base = 1.0 / (1.0 + np.exp(-6.0 * margin))  # logistic around their BATNA
    return float(np.clip(0.10 + 0.85 * base * (0.5 + 0.5 * confidence), 0.02, 0.97))


def _fit(rec_u_self: float, my_batna: float, confidence: float) -> dict:
    # Single-issue is short-circuited in negotiate_turn before _fit is reached.
    if rec_u_self <= my_batna + 0.02:
        return {"score": "poor", "reason": "best package barely clears your walk-away"}
    if confidence < 0.35:
        return {"score": "marginal",
                "reason": "few/no counter-offers yet — priorities are a cold-start guess"}
    return {"score": "good", "reason": "Pareto-efficient package with a clear logroll"}


def _message(rec: dict, trade: str, action: str, accept_note: str) -> str:
    terms = ", ".join(f"{k}: {v}" for k, v in rec.items())
    if action == "accept":
        return f"Their offer works — accept it. {accept_note}".strip()
    return (
        f"Proposed package — {terms}. This is structured to work for both sides: "
        f"{trade}"
    )
