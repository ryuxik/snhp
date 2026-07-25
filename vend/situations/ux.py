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
from vend.situations.schema import ASSUMED, INFERRED, Outcome, Situation

# The whole component vocabulary. Adding a situation must never add to
# this list; if it wants to, the field belongs in an existing kind.
COMPONENTS = ("money", "months", "count", "choice", "bool", "text", "metro")


def build(situation: Situation, priors: Priors, outcome: Outcome | None = None) -> dict:
    """The screen, derived.

    Three regions, in the order a person actually needs them:

    1. `reflection` — the helper's structured read of the situation,
       every field tagged with where it came from and editable. This is
       the trust surface — but SPLIT, and the split is the whole point.
       See below.
    2. `questions` — each carrying the reason it earned its place.
    3. `answer` — the fixed output contract, once there is one.

    ON THE SPLIT
    The first version of this put every resolved prior on screen as a row
    with a colour-coded provenance tag and a legend to decode it. Seven
    rows of homework for the person to mark. That is a confession
    dressed as transparency: most of those rows are things they typed
    thirty seconds ago, and showing somebody their own answer back with
    a green badge is noise, not trust.

    What actually needs their attention is the narrow set we GUESSED at —
    the values an LLM worked out rather than read, and the defaults we
    picked. Everything they stated collapses to one quiet line they can
    open if something looks wrong.

    So: `check` is prominent and usually short or empty. `confirmed` is a
    sentence. Trust comes from us being visibly unsure about exactly the
    right things, not from handing over a spreadsheet.
    """
    questions = sensitivity.rank(situation, priors)
    asked = {q.key for q in questions}
    shown = [a for a in priors.assumptions(situation) if a.key not in asked]

    # `check` is INFERRED only — things a model worked out about THEIR
    # situation. Not ASSUMED: a default that survives this far is, by
    # construction, one the sensitivity engine already judged not to
    # matter, so putting it up for review would contradict the thing
    # that decided not to ask about it. Defaults are disclosed in the
    # quiet line instead, which is the difference between honest and
    # alarming.
    check = [a for a in shown if a.provenance == INFERRED]
    confirmed = [a for a in shown if a.provenance != INFERRED]

    return {
        "situation": {
            "key": situation.key,
            "name": situation.name,
            "one_liner": situation.one_liner,
        },
        "reflection": {
            "check": [a.to_dict() for a in check],
            "check_intro": (
                "I worked these out rather than reading them. Worth a look."
                if check else ""
            ),
            "confirmed": [a.to_dict() for a in confirmed],
            "confirmed_summary": _summary(confirmed),
        },
        "questions": [q.to_dict() for q in questions],
        "questions_note": _questions_note(questions),
        "answer": outcome.to_dict() if outcome else None,
        "answer_is_provisional": bool(questions),
        "components": list(COMPONENTS),
    }


def _summary(confirmed) -> str:
    """One line, not a table. Things they told us, played back compactly
    enough to scan and correct without reading a form back to them."""
    if not confirmed:
        return ""
    parts = [a.value_display for a in confirmed]
    joined = " · ".join(parts)
    assumed = sum(1 for a in confirmed if a.provenance == ASSUMED)
    if assumed:
        return f"{joined} — {assumed} of these are defaults I picked."
    return joined


def _questions_note(questions) -> str:
    if not questions:
        return (
            "Nothing else you could tell me would change this answer, so "
            "I'm not going to ask."
        )
    if len(questions) == 1:
        return "One thing would change this answer:"
    return f"{len(questions)} things would change this answer:"
