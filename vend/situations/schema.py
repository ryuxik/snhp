"""The situation schema — layer 2 of the helper framework.

THE POINT OF THIS FILE
A rent renewal and a lease break are the same object with different
contents. What varies per situation is DATA (which priors exist, where
they come from, what may never be asserted) plus one pure function from
resolved priors to an outcome. Everything else — asking the right
question, ordering questions by consequence, tagging provenance,
enforcing the must-not-assert rules, shaping the answer — is framework
and is written once.

The test of whether that claim is real is in test_situations.py: adding
lease-break must touch data and one assess function, and nothing here.

WHY THE OUTPUT CONTRACT IS FIXED
Six fields, same shape for every situation. That is what makes forty
tools feel like one helper: a person learns to read one answer, not one
per problem. It also means a new situation cannot invent a new way to be
persuasive — it fills in the same slots, including the ones that make it
honest (`exposure`, `verify`, `caveats`).

WHY `verdict` INCLUDES "weak"
Every situation must be able to reach a verdict that tells the person to
do nothing. A tool that always finds leverage is a horoscope. The
framework does not enforce this by type — it enforces it by test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ── Provenance ───────────────────────────────────────────────────────
# Where a value came from. This is the trust primitive: the person is
# asked to confirm a picture, not to believe a verdict, and they can
# only do that if every field says where it came from.

STATED = "stated"        # the person said it
INFERRED = "inferred"    # an LLM read it out of their text but they didn't say it plainly
MARKET = "market"        # a verified market-data module
RULES = "rules"          # a verified legal/structural rules module
ASSUMED = "assumed"      # a framework default, disclosed as such
UNKNOWN = "unknown"      # not resolved; may become a question

PROVENANCE_LABEL = {
    STATED: "you said",
    INFERRED: "we read this from your message",
    MARKET: "market data",
    RULES: "statute / published rule",
    ASSUMED: "assumed",
    UNKNOWN: "not known",
}

# Provenance that a judgment may rest on without disclosure-as-guess.
# INFERRED is deliberately absent: an LLM reading a number out of prose
# is a guess until a human confirms it.
FIRM = (STATED, MARKET, RULES)


# ── Fields (what a situation needs to know) ──────────────────────────

MONEY = "money"
MONTHS = "months"
COUNT = "count"
CHOICE = "choice"
BOOL = "bool"
TEXT = "text"
METRO = "metro"

_KINDS = (MONEY, MONTHS, COUNT, CHOICE, BOOL, TEXT, METRO)


@dataclass(frozen=True)
class Field:
    """One prior a situation may need.

    `sweep` is the load-bearing field and the reason the UI can be
    derived rather than designed: it is the set of values this prior
    could plausibly take. The framework substitutes each one, re-runs
    the situation's assess function, and asks the person about this
    field only if the answer actually moves. A field with a sweep that
    never changes the outcome is never shown — see sensitivity.py.
    """

    key: str
    label: str
    kind: str
    required: bool = False
    help: str = ""
    unit: str = ""
    # (value, human label) pairs — CHOICE only.
    options: tuple[tuple[str, str], ...] = ()
    # A closed list of acceptable values, for fields whose vocabulary is
    # a table we own. Shown to the intake model so it SELECTS rather than
    # RECALLS: a measured Haiku run returned metro "Brooklyn" instead of
    # "New York" and silently degraded the answer to national figures.
    # Opus happened to know the mapping; depending on world knowledge for
    # a lookup we have on disk is fragile in both cases.
    vocabulary: tuple[str, ...] = ()
    # Used when the person hasn't supplied one. Always tagged ASSUMED.
    default: Any = None
    # Candidate values for the sensitivity sweep. Empty means "derive
    # from kind", which works for BOOL and CHOICE and is a coarse
    # guess for money.
    sweep: tuple = ()
    # A prior the framework may resolve but must never put on screen as
    # a question (e.g. derived from another field).
    never_ask: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"{self.key}: unknown kind {self.kind!r}")
        if self.kind == CHOICE and not self.options:
            raise ValueError(f"{self.key}: CHOICE fields need options")

    def candidates(self, current: Any) -> tuple:
        """Plausible values, for the sensitivity sweep."""
        if self.sweep:
            return self.sweep
        if self.kind == BOOL:
            return (True, False)
        if self.kind == CHOICE:
            return tuple(v for v, _ in self.options)
        if self.kind in (MONEY, MONTHS, COUNT):
            base = current if isinstance(current, (int, float)) and current else self.default
            if isinstance(base, (int, float)) and base:
                return (type(base)(base * 0.5), base, type(base)(base * 2))
        return ()

    def display(self, value: Any) -> str:
        if value is None:
            return "—"
        if self.kind == MONEY:
            return f"${value:,.0f}"
        if self.kind == BOOL:
            return "yes" if value else "no"
        if self.kind == CHOICE:
            for v, label in self.options:
                if v == value:
                    return label
            return str(value)
        if self.kind in (MONTHS, COUNT):
            return f"{value:g} {self.unit or ''}".strip()
        if self.kind == METRO:
            # Keys are normalised lowercase; show them the way a person
            # wrote them. Deliberately generic — the framework must not
            # know that a metro table exists.
            return str(value).replace("_", " ").title()
        return str(value)


# ── The output contract (identical for every situation) ──────────────


@dataclass(frozen=True)
class Route:
    """One thing the person could do, and what it is likely to cost.

    `available` exists so a route can appear as ruled out rather than
    silently vanish — "you can't assign, your lease forbids it" is
    information; an absent option is not.
    """

    key: str
    label: str
    detail: str
    why: str
    ease: str = "moderate"           # easiest | moderate | hardest
    est_cost_usd: int | None = None  # what this route costs you
    est_value_usd: int | None = None # what it saves vs doing nothing
    available: bool = True
    unavailable_because: str = ""
    ask_phrase: str = ""             # embeddable clause for the drafted message


@dataclass(frozen=True)
class Assumption:
    """One resolved prior, shown back for confirmation."""

    key: str
    label: str
    value_display: str
    provenance: str
    editable: bool = True

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value_display,
            "provenance": self.provenance,
            "provenance_label": PROVENANCE_LABEL.get(self.provenance, self.provenance),
            "editable": self.editable,
        }


@dataclass(frozen=True)
class Outcome:
    """What every situation returns. Same six things, always.

    `metric_usd` is not shown to anyone. It is the scalar the
    sensitivity engine differences to decide whether a question is worth
    asking, and it must be denominated in dollars-per-year so the
    threshold means the same thing across situations.
    """

    verdict: str            # strong | moderate | weak
    # How that verdict reads to a person. Nobody has ever felt
    # "moderate" about their rent. The enum stays for the machinery
    # (sensitivity compares it, lint checks it); this is what gets shown,
    # and each situation says it in its own words.
    verdict_label: str = ""
    headline: str = ""
    routes: list[Route] = field(default_factory=list)
    # The single "do this now" instruction. Required in spirit for every
    # situation: a page full of options and no closing instruction is
    # where people stall. It carries urgency and routing — on the
    # regulated renewal path it is the most important sentence there is,
    # because it sends somebody to the legal question instead of the
    # negotiation.
    next_step: str = ""
    message: str = ""
    exposure: list[str] = field(default_factory=list)   # what you're on the hook for
    verify: list[dict] = field(default_factory=list)    # how to check, never asserting
    caveats: list[str] = field(default_factory=list)
    odds: float | None = None
    odds_basis: str = ""
    evidence_note: str = ""
    metric_usd: float = 0.0
    context: dict = field(default_factory=dict)

    def top_route_key(self) -> str:
        for r in self.routes:
            if r.available:
                return r.key
        return ""

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "verdict_label": self.verdict_label or self.verdict,
            "headline": self.headline,
            "routes": [
                {
                    "key": r.key,
                    "label": r.label,
                    "detail": r.detail,
                    "why": r.why,
                    "ease": r.ease,
                    "est_cost_usd": r.est_cost_usd,
                    "est_value_usd": r.est_value_usd,
                    "available": r.available,
                    "unavailable_because": r.unavailable_because,
                }
                for r in self.routes
            ],
            "next_step": self.next_step,
            "message": self.message,
            "exposure": self.exposure,
            "verify": self.verify,
            "caveats": self.caveats,
            "odds": round(self.odds, 2) if self.odds is not None else None,
            "odds_basis": self.odds_basis,
            "evidence_note": self.evidence_note,
            "context": self.context,
        }


# ── Must-not-assert rules ────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """One thing a situation's output may never say.

    These cannot be derived, generalised, or inferred by the framework.
    Somebody with domain knowledge writes them per situation, and they
    are the difference between a tool and a lawsuit. The framework's
    only job is to enforce them on every string that reaches a person.
    """

    pattern: str
    why: str

    def hits(self, text: str) -> bool:
        return re.search(self.pattern, text, re.IGNORECASE) is not None


class MustNotAssert(Exception):
    """Raised when generated copy would assert something forbidden."""


# ── The situation itself ─────────────────────────────────────────────


@dataclass(frozen=True)
class Situation:
    """A problem the helper knows how to think about.

    `assess` is the only per-situation code. It takes fully resolved
    priors as a plain dict and returns an Outcome. It must be pure and
    cheap: the sensitivity engine calls it once per candidate value of
    every unresolved field, and it must give the same answer every time
    so an answer can be re-derived and disputed.
    """

    key: str
    name: str
    one_liner: str
    fields: tuple[Field, ...]
    assess: Callable[[dict], Outcome]
    must_not_assert: tuple[Rule, ...] = ()
    # Whether this situation is shown to the public. A situation whose
    # evidence is not sourced yet still works in development and still
    # passes lint — it just does not appear for a person who came here
    # for help. Without this the registry is all-or-nothing, and shipping
    # the finished renewal advisor would mean shipping an unfinished
    # lease-break alongside it.
    live: bool = False
    # Cheap keyword classification, used when no API key is configured
    # so the whole surface still works without an LLM.
    triggers: tuple[str, ...] = ()
    intake_hint: str = ""

    def field(self, key: str) -> Field | None:
        for f in self.fields:
            if f.key == key:
                return f
        return None
