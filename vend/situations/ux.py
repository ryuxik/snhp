"""Derived UX — the screen is a projection, not a design.

There is no rent-renewal form and no lease-break form. There is a fixed,
small vocabulary of components (money, months, choice, yes/no, text) and
a rule for which of them appear and in what order:

    show the priors where confidence is low AND consequence is high,
    ranked by consequence; assume everything else and disclose it.

Consequence comes from sensitivity.py; confidence comes from provenance.
Neither is a judgment call made here.

WHAT IS DELIBERATELY NOT HERE
No LLM generates markup. Generated UI is non-deterministic, unauditable,
and unstyleable, and it is the same mistake as writing a bespoke pricer
per vertical. What is dynamic is *which* components appear and in what
order — that is derived; the components themselves are fixed.
"""

from __future__ import annotations

from vend.situations import sensitivity
from vend.situations.priors import Priors
from vend.situations.schema import Outcome, Situation

# The whole component vocabulary. Adding a situation must never add to
# this list; if it wants to, the field belongs in an existing kind.
COMPONENTS = ("money", "months", "count", "choice", "bool", "text", "metro")


def build(situation: Situation, priors: Priors, outcome: Outcome | None = None) -> dict:
    """The screen, derived.

    Three regions, in the order a person actually needs them:

    1. `reflection` — the helper's structured read of the situation,
       every field tagged with where it came from and editable. This is
       the trust surface: you audit inputs, you don't have to believe an
       output.
    2. `questions` — at most three, each carrying the reason it earned
       its place.
    3. `answer` — the fixed output contract, once there is one.
    """
    questions = sensitivity.rank(situation, priors)
    asked = {q.key for q in questions}

    return {
        "situation": {
            "key": situation.key,
            "name": situation.name,
            "one_liner": situation.one_liner,
        },
        "reflection": {
            "intro": (
                "Here's how I read your situation. Fix anything that's wrong — "
                "the answer is only as good as this."
            ),
            "fields": [
                a.to_dict()
                for a in priors.assumptions(situation)
                if a.key not in asked
            ],
        },
        "questions": [q.to_dict() for q in questions],
        "questions_note": _questions_note(questions),
        "answer": outcome.to_dict() if outcome else None,
        "answer_is_provisional": bool(questions),
        "components": list(COMPONENTS),
    }


def _questions_note(questions) -> str:
    if not questions:
        return (
            "Nothing else you could tell me would change this answer, so "
            "I'm not going to ask."
        )
    if len(questions) == 1:
        return "One thing would change this answer:"
    return f"{len(questions)} things would change this answer:"
