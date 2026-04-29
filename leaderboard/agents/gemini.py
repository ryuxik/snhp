"""
Gemini Flash agent — wraps Gemini-2.5-Flash (reasoning OFF, since the cost
audit found reasoning tokens dominate and we want a credible "vanilla LLM
negotiator" baseline, not a reasoning-tuned one).

Falls back to a clear no-op if GOOGLE_API_KEY isn't set, so the rest of
the leaderboard keeps running.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from leaderboard.protocol import GameState


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


def gemini_flash_vanilla_agent(state: GameState) -> dict:
    """Vanilla-prompt Gemini negotiator — no reasoning, no game-theory
    primer. The point of the comparison is "what does an LLM do off-the-
    shelf?" not "what does an LLM do with our prompt engineering?"

    If GOOGLE_API_KEY is missing, returns the deterministic-fallback
    aspiration recommendation so the leaderboard still produces output.
    """
    c = _client()
    if c is None:
        return _fallback(state)

    prompt = _build_prompt(state)
    try:
        response = c.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_budget": 0},  # reasoning OFF
            },
        )
        parsed = _parse(response.text or "")
    except Exception:
        return _fallback(state)

    if parsed is None:
        return _fallback(state)
    return parsed


def _build_prompt(state: GameState) -> str:
    role = state.role
    opp_role = "buyer" if role == "seller" else "seller"
    history_lines = []
    for i, (mine, theirs) in enumerate(zip(
        state.my_offer_history,
        state.opponent_offer_history + [None] * (len(state.my_offer_history))
    )):
        if mine is not None:
            history_lines.append(f"  round {2*i}: me ({role}) offered {mine:.3f}")
        if theirs is not None:
            history_lines.append(f"  round {2*i+1}: opponent ({opp_role}) offered {theirs:.3f}")
    history = "\n".join(history_lines) if history_lines else "  (none yet)"

    return f"""You are an AI agent negotiating on behalf of a {role} in a single-axis price negotiation.

Utility convention: every number below is utility-to-you in [0, 1], where 1.0 means you capture all surplus and 0.0 means you walk away empty-handed.

Game rules:
- Single-axis price; both sides have a private walk-away utility (reservation).
- Alternating offers, max {state.deadline_rounds} rounds.
- You may either OFFER a new price, ACCEPT the opponent's last offer, or WALK away.

Your reservation (walk-away utility): {state.my_reservation:.3f}
Round: {state.round_index + 1} of {state.deadline_rounds}
History (utility-to-you):
{history}
Opponent's last offer to you: {state.last_opponent_offer if state.last_opponent_offer is not None else "—"}

Output a JSON object with one of these shapes:
  {{"action": "offer", "price": <float in [0, 1]>}}
  {{"action": "accept"}}
  {{"action": "walk"}}

Return ONLY the JSON object, no preamble or markdown."""


def _parse(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage: find the first {...} block.
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    action = d.get("action")
    if action == "offer":
        try:
            p = float(d["price"])
        except (KeyError, TypeError, ValueError):
            return None
        return {"action": "offer", "price": max(0.0, min(1.0, p))}
    if action in ("accept", "walk"):
        return {"action": action}
    return None


def _fallback(state: GameState) -> dict:
    """Deterministic fallback when the LLM is unavailable. Aspiration-style
    so the leaderboard still produces a non-degenerate baseline."""
    t = state.round_index / max(1, state.deadline_rounds - 1)
    aspiration = 0.95 - (0.95 - state.my_reservation) * t
    if (state.last_opponent_offer is not None
            and state.last_opponent_offer >= aspiration):
        return {"action": "accept"}
    return {"action": "offer", "price": aspiration}
