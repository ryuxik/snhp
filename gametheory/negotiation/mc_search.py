"""Spend idle compute on Monte-Carlo rollouts — the production engine.

Two tiers sit on top of this module:

  Tier 1 (here): a budget-bounded ANYTIME search. The caller passes a compute
  budget (the seconds it's about to spend blocked on its LLM or the counterparty);
  we run vectorised rollouts until that budget is spent and return the best move
  found, with a convergence signal. Two guarantees:
    * anytime — there is always a valid answer (we seed with the closed-form move);
    * never-worse-in-model — we only deviate from the closed-form when another move
      is *significantly* better under the rollout model, so noise can't make it
      pick a worse move than the closed form.

  Tier 2 (pondering.py): a stateful session that calls this engine in the
  background during the counterparty's think-time.

The rollout model here is deliberately simple (a conceder opponent with an unknown
reservation, expressed in OUR utility frame) and is a v0 to be calibrated against
the tournament — the value of this module is the anytime mechanism and the
in-model improvement guarantee, not a claim that the heuristic belief is exact.
See mc_prototype.py / mc_multi.py for the controlled measurements that motivate it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Callable, Sequence

import numpy as np

from gametheory.negotiation.plain_terms import (
    negotiate_turn as _closed_form_turn,
    _seller_frame, _buyer_frame, _clamp01, _draft,
)

# rollout hyper-parameters (the conceder model)
_DELTA = 0.92          # per-round discount
_C0 = 0.50             # opponent accepts our utility u <= u_opp_max * c(t); c rises C0 -> 1
_E_OPP = 2.5           # opponent concession exponent (Boulware)
_E_ME = 2.5            # our base continuation concession exponent


@dataclass
class SearchResult:
    action: float          # chosen action (here: our next offer, in OUR utility [0,1])
    action_index: int
    value: float           # estimated discounted payoff of the chosen action
    ci: float              # 95% half-width on that estimate
    samples: int
    converged: bool
    base_index: int
    base_value: float
    improved: bool         # did MC move off the closed-form action?


def anytime_search(
    actions: Sequence[float],
    batch_payoffs: Callable[[int], np.ndarray],
    *,
    deadline_s: float,
    base_index: int,
    batch: int = 256,
    max_samples: int = 2_000_000,
    sig_margin: float = 1.0,
    time_fn: Callable[[], float] = time.monotonic,
) -> SearchResult:
    """Accumulate vectorised rollout batches until the time budget (or sample cap)
    is spent, then return the best action — but only deviate from ``base_index``
    when the winner beats it by ``sig_margin`` * (combined standard errors).

    batch_payoffs(n) must return an array of shape [len(actions), n] of payoffs.
    """
    n = len(actions)
    mean = np.zeros(n)
    M2 = np.zeros(n)              # sum of squares of deviations (for variance)
    cnt = 0
    t_end = time_fn() + deadline_s
    while cnt < max_samples:
        P = np.asarray(batch_payoffs(batch), dtype=float)   # [n, batch]
        b = P.shape[1]
        bmean = P.mean(axis=1)
        bM2 = ((P - bmean[:, None]) ** 2).sum(axis=1)
        # Chan parallel-variance merge of the new batch into the running stats.
        delta = bmean - mean
        tot = cnt + b
        mean = mean + delta * (b / tot)
        M2 = M2 + bM2 + delta ** 2 * (cnt * b / tot)
        cnt = tot
        if time_fn() >= t_end:
            break

    var = M2 / max(cnt - 1, 1)
    se = np.sqrt(var / max(cnt, 1))
    best = int(np.argmax(mean))
    # never-worse-in-model: only leave the closed form when confidently better
    gap = mean[best] - mean[base_index]
    if best != base_index and gap <= sig_margin * (se[best] + se[base_index]):
        best = base_index
    return SearchResult(
        action=float(actions[best]), action_index=best,
        value=float(mean[best]), ci=float(1.96 * se[best]),
        samples=int(cnt), converged=bool(gap > 2 * (se[best] + se[base_index]) or n == 1),
        base_index=base_index, base_value=float(mean[base_index]),
        improved=bool(best != base_index),
    )


def _conceder_payoffs(u_actions, u_opp_lo, rounds, rng, n):
    """Vectorised rollout in OUR utility frame.

    Opponent accepts our offer of utility-to-us ``u`` at round t iff
    ``u <= u_opp_max * c(t)`` where ``u_opp_max ~ Uniform[u_opp_lo, 1]`` (their max
    concession, hidden) and c(t) rises from C0 to 1 across the remaining rounds.
    First move = each candidate action; if rejected we play a Boulware continuation
    conceding from the candidate down toward u_opp_lo. Payoff = discounted utility.
    Returns [len(u_actions), n].
    """
    R = max(rounds, 2)
    s = rng.uniform(u_opp_lo, 1.0, size=n)                       # sampled u_opp_max [n]
    ua = np.asarray(u_actions, float)[:, None]                  # [k,1]
    payoff = np.zeros((ua.shape[0], n))
    alive = np.ones_like(payoff, dtype=bool)
    tt = np.arange(R)
    cc = _C0 + (1 - _C0) * (tt / (R - 1)) ** (1.0 / _E_OPP)      # concession curve [R]
    for t in range(R):
        thr = s * cc[t]                                         # opp threshold this round [n]
        if t == 0:
            offer = ua                                          # [k,1] our first move
        else:                                                   # Boulware continuation
            frac = ((R - 1 - t) / (R - 1)) ** (1.0 / _E_ME)
            offer = u_opp_lo + (ua - u_opp_lo) * frac           # [k,1]
        acc = alive & (offer <= thr[None, :])
        payoff = np.where(acc, (_DELTA ** t) * np.broadcast_to(offer, payoff.shape), payoff)
        alive = alive & ~acc
    return payoff


def _single_issue_model(side, walk_away, target, counterparty_offers, rounds_left, base_price,
                        n_grid=25):
    """Build (actions, base_index, batch_payoffs) for a single-issue turn, working
    in OUR utility frame so seller and buyer share one code path."""
    to_util, to_price = (_seller_frame(walk_away, target) if side == "sell"
                         else _buyer_frame(walk_away, target))
    opp_hist = [_clamp01(to_util(p)) for p in (counterparty_offers or [])]
    # the opponent has already conceded us at least max(opp_hist); they'll land
    # somewhere between that and our target (u=1). Belief lower bound:
    u_lo = min(0.9, max([0.0] + opp_hist))
    u_base = _clamp01(to_util(base_price))
    grid = list(np.linspace(u_lo, 1.0, n_grid))
    actions = sorted(set(grid + [u_base]))
    base_index = int(np.argmin([abs(a - u_base) for a in actions]))
    to_price_fn = to_price
    return actions, base_index, u_lo, to_price_fn


def negotiate_turn_mc(*, side, walk_away, target, counterparty_offers=None,
                      my_previous_offers=None, rounds_left=8, item="this",
                      compute_ms=0, seed=0):
    """Tier 1: the closed-form turn, optionally refined by an anytime MC search of
    the counter price. Returns the same dict as negotiate_turn plus a ``compute``
    block. Falls back to the closed form when there's no budget or no counter to
    optimise (accept / walk / one-shot)."""
    base = _closed_form_turn(
        side=side, walk_away=walk_away, target=target,
        counterparty_offers=counterparty_offers, my_previous_offers=my_previous_offers,
        rounds_left=rounds_left, item=item)
    if compute_ms <= 0 or base["action"] != "counter":
        return base

    actions, base_index, u_lo, to_price = _single_issue_model(
        side, walk_away, target, counterparty_offers, rounds_left, base["recommended_price"])
    rng = np.random.default_rng(seed)
    res = anytime_search(
        actions,
        lambda nb: _conceder_payoffs(actions, u_lo, rounds_left, rng, nb),
        deadline_s=compute_ms / 1000.0, base_index=base_index)

    if res.improved:
        new_price = round(float(to_price(res.action)), 2)
        base["recommended_price"] = new_price
        base["message"] = _draft(side, "counter", new_price, item)
        base["rationale"] = (base.get("rationale", "") +
                             f" (Monte-Carlo refined over {res.samples:,} rollouts.)")
    base["compute"] = {
        "budget_ms": compute_ms, "samples": res.samples, "converged": res.converged,
        "improved": res.improved, "value": round(res.value, 4),
        "ci95": round(res.ci, 4), "vs_closed_form": round(res.value - res.base_value, 4),
    }
    return base
