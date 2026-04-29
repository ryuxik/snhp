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
import time
from typing import Optional

from negmas.outcomes import Outcome
from negmas.sao import SAOState, ResponseType

import sys
import os.path as _op
sys.path.insert(0, _op.join(_op.dirname(_op.dirname(_op.dirname(_op.abspath(__file__)))), "snhp"))

from b2b_opponents import B2BBase  # noqa: E402

from leaderboard.agents._usage import (  # noqa: E402
    record_call, record_failure, record_retry,
)


# Retryable errors are usually 503 UNAVAILABLE / 504 DEADLINE_EXCEEDED /
# 429 RESOURCE_EXHAUSTED bursts when many workers hit the API at once.
# 4xx 'INVALID_ARGUMENT' / 'PERMISSION_DENIED' should NOT be retried — they
# point to a bug in the prompt or the key.
_RETRYABLE_STATUS = ("503", "504", "429", "UNAVAILABLE", "DEADLINE", "RESOURCE_EXHAUSTED")
_MAX_ATTEMPTS = 4
_BASE_SLEEP = 1.5  # seconds; doubles each retry → 1.5, 3.0, 6.0


def _is_retryable(exc: Exception) -> bool:
    s = f"{type(exc).__name__}: {exc}"
    return any(tok in s for tok in _RETRYABLE_STATUS)


def _call_with_retry(c, model: str, prompt: str, config: dict, *, agent: str):
    """Single LLM call with exponential backoff on transient errors.
    Returns (response, total_latency_ms) or raises the final exception."""
    import random
    last_exc: Optional[Exception] = None
    t_outer = time.time()
    for attempt in range(_MAX_ATTEMPTS):
        try:
            t0 = time.time()
            r = c.models.generate_content(model=model, contents=prompt, config=config)
            return r, (time.time() - t0) * 1000
        except Exception as e:
            last_exc = e
            if not _is_retryable(e) or attempt == _MAX_ATTEMPTS - 1:
                raise
            sleep_s = _BASE_SLEEP * (2 ** attempt) * (0.5 + random.random())  # jittered
            record_retry(agent=agent, model=model,
                          attempt=attempt + 1, sleep_s=sleep_s)
            time.sleep(sleep_s)
    raise last_exc  # pragma: no cover (loop above always returns or raises)


_genai_client = None
# Flash 2.5 is stale. Default to gemini-3-flash-preview (matches the rest of
# the codebase per snhp/llm_extractor.py). Reasoning is OFF — set via
# `thinking_config: {thinking_budget: 0}` below — so the
# `reasoning_token_multiplier` in cost_calculator.py doesn't apply for the
# tournament cost estimate.
_GEMINI_MODEL = os.environ.get("LEADERBOARD_GEMINI_MODEL", "gemini-3-flash-preview")


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

    config = {"temperature": 0.2, "thinking_config": {"thinking_budget": 0}}
    try:
        response, latency_ms = _call_with_retry(
            c, _GEMINI_MODEL, prompt, config, agent="GeminiFlashVanilla",
        )
    except Exception as e:
        record_failure(agent="GeminiFlashVanilla", model=_GEMINI_MODEL,
                        error=f"{type(e).__name__}: {e}")
        return None
    record_call(agent="GeminiFlashVanilla", model=_GEMINI_MODEL,
                usage_metadata=response.usage_metadata,
                latency_ms=latency_ms)
    return _parse_target(response.text or "")


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
