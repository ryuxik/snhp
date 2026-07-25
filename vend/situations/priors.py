"""Priors resolution — layer 3.

THE HARD RULE OF THIS MODULE: a value that a judgment depends on comes
from the person, a verified data module, or a verified rules module.
Never from a language model's memory.

The intake layer (layer 4) is allowed to read a number out of somebody's
prose, but what it produces is tagged INFERRED, which is not in FIRM —
so the framework treats it as a guess, shows it back for confirmation,
and the sensitivity engine keeps asking about it until a human agrees.
That is the whole safety story of putting a chat box in front of a
deterministic core.

Degrading is always allowed and always disclosed. An unknown metro falls
back to national context rather than inventing a local figure; an
unresolved field becomes a question rather than a confident default.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _field

from vend.situations import schema
from vend.situations.schema import (
    ASSUMED, FIRM, INFERRED, STATED, UNKNOWN, Assumption, Field, Situation,
)


@dataclass
class Priors:
    """Resolved values plus where each one came from.

    `values` is what gets handed to a situation's assess function — a
    plain dict, so situation authors never import this module. Everything
    else here is the framework's bookkeeping.
    """

    values: dict = _field(default_factory=dict)
    provenance: dict = _field(default_factory=dict)
    confidence: dict = _field(default_factory=dict)
    quoted: dict = _field(default_factory=dict)   # the user's own words, per field

    def get(self, key, default=None):
        return self.values.get(key, default)

    def source(self, key: str) -> str:
        return self.provenance.get(key, UNKNOWN)

    def is_firm(self, key: str) -> bool:
        """True when a judgment may rest on this value without asking."""
        return self.source(key) in FIRM

    def with_value(self, key, value) -> "Priors":
        """A copy with one value replaced — used by the sensitivity sweep."""
        return Priors(
            values={**self.values, key: value},
            provenance=dict(self.provenance),
            confidence=dict(self.confidence),
            quoted=dict(self.quoted),
        )

    def unresolved(self, situation: Situation) -> list[str]:
        """Fields a judgment should not silently rest on.

        Both genuinely-missing fields and LLM-inferred ones. The latter
        matters more than it looks: an inferred value that changes the
        answer is exactly the case where a smooth chat interface would
        quietly get somebody's lease wrong.
        """
        out = []
        for f in situation.fields:
            if f.never_ask:
                continue
            if self.values.get(f.key) is None:
                out.append(f.key)
            elif not self.is_firm(f.key):
                out.append(f.key)
        return out

    def assumptions(self, situation: Situation) -> list[Assumption]:
        """Every resolved prior, for the confirm-the-picture panel."""
        out = []
        for f in situation.fields:
            if f.key not in self.values or self.values[f.key] is None:
                continue
            out.append(
                Assumption(
                    key=f.key,
                    label=f.label,
                    value_display=f.display(self.values[f.key]),
                    provenance=self.source(f.key),
                    editable=not f.never_ask,
                )
            )
        return out


def resolve(
    situation: Situation,
    stated: dict | None = None,
    provenance: dict | None = None,
    confidence: dict | None = None,
    quoted: dict | None = None,
) -> Priors:
    """Merge what we know into one struct, tagging every field.

    Precedence, highest first: what the person stated, what the intake
    layer inferred, the field's declared default. Data and rules modules
    are not consulted here — they are the situation's own business, and
    they tag their own provenance inside assess.
    """
    stated = dict(stated or {})
    provenance = dict(provenance or {})
    confidence = dict(confidence or {})
    quoted = dict(quoted or {})

    values: dict = {}
    prov: dict = {}

    for f in situation.fields:
        if f.key in stated and stated[f.key] is not None:
            values[f.key] = _coerce(f, stated[f.key])
            prov[f.key] = provenance.get(f.key, STATED)
        elif f.default is not None:
            values[f.key] = f.default
            prov[f.key] = ASSUMED
        else:
            values[f.key] = None
            prov[f.key] = UNKNOWN

    return Priors(values=values, provenance=prov, confidence=confidence, quoted=quoted)


def _coerce(f: Field, raw):
    """Turn whatever arrived into the field's type, or None.

    Deliberately forgiving on the way in and strict about the result:
    "$3,400/mo" becomes 3400, and anything unparseable becomes None (a
    question) rather than a zero (a silent wrong answer).
    """
    if raw is None:
        return None
    if f.kind == schema.BOOL:
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("true", "yes", "y", "1"):
            return True
        if s in ("false", "no", "n", "0"):
            return False
        return None
    if f.kind in (schema.MONEY, schema.MONTHS, schema.COUNT):
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return raw
        s = str(raw).replace(",", "").replace("$", "").strip()
        # keep the first numeric run: "3400/mo" -> 3400, "about 9" -> 9
        num = ""
        for ch in s:
            if ch.isdigit() or (ch == "." and "." not in num):
                num += ch
            elif num:
                break
        if not num:
            return None
        try:
            v = float(num)
        except ValueError:
            return None
        return int(v) if f.kind != schema.MONTHS else v
    if f.kind == schema.CHOICE:
        s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
        allowed = {v for v, _ in f.options}
        return s if s in allowed else None
    if f.kind == schema.METRO:
        return str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    return str(raw).strip() or None
