"""The situation registry, and the keyless classifier.

Adding a situation is one import and one line in SITUATIONS. That is the
whole registration story, and it is deliberately boring — if registering
a situation required touching the framework, the framework would not be
one.

The keyword classifier exists so the entire surface works with no API
key configured: no LLM, no extraction, but the right situation and a
plain set of questions. Degrading to a form is an acceptable failure.
Guessing is not.
"""

from __future__ import annotations

from vend.situations import rent_renewal, salary_negotiation
from vend.situations.lease_break import SITUATION as _LEASE_BREAK
from vend.situations.schema import Situation

SITUATIONS: dict[str, Situation] = {
    rent_renewal.SITUATION.key: rent_renewal.SITUATION,
    _LEASE_BREAK.key: _LEASE_BREAK,
    salary_negotiation.SITUATION.key: salary_negotiation.SITUATION,
}


def get(key: str, *, public: bool = False) -> Situation | None:
    """Fetch a situation. `public=True` hides ones that aren't live yet."""
    s = SITUATIONS.get(key)
    if s is None or (public and not s.live):
        return None
    return s


def live() -> dict:
    return {k: s for k, s in SITUATIONS.items() if s.live}


def catalog(*, public: bool = True) -> list[dict]:
    """What a person is offered. Public by default — the safe direction."""
    source = live() if public else SITUATIONS
    return [
        {"key": s.key, "name": s.name, "one_liner": s.one_liner}
        for s in source.values()
    ]


def classify(text: str, *, public: bool = True) -> tuple[str | None, float]:
    """Which situation is this, from keywords alone.

    Returns (key, confidence). Confidence is deliberately capped below
    certainty: the caller shows the person which situation was picked
    and lets them switch, because a misread situation produces a
    confidently wrong answer rather than an obviously wrong one.
    """
    if not text:
        return (None, 0.0)
    low = text.lower()

    scores: dict[str, int] = {}
    for key, s in (live() if public else SITUATIONS).items():
        hits = sum(1 for t in s.triggers if t in low)
        if hits:
            scores[key] = hits

    if not scores:
        return (None, 0.0)

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_key, top_hits = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    if top_hits == runner_up:
        # Genuinely ambiguous — say so rather than picking.
        return (top_key, 0.4)
    return (top_key, min(0.85, 0.5 + 0.15 * top_hits))
