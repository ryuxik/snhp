"""Sensitivity — the mechanism that lets the UI be derived, not designed.

THE IDEA
A question is worth asking exactly when the answer would change the
advice. That is not a matter of taste, it is computable: the situation's
assess function is deterministic and cheap, so substitute each plausible
value of an unresolved prior, re-run, and see whether the verdict flips,
the recommended route changes, or the dollar figure moves materially.
Rank by how much it moves. Ask the top two or three. Assume the rest and
say so.

WHAT THIS BUYS
No screens get authored. Adding lease-break does not mean designing a
lease-break form — the questions fall out of which priors matter, in the
order they matter, and a field that never changes the answer never
appears no matter how natural it feels to ask. `credit_score` in the
lease-break situation exists precisely to prove that: it is declared, it
is swept, it scores zero, and it is never shown.

THRESHOLDS ARE JUDGMENT
`MATERIAL_USD` and `ASK_THRESHOLD` are set so that a question has to be
worth roughly a month of rent, or actually change the plan, before a
person is made to answer it. They are the only tuned numbers in the
framework and they are stated here rather than buried.
"""

from __future__ import annotations

from dataclasses import dataclass

from vend.situations.priors import Priors
from vend.situations.schema import Situation

# A dollar swing below this is noise; nobody should be asked about it.
MATERIAL_USD = 600.0
# Score at or above which a field becomes a question.
ASK_THRESHOLD = 0.34

# THERE IS NO CAP ON THE NUMBER OF QUESTIONS, DELIBERATELY.
#
# An earlier version truncated to three, on the instinct that a long list
# of questions is a form wearing a conversation's clothes. That was the
# wrong instrument and it broke the actual rule: a field that cleared the
# threshold — that genuinely changes the advice — could be silently
# dropped to satisfy a quota. Rent renewal has four inputs its core
# cannot run without, and the cap sent people back for a second round to
# collect the fourth.
#
# The threshold IS the filter. If eight priors really move the answer,
# then it really is an eight-question problem, and pretending otherwise
# produces a confident answer resting on defaults nobody confirmed.
# Ranking handles the rest: the most consequential come first.


@dataclass(frozen=True)
class Question:
    """A question the framework decided is worth a person's attention.

    `why_it_matters` is generated from the sweep that produced it, not
    written by hand — it says what actually changes, which is the only
    honest justification for asking.
    """

    key: str
    label: str
    kind: str
    help: str
    unit: str
    options: tuple[tuple[str, str], ...]
    score: float
    why_it_matters: str
    swing_usd: float
    current: object = None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "help": self.help,
            "unit": self.unit,
            "options": [{"value": v, "label": l} for v, l in self.options],
            "why_it_matters": self.why_it_matters,
            "swing_usd": round(self.swing_usd),
            "current": self.current,
        }


def _safe_assess(situation: Situation, values: dict):
    try:
        return situation.assess(values)
    except Exception:
        return None


def rank(situation: Situation, priors: Priors) -> list[Question]:
    """Every unresolved prior, scored by how much it moves the answer."""
    base = _safe_assess(situation, priors.values)
    if base is None:
        # No baseline to sweep against, so nothing can be scored. Ask for
        # every required input at once — these are not a judgment call,
        # they are the minimum the core needs to run, and rationing them
        # just sends somebody back for a second round.
        return [
            _question(situation, priors, key, 1.0,
                      "Needed before anything can be worked out.", 0.0)
            for key in priors.unresolved(situation)
            if (f := situation.field(key)) and f.required
        ]

    scored: list[Question] = []
    for key in priors.unresolved(situation):
        f = situation.field(key)
        if f is None:
            continue
        cands = f.candidates(priors.get(key))
        if not cands:
            # Nothing to sweep, but it's required and missing — ask.
            if f.required and priors.get(key) is None:
                scored.append(
                    _question(situation, priors, key, 1.0,
                              "We can't answer without this.", 0.0)
                )
            continue

        flips = 0
        tried = 0
        swings: list[float] = []
        outcomes = []
        for c in cands:
            o = _safe_assess(situation, priors.with_value(key, c).values)
            if o is None:
                continue
            tried += 1
            outcomes.append((c, o))
            if o.verdict != base.verdict or o.top_route_key() != base.top_route_key():
                flips += 1
            swings.append(abs(o.metric_usd - base.metric_usd))

        if not tried:
            continue

        flip_share = flips / tried
        swing = max(swings) if swings else 0.0
        money_score = min(1.0, swing / MATERIAL_USD) if swing else 0.0
        # A changed plan counts for more than a changed number: being
        # told the wrong ACTION is worse than being told the wrong total.
        score = min(1.0, 0.7 * flip_share + 0.5 * money_score)

        if score < ASK_THRESHOLD:
            continue

        scored.append(
            _question(situation, priors, key, score,
                      _why(f, base, outcomes), swing)
        )

    scored.sort(key=lambda q: (-q.score, -q.swing_usd, q.key))
    return scored


def _question(situation, priors, key, score, why, swing) -> Question:
    f = situation.field(key)
    return Question(
        key=key,
        label=f.label,
        kind=f.kind,
        help=f.help,
        unit=f.unit,
        options=f.options,
        score=score,
        why_it_matters=why,
        swing_usd=swing,
        current=priors.get(key),
    )


def _why(f, base, outcomes) -> str:
    """State what actually changes, using the sweep that just ran.

    Prefer naming the two different plans over quoting a dollar range —
    "this decides whether you use the clause or negotiate" is a reason a
    person can act on; "this is worth $2,400" is a number they have to
    take on faith.
    """
    plans = []
    for c, o in outcomes:
        label = f.display(c)
        top = next((r.label for r in o.routes if r.available), "no clear move")
        plans.append((label, top, o.verdict))

    distinct = {p[1] for p in plans}
    if len(distinct) > 1 and len(plans) <= 4:
        # Name the plans rather than quoting a dollar range: "this decides
        # whether you use the clause or negotiate" is a reason somebody
        # can act on; a number is one they have to take on faith.
        parts = [f"{lab} → {top}" for lab, top, _ in plans]
        return "Changes the plan. " + " · ".join(parts)

    verdicts = {p[2] for p in plans}
    if len(verdicts) > 1:
        return (
            "This changes how strong your position is, which changes "
            "whether it's worth pushing at all."
        )

    swing = max(abs(o.metric_usd - base.metric_usd) for _, o in outcomes)
    if swing >= MATERIAL_USD:
        return f"This moves what's at stake by about ${swing:,.0f}."
    return "This affects the answer enough to be worth a moment."
