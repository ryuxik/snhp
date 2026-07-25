"""The helper: conversation -> declared priors -> deterministic sim -> answer.

    text ──▶ intake ──▶ priors ──▶ assess ──▶ guard ──▶ contract
                 │         │          │
                 │         │          └── sensitivity ──▶ derived UX
                 │         └── provenance on every field
                 └── LLM, bounded: fills the struct, never a judgment

`answer()` is the whole public surface. Everything above it in the stack
(HTTP routes, the page) is presentation; everything below is the parts
documented in their own modules.

Two invariants hold across every situation, and the tests enforce both:
the answer is a pure function of the declared priors, and no situation
can put a string in front of a person that breaks its own
must-not-assert rules.
"""

from __future__ import annotations

from vend.situations import guard, intake, priors as _priors, registry, ux
from vend.situations.schema import MustNotAssert, STATED, Situation

__all__ = ["answer", "registry", "intake", "ux", "guard"]


def answer(
    text: str | None = None,
    situation_key: str | None = None,
    values: dict | None = None,
    read_text: bool = True,
    include_draft: bool = False,
) -> dict:
    """One call, from whatever the person has given us so far.

    `include_draft` reaches situations that are not live yet. It is off
    by default, so the public surface can only ever offer work whose
    evidence is sourced — a caller has to ask for a draft on purpose.

    `text` is their description. `values` is anything they have since
    confirmed or corrected in the reflection panel — those always win
    over what the intake layer read, and are tagged as stated, because
    a human typing a number into a field they can see is the strongest
    provenance there is.
    """
    values = dict(values or {})

    reading = None
    if text and read_text:
        reading = intake.read(text, situation_key=situation_key,
                              include_draft=include_draft)
        situation_key = situation_key or reading.situation_key

    situation = (registry.get(situation_key, public=not include_draft)
                 if situation_key else None)
    if situation is None:
        return {
            "resolved": False,
            "reason": "situation_unknown",
            "message": (
                "Tell me what's going on, or pick the closest situation — "
                "I'd rather ask than guess which problem this is."
            ),
            "catalog": registry.catalog(public=not include_draft),
            "reading": reading.to_dict() if reading else None,
        }

    merged, prov, conf, quoted = _merge(reading, values)
    p = _priors.resolve(
        situation, stated=merged, provenance=prov, confidence=conf, quoted=quoted
    )

    outcome, error = _assess(situation, p)
    screen = ux.build(situation, p, outcome)
    screen.update({
        "resolved": True,
        "reading": reading.to_dict() if reading else None,
        "blocked": error,
        "catalog": registry.catalog(public=not include_draft),
        "missing_required": [
            f.key for f in situation.fields
            if f.required and p.get(f.key) is None
        ],
    })
    return screen


def _merge(reading, values: dict):
    """Confirmed values beat read values. Always."""
    merged: dict = {}
    prov: dict = {}
    conf: dict = {}
    quoted: dict = {}

    if reading is not None:
        merged.update(reading.values)
        prov.update(reading.provenance)
        conf.update(reading.confidence)
        quoted.update(reading.quoted)

    for k, v in values.items():
        if v is None:
            continue
        merged[k] = v
        prov[k] = STATED
        conf[k] = 1.0
        quoted[k] = ""

    return merged, prov, conf, quoted


def _assess(situation: Situation, p) -> tuple[object | None, str | None]:
    """Run the core, or say plainly why we couldn't.

    A must-not-assert violation is a hard stop, not a warning. Serving a
    reduced page is recoverable; telling somebody their increase is
    unlawful when it may not be is not.
    """
    missing = [f.key for f in situation.fields if f.required and p.get(f.key) is None]
    if missing:
        return (None, None)
    try:
        outcome = situation.assess(p.values)
    except ValueError:
        return (None, "invalid_inputs")
    except Exception:
        return (None, "assess_failed")

    try:
        guard.check(situation, outcome)
    except MustNotAssert:
        return (None, "guard_tripped")
    return (outcome, None)
