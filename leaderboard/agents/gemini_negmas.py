"""
Gemini Flash NegMAS SAONegotiator wrapper.

Multi-attribute B2B outcomes (price + warranty + delivery + payment),
matching the existing tournament's outcome space. The LLM produces a
*target utility level* in [0, 1]; we map it to the nearest enumerable
outcome via the same helper the heuristic agents use (`_outcome_at_util`).

Reasoning is OFF (per cost audit). With reasoning on, Gemini Flash 2.5
spent ~$0.003/call dominated by reasoning tokens — that's the pattern
we explicitly want to NOT showcase, since "vanilla LLM negotiator" is
the credible comparison point for buyers.

If GOOGLE_API_KEY isn't set, this falls back to a passthrough that
mimics aspiration-style behavior so the tournament still produces an
output (clearly labeled in the leaderboard so we don't pretend an LLM
ran when one didn't).
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

import sys
import os.path as _op
sys.path.insert(0, _op.join(_op.dirname(_op.dirname(_op.dirname(_op.abspath(__file__)))), "snhp"))

from b2b_opponents import B2BBase  # noqa: E402


_genai_client = None
_GEMINI_MODEL = os.environ.get("LEADERBOARD_GEMINI_MODEL", "gemini-2.5-flash")


def _client():
    global _genai_client
    if _genai_client is not None:
        return _genai_client
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore
    _genai_client = genai.Client(
        api_key=api_key,
        http_options=genai_types.HttpOptions(timeout=30000),
    )
    return _genai_client


def _gemini_target_util(role: str, t: float, my_util_history: list[float],
                         opp_util_history: list[float],
                         my_reservation: float) -> Optional[float]:
    """Ask Gemini for a target utility ∈ [0, 1] for the next move.
    Returns None on any failure (fallback to heuristic)."""
    c = _client()
    if c is None:
        return None
    history_lines = []
    for i, (m, o) in enumerate(zip(my_util_history,
                                    opp_util_history + [None] * len(my_util_history))):
        if m is not None:
            history_lines.append(f"  round {2*i}: I ({role}) demanded utility {m:.3f}")
        if o is not None:
            history_lines.append(f"  round {2*i+1}: opponent demanded utility {1-o:.3f} (= I would get {o:.3f})")
    history = "\n".join(history_lines) if history_lines else "  (none yet)"

    prompt = f"""You are an AI agent negotiating a B2B contract as the {role}.
Single-axis utility convention: 1.0 = best for me, 0.0 = walk-away.

State:
  My role: {role}
  My walk-away utility (reservation): {my_reservation:.3f}
  Time elapsed (0=start, 1=deadline): {t:.2f}
  History (utility-to-me at each round):
{history}

Output JSON: {{"target_utility": <float in [{my_reservation:.3f}, 1.0]>}}.
This is the utility level I should aim for in my NEXT proposal.
Return ONLY the JSON object."""

    try:
        response = c.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_budget": 0},
            },
        )
        return _parse_target(response.text or "")
    except Exception:
        return None


def _parse_target(raw: str) -> Optional[float]:
    if not raw:
        return None
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    try:
        v = float(d["target_utility"])
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, min(1.0, v))


class GeminiFlashVanilla(B2BBase):
    """Vanilla Gemini Flash 2.5 negotiator (no reasoning, no game-theory
    primer in the prompt). The whole point of the comparison is "what does
    a stock LLM do off the shelf."

    Prompt is intentionally simple: state + history + target_utility ask.
    No mention of Rubinstein, Pareto, BATNA, or anchoring tactics.
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

        target = _gemini_target_util(
            role=self._role, t=t,
            my_util_history=self._my_util,
            opp_util_history=self._opp_util_to_us,
            my_reservation=my_reservation,
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

        target = _gemini_target_util(
            role=self._role, t=t,
            my_util_history=self._my_util,
            opp_util_history=self._opp_util_to_us,
            my_reservation=my_reservation,
        )
        if target is None:
            target = 0.95 - (0.95 - my_reservation) * t

        return ResponseType.ACCEPT_OFFER if u >= target else ResponseType.REJECT_OFFER

    def _my_util_(self, offer) -> float:
        if self.ufun is None or offer is None:
            return 0.0
        u = self.ufun(offer)
        return float(u) if u is not None else 0.0
