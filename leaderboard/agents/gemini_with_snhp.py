"""
Gemini Flash + SNHP scaffolding — same Gemini agent as the vanilla one,
but the prompt is augmented with SNHP's recommendation (recommended offer,
acceptance probability, brief posterior summary). Lets the LLM use the
math primitives without us forcing it to.

This is "Bar 3" in the public leaderboard's headline comparison:
  vanilla LLM (Bar 1/2) vs LLM + SNHP scaffolding (Bar 3).

Same model, same reasoning config — only the prompt changes. So any
delta in tournament outcome is attributable to the scaffolding.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

import sys
import os.path as _op
# Reach into snhp/ for the math layer (sell_next_offer / buy_next_offer).
_REPO_ROOT = _op.dirname(_op.dirname(_op.dirname(_op.abspath(__file__))))
sys.path.insert(0, _op.join(_REPO_ROOT, "snhp"))
sys.path.insert(0, _REPO_ROOT)

from b2b_opponents import B2BBase  # noqa: E402
from gametheory.negotiation.sell import sell_next_offer  # noqa: E402
from gametheory.negotiation.buy import buy_next_offer  # noqa: E402

from leaderboard.agents.gemini_negmas import (  # noqa: E402
    _client, _GEMINI_MODEL, _parse_target, _call_with_retry,
)
from leaderboard.agents._usage import record_call, record_failure  # noqa: E402


def _gemini_with_snhp_target(
    *,
    role: str,
    t: float,
    my_util_history: list[float],
    opp_util_history: list[float],
    my_reservation: float,
    deadline_rounds: int,
) -> Optional[float]:
    """Same shape as `_gemini_target_util` but the prompt also exposes
    SNHP's recommendation. Returns target utility or None on failure."""

    # 1) Pull SNHP's recommendation from the math layer.
    snhp_kwargs = dict(
        my_reservation=my_reservation,
        my_offer_history=my_util_history,
        deadline_rounds=deadline_rounds,
        pareto_knob=0.5,
    )
    if role == "seller":
        rec = sell_next_offer(opponent_offer_history=opp_util_history, **snhp_kwargs)
    else:
        rec = buy_next_offer(seller_offer_history=opp_util_history, **snhp_kwargs)

    snhp_offer = float(rec["recommended_offer"])
    accept_prob = float(rec.get("acceptance_probability", 0.5))
    posterior = rec.get("posterior", {})
    inferred_opp_w = posterior.get("inferred_opp_price_weight", None)
    estimated_opp_res = posterior.get("estimated_opp_reservation", None)

    # 2) Build the scaffolded prompt: same negotiation context as vanilla,
    #    plus a "Decision support" block.
    history_lines = []
    for i, (m, o) in enumerate(zip(
        my_util_history,
        opp_util_history + [None] * len(my_util_history),
    )):
        if m is not None:
            history_lines.append(f"  round {2*i}: I ({role}) demanded utility {m:.3f}")
        if o is not None:
            history_lines.append(
                f"  round {2*i+1}: opponent demanded utility {1-o:.3f} (= I would get {o:.3f})"
            )
    history = "\n".join(history_lines) if history_lines else "  (none yet)"

    # Inferred opponent line — only include if posterior gave us values.
    posterior_line = ""
    if inferred_opp_w is not None and estimated_opp_res is not None:
        posterior_line = (
            f"\n  Inferred opponent price-weight: {float(inferred_opp_w):.2f}"
            f"\n  Estimated opponent reservation: {float(estimated_opp_res):.3f}"
        )

    prompt = f"""You are an AI agent negotiating a B2B contract as the {role}.
Single-axis utility convention: 1.0 = best for me, 0.0 = walk-away.

State:
  My role: {role}
  My walk-away utility (reservation): {my_reservation:.3f}
  Time elapsed (0=start, 1=deadline): {t:.2f}
  History (utility-to-me at each round):
{history}

Decision support (optional — use as you see fit):
  Game-theoretic recommended offer: {snhp_offer:.3f}
  Estimated acceptance probability:  {accept_prob:.2f}{posterior_line}

Output JSON: {{"target_utility": <float in [{my_reservation:.3f}, 1.0]>}}.
Return ONLY the JSON object."""

    c = _client()
    if c is None:
        return None
    config = {"temperature": 0.2, "thinking_config": {"thinking_budget": 0}}
    try:
        response, latency_ms = _call_with_retry(
            c, _GEMINI_MODEL, prompt, config, agent="GeminiWithSnhp",
        )
    except Exception as e:
        record_failure(agent="GeminiWithSnhp", model=_GEMINI_MODEL,
                        error=f"{type(e).__name__}: {e}")
        return None
    record_call(agent="GeminiWithSnhp", model=_GEMINI_MODEL,
                usage_metadata=response.usage_metadata,
                latency_ms=latency_ms)
    return _parse_target(response.text or "")


class GeminiWithSnhp(B2BBase):
    """Gemini Flash + SNHP scaffolding.

    Same model and reasoning config as `GeminiFlashVanilla`, but the prompt
    exposes the math layer's recommendation. The LLM still owns the final
    decision — we don't override its choice.

    Falls back to aspiration if the LLM call fails (same fallback as
    vanilla so the comparison stays fair on infra failures).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._role: str = "seller"
        self._opp_util_to_us: list[float] = []
        self._my_util: list[float] = []

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        my_reservation = float(getattr(self.ufun, "reserved_value", 0.30) or 0.30)
        deadline_rounds = self._total_steps()

        target = _gemini_with_snhp_target(
            role=self._role, t=t,
            my_util_history=self._my_util,
            opp_util_history=self._opp_util_to_us,
            my_reservation=my_reservation,
            deadline_rounds=deadline_rounds,
        )
        if target is None:
            target = 0.95 - (0.95 - my_reservation) * t

        target = max(target, my_reservation)
        offer = self._outcome_at_util(target)
        if offer:
            self._my_offers.append(offer)
            self._my_util.append(self._my_util_(offer))
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util_(offer)
        self._opp_util_to_us.append(u)
        my_reservation = float(getattr(self.ufun, "reserved_value", 0.30) or 0.30)
        t = state.relative_time
        deadline_rounds = self._total_steps()

        target = _gemini_with_snhp_target(
            role=self._role, t=t,
            my_util_history=self._my_util,
            opp_util_history=self._opp_util_to_us,
            my_reservation=my_reservation,
            deadline_rounds=deadline_rounds,
        )
        if target is None:
            target = 0.95 - (0.95 - my_reservation) * t

        return ResponseType.ACCEPT_OFFER if u >= target else ResponseType.REJECT_OFFER

    def _my_util_(self, offer) -> float:
        if self.ufun is None or offer is None:
            return 0.0
        u = self.ufun(offer)
        return float(u) if u is not None else 0.0
