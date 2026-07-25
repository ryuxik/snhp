"""Must-not-assert enforcement.

The rules themselves are per-situation data written by somebody with
domain knowledge (see each situation's `must_not_assert`). This module
is the framework half: it walks every string that will reach a person —
headline, routes, message, exposure, caveats — and refuses to emit
output that breaks one.

WHY THIS IS A HARD FAILURE
The rules exist because the failure mode is not "the answer is wrong,"
it is "somebody walks into a confrontation, or withholds rent, holding a
false premise we handed them." A degraded answer is recoverable. That is
not. So `check` raises, and the caller is expected to serve a reduced
response rather than the offending one.

The rules are written against the situation's OWN generated copy. They
are a regression harness for the copy, not a content filter on user
input — a person may describe their situation however they like.
"""

from __future__ import annotations

from vend.situations.schema import MustNotAssert, Outcome, Situation


def strings(outcome: Outcome) -> list[tuple[str, str]]:
    """Every user-facing string in an outcome, with where it came from."""
    out: list[tuple[str, str]] = [("headline", outcome.headline)]
    for r in outcome.routes:
        out.append((f"route:{r.key}:label", r.label))
        out.append((f"route:{r.key}:detail", r.detail))
        out.append((f"route:{r.key}:why", r.why))
        if r.unavailable_because:
            out.append((f"route:{r.key}:unavailable", r.unavailable_because))
        if r.ask_phrase:
            out.append((f"route:{r.key}:ask_phrase", r.ask_phrase))
    if outcome.next_step:
        out.append(("next_step", outcome.next_step))
    if outcome.message:
        out.append(("message", outcome.message))
    for i, e in enumerate(outcome.exposure):
        out.append((f"exposure[{i}]", e))
    for i, c in enumerate(outcome.caveats):
        out.append((f"caveat[{i}]", c))
    for i, v in enumerate(outcome.verify):
        for k in ("action", "where", "note"):
            if v.get(k):
                out.append((f"verify[{i}].{k}", v[k]))
    if outcome.odds_basis:
        out.append(("odds_basis", outcome.odds_basis))
    return out


def check(situation: Situation, outcome: Outcome) -> None:
    """Raise if any generated copy breaks one of this situation's rules."""
    if not situation.must_not_assert:
        return
    for where, text in strings(outcome):
        if not text:
            continue
        for rule in situation.must_not_assert:
            if rule.hits(text):
                raise MustNotAssert(
                    f"{situation.key}: {where} violates a must-not-assert rule "
                    f"({rule.why}). Offending text: {text!r}"
                )


def safe_outcome(situation: Situation, outcome: Outcome) -> Outcome:
    """Run the check and return the outcome, for use at the call site."""
    check(situation, outcome)
    return outcome
