"""Rent renewal, expressed in the situation schema.

This is an ADAPTER. `vend/rent/advisor.py` is not modified and not
imported anywhere else in the framework — it stays the deterministic
core it already was, and this file is the declaration of what it needs
and what it may never say.

That is the shape every situation takes: fields (data), a rules list
(data), and a pure function that maps resolved priors to the output
contract. If a second situation could not be added the same way, the
framework wouldn't be real — see lease_break/.
"""

from __future__ import annotations

from vend.rent import advisor as _advisor
from vend.rent import metros as _metros
from vend.situations.schema import (
    BOOL, CHOICE, COUNT, METRO, MONEY, MONTHS,
    Field, Outcome, Route, Rule, Situation,
)

# The metro table, as a closed vocabulary for the intake model.
_METRO_KEYS = tuple(sorted(_metros.METROS))

FIELDS = (
    Field(
        key="metro",
        label="Where you live",
        kind=METRO,
        required=True,
        vocabulary=_METRO_KEYS,
        help="Metro area. Somewhere we don't have data for falls back to national figures.",
    ),
    Field(
        key="current_rent",
        label="What you pay now",
        kind=MONEY,
        required=True,
        unit="per month",
    ),
    Field(
        key="offered_rent",
        label="What they're asking for the renewal",
        kind=MONEY,
        required=True,
        unit="per month",
    ),
    Field(
        key="months_at_address",
        label="How long you've lived there",
        kind=COUNT,
        required=True,
        unit="months",
        help="Tenure is the strongest single predictor of whether asking works.",
        # Straddles the 24-month threshold where the odds roughly double,
        # so the sweep can see the flip rather than sampling around it.
        sweep=(6, 18, 30, 48),
    ),
)


# Written against the same primary-source review that produced
# vend/rent/jurisdictions.py. Every one of these is a sentence that
# would send somebody into a confrontation holding a false premise.
MUST_NOT_ASSERT = (
    # The lookbehinds matter. "find out whether your apartment is rent
    # regulated" is the exact framing this whole module is built on;
    # "your apartment is rent regulated" is the thing that must never be
    # said. Same distinction as the withholding rules below: the rule
    # targets the assertive construction, not the keyword.
    Rule(r"(?<!whether )(?<!\bif )\byou are (rent[- ])?(stabilized|regulated|controlled)\b",
         "regulation status depends on unit facts we cannot see"),
    Rule(r"(?<!whether )(?<!\bif )\byour (apartment|unit|building) is "
         r"(rent[- ])?(stabilized|regulated)\b",
         "same — we can only say how to check"),
    Rule(r"\b(this|the) increase is (illegal|unlawful|not allowed)\b",
         "an increase above a guideline is not automatically an overcharge"),
    Rule(r"\bthe legal (cap|maximum) (is|on your rent)\b",
         "no cap may be asserted; lawful increases can stack above a guideline"),
    # Advisory constructions only. The renewal advisor's own NYC copy
    # correctly warns "Never withhold rent on the strength of anything
    # here" — a blunter rule would have blocked the warning.
    Rule(r"\b(you (can|could|should|may|might)|consider|try|feel free to)\s+"
         r"(stop|cease|quit)\s+paying\b",
         "never advise withholding rent — the official guidance is pay and file"),
    Rule(r"\b(you (can|could|should|may|might)|consider|try|feel free to)\s+withhold",
         "never advise withholding rent"),
    Rule(r"\byou (don'?t|do not) (have to |need to )?(pay|owe)\b",
         "we cannot tell somebody a payment isn't owed"),
    Rule(r"\bgood cause (eviction )?caps\b",
         "Good Cause is a rebuttable presumption raised as a defense, not a cap"),
    Rule(r"\bwe guarantee\b|\byou will (get|win)\b",
         "no outcome may be promised"),
    Rule(r"\bthis is legal advice\b",
         "information, not legal advice"),
)


# Nobody has ever felt "moderate" about their rent.
_VERDICT_LABEL = {
    "strong": "worth asking",
    "moderate": "worth a short, friendly ask",
    "weak": "just sign it",
}

_EASE_FROM_ADVISOR = {"easiest": "easiest", "moderate": "moderate", "hardest": "hardest"}


def assess(values: dict) -> Outcome:
    """Resolved priors -> the fixed output contract.

    Pure and cheap: the sensitivity engine calls this once per candidate
    value of every unresolved field.
    """
    a = _advisor.assess(
        metro=values["metro"],
        current_rent=int(values["current_rent"]),
        offered_rent=int(values["offered_rent"]),
        months_at_address=int(values["months_at_address"]),
    )

    routes = [
        Route(
            key=ask.key,
            label=ask.headline,
            detail=ask.detail,
            why=ask.why,
            ease=_EASE_FROM_ADVISOR.get(ask.ease, "moderate"),
            est_value_usd=ask.est_annual_value,
            ask_phrase=ask.ask_phrase,
        )
        for ask in a.asks
    ]

    legal = a.legal or {}
    verify = list(legal.get("how_to_verify", []))
    if legal.get("may_be_regulated") and legal.get("worth_checking_if"):
        verify.append({
            "action": "Check whether the unit might be regulated",
            "where": legal.get("jurisdiction", "your local rent board"),
            "note": " ".join(legal["worth_checking_if"][:2]),
        })

    # What you are on the hook for if you do nothing. For a renewal that
    # is simply the increase — stated plainly so the number the person
    # is deciding about is never implicit.
    exposure = []
    if a.annual_cost > 0:
        exposure.append(
            f"Signing as offered costs you ${a.annual_cost:,} more over the "
            f"next year than you pay today."
        )
    exposure.append(_advisor.DELAY_PENALTY_NOTE)
    # The credible-signal lesson, and the single most important sentence
    # the advisor produces. An earlier version of this adapter dropped it
    # on the floor: it lives in the advisor's `shopping_around` key and
    # had no slot in the contract. "Be credible" is the action; asking is
    # only how you deliver it, and a claim nobody can check is worth
    # about nothing.
    exposure.append(_advisor.SHOPPING_AROUND_NOTE)
    # Same category as the note above — what actually moves a landlord —
    # and the one that runs against intuition.
    exposure.append(_advisor.NON_PRICE_MOVER_NOTE)

    # The 61% figure is what turns odds into a reason to act — it is the
    # difference between a calculator and advice, so it rides with the
    # odds rather than being left in context for nobody to render.
    odds_basis = (
        f"{a.odds_basis} About "
        f"{_advisor.SHARE_WHO_NEVER_ASK * 100:.0f}% of tenants never ask at all."
    )

    # Companion to SHOPPING_AROUND_NOTE, which sits in `exposure`.
    # Proving an alternative helps you individually and would hurt
    # renters collectively if it became standard. The mechanism is
    # unravelling, which is textbook — so nothing here is quoted from
    # our own simulation, whose accuracy checks failed.
    caveats = list(a.caveats)
    caveats.append(
        "A specific, checkable alternative is worth far more than a vague "
        "one — partly because so few people bring one. If showing proof ever "
        "became normal, saying nothing would start to read as having nothing, "
        "and renters as a group would end up worse off than when none of it "
        "could be checked. Worth using now; worth knowing what it is."
    )

    return Outcome(
        verdict=a.verdict,
        verdict_label=_VERDICT_LABEL[a.verdict],
        headline=a.headline,
        routes=routes,
        next_step=a.next_step,
        message=a.message,
        exposure=exposure,
        verify=verify,
        caveats=caveats,
        odds=a.odds_if_you_ask,
        odds_basis=odds_basis,
        evidence_note=_advisor.EVIDENCE_NOTE,
        # What is at stake per year — the scalar the sensitivity engine
        # differences. Denominated in dollars/year like every situation.
        metric_usd=float(a.annual_cost),
        context={
            "market": a.market,
            "legal": legal,
            "next_step": a.next_step,
            "share_who_never_ask": _advisor.SHARE_WHO_NEVER_ASK,
        },
    )


SITUATION = Situation(
    key="rent_renewal",
    name="Rent renewal offer",
    one_liner="You've been offered a renewal and want to know if the number is fair.",
    fields=FIELDS,
    assess=assess,
    must_not_assert=MUST_NOT_ASSERT,
    # Live: every figure is sourced and this advice already ships at
    # /rent. The adapter changes the packaging, not the evidence.
    live=True,
    triggers=(
        "renewal", "renew", "raising my rent", "rent increase", "lease is up",
        "renewal offer", "they want to raise", "going up",
    ),
    intake_hint=(
        "The person is holding a renewal offer and deciding whether to sign "
        "or push back. Look for: their current rent, the offered rent, how "
        "long they have lived there, and the city."
    ),
)


def known_metros() -> list[dict]:
    """The metro picker, served from the table the assessment uses."""
    return [
        {"key": k, "name": m.name, "tier": m.tier}
        for k, m in sorted(_metros.METROS.items(), key=lambda kv: kv[1].name)
    ]
