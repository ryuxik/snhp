"""Anonymous, bucketed records of what the tool said and what happened.

WHY COLLECT ANYTHING
`writing/rent-no-source.md` went looking for what landlords actually
concede — rent versus a free month versus a waived fee versus a term
deal — and found nothing. Not a thin literature: a blank. The largest
renter survey in the country never asks whether you negotiated. So the
one dataset that would settle the question does not exist, and a tool
that gives this advice to real people is standing on the collection
mechanism for it.

THE DESIGN RULE
Anonymity is enforced at a choke point, not by remembering to be
careful. Everything written to disk passes through `redact()`, which is
an ALLOWLIST: a field that is not explicitly named and explicitly
bucketed does not survive. Add a field to the situation schema and it is
absent from telemetry until somebody deliberately adds it here — the
failure mode is losing data, never leaking it.

WHAT IS NEVER STORED
- The person's own words. The free-text description is not passed to
  this module at all, so it cannot be written by accident. That is the
  single largest PII risk in the product and it is handled by making the
  data structurally unavailable rather than by filtering it.
- Any exact figure. Rents, months, percentages and dollar amounts are
  bucketed before they are written. An exact rent plus a metro plus a
  lease length is close to a fingerprint; a band is not.
- IP address, user agent, referrer, or any request header.
- Cookies, accounts, device identifiers, or anything that links two
  sessions to one person.
- Timestamps finer than the calendar MONTH. Day granularity was the
  weakest link in the first cut of this: a rare band combination plus
  a specific date is close to a singleton even when every field is
  coarse ("the one person in Buffalo who used this on a Tuesday").

WHAT IS STORED
The situation, the metro (an area of millions of people — the same
granularity Zillow publishes), the calendar month, coarse bands for
money and time, the verdict, which questions the framework decided to ask, and — if the
person chooses to come back and say — what the landlord actually did.

THE RECEIPT
A record carries a random token so a person can later report an outcome
against it. The token joins an outcome to a bucketed row and to nothing
else: no session, no address, no return path to a human. It is issued
once, never stored anywhere near an identifier, and is useless to anyone
who does not already hold it.

OFF BY DEFAULT. The operator opts in with SNHP_HELPER_TELEMETRY=1, and a
person can opt out per request regardless — checked BEFORE anything is
built, not before it is written.

THE STANDARD THIS HAS TO MEET
Two exposures, and the second is the one that actually bites.

1. Privacy law. The CPRA test for deidentified data is not "we removed
   the name": it requires reasonable measures against reassociation, a
   PUBLIC COMMITMENT to keep it deidentified, and no attempt to
   reidentify. `COMMITMENT` below is that public commitment, and it is
   served from the API so it cannot quietly diverge from the code. GDPR
   Recital 26 asks whether reidentification is reasonably likely by any
   means — with no free text, no IP, no cookie, no exact value and
   month-level time, it is not.

2. FTC Act §5. Saying "nothing is stored" while storing something is a
   deceptive practice, and it does not matter how anonymous the thing
   stored is. That is the failure mode most likely to produce a letter,
   and it is a copy problem rather than a code problem: every page that
   made a no-storage promise has to stop making it on the same commit
   that turns this on. See PRIVACY.md for the reidentification analysis.

Nothing here is legal advice about ourselves either — it is the analysis
a lawyer would want to start from, written down so it can be checked.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone

# ── Buckets ──────────────────────────────────────────────────────────
# Coarse on purpose. Each band holds a large enough population that a
# row is not a person, and the questions this data exists to answer
# ("do soft markets concede more often?") do not need more resolution.

MONEY_BANDS = (
    (1000, "under_1000"), (1500, "1000_1499"), (2000, "1500_1999"),
    (3000, "2000_2999"), (4500, "3000_4499"),
)
MONEY_TOP = "4500_plus"

PCT_BANDS = (
    (0.0001, "none_or_decrease"), (3, "0_3"), (5, "3_5"),
    (8, "5_8"), (15, "8_15"),
)
PCT_TOP = "15_plus"

MONTH_BANDS = (
    (3, "under_3"), (6, "3_6"), (12, "6_12"), (24, "12_24"), (48, "24_48"),
)
MONTH_TOP = "48_plus"


def _band(value, bands, top) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    for edge, label in bands:
        if v < edge:
            return label
    return top


def money_band(v) -> str | None:
    return _band(v, MONEY_BANDS, MONEY_TOP)


def pct_band(v) -> str | None:
    return _band(v, PCT_BANDS, PCT_TOP)


def month_band(v) -> str | None:
    return _band(v, MONTH_BANDS, MONTH_TOP)


# ── The allowlist ────────────────────────────────────────────────────
# Field key -> the bucketer that field must pass through. A field absent
# from this table is absent from telemetry, full stop. Free text has no
# entry and never will.

FIELD_BUCKETS = {
    # rent_renewal
    "metro": "metro",
    "current_rent": money_band,
    "offered_rent": money_band,
    "months_at_address": month_band,
    # lease_break
    "monthly_rent": money_band,
    "months_remaining": month_band,
    "termination_fee_months": month_band,
    "security_deposit": money_band,
    "has_termination_clause": bool,
    "replacement_tenant_ready": bool,
    "lease_allows_transfer": "choice",
    "move_out_reason": "choice",
}

# Choice fields whose values are a closed vocabulary and therefore safe
# to record verbatim. Anything not listed is dropped rather than guessed.
SAFE_CHOICES = {
    "lease_allows_transfer": {"yes", "no", "unknown"},
    "move_out_reason": {"job", "cost", "military", "safety",
                        "habitability", "other"},
}

RECORD_KEYS = {
    "v", "month", "receipt", "situation", "verdict", "inputs",
    "asked", "route_offered", "stated_count", "inferred_count",
    "assumed_count", "used_llm", "outcome",
}


def enabled() -> bool:
    return os.environ.get("SNHP_HELPER_TELEMETRY", "").strip().lower() in (
        "1", "true", "yes", "on")


# The public commitment CPRA deidentification requires. Served from
# /v1/helper/privacy so the promise and the code ship together.
COMMITMENT = (
    "We do not attempt to reidentify anyone from this data, we do not "
    "sell it, we do not share it with data brokers or advertisers, and we "
    "do not combine it with anything that could identify a person. It is "
    "kept deidentified for as long as we keep it, and we publish the "
    "reidentification analysis rather than asking you to take our word."
)

NOT_ADVICE = (
    "This is information, not legal or financial advice, and using it does "
    "not create a professional relationship of any kind. Your lease and "
    "your state's law decide your position; we can only tell you what to "
    "go and check. For anything contested, talk to a tenant attorney or a "
    "legal-services organisation — many are free."
)


def _month() -> str:
    """Calendar month. See the note above on why this is not the day."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def redact(
    *,
    situation_key: str,
    values: dict,
    provenance: dict,
    verdict: str,
    asked: list,
    route_offered: str | None,
    used_llm: bool,
) -> dict:
    """Build the only shape that is ever written. Allowlist, not filter.

    Note what this signature does NOT accept: the person's description,
    a request, an address, a name, an identifier of any kind. The unsafe
    data is not passed in, so it cannot be written out.
    """
    inputs: dict = {}
    for key, bucket in FIELD_BUCKETS.items():
        raw = (values or {}).get(key)
        if raw is None:
            continue
        if bucket == "metro":
            # A metro is an area of millions. Normalised, and only ever
            # a metro — never a neighbourhood, borough or postcode.
            inputs[key] = str(raw).lower().replace(" ", "_")[:40]
        elif bucket == "choice":
            allowed = SAFE_CHOICES.get(key, set())
            if str(raw) in allowed:
                inputs[key] = str(raw)
        elif bucket is bool:
            inputs[key] = bool(raw)
        else:
            b = bucket(raw)
            if b is not None:
                inputs[key] = b

    # The renewal increase, as a band. Derived rather than stored raw,
    # because the size of the ask is the interesting variable.
    cur, off = (values or {}).get("current_rent"), (values or {}).get("offered_rent")
    try:
        if cur and off and float(cur) > 0:
            inputs["increase_pct"] = pct_band((float(off) - float(cur)) / float(cur) * 100)
    except (TypeError, ValueError):
        pass

    prov = provenance or {}
    counts = {"stated": 0, "inferred": 0, "assumed": 0}
    for k in (values or {}):
        p = prov.get(k)
        if p in counts:
            counts[p] += 1

    return {
        "v": 1,
        "month": _month(),                   # calendar month, never finer
        "receipt": secrets.token_hex(8),     # joins to a band, to nothing else
        "situation": str(situation_key)[:40],
        "verdict": str(verdict)[:16],
        "inputs": inputs,
        # Which questions the framework decided were worth asking. This
        # is the record that tells us whether the sensitivity engine is
        # asking about the right things.
        "asked": sorted(str(a)[:40] for a in (asked or []))[:12],
        "route_offered": (str(route_offered)[:40] if route_offered else None),
        "stated_count": counts["stated"],
        "inferred_count": counts["inferred"],
        "assumed_count": counts["assumed"],
        "used_llm": bool(used_llm),
        "outcome": None,                     # filled in only if they tell us
    }


# ── Outcomes: the part nobody has ────────────────────────────────────

OUTCOMES = {
    "no_reply": "They never replied",
    "refused": "They said no to everything",
    "concession": "Got a free month or a move-in style credit",
    "fee_waiver": "Got a fee waived",
    "rent_reduction": "Got the rent lowered or held flat",
    "term_deal": "Got a longer term at a better rate",
    "released": "Got released from the lease",
    "signed_anyway": "Signed as offered",
    "still_waiting": "Still waiting",
    "other": "Something else",
}


def redact_outcome(receipt: str, outcome: str, amount=None) -> dict | None:
    """An anonymous report of what actually happened.

    Rejects anything not in the closed vocabulary rather than storing a
    free-text explanation — "other" with no detail is worth more than a
    text field somebody types their address into.
    """
    if not receipt or not isinstance(receipt, str):
        return None
    rec = "".join(c for c in receipt if c in "0123456789abcdef")[:32]
    if len(rec) < 8 or outcome not in OUTCOMES:
        return None
    return {
        "v": 1,
        "month": _month(),
        "receipt": rec,
        "outcome": outcome,
        "amount": money_band(amount),
    }


# ── Storage ──────────────────────────────────────────────────────────


def _path(name: str) -> str:
    base = os.environ.get("SNHP_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, name)


def write(record: dict, filename: str = "helper_telemetry.jsonl") -> bool:
    """Append one record, if and only if it is well-formed.

    The key check is not paranoia about our own code — it is the thing
    that makes adding a field to a situation safe. A new key arrives
    here only when somebody put it in the allowlist on purpose.
    """
    if not enabled() or not record:
        return False
    stray = set(record) - RECORD_KEYS - {"amount"}
    if stray:
        return False
    try:
        with open(_path(filename), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


DISCLOSURE = (
    "We keep an anonymous record of what this tool was asked and what it "
    "said, so it can be made less wrong. Never your description in your own "
    "words, never an exact rent or date, never your address, never your IP, "
    "no account and no cookie. What's kept is the situation, your metro, "
    "broad bands instead of figures, and the answer you were given. If you "
    "come back and tell us what your landlord actually did, that goes in "
    "too — and that particular question has never been measured by anyone, "
    "which is most of why this is here."
)
