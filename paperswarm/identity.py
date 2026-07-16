"""Deterministic card identity from a listing (SPEC.md: PERFECT IDENTITY).

PSA cert numbers are the anchor — "no fuzzy matching" (SPEC "Venue and why").
Regex/keyword parse is authoritative; an LLM fallback exists only as an
interface stub (SPEC swarm: "LLM usage: parsing/identity extraction only").
Pricing never touches an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# PSA cert numbers are 8-9 digit integers (historically 7-9). Match a labeled
# cert first (highest confidence), then a bare long integer near "PSA".
_CERT_LABELLED = re.compile(
    r"(?:cert(?:ification)?\s*(?:#|no\.?|number)?\s*[:#]?\s*)(\d{7,9})",
    re.IGNORECASE,
)
_CERT_NEAR_PSA = re.compile(r"psa[^0-9]{0,6}cert[^0-9]{0,6}(\d{7,9})", re.IGNORECASE)

# Grade: "PSA 10", "PSA10", "PSA GEM MT 10". Grades are 1-10 (half grades rare).
_GRADE = re.compile(r"psa\s*(?:gem\s*mt?|mint|nm-?mt)?\s*(10|[1-9](?:\.5)?)\b", re.IGNORECASE)

# Card number: "#11", "No. 11", "11/108". Prefer a '#'-prefixed token.
_CARD_NUM_HASH = re.compile(r"#\s*([0-9]{1,3}[a-z]?)\b", re.IGNORECASE)
_CARD_NUM_SLASH = re.compile(r"\b([0-9]{1,3})\s*/\s*[0-9]{1,3}\b")

# Known Pokémon-name heads help pull card_name out of a noisy title. This is a
# convenience shortlist for the launch niche, not an identity requirement — the
# grade+number+cert triple is what buckets comps.
_KNOWN_NAMES = (
    "umbreon vmax", "charizard vmax", "rayquaza vmax", "charizard",
    "blastoise", "venusaur", "pikachu", "mewtwo", "lugia", "umbreon",
    "espeon", "gengar", "gyarados", "dragonite", "snorlax",
)


@dataclass(frozen=True)
class Identity:
    """Parsed card identity. `comp_key` buckets sold comps (SPEC: cert-grade/card)."""
    card_name: str | None
    number: str | None
    grade: str | None
    cert: str | None
    confidence: str  # "cert" | "regex" | "partial" | "none"

    @property
    def comp_key(self) -> str | None:
        """Bucket key for comps: card_name|number|grade, normalized.

        Comps aggregate by card+grade, not by cert — every cert is a unique
        single copy, so a cert has at most one own-sale (SPEC SELL rule).
        Returns None when we cannot form a usable bucket.
        """
        if self.card_name and self.grade:
            num = self.number or "?"
            return f"{self.card_name.strip().lower()}|{num}|{self.grade}"
        return None

    @property
    def is_identified(self) -> bool:
        return self.comp_key is not None


def _find_grade(text: str) -> str | None:
    m = _GRADE.search(text)
    return m.group(1) if m else None


def _find_cert(text: str) -> str | None:
    m = _CERT_NEAR_PSA.search(text) or _CERT_LABELLED.search(text)
    return m.group(1) if m else None


def _find_number(text: str) -> str | None:
    m = _CARD_NUM_HASH.search(text)
    if m:
        return m.group(1)
    m = _CARD_NUM_SLASH.search(text)
    return m.group(1) if m else None


def _find_name(text: str) -> str | None:
    low = text.lower()
    for name in _KNOWN_NAMES:  # ordered longest/most-specific first
        if name in low:
            return name
    return None


def parse_identity(title: str, aspects: dict[str, str] | None = None) -> Identity:
    """Deterministic parse of (card_name, number, grade, cert) from a listing.

    SPEC PERFECT IDENTITY: cert-number anchored, no fuzzy matching. `aspects`
    are eBay `localizedAspects` (name->value) from item detail, which are
    higher-confidence than the title when present.
    """
    aspects = {k.lower(): v for k, v in (aspects or {}).items()}

    # Structured aspects win when present.
    cert = aspects.get("certification number") or _find_cert(title)
    grade = aspects.get("grade") or _find_grade(title)
    number = aspects.get("card number") or _find_number(title)
    name = aspects.get("card name")
    if name:
        name = name.strip().lower()
    else:
        name = _find_name(title)

    if cert and grade and name:
        confidence = "cert"
    elif grade and name:
        confidence = "regex"
    elif grade or name:
        confidence = "partial"
    else:
        confidence = "none"

    return Identity(
        card_name=name,
        number=str(number) if number is not None else None,
        grade=str(grade) if grade is not None else None,
        cert=str(cert) if cert is not None else None,
        confidence=confidence,
    )


def llm_identity_stub(title: str, aspects: dict[str, str] | None = None) -> Identity:
    """Interface stub for the haiku-class identity fallback (NOT wired in P1).

    SPEC swarm: LLM is for parsing/identity extraction only. Phase 1 ships the
    deterministic parser as the single source of truth; this signature reserves
    the fallback so Phase 2 can drop in a metered haiku call (charged via
    config.LLM_CALL_COST_USD) without changing callers. Raises to make any
    accidental reliance loud.
    """
    raise NotImplementedError(
        "LLM identity fallback is a Phase-1 interface stub only; "
        "deterministic parse_identity() is authoritative."
    )
