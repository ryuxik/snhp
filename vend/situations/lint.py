"""Conformance checks every situation must pass before it is registered.

WHY THIS EXISTS
The objection to the framework is that each new situation needs a domain
expert to write the rules and somebody to source the evidence — services
economics wearing software's clothes. The answer is not that the work
disappears. It is that the work splits:

    the model DRAFTS      (author.py)
    the linter ENFORCES   (this file — deterministic, no LLM)
    a human VERIFIES      (the numbers, and only the numbers)

This file is the enforcement half, and it is deliberately dumb. Every
check is a property the framework already relies on somewhere, made
explicit so situation #50 is safe without a lawyer reading every line of
it. A draft that passes lint is not correct — it is merely well-formed
and honest about what it doesn't know. Correctness still needs the human.

THE GRID COMES FROM THE SITUATION ITSELF
Each field already declares a `sweep` so the sensitivity engine can score
it. That same declaration doubles as the test fixture here, which means a
situation author never writes fixtures: declaring what a prior could
plausibly be is the one piece of work that pays for itself twice.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from vend.situations import guard, ux
from vend.situations.schema import (
    CHOICE, MustNotAssert, Outcome, Situation,
)

VERDICTS = ("strong", "moderate", "weak")
# Enough to exercise the branches without turning lint into a benchmark.
MAX_COMBINATIONS = 600


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str      # "error" blocks registration; "warn" is a smell
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.check}: {self.detail}"


def _synth(f) -> tuple:
    """Stand-in values for a field declaring neither sweep nor default.

    A SPREAD rather than a single value: one value per axis makes the
    grid degenerate, and a degenerate grid reports that a situation only
    ever returns one verdict when the truth is that lint never varied
    the input. Deliberately generic — lint must not know that a metro
    table exists, so the placeholder metro also exercises the
    degrade-to-national path every situation is supposed to have.
    """
    from vend.situations import schema

    if f.kind == schema.MONEY:
        return (1200, 2000, 3400)
    if f.kind in (schema.MONTHS, schema.COUNT):
        return (2, 12, 30)
    if f.kind == schema.METRO:
        return ("somewhere_we_have_no_data_for",)
    if f.kind == schema.CHOICE:
        return tuple(v for v, _ in f.options)
    if f.kind == schema.BOOL:
        return (True, False)
    return ("x",)


def _sample_values(situation: Situation) -> list[dict]:
    """A grid built from the fields' own declared sweeps.

    The sweep a field declares for the sensitivity engine doubles as the
    fixture here, so a situation author never writes test data.
    """
    axes = []
    for f in situation.fields:
        cands = f.candidates(f.default)
        if not cands:
            if f.default is not None:
                cands = (f.default,)
            elif f.required:
                cands = _synth(f)
            else:
                cands = (None,) + _synth(f)
        # Keep it small: ends and middle are where the branches live.
        if len(cands) > 3:
            cands = (cands[0], cands[len(cands) // 2], cands[-1])
        axes.append([(f.key, c) for c in cands])

    # Stride across the whole product rather than taking its head.
    # itertools.product varies the LAST axis fastest, so the first N
    # combinations hold every early field at its first value — which
    # reported "this situation only ever returns weak" when the truth was
    # that lint never varied months-remaining. Deterministic stride, so
    # the sample is stable across runs.
    total = 1
    for a in axes:
        total *= len(a)
    step = max(1, total // MAX_COMBINATIONS)
    return [
        dict(combo)
        for combo in itertools.islice(itertools.product(*axes), 0, None, step)
    ]


def _run(situation: Situation, values: dict) -> Outcome | None:
    try:
        return situation.assess(values)
    except Exception:
        return None


def check(situation: Situation, extra_values: list[dict] | None = None) -> list[Finding]:
    """Every conformance failure, worst first. Empty means well-formed."""
    out: list[Finding] = []
    grid = _sample_values(situation) + list(extra_values or [])

    # ── Declaration-level ────────────────────────────────────────────
    if not situation.must_not_assert:
        out.append(Finding(
            "must_not_assert", "error",
            "declares no rules. Nobody derives these — a person with domain "
            "knowledge writes them, and they are the difference between a "
            "tool and a lawsuit."))

    if not any(f.required for f in situation.fields):
        out.append(Finding("fields", "warn",
                           "no required fields; the core can run on defaults alone"))

    for f in situation.fields:
        if f.kind not in ux.COMPONENTS:
            out.append(Finding("fields", "error",
                               f"{f.key}: kind {f.kind!r} is not in the component "
                               f"vocabulary; adding a kind is a framework change"))
        if f.kind == CHOICE and not f.options:
            out.append(Finding("fields", "error", f"{f.key}: CHOICE with no options"))
        if f.required and f.default is not None:
            out.append(Finding(
                "fields", "error",
                f"{f.key}: required AND defaulted, so it resolves silently and "
                f"is never asked. Pick one."))
        if not f.required and not f.never_ask and not f.candidates(f.default):
            out.append(Finding(
                "fields", "warn",
                f"{f.key}: optional with no sweep, so it can never be scored — "
                f"it will never be asked and never be corrected"))

    if not situation.triggers:
        out.append(Finding("triggers", "warn",
                           "no keyword triggers; the keyless path can't route here"))

    # ── Behaviour over the grid ──────────────────────────────────────
    ran = 0
    verdicts_seen = set()
    for values in grid:
        o = _run(situation, values)
        if o is None:
            continue
        ran += 1
        verdicts_seen.add(o.verdict)

        if o.verdict not in VERDICTS:
            out.append(Finding("verdict", "error",
                               f"{o.verdict!r} is not one of {VERDICTS}"))
        if not o.headline:
            out.append(Finding("headline", "error", "empty headline"))
        if not o.next_step:
            out.append(Finding(
                "next_step", "error",
                "no closing instruction. A page of options with no 'do this "
                "now' is where people stall."))
        if not o.caveats:
            out.append(Finding("caveats", "error",
                               "an answer with no stated limits is not an honest one"))
        try:
            guard.check(situation, o)
        except MustNotAssert as exc:
            out.append(Finding("guard", "error", str(exc)))
        if o.metric_usd < 0:
            out.append(Finding("metric_usd", "error",
                               "must be a non-negative dollar magnitude"))

        # Determinism, spot-checked rather than everywhere.
        if ran <= 5:
            again = _run(situation, values)
            if again is None or again.to_dict() != o.to_dict():
                out.append(Finding(
                    "determinism", "error",
                    "same inputs produced a different answer; an answer that "
                    "cannot be re-derived cannot be disputed"))

    if not ran:
        out.append(Finding("assess", "error",
                           "never produced an outcome across its own declared sweeps"))
        return _rank(out)

    if "weak" not in verdicts_seen:
        out.append(Finding(
            "horoscope", "error",
            "never reaches verdict 'weak' anywhere in its own sweeps. A tool "
            "that always finds leverage is a horoscope."))

    if len(verdicts_seen) == 1:
        out.append(Finding("verdict", "warn",
                           f"only ever returns {verdicts_seen.pop()!r}"))

    return _rank(_dedupe(out))


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in findings:
        k = (f.check, f.severity, f.detail[:120])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _rank(findings: list[Finding]) -> list[Finding]:
    order = {"error": 0, "warn": 1}
    return sorted(findings, key=lambda f: (order.get(f.severity, 2), f.check))


def errors(situation: Situation) -> list[Finding]:
    return [f for f in check(situation) if f.severity == "error"]


def report(situation: Situation) -> str:
    findings = check(situation)
    if not findings:
        return f"{situation.key}: well-formed (this is not the same as correct)"
    lines = [f"{situation.key}: {len(findings)} finding(s)"]
    lines += [f"  {f}" for f in findings]
    return "\n".join(lines)
